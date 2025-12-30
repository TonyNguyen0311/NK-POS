
import bcrypt
import uuid
from datetime import datetime
import streamlit as st
import pyrebase # Thêm thư viện pyrebase

class AuthManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.auth = firebase_client.auth # Thêm auth client
        self.users_col = self.db.collection('users')

    def _hash_password(self, password):
        if not password:
            return None
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _check_password(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def check_cookie_and_re_auth(self):
        """Kiểm tra cookie để xác thực lại và duy trì phiên đăng nhập."""
        if 'user' in st.session_state and st.session_state.user is not None:
            return True # Đã có phiên, không cần làm gì

        try:
            # Cố gắng lấy token từ cookie
            id_token = st.experimental_get_query_params().get('idToken', [None])[0]
        except (AttributeError, KeyError):
            id_token = None

        if not id_token:
            return False

        try:
            # Xác thực token với Firebase Auth
            user_info = self.auth.get_account_info(id_token)
            uid = user_info['users'][0]['localId']
            
            # Lấy thông tin chi tiết từ Firestore
            user_doc = self.users_col.document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['uid'] = uid
                st.session_state['user'] = user_data
                return True
            else:
                st.experimental_set_query_params(idToken=None) # Xóa cookie nếu user không tồn tại trong DB
                return False
        except Exception as e:
            # Xóa cookie nếu token không hợp lệ
            st.experimental_set_query_params(idToken=None)
            return False

    def login(self, username, password):
        """
        Hàm đăng nhập hỗ trợ cả hệ thống mới (Firebase Auth) và cũ (bcrypt).
        """
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
            query = self.users_col.where('username', '==', normalized_username).limit(1).stream()
            user_doc_list = list(query)

            if not user_doc_list:
                return None # Không tìm thấy username

            user_doc = user_doc_list[0]
            user_data = user_doc.to_dict()
            hashed_password = user_data.get("password_hash")

            if not hashed_password:
                return None # User này không có password_hash, không phải hệ thống cũ

            # Kiểm tra mật khẩu bằng bcrypt
            if self._check_password(password, hashed_password):
                uid = user_doc.id
                user_data['uid'] = uid
                
                if user_data.get('active', False):
                    self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
                    st.session_state['user'] = user_data
                    # Lưu ý: Người dùng hệ thống cũ sẽ không có phiên đăng nhập bền bỉ (cookie)
                    return user_data

            return None # Sai mật khẩu hệ thống cũ hoặc tài khoản không active

    def logout(self):
        """Xóa session và cookie để đăng xuất."""
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
            user.pop('password_hash', None) # Không hiển thị hash trong danh sách
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
            # Tạo người dùng trong Firebase Authentication
            user_record = self.auth.create_user_with_email_and_password(email, password)
            uid = user_record['localId']
        except Exception as e:
            if "EMAIL_EXISTS" in str(e):
                raise ValueError(f"Lỗi: Username '{normalized_username}' đã được sử dụng.")
            raise e

        # Lưu thông tin người dùng vào Firestore
        data['uid'] = uid
        data['created_at'] = datetime.now().isoformat()
        data['active'] = True
        if 'branch_ids' not in data:
            data['branch_ids'] = []
        
        # Không lưu password hash nữa
        data.pop('password_hash', None)

        self.users_col.document(uid).set(data)
        return data

    def update_user_record(self, uid: str, data: dict, new_password: str = None):
        if new_password:
            # Cập nhật password qua Firebase Auth
            self.auth.update_user(uid, password=new_password)
        
        if 'username' in data:
            data['username'] = data['username'].lower()

        data['updated_at'] = datetime.now().isoformat()
        self.users_col.document(uid).update(data)
        return True
