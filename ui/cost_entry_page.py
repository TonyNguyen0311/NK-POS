
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from managers.cost_manager import CostManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_title, render_section_header, render_sub_header, render_branch_selector
from utils.formatters import format_currency, format_number

# --- Dialog for viewing receipt ---
@st.dialog("Xem chứng từ")
def view_receipt_dialog(image_bytes):
    st.image(image_bytes, use_column_width=True)
    if st.button("Đóng", use_container_width=True):
        st.session_state.viewing_attachment_id = None # Clear state
        st.rerun()

# --- Main Page Rendering ---
def render_cost_entry_page(cost_mgr: CostManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    render_page_title("Ghi nhận Chi phí")

    user = auth_mgr.get_current_user_info()
    if not user:
        st.error("Phiên đăng nhập hết hạn. Vui lòng đăng xuất và đăng nhập lại.")
        return

    user_role = user.get('role', 'staff')
    allowed_branches_map = auth_mgr.get_allowed_branches_map()
    default_branch_id = user.get('default_branch_id')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
    
    # FIX: Use the correct key "CostCategories"
    cost_groups_raw = cost_mgr.get_all_category_items("CostCategories")
    group_map = {g['id']: g['category_name'] for g in cost_groups_raw}

    # Handle dialog trigger
    if 'viewing_attachment_id' in st.session_state and st.session_state.viewing_attachment_id:
        if cost_mgr.image_handler:
            with st.spinner("Đang tải ảnh chứng từ..."):
                image_bytes = cost_mgr.image_handler.load_drive_image(st.session_state.viewing_attachment_id)
                if image_bytes:
                    view_receipt_dialog(image_bytes)
                else:
                    st.error("Không thể tải được ảnh chứng từ.")
                    st.session_state.viewing_attachment_id = None # Clear state on failure
        else:
            st.warning("Trình xử lý ảnh chưa được cấu hình.")
            st.session_state.viewing_attachment_id = None # Clear state

    tab1, tab2 = st.tabs(["Ghi nhận Chi phí mới", "Lịch sử & Quản lý Chi phí"])

    with tab1:
        render_section_header("Ghi nhận chi phí mới")
        with st.form("new_cost_entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                selected_branch_id = render_branch_selector(allowed_branches_map, default_branch_id)
                if not selected_branch_id:
                    st.warning("Bạn cần được gán vào một chi nhánh để thực hiện.")
                    st.stop()

                amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000)
                entry_date = st.date_input("Ngày chi", datetime.now())

            with c2:
                selected_group_id = st.selectbox("Nhóm chi phí", options=list(group_map.keys()), format_func=lambda x: group_map.get(x, x))
                name = st.text_input("Mô tả/Diễn giải chi phí")
            
            st.divider()

            render_sub_header("Phân loại và khấu hao")
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
                    st.error("Vui lòng điền đầy đủ: Tên, Số tiền, và Nhóm chi phí.")
                else:
                    with st.spinner("Đang lưu..."):
                        success, _ = cost_mgr.create_cost_entry(
                            branch_id=selected_branch_id,
                            name=name, amount=amount, group_id=selected_group_id,
                            entry_date=entry_date.isoformat(), created_by=user['uid'],
                            classification='CAPEX' if "CAPEX" in classification_display else 'OPEX',
                            is_amortized=is_amortized, 
                            amortize_months=amortize_months,
                            attachment_file=uploaded_file  # Pass the file object directly
                        )
                        if success:
                            st.rerun()

    with tab2:
        render_section_header("Lịch sử và quản lý chi phí")
        with st.expander("Bộ lọc", expanded=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            today = datetime.now()
            filter_start_date = f_c1.date_input("Từ ngày", today - timedelta(days=30), key="cost_filter_start")
            filter_end_date = f_c2.date_input("Đến ngày", today, key="cost_filter_end")
            
            filter_branch_map = {"all": "Tất cả chi nhánh được phép"}
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
            'status': 'ACTIVE', # Only show active entries by default
            'source_entry_id_is_null': True # Exclude child amortization entries
        }

        if 'all' not in selected_branches:
            filters['branch_ids'] = selected_branches
        else:
            filters['branch_ids'] = list(allowed_branches_map.keys())

        try:
            with st.spinner("Đang tải dữ liệu..."):
                cost_entries = cost_mgr.query_cost_entries(filters)
            
            if not cost_entries:
                st.info("Không có dữ liệu chi phí trong bộ lọc đã chọn.")
            else:
                st.write(f"Tìm thấy {format_number(len(cost_entries))} mục chi phí.")
                for entry in cost_entries:
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([2.5, 1.5, 1, 1.5])
                        with c1:
                            st.markdown(f"**{entry['name']}**")
                            st.markdown(f"*{group_map.get(entry['group_id'], 'N/A')}* - {all_branches_map.get(entry['branch_id'], 'N/A')}")
                            status = entry.get('status')
                            if status == 'AMORTIZED_SOURCE':
                                st.success("Đã phân bổ khấu hao", icon="📊")

                        with c2:
                            st.markdown(f"**{format_currency(entry['amount'], 'đ')}**")
                            st.caption(f"Ngày: {datetime.fromisoformat(entry['entry_date']).strftime('%d/%m/%Y')}")

                        with c3:
                            if entry.get('attachment_id'):
                                if st.button("Xem ảnh", key=f"view_receipt_{entry['id']}", use_container_width=True):
                                    st.session_state.viewing_attachment_id = entry['attachment_id']
                                    st.rerun()

                        with c4: 
                            if user_role == 'admin': # Only admins can permanently delete
                                if f"delete_confirm_{entry['id']}" not in st.session_state:
                                    st.session_state[f"delete_confirm_{entry['id']}"] = False
                                
                                if st.session_state[f"delete_confirm_{entry['id']}"]:
                                    if st.button("❌ XÁC NHẬN", key=f"confirm_delete_{entry['id']}", use_container_width=True, type="primary"):
                                        success, msg = cost_mgr.delete_cost_entry(entry['id'])
                                        if success: st.success(msg)
                                        else: st.error(msg)
                                        st.session_state[f"delete_confirm_{entry['id']}"] = False
                                        st.rerun()
                                else:
                                    if st.button("Xóa", key=f"delete_{entry['id']}", use_container_width=True):
                                        st.session_state[f"delete_confirm_{entry['id']}"] = True
                                        st.rerun()

        except Exception as e:
            st.error(f"Lỗi khi tải lịch sử chi phí: {e}")
            st.exception(e)
