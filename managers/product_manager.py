import uuid
from datetime import datetime
import streamlit as st

class ProductManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.bucket = firebase_client.bucket
        self.collection = self.db.collection('products')
        self.cat_col = self.db.collection('categories')
        self.unit_col = self.db.collection('units')

    # --- XỬ LÝ ẢNH (STORAGE) ---
    def upload_image(self, file_obj, filename):
        """Upload file lên Firebase Storage và trả về Public URL"""
        if not self.bucket:
            return None
        try:
            # Tạo đường dẫn lưu: products/timestamp_filename
            path = f"products/{int(datetime.now().timestamp())}_{filename}"
            blob = self.bucket.blob(path)
            
            # Upload
            blob.upload_from_file(file_obj, content_type=file_obj.type)
            
            # Make public (cần set rule hoặc config bucket public)
            # Cách đơn giản nhất cho MVP: dùng make_public()
            blob.make_public()
            return blob.public_url
        except Exception as e:
            print(f"Upload error: {e}")
            return None

    # --- DANH MỤC & ĐƠN VỊ ---
    def create_category(self, name):
        cat_id = f"CAT-{uuid.uuid4().hex[:4].upper()}"
        data = {"id": cat_id, "name": name, "active": True}
        self.cat_col.document(cat_id).set(data)
        return data

    def get_categories(self):
        return [d.to_dict() for d in self.cat_col.stream()]

    def create_unit(self, name):
        unit_id = f"UNT-{uuid.uuid4().hex[:4].upper()}"
        data = {"id": unit_id, "name": name}
        self.unit_col.document(unit_id).set(data)
        return data

    def get_units(self):
        return [d.to_dict() for d in self.unit_col.stream()]

    # --- SẢN PHẨM ---
    def create_product(self, product_data):
        """
        product_data: dict chứa sku, name, price_default, price_by_branch...
        """
        # Kiểm tra SKU trùng
        if self.collection.document(product_data['sku']).get().exists:
            return False, "Mã SKU đã tồn tại!"
        
        product_data['created_at'] = datetime.now().isoformat()
        product_data['active'] = True
        
        self.collection.document(product_data['sku']).set(product_data)
        return True, "Tạo thành công"

    def update_product(self, sku, updates):
        self.collection.document(sku).update(updates)

    def get_all_products(self):
        docs = self.collection.where("active", "==", True).stream()
        return [doc.to_dict() for doc in docs]
        
    def delete_product(self, sku):
        # Soft delete
        self.collection.document(sku).update({"active": False})
