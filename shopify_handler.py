import shopify
import logging
from typing import List, Dict, Optional
import os
from datetime import datetime
import json

class ShopifyHandler:
    def __init__(self, settings_path: str = 'settings.json'):
        self.session = None
        self.shop_url = None
        self.access_token = None
        self.api_key = None
        self.api_secret = None
        self.load_settings(settings_path)
        self.initialize_session()

    def load_settings(self, settings_path: str):
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            self.shop_url = settings.get('shopify_domain')
            self.access_token = settings.get('shopify_token')
            self.api_key = settings.get('shopify_api_key')
            self.api_secret = settings.get('shopify_api_secret')
        except Exception as e:
            logging.error(f"Failed to load Shopify settings: {str(e)}")
            raise

    def initialize_session(self):
        try:
            self.session = shopify.Session(self.shop_url, '2024-01', self.access_token)
            shopify.ShopifyResource.activate_session(self.session)
        except Exception as e:
            logging.error(f"Failed to initialize Shopify session: {str(e)}")
            raise

    def get_or_create_vendor(self, brand_name: str) -> str:
        """Check if vendor exists, create if it doesn't"""
        try:
            # Search for existing products with this vendor
            products = shopify.Product.find(vendor=brand_name)
            if products:
                return brand_name

            # Create a test product with the vendor to establish it
            product = shopify.Product()
            product.title = f"Test Product - {brand_name}"
            product.vendor = brand_name
            product.product_type = "Perfume"
            product.status = "draft"
            product.save()

            # Delete the test product
            product.destroy()
            return brand_name
        except Exception as e:
            logging.error(f"Error in get_or_create_vendor: {str(e)}")
            raise

    def get_or_create_tag(self, brand_name: str) -> str:
        """Check if tag exists, create if it doesn't"""
        try:
            # Search for products with this tag
            products = shopify.Product.find(tag=brand_name)
            if products:
                return brand_name

            # Create a test product with the tag to establish it
            product = shopify.Product()
            product.title = f"Test Product - {brand_name}"
            product.tags = brand_name
            product.product_type = "Perfume"
            product.status = "draft"
            product.save()

            # Delete the test product
            product.destroy()
            return brand_name
        except Exception as e:
            logging.error(f"Error in get_or_create_tag: {str(e)}")
            raise

    def find_product(self, product_name: str) -> Optional[shopify.Product]:
        """Search for a product by name"""
        try:
            products = shopify.Product.find(title=product_name)
            return products[0] if products else None
        except Exception as e:
            logging.error(f"Error in find_product: {str(e)}")
            return None

    def create_product(self, product_data: Dict) -> shopify.Product:
        """Create a new product"""
        try:
            product = shopify.Product()
            product.title = product_data['title']
            product.vendor = product_data['vendor']
            product.product_type = "Perfume"
            product.tags = product_data['tags']
            product.body_html = product_data.get('description', '')
            product.status = "draft"

            # Create variants
            variants = []
            for variant_data in product_data.get('variants', []):
                variant = shopify.Variant()
                variant.title = variant_data['title']
                variant.price = variant_data['price']
                variant.sku = variant_data.get('sku', '')
                variant.inventory_management = "shopify"
                variant.inventory_quantity = 0
                variants.append(variant)

            product.variants = variants
            product.save()
            return product
        except Exception as e:
            logging.error(f"Error in create_product: {str(e)}")
            raise

    def update_product(self, product: shopify.Product, product_data: Dict) -> shopify.Product:
        """Update an existing product"""
        try:
            if 'title' in product_data:
                product.title = product_data['title']
            if 'vendor' in product_data:
                product.vendor = product_data['vendor']
            if 'tags' in product_data:
                product.tags = product_data['tags']
            if 'description' in product_data:
                product.body_html = product_data['description']

            # Update variants if provided
            if 'variants' in product_data:
                for variant_data in product_data['variants']:
                    variant = next((v for v in product.variants if v.title == variant_data['title']), None)
                    if variant:
                        variant.price = variant_data['price']
                        if 'sku' in variant_data:
                            variant.sku = variant_data['sku']
                    else:
                        new_variant = shopify.Variant()
                        new_variant.title = variant_data['title']
                        new_variant.price = variant_data['price']
                        new_variant.sku = variant_data.get('sku', '')
                        new_variant.inventory_management = "shopify"
                        new_variant.inventory_quantity = 0
                        product.variants.append(new_variant)

            product.save()
            return product
        except Exception as e:
            logging.error(f"Error in update_product: {str(e)}")
            raise

    def add_product_images(self, product: shopify.Product, image_paths: List[str]) -> None:
        """Add images to a product"""
        try:
            for image_path in image_paths:
                if os.path.exists(image_path):
                    with open(image_path, 'rb') as f:
                        image = shopify.Image()
                        image.product_id = product.id
                        image.attachment = f.read()
                        image.save()
        except Exception as e:
            logging.error(f"Error in add_product_images: {str(e)}")
            raise

    def get_products_without_prices(self) -> List[shopify.Product]:
        """Get all products that have variants without prices"""
        try:
            products = shopify.Product.find()
            products_without_prices = []
            
            for product in products:
                has_missing_price = any(
                    variant.price is None or float(variant.price) == 0
                    for variant in product.variants
                )
                if has_missing_price:
                    products_without_prices.append(product)
            
            return products_without_prices
        except Exception as e:
            logging.error(f"Error in get_products_without_prices: {str(e)}")
            raise 