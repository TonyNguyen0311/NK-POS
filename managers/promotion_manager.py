import streamlit as st
from google.cloud.firestore_v1.base_query import FieldFilter

class PromotionManager:
    """
    Manages all promotion-related logic, including Price Programs, Vouchers, etc.
    """
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection_ref = self.db.collection('promotions')

    def check_and_initialize(self):
        """
        Checks if the promotions collection has any documents.
        If not, it creates a sample, inactive Price Program for demonstration.
        """
        docs = self.collection_ref.limit(1).get()
        if not docs:
            st.warning("⚠️ Database 'promotions' không tìm thấy hoặc trống. Đang khởi tạo dữ liệu mẫu...")
            
            sample_price_program = {
              "name": "Chương trình giá mẫu (Không hoạt động)",
              "description": "Giảm giá 10% tự động cho tất cả hàng thời trang và cho phép nhân viên giảm thêm 5%.",
              "is_active": False,
              "start_datetime": "2024-01-01T00:00:00Z",
              "end_datetime": "2029-12-31T23:59:59Z",
              "priority": 100,
              "stacking_rule": "EXCLUSIVE",
              "promotion_type": "PRICE_PROGRAM",

              "scope": {
                "type": "ALL", 
                "ids": [] 
              },

              "rules": {
                "auto_discount": { "type": "PERCENT", "value": 10 },
                "manual_extra_limit": { "type": "PERCENT", "value": 5 }
              },

              "constraints": {
                  "min_margin_floor_percent": 10,
                  "per_line_cap_vnd": 500000
              }
            }
            self.collection_ref.add(sample_price_program)
            st.success("✅ Khởi tạo dữ liệu mẫu cho 'promotions' thành công!")

    def create_promotion(self, promo_data):
        """
        Creates a new promotion document in Firestore.
        """
        try:
            self.collection_ref.add(promo_data)
            return True, "Tạo chương trình khuyến mãi thành công."
        except Exception as e:
            st.error(f"Lỗi khi tạo chương trình khuyến mãi: {e}")
            return False, str(e)
