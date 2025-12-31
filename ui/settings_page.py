
import streamlit as st
from managers.settings_manager import SettingsManager
from managers.auth_manager import AuthManager

def render_settings_page(settings_mgr: SettingsManager, auth_mgr: AuthManager):
    st.title("⚙️ Quản trị Hệ thống")

    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role', '').lower() != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        return

    current_settings = settings_mgr.get_settings()

    # Cấu trúc tab để dễ dàng mở rộng trong tương lai
    tab1, tab2, tab3 = st.tabs(["Cài đặt Chung", "Thông tin Kinh doanh", "Bảo mật"])

    # ===================================
    # TAB 1: CÀI ĐẶT CHUNG (PREVIOUSLY BRANCHES)
    # ===================================
    with tab1:
        st.subheader("Quản lý Chi nhánh")
        branch_mgr = st.session_state.branch_mgr # Lấy manager từ session state

        # Form thêm chi nhánh mới
        with st.form("add_branch_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                branch_name = st.text_input("Tên chi nhánh")
            with c2:
                branch_address = st.text_input("Địa chỉ")
            if st.form_submit_button("Thêm chi nhánh", type="primary"):
                if branch_name:
                    try:
                        branch_mgr.create_branch(branch_name, branch_address)
                        st.success(f"Đã thêm chi nhánh '{branch_name}'")
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                else:
                    st.warning("Tên chi nhánh không được để trống.")

        st.divider()
        
        # Danh sách chi nhánh hiện có
        st.write("**Các chi nhánh hiện có:**")
        branches = branch_mgr.list_branches(active_only=False) # Lấy tất cả chi nhánh
        if not branches:
            st.info("Chưa có chi nhánh nào được tạo.")
        else:
            for branch in branches:
                with st.container(border=True):
                    b_c1, b_c2 = st.columns([0.8, 0.2])
                    with b_c1:
                        st.text_input("Tên", value=branch['name'], key=f"name_{branch['id']}", disabled=True)
                        st.text_input("Địa chỉ", value=branch.get('address', ''), key=f"addr_{branch['id']}", disabled=True)
                    with b_c2:
                        if st.button("Xóa", key=f"del_{branch['id']}", use_container_width=True):
                            st.session_state[f'confirm_delete_{branch['id']}'] = True
            
                if st.session_state.get(f'confirm_delete_{branch['id']}'):
                    st.warning(f"Bạn có chắc muốn xóa chi nhánh '{branch['name']}'? Hành động này không thể hoàn tác.")
                    cd_c1, cd_c2 = st.columns(2)
                    if cd_c1.button("Xác nhận Xóa", key=f"confirm_btn_{branch['id']}", type="primary"):
                        try:
                            branch_mgr.delete_branch(branch['id'])
                            st.success("Đã xóa thành công!")
                            del st.session_state[f'confirm_delete_{branch['id']}'] 
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi xóa: {e}")
                    if cd_c2.button("Hủy", key=f"cancel_btn_{branch['id']}"):
                        del st.session_state[f'confirm_delete_{branch['id']}']
                        st.rerun()

    # ===================================
    # TAB 2: THÔNG TIN KINH DOANH
    # ===================================
    with tab2:
        st.subheader("Thông tin Doanh nghiệp/Cửa hàng")
        business_info = current_settings.get('business_info', {})

        with st.form("business_info_form"):
            name = st.text_input("Tên doanh nghiệp", value=business_info.get('name', ''))
            tax_code = st.text_input("Mã số thuế", value=business_info.get('tax_code', ''))
            phone = st.text_input("Số điện thoại", value=business_info.get('phone', ''))
            address = st.text_area("Địa chỉ đăng ký kinh doanh", value=business_info.get('address', ''))

            if st.form_submit_button("Lưu thông tin", type="primary"):
                current_settings['business_info'] = {
                    'name': name,
                    'tax_code': tax_code,
                    'phone': phone,
                    'address': address
                }
                settings_mgr.save_settings(current_settings)
                st.success("Đã cập nhật thông tin doanh nghiệp.")

    # ===================================
    # TAB 3: BẢO MẬT (PREVIOUSLY CÀI ĐẶT KHÁC)
    # ===================================
    with tab3:
        st.subheader("Cài đặt Phiên đăng nhập")
        
        persistence_days = current_settings.get('session_persistence_days', 0)

        with st.form("session_settings_form"):
            new_persistence_days = st.number_input(
                "Thời gian ghi nhớ đăng nhập (số ngày)",
                min_value=0,
                max_value=365, # Giới hạn 1 năm để đảm bảo an toàn
                value=persistence_days,
                step=1,
                help="Đặt số ngày mà hệ thống sẽ ghi nhớ đăng nhập của người dùng trên trình duyệt. Đặt là 0 để yêu cầu đăng nhập mỗi khi trình duyệt tắt."
            )

            if st.form_submit_button("Lưu Cài đặt Phiên", type="primary"):
                current_settings['session_persistence_days'] = new_persistence_days
                settings_mgr.save_settings(current_settings)
                st.success(f"Đã lưu cài đặt. Thời gian ghi nhớ đăng nhập là {new_persistence_days} ngày.")
                st.rerun()

