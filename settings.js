const { ipcRenderer } = require('electron');

// Mappa locale per le impostazioni
const settingsMap = new Map();

console.log('Settings.js loaded');

// Funzione per salvare la Map in localStorage
function saveMapToStorage() {
    const mapData = Object.fromEntries(settingsMap);
    localStorage.setItem('settings', JSON.stringify(mapData));
    console.log('Saved Map to localStorage:', mapData);
}

// Funzione per caricare la Map da localStorage
function loadMapFromStorage() {
    const savedData = localStorage.getItem('settings');
    if (savedData) {
        const mapData = JSON.parse(savedData);
        console.log('Loading Map from localStorage:', mapData);
        Object.entries(mapData).forEach(([key, value]) => {
            settingsMap.set(key, value);
        });
    }
}

// Verifica che ipcRenderer sia disponibile
if (!ipcRenderer) {
    console.error('ipcRenderer non è disponibile!');
    showMessage('Errore: ipcRenderer non disponibile', 'error');
}

// Funzione per verificare l'esistenza degli elementi UI
function verifyUIElements() {
    const elements = {
        settingsForm: document.getElementById('settingsForm'),
        backButton: document.getElementById('backButton'),
        browseImagesButton: document.getElementById('browseImagesButton'),
        messageDiv: document.getElementById('messageDiv')
    };

    // Verifica che tutti gli elementi esistano
    Object.entries(elements).forEach(([name, element]) => {
        if (!element) {
            console.error(`Elemento UI non trovato: ${name}`);
            // Crea l'elemento messageDiv se non esiste
            if (name === 'messageDiv') {
                const div = document.createElement('div');
                div.id = 'messageDiv';
                div.className = 'message';
                div.style.display = 'none';
                document.body.appendChild(div);
                elements.messageDiv = div;
                console.log('Creato elemento messageDiv');
            }
        }
    });

    return elements;
}

// Funzione per salvare le impostazioni nella Map
function saveSettingsToMap(settings) {
    console.log('Saving settings to Map:', settings);
    
    // Salva solo i valori non vuoti
    Object.entries(settings).forEach(([key, value]) => {
        if (value) {
            settingsMap.set(key, value);
        } else {
            settingsMap.delete(key);
        }
    });
    
    console.log('Current Map contents:', Object.fromEntries(settingsMap));
    
    // Salva la Map in localStorage
    saveMapToStorage();
    
    // Sincronizza con il file .env
    try {
        const envContent = Array.from(settingsMap.entries())
            .map(([key, value]) => `${key.toUpperCase()}=${value}`)
            .join('\n');
        
        // Invia il contenuto al main process per scrivere nel file .env
        ipcRenderer.send('write-env', envContent);
    } catch (error) {
        console.error('Error syncing with .env:', error);
        showMessage('Errore durante il salvataggio nel file .env', 'error');
    }
}

// Funzione per caricare le impostazioni dalla Map
function loadSettingsFromMap() {
    const settings = Object.fromEntries(settingsMap);
    console.log('Loading settings from Map:', settings);
    
    // Popola i campi del form
    Object.entries(settings).forEach(([key, value]) => {
        const input = document.getElementById(key);
        if (input) {
            input.value = value;
            console.log(`Setting ${key} to value: ${value}`);
        } else {
            console.warn(`Input field with id ${key} not found`);
        }
    });
}

// Verifica e ottieni gli elementi UI
const ui = verifyUIElements();

// Gestione del form
ui.settingsForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    console.log('Form submitted');
    
    // Raccogli i dati dal form
    const settings = {
        shopify_domain: document.getElementById('shopify_domain')?.value || '',
        shopify_token: document.getElementById('shopify_token')?.value || '',
        shopify_api_key: document.getElementById('shopify_api_key')?.value || '',
        shopify_api_secret: document.getElementById('shopify_api_secret')?.value || '',
        openai_api_key: document.getElementById('openai_api_key')?.value || '',
        serpapi_key: document.getElementById('serpapi_key')?.value || '',
        image_storage_path: document.getElementById('image_storage_path')?.value || ''
    };
    
    console.log('Settings to save:', settings);
    showMessage('Salvataggio in corso...', 'info');
    
    // Salva nella Map
    saveSettingsToMap(settings);
    showMessage('Impostazioni salvate con successo!', 'success');
});

// Gestione del pulsante indietro
ui.backButton.addEventListener('click', () => {
    window.location.href = 'index.html';
});

// Gestione del pulsante per selezionare la cartella delle immagini
ui.browseImagesButton.addEventListener('click', () => {
    // Invia richiesta al main process per aprire il dialog
    ipcRenderer.send('open-directory-dialog');
});

// Listener per la risposta del dialog
ipcRenderer.on('selected-directory', (event, path) => {
    if (path) {
        const input = document.getElementById('image_storage_path');
        if (input) {
            input.value = path;
        }
    }
});

// Funzione per mostrare i messaggi
function showMessage(message, type = 'info') {
    console.log('Showing message:', message, 'of type:', type);
    if (!ui.messageDiv) {
        console.error('messageDiv non disponibile');
        return;
    }
    ui.messageDiv.textContent = message;
    ui.messageDiv.className = `message ${type}`;
    ui.messageDiv.style.display = 'block';
    
    // Nascondi il messaggio dopo 3 secondi
    setTimeout(() => {
        ui.messageDiv.style.display = 'none';
    }, 3000);
}

// Carica le impostazioni salvate quando la pagina viene caricata
document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOM Content Loaded');
    
    // Verifica che tutti gli elementi del form siano presenti
    const requiredFields = [
        'shopify_domain',
        'shopify_token',
        'shopify_api_key',
        'shopify_api_secret',
        'openai_api_key',
        'serpapi_key',
        'image_storage_path'
    ];
    
    requiredFields.forEach(fieldId => {
        const element = document.getElementById(fieldId);
        if (!element) {
            console.error(`Required field ${fieldId} not found in the DOM`);
        }
    });
    
    // Carica prima da localStorage
    loadMapFromStorage();
    
    // Popola i campi con i dati della Map
    loadSettingsFromMap();
    
    // Poi carica dal main process
    console.log('Requesting settings from main process');
    ipcRenderer.send('load-settings');
    
    // Aggiungi listener per il caricamento delle impostazioni dal main process
    ipcRenderer.on('settings-loaded', (event, settings) => {
        console.log('Received settings from main process:', settings);
        if (settings) {
            // Aggiorna la Map con le impostazioni ricevute
            Object.entries(settings).forEach(([key, value]) => {
                if (value) {
                    settingsMap.set(key.toLowerCase(), value);
                }
            });
            // Salva la Map aggiornata in localStorage
            saveMapToStorage();
            // Ricarica i campi del form
            loadSettingsFromMap();
        }
    });
}); 