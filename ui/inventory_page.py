
import streamlit as st
import pandas as pd
from datetime import datetime

# Import managers
from managers.inventory_manager import InventoryManager
from managers.branch_manager import BranchManager
from managers.product_manager import ProductManager
from managers.auth_manager import AuthManager

def render_inventory_page(inv_mgr: InventoryManager, branch_mgr: BranchManager, prod_mgr: ProductManager, auth_mgr: AuthManager):
    st.header("📦 Quản lý Kho")

    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.error("Vui lòng đăng nhập.")
        return

    # --- LOGIC PHÂN QUYỀN ---
    user_role = user_info.get('role', 'staff')
    if user_role not in ['admin', 'manager']:
        st.warning("Bạn không có quyền truy cập vào chức năng này.")
        return

    user_branches = user_info.get('branch_ids', [])
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.get_branches()}
    allowed_branches_map = {branch_id: all_branches_map[branch_id] for branch_id in user_branches if branch_id in all_branches_map}
    if user_role == 'admin': # Admin có quyền trên tất cả chi nhánh
        allowed_branches_map = all_branches_map

    if not allowed_branches_map:
        st.warning("Tài khoản của bạn chưa được gán vào chi nhánh nào. Vui lòng liên hệ Admin.")
        return

    product_map = {p['sku']: p for p in prod_mgr.list_products()}

    tab1, tab2, tab3, tab4 = st.tabs([
        "🚚 Luân chuyển hàng hóa",
        "📥 Nhập kho (từ NCC)",
        "📤 Xuất/Hủy kho",
        "📋 Kiểm kê kho"
    ])

    # Helper để tạo selectbox chi nhánh đã được phân quyền
    def create_branch_selectbox(key_prefix):
        if len(allowed_branches_map) > 1:
            return st.selectbox("Chi nhánh", options=list(allowed_branches_map.keys()), format_func=lambda x: allowed_branches_map[x], key=f"{key_prefix}_branch")
        else:
            branch_id = list(allowed_branches_map.keys())[0]
            st.text_input("Chi nhánh", value=allowed_branches_map[branch_id], disabled=True, key=f"{key_prefix}_branch_disabled")
            return branch_id

    # --- TAB 1: LUÂN CHUYỂN HÀNG HÓA ---
    with tab1:
        # ... Chỉ admin mới có thể tạo phiếu chuyển kho đi từ chi nhánh bất kỳ ...
        # Manager chỉ có thể chuyển từ chi nhánh của mình
        # Việc nhận hàng được xử lý ở danh sách phiếu bên dưới
        pass

    # --- TAB 2: NHẬP KHO ---
    with tab2:
        with st.form("stock_in_form", clear_on_submit=True):
            st.subheader("Tạo phiếu nhập hàng từ Nhà cung cấp")
            adj_branch_in = create_branch_selectbox("in")
            # ... (phần còn lại của form giữ nguyên)
            pass

    # --- TAB 3: XUẤT HỦY KHO ---
    with tab3:
        with st.form("stock_out_form", clear_on_submit=True):
            st.subheader("Tạo phiếu xuất/hủy hàng hóa")
            adj_branch_out = create_branch_selectbox("out")
            # ... (phần còn lại của form giữ nguyên)
            pass

    # --- TAB 4: KIỂM KÊ KHO ---
    with tab4:
        st.subheader("Kiểm kê và điều chỉnh tồn kho thực tế")
        selected_branch = create_branch_selectbox("stk")
        
        # Logic kiểm kê giờ đây sẽ dựa trên `selected_branch` đã được phân quyền
        # ... (phần còn lại của logic kiểm kê giữ nguyên) ...
        pass
