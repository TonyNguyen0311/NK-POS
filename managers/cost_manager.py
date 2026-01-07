
import uuid
from datetime import datetime
import logging
import streamlit as st
from google.cloud import firestore
from dateutil.relativedelta import relativedelta

from managers.image_handler import ImageHandler

def hash_cost_manager(manager):
    return "CostManager"

class CostManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.entry_col = self.db.collection('cost_entries')
        self.allocation_rules_col = self.db.collection('cost_allocation_rules')
        self._image_handler = None
        self.receipt_image_folder_id = st.secrets.get("drive_receipt_folder_id") or st.secrets.get("drive_folder_id")

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

    def get_all_category_items(self, collection_name: str):
        try:
            docs = self.db.collection(collection_name).order_by("created_at").stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting items from {collection_name}: {e}")
            st.error(f"Lỗi khi tải dữ liệu từ {collection_name}: {e}")
            return []

    def add_category_item(self, collection_name: str, data: dict):
        try:
            doc_ref = self.db.collection(collection_name).document()
            data['id'] = doc_ref.id
            data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(data)
            self.get_all_category_items.clear()
            return True
        except Exception as e:
            logging.error(f"Error adding item to {collection_name}: {e}")
            raise e

    def update_category_item(self, collection_name: str, doc_id: str, updates: dict):
        try:
            self.db.collection(collection_name).document(doc_id).update(updates)
            self.get_all_category_items.clear()
            return True
        except Exception as e:
            logging.error(f"Error updating item {doc_id} in {collection_name}: {e}")
            raise e

    def delete_category_item(self, collection_name: str, doc_id: str):
        try:
            self.db.collection(collection_name).document(doc_id).delete()
            self.get_all_category_items.clear()
            return True
        except Exception as e:
            logging.error(f"Error deleting item {doc_id} from {collection_name}: {e}")
            raise e
            
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
                st.error(f"Lỗi khi tải ảnh chứng từ lên: {e}")
                return False, "Lỗi tải ảnh lên, bút toán chưa được tạo."

        kwargs['attachment_id'] = attachment_id
        try:
            if not kwargs.get('is_amortized') or kwargs.get('amortize_months', 0) <= 1:
                entry_id = base_id
                entry_data = {**kwargs, 'id': entry_id, 'created_at': datetime.now().isoformat(), 'status': 'ACTIVE', 'source_entry_id': None}
                self.entry_col.document(entry_id).set(entry_data)
            else:
                # Create batch for amortized entries
                batch = self.db.batch()
                source_entry_id = base_id
                source_ref = self.entry_col.document(source_entry_id)
                source_entry_data = {**kwargs, 'name': f"[TRẢ TRƯỚC] {kwargs['name']}", 'created_at': datetime.now().isoformat(), 'status': 'AMORTIZED_SOURCE', 'id': source_entry_id}
                batch.set(source_ref, source_entry_data)

                monthly_amount = round(kwargs['amount'] / kwargs['amortize_months'], 2)
                start_date = datetime.fromisoformat(kwargs['entry_date'])
                for i in range(kwargs['amortize_months']):
                    child_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
                    child_ref = self.entry_col.document(child_id)
                    child_data = {
                        'id': child_id, 'branch_id': kwargs['branch_id'], 'group_id': kwargs['group_id'],
                        'name': f"{kwargs['name']} (Tháng {i + 1}/{kwargs['amortize_months']})",
                        'amount': monthly_amount, 'entry_date': (start_date + relativedelta(months=i)).isoformat(),
                        'created_by': kwargs['created_by'], 'classification': kwargs['classification'],
                        'attachment_id': None, 'is_amortized': False, 'amortize_months': 0,
                        'created_at': datetime.now().isoformat(), 'status': 'ACTIVE', 'source_entry_id': source_entry_id
                    }
                    batch.set(child_ref, child_data)
                batch.commit()

            self.query_cost_entries.clear()
            return True, base_id
        except Exception as e:
            logging.error(f"Error creating cost entry: {e}")
            if attachment_id and self.image_handler: self.image_handler.delete_image_by_id(attachment_id)
            st.error(f"Lỗi khi tạo bút toán chi phí: {e}")
            return False, None

    def delete_cost_entry(self, entry_id: str):
        # ... (implementation remains the same)

    def get_cost_entry(self, entry_id):
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        """
        Queries cost entries from Firestore based on a set of filters.
        NOTE: This function may require creating composite indexes in Firestore.
        If you see an error in the terminal with a link to create an index, please
        follow that link to enable the query.
        """
        if filters is None: filters = {}
        query = self.entry_col

        if 'branch_ids' in filters and filters['branch_ids']:
            query = query.where('branch_id', 'in', filters['branch_ids'])
        if 'branch_id' in filters:
            query = query.where('branch_id', '==', filters['branch_id'])
        if 'status' in filters:
            query = query.where('status', '==', filters['status'])
        if filters.get('source_entry_id_is_null'):
            query = query.where('source_entry_id', '==', None)
        if 'start_date' in filters:
            query = query.where('entry_date', '>=', filters['start_date'])
        if 'end_date' in filters:
            query = query.where('entry_date', '<=', filters['end_date'])

        try:
            # Add ordering before streaming the results
            query = query.order_by('entry_date', direction=firestore.Query.DESCENDING)
            docs = query.stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logging.error(f"Error querying cost entries: {e}")
            st.warning(
                "Lỗi khi truy vấn chi phí. Có thể bạn cần tạo một chỉ mục (index) trong Firestore. "
                "Hãy kiểm tra log của terminal để xem có link tạo chỉ mục tự động không."
            )
            return []

# ... (Rest of the class and decorators remain the same)
CostManager.get_all_category_items = st.cache_data(ttl=3600, hash_funcs={CostManager: hash_cost_manager})(CostManager.get_all_category_items)
CostManager.get_cost_entry = st.cache_data(ttl=3600, hash_funcs={CostManager: hash_cost_manager})(CostManager.get_cost_entry)
CostManager.query_cost_entries = st.cache_data(ttl=300, hash_funcs={CostManager: hash_cost_manager})(CostManager.query_cost_entries)
CostManager.get_allocation_rules = st.cache_data(ttl=3600, hash_funcs={CostManager: hash_cost_manager})(CostManager.get_allocation_rules)
