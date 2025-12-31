
import uuid
import logging
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.base_query import And, FieldFilter

from .product.category_manager import CategoryManager
from .product.unit_manager import UnitManager

class ProductManager:
    def __init__(self, firebase_client, image_handler=None):
        self.db = firebase_client.db
        self.collection = self.db.collection('products')
        self.category_manager = CategoryManager(self.db)
        self.unit_manager = UnitManager(self.db)
        self.image_handler = image_handler

    # --- Category and Unit passthrough methods ---
    def get_categories(self): return self.category_manager.get_categories()
    def create_category(self, name, prefix): return self.category_manager.create_category(name, prefix)
    def get_units(self): return self.unit_manager.get_units()
    def create_unit(self, name): return self.unit_manager.create_unit(name)

    def upload_image(self, file_obj, filename):
        if self.image_handler:
            optimized_buffer = self.image_handler.optimize_image(file_obj)
            if optimized_buffer:
                return self.image_handler.upload_image(optimized_buffer, filename)
        logging.warning("Image Handler not configured or image optimization failed.")
        return None

    def create_product(self, product_data):
        if not product_data.get('category_id'):
            return False, "Thiếu ID danh mục."

        cat_ref = self.category_manager.cat_col.document(product_data['category_id'])
        transaction = self.db.transaction()

        @firestore.transactional
        def update_in_transaction(trans, cat_ref, product_data):
            try:
                cat_snapshot = trans.get(cat_ref, field_paths=["prefix", "current_seq"])[0].to_dict()
                prefix = cat_snapshot.get("prefix", "PRD")
                current_seq = cat_snapshot.get("current_seq", 0)
                new_seq = current_seq + 1
                sku = f"{prefix}-{str(new_seq).zfill(4)}"

                product_data['sku'] = sku
                product_data['active'] = True
                product_data['created_at'] = firestore.SERVER_TIMESTAMP
                product_data['updated_at'] = firestore.SERVER_TIMESTAMP

                product_ref = self.collection.document(sku)
                trans.set(product_ref, product_data)
                trans.update(cat_ref, {"current_seq": new_seq})
                return sku, None
            except Exception as e:
                logging.error(f"Transaction failed: {e}")
                raise e

        try:
            sku, error = update_in_transaction(transaction, cat_ref, product_data)
            if error:
                return False, error
            return True, sku
        except Exception as e:
            return False, f"Lỗi khi tạo sản phẩm: {str(e)}"

    def update_product(self, sku, updates):
        if not sku or not isinstance(updates, dict):
            return False, "SKU hoặc dữ liệu cập nhật không hợp lệ."
        try:
            updates['updated_at'] = firestore.SERVER_TIMESTAMP
            self.collection.document(sku).update(updates)
            return True, f"Sản phẩm {sku} đã được cập nhật."
        except Exception as e:
            logging.error(f"Error updating product {sku}: {e}")
            return False, f"Lỗi khi cập nhật sản phẩm: {e}"
    
    def set_product_active_status(self, sku, active: bool):
        return self.update_product(sku, {'active': active})

    def hard_delete_product(self, sku):
        try:
            self.collection.document(sku).delete()
            return True, f"Sản phẩm {sku} đã được xóa vĩnh viễn."
        except Exception as e:
            logging.error(f"Error permanently deleting product {sku}: {e}")
            return False, f"Lỗi khi xóa sản phẩm: {e}"

    def get_all_products(self, show_inactive=False):
        try:
            query = self.collection
            if not show_inactive:
                query = query.where(filter=FieldFilter("active", "==", True))
            
            docs = query.order_by("sku").stream()
            results = []
            for doc in docs:
                d = doc.to_dict()
                d['id'] = doc.id # Use id (which is sku) for keying
                d['sku'] = doc.id
                results.append(d)
            return results
        except Exception as e:
            logging.error(f"Error getting all products: {e}")
            return []
    
    def get_product_by_sku(self, sku):
        try:
            doc = self.collection.document(sku).get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                data['sku'] = doc.id
                return data
            return None
        except Exception as e:
            logging.error(f"Error fetching product by SKU {sku}: {e}")
            return None

    def get_listed_products_for_branch(self, branch_id: str):
        try:
            all_active_products = self.get_all_products(show_inactive=False)
            results = []
            for product in all_active_products:
                price_info = product.get('price_by_branch', {}).get(branch_id)
                if isinstance(price_info, dict) and price_info.get('active') is True:
                    results.append(product)
            return results
        except Exception as e:
            logging.error(f"Error in get_listed_products_for_branch for {branch_id}: {e}")
            return []
