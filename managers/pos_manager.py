from google.cloud import firestore
from datetime import datetime
import uuid

class POSManager:
    def __init__(self, firebase_client, inventory_mgr, customer_mgr, voucher_mgr):
        self.db = firebase_client.db
        self.inventory_mgr = inventory_mgr
        self.customer_mgr = customer_mgr
        self.voucher_mgr = voucher_mgr # Sẽ dùng sau
        self.orders_collection = self.db.collection('orders')

    def _create_order_id(self, branch_id):
        """Tạo Order ID theo format: BR-YYMMDD-XXXXXX"""
        now = datetime.now()
        date_str = now.strftime("%y%m%d")
        short_uuid = uuid.uuid4().hex[:6].upper()
        return f"{branch_id}-{date_str}-{short_uuid}"

    def create_order(self, order_data: dict):
        """
        Tạo một đơn hàng mới trong một transaction để đảm bảo toàn vẹn dữ liệu.
        - Tạo bản ghi Order
        - Trừ tồn kho (atomic)
        - Cập nhật điểm/chi tiêu cho khách hàng (atomic)
        - (Tương lai) Đánh dấu voucher đã sử dụng
        """
        branch_id = order_data['branch_id']
        customer_id = order_data.get('customer_id')
        items = order_data['items']
        total_amount = order_data['total_amount']
        
        try:
            # Bắt đầu một transaction
            @firestore.transactional
            def _process_order(transaction):
                # 1. Tạo ID đơn hàng mới
                order_id = self._create_order_id(branch_id)
                order_ref = self.orders_collection.document(order_id)
                
                # 2. Xử lý từng sản phẩm trong giỏ hàng
                for item in items:
                    sku = item['sku']
                    quantity = item['quantity']
                    
                    # Lấy tồn kho hiện tại (để kiểm tra)
                    # Lưu ý: Việc kiểm tra này có thể không hoàn toàn chính xác trong môi trường đồng thời cao
                    # nhưng là một lớp phòng vệ tốt. Firestore transaction sẽ đảm bảo lần ghi cuối cùng là an toàn.
                    current_stock = self.inventory_mgr.get_stock(sku, branch_id)
                    if current_stock < quantity:
                        # Ném lỗi để hủy toàn bộ transaction
                        raise Exception(f"Không đủ tồn kho cho sản phẩm {item['name']} (SKU: {sku}). Hiện có {current_stock}, cần {quantity}.")

                    # Gọi hàm cập nhật tồn kho bên trong transaction
                    self.inventory_mgr.update_inventory(
                        sku=sku, 
                        branch_id=branch_id, 
                        delta=-quantity, # Trừ đi số lượng bán
                        transaction=transaction
                    )

                # 3. Cập nhật điểm và chi tiêu cho khách hàng (nếu có)
                self.customer_mgr.update_customer_stats(
                    transaction=transaction,
                    customer_id=customer_id,
                    amount_spent_delta=total_amount,
                    points_delta=int(total_amount / 1000) # Ví dụ: 1000đ = 1 điểm
                )

                # 4. Tạo bản ghi đơn hàng
                final_order_data = order_data.copy()
                final_order_data.update({
                    'id': order_id,
                    'created_at': datetime.now().isoformat(),
                    'status': 'COMPLETED'
                })
                transaction.set(order_ref, final_order_data)
                
                return final_order_data # Trả về đơn hàng đã tạo

            # Thực thi transaction
            result = _process_order(self.db.transaction())
            return True, result

        except Exception as e:
            # Bất kỳ lỗi nào xảy ra trong transaction sẽ được bắt ở đây
            return False, str(e)

    def list_orders_by_branch(self, branch_id: str, start_date=None, end_date=None):
        """Lấy danh sách đơn hàng theo chi nhánh và khoảng thời gian."""
        query = self.orders_collection.where('branch_id', '==', branch_id)
        
        if start_date:
            query = query.where('created_at', '>=', start_date.isoformat())
        if end_date:
            query = query.where('created_at', '<=', end_date.isoformat())
            
        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
        
        docs = query.stream()
        return [doc.to_dict() for doc in docs]
