
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from datetime import datetime

def hash_inventory_manager(manager):
    return "InventoryManager"

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.inventory_col = self.db.collection('inventory')
        self.transfers_col = self.db.collection('stock_transfers')
        # NEW: Collection for all inventory transactions (goods receipt, adjustments, sales, etc.)
        self.transactions_col = self.db.collection('inventory_transactions')

    def _get_doc_id(self, sku: str, branch_id: str):
        return f"{sku.upper()}_{branch_id}"

    def _clear_inventory_caches(self, branch_id: str, sku: str = None):
        # Clear caches more granularly if possible
        self.get_inventory_by_branch.clear()
        if sku and branch_id:
            self.get_stock_quantity.clear(self, sku, branch_id)
            self.get_inventory_item.clear(self, sku, branch_id)
        else:
            self.get_stock_quantity.clear()
            self.get_inventory_item.clear()

    def get_inventory_item(self, sku: str, branch_id: str):
        """Fetches a single inventory item document."""
        if not sku or not branch_id: return None
        try:
            doc_ref = self.inventory_col.document(self._get_doc_id(sku, branch_id))
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logging.error(f"Error getting inventory item {sku}@{branch_id}: {e}")
            return None

    @firestore.transactional
    def _record_transaction_and_update_inventory(self, transaction, sku, branch_id, delta, user_id, reason, notes="", purchase_price=None):
        """A transactional function to log a transaction and update inventory state, including weighted average cost."""
        inv_doc_ref = self.inventory_col.document(self._get_doc_id(sku, branch_id))
        inv_snapshot = inv_doc_ref.get(transaction=transaction)
        
        current_quantity = 0
        current_avg_cost = 0
        if inv_snapshot.exists:
            inv_data = inv_snapshot.to_dict()
            current_quantity = inv_data.get('stock_quantity', 0)
            current_avg_cost = inv_data.get('average_cost', 0)

        new_quantity = current_quantity + delta
        new_avg_cost = current_avg_cost

        # --- Weighted Average Cost Calculation ---
        if delta > 0 and purchase_price is not None and purchase_price >= 0:
            # This is a purchase or positive adjustment with a specified cost
            current_total_value = current_quantity * current_avg_cost
            adjustment_value = delta * purchase_price
            if new_quantity > 0:
                new_avg_cost = (current_total_value + adjustment_value) / new_quantity
            else:
                new_avg_cost = 0 # Reset if stock is zero
        elif delta < 0:
            # For sales, transfers, or negative adjustments, the average cost does not change.
            # The value of the outgoing stock is based on the current average cost.
            pass # new_avg_cost is already set to current_avg_cost

        if new_quantity < 0:
            raise Exception(f"Tồn kho không đủ cho sản phẩm {sku}. Giao dịch thất bại.")

        # 1. Update Inventory Document
        transaction.set(inv_doc_ref, {
            'sku': sku,
            'branch_id': branch_id,
            'stock_quantity': new_quantity,
            'average_cost': new_avg_cost, # NEW: Store the calculated average cost
            'last_updated': datetime.now().isoformat(),
        }, merge=True)

        # 2. Record the transaction
        trans_id = f"TRANS-{uuid.uuid4().hex[:10].upper()}"
        trans_ref = self.transactions_col.document(trans_id)
        transaction.set(trans_ref, {
            'id': trans_id,
            'sku': sku,
            'branch_id': branch_id,
            'user_id': user_id,
            'reason': reason, # e.g., 'GOODS_RECEIPT', 'SALE', 'ADJUSTMENT'
            'delta': delta,
            'quantity_before': current_quantity,
            'quantity_after': new_quantity,
            'cost_at_transaction': new_avg_cost, # Cost of inventory *after* this transaction
            'purchase_price': purchase_price, # The price for this specific transaction (if any)
            'notes': notes,
            'timestamp': datetime.now().isoformat(),
        })

    def receive_stock(self, sku, branch_id, quantity, purchase_price, user_id, supplier="", notes=""):
        """Handles receiving stock (goods receipt), updating quantity and average cost."""
        if quantity <= 0:
            raise ValueError("Số lượng nhập phải lớn hơn 0.")
        
        full_notes = f"Nhà cung cấp: {supplier or 'N/A'}. Ghi chú: {notes or 'Không có'}."
        transaction = self.db.transaction()
        self._record_transaction_and_update_inventory(
            transaction=transaction,
            sku=sku,
            branch_id=branch_id,
            delta=quantity,
            user_id=user_id,
            reason="GOODS_RECEIPT",
            purchase_price=purchase_price,
            notes=full_notes
        )
        self._clear_inventory_caches(branch_id, sku)
        self.get_inventory_transactions.clear()

    def adjust_stock(self, sku, branch_id, new_quantity, user_id, reason, notes):
        """Handles manual stock adjustments. The cost of adjustment is based on current average cost."""
        item = self.get_inventory_item(sku, branch_id)
        current_quantity = item.get('stock_quantity', 0) if item else 0
        delta = new_quantity - current_quantity
        
        if delta == 0: 
            return # No change needed

        transaction = self.db.transaction()
        self._record_transaction_and_update_inventory(
            transaction=transaction,
            sku=sku, 
            branch_id=branch_id, 
            delta=delta,
            user_id=user_id, 
            reason=f"ADJUSTMENT_{reason.upper()SERIALIZED}",
            notes=notes
            # purchase_price is None, so avg cost won't be recalculated based on a new price
        )
        self._clear_inventory_caches(branch_id, sku)
        self.get_inventory_transactions.clear()
    
    def get_stock_quantity(self, sku: str, branch_id: str) -> int:
        item = self.get_inventory_item(sku, branch_id)
        return item.get('stock_quantity', 0) if item else 0

    def get_inventory_by_branch(self, branch_id: str) -> dict:
        try:
            if not branch_id: return {}
            docs = self.inventory_col.where('branch_id', '==', branch_id).stream()
            return {doc.to_dict()['sku']: doc.to_dict() for doc in docs if 'sku' in doc.to_dict()}
        except Exception as e:
            logging.error(f"Error fetching inventory for branch '{branch_id}': {e}")
            return {}

    def get_inventory_transactions(self, branch_id: str, limit: int = 200):
        try:
            if not branch_id: return []
            query = self.transactions_col.where('branch_id', '==', branch_id).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
            return [doc.to_dict() for doc in query.stream()]
        except Exception as e:
            logging.error(f"Lỗi khi lấy lịch sử giao dịch kho cho chi nhánh '{branch_id}': {e}")
            return []

    def create_transfer(self, from_branch_id, to_branch_id, items, user_id, notes=""):
        if not all([from_branch_id, to_branch_id, items]):
            raise ValueError("Thiếu thông tin chi nhánh hoặc sản phẩm.")
        transfer_id = f"TRF-{uuid.uuid4().hex[:10].upper()}"
        # ... (transfer logic remains the same, but will eventually use the new transaction model)
        self.transfers_col.document(transfer_id).set({
            "id": transfer_id, "from_branch_id": from_branch_id, "to_branch_id": to_branch_id,
            "items": items, "created_by": user_id, "created_at": datetime.now().isoformat(),
            "status": "PENDING", "history": [{"status": "PENDING", "updated_at": datetime.now().isoformat(), "user_id": user_id}],
            "notes": notes
        })
        self.get_transfers.clear()
        return transfer_id

    # ... other transfer methods (ship, receive) need to be updated to use the new transaction model
    # This is a larger change, for now we focus on getting GOODS_RECEIPT right.
    def ship_transfer(self, transfer_id, user_id):
        pass # TODO: Refactor to use _record_transaction_and_update_inventory

    def receive_transfer(self, transfer_id, user_id):
        pass # TODO: Refactor to use _record_transaction_and_update_inventory

    def get_transfers(self, branch_id: str = None, direction: str = 'all', status: str = None, limit=100):
        # This function can remain as is for now.
        pass

# Apply decorators after the class is defined
InventoryManager.get_inventory_item = st.cache_data(ttl=60, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_inventory_item)
InventoryManager.get_stock_quantity = st.cache_data(ttl=60, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_stock_quantity)
InventoryManager.get_inventory_by_branch = st.cache_data(ttl=60, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_inventory_by_branch)
InventoryManager.get_inventory_transactions = st.cache_data(ttl=120, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_inventory_transactions)
InventoryManager.get_transfers = st.cache_data(ttl=30, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_transfers)
