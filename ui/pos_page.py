import streamlit as st
import pandas as pd
from datetime import datetime

def render_pos_page():
    st.header("🛒 Bán hàng (POS)")

    # Lấy các manager và thông tin cần thiết
    product_mgr = st.session_state.product_mgr
    customer_mgr = st.session_state.customer_mgr
    inventory_mgr = st.session_state.inventory_mgr
    pos_mgr = st.session_state.pos_mgr
    promotion_mgr = st.session_state.promotion_mgr
    current_branch_id = st.session_state.user['branch_id']

    # ---- KHỞI TẠO STATE ----
    if 'cart' not in st.session_state:
        st.session_state.cart = []
    if 'manual_discount_percent' not in st.session_state:
        st.session_state.manual_discount_percent = 0
    
    # Lấy chương trình khuyến mãi đang hoạt động
    active_program = promotion_mgr.get_active_price_program()
    
    # Lấy quy tắc từ chương trình KM (nếu có)
    auto_discount_percent = 0
    manual_discount_limit = 0
    if active_program:
        auto_discount_percent = active_program.get('rules', {}).get('auto_discount', {}).get('value', 0)
        manual_discount_limit = active_program.get('rules', {}).get('manual_extra_limit', {}).get('value', 0)

    # ---- TÍNH TOÁN GIỎ HÀNG ----
    subtotal = 0
    total_auto_discount = 0
    cart_items_for_order = []

    for item in st.session_state.cart:
        original_line_total = item['original_price'] * item['quantity']
        subtotal += original_line_total
        
        # Áp dụng giảm giá tự động
        line_auto_discount = original_line_total * (auto_discount_percent / 100)
        total_auto_discount += line_auto_discount
        
        # Tạo item cho việc lưu đơn hàng
        cart_items_for_order.append({
            "sku": item["sku"],
            "name": item["name"],
            "original_price": item['original_price'],
            "quantity": item["quantity"],
            "final_price_after_discounts": (original_line_total - line_auto_discount) / item['quantity'] # Sẽ trừ nốt manual discount sau
        })

    # Áp dụng giảm giá thủ công trên tổng đơn
    total_manual_discount = subtotal * (st.session_state.manual_discount_percent / 100)
    final_total = subtotal - total_auto_discount - total_manual_discount

    # Cập nhật lại final price trong list items
    for item in cart_items_for_order:
        item['final_price_after_discounts'] -= (item['original_price'] * item['quantity'] / subtotal) * total_manual_discount / item['quantity'] if subtotal > 0 else 0

    # ---- GIAO DIỆN ----
    col1, col2 = st.columns([2, 3])

    with col1:
        st.subheader("Thông tin đơn hàng")
        
        # Hiển thị chương trình khuyến mãi
        if active_program:
            st.success(f"🎉 Đang áp dụng: {active_program['name']}")
        else:
            st.info("Không có chương trình giá nào đang hoạt động.")

        # Chọn khách hàng
        customers = customer_mgr.list_customers()
        customer_options = {c['id']: f"{c['name']} - {c['phone']}" for c in customers}
        customer_options["-"] = "Khách vãng lai"
        selected_customer_id = st.selectbox("👤 Khách hàng", list(customer_options.keys()), format_func=lambda x: customer_options[x], index=len(customer_options) - 1)

        st.divider()
        st.subheader("Giỏ hàng")

        if not st.session_state.cart:
            st.info("Giỏ hàng đang trống")
        else:
            cart_df = pd.DataFrame(st.session_state.cart)[["name", "quantity", "original_price"]]
            cart_df.columns = ["Tên SP", "SL", "Đơn giá"]
            st.dataframe(cart_df, use_container_width=True, hide_index=True)

            # Form cho giảm giá và tổng tiền
            with st.form("payment_form"):
                st.number_input(
                    f"Giảm giá thêm (% - Tối đa: {manual_discount_limit}%)",
                    min_value=0.0, max_value=float(manual_discount_limit),
                    step=1.0, key="manual_discount_percent"
                )
                
                st.metric("Tổng tiền hàng", f"{subtotal:,.0f} VNĐ")
                st.metric("Giảm giá", f"- {total_auto_discount + total_manual_discount:,.0f} VNĐ")
                st.markdown("###")
                st.metric("✅ KHÁCH CẦN TRẢ", f"{final_total:,.0f} VNĐ")
                
                submitted_payment = st.form_submit_button("💳 THANH TOÁN", use_container_width=True, type="primary")

            if submitted_payment:
                order_data = {
                    "branch_id": current_branch_id,
                    "customer_id": selected_customer_id if selected_customer_id != "-" else None,
                    "items": cart_items_for_order,
                    "subtotal_amount": subtotal,
                    "auto_discount_amount": total_auto_discount,
                    "manual_discount_percent": st.session_state.manual_discount_percent,
                    "manual_discount_amount": total_manual_discount,
                    "total_amount": final_total,
                    "promotion_applied": active_program['name'] if active_program else None,
                    "created_by": st.session_state.user['id'],
                    "payment_method": "Cash"
                }
                with st.spinner("Đang xử lý đơn hàng..."):
                    success, result = pos_mgr.create_order(order_data)
                if success:
                    st.success(f"Tạo đơn hàng {result['id']} thành công!")
                    st.session_state.cart = []
                    st.session_state.manual_discount_percent = 0
                    st.rerun()
                else:
                    st.error(f"Lỗi: {result}")

        if st.session_state.cart and not submitted_payment:
            if st.button("🗑️ Xóa giỏ hàng", use_container_width=True):
                st.session_state.cart = []
                st.session_state.manual_discount_percent = 0
                st.rerun()

    with col2:
        st.subheader("Thêm sản phẩm")
        products = product_mgr.list_products()
        branch_inventory = inventory_mgr.get_inventory_by_branch(current_branch_id)

        product_display_list = [{
            "sku": p['sku'], 
            "name": p['name'], 
            "price": p.get('price_default', 0),
            "stock": branch_inventory.get(p['sku'], {}).get('stock_quantity', 0)
        } for p in products]
        
        product_df = pd.DataFrame([p for p in product_display_list if p['stock'] > 0])

        if product_df.empty:
            st.warning("Tất cả sản phẩm tại chi nhánh này đã hết hàng.")
            return

        options = [f"{name} | Tồn kho: {stock}" for name, stock in zip(product_df["name"], product_df["stock"])]
        selected_product_str = st.selectbox("Chọn hoặc tìm sản phẩm", options)

        if selected_product_str:
            selected_name = selected_product_str.split(' |')[0]
            selected_row = product_df[product_df['name'] == selected_name].iloc[0]
            
            col_q, col_b = st.columns([1, 2])
            quantity = col_q.number_input("Số lượng", 1, int(selected_row['stock']), 1)
            
            if col_b.button("Thêm vào giỏ", use_container_width=True):
                existing_item = next((item for item in st.session_state.cart if item["sku"] == selected_row["sku"]), None)
                if existing_item:
                    new_quantity = existing_item['quantity'] + quantity
                    if new_quantity > selected_row['stock']:
                        st.error(f"Vượt quá tồn kho! (Tối đa: {selected_row['stock']})")
                    else:
                        existing_item['quantity'] = new_quantity
                else:
                    st.session_state.cart.append({
                        "sku": selected_row["sku"],
                        "name": selected_row["name"],
                        "original_price": selected_row["price"],
                        "quantity": quantity
                    })
                st.rerun()