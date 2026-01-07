# ui/transfer_outgoing_tab.py
import streamlit as st
from datetime import datetime
from ui._utils import render_section_header

def render_outgoing_transfers(branch_id, all_branches_map, stock_transfer_manager, user_id):
    render_section_header("Phiếu Chuyển Đi")
    
    # Map UI status to DB status
    status_map = {
        "Đang chờ": "PENDING",
        "Đang vận chuyển": "IN_TRANSIT",
        "Hoàn thành": "COMPLETED",
        "Đã hủy": "CANCELLED"
    }
    reverse_status_map = {v: k for k, v in status_map.items()}

    selected_status_ui = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None] + list(status_map.keys()), 
        format_func=lambda x: "Tất cả" if x is None else x,
        key="out_status_filter"
    )

    status_filter_db = [status_map[selected_status_ui]] if selected_status_ui else list(status_map.values())

    try:
        transfers = stock_transfer_manager.get_outgoing_transfers(branch_id, status=status_filter_db)
    except Exception as e:
        st.error(f"Lỗi khi tải danh sách phiếu chuyển đi: {e}")
        return

    if not transfers:
        st.info("Không có phiếu luân chuyển nào được gửi đi từ chi nhánh này.")
        return

    for t in transfers:
        to_branch_name = all_branches_map.get(t.get('destination_branch_id'), t.get('destination_branch_id'))
        status_ui = reverse_status_map.get(t.get('status'), t.get('status'))
        with st.expander(f"Phiếu `{t.get('id')}` gửi tới CN `{to_branch_name}` - **{status_ui}**"):
            created_at_str = datetime.fromisoformat(t['created_at']).strftime('%d-%m-%Y %H:%M') if 'created_at' in t else 'N/A'
            st.write(f"**Ngày tạo:** {created_at_str}")
            st.write(f"**Ghi chú:** {t.get('notes', 'Không có')}")
            st.write("**Sản phẩm:**")
            for item in t.get('items', []):
                st.write(f"- {item.get('product_name', item.get('sku', '?'))}: **{item.get('quantity', 0)}**")
            
            # Dispatch action
            if t.get('status') == 'PENDING':
                col1, col2 = st.columns(2)
                if col1.button("Xác nhận Gửi hàng", key=f"dispatch_{t.get('id')}", use_container_width=True):
                    try:
                        # This needs a wrapper function in the manager
                        stock_transfer_manager.dispatch_transfer_transactional(t['id'], user_id)
                        st.success(f"Đã xác nhận gửi phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận gửi: {e}")
                
                # Cancel action
                if col2.button("Hủy Phiếu", key=f"cancel_{t.get('id')}", use_container_width=True):
                    try:
                        # This needs a new method in the manager
                        stock_transfer_manager.cancel_transfer(t['id'], user_id, reason_notes="Hủy bởi người dùng từ giao diện.")
                        st.warning(f"Đã hủy phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi hủy phiếu: {e}")

            # Display dispatch info
            if t.get('dispatch_info'):
                dispatch_info = t['dispatch_info']
                dispatched_at = datetime.fromisoformat(dispatch_info['dispatched_at']).strftime('%d-%m-%Y %H:%M')
                st.info(f"Đã gửi lúc: {dispatched_at} bởi {dispatch_info['dispatched_by']}\nSource Voucher: `{dispatch_info.get('source_voucher_id', 'N/A')}`")
