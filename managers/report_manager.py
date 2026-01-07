
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
        self.transactions_collection = self.db.collection('transactions')
        self.products_collection = self.db.collection('products')
        self.inventory_collection = self.db.collection('inventory')
        self.categories_collection = self.db.collection('ProductCategories')

    def get_profit_loss_statement(self, start_date: datetime, end_date: datetime, branch_ids: list = None):
        """
        Tạo báo cáo Lãi và Lỗ từ một nguồn dữ liệu duy nhất: collection 'transactions'.
        """
        try:
            query = self.transactions_collection \
                         .where('created_at', '>=', start_date) \
                         .where('created_at', '<=', end_date)
            
            if branch_ids and isinstance(branch_ids, list) and len(branch_ids) > 0:
                query = query.where('branch_id', 'in', branch_ids)
            
            all_transactions = query.stream()

            total_revenue = 0.0
            total_cogs = 0.0
            total_operating_expenses = 0.0
            order_count = 0
            op_expenses_by_group = {}

            cost_groups_raw = self.cost_mgr.get_all_category_items('cost_groups')
            cost_groups = {g['id']: g['group_name'] for g in cost_groups_raw}

            for trans in all_transactions:
                trans_data = trans.to_dict()
                trans_type = trans_data.get('type')

                if trans_type == 'SALE':
                    total_revenue += trans_data.get('total_amount', 0)
                    total_cogs += trans_data.get('total_cogs', 0)
                    order_count += 1
                
                elif trans_type == 'EXPENSE':
                    expense_amount = abs(trans_data.get('total_amount', 0))
                    total_operating_expenses += expense_amount
                    group_id = trans_data.get('expense_details', {}).get('group_id')
                    group_name = cost_groups.get(group_id, "Chưa phân loại")
                    op_expenses_by_group[group_name] = op_expenses_by_group.get(group_name, 0) + expense_amount

            gross_profit = total_revenue - total_cogs
            net_profit = gross_profit - total_operating_expenses

            return {
                "success": True,
                "data": {
                    "start_date": start_date.strftime('%Y-%m-%d'),
                    "end_date": end_date.strftime('%Y-%m-%d'),
                    "branch_ids": branch_ids,
                    "order_count": order_count,
                    "total_revenue": total_revenue,
                    "total_cogs": total_cogs,
                    "gross_profit": gross_profit,
                    "operating_expenses_by_group": op_expenses_by_group,
                    "total_operating_expenses": total_operating_expenses,
                    "net_profit": net_profit
                }
            }
        except Exception as e:
            logging.error(f"Lỗi khi tạo báo cáo P&L: {e}")
            return {"success": False, "message": f"Đã xảy ra lỗi: {e}"}

    def get_profit_analysis_report(self, start_date: datetime, end_date: datetime, branch_ids: list):
        try:
            products_snapshot = self.products_collection.stream()
            product_details = {p.id: p.to_dict() for p in products_snapshot}
            categories_snapshot = self.categories_collection.stream()
            category_details = {c.id: c.to_dict().get('category_name', 'N/A') for c in categories_snapshot}

            query = self.transactions_collection.where('type', '==', 'SALE') \
                                               .where('created_at', '>=', start_date) \
                                               .where('created_at', '<=', end_date)
            if branch_ids:
                query = query.where('branch_id', 'in', branch_ids)
            transactions = query.stream()

            product_profit_data = {}
            for trans in transactions:
                trans_data = trans.to_dict()
                for item in trans_data.get('items', []):
                    sku = item.get('sku')
                    if not sku: continue
                    quantity = item.get('quantity', 0)
                    revenue = item.get('final_price', 0) * quantity
                    cogs = item.get('line_cogs', 0)
                    profit = revenue - cogs
                    if sku not in product_profit_data:
                        product_profit_data[sku] = {
                            'product_name': item.get('name', 'N/A'),
                            'category_id': product_details.get(sku, {}).get('category_id'),
                            'total_quantity_sold': 0, 'total_revenue': 0, 'total_profit': 0
                        }
                    product_profit_data[sku]['total_quantity_sold'] += quantity
                    product_profit_data[sku]['total_revenue'] += revenue
                    product_profit_data[sku]['total_profit'] += profit

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
        try:
            products_snapshot = self.products_collection.stream()
            product_details = {p.id: p.to_dict() for p in products_snapshot}

            inventory_query = self.inventory_collection
            if branch_ids:
                inventory_query = inventory_query.where('branch_id', 'in', branch_ids)
            inventory_docs = list(inventory_query.stream())

            if not inventory_docs:
                return {"success": True, "data": None, "message": "Không có dữ liệu tồn kho."}

            inventory_list = []
            for item_doc in inventory_docs:
                item_data = item_doc.to_dict()
                sku = item_data.get('sku')
                product_info = product_details.get(sku, {})
                inventory_list.append({
                    'product_id': sku,
                    'product_name': product_info.get('name', 'N/A'),
                    'branch_id': item_data.get('branch_id'),
                    'quantity': item_data.get('stock_quantity', 0),
                    'cost_price': item_data.get('average_cost', 0),
                    'total_value': item_data.get('stock_quantity', 0) * item_data.get('average_cost', 0)
                })
            
            if not inventory_list:
                 return { "success": True, "data": None, "message": "Không có dữ liệu tồn kho hợp lệ." }

            inventory_df = pd.DataFrame(inventory_list)
            return { "success": True, "data": inventory_df }
        except Exception as e:
            logging.error(f"Lỗi khi tạo báo cáo tồn kho: {e}")
            return { "success": False, "message": str(e) }

    def get_revenue_report(self, start_date: datetime, end_date: datetime, branch_ids: list):
        try:
            query = self.transactions_collection.where('type', '==', 'SALE') \
                                       .where('created_at', '>=', start_date) \
                                       .where('created_at', '<=', end_date)
            if branch_ids:
                query = query.where('branch_id', 'in', branch_ids)
            transactions = query.stream()

            revenue_data = []
            for trans in transactions:
                revenue_data.append(trans.to_dict())

            if not revenue_data:
                return {"success": True, "data": None, "message": "Không có giao dịch trong kỳ."}

            revenue_df = pd.DataFrame(revenue_data)
            return {"success": True, "data": revenue_df}
        except Exception as e:
            logging.error(f"Lỗi khi lấy báo cáo doanh thu: {e}")
            return {"success": False, "message": str(e)}

# Áp dụng decorator cho các phương thức sau khi class đã được định nghĩa
ReportManager.get_profit_loss_statement = st.cache_data(ttl=900, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_profit_loss_statement)
ReportManager.get_inventory_report = st.cache_data(ttl=300, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_inventory_report)
ReportManager.get_profit_analysis_report = st.cache_data(ttl=900, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_profit_analysis_report)
ReportManager.get_revenue_report = st.cache_data(ttl=900, hash_funcs={ReportManager: hash_report_manager})(ReportManager.get_revenue_report)
