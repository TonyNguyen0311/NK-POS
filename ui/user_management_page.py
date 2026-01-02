
import streamlit as st
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from ui._utils import render_page_header

# --- Constants and Configuration ---
ROLES = ['staff', 'supervisor', 'manager', 'admin']
# Defines which roles a given role can create/edit.
ALLOWED_TO_MANAGE = {
    'admin': ['staff', 'supervisor', 'manager', 'admin'],
    'manager': ['staff', 'supervisor'],
    'supervisor': ['staff'],
    'staff': []
}

# --- Helper Functions ---
def can_edit_user(current_user_role, target_user_role, is_self):
    """Check if the current user can edit the target user."""
    if is_self or current_user_role == target_user_role:
        return False # Cannot edit self or users with the same role
    if current_user_role == 'admin':
        return True # Admin can edit anyone (except themselves)
    try:
        # Check if target role is lower in hierarchy
        return ROLES.index(current_user_role) > ROLES.index(target_user_role)
    except (ValueError, IndexError):
        return False

# --- UI for Forms ---

@st.dialog("Sửa thông tin Người dùng")
def show_edit_user_dialog(user_data, auth_mgr: AuthManager, branch_mgr: BranchManager, current_user_role: str):
    """A dialog for editing an existing user."""
    st.subheader(f"Chỉnh sửa: {user_data.get('display_name')}")

    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}

    with st.form(key="edit_user_form"):
        display_name = st.text_input("Tên hiển thị", value=user_data.get("display_name", ""))
        password = st.text_input("Mật khẩu mới", type="password", help="Để trống nếu không muốn thay đổi.")

        # Role selection logic - Only admins can change roles
        is_admin = current_user_role == 'admin'
        editable_roles = ALLOWED_TO_MANAGE.get(current_user_role, [])
        user_role = user_data.get('role', 'staff').lower()

        try:
            current_role_index = editable_roles.index(user_role)
        except ValueError:
            current_role_index = 0

        role = st.selectbox(
            "Vai trò",
            options=editable_roles,
            index=current_role_index,
            disabled=not is_admin # Only admin can change role
        )

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
            st.info("Admin có toàn quyền truy cập tất cả chi nhánh.")

        c1, c2 = st.columns(2)
        if c1.form_submit_button("Lưu thay đổi", use_container_width=True, type="primary"):
            if not display_name:
                st.error("Tên hiển thị là bắt buộc.")
            else:
                update_data = {
                    "display_name": display_name,
                    "role": role,
                    "branch_ids": assigned_branches if role != 'admin' else []
                }
                try:
                    auth_mgr.update_user_record(user_data['uid'], update_data, password if password else None)
                    st.toast("Cập nhật thành công!", icon="🎉")
                    st.session_state.editing_user = None # Close dialog
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi cập nhật: {e}")

        if c2.form_submit_button("Hủy", use_container_width=True):
            st.session_state.editing_user = None
            st.rerun()


def render_create_user_form(auth_mgr: AuthManager, branch_mgr: BranchManager, current_user_role: str):
    """A form displayed in a tab to create a new user."""
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}
    creatable_roles = ALLOWED_TO_MANAGE.get(current_user_role, [])

    if not creatable_roles:
        st.info("Bạn không có quyền tạo người dùng mới.")
        return

    with st.form(key="create_user_form", clear_on_submit=True):
        st.subheader("Điền thông tin người dùng mới")
        c1, c2 = st.columns(2)
        username = c1.text_input("Tên đăng nhập (*)", help="Không thể thay đổi sau khi tạo")
        display_name = c2.text_input("Tên hiển thị (*)")
        password = c1.text_input("Mật khẩu (*)", type="password")
        role = c2.selectbox("Vai trò (*)", options=creatable_roles)

        assigned_branches = []
        if role != 'admin':
            assigned_branches = st.multiselect(
                "Các chi nhánh được gán (*)",
                options=list(all_branches_map.keys()),
                format_func=all_branches_map.get
            )
        else:
            st.info("Admin sẽ có quyền truy cập tất cả chi nhánh.")

        if st.form_submit_button("Tạo Người dùng", use_container_width=True, type="primary"):
            if not all([username, display_name, password, role]):
                st.warning("Vui lòng điền đầy đủ các trường có dấu (*).")
            elif role != 'admin' and not assigned_branches:
                st.warning("Vui lòng gán ít nhất một chi nhánh cho vai trò này.")
            else:
                form_data = {
                    "username": username,
                    "display_name": display_name,
                    "role": role,
                    "branch_ids": assigned_branches if role != 'admin' else []
                }
                try:
                    auth_mgr.create_user_record(form_data, password)
                    st.success(f"Đã tạo thành công người dùng '{display_name}'.")
                except Exception as e:
                    st.error(f"Lỗi khi tạo người dùng: {e}")


def render_user_list(users, current_user, auth_mgr: AuthManager, branch_mgr: BranchManager):
    """Displays the list of users with actions."""
    search_query = st.text_input("Tìm kiếm (theo tên hoặc username)", key="user_search").lower()
    
    current_user_role = current_user.get('role', 'staff').lower()
    current_user_uid = current_user.get('uid')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}

    # Filter logic
    visible_users = []
    allowed_to_see = ALLOWED_TO_MANAGE.get(current_user_role, [])

    for user in users:
        user_role_lower = user.get('role', 'staff').lower()
        is_self = user.get('uid') == current_user_uid

        can_see = (current_user_role == 'admin') or is_self or (user_role_lower in allowed_to_see)

        if can_see:
            search_match = (search_query in user.get('display_name', '').lower() or
                            search_query in user.get('username', '').lower())
            if search_match:
                visible_users.append(user)

    visible_users.sort(key=lambda u: ROLES.index(u.get('role', 'staff').lower()), reverse=True)

    # --- Display Header ---
    c = st.columns([0.2, 0.2, 0.15, 0.25, 0.2])
    c[0].markdown("**Tên & Username**")
    c[1].markdown("**Vai trò**")
    c[2].markdown("**Trạng thái**")
    c[3].markdown("**Chi nhánh**")
    c[4].markdown("**Hành động**")
    st.divider()

    if not visible_users:
        st.info("Không tìm thấy người dùng nào.")
    else:
        for user in visible_users:
            uid = user.get('uid')
            user_role = user.get('role', 'staff').lower()
            is_self = (uid == current_user_uid)
            is_active = user.get("active", False)
            can_edit = can_edit_user(current_user_role, user_role, is_self)

            cols = st.columns([0.2, 0.15, 0.15, 0.25, 0.25])
            
            # Column 1: Name and Username
            cols[0].write(f"**{user.get('display_name')}**")
            cols[0].write(f"*{user.get('username')}*")

            # Column 2: Role
            cols[1].chip(user_role.upper(), icon="👑" if user_role == 'admin' else '👤')

            # Column 3: Status
            cols[2].chip("Hoạt động" if is_active else "Vô hiệu", icon="✔️" if is_active else "✖️")

            # Column 4: Branches
            branch_names = [all_branches_map.get(b_id, "?") for b_id in user.get("branch_ids", [])]
            if branch_names:
                cols[3].text(", ".join(branch_names))
            else:
                cols[3].text("Tất cả (Admin)")


            # Column 5: Actions
            action_col = cols[4]
            if can_edit:
                btn_cols = action_col.columns(2)
                if btn_cols[0].button("Sửa", key=f"edit_{uid}", use_container_width=True):
                    st.session_state.editing_user = user
                    st.rerun()

                toggle_text = "Tắt" if is_active else "Mở"
                if btn_cols[1].button(toggle_text, key=f"toggle_{uid}", use_container_width=True):
                    try:
                        auth_mgr.update_user_record(uid, {"active": not is_active})
                        st.toast(f"Đã {toggle_text.lower()} tài khoản.", icon="👍")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
            elif is_self:
                 action_col.text("Là bạn")
            else:
                action_col.text("—")


def render_user_management_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    render_page_header("Quản lý Người dùng", "👥")

    current_user = auth_mgr.get_current_user_info()
    if not current_user:
        st.warning("Vui lòng đăng nhập.")
        return
        
    current_role = current_user.get('role', 'staff').lower()

    if current_role not in ['admin', 'manager', 'supervisor']:
        st.error("Bạn không có quyền truy cập chức năng này.")
        return

    try:
        all_users = auth_mgr.list_users()
    except Exception as e:
        st.error(f"Lỗi khi tải danh sách người dùng: {e}")
        return

    if "editing_user" in st.session_state and st.session_state.editing_user:
        show_edit_user_dialog(st.session_state.editing_user, auth_mgr, branch_mgr, current_role)

    creatable_roles = ALLOWED_TO_MANAGE.get(current_role, [])
    
    if creatable_roles:
        tab1, tab2 = st.tabs(["📑 Danh sách Người dùng", "＋ Tạo Người dùng mới"])
        with tab1:
            render_user_list(all_users, current_user, auth_mgr, branch_mgr)
        with tab2:
            render_create_user_form(auth_mgr, branch_mgr, current_role)
    else:
        render_user_list(all_users, current_user, auth_mgr, branch_mgr)

