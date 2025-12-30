
import uuid
from google.cloud import firestore
from datetime import datetime

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        # --- Collections ---
        self.inventory_col = self.db.collection('inventory')
        self.transfers_col = self.db.collection('stock_transfers')
        # Collection để ghi lại lịch sử mỗi lần thay đổi tồn kho
        self.adjustments_col = self.db.collection('inventory_adjustments')

    def _get_doc_id(self, sku: str, branch_id: str):
        return f"{sku.upper()}_{branch_id}"

    # --------------------------------------------------------------------------
    # SECTION 1: CÁC HÀM CẬP NHẬT TỒN KHO CHÍNH
    # --------------------------------------------------------------------------

    def update_inventory(self, sku: str, branch_id: str, delta: int, transaction: firestore.Transaction):
        """
        Hàm lõi, nhận transaction để cập nhật tồn kho. 
        Delta có thể là số dương (nhập hàng) hoặc âm (bán hàng, hủy hàng).
        Đây là hàm private vì nó yêu cầu một transaction bên ngoài.
        """
        inv_doc_ref = self.inventory_col.document(self._get_doc_id(sku, branch_id))
        transaction.set(inv_doc_ref, {
            'stock_quantity': firestore.FieldValue.increment(delta),
            'last_updated': datetime.now().isoformat(),
            'sku': sku, 
            'branch_id': branch_id
        }, merge=True)

    @firestore.transactional
    def _adjust_stock_transaction(self, transaction, sku, branch_id, new_quantity, user_id, reason, notes):
        """
        Transaction cho việc điều chỉnh tồn kho (không phải nhập/xuất/bán).
        Ví dụ: Kiểm kê thấy sai, hàng hỏng...
        """
        doc_id = self._get_doc_id(sku, branch_id)
        inv_ref = self.inventory_col.document(doc_id)
        inv_snapshot = inv_ref.get(transaction=transaction)

        current_quantity = 0
        if inv_snapshot.exists:
            current_quantity = inv_snapshot.to_dict().get('stock_quantity', 0)
        
        delta = new_quantity - current_quantity

        if delta == 0:
            return # Không có gì thay đổi

        # 1. Cập nhật tồn kho hiện tại
        self.update_inventory(sku, branch_id, delta, transaction)

        # 2. Ghi lại lịch sử điều chỉnh
        adj_id = f"ADJ-{uuid.uuid4().hex[:8].upper()}"
        adj_ref = self.adjustments_col.document(adj_id)
        transaction.set(adj_ref, {
            "id": adj_id,
            "sku": sku,
            "branch_id": branch_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "quantity_before": current_quantity,
            "quantity_after": new_quantity,
            "delta": delta,
            "reason": reason, # Ví dụ: 'STOCK_TAKE', 'DAMAGED_GOODS', 'MANUAL_CORRECTION'
            "notes": notes
        })

    @firestore.transactional
    def _receive_stock_transaction(self, transaction, sku, branch_id, quantity, user_id, notes, cost_price, supplier):
        """
        Transaction cho việc nhập hàng từ nhà cung cấp.
        """
        if quantity <= 0:
            raise ValueError("Số lượng nhập phải lớn hơn 0.")

        current_quantity = 0
        inv_ref = self.inventory_col.document(self._get_doc_id(sku, branch_id))
        inv_snapshot = inv_ref.get(transaction=transaction)
        if inv_snapshot.exists:
            current_quantity = inv_snapshot.to_dict().get('stock_quantity', 0)

        # 1. Cập nhật tồn kho (tăng lên)
        self.update_inventory(sku, branch_id, quantity, transaction)

        # 2. Ghi lại lịch sử nhập hàng
        adj_id = f"GRN-{uuid.uuid4().hex[:8].upper()}" # Goods Received Note
        adj_ref = self.adjustments_col.document(adj_id)
        transaction.set(adj_ref, {
            "id": adj_id,
            "sku": sku,
            "branch_id": branch_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "quantity_before": current_quantity,
            "quantity_after": current_quantity + quantity,
            "delta": quantity,
            "reason": "GOODS_RECEIVED",
            "notes": notes,
            "cost_price_per_unit": cost_price, 
            "total_cost": cost_price * quantity,
            "supplier": supplier
        })

    def adjust_stock(self, sku, branch_id, new_quantity, user_id, reason, notes):
        """Hàm public để gọi transaction điều chỉnh kho."""
        transaction = self.db.transaction()
        self._adjust_stock_transaction(transaction, sku, branch_id, new_quantity, user_id, reason, notes)

    def receive_stock(self, sku, branch_id, quantity, user_id, cost_price, supplier, notes=""):
        """Hàm public để gọi transaction nhập hàng."""
        transaction = self.db.transaction()
        self._receive_stock_transaction(transaction, sku, branch_id, quantity, user_id, notes, cost_price, supplier)

    # --------------------------------------------------------------------------
    # SECTION 2: CÁC HÀM TRUY VẤN
    # --------------------------------------------------------------------------
    def get_stock_quantity(self, sku: str, branch_id: str) -> int:
        """Lấy số lượng tồn kho thực tế của một sản phẩm tại một chi nhánh."""
        doc_id = self._get_doc_id(sku, branch_id)
        doc = self.inventory_col.document(doc_id).get()
        if doc.exists:
            return doc.to_dict().get('stock_quantity', 0)
        return 0

    def get_inventory_by_branch(self, branch_id: str) -> dict:
        """Lấy toàn bộ thông tin tồn kho của một chi nhánh, trả về dict với key là SKU."""
        docs = self.inventory_col.where('branch_id', '==', branch_id).stream()
        inventory_data = {}
        for doc in docs:
            data = doc.to_dict()
            data['low_stock_threshold'] = data.get('low_stock_threshold', 10) 
            inventory_data[data['sku']] = data
        return inventory_data
        
    def get_inventory_adjustments_history(self, sku: str = None, branch_id: str = None, start_date=None, end_date=None, limit=50):
        """Lấy lịch sử các lần thay đổi tồn kho."""
        query = self.adjustments_col
        if sku:
            query = query.where("sku", "==", sku)
        if branch_id:
            query = query.where("branch_id", "==", branch_id)
        if start_date:
            query = query.where("timestamp", ">=", start_date.isoformat())
        if end_date:
            query = query.where("timestamp", "<=", end_date.isoformat())
            
        return [doc.to_dict() for doc in query.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()]

    # --------------------------------------------------------------------------
    # SECTION 3: QUẢN LÝ LUÂN CHUYỂN HÀNG HÓA (STOCK TRANSFER)
    # --------------------------------------------------------------------------
    def create_transfer(self, from_branch_id, to_branch_id, items, user_id, notes=""):
        """
        Tạo một phiếu yêu cầu luân chuyển hàng hóa.
        items: list of dicts, mỗi dict chứa {'sku': str, 'quantity': int}
        """
        transfer_id = f"TRF-{uuid.uuid4().hex[:10].upper()}"
        self.transfers_col.document(transfer_id).set({
            "id": transfer_id,
            "from_branch_id": from_branch_id,
            "to_branch_id": to_branch_id,
            "items": items,
            "created_by": user_id,
            "created_at": datetime.now().isoformat(),
            "status": "PENDING",  # PENDING -> SHIPPED -> COMPLETED
            "history": [{
                "status": "PENDING",
                "updated_at": datetime.now().isoformat(),
                "user_id": user_id
            }],
            "notes": notes
        })
        return transfer_id

    @firestore.transactional
    def _ship_transfer_transaction(self, transaction, transfer_id, user_id):
        """
        Transaction để xác nhận gửi hàng đi.
        1. Cập nhật trạng thái phiếu chuyển thành "SHIPPED".
        2. Trừ tồn kho tại chi nhánh gửi.
        3. Ghi log vào inventory_adjustments.
        """
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get(transaction=transaction).to_dict()

        if transfer_doc.get('status') != 'PENDING':
            raise Exception("Chỉ có thể gửi đi các phiếu ở trạng thái PENDING.")

        from_branch = transfer_doc['from_branch_id']
        items = transfer_doc['items']
        
        # Trừ kho và ghi log cho từng sản phẩm
        for item in items:
            sku = item['sku']
            quantity = item['quantity']
            
            # Lấy tồn kho hiện tại
            current_quantity = 0
            inv_ref = self.inventory_col.document(self._get_doc_id(sku, from_branch))
            inv_snapshot = inv_ref.get(transaction=transaction)
            if inv_snapshot.exists:
                current_quantity = inv_snapshot.to_dict().get('stock_quantity', 0)

            if current_quantity < quantity:
                raise Exception(f"Tồn kho sản phẩm {sku} không đủ để thực hiện luân chuyển.")

            # 1. Trừ tồn kho chi nhánh gửi
            self.update_inventory(sku, from_branch, -quantity, transaction)

            # 2. Ghi log
            adj_id = f"STO-{uuid.uuid4().hex[:8].upper()}" # Stock Transfer Out
            adj_ref = self.adjustments_col.document(adj_id)
            transaction.set(adj_ref, {
                "id": adj_id, "sku": sku, "branch_id": from_branch, "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "quantity_before": current_quantity,
                "quantity_after": current_quantity - quantity,
                "delta": -quantity,
                "reason": "STOCK_TRANSFER_OUT",
                "notes": f"Luân chuyển tới chi nhánh {transfer_doc['to_branch_id']} (phiếu {transfer_id})",
                "related_transfer_id": transfer_id
            })

        # 3. Cập nhật trạng thái phiếu chuyển
        transaction.update(transfer_ref, {
            "status": "SHIPPED",
            "shipped_at": datetime.now().isoformat(),
            "shipped_by": user_id,
            "history": firestore.ArrayUnion([{
                "status": "SHIPPED",
                "updated_at": datetime.now().isoformat(),
                "user_id": user_id
            }])
        })

    def ship_transfer(self, transfer_id, user_id):
        """Hàm public để gọi transaction xác nhận gửi hàng."""
        transaction = self.db.transaction()
        self._ship_transfer_transaction(transaction, transfer_id, user_id)

    @firestore.transactional
    def _receive_transfer_transaction(self, transaction, transfer_id, user_id):
        """
        Transaction để xác nhận đã nhận được hàng.
        1. Cập nhật trạng thái phiếu chuyển thành "COMPLETED".
        2. Cộng tồn kho tại chi nhánh nhận.
        3. Ghi log vào inventory_adjustments.
        """
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get(transaction=transaction).to_dict()

        if transfer_doc.get('status') != 'SHIPPED':
            raise Exception("Chỉ có thể nhận các phiếu đã được gửi đi (trạng thái SHIPPED).")

        to_branch = transfer_doc['to_branch_id']
        items = transfer_doc['items']

        # Cộng kho và ghi log cho từng sản phẩm
        for item in items:
            sku = item['sku']
            quantity = item['quantity']
            
            # Lấy tồn kho hiện tại
            current_quantity = 0
            inv_ref = self.inventory_col.document(self._get_doc_id(sku, to_branch))
            inv_snapshot = inv_ref.get(transaction=transaction)
            if inv_snapshot.exists:
                current_quantity = inv_snapshot.to_dict().get('stock_quantity', 0)

            # 1. Cộng tồn kho chi nhánh nhận
            self.update_inventory(sku, to_branch, quantity, transaction)
            
            # 2. Ghi log
            adj_id = f"STI-{uuid.uuid4().hex[:8].upper()}" # Stock Transfer In
            adj_ref = self.adjustments_col.document(adj_id)
            transaction.set(adj_ref, {
                "id": adj_id, "sku": sku, "branch_id": to_branch, "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "quantity_before": current_quantity,
                "quantity_after": current_quantity + quantity,
                "delta": quantity,
                "reason": "STOCK_TRANSFER_IN",
                "notes": f"Nhận hàng từ chi nhánh {transfer_doc['from_branch_id']} (phiếu {transfer_id})",
                "related_transfer_id": transfer_id
            })

        # 3. Cập nhật trạng thái phiếu chuyển
        transaction.update(transfer_ref, {
            "status": "COMPLETED",
            "completed_at": datetime.now().isoformat(),
            "completed_by": user_id,
            "history": firestore.ArrayUnion([{
                "status": "COMPLETED",
                "updated_at": datetime.now().isoformat(),
                "user_id": user_id
            }])
        })
        
    def receive_transfer(self, transfer_id, user_id):
        """Hàm public để gọi transaction xác nhận nhận hàng."""
        transaction = self.db.transaction()
        self._receive_transfer_transaction(transaction, transfer_id, user_id)

    def get_transfers(self, branch_id: str, direction: str = 'all', status: str = None, limit=50):
        """
        Lấy danh sách các phiếu luân chuyển liên quan đến một chi nhánh.
        - direction: 'outgoing' (chi nhánh là người gửi), 'incoming' (chi nhánh là người nhận), 'all'
        - status: 'PENDING', 'SHIPPED', 'COMPLETED'
        """
        results = []
        base_query = self.transfers_col.order_by("created_at", direction=firestore.Query.DESCENDING)

        # Build queries based on direction
        queries = []
        if direction == 'outgoing' or direction == 'all':
            q_out = base_query.where('from_branch_id', '==', branch_id)
            if status:
                q_out = q_out.where('status', '==', status)
            queries.append(q_out)
        
        if direction == 'incoming' or direction == 'all':
            q_in = base_query.where('to_branch_id', '==', branch_id)
            if status:
                q_in = q_in.where('status', '==', status)
            queries.append(q_in)

        # Execute queries and merge results
        transfer_ids = set()
        for query in queries:
            docs = query.limit(limit).stream()
            for doc in docs:
                if doc.id not in transfer_ids:
                    results.append(doc.to_dict())
                    transfer_ids.add(doc.id)
        
        # Sort final results by date again as we merged two queries
        results.sort(key=lambda x: x['created_at'], reverse=True)
        
        return results[:limit]
