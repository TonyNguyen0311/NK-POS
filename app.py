import streamlit as st
import json

# IMPORT MANAGERS
from managers.firebase_client import FirebaseClient
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from managers.product_manager import ProductManager

# IMPORT UI PAGES
from ui import login_page, products_page

# 1. SETUP PAGE
st.set_page_config(page_title="NK-POS System", page_icon="🛒", layout="wide")

st.markdown("""
<style>
    .main-header {font-size: 1.5rem; color: #4C9EE3; font-weight: bold; margin-bottom: 20px;}
    .stButton>button {border-radius: 6px;}
</style>
""", unsafe_allow_html=True)

# 2. INIT SINGLETONS
if 'db_client' not in st.session_state:
    if "firebase" in st.secrets:
        creds_str = st.secrets["firebase"]["credentials_json"]
        creds = json.loads(creds_str) if isinstance(creds_str, str) else creds_str
        bucket = st.secrets["firebase"].get("storage_bucket")
        st.session_state.db_client = FirebaseClient(creds, bucket)
    else:
        st.error("Chưa cấu hình Secrets!")
        st.stop()
        
    client = st.session_state.db_client
    st.session_state.auth_mgr = AuthManager(client)
    st.session_state.branch_mgr = BranchManager(client)
    st.session_state.product_mgr = ProductManager(client)

# 3. ROUTER
def main():
    if 'user' not in st.session_state:
        login_page.render_login()
        return

    user = st.session_state.user
    
    with st.sidebar:
        st.title("🛒 S-POS")
        st.caption(f"Chi nhánh: {st.session_state.branch_mgr.get_branch(user['branch_id']).get('name', 'N/A')}")
        st.write(f"👤 **{user['display_name']}**")
        st.divider()
        
        menu = ["Bán hàng (POS)", "Sản phẩm", "Kho hàng", "Báo cáo"]
        if user['role'] == 'ADMIN':
            menu.extend(["Quản trị", "Cấu hình"])
        
        choice = st.radio("Menu", menu, label_visibility="collapsed")
        
        st.divider()
        if st.button("Đăng xuất"):
            del st.session_state.user
            st.rerun()

    # Điều hướng
    if choice == "Sản phẩm":
        products_page.render()   # <--- Dòng quan trọng này
    elif choice == "Bán hàng (POS)":
        st.info("Module POS đang xây dựng...")
    else:
        st.info(f"Đang phát triển: {choice}")

if __name__ == "__main__":
    main()
