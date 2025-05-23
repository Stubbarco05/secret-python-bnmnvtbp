from product_scraper import ProductScraper
import pprint

if __name__ == "__main__":
    scraper = ProductScraper()
    query = "Xerjoff Naxos"
    print(f"\n--- Test ricerca Google/SerpAPI per: {query} ---\n")
    risultati = scraper.cerca_google_serpapi(query)
    pprint.pprint(risultati)
    print(f"\nTotale risultati trovati: {len(risultati)}\n")
    if risultati:
        primo = risultati[0]
        print("\n--- Primo risultato ---")
        pprint.pprint(primo) 