# ui/stock_transfer_page.py

import streamlit as st

# Import the render functions from their new modules
from ui._utils import render_page_title
from ui.transfer_create_tab import render_create_transfer_form
from ui.transfer_outgoing_tab import render_outgoing_transfers
from ui.transfer_incoming_tab import render_incoming_transfers

def show_stock_transfer_page(branch_manager, inventory_manager, product_manager, auth_manager):
    render_page_title("Luân chuyển hàng hóa")

    user_info = auth_manager.get_current_user_info()
    if not user_info:
        st.warning("Vui lòng đăng nhập để sử dụng tính năng này.")
        return

    user_id = user_info['uid']
    user_role = user_info.get('role', 'staff')
    
    # Fetch branch data once
    all_branches = branch_manager.list_branches()
    all_branches_map = {b['id']: b.get('name', b['id']) for b in all_branches}

    from_branch_id = None

    # --- Branch Selection Logic ---
    if user_role == 'admin':
        if not all_branches:
            st.warning("Chưa có chi nhánh nào được tạo.")
            return
        from_branch_id = st.selectbox(
            "Chọn chi nhánh thao tác (Admin)", 
            options=list(all_branches_map.keys()), 
            format_func=lambda k: all_branches_map.get(k, k)
        )
    else:
        user_branches = user_info.get('branch_ids', [])
        if not user_branches:
            st.error("Tài khoản của bạn chưa được gán vào chi nhánh nào.")
            return
        
        if len(user_branches) > 1:
            branch_options = {bid: all_branches_map.get(bid, bid) for bid in user_branches}
            from_branch_id = st.selectbox(
                "Chọn chi nhánh thao tác", 
                options=list(branch_options.keys()), 
                format_func=lambda k: branch_options.get(k, k)
            )
        else:
            from_branch_id = user_branches[0]

    if not from_branch_id:
        st.error("Không thể xác định chi nhánh thao tác.")
        return

    current_branch_name = all_branches_map.get(from_branch_id, "N/A")
    st.markdown(f"**Chi nhánh thao tác:** `{current_branch_name}` (`{from_branch_id}`)")

    # --- Tabs ---
    tab1, tab2, tab3 = st.tabs([
        "Tạo Phiếu Luân Chuyển Mới", 
        "Danh sách Phiếu Chuyển Đi", 
        "Danh sách Phiếu Chuyển Đến"
    ])

    with tab1:
        # Call the imported function
        render_create_transfer_form(from_branch_id, all_branches, inventory_manager, product_manager, user_id)

    with tab2:
        # Call the imported function
        render_outgoing_transfers(from_branch_id, all_branches_map, inventory_manager, user_id)
        
    with tab3:
        # Call the imported function
        render_incoming_transfers(from_branch_id, all_branches_map, inventory_manager, user_id)
