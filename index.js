const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true
    }
  });

  mainWindow.loadFile('index.html');
}

function startPythonBackend() {
  // Avvia il processo Python
  const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
  pythonProcess = spawn(pythonPath, ['shopify_automation.py'], {
    stdio: ['pipe', 'pipe', 'pipe']
  });

  // Gestione output Python
  pythonProcess.stdout.on('data', (data) => {
    try {
      const message = JSON.parse(data.toString());
      mainWindow.webContents.send('python-output', message);
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
}

// Gestione eventi IPC
ipcMain.on('start-analysis', (event, data) => {
  if (pythonProcess) {
    try {
      pythonProcess.stdin.write(JSON.stringify(data) + '\n');
    } catch (e) {
      console.error('Error sending data to Python:', e);
      mainWindow.webContents.send('python-error', 'Errore nell\'invio dei dati a Python');
    }
  } else {
    mainWindow.webContents.send('python-error', 'Processo Python non attivo');
  }
});

ipcMain.on('check-prices', (event) => {
  if (pythonProcess) {
    try {
      pythonProcess.stdin.write(JSON.stringify({ action: 'check_prices' }) + '\n');
    } catch (e) {
      console.error('Error sending check_prices command:', e);
      mainWindow.webContents.send('python-error', 'Errore nell\'invio del comando check_prices');
    }
  }
});

ipcMain.on('save-settings', (event, settings) => {
  try {
    fs.writeFileSync('settings.json', JSON.stringify(settings, null, 2));
  } catch (e) {
    console.error('Error saving settings:', e);
    mainWindow.webContents.send('python-error', 'Errore nel salvataggio delle impostazioni');
  }
});

ipcMain.on('variants-selected', (event, data) => {
  // data.selected: array di indici selezionati o 'unknown'
  // data.allVariants: tutte le varianti trovate
  // data.productTitle: titolo prodotto
  if (data.selected.includes('unknown')) {
    // L'utente ha scelto 'Sconosciuto', salta il pricing
    mainWindow.webContents.send('python-output', {
      type: 'progress',
      value: 100,
      message: `Prezzo sconosciuto per ${data.productTitle}, operazione saltata.`
    });
    return;
  }
  // Filtra le varianti selezionate
  const selectedVariants = data.selected.map(idx => data.allVariants[parseInt(idx)]).filter(Boolean);
  // Invia al backend Python la richiesta di creazione varianti
  if (pythonProcess) {
    pythonProcess.stdin.write(JSON.stringify({
      action: 'create-variants',
      productTitle: data.productTitle,
      variants: selectedVariants
    }) + '\n');
  }
});

// Gestione dialog per la selezione cartella
ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result.filePaths[0];
});

app.whenReady().then(() => {
  createWindow();
  startPythonBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
}); 