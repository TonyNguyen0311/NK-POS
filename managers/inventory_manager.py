
import uuid
from google.cloud import firestore
from datetime import datetime

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        # --- Collections ---
        self.inventory_col = self.db.collection('inventory')
        self.transfers_col = self.db.collection('goods_transfers')
        self.adjustments_col = self.db.collection('stock_adjustments')
        self.stock_takes_col = self.db.collection('stock_takes')

    # --------------------------------------------------------------------------
    # SECTION 1: CORE INVENTORY OPERATIONS (HÀM LÕI)
    # --------------------------------------------------------------------------

    def _get_doc_id(self, sku: str, branch_id: str):
        return f"{sku}_{branch_id}"

    def get_stock(self, sku: str, branch_id: str):
        doc_id = self._get_doc_id(sku, branch_id)
        doc = self.inventory_col.document(doc_id).get()
        if doc.exists:
            return doc.to_dict().get('stock_quantity', 0)
        return 0

    def update_inventory(self, sku: str, branch_id: str, delta: int, transaction=None):
        doc_id = self._get_doc_id(sku, branch_id)
        doc_ref = self.inventory_col.document(doc_id)
        update_data = {
            'stock_quantity': firestore.FieldValue.increment(delta),
            'last_updated': datetime.now().isoformat(),
            'sku': sku, 
            'branch_id': branch_id
        }
        if transaction:
            transaction.set(doc_ref, update_data, merge=True)
        else:
            doc_ref.set(update_data, merge=True)

    def get_inventory_by_branch(self, branch_id: str):
        docs = self.inventory_col.where('branch_id', '==', branch_id).stream()
        return {doc.to_dict()['sku']: doc.to_dict() for doc in docs}

    # --------------------------------------------------------------------------
    # SECTION 2: GOODS TRANSFER (LUÂN CHUYỂN KHO)
    # --------------------------------------------------------------------------

    def create_transfer(self, from_branch_id, to_branch_id, items, user_id):
        transfer_id = f"TFR-{uuid.uuid4().hex[:8].upper()}"
        data = {
            "id": transfer_id,
            "from_branch_id": from_branch_id,
            "to_branch_id": to_branch_id,
            "items": items, # list of {'sku': str, 'quantity': int}
            "status": "DRAFT", # DRAFT -> DISPATCHED -> COMPLETED / CANCELLED
            "created_by": user_id,
            "created_at": datetime.now().isoformat(),
        }
        self.transfers_col.document(transfer_id).set(data)
        return data

    @firestore.transactional
    def dispatch_transfer(self, transaction, transfer_id, user_id):
        transfer_ref = self.transfers_col.document(transfer_id)
        snapshot = transfer_ref.get(transaction=transaction).to_dict()

        if snapshot['status'] != 'DRAFT':
            raise Exception("Chỉ có thể gửi hàng từ phiếu nháp (DRAFT).")

        # Trừ tồn kho từ chi nhánh gửi
        for item in snapshot['items']:
            self.update_inventory(item['sku'], snapshot['from_branch_id'], -item['quantity'], transaction)
        
        # Cập nhật trạng thái phiếu
        transaction.update(transfer_ref, {
            "status": "DISPATCHED",
            "dispatched_by": user_id,
            "dispatched_at": datetime.now().isoformat()
        })

    @firestore.transactional
    def receive_transfer(self, transaction, transfer_id, user_id):
        transfer_ref = self.transfers_col.document(transfer_id)
        snapshot = transfer_ref.get(transaction=transaction).to_dict()

        if snapshot['status'] != 'DISPATCHED':
            raise Exception("Chỉ có thể nhận hàng từ phiếu đã gửi (DISPATCHED).")

        # Cộng tồn kho cho chi nhánh nhận
        for item in snapshot['items']:
            self.update_inventory(item['sku'], snapshot['to_branch_id'], item['quantity'], transaction)

        # Cập nhật trạng thái phiếu
        transaction.update(transfer_ref, {
            "status": "COMPLETED",
            "received_by": user_id,
            "received_at": datetime.now().isoformat()
        })

    def get_transfers(self, branch_id=None):
        query = self.transfers_col
        # TODO: Lọc theo from_branch hoặc to_branch nếu cần
        return [doc.to_dict() for doc in query.order_by("created_at", direction=Query.DESCENDING).stream()]


    # --------------------------------------------------------------------------
    # SECTION 3: STOCK ADJUSTMENT (NHẬP/XUẤT TRỰC TIẾP)
    # --------------------------------------------------------------------------

    @firestore.transactional
    def create_adjustment(self, transaction, branch_id, adj_type, items, reason, user_id):
        adjustment_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
        delta_multiplier = 1 if adj_type == 'STOCK_IN' else -1

        # Cập nhật tồn kho
        for item in items:
            delta = item['quantity'] * delta_multiplier
            self.update_inventory(item['sku'], branch_id, delta, transaction)
        
        # Lưu lại phiếu điều chỉnh
        adj_ref = self.adjustments_col.document(adjustment_id)
        data = {
            "id": adjustment_id,
            "branch_id": branch_id,
            "type": adj_type, # STOCK_IN, STOCK_OUT
            "items": items, # list of {'sku': str, 'quantity': int, 'cost_price': float}
            "reason": reason,
            "created_by": user_id,
            "created_at": datetime.now().isoformat()
        }
        transaction.set(adj_ref, data)

    # --------------------------------------------------------------------------
    # SECTION 4: STOCK TAKE (KIỂM KÊ)
    # --------------------------------------------------------------------------

    def start_stock_take_session(self, branch_id, user_id):
        session_id = f"STK-{branch_id}-{datetime.now().strftime('%Y%m%d')}"
        
        # Chụp lại tồn kho hệ thống tại thời điểm bắt đầu
        inventory_snapshot = self.get_inventory_by_branch(branch_id)
        snapshot_items = [
            {'sku': sku, 'system_qty': data.get('stock_quantity', 0)}
            for sku, data in inventory_snapshot.items()
        ]

        data = {
            "id": session_id,
            "branch_id": branch_id,
            "status": "IN_PROGRESS", # IN_PROGRESS -> COMPLETED
            "snapshot_items": snapshot_items, # Tồn kho hệ thống lúc bắt đầu
            "counted_items": [], # Tồn kho thực tế, sẽ được cập nhật dần
            "started_by": user_id,
            "started_at": datetime.now().isoformat()
        }
        self.stock_takes_col.document(session_id).set(data)
        return data
    
    def update_counted_items(self, session_id, counted_items):
        self.stock_takes_col.document(session_id).update({"counted_items": counted_items})

    def finalize_stock_take(self, session_id, user_id):
        session_doc = self.stock_takes_col.document(session_id).get().to_dict()
        if session_doc['status'] != 'IN_PROGRESS':
            raise Exception("Phiên kiểm kê này đã được hoàn thành.")

        # Tạo bảng so sánh
        system_qtys = {item['sku']: item['system_qty'] for item in session_doc['snapshot_items']}
        counted_qtys = {item['sku']: item['counted_qty'] for item in session_doc['counted_items']}
        all_skus = set(system_qtys.keys()) | set(counted_qtys.keys())

        discrepancy_items = []
        for sku in all_skus:
            system_qty = system_qtys.get(sku, 0)
            counted_qty = counted_qtys.get(sku, 0)
            if system_qty != counted_qty:
                discrepancy_items.append({
                    'sku': sku,
                    'quantity': counted_qty, # Số lượng thực tế cuối cùng
                    'system_qty': system_qty
                })

        # Nếu có chênh lệch, tạo phiếu điều chỉnh và cập nhật kho
        if discrepancy_items:
            transaction = self.db.transaction()
            @firestore.transactional
            def _adjust_inventory(transaction, branch_id, items, reason, user):
                # Đây là một logic phức tạp: set lại tồn kho về đúng giá trị thực tế
                for item in items:
                    current_stock = self.get_stock(item['sku'], branch_id)
                    delta = item['quantity'] - current_stock
                    if delta != 0:
                        self.update_inventory(item['sku'], branch_id, delta, transaction)
                # Tạo phiếu điều chỉnh để ghi log
                # ... (có thể gọi lại hàm create_adjustment)

            reason = f"Điều chỉnh sau kiểm kê phiên {session_id}"
            _adjust_inventory(transaction, session_doc['branch_id'], discrepancy_items, reason, user_id)

        # Đóng phiên kiểm kê
        self.stock_takes_col.document(session_id).update({
            "status": "COMPLETED",
            "completed_by": user_id,
            "completed_at": datetime.now().isoformat(),
            "discrepancy_summary": discrepancy_items
        })
        return True
