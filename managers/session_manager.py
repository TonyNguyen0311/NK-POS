
import streamlit as st
import time

def get_session_timeout(default_timeout=60):
    """
    Retrieves the session timeout from the settings manager.
    Defaults to 60 minutes if not set.
    """
    if 'settings_mgr' in st.session_state:
        try:
            settings = st.session_state.settings_mgr.get_settings()
            return settings.get('session_timeout_minutes', default_timeout)
        except Exception:
            return default_timeout
    return default_timeout

def is_session_active():
    """
    Checks if the current session is active based on the last activity time.
    """
    if 'user' not in st.session_state or st.session_state.user is None:
        return False

    timeout_minutes = get_session_timeout()
    if timeout_minutes == "never":
        return True

    if 'last_activity' not in st.session_state:
        st.session_state.last_activity = time.time()
        return True

    elapsed_time = time.time() - st.session_state.last_activity
    if elapsed_time > timeout_minutes * 60:
        # Session has expired, clear the user and rerun
        del st.session_state.user
        if 'last_activity' in st.session_state:
            del st.session_state.last_activity
        return False
    
    # Update last activity time on each interaction
    st.session_state.last_activity = time.time()
    return True

def handle_remember_me(user):
    """
    If "Remember me" is checked, store a token to re-authenticate the user.
    (This is a simplified example, in a real-world scenario, you'd use a secure, 
     long-lived token stored in a cookie or browser storage).
    """
    if st.session_state.get("remember_me"):
        # For simplicity, we'll store the user info directly in a file.
        # In a real app, this should be a secure token.
        with open(".remember_me", "w") as f:
            f.write(str(user))
    else:
        # If "remember me" is not checked, ensure the file is deleted
        if ".remember_me" in st.session_state:
            del st.session_state[".remember_me"]


def check_remember_me():
    """
    Checks for a "remember me" token and logs the user in if it exists.
    """
    try:
        with open(".remember_me", "r") as f:
            user_info = eval(f.read())
            st.session_state.user = user_info
            return True
    except (FileNotFoundError, SyntaxError):
        return False

