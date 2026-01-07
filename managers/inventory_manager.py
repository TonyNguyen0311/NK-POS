
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from datetime import datetime, time

@firestore.transactional
def _create_voucher_and_transactions_transactional(transaction, db, voucher_ref, voucher_data, items):
    """
    Hàm giao dịch cốt lõi để tạo chứng từ và các bản ghi giao dịch tồn kho liên quan.
    Đảm bảo tất cả các hoạt động được thực hiện một cách nguyên tử.
    """
    inventory_col = db.collection('inventory')
    transactions_col = db.collection('inventory_transactions')

    inventory_states = {}
    for item in items:
        sku = item['sku']
        branch_id = voucher_data['branch_id']
        inv_doc_ref = inventory_col.document(f"{sku.upper()}_{branch_id}")
        inv_snapshot = inv_doc_ref.get(transaction=transaction)
        inventory_states[sku] = {"ref": inv_doc_ref, "snapshot": inv_snapshot}

    processed_transaction_ids = []
    for item in items:
        sku = item['sku']
        delta = item['quantity']
        purchase_price = item.get('purchase_price')
        state = inventory_states[sku]
        inv_doc_ref = state["ref"]
        inv_snapshot = state["snapshot"]

        current_quantity = 0
        current_avg_cost = 0
        if inv_snapshot.exists:
            inv_data = inv_snapshot.to_dict()
            current_quantity = inv_data.get('stock_quantity', 0)
            current_avg_cost = inv_data.get('average_cost', 0)

        new_quantity = current_quantity + delta
        new_avg_cost = current_avg_cost

        if delta > 0 and purchase_price is not None and purchase_price >= 0:
            total_value = current_quantity * current_avg_cost
            adjustment_value = delta * purchase_price
            new_avg_cost = (total_value + adjustment_value) / new_quantity if new_quantity > 0 else 0
        
        if new_quantity < 0:
            raise ValueError(f"Tồn kho không đủ cho sản phẩm {sku}. Giao dịch thất bại.")

        transaction.set(inv_doc_ref, {
            'sku': sku, 'branch_id': voucher_data['branch_id'],
            'stock_quantity': new_quantity, 'average_cost': new_avg_cost,
            'last_updated': voucher_data['created_at'],
        }, merge=True)

        trans_id = f"TRANS-{uuid.uuid4().hex[:10].upper()}"
        trans_ref = transactions_col.document(trans_id)
        transaction.set(trans_ref, {
            'id': trans_id, 'voucher_id': voucher_ref.id, 'sku': sku,
            'branch_id': voucher_data['branch_id'], 'user_id': voucher_data['created_by'],
            'reason': voucher_data['type'], 'delta': delta,
            'quantity_before': current_quantity, 'quantity_after': new_quantity,
            'cost_at_transaction': new_avg_cost, 'purchase_price': purchase_price,
            'notes': voucher_data.get('notes', ''), 'timestamp': voucher_data['created_at'],
        })
        processed_transaction_ids.append(trans_id)

    transaction.set(voucher_ref, {**voucher_data, 'transaction_ids': processed_transaction_ids})

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.vouchers_col = self.db.collection('inventory_vouchers')
        self.inventory_col = self.db.collection('inventory')
        self.transactions_col = self.db.collection('inventory_transactions')

    def execute_voucher_creation_in_transaction(self, transaction, voucher_type: str, branch_id: str, user_id: str, items: list, date: datetime, notes: str = '', **kwargs):
        """
        Thực thi việc tạo chứng từ và cập nhật tồn kho BÊN TRONG một giao dịch đã tồn tại.
        Đây là phương thức cốt lõi cho phép các manager khác tích hợp.
        """
        if not items:
            raise ValueError("Chứng từ phải có ít nhất một sản phẩm.")

        prefix_map = st.secrets.get("voucher_prefixes", { # Load from secrets
            "GOODS_RECEIPT": "VGR",
            "GOODS_ISSUE": "VGI",
            "ADJUSTMENT": "VADJ",
            "REVERSAL_GOODS_RECEIPT": "VCAN",
            "REVERSAL_GOODS_ISSUE": "VCAN",
        })
        prefix = prefix_map.get(voucher_type, "VOU")
        voucher_id = f"{prefix}-{uuid.uuid4().hex[:10].upper()}"
        
        created_at = datetime.combine(date, datetime.now().time()).isoformat()

        voucher_data = {
            'id': voucher_id,
            'branch_id': branch_id,
            'created_by': user_id,
            'type': voucher_type,
            'status': 'COMPLETED',
            'created_at': created_at,
            'notes': notes,
            'items': items,
            **kwargs
        }

        voucher_ref = self.vouchers_col.document(voucher_id)
        _create_voucher_and_transactions_transactional(transaction, self.db, voucher_ref, voucher_data, items)
        return voucher_id

    def create_goods_receipt(self, branch_id, user_id, items, supplier, notes, receipt_date):
        transaction = self.db.transaction()
        voucher_id = self.execute_voucher_creation_in_transaction(
            transaction, "GOODS_RECEIPT", branch_id, user_id, items, receipt_date, notes, supplier=supplier
        )
        self._clear_caches()
        return voucher_id

    def create_goods_issue(self, branch_id, user_id, items, notes, issue_date):
        issue_items = [{'sku': item['sku'], 'quantity': -abs(item.get('quantity', 0))} for item in items if item.get('quantity', 0) > 0]
        if not issue_items:
            raise ValueError("Không có sản phẩm hợp lệ để xuất kho.")
        
        transaction = self.db.transaction()
        voucher_id = self.execute_voucher_creation_in_transaction(
            transaction, "GOODS_ISSUE", branch_id, user_id, issue_items, issue_date, notes
        )
        self._clear_caches()
        return voucher_id

    def create_adjustment(self, branch_id, user_id, items, reason, notes, adjustment_date):
        if not items: raise ValueError("Phiếu điều chỉnh phải có ít nhất một sản phẩm.")

        @firestore.transactional
        def _transactional_adjustment(transaction):
            items_with_delta = []
            for item in items:
                inv_doc_ref = self.inventory_col.document(f"{item['sku'].upper()}_{branch_id}")
                inv_snapshot = inv_doc_ref.get(transaction=transaction)
                
                current_quantity = 0
                if inv_snapshot.exists:
                    current_quantity = inv_snapshot.to_dict().get('stock_quantity', 0)
                
                delta = item['actual_quantity'] - current_quantity
                
                if delta != 0:
                    items_with_delta.append({
                        'sku': item['sku'], 
                        'quantity': delta,
                        'actual_quantity': item['actual_quantity'],
                        'quantity_before': current_quantity
                    })
            
            if not items_with_delta:
                return None

            voucher_id = self.execute_voucher_creation_in_transaction(
                transaction,
                f'ADJUSTMENT_{reason.upper()}',
                branch_id,
                user_id,
                items_with_delta,
                adjustment_date,
                notes,
                reason=reason
            )
            return voucher_id

        voucher_id = _transactional_adjustment(self.db.transaction())

        if voucher_id:
            self._clear_caches()
        
        return voucher_id

    def cancel_voucher(self, voucher_id: str, user_id: str):
        original_voucher_ref = self.vouchers_col.document(voucher_id)
        original_voucher_doc = original_voucher_ref.get()
        if not original_voucher_doc.exists: raise FileNotFoundError("Không tìm thấy chứng từ gốc.")
        
        voucher_dict = original_voucher_doc.to_dict()
        if voucher_dict.get('status') == 'CANCELLED': raise ValueError("Chứng từ này đã bị huỷ trước đó.")

        reversal_items = [{'sku': item['sku'], 'quantity': -item['quantity'], 'purchase_price': item.get('purchase_price')} for item in voucher_dict['items']]
        
        cancellation_notes = f"Huỷ chứng từ {voucher_id}."
        reversal_type = f"REVERSAL_{voucher_dict['type']}"
        
        @firestore.transactional
        def _cancel_transactionally(transaction):
            # Tạo chứng từ đảo ngược
            self.execute_voucher_creation_in_transaction(
                transaction, reversal_type, voucher_dict['branch_id'], user_id, reversal_items, 
                datetime.now(), cancellation_notes, reverses_voucher_id=voucher_id
            )
            # Cập nhật trạng thái chứng từ gốc
            transaction.update(original_voucher_ref, {'status': 'CANCELLED', 'cancelled_by': user_id, 'cancelled_at': datetime.now().isoformat()})

        _cancel_transactionally(self.db.transaction())
        self._clear_caches()

    def update_inventory(self, transaction, sku: str, branch_id: str, delta: int, order_id: str, user_id: str) -> float:
        if delta == 0:
            inv_doc_ref = self.inventory_col.document(f"{sku.upper()}_{branch_id}")
            inv_snapshot = inv_doc_ref.get(transaction=transaction)
            return inv_snapshot.to_dict().get('average_cost', 0) if inv_snapshot.exists else 0

        inv_doc_ref = self.inventory_col.document(f"{sku.upper()}_{branch_id}")
        inv_snapshot = inv_doc_ref.get(transaction=transaction)

        current_quantity = 0
        average_cost = 0
        if inv_snapshot.exists:
            inv_data = inv_snapshot.to_dict()
            current_quantity = inv_data.get('stock_quantity', 0)
            average_cost = inv_data.get('average_cost', 0)

        new_quantity = current_quantity + delta
        if new_quantity < 0:
            raise ValueError(f"Tồn kho không đủ cho sản phẩm {sku} tại chi nhánh {branch_id}. Giao dịch thất bại.")

        transaction_timestamp = datetime.now().isoformat()
        transaction.set(inv_doc_ref, {'stock_quantity': new_quantity, 'last_updated': transaction_timestamp}, merge=True)

        trans_id = f"TRANS-{uuid.uuid4().hex[:10].upper()}"
        trans_ref = self.transactions_col.document(trans_id)
        transaction.set(trans_ref, {
            'id': trans_id, 'voucher_id': order_id, 'sku': sku, 'branch_id': branch_id, 'user_id': user_id,
            'reason': 'SALE', 'delta': delta, 'quantity_before': current_quantity, 'quantity_after': new_quantity,
            'cost_at_transaction': average_cost, 'purchase_price': None, 'notes': f'Bán hàng theo đơn hàng {order_id}',
            'timestamp': transaction_timestamp,
        })
        return average_cost

    def _clear_caches(self):
        self.get_inventory_by_branch.clear()
        self.get_inventory_item.clear()
        self.get_vouchers_by_branch.clear()

    @st.cache_data(ttl=60)
    def get_inventory_item(_self, sku: str, branch_id: str):
        if not sku or not branch_id: return None
        doc_ref = _self.inventory_col.document(f"{sku.upper()}_{branch_id}")
        doc = doc_ref.get()
        return doc.to_dict() if doc.exists else None

    @st.cache_data(ttl=60)
    def get_inventory_by_branch(_self, branch_id: str) -> dict:
        try:
            if not branch_id: return {}
            docs = _self.inventory_col.where('branch_id', '==', branch_id).stream()
            return {doc.to_dict()['sku']: doc.to_dict() for doc in docs if 'sku' in doc.to_dict()}
        except Exception as e:
            logging.error(f"Error fetching inventory for branch '{branch_id}': {e}")
            return {}

    @st.cache_data(ttl=120)
    def get_vouchers_by_branch(_self, branch_id: str, limit: int = 100):
        if not branch_id: return []
        query = _self.vouchers_col.where('branch_id', '==', branch_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
        return [doc.to_dict() for doc in query.stream()]
