"""
POST /api/v1/location — Task 4.1
Implements: Requirements 3.3, 3.6, 10.4
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.firebase_admin import get_firebase_db
from db.mongo import get_db
from middleware.auth import require_tourist
from workers.anomaly_detector import location_queue

router = APIRouter(tags=["location"])


class LocationPayload(BaseModel):
    touristId: str
    latitude: float
    longitude: float
    timestamp: int
    accuracy: float = 0.0
    isOfflineBuffered: bool = False


@router.post("/location", status_code=200)
async def update_location(body: LocationPayload, _=Depends(require_tourist)):
    update = body.model_dump()

    # Write to Firebase live location
    fb = get_firebase_db()
    if fb:
        fb.child(f"LiveLocation/{body.touristId}").set({
            "latitude": body.latitude,
            "longitude": body.longitude,
            "time": body.timestamp,          # dashboard + app both read "time"
            "status": "ACTIVE",
            "safetyScore": 100,
            "safetyLabel": "SAFE",
            "zoneRiskLevel": "LOW",
        })
        fb.child(f"LocationHistory/{body.touristId}").push({
            "latitude": body.latitude,
            "longitude": body.longitude,
            "time": body.timestamp,
        })

    # Write to MongoDB with TTL anchor
    db = get_db()
    if db is not None:
        db["location_history"].insert_one({
            **update,
            "recordedAt": int(time.time() * 1000),
        })

    # Feed anomaly detector worker
    await location_queue.put({
        "touristId": body.touristId,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "timestamp": body.timestamp,
        "accuracy": body.accuracy,
        "isOfflineBuffered": body.isOfflineBuffered,
    })

    return {"status": "ok"}
