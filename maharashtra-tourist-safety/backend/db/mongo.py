from pymongo import MongoClient
from pymongo.database import Database

from config import settings

_client: MongoClient | None = None
_db_available = False


def init_mongo() -> None:
    """Initialise the MongoDB client singleton. Skips gracefully if unreachable."""
    global _client, _db_available
    try:
        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
        # Ping to verify connection
        client.admin.command("ping")
        _client = client
        _db_available = True
        print(f"[MongoDB] Connected to {settings.MONGO_URI}")
    except Exception as e:
        _db_available = False
        _client = None  # Don't keep a broken client — avoids background retry delays
        print(f"[MongoDB] WARNING: could not connect — {e}. Running without persistence.")


def get_db() -> Database | None:
    """Return the application database, or None if MongoDB is unavailable."""
    if _client is None or not _db_available:
        return None
    return _client[settings.MONGO_DB_NAME]


def close_mongo() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
