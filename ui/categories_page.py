
import streamlit as st
import pandas as pd
from managers.product_manager import ProductManager
from managers.cost_manager import CostManager
from ui._utils import render_page_title, render_section_header, render_sub_header

def render_categories_page(product_manager: ProductManager, cost_manager: CostManager):
    render_page_title("Thiết lập Danh mục")

    tab1, tab2, tab3 = st.tabs(["Danh mục sản phẩm", "Đơn vị tính", "Nhóm chi phí"])

    with tab1:
        render_generic_category_ui(
            product_manager,
            "Danh mục sản phẩm",
            "ProductCategories",
            "category_name",
            "Tên danh mục"
        )

    with tab2:
        render_generic_category_ui(
            product_manager,
            "Đơn vị tính",
            "ProductUnits",
            "unit_name",
            "Tên đơn vị tính"
        )

    with tab3:
        render_generic_category_ui(
            cost_manager,
            "Nhóm chi phí",
            "CostGroups",
            "group_name",
            "Tên nhóm chi phí"
        )

def render_generic_category_ui(manager, title, collection_name, field_name, column_name):
    render_section_header(f"Quản lý {title}")

    # --- Form to add new item ---
    with st.expander(f"Thêm {title} mới"):
        with st.form(key=f"add_{collection_name}", clear_on_submit=True):
            new_item_name = st.text_input(f"Tên {title} mới")
            submitted = st.form_submit_button("Thêm mới")
            if submitted and new_item_name:
                try:
                    manager.add_category_item(collection_name, {field_name: new_item_name})
                    st.success(f"Đã thêm '{new_item_name}' thành công!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi thêm: {e}")

    # --- Display, Edit, Delete existing items ---
    try:
        items = manager.get_all_category_items(collection_name)
        if not items:
            st.info(f"Chưa có {title} nào.")
            return

        df = pd.DataFrame(items)
        df = df.rename(columns={field_name: column_name, "id": "ID"})
        
        render_sub_header(f"Danh sách {title} hiện có:")

        for index, row in df.iterrows():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.text_input(
                    label="Tên",
                    value=row[column_name],
                    key=f"edit_{collection_name}_{row['ID']}",
                    label_visibility="collapsed"
                )
            with col2:
                if st.button("Lưu", key=f"save_{collection_name}_{row['ID']}"):
                    new_name = st.session_state[f"edit_{collection_name}_{row['ID']}"]
                    if new_name and new_name != row[column_name]:
                        try:
                            manager.update_category_item(collection_name, row['ID'], {field_name: new_name})
                            st.success(f"Đã cập nhật thành công!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi cập nhật: {e}")
            with col3:
                if st.button("Xóa", key=f"delete_{collection_name}_{row['ID']}"):
                    try:
                        manager.delete_category_item(collection_name, row['ID'])
                        st.success(f"Đã xóa thành công!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xóa: {e}")

    except Exception as e:
        st.error(f"Không thể tải danh sách {title}: {e}")
