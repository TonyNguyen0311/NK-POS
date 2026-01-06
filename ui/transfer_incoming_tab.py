# ui/transfer_incoming_tab.py
import streamlit as st
from datetime import datetime
from ui._utils import render_section_header

def render_incoming_transfers(branch_id, all_branches_map, inventory_manager, user_id):
    render_section_header("Phiếu Chuyển Đến")
    
    status_filter = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None, "SHIPPED", "COMPLETED", "CANCELLED"],
        format_func=lambda x: "Tất cả" if x is None else x,
        key="in_status_filter"
    )

    try:
        transfers = inventory_manager.get_transfers(branch_id, direction='incoming', status=status_filter)
    except Exception as e:
        st.error(f"Lỗi khi tải danh sách phiếu chuyển đến: {e}")
        return

    if not transfers:
        st.info("Không có phiếu luân chuyển nào đang được gửi đến chi nhánh này.")
        return

    for t in sorted(transfers, key=lambda x: x.get('shipped_at', x.get('created_at', '')), reverse=True):
        from_branch_name = all_branches_map.get(t.get('from_branch_id'), t.get('from_branch_id'))
        with st.expander(f"Phiếu `{t.get('id')}` từ CN `{from_branch_name}` - **{t.get('status')}**"):
            shipped_at_str = datetime.fromisoformat(t['shipped_at']).strftime('%d-%m-%Y %H:%M') if t.get('shipped_at') else 'Chưa gửi'
            st.write(f"**Ngày gửi:** {shipped_at_str}")
            st.write(f"**Ghi chú:** {t.get('notes', 'Không có')}")
            st.write("**Sản phẩm:**")
            for item in t.get('items', []):
                st.write(f"- {item.get('product_name', item.get('sku', '?'))}: **{item.get('quantity', 0)}**")
            
            if t.get('status') == 'SHIPPED':
                if st.button("Xác nhận Đã Nhận Hàng", key=f"receive_{t.get('id')}", use_container_width=True):
                    try:
                        inventory_manager.receive_transfer(t['id'], user_id)
                        st.success(f"Đã xác nhận nhận hàng từ phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận nhận hàng: {e}")
