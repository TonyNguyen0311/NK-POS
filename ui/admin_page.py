
import streamlit as st

from managers.admin_manager import AdminManager
from managers.auth_manager import AuthManager

def render_admin_page(admin_mgr: AdminManager, auth_mgr: AuthManager):
    st.set_page_config(layout="wide")
    st.title("👨‍💻 Khu vực Quản trị")

    # --- Security Check ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role') != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        st.stop()

    st.warning("**CẢNH BÁO:** Các hành động trong trang này có thể gây mất dữ liệu vĩnh viễn và không thể hoàn tác. Hãy thật cẩn trọng.")
    
    st.divider()

    # --- Inventory Data Management Section ---
    st.subheader("🗑️ Quản lý Dữ liệu Kho")
    st.markdown("Chức năng này sẽ xoá **TOÀN BỘ** dữ liệu trong các collection sau: `inventory`, `inventory_vouchers`, và `inventory_transactions`. Dữ liệu này sẽ bị xoá vĩnh viễn.")

    if 'confirm_delete' not in st.session_state:
        st.session_state.confirm_delete = False

    def toggle_confirm():
        st.session_state.confirm_delete = not st.session_state.confirm_delete

    st.button("Xóa Tất Cả Dữ Liệu Kho...", on_click=toggle_confirm, type="secondary")

    if st.session_state.confirm_delete:
        st.error("HÀNH ĐỘNG NGUY HIỂM: Bạn có chắc chắn muốn xóa không?")
        
        col1, col2, col3 = st.columns([2,2,8])
        
        if col1.button("CÓ, TÔI CHẮC CHẮN MUỐN XOÁ", on_click=toggle_confirm, type="primary"):
            with st.spinner("Đang xử lý... Quá trình này có thể mất vài phút tuỳ vào số lượng dữ liệu."):
                try:
                    result = admin_mgr.clear_inventory_data()
                    st.success("Hoàn tất! Dữ liệu kho đã được dọn dẹp.")
                    
                    # Display detailed results
                    st.write("**Kết quả chi tiết:**")
                    for coll, count in result.items():
                        if isinstance(count, int):
                            st.markdown(f"- **{coll}:** Đã xóa {count} tài liệu.")
                        else:
                            st.markdown(f"- **{coll}:** Có lỗi xảy ra - {count}")
                    
                    # Reset confirmation state
                    st.session_state.confirm_delete = False
                    st.rerun()

                except Exception as e:
                    st.error(f"Một lỗi nghiêm trọng đã xảy ra: {e}")
                    # Reset confirmation state
                    st.session_state.confirm_delete = False
                    st.rerun()
        
        if col2.button("KHÔNG, HỦY BỎ", on_click=toggle_confirm):
            st.session_state.confirm_delete = False
            st.rerun()


