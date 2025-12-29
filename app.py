import streamlit as st
from managers.firebase_client import FirebaseClient

# Import các managers
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from managers.product_manager import ProductManager
from managers.inventory_manager import InventoryManager
from managers.customer_manager import CustomerManager
from managers.pos_manager import POSManager
from managers.report_manager import ReportManager # MỚI

# Import các trang UI
from ui.login_page import render_login
from ui.products_page import render_product_page
# from ui.branch_page import render_branch_page
# from ui.inventory_page import render_inventory_page
from ui.pos_page import render_pos_page
from ui.report_page import render_report_page # MỚI

st.set_page_config(layout="wide")

def main():
    # --- KHỞI TẠO --- 
    if 'firebase_client' not in st.session_state:
        st.session_state.firebase_client = FirebaseClient(st.secrets["firebase_service_account"])
    
    if 'auth_mgr' not in st.session_state:
        st.session_state.auth_mgr = AuthManager(st.session_state.firebase_client)

    if 'branch_mgr' not in st.session_state:
        st.session_state.branch_mgr = BranchManager(st.session_state.firebase_client)
    
    if 'product_mgr' not in st.session_state:
        st.session_state.product_mgr = ProductManager(st.session_state.firebase_client)

    if 'inventory_mgr' not in st.session_state:
        st.session_state.inventory_mgr = InventoryManager(st.session_state.firebase_client)

    if 'customer_mgr' not in st.session_state:
        st.session_state.customer_mgr = CustomerManager(st.session_state.firebase_client)

    if 'report_mgr' not in st.session_state:
        st.session_state.report_mgr = ReportManager(st.session_state.firebase_client)

    if 'pos_mgr' not in st.session_state:
        st.session_state.pos_mgr = POSManager(
            st.session_state.firebase_client, 
            st.session_state.inventory_mgr, 
            st.session_state.customer_mgr, 
            None # voucher_mgr chưa có
        )

    # --- ROUTING --- 
    if 'user' not in st.session_state or st.session_state.user is None:
        render_login()
    else:
        # Lấy thông tin user
        user_info = st.session_state.user
        st.sidebar.success(f"Xin chào, {user_info['display_name']}!")
        st.sidebar.write(f"Chi nhánh: **{st.session_state.branch_mgr.get_branch(user_info['branch_id'])['name']}**")
        st.sidebar.write(f"Vai trò: **{user_info['role']}**")

        # Menu dựa trên vai trò
        menu_options_admin = ["Bán hàng (POS)", "Báo cáo", "Quản lý Sản phẩm", "Quản lý Kho", "Quản lý Chi nhánh", "Quản trị"]
        menu_options_staff = ["Bán hàng (POS)", "Báo cáo", "Quản lý Kho"]
        
        if user_info['role'] == 'ADMIN':
            page = st.sidebar.selectbox("Chức năng", menu_options_admin)
        else: # STAFF
            page = st.sidebar.selectbox("Chức năng", menu_options_staff, help="Một số chức năng yêu cầu quyền ADMIN.")

        # Hiển thị trang tương ứng
        if page == "Bán hàng (POS)":
            render_pos_page()
        elif page == "Báo cáo":
            render_report_page()
        elif page == "Quản lý Sản phẩm":
            render_product_page()
        # elif page == "Quản lý Chi nhánh":
        #     render_branch_page()
        # elif page == "Quản lý Kho":
        #     render_inventory_page()
        # Các trang khác sẽ được thêm sau
        
        if st.sidebar.button("Đăng xuất"):
            del st.session_state.user
            st.rerun()

if __name__ == "__main__":
    main()