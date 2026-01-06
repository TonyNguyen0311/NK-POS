
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from managers.image_handler import ImageHandler
from managers.price_manager import PriceManager

def hash_product_manager(manager):
    return "ProductManager"

class ProductManager:
    def __init__(self, firebase_client, price_mgr: PriceManager = None):
        self.db = firebase_client.db
        self.price_mgr = price_mgr
        self.products_collection = self.db.collection('products')
        self._image_handler = None  # Private attribute for lazy loading
        self.product_image_folder_id = st.secrets.get("drive_product_folder_id") or st.secrets.get("drive_folder_id")

    @property
    def image_handler(self):
        """Lazy loads the ImageHandler to avoid recursion and unnecessary initializations."""
        if self._image_handler is None and "drive_oauth" in st.secrets:
            try:
                creds_info = dict(st.secrets["drive_oauth"])
                if creds_info.get('refresh_token'):
                    self._image_handler = ImageHandler(credentials_info=creds_info)
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler for products: {e}")
        return self._image_handler

    # --- Generic Category/Brand/Unit Methods ---
    def get_all_category_items(self, collection_name: str):
        try:
            docs = self.db.collection(collection_name).order_by("created_at").stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            st.error(f"Lỗi khi tải dữ liệu từ {collection_name}: {e}")
            return []

    def add_category_item(self, collection_name: str, data: dict):
        try:
            doc_ref = self.db.collection(collection_name).document()
            data['id'] = doc_ref.id
            data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(data)
            self.get_all_category_items.clear()
            return True, f"Thêm mục mới vào {collection_name} thành công."
        except Exception as e:
            return False, f"Lỗi khi thêm mục: {e}"

    # --- Product Specific Methods ---
    def create_product(self, product_data):
        image_file = product_data.pop('image_file', None)
        sku = f"PROD-{uuid.uuid4().hex[:8].upper()}"

        try:
            new_product_data = {
                **product_data,
                'sku': sku,
                'active': True,
                'image_id': None,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            self.products_collection.document(sku).set(new_product_data)

            # Handle image upload if an image is provided
            if image_file and self.image_handler and self.product_image_folder_id:
                new_image_id = self.image_handler.upload_image(
                    image_file, self.product_image_folder_id, base_filename=sku
                )
                if new_image_id:
                    self.products_collection.document(sku).update({'image_id': new_image_id})
            
            self.get_all_products.clear()
            return True, f"Tạo sản phẩm '{product_data['name']}' (SKU: {sku}) thành công!"

        except Exception as e:
            logging.error(f"Error creating product: {e}")
            return False, f"Lỗi khi tạo sản phẩm: {e}"

    def update_product(self, product_id, updates):
        image_file = updates.pop('image_file', None)
        delete_image_flag = updates.pop('delete_image', False)

        try:
            product_ref = self.products_collection.document(product_id)
            product_doc = product_ref.get()
            if not product_doc.exists:
                return False, "Sản phẩm không tồn tại."

            current_image_id = product_doc.to_dict().get('image_id')
            new_image_id = current_image_id

            # Logic for image deletion
            if (delete_image_flag or image_file) and current_image_id and self.image_handler:
                self.image_handler.delete_image_by_id(current_image_id)
                new_image_id = None # Set to None after deletion

            # Logic for image upload
            if image_file and self.image_handler and self.product_image_folder_id:
                uploaded_id = self.image_handler.upload_image(
                    image_file, self.product_image_folder_id, base_filename=product_id
                )
                if uploaded_id:
                    new_image_id = uploaded_id
            
            updates['image_id'] = new_image_id
            updates['updated_at'] = firestore.SERVER_TIMESTAMP
            
            product_ref.update(updates)

            # Clear relevant caches
            self.get_all_products.clear()
            self.get_product_by_id.clear()

            return True, f"Sản phẩm {product_id} đã được cập nhật thành công."

        except Exception as e:
            logging.error(f"Error updating product {product_id}: {e}")
            return False, f"Lỗi khi cập nhật sản phẩm: {e}"

    def hard_delete_product(self, product_id):
        try:
            product_ref = self.products_collection.document(product_id)
            product_doc = product_ref.get().to_dict()
            
            # Delete associated image from Google Drive
            if product_doc and product_doc.get('image_id') and self.image_handler:
                self.image_handler.delete_image_by_id(product_doc['image_id'])
            
            # Delete the product document from Firestore
            product_ref.delete()
            self.get_all_products.clear()
            self.get_product_by_id.clear()
            return True, f"Sản phẩm {product_id} đã được xóa vĩnh viễn."
        except Exception as e:
            logging.error(f"Error deleting product {product_id}: {e}")
            return False, f"Lỗi khi xóa sản phẩm: {e}"

    # --- Data Retrieval Methods ---
    @st.cache_data(ttl=600, hash_funcs={object: hash_product_manager})
    def get_all_products(_self, active_only: bool = True):
        try:
            query = _self.products_collection.order_by("created_at", direction=firestore.Query.DESCENDING)
            docs = query.stream()
            all_products = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            if active_only:
                return [p for p in all_products if p.get('active', False)]
            return all_products
        except Exception as e:
            st.error(f"Lỗi khi tải danh sách sản phẩm: {e}")
            return []

    @st.cache_data(ttl=600, hash_funcs={object: hash_product_manager})
    def get_product_by_id(_self, product_id):
        if not product_id: return None
        try:
            doc = _self.products_collection.document(product_id).get()
            return {"id": doc.id, **doc.to_dict()} if doc.exists else None
        except Exception as e:
            logging.error(f"Error fetching product {product_id}: {e}")
            return None

    def get_listed_products_for_branch(self, branch_id: str):
        if not self.price_mgr:
            st.error("Lỗi: Price Manager không được khởi tạo.")
            return []
        try:
            all_products = self.get_all_products(active_only=True)
            # FIX: Called the correct method name 'get_active_prices_for_branch'
            branch_prices = self.price_mgr.get_active_prices_for_branch(branch_id)
            branch_price_map = {p['sku']: p for p in branch_prices}
            
            listed_products = []
            for prod in all_products:
                sku = prod.get('sku')
                if sku in branch_price_map:
                    price_info = branch_price_map[sku]
                    prod_with_price = {
                        **prod,
                        'selling_price': price_info.get('price', 0),
                    }
                    listed_products.append(prod_with_price)
            return listed_products
        except Exception as e:
            st.error(f"Đã xảy ra lỗi khi tải sản phẩm cho chi nhánh: {e}")
            return []
