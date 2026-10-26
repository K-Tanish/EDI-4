"""
AnomalyDetector async worker — Task 8.1
Implements: Requirements 7.1–7.7
Runs as a separate asyncio task; consumes from a shared asyncio.Queue.
"""
from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from db.firebase_admin import get_firebase_db
from db.mongo import get_db

# ── Constants ──────────────────────────────────────────────────────────────────
_STATIONARY_DIST_M = 10        # metres
_STATIONARY_WINDOW_MS = 600_000  # 10 minutes
_ABNORMAL_SPEED_MS = 30        # metres/second
_GPS_LOSS_TIMEOUT_MS = 300_000  # 5 minutes
_ROUTE_DEVIATION_M = 500
_MIN_POINTS = 3

# Shared queue — location events are pushed here by the location router
location_queue: asyncio.Queue = asyncio.Queue()

# Per-tourist sliding window of recent location points
_history: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=50))
_last_gps: Dict[str, int] = {}  # touristId -> last timestamp_ms


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _write_alert(alert: dict):
    db = get_db()
    if db is not None:
        db["anomaly_alerts"].insert_one({**alert})
    fb = get_firebase_db()
    if fb:
        fb.child("Alerts").push(alert)


def _analyse(tourist_id: str, point: dict) -> Optional[dict]:
    history = _history[tourist_id]
    history.append(point)
    _last_gps[tourist_id] = point["timestamp"]

    if len(history) < _MIN_POINTS:
        return None

    pts = list(history)
    latest = pts[-1]
    now_ms = latest["timestamp"]

    # Rule 1: Stationary check
    window = [p for p in pts if now_ms - p["timestamp"] <= _STATIONARY_WINDOW_MS]
    if len(window) >= _MIN_POINTS:
        max_dist = max(
            _haversine(p["latitude"], p["longitude"], latest["latitude"], latest["longitude"])
            for p in window
        )
        if max_dist < _STATIONARY_DIST_M:
            return _make_alert(tourist_id, "STATIONARY", "LOW", latest)

    # Rule 2: Abnormal speed
    prev = pts[-2]
    dt_s = (latest["timestamp"] - prev["timestamp"]) / 1000
    if dt_s > 0:
        dist = _haversine(prev["latitude"], prev["longitude"], latest["latitude"], latest["longitude"])
        speed = dist / dt_s
        if speed > _ABNORMAL_SPEED_MS:
            return _make_alert(tourist_id, "ABNORMAL_SPEED", "MEDIUM", latest)

    return None


def _make_alert(tourist_id: str, alert_type: str, risk_level: str, point: dict) -> dict:
    return {
        "alertId": str(uuid.uuid4()),
        "touristId": tourist_id,
        "type": alert_type,
        "riskLevel": risk_level,
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "timestamp": point["timestamp"],
        "acknowledged": False,
        "escalatedAt": None,
        "createdAt": int(time.time() * 1000),
    }


async def run_worker():
    """Main worker loop — consume from location_queue indefinitely."""
    while True:
        try:
            event = await asyncio.wait_for(location_queue.get(), timeout=5.0)
            tourist_id = event.get("touristId")
            if not tourist_id:
                continue
            alert = _analyse(tourist_id, event)
            if alert:
                _write_alert(alert)
        except asyncio.TimeoutError:
            # Check GPS loss for all tracked tourists
            now_ms = int(time.time() * 1000)
            for tid, last_ts in list(_last_gps.items()):
                if now_ms - last_ts > _GPS_LOSS_TIMEOUT_MS:
                    alert = {
                        "alertId": str(uuid.uuid4()),
                        "touristId": tid,
                        "type": "GPS_LOSS",
                        "riskLevel": "HIGH",
                        "latitude": 0.0,
                        "longitude": 0.0,
                        "timestamp": now_ms,
                        "acknowledged": False,
                        "escalatedAt": None,
                        "createdAt": now_ms,
                    }
                    _write_alert(alert)
                    del _last_gps[tid]
        except Exception:
            pass
