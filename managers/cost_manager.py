
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
        # Check if group name already exists
        existing_groups = self.group_col.where('group_name', '==', group_name).limit(1).get()
        if len(list(existing_groups)) > 0:
            raise ValueError(f"Nhóm chi phí '{group_name}' đã tồn tại.")

        group_id = f"CG-{uuid.uuid4().hex[:6].upper()}"
        data = {"id": group_id, "group_name": group_name}
        self.group_col.document(group_id).set(data)
        return data

    def get_cost_groups(self):
        """Lấy danh sách tất cả các nhóm chi phí."""
        return [doc.to_dict() for doc in self.group_col.order_by("group_name").stream()]
    
    def delete_cost_group(self, group_id):
        """Xóa một nhóm chi phí."""
        # Optional: check if group is in use before deleting
        self.group_col.document(group_id).delete()

    # --- COST ENTRIES (BẢN GHI CHI PHÍ) ---
    def create_cost_entry(self, branch_id, name, amount, group_id, entry_date, created_by, classification, is_amortized=False, amortize_months=0):
        """Tạo một bản ghi chi phí mới với các trường cụ thể."""
        entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
        
        entry_data = {
            'id': entry_id,
            'branch_id': branch_id,
            'name': name,
            'amount': amount,
            'group_id': group_id,
            'entry_date': entry_date, # Should be ISO format string
            'created_by': created_by,
            'classification': classification, # Trường mới được thêm vào
            'is_amortized': is_amortized,
            'amortization_months': amortize_months if is_amortized else 0,
            'created_at': datetime.now().isoformat(),
            'status': 'ACTIVE', # Trạng thái: ACTIVE, CANCELLED
        }
        
        self.entry_col.document(entry_id).set(entry_data)
        return entry_data

    def get_cost_entry(self, entry_id):
        """Lấy thông tin chi tiết của một bản ghi chi phí."""
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        """
        Truy vấn các bản ghi chi phí với bộ lọc.
        filters['branch_ids'] có thể là một list các branch_id để query.
        """
        query = self.entry_col

        if not filters:
            filters = {}

        # Lọc theo nhiều chi nhánh nếu có
        if 'branch_ids' in filters and filters['branch_ids']:
            query = query.where('branch_id', 'in', filters['branch_ids'])
        elif 'branch_id' in filters:
            query = query.where('branch_id', '==', filters['branch_id'])
        
        if 'status' in filters:
            query = query.where('status', '==', filters['status'])
        else: # Mặc định chỉ lấy active
            query = query.where('status', '==', 'ACTIVE')

        # Lọc theo ngày tháng
        if 'start_date' in filters:
             query = query.where('entry_date', '>=', filters['start_date'])
        if 'end_date' in filters:
             query = query.where('entry_date', '<=', filters['end_date'])

        # Sắp xếp để có kết quả nhất quán
        query = query.order_by('entry_date', direction=firestore.Query.DESCENDING)

        return [doc.to_dict() for doc in query.stream()]

    def update_cost_entry(self, entry_id, updates):
        """Cập nhật một bản ghi chi phí."""
        updates['updated_at'] = datetime.now().isoformat()
        self.entry_col.document(entry_id).update(updates)
        return True

    def delete_cost_entry(self, entry_id, user_id):
        """Hủy một bản ghi chi phí (soft delete)."""
        updates = {
            "status": "CANCELLED",
            "cancelled_by": user_id,
            "cancelled_at": datetime.now().isoformat()
        }
        self.update_cost_entry(entry_id, updates)
        return True
