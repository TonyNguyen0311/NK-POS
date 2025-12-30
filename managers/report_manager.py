
from datetime import datetime, timedelta
from google.cloud.firestore import Query
import pandas as pd
from dateutil.relativedelta import relativedelta

# Giả định CostManager được truyền vào, vì report_manager cần nó
from .cost_manager import CostManager 

class ReportManager:
    def __init__(self, firebase_client, cost_mgr: CostManager):
        self.db = firebase_client.db
        self.cost_mgr = cost_mgr
        self.orders_collection = self.db.collection('orders')
        self.products_collection = self.db.collection('products')
        self.cost_entries_collection = self.db.collection('cost_entries') # Thêm collection này

    def get_profit_loss_statement(self, start_date: datetime, end_date: datetime, branch_id: str = None):
        """
        Hàm chính để tạo Báo cáo Kết quả Kinh doanh (P&L) hoàn chỉnh.
        Bao gồm Doanh thu, Giá vốn, Chi phí hoạt động (có xử lý phân bổ) và Lợi nhuận ròng.
        """
        # 1. TÍNH DOANH THU VÀ GIÁ VỐN TỪ ĐƠN HÀNG
        query = self.orders_collection
        if branch_id:
            query = query.where('branch_id', '==', branch_id)
        
        query = query.where('created_at', '>=', start_date.isoformat())
        query = query.where('created_at', '<=', end_date.isoformat())
        query = query.where('status', '==', 'COMPLETED')

        orders = query.stream()
        total_revenue = 0
        total_cogs = 0
        order_count = 0

        for order in orders:
            order_data = order.to_dict()
            total_revenue += order_data.get('grand_total', 0)
            total_cogs += order_data.get('total_cogs', 0)
            order_count += 1

        gross_profit = total_revenue - total_cogs

        # 2. TÍNH CHI PHÍ HOẠT ĐỘNG (OPERATING EXPENSES)
        op_expenses_by_group = {}
        total_op_expenses = 0

        cost_filters = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'status': 'ACTIVE'
        }
        if branch_id:
            cost_filters['branch_id'] = branch_id
        
        # Lấy tất cả chi phí trong kỳ (cần hàm query_cost_entries đã tạo)
        cost_entries = self.cost_mgr.query_cost_entries(filters=cost_filters)
        
        # Lấy thông tin group để mapping tên
        cost_groups_raw = self.cost_mgr.get_cost_groups()
        cost_groups = {g['id']: g['group_name'] for g in cost_groups_raw}

        for entry in cost_entries:
            group_name = cost_groups.get(entry.get('group_id'), "Chưa phân loại")
            if group_name not in op_expenses_by_group:
                op_expenses_by_group[group_name] = 0

            # Xử lý logic phân bổ chi phí
            if entry.get('is_amortized') and entry.get('amortization_months', 0) > 0:
                amortized_cost_in_period = self._calculate_amortized_cost_for_period(entry, start_date, end_date)
                op_expenses_by_group[group_name] += amortized_cost_in_period
                total_op_expenses += amortized_cost_in_period
            else:
                # Chi phí thường, tính toàn bộ
                op_expenses_by_group[group_name] += entry['amount']
                total_op_expenses += entry['amount']

        # 3. TÍNH LỢI NHUẬN RÒNG
        net_profit = gross_profit - total_op_expenses

        return {
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "branch_id": branch_id,
            "order_count": order_count,
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "operating_expenses_by_group": op_expenses_by_group,
            "total_operating_expenses": total_op_expenses,
            "net_profit": net_profit
        }

    def _calculate_amortized_cost_for_period(self, cost_entry, report_start, report_end) -> float:
        """Hàm nội bộ tính toán chi phí phân bổ cho một kỳ báo cáo cụ thể."""
        try:
            amount = float(cost_entry['amount'])
            months = int(cost_entry['amortization_months'])
            entry_start_amort_str = cost_entry['start_amortization_date']
            entry_start_amort = datetime.fromisoformat(entry_start_amort_str).replace(tzinfo=None)

            if months == 0:
                return 0

            monthly_cost = amount / months
            total_cost_in_period = 0
            
            # Duyệt qua từng tháng trong chu kỳ phân bổ của chi phí
            for i in range(months):
                current_amort_month_start = (entry_start_amort + relativedelta(months=i)).replace(day=1)
                current_amort_month_end = current_amort_month_start + relativedelta(months=1) - timedelta(days=1)
                
                # Chỉ tính chi phí nếu tháng phân bổ nằm trong khoảng thời gian của báo cáo
                # (Kiểm tra sự giao thoa giữa 2 khoảng thời gian)
                if current_amort_month_start < report_end and current_amort_month_end > report_start:
                     total_cost_in_period += monthly_cost

            return total_cost_in_period
        except (ValueError, TypeError, KeyError) as e:
            # Ghi lại log lỗi sẽ tốt hơn ở đây
            print(f"Error calculating amortization for entry {cost_entry.get('entry_id')}: {e}")
            return 0

    # --- CÁC HÀM BÁO CÁO CŨ (có thể giữ lại hoặc refactor sau) ---
    def get_revenue_overview(self, branch_id=None, time_range='7d'):
        # ... (giữ nguyên code cũ)
        pass
        
    def get_best_selling_products(self, branch_id=None, limit=10, time_range='mtd'):
        # ... (giữ nguyên code cũ)
        pass
