
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
        """Xóa một nhóm chi phí. Cần kiểm tra xem có đang được sử dụng không trước khi xóa."""
        # In a real-world scenario, you'd check for dependencies first.
        self.group_col.document(group_id).delete()

    # --- COST ENTRIES (BẢN GHI CHI PHÍ) ---
    def upload_receipt_image(self, uploaded_file):
        """Uploads a receipt image to Firebase Storage and returns the public URL."""
        if not uploaded_file:
            return None
        
        file_name = f"receipts/{uuid.uuid4().hex}_{uploaded_file.name}"
        blob = self.bucket.blob(file_name)
        
        # Upload the file
        blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)
        
        # Make the blob publicly viewable
        blob.make_public()
        
        return blob.public_url

    def create_cost_entry(self, branch_id, name, amount, group_id, entry_date, created_by, classification, receipt_url=None, is_amortized=False, amortize_months=0):
        """Tạo một bản ghi chi phí mới với các trường cụ thể."""
        entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
        
        entry_data = {
            'id': entry_id,
            'branch_id': branch_id,
            'name': name,
            'amount': amount,
            'group_id': group_id,
            'entry_date': entry_date,
            'created_by': created_by,
            'classification': classification, 
            'receipt_url': receipt_url, # URL to the uploaded receipt image
            'is_amortized': is_amortized,
            'amortization_months': amortize_months if is_amortized else 0,
            'created_at': datetime.now().isoformat(),
            'status': 'ACTIVE', # Status: ACTIVE, CANCELLED
        }
        
        self.entry_col.document(entry_id).set(entry_data)
        return entry_data

    def get_cost_entry(self, entry_id):
        """Lấy thông tin chi tiết của một bản ghi chi phí."""
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        """Truy vấn các bản ghi chi phí với bộ lọc."""
        query = self.entry_col
        if not filters: filters = {}

        if 'branch_ids' in filters and filters['branch_ids']:
            query = query.where('branch_id', 'in', filters['branch_ids'])
        elif 'branch_id' in filters:
            query = query.where('branch_id', '==', filters['branch_id'])
        
        if 'status' in filters:
            query = query.where('status', '==', filters['status'])

        if 'start_date' in filters:
             query = query.where('entry_date', '>=', filters['start_date'])
        if 'end_date' in filters:
             query = query.where('entry_date', '<=', filters['end_date'])

        query = query.order_by('entry_date', direction=firestore.Query.DESCENDING)

        return [doc.to_dict() for doc in query.stream()]

    def cancel_cost_entry(self, entry_id, user_id):
        """Hủy một bản ghi chi phí (soft delete)."""
        updates = {
            "status": "CANCELLED",
            "cancelled_by": user_id,
            "cancelled_at": datetime.now().isoformat()
        }
        self.entry_col.document(entry_id).update(updates)
        return True
    
    def hard_delete_cost_entry(self, entry_id):
        """Xóa vĩnh viễn một bản ghi chi phí và ảnh liên quan. (Dành cho Admin)"""
        doc_ref = self.entry_col.document(entry_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            receipt_url = data.get('receipt_url')
            if receipt_url:
                try:
                    # Extract blob name from URL
                    blob_name = receipt_url.split(f"/{self.bucket.name}/")[1].split('?')[0]
                    blob = self.bucket.blob(blob_name)
                    if blob.exists():
                        blob.delete()
                except Exception as e:
                    # Log this error, but don't block deletion of the firestore doc
                    print(f"Error deleting blob from URL {receipt_url}: {e}")
            
            doc_ref.delete()
            return True
        return False
