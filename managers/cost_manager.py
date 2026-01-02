
import uuid
from datetime import datetime
from google.cloud import firestore
import logging

class CostManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.bucket = firebase_client.bucket
        self.group_col = self.db.collection('cost_groups')
        self.entry_col = self.db.collection('cost_entries')
        self.allocation_rules_col = self.db.collection('cost_allocation_rules')

    # --- COST GROUPS (NHÓM CHI PHÍ) ---
    def get_cost_groups(self):
        return [doc.to_dict() for doc in self.group_col.order_by("group_name").stream()]

    # --- COST ENTRIES (BẢN GHI CHI PHÍ) ---
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
        """
        Lấy và lọc các bản ghi chi phí. 
        Để tránh lỗi chỉ mục phức hợp của Firestore, hàm này sẽ lấy tất cả các bản ghi
        và thực hiện lọc/sắp xếp ở phía server (Python).
        """
        try:
            all_entries = [doc.to_dict() for doc in self.entry_col.stream()]
        except Exception as e:
            logging.error(f"Error fetching all cost entries from Firestore: {e}")
            return [] # Trả về danh sách rỗng nếu có lỗi khi truy vấn

        if not filters:
            filters = {}

        filtered_entries = all_entries

        # Áp dụng các bộ lọc bằng Python
        if 'branch_ids' in filters and filters['branch_ids']:
            filtered_entries = [e for e in filtered_entries if e.get('branch_id') in filters['branch_ids']]
        elif 'branch_id' in filters:
            filtered_entries = [e for e in filtered_entries if e.get('branch_id') == filters['branch_id']]

        if filters.get('status'):
            filtered_entries = [e for e in filtered_entries if e.get('status') == filters['status']]

        if filters.get('source_entry_id_is_null'):
            filtered_entries = [e for e in filtered_entries if e.get('source_entry_id') is None]

        if filters.get('start_date'):
            filtered_entries = [e for e in filtered_entries if e.get('entry_date') and e.get('entry_date') >= filters['start_date']]

        if filters.get('end_date'):
            filtered_entries = [e for e in filtered_entries if e.get('entry_date') and e.get('entry_date') <= filters['end_date']]

        # Sắp xếp kết quả bằng Python
        try:
            filtered_entries.sort(key=lambda x: x.get('entry_date', '0'), reverse=True)
        except Exception as e:
            logging.warning(f"Could not sort cost entries: {e}")

        return filtered_entries

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
        if source_doc.get('status') == 'ALLOCATED': raise Exception("Chi phí này đã được phân bổ.")
        
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
                **source_doc,
                'id': new_entry_id,
                'branch_id': branch_id,
                'amount': allocated_amount,
                'source_entry_id': source_entry_id,
                'created_at': datetime.now().isoformat(),
                'created_by': user_id,
                'notes': f"Phân bổ từ chi phí {source_entry_id} theo quy tắc {rule['name']}"
            }
            transaction.set(new_entry_ref, new_entry_data)

        transaction.update(source_ref, {'status': 'ALLOCATED', 'notes': f"Đã phân bổ theo quy tắc {rule['name']} bởi {user_id}."})

    def apply_allocation(self, source_entry_id, rule_id, user_id):
        transaction = self.db.transaction()
        self._apply_allocation_transaction(transaction, source_entry_id, rule_id, user_id)
