
import streamlit as st
import uuid
from datetime import datetime

def hash_voucher_manager(manager):
    return "VoucherManager"

class VoucherManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('vouchers')

    def create_voucher(self, data: dict):
        """Tạo một voucher mới."""
        voucher_id = f"VCH-{uuid.uuid4().hex[:8].upper()}"
        data['id'] = voucher_id
        data['created_at'] = datetime.now().isoformat()
        data.setdefault('is_active', True)
        data.setdefault('usage_count', 0)
        
        self.collection.document(voucher_id).set(data)
        self.list_vouchers.clear()
        self.find_voucher_by_code.clear()
        return data

    def list_vouchers(self):
        """Lấy danh sách tất cả các voucher."""
        docs = self.collection.order_by("created_at", direction="DESCENDING").stream()
        return [doc.to_dict() for doc in docs]

    def get_voucher_by_id(self, voucher_id: str):
        """Lấy thông tin chi tiết của một voucher."""
        if not voucher_id: return None
        doc = self.collection.document(voucher_id).get()
        return doc.to_dict() if doc.exists else None

    def find_voucher_by_code(self, code: str):
        """Tìm một voucher đang hoạt động bằng mã của nó."""
        if not code: return None
        query = self.collection.where('code', '==', code.upper()).where('is_active', '==', True).limit(1)
        docs = list(query.stream())
        return docs[0].to_dict() if docs else None

    def update_voucher(self, voucher_id: str, updates: dict):
        """Cập nhật một voucher."""
        updates['updated_at'] = datetime.now().isoformat()
        self.collection.document(voucher_id).update(updates)
        # Clear all relevant caches
        self.list_vouchers.clear()
        self.get_voucher_by_id.clear()
        self.find_voucher_by_code.clear()
        return True

# Apply decorators after the class is defined
VoucherManager.list_vouchers = st.cache_data(ttl=300, hash_funcs={VoucherManager: hash_voucher_manager})(VoucherManager.list_vouchers)
VoucherManager.get_voucher_by_id = st.cache_data(ttl=300, hash_funcs={VoucherManager: hash_voucher_manager})(VoucherManager.get_voucher_by_id)
VoucherManager.find_voucher_by_code = st.cache_data(ttl=60, hash_funcs={VoucherManager: hash_voucher_manager})(VoucherManager.find_voucher_by_code)
