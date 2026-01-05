
import streamlit as st
import pandas as pd

# Import managers
from managers.inventory_manager import InventoryManager
from managers.product_manager import ProductManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

# Import formatters and UI utils
from ui._utils import render_page_header, render_branch_selector
from utils.formatters import format_number, format_currency

def render_inventory_page(inv_mgr: InventoryManager, prod_mgr: ProductManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    render_page_header("Quản lý Tồn kho", "📦")

    # --- 1. GET USER INFO & PERMISSIONS ---
    user_info = auth_mgr.get_current_user_info()
    if not user_info:
        st.error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
        return

    user_role = user_info.get('role', 'staff')
    user_branches = user_info.get('branch_ids', [])
    default_branch_id = user_info.get('default_branch_id')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}

    if user_role == 'admin':
        allowed_branches_map = all_branches_map
    else:
        allowed_branches_map = {bid: all_branches_map[bid] for bid in user_branches if bid in all_branches_map}

    # --- 2. BRANCH SELECTOR ---
    selected_branch = render_branch_selector(allowed_branches_map, default_branch_id)
    if not selected_branch:
        return
    
    st.divider()

    # --- 3. LOAD DATA ONCE --- 
    @st.cache_data(ttl=120)
    def load_data(branch_id):
        branch_inventory_data = inv_mgr.get_inventory_by_branch(branch_id)
        all_products_data = prod_mgr.get_all_products()
        return branch_inventory_data, all_products_data

    with st.spinner("Đang tải dữ liệu kho..."):
        branch_inventory, all_products = load_data(selected_branch)
        product_map = {p['sku']: p for p in all_products if 'sku' in p}

    # --- 4. TABS STRUCTURE ---
    tab1, tab2, tab3 = st.tabs(["📊 Tình hình Tồn kho", "📥 Nhập hàng", "📜 Lịch sử Thay đổi"])

    # =========================================================
    # TAB 1: CURRENT INVENTORY STATUS
    # =========================================================
    with tab1:
        st.subheader(f"Tồn kho hiện tại của: {allowed_branches_map[selected_branch]}")

        if not branch_inventory:
            st.info("Chưa có sản phẩm nào trong kho của chi nhánh này.")
        else:
            inventory_list = []
            for sku, inv_data in branch_inventory.items():
                prod_info = product_map.get(sku, {})
                quantity = inv_data.get('stock_quantity', 0)
                threshold = inv_data.get('low_stock_threshold', 10)
                
                if quantity <= 0:
                    status = "Hết hàng"
                elif quantity < threshold:
                    status = "Sắp hết"
                else:
                    status = "Còn hàng"

                inventory_list.append({
                    'Tên sản phẩm': prod_info.get('name', f'Không rõ (SKU: {sku})'),
                    'SKU': sku,
                    'Số lượng': quantity,
                    'Ngưỡng báo hết': threshold,
                    'Trạng thái': status
                })
            
            if inventory_list:
                inventory_df = pd.DataFrame(inventory_list)

                def highlight_status(row):
                    if row['Trạng thái'] == 'Hết hàng':
                        return ['background-color: #ffcdd2'] * len(row)
                    elif row['Trạng thái'] == 'Sắp hết':
                        return ['background-color: #fff9c4'] * len(row)
                    return [''] * len(row)

                st.dataframe(
                    inventory_df.style.apply(highlight_status, axis=1).format({
                        'Số lượng': format_number,
                        'Ngưỡng báo hết': format_number
                    }),
                    use_container_width=True, 
                    hide_index=True
                )
            else:
                 st.info("Chưa có sản phẩm nào trong kho của chi nhánh này.")

    # =========================================================
    # TAB 2: RECEIVE STOCK
    # =========================================================
    with tab2:
        st.subheader("Tạo Phiếu Nhập hàng")
        
        with st.form("receive_stock_form", clear_on_submit=True):
            product_options = {p['sku']: f"{p['name']} ({p['sku']})" for p in all_products if 'sku' in p}
            selected_sku = st.selectbox("Chọn sản phẩm", options=list(product_options.keys()), format_func=lambda x: product_options[x])
            
            c1, c2 = st.columns(2)
            quantity = c1.number_input("Số lượng nhập", min_value=1, step=1)
            cost_price = c2.number_input("Giá nhập (trên 1 đơn vị)", min_value=0, step=1000)

            supplier = st.text_input("Nhà cung cấp (tùy chọn)")
            notes = st.text_area("Ghi chú (ví dụ: mã PO, số hóa đơn...)")

            submitted = st.form_submit_button("Xác nhận Nhập hàng", use_container_width=True)

        if submitted:
            if not selected_sku:
                st.warning("Vui lòng chọn một sản phẩm.")
            else:
                with st.spinner("Đang xử lý nghiệp vụ nhập hàng..."):
                    try:
                        inv_mgr.receive_stock(
                            sku=selected_sku,
                            branch_id=selected_branch,
                            quantity=quantity,
                            user_id=user_info['uid'],
                            cost_price=cost_price,
                            supplier=supplier,
                            notes=notes
                        )
                        st.success(f"Nhập hàng thành công cho sản phẩm {product_options[selected_sku]}.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Đã xảy ra lỗi khi nhập hàng: {e}")

    # =========================================================
    # TAB 3: ADJUSTMENT HISTORY
    # =========================================================
    with tab3:
        st.subheader("Lịch sử Thay đổi Kho")
        
        @st.cache_data(ttl=60)
        def load_history(branch_id):
            return inv_mgr.get_inventory_adjustments_history(branch_id=branch_id, limit=200)

        with st.spinner("Đang tải lịch sử..."):
            history = load_history(selected_branch)

        if not history:
            st.info("Chưa có lịch sử thay đổi nào cho chi nhánh này.")
        else:
            history_df = pd.DataFrame(history)
            history_df['Sản phẩm'] = history_df['sku'].map(lambda s: product_map.get(s, {}).get('name', s))
            history_df['Thời gian'] = pd.to_datetime(history_df['timestamp']).dt.strftime('%d/%m/%Y %H:%M')
            history_df.rename(columns={
                'delta': 'Thay đổi',
                'quantity_before': 'Tồn trước',
                'quantity_after': 'Tồn sau',
                'reason': 'Lý do',
                'notes': 'Ghi chú'
            }, inplace=True)
            
            display_columns = ['Thời gian', 'Sản phẩm', 'Thay đổi', 'Tồn trước', 'Tồn sau', 'Lý do', 'Ghi chú']
            
            st.dataframe(
                history_df[display_columns].style.format({
                    'Thay đổi': format_number,
                    'Tồn trước': format_number,
                    'Tồn sau': format_number
                }),
                use_container_width=True, 
                hide_index=True
            )
