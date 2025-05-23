# Shopify Automation

Un'applicazione Electron per l'automazione di processi Shopify.

## Caratteristiche

- Gestione delle impostazioni Shopify
- Integrazione con API esterne
- Interfaccia utente intuitiva
- Salvataggio automatico delle configurazioni

## Requisiti

- Node.js
- Python 3.x
- Account Shopify
- API keys per i servizi integrati

## Installazione

1. Clona il repository:
```bash
git clone https://github.com/tuousername/shopify-automation.git
cd shopify-automation
```

2. Installa le dipendenze:
```bash
npm install
```

3. Crea un file `.env` nella root del progetto con le tue configurazioni:
```env
SHOPIFY_DOMAIN=your-domain.myshopify.com
SHOPIFY_TOKEN=your-token
SHOPIFY_API_KEY=your-api-key
SHOPIFY_API_SECRET=your-api-secret
OPENAI_API_KEY=your-openai-key
SERPAPI_KEY=your-serpapi-key
IMAGE_STORAGE_PATH=/path/to/images
```

## Utilizzo

1. Avvia l'applicazione:
```bash
npm start
```

2. Configura le impostazioni nella pagina delle impostazioni
3. Utilizza le funzionalità disponibili nell'interfaccia principale

## Sviluppo

- `main.js`: Processo principale Electron
- `settings.js`: Gestione delle impostazioni
- `index.html`: Interfaccia principale
- `styles.css`: Stili dell'applicazione

## Licenza

MIT 