import logging
from product_scraper import ProductScraper
import json

def test_shopify_integration():
    """Test dell'integrazione con Shopify e gestione delle impostazioni."""
    try:
        # Inizializza lo scraper
        scraper = ProductScraper()
        
        # Test 1: Verifica delle impostazioni correnti
        print("\n1. Verifica delle impostazioni correnti:")
        current_settings = scraper.get_settings()
        print(json.dumps(current_settings, indent=2))
        
        # Test 2: Verifica della connessione Shopify
        print("\n2. Verifica della connessione Shopify:")
        shop = scraper.shop
        print(f"Connesso al negozio: {shop.name}")
        print(f"Email del negozio: {shop.email}")
        print(f"Dominio del negozio: {shop.domain}")
        
        # Test 3: Creazione di un prodotto di test
        print("\n3. Creazione di un prodotto di test:")
        test_product = {
            "brand": "Test Brand",
            "product": "Test Product",
            "descrizioni": ["This is a test product description"],
            "descrizione_completa": "This is a complete test product description",
            "immagini": [],
            "prezzi": ["100.00 €"],
            "prezzo_medio": 100.00,
            "prezzo_min": 100.00,
            "prezzo_max": 100.00,
            "formati": ["100ml"],
            "formato_piu_comune": "100ml",
            "formati_ml": [100]
        }
        
        product = scraper._create_shopify_product(test_product)
        if product:
            print(f"Prodotto creato con successo:")
            print(f"ID: {product.id}")
            print(f"Titolo: {product.title}")
            print(f"Vendor: {product.vendor}")
            print(f"Tipo: {product.product_type}")
            print(f"Tags: {product.tags}")
            
            # Test 4: Ricerca del prodotto appena creato
            print("\n4. Ricerca del prodotto appena creato:")
            found_product = scraper._find_existing_product(product.title)
            if found_product:
                print(f"Prodotto trovato: {found_product.title}")
            else:
                print("Prodotto non trovato")
            
            # Test 5: Verifica del vendor
            print("\n5. Verifica del vendor:")
            vendor_created = scraper._create_or_update_vendor(test_product["brand"])
            print(f"Vendor creato/aggiornato: {vendor_created}")
            
        else:
            print("Errore nella creazione del prodotto di test")
        
    except Exception as e:
        print(f"\nErrore durante il test: {str(e)}")
        logging.error(f"Errore durante il test: {str(e)}")
    finally:
        # Chiudi lo scraper
        if 'scraper' in locals():
            del scraper

if __name__ == "__main__":
    test_shopify_integration() 