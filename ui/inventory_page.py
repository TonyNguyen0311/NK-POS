
import streamlit as st
import pandas as pd

# Import managers
from managers.inventory_manager import InventoryManager
from managers.product_manager import ProductManager
from managers.branch_manager import BranchManager
from managers.auth_manager import AuthManager

# Import formatters and UI utils
from ui._utils import render_page_title, render_branch_selector
from utils.formatters import format_number, format_currency

def render_inventory_page(inv_mgr: InventoryManager, prod_mgr: ProductManager, branch_mgr: BranchManager, auth_mgr: AuthManager):
    render_page_title("Quản lý Tồn kho")

    user_info = auth_mgr.get_current_user_info()
    if not user_info: 
        st.error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."); return

    user_role = user_info.get('role', 'staff')
    user_branches = user_info.get('branch_ids', [])
    default_branch_id = user_info.get('default_branch_id')
    all_branches_map = {b['id']: b['name'] for b in branch_mgr.list_branches(active_only=False)}
    allowed_branches_map = {bid: all_branches_map[bid] for bid in user_branches if bid in all_branches_map} if user_role != 'admin' else all_branches_map

    selected_branch = render_branch_selector(allowed_branches_map, default_branch_id)
    if not selected_branch: return
    
    st.divider()

    @st.cache_data(ttl=120)
    def load_data(branch_id):
        branch_inventory_data = inv_mgr.get_inventory_by_branch(branch_id)
        all_products_data = prod_mgr.get_all_products(active_only=False)
        return branch_inventory_data, all_products_data

    with st.spinner("Đang tải dữ liệu kho..."):
        branch_inventory, all_products = load_data(selected_branch)
        product_map = {p['sku']: p for p in all_products if 'sku' in p}

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Tình hình Tồn kho", "📥 Nhập hàng", "✍️ Điều chỉnh Kho", "📜 Lịch sử Giao dịch"
    ])

    # --- TAB 1: CURRENT INVENTORY STATUS ---
    with tab1:
        st.subheader(f"Tồn kho hiện tại của: {allowed_branches_map[selected_branch]}")
        if not branch_inventory:
            st.info("Chưa có sản phẩm nào trong kho của chi nhánh này.")
        else:
            inventory_list = []
            for sku, inv_data in branch_inventory.items():
                prod_info = product_map.get(sku, {})
                inventory_list.append({
                    'Tên sản phẩm': prod_info.get('name', f'Không rõ (SKU: {sku})'),
                    'SKU': sku,
                    'Số lượng': inv_data.get('stock_quantity', 0),
                    'Giá vốn BQ': inv_data.get('average_cost', 0), # NEW: Show average cost
                    'Giá trị Kho': inv_data.get('stock_quantity', 0) * inv_data.get('average_cost', 0)
                })
            
            if inventory_list:
                inventory_df = pd.DataFrame(inventory_list)
                st.dataframe(
                    inventory_df.style.format({
                        'Số lượng': format_number,
                        'Giá vốn BQ': lambda x: format_currency(x, 'VND'),
                        'Giá trị Kho': lambda x: format_currency(x, 'VND')
                    }),
                    use_container_width=True, hide_index=True
                )
            else:
                 st.info("Chưa có sản phẩm nào trong kho của chi nhánh này.")

    # --- TAB 2: RECEIVE STOCK (NHẬP HÀNG) ---
    with tab2:
        st.subheader("Tạo Phiếu Nhập hàng")
        product_options = {p['sku']: f"{p['name']} ({p['sku']})" for p in all_products if 'sku' in p}
        
        if not product_options:
            st.warning("Chưa có sản phẩm nào được tạo. Vui lòng tạo sản phẩm trước.")
        else:
            with st.form("receive_stock_form", clear_on_submit=True):
                selected_sku = st.selectbox("Chọn sản phẩm", options=list(product_options.keys()), format_func=lambda x: product_options[x], key="receive_sku")
                c1, c2 = st.columns(2)
                quantity = c1.number_input("Số lượng nhập", min_value=1, step=1, key="receive_qty")
                purchase_price = c2.number_input("Giá nhập (trên 1 đơn vị)", min_value=0, step=1000, key="receive_cost")
                supplier = st.text_input("Nhà cung cấp (tùy chọn)", key="receive_supplier")
                notes = st.text_area("Ghi chú (ví dụ: mã PO, số hóa đơn...)", key="receive_notes")
                submitted = st.form_submit_button("Xác nhận Nhập hàng", use_container_width=True)

            if submitted:
                if purchase_price <= 0:
                    st.error("Giá nhập phải lớn hơn 0 để đảm bảo tính giá vốn chính xác.")
                else:
                    with st.spinner("Đang xử lý nghiệp vụ nhập hàng..."):
                        try:
                            inv_mgr.receive_stock(
                                sku=selected_sku,
                                branch_id=selected_branch,
                                quantity=quantity,
                                purchase_price=purchase_price,
                                user_id=user_info['uid'],
                                supplier=supplier,
                                notes=notes
                            )
                            st.success(f"Nhập hàng thành công cho sản phẩm {product_options[selected_sku]}.")
                            st.cache_data.clear() 
                            st.rerun()
                        except Exception as e:
                            st.error(f"Đã xảy ra lỗi khi nhập hàng: {e}")

    # --- TAB 3: STOCK ADJUSTMENT ---
    with tab3:
        st.subheader("Tạo Phiếu Điều chỉnh Kho")
        # ... (This logic remains the same as it now correctly uses adjust_stock)
        with st.form("adjustment_form", clear_on_submit=True):
            adj_sku = st.selectbox("Chọn sản phẩm để điều chỉnh", options=list(product_options.keys()), format_func=lambda x: product_options[x], key="adj_sku")
            current_stock = inv_mgr.get_stock_quantity(adj_sku, selected_branch)
            st.info(f"Tồn kho hiện tại: **{format_number(current_stock)}**")
            actual_quantity = st.number_input("Nhập số lượng thực tế sau điều chỉnh", min_value=0, step=1, key="adj_actual_qty")
            adjustment_reason = st.selectbox("Lý do điều chỉnh", ("Kiểm kê định kỳ", "Hàng hỏng", "Mất mát", "Khác"), key="adj_reason")
            adjustment_notes = st.text_area("Ghi chú chi tiết", key="adj_notes")
            adj_submitted = st.form_submit_button("Xác nhận Điều chỉnh", use_container_width=True)

        if adj_submitted and actual_quantity != current_stock:
            with st.spinner("Đang thực hiện điều chỉnh kho..."):
                try:
                    inv_mgr.adjust_stock(sku=adj_sku, branch_id=selected_branch, new_quantity=actual_quantity, user_id=user_info['uid'], reason=adjustment_reason, notes=adjustment_notes)
                    st.success(f"Điều chỉnh kho thành công cho {product_options[adj_sku]}.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi điều chỉnh kho: {e}")

    # --- TAB 4: TRANSACTION HISTORY (Lịch sử Giao dịch) ---
    with tab4:
        st.subheader("Lịch sử Giao dịch Kho")
        @st.cache_data(ttl=60)
        def load_transactions(branch_id):
            return inv_mgr.get_inventory_transactions(branch_id=branch_id, limit=200)

        with st.spinner("Đang tải lịch sử giao dịch..."):
            transactions = load_transactions(selected_branch)

        if not transactions:
            st.info("Chưa có giao dịch nào cho chi nhánh này.")
        else:
            df = pd.DataFrame(transactions)
            df['Sản phẩm'] = df['sku'].map(lambda s: product_map.get(s, {}).get('name', s))
            try:
                df['Thời gian'] = pd.to_datetime(df['timestamp']).dt.tz_convert('Asia/Ho_Chi_Minh').dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                df['Thời gian'] = pd.to_datetime(df['timestamp']).dt.strftime('%d/%m/%Y %H:%M')

            df.rename(columns={
                'reason': 'Loại Giao dịch', 'delta': 'Thay đổi', 'quantity_before': 'Tồn trước', 'quantity_after': 'Tồn sau',
                'purchase_price': 'Giá nhập', 'cost_at_transaction': 'Giá vốn tại GD', 'notes': 'Ghi chú'
            }, inplace=True)
            
            display_cols = ['Thời gian', 'Sản phẩm', 'Loại Giao dịch', 'Thay đổi', 'Tồn sau', 'Giá nhập', 'Giá vốn tại GD', 'Ghi chú']
            
            st.dataframe(
                df[display_cols].style.format({
                    'Thay đổi': format_number, 'Tồn sau': format_number, 
                    'Giá nhập': lambda x: format_currency(x, 'VND') if pd.notna(x) else '-',
                    'Giá vốn tại GD': lambda x: format_currency(x, 'VND') if pd.notna(x) else '-'
                }),
                use_container_width=True, hide_index=True
            )
