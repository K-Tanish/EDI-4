"""
blockchain_client.py — Web3.py wrapper for the TouristSafety smart contract.

Implements: Requirements 11.2, 11.5

All write methods submit a transaction and return the tx_hash immediately
without blocking on mining (async-friendly).  Use verify_tx() to check
confirmation status.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.exceptions import ContractLogicError

# ── Default paths ──────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent
_DEPLOYED_JSON = _BASE_DIR / "deployed.json"


class BlockchainClientError(Exception):
    """Raised for connection failures or transaction reverts."""


class BlockchainClient:
    """
    Thin wrapper around the TouristSafety smart contract.

    Parameters
    ----------
    ganache_url:      HTTP RPC URL of the Ganache node.
    contract_address: Deployed contract address (checksummed or plain hex).
    abi:              Contract ABI as a Python list.
    sender:           Default sender account; defaults to accounts[0].
    """

    def __init__(
        self,
        ganache_url: str,
        contract_address: str,
        abi: list[dict],
        sender: str | None = None,
    ) -> None:
        self._w3 = Web3(Web3.HTTPProvider(ganache_url))
        if not self._w3.is_connected():
            raise BlockchainClientError(
                f"Cannot connect to Ganache at {ganache_url}"
            )

        checksum_addr = Web3.to_checksum_address(contract_address)
        self._contract = self._w3.eth.contract(address=checksum_addr, abi=abi)

        self._sender: str = sender or self._w3.eth.accounts[0]
        self._w3.eth.default_account = self._sender

    # ── Factory helpers ────────────────────────────────────────────────────────

    @classmethod
    def from_deployed_json(
        cls,
        ganache_url: str = "http://127.0.0.1:8545",
        deployed_json: str | Path = _DEPLOYED_JSON,
        sender: str | None = None,
    ) -> "BlockchainClient":
        """
        Convenience constructor that reads address + ABI from deployed.json
        (produced by deploy.py).
        """
        path = Path(deployed_json)
        if not path.exists():
            raise FileNotFoundError(
                f"deployed.json not found at {path}. Run deploy.py first."
            )
        data = json.loads(path.read_text())
        return cls(ganache_url, data["address"], data["abi"], sender=sender)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _transact(self, fn) -> str:
        """
        Submit a contract function call as a transaction.

        Returns the tx_hash hex string immediately without waiting for mining.
        Raises BlockchainClientError on revert or connection issues.
        """
        try:
            tx_hash = fn.transact({"from": self._sender})
            return tx_hash.hex()
        except ContractLogicError as exc:
            raise BlockchainClientError(f"Transaction reverted: {exc}") from exc
        except Exception as exc:
            raise BlockchainClientError(f"Transaction failed: {exc}") from exc

    # ── Write methods ──────────────────────────────────────────────────────────

    def register_tourist(
        self,
        id_hash: bytes,
        visit_start: int,
        visit_end: int,
    ) -> str:
        """
        Register a tourist on-chain.

        Parameters
        ----------
        id_hash:     32-byte SHA-256 hash of the tourist's identity document.
        visit_start: Unix timestamp (seconds) for visit start.
        visit_end:   Unix timestamp (seconds) for visit end.

        Returns
        -------
        tx_hash: Hex string of the submitted transaction.
        """
        if len(id_hash) != 32:
            raise ValueError("id_hash must be exactly 32 bytes")
        fn = self._contract.functions.registerTourist(id_hash, visit_start, visit_end)
        return self._transact(fn)

    def record_sos_event(
        self,
        token_id: int,
        lat: int,
        lng: int,
        timestamp: int,
    ) -> tuple[str, str]:
        """
        Record an SOS event on-chain.

        Parameters
        ----------
        token_id:  Tourist's on-chain token ID.
        lat:       Latitude in micro-degrees (e.g. 18.975° → 18975000).
        lng:       Longitude in micro-degrees.
        timestamp: Unix timestamp (seconds) of the SOS trigger.

        Returns
        -------
        (tx_hash, event_id): tx_hash is the submitted transaction hex;
                             event_id is the keccak256 event identifier
                             computed locally to match the contract.
        """
        from web3 import Web3 as _W3

        # Compute event_id locally (mirrors contract: keccak256(tokenId, timestamp, lat, lng))
        event_id_bytes: bytes = _W3.solidity_keccak(
            ["uint256", "uint256", "int256", "int256"],
            [token_id, timestamp, lat, lng],
        )
        event_id_hex = event_id_bytes.hex()

        fn = self._contract.functions.recordSosEvent(token_id, lat, lng, timestamp)
        tx_hash = self._transact(fn)
        return tx_hash, event_id_hex

    def record_zone_entry(
        self,
        token_id: int,
        zone_name: str,
        timestamp: int,
    ) -> str:
        """
        Record a tourist entering a geo-fence zone on-chain.

        Parameters
        ----------
        token_id:  Tourist's on-chain token ID.
        zone_name: Human-readable zone name (e.g. "Tadoba Tiger Reserve").
        timestamp: Unix timestamp (seconds) of zone entry.

        Returns
        -------
        tx_hash: Hex string of the submitted transaction.
        """
        fn = self._contract.functions.recordZoneEntry(token_id, zone_name, timestamp)
        return self._transact(fn)

    def resolve_incident(
        self,
        incident_id: bytes,
        officer_id: str,
        timestamp: int,
    ) -> str:
        """
        Resolve an incident and anchor the resolution on-chain.

        Parameters
        ----------
        incident_id: 32-byte incident identifier (keccak256 generated off-chain).
        officer_id:  Ethereum address of the resolving officer (hex string).
        timestamp:   Unix timestamp (seconds) of resolution.

        Returns
        -------
        tx_hash: Hex string of the submitted transaction.
        """
        if len(incident_id) != 32:
            raise ValueError("incident_id must be exactly 32 bytes")
        officer_addr = Web3.to_checksum_address(officer_id)
        fn = self._contract.functions.resolveIncident(incident_id, officer_addr, timestamp)
        return self._transact(fn)

    # ── Read methods ───────────────────────────────────────────────────────────

    def verify_tx(self, tx_hash: str) -> dict[str, Any]:
        """
        Return transaction receipt details for a given tx_hash.

        Parameters
        ----------
        tx_hash: Hex string of the transaction to look up.

        Returns
        -------
        dict with keys: transactionHash, blockNumber, blockHash, status,
                        gasUsed, contractAddress, from, to, logs.
        Raises BlockchainClientError if the transaction is not found.
        """
        try:
            receipt = self._w3.eth.get_transaction_receipt(tx_hash)
        except Exception as exc:
            raise BlockchainClientError(
                f"Failed to fetch receipt for {tx_hash}: {exc}"
            ) from exc

        if receipt is None:
            raise BlockchainClientError(
                f"Transaction {tx_hash} not found (may still be pending)"
            )

        return {
            "transactionHash": receipt["transactionHash"].hex(),
            "blockNumber": receipt["blockNumber"],
            "blockHash": receipt["blockHash"].hex(),
            "status": receipt["status"],          # 1 = success, 0 = reverted
            "gasUsed": receipt["gasUsed"],
            "contractAddress": receipt.get("contractAddress"),
            "from": receipt["from"],
            "to": receipt.get("to"),
            "logs": [dict(log) for log in receipt.get("logs", [])],
        }
