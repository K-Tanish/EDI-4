try:
    import firebase_admin
    from firebase_admin import credentials, db as firebase_db
except ImportError:
    firebase_admin = None
    credentials = None
    firebase_db = None

from config import settings

_firebase_app = None


def init_firebase() -> None:
    """Initialise Firebase Admin SDK. Call once on app startup. Skips gracefully if credentials file is missing."""
    global _firebase_app
    if firebase_admin is None:
        print("[Firebase] WARNING: firebase_admin package not installed — Firebase disabled.")
        return
    if _firebase_app is not None:
        return  # already initialised

    import os
    if not os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
        print(f"[Firebase] WARNING: credentials file '{settings.FIREBASE_CREDENTIALS_PATH}' not found — Firebase disabled.")
        return

    try:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(
            cred,
            {"databaseURL": "https://tourist-safety-sys-default-rtdb.asia-southeast1.firebasedatabase.app"},
        )
        print("[Firebase] Initialised successfully.")
    except Exception as e:
        print(f"[Firebase] WARNING: init failed — {e}. Firebase disabled.")


def _get_project_id() -> str:
    """Extract project_id from the credentials file path (best-effort)."""
    import json, os

    path = settings.FIREBASE_CREDENTIALS_PATH
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
            return data.get("project_id", "maharashtra-tourist-safety")
    return "maharashtra-tourist-safety"


def get_firebase_db():
    """Return the Firebase Realtime Database root reference, or None if not initialised."""
    if firebase_admin is None or _firebase_app is None:
        return None
    return firebase_db.reference("/")
