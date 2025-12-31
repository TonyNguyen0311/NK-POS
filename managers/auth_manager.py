
import bcrypt
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import streamlit as st
import pyrebase
from streamlit_cookies_manager import EncryptedCookieManager
import requests

# Role hierarchy definition (lowest to highest)
ROLES = ['staff', 'supervisor', 'manager', 'admin']
ALLOWED_TO_CREATE = {
    'admin': ['staff', 'supervisor', 'manager', 'admin'],
    'manager': ['staff', 'supervisor'],
    'supervisor': ['staff'],
    'staff': []
}

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
        try:
            session_query = self.sessions_col.where("token_hash", "==", token_hash).limit(1).stream()
            session_docs = list(session_query)

            if not session_docs:
                self.logout()
                return False

            session_doc = session_docs[0]
            session_data = session_doc.to_dict()

            expires_at = session_data.get('expires_at')
            
            if session_data.get('revoked', False) or datetime.now(timezone.utc) > expires_at:
                self.logout()
                return False

            uid = session_data.get('user_id')
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

            self.sessions_col.document(session_doc.id).update({'last_seen': datetime.now(timezone.utc)})
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
                self.users_col.document(uid).update({"last_login": datetime.now(timezone.utc).isoformat()})
                st.session_state['user'] = user_data

                if remember_me:
                    self._create_session(uid)

                return ('SUCCESS', user_data)
            else:
                self.logout() 
                return ('FAILED', "Đăng nhập thất bại. Dữ liệu người dùng không tồn tại.")

        except requests.exceptions.HTTPError as e:
            try:
                error_json = e.response.json()['error']
                error_message = error_json['message']
            except (ValueError, KeyError):
                return ('FAILED', f"Lỗi không xác định từ Firebase: {e}")

            if error_message in ['INVALID_PASSWORD', 'EMAIL_NOT_FOUND']:
                legacy_user_query = self.users_col.where("username", "==", normalized_username).limit(1).stream()
                legacy_user_docs = list(legacy_user_query)
                if not legacy_user_docs:
                    return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")
                
                legacy_user_doc = legacy_user_docs[0]
                legacy_user_data = legacy_user_doc.to_dict()
                password_hash = legacy_user_data.get('password_hash')

                if not password_hash or not self._check_password(password, password_hash):
                    return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")
                
                try:
                    new_user_record = self.auth.create_user_with_email_and_password(email, password)
                    new_uid = new_user_record['localId']

                    legacy_user_data.pop('password_hash', None) 
                    legacy_user_data['uid'] = new_uid
                    legacy_user_data['updated_at'] = datetime.now(timezone.utc).isoformat()
                    if 'created_at' not in legacy_user_data:
                         legacy_user_data['created_at'] = datetime.now(timezone.utc).isoformat()
                    
                    self.users_col.document(new_uid).set(legacy_user_data)
                    self.users_col.document(legacy_user_doc.id).delete()
                    return ('MIGRATED', "Tài khoản của bạn đã được nâng cấp. Vui lòng đăng nhập lại.")

                except requests.exceptions.HTTPError as migrate_e:
                    migrate_error_msg = migrate_e.response.json().get('error', {}).get('message', '')
                    if migrate_error_msg == 'EMAIL_EXISTS':
                        return ('FAILED', "Tài khoản đã tồn tại. Vui lòng thử đăng nhập lại.")
                    return ('FAILED', f"Lỗi nâng cấp tài khoản: {migrate_error_msg}")
                except Exception as migrate_e_general:
                    return ('FAILED', f"Lỗi hệ thống khi nâng cấp tài khoản: {migrate_e_general}")
            
            return ('FAILED', f"Lỗi xác thực: {error_message}")
        except Exception as e:
            return ('FAILED', f"Đã xảy ra lỗi không mong muốn: {e}")

    def _create_session(self, user_id):
        session_token = secrets.token_hex(32)
        token_hash = self._hash_token(session_token)
        
        session_config = self.settings_mgr.get_session_config()
        persistence_days = session_config.get('persistence_days', 7)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=persistence_days)
        
        user_agent = st.query_params.get('user_agent', '')

        session_data = {
            'user_id': user_id,
            'token_hash': token_hash,
            'created_at': now,
            'last_seen': now,
            'expires_at': expires_at,
            'revoked': False,
            'user_agent': user_agent
        }
        self.sessions_col.add(session_data)
        self.cookies['session_token'] = session_token
        self.cookies.save()

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
            self.cookies.save()

        st.query_params.clear()

    def get_current_user_info(self):
        return st.session_state.get('user')

    def has_users(self):
        docs = self.users_col.limit(1).get()
        return len(list(docs)) > 0

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
        actor = self.get_current_user_info()
        if not actor:
            raise PermissionError("Không thể xác thực người dùng. Vui lòng đăng nhập lại.")

        actor_role = actor.get('role', 'staff').lower()
        new_user_role = data.get('role', 'staff').lower()

        allowed_to_create_roles = ALLOWED_TO_CREATE.get(actor_role, [])
        if new_user_role not in allowed_to_create_roles:
            raise PermissionError(f"Vai trò của bạn ({actor_role}) không có quyền tạo người dùng với vai trò '{new_user_role}'.")

        username = data.get('username')
        if not username:
            raise ValueError("Username là bắt buộc.")
        normalized_username = username.lower()
        data['username'] = normalized_username 
        email = f"{normalized_username}@email.placeholder.com"
        
        try:
            user_record = self.auth.create_user_with_email_and_password(email, password)
            uid = user_record['localId']
        except requests.exceptions.HTTPError as e:
            try:
                error_json = e.response.json()['error']
                if error_json['message'] == "EMAIL_EXISTS":
                    raise ValueError(f"Lỗi: Username '{normalized_username}' đã được sử dụng.")
            except (ValueError, KeyError):
                pass
            raise e

        data['uid'] = uid
        data['created_at'] = datetime.now(timezone.utc).isoformat()
        data['creator_id'] = actor.get('uid')
        data['active'] = True
        if 'branch_ids' not in data:
            data['branch_ids'] = []
        
        data.pop('password_hash', None)
        self.users_col.document(uid).set(data)
        return data

    def update_user_record(self, uid: str, data: dict, new_password: str = None):
        actor = self.get_current_user_info()
        if not actor:
            raise PermissionError("Không thể xác thực người dùng. Vui lòng đăng nhập lại.")
        
        actor_uid = actor.get('uid')
        actor_role = actor.get('role', 'staff').lower()
        actor_level = ROLES.index(actor_role)

        target_user_doc = self.users_col.document(uid).get()
        if not target_user_doc.exists:
            raise ValueError("Người dùng không tồn tại.")
        
        target_user_data = target_user_doc.to_dict()
        target_user_role = target_user_data.get('role', 'staff').lower()
        target_level = ROLES.index(target_user_role)

        if actor_uid != uid and actor_level <= target_level and actor_role != 'admin':
            raise PermissionError("Bạn không có quyền chỉnh sửa người dùng có vai trò ngang hoặc cao hơn.")

        if 'role' in data:
            new_role = data['role'].lower()
            if ROLES.index(new_role) > actor_level:
                raise PermissionError(f"Bạn không thể gán vai trò ('{new_role}') cao hơn vai trò của chính mình.")
            if actor_uid == uid and new_role != actor_role and actor_role != 'admin':
                raise PermissionError("Bạn không thể tự thay đổi vai trò của chính mình.")

        if new_password:
            self.auth.update_user_account(uid, password=new_password)

        if 'username' in data:
            data['username'] = data['username'].lower()
        
        data['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.users_col.document(uid).update(data)
        return True
