
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from managers.cost_manager import CostManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_header, render_branch_selector # Import the new utils

def render_cost_entry_page(cost_mgr: CostManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    # Use the new header utility
    render_page_header("Ghi nhận Chi phí", "📝")

    user = auth_mgr.get_current_user_info()
    if not user:
        st.error("Phiên đăng nhập hết hạn. Vui lòng đăng xuất và đăng nhập lại.")
        return

    user_role = user.get('role', 'staff')
    user_branches = user.get('branch_ids', [])
    default_branch_id = user.get('default_branch_id')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
    
    # Determine allowed branches based on user role
    if user_role == 'admin':
        allowed_branches_map = all_branches_map
    else:
        allowed_branches_map = {bid: all_branches_map[bid] for bid in user_branches if bid in all_branches_map}

    cost_groups_raw = cost_mgr.get_cost_groups()
    group_map = {g['id']: g['group_name'] for g in cost_groups_raw}

    tab1, tab2 = st.tabs(["Ghi nhận Chi phí mới", "Lịch sử & Quản lý Chi phí"])

    with tab1:
        with st.form("new_cost_entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                # Use the new branch selector utility
                selected_branch_id = render_branch_selector(allowed_branches_map, default_branch_id)
                if not selected_branch_id: # Stop if user has no access to any branch
                    return

                amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000)
                entry_date = st.date_input("Ngày chi", datetime.now())

            with c2:
                selected_group_id = st.selectbox("Nhóm chi phí", options=list(group_map.keys()), format_func=lambda x: group_map.get(x, x))
                name = st.text_input("Mô tả/Diễn giải chi phí")
            
            st.divider()

            # OPEX/CAPEX Classification
            classification_display = st.selectbox(
                "Phân loại", 
                ["Chi phí hoạt động (OPEX)", "Chi phí vốn (CAPEX)"],
                help="**OPEX**: Chi phí hoạt động hàng ngày. **CAPEX**: Chi phí đầu tư tài sản lớn, có thể khấu hao."
            )

            is_amortized = False
            amortize_months = 0
            if classification_display == "Chi phí vốn (CAPEX)":
                is_amortized = st.toggle("Tính khấu hao cho chi phí này?", help="Bật nếu đây là tài sản cần được khấu hao giá trị theo thời gian.")
                if is_amortized:
                    amortize_months = st.number_input("Khấu hao trong (tháng)", min_value=1, max_value=360, value=12, step=1)

            uploaded_file = st.file_uploader("Ảnh hóa đơn/chứng từ (tùy chọn)", type=["jpg", "jpeg", "png"])
            
            submitted = st.form_submit_button("Lưu Chi phí", use_container_width=True)

            if submitted:
                if not name or amount <= 0 or not selected_group_id:
                    st.error("Vui lòng điền đầy đủ các thông tin bắt buộc: Mô tả, Số tiền và Nhóm chi phí.")
                else:
                    with st.spinner("Đang lưu chi phí..."):
                        try:
                            receipt_url = None
                            if uploaded_file:
                                receipt_url = cost_mgr.upload_receipt_image(uploaded_file)
                            
                            db_classification = 'CAPEX' if classification_display == "Chi phí vốn (CAPEX)" else 'OPEX'
                            
                            cost_mgr.create_cost_entry(
                                branch_id=selected_branch_id,
                                name=name,
                                amount=amount,
                                group_id=selected_group_id,
                                entry_date=entry_date.isoformat(),
                                created_by=user['uid'],
                                classification=db_classification,
                                is_amortized=is_amortized,
                                amortize_months=amortize_months,
                                receipt_url=receipt_url
                            )
                            st.success(f"Đã ghi nhận chi phí '{name}' thành công!")
                        except Exception as e:
                            st.error(f"Lỗi khi ghi nhận chi phí: {e}")
    
    with tab2:
        with st.expander("Bộ lọc", expanded=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            today = datetime.now()
            filter_start_date = f_c1.date_input("Từ ngày", today - timedelta(days=30), key="cost_filter_start")
            filter_end_date = f_c2.date_input("Đến ngày", today, key="cost_filter_end")
            
            filter_branch_map = {"all": "Tất cả chi nhánh"}
            filter_branch_map.update(allowed_branches_map)

            selected_branches = f_c3.multiselect(
                "Lọc theo chi nhánh", 
                options=list(filter_branch_map.keys()), 
                format_func=lambda x: filter_branch_map[x], 
                default='all'
            )

        filters = {
            'start_date': datetime.combine(filter_start_date, datetime.min.time()).isoformat(),
            'end_date': datetime.combine(filter_end_date, datetime.max.time()).isoformat(),
            'status': 'ACTIVE'
        }

        if 'all' not in selected_branches:
            filters['branch_ids'] = selected_branches
        else: # if 'all' is selected, filter by the branches the user is allowed to see
            filters['branch_ids'] = list(allowed_branches_map.keys())

        try:
            with st.spinner("Đang tải dữ liệu..."):
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
                        st.markdown(f"*{row.get('group_name', 'N/A')}* - {row.get('branch_name', 'N/A')}")
                        if row.get('classification') == 'CAPEX':
                            if row.get('is_amortized') and row.get('amortization_months', 0) > 0:
                                st.info(f"CAPEX / Khấu hao trong {row['amortization_months']} tháng", icon="📊")
                            else:
                                st.info("CAPEX", icon="📊")

                    with c2:
                        st.markdown(f"**{row['amount']:,} VNĐ**")
                        st.caption(f"Ngày: {row['entry_date']}")
                    with c3:
                        if row.get('receipt_url'):
                            st.link_button("Xem ảnh", row['receipt_url'])

                    # Action Buttons
                    can_cancel = (user_role in ['admin', 'manager']) or (user_role == 'staff' and row['created_by'] == user['uid'])
                    can_delete = user_role == 'admin'
                    
                    if can_cancel or can_delete:
                        btn_c1, btn_c2 = st.columns(2)
                        if can_cancel:
                            if btn_c1.button("Hủy phiếu", key=f"cancel_{row['id']}", use_container_width=True):
                                cost_mgr.cancel_cost_entry(row['id'], user['uid'])
                                st.success(f"Đã hủy phiếu chi '{row['name']}'.")
                                st.rerun()

                        if can_delete:
                            # Add a confirmation step to prevent accidental deletion
                            if f"delete_confirm_{row['id']}" not in st.session_state:
                                st.session_state[f"delete_confirm_{row['id']}"] = False
                            
                            if st.session_state[f"delete_confirm_{row['id']}"]:
                                if btn_c2.button("❌ XÁC NHẬN XÓA", key=f"confirm_delete_{row['id']}", use_container_width=True, type="primary"):
                                    cost_mgr.hard_delete_cost_entry(row['id'])
                                    st.warning(f"Đã XÓA VĨNH VIỄN phiếu chi '{row['name']}'.")
                                    del st.session_state[f"delete_confirm_{row['id']}"]
                                    st.rerun()
                            else:
                                if btn_c2.button("Xóa vĩnh viễn", key=f"delete_{row['id']}", use_container_width=True):
                                    st.session_state[f"delete_confirm_{row['id']}"] = True
                                    st.rerun()


        except Exception as e:
            st.error(f"Lỗi khi tải lịch sử chi phí: {e}")
            st.exception(e)

