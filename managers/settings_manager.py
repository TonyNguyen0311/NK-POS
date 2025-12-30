
import streamlit as st

class SettingsManager:
    def __init__(self, firebase_client):
        self.db = firebase_client.db
        self.collection = self.db.collection('settings')

    def get_settings(self):
        """
        Retrieves the application settings from Firestore.
        Returns a dictionary of settings or a default dictionary if not found.
        """
        doc_ref = self.collection.document('app_settings')
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            return {
                'session_timeout_minutes': 60  # Default value
            }

    def save_settings(self, settings_data):
        """
        Saves the settings to Firestore.
        """
        doc_ref = self.collection.document('app_settings')
        doc_ref.set(settings_data)

