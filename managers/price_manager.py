
from datetime import datetime, time
import uuid
import pytz
import streamlit as st

class PriceManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.prices_col = self.db.collection('branch_prices')
        self.schedules_col = self.db.collection('price_schedules')

    def set_price(self, sku: str, branch_id: str, price: float):
        # ... (logic không đổi) ...
        self.get_all_prices.clear()
        self.get_active_prices_for_branch.clear()
        self.get_price.clear()
        pass

    def set_business_status(self, sku: str, branch_id: str, is_active: bool):
        # ... (logic không đổi) ...
        self.get_all_prices.clear()
        self.get_active_prices_for_branch.clear()
        pass

    # SỬA LỖI: Thêm _self_unhashable=True
    @st.cache_data(ttl=300, _self_unhashable=True)
    def get_all_prices(self):
        docs = self.prices_col.stream()
        return [doc.to_dict() for doc in docs]

    # SỬA LỖI: Thêm _self_unhashable=True
    @st.cache_data(ttl=300, _self_unhashable=True)
    def get_active_prices_for_branch(self, branch_id: str):
        try:
            all_prices = self.get_all_prices()
            active_products = [
                p for p in all_prices 
                if p.get('branch_id') == branch_id and p.get('is_active', False)
            ]
            return active_products
        except Exception as e:
            print(f"Error getting active prices for branch {branch_id}: {e}")
            return []

    # SỬA LỖI: Thêm _self_unhashable=True
    @st.cache_data(ttl=300, _self_unhashable=True)
    def get_price(self, sku: str, branch_id: str):
        doc = self.prices_col.document(f"{branch_id}_{sku}").get()
        return doc.to_dict() if doc.exists else None

    # ... (các hàm còn lại không đổi) ...
