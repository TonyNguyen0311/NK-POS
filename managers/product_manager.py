import uuid
from datetime import datetime
import streamlit as st
from google.cloud import firestore # Import để dùng Transaction

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

    # --- DANH MỤC (CÓ PREFIX) ---
    def create_category(self, name, prefix):
        """Tạo danh mục với Prefix (VD: Áo thun -> AT)"""
        cat_id = f"CAT-{uuid.uuid4().hex[:4].upper()}"
        data = {
            "id": cat_id, 
            "name": name, 
            "prefix": prefix.upper(), # Lưu mã tiền tố
            "current_seq": 0,         # Bộ đếm bắt đầu từ 0
            "active": True
        }
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

    # --- SẢN PHẨM (AUTO SKU) ---
    def create_product(self, product_data):
        """
        product_data: dict (không cần sku, hệ thống tự sinh)
        Sử dụng Transaction để đảm bảo không trùng số khi nhiều người cùng tạo.
        """
        transaction = self.db.transaction()
        cat_ref = self.cat_col.document(product_data['category_id'])

        try:
            # Gọi hàm transaction nội bộ
            return self._create_product_transaction(transaction, cat_ref, product_data)
        except Exception as e:
            return False, f"Lỗi tạo sản phẩm: {str(e)}"

    @firestore.transactional
    def _create_product_transaction(self, transaction, cat_ref, product_data):
        # 1. Đọc dữ liệu danh mục để lấy prefix và số thứ tự hiện tại
        snapshot = cat_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("Danh mục không tồn tại!")
        
        cat_data = snapshot.to_dict()
        prefix = cat_data.get('prefix', 'SP') # Mặc định là SP nếu thiếu
        current_seq = cat_data.get('current_seq', 0)
        
        # 2. Tăng số thứ tự lên 1
        new_seq = current_seq + 1
        
        # 3. Tạo SKU: VD: AT-0001
        new_sku = f"{prefix}-{new_seq:04d}"
        
        # 4. Kiểm tra xem SKU này có lỡ tồn tại chưa (phòng hờ)
        prod_ref = self.collection.document(new_sku)
        if prod_ref.get(transaction=transaction).exists:
            raise Exception(f"SKU {new_sku} đã tồn tại (Lỗi hệ thống). Vui lòng thử lại.")

        # 5. Cập nhật lại bộ đếm cho danh mục
        transaction.update(cat_ref, {"current_seq": new_seq})

        # 6. Tạo sản phẩm
        product_data['sku'] = new_sku
        product_data['created_at'] = datetime.now().isoformat()
        product_data['active'] = True
        
        transaction.set(prod_ref, product_data)
        
        return True, f"Tạo thành công sản phẩm: {new_sku}"

    def update_product(self, sku, updates):
        self.collection.document(sku).update(updates)

    def get_all_products(self):
        docs = self.collection.where("active", "==", True).stream()
        return [doc.to_dict() for doc in docs]
            
    def delete_product(self, sku):
        self.collection.document(sku).update({"active": False})
