# ui/transfer_create_tab.py
import streamlit as st
from datetime import datetime

def render_create_transfer_form(from_branch_id, all_branches, inventory_manager, product_manager, user_id):
    st.header("Tạo Phiếu Luân Chuyển")
    
    products = product_manager.get_all_products()
    inventory = inventory_manager.get_inventory_by_branch(from_branch_id)

    # Validate data types robustly before use
    if not isinstance(products, list) or not all(isinstance(p, dict) for p in products):
        st.error("Không thể tải được danh sách sản phẩm. Dữ liệu nhận được không hợp lệ.")
        return

    if not isinstance(inventory, dict):
        st.error("Không thể tải được dữ liệu tồn kho. Dữ liệu nhận được không hợp lệ.")
        return

    with st.form("create_transfer_form", clear_on_submit=True):
        other_branches = [b for b in all_branches if b['id'] != from_branch_id]
        if not other_branches:
            st.warning("Không có chi nhánh khác để luân chuyển.")
            return
            
        to_branch_id = st.selectbox(
            "Chọn chi nhánh nhận hàng", 
            options=[b['id'] for b in other_branches],
            format_func=lambda bid: next((b.get('name', bid) for b in other_branches if b['id'] == bid), bid)
        )
        
        st.subheader("Danh sách sản phẩm cần chuyển")
        
        st.session_state.transfer_items = st.session_state.get('transfer_items', [])
        for i, item in enumerate(st.session_state.transfer_items):
            cols = st.columns([4, 2, 1])
            cols[0].write(f"**{item.get('product_name', item['sku'])} ({item['sku']})** - SL: {item['quantity']}")
            if cols[1].button(f"Xóa", key=f"del_{i}", use_container_width=True):
                st.session_state.transfer_items.pop(i)
                st.rerun()
        
        st.markdown("---")
        
        product_options = {p['sku']: p for p in products if 'sku' in p}
        
        available_products = {sku: product for sku, product in product_options.items() if inventory.get(sku, {}).get('stock_quantity', 0) > 0}

        if not available_products:
            st.warning("Chi nhánh này không còn sản phẩm nào có thể luân chuyển.")
            st.form_submit_button("Tạo Phiếu", disabled=True)
            return

        form_cols = st.columns([3, 2, 1])
        selected_sku = form_cols[0].selectbox(
            "Chọn sản phẩm", 
            options=list(available_products.keys()), 
            format_func=lambda sku: f"{available_products.get(sku, {}).get('name', sku)} ({sku})"
        )
        
        if selected_sku:
            current_stock = inventory.get(selected_sku, {}).get('stock_quantity', 0)
            form_cols[0].info(f"Tồn kho khả dụng: {int(current_stock)}")
            quantity = form_cols[1].number_input("Số lượng", min_value=1, max_value=max(1, int(current_stock)), step=1, key=f"qty_{selected_sku}")

            if form_cols[2].form_submit_button("Thêm", use_container_width=True):
                if quantity > current_stock:
                    st.warning(f"Số lượng tồn kho không đủ.")
                else:
                    found = next((item for item in st.session_state.transfer_items if item['sku'] == selected_sku), None)
                    if found:
                        found['quantity'] += quantity
                    else:
                        selected_product = available_products[selected_sku]
                        st.session_state.transfer_items.append({
                            'sku': selected_sku, 
                            'product_name': selected_product.get('name', 'Sản phẩm không tên'), 
                            'cogs': selected_product.get('cogs', 0), 
                            'quantity': quantity
                        })
                    st.rerun()

        notes = st.text_area("Ghi chú (nếu có)")
        if st.form_submit_button("Tạo Phiếu Luân Chuyển", use_container_width=True):
            if not st.session_state.transfer_items:
                st.error("Vui lòng thêm sản phẩm vào phiếu.")
            else:
                try:
                    transfer_id = inventory_manager.create_transfer(
                        from_branch_id=from_branch_id, to_branch_id=to_branch_id,
                        items=st.session_state.transfer_items, user_id=user_id, notes=notes
                    )
                    st.success(f"Đã tạo thành công phiếu luân chuyển `{transfer_id}`.")
                    st.session_state.transfer_items = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi tạo phiếu: {e}")
