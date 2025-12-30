
import streamlit as st
from datetime import datetime

def show_stock_transfer_page(branch_manager, inventory_manager, product_manager, auth_manager):
    st.title("Luân chuyển hàng hóa")

    # Lấy thông tin người dùng và chi nhánh
    user_info = auth_manager.get_user_info()
    if not user_info:
        st.warning("Vui lòng đăng nhập để sử dụng tính năng này.")
        return

    user_id = user_info['uid']
    # Giả định người dùng chỉ thuộc về 1 chi nhánh chính, cần điều chỉnh nếu 1 user có thể làm việc ở nhiều chi nhánh
    assigned_branch_id = user_info.get('branch_id') 
    if not assigned_branch_id:
        st.error("Tài khoản của bạn chưa được gán vào chi nhánh nào.")
        return
        
    all_branches = branch_manager.get_all_branches()
    current_branch_name = next((branch['name'] for branch in all_branches if branch['id'] == assigned_branch_id), "N/A")

    st.markdown(f"**Chi nhánh của bạn:** `{current_branch_name}` (`{assigned_branch_id}`)")

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs([
        "Tạo Phiếu Luân Chuyển Mới", 
        "Danh sách Phiếu Chuyển Đi", 
        "Danh sách Phiếu Chuyển Đến"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: TẠO PHIẾU MỚI
    # --------------------------------------------------------------------------
    with tab1:
        render_create_transfer_form(assigned_branch_id, all_branches, inventory_manager, product_manager, user_id)

    # --------------------------------------------------------------------------
    # TAB 2: DANH SÁCH PHIẾU GỬI ĐI TỪ CHI NHÁNH HIỆN TẠI
    # --------------------------------------------------------------------------
    with tab2:
        render_outgoing_transfers(assigned_branch_id, all_branches, inventory_manager, user_id)
        
    # --------------------------------------------------------------------------
    # TAB 3: DANH SÁCH PHIẾU GỬI ĐẾN CHI NHÁNH HIỆN TẠI
    # --------------------------------------------------------------------------
    with tab3:
        render_incoming_transfers(assigned_branch_id, all_branches, inventory_manager, user_id)

def render_create_transfer_form(from_branch_id, all_branches, inventory_manager, product_manager, user_id):
    st.header("Tạo Phiếu Luân Chuyển")
    
    # Lấy danh mục sản phẩm và tồn kho hiện tại
    products = product_manager.get_all_products()
    inventory = inventory_manager.get_inventory_by_branch(from_branch_id)

    with st.form("create_transfer_form"):
        # Lọc ra các chi nhánh khác để chọn làm điểm đến
        other_branches = [b for b in all_branches if b['id'] != from_branch_id]
        to_branch_id = st.selectbox(
            "Chọn chi nhánh nhận hàng", 
            options=[b['id'] for b in other_branches],
            format_func=lambda bid: f"{next(b['name'] for b in other_branches if b['id'] == bid)} ({bid})"
        )
        
        st.subheader("Danh sách sản phẩm cần chuyển")
        
        # Sử dụng session state để quản lý danh sách sản phẩm động
        if 'transfer_items' not in st.session_state:
            st.session_state.transfer_items = []

        # Hiển thị các sản phẩm đã thêm
        for i, item in enumerate(st.session_state.transfer_items):
            cols = st.columns([4, 2, 1])
            cols[0].write(f"**{item['sku']}**")
            cols[1].write(f"Số lượng: {item['quantity']}")
            if cols[2].button(f"Xóa", key=f"del_{i}"):
                st.session_state.transfer_items.pop(i)
                st.experimental_rerun()
        
        st.markdown("---")
        
        # Form thêm sản phẩm mới
        cols = st.columns([3, 2, 1])
        product_options = {p['sku']: p for p in products}
        selected_sku = cols[0].selectbox("Chọn sản phẩm", options=list(product_options.keys()))
        
        current_stock = inventory.get(selected_sku, {}).get('stock_quantity', 0)
        
        quantity = cols[1].number_input("Số lượng", min_value=1, max_value=int(current_stock), step=1)
        cols[0].info(f"Tồn kho khả dụng: {current_stock}")

        if cols[2].button("Thêm vào phiếu"):
            if selected_sku and quantity > 0:
                # Kiểm tra xem sản phẩm đã có trong list chưa
                found = False
                for item in st.session_state.transfer_items:
                    if item['sku'] == selected_sku:
                        item['quantity'] += quantity
                        found = True
                        break
                if not found:
                    st.session_state.transfer_items.append({'sku': selected_sku, 'quantity': quantity})
                st.experimental_rerun()

        notes = st.text_area("Ghi chú (nếu có)")
        submitted = st.form_submit_button("Tạo Phiếu Luân Chuyển")

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
                    st.session_state.transfer_items = [] # Xóa giỏ hàng
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Lỗi khi tạo phiếu: {e}")

def render_outgoing_transfers(branch_id, all_branches, inventory_manager, user_id):
    st.header("Phiếu Chuyển Đi")
    
    status_filter = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None, "PENDING", "SHIPPED", "COMPLETED"], 
        format_func=lambda x: "Tất cả" if x is None else x,
        key="out_status_filter"
    )

    transfers = inventory_manager.get_transfers(branch_id, direction='outgoing', status=status_filter)

    if not transfers:
        st.info("Không có phiếu luân chuyển nào được gửi đi từ chi nhánh này.")
        return

    for t in transfers:
        with st.expander(f"Phiếu `{t['id']}` gửi tới CN `{t['to_branch_id']}` - Trạng thái: **{t['status']}**"):
            st.write(f"**Ngày tạo:** {datetime.fromisoformat(t['created_at']).strftime('%Y-%m-%d %H:%M')}")
            st.write(f"**Ghi chú:** {t.get('notes', 'N/A')}")
            st.write("**Sản phẩm:**")
            for item in t['items']:
                st.write(f"- {item['sku']}: {item['quantity']}")
            
            if t['status'] == 'PENDING':
                if st.button("Xác nhận Gửi hàng", key=f"ship_{t['id']}"):
                    try:
                        inventory_manager.ship_transfer(t['id'], user_id)
                        st.success(f"Đã xác nhận gửi phiếu `{t['id']}`.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận gửi: {e}")

def render_incoming_transfers(branch_id, all_branches, inventory_manager, user_id):
    st.header("Phiếu Chuyển Đến")
    
    status_filter = st.selectbox(
        "Lọc theo trạng thái", 
        options=[None, "PENDING", "SHIPPED", "COMPLETED"],
        format_func=lambda x: "Tất cả" if x is None else x,
        key="in_status_filter"
    )

    transfers = inventory_manager.get_transfers(branch_id, direction='incoming', status=status_filter)

    if not transfers:
        st.info("Không có phiếu luân chuyển nào đang gửi đến chi nhánh này.")
        return

    for t in transfers:
        with st.expander(f"Phiếu `{t['id']}` từ CN `{t['from_branch_id']}` - Trạng thái: **{t['status']}**"):
            st.write(f"**Ngày gửi (dự kiến):** {datetime.fromisoformat(t.get('shipped_at', t['created_at'])).strftime('%Y-%m-%d %H:%M')}")
            st.write(f"**Ghi chú:** {t.get('notes', 'N/A')}")
            st.write("**Sản phẩm:**")
            for item in t['items']:
                st.write(f"- {item['sku']}: {item['quantity']}")
            
            if t['status'] == 'SHIPPED':
                if st.button("Xác nhận Đã Nhận Hàng", key=f"receive_{t['id']}"):
                    try:
                        inventory_manager.receive_transfer(t['id'], user_id)
                        st.success(f"Đã xác nhận nhận hàng từ phiếu `{t['id']}`.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xác nhận nhận hàng: {e}")

