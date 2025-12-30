
import streamlit as st

def render_cost_allocation_page(cost_mgr, branch_mgr, auth_mgr):
    st.header("Phân bổ Chi phí")
    st.info("Chức năng này cho phép phân bổ một khoản chi phí chung (như chi phí marketing, thuê văn phòng...) ra nhiều chi nhánh theo các quy tắc được định sẵn.")

    # Lấy thông tin user và các chi nhánh
    user_info = auth_mgr.get_current_user_info()
    user_id = user_info['uid']
    all_branches = branch_mgr.list_branches()
    # Giả sử trụ sở chính (Headquarter) có ID đặc biệt, ví dụ 'HQ'
    hq_branch_id = 'HQ' 

    tab1, tab2 = st.tabs(["Áp dụng Phân bổ Chi phí", "Quản lý Quy tắc Phân bổ"])

    with tab2:
        render_rules_management(cost_mgr, all_branches)

    with tab1:
        # Lấy danh sách chi phí từ Trụ sở chính (HQ) mà chưa được phân bổ
        filters = {
            'branch_id': hq_branch_id,
            'status': 'ACTIVE', # Chỉ lấy chi phí chưa được xử lý
            'source_entry_id_is_null': True # Chỉ lấy chi phí gốc
        }
        unallocated_costs = cost_mgr.query_cost_entries(filters)
        render_apply_allocation(cost_mgr, hq_branch_id, user_id, unallocated_costs)

def render_rules_management(cost_mgr, all_branches):
    st.subheader("Quản lý Quy tắc Phân bổ")

    if 'rule_splits' not in st.session_state:
        st.session_state.rule_splits = []

    with st.form("new_rule_form", clear_on_submit=True):
        st.write("**Tạo quy tắc mới**")
        rule_name = st.text_input("Tên quy tắc (ví dụ: Phân bổ chi phí Marketing Q4)")
        description = st.text_area("Mô tả")
        
        st.write("**Chi tiết phân bổ cho các chi nhánh:**")
        
        # Hiển thị các split đã thêm
        total_percentage = 0
        for i, split in enumerate(st.session_state.rule_splits):
            branch_name = next((b['name'] for b in all_branches if b['id'] == split['branch_id']), split['branch_id'])
            cols = st.columns([3, 2, 1])
            cols[0].write(f"- **{branch_name}**")
            cols[1].write(f"Tỷ lệ: {split['percentage']}%") # FIXED
            total_percentage += split['percentage']
            if cols[2].button(f"Xóa", key=f"del_split_{i}"):
                st.session_state.rule_splits.pop(i)
                st.rerun()

        st.info(f"**Tổng tỷ lệ hiện tại: {total_percentage}%** (Phải đạt 100% để lưu)")
        
        st.write("Thêm chi nhánh vào quy tắc:")
        form_cols = st.columns([3, 2, 1])
        # Exclude HQ from being selected for allocation
        branch_list = [b for b in all_branches if b['id'] != 'HQ']
        branch_id = form_cols[0].selectbox("Chọn chi nhánh", options=[b['id'] for b in branch_list], format_func=lambda b_id: next(b['name'] for b in branch_list if b['id'] == b_id), key="rule_branch_select")
        percentage = form_cols[1].number_input("Tỷ lệ %", min_value=1, max_value=100, step=1, key="rule_percentage")
        if form_cols[2].form_submit_button("Thêm", use_container_width=True):
            if not any(s['branch_id'] == branch_id for s in st.session_state.rule_splits):
                st.session_state.rule_splits.append({'branch_id': branch_id, 'percentage': percentage})
                st.rerun()
            else:
                st.warning("Chi nhánh này đã được thêm.")

        submitted = st.form_submit_button("Lưu Quy tắc mới", use_container_width=True)
        if submitted:
            if not rule_name:
                st.error("Vui lòng nhập tên quy tắc.")
            elif not st.session_state.rule_splits:
                st.error("Quy tắc phải có ít nhất một chi nhánh để phân bổ.")
            elif total_percentage != 100:
                 st.error(f"Tổng tỷ lệ phần trăm phải là 100%, không phải là {total_percentage}%.")
            else:
                try:
                    cost_mgr.create_allocation_rule(rule_name, description, st.session_state.rule_splits)
                    st.success("Đã tạo quy tắc thành công!")
                    st.session_state.rule_splits = [] # Clear the state
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    st.divider()
    st.write("**Các quy tắc hiện có**")
    rules = cost_mgr.get_allocation_rules()
    if not rules:
        st.info("Chưa có quy tắc nào.")
    for rule in rules:
        with st.expander(f"{rule['name']} ({len(rule['splits'])} chi nhánh)"):
            st.write(f"*Mô tả: {rule.get('description', 'N/A')}*")
            rule_total = sum(s['percentage'] for s in rule['splits'])
            st.write(f"**Tổng tỷ lệ: {rule_total}%**")
            for split in rule['splits']:
                branch_name = next((b['name'] for b in all_branches if b['id'] == split['branch_id']), split['branch_id'])
                st.write(f"- **{branch_name}**: {split['percentage']}%")
            if st.button("Xóa Quy tắc", key=f"del_rule_{rule['id']}", use_container_width=True):
                cost_mgr.delete_allocation_rule(rule['id'])
                st.success("Đã xóa quy tắc.")
                st.rerun()

def render_apply_allocation(cost_mgr, hq_branch_id, user_id, unallocated_costs):
    st.subheader("Áp dụng Quy tắc vào Chi phí")
    
    # Lấy danh sách quy tắc
    rules = cost_mgr.get_allocation_rules()
    rule_options = {rule['id']: rule for rule in rules if sum(s['percentage'] for s in rule['splits']) == 100}
    if not rule_options:
        st.warning("Chưa có quy tắc phân bổ hợp lệ (tổng 100%). Vui lòng tạo/điều chỉnh quy tắc ở tab bên cạnh trước.")
        return

    if not unallocated_costs:
        st.info(f"Không có chi phí nào từ chi nhánh `{hq_branch_id}` cần được phân bổ.")
        return

    st.write("Chọn chi phí cần phân bổ:")
    for cost in unallocated_costs:
        with st.container():
            cols = st.columns([3, 2, 3, 2])
            cols[0].write(f"**{cost['name']}**")
            cols[1].write(f"{cost['amount']:,} VND") # FIXED
            
            selected_rule_id = cols[2].selectbox(
                "Chọn quy tắc phân bổ", 
                options=list(rule_options.keys()), 
                format_func=lambda rid: rule_options[rid]['name'],
                key=f"rule_{cost['id']}"
            )
            
            if cols[3].button("Áp dụng", key=f"apply_{cost['id']}", use_container_width=True):
                if not selected_rule_id:
                    st.error("Vui lòng chọn một quy tắc.")
                else:
                    try:
                        cost_mgr.apply_allocation(cost['id'], selected_rule_id, user_id)
                        st.success(f"Đã phân bổ thành công chi phí '{cost['name']}'.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi áp dụng: {e}")
