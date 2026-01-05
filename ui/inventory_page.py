
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
    # Tối ưu: Cache dữ liệu tổng hợp trong 2 phút, giảm tải cho DB
    @st.cache_data(ttl=120)
    def load_data(branch_id):
        branch_inventory_data = inv_mgr.get_inventory_by_branch(branch_id)
        all_products_data = prod_mgr.get_all_products(active_only=False) # Lấy tất cả sản phẩm
        return branch_inventory_data, all_products_data

    with st.spinner("Đang tải dữ liệu kho..."):
        branch_inventory, all_products = load_data(selected_branch)
        product_map = {p['sku']: p for p in all_products if 'sku' in p}

    # --- 4. TABS STRUCTURE (CẬP NHẬT: Thêm tab Điều chỉnh kho) ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Tình hình Tồn kho", 
        "📥 Nhập hàng", 
        "✍️ Điều chỉnh Kho", # TAB MỚI
        "📜 Lịch sử Thay đổi"
    ])

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
                
                # Tối ưu: Lấy ngưỡng tồn kho từ dữ liệu sản phẩm, nếu không có thì mặc định là 10
                default_threshold = prod_info.get('low_stock_threshold', 10)
                threshold = inv_data.get('low_stock_threshold', default_threshold)
                
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
    # TAB 2: RECEIVE STOCK (NHẬP HÀNG)
    # =========================================================
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
                cost_price = c2.number_input("Giá nhập (trên 1 đơn vị)", min_value=0, step=1000, key="receive_cost")

                supplier = st.text_input("Nhà cung cấp (tùy chọn)", key="receive_supplier")
                notes = st.text_area("Ghi chú (ví dụ: mã PO, số hóa đơn...)", key="receive_notes")

                submitted = st.form_submit_button("Xác nhận Nhập hàng", use_container_width=True)

            if submitted:
                with st.spinner("Đang xử lý nghiệp vụ nhập hàng..."):
                    try:
                        # Tính toán số lượng mới
                        current_quantity = inv_mgr.get_stock_quantity(selected_sku, selected_branch)
                        new_quantity = current_quantity + quantity
                        
                        # Chuẩn bị ghi chú
                        full_notes = f"Nhà cung cấp: {supplier}. Ghi chú: {notes}."
                        if cost_price > 0:
                            total_cost = cost_price * quantity
                            full_notes += f" Tổng giá nhập: {format_currency(total_cost, 'VND')} ({format_currency(cost_price, 'VND')}/đv)."

                        # Gọi hàm điều chỉnh kho
                        inv_mgr.adjust_stock(
                            sku=selected_sku,
                            branch_id=selected_branch,
                            new_quantity=new_quantity,
                            user_id=user_info['uid'],
                            reason="Nhập hàng",
                            notes=full_notes
                        )
                        st.success(f"Nhập hàng thành công cho sản phẩm {product_options[selected_sku]}.")
                        st.cache_data.clear() # Xóa cache để cập nhật giao diện
                        st.rerun()
                    except Exception as e:
                        st.error(f"Đã xảy ra lỗi khi nhập hàng: {e}")

    # =========================================================
    # TAB 3: STOCK ADJUSTMENT (ĐIỀU CHỈNH KHO) - MỚI
    # =========================================================
    with tab3:
        st.subheader("Tạo Phiếu Điều chỉnh Kho")
        st.markdown("Dùng cho các trường hợp kiểm kê, hàng hỏng, mất mát...")

        if not product_options:
            st.warning("Chưa có sản phẩm nào được tạo. Vui lòng tạo sản phẩm trước.")
        else:
            with st.form("adjustment_form", clear_on_submit=True):
                adj_sku = st.selectbox("Chọn sản phẩm để điều chỉnh", options=list(product_options.keys()), format_func=lambda x: product_options[x], key="adj_sku")
                
                # Hiển thị số lượng tồn hiện tại để người dùng tham khảo
                current_stock = inv_mgr.get_stock_quantity(adj_sku, selected_branch)
                st.info(f"Tồn kho hiện tại của sản phẩm này là: **{format_number(current_stock)}**")
                
                actual_quantity = st.number_input("Nhập số lượng thực tế sau điều chỉnh", min_value=0, step=1, key="adj_actual_qty")
                
                adjustment_reason = st.selectbox(
                    "Lý do điều chỉnh",
                    ("Kiểm kê định kỳ", "Hàng hỏng", "Mất mát", "Khác"),
                    key="adj_reason"
                )
                
                adjustment_notes = st.text_area("Ghi chú chi tiết cho lần điều chỉnh", key="adj_notes")

                adj_submitted = st.form_submit_button("Xác nhận Điều chỉnh", use_container_width=True)

            if adj_submitted:
                if actual_quantity == current_stock:
                    st.warning("Số lượng thực tế bằng với tồn kho hiện tại. Không có gì thay đổi.")
                else:
                    with st.spinner("Đang thực hiện điều chỉnh kho..."):
                        try:
                            # Ghi nhận điều chỉnh
                            inv_mgr.adjust_stock(
                                sku=adj_sku,
                                branch_id=selected_branch,
                                new_quantity=actual_quantity,
                                user_id=user_info['uid'],
                                reason=adjustment_reason,
                                notes=adjustment_notes
                            )
                            st.success(f"Điều chỉnh kho thành công cho sản phẩm {product_options[adj_sku]}.")
                            st.cache_data.clear() # Xóa cache để cập nhật giao diện
                            st.rerun()
                        except Exception as e:
                            st.error(f"Đã xảy ra lỗi khi điều chỉnh kho: {e}")

    # =========================================================
    # TAB 4: ADJUSTMENT HISTORY (LỊCH SỬ THAY ĐỔI)
    # =========================================================
    with tab4:
        st.subheader("Lịch sử Thay đổi Kho")
        
        # Tối ưu: Cache lịch sử trong 1 phút
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
            
            # Chuyển đổi timestamp an toàn hơn
            try:
                history_df['Thời gian'] = pd.to_datetime(history_df['timestamp']).dt.tz_convert('Asia/Ho_Chi_Minh').dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                history_df['Thời gian'] = pd.to_datetime(history_df['timestamp']).dt.strftime('%d/%m/%Y %H:%M')


            history_df.rename(columns={
                'delta': 'Thay đổi',
                'quantity_before': 'Tồn trước',
                'quantity_after': 'Tồn sau',
                'reason': 'Lý do',
                'notes': 'Ghi chú'
            }, inplace=True)
            
            display_columns = ['Thời gian', 'Sản phẩm', 'Thay đổi', 'Tồn trước', 'Tồn sau', 'Lý do', 'Ghi chú']
            
            # Hiển thị tất cả các dòng, không cắt bớt
            st.dataframe(
                history_df[display_columns].style.format({
                    'Thay đổi': format_number,
                    'Tồn trước': format_number,
                    'Tồn sau': format_number
                }),
                use_container_width=True, 
                hide_index=True,
                height=(len(history_df) + 1) * 35 
            )
