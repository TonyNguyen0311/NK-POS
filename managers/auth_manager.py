
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
            # Cố gắng lấy token từ cookie (cách mới, an toàn hơn)
            cookies = st.experimental_get_query_params()
            id_token = cookies.get('idToken')
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
                return False
        except Exception as e:
            return False

    def login(self, username, password):
        # Xác thực qua email và password với Firebase Auth
        try:
            email = f"{username}@email.placeholder.com"
            user = self.auth.sign_in_with_email_and_password(email, password)
            uid = user['localId']
            id_token = user['idToken']

            # Lưu token vào cookie của trình duyệt
            st.experimental_set_query_params(idToken=id_token)

        except Exception as e:
             # Nếu lỗi, có thể là do sai username hoặc password
            return None

        # Lấy thông tin chi tiết từ Firestore
        user_doc = self.users_col.document(uid).get()
        if not user_doc.exists:
            return None # Không tìm thấy bản ghi user trong Firestore
        
        user_data = user_doc.to_dict()
        user_data['uid'] = uid

        # Kiểm tra xem tài khoản có active không
        if not user_data.get('active', False):
            return None # Tài khoản bị vô hiệu hóa

        self.users_col.document(uid).update({"last_login": datetime.now().isoformat()})
        
        st.session_state['user'] = user_data
        return user_data

    def logout(self):
        """Xóa session và cookie để đăng xuất."""
        if 'user' in st.session_state:
            del st.session_state['user']
        # Xóa cookie bằng cách set giá trị rỗng
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
            # Không cần pop password hash vì đã bỏ
            user['uid'] = doc.id
            users.append(user)
        return users

    def create_user_record(self, data: dict, password: str):
        username = data.get('username')
        if not username:
            raise ValueError("Username là bắt buộc.")

        email = f"{username}@email.placeholder.com"
        try:
            # Tạo người dùng trong Firebase Authentication
            user_record = self.auth.create_user_with_email_and_password(email, password)
            uid = user_record['localId']
        except Exception as e:
            if "EMAIL_EXISTS" in str(e):
                raise ValueError(f"Lỗi: Username '{username}' đã được sử dụng.")
            raise e

        # Lưu thông tin người dùng vào Firestore
        data['uid'] = uid
        data['created_at'] = datetime.now().isoformat()
        data['active'] = True
        if 'branch_ids' not in data:
            data['branch_ids'] = []

        self.users_col.document(uid).set(data)
        return data

    def update_user_record(self, uid: str, data: dict, new_password: str = None):
        if new_password:
            # Cập nhật password qua Firebase Auth
            self.auth.update_user(uid, password=new_password)
        
        data['updated_at'] = datetime.now().isoformat()
        self.users_col.document(uid).update(data)
        return True
