
import uuid
import logging
import streamlit as st
from google.cloud import firestore
from datetime import datetime, time


@firestore.transactional
def _create_voucher_and_transactions_transactional(transaction, db, voucher_ref, voucher_data, items):
    """
    Transactional function to create a voucher and all its related inventory transactions.
    This ensures all inventory operations are performed atomically with the voucher creation.
    """
    inventory_col = db.collection('inventory')
    transactions_col = db.collection('inventory_transactions')
    processed_transaction_ids = []

    # 1. Create the main voucher document
    transaction.set(voucher_ref, voucher_data)

    # 2. Process each item in the voucher
    for item in items:
        sku = item['sku']
        delta = item['quantity']
        purchase_price = item.get('purchase_price') # Will be None for adjustments

        inv_doc_ref = inventory_col.document(f"{sku.upper()}_{voucher_data['branch_id']}")
        inv_snapshot = inv_doc_ref.get(transaction=transaction)

        current_quantity = 0
        current_avg_cost = 0
        if inv_snapshot.exists:
            inv_data = inv_snapshot.to_dict()
            current_quantity = inv_data.get('stock_quantity', 0)
            current_avg_cost = inv_data.get('average_cost', 0)

        new_quantity = current_quantity + delta
        new_avg_cost = current_avg_cost

        # Recalculate average cost only on positive delta (receiving stock)
        if delta > 0 and purchase_price is not None and purchase_price >= 0:
            current_total_value = current_quantity * current_avg_cost
            adjustment_value = delta * purchase_price
            new_avg_cost = (current_total_value + adjustment_value) / new_quantity if new_quantity > 0 else 0
        # For negative delta (cancellations/adjustments), the cost basis doesn't change from new purchases
        
        if new_quantity < 0:
            raise ValueError(f"Tồn kho không đủ cho sản phẩm {sku}. Giao dịch thất bại.")

        # Update inventory document (SKU + Branch)
        transaction.set(inv_doc_ref, {
            'sku': sku,
            'branch_id': voucher_data['branch_id'],
            'stock_quantity': new_quantity,
            'average_cost': new_avg_cost,
            'last_updated': voucher_data['created_at'],
        }, merge=True)

        # Create the individual inventory transaction log
        trans_id = f"TRANS-{uuid.uuid4().hex[:10].upper()}"
        trans_ref = transactions_col.document(trans_id)
        transaction.set(trans_ref, {
            'id': trans_id,
            'voucher_id': voucher_ref.id,
            'sku': sku,
            'branch_id': voucher_data['branch_id'],
            'user_id': voucher_data['created_by'],
            'reason': voucher_data['type'], # e.g., GOODS_RECEIPT, ADJUSTMENT
            'delta': delta,
            'quantity_before': current_quantity,
            'quantity_after': new_quantity,
            'cost_at_transaction': new_avg_cost,
            'purchase_price': purchase_price,
            'notes': voucher_data.get('notes', ''),
            'timestamp': voucher_data['created_at'],
        })
        processed_transaction_ids.append(trans_id)
    
    # 3. Update the voucher with the IDs of the transactions it created
    transaction.update(voucher_ref, {'transaction_ids': processed_transaction_ids})

def hash_inventory_manager(manager):
    return "InventoryManager"

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.vouchers_col = self.db.collection('inventory_vouchers')
        self.inventory_col = self.db.collection('inventory')
        self.transactions_col = self.db.collection('inventory_transactions')

    def _clear_caches(self, branch_id: str):
        st.cache_data.clear() # Clear all caches for simplicity

    def create_goods_receipt(self, branch_id, user_id, items, supplier, notes, receipt_date):
        if not items:
            raise ValueError("Phiếu nhập phải có ít nhất một sản phẩm.")
        
        voucher_id = f"VGR-{uuid.uuid4().hex[:10].upper()}"
        voucher_ref = self.vouchers_col.document(voucher_id)
        
        created_at = datetime.combine(receipt_date, datetime.now().time()).isoformat()

        voucher_data = {
            'id': voucher_id,
            'branch_id': branch_id,
            'created_by': user_id,
            'type': 'GOODS_RECEIPT',
            'status': 'COMPLETED',
            'created_at': created_at,
            'notes': notes,
            'supplier': supplier,
            'items': items # Store items for display purposes
        }

        transaction = self.db.transaction()
        _create_voucher_and_transactions_transactional(transaction, self.db, voucher_ref, voucher_data, items)
        self._clear_caches(branch_id)
        return voucher_id

    def create_adjustment(self, branch_id, user_id, items, reason, notes, adjustment_date):
        if not items:
            raise ValueError("Phiếu điều chỉnh phải có ít nhất một sản phẩm.")

        voucher_id = f"VADJ-{uuid.uuid4().hex[:10].upper()}"
        voucher_ref = self.vouchers_col.document(voucher_id)
        created_at = datetime.combine(adjustment_date, datetime.now().time()).isoformat()

        # Prepare items with delta calculation
        items_with_delta = []
        for item in items:
            current_item_state = self.get_inventory_item(item['sku'], branch_id)
            current_quantity = current_item_state.get('stock_quantity', 0) if current_item_state else 0
            delta = item['actual_quantity'] - current_quantity
            if delta != 0:
                items_with_delta.append({
                    'sku': item['sku'],
                    'quantity': delta, # This is the 'delta', not the final quantity
                    'actual_quantity': item['actual_quantity'],
                    'quantity_before': current_quantity
                })
        
        if not items_with_delta:
            logging.warning("No actual change in stock quantities for adjustment.")
            return None

        voucher_data = {
            'id': voucher_id,
            'branch_id': branch_id,
            'created_by': user_id,
            'type': f'ADJUSTMENT_{reason.upper()}',
            'status': 'COMPLETED',
            'created_at': created_at,
            'notes': notes,
            'reason': reason,
            'items': items_with_delta 
        }

        transaction = self.db.transaction()
        _create_voucher_and_transactions_transactional(transaction, self.db, voucher_ref, voucher_data, items_with_delta)
        self._clear_caches(branch_id)
        return voucher_id

    def cancel_voucher(self, voucher_id: str, user_id: str):
        original_voucher_ref = self.vouchers_col.document(voucher_id)
        original_voucher = original_voucher_ref.get()

        if not original_voucher.exists:
            raise FileNotFoundError("Không tìm thấy chứng từ gốc.")
        
        voucher_dict = original_voucher.to_dict()
        if voucher_dict.get('status') == 'CANCELLED':
            raise ValueError("Chứng từ này đã bị huỷ trước đó.")

        # Create reversal items
        reversal_items = []
        for item in voucher_dict['items']:
            reversal_items.append({
                'sku': item['sku'],
                'quantity': -item['quantity'], # Reverse the delta
                'purchase_price': item.get('purchase_price') # Keep original price for cost calculation reversal
            })
        
        # Create the cancellation voucher
        cancellation_voucher_id = f"VCAN-{uuid.uuid4().hex[:10].upper()}"
        cancellation_voucher_ref = self.vouchers_col.document(cancellation_voucher_id)
        created_at = datetime.now().isoformat()
        
        cancellation_voucher_data = {
            'id': cancellation_voucher_id,
            'branch_id': voucher_dict['branch_id'],
            'created_by': user_id,
            'type': f"REVERSAL_{voucher_dict['type']}",
            'status': 'COMPLETED',
            'created_at': created_at,
            'notes': f"Huỷ chứng từ {voucher_id}.",
            'items': reversal_items,
            'reverses_voucher_id': voucher_id
        }
        
        # Use the same transactional function to process the reversal
        transaction = self.db.transaction()
        _create_voucher_and_transactions_transactional(transaction, self.db, cancellation_voucher_ref, cancellation_voucher_data, reversal_items)

        # Mark the original voucher as cancelled
        original_voucher_ref.update({'status': 'CANCELLED', 'cancelled_by': user_id, 'cancelled_at': created_at})

        self._clear_caches(voucher_dict['branch_id'])
        return cancellation_voucher_id

    def get_inventory_item(self, sku: str, branch_id: str):
        if not sku or not branch_id: return None
        doc_ref = self.inventory_col.document(f"{sku.upper()}_{branch_id}")
        doc = doc_ref.get()
        return doc.to_dict() if doc.exists else None

    def get_vouchers_by_branch(self, branch_id: str, limit: int = 100):
        if not branch_id: return []
        query = self.vouchers_col.where('branch_id', '==', branch_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
        return [doc.to_dict() for doc in query.stream()]

# Caching for performance
InventoryManager.get_inventory_item = st.cache_data(ttl=60, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_inventory_item)
InventoryManager.get_vouchers_by_branch = st.cache_data(ttl=120, hash_funcs={InventoryManager: hash_inventory_manager})(InventoryManager.get_vouchers_by_branch)
