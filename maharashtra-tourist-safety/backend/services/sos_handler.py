"""
SosHandler service — Task 7.1
Implements: Requirements 6.2, 6.3, 6.4, 6.5
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from db.firebase_admin import get_firebase_db
from db.mongo import get_db


class SosHandler:
    def __init__(self, blockchain_client=None):
        self._bc = blockchain_client

    async def trigger(
        self,
        tourist_id: str,
        latitude: float,
        longitude: float,
        timestamp_ms: Optional[int] = None,
    ) -> dict:
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        sos_id = str(uuid.uuid4())
        event = {
            "sosId": sos_id,
            "touristId": tourist_id,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp_ms,
            "status": "ACTIVE",
            "blockchainTxHash": None,
            "resolvedAt": None,
            "resolvedBy": None,
        }

        db = get_db()
        if db is not None:
            db["incidents"].insert_one({**event, "incidentId": sos_id, "linkedSosId": sos_id,
                                        "status": "OPEN", "createdAt": timestamp_ms})

        # Write to Firebase SOS + Alerts paths
        fb = get_firebase_db()
        if fb:
            fb.child(f"SOS/{tourist_id}").set({
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp_ms,
                "status": "ACTIVE",
            })
            fb.child("Alerts").push({
                "touristId": tourist_id,
                "type": "SOS",
                "riskLevel": "HIGH",
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp_ms,
                "sosId": sos_id,
            })

        # Async blockchain write
        tx_hash: Optional[str] = None
        if self._bc:
            try:
                loop = asyncio.get_event_loop()
                lat_micro = int(latitude * 1_000_000)
                lng_micro = int(longitude * 1_000_000)
                tx_hash, _ = await loop.run_in_executor(
                    None,
                    self._bc.record_sos_event,
                    0,
                    lat_micro,
                    lng_micro,
                    timestamp_ms // 1000,
                )
                if db is not None:
                    db["incidents"].update_one(
                        {"sosId": sos_id},
                        {"$set": {"blockchainTxHash": tx_hash}},
                    )
            except Exception:
                pass

        return {"sosId": sos_id, "status": "ACTIVE", "txHash": tx_hash}

    async def resolve(self, sos_id: str, officer_id: str) -> dict:
        now_ms = int(time.time() * 1000)
        db = get_db()
        if db is None:
            raise ValueError("Database unavailable")
        result = db["incidents"].update_one(
            {"sosId": sos_id},
            {"$set": {"status": "RESOLVED", "resolvedAt": now_ms, "resolvedBy": officer_id}},
        )
        if result.matched_count == 0:
            raise ValueError(f"SOS {sos_id} not found")

        incident = db["incidents"].find_one({"sosId": sos_id})
        tourist_id = incident.get("touristId", "") if incident else ""

        fb = get_firebase_db()
        if fb and tourist_id:
            fb.child(f"SOS/{tourist_id}").update({"status": "RESOLVED"})

        return {"sosId": sos_id, "status": "RESOLVED"}
