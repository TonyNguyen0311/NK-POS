
import firebase_admin
from firebase_admin import credentials, storage
from google.cloud import firestore as google_cloud_firestore
from google.oauth2 import service_account
import pyrebase
import streamlit as st

class FirebaseClient:
    def __init__(self, credentials_info, pyrebase_config):
        """
        Initializes Firebase from a credentials dictionary.
        """
        project_id = credentials_info.get("project_id")
        if not project_id:
            raise ValueError("project_id not found in credentials.")

        if not firebase_admin._apps:
            try:
                # Use credentials.Certificate with the dictionary directly
                cred = credentials.Certificate(credentials_info)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': pyrebase_config.get("storageBucket")
                })
            except Exception as e:
                # Re-raise the exception to be caught by the caller with more context
                raise e

        # Initialize google-cloud-firestore client for database operations
        gcloud_credentials = service_account.Credentials.from_service_account_info(credentials_info)
        self.db = google_cloud_firestore.Client(project=project_id, credentials=gcloud_credentials)

        self.bucket = storage.bucket()
        
        # Initialize Pyrebase for Authentication
        if not hasattr(st.session_state, 'pyrebase_app'):
            try:
                st.session_state.pyrebase_app = pyrebase.initialize_app(pyrebase_config)
            except Exception as e:
                raise e
        
        self.auth = st.session_state.pyrebase_app.auth()

    def check_connection(self):
        try:
            if self.db and self.auth:
                return True
            return False
        except Exception as e:
            st.error(f"Lỗi kết nối Firebase: {e}")
            return False
