
import streamlit as st
import pandas as pd
from managers.product_manager import ProductManager
from managers.auth_manager import AuthManager

def render_product_catalog_page(prod_mgr: ProductManager, auth_mgr: AuthManager):
    st.header("🗂️ Danh mục Sản phẩm")

    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.warning("Vui lòng đăng nhập để xem.")
        return

    user_role = user_info.get('role', 'user')
    is_admin = user_role == 'admin'
    is_manager_or_admin = user_role in ['admin', 'manager']

    # Initialize session state for editing
    if 'editing_product_id' not in st.session_state:
        st.session_state.editing_product_id = None

    # --- TABS DEFINITION ---
    tab_titles = ["Quản lý Sản phẩm"]
    if is_admin:
        tab_titles.append("Thiết lập Danh mục & Đơn vị")
    tabs = st.tabs(tab_titles)

    # --- PRODUCT MANAGEMENT TAB ---
    with tabs[0]:
        # --- ADD/EDIT FORM ---
        if is_manager_or_admin:
            # If we are in edit mode, get the product details
            editing_product = None
            if st.session_state.editing_product_id:
                editing_product = prod_mgr.get_product_by_sku(st.session_state.editing_product_id)
            
            form_title = "✏️ Chỉnh sửa Sản phẩm" if editing_product else "➕ Thêm Sản Phẩm Mới"
            
            with st.expander(form_title, expanded=st.session_state.editing_product_id is not None):
                categories = prod_mgr.get_categories()
                units = prod_mgr.get_units()
                cat_opts = {c['id']: f"{c['name']} ({c.get('prefix', 'SP')})" for c in categories}
                unit_opts = {u['id']: u['name'] for u in units}

                # Set default values for the form if editing
                default_name = editing_product['name'] if editing_product else ""
                default_cat_index = list(cat_opts.keys()).index(editing_product['category_id']) if editing_product and editing_product.get('category_id') in cat_opts else 0
                default_unit_index = list(unit_opts.keys()).index(editing_product['unit_id']) if editing_product and editing_product.get('unit_id') in unit_opts else 0
                default_barcode = editing_product['barcode'] if editing_product else ""

                with st.form("product_form", clear_on_submit=False):
                    name = st.text_input("**Tên sản phẩm**", value=default_name)
                    col1, col2 = st.columns(2)
                    cat_id = col1.selectbox("**Danh mục**", options=list(cat_opts.keys()), format_func=lambda x: cat_opts[x], index=default_cat_index)
                    unit_id = col2.selectbox("**Đơn vị**", options=list(unit_opts.keys()), format_func=lambda x: unit_opts[x], index=default_unit_index)
                    barcode = st.text_input("Barcode", value=default_barcode)
                    image_file = st.file_uploader("Tải ảnh mới (tùy chọn)", type=['png', 'jpg', 'jpeg'])

                    submit_col, cancel_col = st.columns(2)
                    submitted = submit_col.form_submit_button(f"Lưu {('thay đổi' if editing_product else 'sản phẩm')}")
                    if editing_product:
                        if cancel_col.form_submit_button("Hủy", type="secondary"):
                            st.session_state.editing_product_id = None
                            st.rerun()

                    if submitted:
                        if not name or not cat_id:
                            st.error("Tên sản phẩm và Danh mục là bắt buộc!")
                        else:
                            data = {"name": name, "category_id": cat_id, "unit_id": unit_id, "barcode": barcode}
                            
                            # Image handling
                            img_url = editing_product.get('image_url', "") if editing_product else ""
                            if image_file:
                                with st.spinner("Đang xử lý ảnh..."):
                                    new_img_url = prod_mgr.upload_image(image_file, image_file.name)
                                    if new_img_url:
                                        img_url = new_img_url
                                    else:
                                        st.warning("Tải ảnh thất bại, ảnh cũ (nếu có) sẽ được giữ lại.")
                            data['image_url'] = img_url

                            # Update or Create
                            if editing_product:
                                success, msg = prod_mgr.update_product(editing_product['sku'], data)
                            else:
                                success, msg = prod_mgr.create_product(data)

                            if success:
                                st.success(msg)
                                st.session_state.editing_product_id = None # Exit edit mode
                                st.rerun()
                            else:
                                st.error(msg)
        
        st.divider()

        # --- PRODUCT LIST ---
        st.subheader("Toàn bộ sản phẩm trong danh mục")
        products = prod_mgr.get_all_products(show_inactive=True)

        if not products:
            st.info("Chưa có sản phẩm nào.")
            return
        
        cats_df = pd.DataFrame(prod_mgr.get_categories()).set_index('id')
        cat_names = cats_df['name'].to_dict()

        # Header
        h_cols = st.columns([2, 4, 2, 2, 2])
        h_cols[0].write("**SKU**")
        h_cols[1].write("**Tên sản phẩm**")
        h_cols[2].write("**Danh mục**")
        h_cols[3].write("**Trạng thái**")
        h_cols[4].write("**Hành động**")
        st.markdown("---           ", unsafe_allow_html=True)

        # Product Rows
        for p in products:
            p_cols = st.columns([2, 4, 2, 2, 2])
            p_cols[0].write(p['sku'])
            # Image & Name column
            img_name_col = p_cols[1]
            if p.get('image_url'):
                img_name_col.image(p['image_url'], width=60)
            img_name_col.write(p['name'])

            p_cols[2].write(cat_names.get(p.get('category_id'), "N/A"))

            # Status Toggle (Admin only)
            if is_admin:
                is_active = p.get('active', True)
                if p_cols[3].toggle("Hoạt động", value=is_active, key=f"active_{p['id']}") != is_active:
                    prod_mgr.set_product_active_status(p['id'], not is_active)
                    st.rerun()
            else:
                p_cols[3].write("Hoạt động" if p.get('active', True) else "Vô hiệu hóa")
            
            # Action Buttons
            action_col = p_cols[4]
            if is_manager_or_admin:
                if action_col.button("✏️ Sửa", key=f"edit_{p['id']}", use_container_width=True):
                    st.session_state.editing_product_id = p['id']
                    st.rerun()
            
            if is_admin:
                if action_col.button("🗑️ Xóa", key=f"delete_{p['id']}", use_container_width=True, type="primary"):
                    st.session_state.deleting_product_id = p['id'] # Set state to show confirmation
                    st.rerun()

            # Confirmation dialog for delete
            if is_admin and st.session_state.get('deleting_product_id') == p['id']:
                st.warning(f"Bạn có chắc chắn muốn xóa vĩnh viễn sản phẩm **{p['name']} ({p['sku']})**? Hành động này không thể hoàn tác.")
                c1, c2 = st.columns(2)
                if c1.button("XÁC NHẬN XÓA", key=f"confirm_delete_{p['id']}", use_container_width=True):
                    success, msg = prod_mgr.hard_delete_product(p['id'])
                    st.session_state.deleting_product_id = None
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                    st.rerun()
                if c2.button("Hủy", key=f"cancel_delete_{p['id']}", use_container_width=True):
                    st.session_state.deleting_product_id = None
                    st.rerun()
            
            st.markdown("---           ", unsafe_allow_html=True)

    # --- SETTINGS TAB (Admin only) ---
    if is_admin:
        with tabs[1]:
            # (The existing setup code for categories and units remains unchanged)
            col_cat, col_unit = st.columns(2)
            with col_cat:
                st.subheader("Quản lý Danh mục")
                with st.form("create_cat_form"):
                    new_cat = st.text_input("Tên danh mục mới")
                    cat_prefix = st.text_input("Mã tiền tố (2-3 ký tự)").strip().upper()
                    if st.form_submit_button("Thêm Danh mục"):
                        if new_cat and cat_prefix:
                            prod_mgr.create_category(new_cat, cat_prefix)
                            st.success(f"Đã thêm danh mục '{new_cat}'.")
                            st.rerun()
                        else:
                            st.error("Vui lòng điền đầy đủ thông tin.")
                st.dataframe(prod_mgr.get_categories(), hide_index=True)

            with col_unit:
                st.subheader("Quản lý Đơn vị tính")
                with st.form("create_unit_form"):
                    new_unit = st.text_input("Tên đơn vị mới")
                    if st.form_submit_button("Thêm Đơn vị"):
                        if new_unit:
                            prod_mgr.create_unit(new_unit)
                            st.success(f"Đã thêm đơn vị '{new_unit}'.")
                            st.rerun()
                        else:
                            st.error("Vui lòng nhập tên đơn vị.")
                st.dataframe(prod_mgr.get_units(), hide_index=True)
