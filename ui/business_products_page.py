
import streamlit as st
import pandas as pd
from datetime import datetime

# Import managers
from managers.auth_manager import AuthManager
from managers.branch_manager import BranchManager
from managers.product_manager import ProductManager
from managers.price_manager import PriceManager

def render_business_products_page(auth_mgr: AuthManager, branch_mgr: BranchManager, prod_mgr: ProductManager, price_mgr: PriceManager):
    st.header("🛍️ Sản phẩm Kinh doanh")

    # --- 1. PHÂN QUYỀN & CHỌN CHI NHÁNH --- #
    user_info = auth_mgr.get_current_user_info()
    user_role = user_info.get('role', 'staff')
    user_id = user_info.get('uid')

    if user_role not in ['admin', 'manager']:
        st.warning("Bạn không có quyền truy cập chức năng này.")
        return

    user_branches = user_info.get('branch_ids', [])
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.get_branches()}
    allowed_branches_map = {branch_id: all_branches_map[branch_id] for branch_id in user_branches if branch_id in all_branches_map}
    if user_role == 'admin':
        allowed_branches_map = all_branches_map

    if not allowed_branches_map:
        st.warning("Tài khoản của bạn chưa được gán vào chi nhánh nào.")
        return

    selected_branch_id = st.selectbox(
        "Chọn chi nhánh để quản lý", 
        options=list(allowed_branches_map.keys()), 
        format_func=lambda x: allowed_branches_map[x]
    ) if len(allowed_branches_map) > 1 else list(allowed_branches_map.keys())[0]

    if not selected_branch_id:
        st.stop()

    st.divider()

    # --- NÚT JOB ÁP DỤNG LỊCH TRÌNH GIÁ --- #
    if st.button("Chạy Job áp dụng giá theo lịch trình"):
        with st.spinner("Đang kiểm tra và áp dụng các lịch trình giá đã đến hạn..."):
            applied_count = price_mgr.apply_pending_schedules()
            st.success(f"Hoàn tất! Đã áp dụng thành công {applied_count} lịch trình giá.")

    st.divider()

    # --- DỮ LIỆU --- #
    all_catalog_products = prod_mgr.list_products()
    all_prices = price_mgr.get_all_prices()
    prices_in_branch = {p['sku']: p for p in all_prices if p.get('branch_id') == selected_branch_id}
    listed_skus = prices_in_branch.keys()
    listed_products = [p for p in all_catalog_products if p['sku'] in listed_skus]
    unlisted_products = [p for p in all_catalog_products if p['sku'] not in listed_skus]

    # --- NIÊM YẾT SẢN PHẨM MỚI --- #
    with st.expander("➕ Niêm yết sản phẩm mới vào chi nhánh"):
        # ... (Giữ nguyên) ...
        if not unlisted_products:
            st.info("Tất cả sản phẩm trong danh mục đã được niêm yết tại chi nhánh này.")
        else:
            with st.form("form_list_product"):
                product_to_list = st.selectbox("Chọn sản phẩm từ danh mục", options=unlisted_products, format_func=lambda p: f"{p['name']} ({p['sku']})")
                new_price = st.number_input("Nhập giá bán cho chi nhánh này (VNĐ)", min_value=0, step=1000)
                
                if st.form_submit_button("Niêm yết"):
                    if product_to_list and new_price > 0:
                        sku = product_to_list['sku']
                        price_mgr.set_price(sku, selected_branch_id, new_price)
                        price_mgr.set_business_status(sku, selected_branch_id, True)
                        st.success(f"Đã niêm yết thành công sản phẩm \"{product_to_list['name']}\"")
                        st.rerun()
                    else:
                        st.error("Vui lòng chọn sản phẩm và nhập giá bán lớn hơn 0.")

    st.divider()

    # --- DANH SÁCH SẢN PHẨM ĐANG KINH DOANH --- #
    st.subheader(f"Sản phẩm kinh doanh tại: {allowed_branches_map[selected_branch_id]}")
    if not listed_products:
        st.info("Chưa có sản phẩm nào được niêm yết tại chi nhánh này.")
    else:
        for prod in listed_products:
            sku = prod['sku']
            price_info = prices_in_branch.get(sku, {})
            current_price = price_info.get('price', 0)
            is_active = price_info.get('is_active', True)

            with st.container(border=True):
                c1, c2, c3 = st.columns([2,1,1])
                with c1: st.markdown(f"**{prod['name']}** `{prod['sku']}`")
                with c2: st.metric("Giá hiện tại", f"{current_price:,} VNĐ")
                # Sửa lỗi logic: Sử dụng lambda để đảm bảo giá trị mới nhất từ session_state được dùng
                with c3: st.toggle("Đang bán", value=is_active, key=f"status_{sku}", on_change=lambda sku=sku: price_mgr.set_business_status(sku, selected_branch_id, st.session_state[f"status_{sku}"]))

                # --- LỊCH TRÌNH GIÁ ---
                with st.expander("🗓️ Lịch trình giá tương lai"):
                    pending_schedules = price_mgr.get_pending_schedules_for_product(sku, selected_branch_id)
                    if pending_schedules:
                        for schedule in pending_schedules:
                            sc_col1, sc_col2, sc_col3 = st.columns([2, 2, 1])
                            sc_col1.date_input("Ngày áp dụng", value=schedule['apply_date'], disabled=True, key=f"date_{schedule['schedule_id']}")
                            sc_col2.text_input("Giá mới", value=f"{schedule['new_price']:,} VNĐ", disabled=True, key=f"price_{schedule['schedule_id']}")
                            if sc_col3.button("Hủy", key=f"cancel_{schedule['schedule_id']}"):
                                price_mgr.cancel_schedule(schedule['schedule_id'])
                                st.rerun()
                        st.info("Giá sẽ tự động cập nhật vào 00:00 của ngày áp dụng.")
                    else:
                        st.write("Không có lịch trình nào.")

                    # Form tạo lịch trình mới
                    with st.form(key=f"schedule_form_{sku}"):
                        sf_c1, sf_c2, sf_c3 = st.columns([2,2,1])
                        new_apply_date = sf_c1.date_input("Chọn ngày áp dụng mới")
                        new_scheduled_price = sf_c2.number_input("Nhập giá mới (VNĐ)", min_value=0, step=1000)
                        if st.form_submit_button("Hẹn lịch"):
                            if new_scheduled_price > 0:
                                price_mgr.schedule_price_change(sku, selected_branch_id, new_scheduled_price, new_apply_date, user_id)
                                st.success("Đã hẹn lịch thay đổi giá thành công!")
                                st.rerun()
                            else:
                                st.error("Giá mới phải lớn hơn 0.")

