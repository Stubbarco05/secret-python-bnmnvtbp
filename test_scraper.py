from collections import Counter
from product_scraper import ProductScraper
import logging
import json

# Configura il logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_scraper():
    # Carica le impostazioni
    try:
        with open('settings.json', 'r') as f:
            settings = json.load(f)
    except Exception as e:
        logging.error(f"Errore nel caricamento delle impostazioni: {str(e)}")
        return

    scraper = ProductScraper()
    
    # Test con Xerjoff Naxos
    brand = "Xerjoff"
    product = "Naxos"
    
    print(f"\nTest di ricerca per {brand} {product}")
    print("-" * 50)
    
    risultati = scraper.scrape_product(brand, product)
    
    if not risultati:
        print("Nessun risultato trovato")
        return
    
    print("Risultati trovati:")
    tutti_i_formati = []
    for idx, result in enumerate(risultati, 1):
        print(f"\nRisultato {idx}:")
        print(f"Titolo: {result.get('titolo')}")
        print("Descrizioni trovate:")
        for desc in result.get('descrizioni', []):
            print(f"- {desc}")
        print(f"Prezzi trovati: {result.get('prezzi')}")
        print(f"Formati trovati: {result.get('formati')}")
        tutti_i_formati.extend(result.get('formati', []))
        print("-"*40)
    if tutti_i_formati:
        print("\nFormati più frequenti tra tutti i risultati:")
        counter = Counter(tutti_i_formati)
        for formato, count in counter.most_common():
            print(f"{formato}: {count} occorrenze")

if __name__ == "__main__":
    test_scraper() 