# ui/transactions_page.py
import streamlit as st
from datetime import datetime, date
from ui._utils import render_section_header
import pandas as pd

def render_transactions_page(txn_manager, branch_mgr, auth_mgr):
    # FIX: Get user info from session_state instead of a non-existent method
    user_info = st.session_state.user 
    user_branch_id = user_info.get('branch_id')
    user_role = user_info.get('role')

    render_section_header("Lịch Sử Giao Dịch")

    # --- Date Range and Branch Filters ---
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        start_date = st.date_input("Từ ngày", date.today())
    with col2:
        end_date = st.date_input("Đến ngày", date.today())

    branch_options = branch_mgr.get_all_branches()
    branch_map = {b['id']: b['name'] for b in branch_options}
    
    selected_branch_id = None
    if user_role == 'admin':
        with col3:
            selected_branch_name = st.selectbox(
                "Chọn chi nhánh", 
                options=["Tất cả"] + list(branch_map.values()),
                index=0
            )
            if selected_branch_name != "Tất cả":
                selected_branch_id = [k for k, v in branch_map.items() if v == selected_branch_name][0]
    else:
        st.sidebar.write(f"Chi nhánh: **{branch_map.get(user_branch_id, 'Không xác định')}**")
        selected_branch_id = user_branch_id

    if st.button("Xem Giao Dịch", use_container_width=True, type="primary"):
        if start_date > end_date:
            st.error("Ngày bắt đầu không được lớn hơn ngày kết thúc.")
            return

        try:
            with st.spinner("Đang tải dữ liệu giao dịch..."):
                transactions = txn_manager.query_transactions(start_date, end_date, selected_branch_id)
            
            if not transactions:
                st.info("Không tìm thấy giao dịch nào trong khoảng thời gian và chi nhánh đã chọn.")
            else:
                st.session_state.queried_transactions = transactions

        except Exception as e:
            st.error(f"Đã xảy ra lỗi khi tải giao dịch: {e}")
    
    # --- Display Queried Transactions ---
    if 'queried_transactions' in st.session_state:
        transactions = st.session_state.queried_transactions
        st.write(f"**Tìm thấy {len(transactions)} giao dịch:**")

        for txn in transactions:
            txn_time = txn.get('created_at').strftime("%H:%M %d/%m/%Y") if txn.get('created_at') else "N/A"
            branch_name = branch_map.get(txn.get('branch_id'), txn.get('branch_id'))
            total_amount_formatted = f"{txn.get('total_amount', 0):,}"

            expander_title = f"`{txn['id']}` - **{total_amount_formatted}đ** - {branch_name} - {txn_time}"
            with st.expander(expander_title):
                st.write(f"**Nhân viên:** {txn.get('cashier_id', 'N/A')}")
                st.write(f"**Khách hàng:** {txn.get('customer_name', 'Khách lẻ')} ({txn.get('customer_phone', 'N/A')})")
                
                st.markdown("##### Chi tiết đơn hàng")
                items_data = []
                for item in txn.get('items', []):
                    items_data.append({
                        "Tên SP": item.get('product_name'),
                        "SL": item.get('quantity'),
                        "Đơn giá": f"{item.get('price', 0):,}",
                        "Thành tiền": f"{item.get('total', 0):,}"
                    })
                st.table(pd.DataFrame(items_data).set_index("Tên SP"))

                st.markdown("--- Tóm tắt ---")
                summary_col1, summary_col2 = st.columns(2)
                summary_col1.metric("Tổng tiền hàng", f"{txn.get('sub_total', 0):,}đ")
                summary_col1.metric("Giảm giá", f"- {txn.get('discount_amount', 0):,}đ")
                summary_col1.metric("**Tổng cộng**", f"**{txn.get('total_amount', 0):,}đ**")
                
                summary_col2.write(f"**Tiền khách đưa:** {txn.get('payment_received', 0):,}đ")
                summary_col2.write(f"**Tiền thối:** {txn.get('payment_change', 0):,}đ")
                summary_col2.write(f"**Phương thức:** {txn.get('payment_method', 'Tiền mặt')}")
