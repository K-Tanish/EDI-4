"""
POST /api/v1/sos  &  PATCH /api/v1/incidents/{id} — Task 7.2
Implements: Requirements 6.2, 6.6, 6.7, 8.7
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from middleware.auth import require_tourist, require_authority
from services.sos_handler import SosHandler

router = APIRouter(tags=["sos"])
_handler = SosHandler()


class SosRequest(BaseModel):
    touristId: str
    latitude: float
    longitude: float
    timestamp: Optional[int] = None


class ResolveRequest(BaseModel):
    officerId: str


@router.post("/sos", status_code=200)
async def trigger_sos(body: SosRequest, _=Depends(require_tourist)):
    try:
        result = await _handler.trigger(
            tourist_id=body.touristId,
            latitude=body.latitude,
            longitude=body.longitude,
            timestamp_ms=body.timestamp,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@router.patch("/incidents/{incident_id}", status_code=200)
async def resolve_incident(incident_id: str, body: ResolveRequest, _=Depends(require_authority)):
    try:
        result = await _handler.resolve(sos_id=incident_id, officer_id=body.officerId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result
