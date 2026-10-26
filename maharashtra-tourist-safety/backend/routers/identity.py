"""
POST /api/v1/register — Task 3.2
Implements: Requirements 1.1, 1.5, 1.7
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel, Field

from config import settings
from services.identity_verifier import IdentityVerifier, DuplicateRegistrationError
from utils.validators import ValidationError as AppValidationError

router = APIRouter(tags=["identity"])

_verifier = IdentityVerifier()  # blockchain_client injected at startup if available


class RegisterRequest(BaseModel):
    idType: str = Field(..., description="'aadhaar' or 'passport'")
    idValue: str = Field(..., description="Raw identity document number")
    visitStart: int = Field(..., description="Visit start Unix timestamp ms")
    visitEnd: int = Field(..., description="Visit end Unix timestamp ms")
    region: str = Field(default="Maharashtra")
    name: str = Field(default="", description="Tourist's full name")


def _issue_jwt(tourist_id: str, visit_end_ms: int) -> str:
    """Issue a signed JWT for the tourist."""
    expire = datetime.datetime.utcfromtimestamp(visit_end_ms / 1000)
    payload = {
        "sub": tourist_id,
        "role": "TOURIST",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_tourist(body: RegisterRequest):
    try:
        result = await _verifier.register(
            id_type=body.idType,
            id_value=body.idValue,
            visit_start_ms=body.visitStart,
            visit_end_ms=body.visitEnd,
            region=body.region,
            name=body.name,
        )
    except AppValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DuplicateRegistrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    token = _issue_jwt(result["touristId"], result["validUntil"])

    # If blockchain write is still pending, return 202
    http_status = "accepted" if result["txHash"] is None else "ok"
    return {"status": http_status, "token": token, **result}
