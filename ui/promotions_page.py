import streamlit as st
import pandas as pd
from datetime import date, datetime

def render_promotions_page():
    st.title("🎁 Quản lý Khuyến mãi")

    promotion_mgr = st.session_state.promotion_mgr
    product_mgr = st.session_state.product_mgr

    # Lấy dữ liệu cho các select box
    all_products = product_mgr.list_products()
    all_categories = product_mgr.get_categories()
    product_options = {p['sku']: p['name'] for p in all_products}
    category_options = {c['id']: c['name'] for c in all_categories}

    if 'simulation_results' not in st.session_state:
        st.session_state.simulation_results = None

    # --- FORM TẠO/MÔ PHỎNG ---
    with st.form("promo_form"):
        st.header("Tạo hoặc Mô phỏng Chương trình Giá")
        # ... (Phần code của form giữ nguyên như trước)
        promo_name = st.text_input("Tên chương trình", "Chương trình giảm giá tháng 7", help="VD: Khai trương chi nhánh mới")
        promo_desc = st.text_area("Mô tả", "Giảm giá đặc biệt cho một số mặt hàng tồn kho.")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Ngày bắt đầu", value=date.today())
        with col2:
            end_date = st.date_input("Ngày kết thúc", value=date(date.today().year, 12, 31))

        st.write("**Phạm vi áp dụng:**")
        scope_type = st.selectbox(
            "Loại phạm vi", 
            options=["ALL", "CATEGORY", "PRODUCT"],
            format_func=lambda x: {"ALL": "Toàn bộ cửa hàng", "CATEGORY": "Theo danh mục sản phẩm", "PRODUCT": "Theo sản phẩm cụ thể"}.get(x, x)
        )
        scope_ids = []
        if scope_type == "CATEGORY":
            scope_ids = st.multiselect("Chọn danh mục", options=list(category_options.keys()), format_func=lambda x: category_options[x])
        elif scope_type == "PRODUCT":
            scope_ids = st.multiselect("Chọn sản phẩm", options=list(product_options.keys()), format_func=lambda x: product_options[x])

        st.write("**Quy tắc giảm giá:**")
        auto_discount = st.number_input("Giảm giá tự động (%)", 0, 100, 10)
        manual_limit = st.number_input("Giảm thêm thủ công tối đa (%)", 0, 100, 5)
        st.write("**Ràng buộc:**")
        min_margin = st.number_input("Biên lợi nhuận tối thiểu (%)", 0, 100, 10)

        col_btn1, col_btn2, _ = st.columns([1,1,3])
        submitted_simulate = col_btn1.form_submit_button("Mô phỏng", use_container_width=True)
        submitted_create = col_btn2.form_submit_button("Lưu", type="primary", use_container_width=True)

    # --- XỬ LÝ LOGIC ---
    form_data = {
        "name": promo_name,
        "description": promo_desc,
        "is_active": False, 
        "start_datetime": f"{start_date.isoformat()}T00:00:00Z",
        "end_datetime": f"{end_date.isoformat()}T23:59:59Z",
        "priority": 100, "stacking_rule": "EXCLUSIVE", "promotion_type": "PRICE_PROGRAM",
        "scope": {"type": scope_type, "ids": scope_ids},
        "rules": {"auto_discount": {"type": "PERCENT", "value": auto_discount}, "manual_extra_limit": {"type": "PERCENT", "value": manual_limit}},
        "constraints": {"min_margin_floor_percent": min_margin}
    }
    if submitted_create:
        if not promo_name or (scope_type != 'ALL' and not scope_ids):
            st.error("Vui lòng nhập Tên và chọn Phạm vi áp dụng.")
        else:
            success, message = promotion_mgr.create_promotion(form_data)
            if success: st.success(f"✅ Đã lưu: {promo_name}"); st.rerun()
            else: st.error(message)

    # --- HIỂN THỊ CÁC CHƯƠNG TRÌNH ĐÃ LƯU ---
    st.header("Chương trình Đã Lưu")
    
    def format_scope(scope, product_map, category_map):
        scope_type = scope.get("type", "N/A")
        scope_ids = scope.get("ids", [])
        if scope_type == "ALL": return "Toàn bộ cửa hàng"
        if not scope_ids: return f"({scope_type}) - Chưa chọn mục nào"
        if scope_type == "PRODUCT":
            names = [product_map.get(pid, pid) for pid in scope_ids]
            return f"Sản phẩm: {', '.join(names)}"
        if scope_type == "CATEGORY":
            names = [category_map.get(cid, cid) for cid in scope_ids]
            return f"Danh mục: {' , '.join(names)}"
        return "Không xác định"

    promotions = promotion_mgr.collection_ref.order_by("created_at", direction="DESCENDING").stream()
    if not promotions:
        st.info("Chưa có chương trình khuyến mãi nào.")
    else:
        for promo in promotions:
            promo_data = promo.to_dict()
            is_active = promo_data.get('is_active', False)
            status_text = "Hoạt động" if is_active else "Không hoạt động"
            status_color = "green" if is_active else "red"

            with st.expander(f"**{promo_data.get('name', 'N/A')}** - [Trạng thái: :{status_color}[{status_text}]]"):
                col_info, col_action = st.columns([3, 1])
                with col_info:
                    st.markdown(f"**Mô tả:** *{promo_data.get('description', '...')}*")
                    st.markdown(f"**Thời gian:** `{promo_data.get('start_datetime')[:10]}` đến `{promo_data.get('end_datetime')[:10]}`")
                    scope_text = format_scope(promo_data.get('scope', {}), product_options, category_options)
                    st.markdown(f"**Phạm vi:** {scope_text}")
                    rules = promo_data.get('rules', {})
                    auto = rules.get('auto_discount', {}).get('value', 0)
                    manual = rules.get('manual_extra_limit', {}).get('value', 0)
                    st.markdown(f"**Quy tắc:** Giảm tự động `{auto}%`, giảm thêm tối đa `{manual}%`.")

                with col_action:
                    if is_active:
                        if st.button("🔴 Tắt", key=f"deact_{promo.id}", use_container_width=True):
                            promotion_mgr.update_promotion_status(promo.id, False)
                            st.rerun()
                    else:
                        if st.button("🟢 Kích hoạt", key=f"act_{promo.id}", use_container_width=True, type="primary"):
                            promotion_mgr.update_promotion_status(promo.id, True)
                            st.rerun()