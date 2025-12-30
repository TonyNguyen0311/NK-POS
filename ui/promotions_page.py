import streamlit as st

def render_promotions_page():
    st.title("🎁 Quản lý Khuyến mãi")

    promotion_mgr = st.session_state.promotion_mgr

    # Display existing promotions
    st.header("Chương trình đang có")
    promotions = promotion_mgr.collection_ref.get()
    if not promotions:
        st.info("Chưa có chương trình khuyến mãi nào.")
    else:
        for promo in promotions:
            promo_data = promo.to_dict()
            with st.expander(f"{promo_data.get('name', 'Chưa có tên')} (Loại: {promo_data.get('promotion_type', '')})"):
                st.json(promo_data)

    # Create new promotion form
    st.header("Tạo chương trình khuyến mãi mới")
    with st.form("new_promo_form", clear_on_submit=True):
        st.subheader("Loại chương trình: Chương trình Giá")

        promo_name = st.text_input("Tên chương trình", help="VD: Khai trương chi nhánh mới")
        promo_desc = st.text_area("Mô tả")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Ngày bắt đầu")
        with col2:
            end_date = st.date_input("Ngày kết thúc")

        st.write("**Quy tắc giảm giá:**")
        auto_discount_percent = st.number_input("Giảm giá tự động (%)", min_value=0, max_value=100, value=0)
        manual_extra_percent = st.number_input("Giảm thêm thủ công tối đa (%)", min_value=0, max_value=100, value=0, help="Nhân viên được phép giảm thêm tối đa bao nhiêu % tại POS mà không cần PIN.")
        
        st.write("**Ràng buộc:**")
        min_margin_percent = st.number_input("Biên lợi nhuận tối thiểu (%)", min_value=0, max_value=100, value=10, help="Hệ thống sẽ không cho phép giảm giá nếu lợi nhuận gộp của sản phẩm thấp hơn mức này.")
        
        submitted = st.form_submit_button("Tạo chương trình")

        if submitted:
            if not promo_name:
                st.error("Vui lòng nhập tên chương trình.")
                return

            new_promo_data = {
                "name": promo_name,
                "description": promo_desc,
                "is_active": False, # Default to inactive
                "start_datetime": f"{start_date.isoformat()}T00:00:00Z",
                "end_datetime": f"{end_date.isoformat()}T23:59:59Z",
                "priority": 100, # Default priority
                "stacking_rule": "EXCLUSIVE",
                "promotion_type": "PRICE_PROGRAM",
                "scope": {
                    "type": "ALL",
                    "ids": []
                },
                "rules": {
                    "auto_discount": {"type": "PERCENT", "value": auto_discount_percent},
                    "manual_extra_limit": {"type": "PERCENT", "value": manual_extra_percent}
                },
                "constraints": {
                    "min_margin_floor_percent": min_margin_percent
                }
            }
            
            success, message = promotion_mgr.create_promotion(new_promo_data)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
