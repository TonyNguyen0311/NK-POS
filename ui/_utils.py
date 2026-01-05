
import streamlit as st

def load_css(file_path):
    """Loads a CSS file into the Streamlit app."""
    with open(file_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def render_page_title(title):
    """Renders a formatted page title using a custom CSS class."""
    st.markdown(f'<h1 class="page-title">{title}</h1>', unsafe_allow_html=True)

def render_section_header(title):
    """Renders a formatted section header using a custom CSS class."""
    st.markdown(f'<h2 class="section-header">{title}</h2>', unsafe_allow_html=True)

def render_sub_header(title):
    """Renders a formatted sub-header using a custom CSS class."""
    st.markdown(f'<h3 class="sub-header">{title}</h3>', unsafe_allow_html=True)

def render_branch_selector(allowed_branches_map, default_branch_id=None, key_prefix=""):
    """
    Renders a selectbox for branch selection and returns the selected branch_id.

    Args:
        allowed_branches_map (dict): A dictionary mapping branch_id to branch_name.
        default_branch_id (str, optional): The default branch to select.
        key_prefix (str, optional): A prefix for the widget key to ensure uniqueness.

    Returns:
        str: The selected branch_id or None if no branches are available.
    """
    if not allowed_branches_map:
        return None

    branch_ids = list(allowed_branches_map.keys())
    branch_names = list(allowed_branches_map.values())
    
    # Ensure the default is valid, otherwise use the first available branch
    try:
        default_index = branch_ids.index(default_branch_id) if default_branch_id in branch_ids else 0
    except (ValueError, IndexError):
        default_index = 0

    selected_branch = st.selectbox(
        "**Chọn chi nhánh**",
        options=branch_ids,
        format_func=lambda x: allowed_branches_map.get(x, "Không xác định"),
        index=default_index,
        key=f"{key_prefix}_branch_selector"
    )
    
    return selected_branch
