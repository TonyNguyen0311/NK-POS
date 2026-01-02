
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.base_query import And, FieldFilter

# Corrected import paths to point to the new subdirectory
from managers.image_handler import ImageHandler 
from managers.product.category_manager import CategoryManager
from managers.product.unit_manager import UnitManager

class ProductManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('products')
        self.category_manager = CategoryManager(self.db)
        self.unit_manager = UnitManager(self.db)
        self.image_handler = self._initialize_image_handler()
        # Flexible folder ID: specific first, then general
        self.product_image_folder_id = st.secrets.get("drive_product_folder_id") or st.secrets.get("drive_folder_id")

    def _initialize_image_handler(self):
        if "drive_oauth" in st.secrets:
            try:
                creds_info = dict(st.secrets["drive_oauth"])
                if creds_info.get('refresh_token'):
                    return ImageHandler(credentials_info=creds_info)
                else:
                    logging.warning("ImageHandler not initialized: 'refresh_token' is missing from 'drive_oauth' secrets.")
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler: {e}")
        else:
            logging.warning("ImageHandler not initialized: 'drive_oauth' secret not found.")
        return None

    def get_categories(self): return self.category_manager.get_categories()
    def create_category(self, name, prefix): return self.category_manager.create_category(name, prefix)
    def get_units(self): return self.unit_manager.get_units()
    def create_unit(self, name): return self.unit_manager.create_unit(name)

    def _handle_image_update(self, sku, image_file, delete_image_flag):
        # Provide specific error messages for configuration issues
        if not self.image_handler:
            st.error("Lỗi Cấu Hình: Trình xử lý ảnh chưa được khởi tạo. Vui lòng kiểm tra lại 'drive_oauth' trong Streamlit secrets.")
            return False
        if not self.product_image_folder_id:
            st.error("Lỗi Cấu Hình: Cần cài đặt 'drive_product_folder_id' hoặc 'drive_folder_id' trong secrets.")
            return False
        
        filename = f"{sku}.jpg"
        if delete_image_flag:
            try:
                self.image_handler.delete_image_by_filename(self.product_image_folder_id, filename)
                self.collection.document(sku).update({"image_url": ""})
                st.info(f"Đã xóa ảnh cho sản phẩm {sku}.")
            except Exception as e:
                st.error(f"Lỗi khi xóa ảnh: {e}")
                return False
            return True # Successfully deleted

        if image_file:
            try:
                st.info(f"Đang tải ảnh sản phẩm lên cho SKU: {sku}...")
                image_url = self.image_handler.upload_product_image(image_file, self.product_image_folder_id, sku)
                if image_url:
                    self.collection.document(sku).update({'image_url': image_url})
                    st.success(f"Đã cập nhật ảnh cho sản phẩm {sku}.")
                else:
                    st.error("Tải ảnh lên thất bại.")
                    return False
            except Exception as e:
                st.error(f"Lỗi trong quá trình tải ảnh lên: {e}")
                return False
        return True # Successfully uploaded or no action needed

    def create_product(self, product_data):
        image_file_to_upload = product_data.pop('image_file', None)
        
        # If there's an image, check configuration first.
        if image_file_to_upload:
            if not self.image_handler:
                st.error("Lỗi Cấu Hình: Trình xử lý ảnh chưa được khởi tạo. Vui lòng kiểm tra lại 'drive_oauth' trong Streamlit secrets.")
                return False, "Tạo sản phẩm thất bại do lỗi cấu hình."
            if not self.product_image_folder_id:
                st.error("Lỗi Cấu Hình: Cần cài đặt 'drive_product_folder_id' hoặc 'drive_folder_id' trong secrets.")
                return False, "Tạo sản phẩm thất bại do lỗi cấu hình."

        cat_ref = self.category_manager.cat_col.document(product_data['category_id'])

        @firestore.transactional
        def _create_in_transaction(transaction, cat_ref, product_data):
            cat_snapshot = transaction.get(cat_ref, field_paths=["prefix", "current_seq"])[0].to_dict()
            prefix = cat_snapshot.get("prefix", "PRD")
            new_seq = cat_snapshot.get("current_seq", 0) + 1
            sku = f"{prefix}-{str(new_seq).zfill(4)}"

            product_data.update({
                'sku': sku, 'active': True, 'image_url': "",
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
                if not self._handle_image_update(sku, image_file_to_upload, delete_image_flag=False):
                    return False, f"Sản phẩm '{product_data['name']}' đã được tạo với SKU '{sku}', nhưng tải ảnh lên thất bại."
            return True, f"Tạo sản phẩm '{product_data['name']}' (SKU: '{sku}') thành công!"
        except Exception as e:
            logging.error(f"Error creating product: {e}")
            return False, f"Lỗi khi tạo sản phẩm: {e}"

    def update_product(self, sku, updates):
        image_file_to_upload = updates.pop('image_file', None)
        delete_image_flag = updates.pop('delete_image', False)

        try:
            image_op_success = True
            if image_file_to_upload or delete_image_flag:
                image_op_success = self._handle_image_update(sku, image_file_to_upload, delete_image_flag)
            
            if not image_op_success:
                return False, f"Cập nhật ảnh cho sản phẩm {sku} thất bại. Các thông tin khác không được cập nhật."

            if updates:
                updates['updated_at'] = firestore.SERVER_TIMESTAMP
                self.collection.document(sku).update(updates)
            
            return True, f"Sản phẩm {sku} đã được cập nhật thành công."
        except Exception as e:
            logging.error(f"Error updating product {sku}: {e}")
            return False, f"Lỗi khi cập nhật sản phẩm: {e}"

    def set_product_active_status(self, sku, active: bool):
        return self.update_product(sku, {'active': active})

    def hard_delete_product(self, sku):
        try:
            if self.image_handler and self.product_image_folder_id:
                try:
                    filename = f"{sku}.jpg"
                    self.image_handler.delete_image_by_filename(self.product_image_folder_id, filename)
                except Exception as e:
                    logging.warning(f"Không thể xóa ảnh của sản phẩm {sku}. Lỗi: {e}. Tiếp tục xóa sản phẩm khỏi database.")
            
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
