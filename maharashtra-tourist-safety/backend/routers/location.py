"""
POST /api/v1/location — Task 4.1
Implements: Requirements 3.3, 3.6, 10.4
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from typing import Optional

from db.firebase_admin import get_firebase_db
from db.mongo import get_db
from middleware.auth import require_tourist
from workers.anomaly_detector import get_pipeline_telemetry, location_queue

router = APIRouter(tags=["location"])


class LocationPayload(BaseModel):
    touristId: str
    latitude: float
    longitude: float
    timestamp: int
    accuracy: float = 0.0
    isOfflineBuffered: bool = False
    emittedAtMs: Optional[int] = None


@router.post("/location", status_code=200)
async def update_location(body: LocationPayload, _=Depends(require_tourist)):
    received_at_ms = int(time.time() * 1000)
    update = body.model_dump()

    # Write to Firebase live location
    fb = get_firebase_db()
    if fb:
        fb.child(f"LiveLocation/{body.touristId}").set({
            "latitude": body.latitude,
            "longitude": body.longitude,
            "time": body.timestamp,          # dashboard + app both read "time"
            "simulatedTime": body.timestamp,
            "actualEmittedAtMs": body.emittedAtMs or received_at_ms,
            "receivedAtWallClockMs": received_at_ms,
            "status": "ACTIVE",
            "safetyScore": 100,
            "safetyLabel": "SAFE",
            "zoneRiskLevel": "LOW",
        })
        fb.child(f"LocationHistory/{body.touristId}").push({
            "latitude": body.latitude,
            "longitude": body.longitude,
            "time": body.timestamp,
            "simulatedTime": body.timestamp,
            "receivedAtWallClockMs": received_at_ms,
        })

    # Write to MongoDB with TTL anchor
    db = get_db()
    if db is not None:
        db["location_history"].insert_one({
            **update,
            "receivedAtWallClockMs": received_at_ms,
            "recordedAt": received_at_ms,
        })

    # Feed anomaly detector worker with distinct arrival timestamp
    await location_queue.put({
        "touristId": body.touristId,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "timestamp": body.timestamp,
        "accuracy": body.accuracy,
        "isOfflineBuffered": body.isOfflineBuffered,
        "emittedAtMs": body.emittedAtMs or received_at_ms,
        "receivedAt": received_at_ms,
    })

    return {
        "status": "ok",
        "touristId": body.touristId,
        "simulatedTimestamp": body.timestamp,
        "receivedAtWallClockMs": received_at_ms,
    }


@router.get("/location/telemetry", status_code=200)
async def get_telemetry():
    """Inspect pipeline telemetry distinguishing tourist IDs and recorded timestamps."""
    return get_pipeline_telemetry()
