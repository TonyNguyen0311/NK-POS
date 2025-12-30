
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from managers.cost_manager import CostManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

# Định nghĩa các loại chi phí
COST_CLASSIFICATIONS = {
    "FIXED": "Định phí (Mặt bằng, Lương,...)",
    "VARIABLE": "Biến phí (Nguyên vật liệu, Điện nước,...)",
    "AMORTIZED": "Chi phí phân bổ (Marketing, Sửa chữa lớn,...)",
    "CAPEX": "Chi phí vốn (Mua sắm máy móc, Xây dựng,...)"
}

def render_cost_page(cost_mgr: CostManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    st.header("Quản lý Chi phí Hoạt động")

    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.error("Vui lòng đăng nhập.")
        return

    # --- LOGIC PHÂN QUYỀN (giữ nguyên) ---
    user_role = user_info.get('role', 'staff')
    if user_role not in ['admin', 'manager']:
        st.warning("Bạn không có quyền truy cập vào chức năng này.")
        return

    user_branches = user_info.get('branch_ids', [])
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.get_branches()}
    allowed_branches_map = {branch_id: all_branches_map[branch_id] for branch_id in user_branches if branch_id in all_branches_map}
    if user_role == 'admin':
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
            # Chọn chi nhánh
            if len(allowed_branches_map) > 1:
                selected_branch_id = st.selectbox("Chi nhánh", options=list(allowed_branches_map.keys()), format_func=lambda x: allowed_branches_map[x])
            else:
                selected_branch_id = list(allowed_branches_map.keys())[0]
                st.text_input("Chi nhánh", value=allowed_branches_map[selected_branch_id], disabled=True)

            c1, c2 = st.columns(2)
            with c1:
                amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000)
                selected_group_id = st.selectbox("Nhóm chi phí", options=list(group_map.keys()), format_func=lambda x: group_map.get(x, x))
            with c2:
                entry_date = st.date_input("Ngày chi")
                # === THÊM TRƯỜNG PHÂN LOẠI CHI PHÍ ===
                classification = st.selectbox("Phân loại chi phí", options=list(COST_CLASSIFICATIONS.keys()), format_func=lambda k: COST_CLASSIFICATIONS[k])
            
            name = st.text_input("Mô tả chi tiết chi phí")

            # Phần phân bổ giữ nguyên
            is_amortized = st.checkbox("Phân bổ chi phí này (chia đều cho nhiều tháng tới)")
            amortize_months = 0
            if is_amortized:
                amortize_months = st.number_input("Phân bổ trong bao nhiêu tháng?", min_value=1, max_value=36, value=3, step=1)
            
            submitted = st.form_submit_button("Lưu Chi phí")

            if submitted:
                if not name or amount <= 0:
                    st.error("Vui lòng điền đầy đủ mô tả và số tiền.")
                else:
                    try:
                        cost_mgr.create_cost_entry(
                            branch_id=selected_branch_id,
                            name=name,
                            amount=amount,
                            group_id=selected_group_id,
                            entry_date=entry_date.isoformat(),
                            created_by=user_info['uid'],
                            # Truyền giá trị classification mới
                            classification=classification, 
                            is_amortized=is_amortized,
                            amortize_months=amortize_months if is_amortized else 0
                        )
                        st.success(f"Đã ghi nhận chi phí '{name}' thành công!")
                    except Exception as e:
                        st.error(f"Lỗi khi ghi nhận chi phí: {e}")

    # --- TAB 2: LỊCH SỬ & QUẢN LÝ ---
    with tab2:
        st.subheader("Lịch sử các chi phí đã ghi nhận")
        # Bộ lọc (giữ nguyên)
        with st.expander("Bộ lọc", expanded=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            filter_start_date = f_c1.date_input("Từ ngày", datetime.now() - timedelta(days=30), key="cost_start")
            filter_end_date = f_c2.date_input("Đến ngày", datetime.now(), key="cost_end")
            
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
            filters['branch_ids'] = list(allowed_branches_map.keys())

        cost_entries = cost_mgr.query_cost_entries(filters)
        
        if cost_entries:
            df = pd.DataFrame(cost_entries)
            # === CẬP NHẬT DF ĐỂ HIỂN THỊ CỘT MỚI ===
            df['entry_date'] = pd.to_datetime(df['entry_date']).dt.strftime('%Y-%m-%d')
            df['branch_name'] = df['branch_id'].map(all_branches_map)
            df['group_name'] = df['group_id'].map(group_map)
            # Dùng map để dịch classification key thành tên dễ đọc
            df['classification_display'] = df['classification'].map(COST_CLASSIFICATIONS)

            st.dataframe(df[[
                'entry_date', 'name', 'amount', 'classification_display', 
                'group_name', 'branch_name', 'created_by'
            ]], column_config={
                "entry_date": "Ngày",
                "name": "Mô tả",
                "amount": st.column_config.NumberColumn("Số tiền", format="%.0f VNĐ"),
                "classification_display": "Phân loại",
                "group_name": "Nhóm",
                "branch_name": "Chi nhánh",
                "created_by": "Người tạo"
            }, use_container_width=True)
        else:
            st.info("Không có dữ liệu chi phí nào trong khoảng thời gian và chi nhánh đã chọn.")

    # --- TAB 3: THIẾT LẬP NHÓM CHI PHÍ (giữ nguyên) ---
    with tab3:
        if user_role == 'admin':
            st.subheader("Quản lý các Nhóm Chi phí")
            # ... (code form tạo và xóa nhóm giữ nguyên) ...
            with st.form("add_group_form", clear_on_submit=True):
                new_group_name = st.text_input("Tên nhóm chi phí mới")
                if st.form_submit_button("Thêm Nhóm"):
                    if new_group_name:
                        try:
                            cost_mgr.create_cost_group(new_group_name)
                            st.success(f"Đã thêm nhóm '{new_group_name}'")
                            st.experimental_rerun()
                        except ValueError as e:
                            st.error(e)
            
            st.write("Các nhóm hiện có:")
            if cost_groups_raw:
                for group in cost_groups_raw:
                    c1, c2 = st.columns([0.8, 0.2])
                    c1.write(group['group_name'])
                    if c2.button("Xóa", key=f"del_{group['id']}"):
                        try:
                            cost_mgr.delete_cost_group(group['id'])
                            st.success(f"Đã xóa nhóm '{group['group_name']}'")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi xóa: {e}")
        else:
            st.info("Chỉ tài khoản Quản trị viên (admin) mới có quyền truy cập chức năng này.")
