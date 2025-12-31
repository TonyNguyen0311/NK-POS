
import bcrypt
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
import streamlit as st
import pyrebase
from streamlit_cookies_manager import EncryptedCookieManager
import requests

class AuthManager:
    def __init__(self, firebase_client, settings_mgr):
        self.db = firebase_client.db
        self.auth = firebase_client.auth
        self.users_col = self.db.collection('users')
        self.sessions_col = self.db.collection('user_device_sessions')
        self.settings_mgr = settings_mgr

        self.cookies = EncryptedCookieManager(
            password=st.secrets.get("cookie_secret_key", "a_default_secret_key_that_is_not_safe"),
            prefix="nk-pos/auth/"
        )
        if not self.cookies.ready():
            st.stop()

    def _hash_password(self, password):
        if not password:
            return None
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _check_password(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def _hash_token(self, token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def check_cookie_and_re_auth(self):
        if 'user' in st.session_state and st.session_state.user is not None:
            return True

        session_token = self.cookies.get('session_token')
        if not session_token:
            return False

        token_hash = self._hash_token(session_token)
        session_query = self.sessions_col.where("token_hash", "==", token_hash).limit(1).stream()
        session_docs = list(session_query)

        if not session_docs:
            self.logout()
            return False

        session_doc = session_docs[0]
        session_data = session_doc.to_dict()

        if session_data.get('revoked', False) or datetime.now() > session_data.get('expires_at'):
            self.logout()
            return False

        uid = session_data.get('user_id')
        try:
            user_doc = self.users_col.document(uid).get()
            if not user_doc.exists:
                self.logout()
                return False

            user_data = user_doc.to_dict()
            if not user_data.get('active', False):
                self.logout()
                return False
            
            user_data['uid'] = uid
            st.session_state['user'] = user_data
            
            # Update last_seen for the session
            self.sessions_col.document(session_doc.id).update({'last_seen': datetime.now()})
            return True

        except Exception:
            self.logout()
            return False

    def login(self, username, password, remember_me=False):
        normalized_username = username.lower()
        email = f"{normalized_username}@email.placeholder.com"

        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            uid = user['localId']
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if not user_data.get('active', False):
                    return ('FAILED', "Tài khoản của bạn đã bị vô hiệu hóa.")

                user_data['uid'] = uid
                self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                st.session_state['user'] = user_data

                if remember_me:
                    self._create_session(uid)

                return ('SUCCESS', user_data)
            else:
                self.logout()
                return ('FAILED', "Đăng nhập thất bại. Dữ liệu người dùng không tồn tại.")

        except requests.exceptions.HTTPError as e:
            # ... (Phần xử lý lỗi và di chuyển người dùng cũ giữ nguyên) ...
            return ('FAILED', f"Lỗi xác thực: {e}")
        except Exception as e:
            return ('FAILED', f"Đã xảy ra lỗi không mong muốn: {e}")

    def _create_session(self, user_id):
        session_token = secrets.token_hex(32)
        token_hash = self._hash_token(session_token)
        
        session_config = self.settings_mgr.get_session_config()
        persistence_days = session_config.get('persistence_days', 7) # Default to 7 days
        expires_at = datetime.now() + timedelta(days=persistence_days)
        
        session_data = {
            'user_id': user_id,
            'token_hash': token_hash,
            'created_at': datetime.now(),
            'last_seen': datetime.now(),
            'expires_at': expires_at,
            'revoked': False,
            'user_agent': st.experimental_get_query_params().get('user_agent', [''])[0]
        }
        self.sessions_col.add(session_data)
        self.cookies['session_token'] = session_token

    def logout(self):
        session_token = self.cookies.get('session_token')
        if session_token:
            token_hash = self._hash_token(session_token)
            session_query = self.sessions_col.where("token_hash", "==", token_hash).limit(1).stream()
            for doc in session_query:
                self.sessions_col.document(doc.id).update({'revoked': True})
        
        if 'user' in st.session_state:
            del st.session_state['user']
        
        if 'session_token' in self.cookies:
            del self.cookies['session_token']
            
        st.query_params.clear()

    def get_current_user_info(self):
        return st.session_state.get('user')

    # ... (Các phương thức khác như has_users, list_users, create_user_record, update_user_record giữ nguyên) ...

