
import streamlit as st
import base64
from datetime import datetime
from ui._utils import render_page_title, render_section_header, render_sub_header, render_branch_selector, inject_custom_css
from utils.formatters import format_currency, format_number
import os

# --- State Management & Callbacks ---

def initialize_pos_state(branch_id):
    """Initializes or resets the POS state when the branch changes."""
    branch_key = f"pos_{branch_id}"
    if st.session_state.get('current_pos_branch_key') != branch_key:
        st.session_state.pos_cart = {}
        st.session_state.pos_customer = "-"
        st.session_state.pos_search = ""
        st.session_state.pos_category = "ALL"
        st.session_state.pos_manual_discount = {"type": "PERCENT", "value": 0}
        st.session_state.current_pos_branch_key = branch_key

def add_to_cart_callback(pos_mgr, branch_id, product_data, stock_quantity):
    """Callback function to add an item to the cart. No rerun needed."""
    pos_mgr.add_item_to_cart(branch_id, product_data, stock_quantity)
    st.toast(f"Đã thêm '{product_data['name']}' vào giỏ!", icon="🛒")

# --- UI Rendering & Asset Functions ---

@st.cache_data(show_spinner=False, ttl=3600)
def get_placeholder_image_b64():
    """Loads the placeholder image and returns its Base64 encoding."""
    try:
        with open(os.path.join("assets", "no-image.png"), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def get_product_image_b64(_product_mgr, image_id):
    """Loads a product image from Google Drive and returns its Base64 encoding."""
    if not image_id or not _product_mgr.image_handler: return None
    try:
        img_bytes = _product_mgr.image_handler.load_drive_image(image_id)
        if img_bytes:
            mime_type = "image/png" if img_bytes.startswith(b'\x89PNG') else "image/jpeg"
            return f"data:{mime_type};base64,{base64.b64encode(img_bytes).decode()}"
    except Exception as e:
        st.error(f"Lỗi tải ảnh: {e}")
    return None

def render_product_gallery(product_mgr, inventory_mgr, pos_mgr, branch_id):
    render_section_header("Thư viện Sản phẩm")
    
    # --- Filter Bar ---
    filter_col1, filter_col2 = st.columns([0.6, 0.4])
    with filter_col1:
        search_query = st.text_input("🔍 Tìm theo tên hoặc SKU", st.session_state.get("pos_search", ""), key="pos_search", label_visibility="collapsed", placeholder="Tìm sản phẩm...")

    all_categories = product_mgr.get_all_category_items("ProductCategories")
    cat_options = {cat['id']: cat['category_name'] for cat in all_categories}
    cat_options["ALL"] = "Tất cả danh mục"
    with filter_col2:
        selected_cat = st.selectbox("Lọc theo danh mục", options=list(cat_options.keys()), format_func=lambda x: cat_options.get(x, "N/A"), key='pos_category', label_visibility="collapsed")
    
    st.divider()

    # --- Product Data Fetching ---
    branch_products = product_mgr.get_listed_products_for_branch(branch_id)
    branch_inventory = inventory_mgr.get_inventory_by_branch(branch_id)

    # --- Filtering Logic ---
    filtered_products = [p for p in branch_products if (search_query.lower() in p['name'].lower() or search_query.lower() in p.get('sku', '').lower())]
    if selected_cat != "ALL":
        filtered_products = [p for p in filtered_products if p.get('category_id') == selected_cat]

    # --- Grid Rendering ---
    if not filtered_products:
        st.info("Không tìm thấy sản phẩm nào phù hợp với lựa chọn của bạn.")
    else:
        placeholder_b64 = f"data:image/png;base64,{get_placeholder_image_b64()}"
        cols = st.columns(4)
        for i, p in enumerate(filtered_products):
            sku = p.get('sku')
            if not sku: continue

            stock_quantity = branch_inventory.get(sku, {}).get('stock_quantity', 0)
            if stock_quantity <= 0: continue

            with cols[i % 4]:
                with st.container(border=True):
                    image_src = get_product_image_b64(product_mgr, p.get('image_id')) or placeholder_b64
                    st.image(image_src)
                    st.markdown(f"<div class='product-title'>{p['name']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='product-price'>{format_currency(p.get('selling_price', 0), 'đ')}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='product-stock'>Tồn kho: {format_number(stock_quantity)}</div>", unsafe_allow_html=True)
                    
                    st.button(
                        "➕ Thêm", 
                        key=f"add_{sku}", 
                        use_container_width=True, 
                        on_click=add_to_cart_callback, 
                        args=(pos_mgr, branch_id, p, stock_quantity)
                    )

def render_cart_view(cart_state, pos_mgr, product_mgr):
    render_section_header(f"Đơn hàng ({cart_state['total_items']} món)")

    if not cart_state['items']:
        st.info("Giỏ hàng đang trống.")
        return

    with st.container(height=300):
        for sku, item in cart_state['items'].items():
            with st.container():
                col_img, col_details = st.columns([1, 4])
                with col_img:
                    image_src = get_product_image_b64(product_mgr, item.get('image_id'))
                    st.image(image_src or "assets/no-image.png", width=60)

                with col_details:
                    st.markdown(f"**{item['name']}** (`{sku}`)")
                    price_col, qty_col = st.columns([2, 1])
                    with price_col:
                        st.markdown(f"Thành tiền: **{format_currency(item['line_total_after_auto_discount'], 'đ')}**")
                        if item['auto_discount_applied'] > 0:
                            st.markdown(f"<small style='color: green; text-decoration: line-through;'>*Cũ: {format_currency(item['original_line_total'], 'đ')}*</small>", unsafe_allow_html=True)
                    with qty_col:
                        q_c1, q_c2, q_c3 = st.columns([1, 1, 1])
                        if q_c1.button("−", key=f"dec_{sku}", use_container_width=True, on_click=pos_mgr.update_item_quantity, args=(sku, item['quantity'] - 1)):
                            pass # Callback handles it
                        q_c2.write(f"<div style='text-align: center; padding-top: 5px'>{format_number(item['quantity'])}</div>", unsafe_allow_html=True)
                        if q_c3.button("＋", key=f"inc_{sku}", use_container_width=True, on_click=pos_mgr.update_item_quantity, args=(sku, item['quantity'] + 1)):
                             if item['quantity'] >= item['stock']:
                                 st.toast("Vượt quá tồn kho!", icon="⚠️")
            st.divider()

def render_checkout_panel(cart_state, customer_mgr, pos_mgr, branch_id):
    with st.container(border=True):
        render_section_header("Thanh Toán")
        customers = customer_mgr.list_customers()
        customer_options = {c['id']: f"{c['name']} ({c['phone']})" for c in customers}
        customer_options["-"] = "Khách vãng lai"
        st.selectbox("👤 **Khách hàng**", options=list(customer_options.keys()), format_func=lambda x: customer_options.get(x, "N/A"), key='pos_customer')
        st.divider()

        render_sub_header("Tổng kết đơn hàng")
        st.markdown(f"Tổng tiền hàng: <span style='float: right;'>{format_currency(cart_state['subtotal'], 'đ')}</span>", unsafe_allow_html=True)
        if cart_state['total_auto_discount'] > 0:
            st.markdown(f"<span style='color: green;'>Giảm giá KM:</span> <span style='float: right; color: green;'>- {format_currency(cart_state['total_auto_discount'], 'đ')}</span>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"<h3 class='sub-header'>Cần thanh toán: <span style='float: right; color: #D22B2B;'>{format_currency(cart_state['grand_total'], 'đ')}</span></h3>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        if c1.button("💳 THANH TOÁN", use_container_width=True, type="primary", disabled=(not cart_state['items'])):
            st.session_state.show_confirm_dialog = True
            st.rerun() # Rerun to open dialog

        if c2.button("🗑️ Xóa giỏ hàng", use_container_width=True, on_click=pos_mgr.clear_cart):
            st.toast("Đã xóa giỏ hàng", icon="🗑️")
            # No rerun needed here, clear_cart changes state and Streamlit reruns automatically

@st.dialog("Xác nhận thanh toán")
def confirm_checkout_dialog(cart_state, pos_mgr, branch_id):
    render_section_header("Xác nhận đơn hàng")
    st.write("Vui lòng kiểm tra lại thông tin trước khi hoàn tất.")
    st.markdown(f"- **Tổng cộng:** {format_number(len(cart_state['items']))} loại sản phẩm")
    st.markdown(f"- **Tổng tiền hàng:** {format_currency(cart_state['subtotal'], 'đ')}")
    total_discount = cart_state['total_auto_discount'] + cart_state.get('total_manual_discount', 0)
    st.markdown(f"- **Tổng cộng giảm:** {format_currency(total_discount, 'đ')}")
    st.markdown(f"- **Khách cần trả:** **{format_currency(cart_state['grand_total'], 'đ')}**")
    st.divider()

    if st.button("✅ Xác nhận & In hóa đơn", use_container_width=True, type="primary"):
        current_user = st.session_state.user
        with st.spinner("Đang xử lý đơn hàng..."):
            st.session_state.inventory_mgr._clear_caches()
            success, message = pos_mgr.create_order(cart_state=cart_state, customer_id=st.session_state.pos_customer, branch_id=branch_id, seller_id=current_user['uid'])
        if success:
            st.success(f"Tạo đơn hàng thành công! ID: {message}")
            # We don't need to call clear_cart here, it will be reset on rerun by initialize_pos_state logic if needed
            st.session_state.inventory_mgr._clear_caches()
            st.session_state.show_confirm_dialog = False
            st.rerun() # Rerun to close dialog and refresh UI
        else:
            st.error(f"Lỗi: {message}")
            st.session_state.inventory_mgr._clear_caches()

    if st.button("Hủy", use_container_width=True):
        st.session_state.show_confirm_dialog = False
        st.rerun() # Rerun to close dialog


# --- Main Page Rendering ---
def render_pos_page(pos_mgr):
    render_page_title("Bán hàng tại quầy (POS)")
    inject_custom_css()

    # Managers & State
    auth_mgr = st.session_state.auth_mgr
    branch_mgr = st.session_state.branch_mgr
    product_mgr = st.session_state.product_mgr
    inventory_mgr = st.session_state.inventory_mgr
    customer_mgr = st.session_state.customer_mgr

    user_info = auth_mgr.get_current_user_info()
    allowed_branches_map = auth_mgr.get_allowed_branches_map()
    if not allowed_branches_map:
        st.error("Tài khoản của bạn chưa được gán vào chi nhánh nào.")
        st.stop()

    selected_branch_id = render_branch_selector(allowed_branches_map, user_info.get('default_branch_id'))
    if not selected_branch_id:
        st.stop()

    initialize_pos_state(selected_branch_id)
    
    # Calculations (now much simpler)
    cart_state = pos_mgr.calculate_cart_state(st.session_state.get('pos_cart', {}), st.session_state.get('pos_customer', "-"), st.session_state.get('pos_manual_discount', {}))

    # Page Layout
    main_col, order_col = st.columns([0.6, 0.4])
    with main_col:
        render_product_gallery(product_mgr, inventory_mgr, pos_mgr, selected_branch_id)
    with order_col:
        render_cart_view(cart_state, pos_mgr, product_mgr)
        render_checkout_panel(cart_state, customer_mgr, pos_mgr, selected_branch_id)

    if st.session_state.get('show_confirm_dialog', False):
        confirm_checkout_dialog(cart_state, pos_mgr, selected_branch_id)
