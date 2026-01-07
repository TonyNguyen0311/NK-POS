
import streamlit as st
import logging
import traceback
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

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
    # HÀM QUẢN LÝ ĐƠN HÀNG
    # --------------------------------------------------------------------------

    def get_all_orders(self):
        try:
            orders_ref = self.db.collection('orders')
            query = orders_ref.order_by("created_at", direction=firestore.Query.DESCENDING)
            docs = query.stream()
            orders = [doc.to_dict() for doc in docs]
            return orders
        except Exception as e:
            st.error(f"Lỗi khi lấy danh sách đơn hàng: {e}")
            return []

    def delete_order_and_revert_stock(self, order_id: str, current_user_id: str):
        """
        Xóa một đơn hàng, các giao dịch tài chính liên quan và hoàn trả tồn kho.
        Hành động được thực hiện trong một transaction để đảm bảo tính toàn vẹn dữ liệu.
        Phiên bản này có logging chi tiết để gỡ lỗi.
        """
        logging.info(f"--- BẮT ĐẦU XÓA ĐƠN HÀNG {order_id} ---")
        order_ref = self.db.collection('orders').document(order_id)
        txns_query = self.db.collection('transactions').where(filter=FieldFilter("order_id", "==", order_id))

        try:
            transaction = self.db.transaction()
            @firestore.transactional
            def _process_deletion(transaction, order_ref, txns_query, current_user_id):
                # --- GIAI ĐOẠN ĐỌC (READ PHASE) ---
                logging.info(f"[{order_id}] (Trong transaction) Giai đoạn ĐỌC: Bắt đầu.")
                
                # 1. Đọc tài liệu đơn hàng
                logging.info(f"[{order_id}] (Trong transaction) Đọc tài liệu đơn hàng từ ref: {order_ref.path}")
                order_doc = transaction.get(order_ref)
                logging.info(f"[{order_id}] (Trong transaction) Kiểu dữ liệu của order_doc: {type(order_doc)}")
                
                if not order_doc.exists:
                    logging.warning(f"[{order_id}] (Trong transaction) Đơn hàng không tồn tại. Dừng quá trình xóa.")
                    raise Exception(f"Không tìm thấy đơn hàng {order_id}.")

                logging.info(f"[{order_id}] (Trong transaction) Đã tìm thấy đơn hàng. Tiếp tục đọc giao dịch liên quan.")
                # 2. Đọc các tài liệu giao dịch tài chính liên quan.
                # `transaction.get(query)` returns a generator of snapshots
                related_txn_docs = list(transaction.get(txns_query))
                logging.info(f"[{order_id}] (Trong transaction) Đã đọc {len(related_txn_docs)} giao dịch tài chính liên quan.")

                # --- GIAI ĐOẠN GHI (WRITE PHASE) ---
                logging.info(f"[{order_id}] (Trong transaction) Giai đoạn GHI: Bắt đầu.")
                order_data = order_doc.to_dict()
                branch_id = order_data.get('branch_id')
                items = order_data.get('items', [])

                # 3. Hoàn trả tồn kho (thao tác GHI)
                if branch_id and items:
                    logging.info(f"[{order_id}] (Trong transaction) Chuẩn bị hoàn trả {len(items)} mặt hàng về chi nhánh {branch_id}.")
                    for item in items:
                        sku = item.get('sku')
                        quantity = item.get('quantity')
                        if sku and quantity > 0:
                            self.inventory_mgr.update_inventory(
                                transaction=transaction,
                                sku=sku,
                                branch_id=branch_id,
                                delta=quantity,
                                order_id=f"REVERT-{order_id}",
                                user_id=current_user_id
                            )
                
                # 4. Xóa các tài liệu giao dịch tài chính đã tìm thấy (thao tác GHI)
                for doc in related_txn_docs:
                    transaction.delete(doc.reference)

                # 5. Xóa chính đơn hàng đó (thao tác GHI)
                transaction.delete(order_ref)

            _process_deletion(transaction, order_ref, txns_query, current_user_id)
            
            logging.info(f"--- HOÀN TẤT XÓA ĐƠN HÀNG {order_id} ---")
            return True, f"Đã xóa thành công đơn hàng {order_id}."

        except Exception as e:
            tb_str = traceback.format_exc()
            logging.error(f"LỖI NGHIÊM TRỌNG KHI XÓA ĐƠN HÀNG {order_id}: {e}\nFULL TRACEBACK:\n{tb_str}")
            return False, f"Lỗi trong quá trình xóa: {e}"
