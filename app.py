
import streamlit as st
import json
from datetime import datetime

# --- Google/Firebase Imports ---
from managers.firebase_client import FirebaseClient

# --- Import Managers ---
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from managers.product_manager import ProductManager
from managers.inventory_manager import InventoryManager
from managers.customer_manager import CustomerManager
from managers.pos_manager import POSManager
from managers.report_manager import ReportManager
from managers.settings_manager import SettingsManager
from managers.promotion_manager import PromotionManager
from managers.cost_manager import CostManager
from managers.price_manager import PriceManager

# --- Import UI Pages ---
from ui.login_page import render_login_page
from ui.pos_page import render_pos_page
from ui.report_page import render_report_page
from ui.settings_page import render_settings_page
from ui.promotions_page import render_promotions_page
from ui.cost_entry_page import render_cost_entry_page
from ui.cost_group_page import render_cost_group_page
from ui.inventory_page import render_inventory_page
from ui.user_management_page import render_user_management_page
from ui.product_catalog_page import render_product_catalog_page
from ui.business_products_page import render_business_products_page
from ui.stock_transfer_page import show_stock_transfer_page
from ui.cost_allocation_page import render_cost_allocation_page
from ui.pnl_report_page import render_pnl_report_page

st.set_page_config(layout="wide", page_title="NK-POS Retail Management")

# --- MENU PERMISSIONS & STRUCTURE ---
# (Your existing MENU_PERMISSIONS and MENU_STRUCTURE dictionaries remain unchanged)
MENU_PERMISSIONS = {
    # Admin has all permissions
    "admin": [
        "Báo cáo P&L", "Báo cáo & Phân tích", "Bán hàng (POS)", "Sản phẩm Kinh doanh",
        "Quản lý Kho", "Luân chuyển Kho", "Ghi nhận Chi phí", "Danh mục Sản phẩm",
        "Danh mục Chi phí", "Phân bổ Chi phí", "Quản lý Khuyến mãi", 
        "Quản lý Người dùng", "Quản trị Hệ thống",
    ],
    # Manager can see reports and manage their users/promotions
    "manager": [
        "Báo cáo P&L", "Báo cáo & Phân tích", "Bán hàng (POS)", "Sản phẩm Kinh doanh",
        "Quản lý Kho", "Luân chuyển Kho", "Ghi nhận Chi phí", "Quản lý Khuyến mãi",
        "Quản lý Người dùng",
    ],
    # Supervisor manages a store's operations and staff
    "supervisor": [
        "Bán hàng (POS)", "Quản lý Kho", "Luân chuyển Kho", "Ghi nhận Chi phí",
        "Quản lý Người dùng",
    ],
    # Staff handles sales and inventory tasks
    "staff": [
        "Bán hàng (POS)", "Quản lý Kho", "Luân chuyển Kho",
    ]
}
MENU_STRUCTURE = {
    "📈 Nghiệp vụ": [
        "Bán hàng (POS)",
        "Báo cáo P&L",
        "Báo cáo & Phân tích",
        "Ghi nhận Chi phí"
    ],
    "📦 Hàng hoá": [
        "Danh mục Sản phẩm",
        "Sản phẩm Kinh doanh",
        "Quản lý Kho",
        "Luân chuyển Kho"
    ],
    "⚙️ Thiết lập": [
        "Danh mục Chi phí",
        "Phân bổ Chi phí",
        "Quản lý Khuyến mãi"
    ],
    "🔑 Quản trị": [
        "Quản lý Người dùng",
        "Quản trị Hệ thống"
    ]
}

@st.cache_resource
def load_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Tệp CSS '{file_name}' không tìm thấy. Bỏ qua việc tải CSS.")

# Correctly parse credentials from Streamlit secrets
def get_corrected_creds(secrets_key):
    creds_section = st.secrets[secrets_key]
    creds_dict = creds_section.to_dict()
    if 'private_key' in creds_dict:
        creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
    return creds_dict

# Initialize all managers and store them in session_state
def init_managers():
    if 'managers_initialized' in st.session_state:
        return

    try:
        if 'firebase_client' not in st.session_state:
            firebase_creds_info = get_corrected_creds("firebase_credentials")
            pyrebase_config = st.secrets["pyrebase_config"].to_dict()
            st.session_state.firebase_client = FirebaseClient(firebase_creds_info, pyrebase_config)
    except Exception as e:
        st.error(f"Lỗi nghiêm trọng khi khởi tạo Firebase: {e}")
        st.stop()

    fb_client = st.session_state.firebase_client

    st.session_state.branch_mgr = BranchManager(fb_client)
    st.session_state.settings_mgr = SettingsManager(fb_client)
    st.session_state.inventory_mgr = InventoryManager(fb_client)
    st.session_state.customer_mgr = CustomerManager(fb_client)
    st.session_state.promotion_mgr = PromotionManager(fb_client)
    st.session_state.cost_mgr = CostManager(fb_client)
    st.session_state.price_mgr = PriceManager(fb_client)
    st.session_state.product_mgr = ProductManager(fb_client)
    st.session_state.auth_mgr = AuthManager(fb_client, st.session_state.settings_mgr)
    st.session_state.report_mgr = ReportManager(fb_client, st.session_state.cost_mgr)
    st.session_state.pos_mgr = POSManager(
        firebase_client=fb_client, inventory_mgr=st.session_state.inventory_mgr,
        customer_mgr=st.session_state.customer_mgr, promotion_mgr=st.session_state.promotion_mgr,
        price_mgr=st.session_state.price_mgr, cost_mgr=st.session_state.cost_mgr
    )
    
    st.session_state.managers_initialized = True

def display_sidebar():
    user_info = st.session_state.user
    st.sidebar.success(f"Xin chào, {user_info.get('display_name', 'Người dùng')}!")
    role = user_info.get('role', 'staff').lower()
    st.sidebar.write(f"Vai trò: **{role.upper()}**")

    user_allowed_pages = MENU_PERMISSIONS.get(role, [])
    
    # Set default page if not set or not allowed
    if 'page' not in st.session_state or st.session_state.page not in user_allowed_pages:
        st.session_state.page = next((p for cat_pages in MENU_STRUCTURE.values() for p in cat_pages if p in user_allowed_pages), None)

    st.sidebar.title("Chức năng")
    for category, pages in MENU_STRUCTURE.items():
        allowed_pages_in_category = [p for p in pages if p in user_allowed_pages]
        if allowed_pages_in_category:
            # Check if the current page is in this category to expand the expander
            is_expanded = st.session_state.get('page') in allowed_pages_in_category
            with st.sidebar.expander(category, expanded=is_expanded):
                for page_name in allowed_pages_in_category:
                    # Use a more descriptive key for the button
                    if st.button(page_name, key=f"btn_nav_{page_name.replace(' ', '_')}", use_container_width=True):
                        st.session_state.page = page_name
                        st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("Đăng xuất", use_container_width=True, key="logout_button"):
        st.session_state.auth_mgr.logout()
        st.rerun()

def main():
    load_css('assets/styles.css') # Load custom CSS

    init_managers()

    auth_mgr = st.session_state.auth_mgr
    branch_mgr = st.session_state.branch_mgr
    
    # This handles re-authentication from cookies
    auth_mgr.check_cookie_and_re_auth()

    # If user is not logged in, show login page
    if 'user' not in st.session_state or st.session_state.user is None:
        render_login_page(auth_mgr, branch_mgr)
        return

    # If user is logged in, display the main app
    display_sidebar()
    
    page = st.session_state.get('page')
    if not page: 
        st.info("Vui lòng chọn một chức năng từ thanh điều hướng bên trái.")
        return

    # Dictionary mapping page names to their render functions
    page_renderers = {
        "Bán hàng (POS)": lambda: render_pos_page(st.session_state.pos_mgr),
        "Báo cáo P&L": lambda: render_pnl_report_page(st.session_state.report_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Báo cáo & Phân tích": lambda: render_report_page(st.session_state.report_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Quản lý Kho": lambda: render_inventory_page(st.session_state.inventory_mgr, st.session_state.product_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Luân chuyển Kho": lambda: show_stock_transfer_page(st.session_state.branch_mgr, st.session_state.inventory_mgr, st.session_state.product_mgr, st.session_state.auth_mgr),
        "Ghi nhận Chi phí": lambda: render_cost_entry_page(st.session_state.cost_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Danh mục Chi phí": lambda: render_cost_group_page(st.session_state.cost_mgr),
        "Phân bổ Chi phí": lambda: render_cost_allocation_page(st.session_state.cost_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Quản lý Khuyến mãi": lambda: render_promotions_page(st.session_state.promotion_mgr, st.session_state.product_mgr, st.session_state.branch_mgr),
        "Quản lý Người dùng": lambda: render_user_management_page(st.session_state.auth_mgr, st.session_state.branch_mgr),
        "Quản trị Hệ thống": lambda: render_settings_page(st.session_state.settings_mgr, st.session_state.auth_mgr),
        "Danh mục Sản phẩm": lambda: render_product_catalog_page(st.session_state.product_mgr, st.session_state.auth_mgr),
        "Sản phẩm Kinh doanh": lambda: render_business_products_page(st.session_state.auth_mgr, st.session_state.branch_mgr, st.session_state.product_mgr, st.session_state.price_mgr),
    }

    # Render the selected page
    renderer = page_renderers.get(page)
    if renderer:
        renderer()
    else:
        st.warning(f"Trang '{page}' đang được phát triển hoặc không tồn tại.")

if __name__ == "__main__":
    main()
