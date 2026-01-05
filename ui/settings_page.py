
import streamlit as st
from managers.settings_manager import SettingsManager
from managers.auth_manager import AuthManager
from ui._utils import render_page_title

def render_settings_page(settings_mgr: SettingsManager, auth_mgr: AuthManager):
    render_page_title("Quản trị Hệ thống")

    user_info = auth_mgr.get_current_user_info()
    if not user_info or user_info.get('role', '').lower() != 'admin':
        st.error("Truy cập bị từ chối. Chức năng này chỉ dành cho Quản trị viên.")
        return

    current_settings = settings_mgr.get_settings()
    branch_mgr = st.session_state.branch_mgr

    # ===================================
    # EXPANDER 1: QUẢN LÝ CHI NHÁNH
    # ===================================
    with st.expander("🏢 Quản lý Chi nhánh"):
        with st.form("add_branch_form", clear_on_submit=True):
            st.subheader("Thêm chi nhánh mới")
            c1, c2 = st.columns(2)
            branch_name = c1.text_input("Tên chi nhánh")
            branch_address = c2.text_input("Địa chỉ")
            if st.form_submit_button("Thêm chi nhánh", type="primary", use_container_width=True):
                if branch_name:
                    try:
                        branch_mgr.create_branch(branch_name, branch_address)
                        st.success(f"Đã thêm chi nhánh '{branch_name}'")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                else:
                    st.warning("Tên chi nhánh không được để trống.")

        st.divider()

        st.subheader("Các chi nhánh hiện có")
        branches = branch_mgr.list_branches(active_only=False)
        if not branches:
            st.info("Chưa có chi nhánh nào được tạo.")
        else:
            for branch in branches:
                with st.container(border=True):
                    b_c1, b_c2 = st.columns([0.8, 0.2])
                    with b_c1:
                        st.markdown(f"**{branch['name']}**")
                        st.markdown(f"*Địa chỉ: {branch.get('address', 'Chưa có')}*")
                    with b_c2:
                        if st.button("Xóa", key=f"del_{branch['id']}", use_container_width=True):
                            st.session_state[f'confirm_delete_{branch['id']}'] = True

                if st.session_state.get(f'confirm_delete_{branch['id']}'):
                    st.warning(f"Bạn có chắc muốn xóa chi nhánh '{branch['name']}'? Hành động này không thể hoàn tác.")
                    cd_c1, cd_c2 = st.columns(2)
                    if cd_c1.button("Xác nhận Xóa", key=f"confirm_btn_{branch['id']}", type="primary", use_container_width=True):
                        try:
                            branch_mgr.delete_branch(branch['id'])
                            st.success("Đã xóa thành công!")
                            del st.session_state[f'confirm_delete_{branch['id']}']
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi xóa: {e}")
                    if cd_c2.button("Hủy", key=f"cancel_btn_{branch['id']}", use_container_width=True):
                        del st.session_state[f'confirm_delete_{branch['id']}']
                        st.rerun()

    # ===================================
    # EXPANDER 2: THÔNG TIN KINH DOANH
    # ===================================
    with st.expander("📄 Thông tin Kinh doanh"):
        business_info = current_settings.get('business_info', {})
        with st.form("business_info_form"):
            name = st.text_input("Tên doanh nghiệp", value=business_info.get('name', ''))
            tax_code = st.text_input("Mã số thuế", value=business_info.get('tax_code', ''))
            phone = st.text_input("Số điện thoại", value=business_info.get('phone', ''))
            address = st.text_area("Địa chỉ đăng ký kinh doanh", value=business_info.get('address', ''))

            if st.form_submit_button("Lưu thông tin", type="primary", use_container_width=True):
                current_settings['business_info'] = {
                    'name': name,
                    'tax_code': tax_code,
                    'phone': phone,
                    'address': address
                }
                settings_mgr.save_settings(current_settings)
                st.success("Đã cập nhật thông tin doanh nghiệp.")

    # ===================================
    # EXPANDER 3: BẢO MẬT
    # ===================================
    with st.expander("🔒 Cài đặt Bảo mật & Phiên đăng nhập"):
        persistence_days = current_settings.get('session_persistence_days', 0)
        with st.form("session_settings_form"):
            new_persistence_days = st.number_input(
                "Thời gian ghi nhớ đăng nhập (số ngày)",
                min_value=0, max_value=365,
                value=persistence_days, step=1,
                help="Đặt số ngày hệ thống ghi nhớ đăng nhập. Đặt là 0 để yêu cầu đăng nhập mỗi khi tắt trình duyệt."
            )
            if st.form_submit_button("Lưu Cài đặt Phiên", type="primary", use_container_width=True):
                current_settings['session_persistence_days'] = new_persistence_days
                settings_mgr.save_settings(current_settings)
                st.success(f"Đã lưu cài đặt. Thời gian ghi nhớ đăng nhập là {new_persistence_days} ngày.")
                st.rerun()
