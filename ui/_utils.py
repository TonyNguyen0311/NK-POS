import streamlit as st

def render_page_header(title, icon=""): 
    st.markdown(f'<h2 style="display: flex; align-items: center; gap: 10px;">{icon} {title}</h2>', unsafe_allow_html=True)
    st.divider()

def render_branch_selector(allowed_branches_map, default_branch_id):
    if not allowed_branches_map:
        st.warning("Tài khoản của bạn chưa được phân quyền vào chi nhánh nào. Vui lòng liên hệ Admin.")
        return None

    if len(allowed_branches_map) > 1:
        # Create a list of keys to find the index of the default branch
        branch_ids = list(allowed_branches_map.keys())
        try:
            default_index = branch_ids.index(default_branch_id)
        except ValueError:
            default_index = 0 # Default to the first branch if the user's default is not in the allowed list

        selected_branch_id = st.selectbox(
            "Chọn chi nhánh",
            options=branch_ids,
            format_func=lambda x: allowed_branches_map[x],
            index=default_index
        )
        return selected_branch_id
    else:
        # If only one branch, display it as disabled text and return its ID
        single_branch_id = list(allowed_branches_map.keys())[0]
        st.text_input("Chi nhánh", value=allowed_branches_map[single_branch_id], disabled=True)
        return single_branch_id