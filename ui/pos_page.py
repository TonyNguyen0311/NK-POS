
import streamlit as st
import base64
from datetime import datetime
from ui._utils import render_page_title, render_section_header, render_sub_header, render_branch_selector
from utils.formatters import format_currency, format_number
import os

# --- State Management ---
def initialize_pos_state(branch_id):
    """Initializes or resets the session state for the POS page for a given branch."""
    branch_key = f"pos_{branch_id}"
    if st.session_state.get('current_pos_branch_key') != branch_key:
        st.session_state.pos_cart = {}
        st.session_state.pos_customer = "-"
        st.session_state.pos_search = ""
        st.session_state.pos_category = "ALL"
        st.session_state.pos_manual_discount = {"type": "PERCENT", "value": 0}
        st.session_state.current_pos_branch_key = branch_key

# --- UI Rendering Functions ---

@st.cache_data(show_spinner=False)
def get_image_as_base64(image_bytes):
    """Converts image bytes to a base64 encoded string."""
    return base64.b64encode(image_bytes).decode()

@st.cache_data(show_spinner=False)
def get_placeholder_image_b64():
    """Reads the placeholder image and returns its base64 representation."""
    try:
        placeholder_path = os.path.join("assets", "no-image.png")
        with open(placeholder_path, "rb") as f:
            return get_image_as_base64(f.read())
    except Exception:
        return None

def get_product_grid_styles():
    """Returns the CSS styles for the responsive product grid."""
    return """
    <style>
        /* Main grid container */
        .product-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 1.5rem;
        }

        /* Individual product card */
        .product-card {
            display: flex;
            flex-direction: column;
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 0.5rem;
            padding: 1rem;
            transition: box-shadow 0.3s ease;
            height: 100%; /* Ensure cards in a row have same height */
        }
        .product-card:hover {
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        /* Image container with fixed aspect ratio */
        .product-image-container {
            aspect-ratio: 1 / 1;
            width: 100%;
            border-radius: 0.25rem;
            overflow: hidden;
            margin-bottom: 0.75rem;
        }

        .product-image {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        /* Product title with line-clamp */
        .product-title {
            font-weight: bold;
            font-size: 1em;
            margin-bottom: 0.25rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
            height: 2.4em; /* Approx 2 lines height */
        }
        
        .product-details {
            flex-grow: 1; /* Pushes the button to the bottom */
            display: flex;
            flex-direction: column;
        }

        .product-price {
            color: #D22B2B;
            font-weight: bold;
            margin-bottom: 0.25rem;
        }

        .product-stock {
            font-size: 0.85em;
            color: #555;
            flex-grow: 1; /* Takes up available space to push button down */
            margin-bottom: 0.75rem;
        }

        /* Custom 'Add to Cart' button styled as a link */
        .add-to-cart-btn {
            display: block;
            text-align: center;
            background-color: #0068c9; /* Streamlit primary color */
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            text-decoration: none;
            transition: background-color 0.3s ease;
            border: 1px solid #0068c9;
        }
        .add-to-cart-btn:hover {
            background-color: #0055a8;
            color: white;
        }
    </style>
    """

def render_product_gallery(pos_mgr, product_mgr, inventory_mgr, branch_id):
    """Displays a fully responsive product grid using HTML/CSS within st.markdown."""
    render_section_header("Thư viện Sản phẩm")
    
    # Inject CSS styles
    st.markdown(get_product_grid_styles(), unsafe_allow_html=True)
    
    # 1. Filters
    search_query = st.text_input("🔍 Tìm theo tên hoặc SKU", st.session_state.get("pos_search", ""), key="pos_search_input", label_visibility="collapsed")
    st.session_state.pos_search = search_query

    all_categories = product_mgr.get_all_category_items("ProductCategories")
    cat_options = {cat['id']: cat['category_name'] for cat in all_categories}
    cat_options["ALL"] = "Tất cả danh mục"
    selected_cat = st.selectbox("Lọc theo danh mục", options=list(cat_options.keys()), format_func=lambda x: cat_options.get(x, "N/A"), key='pos_category')
    st.divider()

    # 2. Product Data Fetching & Filtering
    branch_products = product_mgr.get_listed_products_for_branch(branch_id)
    branch_inventory = inventory_mgr.get_inventory_by_branch(branch_id)

    filtered_products = [p for p in branch_products if (search_query.lower() in p['name'].lower() or search_query.lower() in p.get('sku', '').lower())]
    if selected_cat != "ALL":
        filtered_products = [p for p in filtered_products if p.get('category_id') == selected_cat]

    # 3. Grid Rendering using HTML/CSS
    if not filtered_products:
        st.info("Không tìm thấy sản phẩm phù hợp.")
    else:
        placeholder_b64 = get_placeholder_image_b64()
        
        # Start the grid
        html_cards = '<div class="product-grid">'

        for p in filtered_products:
            sku = p.get('sku')
            if not sku: continue

            stock_quantity = branch_inventory.get(sku, {}).get('stock_quantity', 0)
            if stock_quantity <= 0: continue

            # --- Get Image ---
            image_b64 = placeholder_b64
            image_id = p.get('image_id')
            if image_id and product_mgr.image_handler:
                img_bytes = product_mgr.image_handler.load_drive_image(image_id)
                if img_bytes:
                    image_b64 = get_image_as_base64(img_bytes)
            
            image_src = f"data:image/png;base64,{image_b64}" if image_b64 else ""

            # --- Get Price ---
            selling_price = p.get('selling_price', 0)
            
            # --- Build HTML for one card ---
            html_cards += f'''
            <div class="product-card">
                <div class="product-image-container">
                    <img src="{image_src}" class="product-image">
                </div>
                <div class="product-details">
                    <div class="product-title">{p['name']}</div>
                    <div class="product-price">{format_currency(selling_price, 'đ')}</div>
                    <div class="product-stock">Tồn kho: {format_number(stock_quantity)}</div>
                    <a href="?add_to_cart={sku}" target="_self" class="add-to-cart-btn">➕ Thêm vào giỏ</a>
                </div>
            </div>
            '''

        # Close the grid
        html_cards += '</div>'
        st.markdown(html_cards, unsafe_allow_html=True)


def render_cart_view(cart_state, pos_mgr, product_mgr):
    """Displays the items currently in the cart."""
    render_section_header(f"Đơn hàng ({cart_state['total_items']} món)")

    if not cart_state['items']:
        st.info("Giỏ hàng đang trống.")
        return

    with st.container(height=300):
        for sku, item in cart_state['items'].items():
            with st.container():
                col_img, col_details = st.columns([1, 4])
                with col_img:
                    # Optimized image loading for cart
                    image_id = item.get('image_id')
                    image_data = "assets/no-image.png" 
                    if image_id and product_mgr.image_handler:
                         loaded_data = product_mgr.image_handler.load_drive_image(image_id)
                         if loaded_data:
                            image_data = loaded_data
                    st.image(image_data, width=60)


                with col_details:
                    st.markdown(f"**{item['name']}** (`{sku}`)")
                    price_col, qty_col = st.columns([2, 1])
                    with price_col:
                        st.markdown(f"Thành tiền: **{format_currency(item['line_total_after_auto_discount'], 'đ')}**")
                        if item['auto_discount_applied'] > 0:
                            st.markdown(f"<small style='color: green; text-decoration: line-through;'>*Cũ: {format_currency(item['original_line_total'], 'đ')}*</small>", unsafe_allow_html=True)
                    with qty_col:
                        q_c1, q_c2, q_c3 = st.columns([1, 1, 1])
                        if q_c1.button("−", key=f"dec_{sku}", use_container_width=True):
                            pos_mgr.update_item_quantity(sku, item['quantity'] - 1)
                            st.rerun()
                        q_c2.write(f"<div style='text-align: center; padding-top: 5px'>{format_number(item['quantity'])}</div>", unsafe_allow_html=True)
                        if q_c3.button("＋", key=f"inc_{sku}", use_container_width=True):
                            if item['quantity'] < item['stock']:
                                pos_mgr.update_item_quantity(sku, item['quantity'] + 1)
                                st.rerun()
                            else:
                                st.toast("Vượt quá tồn kho!", icon="⚠️")
            st.divider()

def render_checkout_panel(cart_state, customer_mgr, pos_mgr, branch_id):
    """Displays the customer selection, summary, and checkout button."""
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
            st.rerun()

        if c2.button("🗑️ Xóa giỏ hàng", use_container_width=True):
            pos_mgr.clear_cart()
            st.toast("Đã xóa giỏ hàng", icon="🗑️")
            st.rerun()

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

def handle_add_to_cart_action(pos_mgr, product_mgr, inventory_mgr, branch_id):
    """Checks for 'add_to_cart' in URL query_params and handles the action."""
    if 'add_to_cart' in st.query_params:
        sku_to_add = st.query_params['add_to_cart']
        
        # Find the product and its stock quantity
        product = product_mgr.get_product_by_sku(sku_to_add)
        stock_quantity = inventory_mgr.get_inventory_by_branch(branch_id).get(sku_to_add, {}).get('stock_quantity', 0)

        if product and stock_quantity > 0:
            pos_mgr.add_item_to_cart(branch_id, product, stock_quantity)
            st.toast(f"Đã thêm '{product['name']}' vào giỏ!", icon="🛒")
        
        # Clean up URL and rerun
        st.query_params.clear()
        st.rerun()

# --- Main Page Rendering ---
def render_pos_page(pos_mgr):
    render_page_title("Bán hàng tại quầy (POS)")

    # --- Initialize Managers & State ---
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
    
    # --- Handle URL-based Actions ---
    handle_add_to_cart_action(pos_mgr, product_mgr, inventory_mgr, selected_branch_id)

    # --- Cart Calculation ---
    cart_state = pos_mgr.calculate_cart_state(
        cart_items=st.session_state.get('pos_cart', {}),
        customer_id=st.session_state.get('pos_customer', "-"),
        manual_discount_input=st.session_state.get('pos_manual_discount', {"type": "PERCENT", "value": 0})
    )

    # --- Page Layout ---
    main_col, order_col = st.columns([0.6, 0.4])

    with main_col:
        render_product_gallery(pos_mgr, product_mgr, inventory_mgr, selected_branch_id)

    with order_col:
        render_cart_view(cart_state, pos_mgr, product_mgr)
        render_checkout_panel(cart_state, customer_mgr, pos_mgr, selected_branch_id)

    if st.session_state.get('show_confirm_dialog', False):
        confirm_checkout_dialog(cart_state, pos_mgr, selected_branch_id)
