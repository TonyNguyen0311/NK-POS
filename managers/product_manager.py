import uuid
import logging
from datetime import datetime
import streamlit as st
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud.firestore_v1.base_query import And, FieldFilter

class ProductManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.bucket = firebase_client.bucket
        self.collection = self.db.collection('products')
        self.cat_col = self.db.collection('categories')
        self.unit_col = self.db.collection('units')

    # --- XỬ LÝ ẢNH ---
    def upload_image(self, file_obj, filename):
        if not self.bucket: return None
        try:
            path = f"products/{int(datetime.now().timestamp())}_{filename}"
            blob = self.bucket.blob(path)
            blob.upload_from_file(file_obj, content_type=file_obj.type)
            blob.make_public()
            return blob.public_url
        except Exception as e:
            logging.error(f"Upload error: {e}")
            return None

    # --- HELPER: LẤY DATA AN TOÀN ---
    def _get_safe_list(self, collection_ref):
        try:
            results = []
            for doc in collection_ref.stream():
                data = doc.to_dict()
                data['id'] = doc.id 
                results.append(data)
            return results
        except Exception as e:
            logging.error(f"Error getting safe list from collection {collection_ref.id}: {e}")
            return []

    # --- DANH MỤC --
    def create_category(self, name, prefix):
        cat_id = f"CAT-{uuid.uuid4().hex[:4].upper()}"
        data = {
            "id": cat_id, 
            "name": name, 
            "prefix": prefix.upper(), 
            "current_seq": 0,
            "active": True
        }
        self.cat_col.document(cat_id).set(data)
        return data

    def get_categories(self):
        return self._get_safe_list(self.cat_col)

    # --- ĐƠN VỊ TÍNH ---
    def create_unit(self, name):
        unit_id = f"UNT-{uuid.uuid4().hex[:4].upper()}"
        data = {"id": unit_id, "name": name}
        self.unit_col.document(unit_id).set(data)
        return data

    def get_units(self):
        return self._get_safe_list(self.unit_col)

    # --- SẢN PHẨM ---
    def create_product(self, product_data):
        if not product_data.get('category_id'):
            return False, "Thiếu Category ID"
            
        cat_ref = self.cat_col.document(product_data['category_id'])

        @firestore.transactional
        def run_transaction(transaction, cat_ref, data):
            snapshot = cat_ref.get(transaction=transaction)
            if not snapshot.exists:
                raise Exception("Danh mục không tồn tại!")
            
            cat_data = snapshot.to_dict()
            prefix = cat_data.get('prefix', 'SP')
            current_seq = cat_data.get('current_seq', 0)
            
            new_seq = current_seq + 1
            new_sku = f"{prefix}-{new_seq:04d}"
            
            prod_ref = self.collection.document(new_sku)
            if prod_ref.get(transaction=transaction).exists:
                raise Exception(f"SKU {new_sku} bị trùng. Vui lòng thử lại.")

            transaction.update(cat_ref, {"current_seq": new_seq})

            data['sku'] = new_sku
            data['created_at'] = datetime.now().isoformat()
            data['active'] = True
            
            transaction.set(prod_ref, data)
            return new_sku

        transaction = self.db.transaction()
        try:
            sku = run_transaction(transaction, cat_ref, product_data)
            return True, f"Tạo thành công: {sku}"
        except Exception as e:
            logging.error(f"Lỗi tạo sản phẩm: {e}")
            return False, f"Lỗi tạo sản phẩm: {str(e)}"

    def update_product(self, sku, updates):
        self.collection.document(sku).update(updates)

    def get_all_products(self):
        """
        Lấy tất cả sản phẩm đang active. Trả về list rỗng nếu có lỗi.
        Đổi tên từ list_products và thêm error handling.
        """
        try:
            query = self.collection.where("active", "==", True)
            docs = query.stream()
            results = []
            for doc in docs:
                d = doc.to_dict()
                d['sku'] = doc.id
                # Đồng bộ với UI, thêm trường 'cogs' từ 'cost_price'
                d['cogs'] = d.get('cost_price', 0)
                results.append(d)
            return results
        except Exception as e:
            logging.error(f"Error fetching all products: {e}")
            return []

    def get_listed_products_for_branch(self, branch_id: str):
        try:
            all_active_products = self.get_all_products()
            results = []
            for product in all_active_products:
                price_info = product.get('price_by_branch', {}).get(branch_id)
                if isinstance(price_info, dict) and price_info.get('active') is True:
                    results.append(product)
            return results
        except Exception as e:
            logging.error(f"Error getting listed products for branch {branch_id}: {e}")
            return []

    def delete_product(self, sku):
        self.collection.document(sku).update({"active": False})

    def get_all_products_with_cost(self):
        """
        Lấy tất cả sản phẩm đang active với các trường dữ liệu cần thiết.
        Đã thêm error handling.
        """
        try:
            query = self.collection.where("active", "==", True)
            docs = query.stream()
            results = []
            for doc in docs:
                d = doc.to_dict()
                product_data = {
                    'sku': doc.id,
                    'name': d.get('name'),
                    'price_default': d.get('price_default'),
                    'price_by_branch': d.get('price_by_branch', {}),
                    # Sử dụng 'cogs' để đồng bộ, nhưng vẫn giữ 'cost_price' để tương thích ngược
                    'cost_price': d.get('cost_price', 0),
                    'cogs': d.get('cost_price', 0) 
                }
                results.append(product_data)
            return results
        except Exception as e:
            logging.error(f"Error in get_all_products_with_cost: {e}")
            return []
