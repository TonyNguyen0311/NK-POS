
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import logging

class ImageHandler:
    def __init__(self, credentials_info, folder_id):
        self.folder_id = folder_id
        try:
            creds = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            self.drive_service = build('drive', 'v3', credentials=creds)
        except Exception as e:
            logging.error(f"Failed to initialize Google Drive service: {e}")
            self.drive_service = None
            st.error("Lỗi cấu hình Drive, không thể tải ảnh.")

    def _find_file_by_name(self, filename):
        if not self.drive_service:
            return None
        try:
            query = f"name='{filename}' and '{self.folder_id}' in parents and trashed=false"
            response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            return response.get('files', [])
        except Exception as e:
            logging.error(f"Error finding file '{filename}' in Drive: {e}")
            return None

    def upload_image(self, image_file, product_sku):
        if not self.drive_service:
            st.error("Lỗi dịch vụ Google Drive.")
            return None
        
        filename = f"{product_sku}.jpg"
        image_bytes = io.BytesIO(image_file.getvalue())
        media = MediaIoBaseUpload(image_bytes, mimetype='image/jpeg', resumable=True)
        
        try:
            existing_files = self._find_file_by_name(filename)
            file_metadata = {'name': filename}

            if existing_files:
                file_id = existing_files[0].get('id')
                request = self.drive_service.files().update(fileId=file_id, media_body=media, fields='id, webViewLink')
            else:
                file_metadata['parents'] = [self.folder_id]
                request = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink')
            
            file = request.execute()
            # Manually construct a direct access link
            if file:
                # This is a public, shareable link anyone can view
                return file.get('webViewLink') 
            return None

        except Exception as e:
            logging.error(f"Error uploading image '{filename}' to Google Drive: {e}")
            st.error(f"Lỗi tải ảnh lên Drive: {e}")
            return None

    def delete_image(self, product_sku):
        if not self.drive_service:
            return
        
        filename = f"{product_sku}.jpg"
        try:
            existing_files = self._find_file_by_name(filename)
            if existing_files:
                file_id = existing_files[0].get('id')
                self.drive_service.files().delete(fileId=file_id).execute()
                logging.info(f"Successfully deleted image '{filename}' from Google Drive.")
        except Exception as e:
            logging.error(f"Error deleting image '{filename}' from Google Drive: {e}")
            # Don't show error to user, just log it
