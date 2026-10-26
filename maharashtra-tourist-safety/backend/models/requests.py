"""Pydantic request body models for API endpoints."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    identityType: Literal["AADHAAR", "PASSPORT"]
    identityValue: str
    visitDurationDays: int = Field(..., ge=1, le=90, description="Visit duration in days (1–90)")


class LocationRequest(BaseModel):
    touristId: str
    latitude: float
    longitude: float
    accuracy: float = Field(..., description="Accuracy in metres")
    isOfflineBuffered: bool


class SosRequest(BaseModel):
    touristId: str
    latitude: float
    longitude: float


class IncidentUpdateRequest(BaseModel):
    status: Literal["IN_PROGRESS", "RESOLVED"]
    officerId: str
