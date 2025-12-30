
import uuid
from datetime import datetime
from google.cloud import firestore

class CostManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.bucket = firebase_client.bucket
        self.group_col = self.db.collection('cost_groups')
        self.entry_col = self.db.collection('cost_entries')
        self.allocation_rules_col = self.db.collection('cost_allocation_rules')

    # --- COST GROUPS (NHÓM CHI PHÍ) ---
    def create_cost_group(self, group_name, group_type):
        if group_type not in ['fixed', 'variable']:
            raise ValueError("Loại chi phí phải là 'fixed' hoặc 'variable'.")
        existing_groups = self.group_col.where('group_name', '==', group_name).limit(1).get()
        if len(list(existing_groups)) > 0:
            raise ValueError(f"Nhóm chi phí '{group_name}' đã tồn tại.")
        group_id = f"CG-{uuid.uuid4().hex[:6].upper()}"
        self.group_col.document(group_id).set({"id": group_id, "group_name": group_name, "group_type": group_type})

    def update_cost_group(self, group_id, group_name, group_type):
        if group_type not in ['fixed', 'variable']:
            raise ValueError("Loại chi phí phải là 'fixed' hoặc 'variable'.")
        self.group_col.document(group_id).update({"group_name": group_name, "group_type": group_type})

    def get_cost_groups(self):
        return [doc.to_dict() for doc in self.group_col.order_by("group_name").stream()]
    
    def delete_cost_group(self, group_id):
        self.group_col.document(group_id).delete()

    # --- COST ENTRIES (BẢN GHI CHI PHÍ) ---
    def upload_receipt_image(self, uploaded_file):
        if not uploaded_file: return None
        file_name = f"receipts/{uuid.uuid4().hex}_{uploaded_file.name}"
        blob = self.bucket.blob(file_name)
        blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)
        blob.make_public()
        return blob.public_url

    def create_cost_entry(self, branch_id, name, amount, group_id, entry_date, created_by, classification, receipt_url=None, is_amortized=False, amortize_months=0):
        entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
        entry_data = {
            'id': entry_id, 'branch_id': branch_id, 'name': name, 'amount': amount, 'group_id': group_id,
            'entry_date': entry_date, 'created_by': created_by, 'classification': classification, 
            'receipt_url': receipt_url, 'is_amortized': is_amortized, 'amortization_months': amortize_months if is_amortized else 0,
            'created_at': datetime.now().isoformat(), 'status': 'ACTIVE', 'source_entry_id': None
        }
        self.entry_col.document(entry_id).set(entry_data)
        return entry_data

    def get_cost_entry(self, entry_id):
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        query = self.entry_col
        if not filters: filters = {}
        if 'branch_ids' in filters and filters['branch_ids']:
            query = query.where('branch_id', 'in', filters['branch_ids'])
        elif 'branch_id' in filters:
            query = query.where('branch_id', '==', filters['branch_id'])
        if 'status' in filters:
            query = query.where('status', '==', filters['status'])
        if 'source_entry_id_is_null' in filters and filters['source_entry_id_is_null']:
             query = query.where('source_entry_id', '==', None)
        if 'start_date' in filters: query = query.where('entry_date', '>=', filters['start_date'])
        if 'end_date' in filters: query = query.where('entry_date', '<=', filters['end_date'])
        query = query.order_by('entry_date', direction=firestore.Query.DESCENDING)
        return [doc.to_dict() for doc in query.stream()]

    # --- ALLOCATION RULES ---
    def create_allocation_rule(self, rule_name, description, splits):
        total_percentage = sum(item['percentage'] for item in splits)
        if total_percentage != 100:
            raise ValueError(f"Tổng tỷ lệ phần trăm phải bằng 100, hiện tại là {total_percentage}%.")
        rule_id = f"CAR-{uuid.uuid4().hex[:6].upper()}"
        self.allocation_rules_col.document(rule_id).set({
            'id': rule_id, 'name': rule_name, 'description': description, 'splits': splits
        })

    def get_allocation_rules(self):
        return [doc.to_dict() for doc in self.allocation_rules_col.order_by("name").stream()]

    def delete_allocation_rule(self, rule_id):
        self.allocation_rules_col.document(rule_id).delete()

    @firestore.transactional
    def _apply_allocation_transaction(self, transaction, source_entry_id, rule_id, user_id):
        source_ref = self.entry_col.document(source_entry_id)
        source_doc = source_ref.get(transaction=transaction).to_dict()
        if source_doc['status'] == 'ALLOCATED': raise Exception("Chi phí này đã được phân bổ.")
        
        rule_ref = self.allocation_rules_col.document(rule_id)
        rule = rule_ref.get(transaction=transaction).to_dict()
        if not rule: raise Exception("Không tìm thấy quy tắc phân bổ.")

        source_amount = source_doc['amount']
        for split in rule['splits']:
            branch_id = split['branch_id']
            percentage = split['percentage']
            allocated_amount = source_amount * (percentage / 100.0)
            
            new_entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
            new_entry_ref = self.entry_col.document(new_entry_id)
            new_entry_data = {
                **source_doc, # Copy all fields from source
                'id': new_entry_id,
                'branch_id': branch_id,
                'amount': allocated_amount,
                'source_entry_id': source_entry_id, # Link back to the original entry
                'created_at': datetime.now().isoformat(),
                'created_by': user_id,
                'notes': f"Phân bổ từ chi phí {source_entry_id} theo quy tắc {rule['name']}"
            }
            transaction.set(new_entry_ref, new_entry_data)

        transaction.update(source_ref, {'status': 'ALLOCATED', 'notes': f"Đã phân bổ theo quy tắc {rule['name']} bởi {user_id}."})

    def apply_allocation(self, source_entry_id, rule_id, user_id):
        transaction = self.db.transaction()
        self._apply_allocation_transaction(transaction, source_entry_id, rule_id, user_id)
