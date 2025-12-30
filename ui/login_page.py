
import streamlit as st
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager

def render_login_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    st.set_page_config(layout="centered")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 Đăng nhập hệ thống")

        # ======== TẠM THỜI HIỂN THỊ FORM KHỞI TẠO ========
        st.warning("⚠️ Chế độ thiết lập Admin tạm thời. Vui lòng tạo tài khoản Admin mới.")
        with st.form("setup_form"):
            st.subheader("1. Tạo Chi Nhánh Chính (có thể bỏ qua nếu đã có)")
            br_name = st.text_input("Tên chi nhánh", "Cửa hàng Chính")
            br_addr = st.text_input("Địa chỉ", "Hà Nội")
            br_phone = st.text_input("Số điện thoại", "")
            
            st.subheader("2. Tạo Tài khoản Admin Mới")
            adm_user = st.text_input("Username mới", "admin")
            adm_pass = st.text_input("Password mới", type="password")
            adm_name = st.text_input("Tên hiển thị", "Quản trị viên")
            
            submitted = st.form_submit_button("Khởi tạo Admin")
            
            if submitted:
                if not all([br_name, br_addr, adm_user, adm_pass, adm_name]):
                    st.error("Vui lòng nhập đủ thông tin cho Admin và Chi nhánh.")
                else:
                    try:
                        # Tạo chi nhánh nếu chưa có
                        if not branch_mgr.get_branches():
                            branch_id = branch_mgr.create_branch(br_name, br_addr, br_phone)
                            st.info(f"Đã tạo chi nhánh '{br_name}'.")
                        else:
                            # Lấy chi nhánh đầu tiên làm mặc định
                            branch_id = branch_mgr.get_branches()[0]['id']

                        # Tạo user mới
                        user_data = {
                            "username": adm_user,
                            "display_name": adm_name,
                            "role": "admin",
                            "branch_ids": [branch_id] # Gán user vào chi nhánh
                        }
                        auth_mgr.create_user_record(user_data, adm_pass)
                        st.success(f"🎉 Đã tạo thành công tài khoản admin '{adm_user}'. Vui lòng tải lại trang và đăng nhập.")
                        st.balloons()
                    except ValueError as e:
                        st.error(f"Lỗi: {e}")
                    except Exception as e:
                        st.error(f"Đã có lỗi xảy ra: {e}")

        st.divider()
        # ==========================================================

        # Form đăng nhập bình thường
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            
            login_button = st.form_submit_button("Đăng nhập")
            
            if login_button:
                user = auth_mgr.login(username, password)
                if user:
                    st.success("Đăng nhập thành công!")
                    st.rerun() 
                else:
                    st.error("Sai tên đăng nhập hoặc mật khẩu.")
