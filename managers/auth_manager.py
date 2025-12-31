
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
        st.info("DEBUG: Bắt đầu check_cookie_and_re_auth.")
        if 'user' in st.session_state and st.session_state.user is not None:
            st.info("DEBUG: Đã có user trong session_state. Bỏ qua re-auth.")
            return True

        refresh_token = self.cookies.get('refresh_token')
        st.info(f"DEBUG: Lấy refresh_token từ cookie: {'Tồn tại' if refresh_token else 'Không tồn tại'}.")

        if not refresh_token:
            st.info("DEBUG: Không có refresh_token. Kết thúc re-auth.")
            return False

        st.info("DEBUG: Tìm thấy refresh_token, đang thử làm mới phiên...")
        try:
            user_session = self.auth.refresh(refresh_token)
            uid = user_session['userId']
            st.info(f"DEBUG: Làm mới phiên thành công cho UID: {uid}")
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if not user_data.get('active', False):
                    st.warning("DEBUG: Tài khoản đã bị vô hiệu hóa.")
                    if 'refresh_token' in self.cookies:
                        del self.cookies['refresh_token']
                    return False
                
                user_data['uid'] = uid
                st.session_state['user'] = user_data
                st.success("DEBUG: Tự động đăng nhập lại thành công!")
                return True
            else:
                st.error("DEBUG: Không tìm thấy dữ liệu người dùng cho UID này.")
                if 'refresh_token' in self.cookies:
                    del self.cookies['refresh_token']
                return False
        except Exception as e:
            st.error(f"DEBUG: Lỗi khi làm mới token: {e}")
            if 'refresh_token' in self.cookies:
                del self.cookies['refresh_token']
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
                st.info(f"DEBUG: Kiểm tra ghi nhớ đăng nhập. Số ngày: {persistence_days}")
                if persistence_days > 0 and 'refreshToken' in user:
                    st.info(f"DEBUG: Đang thiết lập refresh_token cookie để ghi nhớ đăng nhập.")
                    self.cookies['refresh_token'] = user['refreshToken']
                    st.info("DEBUG: Đã đặt cookie.")

                return ('SUCCESS', user_data)
            else:
                return ('FAILED', "Đăng nhập thất bại. Dữ liệu người dùng không tồn tại.")

        except requests.exceptions.HTTPError as e:
            try:
                error_json = e.response.json()['error']
                error_message = error_json['message']
            except (ValueError, KeyError):
                return ('FAILED', f"Lỗi không xác định từ Firebase: {e}")

            if error_message == 'INVALID_PASSWORD':
                return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")

            if error_message == 'EMAIL_NOT_FOUND':
                all_users_stream = self.users_col.where("username", "==", normalized_username).limit(1).stream()
                legacy_docs = list(all_users_stream)

                if not legacy_docs:
                    return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")

                found_user_doc = legacy_docs[0]
                user_data = found_user_doc.to_dict()
                password_hash = user_data.get("password_hash")

                if not password_hash or not self._check_password(password, password_hash):
                    return ('FAILED', "Sai tên đăng nhập hoặc mật khẩu.")

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
                    try:
                        migrate_error_json = e_migrate.response.json()['error']
                        if migrate_error_json['message'] == "EMAIL_EXISTS":
                            return ('FAILED', "Tài khoản đã tồn tại. Vui lòng thử đăng nhập lại.")
                        return ('FAILED', f"Lỗi nâng cấp: {migrate_error_json['message']}")
                    except (ValueError, KeyError):
                        return ('FAILED', f"Lỗi không xác định khi nâng cấp: {e_migrate}")
                except Exception as e_migrate_general:
                     return ('FAILED', f"Lỗi hệ thống khi nâng cấp: {e_migrate_general}")
            return ('FAILED', f"Lỗi xác thực: {error_message}")
        except Exception as e:
            return ('FAILED', f"Đã xảy ra lỗi không mong muốn: {e}")

    def logout(self):
        st.info("DEBUG: Bắt đầu quá trình đăng xuất.")
        if 'user' in st.session_state:
            del st.session_state['user']
            st.info("DEBUG: Đã xóa user khỏi session_state.")
        
        if 'refresh_token' in self.cookies:
            del self.cookies['refresh_token']
            st.info("DEBUG: Đã xóa refresh_token khỏi cookie.")
            
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
