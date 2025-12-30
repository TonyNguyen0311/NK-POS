
import streamlit as st
from datetime import datetime

def show_stock_transfer_page(branch_manager, inventory_manager, product_manager, auth_manager):
    st.title("Luân chuyển hàng hóa")

    user_info = auth_manager.get_current_user_info()
    if not user_info:
        st.warning("Vui lòng đăng nhập để sử dụng tính năng này.")
        return

    user_id = user_info['uid']
    user_role = user_info.get('role', 'staff')
    all_branches = branch_manager.list_branches()
    all_branches_map = {b['id']: b['name'] for b in all_branches}

    from_branch_id = None

    if user_role == 'admin':
        if not all_branches:
            st.warning("Chưa có chi nhánh nào được tạo. Vui lòng tạo chi nhánh trong Quản trị Hệ thống trước.")
            return
        from_branch_id = st.selectbox(
            "Chọn chi nhánh thao tác (Admin)", 
            options=list(all_branches_map.keys()), 
            format_func=lambda k: all_branches_map[k]
        )
    else:
        user_branches = user_info.get('branch_ids', [])
        if not user_branches:
            st.error("Tài khoản của bạn chưa được gán vào chi nhánh nào. Vui lòng liên hệ quản trị viên.")
            return
        
        if len(user_branches) > 1:
            branch_options = {bid: all_branches_map.get(bid, bid) for bid in user_branches}
            from_branch_id = st.selectbox(
                "Chọn chi nhánh thao tác", 
                options=list(branch_options.keys()), 
                format_func=lambda k: branch_options[k]
            )
        else:
            from_branch_id = user_branches[0]

    if not from_branch_id:
        st.error("Không thể xác định chi nhánh thao tác. Vui lòng thử lại hoặc liên hệ quản trị viên.")
        return

    current_branch_name = all_branches_map.get(from_branch_id, "N/A")
    st.markdown(f"**Chi nhánh thao tác:** `{current_branch_name}` (`{from_branch_id}`)")

    tab1, tab2, tab3 = st.tabs([
        "Tạo Phiếu Luân Chuyển Mới", 
        "Danh sách Phiếu Chuyển Đi", 
        "Danh sách Phiếu Chuyển Đến"
    ])

    with tab1:
        render_create_transfer_form(from_branch_id, all_branches, inventory_manager, product_manager, user_id)

    with tab2:
        render_outgoing_transfers(from_branch_id, all_branches_map, inventory_manager, user_id)
        
    with tab3:
        render_incoming_transfers(from_branch_id, all_branches_map, inventory_manager, user_id)

def render_create_transfer_form(from_branch_id, all_branches, inventory_manager, product_manager, user_id):
    st.header("Tạo Phiếu Luân Chuyển")
    
    products = product_manager.get_products_for_business()
    inventory = inventory_manager.get_inventory_by_branch(from_branch_id)

    with st.form("create_transfer_form", clear_on_submit=True):
        other_branches = [b for b in all_branches if b['id'] != from_branch_id]
        to_branch_id = st.selectbox(
            "Chọn chi nhánh nhận hàng", 
            options=[b['id'] for b in other_branches],
            format_func=lambda bid: f"{next((b['name'] for b in other_branches if b['id'] == bid), bid)}"
        )
        
        st.subheader("Danh sách sản phẩm cần chuyển")
        
        if 'transfer_items' not in st.session_state:
            st.session_state.transfer_items = []

        for i, item in enumerate(st.session_state.transfer_items):
            cols = st.columns([4, 2, 1])
            cols[0].write(f"**{item['product_name']} ({item['sku']})**")
            cols[1].write(f"Số lượng: {item['quantity']}")
            if cols[2].button(f"Xóa", key=f"del_{i}"):
                st.session_state.transfer_items.pop(i)
                st.rerun()
        
        st.markdown("---")
        
        form_cols = st.columns([3, 2, 1])
        product_options = {p['sku']: p for p in products}
        
        available_products = {sku: product for sku, product in product_options.items() if inventory.get(sku, {}).get('stock_quantity', 0) > 0}

        if not available_products:
            st.warning("Chi nhánh này hiện không có sản phẩm nào để luân chuyển.")
            st.form_submit_button("Tạo Phiếu Luân Chuyển", disabled=True)
            return

        # FIXED: Corrected the typo from [''name''] to ['name']
        selected_sku = form_cols[0].selectbox("Chọn sản phẩm", options=list(available_products.keys()), format_func=lambda sku: f"{available_products[sku]['name']} ({sku})")
        
        current_stock = inventory.get(selected_sku, {}).get('stock_quantity', 0)
        
        quantity = form_cols[1].number_input("Số lượng", min_value=1, max_value=int(current_stock), step=1, key=f"qty_{selected_sku}")
        form_cols[0].info(f"Tồn kho khả dụng: {int(current_stock)}")

        if form_cols[2].form_submit_button("Thêm", use_container_width=True):
            if selected_sku and quantity > 0:
                if quantity > inventory.get(selected_sku, {}).get('stock_quantity', 0):
                    st.warning(f"Số lượng tồn kho của {selected_sku} không đủ.")
                else:
                    found = False
                    for item in st.session_state.transfer_items:
                        if item['sku'] == selected_sku:
                            item['quantity'] += quantity
                            found = True
                            break
                    if not found:
                        selected_product = available_products[selected_sku]
                        st.session_state.transfer_items.append({
                            'sku': selected_sku, 
                            'product_name': selected_product['name'], 
                            'cogs': selected_product.get('cogs', 0), 
                            'quantity': quantity
                        })
                    st.rerun()

        notes = st.text_area("Ghi chú (nếu có)")
        submitted = st.form_submit_button("Tạo Phiếu Luân Chuyển", use_container_width=True)

        if submitted:
            if not to_branch_id:
                st.error("Vui lòng chọn chi nhánh nhận.")
            elif not st.session_state.transfer_items:
                st.error("Vui lòng thêm ít nhất một sản phẩm vào phiếu.")
            else:
                try:
                    transfer_id = inventory_manager.create_transfer(
                        from_branch_id=from_branch_id,
                        to_branch_id=to_branch_id,
                        items=st.session_state.transfer_items,
                        user_id=user_id,
                        notes=notes
                    )
                    st.success(f"Đã tạo thành công phiếu luân chuyển `{transfer_id}`.")
                    st.session_state.transfer_items = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi tạo phiếu: {e}")

def render_outgoing_transfers(branch_id, all_branches_map, inventory_manager, user_id):
    st.header("Phiếu Chuyển Đi")
    
    status_filter = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None, "PENDING", "SHIPPED", "COMPLETED", "CANCELLED"], 
        format_func=lambda x: "Tất cả" if x is None else x,
        key="out_status_filter"
    )

    transfers = inventory_manager.get_transfers(branch_id, direction='outgoing', status=status_filter)

    if not transfers:
        st.info("Không có phiếu luân chuyển nào được gửi đi từ chi nhánh này.")
        return

    for t in sorted(transfers, key=lambda x: x['created_at'], reverse=True):
        to_branch_name = all_branches_map.get(t['to_branch_id'], t['to_branch_id'])
        with st.expander(f"Phiếu `{t['id']}` gửi tới CN `{to_branch_name}` - Trạng thái: **{t['status']}**"):
            st.write(f"**Ngày tạo:** {datetime.fromisoformat(t['created_at']).strftime('%Y-%m-%d %H:%M')}")
            st.write(f"**Ghi chú:** {t.get('notes', 'N/A')}")
            st.write("**Sản phẩm:**")
            for item in t['items']:
                st.write(f"- {item.get('product_name', item['sku'])}: {item['quantity']}")
            
            if t['status'] == 'PENDING':
                col1, col2 = st.columns(2)
                if col1.button("Xác nhận Gửi hàng", key=f"ship_{t['id']}", use_container_width=True):
                    try:
                        inventory_manager.ship_transfer(t['id'], user_id)
                        st.success(f"Đã xác nhận gửi phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận gửi: {e}")
                if col2.button("Hủy Phiếu", key=f"cancel_{t['id']}", use_container_width=True):
                    try:
                        inventory_manager.cancel_transfer(t['id'], user_id)
                        st.warning(f"Đã hủy phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi hủy phiếu: {e}")

def render_incoming_transfers(branch_id, all_branches_map, inventory_manager, user_id):
    st.header("Phiếu Chuyển Đến")
    
    status_filter = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None, "SHIPPED", "COMPLETED", "CANCELLED"],
        format_func=lambda x: "Tất cả" if x is None else x,
        key="in_status_filter"
    )

    transfers = inventory_manager.get_transfers(branch_id, direction='incoming', status=status_filter)

    if not transfers:
        st.info("Không có phiếu luân chuyển nào đang gửi đến chi nhánh này.")
        return

    for t in sorted(transfers, key=lambda x: x.get('shipped_at', x['created_at']), reverse=True):
        from_branch_name = all_branches_map.get(t['from_branch_id'], t['from_branch_id'])
        with st.expander(f"Phiếu `{t['id']}` từ CN `{from_branch_name}` - Trạng thái: **{t['status']}**"):
            st.write(f"**Ngày gửi:** {datetime.fromisoformat(t.get('shipped_at', t['created_at'])).strftime('%Y-%m-%d %H:%M')}")
            st.write(f"**Ghi chú:** {t.get('notes', 'N/A')}")
            st.write("**Sản phẩm:**")
            for item in t['items']:
                st.write(f"- {item.get('product_name', item['sku'])}: {item['quantity']}")
            
            if t['status'] == 'SHIPPED':
                if st.button("Xác nhận Đã Nhận Hàng", key=f"receive_{t['id']}", use_container_width=True):
                    try:
                        inventory_manager.receive_transfer(t['id'], user_id)
                        st.success(f"Đã xác nhận nhận hàng từ phiếu `{t['id']}`.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận nhận hàng: {e}")
