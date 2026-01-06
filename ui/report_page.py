
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Import managers
from managers.report_manager import ReportManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

# Import UI utils and formatters
from ui._utils import render_page_title
from utils.formatters import format_currency, format_number

def render_report_page(report_mgr: ReportManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    # 1. RENDER PAGE HEADER
    render_page_title("Báo cáo & Phân tích")

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
            ["Báo cáo Doanh thu", "Báo cáo Tồn kho", "Phân tích Lợi nhuận"],
            key="report_type_selector"
        )

        is_inventory_report = report_type == "Báo cáo Tồn kho"

        col1, col2 = st.columns(2)
        
        selected_branch_ids = col1.multiselect(
            "Chọn chi nhánh (có thể chọn nhiều)",
            options=list(allowed_branches_map.keys()),
            format_func=lambda x: allowed_branches_map[x],
            default=list(allowed_branches_map.keys()),
            key="branch_multiselect"
        )
        
        # Date filters are not needed for inventory report
        if not is_inventory_report:
            date_col1, date_col2 = st.columns(2)
            today = datetime.now()
            start_date = date_col1.date_input("Từ ngày", today - timedelta(days=30))
            end_date = date_col2.date_input("Đến ngày", today)
        
        if st.button("📈 Xem báo cáo", type="primary", use_container_width=True):
            if not selected_branch_ids:
                st.warning("Vui lòng chọn ít nhất một chi nhánh.")
            else:
                st.session_state.run_report = True
                # Store dates in session state if they exist
                if not is_inventory_report:
                    st.session_state.start_date = start_date
                    st.session_state.end_date = end_date
        else:
            st.session_state.run_report = False

    st.divider()

    # 4. REPORT DISPLAY LOGIC
    if st.session_state.get('run_report', False):
        with st.spinner("Đang xử lý và tải dữ liệu báo cáo..."):
            # --- BÁO CÁO DOANH THU ---
            if report_type == "Báo cáo Doanh thu":
                start_datetime = datetime.combine(st.session_state.start_date, datetime.min.time())
                end_datetime = datetime.combine(st.session_state.end_date, datetime.max.time())
                success, data, message = report_mgr.get_revenue_report(start_datetime, end_datetime, selected_branch_ids)
                if success:
                    # (Existing revenue report display logic - no changes needed here)
                    st.subheader("Tổng quan Doanh thu")
                    kpi_cols = st.columns(4)
                    kpi_cols[0].metric("Tổng Doanh thu", format_currency(data.get('total_revenue', 0), "VNĐ"))
                    kpi_cols[1].metric("Tổng Lợi nhuận gộp", format_currency(data.get('total_profit', 0), "VNĐ"))
                    kpi_cols[2].metric("Số lượng hóa đơn", format_number(data.get('total_orders', 0)))
                    kpi_cols[3].metric("Giá trị/hóa đơn", format_currency(data.get('average_order_value', 0), "VNĐ"))
                    # ... (rest of the revenue display code) ...
                else:
                    st.error(f"Lỗi khi lấy báo cáo: {message}")

            # --- BÁO CÁO TỒN KHO (NEW) ---
            elif report_type == "Báo cáo Tồn kho":
                result = report_mgr.get_inventory_report(selected_branch_ids)
                if result["success"]:
                    report_data = result.get("data")
                    if not report_data:
                        st.info(result.get("message", "Không có dữ liệu tồn kho để hiển thị."))
                        return

                    st.subheader("Tổng quan Tồn kho")
                    kpi_cols = st.columns(2)
                    kpi_cols[0].metric("Tổng giá trị tồn kho", format_currency(report_data.get('total_inventory_value', 0), "VNĐ"))
                    kpi_cols[1].metric("Tổng số lượng sản phẩm trong kho", format_number(report_data.get('total_inventory_items', 0)))
                    st.divider()

                    col1, col2 = st.columns(2)

                    # Top 10 products by value
                    with col1:
                        st.write("**Top 10 sản phẩm giá trị tồn kho cao nhất**")
                        top_prod_df = report_data.get('top_products_by_value_df')
                        if top_prod_df is not None and not top_prod_df.empty:
                            st.dataframe(top_prod_df.style.format({
                                'total_value': lambda x: format_currency(x, 'VNĐ'),
                                'total_quantity': format_number
                            }), use_container_width=True)
                        else:
                            st.info("Không có dữ liệu.")

                    # Low stock items
                    with col2:
                        st.write("**Cảnh báo: Sản phẩm sắp hết hàng (<10)**")
                        low_stock_df = report_data.get('low_stock_items_df')
                        if low_stock_df is not None and not low_stock_df.empty:
                            st.dataframe(low_stock_df[['product_name', 'quantity', 'branch_id']].rename(columns={
                                'product_name': 'Tên sản phẩm',
                                'quantity': 'Tồn kho',
                                'branch_id': 'Chi nhánh'
                            }).style.format({'Tồn kho': format_number}), use_container_width=True)
                        else:
                            st.success("Tốt! Không có sản phẩm nào sắp hết hàng.")

                    # Detailed view
                    with st.expander("Xem chi tiết toàn bộ tồn kho"):
                        detail_df = report_data.get('inventory_details_df')
                        if detail_df is not None and not detail_df.empty:
                             # Map branch IDs to names for better readability
                            detail_df['branch_name'] = detail_df['branch_id'].map(allowed_branches_map)
                            st.dataframe(detail_df[['product_name', 'branch_name', 'quantity', 'cost_price', 'total_value']].rename(columns={
                                'product_name': 'Tên sản phẩm',
                                'branch_name': 'Chi nhánh',
                                'quantity': 'Số lượng',
                                'cost_price': 'Giá vốn',
                                'total_value': 'Tổng giá trị'
                            }).style.format({
                                'Số lượng': format_number,
                                'Giá vốn': lambda x: format_currency(x, 'VNĐ'),
                                'Tổng giá trị': lambda x: format_currency(x, 'VNĐ')
                            }), use_container_width=True)
                else:
                    st.error(f"Lỗi khi tạo báo cáo tồn kho: {result.get('message')}")

            # --- PHÂN TÍCH LỢI NHUẬN ---
            elif report_type == "Phân tích Lợi nhuận":
                st.info("Tính năng 'Phân tích Lợi nhuận' đang trong giai đoạn phát triển.")
        
        st.session_state.run_report = False
