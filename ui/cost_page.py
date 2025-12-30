
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from managers.cost_manager import CostManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

def render_cost_page(cost_mgr: CostManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    st.header("Quản lý Chi phí Hoạt động")

    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.error("Vui lòng đăng nhập.")
        return

    # --- LOGIC PHÂN QUYỀN ---
    user_role = user_info.get('role', 'staff')
    if user_role not in ['admin', 'manager']:
        st.warning("Bạn không có quyền truy cập vào chức năng này.")
        return

    user_branches = user_info.get('branch_ids', [])
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.get_branches()}
    allowed_branches_map = {branch_id: all_branches_map[branch_id] for branch_id in user_branches if branch_id in all_branches_map}
    if user_role == 'admin': # Admin có quyền trên tất cả chi nhánh
        allowed_branches_map = all_branches_map

    if not allowed_branches_map:
        st.warning("Tài khoản của bạn chưa được gán vào chi nhánh nào. Vui lòng liên hệ Admin.")
        return

    cost_groups_raw = cost_mgr.get_cost_groups()
    group_map = {g['id']: g['group_name'] for g in cost_groups_raw}

    tab1, tab2, tab3 = st.tabs([
        "📝 Ghi nhận Chi phí", 
        "🗂️ Lịch sử & Quản lý", 
        "⚙️ Thiết lập Nhóm Chi phí"
    ])

    # --- TAB 1: GHI NHẬN CHI PHÍ MỚI ---
    with tab1:
        st.subheader("Thêm một chi phí mới")
        with st.form("new_cost_entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                if len(allowed_branches_map) > 1:
                    selected_branch_id = st.selectbox("Chi nhánh", options=list(allowed_branches_map.keys()), format_func=lambda x: allowed_branches_map[x])
                else:
                    selected_branch_id = list(allowed_branches_map.keys())[0]
                    st.text_input("Chi nhánh", value=allowed_branches_map[selected_branch_id], disabled=True)
                amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000)
            with c2:
                selected_group_id = st.selectbox("Nhóm chi phí", options=list(group_map.keys()), format_func=lambda x: group_map.get(x, x))
                entry_date = st.date_input("Ngày chi")
            
            name = st.text_input("Mô tả chi tiết chi phí")
            is_amortized = st.checkbox("Phân bổ chi phí này")
            # ... (phần logic phân bổ giữ nguyên) ...

            if st.form_submit_button("Lưu Chi phí"):
                # ... (phần xử lý lưu giữ nguyên) ...
                pass

    # --- TAB 2: LỊCH SỬ & QUẢN LÝ ---
    with tab2:
        st.subheader("Lịch sử các chi phí đã ghi nhận")
        # Bộ lọc
        with st.expander("Bộ lọc", expanded=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            filter_start_date = f_c1.date_input("Từ ngày", datetime.now() - timedelta(days=30), key="cost_start")
            filter_end_date = f_c2.date_input("Đến ngày", datetime.now(), key="cost_end")
            
            # Lọc theo chi nhánh được phép
            filter_branch_options = {'all': "Tất cả chi nhánh được xem"} if len(allowed_branches_map) > 1 else {}
            filter_branch_options.update(allowed_branches_map)
            selected_filter_branch = f_c3.selectbox("Lọc theo chi nhánh", options=list(filter_branch_options.keys()), format_func=lambda x: filter_branch_options[x])

        filters = {
            'start_date': datetime.combine(filter_start_date, datetime.min.time()).isoformat(),
            'end_date': datetime.combine(filter_end_date, datetime.max.time()).isoformat()
        }
        if selected_filter_branch != 'all':
            filters['branch_id'] = selected_filter_branch
        else:
             # Chỉ query các chi nhánh được phép xem
            filters['branch_ids'] = list(allowed_branches_map.keys())

        cost_entries = cost_mgr.query_cost_entries(filters)
        # ... (phần hiển thị dataframe và actions giữ nguyên) ...

    # --- TAB 3: THIẾT LẬP NHÓM CHI PHÍ (CHỈ ADMIN) ---
    with tab3:
        if user_role == 'admin':
            st.subheader("Quản lý các Nhóm Chi phí")
            # ... (code form tạo và xóa nhóm giữ nguyên) ...
        else:
            st.info("Chỉ tài khoản Quản trị viên (admin) mới có quyền truy cập chức năng này.")
