"""
RiskScorer service — Task 5.1
Implements: Requirements 5.1, 5.4
Formula: base_score - incident_penalty - time_penalty, clamped [0, 100]
"""
from __future__ import annotations

_ZONE_BASE: dict[str, int] = {
    "LOW": 90,
    "MEDIUM": 65,
    "HIGH": 35,
    "RESTRICTED": 10,
}


def compute_score(
    zone_risk_level: str,
    incident_density_30d: int,
    current_hour: int,
) -> tuple[int, str]:
    """
    Returns (score, label) where label is SAFE / CAUTION / DANGER.
    """
    base = _ZONE_BASE.get(zone_risk_level.upper(), 65)
    incident_penalty = min(30, incident_density_30d * 3)
    time_penalty = 10 if current_hour >= 22 or current_hour < 5 else 0
    score = max(0, base - incident_penalty - time_penalty)

    if score >= 70:
        label = "SAFE"
    elif score >= 40:
        label = "CAUTION"
    else:
        label = "DANGER"

    return score, label
