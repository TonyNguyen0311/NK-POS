
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
        st.info("DEBUG: --- Bắt đầu kiểm tra Cookie ---")
        if 'user' in st.session_state and st.session_state.user is not None:
            st.info("DEBUG: Người dùng đã có trong session. Bỏ qua.")
            return True

        refresh_token = self.cookies.get('refresh_token')
        if not refresh_token:
            st.warning("DEBUG: Không tìm thấy refresh_token trong cookie. Yêu cầu đăng nhập.")
            return False
        
        st.info(f"DEBUG: Đã tìm thấy refresh_token trong cookie.")

        try:
            st.info("DEBUG: Đang thử làm mới token với Firebase...")
            user_session = self.auth.refresh(refresh_token)
            
            uid = user_session['userId']
            st.info(f"DEBUG: Firebase refresh thành công cho UID: {uid}")
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                st.info(f"DEBUG: Tìm thấy tài liệu người dùng trong Firestore cho UID {uid}.")
                if not user_data.get('active', False):
                    st.warning("DEBUG: Người dùng không hoạt động. Xóa cookie.")
                    self.cookies.delete('refresh_token') 
                    return False
                
                user_data['uid'] = uid
                st.session_state['user'] = user_data
                st.success("DEBUG: Tái xác thực thành công!")
                return True
            else:
                st.error(f"DEBUG: Người dùng với UID {uid} không tồn tại trong Firestore. Xóa cookie.")
                self.cookies.delete('refresh_token')
                return False
        except Exception as e:
            st.error(f"DEBUG: Lỗi khi làm mới token: {e}")
            st.info("DEBUG: Xóa refresh_token có thể không hợp lệ khỏi cookie.")
            self.cookies.delete('refresh_token')
            return False

    def login(self, username, password):
        normalized_username = username.lower()
        email = f"{normalized_username}@email.placeholder.com"

        try:
            # --- Attempt Firebase Auth sign-in first ---
            st.info(f"DEBUG: Cố gắng đăng nhập bằng Firebase Auth cho email: {email}")
            user = self.auth.sign_in_with_email_and_password(email, password)
            uid = user['localId']
            st.info(f"DEBUG: Đăng nhập Firebase Auth thành công cho UID: {uid}")
            
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['uid'] = uid
                if user_data.get('active', False):
                    self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                    st.session_state['user'] = user_data

                    session_config = self.settings_mgr.get_session_config()
                    persistence_days = session_config.get('persistence_days', 0)
                    st.info(f"DEBUG: Thời gian lưu session là {persistence_days} ngày.")
                    if persistence_days > 0 and 'refreshToken' in user:
                        expires = datetime.now() + timedelta(days=persistence_days)
                        self.cookies.set('refresh_token', user['refreshToken'], expires_at=expires)
                        st.info(f"DEBUG: Đã đặt refresh_token vào cookie. Hết hạn: {expires.isoformat()}")

                    return user_data
            st.error("DEBUG: Tài khoản tồn tại trong Auth nhưng không có trong Firestore.")
            return None

        except Exception as e:
            st.warning(f"DEBUG: Đăng nhập Firebase Auth thất bại (đây là điều bình thường đối với tài khoản cũ). Lỗi: {e}. Thử di chuyển tài khoản cũ...")
            
            # --- Fallback to legacy user lookup and migration ---
            all_users_stream = self.users_col.stream()
            found_user_doc = None
            for doc in all_users_stream:
                user_data_legacy = doc.to_dict()
                db_username = user_data_legacy.get('username')
                if db_username and db_username.lower() == normalized_username:
                    found_user_doc = doc
                    break

            if not found_user_doc:
                st.error("DEBUG: Không tìm thấy tài khoản cũ trong Firestore.")
                return None

            user_data = found_user_doc.to_dict()
            password_hash = user_data.get("password_hash")

            if not password_hash or not self._check_password(password, password_hash):
                st.error("DEBUG: Sai mật khẩu cho tài khoản cũ.")
                return None

            # --- MIGRATE LEGACY USER TO FIREBASE AUTH ---
            try:
                st.info("DEBUG: --- Bắt đầu quá trình di chuyển tài khoản cũ ---")
                
                # 1. Create the user in Firebase Auth
                new_user_record = self.auth.create_user_with_email_and_password(email, password)
                new_uid = new_user_record['localId']
                st.info(f"DEBUG: Tạo người dùng Firebase Auth mới với UID: {new_uid}")

                # 2. Prepare new data, remove old hash
                user_data.pop('password_hash', None)
                user_data['uid'] = new_uid
                user_data['updated_at'] = datetime.now().isoformat()
                if 'created_at' not in user_data:
                    user_data['created_at'] = datetime.now().isoformat()

                # 3. Create new doc and delete old one
                self.users_col.document(new_uid).set(user_data)
                self.users_col.document(found_user_doc.id).delete()
                st.info("DEBUG: Đã di chuyển dữ liệu người dùng sang tài liệu Firestore mới.")

                # 4. Sign in the new user to get their session
                user_session = self.auth.sign_in_with_email_and_password(email, password)
                st.info("DEBUG: Đăng nhập bằng tài khoản mới để lấy session.")

                # 5. Set session state and the crucial persistence cookie
                st.session_state['user'] = user_data
                session_config = self.settings_mgr.get_session_config()
                persistence_days = session_config.get('persistence_days', 0)
                st.info(f"DEBUG: Thời gian lưu session là {persistence_days} ngày.")
                
                if persistence_days > 0 and 'refreshToken' in user_session:
                    expires = datetime.now() + timedelta(days=persistence_days)
                    self.cookies.set('refresh_token', user_session['refreshToken'], expires_at=expires)
                    st.info(f"DEBUG: Đã đặt refresh_token vào cookie. Hết hạn: {expires.isoformat()}")
                elif 'refreshToken' not in user_session:
                    st.warning("DEBUG: 'refreshToken' không có trong user_session sau khi di chuyển.")
                else:
                    st.info("DEBUG: Việc lưu session bị tắt (0 ngày). Cookie không được đặt.")
                
                st.success("Nâng cấp tài khoản thành công! Tự động đăng nhập.")
                return user_data

            except Exception as migration_error:
                error_str = str(migration_error)
                st.error(f"DEBUG: LỖI NGHIÊM TRỌNG TRONG QUÁ TRÌNH DI CHUYỂN: {error_str}")
                if "EMAIL_EXISTS" in error_str:
                    st.error("Lỗi: Không thể nâng cấp tài khoản. Username đã tồn tại trong hệ thống mới. Vui lòng liên hệ quản trị viên.")
                else:
                    st.error(f"Lỗi không xác định khi nâng cấp tài khoản: {migration_error}")
                return None

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
