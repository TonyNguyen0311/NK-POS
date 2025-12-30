
import streamlit as st
from managers.cost_manager import CostManager

def render_cost_group_page(cost_mgr: CostManager):
    """
    Renders the page for managing cost groups (categories).
    This page is intended for Admins only.
    """
    st.header("⚙️ Danh mục Chi phí")
    st.info("Chức năng này cho phép bạn tạo và quản lý các nhóm chi phí chung cho toàn bộ hệ thống, giúp phân loại và báo cáo chi phí một cách nhất quán.")

    st.subheader("Thêm Nhóm chi phí mới")
    with st.form("add_group_form", clear_on_submit=True):
        new_group_name = st.text_input("Tên nhóm chi phí")
        submitted = st.form_submit_button("Thêm Nhóm")
        
        if submitted and new_group_name:
            try:
                cost_mgr.create_cost_group(new_group_name)
                st.success(f"Đã thêm nhóm '{new_group_name}' thành công.")
                # No need to rerun, the list will update on next interaction
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Lỗi không xác định: {e}")

    st.divider()

    st.subheader("Các Nhóm chi phí hiện có")
    
    try:
        cost_groups = cost_mgr.get_cost_groups()
        if not cost_groups:
            st.info("Chưa có nhóm chi phí nào được tạo.")
        else:
            for group in cost_groups:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.text(group['group_name'])
                with col2:
                    if st.button("❌ Xóa", key=f"del_{group['id']}", help="Xóa nhóm chi phí này"):
                        # Warning before deletion
                        # A proper implementation might use a modal or a second confirmation
                        try:
                            # TODO: Check if group is in use before deleting.
                            # This is a critical check to prevent orphaned data.
                            cost_mgr.delete_cost_group(group['id'])
                            st.success(f"Đã xóa nhóm '{group['group_name']}'.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Không thể xóa nhóm này. Lỗi: {e}")
    except Exception as e:
        st.error(f"Không thể tải danh sách nhóm chi phí. Lỗi: {e}")

