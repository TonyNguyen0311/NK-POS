import streamlit as st
import pandas as pd
from ui._utils import format_vnd

def render_product_page():
    st.title("📦 Quản lý Sản phẩm")
    
    prod_mgr = st.session_state.product_mgr
    branch_mgr = st.session_state.branch_mgr
    
    tab1, tab2 = st.tabs(["Danh sách Sản phẩm", "Danh mục & Đơn vị"])

    # --- TAB 2: DANH MỤC & ĐƠN VỊ ---
    with tab2:
        col_cat, col_unit = st.columns(2)
        
        with col_cat:
            st.subheader("Danh mục")
            # Form tạo danh mục có thêm Prefix
            with st.form("create_cat"):
                new_cat = st.text_input("Tên danh mục (VD: Áo Thun)")
                cat_prefix = st.text_input("Mã tiền tố (VD: AT)").strip().upper()
                if st.form_submit_button("Thêm Danh mục"):
                    if new_cat and cat_prefix:
                        prod_mgr.create_category(new_cat, cat_prefix)
                        st.success(f"Đã thêm {new_cat} ({cat_prefix})")
                        st.rerun()
                    else:
                        st.error("Vui lòng nhập cả tên và mã tiền tố")
            
            # Hiển thị
            cats = prod_mgr.get_categories()
            if cats:
                st.dataframe(pd.DataFrame(cats)[['name', 'prefix', 'current_seq']], hide_index=True)
        
        with col_unit:
            st.subheader("Đơn vị tính")
            new_unit = st.text_input("Tên đơn vị mới")
            if st.button("Thêm Đơn vị"):
                if new_unit:
                    prod_mgr.create_unit(new_unit)
                    st.success(f"Đã thêm {new_unit}")
                    st.rerun()
            
            units = prod_mgr.get_units()
            if units:
                st.dataframe(pd.DataFrame(units)[['name']], hide_index=True)

    # --- TAB 1: SẢN PHẨM ---
    with tab1:
        categories = prod_mgr.get_categories()
        units = prod_mgr.get_units()
        branches = branch_mgr.get_all_branches()

        with st.expander("➕ THÊM SẢN PHẨM MỚI", expanded=False):
            with st.form("add_product_form", clear_on_submit=True):
                st.info("💡 SKU sẽ được tạo tự động dựa trên Danh mục (VD: AT-0001)")
                
                c1, c2, c3 = st.columns([2, 1, 1])
                name = c1.text_input("Tên sản phẩm")
                
                cat_opts = {f"{c['name']} ({c.get('prefix', 'SP')})": c['id'] for c in categories}
                unit_opts = {u['name']: u['id'] for u in units}
                
                cat_name = c2.selectbox("Danh mục", options=list(cat_opts.keys()) if cat_opts else [])
                unit_name = c3.selectbox("Đơn vị", options=list(unit_opts.keys()) if unit_opts else [])

                c4, c5 = st.columns(2)
                barcode = c4.text_input("Barcode (Quét mã)")
                cost_price = c5.number_input("Giá vốn", min_value=0, step=1000)

                st.markdown("---")
                st.write("💰 **Thiết lập giá bán**")
                col_price_def, col_img = st.columns([1, 2])
                
                price_default = col_price_def.number_input("Giá bán mặc định", min_value=0, step=1000)
                image_file = col_img.file_uploader("Ảnh sản phẩm", type=['png', 'jpg', 'jpeg'])
                
                # Giá theo chi nhánh
                price_by_branch = {}
                if branches:
                    st.caption("Giá riêng theo chi nhánh (để 0 sẽ lấy giá mặc định)")
                    cols = st.columns(len(branches))
                    for idx, br in enumerate(branches):
                        with cols[idx]:
                            p = st.number_input(f"Giá {br['name']}", min_value=0, step=1000, key=f"p_{br['id']}")
                            if p > 0:
                                price_by_branch[br['id']] = p

                submitted = st.form_submit_button("Lưu Sản phẩm")
                
                if submitted:
                    if not name or not cat_name:
                        st.error("Tên và Danh mục là bắt buộc!")
                    else:
                        img_url = ""
                        if image_file:
                            with st.spinner("Đang upload ảnh..."):
                                img_url = prod_mgr.upload_image(image_file, image_file.name)
                        
                        data = {
                            "name": name,
                            "barcode": barcode,
                            "category_id": cat_opts.get(cat_name),
                            "unit_id": unit_opts.get(unit_name),
                            "cost_price": cost_price,
                            "price_default": price_default,
                            "price_by_branch": price_by_branch,
                            "image_url": img_url
                        }
                        
                        success, msg = prod_mgr.create_product(data)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        # HIỂN THỊ DANH SÁCH
        st.divider()
        products = prod_mgr.get_all_products()
        
        if products:
            df_data = []
            for p in products:
                # Tìm tên danh mục từ ID
                cat_display = next((k for k, v in cat_opts.items() if v == p.get('category_id')), "N/A")
                
                df_data.append({
                    "SKU": p['sku'],
                    "Ảnh": p.get('image_url'),
                    "Tên": p['name'],
                    "Giá chuẩn": format_vnd(p.get('price_default', 0)),
                    "Danh mục": cat_display,
                    "Chi nhánh riêng": len(p.get('price_by_branch', {}))
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
            st.info("Chưa có sản phẩm nào.")
