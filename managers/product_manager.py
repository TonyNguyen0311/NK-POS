import uuid
from datetime import datetime
import streamlit as st
from google.cloud import firestore

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
            print(f"Upload error: {e}")
            return None

    # --- HELPER: LẤY DATA AN TOÀN ---
    def _get_safe_list(self, collection_ref):
        results = []
        for doc in collection_ref.stream():
            data = doc.to_dict()
            data['id'] = doc.id 
            results.append(data)
        return results

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

    # --- SẢN PHẨM (LOGIC TRANSACTION THỦ CÔNG - FIX LỖI) ---
    def create_product(self, product_data):
        if not product_data.get('category_id'):
            return False, "Thiếu Category ID"
            
        cat_ref = self.cat_col.document(product_data['category_id'])

        # Định nghĩa hàm transaction nội bộ
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
            # Check tồn tại (optional)
            if prod_ref.get(transaction=transaction).exists:
                 # Nếu xui xẻo trùng, ta có thể thử cộng thêm 1, nhưng ở đây cứ báo lỗi để retry
                raise Exception(f"SKU {new_sku} bị trùng. Vui lòng thử lại.")

            # Update seq
            transaction.update(cat_ref, {"current_seq": new_seq})

            # Create product
            data['sku'] = new_sku
            data['created_at'] = datetime.now().isoformat()
            data['active'] = True
            
            transaction.set(prod_ref, data)
            return new_sku

        # Chạy transaction
        transaction = self.db.transaction()
        try:
            sku = run_transaction(transaction, cat_ref, product_data)
            return True, f"Tạo thành công: {sku}"
        except Exception as e:
            return False, f"Lỗi tạo sản phẩm: {str(e)}"

    def update_product(self, sku, updates):
        self.collection.document(sku).update(updates)

    def list_products(self, filters: dict | None = None):
        # TODO: Implement filtering based on the 'filters' dictionary
        query = self.collection.where("active", "==", True)
        docs = query.stream()
        results = []
        for doc in docs:
            d = doc.to_dict()
            d['sku'] = doc.id
            results.append(d)
        return results

    def get_listed_products_for_branch(self, branch_id: str):
        """
        Lấy danh sách các sản phẩm được niêm yết (có giá và active) cho một chi nhánh cụ thể.
        Đây là hàm để sử dụng trên trang POS.
        """
        field_path = f"price_by_branch.{branch_id}.active"
        query = self.collection.where("active", "==", True).where(field_path, "==", True)
        
        results = []
        for doc in query.stream():
            d = doc.to_dict()
            d['sku'] = doc.id
            results.append(d)
        return results

    def delete_product(self, sku):
        self.collection.document(sku).update({"active": False})

    def get_all_products_with_cost(self):
        """
        Retrieves all active products with essential data for simulation.
        """
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
                'cost_price': d.get('cost_price', 0) # Default cost to 0 if not set
            }
            results.append(product_data)
        return results