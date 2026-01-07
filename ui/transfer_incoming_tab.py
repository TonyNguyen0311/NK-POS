# ui/transfer_incoming_tab.py
import streamlit as st
from datetime import datetime
from ui._utils import render_section_header

def render_incoming_transfers(branch_id, all_branches_map, stock_transfer_manager, user_id):
    render_section_header("Phiếu Chuyển Đến")
    
    status_map = {
        "Đang vận chuyển": "IN_TRANSIT",
        "Hoàn thành": "COMPLETED",
        "Đã hủy": "CANCELLED" # Mặc dù hiếm khi lọc, nhưng vẫn để cho đủ
    }
    reverse_status_map = {v: k for k, v in status_map.items()}

    selected_status_ui = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None] + list(status_map.keys()), 
        format_func=lambda x: "Tất cả" if x is None else x,
        key="in_status_filter"
    )

    status_filter_db = [status_map[selected_status_ui]] if selected_status_ui else list(status_map.values())

    try:
        transfers = stock_transfer_manager.get_incoming_transfers(branch_id, status=status_filter_db)
    except Exception as e:
        st.error(f"Lỗi khi tải danh sách phiếu chuyển đến: {e}")
        return

    if not transfers:
        st.info("Không có phiếu luân chuyển nào đang được gửi đến chi nhánh này.")
        return

    for t in transfers:
        from_branch_name = all_branches_map.get(t.get('source_branch_id'), t.get('source_branch_id'))
        status_ui = reverse_status_map.get(t.get('status'), t.get('status'))
        
        with st.expander(f"Phiếu `{t.get('id')}` từ CN `{from_branch_name}` - **{status_ui}**"):
            created_at_str = datetime.fromisoformat(t['created_at']).strftime('%d-%m-%Y %H:%M')
            st.write(f"**Ngày tạo:** {created_at_str}")
            
            if t.get('dispatch_info'):
                dispatched_at_str = datetime.fromisoformat(t['dispatch_info']['dispatched_at']).strftime('%d-%m-%Y %H:%M')
                st.write(f"**Ngày gửi:** {dispatched_at_str}")

            st.write(f"**Ghi chú:** {t.get('notes', 'Không có')}")
            st.write("**Sản phẩm:**")
            for item in t.get('items', []):
                st.write(f"- {item.get('product_name', item.get('sku', '?'))}: **{item.get('quantity', 0)}**")
            
            if t.get('status') == 'IN_TRANSIT':
                if st.button("Xác nhận Đã Nhận Hàng", key=f"receive_{t.get('id')}", use_container_width=True):
                    try:
                        stock_transfer_manager.receive_transfer_transactional(t['id'], user_id)
                        st.success(f"Đã xác nhận nhận hàng từ phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận nhận hàng: {e}")

            # Display receipt info
            if t.get('receipt_info'):
                receipt_info = t['receipt_info']
                received_at = datetime.fromisoformat(receipt_info['received_at']).strftime('%d-%m-%Y %H:%M')
                st.info(f"Đã nhận lúc: {received_at} bởi {receipt_info['received_by']}\nDestination Voucher: `{receipt_info.get('destination_voucher_id', 'N/A')}`")

            # Display cancellation info
            if t.get('cancellation_info'):
                cancellation_info = t['cancellation_info']
                cancelled_at = datetime.fromisoformat(cancellation_info['cancelled_at']).strftime('%d-%m-%Y %H:%M')
                st.warning(f"Đã hủy lúc: {cancelled_at} bởi {cancellation_info['cancelled_by']}\nLý do: {cancellation_info.get('reason', 'N/A')}")
