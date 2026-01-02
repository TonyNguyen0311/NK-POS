
import uuid
from datetime import datetime
from google.cloud import firestore
import logging
from dateutil.relativedelta import relativedelta

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
        """
        Tạo một bản ghi chi phí.
        Nếu is_amortized=True, nó sẽ tạo một bản ghi 'gốc' và các bản ghi 'con' hàng tháng.
        """
        if not is_amortized or amortize_months <= 1:
            entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
            entry_data = {
                'id': entry_id, 'branch_id': branch_id, 'name': name, 'amount': amount, 'group_id': group_id,
                'entry_date': entry_date, 'created_by': created_by, 'classification': classification,
                'receipt_url': receipt_url, 'is_amortized': is_amortized, 'amortization_months': amortize_months,
                'created_at': datetime.now().isoformat(), 'status': 'ACTIVE', 'source_entry_id': None
            }
            self.entry_col.document(entry_id).set(entry_data)
            return [entry_data]  # Trả về dưới dạng list cho nhất quán
        else:
            batch = self.db.batch()
            
            # 1. Tạo bản ghi chi phí GỐC (source)
            source_entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
            source_ref = self.entry_col.document(source_entry_id)
            source_entry_data = {
                'id': source_entry_id, 'branch_id': branch_id, 'name': f"[TRẢ TRƯỚC] {name}",
                'amount': amount, 'group_id': group_id, 'entry_date': entry_date,
                'created_by': created_by, 'classification': classification, 'receipt_url': receipt_url,
                'is_amortized': True, 'amortization_months': amortize_months,
                'created_at': datetime.now().isoformat(), 'status': 'AMORTIZED_SOURCE',
                'source_entry_id': None
            }
            batch.set(source_ref, source_entry_data)
            created_entries = [source_entry_data]

            # 2. Tạo các bản ghi chi phí CON (child) hàng tháng
            monthly_amount = round(amount / amortize_months, 2)
            start_date = datetime.fromisoformat(entry_date)

            for i in range(amortize_months):
                child_entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
                child_entry_ref = self.entry_col.document(child_entry_id)
                current_month_date = start_date + relativedelta(months=i)

                child_entry_data = {
                    'id': child_entry_id, 'branch_id': branch_id, 'name': f"{name} (Tháng {i + 1}/{amortize_months})",
                    'amount': monthly_amount, 'group_id': group_id, 'entry_date': current_month_date.isoformat(),
                    'created_by': created_by, 'classification': classification, 'receipt_url': None,
                    'is_amortized': False, 'amortization_months': 0,
                    'created_at': datetime.now().isoformat(), 'status': 'ACTIVE',
                    'source_entry_id': source_entry_id
                }
                batch.set(child_entry_ref, child_entry_data)
                created_entries.append(child_entry_data)
            
            batch.commit()
            return created_entries

    def get_cost_entry(self, entry_id):
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        try:
            all_entries = [doc.to_dict() for doc in self.entry_col.stream()]
        except Exception as e:
            logging.error(f"Error fetching all cost entries from Firestore: {e}")
            return []

        if not filters: filters = {}
        filtered_entries = [e for e in all_entries if self._entry_matches_filters(e, filters)]
        
        filtered_entries.sort(key=lambda x: x.get('entry_date', '0'), reverse=True)
        return filtered_entries

    def _entry_matches_filters(self, entry, filters):
        if filters.get('branch_ids') and entry.get('branch_id') not in filters['branch_ids']:
            return False
        if filters.get('branch_id') and entry.get('branch_id') != filters['branch_id']:
            return False
        if filters.get('status') and entry.get('status') != filters['status']:
            return False
        if filters.get('source_entry_id_is_null') and entry.get('source_entry_id') is not None:
            return False
        if filters.get('start_date') and (not entry.get('entry_date') or entry.get('entry_date') < filters['start_date']):
            return False
        if filters.get('end_date') and (not entry.get('entry_date') or entry.get('entry_date') > filters['end_date']):
            return False
        return True

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
            transaction.set(new_entry_ref, {
                **source_doc, 'id': new_entry_id, 'branch_id': branch_id, 'amount': allocated_amount,
                'source_entry_id': source_entry_id, 'created_at': datetime.now().isoformat(),
                'created_by': user_id, 'notes': f"Phân bổ từ {source_entry_id} theo quy tắc {rule['name']}"
            })

        transaction.update(source_ref, {'status': 'ALLOCATED', 'notes': f"Đã phân bổ theo quy tắc {rule['name']}"})

    def apply_allocation(self, source_entry_id, rule_id, user_id):
        transaction = self.db.transaction()
        self._apply_allocation_transaction(transaction, source_entry_id, rule_id, user_id)
