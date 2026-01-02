
import streamlit as st
from datetime import datetime
from ui._utils import render_page_header, render_branch_selector

# --- State Management ---
def initialize_pos_state(branch_id):
    """Initializes or resets the session state for the POS page for a given branch."""
    # Use a branch-specific key to store the cart and other POS-related states.
    # This prevents the cart from persisting when the user switches branches.
    branch_key = f"pos_{branch_id}"
    if st.session_state.get('current_pos_branch_key') != branch_key:
        st.session_state.pos_cart = {}
        st.session_state.pos_customer = "-"
        st.session_state.pos_search = ""
        st.session_state.pos_category = "ALL"
        st.session_state.pos_manual_discount = {"type": "PERCENT", "value": 0}
        st.session_state.current_pos_branch_key = branch_key
        st.rerun() # Rerun to ensure the UI updates with the new branch state

# --- UI Rendering Functions ---

def render_product_gallery(pos_mgr, product_mgr, inventory_mgr, branch_id):
    """Displays the product search, filter, and gallery."""
    
    with st.container(border=False):
        # 1. Filters
        search_query = st.text_input("🔍 Tìm theo tên hoặc SKU", st.session_state.pos_search, key="pos_search_input")
        
        all_categories = product_mgr.get_categories()
        cat_options = {cat['id']: cat['name'] for cat in all_categories}
        cat_options["ALL"] = "Tất cả danh mục"
        selected_cat = st.selectbox("Lọc theo danh mục", options=list(cat_options.keys()), format_func=lambda x: cat_options[x], key='pos_category')
        st.divider()

        # 2. Product Listing
        branch_products = product_mgr.get_listed_products_for_branch(branch_id)
        branch_inventory = inventory_mgr.get_inventory_by_branch(branch_id)

        filtered_products = [p for p in branch_products if (search_query.lower() in p['name'].lower() or search_query.lower() in p.get('sku', '').lower())]
        if selected_cat != "ALL":
            filtered_products = [p for p in filtered_products if p.get('category_id') == selected_cat]

        if not filtered_products:
            st.info("Không tìm thấy sản phẩm phù hợp.")
        else:
            # Display products in a grid
            cols = st.columns(4) # More columns for a denser gallery
            for i, p in enumerate(filtered_products):
                col = cols[i % 4]
                sku = p.get('sku')
                if not sku: continue

                stock_quantity = branch_inventory.get(sku, {}).get('quantity', 0)
                if stock_quantity > 0:
                    with col.container(border=True):
                        if p.get('image_url'):
                            st.image(p['image_url'], use_column_width=True)
                        
                        col.markdown(f"**{p['name']}**")
                        col.caption(f"SKU: {sku} | Tồn: {stock_quantity}")

                        if col.button("➕ Thêm", key=f"add_{sku}", use_container_width=True, type="primary"):
                            pos_mgr.add_item_to_cart(branch_id, p, stock_quantity)
                            st.rerun()


def render_cart_view(cart_state, pos_mgr):
    """Displays the items currently in the cart."""
    if not cart_state['items']:
        st.info("Giỏ hàng đang trống. Hãy chọn sản phẩm từ Thư viện.")
        return

    for sku, item in cart_state['items'].items():
        with st.container(border=True):
            col_img, col_details = st.columns([1, 4])
            with col_img:
                if item.get('image_url'):
                    st.image(item['image_url'], width=60)
                else:
                    st.image("https://via.placeholder.com/60", width=60) # Placeholder

            with col_details:
                st.markdown(f"**{item['name']}** (`{sku}`)")
                
                # Price and discounts
                price_col, qty_col = st.columns([2,1])
                with price_col:
                    st.markdown(f"Thành tiền: **{item['line_total_after_auto_discount']:,.0f}đ**")
                    if item['auto_discount_applied'] > 0:
                        st.markdown(f"<small style='color: green; text-decoration: line-through;'>*Cũ: {item['original_line_total']:,.0f}đ*</small>", unsafe_allow_html=True)
                
                # Quantity controls
                with qty_col:
                    q_c1, q_c2, q_c3 = st.columns([1,1,1])
                    if q_c1.button("−", key=f"dec_{sku}", use_container_width=True):
                        pos_mgr.update_item_quantity(sku, item['quantity'] - 1)
                        st.rerun()
                    q_c2.write(f"<div style='text-align: center; padding-top: 5px'>{item['quantity']}</div>", unsafe_allow_html=True)
                    if q_c3.button("＋", key=f"inc_{sku}", use_container_width=True):
                        if item['quantity'] < item['stock']:
                            pos_mgr.update_item_quantity(sku, item['quantity'] + 1)
                            st.rerun()
                        else:
                            st.toast("Vượt quá tồn kho!", icon="⚠️")


def render_checkout_panel(cart_state, customer_mgr, pos_mgr, branch_id):
    """Displays the customer selection, summary, and checkout button."""
    with st.container(border=True):
        # 1. Customer Selection
        customers = customer_mgr.list_customers()
        customer_options = {c['id']: f"{c['name']} ({c['phone']})" for c in customers}
        customer_options["-"] = "Khách vãng lai"
        st.selectbox("👤 **Khách hàng**", options=list(customer_options.keys()), format_func=lambda x: customer_options[x], key='pos_customer')
        st.divider()

        # 2. Order Summary
        st.markdown(f"Tổng tiền hàng: <span style='float: right;'>{cart_state['subtotal']:,.0f}đ</span>", unsafe_allow_html=True)
        if cart_state['total_auto_discount'] > 0:
            st.markdown(f"<span style='color: green;'>Giảm giá KM:</span> <span style='float: right; color: green;'>- {cart_state['total_auto_discount']:,.0f}đ</span>", unsafe_allow_html=True)
        
        # Manual Discount Section (Placeholder for future development)
        # For now, we keep it simple

        st.markdown("---_", help="") # A slightly thicker divider
        st.markdown(f"### **KHÁCH CẦN TRẢ:** <span style='float: right; color: #D22B2B;'>{cart_state['grand_total']:,.0f}đ</span>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        # 3. Action Buttons
        c1, c2 = st.columns(2)
        if c1.button("💳 THANH TOÁN", use_container_width=True, type="primary"):
            st.session_state.show_confirm_dialog = True
            st.rerun()
        
        if c2.button("🗑️ Xóa giỏ hàng", use_container_width=True):
            pos_mgr.clear_cart()
            st.toast("Đã xóa giỏ hàng", icon="🗑️")
            st.rerun()


@st.dialog("Xác nhận thanh toán")
def confirm_checkout_dialog(cart_state, pos_mgr, branch_id):
    """A dialog to confirm the order before final submission."""
    st.write("Vui lòng xác nhận lại thông tin đơn hàng trước khi thanh toán.")
    
    # Display a mini summary
    st.markdown(f"- **Tổng cộng:** {len(cart_state['items'])} loại sản phẩm")
    st.markdown(f"- **Tổng tiền hàng:** {cart_state['subtotal']:,.0f}đ")
    st.markdown(f"- **Tổng cộng giảm:** {cart_state['total_auto_discount'] + cart_state['total_manual_discount']:,.0f}đ")
    st.markdown(f"- **Khách cần trả:** **{cart_state['grand_total']:,.0f}đ**")
    st.divider()

    if st.button("✅ Xác nhận & In hóa đơn", use_container_width=True, type="primary"):
        current_user = st.session_state.user
        success, message = pos_mgr.create_order(
            cart_state=cart_state,
            customer_id=st.session_state.pos_customer,
            branch_id=branch_id,
            seller_id=current_user['uid']
        )
        if success:
            st.success(f"Tạo đơn hàng thành công! ID: {message}")
            pos_mgr.clear_cart()
            st.session_state.show_confirm_dialog = False
            st.rerun()
        else:
            st.error(f"Lỗi: {message}")

    if st.button("Hủy", use_container_width=True):
        st.session_state.show_confirm_dialog = False
        st.rerun()

# --- Main Page Rendering ---
def render_pos_page(pos_mgr):
    render_page_header("Bán hàng tại quầy", "🛒")
    
    # Get managers
    auth_mgr = st.session_state.auth_mgr
    branch_mgr = st.session_state.branch_mgr
    product_mgr = st.session_state.product_mgr
    inventory_mgr = st.session_state.inventory_mgr
    customer_mgr = st.session_state.customer_mgr
    
    # 1. BRANCH SELECTION
    user_info = auth_mgr.get_current_user_info()
    allowed_branches_map = auth_mgr.get_allowed_branches_map()
    if not allowed_branches_map:
        st.error("Tài khoản của bạn chưa được gán vào chi nhánh nào.")
        st.stop()

    selected_branch_id = render_branch_selector(allowed_branches_map, user_info.get('default_branch_id'))
    if not selected_branch_id:
        st.stop()

    # 2. INITIALIZE STATE FOR THE SELECTED BRANCH
    initialize_pos_state(selected_branch_id)

    # 3. CALCULATE CURRENT CART STATE
    cart_state = pos_mgr.calculate_cart_state(
        cart_items=st.session_state.get('pos_cart', {}),
        customer_id=st.session_state.get('pos_customer', "-"),
        manual_discount_input=st.session_state.get('pos_manual_discount', {"type": "PERCENT", "value": 0})
    )

    # 4. DEFINE LAYOUT: Main area and a sidebar for the order
    main_col, order_col = st.columns([0.6, 0.4])

    with main_col:
        # Tabs for Product Gallery and Current Order View
        tab_gallery, tab_cart = st.tabs(["Thư viện Sản phẩm", f"Đơn hàng ({cart_state['total_items']})"])
        with tab_gallery:
            render_product_gallery(pos_mgr, product_mgr, inventory_mgr, selected_branch_id)
        with tab_cart:
            render_cart_view(cart_state, pos_mgr)

    with order_col:
        render_checkout_panel(cart_state, customer_mgr, pos_mgr, selected_branch_id)

    # 5. DIALOG FOR CHECKOUT CONFIRMATION
    if st.session_state.get('show_confirm_dialog', False):
        confirm_checkout_dialog(cart_state, pos_mgr, selected_branch_id)
