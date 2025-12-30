
from datetime import datetime, timedelta
from google.cloud.firestore import Query
import pandas as pd
from dateutil.relativedelta import relativedelta

from .cost_manager import CostManager 

class ReportManager:
    def __init__(self, firebase_client, cost_mgr: CostManager):
        self.db = firebase_client.db
        self.cost_mgr = cost_mgr
        self.orders_collection = self.db.collection('orders')
        self.products_collection = self.db.collection('products')

    def get_profit_loss_statement(self, start_date: datetime, end_date: datetime, branch_id: str = None):
        """
        Tạo Báo cáo Kết quả Kinh doanh (P&L), bao gồm cả dữ liệu phân tích chi phí.
        """
        # 1. TÍNH DOANH THU VÀ GIÁ VỐN
        query = self.orders_collection
        branch_ids_for_query = []

        # Nếu không có branch_id cụ thể, query tất cả các chi nhánh
        if branch_id:
             branch_ids_for_query = [branch_id]
        # Nếu là admin và xem all, để rỗng để query_cost_entries tự xử lý

        # Query orders
        order_query = self.orders_collection.where('status', '==', 'COMPLETED')\
                                       .where('created_at', '>=', start_date.isoformat())\
                                       .where('created_at', '<=', end_date.isoformat())
        if branch_id:
            order_query = order_query.where('branch_id', '==', branch_id)

        orders = order_query.stream()
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
        # === KHỞI TẠO DICTIONARY MỚI ===
        op_expenses_by_classification = {}
        total_op_expenses = 0

        # Lấy chi phí
        cost_filters = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
        }
        # Phân quyền chi nhánh cho chi phí
        if branch_id:
            cost_filters['branch_id'] = branch_id
        
        cost_entries = self.cost_mgr.query_cost_entries(filters=cost_filters)
        
        # Lấy thông tin nhóm chi phí để mapping tên
        cost_groups_raw = self.cost_mgr.get_cost_groups()
        cost_groups = {g['id']: g['group_name'] for g in cost_groups_raw}

        for entry in cost_entries:
            # Tính toán số tiền chi phí thực tế trong kỳ (xử lý phân bổ)
            cost_in_period = 0
            if entry.get('is_amortized') and entry.get('amortization_months', 0) > 0:
                cost_in_period = self._calculate_amortized_cost_for_period(entry, start_date, end_date)
            elif not entry.get('is_amortized'): # Chỉ tính chi phí không phân bổ
                # Đảm bảo chi phí nằm trong khoảng thời gian báo cáo
                entry_date = datetime.fromisoformat(entry['entry_date']).replace(tzinfo=None)
                if start_date <= entry_date <= end_date:
                    cost_in_period = entry['amount']
            
            if cost_in_period > 0:
                total_op_expenses += cost_in_period

                # a. Phân loại theo NHÓM
                group_name = cost_groups.get(entry.get('group_id'), "Chưa phân loại")
                op_expenses_by_group[group_name] = op_expenses_by_group.get(group_name, 0) + cost_in_period

                # === b. PHÂN LOẠI THEO CLASSIFICATION ===
                classification_key = entry.get('classification', 'UNCATEGORIZED')
                op_expenses_by_classification[classification_key] = op_expenses_by_classification.get(classification_key, 0) + cost_in_period

        # 3. TÍNH LỢI NHUẬN RÒNG
        net_profit = gross_profit - total_op_expenses

        return {
            "success": True,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "branch_id": branch_id,
            "order_count": order_count,
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "operating_expenses_by_group": op_expenses_by_group,
            # === THÊM DỮ LIỆU MỚI VÀO KẾT QUẢ ===
            "operating_expenses_by_classification": op_expenses_by_classification,
            "total_operating_expenses": total_op_expenses,
            "net_profit": net_profit
        }

    def _calculate_amortized_cost_for_period(self, cost_entry, report_start, report_end) -> float:
        try:
            amount = float(cost_entry['amount'])
            months = int(cost_entry['amortization_months'])
            # Ngày bắt đầu phân bổ là ngày ghi chi phí
            entry_date = datetime.fromisoformat(cost_entry['entry_date']).replace(tzinfo=None)

            if months <= 0:
                return 0

            monthly_cost = amount / months
            total_cost_in_period = 0
            
            # Duyệt qua từng tháng trong chu kỳ phân bổ
            for i in range(months):
                amortization_month_start = (entry_date + relativedelta(months=i)).replace(day=1)
                # Nếu tháng phân bổ bắt đầu sau khi báo cáo kết thúc, bỏ qua
                if amortization_month_start > report_end:
                    continue
                
                amortization_month_end = amortization_month_start + relativedelta(months=1) - timedelta(days=1)
                # Nếu tháng phân bổ kết thúc trước khi báo cáo bắt đầu, bỏ qua
                if amortization_month_end < report_start:
                    continue

                # Nếu có giao thoa, tính là chi phí của kỳ này
                total_cost_in_period += monthly_cost

            return total_cost_in_period
        except (ValueError, TypeError, KeyError) as e:
            print(f"Error calculating amortization for entry {cost_entry.get('id')}: {e}")
            return 0
