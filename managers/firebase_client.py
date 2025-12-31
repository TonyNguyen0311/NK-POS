
import firebase_admin
from firebase_admin import credentials, firestore, storage
import pyrebase
import json
import streamlit as st

class FirebaseClient:
    def __init__(self, credentials_path, pyrebase_config):
        """
        Initializes Firebase connection using a credentials file path.
        """
        if not firebase_admin._apps:
            try:
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': pyrebase_config.get("storageBucket")
                })
            except Exception as e:
                st.error(f"Error initializing Firebase Admin SDK: {e}")
                raise # Re-raise the exception to be caught by the caller

        self.db = firestore.client()
        self.bucket = storage.bucket()
        
        # Initialize Pyrebase for Authentication
        if not hasattr(st.session_state, 'pyrebase_app'):
            try:
                st.session_state.pyrebase_app = pyrebase.initialize_app(pyrebase_config)
            except Exception as e:
                st.error(f"Error initializing Pyrebase: {e}")
                raise
        
        self.auth = st.session_state.pyrebase_app.auth()

    def check_connection(self):
        try:
            if self.db and self.auth:
                return True
            return False
        except Exception as e:
            st.error(f"Lỗi kết nối Firebase: {e}")
            return False
