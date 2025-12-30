
from google.cloud import firestore
import streamlit as st
from datetime import datetime
import uuid

class POSManager:
    def __init__(self, firebase_client, inventory_mgr, customer_mgr, promotion_mgr):
        self.db = firebase_client.db
        self.inventory_mgr = inventory_mgr
        self.customer_mgr = customer_mgr
        self.promotion_mgr = promotion_mgr
        self.orders_collection = self.db.collection('orders')

    # --------------------------------------------------------------------------
    # HÀM QUẢN LÝ GIỎ HÀNG (TƯƠNG TÁC VỚI SESSION STATE)
    # --------------------------------------------------------------------------

    def add_item_to_cart(self, product_data: dict, stock_quantity: int):
        sku = product_data['sku']
        if sku in st.session_state.pos_cart:
            # Nếu đã có, chỉ tăng số lượng
            self.update_item_quantity(sku, st.session_state.pos_cart[sku]['quantity'] + 1)
        else:
            # Nếu chưa có, thêm mới với thông tin đầy đủ
            st.session_state.pos_cart[sku] = {
                "sku": sku,
                "name": product_data['name'],
                "category_id": product_data.get('category_id'),
                "original_price": product_data.get('price_default', 0),
                "quantity": 1,
                "stock": stock_quantity
            }

    def update_item_quantity(self, sku: str, new_quantity: int):
        if sku in st.session_state.pos_cart:
            if new_quantity <= 0:
                # Nếu số lượng <= 0, xóa khỏi giỏ
                del st.session_state.pos_cart[sku]
            elif new_quantity > st.session_state.pos_cart[sku]['stock']:
                # Kiểm tra tồn kho
                st.toast(f"Số lượng vượt quá tồn kho ({st.session_state.pos_cart[sku]['stock']})!")
            else:
                st.session_state.pos_cart[sku]['quantity'] = new_quantity
    
    def clear_cart(self):
        st.session_state.pos_cart = {}
        st.session_state.pos_customer = "-"
        st.session_state.pos_manual_discount = {"type": "PERCENT", "value": 0}
        st.session_state.pos_manual_discount_value = 0 # Reset input

    # --------------------------------------------------------------------------
    # HÀM TÍNH TOÁN TRUNG TÂM
    # --------------------------------------------------------------------------

    def calculate_cart_state(self, cart_items: dict, customer_id: str, manual_discount_input: dict):
        # 1. Lấy chương trình khuyến mãi đang hoạt động
        active_promo = self.promotion_mgr.get_active_price_program()
        
        # 2. Khởi tạo các biến trạng thái
        calculated_items = {}
        subtotal = 0
        total_auto_discount = 0
        manual_discount_exceeded = False

        # 3. Lặp qua từng sản phẩm trong giỏ hàng thô
        for sku, item in cart_items.items():
            original_line_total = item['original_price'] * item['quantity']
            subtotal += original_line_total
            
            auto_discount_value = 0
            # Kiểm tra xem sản phẩm có được hưởng KM tự động không
            if self.promotion_mgr.is_item_eligible_for_program(item, active_promo):
                auto_discount_rule = active_promo.get('rules', {}).get('auto_discount', {})
                if auto_discount_rule.get('type') == 'PERCENT':
                    auto_discount_value = original_line_total * (auto_discount_rule.get('value', 0) / 100)
            
            total_auto_discount += auto_discount_value

            # Lưu thông tin đã tính toán cho từng dòng
            calculated_items[sku] = {
                **item, # Copy tất cả thông tin cũ (name, sku, quantity...)
                'original_line_total': original_line_total,
                'auto_discount_applied': auto_discount_value,
                'line_total_after_auto_discount': original_line_total - auto_discount_value
            }
        
        # 4. Tính toán giảm giá thêm (manual discount)
        total_manual_discount = 0
        limit_value = 0
        if active_promo and self.promotion_mgr.is_manual_discount_allowed(active_promo):
            limit_rule = active_promo.get('rules', {}).get('manual_extra_limit', {})
            limit_value = limit_rule.get('value', 0)
            
            user_discount_value = manual_discount_input.get('value', 0)
            
            # Kiểm tra xem người dùng có nhập vượt ngưỡng không
            if user_discount_value > limit_value:
                manual_discount_exceeded = True
            else:
                # Chỉ áp dụng giảm giá nếu không vượt ngưỡng
                total_manual_discount = (subtotal - total_auto_discount) * (user_discount_value / 100)
        
        # 5. Tính toán tổng cuối cùng
        grand_total = subtotal - total_auto_discount - total_manual_discount

        # 6. Trả về một dictionary chứa toàn bộ trạng thái
        return {
            "items": calculated_items, # Danh sách sản phẩm đã được tính toán
            "active_promotion": active_promo, # Thông tin về chương trình KM
            "subtotal": subtotal, # Tổng tiền hàng gốc
            "total_auto_discount": total_auto_discount, # Tổng giảm giá từ KM
            "total_manual_discount": total_manual_discount, # Tổng giảm giá thêm (hợp lệ)
            "manual_discount_input": manual_discount_input, # Giá trị người dùng nhập
            "manual_discount_limit": limit_value, # Ngưỡng cho phép
            "manual_discount_exceeded": manual_discount_exceeded, # Cờ báo vượt ngưỡng
            "grand_total": grand_total # Tổng cuối cùng khách phải trả
        }

    # --------------------------------------------------------------------------
    # HÀM XỬ LÝ ĐƠN HÀNG (TƯƠNG TÁC VỚI DATABASE)
    # --------------------------------------------------------------------------

    def _create_order_id(self, branch_id):
        now = datetime.now()
        date_str = now.strftime("%y%m%d")
        short_uuid = uuid.uuid4().hex[:6].upper()
        return f"{branch_id}-{date_str}-{short_uuid}"

    def create_order(self, cart_state: dict, customer_id: str, branch_id: str, seller_id: str):
        if not cart_state['items']:
            return False, "Giỏ hàng trống."
        if cart_state['manual_discount_exceeded']:
            return False, "Mức giảm giá thêm không hợp lệ."

        order_id = self._create_order_id(branch_id)

        # Chuẩn bị dữ liệu để lưu vào Firestore
        order_items_to_save = []
        for sku, item in cart_state['items'].items():
            # Phân bổ giảm giá thêm cho từng dòng sản phẩm
            line_total_before_manual = item['line_total_after_auto_discount']
            total_before_manual = cart_state['subtotal'] - cart_state['total_auto_discount']
            
            proportional_manual_discount = 0
            if total_before_manual > 0:
                 proportional_manual_discount = (line_total_before_manual / total_before_manual) * cart_state['total_manual_discount']
            
            final_line_total = line_total_before_manual - proportional_manual_discount
            final_price_per_unit = final_line_total / item['quantity'] if item['quantity'] > 0 else 0

            order_items_to_save.append({
                "sku": sku,
                "name": item['name'],
                "quantity": item['quantity'],
                "original_price": item['original_price'],
                "auto_discount_applied": item['auto_discount_applied'],
                "manual_discount_applied": proportional_manual_discount,
                "final_price": final_price_per_unit
            })

        final_order_data = {
            "id": order_id,
            "branch_id": branch_id,
            "seller_id": seller_id,
            "customer_id": customer_id if customer_id != "-" else None,
            "items": order_items_to_save,
            "subtotal": cart_state['subtotal'],
            "total_auto_discount": cart_state['total_auto_discount'],
            "total_manual_discount": cart_state['total_manual_discount'],
            "grand_total": cart_state['grand_total'],
            "promotion_id": cart_state['active_promotion']['id'] if cart_state['active_promotion'] else None,
            "created_at": datetime.now().isoformat(),
            "status": "COMPLETED"
        }

        try:
            # Transaction để đảm bảo tính toàn vẹn
            @firestore.transactional
            def _process_order(transaction):
                order_ref = self.orders_collection.document(order_id)

                # Trừ tồn kho
                for item in order_items_to_save:
                    self.inventory_mgr.update_inventory(
                        sku=item['sku'],
                        branch_id=branch_id,
                        delta=-item['quantity'],
                        transaction=transaction
                    )
                
                # Cập nhật thông tin khách hàng
                if customer_id != "-":
                    self.customer_mgr.update_customer_stats(
                        transaction=transaction,
                        customer_id=customer_id,
                        amount_spent_delta=final_order_data['grand_total'],
                        points_delta=int(final_order_data['grand_total'] / 1000) 
                    )

                # Lưu đơn hàng
                transaction.set(order_ref, final_order_data)

            # Chạy transaction
            _process_order(self.db.transaction())
            return True, order_id
        except Exception as e:
            return False, str(e)

