
import uuid
from datetime import datetime
from google.cloud import firestore
from .inventory_manager import InventoryManager

class StockTransferManager:
    """
    Quản lý quy trình luân chuyển kho hai giai đoạn (xuất và nhập)
    giữa các chi nhánh để đảm bảo tính toàn vẹn của dữ liệu.
    """
    def __init__(self, firebase_client, inventory_mgr: InventoryManager):
        self.db = firebase_client.db
        self.inventory_mgr = inventory_mgr
        self.transfers_col = self.db.collection('stock_transfers')

    def create_transfer_request(self, source_branch_id: str, destination_branch_id: str, items: list, user_id: str, notes: str = ''):
        """
        Tạo một yêu cầu luân chuyển kho (bước 1).
        """
        if not all([source_branch_id, destination_branch_id, items, user_id]):
            raise ValueError("Thông tin chi nhánh nguồn, đích, sản phẩm và người dùng là bắt buộc.")
        if source_branch_id == destination_branch_id:
            raise ValueError("Chi nhánh nguồn và đích không được trùng nhau.")

        transfer_id = f"ST-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        request_data = {
            "id": transfer_id,
            "source_branch_id": source_branch_id,
            "destination_branch_id": destination_branch_id,
            "created_by": user_id,
            "created_at": datetime.now().isoformat(),
            "status": "PENDING",
            "items": items,
            "notes": notes,
            "dispatch_info": None,
            "receipt_info": None,
            "cancellation_info": None
        }
        
        self.transfers_col.document(transfer_id).set(request_data)
        return transfer_id

    @firestore.transactional
    def _dispatch_transfer_in_transaction(self, transaction, transfer_id: str, user_id: str):
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get(transaction=transaction)
        if not transfer_doc.exists: raise FileNotFoundError(f"Không tìm thấy yêu cầu luân chuyển kho với ID: {transfer_id}")
        transfer_data = transfer_doc.to_dict()
        if transfer_data.get('status') != 'PENDING': raise ValueError(f"Chỉ có thể xuất kho cho yêu cầu ở trạng thái 'PENDING'.")

        notes = f"Xuất kho cho phiếu luân chuyển {transfer_id} đến chi nhánh {transfer_data['destination_branch_id']}."
        issue_items = [{'sku': item['sku'], 'quantity': -abs(item.get('quantity', 0))} for item in transfer_data['items'] if item.get('quantity', 0) > 0]

        issue_voucher_id = self.inventory_mgr.execute_voucher_creation_in_transaction(
            transaction, "GOODS_ISSUE", transfer_data['source_branch_id'], user_id, issue_items, datetime.now(), notes
        )
        
        dispatch_info = {"dispatched_by": user_id, "dispatched_at": datetime.now().isoformat(), "source_voucher_id": issue_voucher_id}
        transaction.update(transfer_ref, {"status": "IN_TRANSIT", "dispatch_info": dispatch_info})
        return issue_voucher_id

    def dispatch_transfer_transactional(self, transfer_id: str, user_id: str):
        transaction = self.db.transaction()
        return self._dispatch_transfer_in_transaction(transaction, transfer_id, user_id)

    @firestore.transactional
    def _receive_transfer_in_transaction(self, transaction, transfer_id: str, user_id: str):
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get(transaction=transaction)
        if not transfer_doc.exists: raise FileNotFoundError(f"Không tìm thấy yêu cầu luân chuyển kho với ID: {transfer_id}")
        transfer_data = transfer_doc.to_dict()
        if transfer_data.get('status') != 'IN_TRANSIT': raise ValueError(f"Chỉ có thể nhận hàng cho yêu cầu ở trạng thái 'IN_TRANSIT'.")

        notes = f"Nhập kho từ phiếu luân chuyển {transfer_id} từ chi nhánh {transfer_data['source_branch_id']}."
        
        receipt_voucher_id = self.inventory_mgr.execute_voucher_creation_in_transaction(
            transaction, "GOODS_RECEIPT", transfer_data['destination_branch_id'], user_id, 
            transfer_data['items'], datetime.now(), notes, supplier="Luân chuyển nội bộ"
        )

        receipt_info = {"received_by": user_id, "received_at": datetime.now().isoformat(), "destination_voucher_id": receipt_voucher_id}
        transaction.update(transfer_ref, {"status": "COMPLETED", "receipt_info": receipt_info})
        return receipt_voucher_id

    def receive_transfer_transactional(self, transfer_id: str, user_id: str):
        transaction = self.db.transaction()
        return self._receive_transfer_in_transaction(transaction, transfer_id, user_id)

    def cancel_transfer(self, transfer_id: str, user_id: str, reason_notes: str = ''):
        transfer_ref = self.transfers_col.document(transfer_id)
        transfer_doc = transfer_ref.get()
        if not transfer_doc.exists: raise FileNotFoundError(f"Không tìm thấy yêu cầu luân chuyển kho với ID: {transfer_id}")
        transfer_data = transfer_doc.to_dict()
        if transfer_data.get('status') != 'PENDING': raise ValueError(f"Chỉ có thể hủy yêu cầu ở trạng thái 'PENDING'.")

        cancellation_info = {"cancelled_by": user_id, "cancelled_at": datetime.now().isoformat(), "reason": reason_notes}
        transfer_ref.update({"status": "CANCELLED", "cancellation_info": cancellation_info})
        return True

    def get_outgoing_transfers(self, branch_id: str, status: list) -> list:
        if not branch_id or not status: return []
        query = self.transfers_col.where('source_branch_id', '==', branch_id).where('status', 'in', status)
        transfers = [doc.to_dict() for doc in query.stream()]
        return sorted(transfers, key=lambda x: x['created_at'], reverse=True)

    def get_incoming_transfers(self, branch_id: str, status: list) -> list:
        if not branch_id or not status: return []
        query = self.transfers_col.where('destination_branch_id', '==', branch_id).where('status', 'in', status)
        transfers = [doc.to_dict() for doc in query.stream()]
        return sorted(transfers, key=lambda x: x['created_at'], reverse=True)
