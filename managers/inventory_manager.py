from google.cloud import firestore
from datetime import datetime

class InventoryManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('inventory')

    def _get_doc_id(self, sku: str, branch_id: str):
        """Tạo ID tài liệu nhất quán theo format SKU_BRANCHID."""
        return f"{sku}_{branch_id}"

    def get_stock(self, sku: str, branch_id: str):
        """Lấy số lượng tồn kho hiện tại của một sản phẩm tại một chi nhánh."""
        doc_id = self._get_doc_id(sku, branch_id)
        doc = self.collection.document(doc_id).get()
        if doc.exists:
            return doc.to_dict().get('stock_quantity', 0)
        return 0

    def set_stock(self, sku: str, branch_id: str, quantity: int):
        """Thiết lập lại số lượng tồn kho (dùng cho kiểm kê)."""
        doc_id = self._get_doc_id(sku, branch_id)
        data = {
            'sku': sku,
            'branch_id': branch_id,
            'stock_quantity': quantity,
            'last_updated': datetime.now().isoformat()
        }
        self.collection.document(doc_id).set(data, merge=True)

    def update_inventory(self, sku: str, branch_id: str, delta: int, transaction=None):
        """
        Cập nhật tồn kho một cách an toàn (atomic).
        Sử dụng FieldValue.increment để cộng/trừ.
        Có thể chạy bên trong một transaction có sẵn.
        """
        doc_id = self._get_doc_id(sku, branch_id)
        doc_ref = self.collection.document(doc_id)
        
        update_data = {
            'stock_quantity': firestore.FieldValue.increment(delta),
            'last_updated': datetime.now().isoformat(),
            'sku': sku, # Ghi lại để dễ truy vấn
            'branch_id': branch_id # Ghi lại để dễ truy vấn
        }

        if transaction:
            # Nếu đang trong transaction, dùng transaction để ghi
            transaction.set(doc_ref, update_data, merge=True)
        else:
            # Nếu không, ghi trực tiếp
            doc_ref.set(update_data, merge=True)

    def get_inventory_by_branch(self, branch_id: str):
        """Lấy toàn bộ tồn kho của một chi nhánh."""
        docs = self.collection.where('branch_id', '==', branch_id).stream()
        results = {}
        for doc in docs:
            data = doc.to_dict()
            results[data['sku']] = data
        return results
