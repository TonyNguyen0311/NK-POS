
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

