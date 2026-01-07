
import streamlit as st
import logging
import traceback
from google.cloud import firestore

class AdminManager:
    def __init__(self, firebase_client, inventory_mgr):
        self.db = firebase_client.db
        self.inventory_mgr = inventory_mgr

    # --------------------------------------------------------------------------
    # HÀM DỌN DẸP DỮ LIỆU
    # --------------------------------------------------------------------------

    def _delete_collection_in_batches(self, coll_ref, batch_size):
        deleted_count = 0
        last_doc = None
        while True:
            query = coll_ref.order_by('__name__').limit(batch_size)
            if last_doc:
                query = query.start_after(last_doc)
            docs = list(query.stream())
            if not docs:
                break
            batch = self.db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()
            deleted_count += len(docs)
            last_doc = docs[-1]
            logging.info(f"Đã xóa một lô {len(docs)} tài liệu từ {coll_ref.id}.")
        return deleted_count

    def clear_inventory_data(self):
        collections_to_clear = [
            'inventory',
            'inventory_vouchers',
            'inventory_transactions'
        ]
        deleted_counts = {}
        for coll_name in collections_to_clear:
            try:
                coll_ref = self.db.collection(coll_name)
                count = self._delete_collection_in_batches(coll_ref, 200)
                deleted_counts[coll_name] = count
            except Exception as e:
                deleted_counts[coll_name] = f"Lỗi: {e}"
        return deleted_counts

    # --------------------------------------------------------------------------
    # HÀM QUẢN LÝ GIAO DỊCH (REFACTORED FROM ORDERS)
    # --------------------------------------------------------------------------

    def get_all_transactions(self):
        """Lấy tất cả các giao dịch, sắp xếp theo ngày tạo mới nhất."""
        try:
            transactions_ref = self.db.collection('transactions')
            query = transactions_ref.order_by("created_at", direction=firestore.Query.DESCENDING)
            docs = query.stream()
            transactions = [doc.to_dict() for doc in docs]
            return transactions
        except Exception as e:
            st.error(f"Lỗi khi lấy danh sách giao dịch: {e}")
            logging.error(f"Error fetching transactions, potential index issue: {e}")
            return []

    def delete_transaction_and_revert_stock(self, transaction_id: str, current_user_id: str):
        """
        Xóa một giao dịch (chỉ loại SALE) và hoàn trả tồn kho.
        Hành động được thực hiện trong một Firestore transaction để đảm bảo tính toàn vẹn.
        """
        logging.info(f"--- BẮT ĐẦU XÓA GIAO DỊCH {transaction_id} ---")
        transaction_ref = self.db.collection('transactions').document(transaction_id)

        @firestore.transactional
        def _process_deletion_in_transaction(transaction):
            logging.info(f"[{transaction_id}] (Transaction) Bắt đầu.")
            # --- GIAI ĐOẠN ĐỌC ---
            trans_doc = transaction_ref.get(transaction=transaction)
            if not trans_doc.exists:
                raise Exception(f"Giao dịch {transaction_id} không tồn tại.")
            trans_data = trans_doc.to_dict()
            
            if trans_data.get('type') != 'SALE':
                raise Exception(f"Chỉ có thể xóa các giao dịch loại 'SALE'. Giao dịch này có loại '{trans_data.get('type')}'.")

            # --- GIAI ĐOẠN GHI ---
            branch_id = trans_data.get('branch_id')
            items = trans_data.get('items', [])

            if branch_id and items:
                logging.info(f"[{transaction_id}] (Transaction) Hoàn trả tồn kho.")
                for item in items:
                    sku = item.get('sku')
                    quantity = item.get('quantity')
                    if sku and quantity > 0:
                        self.inventory_mgr.update_inventory(
                            transaction=transaction,
                            sku=sku,
                            branch_id=branch_id,
                            delta=quantity, # Hoàn trả lại hàng
                            order_id=f"REVERT-{transaction_id}",
                            user_id=current_user_id
                        )
            
            logging.info(f"[{transaction_id}] (Transaction) Xóa giao dịch chính.")
            transaction.delete(transaction_ref)

        try:
            _process_deletion_in_transaction(self.db.transaction())
            logging.info(f"--- HOÀN TẤT XÓA GIAO DỊCH {transaction_id} ---")
            return True, f"Đã xóa thành công giao dịch {transaction_id} và hoàn trả tồn kho."
        except Exception as e:
            tb_str = traceback.format_exc()
            logging.error(f"LỖI KHI XÓA GIAO DỊCH {transaction_id}: {e}\n{tb_str}")
            return False, f"Lỗi trong quá trình xóa: {e}"
