"""
GET /api/v1/tourists/live — live tourist state for the web dashboard
Returns all registered tourists with their latest location and safety score.
Falls back to in-memory demo data when MongoDB/Firebase are unavailable.
"""
from __future__ import annotations

import time
from fastapi import APIRouter
from db.mongo import get_db
from db.firebase_admin import get_firebase_db

router = APIRouter(tags=["tourists"])

# Demo seed — used when no DB is available
DEMO_TOURISTS = [
    {"touristId": "t-mumbai-001", "name": "Rahul S.",  "latitude": 19.0760, "longitude": 72.8777, "safetyLabel": "SAFE",    "safetyScore": 82, "zoneName": "Mumbai Urban Core",   "status": "ACTIVE"},
    {"touristId": "t-pune-002",   "name": "Priya M.",  "latitude": 18.5204, "longitude": 73.8567, "safetyLabel": "CAUTION", "safetyScore": 55, "zoneName": "Pune Urban Core",      "status": "ACTIVE"},
    {"touristId": "t-tadoba-003", "name": "James W.",  "latitude": 20.2280, "longitude": 79.3950, "safetyLabel": "DANGER",  "safetyScore": 28, "zoneName": "Tadoba Tiger Reserve", "status": "ACTIVE"},
    {"touristId": "t-ajanta-004", "name": "Mei L.",    "latitude": 20.5519, "longitude": 75.7033, "safetyLabel": "SAFE",    "safetyScore": 91, "zoneName": "Ajanta Caves",         "status": "ACTIVE"},
    {"touristId": "t-konkan-005", "name": "Ahmed K.",  "latitude": 17.0000, "longitude": 73.2500, "safetyLabel": "CAUTION", "safetyScore": 61, "zoneName": "Konkan Coastal Belt",  "status": "ACTIVE"},
    {"touristId": "t-nagpur-006", "name": "Sara T.",   "latitude": 21.1458, "longitude": 79.0882, "safetyLabel": "SAFE",    "safetyScore": 77, "zoneName": "Nagpur Urban",         "status": "ACTIVE"},
    {"touristId": "t-dharavi-007","name": "Vikram P.", "latitude": 19.0390, "longitude": 72.8530, "safetyLabel": "DANGER",  "safetyScore": 31, "zoneName": "Dharavi",              "status": "SOS"},
    {"touristId": "t-lonavala-008","name":"Chen Y.",   "latitude": 18.7481, "longitude": 73.4072, "safetyLabel": "SAFE",    "safetyScore": 88, "zoneName": "Lonavala",             "status": "ACTIVE"},
]

DEMO_ALERTS = [
    {"alertId": "a-001", "type": "SOS",           "touristId": "t-dharavi-007", "riskLevel": "HIGH",   "zoneName": "Dharavi",              "timestamp": int(time.time()*1000) - 120000},
    {"alertId": "a-002", "type": "ZONE_ENTRY",    "touristId": "t-tadoba-003",  "riskLevel": "HIGH",   "zoneName": "Tadoba Tiger Reserve", "timestamp": int(time.time()*1000) - 300000},
    {"alertId": "a-003", "type": "STATIONARY",    "touristId": "t-konkan-005",  "riskLevel": "MEDIUM", "zoneName": "Konkan Coastal Belt",  "timestamp": int(time.time()*1000) - 600000},
    {"alertId": "a-004", "type": "ABNORMAL_SPEED","touristId": "t-pune-002",    "riskLevel": "MEDIUM", "zoneName": "Pune Urban Core",      "timestamp": int(time.time()*1000) - 900000},
]


@router.get("/tourists/live", status_code=200)
async def get_live_tourists():
    db = get_db()
    fb = get_firebase_db()

    if db is None and fb is None:
        # No backends — return demo data
        return {"tourists": DEMO_TOURISTS, "alerts": DEMO_ALERTS, "source": "demo"}

    tourists = []

    # Try Firebase first for live locations
    if fb:
        try:
            live_data = fb.child("LiveLocation").get()
            tourist_data = fb.child("Tourists").get()
            if live_data and isinstance(live_data, dict):
                for tid, loc in live_data.items():
                    if not isinstance(loc, dict):
                        continue
                    t_info = (tourist_data or {}).get(tid, {})
                    tourists.append({
                        "touristId": tid,
                        "name": t_info.get("name", tid[:12]),
                        "latitude": loc.get("latitude", 0),
                        "longitude": loc.get("longitude", 0),
                        "safetyLabel": loc.get("safetyLabel", "SAFE"),
                        "safetyScore": loc.get("safetyScore", 100),
                        "zoneName": loc.get("zoneName", ""),
                        "status": loc.get("status", "ACTIVE"),
                        "timestamp": loc.get("timestamp", 0),
                    })
        except Exception as e:
            print(f"[tourists/live] Firebase read error: {e}")

    # Fallback to MongoDB if Firebase gave nothing
    if not tourists and db is not None:
        try:
            pipeline = [
                {"$sort": {"recordedAt": -1}},
                {"$group": {"_id": "$touristId", "latest": {"$first": "$$ROOT"}}},
            ]
            for doc in db["location_history"].aggregate(pipeline):
                loc = doc["latest"]
                tourists.append({
                    "touristId": loc.get("touristId"),
                    "name": loc.get("touristId", "")[:12],
                    "latitude": loc.get("latitude", 0),
                    "longitude": loc.get("longitude", 0),
                    "safetyLabel": loc.get("safetyLabel", "SAFE"),
                    "safetyScore": loc.get("safetyScore", 100),
                    "zoneName": loc.get("zoneName", ""),
                    "status": "ACTIVE",
                    "timestamp": loc.get("timestamp", 0),
                })
        except Exception as e:
            print(f"[tourists/live] MongoDB read error: {e}")

    # Get recent alerts
    alerts = []
    if db is not None:
        try:
            cutoff = int(time.time() * 1000) - 24 * 60 * 60 * 1000  # last 24h
            raw = list(db["alerts"].find({"timestamp": {"$gte": cutoff}}, {"_id": 0}).sort("timestamp", -1).limit(50))
            alerts = raw
        except Exception as e:
            print(f"[tourists/live] alerts read error: {e}")

    if not tourists:
        return {"tourists": DEMO_TOURISTS, "alerts": DEMO_ALERTS, "source": "demo"}

    return {"tourists": tourists, "alerts": alerts, "source": "live"}
