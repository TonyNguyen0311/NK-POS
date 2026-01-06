
import streamlit as st
import logging

class AdminManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db

    def _delete_collection_in_batches(self, coll_ref, batch_size):
        """
        Deletes all documents in a collection using pagination (cursors) for robustness.
        This method orders documents by their ID and uses `start_after` to paginate,
        ensuring all documents are processed even during mutations.
        """
        deleted_count = 0
        last_doc = None # Acts as the cursor

        while True:
            # Base query ordered by document ID
            query = coll_ref.order_by('__name__').limit(batch_size)

            # If we have a cursor from the last batch, start after it
            if last_doc:
                query = query.start_after(last_doc)

            # Get the next batch of documents
            docs = list(query.stream())

            # If no documents are found, we are done
            if not docs:
                break

            # Create a write batch and add all delete operations
            batch = self.db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            
            # Commit the batch
            batch.commit()

            # Update the count and set the cursor for the next iteration
            deleted_count += len(docs)
            last_doc = docs[-1] # The last doc of the current batch is the cursor for the next one
            logging.info(f"Deleted a batch of {len(docs)} documents from {coll_ref.id}.")
        
        return deleted_count

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
                count = self._delete_collection_in_batches(coll_ref, 200) # Using a batch size of 200
                deleted_counts[coll_name] = count
                logging.info(f"Successfully cleared {coll_name}, deleted {count} documents.")
            except Exception as e:
                logging.error(f"Error clearing collection {coll_name}: {e}")
                deleted_counts[coll_name] = f"Error: {e}"

        # Clear Streamlit's data caches after deletion to reflect changes
        st.cache_data.clear()
        
        return deleted_counts

