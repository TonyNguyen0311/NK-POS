
import streamlit as st
import json
import os
from managers.firebase_client import FirebaseClient

# Import managers
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from managers.product_manager import ProductManager
from managers.inventory_manager import InventoryManager
from managers.customer_manager import CustomerManager
from managers.pos_manager import POSManager
from managers.report_manager import ReportManager
from managers.session_manager import is_session_active, check_remember_me
from managers.settings_manager import SettingsManager
from managers.promotion_manager import PromotionManager

# Import UI pages
from ui.login_page import render_login
from ui.products_page import render_product_page
from ui.pos_page import render_pos_page
from ui.report_page import render_report_page
from ui.settings_page import render_settings_page
from ui.promotions_page import render_promotions_page

st.set_page_config(layout="wide")

def main():
    # Check for Firebase credentials
    if "firebase" not in st.secrets or "credentials_json" not in st.secrets.firebase:
        st.error("Firebase secrets not found...")
        return

    # Initialize Firebase client
    if 'firebase_client' not in st.session_state:
        try:
            creds_dict = json.loads(st.secrets["firebase"]["credentials_json"])
            st.session_state.firebase_client = FirebaseClient(creds_dict)
        except json.JSONDecodeError:
            st.error("Failed to parse Firebase credentials...")
            return

    # Initialize managers
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
    if 'settings_mgr' not in st.session_state:
        st.session_state.settings_mgr = SettingsManager(st.session_state.firebase_client)
    if 'promotion_mgr' not in st.session_state:
        st.session_state.promotion_mgr = PromotionManager(st.session_state.firebase_client)

    # POSManager depends on other managers, so it's initialized last
    if 'pos_mgr' not in st.session_state:
        st.session_state.pos_mgr = POSManager(
            firebase_client=st.session_state.firebase_client,
            inventory_mgr=st.session_state.inventory_mgr,
            customer_mgr=st.session_state.customer_mgr,
            promotion_mgr=st.session_state.promotion_mgr # Correctly passing the promotion manager
        )
    
    # Check and initialize database collections if needed
    st.session_state.promotion_mgr.check_and_initialize()

    # Session and routing
    if 'user' not in st.session_state:
        if not check_remember_me():
            render_login()
            return

    if not is_session_active():
        render_login()
        return

    # Main app UI
    user_info = st.session_state.user
    st.sidebar.success(f"Xin chào, {user_info['display_name']}!")
    st.sidebar.write(f"Chi nhánh: **{st.session_state.branch_mgr.get_branch(user_info['branch_id'])['name']}**")
    st.sidebar.write(f"Vai trò: **{user_info['role']}**")

    # Menu based on role
    menu_options = {
        "ADMIN": ["Bán hàng (POS)", "Báo cáo", "Quản lý Sản phẩm", "Quản lý Khuyến mãi", "Quản lý Kho", "Quản lý Chi nhánh", "Quản trị"],
        "STAFF": ["Bán hàng (POS)", "Báo cáo", "Quản lý Kho"]
    }
    page = st.sidebar.selectbox("Chức năng", menu_options.get(user_info['role'], []))

    # Render the selected page
    page_renderers = {
        "Bán hàng (POS)": render_pos_page,
        "Báo cáo": render_report_page,
        "Quản lý Sản phẩm": render_product_page,
        "Quản lý Khuyến mãi": render_promotions_page,
        "Quản trị": render_settings_page
    }
    if page in page_renderers:
        page_renderers[page]()

    # Logout button
    if st.sidebar.button("Đăng xuất"):
        if os.path.exists(".remember_me"):
            os.remove(".remember_me")
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

if __name__ == "__main__":
    main()
