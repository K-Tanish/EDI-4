"""
POST /api/v1/incidents  &  GET /api/v1/incidents — Task 8 / 19.1
Implements: Requirements 8.4, 8.5, 8.6, 8.7
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional

from db.mongo import get_db
from middleware.auth import require_authority

router = APIRouter(tags=["incidents"])


class IncidentCreate(BaseModel):
    touristId: str
    linkedSosId: Optional[str] = None
    linkedAlertId: Optional[str] = None


class IncidentUpdate(BaseModel):
    status: Literal["IN_PROGRESS", "RESOLVED"]
    officerId: Optional[str] = None


@router.get("/incidents", status_code=200)
async def list_incidents(_=Depends(require_authority)):
    db = get_db()
    if db is None:
        return {"incidents": []}
    incidents = list(db["incidents"].find({}, {"_id": 0}))
    return {"incidents": incidents}


@router.post("/incidents", status_code=201)
async def create_incident(body: IncidentCreate, _=Depends(require_authority)):
    db = get_db()
    now = int(time.time() * 1000)
    incident = {
        "incidentId": str(uuid.uuid4()),
        "touristId": body.touristId,
        "linkedSosId": body.linkedSosId,
        "linkedAlertId": body.linkedAlertId,
        "status": "OPEN",
        "createdAt": now,
        "resolvedAt": None,
        "officerId": None,
        "blockchainTxHash": None,
    }
    if db is not None:
        db["incidents"].insert_one(incident)
    return {"incidentId": incident["incidentId"]}


@router.patch("/incidents/{incident_id}", status_code=200)
async def update_incident(incident_id: str, body: IncidentUpdate, _=Depends(require_authority)):
    db = get_db()
    updates: dict = {"status": body.status}
    if body.status == "RESOLVED":
        updates["resolvedAt"] = int(time.time() * 1000)
    if body.officerId:
        updates["officerId"] = body.officerId
    if db is not None:
        result = db["incidents"].update_one({"incidentId": incident_id}, {"$set": updates})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Incident not found")
    return {"status": "ok"}
