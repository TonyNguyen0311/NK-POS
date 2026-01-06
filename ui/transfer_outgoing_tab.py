# ui/transfer_outgoing_tab.py
import streamlit as st
from datetime import datetime
from ui._utils import render_section_header

def render_outgoing_transfers(branch_id, all_branches_map, inventory_manager, user_id):
    render_section_header("Phiếu Chuyển Đi")
    
    status_filter = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None, "PENDING", "SHIPPED", "COMPLETED", "CANCELLED"], 
        format_func=lambda x: "Tất cả" if x is None else x,
        key="out_status_filter"
    )

    try:
        transfers = inventory_manager.get_transfers(branch_id, direction='outgoing', status=status_filter)
    except Exception as e:
        st.error(f"Lỗi khi tải danh sách phiếu chuyển đi: {e}")
        return

    if not transfers:
        st.info("Không có phiếu luân chuyển nào được gửi đi từ chi nhánh này.")
        return

    for t in sorted(transfers, key=lambda x: x.get('created_at', ''), reverse=True):
        to_branch_name = all_branches_map.get(t.get('to_branch_id'), t.get('to_branch_id'))
        with st.expander(f"Phiếu `{t.get('id')}` gửi tới CN `{to_branch_name}` - **{t.get('status')}**"):
            created_at_str = datetime.fromisoformat(t['created_at']).strftime('%d-%m-%Y %H:%M') if 'created_at' in t else 'N/A'
            st.write(f"**Ngày tạo:** {created_at_str}")
            st.write(f"**Ghi chú:** {t.get('notes', 'Không có')}")
            st.write("**Sản phẩm:**")
            for item in t.get('items', []):
                st.write(f"- {item.get('product_name', item.get('sku', '?'))}: **{item.get('quantity', 0)}**")
            
            if t.get('status') == 'PENDING':
                col1, col2 = st.columns(2)
                if col1.button("Xác nhận Gửi hàng", key=f"ship_{t.get('id')}", use_container_width=True):
                    try:
                        inventory_manager.ship_transfer(t['id'], user_id)
                        st.success(f"Đã xác nhận gửi phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận gửi: {e}")
                if col2.button("Hủy Phiếu", key=f"cancel_{t.get('id')}", use_container_width=True):
                    try:
                        inventory_manager.cancel_transfer(t['id'], user_id, reason_notes="Hủy bởi người dùng từ giao diện.")
                        st.warning(f"Đã hủy phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi hủy phiếu: {e}")
