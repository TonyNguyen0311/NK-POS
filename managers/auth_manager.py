
import bcrypt
import uuid
from datetime import datetime, timedelta
import streamlit as st
import pyrebase 
from streamlit_cookies_manager import EncryptedCookieManager

class AuthManager:
    def __init__(self, firebase_client, settings_mgr):
        self.db = firebase_client.db
        self.auth = firebase_client.auth 
        self.users_col = self.db.collection('users')
        self.settings_mgr = settings_mgr

        # Khởi tạo cookie manager. Yêu cầu phải có secret key trong st.secrets
        # Ví dụ: trong file .streamlit/secrets.toml, thêm dòng: 
        # cookie_secret_key = "ABCDEF1234567890"
        # Bạn nên tự tạo một chuỗi ngẫu nhiên, dài và an toàn cho khóa này.
        self.cookies = EncryptedCookieManager(
            secret=st.secrets.get("cookie_secret_key", "a_default_secret_key_that_is_not_safe"),
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

    def check_cookie_and_re_auth(self):
        """Kiểm tra cookie và tự động tái xác thực.
        Ưu tiên 1: Session state (người dùng vừa đăng nhập).
        Ưu tiên 2: Cookie (người dùng quay lại ứng dụng).
        """
        if 'user' in st.session_state and st.session_state.user is not None:
            return True

        refresh_token = self.cookies.get('refresh_token')
        if not refresh_token:
            return False

        try:
            # Dùng refresh token để lấy id token mới
            user_session = self.auth.refresh(refresh_token)
            uid = user_session['userId']
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                # Kiểm tra lại xem user còn active không
                if not user_data.get('active', False):
                    self.cookies.delete('refresh_token') # Dọn dẹp cookie
                    return False
                
                user_data['uid'] = uid
                st.session_state['user'] = user_data
                return True
            else:
                # User đã bị xóa khỏi hệ thống, dọn dẹp cookie
                self.cookies.delete('refresh_token')
                return False
        except Exception as e:
            # Refresh token hết hạn hoặc không hợp lệ
            self.cookies.delete('refresh_token')
            return False

    def login(self, username, password):
        normalized_username = username.lower()
        email = f"{normalized_username}@email.placeholder.com"

        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            uid = user['localId']
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['uid'] = uid
                if user_data.get('active', False):
                    self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                    st.session_state['user'] = user_data

                    # --- LOGIC GHI NHỚ ĐĂNG NHẬP BẰNG COOKIE ---
                    session_config = self.settings_mgr.get_session_config()
                    persistence_days = session_config.get('persistence_days', 0)

                    if persistence_days > 0 and 'refreshToken' in user:
                        self.cookies.set(
                            'refresh_token',
                            user['refreshToken'],
                            expires_at=datetime.now() + timedelta(days=persistence_days)
                        )
                    # --- KẾT THÚC LOGIC COOKIE ---
                    return user_data
            return None

        except Exception:
            # Logic fallback cho user cũ (bcrypt), không hỗ trợ ghi nhớ đăng nhập
            all_users_stream = self.users_col.stream()
            found_user_doc = None
            for doc in all_users_stream:
                user_data_legacy = doc.to_dict()
                db_username = user_data_legacy.get('username')
                if db_username and db_username.lower() == normalized_username:
                    found_user_doc = doc
                    break

            if not found_user_doc or not self._check_password(password, found_user_doc.to_dict().get("password_hash", "")):
                return None

            user_data = found_user_doc.to_dict()
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
        
        # Xóa cookie để chấm dứt phiên ghi nhớ
        self.cookies.delete('refresh_token')
        
        st.query_params.clear()
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
