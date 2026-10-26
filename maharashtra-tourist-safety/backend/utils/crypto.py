"""Cryptographic utilities for PII protection.

Rules enforced here:
- hash_identity() NEVER returns or stores the raw identity value.
- encrypt_pii / decrypt_pii use AES-256-GCM (authenticated encryption).
- Ciphertext format (base64-encoded): nonce (12 bytes) || tag (16 bytes) || ciphertext
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_NONCE_BYTES = 12  # 96-bit nonce recommended for GCM
_KEY_BYTES = 32    # 256-bit key for AES-256


def hash_identity(raw_value: str) -> str:
    """Return the SHA-256 hex digest of *raw_value*.

    The raw identity document number is consumed locally and is never
    returned, stored, or logged by this function.
    """
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def generate_encryption_key() -> bytes:
    """Return 32 cryptographically random bytes suitable for AES-256."""
    return os.urandom(_KEY_BYTES)


def encrypt_pii(plaintext: str, key: bytes) -> str:
    """AES-256-GCM encrypt *plaintext* with *key*.

    Returns a base64-encoded string containing:
        nonce (12 bytes) || tag (16 bytes) || ciphertext

    The GCM tag is appended by the ``cryptography`` library at the end of
    the returned bytes, so the stored layout is:
        base64( nonce || ciphertext_with_appended_tag )
    """
    if len(key) != _KEY_BYTES:
        raise ValueError(f"Key must be exactly {_KEY_BYTES} bytes for AES-256.")

    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    # AESGCM.encrypt returns ciphertext + 16-byte tag appended
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct_with_tag).decode("ascii")


def decrypt_pii(ciphertext_b64: str, key: bytes) -> str:
    """AES-256-GCM decrypt *ciphertext_b64* with *key*.

    Expects the format produced by :func:`encrypt_pii`.
    Raises ``cryptography.exceptions.InvalidTag`` if authentication fails.
    """
    if len(key) != _KEY_BYTES:
        raise ValueError(f"Key must be exactly {_KEY_BYTES} bytes for AES-256.")

    raw = base64.b64decode(ciphertext_b64)
    nonce = raw[:_NONCE_BYTES]
    ct_with_tag = raw[_NONCE_BYTES:]

    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ct_with_tag, None)
    return plaintext_bytes.decode("utf-8")
