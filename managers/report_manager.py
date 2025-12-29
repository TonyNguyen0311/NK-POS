from datetime import datetime, timedelta
from google.cloud.firestore import Query

class ReportManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.orders_collection = self.db.collection('orders')
        self.products_collection = self.db.collection('products')

    def get_revenue_overview(self, branch_id=None, time_range='7d'):
        """
        Lấy tổng quan doanh thu theo một khoảng thời gian.
        time_range: '7d' (7 days), '30d' (30 days), 'mtd' (month-to-date), 'ytd' (year-to-date)
        """
        end_date = datetime.now()
        if time_range == '7d':
            start_date = end_date - timedelta(days=7)
        elif time_range == '30d':
            start_date = end_date - timedelta(days=30)
        elif time_range == 'mtd':
            start_date = end_date.replace(day=1)
        elif time_range == 'ytd':
            start_date = end_date.replace(month=1, day=1)
        else: # Default to 7 days
            start_date = end_date - timedelta(days=7)

        query = self.orders_collection
        if branch_id:
            query = query.where('branch_id', '==', branch_id)
        
        query = query.where('created_at', '>=', start_date.isoformat())
        query = query.where('created_at', '<=', end_date.isoformat())

        orders = query.stream()

        total_revenue = 0
        order_count = 0
        daily_revenue = {}

        for order in orders:
            order_data = order.to_dict()
            total_revenue += order_data.get('total_amount', 0)
            order_count += 1
            
            # Group by day
            order_date_str = datetime.fromisoformat(order_data['created_at']).strftime('%Y-%m-%d')
            daily_revenue[order_date_str] = daily_revenue.get(order_date_str, 0) + order_data.get('total_amount', 0)

        return {
            'total_revenue': total_revenue,
            'order_count': order_count,
            'daily_revenue': sorted(daily_revenue.items()), # Sắp xếp để vẽ biểu đồ
            'start_date': start_date,
            'end_date': end_date
        }

    def get_best_selling_products(self, branch_id=None, limit=10):
        """Lấy danh sách sản phẩm bán chạy nhất."""
        query = self.orders_collection
        if branch_id:
            query = query.where('branch_id', '==', branch_id)
        
        orders = query.stream()
        
        product_sales = {}
        for order in orders:
            for item in order.to_dict().get('items', []):
                sku = item['sku']
                quantity = item['quantity']
                product_sales[sku] = product_sales.get(sku, 0) + quantity
        
        # Sắp xếp sản phẩm theo số lượng bán được
        sorted_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        # Lấy thông tin chi tiết của sản phẩm
        product_details = []
        for sku, quantity_sold in sorted_products:
            product_doc = self.products_collection.document(sku).get()
            if product_doc.exists:
                product_data = product_doc.to_dict()
                product_details.append({
                    'sku': sku,
                    'name': product_data.get('name', 'N/A'),
                    'quantity_sold': quantity_sold
                })
        
        return product_details
