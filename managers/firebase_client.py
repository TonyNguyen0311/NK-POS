import firebase_admin
from firebase_admin import credentials, firestore
import pyrebase # Thêm pyrebase
import json
import streamlit as st

class FirebaseClient:
    def __init__(self, credentials_input, pyrebase_config, storage_bucket=None):
        """
        Khởi tạo kết nối Firebase, bao gồm cả Firestore (admin) và Auth (pyrebase).
        """
        # --- Khởi tạo Firebase Admin (cho Firestore) ---
        if not firebase_admin._apps:
            if isinstance(credentials_input, dict):
                cred = credentials.Certificate(credentials_input)
            else:
                cred = credentials.Certificate(credentials_input)
            
            firebase_admin.initialize_app(cred)

        self.db = firestore.client()
        
        # --- Khởi tạo Pyrebase (cho Authentication) ---
        # Pyrebase không tự quản lý việc khởi tạo duy nhất, nhưng chúng ta sẽ khởi tạo nó ở đây
        # để gom tất cả client vào một nơi.
        firebase = pyrebase.initialize_app(pyrebase_config)
        self.auth = firebase.auth() # Tạo thuộc tính auth
        
        self.bucket = None # Tắt Storage

    def check_connection(self):
        try:
            # Kiểm tra cả hai kết nối nếu cần
            if self.db and self.auth:
                return True
            return False
        except Exception as e:
            st.error(f"Lỗi kết nối Firebase: {e}")
            return False
