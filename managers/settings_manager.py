
import streamlit as st

class SettingsManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('settings')
        self._settings_doc_id = 'app_config' # Đổi tên để tổng quát hơn

    def get_settings(self):
        """
        Lấy toàn bộ cài đặt của ứng dụng từ Firestore.
        Trả về một dict chứa cài đặt hoặc dict mặc định nếu chưa có.
        """
        doc_ref = self.collection.document(self._settings_doc_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            # Cấu hình mặc định ban đầu
            return {
                'session_persistence_days': 0  # 0 ngày = không ghi nhớ đăng nhập
            }

    def save_settings(self, settings_data):
        """
        Lưu toàn bộ cài đặt vào Firestore.
        """
        doc_ref = self.collection.document(self._settings_doc_id)
        doc_ref.set(settings_data, merge=True) # Dùng merge=True để an toàn hơn

    def get_session_config(self):
        """
        Hàm chuyên biệt để lấy cấu hình phiên đăng nhập.
        Trả về một dict chứa các thông tin liên quan đến session.
        """
        settings = self.get_settings()
        return {
            'persistence_days': settings.get('session_persistence_days', 0)
        }
