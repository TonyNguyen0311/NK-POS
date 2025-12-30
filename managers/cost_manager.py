"""
Module này chịu trách nhiệm xử lý tất cả logic liên quan đến chi phí sản phẩm,
bao gồm tính giá vốn bình quân gia quyền và cung cấp dữ liệu chi phí cho báo cáo.
"""

from google.cloud import firestore
# Sửa lỗi: Import hằng số SERVER_TIMESTAMP
from google.cloud.firestore import SERVER_TIMESTAMP

class CostManager:
    def __init__(self, firebase_client):
        """
        Khởi tạo CostManager với một đối tượng FirebaseClient đã được khởi tạo.
        
        Args:
            firebase_client: Một instance của lớp FirebaseClient.
        """
        self.db = firebase_client.db

    def record_shipment_and_update_avg_cost(self, product_id, branch_id, quantity, unit_cost, transaction=None):
        """
        Ghi nhận một lô hàng mới và tính toán lại giá vốn bình quân gia quyền.
        Hàm này nên được gọi bên trong một transaction lớn hơn nếu có.
        """
        inventory_ref = self.db.collection('branch_inventory').document(f"{branch_id}_{product_id}")

        def _update_avg_cost(transaction, inventory_ref):
            inventory_snapshot = inventory_ref.get(transaction=transaction)
            
            current_quantity = 0
            current_avg_cost = 0.0

            if inventory_snapshot.exists:
                inventory_data = inventory_snapshot.to_dict()
                current_quantity = inventory_data.get('stock_quantity', 0)
                current_avg_cost = inventory_data.get('average_cost', 0.0)

            total_value = (current_quantity * current_avg_cost) + (quantity * unit_cost)
            new_quantity = current_quantity + quantity
            new_avg_cost = total_value / new_quantity if new_quantity > 0 else 0

            update_data = {
                'product_id': product_id,
                'branch_id': branch_id,
                'stock_quantity': new_quantity,
                'average_cost': new_avg_cost,
                # Sửa lỗi: Sử dụng hằng số SERVER_TIMESTAMP
                'last_updated': SERVER_TIMESTAMP
            }
            transaction.set(inventory_ref, update_data, merge=True)

            log_ref = self.db.collection('shipment_logs').document()
            transaction.set(log_ref, {
                'product_id': product_id,
                'branch_id': branch_id,
                'quantity': quantity,
                'unit_cost': unit_cost,
                'new_average_cost': new_avg_cost,
                # Sửa lỗi: Sử dụng hằng số SERVER_TIMESTAMP
                'timestamp': SERVER_TIMESTAMP
            })
            
            return new_avg_cost

        if transaction is None:
            transaction = self.db.transaction()
            return firestore.transactional(_update_avg_cost)(transaction, inventory_ref)
        else:
            return _update_avg_cost(transaction, inventory_ref)

    def get_cogs_for_items(self, branch_id, items):
        """
        Lấy tổng Giá vốn hàng bán (COGS) cho một danh sách các mặt hàng đã bán.
        """
        total_cogs = 0.0
        for item in items:
            product_id = item['product_id']
            quantity = item['quantity']
            inventory_ref = self.db.collection('branch_inventory').document(f"{branch_id}_{product_id}")
            inventory_doc = inventory_ref.get()

            if inventory_doc.exists:
                avg_cost = inventory_doc.to_dict().get('average_cost', 0.0)
                total_cogs += avg_cost * quantity
        
        return total_cogs
