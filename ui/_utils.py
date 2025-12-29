import streamlit as st

def set_wide_layout():
    st.set_page_config(layout="wide")

def format_vnd(value):
    return f"{value:,.0f} đ"

def show_toast(message, type='success'):
    st.toast(message, icon='✅' if type == 'success' else '⚠️')

def confirm_dialog(message):
    return st.confirm(message)

def load_css(file_path):
    with open(file_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
