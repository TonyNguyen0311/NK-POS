
import streamlit as st
import json
import tempfile
import os
from datetime import datetime

# --- Google/Firebase Imports -- -
from managers.firebase_client import FirebaseClient
from google.oauth2 import service_account
from googleapiclient.discovery import build

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
from managers.product.image_handler import ImageHandler

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

def get_creds_from_secrets(creds_section_name):
    """
    The definitive solution:
    1. Reads a secrets section.
    2. Manually creates a dictionary.
    3. **Fixes the private_key newline corruption** caused by Streamlit.
    4. Writes the corrected dictionary to a temporary JSON file.
    5. Returns the path to this file.
    """
    creds_section = st.secrets[creds_section_name]
    creds_dict = {}
    for key in creds_section.keys():
        creds_dict[key] = creds_section[key]

    # The crucial fix: correct the private_key before writing to file
    if 'private_key' in creds_dict:
        creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')

    # Create a temporary file to hold the corrected credentials
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
        json.dump(creds_dict, temp_file)
        return temp_file.name

def init_managers():
    firebase_creds_path = None
    gdrive_creds_path = None
    try:
        # --- Initialize Firebase Client (Project: nk-pos-47135) ---
        if 'firebase_client' not in st.session_state:
            firebase_creds_path = get_creds_from_secrets("firebase_credentials")
            pyrebase_config = {key: st.secrets["pyrebase_config"][key] for key in st.secrets["pyrebase_config"].keys()}
            st.session_state.firebase_client = FirebaseClient(firebase_creds_path, pyrebase_config)
            st.info("✅ Đã kết nối tới Firebase (Database & Auth).")

        # --- Initialize Google Drive Image Handler (Project: nk-pos-482708) ---
        if 'image_handler' not in st.session_state:
            gdrive_creds_path = get_creds_from_secrets("gdrive_credentials")
            folder_id = st.secrets["gdrive_folder_id"]
            st.session_state.image_handler = ImageHandler(gdrive_creds_path, folder_id)
            st.info("✅ Đã kết nối tới Google Drive (Lưu trữ ảnh).")

    except Exception as e:
        st.error(f"Lỗi khởi tạo credentials: {e}")
        st.stop()
    finally:
        # --- Clean up temporary files ---
        if firebase_creds_path and os.path.exists(firebase_creds_path):
            os.remove(firebase_creds_path)
        if gdrive_creds_path and os.path.exists(gdrive_creds_path):
            os.remove(gdrive_creds_path)

    # --- Initialize All Other Managers (No changes needed here) ---
    fb_client = st.session_state.firebase_client
    if 'product_mgr' not in st.session_state:
        st.session_state.product_mgr = ProductManager(fb_client, st.session_state.image_handler)

    other_managers = {
        'auth_mgr': AuthManager, 'branch_mgr': BranchManager,
        'inventory_mgr': InventoryManager, 'customer_mgr': CustomerManager,
        'settings_mgr': SettingsManager, 'promotion_mgr': PromotionManager,
        'cost_mgr': CostManager, 'price_mgr': PriceManager,
    }
    for mgr_name, mgr_class in other_managers.items():
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
