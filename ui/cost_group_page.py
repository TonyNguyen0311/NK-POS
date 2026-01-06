
import streamlit as st
from managers.cost_manager import CostManager
from ui._utils import render_page_title, render_section_header

def render_cost_group_page(cost_mgr: CostManager):
    """
    Renders the page for managing cost groups, now including cost type (fixed/variable).
    """
    render_page_title("⚙️ Danh mục Chi phí")
    st.info("Phân loại các khoản chi phí vào các nhóm, đồng thời xác định chúng là Định phí (chi phí cố định, vd: thuê nhà) hay Biến phí (chi phí thay đổi theo doanh thu, vd: hoa hồng).")

    # Initialize session state for editing
    if 'editing_group_id' not in st.session_state:
        st.session_state.editing_group_id = None

    # --- FORM ĐỂ THÊM NHÓM MỚI ---
    render_section_header("Thêm Nhóm chi phí mới")
    with st.form("add_group_form", clear_on_submit=True):
        new_group_name = st.text_input("Tên nhóm chi phí")
        group_type_display = st.selectbox("Loại chi phí", ["Định phí", "Biến phí"], help="**Định phí**: Chi phí cố định không thay đổi theo mức độ hoạt động. **Biến phí**: Chi phí thay đổi khi mức độ hoạt động thay đổi.")
        submitted = st.form_submit_button("Thêm Nhóm")
        
        if submitted and new_group_name:
            group_type = 'fixed' if group_type_display == "Định phí" else 'variable'
            try:
                cost_mgr.create_cost_group(new_group_name, group_type)
                st.success(f"Đã thêm nhóm '{new_group_name}' thành công.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Lỗi không xác định: {e}")

    st.divider()

    render_section_header("Các Nhóm chi phí hiện có")
    try:
        cost_groups = cost_mgr.get_cost_groups()
        if not cost_groups:
            st.info("Chưa có nhóm chi phí nào được tạo.")
        else:
            # Display header
            cols = st.columns([3, 2, 2, 1])
            cols[0].markdown("**Tên Nhóm**")
            cols[1].markdown("**Loại Chi Phí**")
            
            for group in cost_groups:
                # If this group is being edited, show the edit form
                if st.session_state.editing_group_id == group['id']:
                    with st.form(key=f"edit_form_{group['id']}"):
                        edit_cols = st.columns([3, 2, 2, 1])
                        new_name = edit_cols[0].text_input("Tên", value=group['group_name'], label_visibility="collapsed")
                        
                        current_type_index = 0 if group.get('group_type', 'fixed') == 'fixed' else 1
                        new_type_display = edit_cols[1].selectbox("Loại", ["Định phí", "Biến phí"], index=current_type_index, label_visibility="collapsed")
                        
                        if edit_cols[2].form_submit_button("Lưu", use_container_width=True):
                            new_type = 'fixed' if new_type_display == "Định phí" else 'variable'
                            try:
                                cost_mgr.update_cost_group(group['id'], new_name, new_type)
                                st.success("Đã cập nhật thành công!")
                                st.session_state.editing_group_id = None
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")
                        
                        if edit_cols[3].form_submit_button("Hủy", use_container_width=True):
                            st.session_state.editing_group_id = None
                            st.rerun()
                else:
                    # Show the normal display row
                    display_cols = st.columns([3, 2, 1, 1])
                    group_type = group.get('group_type', 'N/A')
                    group_type_display = "Định phí" if group_type == 'fixed' else ("Biến phí" if group_type == 'variable' else "Chưa xác định")
                    
                    display_cols[0].write(group['group_name'])
                    display_cols[1].write(group_type_display)
                    
                    if display_cols[2].button("✏️ Sửa", key=f"edit_{group['id']}", use_container_width=True):
                        st.session_state.editing_group_id = group['id']
                        st.rerun()
                    
                    if display_cols[3].button("❌ Xóa", key=f"del_{group['id']}", use_container_width=True, help="Xóa nhóm chi phí này"):
                        try:
                            cost_mgr.delete_cost_group(group['id'])
                            st.success(f"Đã xóa nhóm '{group['group_name']}'.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Không thể xóa. Lỗi: {e}")
    except Exception as e:
        st.error(f"Không thể tải danh sách nhóm chi phí. Lỗi: {e}")

