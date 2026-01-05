
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
            return True
        except Exception as e:
            logging.error(f"Error adding item to {collection_name}: {e}")
            raise e

    def update_category_item(self, collection_name: str, doc_id: str, updates: dict):
        try:
            self.db.collection(collection_name).document(doc_id).update(updates)
            return True
        except Exception as e:
            logging.error(f"Error updating item {doc_id} in {collection_name}: {e}")
            raise e

    def delete_category_item(self, collection_name: str, doc_id: str):
        try:
            self.db.collection(collection_name).document(doc_id).delete()
            return True
        except Exception as e:
            logging.error(f"Error deleting item {doc_id} from {collection_name}: {e}")
            raise e

    def _handle_image_update(self, sku, image_file, delete_image_flag):
        if not self.image_handler:
            st.error("Lỗi Cấu Hình: Trình xử lý ảnh chưa được khởi tạo.")
            return None
        if not self.product_image_folder_id:
            st.error("Lỗi Cấu Hình: ID thư mục Google Drive cho ảnh sản phẩm chưa được cài đặt.")
            return None

        product_ref = self.products_collection.document(sku)
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
            sku = f"PROD-{uuid.uuid4().hex[:8].upper()}"
            
            new_product_data = {
                **product_data,
                'sku': sku,
                'active': True,
                'image_id': "",
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            self.products_collection.document(sku).set(new_product_data)

            if image_file:
                new_image_id = self._handle_image_update(sku, image_file, delete_image_flag=False)
                if new_image_id is not None:
                    self.products_collection.document(sku).update({'image_id': new_image_id})

            return True, f"Tạo sản phẩm '{product_data['name']}' (SKU: {sku}) thành công!"
        except Exception as e:
            logging.error(f"Error creating product: {e}")
            return False, f"Lỗi khi tạo sản phẩm: {e}"

    def update_product(self, product_id, updates):
        image_file = updates.pop('image_file', None)
        delete_image = updates.pop('delete_image', False)

        try:
            product_ref = self.products_collection.document(product_id)
            sku = product_ref.get().to_dict().get('sku', product_id)

            if image_file or delete_image:
                new_image_id = self._handle_image_update(sku, image_file, delete_image)
                if new_image_id is not None:
                    updates['image_id'] = new_image_id
            
            if updates:
                updates['updated_at'] = firestore.SERVER_TIMESTAMP
                product_ref.update(updates)

            return True, f"Sản phẩm {sku} đã được cập nhật thành công."
        except Exception as e:
            logging.error(f"Error updating product {product_id}: {e}")
            return False, f"Lỗi khi cập nhật sản phẩm: {e}"

    def set_product_active_status(self, product_id, active: bool):
        try:
            self.products_collection.document(product_id).update({'active': active, 'updated_at': firestore.SERVER_TIMESTAMP})
            return True, "Cập nhật trạng thái thành công"
        except Exception as e:
            return False, f"Lỗi: {e}"
            
    def hard_delete_product(self, product_id):
        try:
            product_ref = self.products_collection.document(product_id)
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
            if "requires an index" in str(e):
                st.error("Lỗi truy vấn cơ sở dữ liệu. Vui lòng liên hệ quản trị viên.")
            else:
                st.error(f"Lỗi khi tải danh sách sản phẩm: {e}")
            return []

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

    def get_listed_products_for_branch(self, branch_id: str):
        if not self.price_mgr:
            st.error("Lỗi: Price Manager không được khởi tạo trong Product Manager.")
            return []
        try:
            # 1. Get all active products from the general catalog
            all_active_products = self.get_all_products(active_only=True)
            
            # 2. Get all price/business records for the specific branch
            prices_in_branch = self.price_mgr.get_all_prices_for_branch(branch_id)
            
            # 3. Create a dictionary for quick lookup
            branch_price_map = {p['sku']: p for p in prices_in_branch}

            # 4. Filter products that are actively sold in the branch and attach price info
            listed_products = []
            for prod in all_active_products:
                sku = prod['sku']
                if sku in branch_price_map:
                    price_info = branch_price_map[sku]
                    # Check if the product is marked as 'is_active' for business in this branch
                    if price_info.get('is_active', False):
                        # Attach the current price to the product dictionary
                        prod_with_price = {
                            **prod,
                            'price': price_info.get('price', 0) 
                        }
                        listed_products.append(prod_with_price)
            
            return listed_products
        except Exception as e:
            logging.error(f"Error in get_listed_products_for_branch: {e}")
            return []
