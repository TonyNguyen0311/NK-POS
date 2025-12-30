
import streamlit as st

def render_settings_page():
    st.title("⚙️ Quản trị")

    if 'settings_mgr' not in st.session_state:
        st.error("Settings Manager not initialized.")
        return

    settings_mgr = st.session_state.settings_mgr
    current_settings = settings_mgr.get_settings()

    st.subheader("Cài đặt phiên đăng nhập")

    timeout_options = {
        "30 phút": 30,
        "60 phút (mặc định)": 60,
        "120 phút": 120,
        "Không bao giờ": "never"
    }

    # Find the current setting in the options
    current_timeout_val = current_settings.get('session_timeout_minutes', 60)
    current_option_key = next((key for key, value in timeout_options.items() if value == current_timeout_val), "60 phút (mặc định)")

    new_timeout_key = st.selectbox(
        "Thời gian tự động đăng xuất sau khi không hoạt động",
        options=list(timeout_options.keys()),
        index=list(timeout_options.keys()).index(current_option_key)
    )

    if st.button("Lưu cài đặt"):
        new_timeout_val = timeout_options[new_timeout_key]
        settings_mgr.save_settings({'session_timeout_minutes': new_timeout_val})
        st.success("Đã lưu cài đặt!")
        st.rerun()

