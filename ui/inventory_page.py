
import streamlit as st
import pandas as pd
from datetime import datetime

# Import managers
from managers.inventory_manager import InventoryManager
from managers.product_manager import ProductManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager, hash_auth_manager

# Import formatters and UI utils
from ui._utils import render_page_title, render_section_header, render_sub_header, render_branch_selector
from utils.formatters import format_number, format_currency

def init_session_state():
    """Initializes session state keys for the inventory page."""
    if 'active_inventory_tab' not in st.session_state:
        st.session_state.active_inventory_tab = "📊 Tình hình Tồn kho"
    if 'voucher_items' not in st.session_state:
        st.session_state.voucher_items = []
    if 'voucher_type' not in st.session_state:
        st.session_state.voucher_type = "Phiếu Nhập hàng"

def render_inventory_page(inv_mgr: InventoryManager, prod_mgr: ProductManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    render_page_title("Quản lý Tồn kho")
    init_session_state()

    # --- User and Branch Management ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
        return

    user_role = user_info.get('role', 'staff')
    user_branches = user_info.get('branch_ids', [])
    default_branch_id = user_info.get('default_branch_id')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}
    allowed_branches_map = {bid: all_branches_map[bid] for bid in user_branches if bid in all_branches_map} if user_role != 'admin' else all_branches_map

    selected_branch = render_branch_selector(allowed_branches_map, default_branch_id)
    if not selected_branch:
        return
    
    st.divider()

    # --- Data Loading ---
    @st.cache_data(ttl=60)
    def load_data(branch_id):
        all_products = prod_mgr.get_all_products(active_only=False)
        branch_inventory = inv_mgr.get_inventory_by_branch(branch_id)
        return all_products, branch_inventory

    with st.spinner("Đang tải dữ liệu sản phẩm và kho..."):
        all_products, branch_inventory = load_data(selected_branch)
        product_map = {p['sku']: p for p in all_products if 'sku' in p}
        product_options = {p['sku']: f"{p['name']} ({p['sku']})" for p in all_products if 'sku' in p}

    # --- Custom Tab Navigation ---
    tabs = ["📊 Tình hình Tồn kho", "📝 Tạo Chứng từ", "📜 Lịch sử Chứng từ"]
    st.session_state.active_inventory_tab = st.radio(
        "Chức năng:", tabs, horizontal=True, label_visibility="collapsed",
        key="inventory_tab_selector"
    )

    # --- TAB 1: CURRENT INVENTORY ---
    if st.session_state.active_inventory_tab == "📊 Tình hình Tồn kho":
        render_section_header(f"Tồn kho hiện tại của: {allowed_branches_map[selected_branch]}")
        if not branch_inventory:
            st.info("Chưa có sản phẩm nào trong kho của chi nhánh này.")
        else:
            inventory_list = []
            for sku, inv_data in branch_inventory.items():
                prod_info = product_map.get(sku, {})
                inventory_list.append({
                    'Tên sản phẩm': prod_info.get('name', f'Không rõ (SKU: {sku})'),
                    'SKU': sku,
                    'Số lượng': inv_data.get('stock_quantity', 0),
                    'Giá vốn BQ': inv_data.get('average_cost', 0),
                    'Giá trị Kho': inv_data.get('stock_quantity', 0) * inv_data.get('average_cost', 0)
                })
            
            if inventory_list:
                inventory_df = pd.DataFrame(inventory_list)
                st.dataframe(
                    inventory_df.style.format({
                        'Số lượng': format_number,
                        'Giá vốn BQ': lambda x: format_currency(x, 'VND'),
                        'Giá trị Kho': lambda x: format_currency(x, 'VND')
                    }),
                    use_container_width=True, hide_index=True
                )
            else:
                 st.info("Chưa có sản phẩm nào trong kho của chi nhánh này.")


    # --- TAB 2: VOUCHER CREATION ---
    elif st.session_state.active_inventory_tab == "📝 Tạo Chứng từ":
        render_section_header("Tạo Chứng từ Kho")
        
        voucher_type = st.radio(
            "Chọn loại chứng từ:", ["Phiếu Nhập hàng", "Phiếu Điều chỉnh kho"],
            horizontal=True, key="voucher_type_selector",
            on_change=lambda: st.session_state.update(voucher_items=[])
        )
        st.session_state.voucher_type = voucher_type

        with st.form("add_item_form", clear_on_submit=True):
            render_sub_header("Thêm sản phẩm vào chứng từ")
            c1, c2 = st.columns([2, 1])
            selected_sku = c1.selectbox("Chọn sản phẩm", options=list(product_options.keys()), format_func=lambda x: product_options.get(x, x), key="item_sku")
            
            if voucher_type == "Phiếu Nhập hàng":
                quantity = c2.number_input("Số lượng nhập", min_value=1, step=1, key="item_qty")
                purchase_price = st.number_input("Giá nhập (trên 1 đơn vị)", min_value=0, step=1000, key="item_price")
            else: 
                current_stock_item = inv_mgr.get_inventory_item(selected_sku, selected_branch)
                current_qty = current_stock_item.get('stock_quantity', 0) if current_stock_item else 0
                c2.info(f"Tồn hiện tại: {current_qty}")
                quantity = st.number_input("Số lượng thực tế", min_value=0, step=1, key="item_qty")

            if st.form_submit_button("Thêm vào phiếu", use_container_width=True):
                if selected_sku:
                    item_data = {'sku': selected_sku, 'name': product_map[selected_sku]['name']}
                    if voucher_type == "Phiếu Nhập hàng":
                        item_data.update({'quantity': quantity, 'purchase_price': purchase_price})
                    else:
                        item_data.update({'actual_quantity': quantity})
                    st.session_state.voucher_items.append(item_data)
        
        st.divider()

        if st.session_state.voucher_items:
            render_sub_header("Các sản phẩm trong phiếu:")
            df_items = pd.DataFrame(st.session_state.voucher_items)
            st.dataframe(df_items, use_container_width=True, hide_index=True)

            with st.form("create_voucher_form"):
                if voucher_type == "Phiếu Nhập hàng":
                    render_sub_header("Thông tin Phiếu Nhập hàng")
                    c1, c2 = st.columns(2)
                    receipt_date = c1.date_input("Ngày nhập hàng", value=datetime.now(), help="Ngày chứng từ có hiệu lực. Mặc định là hôm nay.")
                    supplier = c2.text_input("Nhà cung cấp")
                    notes = st.text_area("Ghi chú chung")
                    
                    b1, b2 = st.columns(2)
                    submit_button = b1.form_submit_button("Xác nhận Tạo Phiếu Nhập", use_container_width=True, type="primary")
                    cancel_button = b2.form_submit_button("Hủy Giao Dịch", use_container_width=True)

                    if cancel_button:
                        st.session_state.voucher_items = []
                        st.rerun()

                    if submit_button:
                        with st.spinner("Đang tạo phiếu nhập hàng..."):
                            try:
                                voucher_id = inv_mgr.create_goods_receipt(
                                    branch_id=selected_branch, user_id=user_info['uid'],
                                    items=st.session_state.voucher_items, supplier=supplier,
                                    notes=notes, receipt_date=receipt_date
                                )
                                st.success(f"Tạo phiếu nhập hàng {voucher_id} thành công!")
                                st.session_state.voucher_items = []
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi khi tạo phiếu nhập: {e}")

                else: 
                    render_sub_header("Thông tin Phiếu Điều chỉnh kho")
                    c1, c2 = st.columns(2)
                    adjustment_date = c1.date_input("Ngày điều chỉnh", value=datetime.now(), help="Ngày chứng từ có hiệu lực. Mặc định là hôm nay.")
                    reason = c2.selectbox("Lý do điều chỉnh", ["Kiểm kê định kỳ", "Hàng hỏng", "Mất mát", "Khác"])
                    notes = st.text_area("Ghi chú chung cho phiếu điều chỉnh")
                    
                    b1, b2 = st.columns(2)
                    submit_button = b1.form_submit_button("Xác nhận Tạo Phiếu Điều chỉnh", use_container_width=True, type="primary")
                    cancel_button = b2.form_submit_button("Hủy Giao Dịch", use_container_width=True)

                    if cancel_button:
                        st.session_state.voucher_items = []
                        st.rerun()

                    if submit_button:
                        with st.spinner("Đang tạo phiếu điều chỉnh..."):
                            try:
                                voucher_id = inv_mgr.create_adjustment(
                                    branch_id=selected_branch, user_id=user_info['uid'],
                                    items=st.session_state.voucher_items, reason=reason,
                                    notes=notes, adjustment_date=adjustment_date
                                )
                                if voucher_id:
                                    st.success(f"Tạo phiếu điều chỉnh {voucher_id} thành công!")
                                else:
                                    st.warning("Không có thay đổi nào được ghi nhận.")
                                st.session_state.voucher_items = []
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi khi tạo phiếu điều chỉnh: {e}")
        else:
            st.info("Chưa có sản phẩm nào được thêm vào chứng từ.")

    # --- TAB 3: VOUCHER HISTORY ---
    elif st.session_state.active_inventory_tab == "📜 Lịch sử Chứng từ":
        render_section_header("Lịch sử Chứng từ Kho")

        @st.cache_data(ttl=3600, hash_funcs={AuthManager: hash_auth_manager})
        def get_user_map(auth_manager):
            all_users = auth_manager.get_all_users()
            return {user['uid']: user['displayName'] for user in all_users}

        user_map = get_user_map(auth_mgr)
        vouchers = inv_mgr.get_vouchers_by_branch(branch_id=selected_branch, limit=100)

        if not vouchers:
            st.info("Chưa có chứng từ nào cho chi nhánh này.")
        else:
            for voucher in vouchers:
                with st.container(border=True):
                    voucher_id = voucher['id']
                    voucher_type_display = voucher['type'].replace('_', ' ').title()
                    voucher_status = voucher['status']
                    
                    header_cols = st.columns([3, 2, 1, 1])
                    header_cols[0].markdown(f"**ID:** `{voucher_id}`")
                    header_cols[1].markdown(f"**Loại:** {voucher_type_display}")

                    created_at_dt = pd.to_datetime(voucher['created_at'])
                    if created_at_dt.tzinfo is None:
                        created_at_dt = created_at_dt.tz_localize('Asia/Ho_Chi_Minh')
                    else:
                        created_at_dt = created_at_dt.tz_convert('Asia/Ho_Chi_Minh')

                    header_cols[2].markdown(f"**Ngày:** {created_at_dt.strftime('%d/%m/%Y')}")

                    if voucher_status == 'CANCELLED':
                        header_cols[3].error("Đã Huỷ")
                    else:
                        header_cols[3].success("Hoàn thành")

                    with st.expander("Xem chi tiết"):
                        created_by_id = voucher['created_by']
                        created_by_name = user_map.get(created_by_id, created_by_id) # Fallback to ID
                        st.markdown(f"**Người tạo:** {created_by_name}")
                        st.markdown(f"**Ghi chú:** *{voucher.get('notes', 'Không có')}*")
                        if 'supplier' in voucher: st.markdown(f"**Nhà cung cấp:** {voucher['supplier']}")
                        render_sub_header("Sản phẩm trong chứng từ:")
                        st.dataframe(pd.DataFrame(voucher['items']), use_container_width=True, hide_index=True)

                        if user_role == 'admin' and voucher_status != 'CANCELLED':
                            st.divider()
                            st.error("Khu vực nguy hiểm (chỉ Admin)")
                            if st.button(f"🚨 Huỷ Chứng từ này", key=f"cancel_{voucher_id}", help=f"Hành động này sẽ đảo ngược toàn bộ giao dịch của chứng từ {voucher_id}. Không thể hoàn tác."):
                                try:
                                    with st.spinner(f"Đang huỷ chứng từ {voucher_id}..."):
                                        inv_mgr.cancel_voucher(voucher_id, user_info['uid'])
                                        st.success(f"Đã huỷ thành công chứng từ {voucher_id}. Tải lại trang để cập nhật.")
                                        st.rerun()
                                except Exception as e: st.error(f"Lỗi khi huỷ chứng từ: {e}")
