import streamlit as st
import pandas as pd
from managers.admin_manager import AdminManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_title, render_section_header

def render_admin_page(admin_mgr: AdminManager, auth_mgr: AuthManager):
    render_page_title("👨‍💻 Khu vực Quản trị")

    # --- Initialize Session State (Refactored for Transactions) ---
    if "confirm_delete_inventory" not in st.session_state:
        st.session_state.confirm_delete_inventory = False
    if "transaction_to_delete" not in st.session_state:
        st.session_state.transaction_to_delete = None
    if "delete_result" not in st.session_state:
        st.session_state.delete_result = None

    # --- Security Check ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role') != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        st.stop()

    st.warning("**CẢNH BÁO:** Các hành động trong trang này có thể gây mất dữ liệu vĩnh viễn và không thể hoàn tác. Hãy thật cẩn trọng.")
    
    tab1, tab2 = st.tabs(["Xóa Giao Dịch Bán Hàng Lỗi", "Dọn Dẹp Dữ Liệu Kho"]) # MODIFIED: Tab title

    with tab1:
        render_transaction_deletion_tab(admin_mgr, user_info['uid']) # MODIFIED: Function call
    
    with tab2:
        render_inventory_cleanup_tab(admin_mgr)

def render_transaction_deletion_tab(admin_mgr, current_user_id):
    render_section_header("❌ Xóa Giao Dịch SALE và Hoàn Trả Tồn Kho") # MODIFIED: Header

    if st.session_state.delete_result:
        success, message = st.session_state.delete_result
        if success:
            st.success(message)
        else:
            st.error(message)
        if st.button("OK"):
            st.session_state.delete_result = None
            st.rerun()
        return 

    st.markdown("Chức năng này cho phép bạn xóa một giao dịch **bán hàng (SALE)** cụ thể. Hệ thống sẽ **tự động cộng trả lại số lượng tồn kho** tương ứng. Hành động này không thể hoàn tác.") # MODIFIED: Text

    with st.spinner("Đang tải danh sách giao dịch..."):
        transactions = admin_mgr.get_all_transactions() # MODIFIED: Function call
    
    if not transactions:
        st.info("Hiện không có giao dịch nào trong hệ thống.") # MODIFIED: Text
        return

    # Filter for SALE transactions only, as they are the only ones revertible
    sale_transactions = [t for t in transactions if t.get('type') == 'SALE']
    if not sale_transactions:
        st.info("Hiện không có giao dịch bán hàng (SALE) nào để xóa.")
        return

    df = pd.DataFrame(sale_transactions)
    # MODIFIED: Display columns relevant to transactions
    df_display = df[['id', 'created_at', 'branch_id', 'total_amount', 'total_cogs']].copy()
    df_display['created_at'] = df_display['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    df_display['total_amount'] = df_display['total_amount'].apply(lambda x: f"{x:,.0f}đ")

    st.write("**Danh sách các giao dịch bán hàng:**") # MODIFIED: Text
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.divider()

    if not st.session_state.transaction_to_delete:
        transaction_ids = [t['id'] for t in sale_transactions] # MODIFIED: Variable name
        selected_transaction_id = st.selectbox("Chọn Giao Dịch Cần Xóa:", options=[""] + transaction_ids) # MODIFIED: Text & var
        if selected_transaction_id and st.button("Xóa Giao Dịch Được Chọn...", type="primary"):
            st.session_state.transaction_to_delete = selected_transaction_id # MODIFIED: State var
            st.rerun()

    if st.session_state.transaction_to_delete:
        st.error(f"Bạn có chắc chắn muốn xóa vĩnh viễn giao dịch **{st.session_state.transaction_to_delete}** và hoàn trả tồn kho không?")
        
        col1, col2, _ = st.columns([2, 2, 8])
        if col1.button("CÓ, TÔI CHẮC CHẮN", type="secondary"):
            with st.spinner("Đang xử lý..."):
                # MODIFIED: Call the new manager function
                success, message = admin_mgr.delete_transaction_and_revert_stock(st.session_state.transaction_to_delete, current_user_id)
                st.session_state.delete_result = (success, message)
                if success:
                    st.cache_data.clear()
            st.session_state.transaction_to_delete = None # MODIFIED: State var
            st.rerun()

        if col2.button("HỦY BỎ"):
            st.session_state.transaction_to_delete = None # MODIFIED: State var
            st.rerun()

def render_inventory_cleanup_tab(admin_mgr):
    # This function does not interact with orders/transactions, so it remains unchanged.
    render_section_header("🗑️ Dọn dẹp toàn bộ Dữ liệu Kho")
    st.markdown("Chức năng này sẽ xoá **TOÀN BỘ** dữ liệu trong các collection sau: `inventory`, `inventory_vouchers`, và `inventory_transactions`. Dữ liệu này sẽ bị xoá vĩnh viễn.")

    if "operation_result" not in st.session_state:
        st.session_state.operation_result = None
    if "show_result" not in st.session_state:
        st.session_state.show_result = False

    if st.button("Xóa Tất Cả Dữ Liệu Kho...", type="secondary"):
        st.session_state.confirm_delete_inventory = True
        st.session_state.operation_result = None
        st.session_state.show_result = False

    if st.session_state.confirm_delete_inventory:
        st.error("HÀNH ĐỘNG NGUY HIỂM: Bạn có chắc chắn muốn xóa không?")
        
        col1, col2, _ = st.columns([2, 2, 8])
        
        if col1.button("CÓ, TÔI CHẮC CHẮN MUỐN XOÁ", type="secondary"):
            with st.spinner("Đang xử lý... Quá trình này có thể mất vài phút."):
                result = admin_mgr.clear_inventory_data()
                st.session_state.operation_ và `inventory_transactions`.")

    if "operation_result" not in st.session_state:
        st.session_state.operation_result = None
    if "show_result" not in st.session_state:
        st.session_state.show_result = False

    if st.button("Xóa Tất Cả Dữ Liệu Kho...", type="secondary"):
        st.session_state.confirm_delete_inventory = True
        st.session_state.operation_result = None
        st.session_state.show_result = False

    if st.session_state.confirm_delete_inventory:
        st.error("HÀNH ĐỘNG NGUY HIỂM: Bạn có chắc chắn muốn xóa không?")
        
        col1, col2, _ = st.columns([2, 2, 8])
        
        if col1.button("CÓ, TÔI CHẮC CHẮN MUỐN XOÁ", type="secondary"):
            with st.spinner("Đang xử lý... Quá trình này có thể mất vài phút."):
                result = admin_mgr.clear_inventory_data()
                st.session_state.operation_result = result
                st.session_state.show_result = True
                st.cache_data.clear() 
            st.session_state.confirm_delete_inventory = False
            st.rerun()

        if col2.button("KHÔNG, HỦY BỎ"):
            st.session_state.confirm_delete_inventory = False
            st.rerun()

    if st.session_state.show_result and st.session_state.operation_result:
        result = st.session_state.operation_result
        if "error" in result:
            st.error(f"Lỗi: {result['error']}")
        else:
            st.success("Hoàn tất! Dữ liệu kho đã được dọn dẹp.")
            st.write("**Kết quả:**")
            for coll, count in result.items():
                st.markdown(f"- **{coll}:** Đã xóa {count} tài liệu.")
        if st.button("OK"):
            st.session_state.show_result = False
            st.session_state.operation_result = None
            st.rerun()
