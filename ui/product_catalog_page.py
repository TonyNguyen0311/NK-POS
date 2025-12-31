
import streamlit as st
import pandas as pd
from managers.product_manager import ProductManager
from managers.auth_manager import AuthManager

def render_product_catalog_page(prod_mgr: ProductManager, auth_mgr: AuthManager):
    st.header("🗂️ Danh mục Sản phẩm")

    # --- Check access rights ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role') != 'admin':
        st.error("Chỉ Quản trị viên (admin) mới có quyền truy cập chức năng này.")
        return

    # --- Category & Unit Setup (for Admin) ---
    with st.expander("Thiết lập Danh mục & Đơn vị"):
        col_cat, col_unit = st.columns(2)
        with col_cat:
            st.subheader("Danh mục")
            with st.form("create_cat"):
                new_cat = st.text_input("Tên danh mục (VD: Áo Thun)")
                cat_prefix = st.text_input("Mã tiền tố (VD: AT)").strip().upper()
                if st.form_submit_button("Thêm Danh mục"):
                    if new_cat and cat_prefix:
                        prod_mgr.create_category(new_cat, cat_prefix)
                        st.success(f"Đã thêm '{new_cat}' ({cat_prefix})")
                        st.rerun()
                    else:
                        st.error("Vui lòng nhập cả tên và mã tiền tố")
            cats = prod_mgr.get_categories()
            if cats:
                st.dataframe(pd.DataFrame(cats)[['name', 'prefix', 'current_seq']], hide_index=True)
        
        with col_unit:
            st.subheader("Đơn vị tính")
            with st.form("create_unit"):
                new_unit = st.text_input("Tên đơn vị mới (VD: Cái, Chiếc)")
                if st.form_submit_button("Thêm Đơn vị"):
                    if new_unit:
                        prod_mgr.create_unit(new_unit)
                        st.success(f"Đã thêm '{new_unit}'")
                        st.rerun()
            units = prod_mgr.get_units()
            if units:
                st.dataframe(pd.DataFrame(units)[['name']], hide_index=True)

    st.divider()

    # --- Form to Add New Product (Master Product) ---
    with st.expander("➕ Thêm Sản Phẩm Mới", expanded=False):
        with st.form("add_product_form", clear_on_submit=True):
            st.info("💡 SKU sẽ được tạo tự động dựa trên Danh mục (VD: AT-0001)")
            
            categories = prod_mgr.get_categories()
            units = prod_mgr.get_units()

            c1, c2, c3 = st.columns([2, 1, 1])
            name = c1.text_input("**Tên sản phẩm**")
            cat_opts = {f"{c['name']} ({c.get('prefix', 'SP')})": c['id'] for c in categories}
            unit_opts = {u['name']: u['id'] for u in units}
            cat_name = c2.selectbox("**Danh mục**", options=list(cat_opts.keys()) if cat_opts else [])
            unit_name = c3.selectbox("**Đơn vị**", options=list(unit_opts.keys()) if unit_opts else [])

            # REMOVED reference cost price, barcode now takes full width
            barcode = st.text_input("Barcode (Nếu có)")
            
            image_file = st.file_uploader("Ảnh sản phẩm", type=['png', 'jpg', 'jpeg'])

            submitted = st.form_submit_button("Lưu vào Danh mục")
            if submitted:
                if not name or not cat_name:
                    st.error("Tên sản phẩm và Danh mục là bắt buộc!")
                else:
                    img_url = "" # Default to empty string
                    if image_file:
                        if prod_mgr.image_handler:
                            with st.spinner("Đang tối ưu và tải ảnh lên Google Drive..."):
                                img_url = prod_mgr.upload_image(image_file, image_file.name)
                                if not img_url:
                                    st.warning("Tải ảnh thất bại, nhưng sản phẩm vẫn sẽ được tạo không có ảnh.")
                        else:
                            st.warning("Chức năng tải ảnh chưa được cấu hình. Sản phẩm sẽ được tạo không có ảnh.")
                    
                    # REMOVED cost_price from data dictionary
                    data = {
                        "name": name,
                        "barcode": barcode,
                        "category_id": cat_opts.get(cat_name),
                        "unit_id": unit_opts.get(unit_name),
                        "image_url": img_url
                    }
                    
                    success, msg = prod_mgr.create_product(data)
                    if success:
                        st.success(f"Tạo sản phẩm '{name}' với SKU '{msg}' thành công!")
                        st.rerun()
                    else:
                        st.error(msg)

    st.divider()

    # --- Master Product List ---
    st.subheader("Toàn bộ sản phẩm trong danh mục")
    products = prod_mgr.get_all_products()
    
    if products:
        # Get category info for display
        cats_df = pd.DataFrame(prod_mgr.get_categories()).set_index('id')
        cat_names = cats_df['name'].to_dict()

        df_data = []
        for p in products:
            df_data.append({
                "SKU": p['sku'],
                "Ảnh": p.get('image_url'),
                "Tên": p['name'],
                "Danh mục": cat_names.get(p.get('category_id'), "N/A"),
                "Barcode": p.get('barcode', '-')
            })
        
        st.dataframe(
            pd.DataFrame(df_data),
            column_config={
                "Ảnh": st.column_config.ImageColumn("Ảnh", width="small")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Chưa có sản phẩm nào trong danh mục.")
