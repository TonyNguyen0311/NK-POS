
import streamlit as st
import pandas as pd

# Import managers
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager

def render_user_management_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    st.header("Quản lý Người dùng")

    user_info = auth_mgr.get_current_user_info()

    # Chỉ admin mới được truy cập trang này
    if not user_info or user_info.get('role', '').lower() != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        return

    try:
        all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
    except Exception as e:
        st.error(f"Không thể tải danh sách chi nhánh: {e}")
        return

    all_users = auth_mgr.list_users()
    is_admin = user_info.get('role', '').lower() == 'admin'

    tab1, tab2 = st.tabs(["Danh sách Người dùng", "Thêm Người dùng mới"])

    with tab1:
        st.subheader("Danh sách người dùng hiện tại")
        if not all_users:
            st.info("Chưa có người dùng nào trong hệ thống.")
        else:
            for user in all_users:
                uid = user.get('uid', user.get('id'))
                if not uid:
                    continue

                is_self = (uid == user_info.get('uid'))

                with st.expander(f"{user.get('display_name', 'N/A')} (`{user.get('username', 'N/A')}`) - Vai trò: {user.get('role', 'N/A').upper()}"):
                    with st.form(f"form_edit_{uid}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            new_display_name = st.text_input("Tên hiển thị", value=user.get('display_name', ''), key=f"name_{uid}")
                            
                            current_role = user.get('role', 'staff').lower()
                            role_options = ['staff', 'manager', 'admin']
                            
                            try:
                                role_index = role_options.index(current_role)
                            except ValueError:
                                role_index = 0

                            # Chỉ Admin mới có quyền thay đổi vai trò và không thể tự đổi vai trò của mình
                            new_role = st.selectbox("Vai trò", options=role_options, index=role_index, key=f"role_{uid}", disabled=not is_admin or is_self)
                            
                            # Chỉ Admin mới có quyền thay đổi trạng thái và không thể tự hủy
                            new_active_status = st.checkbox("Đang hoạt động", value=user.get('active', True), key=f"active_{uid}", disabled=not is_admin or is_self)
                        
                        with c2:
                            new_password = st.text_input("Mật khẩu mới (để trống nếu không đổi)", type="password", key=f"pass_{uid}")
                            default_branches = user.get('branch_ids', [])
                            valid_defaults = [b_id for b_id in default_branches if b_id in all_branches_map]

                            if new_role != 'admin':
                                # Chỉ Admin mới có quyền gán chi nhánh và không thể tự gán cho mình (vì admin có mọi quyền)
                                assigned_branches = st.multiselect(
                                    "Các chi nhánh được gán",
                                    options=list(all_branches_map.keys()),
                                    format_func=lambda x: all_branches_map.get(x, "Chi nhánh không xác định"),
                                    default=valid_defaults,
                                    key=f"branch_{uid}",
                                    disabled=not is_admin or is_self
                                )
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
                                st.error(f"Lỗi khi cập nhật: {e}")

    with tab2:
        st.subheader("Tạo tài khoản người dùng mới")
        with st.form("form_create_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                create_username = st.text_input("Tên đăng nhập (username)", key="create_username_input")
                create_display_name = st.text_input("Tên hiển thị", key="create_display_name_input")
                create_role = st.selectbox("Vai trò", options=['staff', 'manager', 'admin'], key="create_role_select")
            with c2:
                create_password = st.text_input("Mật khẩu", type="password", key="create_password_input")
                if create_role != 'admin':
                    create_branches = st.multiselect(
                        "Các chi nhánh được gán",
                        options=list(all_branches_map.keys()),
                        format_func=lambda x: all_branches_map.get(x, "Chi nhánh không xác định"),
                        key="create_branch_multiselect"
                    )
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
                    except Exception as e:
                        st.error(f"Lỗi khi tạo người dùng: {e}")
