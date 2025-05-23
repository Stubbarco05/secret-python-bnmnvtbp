import logging
from typing import Dict, List, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, TimeoutError
import time
import re
from urllib.parse import quote_plus, urlparse
import json
from dataclasses import dataclass
from collections import defaultdict
import whois
import tldextract
import openai
import os
from dotenv import load_dotenv, set_key
import wikipedia
from price_parser import Price
import statistics
import mimetypes
from io import BytesIO
from PIL import Image
import shutil
import shopify
from datetime import datetime
import base64

# Carica le variabili d'ambiente
load_dotenv()

# Configurazione selettori per sito
SITE_CONFIG = {
    "__default__": {
        "variant_selectors": [
            # Select elements
            "select option",
            ".product-variant-selector option",
            ".variant-selector option",
            ".product-options select option",
            # Radio buttons
            "input[type='radio'][name*='variant']",
            "input[type='radio'][name*='option']",
            ".product-form__input input[type='radio']",
            # Buttons and links
            ".product-variant",
            ".variant-option",
            ".product-options__value",
            ".swatch-element",
            "[data-variant-selector]",
            ".product-options__selector",
            # Generic selectors
            "[data-option]",
            "[data-variant]",
            ".product-option",
            ".variant-selector"
        ],
        "price_selectors": [
            # Common price selectors
            ".product-price",
            ".price",
            ".product__price",
            "[itemprop='price']",
            # Specific price elements
            ".product-single__price",
            ".price-item--regular",
            ".product-form__price",
            ".product__price--regular",
            "[data-price]",
            ".product-price__regular",
            # Generic price selectors
            "[data-product-price]",
            ".current-price",
            ".product-current-price",
            ".product-price__value"
        ],
        "search_selectors": [
            # Common product selectors
            ".product-item",
            ".product-card",
            ".search-result-item",
            ".product",
            # Link selectors
            "a[href*='product']",
            ".product-link",
            # Grid and list items
            ".product-grid-item",
            ".product-tile",
            ".product-box",
            ".product-list__item",
            ".product-grid__item",
            # Generic selectors
            "[data-product]",
            ".search-result",
            ".product-result"
        ]
    }
}

# Configurazione per il salvataggio delle immagini
IMAGE_SETTINGS = {
    "max_size_mb": 10,
    "base_folder": os.getenv("IMAGE_STORAGE_PATH", "images"),  # Cartella base per le immagini
    "quality": 85,  # Qualità JPEG per la compressione
    "max_dimension": 2000  # Dimensione massima in pixel per lato
}

# Configurazione Shopify
SHOPIFY_CONFIG = {
    "shop_url": os.getenv("SHOPIFY_SHOP_URL"),
    "api_key": os.getenv("SHOPIFY_API_KEY"),
    "password": os.getenv("SHOPIFY_PASSWORD"),
    "api_version": "2024-01"  # Aggiorna con la versione più recente
}

class SettingsManager:
    def __init__(self, env_path: str = ".env"):
        self.env_path = env_path
        self._load_settings()

    def _load_settings(self):
        """Carica le impostazioni dal file .env."""
        load_dotenv(self.env_path)
        
        # Carica le impostazioni correnti
        self.settings = {
            "shopify": {
                "shop_url": os.getenv("SHOPIFY_SHOP_URL", ""),
                "api_key": os.getenv("SHOPIFY_API_KEY", ""),
                "api_secret": os.getenv("SHOPIFY_API_SECRET", ""),
                "access_token": os.getenv("SHOPIFY_ACCESS_TOKEN", ""),
                "api_version": SHOPIFY_CONFIG["api_version"]
            },
            "images": {
                "storage_path": os.getenv("IMAGE_STORAGE_PATH", "images"),
                "max_size_mb": IMAGE_SETTINGS["max_size_mb"],
                "quality": IMAGE_SETTINGS["quality"],
                "max_dimension": IMAGE_SETTINGS["max_dimension"]
            },
            "serpapi": {
                "api_key": os.getenv("SERPAPI_KEY", "")
            },
            "openai": {
                "api_key": os.getenv("OPENAI_API_KEY", "")
            }
        }

    def get_settings(self) -> Dict:
        """Restituisce tutte le impostazioni correnti."""
        return self.settings

    def update_settings(self, new_settings: Dict) -> bool:
        """Aggiorna le impostazioni nel file .env."""
        try:
            # Aggiorna le impostazioni Shopify
            if "shopify" in new_settings:
                shopify_settings = new_settings["shopify"]
                self._update_env_key("SHOPIFY_SHOP_URL", shopify_settings.get("shop_url"))
                self._update_env_key("SHOPIFY_API_KEY", shopify_settings.get("api_key"))
                self._update_env_key("SHOPIFY_API_SECRET", shopify_settings.get("api_secret"))
                self._update_env_key("SHOPIFY_ACCESS_TOKEN", shopify_settings.get("access_token"))
                SHOPIFY_CONFIG["api_version"] = shopify_settings.get("api_version", SHOPIFY_CONFIG["api_version"])

            # Aggiorna le impostazioni delle immagini
            if "images" in new_settings:
                image_settings = new_settings["images"]
                self._update_env_key("IMAGE_STORAGE_PATH", image_settings.get("storage_path"))
                IMAGE_SETTINGS["max_size_mb"] = image_settings.get("max_size_mb", IMAGE_SETTINGS["max_size_mb"])
                IMAGE_SETTINGS["quality"] = image_settings.get("quality", IMAGE_SETTINGS["quality"])
                IMAGE_SETTINGS["max_dimension"] = image_settings.get("max_dimension", IMAGE_SETTINGS["max_dimension"])

            # Aggiorna le impostazioni SerpAPI
            if "serpapi" in new_settings:
                self._update_env_key("SERPAPI_KEY", new_settings["serpapi"].get("api_key"))

            # Aggiorna le impostazioni OpenAI
            if "openai" in new_settings:
                self._update_env_key("OPENAI_API_KEY", new_settings["openai"].get("api_key"))

            # Ricarica le impostazioni
            self._load_settings()
            return True
        except Exception as e:
            logging.error(f"Errore nell'aggiornamento delle impostazioni: {str(e)}")
            return False

    def _update_env_key(self, key: str, value: str):
        """Aggiorna una singola chiave nel file .env."""
        if value is not None:
            set_key(self.env_path, key, value)

@dataclass
class PriceOption:
    price: float
    source: str
    url: str
    description: str
    variants: List[Dict]

class ProductScraper:
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)  # 30 secondi di timeout
        
        # Configurazione logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        # Inizializza il gestore delle impostazioni
        self.settings_manager = SettingsManager()
        
        # Verifica le impostazioni necessarie
        self._verify_settings()
        
        # Crea la cartella base per le immagini se non esiste
        os.makedirs(IMAGE_SETTINGS["base_folder"], exist_ok=True)
        
        # Inizializza Shopify
        self._init_shopify()

    def __del__(self):
        if hasattr(self, 'browser'):
            self.browser.close()
        if hasattr(self, 'playwright'):
            self.playwright.stop()

    def _verify_settings(self):
        """Verifica che tutte le impostazioni necessarie siano presenti."""
        settings = self.settings_manager.get_settings()
        
        # Verifica SerpAPI
        if not settings["serpapi"]["api_key"]:
            raise ValueError("Devi impostare SERPAPI_KEY nel file .env o nelle variabili d'ambiente!")
        
        # Verifica Shopify
        if not all([
            settings["shopify"]["shop_url"],
            settings["shopify"]["api_key"],
            settings["shopify"]["api_secret"],
            settings["shopify"]["access_token"]
        ]):
            raise ValueError("Devi impostare tutte le credenziali Shopify nel file .env o nelle variabili d'ambiente!")

    def get_settings(self) -> Dict:
        """Restituisce le impostazioni correnti."""
        return self.settings_manager.get_settings()

    def update_settings(self, new_settings: Dict) -> bool:
        """Aggiorna le impostazioni."""
        return self.settings_manager.update_settings(new_settings)

    def _get_site_config(self, url: str) -> Dict:
        """Ottiene la configurazione dei selettori per il dominio specifico."""
        domain = urlparse(url).netloc.replace("www.", "")
        return SITE_CONFIG.get(domain, SITE_CONFIG["__default__"])

    def _extract_dynamic_variants(self, page: Page, url: str) -> List[Dict]:
        """Estrae dinamicamente tutte le varianti e prezzi da una pagina prodotto."""
        variants = []
        try:
            logging.info(f"Estraggo varianti dinamiche da: {url}")
            page.goto(url)
            page.wait_for_load_state('networkidle')
            time.sleep(2)  # Attendi il caricamento JavaScript
            
            # Prima prova con selettori data-* (più moderni e specifici)
            data_variant_selectors = [
                "[data-variant-selector]",
                "[data-variant]",
                "[data-option]",
                "[data-format]"
            ]
            
            data_price_selectors = [
                "[data-price]",
                "[data-product-price]",
                "[data-current-price]"
            ]
            
            # Prova prima i selettori data-*
            for variant_selector in data_variant_selectors:
                try:
                    logging.info(f"Provo il selettore data: {variant_selector}")
                    variant_elements = page.query_selector_all(variant_selector)
                    
                    if variant_elements:
                        logging.info(f"Trovate {len(variant_elements)} varianti con selettore data: {variant_selector}")
                        
                        for element in variant_elements:
                            try:
                                variant_text = element.text_content().strip()
                                if not variant_text:
                                    continue
                                    
                                element.scroll_into_view_if_needed()
                                
                                # Prova il click
                                try:
                                    element.click()
                                except:
                                    page.evaluate("(element) => element.click()", element)
                                
                                # Attendi sia il networkidle che un timeout fisso
                                page.wait_for_load_state('networkidle')
                                time.sleep(1)  # Timeout fisso come nel codice di esempio
                                
                                # Prova i selettori data-* per il prezzo
                                for price_selector in data_price_selectors:
                                    try:
                                        price_element = page.wait_for_selector(
                                            price_selector,
                                            timeout=5000,
                                            state='visible'
                                        )
                                        
                                        if price_element:
                                            price_text = price_element.text_content().strip()
                                            try:
                                                price = Price.fromstring(price_text)
                                                variants.append({
                                                    "size": variant_text,
                                                    "price": price.amount,
                                                    "currency": price.currency
                                                })
                                                logging.info(f"Trovata variante con selettore data: {variant_text} - {price.amount} {price.currency}")
                                                break
                                            except Exception as e:
                                                logging.error(f"Errore nel parsing del prezzo '{price_text}': {str(e)}")
                                    except TimeoutError:
                                        continue
                                    
                            except Exception as e:
                                logging.error(f"Errore nel processare la variante {variant_text}: {str(e)}")
                                continue
                                
                        if variants:
                            return variants
                            
                except Exception as e:
                    logging.error(f"Errore con selettore data {variant_selector}: {str(e)}")
                    continue
            
            # Se non abbiamo trovato varianti con selettori data-*, usa i selettori generici esistenti
            config = self._get_site_config(url)
            variant_selectors = config["variant_selectors"]
            price_selectors = config["price_selectors"]
            
            # Prova ogni selettore delle varianti generiche
            for variant_selector in variant_selectors:
                try:
                    logging.info(f"Provo il selettore generico: {variant_selector}")
                    page.wait_for_selector(variant_selector, timeout=5000)
                    variant_elements = page.query_selector_all(variant_selector)
                    
                    if variant_elements:
                        logging.info(f"Trovate {len(variant_elements)} varianti con selettore generico: {variant_selector}")
                        
                        for element in variant_elements:
                            try:
                                variant_text = element.text_content().strip()
                                if not variant_text:
                                    continue
                                    
                                element.scroll_into_view_if_needed()
                                
                                if variant_selector.startswith("select"):
                                    value = element.get_attribute("value")
                                    if value:
                                        page.select_option(variant_selector, value=value)
                                else:
                                    try:
                                        element.click()
                                    except:
                                        page.evaluate("(element) => element.click()", element)
                                
                                # Attendi sia il networkidle che un timeout fisso
                                page.wait_for_load_state('networkidle')
                                time.sleep(1)  # Timeout fisso come nel codice di esempio
                                
                                for price_selector in price_selectors:
                                    try:
                                        price_element = page.wait_for_selector(
                                            price_selector,
                                            timeout=5000,
                                            state='visible'
                                        )
                                        
                                        if price_element:
                                            price_text = price_element.text_content().strip()
                                            try:
                                                price = Price.fromstring(price_text)
                                                variants.append({
                                                    "size": variant_text,
                                                    "price": price.amount,
                                                    "currency": price.currency
                                                })
                                                logging.info(f"Trovata variante con selettore generico: {variant_text} - {price.amount} {price.currency}")
                                                break
                                            except Exception as e:
                                                logging.error(f"Errore nel parsing del prezzo '{price_text}': {str(e)}")
                                    except TimeoutError:
                                        continue
                                    
                            except Exception as e:
                                logging.error(f"Errore nel processare la variante {variant_text}: {str(e)}")
                                continue
                                
                        if variants:
                            break
                            
                except TimeoutError:
                    logging.info(f"Nessun elemento trovato con selettore {variant_selector}")
                    continue
                except Exception as e:
                    logging.error(f"Errore con il selettore {variant_selector}: {str(e)}")
                    continue
            
            # Se non abbiamo trovato varianti, prova a cercare prezzi multipli nella pagina
            if not variants:
                logging.info("Nessuna variante trovata, cerco prezzi multipli nella pagina")
                for price_selector in price_selectors + data_price_selectors:  # Prova sia i selettori generici che data-*
                    try:
                        price_elements = page.query_selector_all(price_selector)
                        for elem in price_elements:
                            text = elem.text_content().strip()
                            if "ml" in text.lower():
                                try:
                                    price = Price.fromstring(text)
                                    variants.append({
                                        "size": text.strip(),
                                        "price": price.amount,
                                        "currency": price.currency
                                    })
                                    logging.info(f"Trovato prezzo multiplo: {text} - {price.amount} {price.currency}")
                                except Exception as e:
                                    logging.error(f"Errore nel parsing del prezzo multiplo '{text}': {str(e)}")
                    except Exception as e:
                        logging.error(f"Errore nel cercare prezzi multipli con {price_selector}: {str(e)}")
                        continue
            
            return variants
            
        except Exception as e:
            logging.error(f"Errore nell'estrazione dinamica delle varianti: {str(e)}")
            return []

    def _extract_from_google_search(self, brand: str, product: str) -> List[Dict]:
        """Estrae informazioni prodotto dai risultati di ricerca Google."""
        variants = []
        try:
            logging.info(f"Cercando {brand} {product} su Google")
            query = f"{brand} {product} prezzo"
            self.page.goto(f"https://www.google.com/search?q={query}")
            self.page.wait_for_load_state('networkidle')
            time.sleep(2)  # Attendi un po' per il caricamento completo
            
            # Cerca i risultati di ricerca (aggiornati per la struttura attuale di Google)
            results = self.page.query_selector_all("div[data-hveid]")
            
            for result in results:
                try:
                    # Estrai titolo e descrizione (aggiornati per la struttura attuale di Google)
                    title = result.query_selector("h3")
                    description = result.query_selector("div[data-content-feature='1']")
                    
                    if title and description:
                        title_text = title.text_content().strip()
                        desc_text = description.text_content().strip()
                        
                        # Log per debug
                        logging.info(f"Trovato risultato - Titolo: {title_text}")
                        logging.info(f"Descrizione: {desc_text}")
                        
                        # Cerca il formato (es. 100ml, 50ml, etc.)
                        size_match = re.search(r'(\d{1,4})\s*ml', desc_text.lower())
                        if size_match:
                            size = f"{size_match.group(1)}ml"
                            
                            # Cerca il prezzo (aggiornato per gestire più formati)
                            price_match = re.search(r'(\d{1,3}(?:[.,]\d{2})?)\s*€', desc_text)
                            if price_match:
                                try:
                                    price = float(price_match.group(1).replace(',', '.'))
                                    variants.append({
                                        "size": size,
                                        "price": price,
                                        "currency": "EUR",
                                        "source": "Google Search",
                                        "description": desc_text
                                    })
                                    logging.info(f"Trovata variante da Google: {size} - {price} EUR")
                                except Exception as e:
                                    logging.error(f"Errore nel parsing del prezzo: {str(e)}")
                                    
                except Exception as e:
                    logging.error(f"Errore nel processare risultato: {str(e)}")
                    continue
                
            return variants
            
        except Exception as e:
            logging.error(f"Errore nell'estrazione da Google: {str(e)}")
            return []

    def estrai_prezzo_formato(self, testo):
        prezzo_match = re.findall(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\s*€", testo)
        formato_match = re.findall(r"\b\d{2,3}\s*(?:ml|ML|mL)\b", testo)
        return prezzo_match, formato_match

    def estrai_formati_ml(self, *testi):
        formati = []
        for testo in testi:
            if testo:
                found = re.findall(r"\b\d{1,4}\s*(?:ml|ML|mL)\b", testo)
                formati.extend(found)
        return list(set(formati))

    def cerca_google_serpapi(self, query):
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": query,
            "hl": "it",
            "gl": "it",
            "api_key": self.settings_manager.get_settings()["serpapi"]["api_key"]
        }
        logging.info(f"Chiamata SerpAPI con query: {query}")
        res = requests.get(url, params=params)
        data = res.json()
        logging.info(f"Risposta SerpAPI: {json.dumps(data, indent=2)}")
        risultati = []
        
        # Estrai la descrizione principale se presente
        main_description = None
        if "knowledge_graph" in data and "description" in data["knowledge_graph"]:
            main_description = data["knowledge_graph"]["description"]
        
        # Estrai le immagini principali
        main_images = []
        if "knowledge_graph" in data and "thumbnails" in data["knowledge_graph"]:
            main_images = data["knowledge_graph"]["thumbnails"]
        
        for risultato in data.get("organic_results", []):
            titolo = risultato.get("title", "")
            snippet = risultato.get("snippet", "")
            descrizioni = [snippet, titolo]
            
            # Aggiungi la descrizione principale se presente
            if main_description:
                descrizioni.append(main_description)
            
            # Estrai immagini dal risultato
            immagini = []
            if "thumbnail" in risultato:
                immagini.append(risultato["thumbnail"])
            
            prezzi = []
            formati = []
            
            # Estrai da snippet e titolo
            prezzo_snip, formato_snip = self.estrai_prezzo_formato(snippet)
            prezzi.extend(prezzo_snip)
            formati.extend(formato_snip)
            formati.extend(self.estrai_formati_ml(snippet, titolo))
            
            # Estrai da rich_snippet
            rich = risultato.get("rich_snippet", {})
            for pos in ["top", "bottom"]:
                ext = rich.get(pos, {}).get("detected_extensions", {})
                if "price" in ext:
                    prezzi.append(f"{ext['price']} €")
                if "original_price" in ext:
                    prezzi.append(f"{ext['original_price']} €")
                if "currency" in ext and "price" in ext:
                    prezzi.append(f"{ext['price']} {ext['currency']}")
            
            # Estrai da extensions
            extensions = rich.get("top", {}).get("extensions", []) + rich.get("bottom", {}).get("extensions", [])
            for ext in extensions:
                if "€" in ext:
                    prezzi.append(ext)
                if "ml" in ext.lower():
                    formati.extend(self.estrai_formati_ml(ext))
            
            # Estrai da altri campi testuali se presenti
            for campo in ["description", "name"]:
                if campo in risultato:
                    descrizioni.append(risultato[campo])
                    formati.extend(self.estrai_formati_ml(risultato[campo]))
            
            risultati.append({
                "titolo": titolo,
                "descrizioni": [d for d in descrizioni if d],
                "prezzi": list(set(prezzi)),
                "formati": list(set(formati)),
                "immagini": immagini,
                "main_images": main_images if not immagini else []  # Aggiungi le immagini principali solo se non ci sono già immagini specifiche
            })
        
        return risultati

    def _get_unique_filename(self, folder_path: str, base_name: str, extension: str) -> str:
        """Genera un nome file unico aggiungendo numeri se necessario."""
        counter = 1
        filename = f"{base_name}{extension}"
        while os.path.exists(os.path.join(folder_path, filename)):
            filename = f"{base_name}_{counter}{extension}"
            counter += 1
        return filename

    def _optimize_image(self, img: Image.Image) -> Image.Image:
        """Ottimizza l'immagine per ridurre la dimensione."""
        # Ridimensiona se necessario
        if max(img.size) > IMAGE_SETTINGS["max_dimension"]:
            ratio = IMAGE_SETTINGS["max_dimension"] / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        return img

    def _save_image(self, image_data: bytes, brand: str, product: str, index: int = None) -> Optional[str]:
        """Salva l'immagine nella struttura delle cartelle appropriata."""
        try:
            # Crea il percorso della cartella brand
            brand_folder = os.path.join(IMAGE_SETTINGS["base_folder"], brand)
            os.makedirs(brand_folder, exist_ok=True)
            
            # Crea il percorso della cartella prodotto
            product_folder = os.path.join(brand_folder, product)
            os.makedirs(product_folder, exist_ok=True)
            
            # Apri l'immagine
            img = Image.open(BytesIO(image_data))
            
            # Ottimizza l'immagine
            img = self._optimize_image(img)
            
            # Prepara il nome base del file
            base_name = product
            if index is not None:
                base_name = f"{product}_{index}"
            
            # Determina l'estensione dal formato dell'immagine
            extension = f".{img.format.lower()}"
            
            # Genera un nome file unico
            filename = self._get_unique_filename(product_folder, base_name, extension)
            filepath = os.path.join(product_folder, filename)
            
            # Salva l'immagine con compressione
            if img.format == 'JPEG':
                img.save(filepath, 'JPEG', quality=IMAGE_SETTINGS["quality"], optimize=True)
            else:
                img.save(filepath, optimize=True)
            
            return filepath
            
        except Exception as e:
            logging.error(f"Errore nel salvataggio dell'immagine: {str(e)}")
            return None

    def _get_image_info(self, image_url: str, brand: str, product: str, index: int = None) -> Optional[Dict]:
        """Scarica l'immagine, ottiene informazioni e la salva."""
        try:
            response = requests.get(image_url, timeout=10)
            if response.status_code == 200:
                # Ottieni il tipo MIME
                content_type = response.headers.get('content-type', '')
                
                # Prova ad aprire l'immagine con PIL
                try:
                    img = Image.open(BytesIO(response.content))
                    width, height = img.size
                    format = img.format.lower()
                    
                    # Salva l'immagine
                    saved_path = self._save_image(response.content, brand, product, index)
                    
                    return {
                        'url': image_url,
                        'format': format,
                        'width': width,
                        'height': height,
                        'size_bytes': len(response.content),
                        'content_type': content_type,
                        'saved_path': saved_path
                    }
                except Exception as e:
                    logging.error(f"Errore nell'analisi dell'immagine {image_url}: {str(e)}")
                    return {
                        'url': image_url,
                        'format': content_type.split('/')[-1] if '/' in content_type else 'unknown',
                        'content_type': content_type
                    }
        except Exception as e:
            logging.error(f"Errore nel download dell'immagine {image_url}: {str(e)}")
            return None

    def _normalize_text(self, text: str) -> str:
        """Normalizza il testo per la ricerca, mantenendo le maiuscole iniziali."""
        if not text:
            return text
            
        # Rimuovi spazi extra e converti in minuscolo per la normalizzazione
        text = text.strip().lower()
        
        # Capitalizza la prima lettera di ogni parola
        words = text.split()
        normalized_words = []
        
        for word in words:
            # Gestisci casi speciali
            if word in ['de', 'di', 'da', 'del', 'della', 'delle', 'e', 'ed', 'la', 'le', 'il', 'lo', 'gli', 'un', 'una', 'uno']:
                normalized_words.append(word)
            else:
                normalized_words.append(word.capitalize())
        
        return ' '.join(normalized_words)

    def parse_user_input(self, input_text: str) -> List[Dict[str, str]]:
        """Analizza l'input dell'utente nel formato dove i prodotti sono tutte le righe tra i brand (indicati da ':')."""
        products = []
        current_brand = None
        current_products = []
        
        # Dividi il testo in righe e rimuovi spazi extra
        lines = [line.strip() for line in input_text.strip().split('\n') if line.strip()]
        
        for line in lines:
            if ':' in line:
                # Se abbiamo già un brand e prodotti, salviamoli
                if current_brand and current_products:
                    for product in current_products:
                        products.append({
                            'brand': self._normalize_text(current_brand),
                            'product': self._normalize_text(product)
                        })
                
                # Inizia un nuovo brand
                current_brand = line.replace(':', '').strip()
                current_products = []
            elif current_brand:
                # Aggiungi il prodotto al brand corrente
                current_products.append(line)
        
        # Aggiungi l'ultimo gruppo di prodotti
        if current_brand and current_products:
            for product in current_products:
                products.append({
                    'brand': self._normalize_text(current_brand),
                    'product': self._normalize_text(product)
                })
        
        return products

    def process_products(self, input_text: str, skip_price: bool = False, skip_variant: bool = False) -> List[Dict]:
        """Elabora una lista di prodotti dall'input dell'utente."""
        products = self.parse_user_input(input_text)
        results = []
        
        for product_info in products:
            try:
                # Costruisci la query
                query = f"{product_info['brand']} {product_info['product']}"
                logging.info(f"Elaborazione prodotto: {query}")
                
                # Cerca e crea il prodotto
                result = self.cerca_prodotto(
                    query,
                    skip_price=skip_price,
                    skip_variant=skip_variant
                )
                
                if result:
                    results.append({
                        'input': product_info,
                        'result': result
                    })
                else:
                    results.append({
                        'input': product_info,
                        'error': f"Nessun risultato trovato per {query}"
                    })
                    
            except Exception as e:
                logging.error(f"Errore nell'elaborazione di {query}: {str(e)}")
                results.append({
                    'input': product_info,
                    'error': str(e)
                })
        
        return results

    def cerca_prodotto(self, query, skip_price: bool = False, skip_variant: bool = False):
        """Cerca un prodotto e lo integra con Shopify."""
        risultati = self.cerca_google_serpapi(query)
        if not risultati:
            return None
        
        # Estrai brand e product dalla query
        parts = query.split()
        brand = parts[0] if parts else "unknown"
        product = " ".join(parts[1:]) if len(parts) > 1 else "unknown"
        
        # Estrai tutte le descrizioni
        descrizioni = []
        for r in risultati:
            descrizioni.extend(r.get("descrizioni", []))
        
        # Estrai tutte le immagini
        immagini = []
        for r in risultati:
            immagini.extend(r.get("immagini", []))
            immagini.extend(r.get("main_images", []))
        
        # Ottieni informazioni sulle immagini
        immagini_info = []
        for i, img_url in enumerate(set(immagini)):  # Rimuovi duplicati
            img_info = self._get_image_info(img_url, brand, product, i + 1)
            if img_info:
                immagini_info.append(img_info)
        
        # Estrai tutti i prezzi
        prezzi = []
        for r in risultati:
            prezzi.extend(r.get("prezzi", []))
        
        # Estrai tutti i formati
        formati = []
        for r in risultati:
            formati.extend(r.get("formati", []))
        
        # Calcola statistiche sui prezzi
        prezzi_numerici = []
        for prezzo in prezzi:
            try:
                # Rimuovi il simbolo dell'euro e altri caratteri non numerici
                prezzo_pulito = prezzo.replace("€", "").replace(",", ".").strip()
                # Estrai il primo numero trovato
                match = re.search(r'\d+\.?\d*', prezzo_pulito)
                if match:
                    prezzi_numerici.append(float(match.group()))
            except:
                continue
        
        # Calcola statistiche sui formati
        formati_ml = []
        for formato in formati:
            try:
                # Estrai il numero prima di "ml"
                match = re.search(r'(\d+)\s*ml', formato.lower())
                if match:
                    formati_ml.append(int(match.group(1)))
            except:
                continue
        
        # Unisci tutte le descrizioni in un unico testo
        descrizione_completa = " ".join(descrizioni)
        
        # Crea/aggiorna il prodotto su Shopify
        shopify_product = self._create_shopify_product({
            "brand": brand,
            "product": product,
            "descrizioni": descrizioni,
            "descrizione_completa": descrizione_completa,
            "immagini": immagini_info,
            "prezzi": prezzi,
            "prezzo_medio": statistics.mean(prezzi_numerici) if prezzi_numerici else None,
            "prezzo_min": min(prezzi_numerici) if prezzi_numerici else None,
            "prezzo_max": max(prezzi_numerici) if prezzi_numerici else None,
            "formati": formati,
            "formato_piu_comune": statistics.mode(formati_ml) if formati_ml else None,
            "formati_ml": formati_ml
        }, skip_price, skip_variant)
        
        return {
            "query": query,
            "brand": brand,
            "product": product,
            "descrizioni": descrizioni,
            "descrizione_completa": descrizione_completa,
            "immagini": immagini_info,
            "prezzi": prezzi,
            "prezzo_medio": statistics.mean(prezzi_numerici) if prezzi_numerici else None,
            "prezzo_min": min(prezzi_numerici) if prezzi_numerici else None,
            "prezzo_max": max(prezzi_numerici) if prezzi_numerici else None,
            "formati": formati,
            "formato_piu_comune": statistics.mode(formati_ml) if formati_ml else None,
            "formati_ml": formati_ml,
            "shopify_product": shopify_product
        }

    def _init_shopify(self):
        """Inizializza la connessione con Shopify."""
        try:
            settings = self.settings_manager.get_settings()["shopify"]
            
            # Configura la sessione di Shopify
            session = shopify.Session(
                settings['shop_url'],
                settings['api_version'],
                settings['access_token']
            )
            shopify.ShopifyResource.activate_session(session)
            
            # Verifica la connessione
            self.shop = shopify.shop.Shop.current()
            logging.info(f"Connessione Shopify inizializzata con successo per il negozio: {self.shop.name}")
            
            # Verifica le credenziali
            if not self.shop:
                raise ValueError("Impossibile connettersi a Shopify. Verifica le credenziali.")
                
        except Exception as e:
            logging.error(f"Errore nell'inizializzazione di Shopify: {str(e)}")
            raise

    def _find_existing_product(self, title: str) -> Optional[object]:
        """Cerca un prodotto esistente su Shopify, ignorando le maiuscole."""
        try:
            # Normalizza il titolo per la ricerca
            normalized_title = self._normalize_text(title)
            
            # Cerca prodotti con titolo simile usando la query API
            products = shopify.product.Product.find(
                title=normalized_title,
                limit=1
            )
            
            if products:
                return products[0]
            return None
            
        except Exception as e:
            logging.error(f"Errore nella ricerca del prodotto su Shopify: {str(e)}")
            return None

    def _create_or_update_vendor(self, vendor_name: str) -> bool:
        """Crea o aggiorna un vendor su Shopify."""
        try:
            # Verifica se il vendor esiste
            vendors = shopify.smart_collection.SmartCollection.find(
                title=vendor_name,
                limit=1
            )
            
            if not vendors:
                # Crea nuovo vendor
                vendor = shopify.smart_collection.SmartCollection()
                vendor.title = vendor_name
                vendor.rules = [{
                    "column": "vendor",
                    "relation": "equals",
                    "condition": vendor_name
                }]
                vendor.published = True
                vendor.save()
                logging.info(f"Vendor creato: {vendor_name}")
            return True
            
        except Exception as e:
            logging.error(f"Errore nella gestione del vendor: {str(e)}")
            return False

    def _create_or_update_tag(self, tag_name: str) -> bool:
        """Crea o aggiorna un tag su Shopify."""
        try:
            # I tag vengono gestiti automaticamente da Shopify quando vengono aggiunti ai prodotti
            return True
        except Exception as e:
            logging.error(f"Errore nella gestione del tag: {str(e)}")
            return False

    def _upload_image_to_shopify(self, image_path: str, product_id: int) -> bool:
        """Carica un'immagine su Shopify."""
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            image = shopify.product.Image()
            image.product_id = product_id
            image.attachment = base64.b64encode(image_data).decode('utf-8')
            image.position = 1  # Imposta la posizione dell'immagine
            image.save()
            
            logging.info(f"Immagine caricata con successo per il prodotto {product_id}")
            return True
            
        except Exception as e:
            logging.error(f"Errore nel caricamento dell'immagine su Shopify: {str(e)}")
            return False

    def _create_shopify_product(self, product_data: Dict, skip_price: bool = False, skip_variant: bool = False) -> Optional[object]:
        """Crea o aggiorna un prodotto su Shopify."""
        try:
            # Estrai i dati necessari
            brand = product_data.get('brand', '')
            product_name = product_data.get('product', '')
            title = f"{brand} {product_name}"
            
            # Verifica se il prodotto esiste
            existing_product = self._find_existing_product(title)
            
            if existing_product:
                product = existing_product
                logging.info(f"Prodotto esistente trovato: {title}")
            else:
                product = shopify.product.Product()
                product.title = title
                product.vendor = brand
                product.product_type = "Fragrance"
                product.tags = [brand]
                product.status = "active"  # Imposta il prodotto come attivo
                logging.info(f"Nuovo prodotto creato: {title}")

            # Gestisci la descrizione
            if not product.body_html and product_data.get('descrizione_completa'):
                product.body_html = product_data['descrizione_completa']
            
            # Gestisci prezzo e varianti se non da saltare
            if not skip_price and not skip_variant:
                variants = []
                for formato in product_data.get('formati_ml', []):
                    variant = shopify.product.Variant()
                    variant.title = f"{formato}ml"
                    variant.price = product_data.get('prezzo_medio')
                    variant.inventory_management = "shopify"
                    variant.inventory_quantity = 0
                    variant.requires_shipping = True
                    variant.taxable = True
                    variants.append(variant)
                
                if variants:
                    product.variants = variants

            # Salva il prodotto
            if product.save():
                logging.info(f"Prodotto salvato con successo: {title}")
                
                # Gestisci le immagini
                if product_data.get('immagini'):
                    for img_info in product_data['immagini']:
                        if img_info.get('saved_path'):
                            self._upload_image_to_shopify(img_info['saved_path'], product.id)
                
                # Gestisci vendor e tag
                self._create_or_update_vendor(brand)
                
                return product
            else:
                logging.error(f"Errore nel salvataggio del prodotto: {title}")
                return None
            
        except Exception as e:
            logging.error(f"Errore nella creazione/aggiornamento del prodotto su Shopify: {str(e)}")
            return None

    def _get_official_website_from_wikipedia(self, brand: str) -> Optional[str]:
        """Cerca il sito ufficiale del brand su Wikipedia."""
        try:
            logging.info(f"Cercando sito ufficiale su Wikipedia per {brand}")
            page = wikipedia.page(brand)
            html = page.html()
            soup = BeautifulSoup(html, "html.parser")
            
            # Cerca nel riquadro informativo
            infobox = soup.find("table", {"class": "infobox"})
            if infobox:
                for row in infobox.find_all("tr"):
                    if "Website" in row.text:
                        link = row.find("a", href=True)
                        if link and "http" in link['href']:
                            url = link['href']
                            logging.info(f"Trovato sito ufficiale su Wikipedia: {url}")
                            return url
                            
            # Cerca nel testo della pagina
            for link in soup.find_all("a", href=True):
                if "official" in link.text.lower() and "http" in link['href']:
                    url = link['href']
                    logging.info(f"Trovato sito ufficiale nel testo: {url}")
                    return url
                    
        except wikipedia.DisambiguationError as e:
            logging.warning(f"Disambiguazione necessaria per {brand}")
            # Prova con la prima opzione
            try:
                page = wikipedia.page(e.options[0])
                # ... ripeti la ricerca come sopra ...
            except Exception as e:
                logging.error(f"Errore nella disambiguazione: {str(e)}")
        except Exception as e:
            logging.error(f"Errore nella ricerca Wikipedia: {str(e)}")
        
        return None

    def _get_official_website_from_google(self, brand: str) -> Optional[str]:
        """Cerca il sito ufficiale del brand su Google."""
        try:
            logging.info(f"Cercando sito ufficiale su Google per {brand}")
            query = f"{brand} official website"
            self.page.goto(f"https://www.google.com/search?q={query}")
            time.sleep(2)  # Attendi il caricamento
            
            # Cerca il primo risultato non pubblicitario
            results = self.page.query_selector_all("div.g")
            for result in results:
                link = result.query_selector("a")
                if link:
                    url = link.get_attribute("href")
                    if url and not any(x in url for x in ["google.com", "youtube.com", "facebook.com"]):
                        logging.info(f"Trovato sito ufficiale su Google: {url}")
                        return url
                        
        except Exception as e:
            logging.error(f"Errore nella ricerca Google: {str(e)}")
        
        return None

    def _find_official_website(self, brand: str) -> Optional[str]:
        """Trova il sito ufficiale del brand usando Wikipedia e Google."""
        # Prima prova con Wikipedia
        url = self._get_official_website_from_wikipedia(brand)
        if url:
            return url
            
        # Se Wikipedia non funziona, prova con Google
        url = self._get_official_website_from_google(brand)
        if url:
            return url
            
        logging.warning(f"Nessun sito ufficiale trovato per {brand}")
        return None

    def _search_product_on_official_site(self, brand: str, product: str, official_url: str) -> Optional[str]:
        """Cerca il prodotto sul sito ufficiale."""
        try:
            domain = urlparse(official_url).netloc
            logging.info(f"Cercando {product} su {domain}")
            
            # Prova prima la ricerca interna
            search_url = f"{official_url.rstrip('/')}/search?q={product}"
            logging.info(f"Tentativo di ricerca su: {search_url}")
            self.page.goto(search_url)
            
            # Attendi il caricamento completo della pagina
            self.page.wait_for_load_state('networkidle')
            time.sleep(3)  # Attendi un po' di più per il caricamento dinamico
            
            # Ottieni la configurazione dei selettori per questo sito
            config = self._get_site_config(official_url)
            search_selectors = config["search_selectors"]
            
            # Prova ogni selettore per trovare i risultati
            for selector in search_selectors:
                try:
                    logging.info(f"Provo il selettore: {selector}")
                    # Attendi che almeno un elemento sia presente
                    self.page.wait_for_selector(selector, timeout=5000)
                    elements = self.page.query_selector_all(selector)
                    
                    if elements:
                        logging.info(f"Trovati {len(elements)} elementi con selettore {selector}")
                        # Per ogni elemento trovato
                        for element in elements:
                            try:
                                # Estrai il testo e l'URL
                                text = element.text_content().strip().lower()
                                href = element.get_attribute("href")
                                
                                # Log per debug
                                logging.info(f"Elemento trovato - Testo: {text}")
                                if href:
                                    logging.info(f"URL trovato: {href}")
                                
                                # Verifica se il testo contiene il nome del prodotto
                                if product.lower() in text:
                                    if href:
                                        if not href.startswith("http"):
                                            href = f"{official_url.rstrip('/')}/{href.lstrip('/')}"
                                        logging.info(f"Trovato prodotto su {domain}: {href}")
                                        return href
                            except Exception as e:
                                logging.error(f"Errore nel processare elemento: {str(e)}")
                                continue
                except TimeoutError:
                    logging.info(f"Nessun elemento trovato con selettore {selector}")
                    continue
                except Exception as e:
                    logging.error(f"Errore con selettore {selector}: {str(e)}")
                    continue
            
            # Se non trova con la ricerca interna, prova con Google
            logging.info("Nessun risultato trovato con la ricerca interna, provo con Google")
            query = f"site:{domain} {brand} {product}"
            self.page.goto(f"https://www.google.com/search?q={query}")
            time.sleep(2)
            
            results = self.page.query_selector_all("div.g")
            for result in results:
                link = result.query_selector("a")
                if link:
                    url = link.get_attribute("href")
                    if url and domain in url:
                        logging.info(f"Trovato prodotto via Google: {url}")
                        return url
                        
        except Exception as e:
            logging.error(f"Errore nella ricerca del prodotto: {str(e)}")
        
        logging.warning(f"Nessun risultato trovato per {product} su {domain}")
        return None

    def _scrape_niche_perfume(self, brand: str, product_name: str) -> Optional[Dict]:
        """Scrape from Niche Perfume"""
        try:
            search_url = f"https://www.nicheperfume.com/search?q={quote_plus(f'{brand} {product_name}')}"
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(search_url)
                page.wait_for_load_state('networkidle')
                
                # Implementa la logica specifica per Niche Perfume
                product_data = {
                    'title': f"{brand} {product_name}",
                    'description': self._extract_niche_perfume_description(page),
                    'price': self._extract_niche_perfume_price(page),
                    'variants': self._extract_niche_perfume_variants(page)
                }
                
                browser.close()
                return product_data if product_data['price'] else None
        except Exception as e:
            logging.error(f"Error scraping Niche Perfume: {str(e)}")
            return None

    def _scrape_first_in_fragrance(self, brand: str, product_name: str) -> Optional[Dict]:
        """Scrape from First in Fragrance"""
        try:
            search_url = f"https://www.ausliebezumduft.de/search?q={quote_plus(f'{brand} {product_name}')}"
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(search_url)
                page.wait_for_load_state('networkidle')
                
                # Implementa la logica specifica per First in Fragrance
                product_data = {
                    'title': f"{brand} {product_name}",
                    'description': self._extract_fif_description(page),
                    'price': self._extract_fif_price(page),
                    'variants': self._extract_fif_variants(page)
                }
                
                browser.close()
                return product_data if product_data['price'] else None
        except Exception as e:
            logging.error(f"Error scraping First in Fragrance: {str(e)}")
            return None

    def _scrape_jovoy(self, brand: str, product_name: str) -> Optional[Dict]:
        """Scrape from Jovoy Paris"""
        try:
            search_url = f"https://www.jovoyparis.com/search?q={quote_plus(f'{brand} {product_name}')}"
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(search_url)
                page.wait_for_load_state('networkidle')
                
                # Implementa la logica specifica per Jovoy
                product_data = {
                    'title': f"{brand} {product_name}",
                    'description': self._extract_jovoy_description(page),
                    'price': self._extract_jovoy_price(page),
                    'variants': self._extract_jovoy_variants(page)
                }
                
                browser.close()
                return product_data if product_data['price'] else None
        except Exception as e:
            logging.error(f"Error scraping Jovoy: {str(e)}")
            return None

    def _scrape_nose(self, brand: str, product_name: str) -> Optional[Dict]:
        """Scrape from Nose Paris"""
        try:
            search_url = f"https://nose.fr/search?q={quote_plus(f'{brand} {product_name}')}"
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(search_url)
                page.wait_for_load_state('networkidle')
                
                # Implementa la logica specifica per Nose
                product_data = {
                    'title': f"{brand} {product_name}",
                    'description': self._extract_nose_description(page),
                    'price': self._extract_nose_price(page),
                    'variants': self._extract_nose_variants(page)
                }
                
                browser.close()
                return product_data if product_data['price'] else None
        except Exception as e:
            logging.error(f"Error scraping Nose: {str(e)}")
            return None

    def _scrape_osswald(self, brand: str, product_name: str) -> Optional[Dict]:
        """Scrape from Osswald"""
        try:
            search_url = f"https://www.osswald.com/search?q={quote_plus(f'{brand} {product_name}')}"
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(search_url)
                page.wait_for_load_state('networkidle')
                
                # Implementa la logica specifica per Osswald
                product_data = {
                    'title': f"{brand} {product_name}",
                    'description': self._extract_osswald_description(page),
                    'price': self._extract_osswald_price(page),
                    'variants': self._extract_osswald_variants(page)
                }
                
                browser.close()
                return product_data if product_data['price'] else None
        except Exception as e:
            logging.error(f"Error scraping Osswald: {str(e)}")
            return None

    # Metodi di estrazione per Google Shopping
    def _extract_google_description(self, page) -> str:
        try:
            description = page.query_selector('.sh-dgr__content-summary')
            return description.inner_text() if description else ''
        except Exception as e:
            logging.error(f"Error extracting Google description: {str(e)}")
            return ''

    def _extract_google_price(self, page) -> Optional[float]:
        try:
            # Cerca il prezzo della prima variante valida
            variants = self._extract_google_variants(page)
            if variants:
                return variants[0]['price']
            # Fallback: cerca il primo prezzo generico
            price_element = page.query_selector('.a8Pemb')
            if price_element:
                raw_price = price_element.inner_text()
                logging.info(f"[Google Fallback] Prezzo grezzo: {raw_price}")
                return self._parse_price(raw_price)
            return None
        except Exception as e:
            logging.error(f"Error extracting Google price: {str(e)}")
            return None

    def _extract_google_variants(self, page) -> List[Dict]:
        try:
            variants = []
            variant_elements = page.query_selector_all('.sh-dgr__content-result')
            for element in variant_elements:
                # Prova a estrarre titolo e prezzo
                title = element.query_selector('.tAxDx')
                price = element.query_selector('.a8Pemb')
                # Logga il testo grezzo
                raw_title = title.inner_text() if title else ''
                raw_price = price.inner_text() if price else ''
                logging.info(f"[Google Variant] Titolo grezzo: {raw_title} | Prezzo grezzo: {raw_price}")
                # Cerca di estrarre la dimensione in ml dal titolo
                size_ml = None
                import re
                match = re.search(r'(\d{1,4}) ?ml', raw_title.lower())
                if match:
                    size_ml = int(match.group(1))
                if raw_title and raw_price:
                    variants.append({
                        'title': raw_title,
                        'size_ml': size_ml,
                        'price': self._parse_price(raw_price)
                    })
            return variants
        except Exception as e:
            logging.error(f"Error extracting Google variants: {str(e)}")
            return []

    # Metodi di estrazione per Niche Perfume
    def _extract_niche_perfume_description(self, page) -> str:
        try:
            description = page.query_selector('.product-description')
            return description.inner_text() if description else ''
        except Exception as e:
            logging.error(f"Error extracting Niche Perfume description: {str(e)}")
            return ''

    def _extract_niche_perfume_price(self, page) -> Optional[float]:
        try:
            price_element = page.query_selector('.product-price')
            if price_element:
                return self._parse_price(price_element.inner_text())
            return None
        except Exception as e:
            logging.error(f"Error extracting Niche Perfume price: {str(e)}")
            return None

    def _extract_niche_perfume_variants(self, page) -> List[Dict]:
        try:
            variants = []
            variant_elements = page.query_selector_all('.product-variant')
            
            for element in variant_elements:
                title = element.query_selector('.variant-title')
                price = element.query_selector('.variant-price')
                
                if title and price:
                    variants.append({
                        'title': title.inner_text(),
                        'price': self._parse_price(price.inner_text())
                    })
            
            return variants
        except Exception as e:
            logging.error(f"Error extracting Niche Perfume variants: {str(e)}")
            return []

    # Metodi di estrazione per First in Fragrance
    def _extract_fif_description(self, page) -> str:
        try:
            description = page.query_selector('.product-description')
            return description.inner_text() if description else ''
        except Exception as e:
            logging.error(f"Error extracting First in Fragrance description: {str(e)}")
            return ''

    def _extract_fif_price(self, page) -> Optional[float]:
        try:
            price_element = page.query_selector('.product-price')
            if price_element:
                return self._parse_price(price_element.inner_text())
            return None
        except Exception as e:
            logging.error(f"Error extracting First in Fragrance price: {str(e)}")
            return None

    def _extract_fif_variants(self, page) -> List[Dict]:
        try:
            variants = []
            variant_elements = page.query_selector_all('.product-variant')
            
            for element in variant_elements:
                title = element.query_selector('.variant-title')
                price = element.query_selector('.variant-price')
                
                if title and price:
                    variants.append({
                        'title': title.inner_text(),
                        'price': self._parse_price(price.inner_text())
                    })
            
            return variants
        except Exception as e:
            logging.error(f"Error extracting First in Fragrance variants: {str(e)}")
            return []

    # Metodi di estrazione per Jovoy
    def _extract_jovoy_description(self, page) -> str:
        try:
            description = page.query_selector('.product-description')
            return description.inner_text() if description else ''
        except Exception as e:
            logging.error(f"Error extracting Jovoy description: {str(e)}")
            return ''

    def _extract_jovoy_price(self, page) -> Optional[float]:
        try:
            price_element = page.query_selector('.product-price')
            if price_element:
                return self._parse_price(price_element.inner_text())
            return None
        except Exception as e:
            logging.error(f"Error extracting Jovoy price: {str(e)}")
            return None

    def _extract_jovoy_variants(self, page) -> List[Dict]:
        try:
            variants = []
            variant_elements = page.query_selector_all('.product-variant')
            
            for element in variant_elements:
                title = element.query_selector('.variant-title')
                price = element.query_selector('.variant-price')
                
                if title and price:
                    variants.append({
                        'title': title.inner_text(),
                        'price': self._parse_price(price.inner_text())
                    })
            
            return variants
        except Exception as e:
            logging.error(f"Error extracting Jovoy variants: {str(e)}")
            return []

    # Metodi di estrazione per Nose
    def _extract_nose_description(self, page) -> str:
        try:
            description = page.query_selector('.product-description')
            return description.inner_text() if description else ''
        except Exception as e:
            logging.error(f"Error extracting Nose description: {str(e)}")
            return ''

    def _extract_nose_price(self, page) -> Optional[float]:
        try:
            price_element = page.query_selector('.product-price')
            if price_element:
                return self._parse_price(price_element.inner_text())
            return None
        except Exception as e:
            logging.error(f"Error extracting Nose price: {str(e)}")
            return None

    def _extract_nose_variants(self, page) -> List[Dict]:
        try:
            variants = []
            variant_elements = page.query_selector_all('.product-variant')
            
            for element in variant_elements:
                title = element.query_selector('.variant-title')
                price = element.query_selector('.variant-price')
                
                if title and price:
                    variants.append({
                        'title': title.inner_text(),
                        'price': self._parse_price(price.inner_text())
                    })
            
            return variants
        except Exception as e:
            logging.error(f"Error extracting Nose variants: {str(e)}")
            return []

    # Metodi di estrazione per Osswald
    def _extract_osswald_description(self, page) -> str:
        try:
            description = page.query_selector('.product-description')
            return description.inner_text() if description else ''
        except Exception as e:
            logging.error(f"Error extracting Osswald description: {str(e)}")
            return ''

    def _extract_osswald_price(self, page) -> Optional[float]:
        try:
            price_element = page.query_selector('.product-price')
            if price_element:
                return self._parse_price(price_element.inner_text())
            return None
        except Exception as e:
            logging.error(f"Error extracting Osswald price: {str(e)}")
            return None

    def _extract_osswald_variants(self, page) -> List[Dict]:
        try:
            variants = []
            variant_elements = page.query_selector_all('.product-variant')
            
            for element in variant_elements:
                title = element.query_selector('.variant-title')
                price = element.query_selector('.variant-price')
                
                if title and price:
                    variants.append({
                        'title': title.inner_text(),
                        'price': self._parse_price(price.inner_text())
                    })
            
            return variants
        except Exception as e:
            logging.error(f"Error extracting Osswald variants: {str(e)}")
            return []

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price text to float"""
        try:
            # Remove currency symbols and convert to float
            price = re.sub(r'[^\d.,]', '', price_text)
            price = price.replace(',', '.')
            return float(price)
        except Exception as e:
            logging.error(f"Error parsing price {price_text}: {str(e)}")
            return None 