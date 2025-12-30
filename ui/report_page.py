
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Import managers
from managers.report_manager import ReportManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

def render_report_page(report_mgr: ReportManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    st.header("Báo cáo & Phân tích Kinh doanh")

    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.error("Vui lòng đăng nhập để xem báo cáo.")
        return

    # --- LOGIC PHÂN QUYỀN VÀ LỌC DỮ LIỆU ---
    user_role = user_info.get('role', 'staff')
    user_branches = user_info.get('branch_ids', [])

    all_branches_map = {b['id']: b['name'] for b in branch_mgr.get_branches()}
    allowed_branches_map = {}

    if user_role == 'admin':
        allowed_branches_map = all_branches_map
        allowed_branches_map['all'] = "Toàn bộ chuỗi"
        default_branch_selection = 'all'
    else: # manager hoặc staff
        if not user_branches:
            st.warning("Tài khoản của bạn chưa được gán vào chi nhánh nào. Vui lòng liên hệ Admin.")
            return
        allowed_branches_map = {branch_id: all_branches_map[branch_id] for branch_id in user_branches if branch_id in all_branches_map}
        default_branch_selection = user_branches[0]

    # --- BỘ LỌC CHUNG ---
    st.write("**Tùy chọn lọc:**")
    c1, c2, c3 = st.columns(3)

    with c1:
        # Chỉ hiển thị ô chọn nếu người dùng có quyền xem nhiều hơn 1 chi nhánh
        if len(allowed_branches_map) > 1 or user_role == 'admin':
            selected_branch = st.selectbox(
                "Chọn chi nhánh",
                options=list(allowed_branches_map.keys()),
                format_func=lambda x: allowed_branches_map[x],
                index=list(allowed_branches_map.keys()).index(default_branch_selection)
            )
        else:
            # Tự động chọn chi nhánh duy nhất được phép
            selected_branch = default_branch_selection
            st.text_input("Chi nhánh", value=allowed_branches_map[selected_branch], disabled=True)

    with c2:
        start_date = st.date_input("Từ ngày", datetime.now() - timedelta(days=30))
    with c3:
        end_date = st.date_input("Đến ngày", datetime.now())

    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    st.divider()

    # --- HIỂN THỊ BÁO CÁO LÃI/LỖ ---
    if st.button("Xem Báo cáo", type="primary"):
        branch_id_for_query = None if selected_branch == 'all' else selected_branch

        with st.spinner("Đang tổng hợp và tính toán dữ liệu..."):
            pnl_data = report_mgr.get_profit_loss_statement(start_datetime, end_datetime, branch_id_for_query)

            if not pnl_data:
                st.error("Không thể tải được dữ liệu báo cáo cho lựa chọn này.")
                return

            st.subheader(f"Báo cáo Kết quả Kinh doanh")
            st.caption(f"Từ {pnl_data['start_date']} đến {pnl_data['end_date']} cho: **{allowed_branches_map[selected_branch]}**")

            # ... (Phần còn lại của trang hiển thị số liệu không thay đổi) ...
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Tổng Doanh thu", f"{pnl_data['total_revenue']:,.0f} đ")
            kpi2.metric("Lợi nhuận gộp", f"{pnl_data['gross_profit']:,.0f} đ")
            kpi3.metric("Tổng Chi phí HĐ", f"{pnl_data['total_operating_expenses']:,.0f} đ")
            kpi4.metric("LỢI NHUẬN RÒNG", f"{pnl_data['net_profit']:,.0f} đ", delta_color="inverse")

            with st.expander("Xem chi tiết tính toán Lợi nhuận ròng", expanded=True):
                pnl_df = pd.DataFrame([
                    {"Chỉ tiêu": "1. Tổng Doanh thu", "Số tiền": pnl_data['total_revenue']},
                    {"Chỉ tiêu": "2. Giá vốn hàng bán (COGS)", "Số tiền": -pnl_data['total_cogs']},
                    {"Chỉ tiêu": "**3. Lợi nhuận gộp**", "Số tiền": pnl_data['gross_profit']},
                    {"Chỉ tiêu": "", "Số tiền": None},
                    {"Chỉ tiêu": "**4. Chi phí hoạt động**", "Số tiền": None},
                ])
                op_expenses_df = pd.DataFrame([
                    {"Chỉ tiêu": f"   - {group_name}", "Số tiền": -amount}
                    for group_name, amount in pnl_data.get('operating_expenses_by_group', {}).items()
                ])
                pnl_df = pd.concat([pnl_df, op_expenses_df], ignore_index=True)
                pnl_df = pd.concat([
                    pnl_df,
                    pd.DataFrame([
                        {"Chỉ tiêu": "**Tổng chi phí hoạt động**", "Số tiền": -pnl_data['total_operating_expenses']},
                        {"Chỉ tiêu": "", "Số tiền": None},
                        {"Chỉ tiêu": "**5. LỢI NHUẬN RÒNG**", "Số tiền": pnl_data['net_profit']},
                    ])
                ], ignore_index=True)
                st.dataframe(
                    pnl_df.style.format(
                        {"Số tiền": "{:,.0f} đ"},
                        na_rep=""
                    ).apply(lambda x: ['font-weight: bold' if '**' in str(val) else '' for val in x], axis=1),
                    use_container_width=True,
                    hide_index=True
                )
