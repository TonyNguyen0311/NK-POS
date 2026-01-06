import streamlit as st
from datetime import datetime, time

class TransactionManager:
    def __init__(self, firebase_client):
        # FIX: Directly get the db instance from the firebase_client
        self.db = firebase_client.db

    def query_transactions(self, start_date, end_date, branch_id=None):
        """
        Queries transactions from Firestore based on a date range and optional branch_id.

        Args:
            start_date (date): The start of the date range.
            end_date (date): The end of the date range.
            branch_id (str, optional): The ID of the branch to filter by. Defaults to None.

        Returns:
            list: A list of transaction dictionaries.
        """
        # FIX: Use self.db directly instead of a non-existent method
        db = self.db
        
        # Combine date with time to create datetime objects for the query range
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)

        # Start with the base query on the collection
        query = db.collection('transactions')

        # Apply filters
        query = query.where('created_at', '>=', start_datetime)
        query = query.where('created_at', '<=', end_datetime)

        if branch_id:
            query = query.where('branch_id', '==', branch_id)
            
        # Order by creation time for chronological display
        query = query.order_by('created_at', direction='DESCENDING')

        try:
            docs = query.stream()
            transactions = []
            for doc in docs:
                txn_data = doc.to_dict()
                txn_data['id'] = doc.id
                
                # Convert Firestore Timestamp to Python datetime object if it's not already
                if 'created_at' in txn_data and hasattr(txn_data['created_at'], 'to_pydatetime'):
                    txn_data['created_at'] = txn_data['created_at'].to_pydatetime()
                
                transactions.append(txn_data)
            return transactions
        except Exception as e:
            # DEBUG: Provide a more informative error message
            st.error(f"Error querying Firestore: {e}")
            # Log the full traceback to the console for debugging
            print(f"[DEBUG] Firestore Query Error: {e}")
            import traceback
            traceback.print_exc()
            return []
