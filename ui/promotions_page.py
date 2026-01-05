
import streamlit as st
import pandas as pd
from datetime import date, datetime

from managers.promotion_manager import PromotionManager
from managers.product_manager import ProductManager
from managers.branch_manager import BranchManager
from ui._utils import render_page_title

def render_promotions_page(promotion_mgr: PromotionManager, product_mgr: ProductManager, branch_mgr: BranchManager):
    render_page_title("Quản lý Khuyến mãi")

    # Lấy dữ liệu cho các select box
    all_products = product_mgr.list_products()
    all_categories = product_mgr.get_categories()
    product_options = {p['sku']: p['name'] for p in all_products if 'sku' in p}
    category_options = {c['id']: c['name'] for c in all_categories}

    # --- FORM TẠO/MÔ PHỎNG ---
    with st.expander("📝 Tạo Chương trình Khuyến mãi Mới", expanded=True):
        with st.form("promo_form", clear_on_submit=True):
            promo_name = st.text_input("Tên chương trình", help="VD: Khai trương chi nhánh mới, xả hàng hè...")
            promo_desc = st.text_area("Mô tả ngắn")
            
            c1, c2 = st.columns(2)
            start_date = c1.date_input("Ngày bắt đầu", value=date.today())
            end_date = c2.date_input("Ngày kết thúc", value=date(date.today().year, 12, 31))

            st.write("**Phạm vi áp dụng:**")
            scope_type = st.selectbox(
                "Loại phạm vi", 
                options=["ALL", "CATEGORY", "PRODUCT"],
                format_func=lambda x: {"ALL": "Toàn bộ cửa hàng", "CATEGORY": "Theo danh mục sản phẩm", "PRODUCT": "Theo sản phẩm cụ thể"}.get(x, x)
            )
            scope_ids = []
            if scope_type == "CATEGORY":
                scope_ids = st.multiselect("Chọn danh mục", options=list(category_options.keys()), format_func=lambda x: category_options.get(x, x))
            elif scope_type == "PRODUCT":
                scope_ids = st.multiselect("Chọn sản phẩm", options=list(product_options.keys()), format_func=lambda x: product_options.get(x, x))

            st.write("**Quy tắc giảm giá:**")
            c1, c2 = st.columns(2)
            auto_discount = c1.number_input("Giảm giá tự động (%)", 0, 100, 10)
            manual_limit = c2.number_input("Giảm thêm thủ công tối đa (%)", 0, 100, 5, help="Giới hạn cho nhân viên khi giảm giá thêm trên tổng hóa đơn.")
            
            st.write("**Ràng buộc:**")
            min_margin = st.number_input("Biên lợi nhuận tối thiểu bắt buộc (%)", 0, 100, 10, help="Hệ thống sẽ không cho phép bán nếu giá sau giảm khiến lợi nhuận thấp hơn mức này.")

            submitted_create = st.form_submit_button("Lưu Chương trình", type="primary", use_container_width=True)

    if submitted_create:
        if not promo_name or (scope_type != 'ALL' and not scope_ids):
            st.error("Vui lòng nhập Tên chương trình và chọn ít nhất một mục trong Phạm vi áp dụng.")
        else:
            form_data = {
                "name": promo_name,
                "description": promo_desc,
                "is_active": False,
                "start_datetime": datetime.combine(start_date, datetime.min.time()).isoformat(),
                "end_datetime": datetime.combine(end_date, datetime.max.time()).isoformat(),
                "priority": 100, 
                "stacking_rule": "EXCLUSIVE", 
                "promotion_type": "PRICE_PROGRAM",
                "scope": {"type": scope_type, "ids": scope_ids},
                "rules": {
                    "auto_discount": {"type": "PERCENT", "value": auto_discount},
                    "manual_extra_limit": {"type": "PERCENT", "value": manual_limit}
                },
                "constraints": {
                    "min_margin_floor_percent": min_margin
                }
            }
            success, message = promotion_mgr.create_promotion(form_data)
            if success:
                st.success(f"Đã lưu thành công chương trình: '{promo_name}'")
                st.rerun()
            else:
                st.error(f"Lỗi khi lưu: {message}")

    st.divider()

    # --- HIỂN THỊ CÁC CHƯƠNG TRÌNH ĐÃ LƯU ---
    st.subheader("Danh sách các chương trình đã lưu")
    
    def format_scope(scope, product_map, category_map):
        scope_type = scope.get("type", "N/A")
        scope_ids = scope.get("ids", [])
        if scope_type == "ALL": return "Toàn bộ cửa hàng"
        if not scope_ids: return f"({scope_type}) - Chưa chọn mục nào"
        names = []
        if scope_type == "PRODUCT":
            names = [product_map.get(pid, pid) for pid in scope_ids]
            return f"Sản phẩm: {', '.join(names)}"
        if scope_type == "CATEGORY":
            names = [category_map.get(cid, cid) for cid in scope_ids]
            return f"Danh mục: {', '.join(names)}"
        return "Không xác định"

    promotions = promotion_mgr.get_all_promotions()
    if not promotions:
        st.info("Chưa có chương trình khuyến mãi nào được tạo.")
    else:
        for promo in promotions:
            is_active = promo.get('is_active', False)
            status_text = "Đang hoạt động" if is_active else "Không hoạt động"
            status_color = "green" if is_active else "red"

            with st.expander(f"**{promo.get('name', 'N/A')}** - [Trạng thái: :{status_color}[{status_text}]]"):
                col_info, col_action = st.columns([3, 1])
                with col_info:
                    st.markdown(f"**Mô tả:** *{promo.get('description', '...')}*")
                    start_dt = datetime.fromisoformat(promo.get('start_datetime')).strftime('%d/%m/%Y')
                    end_dt = datetime.fromisoformat(promo.get('end_datetime')).strftime('%d/%m/%Y')
                    st.markdown(f"**Thời gian:** `{start_dt}` đến `{end_dt}`")
                    scope_text = format_scope(promo.get('scope', {}), product_options, category_options)
                    st.markdown(f"**Phạm vi:** {scope_text}")
                    rules = promo.get('rules', {})
                    auto = rules.get('auto_discount', {}).get('value', 0)
                    manual = rules.get('manual_extra_limit', {}).get('value', 0)
                    st.markdown(f"**Quy tắc:** Giảm tự động `{auto}%`, giảm thêm tối đa `{manual}%`.")

                with col_action:
                    if is_active:
                        if st.button("🔴 Tắt", key=f"deact_{promo['id']}", use_container_width=True):
                            promotion_mgr.update_promotion_status(promo['id'], False)
                            st.rerun()
                    else:
                        if st.button("🟢 Kích hoạt", key=f"act_{promo['id']}", use_container_width=True, type="primary"):
                            promotion_mgr.update_promotion_status(promo['id'], True)
                            st.rerun()
