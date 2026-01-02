# managers/product_manager.py
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.base_query import And, FieldFilter

from managers.image_handler import ImageHandler

# --- BEGIN INLINED CategoryManager ---
class CategoryManager:
    def __init__(self, db):
        self.db = db
        self.cat_col = self.db.collection('categories')

    def create_category(self, name, prefix):
        try:
            cat_id = f"CAT-{uuid.uuid4().hex[:4].upper()}"
            data = {
                "id": cat_id, 
                "name": name, 
                "prefix": prefix.upper(), 
                "current_seq": 0,
                "active": True,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            self.cat_col.document(cat_id).set(data)
            return True, f"Tạo danh mục '{name}' thành công!"
        except Exception as e:
            logging.error(f"Failed to create category '{name}': {e}")
            return False, f"Lỗi: {e}"

    def get_categories(self):
        try:
            docs = self.cat_col.order_by("name").stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting categories: {e}")
            return []

    def delete_category(self, cat_id):
        try:
            self.cat_col.document(cat_id).delete()
            return True, "Xóa danh mục thành công."
        except Exception as e:
            logging.error(f"Error deleting category {cat_id}: {e}")
            return False, f"Lỗi: {e}"
# --- END INLINED CategoryManager ---

# --- BEGIN INLINED UnitManager ---
class UnitManager:
    def __init__(self, db):
        self.db = db
        self.unit_col = self.db.collection('units')

    def create_unit(self, name):
        try:
            unit_id = f"UNT-{uuid.uuid4().hex[:4].upper()}"
            data = {
                "id": unit_id, 
                "name": name,
                "created_at": firestore.SERVER_TIMESTAMP
            }
            self.unit_col.document(unit_id).set(data)
            return True, f"Tạo đơn vị '{name}' thành công!"
        except Exception as e:
            logging.error(f"Failed to create unit '{name}': {e}")
            return False, f"Lỗi: {e}"

    def get_units(self):
        try:
            docs = self.unit_col.order_by("name").stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting units: {e}")
            return []

    def delete_unit(self, unit_id):
        try:
            self.unit_col.document(unit_id).delete()
            return True, "Xóa đơn vị thành công."
        except Exception as e:
            logging.error(f"Error deleting unit {unit_id}: {e}")
            return False, f"Lỗi: {e}"
# --- END INLINED UnitManager ---

class ProductManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('products')
        # Initialize managers directly
        self.category_manager = CategoryManager(self.db)
        self.unit_manager = UnitManager(self.db)
        self.image_handler = self._initialize_image_handler()
        self.product_image_folder_id = st.secrets.get("drive_product_folder_id") or st.secrets.get("drive_folder_id")

    def _initialize_image_handler(self):
        if "drive_oauth" in st.secrets:
            try:
                creds_info = dict(st.secrets["drive_oauth"])
                if creds_info.get('refresh_token'):
                    return ImageHandler(credentials_info=creds_info)
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler: {e}")
        return None

    # Category and Unit pass-through methods
    def get_categories(self): return self.category_manager.get_categories()
    def add_category(self, name, prefix): return self.category_manager.create_category(name, prefix)
    def delete_category(self, cat_id): return self.category_manager.delete_category(cat_id)
    
    def get_units(self): return self.unit_manager.get_units()
    def add_unit(self, name): return self.unit_manager.create_unit(name)
    def delete_unit(self, unit_id): return self.unit_manager.delete_unit(unit_id)

    def _handle_image_update(self, sku, image_file, delete_image_flag):
        # ... (rest of the functions remain the same)
        if not self.image_handler:
            st.error("Lỗi Cấu Hình: Trình xử lý ảnh chưa được khởi tạo.")
            return None
        if not self.product_image_folder_id:
            st.error("Lỗi Cấu Hình: ID thư mục Google Drive cho ảnh sản phẩm chưa được cài đặt.")
            return None

        product_ref = self.collection.document(sku)
        try:
            product_doc = product_ref.get()
            current_image_id = product_doc.to_dict().get('image_id') if product_doc.exists else None
        except Exception as e:
            st.error(f"Không thể truy cập sản phẩm {sku}. Lỗi: {e}")
            return None

        if delete_image_flag or image_file:
            if current_image_id:
                try:
                    self.image_handler.delete_image_by_id(current_image_id)
                except Exception as e:
                    st.warning(f"Không thể xóa ảnh cũ. Lỗi: {e}.")
            if delete_image_flag and not image_file:
                return ""

        if image_file:
            try:
                new_image_id = self.image_handler.upload_product_image(image_file, self.product_image_folder_id, sku)
                if new_image_id:
                    return new_image_id
                else:
                    st.error("Tải ảnh lên thất bại.")
                    return None
            except Exception as e:
                st.error(f"Lỗi trong quá trình tải ảnh lên: {e}")
                return None
        
        return current_image_id

    def create_product(self, product_data):
        image_file = product_data.pop('image_file', None)
        
        try:
            cat_ref = self.category_manager.cat_col.document(product_data['category_id'])
            
            @firestore.transactional
            def _create_in_transaction(transaction, cat_ref, product_data):
                cat_snap = transaction.get(cat_ref)
                if isinstance(cat_snap, (list, tuple)):
                    cat_snapshot = cat_snap[0].to_dict()
                else:
                    cat_snapshot = cat_snap.to_dict()

                prefix = cat_snapshot.get("prefix", "PRD")
                new_seq = cat_snapshot.get("current_seq", 0) + 1
                sku = f"{prefix}-{str(new_seq).zfill(4)}"

                new_product_data = {
                    **product_data,
                    'sku': sku,
                    'active': True,
                    'image_id': "",
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'updated_at': firestore.SERVER_TIMESTAMP
                }
                
                product_ref = self.collection.document(sku)
                transaction.set(product_ref, new_product_data)
                transaction.update(cat_ref, {"current_seq": new_seq})
                return sku

            transaction = self.db.transaction()
            sku = _create_in_transaction(transaction, cat_ref, product_data)

            if sku and image_file:
                new_image_id = self._handle_image_update(sku, image_file, delete_image_flag=False)
                if new_image_id is not None:
                    self.collection.document(sku).update({'image_id': new_image_id})

            return True, f"Tạo sản phẩm '{product_data['name']}' (SKU: {sku}) thành công!"
        except Exception as e:
            logging.error(f"Error creating product: {e}")
            return False, f"Lỗi khi tạo sản phẩm: {e}"

    def update_product(self, product_id, updates):
        image_file = updates.pop('image_file', None)
        delete_image = updates.pop('delete_image', False)

        try:
            product_ref = self.collection.document(product_id)
            sku = product_ref.get().to_dict().get('sku', product_id)

            if image_file or delete_image:
                new_image_id = self._handle_image_update(sku, image_file, delete_image)
                if new_image_id is not None:
                    updates['image_id'] = new_image_id
                # Removed the failure return here to allow metadata updates even if image fails
            
            if updates:
                updates['updated_at'] = firestore.SERVER_TIMESTAMP
                product_ref.update(updates)

            return True, f"Sản phẩm {sku} đã được cập nhật thành công."
        except Exception as e:
            logging.error(f"Error updating product {product_id}: {e}")
            return False, f"Lỗi khi cập nhật sản phẩm: {e}"

    def set_product_active_status(self, product_id, active: bool):
        try:
            self.collection.document(product_id).update({'active': active, 'updated_at': firestore.SERVER_TIMESTAMP})
            return True, "Cập nhật trạng thái thành công"
        except Exception as e:
            return False, f"Lỗi: {e}"
            
    def hard_delete_product(self, product_id):
        try:
            product_ref = self.collection.document(product_id)
            product_doc = product_ref.get().to_dict()
            
            if product_doc and product_doc.get('image_id') and self.image_handler:
                try:
                    self.image_handler.delete_image_by_id(product_doc['image_id'])
                except Exception as e:
                    logging.warning(f"Không thể xóa ảnh của sản phẩm {product_id}. Lỗi: {e}.")
            
            product_ref.delete()
            return True, f"Sản phẩm {product_id} đã được xóa vĩnh viễn."
        except Exception as e:
            logging.error(f"Error deleting product {product_id}: {e}")
            return False, f"Lỗi khi xóa sản phẩm: {e}"

    def get_all_products(self, show_inactive=False):
        try:
            query = self.collection if show_inactive else self.collection.where(filter=FieldFilter("active", "==", True))
            docs = query.order_by("created_at", direction=firestore.Query.DESCENDING).stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting all products: {e}")
            return []

    def get_product_by_id(self, product_id):
        if not product_id: return None
        try:
            doc = self.collection.document(product_id).get()
            if doc.exists:
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            logging.error(f"Error fetching product {product_id}: {e}")
            return None
            
    def get_product_by_sku(self, sku):
        return self.get_product_by_id(sku)

    def get_listed_products_for_branch(self, branch_id: str):
        try:
            all_active_products = self.get_all_products()
            return all_active_products 
        except Exception as e:
            logging.error(f"Error in get_listed_products_for_branch: {e}")
            return []
