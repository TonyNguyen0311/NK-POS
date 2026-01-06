
import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io
from PIL import Image
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def hash_image_handler(handler):
    """A hash function for st.cache_data to handle the ImageHandler instance."""
    return "ImageHandler_Singleton"

class ImageHandler:
    """Manages image operations with Google Drive, including uploading and private loading."""
    def __init__(self, credentials_info):
        self.drive_service = self._initialize_drive_service(credentials_info)

    def _initialize_drive_service(self, credentials_info):
        """Initializes the Google Drive API service using OAuth credentials."""
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

    @st.cache_data(show_spinner=False, hash_funcs={object: hash_image_handler})
    def load_drive_image(_self, file_id: str) -> bytes | None:
        """
        Loads a private image from Google Drive using its file_id.
        The image data is returned as bytes, suitable for st.image().
        This method is cached to prevent redundant downloads.
        """
        if not _self.drive_service or not file_id:
            logger.warning("Drive service not initialized or file_id is missing for loading.")
            return None
        try:
            request = _self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            return fh.getvalue()
        except HttpError as error:
            logger.error(f"Error loading image {file_id}: {error}")
            return None

    def upload_image(self, image_file, folder_id: str, base_filename: str) -> str | None:
        """
        Optimizes, and uploads an image to a specified Google Drive folder.
        Returns the file_id of the newly created file.
        """
        if not self.drive_service:
            st.error("Dịch vụ Google Drive chưa được khởi tạo.")
            return None

        # 1. Generate a unique filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{base_filename}_{timestamp}.jpg"

        # 2. Optimize the image
        try:
            optimized_bytes = self._optimize_image(image_file, max_width=1024, quality=80)
        except Exception as e:
            st.error(f"Lỗi khi tối ưu hóa ảnh: {e}")
            return None
        
        # 3. Upload the optimized image and get file_id
        return self._upload_to_drive(folder_id, unique_filename, optimized_bytes)

    def _optimize_image(self, image_file, max_width: int, quality: int) -> io.BytesIO:
        """Resizes and compresses an image, returning it as a BytesIO object."""
        with Image.open(image_file) as img:
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

    def _upload_to_drive(self, folder_id: str, filename: str, image_bytes: io.BytesIO) -> str | None:
        """A private method to handle the file creation in Google Drive."""
        try:
            file_metadata = {'name': filename, 'parents': [folder_id]}
            media = MediaIoBaseUpload(image_bytes, mimetype='image/jpeg', resumable=True)
            
            created_file = self.drive_service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id'
            ).execute()
            
            file_id = created_file.get('id')
            if file_id:
                logger.info(f"Successfully uploaded file '{filename}' with ID: {file_id}")
                return file_id
            else:
                logger.error("Upload process did not return a file ID.")
                return None
        except HttpError as error:
            logger.error(f"An HTTP error occurred during upload: {error}")
            st.error(f"Lỗi khi tải ảnh lên Drive: {error}")
            return None

    def delete_image_by_id(self, file_id: str):
        """Deletes a file from Google Drive using its file_id."""
        if not self.drive_service or not file_id:
            logger.warning("Drive service not initialized or file_id is missing. Cannot delete.")
            return
        try:
            self.drive_service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file with ID '{file_id}' from Drive.")
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Attempted to delete file ID '{file_id}', but it was not found.")
            else:
                logger.error(f"Error deleting file ID '{file_id}': {e}")

