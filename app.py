import streamlit as st
import json
from managers.firebase_client import FirebaseClient

# 1. Cấu hình trang (Phải gọi đầu tiên)
st.set_page_config(
    page_title="NK-POS System",
    page_icon="🛒",
    layout="wide"
)

# 2. CSS Tùy chỉnh (Placeholder)
st.markdown("""
<style>
    .main-header {font-size: 2rem; color: #4C9EE3; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# 3. Khởi tạo kết nối Firebase (Singleton)
if 'db_client' not in st.session_state:
    try:
        # Lấy secrets từ Streamlit Cloud
        if "firebase" in st.secrets:
            creds_str = st.secrets["firebase"]["credentials_json"]
            # Streamlit secrets trả về string hoặc dict tùy cấu hình, ta đảm bảo nó là dict
            if isinstance(creds_str, str):
                creds = json.loads(creds_str)
            else:
                creds = creds_str
                
            bucket_name = st.secrets["firebase"].get("storage_bucket")
            
            st.session_state.db_client = FirebaseClient(creds, bucket_name)
            st.toast("Kết nối Firebase thành công!", icon="🔥")
        else:
            st.warning("Chưa cấu hình Firebase Secrets.")
            
    except Exception as e:
        st.error(f"Không thể kết nối Firebase: {e}")

# 4. Giao diện chính
st.markdown('<div class="main-header">🛒 S-POS System</div>', unsafe_allow_html=True)
st.write("Chào mừng đến với hệ thống quản lý bán hàng đa chi nhánh.")

# Kiểm tra trạng thái
if 'db_client' in st.session_state:
    st.success("Hệ thống đã sẵn sàng kết nối Database.")
    # Nút test thử kết nối
    if st.button("Kiểm tra kết nối Firestore"):
        if st.session_state.db_client.check_connection():
            st.info("Firestore Client đang hoạt động tốt.")
else:
    st.error("Lỗi: Chưa kết nối được Database.")
