
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.base_query import And, FieldFilter
from managers.image_handler import ImageHandler
from managers.price_manager import PriceManager

class ProductManager:
    def __init__(self, firebase_client, price_mgr: PriceManager = None):
        self.db = firebase_client.db
        self.price_mgr = price_mgr
        self.products_collection = self.db.collection('products')
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

    # SỬA LỖI: Thụt lề đúng
    @st.cache_data(ttl=300, _self_unhashable=True)
    def get_all_category_items(self, collection_name: str):
        try:
            docs = self.db.collection(collection_name).order_by("created_at").stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting items from {collection_name}: {e}")
            st.error(f"Lỗi khi tải dữ liệu từ {collection_name}: {e}")
            return []

    def add_category_item(self, collection_name: str, data: dict):
        try:
            doc_ref = self.db.collection(collection_name).document()
            data['id'] = doc_ref.id
            data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(data)
            self.get_all_category_items.clear()
            return True
        except Exception as e:
            logging.error(f"Error adding item to {collection_name}: {e}")
            raise e

    def update_category_item(self, collection_name: str, doc_id: str, updates: dict):
        try:
            self.db.collection(collection_name).document(doc_id).update(updates)
            self.get_all_category_items.clear()
            return True
        except Exception as e:
            logging.error(f"Error updating item {doc_id} in {collection_name}: {e}")
            raise e

    def delete_category_item(self, collection_name: str, doc_id: str):
        try:
            self.db.collection(collection_name).document(doc_id).delete()
            self.get_all_category_items.clear()
            return True
        except Exception as e:
            logging.error(f"Error deleting item {doc_id} from {collection_name}: {e}")
            raise e

    # ... (các hàm không có decorator giữ nguyên)

    # SỬA LỖI: Thụt lề đúng
    @st.cache_data(ttl=600, _self_unhashable=True)
    def get_all_products(self, active_only: bool = True):
        try:
            base_query = self.products_collection.order_by("created_at", direction=firestore.Query.DESCENDING)
            docs = base_query.stream()
            all_products = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            if active_only:
                return [p for p in all_products if p.get('active', False)]
            else:
                return all_products
        except Exception as e:
            logging.error(f"Error getting all products: {e}")
            return []

    # SỬA LỖI: Thụt lề đúng
    @st.cache_data(ttl=600, _self_unhashable=True)
    def get_product_by_id(self, product_id):
        if not product_id: return None
        try:
            doc = self.products_collection.document(product_id).get()
            if doc.exists:
                return {"id": doc.id, **doc.to_dict()}
            return None
        except Exception as e:
            logging.error(f"Error fetching product {product_id}: {e}")
            return None
            
    def get_product_by_sku(self, sku):
        return self.get_product_by_id(sku)

    # ... (các hàm còn lại giữ nguyên)
