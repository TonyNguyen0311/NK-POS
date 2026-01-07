
from google.cloud import firestore
import streamlit as st
from datetime import datetime
import uuid
from .cost_manager import CostManager
from .price_manager import PriceManager

class POSManager:
    def __init__(self, firebase_client, inventory_mgr, customer_mgr, promotion_mgr, cost_mgr: CostManager, price_mgr: PriceManager):
        self.db = firebase_client.db
        self.inventory_mgr = inventory_mgr
        self.customer_mgr = customer_mgr
        self.promotion_mgr = promotion_mgr
        self.cost_mgr = cost_mgr
        self.price_mgr = price_mgr
        # self.orders_collection = self.db.collection('orders') # REMOVED: No longer writing to 'orders'

    # --------------------------------------------------------------------------
    # HÀM QUẢN LÝ GIỎ HÀNG
    # --------------------------------------------------------------------------

    def add_item_to_cart(self, branch_id: str, product_data: dict, stock_quantity: int):
        sku = product_data['sku']
        current_price = product_data.get('selling_price', 0)

        if current_price <= 0:
            st.error(f"Sản phẩm '{product_data['name']}' ({sku}) chưa được thiết lập giá bán tại chi nhánh này. Vui lòng kiểm tra lại.")
            return

        if sku in st.session_state.pos_cart:
            self.update_item_quantity(sku, st.session_state.pos_cart[sku]['quantity'] + 1)
        else:
            image_id = product_data.get('image_id')
            st.session_state.pos_cart[sku] = {
                "sku": sku,
                "name": product_data['name'],
                "category_id": product_data.get('category_id'),
                "original_price": current_price,
                "quantity": 1,
                "stock": stock_quantity,
                "image_id": image_id
            }

    def update_item_quantity(self, sku: str, new_quantity: int):
        if sku in st.session_state.pos_cart:
            if new_quantity <= 0:
                del st.session_state.pos_cart[sku]
            elif new_quantity > st.session_state.pos_cart[sku]['stock']:
                st.toast(f"Số lượng vượt quá tồn kho ({st.session_state.pos_cart[sku]['stock']})!")
            else:
                st.session_state.pos_cart[sku]['quantity'] = new_quantity
    
    def clear_cart(self):
        st.session_state.pos_cart = {}
        st.session_state.pos_customer = "-"
        st.session_state.pos_manual_discount = {"type": "PERCENT", "value": 0}
        st.session_state.pos_manual_discount_value = 0

    # --------------------------------------------------------------------------
    # HÀM TÍNH TOÁN GIỎ HÀNG
    # --------------------------------------------------------------------------

    def calculate_cart_state(self, cart_items: dict, customer_id: str, manual_discount_input: dict):
        # ... (implementation remains the same)
        active_promo = self.promotion_mgr.get_active_price_program()
        calculated_items = {}
        subtotal = 0
        total_auto_discount = 0
        manual_discount_exceeded = False
        total_items = 0 

        for sku, item in cart_items.items():
            total_items += item['quantity'] 
            original_line_total = item['original_price'] * item['quantity']
            subtotal += original_line_total
            
            auto_discount_value = 0
            if self.promotion_mgr.is_item_eligible_for_program(item, active_promo):
                auto_discount_rule = active_promo.get('rules', {}).get('auto_discount', {})
                if auto_discount_rule.get('type') == 'PERCENT':
                    auto_discount_value = original_line_total * (auto_discount_rule.get('value', 0) / 100)
            
            total_auto_discount += auto_discount_value

            calculated_items[sku] = {
                **item,
                'original_line_total': original_line_total,
                'auto_discount_applied': auto_discount_value,
                'line_total_after_auto_discount': original_line_total - auto_discount_value
            }
        
        total_manual_discount = 0
        limit_value = 0
        if active_promo and self.promotion_mgr.is_manual_discount_allowed(active_promo):
            limit_rule = active_promo.get('rules', {}).get('manual_extra_limit', {})
            limit_value = limit_rule.get('value', 0)
            user_discount_value = manual_discount_input.get('value', 0)
            
            if user_discount_value > limit_value:
                manual_discount_exceeded = True
            else:
                total_manual_discount = (subtotal - total_auto_discount) * (user_discount_value / 100)
        
        grand_total = subtotal - total_auto_discount - total_manual_discount

        return {
            "items": calculated_items,
            "total_items": total_items, 
            "active_promotion": active_promo,
            "subtotal": subtotal,
            "total_auto_discount": total_auto_discount,
            "total_manual_discount": total_manual_discount,
            "manual_discount_input": manual_discount_input,
            "manual_discount_limit": limit_value,
            "manual_discount_exceeded": manual_discount_exceeded,
            "grand_total": grand_total
        }

    # --------------------------------------------------------------------------
    # HÀM XỬ LÝ TẠO ĐƠN HÀNG (REFACTORED)
    # --------------------------------------------------------------------------

    def _create_order_id(self, branch_id):
        now = datetime.now()
        date_str = now.strftime('%y%m%d')
        short_uuid = uuid.uuid4().hex[:6].upper()
        return f'{branch_id}-{date_str}-{short_uuid}'

    def create_order(self, cart_state: dict, customer_id: str, branch_id: str, seller_id: str):
        if not cart_state['items']:
            return False, "Giỏ hàng trống."
        if cart_state['manual_discount_exceeded']:
            return False, "Mức giảm giá thêm không hợp lệ."

        order_id = self._create_order_id(branch_id)
        creation_timestamp = datetime.now()
        
        try:
            @firestore.transactional
            def _process_order_and_cogs(transaction):
                order_items_to_save = []
                total_cogs = 0

                # Stage 1: Update inventory and get the accurate COGS for each item
                for sku, item in cart_state['items'].items():
                    accurate_cost_price = self.inventory_mgr.update_inventory(
                        transaction=transaction, sku=sku, branch_id=branch_id,
                        delta=-item['quantity'], order_id=order_id, user_id=seller_id
                    )
                    line_cogs = accurate_cost_price * item['quantity']
                    total_cogs += line_cogs
                    order_items_to_save.append({
                        **item, "cost_price": accurate_cost_price, "line_cogs": line_cogs
                    })

                # Stage 2: Calculate final prices and discounts
                finalized_items = []
                for item in order_items_to_save:
                    line_total_before_manual = item['line_total_after_auto_discount']
                    total_before_manual = cart_state['subtotal'] - cart_state['total_auto_discount']
                    proportional_manual_discount = (line_total_before_manual / total_before_manual) * cart_state['total_manual_discount'] if total_before_manual > 0 else 0
                    final_line_total = line_total_before_manual - proportional_manual_discount
                    final_price_per_unit = final_line_total / item['quantity'] if item['quantity'] > 0 else 0
                    finalized_items.append({
                        "sku": item['sku'], "name": item['name'], "quantity": item['quantity'],
                        "original_price": item['original_price'], "cost_price": item['cost_price'],
                        "line_cogs": item['line_cogs'], "auto_discount_applied": item['auto_discount_applied'],
                        "manual_discount_applied": proportional_manual_discount,
                        "final_price": final_price_per_unit, "image_id": item.get('image_id')
                    })

                # Stage 3: Construct the single source of truth: The Transaction Data
                transaction_data = {
                    "id": order_id, "type": "SALE", "status": "COMPLETED", "payment_method": "Tiền mặt",
                    "created_at": creation_timestamp, "branch_id": branch_id,
                    "cashier_id": seller_id, "customer_id": customer_id if customer_id != "-" else None,
                    "items": finalized_items,
                    "sub_total": cart_state['subtotal'],
                    "total_amount": cart_state['grand_total'],
                    "total_cogs": total_cogs,
                    "total_auto_discount": cart_state['total_auto_discount'],
                    "total_manual_discount": cart_state['total_manual_discount'],
                    "discount_amount": cart_state['total_auto_discount'] + cart_state['total_manual_discount'],
                    "promotion_id": cart_state['active_promotion']['id'] if cart_state['active_promotion'] else None,
                }

                # Stage 4: Update other services and write the single transaction document
                if customer_id != "-":
                    self.customer_mgr.update_customer_stats(
                        transaction=transaction, customer_id=customer_id,
                        amount_spent_delta=transaction_data['total_amount'],
                        points_delta=int(transaction_data['total_amount'] / 1000) 
                    )
                
                # Set the single, authoritative transaction document
                transaction_ref = self.db.collection('transactions').document(order_id)
                transaction.set(transaction_ref, transaction_data)

            # Execute the transaction
            _process_order_and_cogs(self.db.transaction())
            return True, order_id
        except Exception as e:
            return False, str(e)
