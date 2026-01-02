
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
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('products')
        self.category_manager = CategoryManager(self.db)
        self.unit_manager = UnitManager(self.db)
        self.image_handler = self._initialize_image_handler()

    def _initialize_image_handler(self):
        logging.info("Attempting to initialize ImageHandler using OAuth 2.0...")
        if "drive_oauth" in st.secrets and "drive_folder_id" in st.secrets:
            try:
                creds_info = dict(st.secrets["drive_oauth"])
                folder_id = st.secrets["drive_folder_id"]
                if folder_id and creds_info.get('refresh_token'):
                    logging.info("Google Drive OAuth credentials and folder ID found. Initializing ImageHandler.")
                    return ImageHandler(credentials_info=creds_info, folder_id=folder_id)
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler via OAuth: {e}")
        logging.warning("ImageHandler not initialized. Check secrets.")
        return None

    def get_categories(self): return self.category_manager.get_categories()
    def create_category(self, name, prefix): return self.category_manager.create_category(name, prefix)
    def get_units(self): return self.unit_manager.get_units()
    def create_unit(self, name): return self.unit_manager.create_unit(name)

    def _handle_image_update(self, sku, image_file, delete_image_flag):
        """Handles creating, updating, or deleting a product image."""
        if not self.image_handler:
            st.error("Lỗi Cấu Hình: Trình xử lý ảnh không được khởi tạo.")
            return
        
        # If delete flag is set, delete the image and clear the ID
        if delete_image_flag:
            try:
                self.image_handler.delete_image(sku)
                self.collection.document(sku).update({"image_id": ""})
                st.info(f"Đã xóa ảnh cho sản phẩm {sku}.")
            except Exception as e:
                st.error(f"Lỗi khi xóa ảnh: {e}")
            return # Stop further processing

        # If a new image file is provided, upload it
        if image_file:
            try:
                st.info(f"Đang tải ảnh lên cho SKU: {sku}...")
                image_id = self.image_handler.upload_image(image_file, sku)
                if image_id:
                    self.collection.document(sku).update({'image_id': image_id})
                    st.success(f"Đã cập nhật ảnh cho sản phẩm {sku}.")
                else:
                    st.error("Tải ảnh lên thất bại. Không nhận được ID ảnh.")
            except Exception as e:
                st.error(f"Lỗi trong quá trình tải ảnh lên: {e}")

    def create_product(self, product_data):
        image_file_to_upload = product_data.pop('image_file', None)
        cat_ref = self.category_manager.cat_col.document(product_data['category_id'])

        @firestore.transactional
        def _create_in_transaction(transaction, cat_ref, product_data):
            cat_snapshot = transaction.get(cat_ref, field_paths=["prefix", "current_seq"])[0].to_dict()
            prefix = cat_snapshot.get("prefix", "PRD")
            new_seq = cat_snapshot.get("current_seq", 0) + 1
            sku = f"{prefix}-{str(new_seq).zfill(4)}"

            product_data.update({
                'sku': sku, 'active': True, 'image_id': "",
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            
            product_ref = self.collection.document(sku)
            transaction.set(product_ref, product_data)
            transaction.update(cat_ref, {"current_seq": new_seq})
            return sku

        try:
            transaction = self.db.transaction()
            sku = _create_in_transaction(transaction, cat_ref, product_data)
            if sku and image_file_to_upload:
                self._handle_image_update(sku, image_file_to_upload, delete_image_flag=False)
            return True, f"Tạo sản phẩm '{product_data['name']}' (SKU: '{sku}') thành công!"
        except Exception as e:
            logging.error(f"Error creating product: {e}")
            return False, f"Lỗi khi tạo sản phẩm: {e}"

    def update_product(self, sku, updates):
        image_file_to_upload = updates.pop('image_file', None)
        delete_image_flag = updates.pop('delete_image', False)

        try:
            # Handle image changes first
            self._handle_image_update(sku, image_file_to_upload, delete_image_flag)

            # Update other fields if there are any
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
            # Ensure image is deleted from Drive before deleting the document
            if self.image_handler:
                self.image_handler.delete_image(sku)
            self.collection.document(sku).delete()
            return True, f"Sản phẩm {sku} đã được xóa vĩnh viễn."
        except Exception as e:
            logging.error(f"Error deleting product {sku}: {e}")
            return False, f"Lỗi khi xóa sản phẩm: {e}"

    def get_all_products(self, show_inactive=False):
        try:
            query = self.collection if show_inactive else self.collection.where(filter=FieldFilter("active", "==", True))
            docs = query.order_by("sku").stream()
            return [{"id": doc.id, "sku": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting all products: {e}")
            return []

    def list_products(self, show_inactive=False):
        """Returns a list of all products. Alias for get_all_products."""
        return self.get_all_products(show_inactive)
    
    def get_product_by_sku(self, sku):
        try:
            doc = self.collection.document(sku).get()
            if doc.exists:
                return {"id": doc.id, "sku": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            logging.error(f"Error fetching product {sku}: {e}")
            return None

    def get_listed_products_for_branch(self, branch_id: str):
        try:
            all_active_products = self.get_all_products()
            return [p for p in all_active_products if isinstance(p.get('price_by_branch', {}).get(branch_id), dict) and p['price_by_branch'][branch_id].get('active')]
        except Exception as e:
            logging.error(f"Error in get_listed_products_for_branch: {e}")
            return []
