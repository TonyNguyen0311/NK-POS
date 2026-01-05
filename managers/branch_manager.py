
import uuid
from datetime import datetime
import streamlit as st

# Define a hash function for the BranchManager class
def hash_branch_manager(manager):
    # Since the manager is essentially a singleton, we can use a constant identifier.
    return "BranchManager"

class BranchManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('branches')

    def create_branch(self, data: dict):
        """Tạo chi nhánh mới từ một dictionary"""
        branch_id = f"BR-{uuid.uuid4().hex[:6].upper()}"
        
        new_data = data.copy()
        new_data['id'] = branch_id
        new_data['active'] = True
        new_data['created_at'] = datetime.now().isoformat()
        
        self.collection.document(branch_id).set(new_data)
        # Manually clear the cache for all users
        self.list_branches.clear()
        return new_data

    @st.cache_data(ttl=3600, hash_funcs={BranchManager: hash_branch_manager})
    def list_branches(self, active_only: bool = True):
        """Lấy danh sách chi nhánh, có thể chỉ lấy các chi nhánh đang hoạt động."""
        query = self.collection
        if active_only:
            query = query.where('active', '==', True)
        
        docs = query.stream()
        return [doc.to_dict() for doc in docs]

    @st.cache_data(ttl=3600, hash_funcs={BranchManager: hash_branch_manager})
    def get_branch(self, branch_id):
        """Lấy thông tin chi tiết của một chi nhánh."""
        if not branch_id:
            return None
        doc = self.collection.document(branch_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def update_branch(self, branch_id: str, updates: dict):
        """Cập nhật thông tin cho một chi nhánh."""
        updates['updated_at'] = datetime.now().isoformat()
        self.collection.document(branch_id).update(updates)
        # Manually clear caches
        self.list_branches.clear()
        self.get_branch.clear()
        return self.get_branch(branch_id) # Trả về dữ liệu đã cập nhật
