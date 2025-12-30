
import streamlit as st
import pandas as pd

# Import managers
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager

def render_user_management_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    st.header("Quản lý Người dùng")

    # Chỉ Admin mới có quyền truy cập trang này (kiểm tra lại ở đây cho chắc)
    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role') != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        return

    # Lấy danh sách chi nhánh và người dùng
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.get_branches()}
    all_users = auth_mgr.list_users()

    tab1, tab2 = st.tabs(["Danh sách Người dùng", "Thêm Người dùng mới"])

    # --- TAB 1: DANH SÁCH & CHỈNH SỬA ---
    with tab1:
        st.subheader("Danh sách người dùng hiện tại")
        if not all_users:
            st.info("Chưa có người dùng nào trong hệ thống.")
            return

        for user in all_users:
            uid = user['uid']
            # Không cho admin tự sửa vai trò hoặc chi nhánh của chính mình
            is_self = (user['uid'] == user_info['uid'])

            with st.expander(f"{user['display_name']} (`{user['username']}`) - Vai trò: {user.get('role', 'N/A').upper()}"):
                with st.form(f"form_edit_{uid}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        new_display_name = st.text_input("Tên hiển thị", value=user['display_name'], key=f"name_{uid}")
                        new_role = st.selectbox("Vai trò", options=['staff', 'manager', 'admin'], index=['staff', 'manager', 'admin'].index(user.get('role', 'staff')), key=f"role_{uid}", disabled=is_self)
                        new_active_status = st.checkbox("Đang hoạt động", value=user.get('active', True), key=f"active_{uid}", disabled=is_self)
                    with c2:
                        new_password = st.text_input("Mật khẩu mới (để trống nếu không đổi)", type="password", key=f"pass_{uid}")
                        # Admin không bị giới hạn chi nhánh
                        if new_role != 'admin':
                           assigned_branches = st.multiselect("Các chi nhánh được gán", options=list(all_branches_map.keys()), format_func=lambda x: all_branches_map[x], default=user.get('branch_ids', []), key=f"branch_{uid}", disabled=is_self)
                        else:
                            assigned_branches = []
                            st.info("Admin có quyền truy cập tất cả các chi nhánh.")

                    if st.form_submit_button("Lưu thay đổi"):
                        update_data = {
                            "display_name": new_display_name,
                            "role": new_role,
                            "branch_ids": assigned_branches,
                            "active": new_active_status,
                        }
                        try:
                            auth_mgr.update_user_record(uid, update_data, new_password)
                            st.success(f"Đã cập nhật thành công thông tin cho {new_display_name}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi: {e}")

    # --- TAB 2: THÊM MỚI ---
    with tab2:
        st.subheader("Tạo tài khoản người dùng mới")
        with st.form("form_create_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                create_username = st.text_input("Tên đăng nhập (username)")
                create_display_name = st.text_input("Tên hiển thị")
                create_role = st.selectbox("Vai trò", options=['staff', 'manager', 'admin'], key="create_role")
            with c2:
                create_password = st.text_input("Mật khẩu", type="password")
                if create_role != 'admin':
                     create_branches = st.multiselect("Các chi nhánh được gán", options=list(all_branches_map.keys()), format_func=lambda x: all_branches_map[x], key="create_branch")
                else:
                    create_branches = []

            if st.form_submit_button("Tạo Người dùng"):
                if not all([create_username, create_display_name, create_password, create_role]):
                    st.error("Vui lòng điền đầy đủ các thông tin bắt buộc.")
                else:
                    user_data = {
                        "username": create_username,
                        "display_name": create_display_name,
                        "role": create_role,
                        "branch_ids": create_branches
                    }
                    try:
                        auth_mgr.create_user_record(user_data, create_password)
                        st.success(f"Đã tạo thành công người dùng '{create_username}'.")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"Lỗi: {e}")

