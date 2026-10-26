"""
MongoDB indexes — Task 10.1
Implements: Requirements 10.4, 10.5
"""
from __future__ import annotations

import time

from pymongo import ASCENDING, DESCENDING, IndexModel
from db.mongo import get_db


def create_indexes():
    db = get_db()
    if db is None:
        print("[Indexes] MongoDB unavailable — skipping index creation.")
        return

    # Unique index on tourists.idHash
    db["tourists"].create_index("idHash", unique=True, sparse=True)

    # TTL index on location_history — expire 90 days after visitEnd
    # We store expireAt = visitEnd + 90 days on each document
    db["location_history"].create_index(
        "expireAt",
        expireAfterSeconds=0,
        name="ttl_location_history",
    )

    # Compound index on incidents
    db["incidents"].create_index(
        [("touristId", ASCENDING), ("status", ASCENDING)],
        name="idx_incidents_tourist_status",
    )

    # Audit log index
    db["audit_log"].create_index(
        [("userId", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_audit_log",
    )


def purge_tourist_data(tourist_id: str):
    """On-demand deletion of all tourist data within 24 h (Requirement 10.5)."""
    db = get_db()
    db["location_history"].delete_many({"touristId": tourist_id})
    db["tourists"].update_one(
        {"touristId": tourist_id},
        {"$set": {"status": "PURGED", "purgedAt": int(time.time() * 1000)}},
    )
