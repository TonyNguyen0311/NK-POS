import streamlit as st
import json

# IMPORT MANAGERS
from managers.firebase_client import FirebaseClient
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager

# IMPORT UI PAGES
from ui import login_page

# 1. SETUP PAGE
st.set_page_config(page_title="NK-POS System", page_icon="🛒", layout="wide")

# CSS Global
st.markdown("""
<style>
    .main-header {font-size: 1.5rem; color: #4C9EE3; font-weight: bold; margin-bottom: 20px;}
    .stButton>button {border-radius: 6px;}
</style>
""", unsafe_allow_html=True)

# 2. INIT SINGLETONS (Chỉ chạy 1 lần)
if 'db_client' not in st.session_state:
    # Load Firebase
    if "firebase" in st.secrets:
        creds_str = st.secrets["firebase"]["credentials_json"]
        creds = json.loads(creds_str) if isinstance(creds_str, str) else creds_str
        bucket = st.secrets["firebase"].get("storage_bucket")
        st.session_state.db_client = FirebaseClient(creds, bucket)
    else:
        st.error("Chưa cấu hình Secrets!")
        st.stop()
        
    # Init Managers
    client = st.session_state.db_client
    st.session_state.auth_mgr = AuthManager(client)
    st.session_state.branch_mgr = BranchManager(client)
    # Các manager khác sẽ init sau...

# 3. ROUTER & NAVIGATION
def main():
    # Kiểm tra trạng thái đăng nhập
    if 'user' not in st.session_state:
        login_page.render_login()
        return

    # Đã đăng nhập -> Hiển thị Sidebar & Main Content
    user = st.session_state.user
    
    with st.sidebar:
        st.title("🛒 NK-POS")
        st.write(f"👤 **{user['display_name']}**")
        st.write(f"🏢 {user['role']}")
        st.divider()
        
        # Menu điều hướng
        menu = ["Bán hàng (POS)", "Sản phẩm", "Kho hàng", "Báo cáo"]
        if user['role'] == 'ADMIN':
            menu.extend(["Quản trị", "Cấu hình"])
        
        choice = st.radio("Menu", menu, label_visibility="collapsed")
        
        st.divider()
        if st.button("Đăng xuất"):
            del st.session_state.user
            st.rerun()

    # Nội dung chính
    st.markdown(f'<div class="main-header">{choice}</div>', unsafe_allow_html=True)
    
    if choice == "Bán hàng (POS)":
        st.info("Module POS đang xây dựng...")
    elif choice == "Quản trị":
        st.info("Module Admin đang xây dựng...")
    else:
        st.write(f"Đang phát triển trang: {choice}")

if __name__ == "__main__":
    main()
