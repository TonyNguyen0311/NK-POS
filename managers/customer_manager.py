
import uuid
from datetime import datetime
from firebase_admin import firestore

class CustomerManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('customers')

    def create_customer(self, data: dict):
        """Tạo khách hàng mới."""
        customer_id = f"CUS-{uuid.uuid4().hex[:6].upper()}"
        
        new_data = data.copy()
        new_data['id'] = customer_id
        new_data['created_at'] = datetime.now().isoformat()
        new_data.setdefault('total_spent', 0)
        new_data.setdefault('points', 0)
        new_data.setdefault('rank', 'Đồng')

        self.collection.document(customer_id).set(new_data)
        return new_data

    def list_customers(self, query: str | None = None):
        """Lấy danh sách khách hàng. Có thể tìm kiếm theo tên hoặc sđt."""
        # Note: Firestore không hỗ trợ full-text search hiệu quả.
        # Cách tiếp cận đơn giản là lấy tất cả và lọc bằng Python.
        # Với lượng khách hàng lớn, cần giải pháp search mạnh hơn (VD: Algolia, Elasticsearch)
        docs = self.collection.stream()
        results = []
        for doc in docs:
            results.append(doc.to_dict())

        if query:
            query = query.lower()
            return [
                c for c in results 
                if query in c.get('name', '').lower() or query in c.get('phone', '')
            ]
        return results

    def get_customer_by_id(self, customer_id: str):
        """Lấy thông tin chi tiết một khách hàng."""
        doc = self.collection.document(customer_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def update_customer_stats(self, transaction, customer_id, amount_spent_delta, points_delta):
        """ 
        Cập nhật tổng chi tiêu và điểm của khách hàng.
        Hàm này được thiết kế để chạy bên trong một transaction lớn hơn (khi tạo đơn hàng).
        """
        if not customer_id: return

        customer_ref = self.collection.document(customer_id)
        
        # Dùng FieldValue.increment để đảm bảo an toàn
        transaction.update(customer_ref, {
            'total_spent': firestore.FieldValue.increment(amount_spent_delta),
            'points': firestore.FieldValue.increment(points_delta),
            'last_purchase_date': datetime.now().isoformat()
        })
