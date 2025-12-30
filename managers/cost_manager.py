
import uuid
from datetime import datetime
from google.cloud import firestore

class CostManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.bucket = firebase_client.bucket
        self.group_col = self.db.collection('cost_groups')
        self.entry_col = self.db.collection('cost_entries')

    # --- COST GROUPS (NHÓM CHI PHÍ) ---
    def create_cost_group(self, group_name):
        """Tạo một nhóm chi phí mới."""
        group_id = f"CG-{uuid.uuid4().hex[:6].upper()}"
        data = {"group_id": group_id, "group_name": group_name}
        self.group_col.document(group_id).set(data)
        return data

    def get_cost_groups(self):
        """Lấy danh sách tất cả các nhóm chi phí."""
        groups = []
        for doc in self.group_col.stream():
            data = doc.to_dict()
            data['id'] = doc.id
            groups.append(data)
        return groups
    
    def update_cost_group(self, group_id, updates):
        """Cập nhật thông tin nhóm chi phí."""
        self.group_col.document(group_id).update(updates)

    def delete_cost_group(self, group_id):
        """Xóa một nhóm chi phí."""
        self.group_col.document(group_id).delete()

    # --- COST ENTRIES (BẢN GHI CHI PHÍ) ---
    def create_cost_entry(self, entry_data):
        """Tạo một bản ghi chi phí mới."""
        entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
        entry_data['entry_id'] = entry_id
        entry_data['created_at'] = datetime.now().isoformat()
        entry_data['status'] = 'ACTIVE' # Trạng thái: ACTIVE, CANCELLED
        
        # Đảm bảo các giá trị mặc định nếu không được cung cấp
        entry_data.setdefault('is_amortized', False)
        entry_data.setdefault('amortization_months', 0)
        entry_data.setdefault('start_amortization_date', None)
        entry_data.setdefault('evidence_url', None)

        self.entry_col.document(entry_id).set(entry_data)
        return entry_data

    def get_cost_entry(self, entry_id):
        """Lấy thông tin chi tiết của một bản ghi chi phí."""
        doc = self.entry_col.document(entry_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def query_cost_entries(self, filters=None):
        """
        Truy vấn các bản ghi chi phí với bộ lọc.
        filters là một dict, ví dụ:
        {
            "branch_id": "BR-001",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2023-01-31T23:59:59",
            "status": "ACTIVE"
        }
        """
        query = self.entry_col

        if filters:
            if 'branch_id' in filters:
                query = query.where('branch_id', '==', filters['branch_id'])
            if 'status' in filters:
                query = query.where('status', '==', filters['status'])
            # Firestore không hỗ trợ lọc theo 2 trường bất bình đẳng (range) cùng lúc
            # nên việc lọc start_date và end_date cần được xử lý cẩn thận
            if 'start_date' in filters:
                 query = query.where('entry_date', '>=', filters['start_date'])
            if 'end_date' in filters:
                 query = query.where('entry_date', '<=', filters['end_date'])

        entries = []
        for doc in query.stream():
            data = doc.to_dict()
            entries.append(data)
        return entries

    def update_cost_entry(self, entry_id, updates):
        """
        Cập nhật một bản ghi chi phí.
        'updates' là một dict chứa các trường cần thay đổi.
        """
        updates['updated_at'] = datetime.now().isoformat()
        self.entry_col.document(entry_id).update(updates)
        return True

    def cancel_cost_entry(self, entry_id, user_id):
        """Hủy một bản ghi chi phí."""
        updates = {
            "status": "CANCELLED",
            "cancelled_by": user_id,
            "cancelled_at": datetime.now().isoformat()
        }
        self.update_cost_entry(entry_id, updates)
        return True
        
    def restore_cost_entry(self, entry_id):
        """Phục hồi một bản ghi chi phí đã hủy."""
        updates = {
            "status": "ACTIVE",
        }
        # Xóa các trường liên quan đến việc hủy
        updates['cancelled_by'] = firestore.DELETE_FIELD
        updates['cancelled_at'] = firestore.DELETE_FIELD
        self.update_cost_entry(entry_id, updates)
        return True

    def delete_cost_entry_permanently(self, entry_id):
        """
        Xóa vĩnh viễn một bản ghi chi phí. 
        Chỉ dành cho Super Admin.
        """
        self.entry_col.document(entry_id).delete()
        return True
