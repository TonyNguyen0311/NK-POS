
import bcrypt
import uuid
from datetime import datetime
import streamlit as st

class AuthManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.users_col = self.db.collection('users')

    def _hash_password(self, password):
        if not password:
            return None
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _check_password(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def login(self, username, password):
        docs = self.users_col.where("username", "==", username).where("active", "==", True).limit(1).stream()
        user_list = [d.to_dict() for d in docs]
        if not user_list:
            return None
        
        user_data = user_list[0]
        if self._check_password(password, user_data.get('password_hash', "")):
            user_data.pop('password_hash', None)
            self.users_col.document(user_data['uid']).update({"last_login": datetime.now().isoformat()})
            # Lưu thông tin user vào session state để truy cập toàn cục
            st.session_state['user'] = user_data
            return user_data
        return None

    def get_current_user_info(self):
        return st.session_state.get('user')

    def has_users(self):
        return len(self.users_col.limit(1).get()) > 0

    # --- CÁC HÀM QUẢN LÝ CRUD CHO ADMIN ---

    def list_users(self):
        """Lấy danh sách tất cả người dùng để hiển thị cho Admin."""
        docs = self.users_col.order_by("display_name").stream()
        users = []
        for doc in docs:
            user = doc.to_dict()
            user.pop('password_hash', None)
            users.append(user)
        return users

    def create_user_record(self, data: dict, password: str):
        """Tạo một bản ghi người dùng mới."""
        username = data.get('username')
        if not username:
            raise ValueError("Username là bắt buộc.")
        
        existing = self.users_col.where("username", "==", username).limit(1).get()
        if len(existing) > 0:
            raise ValueError(f"Username '{username}' đã tồn tại.")

        uid = f"U-{uuid.uuid4().hex[:6].upper()}"
        data['uid'] = uid
        data['password_hash'] = self._hash_password(password)
        data['created_at'] = datetime.now().isoformat()
        data['active'] = True
        
        self.users_col.document(uid).set(data)
        data.pop('password_hash', None)
        return data

    def update_user_record(self, uid: str, data: dict, new_password: str = None):
        """Cập nhật thông tin người dùng. Hash password mới nếu có."""
        if new_password:
            data['password_hash'] = self._hash_password(new_password)
        
        data['updated_at'] = datetime.now().isoformat()
        self.users_col.document(uid).update(data)
        return True
