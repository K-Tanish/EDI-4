"""
GET /api/v1/blockchain/verify/{txHash} — blockchain verification endpoint
Implements: Requirements 11.4
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["blockchain"])


@router.get("/blockchain/verify/{tx_hash}", status_code=200)
async def verify_tx(tx_hash: str):
    """
    Verify a blockchain transaction hash against Ganache.
    Returns receipt details if found.
    """
    try:
        from blockchain.blockchain_client import BlockchainClient
        client = BlockchainClient.from_deployed_json()
        receipt = client.verify_tx(tx_hash)
        return {"verified": receipt["status"] == 1, "receipt": receipt}
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Blockchain node not configured")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
