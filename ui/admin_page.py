import streamlit as st
from managers.admin_manager import AdminManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_title, render_section_header

def render_admin_page(admin_mgr: AdminManager, auth_mgr: AuthManager):
    render_page_title("👨‍💻 Khu vực Quản trị")

    # --- Initialize Session State ---
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False
    if "operation_result" not in st.session_state:
        st.session_state.operation_result = None
    if "show_result" not in st.session_state:
        st.session_state.show_result = False

    # --- Security Check ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role') != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        st.stop()

    st.warning("**CẢNH BÁO:** Các hành động trong trang này có thể gây mất dữ liệu vĩnh viễn và không thể hoàn tác. Hãy thật cẩn trọng.")
    
    st.divider()

    # --- Inventory Data Management Section ---
    render_section_header("🗑️ Quản lý Dữ liệu Kho")
    st.markdown("Chức năng này sẽ xoá **TOÀN BỘ** dữ liệu trong các collection sau: `inventory`, `inventory_vouchers`, và `inventory_transactions`. Dữ liệu này sẽ bị xoá vĩnh viễn.")

    if st.button("Xóa Tất Cả Dữ Liệu Kho...", type="secondary"):
        if not st.session_state.confirm_delete:
            st.session_state.confirm_delete = True
        st.session_state.operation_result = None # Clear previous results
        st.session_state.show_result = False

    if st.session_state.confirm_delete:
        st.error("HÀNH ĐỘNG NGUY HIỂM: Bạn có chắc chắn muốn xóa không?")
        
        col1, col2, _ = st.columns([2, 2, 8])
        
        if col1.button("CÓ, TÔI CHẮC CHẮN MUỐN XOÁ", type="primary"):
            with st.spinner("Đang xử lý... Quá trình này có thể mất vài phút tuỳ vào số lượng dữ liệu."):
                try:
                    result = admin_mgr.clear_inventory_data()
                    st.session_state.operation_result = result
                    st.session_state.show_result = True
                except Exception as e:
                    st.session_state.operation_result = {"error": str(e)}
                    st.session_state.show_result = True
            st.session_state.confirm_delete = False # Reset confirmation

        if col2.button("KHÔNG, HỦY BỎ"):
            st.session_state.confirm_delete = False
            st.session_state.operation_result = None
            st.rerun()

    # --- Display Results --- 
    if st.session_state.show_result and st.session_state.operation_result:
        result = st.session_state.operation_result
        if "error" in result:
            st.error(f"Một lỗi nghiêm trọng đã xảy ra: {result['error']}")
        else:
            st.success("Hoàn tất! Dữ liệu kho đã được dọn dẹp.")
            st.write("**Kết quả chi tiết:**")
            for coll, count in result.items():
                if isinstance(count, int):
                    st.markdown(f"- **{coll}:** Đã xóa {count} tài liệu.")
                else:
                    st.markdown(f"- **{coll}:** Có lỗi xảy ra - {count}")
        # Add a button to clear the results and hide the message
        if st.button("OK"):
            st.session_state.show_result = False
            st.session_state.operation_result = None
            st.rerun()

