const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const dotenv = require('dotenv');

let mainWindow;
let pythonProcess;

// Funzione per scrivere nel file .env
function writeToEnvFile(settings) {
    try {
        const envPath = path.join(__dirname, '.env');
        console.log('Writing to .env file at:', envPath);
        
        // Leggi il file .env esistente se presente
        let envConfig = {};
        if (fs.existsSync(envPath)) {
            envConfig = dotenv.parse(fs.readFileSync(envPath));
            console.log('Current .env content:', envConfig);
        }
        
        // Aggiorna le impostazioni
        Object.keys(settings).forEach(key => {
            if (settings[key]) {  // Salva solo i valori non vuoti
                envConfig[key.toUpperCase()] = settings[key];
            }
        });
        console.log('Updated .env content:', envConfig);
        
        // Scrivi il file .env
        const envContent = Object.entries(envConfig)
            .map(([key, value]) => `${key}=${value}`)
            .join('\n');
        
        fs.writeFileSync(envPath, envContent);
        console.log('Successfully wrote to .env file');
        
        // Verifica che il file sia stato scritto correttamente
        const writtenContent = fs.readFileSync(envPath, 'utf8');
        console.log('Verification - .env file content:', writtenContent);
        
        return true;
    } catch (error) {
        console.error('Error writing to .env file:', error);
        return false;
    }
}

function createWindow() {
    console.log('Creating main window');
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            enableRemoteModule: true,
            webSecurity: false
        }
    });

    // Imposta la Content Security Policy
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
        callback({
            responseHeaders: {
                ...details.responseHeaders,
                'Content-Security-Policy': [
                    "default-src 'self' 'unsafe-inline' 'unsafe-eval' data:;",
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval';",
                    "style-src 'self' 'unsafe-inline';",
                    "img-src 'self' data: https:;",
                    "connect-src 'self' https:;"
                ].join(' ')
            }
        });
    });

    mainWindow.loadFile('index.html');
    mainWindow.webContents.openDevTools();
    
    // Log quando la finestra è pronta
    mainWindow.webContents.on('did-finish-load', () => {
        console.log('Main window loaded');
    });

    // Log degli errori di caricamento
    mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        console.error('Failed to load:', errorCode, errorDescription);
    });
}

// Registra gli handler IPC
function setupIpcHandlers() {
    console.log('Setting up IPC handlers');
    
    // Handler per il salvataggio delle impostazioni
    ipcMain.on('save-settings', (event, settings) => {
        console.log('Received save-settings request with data:', settings);
        
        try {
            // Scrivi nel file .env
            const success = writeToEnvFile(settings);
            
            // Invia conferma al renderer
            console.log('Sending response to renderer:', success);
            event.reply('settings-saved', success);
        } catch (error) {
            console.error('Error in save-settings handler:', error);
            event.reply('settings-saved', false);
        }
    });

    // Handler per il caricamento delle impostazioni
    ipcMain.on('load-settings', (event) => {
        console.log('Received load-settings request');
        try {
            const envPath = path.join(__dirname, '.env');
            let settings = {};
            
            if (fs.existsSync(envPath)) {
                settings = dotenv.parse(fs.readFileSync(envPath));
                console.log('Loaded settings from .env:', settings);
            }
            
            console.log('Sending settings to renderer:', settings);
            event.reply('settings-loaded', settings);
        } catch (error) {
            console.error('Error loading settings:', error);
            event.reply('settings-loaded', {});
        }
    });

    // Handler per scrivere nel file .env
    ipcMain.on('write-env', (event, content) => {
        console.log('Received write-env request');
        try {
            const envPath = path.join(__dirname, '.env');
            fs.writeFileSync(envPath, content);
            console.log('Successfully wrote to .env file');
            event.reply('env-written', true);
        } catch (error) {
            console.error('Error writing to .env file:', error);
            event.reply('env-written', false);
        }
    });

    // Handler per aprire il dialog di selezione directory
    ipcMain.on('open-directory-dialog', async (event) => {
        try {
            const result = await dialog.showOpenDialog({
                properties: ['openDirectory']
            });
            
            if (!result.canceled && result.filePaths.length > 0) {
                event.reply('selected-directory', result.filePaths[0]);
            }
        } catch (error) {
            console.error('Error opening directory dialog:', error);
            event.reply('selected-directory', null);
        }
    });
}

// Assicurati che il main process sia pronto prima di creare la finestra
app.whenReady().then(() => {
    console.log('Main process started');
    
    // Registra gli handler IPC prima di creare la finestra
    setupIpcHandlers();
    
    // Crea la finestra
    createWindow();
});

// Log degli eventi dell'app
app.on('window-all-closed', () => {
    console.log('All windows closed');
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    console.log('App activated');
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// Gestione dell'avvio dell'analisi
ipcMain.on('start-analysis', (event, data) => {
    const pythonScript = path.join(__dirname, 'test_scraper.py');
    
    pythonProcess = spawn('python', [pythonScript, JSON.stringify(data)], {
        stdio: ['pipe', 'pipe', 'pipe']
    });

    pythonProcess.stdout.on('data', (data) => {
        try {
            const output = JSON.parse(data.toString());
            mainWindow.webContents.send('python-output', output);
        } catch (e) {
            console.error('Error parsing Python output:', e);
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        mainWindow.webContents.send('python-error', data.toString());
    });

    pythonProcess.on('close', (code) => {
        mainWindow.webContents.send('python-closed', code);
    });
});

// Gestione del check dei prezzi mancanti
ipcMain.on('check-prices', (event) => {
    const pythonScript = path.join(__dirname, 'check_missing_prices.py');
    
    pythonProcess = spawn('python', [pythonScript], {
        stdio: ['pipe', 'pipe', 'pipe']
    });

    pythonProcess.stdout.on('data', (data) => {
        try {
            const output = JSON.parse(data.toString());
            mainWindow.webContents.send('python-output', output);
        } catch (e) {
            console.error('Error parsing Python output:', e);
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        mainWindow.webContents.send('python-error', data.toString());
    });

    pythonProcess.on('close', (code) => {
        mainWindow.webContents.send('python-closed', code);
    });
}); 