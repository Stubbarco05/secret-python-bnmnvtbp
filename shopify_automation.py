import sys
import os
import json
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QTextEdit, QPushButton, QLabel, 
                            QFileDialog, QMessageBox, QTabWidget, QLineEdit,
                            QProgressBar, QCheckBox, QScrollArea, QDialog,
                            QListWidget, QListWidgetItem, QGridLayout, QFormLayout)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QPalette, QColor
import shopify
from dotenv import load_dotenv
from shopify_handler import ShopifyHandler
from product_scraper import ProductScraper
from typing import Dict, List
from shopify_api import ShopifyAPI
from web_scraper import WebScraper
from image_processor import ImageProcessor

# Configure logging
logging.basicConfig(
    filename='shopify_automation.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Set application style
app = QApplication(sys.argv)
app.setStyle('Fusion')

# Define a modern color palette
palette = QPalette()
palette.setColor(QPalette.Window, QColor(53, 53, 53))
palette.setColor(QPalette.WindowText, Qt.white)
palette.setColor(QPalette.Base, QColor(25, 25, 25))
palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
palette.setColor(QPalette.ToolTipBase, Qt.white)
palette.setColor(QPalette.ToolTipText, Qt.white)
palette.setColor(QPalette.Text, Qt.white)
palette.setColor(QPalette.Button, QColor(53, 53, 53))
palette.setColor(QPalette.ButtonText, Qt.white)
palette.setColor(QPalette.BrightText, Qt.red)
palette.setColor(QPalette.Link, QColor(42, 130, 218))
palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
palette.setColor(QPalette.HighlightedText, Qt.black)

app.setPalette(palette)

class MissingPricesDialog(QDialog):
    def __init__(self, products, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Products with Missing Prices")
        self.setMinimumSize(600, 400)
        self.products = products
        self.selected_products = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Product list
        self.product_list = QListWidget()
        for product in self.products:
            item = QListWidgetItem(f"{product.title} - {product.vendor}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.product_list.addItem(item)

        layout.addWidget(self.product_list)

        # Buttons
        button_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(deselect_all_btn)

        update_btn = QPushButton("Update Selected")
        update_btn.clicked.connect(self.accept)
        button_layout.addWidget(update_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def select_all(self):
        for i in range(self.product_list.count()):
            item = self.product_list.item(i)
            item.setCheckState(Qt.CheckState.Checked)

    def deselect_all(self):
        for i in range(self.product_list.count()):
            item = self.product_list.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)

    def get_selected_products(self):
        selected = []
        for i in range(self.product_list.count()):
            item = self.product_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(self.products[i])
        return selected

class ShopifyWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, shop_url, access_token, input_text, image_folder):
        super().__init__()
        self.shop_url = shop_url
        self.access_token = access_token
        self.input_text = input_text
        self.image_folder = image_folder
        self.shopify_handler = None
        self.scraper = ProductScraper()

    def run(self):
        try:
            self.shopify_handler = ShopifyHandler(self.shop_url, self.access_token)
            self.process_input()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
            logging.error(f"Error in ShopifyWorker: {str(e)}")

    def process_input(self):
        # Parse input text into brands and products
        brands_products = {}
        current_brand = None
        
        for line in self.input_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.endswith(':'):
                current_brand = line[:-1].strip()
                brands_products[current_brand] = []
            elif current_brand:
                brands_products[current_brand].append(line)

        # Process each brand and its products
        for brand, products in brands_products.items():
            self.progress.emit(f"Processing brand: {brand}")
            
            # Get or create vendor and tag
            vendor = self.shopify_handler.get_or_create_vendor(brand)
            tag = self.shopify_handler.get_or_create_tag(brand)
            
            # Process each product
            for product in products:
                self.progress.emit(f"Processing product: {product}")
                self.process_product(product, vendor, tag)

    def process_product(self, product_name, vendor, tag):
        # Check if product exists
        existing_product = self.shopify_handler.find_product(product_name)
        
        if existing_product:
            self.progress.emit(f"Product {product_name} already exists, checking for missing data...")
            self.update_existing_product(existing_product, vendor, tag)
        else:
            self.progress.emit(f"Creating new product: {product_name}")
            self.create_new_product(product_name, vendor, tag)

    def update_existing_product(self, product, vendor, tag):
        # Check for missing data
        missing_data = {}
        
        if not product.body_html:
            missing_data['description'] = True
        if not product.variants or any(not v.price for v in product.variants):
            missing_data['price'] = True
        if not product.images:
            missing_data['images'] = True

        if missing_data:
            # Scrape missing data
            product_data = self.scraper.scrape_product(vendor, product.title)
            if product_data:
                update_data = {}
                if 'description' in missing_data and product_data.get('description'):
                    update_data['description'] = product_data['description']
                if 'price' in missing_data and product_data.get('variants'):
                    update_data['variants'] = product_data['variants']
                
                if update_data:
                    self.shopify_handler.update_product(product, update_data)
                    self.progress.emit(f"Updated product {product.title} with missing data")

    def create_new_product(self, product_name, vendor, tag):
        # Scrape product data
        product_data = self.scraper.scrape_product(vendor, product_name)
        
        if product_data:
            # Add vendor and tag
            product_data['vendor'] = vendor
            product_data['tags'] = tag
            
            # Create product
            product = self.shopify_handler.create_product(product_data)
            
            # Add images if available
            if self.image_folder:
                image_path = os.path.join(self.image_folder, vendor, product_name)
                if os.path.exists(image_path):
                    image_files = [os.path.join(image_path, f) for f in os.listdir(image_path)
                                 if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                    if image_files:
                        self.shopify_handler.add_product_images(product, image_files)
            
            self.progress.emit(f"Created new product: {product_name}")
        else:
            self.progress.emit(f"Could not find data for product: {product_name}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shopify Automation Tool")
        self.setMinimumSize(800, 600)
        
        # Initialize UI
        self.init_ui()
        
        # Load settings
        self.load_settings()

    def init_ui(self):
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Main tab
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)

        # Input text area
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Enter brands and products in the format:\nbrand:\nproduct1\nproduct2\n\nbrand2:\nproduct1\nproduct2")
        main_layout.addWidget(self.input_text)

        # Buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Analysis and Update")
        self.start_button.clicked.connect(self.start_processing)
        button_layout.addWidget(self.start_button)

        self.check_prices_button = QPushButton("Check Missing Prices")
        self.check_prices_button.clicked.connect(self.check_missing_prices)
        button_layout.addWidget(self.check_prices_button)

        main_layout.addLayout(button_layout)

        # Progress area
        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        main_layout.addWidget(self.progress_text)

        # Settings tab
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)

        # Shopify settings
        shopify_group = QWidget()
        shopify_layout = QFormLayout(shopify_group)

        self.shop_url_input = QLineEdit()
        self.shop_url_input.setPlaceholderText("Shop URL (e.g., your-store.myshopify.com)")
        shopify_layout.addRow("Shop URL:", self.shop_url_input)

        self.access_token_input = QLineEdit()
        self.access_token_input.setPlaceholderText("Access Token")
        self.access_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        shopify_layout.addRow("Access Token:", self.access_token_input)

        settings_layout.addWidget(shopify_group)

        # Image folder settings
        image_group = QWidget()
        image_layout = QHBoxLayout(image_group)

        self.image_folder_input = QLineEdit()
        self.image_folder_input.setReadOnly(True)
        image_layout.addWidget(self.image_folder_input)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_image_folder)
        image_layout.addWidget(browse_button)

        settings_layout.addWidget(image_group)

        # Save settings button
        save_settings_button = QPushButton("Save Settings")
        save_settings_button.clicked.connect(self.save_settings)
        settings_layout.addWidget(save_settings_button)

        # Add tabs
        tabs.addTab(main_tab, "Main")
        tabs.addTab(settings_tab, "Settings")

    def load_settings(self):
        try:
            if os.path.exists('settings.json'):
                with open('settings.json', 'r') as f:
                    settings = json.load(f)
                    self.shop_url_input.setText(settings.get('shop_url', ''))
                    self.access_token_input.setText(settings.get('access_token', ''))
                    self.image_folder_input.setText(settings.get('image_folder', ''))
        except Exception as e:
            logging.error(f"Error loading settings: {str(e)}")

    def save_settings(self):
        settings = {
            'shop_url': self.shop_url_input.text(),
            'access_token': self.access_token_input.text(),
            'image_folder': self.image_folder_input.text()
        }
        try:
            with open('settings.json', 'w') as f:
                json.dump(settings, f)
            QMessageBox.information(self, "Success", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")
            logging.error(f"Error saving settings: {str(e)}")

    def browse_image_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder:
            self.image_folder_input.setText(folder)

    def start_processing(self):
        if not self.validate_settings():
            return

        self.worker = ShopifyWorker(
            self.shop_url_input.text(),
            self.access_token_input.text(),
            self.input_text.toPlainText(),
            self.image_folder_input.text()
        )
        
        self.worker.progress.connect(self.update_progress)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.processing_finished)
        
        self.start_button.setEnabled(False)
        self.worker.start()

    def check_missing_prices(self):
        if not self.validate_settings():
            return

        try:
            shopify_handler = ShopifyHandler(
                self.shop_url_input.text(),
                self.access_token_input.text()
            )
            
            products = shopify_handler.get_products_without_prices()
            
            if products:
                dialog = MissingPricesDialog(products, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    selected_products = dialog.get_selected_products()
                    self.update_selected_products(selected_products)
            else:
                QMessageBox.information(self, "Info", "No products with missing prices found!")
                
        except Exception as e:
            self.show_error(str(e))

    def update_selected_products(self, products):
        self.worker = ShopifyWorker(
            self.shop_url_input.text(),
            self.access_token_input.text(),
            "",  # No input text needed for updates
            self.image_folder_input.text()
        )
        
        self.worker.progress.connect(self.update_progress)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.processing_finished)
        
        self.start_button.setEnabled(False)
        self.worker.start()

    def validate_settings(self):
        if not self.shop_url_input.text() or not self.access_token_input.text():
            QMessageBox.warning(self, "Warning", "Please fill in all Shopify settings!")
            return False
        return True

    def update_progress(self, message):
        self.progress_text.append(message)
        logging.info(message)

    def show_error(self, error_message):
        QMessageBox.critical(self, "Error", error_message)
        logging.error(error_message)

    def processing_finished(self):
        self.start_button.setEnabled(True)
        QMessageBox.information(self, "Success", "Processing completed!")

class ShopifyAutomation:
    def __init__(self):
        self.shopify = None
        self.scraper = None
        self.image_processor = None
        self.settings = self.load_settings()

    def load_settings(self):
        try:
            with open('settings.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def initialize(self, settings):
        self.settings = settings
        self.shopify = ShopifyAPI(settings['shopifyDomain'], settings['apiToken'])
        self.scraper = WebScraper()
        if settings.get('imagesPath'):
            self.image_processor = ImageProcessor(settings['imagesPath'])

    def analyze_product(self, url, category):
        try:
            # Invia progresso
            self.send_progress(10, 'Analisi del prodotto in corso...')
            
            # Ottieni dati dal sito
            product_data = self.scraper.scrape_product(url)
            self.send_progress(30, 'Dati del prodotto ottenuti')
            
            # Verifica prezzi
            price_check = self.shopify.check_prices(product_data['price'])
            self.send_progress(50, 'Verifica prezzi completata')
            
            # Elabora immagini se necessario
            if self.image_processor:
                images = self.image_processor.process_images(product_data['images'])
                self.send_progress(70, 'Immagini elaborate')
            else:
                images = product_data['images']
            
            # Prepara risultati
            results = {
                'product_data': product_data,
                'price_check': price_check,
                'images': images,
                'category': category
            }
            
            self.send_progress(100, 'Analisi completata')
            self.send_results(results)
            
        except Exception as e:
            self.send_error(str(e))

    def send_progress(self, value, message):
        output = {
            'type': 'progress',
            'value': value,
            'message': message
        }
        print(json.dumps(output))
        sys.stdout.flush()

    def send_results(self, results):
        output = {
            'type': 'result',
            'results': results
        }
        print(json.dumps(output))
        sys.stdout.flush()

    def send_error(self, error):
        output = {
            'type': 'error',
            'message': error
        }
        print(json.dumps(output))
        sys.stdout.flush()

def main():
    automation = ShopifyAutomation()
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            data = json.loads(line)
            action = data.get('action')
            if action == 'analyze':
                automation.analyze_product(data['url'], data['category'])
            elif action == 'create-variants':
                # Nuova logica: crea varianti in Shopify
                product_title = data.get('productTitle')
                variants = data.get('variants', [])
                if not product_title or not variants:
                    print(json.dumps({'type': 'error', 'message': 'Dati varianti mancanti'}))
                    continue
                # Carica handler e crea prodotto/varianti
                handler = ShopifyHandler()
                product = handler.find_product(product_title)
                if product:
                    # Aggiorna prodotto esistente
                    update_data = {'variants': []}
                    for v in variants:
                        update_data['variants'].append({
                            'title': v.get('title', ''),
                            'price': v.get('price', 0),
                            'sku': f"{product_title}-{v.get('size_ml','') or v.get('title','')}"
                        })
                    handler.update_product(product, update_data)
                    print(json.dumps({'type': 'progress', 'value': 100, 'message': f'Varianti aggiornate per {product_title}'}))
                else:
                    # Crea nuovo prodotto
                    product_data = {
                        'title': product_title,
                        'vendor': '',
                        'tags': '',
                        'variants': []
                    }
                    for v in variants:
                        product_data['variants'].append({
                            'title': v.get('title', ''),
                            'price': v.get('price', 0),
                            'sku': f"{product_title}-{v.get('size_ml','') or v.get('title','')}"
                        })
                    handler.create_product(product_data)
                    print(json.dumps({'type': 'progress', 'value': 100, 'message': f'Prodotto creato con varianti per {product_title}'}))
        except Exception as e:
            print(json.dumps({'type': 'error', 'message': str(e)}))
            continue

if __name__ == "__main__":
    main() 