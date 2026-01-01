
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.base_query import And, FieldFilter

# These managers are now self-contained
from .product.category_manager import CategoryManager
from .product.unit_manager import UnitManager
from .product.image_handler import ImageHandler

class ProductManager:
    """
    Manages all product-related operations, including categories, units,
    and product data. It now self-initializes the ImageHandler.
    """
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('products')
        self.category_manager = CategoryManager(self.db)
        self.unit_manager = UnitManager(self.db)
        # Image handler is now initialized internally
        self.image_handler = self._initialize_image_handler()

    def _get_corrected_creds(self, secrets_key):
        """Correctly formats the private key from Streamlit secrets."""
        if secrets_key not in st.secrets:
            return None
        creds_section = st.secrets[secrets_key]
        creds_dict = dict(creds_section)
        if 'private_key' in creds_dict:
            creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
        return creds_dict

    def _initialize_image_handler(self):
        """Initializes ImageHandler using secrets from st.secrets."""
        logging.info("Attempting to initialize ImageHandler...")
        # Check for the correct secret keys as specified by the user
        if "gdrive_credentials" in st.secrets and "gdrive_folder_id" in st.secrets:
            try:
                creds_info = self._get_corrected_creds("gdrive_credentials")
                folder_id = st.secrets["gdrive_folder_id"]
                
                if folder_id and creds_info:
                    logging.info("Google Drive credentials and folder ID found. Initializing ImageHandler.")
                    return ImageHandler(credentials_info=creds_info, folder_id=folder_id)
                else:
                    logging.warning("Google Drive folder ID or credentials are not fully set in secrets.")
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler: {e}")
                st.warning("Không thể khởi tạo trình xử lý ảnh. Chức năng tải ảnh sẽ bị tắt.")
        else:
            logging.warning("'gdrive_credentials' or 'gdrive_folder_id' not found in Streamlit secrets. Image uploads will be disabled.")
        return None

    # --- Category and Unit methods ---
    def get_categories(self): return self.category_manager.get_categories()
    def create_category(self, name, prefix): return self.category_manager.create_category(name, prefix)
    def get_units(self): return self.unit_manager.get_units()
    def create_unit(self, name): return self.unit_manager.create_unit(name)

    def _upload_and_update_image_url(self, sku, image_file):
        """A private method to handle the image upload and Firestore URL update."""
        if self.image_handler and image_file and sku:
            try:
                st.info(f"Đang tải ảnh lên cho SKU: {sku}...")
                image_url = self.image_handler.upload_image(image_file, sku)
                if image_url:
                    self.collection.document(sku).update({'image_url': image_url})
                    logging.info(f"Successfully uploaded image for {sku}. URL: {image_url}")
                    return image_url
                else:
                    st.error("Tải ảnh lên thất bại. Không nhận được URL.")
            except Exception as e:
                logging.error(f"Image upload failed for {sku}: {e}")
                st.error(f"Lỗi trong quá trình tải ảnh lên: {e}")
        return None

    def create_product(self, product_data):
        if not product_data.get('category_id'):
            return False, "Thiếu ID danh mục."

        cat_ref = self.category_manager.cat_col.document(product_data['category_id'])
        image_file_to_upload = product_data.pop('image_file', None)

        transaction = self.db.transaction()
        @firestore.transactional
        def _create_product_in_transaction(trans, cat_ref, product_data):
            cat_snapshot = trans.get(cat_ref, field_paths=["prefix", "current_seq"])[0].to_dict()
            prefix = cat_snapshot.get("prefix", "PRD")
            current_seq = cat_snapshot.get("current_seq", 0)
            new_seq = current_seq + 1
            sku = f"{prefix}-{str(new_seq).zfill(4)}"

            product_data['sku'] = sku
            product_data['active'] = True
            product_data['created_at'] = firestore.SERVER_TIMESTAMP
            product_data['updated_at'] = firestore.SERVER_TIMESTAMP
            product_data['image_url'] = "" # Initially empty
            
            product_ref = self.collection.document(sku)
            trans.set(product_ref, product_data)
            trans.update(cat_ref, {"current_seq": new_seq})
            return sku

        try:
            sku = _create_product_in_transaction(transaction, cat_ref, product_data)
            if not sku:
                raise Exception("Không thể tạo SKU sản phẩm trong giao dịch.")

            # Upload image after the product is successfully created
            if image_file_to_upload:
                self._upload_and_update_image_url(sku, image_file_to_upload)

            return True, f"Tạo sản phẩm '{product_data['name']}' với SKU '{sku}' thành công!"
        except Exception as e:
            logging.error(f"Error during product creation for {product_data.get('name')}: {e}")
            return False, f"Lỗi khi tạo sản phẩm: {str(e)}"

    def update_product(self, sku, updates):
        if not sku or not isinstance(updates, dict):
            return False, "SKU hoặc dữ liệu cập nhật không hợp lệ."
        try:
            image_file_to_upload = updates.pop('image_file', None)
            if image_file_to_upload:
                self._upload_and_update_image_url(sku, image_file_to_upload)

            if updates: 
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
            if self.image_handler:
                self.image_handler.delete_image(sku)
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
                d['id'] = doc.id
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
