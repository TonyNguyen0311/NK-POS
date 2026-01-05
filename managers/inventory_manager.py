
import uuid
import logging
from google.cloud import firestore
from datetime import datetime

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.inventory_col = self.db.collection('inventory')
        self.transfers_col = self.db.collection('stock_transfers')
        self.adjustments_col = self.db.collection('inventory_adjustments')

    def _get_doc_id(self, sku: str, branch_id: str):
        return f"{sku.upper()}_{branch_id}"

    def update_inventory(self, sku: str, branch_id: str, delta: int, transaction: firestore.Transaction):
        inv_doc_ref = self.inventory_col.document(self._get_doc_id(sku, branch_id))
        transaction.set(inv_doc_ref, {
            'stock_quantity': firestore.FieldValue.increment(delta),
            'last_updated': datetime.now().isoformat(),
            'sku': sku, 
            'branch_id': branch_id
        }, merge=True)

    @firestore.transactional
    def _adjust_stock_transaction(self, transaction, sku, branch_id, new_quantity, user_id, reason, notes):
        doc_id = self._get_doc_id(sku, branch_id)
        inv_ref = self.inventory_col.document(doc_id)
        inv_snapshot = inv_ref.get(transaction=transaction)
        current_quantity = inv_snapshot.to_dict().get('stock_quantity', 0) if inv_snapshot.exists else 0
        delta = new_quantity - current_quantity
        if delta == 0: return

        self.update_inventory(sku, branch_id, delta, transaction)
        adj_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
        adj_ref = self.adjustments_col.document(adj_id)
        transaction.set(adj_ref, {
            "id": adj_id, "sku": sku, "branch_id": branch_id, "user_id": user_id,
            "timestamp": datetime.now().isoformat(), "quantity_before": current_quantity,
            "quantity_after": new_quantity, "delta": delta, "reason": reason, "notes": notes
        })

    def adjust_stock(self, sku, branch_id, new_quantity, user_id, reason, notes):
        transaction = self.db.transaction()
        self._adjust_stock_transaction(transaction, sku, branch_id, new_quantity, user_id, reason, notes)

    def get_stock_quantity(self, sku: str, branch_id: str) -> int:
        try:
            if not branch_id or not sku: return 0
            doc = self.inventory_col.document(self._get_doc_id(sku, branch_id)).get()
            return doc.to_dict().get('stock_quantity', 0) if doc.exists else 0
        except Exception as e:
            logging.error(f"Error getting stock for {sku}@{branch_id}: {e}")
            return 0

    def get_inventory_by_branch(self, branch_id: str) -> dict:
        try:
            if not branch_id: return {}
            docs = self.inventory_col.where('branch_id', '==', branch_id).stream()
            return {doc.to_dict()['sku']: doc.to_dict() for doc in docs if 'sku' in doc.to_dict()}
        except Exception as e:
            logging.error(f"Error fetching inventory for branch '{branch_id}': {e}")
            return {}
    
    def get_inventory_adjustments_history(self, branch_id: str, limit: int = 200):
        """
        Lấy lịch sử điều chỉnh kho cho một chi nhánh cụ thể.
        Sắp xếp được thực hiện ở phía server-side (Python) để tránh lỗi index của Firestore.
        """
        try:
            if not branch_id:
                return []
            query = self.adjustments_col.where('branch_id', '==', branch_id).limit(limit)
            docs = query.stream()
            results = [doc.to_dict() for doc in docs]
            results.sort(key=lambda x: x.get('timestamp', '1970-01-01T00:00:00.000000'), reverse=True)
            return results
        except Exception as e:
            logging.error(f"Lỗi khi lấy lịch sử điều chỉnh kho cho chi nhánh '{branch_id}': {e}")
            return []

    def create_transfer(self, from_branch_id, to_branch_id, items, user_id, notes=""):
        if not all([from_branch_id, to_branch_id, items]):
            raise ValueError("Thiếu thông tin chi nhánh hoặc sản phẩm.")

        transfer_id = f"TRF-{uuid.uuid4().hex[:10].upper()}"
        self.transfers_col.document(transfer_id).set({
            "id": transfer_id, "from_branch_id": from_branch_id, "to_branch_id": to_branch_id,
            "items": items, "created_by": user_id, "created_at": datetime.now().isoformat(),
            "status": "PENDING", "history": [{"status": "PENDING", "updated_at": datetime.now().isoformat(), "user_id": user_id}],
            "notes": notes
        })
        return transfer_id

    def _update_transfer_status(self, transaction, transfer_ref, new_status, user_id, update_data={}):
        payload = {"status": new_status, "history": firestore.ArrayUnion([{"status": new_status, "updated_at": datetime.now().isoformat(), "user_id": user_id}])}
        payload.update(update_data)
        transaction.update(transfer_ref, payload)

    @firestore.transactional
    def _ship_transfer_transaction(self, transaction, transfer_id, user_id):
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get(transaction=transaction).to_dict()
        if transfer_doc.get('status') != 'PENDING': raise Exception("Phiếu không ở trạng thái PENDING.")

        from_branch = transfer_doc['from_branch_id']
        for item in transfer_doc['items']:
            if self.get_stock_quantity(item['sku'], from_branch) < item['quantity']: raise Exception(f"Tồn kho {item['sku']} không đủ.")
            self.update_inventory(item['sku'], from_branch, -item['quantity'], transaction)
        self._update_transfer_status(transaction, transfer_ref, "SHIPPED", user_id, {"shipped_at": datetime.now().isoformat(), "shipped_by": user_id})

    def ship_transfer(self, transfer_id, user_id):
        self._ship_transfer_transaction(self.db.transaction(), transfer_id, user_id)

    @firestore.transactional
    def _receive_transfer_transaction(self, transaction, transfer_id, user_id):
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get(transaction=transaction).to_dict()
        if transfer_doc.get('status') != 'SHIPPED': raise Exception("Phiếu không ở trạng thái SHIPPED.")

        to_branch = transfer_doc['to_branch_id']
        for item in transfer_doc['items']:
            self.update_inventory(item['sku'], to_branch, item['quantity'], transaction)
        self._update_transfer_status(transaction, transfer_ref, "COMPLETED", user_id, {"completed_at": datetime.now().isoformat(), "completed_by": user_id})
        
    def receive_transfer(self, transfer_id, user_id):
        self._receive_transfer_transaction(self.db.transaction(), transfer_id, user_id)

    def get_transfers(self, branch_id: str = None, direction: str = 'all', status: str = None, limit=100):
        if not branch_id:
            query = self.transfers_col
            if status:
                query = query.where('status', '==', status)
            # Sắp xếp ở client-side nếu không có index
            results = [doc.to_dict() for doc in query.limit(limit).stream()]
            results.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return results

        results = []
        transfer_ids = set()

        queries_to_run = []
        if direction in ['outgoing', 'all']:
            q_out = self.transfers_col.where('from_branch_id', '==', branch_id)
            if status:
                q_out = q_out.where('status', '==', status)
            queries_to_run.append(q_out)
        
        if direction in ['incoming', 'all']:
            q_in = self.transfers_col.where('to_branch_id', '==', branch_id)
            if status:
                q_in = q_in.where('status', '==', status)
            queries_to_run.append(q_in)

        for query in queries_to_run:
            try:
                docs = query.limit(limit).stream()
                for doc in docs:
                    if doc.id not in transfer_ids:
                        results.append(doc.to_dict())
                        transfer_ids.add(doc.id)
            except Exception as e:
                logging.error(f"Firestore query failed: {e}. This might be due to a missing index.")
                # Optionally, re-raise or handle more gracefully
                raise e

        # Sắp xếp kết quả cuối cùng bằng Python
        results.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return results[:limit]
