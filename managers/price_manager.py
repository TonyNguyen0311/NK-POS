
from datetime import datetime, time
import uuid
import pytz

class PriceManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.prices_col = self.db.collection('branch_prices')
        self.schedules_col = self.db.collection('price_schedules')

    # --- CÁC HÀM QUẢN LÝ GIÁ TRỰC TIẾP ---
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

    def set_business_status(self, sku: str, branch_id: str, is_active: bool):
        doc_id = f"{branch_id}_{sku}"
        self.prices_col.document(doc_id).set({
            'is_active': is_active,
            'updated_at': datetime.now().isoformat()
        }, merge=True)

    def get_all_prices(self):
        docs = self.prices_col.stream()
        return [doc.to_dict() for doc in docs]

    def get_active_prices_for_branch(self, branch_id: str):
        """Lấy các sản phẩm đang được 'Kinh doanh' tại một chi nhánh (đã sửa lỗi)."""
        try:
            # Đơn giản hóa truy vấn để chỉ lọc theo branch_id
            docs_in_branch = self.prices_col.where('branch_id', '==', branch_id).stream()

            # Lọc các sản phẩm 'is_active' bằng Python
            active_products = [
                doc.to_dict() for doc in docs_in_branch if doc.to_dict().get('is_active', False)
            ]
            return active_products
        except Exception as e:
            print(f"Error getting active prices for branch {branch_id}: {e}")
            return []

    def get_price(self, sku: str, branch_id: str):
        doc = self.prices_col.document(f"{branch_id}_{sku}").get()
        return doc.to_dict() if doc.exists else None

    # --- CÁC HÀM MỚI CHO LỊCH TRÌNH GIÁ ---
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
            
            # Lọc kết quả bằng Python thay vì truy vấn phức tạp
            product_schedules = [
                s for s in all_pending 
                if s.get('sku') == sku and s.get('branch_id') == branch_id
            ]
            
            # Sắp xếp kết quả theo ngày
            product_schedules.sort(key=lambda s: s.get('start_date', datetime.max))
            
            return product_schedules
        except Exception as e:
            print(f"Error getting pending schedules: {e}") # Log lỗi để dễ debug
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
        
        return applied_count
