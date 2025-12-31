
import bcrypt
import uuid
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

        refresh_token = self.cookies.get('refresh_token')
        if not refresh_token:
            return False

        try:
            user_session = self.auth.refresh(refresh_token)
            uid = user_session['userId']
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if not user_data.get('active', False):
                    self.cookies.delete('refresh_token') 
                    return False
                
                user_data['uid'] = uid
                st.session_state['user'] = user_data
                return True
            else:
                self.cookies.delete('refresh_token')
                return False
        except Exception:
            self.cookies.delete('refresh_token')
            return False

    def login(self, username, password):
        """
        Logs in a user or migrates a legacy user.

        Returns:
            tuple: A tuple containing the status and data.
                   - ('SUCCESS', user_data): On successful login.
                   - ('MIGRATED', message): On successful legacy user migration.
                   - ('FAILED', error_message): On any failure.
        """
        normalized_username = username.lower()
        email = f"{normalized_username}@email.placeholder.com"

        try:
            # Standard login for users already in Firebase Auth
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

                # Set persistence cookie
                session_config = self.settings_mgr.get_session_config()
                persistence_days = session_config.get('persistence_days', 0)
                if persistence_days > 0 and 'refreshToken' in user:
                    expires = datetime.now() + timedelta(days=persistence_days)
                    self.cookies.set('refresh_token', user['refreshToken'], expires_at=expires)

                return ('SUCCESS', user_data)
            else:
                # This case is unlikely but handled for safety
                return ('FAILED', "Đăng nhập thất bại. Dữ liệu người dùng không tồn tại.")

        except requests.exceptions.HTTPError as e:
            try:
                error_json = e.response.json()['error']
                error_message = error_json['message']
            except (ValueError, KeyError):
                return ('FAILED', f"Lỗi không xác định từ Firebase: {e}")


            # If password is just wrong for an existing user, fail fast.
            if error_message == 'INVALID_PASSWORD':
                return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")

            # If user is not in Firebase Auth, proceed to legacy check.
            if error_message == 'EMAIL_NOT_FOUND':
                # --- Legacy User Migration Flow ---
                all_users_stream = self.users_col.stream()
                found_user_doc = None
                for doc in all_users_stream:
                    user_data_legacy = doc.to_dict()
                    db_username = user_data_legacy.get('username')
                    if db_username and db_username.lower() == normalized_username:
                        found_user_doc = doc
                        break

                if not found_user_doc:
                    return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")

                user_data = found_user_doc.to_dict()
                password_hash = user_data.get("password_hash")

                if not password_hash or not self._check_password(password, password_hash):
                    return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")

                # Password is correct, proceed with migration
                try:
                    new_user_record = self.auth.create_user_with_email_and_password(email, password)
                    new_uid = new_user_record['localId']

                    user_data.pop('password_hash', None)
                    user_data['uid'] = new_uid
                    user_data['updated_at'] = datetime.now().isoformat()
                    if 'created_at' not in user_data:
                        user_data['created_at'] = datetime.now().isoformat()

                    self.users_col.document(new_uid).set(user_data)
                    self.users_col.document(found_user_doc.id).delete()

                    return ('MIGRATED', "Tài khoản của bạn đã được nâng cấp. Vui lòng đăng nhập lại.")

                except requests.exceptions.HTTPError as e_migrate:
                    # Handle migration-specific errors
                    try:
                        migrate_error_json = e_migrate.response.json()['error']
                        if migrate_error_json['message'] == "EMAIL_EXISTS":
                            return ('FAILED', "Lỗi: Không thể nâng cấp tài khoản. Username đã tồn tại trong hệ thống mới. Vui lòng liên hệ quản trị viên.")
                        return ('FAILED', f"Lỗi không xác định khi nâng cấp tài khoản: {migrate_error_json['message']}")
                    except (ValueError, KeyError):
                        return ('FAILED', f"Lỗi không xác định khi nâng cấp tài khoản: {e_migrate}")
                except Exception as e_migrate_general:
                     return ('FAILED', f"Lỗi hệ thống khi nâng cấp tài khoản: {e_migrate_general}")

            # Handle other Firebase auth errors
            return ('FAILED', f"Lỗi xác thực: {error_message}")
            
        except Exception as e:
            # Catch any other unexpected errors
            return ('FAILED', f"Đã xảy ra lỗi không mong muốn: {e}")

    def logout(self):
        if 'user' in st.session_state:
            del st.session_state['user']
        
        if self.cookies.get('refresh_token'):
            self.cookies.delete('refresh_token')
            
        st.query_params.clear()
        st.rerun()

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
                raise e # Re-raise original error if parsing fails
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
