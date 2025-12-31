
import bcrypt
import uuid
import json
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

    def check_cookie_and_re_auth(self):
        if 'user' in st.session_state and st.session_state.user is not None:
            return True

        cookie_data_str = self.cookies.get('refresh_token')
        if not cookie_data_str:
            return False

        try:
            cookie_data = json.loads(cookie_data_str)
            expires_at_str = cookie_data.get('expires_at')
            refresh_token = cookie_data.get('token')

            if not expires_at_str or not refresh_token:
                self.logout()
                return False

            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                self.logout()
                return False

            user_session = self.auth.refresh(refresh_token)
            uid = user_session['userId']
            
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
            return True

        except (json.JSONDecodeError, TypeError, KeyError):
            self.logout()
            return False
        except Exception:
            self.logout()
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
                if not user_data.get('active', False):
                    return ('FAILED', "Tài khoản của bạn đã bị vô hiệu hóa.")

                user_data['uid'] = uid
                self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                st.session_state['user'] = user_data

                session_config = self.settings_mgr.get_session_config()
                persistence_days = session_config.get('persistence_days', 0)
                if persistence_days > 0 and 'refreshToken' in user:
                    expires_at = datetime.now() + timedelta(days=persistence_days)
                    cookie_data = {
                        'token': user['refreshToken'],
                        'expires_at': expires_at.isoformat()
                    }
                    self.cookies['refresh_token'] = json.dumps(cookie_data)

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
                    legacy_user_data['updated_at'] = datetime.now().isoformat()
                    if 'created_at' not in legacy_user_data:
                         legacy_user_data['created_at'] = datetime.now().isoformat()
                    
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

    def logout(self):
        if 'user' in st.session_state:
            del st.session_state['user']
        
        if 'refresh_token' in self.cookies:
            self.cookies.delete('refresh_token')
            
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
