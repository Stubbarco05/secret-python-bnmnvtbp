const { ipcRenderer } = require('electron');

// Gestione delle impostazioni
let settings = {
    shopify_domain: '',
    shopify_token: '',
    shopify_api_key: '',
    shopify_api_secret: '',
    openai_api_key: '',
    serpapi_key: '',
    image_storage_path: ''
};

// Elementi UI
const inputArea = document.getElementById('input');
const submitButton = document.getElementById('submit');
const outputArea = document.getElementById('output');
const settingsButton = document.getElementById('settingsButton');
const checkPricesButton = document.getElementById('checkPricesButton');
const operationsTable = document.getElementById('operationsTable');
const settingsForm = document.getElementById('settingsForm');
const analysisForm = document.getElementById('analysisForm');
const browseImagesButton = document.getElementById('browseImagesButton');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

// Gestione del click sul bottone impostazioni
settingsButton.addEventListener('click', () => {
    window.location.href = 'settings.html';
});

// Gestione del click sul bottone di navigazione immagini
browseImagesButton.addEventListener('click', () => {
    const { dialog } = require('electron').remote;
    dialog.showOpenDialog({
        properties: ['openDirectory']
    }).then(result => {
        if (!result.canceled) {
            document.getElementById('image_storage_path').value = result.filePaths[0];
        }
    }).catch(err => {
        console.error(err);
    });
});

// Gestione form impostazioni
settingsForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const formData = new FormData(settingsForm);
    settings = {
        shopify_domain: formData.get('shopify_domain'),
        shopify_token: formData.get('shopify_token'),
        shopify_api_key: formData.get('shopify_api_key'),
        shopify_api_secret: formData.get('shopify_api_secret'),
        openai_api_key: formData.get('openai_api_key'),
        serpapi_key: formData.get('serpapi_key'),
        image_storage_path: formData.get('image_storage_path')
    };
    
    // Validazione
    if (!settings.shopify_domain || !settings.shopify_token) {
        showError('Dominio Shopify e Token sono obbligatori');
        return;
    }
    
    // Salva le impostazioni
    ipcRenderer.send('save-settings', settings);
    showMessage('Impostazioni salvate con successo!', 'success');
});

// Gestione del click sul bottone "Avvia Analisi"
submitButton.addEventListener('click', async () => {
    const input = inputArea.value;
    if (!input) {
        showError('Inserisci i dati dei brand e profumi');
        return;
    }

    // Parsing dell'input
    const brands = parseInput(input);
    
    // Aggiungi riga alla tabella operazioni
    addOperationRow('Inizio analisi', 'In corso');
    
    // Invia i dati al backend Python
    ipcRenderer.send('start-analysis', {
        action: 'analyze',
        brands: brands
    });
});

// Gestione del click sul bottone "Check Missing Prices"
checkPricesButton.addEventListener('click', async () => {
    addOperationRow('Verifica prezzi mancanti', 'In corso');
    ipcRenderer.send('check-prices');
});

// Gestione output dal backend Python
ipcRenderer.on('python-output', (event, data) => {
    if (data.type === 'progress') {
        updateProgress(data.value, data.message);
    } else if (data.type === 'result') {
        // Se ci sono varianti, mostra il dialog di selezione
        if (data.results && data.results.variants && data.results.variants.length > 0) {
            showVariantsDialog(data.results.variants, (selected) => {
                // Invia la selezione al backend
                ipcRenderer.send('variants-selected', {
                    selected,
                    allVariants: data.results.variants,
                    productTitle: data.results.title
                });
            });
        } else {
            showResults(data.results);
        }
    }
});

ipcRenderer.on('python-error', (event, error) => {
    showError(`Errore: ${error}`);
});

ipcRenderer.on('python-closed', (event, code) => {
    showError(`Processo Python terminato con codice: ${code}`);
});

// Funzioni di utilità
function parseInput(input) {
    const lines = input.split('\n');
    const brands = {};
    let currentBrand = null;

    for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;

        if (trimmedLine.endsWith(':')) {
            currentBrand = trimmedLine.slice(0, -1).trim();
            brands[currentBrand] = [];
        } else if (currentBrand) {
            brands[currentBrand].push(trimmedLine);
        }
    }

    return brands;
}

function addOperationRow(operation, status) {
    const row = operationsTable.insertRow();
    const timestamp = new Date().toLocaleTimeString();
    
    row.innerHTML = `
        <td>${timestamp}</td>
        <td>${operation}</td>
        <td>${status}</td>
    `;
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.textContent = message;
    outputArea.appendChild(errorDiv);
    
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}

function showVariantsDialog(variants, onConfirm) {
    // Rimuovi eventuali dialog precedenti
    const oldDialog = document.getElementById('variantsDialog');
    if (oldDialog) oldDialog.remove();

    const dialog = document.createElement('div');
    dialog.id = 'variantsDialog';
    dialog.className = 'variants-dialog';
    dialog.innerHTML = `
        <div class="variants-content">
            <h3>Varianti trovate</h3>
            <form id="variantsForm">
                <div class="variants-list">
                    ${variants.map((variant, idx) => `
                        <div class="variant-item">
                            <input type="checkbox" id="variant-${idx}" name="variant" value="${idx}">
                            <label for="variant-${idx}">
                                ${variant.size_ml ? variant.size_ml + ' ml' : variant.title} - €${variant.price}
                            </label>
                        </div>
                    `).join('')}
                    <div class="variant-item">
                        <input type="checkbox" id="variant-unknown" name="variant" value="unknown">
                        <label for="variant-unknown">Sconosciuto</label>
                    </div>
                </div>
                <div class="button-group">
                    <button type="submit" class="primary-button">Conferma</button>
                    <button type="button" class="secondary-button" id="skipVariants">Salta</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(dialog);

    document.getElementById('skipVariants').onclick = () => {
        dialog.remove();
        if (onConfirm) onConfirm([]);
    };

    document.getElementById('variantsForm').onsubmit = (e) => {
        e.preventDefault();
        const checked = Array.from(document.querySelectorAll('input[name="variant"]:checked')).map(cb => cb.value);
        dialog.remove();
        if (onConfirm) onConfirm(checked);
    };
}

function showMessage(message, type) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.textContent = message;
    outputArea.appendChild(messageDiv);
    setTimeout(() => messageDiv.remove(), 5000);
}

function updateProgress(value, message) {
    progressBar.style.width = `${value}%`;
    progressText.textContent = message;
}

function showResults(results) {
    const resultsDiv = document.createElement('div');
    resultsDiv.className = 'results';
    resultsDiv.innerHTML = `
        <h3>Risultati dell'analisi</h3>
        <pre>${JSON.stringify(results, null, 2)}</pre>
    `;
    outputArea.appendChild(resultsDiv);
}

// Gestione del click sul bottone "Salta" nel dialog delle varianti
document.getElementById('skipVariants').addEventListener('click', () => {
    const dialog = document.getElementById('variantsDialog');
    if (dialog) dialog.remove();
});

// Gestione del submit del form delle varianti
document.getElementById('variantsForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const selectedVariants = Array.from(document.querySelectorAll('input[name="variant"]:checked')).map(input => input.value);
    const dialog = document.getElementById('variantsDialog');
    if (dialog) dialog.remove();
    // Qui puoi gestire le varianti selezionate, ad esempio inviandole al backend
    console.log('Varianti selezionate:', selectedVariants);
});

// Inizializzazione
document.addEventListener('DOMContentLoaded', () => {
    // Carica le impostazioni salvate
    try {
        const savedSettings = localStorage.getItem('shopifySettings');
        if (savedSettings) {
            settings = JSON.parse(savedSettings);
            // Popola i campi del form con le impostazioni salvate
            Object.keys(settings).forEach(key => {
                const input = document.getElementById(key);
                if (input) {
                    input.value = settings[key];
                }
            });
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}); 