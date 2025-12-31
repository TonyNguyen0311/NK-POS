
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

class ImageHandler:
    def __init__(self, credentials_input, folder_id):
        self.folder_id = folder_id
        try:
            # The input is now a file path, which is directly usable by service_account.Credentials.from_service_account_file
            creds = service_account.Credentials.from_service_account_file(
                credentials_input,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            self.drive_service = build('drive', 'v3', credentials=creds)
        except Exception as e:
            st.error(f"Failed to initialize Google Drive service: {e}")
            self.drive_service = None

    def upload_image(self, image_file, product_id):
        if not self.drive_service:
            st.error("Google Drive service is not available.")
            return None

        if image_file is None:
            return None

        try:
            file_metadata = {
                'name': f'{product_id}.jpg',
                'parents': [self.folder_id]
            }
            # Create a BytesIO object from the uploader's buffer
            image_bytes = io.BytesIO(image_file.getvalue())
            media = MediaIoBaseUpload(image_bytes, mimetype='image/jpeg', resumable=True)
            
            # Check if file with the same name already exists
            query = f"name='{file_metadata['name']}' and '{self.folder_id}' in parents"
            response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            existing_files = response.get('files', [])
            
            if existing_files:
                # Update the existing file
                file_id = existing_files[0].get('id')
                request = self.drive_service.files().update(fileId=file_id, media_body=media, fields='id, webViewLink')
            else:
                # Create a new file
                request = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink')
            
            file = request.execute()
            st.success(f"Image '{file_metadata['name']}' uploaded successfully!")
            return file.get('webViewLink')

        except Exception as e:
            st.error(f"Error uploading image to Google Drive: {e}")
            return None
