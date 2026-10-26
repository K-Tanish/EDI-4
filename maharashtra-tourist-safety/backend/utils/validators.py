"""Input validators for identity documents."""
from __future__ import annotations

import re


class ValidationError(ValueError):
    """Raised when an identity document fails format validation."""


# Aadhaar: exactly 12 decimal digits
_AADHAAR_RE = re.compile(r"^\d{12}$")

# Passport: alphanumeric, 8–15 characters
_PASSPORT_RE = re.compile(r"^[A-Za-z0-9]{8,15}$")


def validate_aadhaar(value: str) -> bool:
    """Raise ValidationError if *value* is not a valid Aadhaar number."""
    if not _AADHAAR_RE.match(value):
        raise ValidationError("Aadhaar must be exactly 12 digits")
    return True


def validate_passport(value: str) -> bool:
    """Raise ValidationError if *value* is not a valid passport number."""
    if not _PASSPORT_RE.match(value):
        raise ValidationError("Passport must be 8–15 alphanumeric characters")
    return True


def validate_identity(identity_type: str, value: str) -> bool:
    """Dispatch to the correct validator based on *identity_type*.

    Args:
        identity_type: ``"AADHAAR"`` or ``"PASSPORT"`` (case-insensitive).
        value: The raw identity document number to validate.

    Returns:
        True if the value passes the format check for the given type.

    Raises:
        ValueError: If *identity_type* is not recognised.
    """
    normalised = identity_type.upper()
    if normalised == "AADHAAR":
        return validate_aadhaar(value)
    if normalised == "PASSPORT":
        return validate_passport(value)
    raise ValueError(f"Unknown identity type: {identity_type!r}. Expected 'AADHAAR' or 'PASSPORT'.")
