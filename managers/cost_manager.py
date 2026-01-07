
import uuid
from datetime import datetime
import logging
import streamlit as st
from google.cloud import firestore
from dateutil.relativedelta import relativedelta
from managers.image_handler import ImageHandler
from managers.category_manager import CategoryManager

def hash_cost_manager(manager):
    return "CostManager"

class CostManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.entry_col = self.db.collection('cost_entries')
        self.transactions_col = self.db.collection('transactions') # Thêm collection mới
        self.allocation_rules_col = self.db.collection('cost_allocation_rules')
        self._image_handler = None
        self.receipt_image_folder_id = st.secrets.get("drive_receipt_folder_id") or st.secrets.get("drive_folder_id")
        self.category_manager = CategoryManager(firebase_client) # Sử dụng CategoryManager

    # --- Cost Group Methods (using CategoryManager) ---
    def get_all_cost_groups(self):
        return self.category_manager.get_all_category_items('cost_groups')

    def add_cost_group(self, group_name: str, description: str):
        return self.category_manager.add_category_item(
            'cost_groups',
            {'group_name': group_name, 'description': description, 'created_at': datetime.now().isoformat()},
            id_prefix="CG"
        )

    def update_cost_group(self, group_id: str, updates: dict):
        return self.category_manager.update_category_item('cost_groups', group_id, updates)

    def delete_cost_group(self, group_id: str):
        return self.category_manager.delete_category_item('cost_groups', group_id)

    @property
    def image_handler(self):
        if self._image_handler is None and "drive_oauth" in st.secrets:
            try:
                creds_info = dict(st.secrets["drive_oauth"])
                if creds_info.get('refresh_token'):
                    self._image_handler = ImageHandler(credentials_info=creds_info)
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler for costs: {e}")
        return self._image_handler

    def create_cost_entry(self, **kwargs):
        attachment_file = kwargs.pop('attachment_file', None)
        base_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
        attachment_id = None

        if attachment_file and self.image_handler and self.receipt_image_folder_id:
            try:
                attachment_id = self.image_handler.upload_image(
                    attachment_file, self.receipt_image_folder_id, base_filename=base_id
                )
            except Exception as e:
                return False, f"Lỗi tải ảnh lên: {e}"

        kwargs['attachment_id'] = attachment_id
        try:
            batch = self.db.batch()
            now_iso = datetime.now().isoformat()

            if not kwargs.get('is_amortized') or kwargs.get('amortize_months', 0) <= 1:
                entry_id = base_id
                entry_data = {**kwargs, 'id': entry_id, 'created_at': now_iso, 'status': 'ACTIVE', 'source_entry_id': None}
                entry_ref = self.entry_col.document(entry_id)
                batch.set(entry_ref, entry_data)

                # Tạo một transaction tương ứng
                trans_ref = self.transactions_col.document(entry_id)
                trans_data = self._map_cost_to_transaction(entry_data)
                batch.set(trans_ref, trans_data)

            else: # Xử lý chi phí trả trước
                source_entry_id = base_id
                source_ref = self.entry_col.document(source_entry_id)
                source_entry_data = {**kwargs, 'name': f"[TRẢ TRƯỚC] {kwargs['name']}", 'created_at': now_iso, 'status': 'AMORTIZED_SOURCE', 'id': source_entry_id}
                batch.set(source_ref, source_entry_data)
                # Không tạo transaction cho bút toán gốc của chi phí trả trước

                monthly_amount = round(kwargs['amount'] / kwargs['amortize_months'], 2)
                start_date = datetime.fromisoformat(kwargs['entry_date'])
                for i in range(kwargs['amortize_months']):
                    child_id = f"CE-AM-{uuid.uuid4().hex[:7].upper()}"
                    child_ref = self.entry_col.document(child_id)
                    child_data = {
                        'id': child_id, 'branch_id': kwargs['branch_id'], 'group_id': kwargs['group_id'],
                        'name': f"{kwargs['name']} (Tháng {i + 1}/{kwargs['amortize_months']})",
                        'amount': monthly_amount, 'entry_date': (start_date + relativedelta(months=i)).isoformat(),
                        'created_by': kwargs['created_by'], 'classification': kwargs['classification'],
                        'attachment_id': None, 'is_amortized': False, 'amortize_months': 0,
                        'created_at': now_iso, 'status': 'ACTIVE', 'source_entry_id': source_entry_id
                    }
                    batch.set(child_ref, child_data)
                    
                    # Tạo transaction cho từng bút toán con hàng tháng
                    child_trans_ref = self.transactions_col.document(child_id)
                    child_trans_data = self._map_cost_to_transaction(child_data)
                    batch.set(child_trans_ref, child_trans_data)
            
            batch.commit()
            self.query_cost_entries.clear()
            return True, base_id
        except Exception as e:
            logging.error(f"Error creating cost entry: {e}")
            if attachment_id and self.image_handler: self.image_handler.delete_image_by_id(attachment_id)
            raise e

    def delete_cost_entry(self, entry_id: str):
        try:
            batch = self.db.batch()
            entry_ref = self.entry_col.document(entry_id)
            entry_doc = entry_ref.get()
            if not entry_doc.exists: return False, "Bút toán không tồn tại."
            
            attachment_id = entry_doc.to_dict().get('attachment_id')
            if attachment_id and self.image_handler: self.image_handler.delete_image_by_id(attachment_id)

            # Xóa bút toán chi phí
            batch.delete(entry_ref)
            
            # Xóa transaction tương ứng
            trans_ref = self.transactions_col.document(entry_id)
            batch.delete(trans_ref)

            batch.commit()
            self.query_cost_entries.clear()
            self.get_cost_entry.clear()
            return True, f"Đã xóa thành công bút toán {entry_id}."
        except Exception as e:
            logging.error(f"Error deleting cost entry {entry_id}: {e}")
            return False, f"Lỗi khi xóa: {e}"

    def _map_cost_to_transaction(self, cost_data: dict) -> dict:
        """Chuyển đổi dữ liệu từ một bút toán chi phí sang định dạng của một transaction."""
        return {
            "id": cost_data['id'],
            "type": "EXPENSE",
            "status": "COMPLETED",
            "created_at": datetime.fromisoformat(cost_data['entry_date']), # Dùng ngày hạch toán
            "branch_id": cost_data['branch_id'],
            "cashier_id": cost_data['created_by'], # Người tạo chi phí
            "total_amount": -abs(cost_data['amount']), # Chi phí là số âm
            "total_cogs": 0,
            "items": [], # Không có items cho chi phí
            "notes": cost_data.get('name'),
            # Các trường dành riêng cho chi phí
            "expense_details": {
                "group_id": cost_data.get('group_id'),
                "classification": cost_data.get('classification'),
                "attachment_id": cost_data.get('attachment_id'),
                "source_entry_id": cost_data.get('source_entry_id'),
            }
        }
    
    def get_allocation_rules(self):
        try:
            rules = self.allocation_rules_col.stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in rules]
        except Exception as e:
            logging.error(f"Error getting cost allocation rules: {e}")
            st.error(f"Lỗi khi tải quy tắc phân bổ: {e}")
            return []

    def create_allocation_rule(self, rule_data):
        try:
            doc_ref = self.allocation_rules_col.document()
            rule_data['id'] = doc_ref.id
            rule_data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(rule_data)
            self.get_allocation_rules.clear()
            return True, f"Đã tạo quy tắc '{rule_data['rule_name']}' thành công."
        except Exception as e:
            logging.error(f"Error creating allocation rule: {e}")
            return False, f"Lỗi khi tạo quy tắc: {e}"

    def delete_allocation_rule(self, rule_id):
        try:
            self.allocation_rules_col.document(rule_id).delete()
            self.get_allocation_rules.clear()
            return True, "Đã xóa quy tắc thành công."
        except Exception as e:
            logging.error(f"Error deleting allocation rule {rule_id}: {e}")
            return False, f"Lỗi khi xóa quy tắc: {e}"

    def get_cost_entry(self, entry_id):
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        if filters is None: filters = {}
        query = self.entry_col
        if 'branch_ids' in filters and filters['branch_ids']:
            query = query.where('branch_id', 'in', filters['branch_ids'])
        if 'status' in filters:
            query = query.where('status', '==', filters['status'])
        if filters.get('source_entry_id_is_null'):
            query = query.where('source_entry_id', '==', None)
        if 'start_date' in filters:
            query = query.where('entry_date', '>=', filters['start_date'])
        if 'end_date' in filters:
            query = query.where('entry_date', '<=', filters['end_date'])
        try:
            query = query.order_by('entry_date', direction=firestore.Query.DESCENDING)
            docs = query.stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logging.error(f"Error querying cost entries: {e}")
            return []

CostManager.get_cost_entry = st.cache_data(ttl=3600, hash_funcs={CostManager: hash_cost_manager})(CostManager.get_cost_entry)
CostManager.query_cost_entries = st.cache_data(ttl=300, hash_funcs={CostManager: hash_cost_manager})(CostManager.query_cost_entries)
CostManager.get_allocation_rules = st.cache_data(ttl=3600, hash_funcs={CostManager: hash_cost_manager})(CostManager.get_allocation_rules)
