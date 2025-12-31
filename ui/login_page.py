
import streamlit as st
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
import time

def render_login_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    st.set_page_config(layout="centered")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # Check if any user exists. If not, show the initial setup form.
        if not auth_mgr.has_users():
            st.title("🚀 Khởi tạo hệ thống")
            st.info("Chào mừng bạn đến với NK-POS. Vì đây là lần chạy đầu tiên, chúng ta cần thiết lập một vài thông tin cơ bản.")

            with st.form("initial_setup_form"):
                st.subheader("1. Tạo Chi Nhánh Chính")
                branch_name = st.text_input("Tên chi nhánh", "Cửa hàng Chính")
                branch_address = st.text_input("Địa chỉ", "Hà Nội")
                branch_phone = st.text_input("Số điện thoại", "")

                st.subheader("2. Tạo Tài khoản Quản trị (Admin)")
                admin_username = st.text_input("Username Admin", "admin")
                admin_password = st.text_input("Password (ít nhất 6 ký tự)", type="password")
                admin_display_name = st.text_input("Tên hiển thị", "Quản trị viên")

                submitted = st.form_submit_button("Hoàn tất Thiết lập")

                if submitted:
                    if len(admin_password) < 6:
                        st.error("Mật khẩu của Admin phải có ít nhất 6 ký tự.")
                    elif not all([branch_name, branch_address, admin_username, admin_password, admin_display_name]):
                        st.error("Vui lòng điền đầy đủ tất cả các trường.")
                    else:
                        try:
                            # 1. Create the main branch
                            branch_id = branch_mgr.create_branch(branch_name, branch_address, branch_phone)

                            # 2. Create the admin user
                            admin_data = {
                                "username": admin_username,
                                "display_name": admin_display_name,
                                "role": "admin",
                                "branch_ids": [] # Admin has access to all branches
                            }
                            auth_mgr.create_user_record(admin_data, admin_password)

                            st.success("🎉 Thiết lập ban đầu thành công! Hệ thống sẽ tự tải lại để bạn đăng nhập.")
                            st.balloons()
                            time.sleep(3)
                            st.rerun()

                        except ValueError as ve:
                            st.error(f"Lỗi: {ve}")
                        except Exception as e:
                            st.error(f"Đã có lỗi xảy ra trong quá trình thiết lập: {e}")

        else:
            # If users exist, show the normal login form
            st.title("🔐 Đăng nhập hệ thống")
            with st.form("login_form"):
                username = st.text_input("Tên đăng nhập")
                password = st.text_input("Mật khẩu", type="password")
                login_button = st.form_submit_button("Đăng nhập")

                if login_button:
                    # The login function now returns a tuple (status, data)
                    status, data = auth_mgr.login(username, password)

                    if status == 'SUCCESS':
                        st.success("Đăng nhập thành công!")
                        # The user data is already in session_state from the auth_mgr
                        time.sleep(1) # Short pause to show the message
                        st.rerun() 
                    elif status == 'MIGRATED':
                        # Show the migration success message and let the user log in again
                        st.info(data)
                    elif status == 'FAILED':
                        # Show the specific error message from the auth_mgr
                        st.error(data)
                    else:
                        # Fallback for any unexpected status
                        st.error("Đã xảy ra lỗi không xác định. Vui lòng thử lại.")
