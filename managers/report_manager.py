
import logging
from datetime import datetime, timedelta
from google.cloud.firestore import Query
import pandas as pd
from dateutil.relativedelta import relativedelta
import streamlit as st

from .cost_manager import CostManager

def hash_report_manager(manager):
    return "ReportManager"

class ReportManager:
    def __init__(self, firebase_client, cost_mgr: CostManager):
        self.db = firebase_client.db
        self.cost_mgr = cost_mgr
        self.orders_collection = self.db.collection('orders')
        self.products_collection = self.db.collection('products')
        self.inventory_collection = self.db.collection('inventory')
        self.categories_collection = self.db.collection('categories')

    def get_profit_analysis_report(self, start_date: datetime, end_date: datetime, branch_ids: list):
        """
        Phân tích lợi nhuận chi tiết theo sản phẩm và danh mục.
        """
        try:
            products_snapshot = self.products_collection.stream()
            product_details = {p.id: p.to_dict() for p in products_snapshot}
            categories_snapshot = self.categories_collection.stream()
            category_details = {c.id: c.to_dict().get('name', 'N/A') for c in categories_snapshot}

            order_query = self.orders_collection.where('status', '==', 'COMPLETED') \
                                               .where('created_at', '>=', start_date.isoformat()) \
                                               .where('created_at', '<=', end_date.isoformat())
            if branch_ids:
                order_query = order_query.where('branch_id', 'in', branch_ids)
            orders = order_query.stream()

            product_profit_data = {}
            for order in orders:
                order_data = order.to_dict()
                for item in order_data.get('line_items', []):
                    product_id = item.get('product_id')
                    if not product_id: continue
                    quantity = item.get('quantity', 0)
                    revenue = item.get('final_price', 0) * quantity
                    cogs = item.get('cost_price', 0) * quantity
                    profit = revenue - cogs
                    if product_id not in product_profit_data:
                        product_profit_data[product_id] = {
                            'product_name': item.get('product_name', 'N/A'),
                            'category_id': product_details.get(product_id, {}).get('category_id'),
                            'total_quantity_sold': 0, 'total_revenue': 0, 'total_profit': 0
                        }
                    product_profit_data[product_id]['total_quantity_sold'] += quantity
                    product_profit_data[product_id]['total_revenue'] += revenue
                    product_profit_data[product_id]['total_profit'] += profit

            if not product_profit_data:
                return {"success": True, "data": None, "message": "Không có dữ liệu bán hàng trong kỳ."}

            profit_df = pd.DataFrame.from_dict(product_profit_data, orient='index').reset_index().rename(columns={'index': 'product_id'})
            profit_df['category_name'] = profit_df['category_id'].map(category_details).fillna('Không có danh mục')
            profit_df['profit_margin'] = profit_df.apply(
                lambda row: (row['total_profit'] / row['total_revenue']) * 100 if row['total_revenue'] > 0 else 0, axis=1)

            category_profit_df = profit_df.groupby('category_name').agg(
                total_revenue=('total_revenue', 'sum'),
                total_profit=('total_profit', 'sum')
            ).reset_index()
            category_profit_df['profit_margin'] = category_profit_df.apply(
                lambda row: (row['total_profit'] / row['total_revenue']) * 100 if row['total_revenue'] > 0 else 0, axis=1)

            profit_df = profit_df.sort_values(by='total_profit', ascending=False)
            category_profit_df = category_profit_df.sort_values(by='total_profit', ascending=False)
            return {"success": True, "data": {'product_profit_df': profit_df, 'category_profit_df': category_profit_df}}
        except Exception as e:
            logging.error(f"Lỗi khi tạo báo cáo phân tích lợi nhuận: {e}")
            return {"success": False, "message": str(e)}

    def get_inventory_report(self, branch_ids: list):
        """
        Tạo báo cáo tồn kho chi tiết, sử dụng giá vốn bình quân gia quyền (average_cost)
        trực tiếp từ collection 'inventory'.
        """
        try:
            products_snapshot = self.products_collection.stream()
            product_details = {p.id: p.to_dict() for p in products_snapshot}

            inventory_query = self.inventory_collection
            if branch_ids:
                inventory_query = inventory_query.where('branch_id', 'in', branch_ids)
            inventory_docs = list(inventory_query.stream())

            if not inventory_docs:
                return {"success": True, "data": None, "message": "Không có dữ liệu tồn kho cho chi nhánh đã chọn."}

            inventory_list = []
            total_inventory_value = 0
            total_inventory_items = 0

            for item_doc in inventory_docs:
                item_data = item_doc.to_dict()
                sku = item_data.get('sku')
                quantity = item_data.get('stock_quantity', 0)
                
                average_cost = item_data.get('average_cost', 0)
                item_value = average_cost * quantity

                product_info = product_details.get(sku, {})

                inventory_list.append({
                    'product_id': sku,
                    'product_name': product_info.get('name', 'N/A'),
                    'branch_id': item_data.get('branch_id'),
                    'quantity': quantity,
                    'average_cost': average_cost,
                    'total_value': item_value
                })
                total_inventory_value += item_value
                total_inventory_items += quantity
            
            if not inventory_list:
                 return { "success": True, "data": None, "message": "Không có dữ liệu tồn kho hợp lệ để hiển thị." }

            inventory_df = pd.DataFrame(inventory_list)
            top_products_df = inventory_df.sort_values(by='total_value', ascending=False).head(10)
            low_stock_df = inventory_df[inventory_df['quantity'] < 10].sort_values(by='quantity')

            report_data = {
                'total_inventory_value': total_inventory_value,
                'total_inventory_items': total_inventory_items,
                'inventory_details_df': inventory_df,
                'top_products_by_value_df': top_products_df,
                'low_stock_items_df': low_stock_df
            }
            return { "success": True, "data": report_data }
        except Exception as e:
            logging.error(f"Lỗi khi tạo báo cáo tồn kho: {e}")
            if "index" in str(e).lower():
                return { "success": False, "message": f"Lỗi truy vấn Firestore, có thể bạn thiếu index. Chi tiết: {e}" }
            return { "success": False, "message": str(e) }

    def get_revenue_report(self, start_date: datetime, end_date: datetime, branch_ids: list):
        try:
            query = self.orders_collection.where('status', '==', 'COMPLETED') \
                                       .where('created_at', '>=', start_date.isoformat()) \
                                       .where('created_at', '<=', end_date.isoformat())
            if branch_ids:
                query = query.where('branch_id', 'in', branch_ids)
            orders = query.stream()

            revenue_data = []
            top_products = {}
            total_revenue = 0
            total_cogs = 0
            total_orders = 0

            for order in orders:
                order_data = order.to_dict()
                created_at = pd.to_datetime(order_data['created_at'])
                total_revenue += order_data.get('grand_total', 0)
                total_cogs += order_data.get('total_cogs', 0)
                total_orders += 1
                revenue_data.append({'date': created_at.date(), 'revenue': order_data.get('grand_total', 0)})
                for item in order_data.get('line_items', []):
                    prod_id = item['product_id']
                    if prod_id not in top_products:
                        top_products[prod_id] = {'name': item['product_name'], 'revenue': 0, 'profit': 0, 'quantity': 0}
                    item_revenue = item['final_price'] * item['quantity']
                    item_cogs = item['cost_price'] * item['quantity']
                    item_profit = item_revenue - item_cogs
                    top_products[prod_id]['revenue'] += item_revenue
                    top_products[prod_id]['profit'] += item_profit
                    top_products[prod_id]['quantity'] += item['quantity']

            if not revenue_data:
                return False, None, "Không có đơn hàng nào trong khoảng thời gian này."

            gross_profit = total_revenue - total_cogs
            revenue_df = pd.DataFrame(revenue_data).groupby('date')['revenue'].sum().reset_index()
            revenue_df = revenue_df.set_index('date')
            top_products_df = pd.DataFrame.from_dict(top_products, orient='index').sort_values(by='revenue', ascending=False)
            top_products_df.rename(columns={'name': 'Tên sản phẩm', 'revenue': 'Doanh thu', 'profit': 'Lợi nhuận', 'quantity': 'Số lượng'}, inplace=True)

            report = {
                'total_revenue': total_revenue,
                'total_profit': gross_profit,
                'total_orders': total_orders,
                'average_order_value': total_revenue / total_orders if total_orders > 0 else 0,
                'revenue_by_day': revenue_df,
                'top_products_by_revenue': top_products_df.head(5)
            }
            return True, report, "Tạo báo cáo thành công"
        except Exception as e:
            logging.error(f"Lỗi khi lấy báo cáo doanh thu: {e}")
            return False, None, str(e)

    def get_profit_loss_statement(self, start_date: datetime, end_date: datetime, branch_id: str = None):
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
        op_expenses_by_group = {}
        op_expenses_by_classification = {}
        total_op_expenses = 0

        cost_filters = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
        }
        if branch_id:
            cost_filters['branch_id'] = branch_id

        cost_entries = self.cost_mgr.query_cost_entries(filters=cost_filters)
        cost_groups_raw = self.cost_mgr.get_all_category_items('cost_groups')
        cost_groups = {g['id']: g['group_name'] for g in cost_groups_raw}

        for entry in cost_entries:
            cost_in_period = 0
            if entry.get('is_amortized') and entry.get('amortization_months', 0) > 0:
                cost_in_period = self._calculate_amortized_cost_for_period(entry, start_date, end_date)
            elif not entry.get('is_amortized'):
                entry_date = datetime.fromisoformat(entry['entry_date']).replace(tzinfo=None)
                if start_date <= entry_date <= end_date:
                    cost_in_period = entry['amount']

            if cost_in_period > 0:
                total_op_expenses += cost_in_period
                group_name = cost_groups.get(entry.get('group_id'), "Chưa phân loại")
                op_expenses_by_group[group_name] = op_expenses_by_group.get(group_name, 0) + cost_in_period
                classification_key = entry.get('classification', 'UNCATEGORIZED')
                op_expenses_by_classification[classification_key] = op_expenses_by_classification.get(classification_key, 0) + cost_in_period

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
            "operating_expenses_by_classification": op_expenses_by_classification,
            "total_operating_expenses": total_op_expenses,
            "net_profit": net_profit
        }

    def _calculate_amortized_cost_for_period(self, cost_entry, report_start, report_end) -> float:
        try:
            amount = float(cost_entry['amount'])
            months = int(cost_entry['amortization_months'])
            entry_date = datetime.fromisoformat(cost_entry['entry_date']).replace(tzinfo=None)

            if months <= 0: return 0

            monthly_cost = amount / months
            total_cost_in_period = 0

            for i in range(months):
                amortization_month_start = (entry_date + relativedelta(months=i)).replace(day=1)
                if amortization_month_start > report_end: continue
                amortization_month_end = amortization_month_start + relativedelta(months=1) - timedelta(days=1)
                if amortization_month_end < report_start: continue
                total_cost_in_period += monthly_cost
            return total_cost_in_period
        except (ValueError, TypeError, KeyError) as e:
            logging.error(f"Error calculating amortization for entry {cost_entry.get('id')}: {e}")
            return 0

# Apply decorators after the class is defined
ReportManager.get_profit_loss_statement = st.cache_data(ttl=900, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_profit_loss_statement)
ReportManager.get_inventory_report = st.cache_data(ttl=300, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_inventory_report)
ReportManager.get_profit_analysis_report = st.cache_data(ttl=900, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_profit_analysis_report)
