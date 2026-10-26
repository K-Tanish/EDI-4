"""
Escalation scheduler — Task 8.2
Implements: Requirement 7.8
Polls unacknowledged alerts every 60 s; escalates risk level after 5-minute timeout.
"""
from __future__ import annotations

import asyncio
import time

from db.firebase_admin import get_firebase_db
from db.mongo import get_db

_ESCALATION_TIMEOUT_MS = 300_000  # 5 minutes
_LEVEL_UP = {"LOW": "MEDIUM", "MEDIUM": "HIGH"}


async def run_scheduler():
    while True:
        await asyncio.sleep(60)
        try:
            _escalate_pending()
        except Exception:
            pass


def _escalate_pending():
    db = get_db()
    if db is None:
        return
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - _ESCALATION_TIMEOUT_MS

    alerts = list(db["anomaly_alerts"].find({
        "acknowledged": False,
        "escalatedAt": None,
        "createdAt": {"$lte": cutoff},
        "riskLevel": {"$in": ["LOW", "MEDIUM"]},
    }))

    for alert in alerts:
        new_level = _LEVEL_UP.get(alert["riskLevel"])
        if not new_level:
            continue
        db["anomaly_alerts"].update_one(
            {"alertId": alert["alertId"]},
            {"$set": {"riskLevel": new_level, "escalatedAt": now_ms}},
        )
        fb = get_firebase_db()
        if fb:
            fb.child(f"Alerts/{alert['alertId']}").update({
                "riskLevel": new_level,
                "escalatedAt": now_ms,
            })
