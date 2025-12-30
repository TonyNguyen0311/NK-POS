
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

def render_pnl_report_page(report_mgr, branch_mgr, auth_mgr):
    st.header("📈 Báo cáo Kết quả Kinh doanh (P&L)")
    st.info("Báo cáo này tổng hợp doanh thu, giá vốn và chi phí để tính toán lợi nhuận gộp và lợi nhuận ròng trong một khoảng thời gian tùy chọn.")

    # --- 1. FILTERS ---
    user_info = auth_mgr.get_current_user_info()
    user_role = user_info.get('role', 'staff')
    
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches()}
    
    branch_options = {}
    if user_role == 'admin':
        branch_options = {'all': "Toàn bộ hệ thống", **all_branches_map}
    else:
        user_branches = user_info.get('branch_ids', [])
        branch_options = {bid: all_branches_map[bid] for bid in user_branches if bid in all_branches_map}

    cols = st.columns([1, 1, 2])
    today = datetime.now()
    start_date = cols[0].date_input("Từ ngày", today - timedelta(days=30))
    end_date = cols[1].date_input("Đến ngày", today)
    selected_branch_key = cols[2].selectbox(
        "Xem báo cáo cho", 
        options=list(branch_options.keys()),
        format_func=lambda k: branch_options[k]
    )

    if st.button("📊 Xem Báo cáo", use_container_width=True):
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        branch_id_for_query = None if selected_branch_key == 'all' else selected_branch_key

        try:
            with st.spinner("Đang tổng hợp dữ liệu..."):
                pnl_data = report_mgr.get_profit_loss_statement(
                    start_date=start_datetime,
                    end_date=end_datetime,
                    branch_id=branch_id_for_query
                )
            
            if not pnl_data or not pnl_data.get("success"):
                st.error("Không thể tạo báo cáo: " + pnl_data.get("message", "Không có dữ liệu."))
                return

            st.success(f"Báo cáo cho: **{branch_options[selected_branch_key]}** từ **{start_date}** đến **{end_date}**")
            st.markdown("---")

            # --- 2. DISPLAY METRICS ---
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Tổng Doanh thu", f"{pnl_data['total_revenue']:,.0f} đ")
            col2.metric("Tổng Giá vốn (COGS)", f"{pnl_data['total_cogs']:,.0f} đ")
            col3.metric("Lợi nhuận gộp", f"{pnl_data['gross_profit']:,.0f} đ", f"{pnl_data['gross_profit']-pnl_data['total_revenue']:,.0f} đ")
            
            net_profit_delta_color = "normal" if pnl_data['net_profit'] >= 0 else "inverse"
            col4.metric("Lợi nhuận Ròng", f"{pnl_data['net_profit']:,.0f} đ", delta_color=net_profit_delta_color)

            st.markdown("---")
            
            # --- 3. DISPLAY CHARTS & DETAILS ---
            st.subheader("Phân tích Chi phí Hoạt động (OPEX)")
            
            # If there are no expenses, show a message and stop.
            if pnl_data['total_operating_expenses'] == 0:
                st.info("Không phát sinh chi phí hoạt động trong kỳ báo cáo.")
            else:
                c1, c2 = st.columns(2)
                
                # Expenses by Group
                expenses_by_group = pnl_data.get("operating_expenses_by_group", {})
                if expenses_by_group:
                    df_group = pd.DataFrame(expenses_by_group.items(), columns=['Nhóm chi phí', 'Số tiền'])
                    df_group = df_group[df_group['Số tiền'] > 0]
                    fig_group = px.pie(df_group, values='Số tiền', names='Nhóm chi phí', title='Tỷ trọng theo Nhóm chi phí')
                    c1.plotly_chart(fig_group, use_container_width=True)
                
                # Expenses by Classification
                expenses_by_class = pnl_data.get("operating_expenses_by_classification", {})
                if expenses_by_class:
                    class_map = {'FIXED': 'Định phí', 'VARIABLE': 'Biến phí', 'OPEX': 'OPEX', 'CAPEX': 'Khấu hao CAPEX', 'AMORTIZED': 'Khấu hao'}
                    mapped_expenses = {class_map.get(k, k): v for k, v in expenses_by_class.items()}
                    df_class = pd.DataFrame(mapped_expenses.items(), columns=['Phân loại', 'Số tiền'])
                    df_class = df_class[df_class['Số tiền'] > 0]
                    fig_class = px.pie(df_class, values='Số tiền', names='Phân loại', title='Tỷ trọng theo Phân loại')
                    c2.plotly_chart(fig_class, use_container_width=True)
                
                with st.expander("Xem chi tiết Chi phí hoạt động"):
                    if not df_group.empty:
                        st.dataframe(df_group.style.format({'Số tiền': '{:,.0f} đ'}), use_container_width=True)
                    else:
                        st.write("Không có chi phí để hiển thị.")

        except Exception as e:
            st.error("Đã xảy ra lỗi khi tạo báo cáo.")
            st.exception(e)
