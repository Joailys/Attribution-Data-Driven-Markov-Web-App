from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import tempfile
import os
import json
from google.cloud import bigquery
from google.oauth2 import service_account

app = FastAPI()

# Autoriser le CORS pour le développement local du frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    project_id: str
    query: str
    credentials_json: Optional[str] = None  # JSON encodé ou sous forme de chaîne

@app.post("/run_query/")
def run_query(req: QueryRequest):
    """
    Exécute une requête BigQuery à partir des informations fournies par l'utilisateur.
    """
    try:
        if req.credentials_json:
            creds_dict = json.loads(req.credentials_json)
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
            client = bigquery.Client(project=req.project_id, credentials=credentials)
        else:
            client = bigquery.Client(project=req.project_id)
        df = client.query(req.query).to_dataframe()
        return {"columns": df.columns.tolist(), "data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lors de l'exécution de la requête : {str(e)}")

@app.post("/analyze/")
def analyze(data: dict):
    try:
        df = pd.DataFrame(data["data"])
        # Récupération du mapping des colonnes
        id_col = data.get("id_col")
        source_col = data.get("source_col")
        date_col = data.get("date_col")
        first_click_col = data.get("first_click_col")
        last_click_col = data.get("last_click_col")
        post_click_col = data.get("post_click_col")

        # Vérification des colonnes obligatoires
        for col, label in [(id_col, "identifiant de conversion"), (source_col, "source/medium"), (date_col, "date")]:
            if not col or col not in df.columns:
                return {"erreur": f"La colonne '{label}' ('{col}') est absente des données."}

        # Conversion des dates
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col])

        # Conversion des colonnes booléennes si présentes
        for col_name, user_col in [("first_click", first_click_col), ("last_click", last_click_col), ("post_click", post_click_col)]:
            if user_col and user_col in df.columns:
                if df[user_col].dtype == 'object':
                    df[user_col] = df[user_col].map({'TRUE': True, 'FALSE': False, True: True, False: False})
            else:
                df[col_name] = False  # Si pas de colonne, valeur False par défaut

        # Création des chemins de conversion
        def create_conversion_paths(df, id_col, source_col, date_col, first_click_col, last_click_col):
            # Toujours utiliser date_col transmis
            df_sorted = df.sort_values([id_col, date_col])
            path_data = []
            for conv_id, group in df_sorted.groupby(id_col):
                channel_path = []
                for _, row in group.iterrows():
                    channel_info = (
                        row[source_col],
                        bool(row[first_click_col]) if first_click_col and first_click_col in df.columns else False,
                        bool(row[last_click_col]) if last_click_col and last_click_col in df.columns else False
                    )
                    channel_path.append(channel_info)
                if not channel_path:
                    continue
                path_data.append({
                    'order_id': conv_id,
                    'path': channel_path,
                    'path_length': len(channel_path),
                    'first_touch': channel_path[0][0],
                    'last_touch': channel_path[-1][0],
                    'path_string': ' -> '.join([item[0] for item in channel_path])
                })
            return pd.DataFrame(path_data)

        path_df = create_conversion_paths(df, id_col, source_col, date_col, first_click_col, last_click_col)

        # Création de la matrice de transition de Markov
        from collections import defaultdict, Counter
        def create_transition_matrix(path_df):
            transitions = []
            for path in path_df['path']:
                channels = [item[0] for item in path]
                for i in range(len(channels) - 1):
                    transitions.append((channels[i], channels[i+1]))
                transitions.append((channels[-1], 'conversion'))
            transition_counts = Counter(transitions)
            transition_dict = defaultdict(lambda: defaultdict(int))
            for (from_state, to_state), count in transition_counts.items():
                transition_dict[from_state][to_state] = count
            transition_probs = {}
            for from_state, to_states in transition_dict.items():
                total = sum(to_states.values())
                transition_probs[from_state] = {
                    to_state: count / total for to_state, count in to_states.items()
                }
            return transition_probs

        transition_probs = create_transition_matrix(path_df)

        # Calcul de l'attribution data-driven
        def calculate_attribution(transition_probs, path_df):
            all_channels = set()
            for path in path_df['path']:
                for item in path:
                    all_channels.add(item[0])
            first_touch_counts = Counter(path_df['first_touch'])
            total_paths = len(path_df)
            start_probs = {channel: count/total_paths for channel, count in first_touch_counts.items()}
            def calculate_conversion_prob(trans_probs, start_p, available_channels):
                state_probs = {channel: 0 for channel in available_channels}
                state_probs['conversion'] = 0
                for channel, prob in start_p.items():
                    if channel in available_channels:
                        state_probs[channel] = prob
                if sum(state_probs.values()) == 0:
                    return 0
                total_prob = sum(state_probs.values())
                if total_prob > 0:
                    for channel in state_probs:
                        if channel != 'conversion':
                            state_probs[channel] /= total_prob
                for _ in range(100):
                    new_probs = {state: 0 for state in state_probs}
                    new_probs['conversion'] = state_probs['conversion']
                    for from_state, to_states in trans_probs.items():
                        if from_state in available_channels:
                            for to_state, prob in to_states.items():
                                if to_state in new_probs:
                                    new_probs[to_state] += state_probs[from_state] * prob
                    diff = abs(new_probs['conversion'] - state_probs['conversion'])
                    if diff < 1e-6:
                        break
                    state_probs = new_probs
                return state_probs['conversion']
            base_conv_prob = calculate_conversion_prob(transition_probs, start_probs, all_channels)
            removal_effects = {}
            for channel in all_channels:
                channels_without_channel = all_channels - {channel}
                mod_conv_prob = calculate_conversion_prob(
                    transition_probs, start_probs, channels_without_channel
                )
                removal_effect = base_conv_prob - mod_conv_prob
                removal_effects[channel] = removal_effect
            total_effect = sum(max(0, effect) for effect in removal_effects.values())
            if total_effect > 0:
                attribution = {
                    channel: max(0, effect) / total_effect
                    for channel, effect in removal_effects.items()
                }
            else:
                attribution = {channel: 1/len(all_channels) for channel in all_channels}
            return attribution, base_conv_prob

        attribution, base_conv_prob = calculate_attribution(transition_probs, path_df)
        attribution_df = pd.DataFrame({
            'canal': list(attribution.keys()),
            'attribution': list(attribution.values())
        }).sort_values('attribution', ascending=False)

        # Analyse des chemins de conversion
        def analyze_conversion_paths(path_df, attribution):
            def calculate_path_score(path, attr_values):
                channels = [item[0] for item in path]
                return sum(attr_values.get(channel, 0) for channel in channels)
            path_df['score'] = path_df['path'].apply(lambda x: calculate_path_score(x, attribution))
            path_scores = path_df.groupby('path_string').agg(
                commandes=('order_id', 'count'),
                score_moyen=('score', 'mean'),
                longueur_moyenne=('path_length', 'mean')
            ).reset_index()
            path_scores['valeur'] = path_scores['commandes'] * path_scores['score_moyen']
            return path_scores.sort_values('valeur', ascending=False)

        path_scores = analyze_conversion_paths(path_df, attribution)

        # Analyse des combinaisons de canaux
        def analyze_channel_combinations(path_df, path_scores):
            pairs_data = []
            for _, row in path_scores.iterrows():
                path_string = row['path_string']
                channels = path_string.split(' -> ')
                if len(channels) >= 2:
                    for i in range(len(channels) - 1):
                        pairs_data.append({
                            'source': channels[i],
                            'destination': channels[i+1],
                            'valeur': row['valeur'],
                            'commandes': row['commandes']
                        })
            pairs_df = pd.DataFrame(pairs_data)
            if len(pairs_df) == 0:
                return pd.DataFrame(columns=['source', 'destination', 'valeur_totale', 'frequence'])
            pairs_agg = pairs_df.groupby(['source', 'destination']).agg(
                valeur_totale=('valeur', 'sum'),
                frequence=('commandes', 'sum')
            ).reset_index().sort_values('valeur_totale', ascending=False)
            return pairs_agg

        channel_pairs = analyze_channel_combinations(path_df, path_scores)

        # Retourner les résultats principaux en JSON
        return {
            "attribution": attribution_df.head(15).to_dict(orient="records"),
            "chemins": path_scores.head(10).to_dict(orient="records"),
            "combinaisons": channel_pairs.head(10).to_dict(orient="records"),
            "resume": {
                "nb_chemins": int(len(path_df)),
                "nb_canaux": int(len(attribution)),
                "base_conv_prob": float(base_conv_prob)
            }
        }
    except Exception as e:
        return {"erreur": f"Erreur lors de l'analyse : {str(e)}"}
