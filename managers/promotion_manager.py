import streamlit as st
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from datetime import datetime, timezone

class PromotionManager:
    """
    Manages all promotion-related logic, including Price Programs, Vouchers, etc.
    """
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection_ref = self.db.collection('promotions')

    def get_active_price_program(self):
        """
        Finds the highest-priority, active price program for the current time.
        Returns the program data dict or None.
        """
        now = datetime.now(timezone.utc).isoformat()

        query = self.collection_ref.where(filter=FieldFilter("promotion_type", "==", "PRICE_PROGRAM")) \
                                   .where(filter=FieldFilter("is_active", "==", True)) \
                                   .where(filter=FieldFilter("start_datetime", "<=", now)) \
                                   .where(filter=FieldFilter("end_datetime", ">=", now)) \
                                   .order_by("priority", direction=firestore.Query.DESCENDING) \
                                   .limit(1)
        
        active_programs = list(query.stream())

        if active_programs:
            # Return the first (and only) document's data
            return active_programs[0].to_dict()
        
        return None

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
            # Add created_at timestamp
            promo_data['created_at'] = datetime.now(timezone.utc).isoformat()
            self.collection_ref.add(promo_data)
            return True, "Tạo chương trình khuyến mãi thành công."
        except Exception as e:
            st.error(f"Lỗi khi tạo chương trình khuyến mãi: {e}")
            return False, str(e)

    def update_promotion_status(self, promo_id, is_active: bool):
        """
        Updates the 'is_active' status of a specific promotion.
        """
        try:
            self.collection_ref.document(promo_id).update({"is_active": is_active})
            return True, f"Đã cập nhật trạng thái của chương trình {promo_id}."
        except Exception as e:
            st.error(f"Lỗi khi cập nhật trạng thái: {e}")
            return False, str(e)

    def simulate_price_program_impact(self, promo_data, product_manager):
        """
        Simulates the impact of a price program on all products.
        """
        all_products = product_manager.get_all_products_with_cost()
        simulation_results = []

        # Extract promotion rules
        auto_discount_percent = promo_data.get('rules', {}).get('auto_discount', {}).get('value', 0)
        manual_extra_percent = promo_data.get('rules', {}).get('manual_extra_limit', {}).get('value', 0)
        min_margin_floor = promo_data.get('constraints', {}).get('min_margin_floor_percent', 0)

        for product in all_products:
            original_price = product.get('price_default') or 0
            cost_price = product.get('cost_price') or 0

            if original_price == 0:
                continue # Skip products without a price

            # --- Calculations ---
            original_margin_vnd = original_price - cost_price
            original_margin_percent = (original_margin_vnd / original_price * 100) if original_price > 0 else 0

            # After auto discount
            price_after_auto = original_price * (1 - auto_discount_percent / 100)
            auto_margin_vnd = price_after_auto - cost_price
            auto_margin_percent = (auto_margin_vnd / price_after_auto * 100) if price_after_auto > 0 else 0

            # After max manual discount
            total_discount_percent = auto_discount_percent + manual_extra_percent
            price_after_manual_max = original_price * (1 - total_discount_percent / 100)
            manual_max_margin_vnd = price_after_manual_max - cost_price
            manual_max_margin_percent = (manual_max_margin_vnd / price_after_manual_max * 100) if price_after_manual_max > 0 else 0

            # --- Warnings ---
            warnings = []
            if auto_margin_percent < min_margin_floor:
                warnings.append(f"Lợi nhuận sau giảm tự động ({auto_margin_percent:.1f}%) thấp hơn ngưỡng ({min_margin_floor}%)")
            if manual_max_margin_percent < min_margin_floor:
                warnings.append(f"Lợi nhuận sau giảm tối đa ({manual_max_margin_percent:.1f}%) thấp hơn ngưỡng ({min_margin_floor}%)")
            
            simulation_results.append({
                "sku": product.get('sku'),
                "name": product.get('name'),
                "cost_price": cost_price,
                "original_price": original_price,
                "original_margin_percent": original_margin_percent,
                "price_after_auto": price_after_auto,
                "auto_margin_percent": auto_margin_percent,
                "price_after_manual_max": price_after_manual_max,
                "manual_max_margin_percent": manual_max_margin_percent,
                "warnings": warnings
            })

        return simulation_results