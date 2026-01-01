
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import io
from PIL import Image
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageHandler:
    """
    Handles image uploads to Google Drive, including optimization and public access.
    """
    def __init__(self, credentials_info, folder_id):
        self.folder_id = folder_id
        self.drive_service = self._initialize_drive_service(credentials_info)

    def _initialize_drive_service(self, credentials_info):
        """Initializes the Google Drive service using service account credentials."""
        try:
            # Using a more specific scope is best practice, but drive is fine
            scopes = ['https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive service: {e}")
            st.error("Lỗi cấu hình Google Drive. Không thể tải ảnh lên.")
            return None

    def _optimize_image(self, image_file, max_width=800, quality=85):
        """
        Resizes and compresses the image before uploading.
        Converts image to JPEG for better compression.
        """
        try:
            img = Image.open(image_file)
            
            # Convert to RGB if it's not (e.g., RGBA from PNG)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Resize based on width
            if img.width > max_width:
                ratio = max_width / float(img.width)
                height = int(float(img.height) * ratio)
                img = img.resize((max_width, height), Image.LANCZOS)

            # Save to an in-memory byte stream
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
            img_byte_arr.seek(0)
            return img_byte_arr
        except Exception as e:
            logger.error(f"Error optimizing image: {e}")
            st.warning("Không thể tối ưu hóa ảnh. Tải lên ảnh gốc.")
            # Fallback to original file if optimization fails
            image_file.seek(0)
            return image_file


    def upload_image(self, image_file, product_sku):
        """
        Optimizes and uploads an image to Google Drive, then makes it public.
        Uses product_sku as the unique filename.
        """
        if not self.drive_service:
            st.error("Dịch vụ Google Drive chưa được khởi tạo.")
            return None

        # A more robust approach for unique filenames could be:
        # filename = f"{product_sku}_{uuid.uuid4().hex}.jpg"
        filename = f"{product_sku}.jpg"

        # Optimize the image
        optimized_image_bytes = self._optimize_image(image_file)

        media = MediaIoBaseUpload(optimized_image_bytes, mimetype='image/jpeg', resumable=True)
        file_metadata = {
            'name': filename,
            'parents': [self.folder_id]
        }

        try:
            # Check if a file with the same name already exists to update it
            query = f"name='{filename}' and '{self.folder_id}' in parents and trashed=false"
            response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            existing_files = response.get('files', [])

            if existing_files:
                file_id = existing_files[0].get('id')
                request = self.drive_service.files().update(fileId=file_id, media_body=media, fields='id')
            else:
                request = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id')
            
            file = request.execute()
            file_id = file.get('id')

            if file_id:
                # Set permission to anyone with the link can view
                self.drive_service.permissions().create(
                    fileId=file_id,
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()
                
                # Return the direct download link
                direct_link = f"https://drive.google.com/uc?id={file_id}"
                st.success(f"Ảnh đã được tải lên thành công!")
                return direct_link

            return None

        except HttpError as error:
            logger.error(f"An HTTP error occurred: {error}")
            st.error(f"Lỗi khi tải ảnh lên: {error}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            st.error(f"Đã có lỗi không mong muốn xảy ra: {e}")
            return None

    def delete_image(self, product_sku):
        """Deletes an image from Google Drive based on product_sku."""
        if not self.drive_service:
            return

        filename = f"{product_sku}.jpg"
        try:
            query = f"name='{filename}' and '{self.folder_id}' in parents and trashed=false"
            response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            existing_files = response.get('files', [])

            if existing_files:
                file_id = existing_files[0].get('id')
                self.drive_service.files().delete(fileId=file_id).execute()
                logger.info(f"Successfully deleted image '{filename}' from Google Drive.")
        except Exception as e:
            logger.error(f"Error deleting image '{filename}' from Google Drive: {e}")

