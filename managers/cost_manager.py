
import uuid
from datetime import datetime
import logging
import streamlit as st
from google.cloud import firestore
from dateutil.relativedelta import relativedelta

# Corrected import path to be absolute
from managers.image_handler import ImageHandler

class CostManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.entry_col = self.db.collection('cost_entries')
        self.allocation_rules_col = self.db.collection('cost_allocation_rules')
        self.image_handler = self._initialize_image_handler()
        self.receipt_image_folder_id = st.secrets.get("drive_receipt_folder_id") or st.secrets.get("drive_folder_id")

    def _initialize_image_handler(self):
        if "drive_oauth" in st.secrets:
            try:
                creds_info = dict(st.secrets["drive_oauth"])
                if creds_info.get('refresh_token'):
                    return ImageHandler(credentials_info=creds_info)
            except Exception as e:
                logging.error(f"Failed to initialize ImageHandler for costs: {e}")
        return None

    # --- Generic Category Management Methods (for CostGroups, etc.) ---

    def get_all_category_items(self, collection_name: str):
        """Fetches all items from a specified category collection (e.g., CostGroups)."""
        try:
            docs = self.db.collection(collection_name).order_by("created_at").stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        except Exception as e:
            logging.error(f"Error getting items from {collection_name}: {e}")
            st.error(f"Lỗi khi tải dữ liệu từ {collection_name}: {e}")
            return []

    def add_category_item(self, collection_name: str, data: dict):
        """Adds a new item to a specified category collection."""
        try:
            doc_ref = self.db.collection(collection_name).document()
            data['id'] = doc_ref.id
            data['created_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(data)
            return True
        except Exception as e:
            logging.error(f"Error adding item to {collection_name}: {e}")
            raise e

    def update_category_item(self, collection_name: str, doc_id: str, updates: dict):
        """Updates an item in a specified category collection."""
        try:
            self.db.collection(collection_name).document(doc_id).update(updates)
            return True
        except Exception as e:
            logging.error(f"Error updating item {doc_id} in {collection_name}: {e}")
            raise e

    def delete_category_item(self, collection_name: str, doc_id: str):
        """Deletes an item from a specified category collection."""
        try:
            # TODO: Check if the cost group is in use before deleting.
            self.db.collection(collection_name).document(doc_id).delete()
            return True
        except Exception as e:
            logging.error(f"Error deleting item {doc_id} from {collection_name}: {e}")
            raise e

    # --- Cost Entry and Allocation Methods ---

    def upload_receipt_image(self, image_file):
        if not self.image_handler:
            st.error("Lỗi Cấu Hình: Trình xử lý ảnh chưa được khởi tạo.")
            return None
        if not self.receipt_image_folder_id:
            st.error("Lỗi Cấu Hình: ID thư mục ảnh chứng từ chưa được cài đặt.")
            return None
        try:
            return self.image_handler.upload_receipt_image(image_file, self.receipt_image_folder_id)
        except Exception as e:
            st.error(f"Lỗi khi tải ảnh chứng từ lên: {e}")
            return None

    def create_cost_entry(self, **kwargs):
        # Logic remains the same
        if not kwargs.get('is_amortized') or kwargs.get('amortize_months', 0) <= 1:
            entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
            entry_data = {
                **kwargs,
                'id': entry_id,
                'created_at': datetime.now().isoformat(),
                'status': 'ACTIVE',
                'source_entry_id': None
            }
            self.entry_col.document(entry_id).set(entry_data)
            return [entry_data]
        else:
            # Amortization logic remains the same
            batch = self.db.batch()
            source_entry_id = f"CE-{uuid.uuid4().hex[:8].upper()}"
            source_ref = self.entry_col.document(source_entry_id)
            source_entry_data = {
                **kwargs,
                'name': f"[TRẢ TRƯỚC] {kwargs['name']}",
                'created_at': datetime.now().isoformat(),
                'status': 'AMORTIZED_SOURCE',
                'source_entry_id': None,
                'id': source_entry_id
            }
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
                    'receipt_url': None, 'is_amortized': False, 'amortization_months': 0,
                    'created_at': datetime.now().isoformat(), 'status': 'ACTIVE',
                    'source_entry_id': source_entry_id
                }
                batch.set(child_ref, child_data)
            batch.commit()
            st.success(f"Đã tạo chi phí trả trước và {kwargs['amortize_months']} kỳ khấu hao.")
            return [source_entry_data]

    def get_cost_entry(self, entry_id):
        doc = self.entry_col.document(entry_id).get()
        return doc.to_dict() if doc.exists else None

    def query_cost_entries(self, filters=None):
        # Logic remains the same
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
        # Logic remains the same
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

    def create_allocation_rule(self, rule_name, description, splits):
        # Logic remains the same
        total_percentage = sum(item['percentage'] for item in splits)
        if total_percentage != 100:
            raise ValueError(f"Tổng tỷ lệ phần trăm phải bằng 100, hiện tại là {total_percentage}%.")
        rule_id = f"CAR-{uuid.uuid4().hex[:6].upper()}"
        self.allocation_rules_col.document(rule_id).set({
            'id': rule_id, 'name': rule_name, 'description': description, 'splits': splits
        })

    def get_allocation_rules(self):
        # Logic remains the same
        return [doc.to_dict() for doc in self.allocation_rules_col.order_by("name").stream()]

    @firestore.transactional
    def _apply_allocation_transaction(self, transaction, source_entry_id, rule_id, user_id):
        # Logic remains the same
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
        # Logic remains the same
        transaction = self.db.transaction()
        self._apply_allocation_transaction(transaction, source_entry_id, rule_id, user_id)

