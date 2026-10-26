"""
GET /api/v1/score/{touristId} — Task 5.2
Implements: Requirements 5.2, 5.3
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter

from db.firebase_admin import get_firebase_db
from db.mongo import get_db
from services.risk_scorer import compute_score

router = APIRouter(tags=["score"])


@router.get("/score/{tourist_id}", status_code=200)
async def get_score(tourist_id: str):
    db = get_db()
    # No 404 on missing tourist — DB may have been offline during registration
    
    # Determine zone risk level from live location zone
    zone_risk = "MEDIUM"  # default
    fb = get_firebase_db()
    if fb:
        live = fb.child(f"LiveLocation/{tourist_id}").get()
        if live and isinstance(live, dict):
            zone_risk = live.get("zoneRiskLevel", "MEDIUM")

    # Incident density last 30 days
    incident_count = 0
    if db is not None:
        now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
        thirty_days_ms = 30 * 24 * 60 * 60 * 1000
        incident_count = db["incidents"].count_documents({
            "touristId": tourist_id,
            "createdAt": {"$gte": now_ms - thirty_days_ms},
        })

    current_hour = datetime.datetime.utcnow().hour
    score, label = compute_score(zone_risk, incident_count, current_hour)

    # Update Firebase live location with score
    if fb:
        fb.child(f"LiveLocation/{tourist_id}").update({
            "safetyScore": score,
            "safetyLabel": label,
        })

    return {"touristId": tourist_id, "score": score, "label": label}
