
import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import io
from PIL import Image
import logging
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageHandler:
    def __init__(self, credentials_info):
        self.drive_service = self._initialize_drive_service(credentials_info)

    def _initialize_drive_service(self, credentials_info):
        try:
            creds = Credentials(
                None, 
                refresh_token=credentials_info['refresh_token'],
                token_uri=credentials_info.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=credentials_info['client_id'],
                client_secret=credentials_info['client_secret'],
                scopes=credentials_info.get('scopes', ['https://www.googleapis.com/auth/drive.file'])
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive service: {e}")
            st.error(f"Lỗi cấu hình Google Drive: {e}")
            return None

    def _optimize_image(self, image_file, max_width=800, quality=85):
        try:
            img = Image.open(image_file)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            if img.width > max_width:
                ratio = max_width / float(img.width)
                height = int(float(img.height) * ratio)
                img = img.resize((max_width, height), Image.LANCZOS)
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
            img_byte_arr.seek(0)
            return img_byte_arr
        except Exception as e:
            logger.error(f"Error optimizing image: {e}")
            image_file.seek(0)
            return image_file

    def _upload_to_drive(self, folder_id, filename, image_bytes, update_existing=False):
        if not self.drive_service:
            raise Exception("Dịch vụ Google Drive chưa được khởi tạo.")

        media = MediaIoBaseUpload(image_bytes, mimetype='image/jpeg', resumable=True)
        
        try:
            file_id_to_update = None
            if update_existing:
                query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
                response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
                if response.get('files'):
                    file_id_to_update = response.get('files')[0].get('id')

            if file_id_to_update:
                request = self.drive_service.files().update(fileId=file_id_to_update, media_body=media, fields='id')
                response = request.execute()
                file_id = response.get('id')
            else:
                file_metadata = {'name': filename, 'parents': [folder_id]}
                request = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id')
                response = request.execute()
                file_id = response.get('id')
            
            if file_id:
                self.drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
                return f"https://drive.google.com/uc?export=view&id={file_id}"
            return None

        except HttpError as error:
            logger.error(f"An HTTP error occurred: {error}")
            raise Exception(f"Lỗi khi tải ảnh lên Drive: {error}")

    def upload_product_image(self, image_file, folder_id, product_sku):
        filename = f"{product_sku}.jpg"
        optimized_image_bytes = self._optimize_image(image_file, max_width=800, quality=85)
        return self._upload_to_drive(folder_id, filename, optimized_image_bytes, update_existing=True)

    def upload_receipt_image(self, image_file, folder_id):
        filename = f"receipt_{uuid.uuid4().hex[:12]}.jpg"
        optimized_image_bytes = self._optimize_image(image_file, max_width=1200, quality=80)
        return self._upload_to_drive(folder_id, filename, optimized_image_bytes, update_existing=False)

    def delete_image_by_filename(self, folder_id, filename):
        if not self.drive_service:
            return
        try:
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            if files := response.get('files', []):
                file_id = files[0].get('id')
                self.drive_service.files().delete(fileId=file_id).execute()
                logger.info(f"Deleted '{filename}' from Drive.")
        except HttpError as e:
            logger.error(f"Error deleting '{filename}': {e}")
