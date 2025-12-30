
import streamlit as st
from datetime import datetime

def render_pos_page():
    st.header("🛒 Bán hàng (POS)")

    # 1. LẤY CÁC MANAGER VÀ THÔNG TIN CẦN THIẾT
    product_mgr = st.session_state.product_mgr
    customer_mgr = st.session_state.customer_mgr
    inventory_mgr = st.session_state.inventory_mgr
    pos_mgr = st.session_state.pos_mgr
    promotion_mgr = st.session_state.promotion_mgr
    current_user = st.session_state.user
    current_branch_id = current_user['branch_id']

    # 2. KHỞI TẠO SESSION STATE CHO GIỎ HÀNG VÀ BỘ LỌC
    if 'pos_cart' not in st.session_state:
        st.session_state.pos_cart = {} # Dùng dict để dễ dàng cập nhật/xóa
    if 'pos_customer' not in st.session_state:
        st.session_state.pos_customer = "-"
    if 'pos_search' not in st.session_state:
        st.session_state.pos_search = ""
    if 'pos_category' not in st.session_state:
        st.session_state.pos_category = "ALL"
    if 'pos_manual_discount' not in st.session_state:
        st.session_state.pos_manual_discount = {"type": "PERCENT", "value": 0}


    # 3. LẤY DỮ LIỆU GỐC
    all_products = product_mgr.list_products()
    all_categories = product_mgr.get_categories()
    branch_inventory = inventory_mgr.get_inventory_by_branch(current_branch_id)
    customers = customer_mgr.list_customers()

    # 4. XỬ LÝ LOGIC GIỎ HÀNG VÀ KHUYẾN MÃI
    # Hàm này sẽ được gọi mỗi khi giỏ hàng thay đổi
    cart_state = pos_mgr.calculate_cart_state(
        cart_items=st.session_state.pos_cart,
        customer_id=st.session_state.pos_customer,
        manual_discount_input=st.session_state.pos_manual_discount
    )

    # 5. THIẾT KẾ BỐ CỤC 2 CỘT
    col_left, col_right = st.columns([2, 1])

    # =====================================================================================
    # CỘT TRÁI - THƯ VIỆN SẢN PHẨM
    # =====================================================================================
    with col_left:
        st.subheader("Thư viện Sản phẩm")

        # --- BỘ LỌC ---
        search_query = st.text_input("🔍 Tìm theo tên hoặc SKU", st.session_state.pos_search)
        st.session_state.pos_search = search_query

        cat_options = {cat['id']: cat['name'] for cat in all_categories}
        cat_options["ALL"] = "Tất cả danh mục"
        
        selected_cat = st.selectbox("Lọc theo danh mục", options=list(cat_options.keys()), format_func=lambda x: cat_options[x], key='pos_category')

        st.divider()

        # --- HIỂN THỊ SẢN PHẨM ---
        
        # Áp dụng bộ lọc
        filtered_products = [p for p in all_products if (search_query.lower() in p['name'].lower() or search_query.lower() in p['sku'].lower())]
        if selected_cat != "ALL":
            filtered_products = [p for p in filtered_products if p.get('category_id') == selected_cat]

        if not filtered_products:
            st.info("Không tìm thấy sản phẩm phù hợp.")
        else:
            # Chia thành các cột để hiển thị card
            product_cols = st.columns(3)
            col_index = 0
            for p in filtered_products:
                with product_cols[col_index]:
                    stock_quantity = branch_inventory.get(p['sku'], {}).get('stock_quantity', 0)
                    
                    # Chỉ hiển thị sản phẩm còn hàng
                    if stock_quantity > 0:
                        with st.container(border=True):
                            st.markdown(f"**{p['name']}**")
                            st.caption(f"SKU: {p['sku']}")
                            
                            price_display = f"{p.get('price_default', 0):,.0f} VNĐ"
                            st.markdown(f"<div style='text-align: right; color: #2E8B57; font-weight: bold;'>{price_display}</div>", unsafe_allow_html=True)

                            if st.button("➕ Thêm vào giỏ", key=f"add_{p['sku']}", use_container_width=True):
                                pos_mgr.add_item_to_cart(p, stock_quantity)
                                st.rerun()

                            st.caption(f"Tồn kho: {stock_quantity}")
                col_index = (col_index + 1) % 3

    # =====================================================================================
    # CỘT PHẢI - GIỎ HÀNG & THANH TOÁN
    # =====================================================================================
    with col_right:
        st.subheader("Đơn hàng")

        # --- CHỌN KHÁCH HÀNG ---
        customer_options = {c['id']: f"{c['name']} - {c['phone']}" for c in customers}
        customer_options["-"] = "Khách vãng lai"
        st.selectbox("👤 Khách hàng", options=list(customer_options.keys()), format_func=lambda x: customer_options[x], key='pos_customer')

        st.divider()

        # --- HIỂN THỊ GIỎ HÀNG ---
        if not cart_state['items']:
            st.info("Giỏ hàng đang trống")
        else:
            for sku, item in cart_state['items'].items():
                with st.container(border=True):
                    col_name, col_qty, col_price = st.columns([3,2,2])
                    with col_name:
                        st.markdown(f"**{item['name']}**")
                        if item['auto_discount_applied'] > 0:
                            st.markdown(f"<span style='color: green; font-size: 0.9em'>- {item['auto_discount_applied']:,.0f}đ (KM)</span>", unsafe_allow_html=True)

                    with col_qty:
                        # Nút tăng giảm số lượng
                        qty_col1, qty_col2, qty_col3 = st.columns([1,1,1])
                        if qty_col1.button("-", key=f"dec_{sku}"):
                            pos_mgr.update_item_quantity(sku, item['quantity'] - 1)
                            st.rerun()
                        qty_col2.write(f"{item['quantity']}")
                        if qty_col3.button("+", key=f"inc_{sku}"):
                            if item['quantity'] < item['stock']:
                                pos_mgr.update_item_quantity(sku, item['quantity'] + 1)
                                st.rerun()
                            else:
                                st.toast("Vượt quá tồn kho!")

                    with col_price:
                        st.markdown(f"<div style='text-align: right'>{item['line_total_after_auto_discount']:,.0f}đ</div>", unsafe_allow_html=True)
                        if item['auto_discount_applied'] > 0:
                            st.markdown(f"<div style='text-align: right; text-decoration: line-through; color: grey; font-size: 0.8em'>{item['original_line_total']:,.0f}đ</div>", unsafe_allow_html=True)


        st.divider()

        # --- TỔNG KẾT & GIẢM GIÁ THÊM ---
        if cart_state['items']:
            st.markdown(f"**Tổng tiền hàng:** <span style='float: right;'>{cart_state['subtotal']:,.0f}đ</span>", unsafe_allow_html=True)
            if cart_state['total_auto_discount'] > 0:
                st.markdown(f"**Giảm giá KM:** <span style='float: right; color: green;'>- {cart_state['total_auto_discount']:,.0f}đ</span>", unsafe_allow_html=True)
            
            # --- LOGIC GIẢM GIÁ THÊM ---
            promo = cart_state['active_promotion']
            if promo and promo['rules']['manual_extra_limit']['value'] > 0:
                if st.checkbox("Giảm giá thêm"):
                    limit = promo['rules']['manual_extra_limit']['value']
                    help_text = f"Nhân viên được phép giảm thêm tối đa {limit}% trên tổng đơn hàng."
                    if current_user['role'] != 'ADMIN':
                        help_text = "Nhập % hoặc số tiền giảm thêm được quản lý cho phép."

                    st.number_input(
                        "Nhập giảm giá thêm (%)", 
                        min_value=0.0, 
                        max_value=100.0, # Tạm thời không giới hạn ở front-end để test logic
                        step=1.0, 
                        key="pos_manual_discount_value",
                        help=help_text
                    )
                    # Cập nhật state để tính toán lại
                    st.session_state.pos_manual_discount['value'] = st.session_state.pos_manual_discount_value

            # Hiển thị giảm giá thêm nếu có
            if cart_state['total_manual_discount'] > 0:
                 st.markdown(f"**Giảm giá thêm:** <span style='float: right; color: orange;'>- {cart_state['total_manual_discount']:,.0f}đ</span>", unsafe_allow_html=True)
            
            # --- HIỂN THỊ CẢNH BÁO NẾU VƯỢT NGƯỠNG --- 
            if cart_state['manual_discount_exceeded']:
                st.warning("Mức giảm thêm vượt quá giới hạn cho phép của chương trình!")

            # --- TỔNG CUỐI CÙNG --- 
            st.markdown("###")
            st.markdown(f"### **KHÁCH CẦN TRẢ:** <span style='float: right; color: #D22B2B;'>{cart_state['grand_total']:,.0f}đ</span>", unsafe_allow_html=True)

            # --- NÚT THANH TOÁN --- 
            if st.button("💳 THANH TOÁN", use_container_width=True, type="primary"):
                if cart_state['manual_discount_exceeded']:
                    st.error("Không thể thanh toán. Mức giảm thêm không hợp lệ.")
                else:
                    success, message = pos_mgr.create_order(
                        cart_state=cart_state,
                        customer_id=st.session_state.pos_customer,
                        branch_id=current_branch_id,
                        seller_id=current_user['id']
                    )
                    if success:
                        st.success(f"Tạo đơn hàng thành công! ID: {message}")
                        # Reset state
                        del st.session_state.pos_cart
                        del st.session_state.pos_customer
                        del st.session_state.pos_manual_discount
                        st.rerun()
                    else:
                        st.error(f"Lỗi khi tạo đơn hàng: {message}")

            # --- NÚT XOÁ GIỎ HÀNG ---
            if st.button("🗑️ Xóa giỏ hàng", use_container_width=True):
                pos_mgr.clear_cart()
                st.rerun()

