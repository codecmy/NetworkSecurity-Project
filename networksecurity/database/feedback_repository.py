"""
Feedback repository — a dedicated MongoDB database for user-verified verdicts.

Each document stores the URL, the verdict shown to the user, the user's
"correct"/"wrong" rating, and (best-effort) the 30 extracted features so the
collected data can be used to retrain the model without re-visiting the URL.

Lives in its own database (NetworkSecurityFeedback) to keep it separate from
the training dataset (NetworkSecurity).
"""

from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional

import certifi
from dotenv import load_dotenv

load_dotenv()

import pymongo

from networksecurity.constants.training_pipeline import (
    FEEDBACK_DATABASE_NAME,
    FEEDBACK_COLLECTION_NAME,
)

_client: Optional[pymongo.MongoClient] = None
_lock = threading.Lock()


def _collection():
    global _client
    with _lock:
        if _client is None:
            url = os.getenv("MONGODB_URL")
            if not url:
                raise RuntimeError("MONGODB_URL is not set")
            _client = pymongo.MongoClient(
                url, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=8000
            )
    return _client[FEEDBACK_DATABASE_NAME][FEEDBACK_COLLECTION_NAME]


def ping() -> bool:
    """Return True when MongoDB is reachable."""
    try:
        _collection().database.client.admin.command("ping")
        return True
    except Exception:
        return False


def save_feedback(doc: Dict) -> str:
    """Insert one feedback document; returns its Mongo _id as a string."""
    result = _collection().insert_one(doc)
    return str(result.inserted_id)


def load_feedback(query: Optional[Dict] = None, limit: int = 0) -> List[Dict]:
    """Return feedback documents (newest first) as plain dicts (no _id)."""
    cursor = _collection().find(query or {}).sort("timestamp", -1)
    if limit and limit > 0:
        cursor = cursor.limit(limit)
    return [{k: v for k, v in doc.items() if k != "_id"} for doc in cursor]


def count_feedback(query: Optional[Dict] = None) -> int:
    return _collection().count_documents(query or {})


def clear_feedback(query: Optional[Dict] = None) -> int:
    """Delete feedback docs (optionally filtered). Returns the number removed."""
    result = _collection().delete_many(query or {})
    return result.deleted_count


def feedback_to_dataframe(query: Optional[Dict] = None, limit: int = 0):
    import pandas as pd

    return pd.DataFrame(load_feedback(query=query, limit=limit))
