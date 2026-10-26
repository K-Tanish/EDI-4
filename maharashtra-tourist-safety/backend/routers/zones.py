"""
GET /api/v1/zones  &  POST/PATCH /api/v1/zones — Task 6.2
Implements: Requirements 13.2, 13.3
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional

from db.firebase_admin import get_firebase_db
from db.mongo import get_db
from middleware.auth import require_authority

router = APIRouter(tags=["zones"])

# ── Seed data (Maharashtra zone registry) ─────────────────────────────────────
MAHARASHTRA_ZONES = [
    {"name": "Mumbai Urban Core",    "type": "URBAN",        "riskLevel": "MEDIUM",     "centerLat": 19.0760, "centerLng": 72.8777, "radiusMeters": 15000},
    {"name": "Dharavi",              "type": "URBAN",        "riskLevel": "HIGH",       "centerLat": 19.0390, "centerLng": 72.8530, "radiusMeters": 2000},
    {"name": "Konkan Coastal Belt",  "type": "COASTAL",      "riskLevel": "MEDIUM",     "centerLat": 17.0000, "centerLng": 73.2500, "radiusMeters": 50000},
    {"name": "Ratnagiri Coastal",    "type": "COASTAL",      "riskLevel": "HIGH",       "centerLat": 16.9902, "centerLng": 73.3120, "radiusMeters": 10000},
    {"name": "Mahabaleshwar",        "type": "HILL_STATION", "riskLevel": "LOW",        "centerLat": 17.9237, "centerLng": 73.6586, "radiusMeters": 8000},
    {"name": "Lonavala",             "type": "HILL_STATION", "riskLevel": "LOW",        "centerLat": 18.7481, "centerLng": 73.4072, "radiusMeters": 5000},
    {"name": "Tadoba Tiger Reserve", "type": "FOREST",       "riskLevel": "RESTRICTED", "centerLat": 20.2280, "centerLng": 79.3950, "radiusMeters": 30000},
    {"name": "Melghat Tiger Reserve","type": "FOREST",       "riskLevel": "RESTRICTED", "centerLat": 21.5000, "centerLng": 77.0000, "radiusMeters": 40000},
    {"name": "Ajanta Caves",         "type": "HERITAGE",     "riskLevel": "LOW",        "centerLat": 20.5519, "centerLng": 75.7033, "radiusMeters": 3000},
    {"name": "Ellora Caves",         "type": "HERITAGE",     "riskLevel": "LOW",        "centerLat": 20.0258, "centerLng": 75.1780, "radiusMeters": 3000},
    {"name": "Nagpur Urban",         "type": "URBAN",        "riskLevel": "MEDIUM",     "centerLat": 21.1458, "centerLng": 79.0882, "radiusMeters": 12000},
    {"name": "Pune Urban Core",      "type": "URBAN",        "riskLevel": "MEDIUM",     "centerLat": 18.5204, "centerLng": 73.8567, "radiusMeters": 12000},
]


def seed_zones_if_empty():
    db = get_db()
    if db is None:
        return
    if db["zones"].count_documents({}) == 0:
        now = int(time.time() * 1000)
        docs = [
            {**z, "zoneId": str(uuid.uuid4()), "active": True, "updatedAt": now}
            for z in MAHARASHTRA_ZONES
        ]
        db["zones"].insert_many(docs)


# ── Request models ─────────────────────────────────────────────────────────────
class ZoneBody(BaseModel):
    name: str
    type: Literal["URBAN", "COASTAL", "HILL_STATION", "FOREST", "HERITAGE"]
    riskLevel: Literal["LOW", "MEDIUM", "HIGH", "RESTRICTED"]
    centerLat: float
    centerLng: float
    radiusMeters: float
    active: bool = True


class ZonePatch(BaseModel):
    riskLevel: Optional[Literal["LOW", "MEDIUM", "HIGH", "RESTRICTED"]] = None
    active: Optional[bool] = None
    radiusMeters: Optional[float] = None


# ── Routes ─────────────────────────────────────────────────────────────────────
@router.get("/zones", status_code=200)
async def list_zones():
    seed_zones_if_empty()
    db = get_db()
    if db is None:
        # Return hardcoded Maharashtra zones when DB is unavailable
        now = int(time.time() * 1000)
        zones = [{**z, "zoneId": f"default-{i}", "active": True, "updatedAt": now}
                 for i, z in enumerate(MAHARASHTRA_ZONES)]
        return {"zones": zones}
    zones = list(db["zones"].find({"active": True}, {"_id": 0}))
    return {"zones": zones}


@router.post("/zones", status_code=201)
async def create_zone(body: ZoneBody, _=Depends(require_authority)):
    db = get_db()
    now = int(time.time() * 1000)
    zone = {**body.model_dump(), "zoneId": str(uuid.uuid4()), "updatedAt": now}
    if db is not None:
        db["zones"].insert_one(zone)
    _sync_zone_to_firebase(zone)
    return {"zoneId": zone["zoneId"]}


@router.patch("/zones/{zone_id}", status_code=200)
async def update_zone(zone_id: str, body: ZonePatch, _=Depends(require_authority)):
    db = get_db()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updatedAt"] = int(time.time() * 1000)
    if db is not None:
        result = db["zones"].update_one({"zoneId": zone_id}, {"$set": updates})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Zone not found")
        zone = db["zones"].find_one({"zoneId": zone_id}, {"_id": 0})
        _sync_zone_to_firebase(zone)
    return {"status": "ok"}


def _sync_zone_to_firebase(zone: dict):
    fb = get_firebase_db()
    if fb and zone:
        fb.child(f"Zones/{zone['zoneId']}").set({
            k: v for k, v in zone.items() if k != "_id"
        })
