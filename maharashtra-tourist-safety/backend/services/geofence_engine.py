"""
GeoFenceEngine service — Task 6.1
Implements: Requirements 4.1, 4.2, 4.4, 4.5, 4.6
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Optional

from db.firebase_admin import get_firebase_db
from db.mongo import get_db

# In-memory cooldown: (touristId, zoneId) -> last_alert_timestamp_s
_cooldown: dict[tuple[str, str], float] = {}
_COOLDOWN_SECONDS = 300  # 5 minutes


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_zones(
    tourist_id: str,
    latitude: float,
    longitude: float,
    timestamp_ms: int,
    blockchain_client=None,
) -> Optional[dict]:
    """
    Check tourist location against all active zones.
    Returns the matched zone dict if an alert was fired, else None.
    """
    db = get_db()
    zones = list(db["zones"].find({"active": True})) if db is not None else []

    for zone in zones:
        dist = haversine_meters(latitude, longitude, zone["centerLat"], zone["centerLng"])
        if dist > zone["radiusMeters"]:
            continue

        risk = zone.get("riskLevel", "LOW")
        if risk not in ("HIGH", "RESTRICTED"):
            continue

        # Cooldown check
        key = (tourist_id, zone["zoneId"])
        now_s = time.time()
        if now_s - _cooldown.get(key, 0) < _COOLDOWN_SECONDS:
            continue

        _cooldown[key] = now_s

        # Write alert to Firebase
        alert = {
            "alertId": str(uuid.uuid4()),
            "touristId": tourist_id,
            "type": "ZONE_ENTRY",
            "riskLevel": risk,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp_ms,
            "zoneName": zone["name"],
            "acknowledged": False,
        }
        fb = get_firebase_db()
        if fb:
            fb.child("Alerts").push(alert)

        # Blockchain log for RESTRICTED zones (async — fire and forget)
        if risk == "RESTRICTED" and blockchain_client:
            try:
                blockchain_client.record_zone_entry(
                    0,  # tokenId resolved by caller if needed
                    zone["name"],
                    timestamp_ms // 1000,
                )
            except Exception:
                pass

        return zone

    return None
