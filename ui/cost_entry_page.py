
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from managers.cost_manager import CostManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

COST_CLASSIFICATIONS = {
    "FIXED": "Định phí (Mặt bằng, Lương,...)",
    "VARIABLE": "Biến phí (Nguyên vật liệu, Điện nước,...)",
    "AMORTIZED": "Chi phí phân bổ (Marketing, Sửa chữa lớn,...)",
    "CAPEX": "Chi phí vốn (Mua sắm máy móc, Xây dựng,...)"
}

def render_cost_entry_page(cost_mgr: CostManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    st.header("📝 Ghi nhận Chi phí")

    user = auth_mgr.get_current_user_info()
    if not user:
        st.error("Phiên đăng nhập hết hạn. Vui lòng đăng xuất và đăng nhập lại.")
        return

    user_role = user.get('role', 'staff')
    user_branches = user.get('branch_ids', [])
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
    allowed_branches_map = {bid: all_branches_map[bid] for bid in user_branches if bid in all_branches_map}
    if user_role == 'admin':
        allowed_branches_map = all_branches_map

    if not allowed_branches_map:
        st.warning("Tài khoản của bạn chưa được phân quyền vào chi nhánh nào. Vui lòng liên hệ Admin.")
        return

    cost_groups_raw = cost_mgr.get_cost_groups()
    group_map = {g['id']: g['group_name'] for g in cost_groups_raw}

    tab1, tab2 = st.tabs(["Ghi nhận Chi phí mới", "Lịch sử & Quản lý Chi phí"])

    # --- TAB 1: GHI NHẬN CHI PHÍ MỚI ---
    with tab1:
        with st.form("new_cost_entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                if len(allowed_branches_map) > 1:
                    selected_branch_id = st.selectbox("Chi nhánh", options=list(allowed_branches_map.keys()), format_func=lambda x: allowed_branches_map[x], key="cost_branch")
                else:
                    selected_branch_id = list(allowed_branches_map.keys())[0]
                    st.text_input("Chi nhánh", value=allowed_branches_map[selected_branch_id], disabled=True)
                
                amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000, key="cost_amount")
                entry_date = st.date_input("Ngày chi", key="cost_date")

            with c2:
                selected_group_id = st.selectbox("Nhóm chi phí", options=list(group_map.keys()), format_func=lambda x: group_map.get(x, x), key="cost_group")
                classification = st.selectbox("Phân loại chi phí", options=list(COST_CLASSIFICATIONS.keys()), format_func=lambda k: COST_CLASSIFICATIONS[k], key="cost_class")
                
            name = st.text_input("Mô tả/Diễn giải chi phí", key="cost_name")
            
            # --- NEW: Image Upload ---
            uploaded_file = st.file_uploader("Ảnh hóa đơn/chứng từ (tùy chọn)", type=["jpg", "jpeg", "png"])

            is_amortized = st.checkbox("Phân bổ chi phí này (chia đều cho nhiều tháng tới)", key="cost_amortize_check")
            amortize_months = 0
            if is_amortized:
                amortize_months = st.number_input("Phân bổ trong bao nhiêu tháng?", min_value=1, max_value=36, value=3, step=1, key="cost_amortize_months")
            
            submitted = st.form_submit_button("Lưu Chi phí")

            if submitted:
                if not name or amount <= 0 or not selected_group_id:
                    st.error("Vui lòng điền đầy đủ các thông tin bắt buộc: Mô tả, Số tiền và Nhóm chi phí.")
                else:
                    try:
                        receipt_url = None
                        if uploaded_file:
                            receipt_url = cost_mgr.upload_receipt_image(uploaded_file)
                        
                        cost_mgr.create_cost_entry(
                            branch_id=selected_branch_id,
                            name=name,
                            amount=amount,
                            group_id=selected_group_id,
                            entry_date=entry_date.isoformat(),
                            created_by=user['uid'],
                            classification=classification, 
                            is_amortized=is_amortized,
                            amortize_months=amortize_months,
                            receipt_url=receipt_url # Save the URL
                        )
                        st.success(f"Đã ghi nhận chi phí '{name}' thành công!")
                    except Exception as e:
                        st.error(f"Lỗi khi ghi nhận chi phí: {e}")
    
    # --- TAB 2: LỊCH SỬ & QUẢN LÝ ---
    with tab2:
        with st.expander("Bộ lọc", expanded=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            today = datetime.now()
            filter_start_date = f_c1.date_input("Từ ngày", today - timedelta(days=30), key="cost_filter_start")
            filter_end_date = f_c2.date_input("Đến ngày", today, key="cost_filter_end")
            
            if len(allowed_branches_map) > 1:
                branch_options = ['all'] + list(allowed_branches_map.keys())
                format_func = lambda x: "Tất cả chi nhánh" if x == 'all' else allowed_branches_map[x]
                selected_branches = f_c3.multiselect("Lọc theo chi nhánh", options=branch_options, format_func=format_func, default='all')
            else:
                selected_branches = list(allowed_branches_map.keys())

        filters = {
            'start_date': datetime.combine(filter_start_date, datetime.min.time()).isoformat(),
            'end_date': datetime.combine(filter_end_date, datetime.max.time()).isoformat(),
            'status': 'ACTIVE'
        }

        if 'all' in selected_branches:
            filters['branch_ids'] = list(allowed_branches_map.keys())
        else:
            filters['branch_ids'] = selected_branches

        try:
            cost_entries = cost_mgr.query_cost_entries(filters)
            
            if not cost_entries:
                st.info("Không có dữ liệu chi phí trong bộ lọc đã chọn.")
            else:
                df = pd.DataFrame(cost_entries)
                df['entry_date'] = pd.to_datetime(df['entry_date']).dt.strftime('%Y-%m-%d')
                df['branch_name'] = df['branch_id'].map(all_branches_map)
                df['group_name'] = df['group_id'].map(group_map)

                st.write(f"Tìm thấy {len(df)} mục chi phí.")
                for index, row in df.iterrows():
                    st.markdown("---")
                    c1, c2, c3 = st.columns([2, 2, 1])
                    with c1:
                        st.markdown(f"**{row['name']}**")
                        st.markdown(f"*{row['group_name']}* - {all_branches_map.get(row['branch_id'])}")
                    with c2:
                        st.markdown(f"**{row['amount']:,} VNĐ**")
                        st.caption(f"Ngày: {row['entry_date']}")
                    with c3:
                        if row.get('receipt_url'):
                            st.link_button("Xem ảnh", row['receipt_url'])

                    # --- Action Buttons based on Role ---
                    can_cancel = (user_role in ['admin', 'manager']) or (user_role == 'staff' and row['created_by'] == user['uid'])
                    can_delete = user_role == 'admin'
                    
                    btn_c1, btn_c2, btn_c3 = st.columns(3)
                    if can_cancel:
                        if btn_c2.button("Hủy phiếu chi", key=f"cancel_{row['id']}", use_container_width=True):
                            cost_mgr.cancel_cost_entry(row['id'], user['uid'])
                            st.success(f"Đã hủy phiếu chi '{row['name']}'.")
                            st.rerun()

                    if can_delete:
                        if btn_c3.button("❌ Xóa vĩnh viễn", key=f"delete_{row['id']}", use_container_width=True):
                            cost_mgr.hard_delete_cost_entry(row['id'])
                            st.warning(f"Đã XÓA VĨNH VIỄN phiếu chi '{row['name']}'.")
                            st.rerun()

        except Exception as e:
            st.error(f"Lỗi khi tải lịch sử chi phí: {e}")
