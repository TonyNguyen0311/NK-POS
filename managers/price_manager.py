
from datetime import datetime, time
import uuid
import pytz
import streamlit as st

def hash_price_manager(manager):
    return "PriceManager"

class PriceManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.prices_col = self.db.collection('branch_prices')
        self.schedules_col = self.db.collection('price_schedules')

    def set_price(self, sku: str, branch_id: str, price: float):
        if not all([sku, branch_id, price >= 0]):
            raise ValueError("Thông tin SKU, chi nhánh và giá là bắt buộc.")
        doc_id = f"{branch_id}_{sku}"
        self.prices_col.document(doc_id).set({
            'branch_id': branch_id,
            'sku': sku,
            'price': price,
            'updated_at': datetime.now().isoformat()
        }, merge=True)
        self.get_all_prices.clear()
        self.get_active_prices_for_branch.clear()
        self.get_price.clear()

    def set_business_status(self, sku: str, branch_id: str, is_active: bool):
        doc_id = f"{branch_id}_{sku}"
        self.prices_col.document(doc_id).set({
            'is_active': is_active,
            'updated_at': datetime.now().isoformat()
        }, merge=True)
        self.get_all_prices.clear()
        self.get_active_prices_for_branch.clear()

    def get_all_prices(self):
        docs = self.prices_col.stream()
        return [doc.to_dict() for doc in docs]

    def get_active_prices_for_branch(self, branch_id: str):
        """Lấy các sản phẩm đang được 'Kinh doanh' tại một chi nhánh (đã sửa lỗi)."""
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

    def get_price(self, sku: str, branch_id: str):
        doc = self.prices_col.document(f"{branch_id}_{sku}").get()
        return doc.to_dict() if doc.exists else None

    def schedule_price_change(self, sku: str, branch_id: str, new_price: float, apply_date: datetime, created_by: str):
        if not all([sku, branch_id, new_price > 0, apply_date, created_by]):
            return False, "Dữ liệu không hợp lệ."
        
        apply_datetime = datetime.combine(apply_date, time.min)

        schedule_id = f"SCH-{uuid.uuid4().hex[:8].upper()}"
        data = {
            "schedule_id": schedule_id,
            "sku": sku,
            "branch_id": branch_id,
            "new_price": new_price,
            "start_date": apply_datetime, 
            "status": "PENDING",
            "created_at": datetime.now(),
            "created_by": created_by
        }
        self.schedules_col.document(schedule_id).set(data)
        return True, schedule_id

    def get_pending_schedules_for_product(self, sku: str, branch_id: str):
        """Lấy các lịch trình đang chờ áp dụng cho một sản phẩm cụ thể (đã sửa lỗi)."""
        try:
            query = self.schedules_col.where('status', '==', 'PENDING')
            all_pending = [doc.to_dict() for doc in query.stream()]
            
            product_schedules = [
                s for s in all_pending 
                if s.get('sku') == sku and s.get('branch_id') == branch_id
            ]
            
            product_schedules.sort(key=lambda s: s.get('start_date', datetime.max))
            
            return product_schedules
        except Exception as e:
            print(f"Error getting pending schedules: {e}")
            return []

    def cancel_schedule(self, schedule_id: str):
        doc_ref = self.schedules_col.document(schedule_id)
        if doc_ref.get().exists:
            doc_ref.update({"status": "CANCELED"})
            return True
        return False

    def apply_pending_schedules(self):
        now = datetime.now(pytz.utc)
        query = self.schedules_col \
            .where('status', '==', 'PENDING') \
            .where('start_date', '<=', now) \
            .order_by('start_date')
        
        applied_count = 0
        for doc in query.stream():
            schedule = doc.to_dict()
            try:
                self.set_price(schedule['sku'], schedule['branch_id'], schedule['new_price'])
                doc.reference.update({"status": "APPLIED"})
                applied_count += 1
            except Exception as e:
                print(f"Error applying schedule {schedule['schedule_id']}: {e}")
        
        if applied_count > 0:
            print(f"Applied {applied_count} price schedules.")

        return applied_count

# Apply decorators after the class is defined
PriceManager.get_all_prices = st.cache_data(
    ttl=300, hash_funcs={PriceManager: hash_price_manager}
)(PriceManager.get_all_prices)

PriceManager.get_active_prices_for_branch = st.cache_data(
    ttl=300, hash_funcs={PriceManager: hash_price_manager}
)(PriceManager.get_active_prices_for_branch)

PriceManager.get_price = st.cache_data(
    ttl=300, hash_funcs={PriceManager: hash_price_manager}
)(PriceManager.get_price)
