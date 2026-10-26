"""
IdentityVerifier service — Task 3.1
Implements: Requirements 1.1, 1.2, 1.3, 1.5, 1.7
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from db.mongo import get_db
from utils.crypto import hash_identity
from utils.validators import validate_aadhaar, validate_passport


class DuplicateRegistrationError(Exception):
    pass


class IdentityVerifier:
    def __init__(self, blockchain_client=None):
        self._bc = blockchain_client

    async def register(
        self,
        id_type: str,
        id_value: str,
        visit_start_ms: int,
        visit_end_ms: int,
        region: str,
        name: str = "",
    ) -> dict:
        # 1. Format validation
        if id_type == "aadhaar":
            validate_aadhaar(id_value)
        elif id_type == "passport":
            validate_passport(id_value)
        else:
            raise ValueError(f"Unknown id_type: {id_type}")

        # 2. Hash — raw value never stored
        id_hash = hash_identity(id_value)

        # 3. Duplicate check (same hash, visitEnd > now)
        now_ms = int(time.time() * 1000)
        db = get_db()
        if db is not None:
            existing = db["tourists"].find_one(
                {"idHash": id_hash, "visitEnd": {"$gt": now_ms}, "status": "ACTIVE"}
            )
            if existing:
                raise DuplicateRegistrationError(
                    "Active Digital_Tourist_ID already exists for this identity"
                )

        # 4. Issue UUID tourist ID
        tourist_id = str(uuid.uuid4())
        record = {
            "touristId": tourist_id,
            "idHash": id_hash,
            "name": name,
            "visitStart": visit_start_ms,
            "visitEnd": visit_end_ms,
            "status": "ACTIVE",
            "blockchainTxHash": None,
            "region": region,
        }
        if db is not None:
            db["tourists"].insert_one(record)

        # 5. Async blockchain write — non-blocking
        tx_hash: Optional[str] = None
        if self._bc:
            try:
                id_hash_bytes = bytes.fromhex(id_hash)
                visit_start_s = visit_start_ms // 1000
                visit_end_s = visit_end_ms // 1000
                loop = asyncio.get_event_loop()
                tx_hash = await loop.run_in_executor(
                    None,
                    self._bc.register_tourist,
                    id_hash_bytes,
                    visit_start_s,
                    visit_end_s,
                )
                if db is not None:
                    db["tourists"].update_one(
                        {"touristId": tourist_id},
                        {"$set": {"blockchainTxHash": tx_hash}},
                    )
            except Exception:
                # Blockchain timeout — ID already issued, retry handled separately
                pass

        return {
            "touristId": tourist_id,
            "validUntil": visit_end_ms,
            "txHash": tx_hash,
        }
