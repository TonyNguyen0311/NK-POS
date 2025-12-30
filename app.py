
import streamlit as st
import json
from datetime import datetime
from managers.firebase_client import FirebaseClient

# Import managers
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

# Import UI pages
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
from ui.pnl_report_page import render_pnl_report_page # New import

st.set_page_config(layout="wide")

# --- MENU PERMISSIONS ---
MENU_PERMISSIONS = {
    "admin": [
        "Báo cáo P&L", "Báo cáo & Phân tích", "Bán hàng (POS)", "Sản phẩm Kinh doanh",
        "Quản lý Kho", "Luân chuyển Kho", "Ghi nhận Chi phí", "Danh mục Sản phẩm", 
        "Danh mục Chi phí", "Phân bổ Chi phí",
        "Quản lý Khuyến mãi", "Quản lý Người dùng", "Quản trị Hệ thống",
    ],
    "manager": [
        "Báo cáo P&L", "Báo cáo & Phân tích", "Bán hàng (POS)", "Sản phẩm Kinh doanh",
        "Quản lý Kho", "Luân chuyển Kho", "Ghi nhận Chi phí",
    ],
    "staff": ["Bán hàng (POS)", "Ghi nhận Chi phí"]
}

# --- NEW MENU STRUCTURE ---
MENU_STRUCTURE = {
    "📈 Nghiệp vụ": [
        "Bán hàng (POS)",
        "Báo cáo P&L", # Added
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

def init_managers():
    if 'firebase_client' not in st.session_state:
        try:
            creds_dict = json.loads(st.secrets["firebase"]["credentials_json"])
            pyrebase_config_dict = json.loads(st.secrets["firebase"]["pyrebase_config"])
            st.session_state.firebase_client = FirebaseClient(creds_dict, pyrebase_config_dict)
        except Exception as e:
            st.error(f"Lỗi cấu hình Firebase: {e}")
            st.stop()

    fb_client = st.session_state.firebase_client
    managers_to_init = {
        'auth_mgr': AuthManager, 'branch_mgr': BranchManager, 'product_mgr': ProductManager,
        'inventory_mgr': InventoryManager, 'customer_mgr': CustomerManager, 'settings_mgr': SettingsManager,
        'promotion_mgr': PromotionManager, 'cost_mgr': CostManager, 'price_mgr': PriceManager,
    }
    for mgr_name, mgr_class in managers_to_init.items():
        if mgr_name not in st.session_state:
            st.session_state[mgr_name] = mgr_class(fb_client)

    if 'report_mgr' not in st.session_state:
        st.session_state.report_mgr = ReportManager(fb_client, st.session_state.cost_mgr)
        
    if 'pos_mgr' not in st.session_state:
        st.session_state.pos_mgr = POSManager(
            firebase_client=fb_client, inventory_mgr=st.session_state.inventory_mgr,
            customer_mgr=st.session_state.customer_mgr, promotion_mgr=st.session_state.promotion_mgr,
            price_mgr=st.session_state.price_mgr, cost_mgr=st.session_state.cost_mgr
        )
    return True

def display_sidebar():
    user_info = st.session_state.user
    st.sidebar.success(f"Xin chào, {user_info.get('display_name', 'Người dùng')}!")
    role = user_info.get('role', 'staff').lower()
    st.sidebar.write(f"Vai trò: **{role.upper()}**")
    
    user_allowed_pages = MENU_PERMISSIONS.get(role, [])
    if 'page' not in st.session_state or st.session_state.page not in user_allowed_pages:
        st.session_state.page = next((p for cat_pages in MENU_STRUCTURE.values() for p in cat_pages if p in user_allowed_pages), None)

    st.sidebar.title("Chức năng")
    for category, pages in MENU_STRUCTURE.items():
        allowed_pages_in_category = [p for p in pages if p in user_allowed_pages]
        if allowed_pages_in_category:
            is_expanded = st.session_state.get('page') in allowed_pages_in_category
            with st.sidebar.expander(category, expanded=is_expanded):
                for page_name in allowed_pages_in_category:
                    if st.button(page_name, key=f"btn_{page_name.replace(' ', '_')}", use_container_width=True):
                        st.session_state.page = page_name
                        st.rerun()
    
    st.sidebar.divider()
    if st.sidebar.button("Đăng xuất", use_container_width=True):
        st.session_state.auth_mgr.logout()
        st.rerun()

def main():
    if not init_managers(): return

    auth_mgr = st.session_state.auth_mgr
    branch_mgr = st.session_state.branch_mgr
    auth_mgr.check_cookie_and_re_auth()

    if 'user' not in st.session_state or st.session_state.user is None:
        render_login_page(auth_mgr, branch_mgr)
        return
    
    display_sidebar()
    page = st.session_state.get('page')
    if not page: st.info("Vui lòng chọn chức năng."); return

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

    renderer = page_renderers.get(page)
    if renderer: renderer()
    else: st.warning(f"Trang '{page}' đang phát triển.")

if __name__ == "__main__":
    main()
