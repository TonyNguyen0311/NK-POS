import streamlit as st

def format_vnd(amount):
    """Chuyển số thành định dạng tiền Việt: 100000 -> 100,000 ₫"""
    if amount is None:
        return "0 ₫"
    return "{:,.0f} ₫".format(amount)
