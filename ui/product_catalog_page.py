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

    if 'editing_product_id' not in st.session_state:
        st.session_state.editing_product_id = None
    if 'deleting_product_id' not in st.session_state:
        st.session_state.deleting_product_id = None

    # --- TABS ---
    tab_titles = ["Quản lý Sản phẩm"] + (["Thiết lập Danh mục & Đơn vị"] if is_admin else [])
    tabs = st.tabs(tab_titles)

    # --- PRODUCT MANAGEMENT TAB ---
    with tabs[0]:
        if is_manager_or_admin:
            editing_product = prod_mgr.get_product_by_id(st.session_state.editing_product_id) if st.session_state.editing_product_id else None
            form_title = "✏️ Chỉnh sửa Sản phẩm" if editing_product else "➕ Thêm Sản Phẩm Mới"
            
            with st.expander(form_title, expanded=st.session_state.editing_product_id is not None):
                categories = prod_mgr.get_categories()
                units = prod_mgr.get_units()
                cat_opts = {c['id']: f"{c['name']} ({c.get('prefix', 'SP')})" for c in categories}
                unit_opts = {u['id']: u['name'] for u in units}

                with st.form("product_form"):
                    st.text_input("SKU", value=(editing_product['sku'] if editing_product else "Tạo tự động"), disabled=True)
                    name = st.text_input("**Tên sản phẩm**", value=editing_product['name'] if editing_product else "")
                    
                    col1, col2 = st.columns(2)
                    default_cat_idx = list(cat_opts.keys()).index(editing_product['category_id']) if editing_product and editing_product.get('category_id') in cat_opts else 0
                    cat_id = col1.selectbox("**Danh mục**", options=list(cat_opts.keys()), format_func=lambda x: cat_opts.get(x, "N/A"), index=default_cat_idx)
                    default_unit_idx = list(unit_opts.keys()).index(editing_product['unit_id']) if editing_product and editing_product.get('unit_id') in unit_opts else 0
                    unit_id = col2.selectbox("**Đơn vị**", options=list(unit_opts.keys()), format_func=lambda x: unit_opts.get(x, "N/A"), index=default_unit_idx)
                    
                    barcode = st.text_input("Barcode", value=editing_product['barcode'] if editing_product else "")
                    
                    st.write("Ảnh sản phẩm:")
                    delete_image = False
                    
                    image_id_to_edit = editing_product.get('image_id') if editing_product else None
                    image_url_to_edit = prod_mgr.image_handler.get_public_view_url(image_id_to_edit)
                    st.image(image_url_to_edit, width=150)
                    
                    if image_id_to_edit:
                        delete_image = st.checkbox("Xóa ảnh này và không thay thế", key=f"delete_img_{editing_product['id']}")

                    image_file = st.file_uploader("Tải ảnh mới (chỉ 1 ảnh, để trống nếu không đổi)", type=['png', 'jpg', 'jpeg'])

                    submit_col, cancel_col = st.columns([1,5])
                    if submit_col.form_submit_button("Lưu"):
                        if not name or not cat_id:
                            st.error("Tên sản phẩm và Danh mục là bắt buộc!")
                        else:
                            data = {"name": name, "category_id": cat_id, "unit_id": unit_id, "barcode": barcode}
                            if image_file: data['image_file'] = image_file
                            if delete_image: data['delete_image'] = True

                            with st.spinner("Đang xử lý..."):
                                if editing_product:
                                    success, msg = prod_mgr.update_product(editing_product['id'], data)
                                else:
                                    success, msg = prod_mgr.create_product(data)

                            if success:
                                st.success(msg)
                                st.session_state.editing_product_id = None
                                st.cache_data.clear() # <<< SỬA LỖI: Xóa cache để đảm bảo dữ liệu mới được tải
                                st.rerun()
                            else:
                                st.error(msg)
                    
                    if editing_product and cancel_col.form_submit_button("Hủy", type="secondary"):
                        st.session_state.editing_product_id = None
                        st.rerun()
        
        st.divider()
        st.subheader("Toàn bộ sản phẩm trong danh mục")
        products = prod_mgr.get_all_products(show_inactive=True)

        if not products:
            st.info("Chưa có sản phẩm nào.")
            return
        
        cat_names = {c['id']: c['name'] for c in prod_mgr.get_categories()}

        h_cols = st.columns([1, 1, 4, 2, 1, 2])
        h_cols[0].markdown("**SKU**")
        h_cols[1].markdown("**Ảnh**")
        h_cols[2].markdown("**Tên**")
        h_cols[3].markdown("**Danh mục**")
        h_cols[4].markdown("**Trạng thái**")
        h_cols[5].markdown("**Hành động**")
        st.markdown("<hr style='margin:0.5rem 0'>", unsafe_allow_html=True)

        for p in products:
            p_cols = st.columns([1, 1, 4, 2, 1, 2])
            p_cols[0].write(p['sku'])
            
            image_url = prod_mgr.image_handler.get_public_view_url(p.get('image_id'))
            p_cols[1].image(image_url, width=60)

            p_cols[2].write(p['name'])
            p_cols[3].write(cat_names.get(p.get('category_id'), "N/A"))

            if is_admin:
                is_active = p.get('active', True)
                new_status = p_cols[4].toggle("", value=is_active, key=f"active_{p['id']}", label_visibility="collapsed")
                if new_status != is_active:
                    prod_mgr.set_product_active_status(p['id'], new_status)
                    st.rerun()
            else:
                p_cols[4].write("✅" if p.get('active', True) else "🔒")
            
            action_col = p_cols[5].columns(2)
            if is_manager_or_admin:
                if action_col[0].button("✏️", key=f"edit_{p['id']}", use_container_width=True):
                    st.session_state.editing_product_id = p['id']
                    st.rerun()
            if is_admin:
                if action_col[1].button("🗑️", key=f"delete_{p['id']}", use_container_width=True):
                    st.session_state.deleting_product_id = p['id']
                    st.rerun()

            if is_admin and st.session_state.get('deleting_product_id') == p['id']:
                st.warning(f"Xóa vĩnh viễn **{p['name']} ({p['sku']})**? Hành động này không thể hoàn tác.")
                c1, c2 = st.columns(2)
                if c1.button("XÁC NHẬN XÓA", key=f"confirm_delete_{p['id']}", type="primary"):
                    prod_mgr.hard_delete_product(p['id'])
                    st.session_state.deleting_product_id = None
                    st.cache_data.clear() # <<< SỬA LỖI: Xóa cache khi xóa sản phẩm
                    st.rerun()
                if c2.button("Hủy bỏ", key=f"cancel_delete_{p['id']}"):
                    st.session_state.deleting_product_id = None
                    st.rerun()
            st.markdown("<hr style='margin:0.25rem 0'>", unsafe_allow_html=True)

    if is_admin and len(tabs) > 1:
        with tabs[1]:
            st.subheader("Thiết lập các thuộc tính sản phẩm")
            
            set_c1, set_c2 = st.columns(2)

            with set_c1:
                st.markdown("##### **Danh mục**")
                with st.form("new_category_form"):
                    new_cat_name = st.text_input("Tên danh mục mới")
                    new_cat_prefix = st.text_input("Tiền tố SKU (2-3 ký tự)", max_chars=3)
                    if st.form_submit_button("➕ Thêm Danh mục"):
                        if new_cat_name and new_cat_prefix:
                            success, msg = prod_mgr.add_category(new_cat_name, new_cat_prefix)
                            if success: 
                                st.success(msg)
                                st.cache_data.clear() # <<< SỬA LỖI: Xóa cache 
                                st.rerun()
                            else: st.error(msg)
                        else: st.warning("Vui lòng nhập đủ tên và tiền tố.")
                
                st.divider()
                st.write("**Danh sách danh mục:**")
                categories = prod_mgr.get_categories()
                if not categories:
                    st.info("Chưa có danh mục nào.")
                else:
                    for cat in categories:
                        cat_cols = st.columns([3, 2, 1])
                        cat_cols[0].write(cat['name'])
                        cat_cols[1].code(cat.get('prefix', 'N/A'))
                        if cat_cols[2].button("🗑️", key=f"del_cat_{cat['id']}", use_container_width=True):
                            prod_mgr.delete_category(cat['id'])
                            st.cache_data.clear() # <<< SỬA LỖI: Xóa cache 
                            st.rerun()

            with set_c2:
                st.markdown("##### **Đơn vị tính**")
                with st.form("new_unit_form"):
                    new_unit_name = st.text_input("Tên đơn vị mới")
                    if st.form_submit_button("➕ Thêm Đơn vị"):
                        if new_unit_name:
                            success, msg = prod_mgr.add_unit(new_unit_name)
                            if success: 
                                st.success(msg)
                                st.cache_data.clear() # <<< SỬA LỖI: Xóa cache 
                                st.rerun()
                            else: st.error(msg)
                        else: st.warning("Vui lòng nhập tên đơn vị.")

                st.divider()
                st.write("**Danh sách đơn vị:**")
                units = prod_mgr.get_units()
                if not units:
                    st.info("Chưa có đơn vị nào.")
                else:
                    for unit in units:
                        unit_cols = st.columns([4, 1])
                        unit_cols[0].write(unit['name'])
                        if unit_cols[1].button("🗑️", key=f"del_unit_{unit['id']}", use_container_width=True):
                            prod_mgr.delete_unit(unit['id'])
                            st.cache_data.clear() # <<< SỬA LỖI: Xóa cache 
                            st.rerun()