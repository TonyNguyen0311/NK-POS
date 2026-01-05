
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Import managers
from managers.report_manager import ReportManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

# Import UI utils and formatters
from ui._utils import render_page_header
from utils.formatters import format_currency, format_number

def render_report_page(report_mgr: ReportManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    # 1. RENDER PAGE HEADER
    render_page_header("Báo cáo & Phân tích", "📊")

    # 2. USER PERMISSIONS & DATA ACCESS
    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.warning("Vui lòng đăng nhập để xem báo cáo.")
        return

    user_role = user_info.get('role', 'staff')
    user_branches = user_info.get('branch_ids', [])
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}

    if user_role == 'admin':
        allowed_branches_map = all_branches_map
    else:
        allowed_branches_map = {bid: name for bid, name in all_branches_map.items() if bid in user_branches}

    if not allowed_branches_map:
        st.error("Tài khoản của bạn chưa được gán cho chi nhánh nào. Vui lòng liên hệ quản trị viên.")
        return

    # 3. FILTERING UI
    with st.expander("⚙️ Tùy chọn báo cáo", expanded=True):
        report_type = st.selectbox(
            "Chọn loại báo cáo",
            ["Báo cáo Doanh thu", "Phân tích Lợi nhuận", "Báo cáo Tồn kho"],
            key="report_type_selector"
        )

        selected_branch_ids = st.multiselect(
            "Chọn chi nhánh (có thể chọn nhiều)",
            options=list(allowed_branches_map.keys()),
            format_func=lambda x: allowed_branches_map[x],
            default=list(allowed_branches_map.keys()),
            key="branch_multiselect"
        )

        date_col1, date_col2 = st.columns(2)
        today = datetime.now()
        start_date = date_col1.date_input("Từ ngày", today - timedelta(days=30))
        end_date = date_col2.date_input("Đến ngày", today)
        
        if st.button("📈 Xem báo cáo", type="primary", use_container_width=True):
            if not selected_branch_ids:
                st.warning("Vui lòng chọn ít nhất một chi nhánh.")
            else:
                st.session_state.run_report = True
        else:
            st.session_state.run_report = False

    st.divider()

    # 4. REPORT DISPLAY LOGIC
    if st.session_state.get('run_report', False):
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())

        with st.spinner("Đang xử lý và tải dữ liệu báo cáo..."):
            if report_type == "Báo cáo Doanh thu":
                success, data, message = report_mgr.get_revenue_report(start_datetime, end_datetime, selected_branch_ids)
                if success:
                    st.subheader("Tổng quan Doanh thu")
                    
                    # Display KPIs using formatters
                    kpi_cols = st.columns(4)
                    kpi_cols[0].metric("Tổng Doanh thu", format_currency(data.get('total_revenue', 0), "VNĐ"))
                    kpi_cols[1].metric("Tổng Lợi nhuận gộp", format_currency(data.get('total_profit', 0), "VNĐ"))
                    kpi_cols[2].metric("Số lượng hóa đơn", format_number(data.get('total_orders', 0)))
                    kpi_cols[3].metric("Giá trị/hóa đơn", format_currency(data.get('average_order_value', 0), "VNĐ"))
                    st.divider()
                    
                    # Display charts and dataframes
                    st.write("**Biểu đồ doanh thu theo ngày**")
                    if not data.get('revenue_by_day', pd.DataFrame()).empty:
                        st.line_chart(data['revenue_by_day'])
                    else:
                        st.info("Không có dữ liệu doanh thu trong khoảng thời gian này.")

                    st.write("**Top 5 sản phẩm bán chạy nhất (theo doanh thu)**")
                    top_products_df = data.get('top_products_by_revenue')
                    if top_products_df is not None and not top_products_df.empty:
                        # Assuming the columns are named 'Doanh thu' and 'Lợi nhuận'
                        st.dataframe(
                            top_products_df.style.format({
                                'Doanh thu': lambda x: format_currency(x, 'VNĐ'),
                                'Lợi nhuận': lambda x: format_currency(x, 'VNĐ'),
                                'Số lượng': format_number
                            }), 
                            use_container_width=True
                        )
                    else:
                        st.info("Không có dữ liệu về sản phẩm bán chạy.")
                else:
                    st.error(f"Lỗi khi lấy báo cáo: {message}")

            elif report_type == "Phân tích Lợi nhuận":
                st.info("Tính năng 'Phân tích Lợi nhuận' đang trong giai đoạn phát triển.")

            elif report_type == "Báo cáo Tồn kho":
                st.info("Tính năng 'Báo cáo Tồn kho' đang trong giai đoạn phát triển.")
        
        st.session_state.run_report = False
