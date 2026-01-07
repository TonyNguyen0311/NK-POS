
import streamlit as st
import uuid

def hash_category_manager(manager):
    return "CategoryManager"

class CategoryManager:
    """
    A general-purpose manager to handle CRUD operations for various category-like
    collections in Firestore, such as product categories, cost groups, etc.
    """
    def __init__(self, firebase_client):
        self.db = firebase_client.db

    def _get_collection_ref(self, collection_name: str):
        """Helper to get a collection reference."""
        return self.db.collection(collection_name)

    @st.cache_data(ttl=300, hash_funcs={_self_: hash_category_manager})
    def get_all_category_items(_self, collection_name: str) -> list[dict]:
        """
        Retrieves all items from a specified category collection.
        The result is cached to improve performance.

        Args:
            collection_name (str): The name of the Firestore collection.

        Returns:
            list[dict]: A list of dictionaries, where each dictionary represents an item.
        """
        docs = _self._get_collection_ref(collection_name).stream()
        return [doc.to_dict() for doc in docs]

    def add_category_item(self, collection_name: str, item_data: dict, id_prefix: str) -> dict:
        """
        Adds a new item to the specified category collection.

        Args:
            collection_name (str): The name of the Firestore collection.
            item_data (dict): The data for the new item.
            id_prefix (str): A prefix for the new item's ID.

        Returns:
            dict: The newly created item data, including its ID.
        """
        item_id = f"{id_prefix}-{uuid.uuid4().hex[:6].upper()}"
        item_data['id'] = item_id
        
        self._get_collection_ref(collection_name).document(item_id).set(item_data)
        
        # Clear cache for this specific collection
        self.get_all_category_items.clear()
        
        return item_data

    def update_category_item(self, collection_name: str, item_id: str, item_data: dict) -> bool:
        """
        Updates an existing item in the specified category collection.

        Args:
            collection_name (str): The name of the Firestore collection.
            item_id (str): The ID of the item to update.
            item_data (dict): The data to update.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        self._get_collection_ref(collection_name).document(item_id).update(item_data)
        
        # Clear cache for this specific collection
        self.get_all_category_items.clear()
        
        return True

    def delete_category_item(self, collection_name: str, item_id: str) -> bool:
        """
        Deletes an item from the specified category collection.

        Args:
            collection_name (str): The name of the Firestore collection.
            item_id (str): The ID of the item to delete.

        Returns:
            bool: True if the deletion was successful, False otherwise.
        """
        self._get_collection_ref(collection_name).document(item_id).delete()
        
        # Clear cache for this specific collection
        self.get_all_category_items.clear()
        
        return True
