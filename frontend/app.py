// URL de base de l'API backend (Render)
const API_BASE_URL = 'https://attribution-data-driven-markov-web-app.onrender.com';

// État global de l'application
const appState = {
    bigqueryConnected: false,
    selectedDataset: null,
    mappingCompleted: false,
    configurationCompleted: false,
    currentStep: 'connection',
    projectId: '',
    serviceAccount: '',
    availableDatasets: [],
    datasetColumns: [],
    columnMapping: {},
    attributionResults: null
};

// Données de simulation
const sampleData = {
    datasets: [
        { id: 'marketing.attribution_data', name: 'Attribution Data', description: 'Données d\'attribution marketing' },
        { id: 'analytics.conversion_paths', name: 'Conversion Paths', description: 'Parcours de conversion' },
        { id: 'advertising.campaign_data', name: 'Campaign Data', description: 'Données de campagnes publicitaires' }
    ],
    sampleColumns: [
        'conversion_id', 'visitor_id', 'session_id', 'source', 'medium', 'campaign',
        'content', 'keyword', 'utm_id', 'interaction_datetime', 'conversion_datetime',
        'device_type', 'browser', 'country', 'revenue'
    ],
    sampleRows: [
        ['CONV_001', 'USER_123', 'SESS_456', 'google', 'cpc', 'summer_sale', 'ad_text_1', 'shoes', 'utm_001', '2024-06-01 10:30:00', '2024-06-01 15:45:00', 'desktop', 'chrome', 'FR', '89.99'],
        ['CONV_002', 'USER_789', 'SESS_012', 'facebook', 'social', 'brand_awareness', 'image_ad', '', 'utm_002', '2024-06-01 14:20:00', '2024-06-01 16:30:00', 'mobile', 'safari', 'US', '156.50'],
        ['CONV_003', 'USER_456', 'SESS_789', 'email', 'newsletter', 'weekly_promo', 'cta_button', '', 'utm_003', '2024-06-02 09:15:00', '2024-06-02 11:20:00', 'desktop', 'firefox', 'DE', '245.00']
    ]
};

const requiredColumns = [
    { name: 'conversion_id', description: 'Identifiant unique de la conversion', required: true },
    { name: 'source', description: 'Source du trafic (ex: google, facebook)', required: true },
    { name: 'medium', description: 'Medium du trafic (ex: cpc, organic)', required: true },
    { name: 'datetime', description: 'Date et heure de l\'interaction', required: true },
    { name: 'conversion_datetime', description: 'Date et heure de la conversion', required: true },
    { name: 'visitor_id', description: 'Identifiant unique du visiteur', required: true },
    { name: 'session_id', description: 'Identifiant unique de la session', required: true },
    { name: 'campaign', description: 'Nom de la campagne', required: false },
    { name: 'content', description: 'Contenu de l\'annonce', required: false },
    { name: 'keyword', description: 'Mot-clé', required: false },
    { name: 'utm_id', description: 'Identifiant UTM', required: false }
];

// Initialisation de l'application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    bindEvents();
    updateUIState();
});

function initializeApp() {
    // Définir les dates par défaut
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 3);
    
    document.getElementById('start-date').value = startDate.toISOString().split('T')[0];
    document.getElementById('end-date').value = endDate.toISOString().split('T')[0];
    
    // S'assurer que le dataset select est vide et désactivé
    const datasetSelect = document.getElementById('dataset-select');
    datasetSelect.innerHTML = '<option value="">Connexion BigQuery requise</option>';
    datasetSelect.disabled = true;
}

function bindEvents() {
    // Connexion BigQuery
    document.getElementById('test-connection').addEventListener('click', testBigQueryConnection);
    
    // Navigation dans les étapes
    document.querySelectorAll('.step').forEach(step => {
        step.addEventListener('click', (e) => {
            const stepName = e.currentTarget.dataset.step;
            if (!e.currentTarget.classList.contains('step--disabled')) {
                navigateToStep(stepName);
            }
        });
    });
    
    // Sélection dataset
    document.getElementById('dataset-select').addEventListener('change', onDatasetSelect);
    document.getElementById('validate-dataset').addEventListener('click', validateDataset);
    
    // Mapping
    document.getElementById('validate-mapping').addEventListener('click', validateMapping);
    
    // Configuration
    document.getElementById('launch-analysis').addEventListener('click', launchAnalysis);
}

function updateUIState() {
    // Mise à jour du statut de connexion
    const statusElement = document.getElementById('connection-status');
    const statusSpan = statusElement.querySelector('.status');
    
    if (appState.bigqueryConnected) {
        statusSpan.className = 'status status--success';
        statusSpan.innerHTML = '<span class="status-dot"></span>Connecté';
    } else {
        statusSpan.className = 'status status--error';
        statusSpan.innerHTML = '<span class="status-dot"></span>Déconnecté';
    }
    
    // Mise à jour des étapes
    updateStepStates();
    
    // Mise à jour des contrôles
    updateControlStates();
}

function updateStepStates() {
    const steps = document.querySelectorAll('.step');
    
    steps.forEach(step => {
        const stepName = step.dataset.step;
        step.classList.remove('step--active', 'step--completed', 'step--disabled');
        
        if (stepName === appState.currentStep) {
            step.classList.add('step--active');
        } else if (isStepCompleted(stepName)) {
            step.classList.add('step--completed');
        } else if (!isStepAccessible(stepName)) {
            step.classList.add('step--disabled');
        }
    });
}

function updateControlStates() {
    // Dataset select
    const datasetSelect = document.getElementById('dataset-select');
    const validateDatasetBtn = document.getElementById('validate-dataset');
    
    datasetSelect.disabled = !appState.bigqueryConnected;
    validateDatasetBtn.disabled = !appState.selectedDataset;
    
    // Mapping
    const validateMappingBtn = document.getElementById('validate-mapping');
    validateMappingBtn.disabled = !appState.selectedDataset || !hasRequiredMappings();
}

function isStepAccessible(stepName) {
    switch (stepName) {
        case 'connection':
            return true;
        case 'dataset':
            return appState.bigqueryConnected;
        case 'mapping':
            return appState.selectedDataset !== null;
        case 'config':
            return appState.mappingCompleted;
        case 'results':
            return appState.configurationCompleted;
        default:
            return false;
    }
}

function isStepCompleted(stepName) {
    switch (stepName) {
        case 'connection':
            return appState.bigqueryConnected;
        case 'dataset':
            return appState.selectedDataset !== null;
        case 'mapping':
            return appState.mappingCompleted;
        case 'config':
            return appState.configurationCompleted;
        default:
            return false;
    }
}

function navigateToStep(stepName) {
    if (!isStepAccessible(stepName)) return;
    
    // Cacher tous les contenus
    document.querySelectorAll('.step-content').forEach(content => {
        content.classList.remove('step-content--active');
    });
    
    // Afficher le contenu de l'étape
    document.getElementById(`content-${stepName}`).classList.add('step-content--active');
    
    appState.currentStep = stepName;
    updateUIState();
}

async function testBigQueryConnection() {
    const projectId = document.getElementById('project-id').value.trim();
    const serviceAccount = document.getElementById('service-account').value.trim();
    const testBtn = document.getElementById('test-connection');
    const spinner = document.getElementById('connection-spinner');
    const resultDiv = document.getElementById('connection-result');
    
    if (!projectId || !serviceAccount) {
        showConnectionResult('Veuillez remplir tous les champs requis.', false);
        return;
    }
    
    // Validation basique du JSON
    try {
        JSON.parse(serviceAccount);
    } catch (e) {
        showConnectionResult('Le JSON du service account n\'est pas valide.', false);
        return;
    }
    
    testBtn.disabled = true;
    spinner.classList.remove('hidden');
    resultDiv.classList.add('hidden');

    try {
        // Préparer le fichier JSON à envoyer comme UploadFile "file"
        const blob = new Blob([serviceAccount], { type: 'application/json' });
        const file = new File([blob], 'service_account.json', { type: 'application/json' });
        const formData = new FormData();
        formData.append('file', file);
        // Optionnel : si tu veux tester un dataset/table précis, tu peux remplir ces champs
        // formData.append('dataset_id', 'mon_dataset');
        // formData.append('table_id', 'ma_table');

        const response = await fetch(`${API_BASE_URL}/api/test-connection`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok || data.status === 'error') {
            const message = data.message || data.detail || 'Erreur lors de la connexion à BigQuery.';
            throw new Error(message);
        }

        appState.bigqueryConnected = true;
        appState.projectId = projectId;
        appState.serviceAccount = serviceAccount;

        showConnectionResult('Connexion réussie ! Vous pouvez maintenant sélectionner un dataset.', true);

        // Adapter la liste renvoyée par l'API (liste d'IDs) au format attendu par le frontend
        if (Array.isArray(data.datasets) && data.datasets.length > 0) {
            appState.availableDatasets = data.datasets.map(id => ({
                id: id,
                name: id,
                description: ''
            }));
        } else {
            appState.availableDatasets = sampleData.datasets;
        }

        populateDatasetSelect();
        updateUIState();

        setTimeout(() => {
            navigateToStep('dataset');
        }, 800);
    } catch (error) {
        console.error(error);
        showConnectionResult(`Erreur: ${error.message}`, false);
    } finally {
        testBtn.disabled = false;
        spinner.classList.add('hidden');
    }
}

function showConnectionResult(message, success) {
    const resultDiv = document.getElementById('connection-result');
    resultDiv.className = `connection-result ${success ? 'connection-result--success' : 'connection-result--error'}`;
    resultDiv.textContent = message;
    resultDiv.classList.remove('hidden');
}

function populateDatasetSelect() {
    const select = document.getElementById('dataset-select');
    select.innerHTML = '<option value="">Sélectionnez un dataset</option>';
    
    appState.availableDatasets.forEach(dataset => {
        const option = document.createElement('option');
        option.value = dataset.id;
        option.textContent = `${dataset.name} - ${dataset.description}`;
        select.appendChild(option);
    });
    
    select.disabled = false;
}

function onDatasetSelect() {
    const select = document.getElementById('dataset-select');
    const selectedValue = select.value;
    
    if (selectedValue) {
        appState.selectedDataset = selectedValue;
        appState.datasetColumns = sampleData.sampleColumns;
        showDatasetPreview();
    } else {
        appState.selectedDataset = null;
        hideDatasetPreview();
    }
    
    updateUIState();
}

function showDatasetPreview() {
    const preview = document.getElementById('dataset-preview');
    const table = document.getElementById('preview-table');
    
    // Créer les en-têtes
    const thead = table.querySelector('thead');
    thead.innerHTML = '';
    const headerRow = document.createElement('tr');
    
    sampleData.sampleColumns.slice(0, 8).forEach(column => {
        const th = document.createElement('th');
        th.textContent = column;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    
    // Créer les lignes de données
    const tbody = table.querySelector('tbody');
    tbody.innerHTML = '';
    
    sampleData.sampleRows.forEach(row => {
        const tr = document.createElement('tr');
        row.slice(0, 8).forEach(cell => {
            const td = document.createElement('td');
            td.textContent = cell;
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    
    preview.classList.remove('hidden');
}

function hideDatasetPreview() {
    document.getElementById('dataset-preview').classList.add('hidden');
}

function validateDataset() {
    if (appState.selectedDataset) {
        generateMappingInterface();
        navigateToStep('mapping');
    }
}

function generateMappingInterface() {
    const container = document.getElementById('mapping-container');
    container.innerHTML = '';
    
    requiredColumns.forEach(column => {
        const row = document.createElement('div');
        row.className = `mapping-row ${column.required ? 'mapping-row--required' : ''}`;
        
        row.innerHTML = `
            <div class="column-info">
                <div class="column-name">
                    ${column.name}
                    ${column.required ? '<span class="required-indicator">*</span>' : ''}
                </div>
                <div class="column-description">${column.description}</div>
            </div>
            <div class="form-group">
                <select class="form-control mapping-select" data-column="${column.name}">
                    <option value="">Sélectionnez une colonne</option>
                    ${appState.datasetColumns.map(col => `<option value="${col}">${col}</option>`).join('')}
                </select>
            </div>
            <div class="column-info">
                <div class="column-name">Type: ${column.required ? 'Obligatoire' : 'Optionnel'}</div>
            </div>
        `;
        
        container.appendChild(row);
    });
    
    // Bind events pour les selects de mapping
    container.querySelectorAll('.mapping-select').forEach(select => {
        select.addEventListener('change', onMappingChange);
    });
    
    updateUIState();
}

function onMappingChange() {
    const mappingSelects = document.querySelectorAll('.mapping-select');
    appState.columnMapping = {};
    
    mappingSelects.forEach(select => {
        const columnName = select.dataset.column;
        const selectedValue = select.value;
        if (selectedValue) {
            appState.columnMapping[columnName] = selectedValue;
        }
    });
    
    updateUIState();
}

function hasRequiredMappings() {
    const requiredCols = requiredColumns.filter(col => col.required);
    return requiredCols.every(col => appState.columnMapping[col.name]);
}

function validateMapping() {
    if (hasRequiredMappings()) {
        appState.mappingCompleted = true;
        updateUIState();
        navigateToStep('config');
    }
}

function launchAnalysis() {
    appState.configurationCompleted = true;
    
    // Simuler l'analyse des données
    generateAttributionResults();
    updateUIState();
    navigateToStep('results');
}

function generateAttributionResults() {
    // Données d'exemple pour les résultats
    const sampleResults = {
        totalConversions: 158,
        uniqueChannels: 5,
        avgPathLength: 2.4,
        channelAttribution: {
            'Google Ads': 28,
            'Facebook': 24,
            'Email': 16,
            'Organic Search': 19,
            'Direct': 13
        },
        modelComparison: {
            'First Click': { 'Google Ads': 35, 'Facebook': 25, 'Email': 10, 'Organic Search': 20, 'Direct': 10 },
            'Last Click': { 'Google Ads': 15, 'Facebook': 20, 'Email': 15, 'Organic Search': 25, 'Direct': 25 },
            'Linear': { 'Google Ads': 25, 'Facebook': 22, 'Email': 18, 'Organic Search': 22, 'Direct': 13 },
            'Data-Driven': { 'Google Ads': 28, 'Facebook': 24, 'Email': 16, 'Organic Search': 19, 'Direct': 13 }
        },
        topPaths: [
            { path: ['Google Ads', 'Email', 'Direct'], conversions: 45, attribution: 28.5 },
            { path: ['Facebook', 'Google Ads', 'Direct'], conversions: 32, attribution: 22.4 },
            { path: ['Organic Search', 'Email', 'Direct'], conversions: 28, attribution: 19.6 },
            { path: ['Facebook', 'Direct'], conversions: 15, attribution: 12.0 },
            { path: ['Google Ads', 'Direct'], conversions: 38, attribution: 27.5 }
        ]
    };
    
    appState.attributionResults = sampleResults;
    displayResults();
}

function displayResults() {
    const results = appState.attributionResults;
    
    // Mettre à jour les métriques
    document.getElementById('total-conversions').textContent = results.totalConversions;
    document.getElementById('unique-channels').textContent = results.uniqueChannels;
    document.getElementById('avg-path-length').textContent = results.avgPathLength;
    
    // Créer les graphiques
    createChannelAttributionChart(results.channelAttribution);
    createModelComparisonChart(results.modelComparison);
    
    // Remplir le tableau des parcours
    populateTopPathsTable(results.topPaths);
}

function createChannelAttributionChart(data) {
    const ctx = document.getElementById('channel-attribution-chart').getContext('2d');
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(data),
            datasets: [{
                data: Object.values(data),
                backgroundColor: ['#1FB8CD', '#FFC185', '#B4413C', '#ECEBD5', '#5D878F']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                },
                title: {
                    display: true,
                    text: 'Attribution par Canal (%)'
                }
            }
        }
    });
}

function createModelComparisonChart(data) {
    const ctx = document.getElementById('model-comparison-chart').getContext('2d');
    const channels = Object.keys(data['Data-Driven']);
    
    const datasets = Object.keys(data).map((model, index) => ({
        label: model,
        data: channels.map(channel => data[model][channel]),
        backgroundColor: ['#1FB8CD', '#FFC185', '#B4413C', '#ECEBD5'][index],
        borderWidth: 1
    }));
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: channels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Comparaison des Modèles d\'Attribution'
                },
                legend: {
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Attribution (%)'
                    }
                }
            }
        }
    });
}

function populateTopPathsTable(paths) {
    const tbody = document.getElementById('top-paths-body');
    tbody.innerHTML = '';
    
    paths.forEach(pathData => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${pathData.path.join(' → ')}</td>
            <td>${pathData.conversions}</td>
            <td>${pathData.attribution.toFixed(1)}%</td>
        `;
        tbody.appendChild(row);
    });
}
