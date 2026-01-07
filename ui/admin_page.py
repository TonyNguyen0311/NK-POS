import streamlit as st
import pandas as pd
from managers.admin_manager import AdminManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_title, render_section_header

def render_admin_page(admin_mgr: AdminManager, auth_mgr: AuthManager):
    render_page_title("👨‍💻 Khu vực Quản trị")

    # --- Initialize Session State ---
    if "confirm_delete_inventory" not in st.session_state:
        st.session_state.confirm_delete_inventory = False
    # SỬA LỖI: Thay đổi cách quản lý trạng thái xóa đơn hàng
    if "order_to_delete" not in st.session_state:
        st.session_state.order_to_delete = None
    if "delete_result" not in st.session_state:
        st.session_state.delete_result = None

    # --- Security Check ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role') != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        st.stop()

    st.warning("**CẢNH BÁO:** Các hành động trong trang này có thể gây mất dữ liệu vĩnh viễn và không thể hoàn tác. Hãy thật cẩn trọng.")
    
    tab1, tab2 = st.tabs(["Xóa Đơn Hàng Lỗi", "Dọn Dẹp Dữ Liệu Kho"])

    with tab1:
        render_order_deletion_tab(admin_mgr, user_info['uid'])
    
    with tab2:
        render_inventory_cleanup_tab(admin_mgr)


def render_order_deletion_tab(admin_mgr, current_user_id):
    render_section_header("❌ Xóa Đơn Hàng và Hoàn Trả Tồn Kho")

    # SỬA LỖI: Hiển thị kết quả xóa một cách rõ ràng
    if st.session_state.delete_result:
        success, message = st.session_state.delete_result
        if success:
            st.success(message)
        else:
            st.error(message)
        if st.button("OK"):
            st.session_state.delete_result = None
            st.rerun()
        return # Dừng render phần còn lại để người dùng thấy kết quả

    st.markdown("Chức năng này cho phép bạn xóa một đơn hàng cụ thể. Hệ thống sẽ **tự động cộng trả lại số lượng tồn kho** tương ứng với đơn hàng bị xóa. Hành động này không thể hoàn tác.")

    with st.spinner("Đang tải danh sách đơn hàng..."):
        orders = admin_mgr.get_all_orders()
    
    if not orders:
        st.info("Hiện không có đơn hàng nào trong hệ thống.")
        return

    df = pd.DataFrame(orders)
    df_display = df[['id', 'created_at', 'branch_id', 'grand_total', 'total_cogs']].copy()
    df_display['created_at'] = pd.to_datetime(df_display['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    df_display['grand_total'] = df_display['grand_total'].apply(lambda x: f"{x:,.0f}đ")

    st.write("**Danh sách các đơn hàng:**")
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.divider()

    # SỬA LỖI: Quy trình xác nhận và xóa được thiết kế lại
    if not st.session_state.order_to_delete:
        order_ids = [order['id'] for order in orders]
        selected_order_id = st.selectbox("Chọn Đơn Hàng Cần Xóa:", options=[""] + order_ids)
        if selected_order_id and st.button("Xóa Đơn Hàng Được Chọn...", type="primary"):
            st.session_state.order_to_delete = selected_order_id
            st.rerun()

    if st.session_state.order_to_delete:
        st.error(f"Bạn có chắc chắn muốn xóa vĩnh viễn đơn hàng **{st.session_state.order_to_delete}** và hoàn trả tồn kho không?")
        
        col1, col2, _ = st.columns([2, 2, 8])
        if col1.button("CÓ, TÔI CHẮC CHẮN", type="primary"):
            with st.spinner("Đang xử lý..."):
                success, message = admin_mgr.delete_order_and_revert_stock(st.session_state.order_to_delete, current_user_id)
                # Lưu kết quả vào session state
                st.session_state.delete_result = (success, message)
                if success:
                    # Xóa cache ở phía UI sau khi thành công
                    st.cache_data.clear()
            # Reset và rerun để hiển thị kết quả
            st.session_state.order_to_delete = None
            st.rerun()

        if col2.button("HỦY BỎ"):
            st.session_state.order_to_delete = None
            st.rerun()

def render_inventory_cleanup_tab(admin_mgr):
    render_section_header("🗑️ Dọn dẹp toàn bộ Dữ liệu Kho")
    st.markdown("Chức năng này sẽ xoá **TOÀN BỘ** dữ liệu trong các collection sau: `inventory`, `inventory_vouchers`, và `inventory_transactions`. Dữ liệu này sẽ bị xoá vĩnh viễn.")

    # Giữ nguyên logic của tab này vì nó đã đúng
    if "operation_result" not in st.session_state:
        st.session_state.operation_result = None
    if "show_result" not in st.session_state:
        st.session_state.show_result = False

    if st.button("Xóa Tất Cả Dữ Liệu Kho...", type="secondary"):
        st.session_state.confirm_delete_inventory = True
        st.session_state.operation_result = None
        st.session_state.show_result = False

    if st.session_state.confirm_delete_inventory:
        st.error("HÀNH ĐỘNG NGUY HIỂM: Bạn có chắc chắn muốn xóa không?")
        
        col1, col2, _ = st.columns([2, 2, 8])
        
        if col1.button("CÓ, TÔI CHẮC CHẮN MUỐN XOÁ", type="primary"):
            with st.spinner("Đang xử lý... Quá trình này có thể mất vài phút."):
                result = admin_mgr.clear_inventory_data()
                st.session_state.operation_result = result
                st.session_state.show_result = True
                st.cache_data.clear() # Xóa cache sau khi dọn dẹp
            st.session_state.confirm_delete_inventory = False
            st.rerun()

        if col2.button("KHÔNG, HỦY BỎ"):
            st.session_state.confirm_delete_inventory = False
            st.rerun()

    if st.session_state.show_result and st.session_state.operation_result:
        result = st.session_state.operation_result
        if "error" in result:
            st.error(f"Lỗi: {result['error']}")
        else:
            st.success("Hoàn tất! Dữ liệu kho đã được dọn dẹp.")
            st.write("**Kết quả:**")
            for coll, count in result.items():
                st.markdown(f"- **{coll}:** Đã xóa {count} tài liệu.")
        if st.button("OK"):
            st.session_state.show_result = False
            st.session_state.operation_result = None
            st.rerun()
