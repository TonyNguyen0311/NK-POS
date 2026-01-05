
import streamlit as st
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from ui._utils import render_page_title

# --- Constants and Configuration ---
ROLES = ['staff', 'supervisor', 'manager', 'admin']

ROLE_STYLES = {
    'admin': {'icon': '👑', 'color': '#D4AF37'},
    'manager': {'icon': '💼', 'color': '#4682B4'},
    'supervisor': {'icon': '👀', 'color': '#5F9EA0'},
    'staff': {'icon': '👤', 'color': '#696969'},
    'default': {'icon': '👤', 'color': '#696969'}
}

# --- Helper Functions ---
def _get_safe_role(user_data, default='staff'):
    """Safely get user role, defaulting if it's missing, None, or not a string."""
    if not user_data: return default
    role = user_data.get('role')
    if not isinstance(role, str) or not role.strip():
        return default
    return role.lower()

def can_perform_action(current_user_role, target_user_role, is_self):
    """Determines permissions for editing or deleting."""
    permissions = {'can_edit': False, 'can_delete': False}
    if is_self:
        return permissions
    if current_user_role == 'admin':
        permissions['can_edit'] = True
        permissions['can_delete'] = True
        return permissions
    try:
        current_role_index = ROLES.index(current_user_role)
        target_role_index = ROLES.index(target_user_role)
        if current_role_index > target_role_index:
            permissions['can_edit'] = True
    except (ValueError, IndexError):
        pass
    return permissions

# --- UI Dialogs ---
@st.dialog("Sửa thông tin Người dùng")
def show_edit_user_dialog(user_data, auth_mgr: AuthManager, branch_mgr: BranchManager):
    st.subheader(f"Chỉnh sửa: {user_data.get('display_name')}")
    current_user_role = _get_safe_role(auth_mgr.get_current_user_info())
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}

    with st.form(key="edit_user_form"):
        display_name = st.text_input("Tên hiển thị", value=user_data.get("display_name", ""))
        password = st.text_input("Mật khẩu mới", type="password", help="Để trống nếu không muốn thay đổi.")
        is_admin = current_user_role == 'admin'
        user_role = _get_safe_role(user_data)
        if is_admin:
            try:
                current_role_index = ROLES.index(user_role)
            except ValueError:
                current_role_index = 0
            role = st.selectbox("Vai trò", options=ROLES, index=current_role_index)
        else:
            role = user_role
            st.text_input("Vai trò", value=role, disabled=True)
        assigned_branches = user_data.get("branch_ids", [])
        if role != 'admin':
            assigned_branches = st.multiselect(
                "Các chi nhánh được gán",
                options=list(all_branches_map.keys()),
                format_func=all_branches_map.get,
                default=[b for b in assigned_branches if b in all_branches_map]
            )
        else:
            st.info("Admin có toàn quyền truy cập tất cả chi nhánh.")
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Lưu thay đổi", use_container_width=True, type="primary"):
            update_data = {
                "display_name": display_name,
                "role": role,
                "branch_ids": assigned_branches if role != 'admin' else []
            }
            try:
                auth_mgr.update_user_record(user_data['uid'], update_data, password if password else None)
                st.toast("Cập nhật thành công!", icon="🎉")
                st.session_state.editing_user = None
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi khi cập nhật: {e}")
        if c2.form_submit_button("Hủy", use_container_width=True):
            st.session_state.editing_user = None
            st.rerun()

@st.dialog("Xác nhận Xóa")
def show_delete_user_dialog(user_data, auth_mgr: AuthManager):
    st.warning(f"Bạn có chắc chắn muốn xóa người dùng **{user_data.get('display_name')}** ({user_data.get('username')}) không?")
    st.write("Hành động này không thể hoàn tác.")
    c1, c2 = st.columns(2)
    if c1.button("Xóa vĩnh viễn", use_container_width=True, type="primary"):
        try:
            auth_mgr.delete_user_record(user_data['uid'])
            st.toast("Đã xóa người dùng.", icon="🗑️")
            st.session_state.deleting_user = None
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi khi xóa: {e}")
    if c2.button("Hủy", use_container_width=True):
        st.session_state.deleting_user = None
        st.rerun()

# --- UI Rendering ---
def render_create_user_form(auth_mgr: AuthManager, branch_mgr: BranchManager):
    current_user_role = _get_safe_role(auth_mgr.get_current_user_info())
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}
    try:
        creatable_roles = ROLES[:ROLES.index(current_user_role)]
    except ValueError:
        creatable_roles = []
    if current_user_role == 'admin':
        creatable_roles = ROLES
    if not creatable_roles:
        st.info("Bạn không có quyền tạo người dùng mới.")
        return
    with st.form(key="create_user_form", clear_on_submit=True):
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
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi tạo người dùng: {e}")

def render_user_list(users, current_user, auth_mgr: AuthManager, branch_mgr: BranchManager):
    search_query = st.text_input("Tìm kiếm (theo tên hoặc username)", key="user_search").lower()
    current_user_role = _get_safe_role(current_user)
    current_user_uid = current_user.get('uid')
    current_user_role_index = ROLES.index(current_user_role)
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}
    visible_users = []
    for user in users:
        user_role = _get_safe_role(user)
        try:
            user_role_index = ROLES.index(user_role)
        except ValueError:
            continue
        can_see = (current_user_role == 'admin') or (user_role_index <= current_user_role_index)
        if can_see:
            search_match = (search_query in user.get('display_name', '').lower() or
                            search_query in user.get('username', '').lower())
            if not search_query or search_match:
                visible_users.append(user)
    visible_users.sort(key=lambda u: ROLES.index(_get_safe_role(u)), reverse=True)
    cols = [0.25, 0.2, 0.15, 0.2, 0.2]
    c = st.columns(cols)
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
            user_role = _get_safe_role(user)
            is_self = (uid == current_user_uid)
            is_active = user.get("active", False)
            permissions = can_perform_action(current_user_role, user_role, is_self)
            c = st.columns(cols)
            c[0].write(f"**{user.get('display_name')}**")
            c[0].write(f"*{user.get('username')}*")
            style = ROLE_STYLES.get(user_role, ROLE_STYLES['default'])
            c[1].markdown(f"<div style='background-color: {style['color']}; color: white; border-radius: 0.5rem; padding: 0.2rem 0.6rem; text-align: center; display: inline-block;'>{style['icon']} {user_role.upper()}</div>", unsafe_allow_html=True)
            status_color = "#28a745" if is_active else "#dc3545"
            status_icon = "✔️" if is_active else "✖️"
            c[2].markdown(f"<div style='background-color: {status_color}; color: white; border-radius: 0.5rem; width: 2.2rem; height: 1.8rem; display: flex; align-items: center; justify-content: center;'>{status_icon}</div>", unsafe_allow_html=True)
            branch_names = [all_branches_map.get(b_id, "?") for b_id in user.get("branch_ids", [])]
            c[3].text(", ".join(branch_names) if branch_names else "Tất cả (Admin)")
            action_col = c[4]
            if is_self:
                action_col.text("Là bạn")
            else:
                num_buttons = permissions['can_edit'] + permissions['can_delete']
                if num_buttons > 0:
                    btn_cols = action_col.columns(num_buttons)
                    button_idx = 0
                    if permissions['can_edit']:
                        if btn_cols[button_idx].button("Sửa", key=f"edit_{uid}", use_container_width=True):
                            st.session_state.editing_user = user
                            st.rerun()
                        button_idx += 1
                    if permissions['can_delete']:
                        if btn_cols[button_idx].button("Xóa", key=f"del_{uid}", use_container_width=True, type="secondary"):
                            st.session_state.deleting_user = user
                            st.rerun()
                else:
                    action_col.text("—")

def render_user_management_page(auth_mgr: AuthManager, branch_mgr: BranchManager):
    render_page_title("Quản lý Người dùng")
    current_user = auth_mgr.get_current_user_info()
    if not current_user:
        st.warning("Vui lòng đăng nhập.")
        return
    current_role = _get_safe_role(current_user)
    if current_role not in ['admin', 'manager', 'supervisor']:
        st.error("Bạn không có quyền truy cập chức năng này.")
        return
    try:
        all_users = auth_mgr.list_users()
    except Exception as e:
        st.error(f"Lỗi khi tải danh sách người dùng: {e}")
        return
    if "editing_user" in st.session_state and st.session_state.editing_user:
        show_edit_user_dialog(st.session_state.editing_user, auth_mgr, branch_mgr)
    if "deleting_user" in st.session_state and st.session_state.deleting_user:
        show_delete_user_dialog(st.session_state.deleting_user, auth_mgr)
    try:
        creatable_roles = ROLES[:ROLES.index(current_role)]
        if current_role == 'admin': creatable_roles = ROLES
    except ValueError:
        creatable_roles = []
    if creatable_roles:
        with st.expander("＋ Tạo Người dùng mới"):
            render_create_user_form(auth_mgr, branch_mgr)
    st.divider()
    st.subheader("Danh sách Người dùng")
    render_user_list(all_users, current_user, auth_mgr, branch_mgr)
