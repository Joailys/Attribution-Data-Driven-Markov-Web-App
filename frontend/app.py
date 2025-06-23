import streamlit as st
import pandas as pd
import requests
import json
import io
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Attribution Data-Driven", layout="wide")
st.title("Attribution Data-Driven (Markov) – Web App")

st.markdown("""
Téléversez votre fichier JSON de compte de service Google, saisissez l'ID du projet et une requête SQL BigQuery. L'application extraira les données et calculera l'attribution data-driven.
""")

if 'df' not in st.session_state:
    st.session_state.df = None
if 'id_col' not in st.session_state:
    st.session_state.id_col = None
if 'results' not in st.session_state:
    st.session_state.results = None

with st.form("query_form"):
    project_id = st.text_input("ID projet GCP", value="project-id")
    query = st.text_area("Requête SQL BigQuery", value="SELECT * FROM `project-ID.ressourceID.tableID` LIMIT 1000")
    credentials_file = st.file_uploader("Fichier JSON de compte de service Google", type=["json"])
    submitted = st.form_submit_button("Extraire les données")

if submitted:
    if not (project_id and query and credentials_file):
        st.error("Merci de fournir tous les champs.")
    else:
        creds_json = json.load(credentials_file)
        payload = {
            "project_id": project_id,
            "query": query,
            "credentials_json": json.dumps(creds_json)
        }
        with st.spinner("Extraction des données depuis BigQuery..."):
          resp = requests.post("https://attribution-data-driven-markov-web-app.onrender.com/run_query/", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            st.session_state.df = pd.DataFrame(data["data"])
            st.success(f"{len(st.session_state.df)} lignes extraites.")
        else:
            st.error(f"Erreur extraction : {resp.text}")

if st.session_state.df is not None:
    df = st.session_state.df
    st.markdown("#### Données extraites depuis BigQuery")
    st.dataframe(df)
    st.markdown("#### Mapping manuel des colonnes pour l'analyse")
    col1, col2 = st.columns(2)
    with col1:
        id_col = st.selectbox("Colonne identifiant de conversion", options=list(df.columns), key="id_col")
        source_col = st.selectbox("Colonne source/medium", options=list(df.columns), key="source_col")
        date_col = st.selectbox("Colonne date", options=list(df.columns), key="date_col")
    with col2:
        first_click_col = st.selectbox("Colonne first_click", options=[None]+list(df.columns), key="first_click_col")
        last_click_col = st.selectbox("Colonne last_click", options=[None]+list(df.columns), key="last_click_col")
        post_click_col = st.selectbox("Colonne post_click", options=[None]+list(df.columns), key="post_click_col")
    mapping = {
        "id_col": id_col,
        "source_col": source_col,
        "date_col": date_col,
        "first_click_col": first_click_col,
        "last_click_col": last_click_col,
        "post_click_col": post_click_col
    }
    if st.button("Lancer l'analyse d'attribution"):
        with st.spinner("Analyse d'attribution data-driven en cours..."):
            analyze_payload = {
                "data": df.to_dict('records'),
                **mapping
            }
            analyze_resp = requests.post(
                "https://attribution-data-driven-markov-web-app.onrender.com/analyze/",
                json=analyze_payload
            )
        if analyze_resp.status_code == 200:
            st.session_state.results = analyze_resp.json()
        else:
            st.error(f"Erreur analyse : {analyze_resp.text}")

if st.session_state.results is not None:
    if "erreur" in st.session_state.results:
        st.error(st.session_state.results["erreur"])
    else:
        st.header("Résultats de l'attribution data-driven")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Attribution par canal (top 15)")
            attr_df = pd.DataFrame(st.session_state.results["attribution"])
            st.dataframe(attr_df)
            csv = attr_df.to_csv(index=False).encode('utf-8')
            st.download_button("Télécharger CSV attribution", csv, "attribution.csv", "text/csv")
            # Barplot
            fig, ax = plt.subplots(figsize=(6,4))
            sns.barplot(y="canal", x="attribution", data=attr_df, ax=ax, palette="viridis")
            ax.set_title("Top canaux par attribution")
            st.pyplot(fig)
        with col2:
            st.subheader("Résumé")
            resume = st.session_state.results["resume"]
            st.markdown(f"**Nombre de chemins :** {resume['nb_chemins']}  ")
            st.markdown(f"**Nombre de canaux :** {resume['nb_canaux']}  ")
            st.markdown(f"**Probabilité de conversion de base :** {resume['base_conv_prob']:.4f}")
        st.subheader("Top chemins de conversion (top 10)")
        paths_df = pd.DataFrame(st.session_state.results["chemins"])
        st.dataframe(paths_df)
        csv2 = paths_df.to_csv(index=False).encode('utf-8')
        st.download_button("Télécharger CSV chemins", csv2, "chemins_conversion.csv", "text/csv")
        fig2, ax2 = plt.subplots(figsize=(8,5))
        sns.barplot(y="path_string", x="valeur", data=paths_df, ax=ax2, palette="viridis")
        ax2.set_title("Top chemins de conversion par valeur")
        st.pyplot(fig2)
        st.subheader("Top combinaisons de canaux (top 10)")
        comb_df = pd.DataFrame(st.session_state.results["combinaisons"])
        st.dataframe(comb_df)
        csv3 = comb_df.to_csv(index=False).encode('utf-8')
        st.download_button("Télécharger CSV combinaisons", csv3, "combinaisons_canaux.csv", "text/csv")
        fig3, ax3 = plt.subplots(figsize=(8,5))
        if not comb_df.empty:
            comb_df['combinaison'] = comb_df['source'] + ' → ' + comb_df['destination']
            sns.barplot(y="combinaison", x="valeur_totale", data=comb_df, ax=ax3, palette="viridis")
            ax3.set_title("Top combinaisons de canaux par valeur")
            st.pyplot(fig3)
