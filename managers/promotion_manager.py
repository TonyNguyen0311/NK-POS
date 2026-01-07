
import streamlit as st
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore
from datetime import datetime, timezone

def hash_promotion_manager(manager):
    return "PromotionManager"

class PromotionManager:
    """
    Quản lý tất cả logic liên quan đến khuyến mãi, bao gồm Chương trình giá, Voucher, v.v.
    """
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection_ref = self.db.collection('promotions')

    def apply_promotions_to_cart(self, cart_items: dict, manual_discount_input: dict):
        """
        Tính toán tất cả các loại giảm giá cho một giỏ hàng.
        Đây là trung tâm xử lý logic khuyến mãi, tách biệt khỏi POSManager.
        """
        active_promo = self.get_active_price_program()
        calculated_items = {}
        subtotal = 0
        total_auto_discount = 0
        manual_discount_exceeded = False

        for sku, item in cart_items.items():
            original_line_total = item['original_price'] * item['quantity']
            subtotal += original_line_total
            
            auto_discount_value = 0
            if self.is_item_eligible_for_program(item, active_promo):
                auto_discount_rule = active_promo.get('rules', {}).get('auto_discount', {})
                if auto_discount_rule.get('type') == 'PERCENT':
                    auto_discount_value = original_line_total * (auto_discount_rule.get('value', 0) / 100)
            
            total_auto_discount += auto_discount_value

            calculated_items[sku] = {
                **item,
                'original_line_total': original_line_total,
                'auto_discount_applied': auto_discount_value,
                'line_total_after_auto_discount': original_line_total - auto_discount_value
            }
        
        total_manual_discount = 0
        limit_value = 0
        if active_promo and self.is_manual_discount_allowed(active_promo):
            limit_rule = active_promo.get('rules', {}).get('manual_extra_limit', {})
            limit_value = limit_rule.get('value', 0)
            user_discount_value = manual_discount_input.get('value', 0)
            
            if user_discount_value > limit_value:
                manual_discount_exceeded = True
            else:
                # Giảm giá thủ công được tính trên tổng tiền sau khi đã áp dụng giảm giá tự động
                total_after_auto_discount = subtotal - total_auto_discount
                total_manual_discount = total_after_auto_discount * (user_discount_value / 100)
        
        grand_total = subtotal - total_auto_discount - total_manual_discount

        return {
            "items": calculated_items,
            "active_promotion": active_promo,
            "subtotal": subtotal,
            "total_auto_discount": total_auto_discount,
            "total_manual_discount": total_manual_discount,
            "manual_discount_limit": limit_value,
            "manual_discount_exceeded": manual_discount_exceeded,
            "grand_total": grand_total
        }

    def get_all_promotions(self):
        """Trả về danh sách tất cả các chương trình khuyến mãi, sắp xếp theo thời gian tạo."""
        query = self.collection_ref.order_by("created_at", direction=firestore.Query.DESCENDING)
        return [doc.to_dict() for doc in query.stream()]

    def get_active_price_program(self):
        """
        Tìm chương trình giá đang hoạt động có ưu tiên cao nhất.
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
            program = active_programs[0].to_dict()
            program['id'] = active_programs[0].id
            return program
        return None

    def check_and_initialize(self):
        docs = self.collection_ref.limit(1).get()
        if not docs:
            st.warning("⚠️ Database 'promotions' trống, đang khởi tạo dữ liệu mẫu...")
            sample_program = {
                "name": "Chương trình giá mẫu (Không hoạt động)",
                "description": "Giảm giá 10% tự động cho tất cả hàng thời trang và cho phép nhân viên giảm thêm 5%.",
                "is_active": False, "start_datetime": "2024-01-01T00:00:00Z", "end_datetime": "2029-12-31T23:59:59Z",
                "priority": 100, "promotion_type": "PRICE_PROGRAM",
                "scope": {"type": "ALL", "ids": []},
                "rules": {"auto_discount": {"type": "PERCENT", "value": 10}, "manual_extra_limit": {"type": "PERCENT", "value": 5}},
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            self.collection_ref.add(sample_program)
            st.success("✅ Khởi tạo dữ liệu mẫu thành công!")
            self.get_all_promotions.clear()

    def create_promotion(self, promo_data):
        try:
            promo_data['created_at'] = datetime.now(timezone.utc).isoformat()
            self.collection_ref.add(promo_data)
            self.get_all_promotions.clear()
            self.get_active_price_program.clear()
            return True, "Tạo chương trình khuyến mãi thành công."
        except Exception as e:
            return False, f"Lỗi khi tạo: {e}"

    def update_promotion_status(self, promo_id, is_active: bool):
        try:
            self.collection_ref.document(promo_id).update({"is_active": is_active})
            self.get_all_promotions.clear()
            self.get_active_price_program.clear()
            return True, "Cập nhật trạng thái thành công."
        except Exception as e:
            return False, f"Lỗi khi cập nhật: {e}"

    def is_item_eligible_for_program(self, item: dict, program: dict) -> bool:
        if not program or not item: return False
        scope = program.get('scope', {})
        scope_type = scope.get('type')
        if scope_type == 'ALL': return True
        scope_ids = scope.get('ids', [])
        if scope_type == 'PRODUCT' and item.get('sku') in scope_ids: return True
        if scope_type == 'CATEGORY' and item.get('category_id') in scope_ids: return True
        return False

    def is_manual_discount_allowed(self, program: dict) -> bool:
        if not program: return False
        return program.get('rules', {}).get('manual_extra_limit', {}).get('value', 0) > 0

# Apply decorators after the class is defined
PromotionManager.get_all_promotions = st.cache_data(ttl=300, hash_funcs={PromotionManager: hash_promotion_manager})(PromotionManager.get_all_promotions)
PromotionManager.get_active_price_program = st.cache_data(ttl=60, hash_funcs={PromotionManager: hash_promotion_manager})(PromotionManager.get_active_price_program)
