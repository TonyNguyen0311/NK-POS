
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
from ui.cost_page import render_cost_page
from ui.inventory_page import render_inventory_page
from ui.user_management_page import render_user_management_page
from ui.product_catalog_page import render_product_catalog_page
from ui.business_products_page import render_business_products_page

st.set_page_config(layout="wide")

# --- MENU PERMISSIONS ---
MENU_PERMISSIONS = {
    "admin": [
        "Báo cáo & Phân tích", "Bán hàng (POS)", "Sản phẩm Kinh doanh",
        "Quản lý Kho", "Quản lý Chi phí", "Danh mục Sản phẩm",
        "Quản lý Khuyến mãi", "Quản lý Người dùng", "Quản trị Hệ thống",
    ],
    "manager": [
        "Báo cáo & Phân tích", "Bán hàng (POS)", "Sản phẩm Kinh doanh",
        "Quản lý Kho", "Quản lý Chi phí",
    ],
    "staff": ["Bán hàng (POS)"]
}

# --- NEW MENU STRUCTURE ---
MENU_STRUCTURE = {
    "📈 Nghiệp vụ": [
        "Bán hàng (POS)", 
        "Báo cáo & Phân tích"
    ],
    "📦 Hàng hoá": [
        "Danh mục Sản phẩm", 
        "Sản phẩm Kinh doanh", 
        "Quản lý Kho"
    ],
    "⚙️ Thiết lập": [
        "Quản lý Chi phí",
        "Quản lý Khuyến mãi"
    ],
    "🔑 Quản trị": [
        "Quản lý Người dùng",
        "Quản trị Hệ thống"
    ]
}


def init_managers():
    """
    Initializes all manager classes and stores them in the session state.
    This function ensures all managers are ready before any other UI logic runs.
    """
    if 'firebase_client' not in st.session_state:
        try:
            creds_dict = json.loads(st.secrets["firebase"]["credentials_json"])
            pyrebase_config_dict = json.loads(st.secrets["firebase"]["pyrebase_config"])
            st.session_state.firebase_client = FirebaseClient(creds_dict, pyrebase_config_dict)
        except Exception as e:
            st.error(f"Lỗi cấu hình Firebase. Vui lòng kiểm tra lại file secrets.toml: {e}")
            st.stop()

    fb_client = st.session_state.firebase_client

    # Initialize managers if they don't exist in session state
    managers_to_init = {
        'auth_mgr': AuthManager,
        'branch_mgr': BranchManager,
        'product_mgr': ProductManager,
        'inventory_mgr': InventoryManager,
        'customer_mgr': CustomerManager,
        'settings_mgr': SettingsManager,
        'promotion_mgr': PromotionManager,
        'cost_mgr': CostManager,
        'price_mgr': PriceManager,
    }
    for mgr_name, mgr_class in managers_to_init.items():
        if mgr_name not in st.session_state:
            st.session_state[mgr_name] = mgr_class(fb_client)

    # Initialize managers with dependencies
    if 'report_mgr' not in st.session_state:
        st.session_state.report_mgr = ReportManager(fb_client, st.session_state.cost_mgr)
        
    if 'pos_mgr' not in st.session_state:
        st.session_state.pos_mgr = POSManager(
            firebase_client=fb_client,
            inventory_mgr=st.session_state.inventory_mgr,
            customer_mgr=st.session_state.customer_mgr,
            promotion_mgr=st.session_state.promotion_mgr,
            price_mgr=st.session_state.price_mgr,
            cost_mgr=st.session_state.cost_mgr
        )
    return True

def display_sidebar():
    user_info = st.session_state.user
    st.sidebar.success(f"Xin chào, {user_info.get('display_name', 'Người dùng')}!")
    role = user_info.get('role', 'staff').lower()
    st.sidebar.write(f"Vai trò: **{role.upper()}**")
    branch_ids = user_info.get('branch_ids', [])
    if role == 'admin':
        st.sidebar.write("Quyền truy cập: **Toàn bộ hệ thống**")
    elif branch_ids:
        branch_names = [st.session_state.branch_mgr.get_branch_name(b_id) for b_id in branch_ids]
        st.sidebar.write(f"Chi nhánh: **{', '.join(branch_names)}**")

    # --- Build hierarchical menu ---
    user_allowed_pages = MENU_PERMISSIONS.get(role, [])
    display_options = []
    display_to_page_map = {}

    for category, pages in MENU_STRUCTURE.items():
        # Check if user has access to any page in this category
        pages_in_category = [p for p in pages if p in user_allowed_pages]
        if pages_in_category:
            for page in pages_in_category:
                display_name = f"{category} > {page}"
                display_options.append(display_name)
                display_to_page_map[display_name] = page
    
    if not display_options:
        st.sidebar.warning("Tài khoản của bạn chưa được cấp quyền truy cập chức năng nào.")
        return None

    selected_display_name = st.sidebar.selectbox("Chức năng", display_options, key="main_menu")
    
    st.sidebar.divider()
    if st.sidebar.button("Đăng xuất", use_container_width=True):
        st.session_state.auth_mgr.logout()
        st.rerun()
        
    st.sidebar.caption(f"Phiên bản: {datetime.now().strftime('%Y%m%d.%H%M')}")
    
    return display_to_page_map.get(selected_display_name)

def main():
    if not init_managers():
        return

    auth_mgr = st.session_state.auth_mgr
    branch_mgr = st.session_state.branch_mgr
    auth_mgr.check_cookie_and_re_auth()

    if 'user' not in st.session_state or st.session_state.user is None:
        render_login_page(auth_mgr, branch_mgr)
        return
    
    page = display_sidebar()

    # If no page is selected or available, do nothing.
    if not page:
        st.info("Vui lòng chọn một chức năng từ thanh công cụ bên trái.")
        return

    page_renderers = {
        "Bán hàng (POS)": lambda: render_pos_page(st.session_state.pos_mgr),
        "Báo cáo & Phân tích": lambda: render_report_page(st.session_state.report_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Quản lý Kho": lambda: render_inventory_page(st.session_state.inventory_mgr, st.session_state.product_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Quản lý Chi phí": lambda: render_cost_page(st.session_state.cost_mgr, st.session_state.branch_mgr, st.session_state.auth_mgr),
        "Quản lý Khuyến mãi": lambda: render_promotions_page(st.session_state.promotion_mgr, st.session_state.product_mgr, st.session_state.branch_mgr),
        "Quản lý Người dùng": lambda: render_user_management_page(st.session_state.auth_mgr, st.session_state.branch_mgr),
        "Quản trị Hệ thống": lambda: render_settings_page(st.session_state.settings_mgr, st.session_state.auth_mgr),
        "Danh mục Sản phẩm": lambda: render_product_catalog_page(st.session_state.product_mgr, st.session_state.auth_mgr),
        "Sản phẩm Kinh doanh": lambda: render_business_products_page(st.session_state.auth_mgr, st.session_state.branch_mgr, st.session_state.product_mgr, st.session_state.price_mgr),
    }

    renderer = page_renderers.get(page)
    if renderer:
        renderer()
    else:
        st.warning(f"Trang '{page}' đang trong quá trình phát triển hoặc đã bị loại bỏ.")

if __name__ == "__main__":
    main()
