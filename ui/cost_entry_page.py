
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from managers.cost_manager import CostManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_header, render_branch_selector
from utils.formatters import format_currency, format_number

# --- Dialog for viewing receipt ---
@st.dialog("Xem chứng từ")
def view_receipt_dialog(image_url):
    st.image(image_url, use_column_width=True)
    if st.button("Đóng", use_container_width=True):
        st.rerun()

# --- Main Page Rendering ---
def render_cost_entry_page(cost_mgr: CostManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    render_page_header("Ghi nhận Chi phí", "📝")

    user = auth_mgr.get_current_user_info()
    if not user:
        st.error("Phiên đăng nhập hết hạn. Vui lòng đăng xuất và đăng nhập lại.")
        return

    user_role = user.get('role', 'staff')
    allowed_branches_map = auth_mgr.get_allowed_branches_map()
    default_branch_id = user.get('default_branch_id')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
    
    cost_groups_raw = cost_mgr.get_all_category_items("CostGroups")
    group_map = {g['id']: g['category_name'] for g in cost_groups_raw}

    if 'viewing_receipt_url' in st.session_state and st.session_state.viewing_receipt_url:
        view_receipt_dialog(st.session_state.viewing_receipt_url)

    tab1, tab2 = st.tabs(["Ghi nhận Chi phí mới", "Lịch sử & Quản lý Chi phí"])

    with tab1:
        with st.form("new_cost_entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                selected_branch_id = render_branch_selector(allowed_branches_map, default_branch_id)
                if not selected_branch_id:
                    st.stop()

                amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000)
                entry_date = st.date_input("Ngày chi", datetime.now())

            with c2:
                selected_group_id = st.selectbox("Nhóm chi phí", options=list(group_map.keys()), format_func=lambda x: group_map.get(x, x))
                name = st.text_input("Mô tả/Diễn giải chi phí")
            
            st.divider()

            classification_display = st.selectbox(
                "Phân loại", 
                ["Chi phí hoạt động (OPEX)", "Chi phí vốn (CAPEX)"],
                help="**OPEX**: Chi phí hàng ngày. **CAPEX**: Đầu tư tài sản lớn."
            )

            is_amortized = False
            amortize_months = 0
            if classification_display == "Chi phí vốn (CAPEX)":
                is_amortized = st.toggle("Tính khấu hao?", help="Bật nếu đây là tài sản cần khấu hao.")
                if is_amortized:
                    amortize_months = st.number_input("Khấu hao trong (tháng)", min_value=1, value=12)

            uploaded_file = st.file_uploader("Ảnh hóa đơn/chứng từ", type=["jpg", "jpeg", "png"])
            
            if st.form_submit_button("Lưu Chi phí", use_container_width=True):
                if not all([name, amount > 0, selected_group_id]):
                    st.error("Vui lòng điền đầy đủ thông tin.")
                else:
                    with st.spinner("Đang lưu..."):
                        try:
                            receipt_url = cost_mgr.upload_receipt_image(uploaded_file) if uploaded_file else None
                            cost_mgr.create_cost_entry(
                                branch_id=selected_branch_id,
                                name=name, amount=amount, group_id=selected_group_id,
                                entry_date=entry_date.isoformat(), created_by=user['uid'],
                                classification='CAPEX' if "CAPEX" in classification_display else 'OPEX',
                                is_amortized=is_amortized, amortize_months=amortize_months,
                                receipt_url=receipt_url
                            )
                            st.success(f"Đã ghi nhận chi phí '{name}'!")
                        except Exception as e:
                            st.error(f"Lỗi: {e}")

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
        else:
            if user_role == 'admin':
                filters['branch_ids'] = list(all_branches_map.keys())
            else:
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

                st.write(f"Tìm thấy {format_number(len(df))} mục chi phí.")
                for index, row in df.iterrows():
                    st.markdown("---")
                    c1, c2, c3 = st.columns([2, 2, 1])
                    with c1:
                        st.markdown(f"**{row['name']}**")
                        st.markdown(f"*{row.get('group_name', 'N/A')}* - {row.get('branch_name', 'N/A')}")
                        if row.get('classification') == 'CAPEX':
                             st.info(f"CAPEX / Khấu hao {row.get('amortize_months', 0)} tháng" if row.get('is_amortized') else "CAPEX", icon="📊")

                    with c2:
                        st.markdown(f"**{format_currency(row['amount'], 'đ')}**")
                        st.caption(f"Ngày: {row['entry_date']}")
                    with c3:
                        if row.get('receipt_url'):
                            if st.button("Xem ảnh", key=f"view_receipt_{row['id']}", use_container_width=True):
                                st.session_state.viewing_receipt_url = row['receipt_url']
                                st.rerun()
                    
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
