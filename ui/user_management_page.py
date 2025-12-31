
import streamlit as st
import pandas as pd
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager

ROLES = ['staff', 'supervisor', 'manager', 'admin']
ALLOWED_TO_CREATE = {
    'admin': ['staff', 'supervisor', 'manager', 'admin'],
    'manager': ['staff', 'supervisor'],
    'supervisor': ['staff'],
    'staff': []
}

def render_user_management_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    """
    Renders the user management page with role-based access control.
    """
    st.header("Quản lý Người dùng")

    current_user = auth_mgr.get_current_user_info()
    current_role = current_user.get('role', 'staff').lower()

    if current_role not in ['admin', 'manager', 'supervisor']:
        st.error("Bạn không có quyền truy cập chức năng này.")
        return

    try:
        all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
        all_users = auth_mgr.list_users()
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu: {e}")
        return

    # --- ACTION: Add new user ---
    if st.button("＋ Thêm Người dùng mới", type="primary"):
        st.session_state['show_user_form'] = True
        st.session_state['editing_user'] = None
    
    # --- DIALOG for Add/Edit User ---
    if st.session_state.get('show_user_form', False):
        editing_user = st.session_state.get('editing_user')
        dialog_title = "Sửa thông tin Người dùng" if editing_user else "Tạo Người dùng mới"

        with st.form(key="user_form"):
            st.subheader(dialog_title)
            
            user_data = editing_user or {}
            
            c1, c2 = st.columns(2)
            with c1:
                username = st.text_input("Tên đăng nhập", value=user_data.get("username", ""), disabled=bool(editing_user))
                display_name = st.text_input("Tên hiển thị", value=user_data.get("display_name", ""))
                password = st.text_input("Mật khẩu mới", type="password", help="Để trống nếu không muốn thay đổi.")

            with c2:
                # Role selection logic
                creatable_roles = ALLOWED_TO_CREATE.get(current_role, [])
                user_role = user_data.get('role', creatable_roles[0] if creatable_roles else '').lower()
                
                role_index = 0
                if user_role in creatable_roles:
                    role_index = creatable_roles.index(user_role)
                
                role = st.selectbox("Vai trò", options=creatable_roles, index=role_index, disabled=(current_role != 'admin' and bool(editing_user)))
                
                # Branch selection logic
                assigned_branches = []
                if role != 'admin':
                    assigned_branches = st.multiselect(
                        "Các chi nhánh được gán",
                        options=list(all_branches_map.keys()),
                        format_func=all_branches_map.get,
                        default=[b for b in user_data.get("branch_ids", []) if b in all_branches_map]
                    )
                else:
                    st.info("Admin có quyền truy cập tất cả chi nhánh.")

            # --- Form Submission ---
            submitted = st.form_submit_button("Lưu")
            if submitted:
                if not username or not display_name:
                    st.error("Tên đăng nhập và Tên hiển thị là bắt buộc.")
                else:
                    form_data = {
                        "username": username,
                        "display_name": display_name,
                        "role": role,
                        "branch_ids": assigned_branches if role != 'admin' else []
                    }
                    try:
                        if editing_user:
                            auth_mgr.update_user_record(editing_user['uid'], form_data, password)
                            st.success("Cập nhật thành công!")
                        else:
                            if not password:
                                st.error("Mật khẩu là bắt buộc khi tạo người dùng mới.")
                            else:
                                auth_mgr.create_user_record(form_data, password)
                                st.success("Tạo người dùng thành công!")
                        
                        st.session_state['show_user_form'] = False
                        st.session_state['editing_user'] = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
            
            if st.form_submit_button("Hủy", type="secondary"):
                st.session_state['show_user_form'] = False
                st.session_state['editing_user'] = None
                st.rerun()


    st.divider()

    # --- Filter and Display Users ---
    search_query = st.text_input("Tìm kiếm người dùng (theo tên hoặc username)", "").lower()

    # Filter logic
    visible_users = []
    allowed_to_see = ALLOWED_TO_CREATE.get(current_role, [])
    
    for user in all_users:
        user_role_lower = user.get('role', 'staff').lower()
        is_self = user.get('uid') == current_user.get('uid')

        # Determine visibility
        can_see = (current_role == 'admin') or is_self or (user_role_lower in allowed_to_see)
        
        if can_see:
            # Search filter
            if search_query in user.get('display_name', '').lower() or search_query in user.get('username', '').lower():
                 visible_users.append(user)

    visible_users.sort(key=lambda u: ROLES.index(u.get('role', 'staff').lower()), reverse=True)

    # --- Display Header ---
    c = st.columns([2, 2, 1, 1, 2, 2])
    c[0].markdown("**Tên hiển thị**")
    c[1].markdown("**Username**")
    c[2].markdown("**Vai trò**")
    c[3].markdown("**Trạng thái**")
    c[4].markdown("**Chi nhánh**")
    c[5].markdown("**Hành động**")

    # --- Display User List ---
    if not visible_users:
        st.info("Không có người dùng nào phù hợp.")
    else:
        for user in visible_users:
            user_role_lower = user.get('role', 'staff').lower()
            uid = user.get('uid')
            is_self = (uid == current_user.get('uid'))
            
            can_edit = (current_role == 'admin' or ROLES.index(current_role) > ROLES.index(user_role_lower)) and not is_self

            cols = st.columns([2, 2, 1, 1, 2, 2])
            cols[0].text(user.get("display_name"))
            cols[1].text(user.get("username"))
            cols[2].text(user_role_lower.upper())
            
            # Status
            active = user.get("active", False)
            cols[3].success("✔️ Hoạt động") if active else cols[3].error("✖️ Vô hiệu")
            
            # Branches
            branch_names = [all_branches_map.get(b_id, "N/A") for b_id in user.get("branch_ids", [])]
            cols[4].text(", ".join(branch_names) if branch_names else "Tất cả (Admin)")

            # Actions
            if can_edit:
                if cols[5].button("Sửa", key=f"edit_{uid}", use_container_width=True):
                    st.session_state['show_user_form'] = True
                    st.session_state['editing_user'] = user
                    st.rerun()

                # Toggle active status
                new_status = not active
                button_text = "Vô hiệu hóa" if active else "Kích hoạt"
                if cols[5].button(button_text, key=f"toggle_{uid}", use_container_width=True):
                    try:
                        auth_mgr.update_user_record(uid, {"active": new_status})
                        st.success(f"Đã {button_text.lower()} người dùng {user.get('display_name')}.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
            else:
                cols[5].text("—")
