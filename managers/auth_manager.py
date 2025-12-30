
import bcrypt
import uuid
from datetime import datetime
import streamlit as st
import pyrebase 

class AuthManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.auth = firebase_client.auth 
        self.users_col = self.db.collection('users')

    def _hash_password(self, password):
        if not password:
            return None
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _check_password(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def check_cookie_and_re_auth(self):
        if 'user' in st.session_state and st.session_state.user is not None:
            return True

        try:
            id_token = st.experimental_get_query_params().get('idToken', [None])[0]
        except (AttributeError, KeyError):
            id_token = None

        if not id_token:
            return False

        try:
            user_info = self.auth.get_account_info(id_token)
            uid = user_info['users'][0]['localId']
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['uid'] = uid
                st.session_state['user'] = user_data
                return True
            else:
                st.experimental_set_query_params(idToken=None)
                return False
        except Exception as e:
            st.experimental_set_query_params(idToken=None)
            return False

    def login(self, username, password):
        normalized_username = username.lower()
        email = f"{normalized_username}@email.placeholder.com"

        # === BƯỚC 1: Thử đăng nhập bằng hệ thống mới (Firebase Auth) ===
        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            uid = user['localId']
            id_token = user['idToken']
            st.experimental_set_query_params(idToken=id_token)
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['uid'] = uid
                if user_data.get('active', False):
                    self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                    st.session_state['user'] = user_data
                    return user_data
            return None

        # === BƯỚC 2: Nếu hệ thống mới thất bại, thử hệ thống cũ (bcrypt) ===
        except Exception:
            # SỬA LỖI: Lấy tất cả user và so sánh trong Python để tránh lỗi case-sensitive
            all_users_stream = self.users_col.stream()
            found_user_doc = None
            for doc in all_users_stream:
                user_data_legacy = doc.to_dict()
                db_username = user_data_legacy.get('username')
                if db_username and db_username.lower() == normalized_username:
                    found_user_doc = doc
                    break

            if not found_user_doc:
                return None # Không tìm thấy username trong toàn bộ user

            user_data = found_user_doc.to_dict()
            hashed_password = user_data.get("password_hash")

            if not hashed_password:
                return None # User này không có password_hash, không phải hệ thống cũ

            if self._check_password(password, hashed_password):
                uid = found_user_doc.id
                user_data['uid'] = uid
                
                if user_data.get('active', False):
                    self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                    st.session_state['user'] = user_data
                    return user_data

            return None

    def logout(self):
        if 'user' in st.session_state:
            del st.session_state['user']
        st.experimental_set_query_params(idToken=None)
        st.rerun()

    def get_current_user_info(self):
        return st.session_state.get('user')

    def has_users(self):
        return len(self.users_col.limit(1).get()) > 0

    def list_users(self):
        docs = self.users_col.order_by("display_name").stream()
        users = []
        for doc in docs:
            user = doc.to_dict()
            user.pop('password_hash', None)
            user['uid'] = doc.id
            users.append(user)
        return users

    def create_user_record(self, data: dict, password: str):
        username = data.get('username')
        if not username:
            raise ValueError("Username là bắt buộc.")

        normalized_username = username.lower()
        data['username'] = normalized_username 
        email = f"{normalized_username}@email.placeholder.com"
        
        try:
            user_record = self.auth.create_user_with_email_and_password(email, password)
            uid = user_record['localId']
        except Exception as e:
            if "EMAIL_EXISTS" in str(e):
                raise ValueError(f"Lỗi: Username '{normalized_username}' đã được sử dụng.")
            raise e

        data['uid'] = uid
        data['created_at'] = datetime.now().isoformat()
        data['active'] = True
        if 'branch_ids' not in data:
            data['branch_ids'] = []
        
        data.pop('password_hash', None)

        self.users_col.document(uid).set(data)
        return data

    def update_user_record(self, uid: str, data: dict, new_password: str = None):
        if new_password:
            self.auth.update_user(uid, password=new_password)
        
        if 'username' in data:
            data['username'] = data['username'].lower()

        data['updated_at'] = datetime.now().isoformat()
        self.users_col.document(uid).update(data)
        return True
