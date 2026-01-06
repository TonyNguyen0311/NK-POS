
import streamlit as st
import logging

class AdminManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db

    def _delete_collection_in_batches(self, coll_ref, batch_size):
        """
        Deletes all documents in a collection in batches to avoid memory/timeout issues.
        """
        docs = coll_ref.limit(batch_size).stream()
        deleted_count = 0
        
        while True:
            batch = self.db.batch()
            doc_count_in_batch = 0
            
            for doc in docs:
                batch.delete(doc.reference)
                doc_count_in_batch += 1
            
            if doc_count_in_batch == 0:
                break  # No more documents to delete
            
            batch.commit()
            deleted_count += doc_count_in_batch
            logging.info(f"Deleted a batch of {doc_count_in_batch} documents from {coll_ref.id}.")

            # Fetch the next batch
            docs = coll_ref.limit(batch_size).stream()
            
        return deleted_count

    # @st.cache_data(ttl=15) # Use a short cache to prevent accidental rapid-fire calls
    def clear_inventory_data(self):
        """
        DANGER: Deletes all documents from 'inventory', 'inventory_vouchers', 
        and 'inventory_transactions'. This is irreversible.
        Returns a dictionary with counts of deleted documents.
        """
        collections_to_clear = [
            'inventory',
            'inventory_vouchers',
            'inventory_transactions'
        ]
        
        deleted_counts = {}
        
        for coll_name in collections_to_clear:
            try:
                coll_ref = self.db.collection(coll_name)
                logging.info(f"Starting to clear collection: {coll_name}")
                # Using a batch size of 200 (Firestore's max is 500)
                count = self._delete_collection_in_batches(coll_ref, 200)
                deleted_counts[coll_name] = count
                logging.info(f"Successfully cleared {coll_name}, deleted {count} documents.")
            except Exception as e:
                logging.error(f"Error clearing collection {coll_name}: {e}")
                deleted_counts[coll_name] = f"Error: {e}"

        # Clear Streamlit's data caches after deletion to reflect changes
        st.cache_data.clear()
        
        return deleted_counts

