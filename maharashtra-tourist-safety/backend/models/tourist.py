"""Pydantic data models for core domain entities."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TouristRecord(BaseModel):
    touristId: str = Field(..., description="UUID v4 string")
    idHash: str = Field(..., description="SHA-256 hex digest of raw identity document")
    visitStart: int = Field(..., description="Visit start Unix timestamp in milliseconds")
    visitEnd: int = Field(..., description="Visit end Unix timestamp in milliseconds")
    status: Literal["ACTIVE", "EXPIRED"]
    blockchainTxHash: Optional[str] = None
    region: str


class LocationUpdate(BaseModel):
    touristId: str
    latitude: float
    longitude: float
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    accuracy: float = Field(..., description="Accuracy in metres")
    isOfflineBuffered: bool


class SosEvent(BaseModel):
    sosId: str = Field(..., description="UUID v4 string")
    touristId: str
    latitude: float
    longitude: float
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    status: Literal["ACTIVE", "ACKNOWLEDGED", "RESOLVED"]
    blockchainTxHash: Optional[str] = None
    resolvedAt: Optional[int] = None
    resolvedBy: Optional[str] = None


class Incident(BaseModel):
    incidentId: str = Field(..., description="UUID v4 string")
    linkedSosId: Optional[str] = None
    linkedAlertId: Optional[str] = None
    touristId: str
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]
    createdAt: int = Field(..., description="Unix timestamp in milliseconds")
    resolvedAt: Optional[int] = None
    officerId: Optional[str] = None
    blockchainTxHash: Optional[str] = None


class GeoFenceZone(BaseModel):
    zoneId: str
    name: str
    type: Literal["URBAN", "COASTAL", "HILL_STATION", "FOREST", "HERITAGE"]
    riskLevel: Literal["LOW", "MEDIUM", "HIGH", "RESTRICTED"]
    centerLat: float
    centerLng: float
    radiusMeters: float
    active: bool
    updatedAt: int = Field(..., description="Unix timestamp in milliseconds")


class AnomalyAlert(BaseModel):
    alertId: str = Field(..., description="UUID v4 string")
    touristId: str
    type: Literal["STATIONARY", "ABNORMAL_SPEED", "GPS_LOSS", "ROUTE_DEVIATION"]
    riskLevel: Literal["LOW", "MEDIUM", "HIGH"]
    latitude: float
    longitude: float
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    acknowledged: bool
    escalatedAt: Optional[int] = None
