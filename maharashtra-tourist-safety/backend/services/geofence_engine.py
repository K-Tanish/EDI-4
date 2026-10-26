"""
GeoFenceEngine service — Task 6.1
Implements: Requirements 4.1, 4.2, 4.4, 4.5, 4.6

Integrates with movement-anomaly pipeline and supports:
  - RESTRICTED zones: Protected tiger reserves, prohibited wilderness (critical alerts)
  - HAZARD zones: High-risk coastal, landslide, and danger zones (high risk alerts)
  - ORDINARY zones: Regulated urban, heritage, and hill-station zones (normal safe travel)

Evaluation distinguishes:
  1. CONFIRMED_VIOLATION: Clear incursion beyond boundary buffer with reliable GPS
  2. BOUNDARY_NOISE: Near-perimeter location (|dist - radius| <= buffer) or border jitter
  3. UNCERTAIN_GPS: Degraded GPS lock (accuracy > 50m) preventing violation confirmation
  4. MISSING_DATA: Missing or invalid coordinate inputs (represented as unknown)
  5. ORDINARY_ZONE: Inside configured standard safe/tourist zones (no violation)
  6. SAFE_OUTSIDE: Outside configured danger zones (not classified as unsafe)

Preserves existing 5-minute cooldown behavior per (touristId, zoneId).
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

try:
    from db.firebase_admin import get_firebase_db
except Exception:
    def get_firebase_db():
        return None

try:
    from db.mongo import get_db
except Exception:
    def get_db():
        return None

try:
    from routers.zones import MAHARASHTRA_ZONES
except Exception:
    MAHARASHTRA_ZONES = [
        {"name": "Mumbai Urban Core",    "type": "URBAN",        "riskLevel": "MEDIUM",     "centerLat": 19.0760, "centerLng": 72.8777, "radiusMeters": 15000.0},
        {"name": "Dharavi",              "type": "URBAN",        "riskLevel": "HIGH",       "centerLat": 19.0390, "centerLng": 72.8530, "radiusMeters": 2000.0},
        {"name": "Konkan Coastal Belt",  "type": "COASTAL",      "riskLevel": "MEDIUM",     "centerLat": 17.0000, "centerLng": 73.2500, "radiusMeters": 50000.0},
        {"name": "Ratnagiri Coastal",    "type": "COASTAL",      "riskLevel": "HIGH",       "centerLat": 16.9902, "centerLng": 73.3120, "radiusMeters": 10000.0},
        {"name": "Mahabaleshwar",        "type": "HILL_STATION", "riskLevel": "LOW",        "centerLat": 17.9237, "centerLng": 73.6586, "radiusMeters": 8000.0},
        {"name": "Lonavala",             "type": "HILL_STATION", "riskLevel": "LOW",        "centerLat": 18.7481, "centerLng": 73.4072, "radiusMeters": 5000.0},
        {"name": "Tadoba Tiger Reserve", "type": "FOREST",       "riskLevel": "RESTRICTED", "centerLat": 20.2280, "centerLng": 79.3950, "radiusMeters": 30000.0},
        {"name": "Melghat Tiger Reserve","type": "FOREST",       "riskLevel": "RESTRICTED", "centerLat": 21.5000, "centerLng": 77.0000, "radiusMeters": 40000.0},
        {"name": "Ajanta Caves",         "type": "HERITAGE",     "riskLevel": "LOW",        "centerLat": 20.5519, "centerLng": 75.7033, "radiusMeters": 3000.0},
        {"name": "Ellora Caves",         "type": "HERITAGE",     "riskLevel": "LOW",        "centerLat": 20.0258, "centerLng": 75.1780, "radiusMeters": 3000.0},
        {"name": "Nagpur Urban",         "type": "URBAN",        "riskLevel": "MEDIUM",     "centerLat": 21.1458, "centerLng": 79.0882, "radiusMeters": 12000.0},
        {"name": "Pune Urban Core",      "type": "URBAN",        "riskLevel": "MEDIUM",     "centerLat": 18.5204, "centerLng": 73.8567, "radiusMeters": 12000.0},
    ]

# In-memory cooldown: (touristId, zoneId) -> last_alert_timestamp_s
_cooldown: Dict[Tuple[str, str], float] = {}
_COOLDOWN_SECONDS = 300  # 5 minutes

# Custom zones override (used for testing or dynamic in-memory configurations)
_custom_zones: Optional[List[Dict[str, Any]]] = None

# GPS Accuracy Thresholds for Geofencing
MAX_UNCERTAIN_GPS_ACCURACY_M = 50.0  # Accuracy > 50m is treated as uncertain fix
DEFAULT_BOUNDARY_BUFFER_M = 20.0     # Minimum boundary uncertainty buffer


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance between two coordinates in metres."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def classify_zone_category(zone: Dict[str, Any]) -> str:
    """
    Classify a zone into RESTRICTED, HAZARD, or ORDINARY.
    """
    risk = str(zone.get("riskLevel", "")).upper()
    zone_type = str(zone.get("type", "")).upper()

    if risk == "RESTRICTED" or zone_type in ("RESTRICTED", "PROHIBITED"):
        return "RESTRICTED"
    if risk in ("HIGH", "HAZARD") or zone_type in ("HAZARD", "DANGER"):
        return "HAZARD"
    return "ORDINARY"


def get_active_zones() -> List[Dict[str, Any]]:
    """
    Retrieve active zones. Prefers custom zones if set, then MongoDB,
    and falls back to standard Maharashtra reference zones.
    """
    global _custom_zones
    if _custom_zones is not None:
        return _custom_zones

    db = get_db()
    if db is not None:
        try:
            zones = list(db["zones"].find({"active": True}))
            if zones:
                return zones
        except Exception:
            pass

    # Fallback to seed zones with generated IDs
    return [
        {**z, "zoneId": z.get("zoneId", f"default-zone-{i}"), "active": True}
        for i, z in enumerate(MAHARASHTRA_ZONES)
    ]


def set_custom_zones(zones: Optional[List[Dict[str, Any]]]) -> None:
    """Set custom active zones for testing or dynamic override."""
    global _custom_zones
    _custom_zones = zones


def reset_geofence_state(tourist_id: Optional[str] = None) -> None:
    """Reset cooldown timestamps and custom zones."""
    global _custom_zones
    if tourist_id:
        for k in list(_cooldown.keys()):
            if k[0] == tourist_id:
                del _cooldown[k]
    else:
        _cooldown.clear()
        _custom_zones = None


def evaluate_geofence(
    tourist_id: str,
    latitude: Optional[float],
    longitude: Optional[float],
    timestamp_ms: int,
    accuracy: float = 0.0,
    history: Optional[List[dict]] = None,
    blockchain_client=None,
    apply_cooldown: bool = True,
    is_sos: bool = False,
) -> Dict[str, Any]:
    """
    Comprehensive geofence evaluation for a tourist position.
    Returns structured evaluation result distinguishing:
      - CONFIRMED_VIOLATION
      - BOUNDARY_NOISE
      - UNCERTAIN_GPS
      - ORDINARY_ZONE
      - SAFE_OUTSIDE
      - MISSING_DATA
    """
    # 1. Check for missing or invalid coordinate inputs
    if latitude is None or longitude is None:
        return {
            "status": "MISSING_DATA",
            "zone": None,
            "zoneCategory": "NONE",
            "alert": None,
            "reason": "Missing or null coordinates",
        }

    try:
        lat = float(latitude)
        lng = float(longitude)
        if math.isnan(lat) or math.isnan(lng) or math.isinf(lat) or math.isinf(lng):
            raise ValueError("NaN or Inf coordinate")
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            raise ValueError("Coordinates out of geographic range")
    except (TypeError, ValueError) as err:
        return {
            "status": "MISSING_DATA",
            "zone": None,
            "zoneCategory": "NONE",
            "alert": None,
            "reason": str(err),
        }

    acc = float(accuracy or 0.0)
    boundary_buffer = max(DEFAULT_BOUNDARY_BUFFER_M, min(acc, MAX_UNCERTAIN_GPS_ACCURACY_M))

    active_zones = get_active_zones()

    # Sort zones by priority: RESTRICTED first, then HAZARD, then ORDINARY
    def zone_priority(z: dict) -> int:
        cat = classify_zone_category(z)
        if cat == "RESTRICTED":
            return 0
        if cat == "HAZARD":
            return 1
        return 2

    sorted_zones = sorted(active_zones, key=zone_priority)

    matched_ordinary_zone = None
    matched_boundary_zone = None
    matched_uncertain_zone = None

    for zone in sorted_zones:
        center_lat = zone.get("centerLat")
        center_lng = zone.get("centerLng")
        radius = float(zone.get("radiusMeters", 0.0))
        if center_lat is None or center_lng is None or radius <= 0:
            continue

        dist = haversine_meters(lat, lng, center_lat, center_lng)
        category = classify_zone_category(zone)

        # ── Case A: ORDINARY ZONE ─────────────────────────────────────────────
        if category == "ORDINARY":
            if dist <= radius:
                matched_ordinary_zone = zone
            continue  # Ordinary zones do not produce violations

        # ── Check for Danger / Restricted Zones (HAZARD or RESTRICTED) ────────
        # 1. Boundary Noise Check:
        # If position is near perimeter (|dist - radius| <= boundary_buffer),
        # measurement is within GPS jitter margin.
        dist_from_border = abs(dist - radius)
        if dist_from_border <= boundary_buffer:
            matched_boundary_zone = (zone, dist, radius, category)
            continue

        # 2. Outside zone beyond boundary buffer -> Safe with respect to this zone
        if dist > radius:
            continue

        # 3. Inside zone (dist < radius - boundary_buffer):
        # Check GPS accuracy certainty. If GPS error circle is too large, fix is uncertain.
        penetration_depth = radius - dist
        if acc > MAX_UNCERTAIN_GPS_ACCURACY_M or (dist + acc > radius):
            matched_uncertain_zone = (zone, dist, radius, category, acc)
            continue

        # 4. Confirmed Violation!
        # Cooldown check: 5-minute suppression per (touristId, zoneId)
        zone_id = str(zone.get("zoneId", zone.get("name", "unknown")))
        key = (tourist_id, zone_id)
        now_s = time.time()
        in_cooldown = False
        if apply_cooldown and not is_sos:
            in_cooldown = (now_s - _cooldown.get(key, 0) < _COOLDOWN_SECONDS)

        rule_name = "RESTRICTED_ZONE_VIOLATION" if category == "RESTRICTED" else "HAZARD_ZONE_VIOLATION"
        risk_level = "RESTRICTED" if category == "RESTRICTED" else "HIGH"

        evidence = {
            "ruleName": rule_name,
            "timestamp": timestamp_ms,
            "measuredValue": round(dist, 2),
            "threshold": round(radius, 2),
            "unit": "metres",
            "details": {
                "zoneId": zone_id,
                "zoneName": zone.get("name", "Unknown Zone"),
                "zoneCategory": category,
                "penetrationDepthM": round(penetration_depth, 2),
                "accuracyM": round(acc, 2),
                "boundaryBufferM": round(boundary_buffer, 2),
                "status": "CONFIRMED_VIOLATION",
                "inCooldown": in_cooldown,
            },
        }

        alert = {
            "alertId": str(uuid.uuid4()),
            "touristId": tourist_id,
            "type": "ZONE_ENTRY",
            "ruleName": rule_name,
            "riskLevel": risk_level,
            "latitude": lat,
            "longitude": lng,
            "timestamp": timestamp_ms,
            "zoneName": zone.get("name", "Unknown Zone"),
            "measuredValue": round(dist, 2),
            "threshold": round(radius, 2),
            "evidence": evidence,
            "acknowledged": False,
            "escalatedAt": None,
            "createdAt": int(now_s * 1000),
        }

        if not in_cooldown:
            _cooldown[key] = now_s

            # Write alert to MongoDB & Firebase
            db = get_db()
            if db is not None:
                try:
                    db["anomaly_alerts"].insert_one({**alert})
                except Exception:
                    pass

            fb = get_firebase_db()
            if fb:
                try:
                    fb.child("Alerts").push(alert)
                except Exception:
                    pass

            # Blockchain log for RESTRICTED zones
            if category == "RESTRICTED" and blockchain_client:
                try:
                    blockchain_client.record_zone_entry(
                        0,
                        zone.get("name", "Restricted Zone"),
                        timestamp_ms // 1000,
                    )
                except Exception:
                    pass

            return {
                "status": "CONFIRMED_VIOLATION",
                "zone": zone,
                "zoneCategory": category,
                "alert": alert,
                "distanceM": round(dist, 2),
                "radiusM": round(radius, 2),
                "boundaryMarginM": round(penetration_depth, 2),
                "accuracyM": round(acc, 2),
            }
        else:
            # Suppressed by cooldown
            return {
                "status": "CONFIRMED_VIOLATION",
                "zone": zone,
                "zoneCategory": category,
                "alert": None,  # suppressed by cooldown
                "distanceM": round(dist, 2),
                "radiusM": round(radius, 2),
                "boundaryMarginM": round(penetration_depth, 2),
                "accuracyM": round(acc, 2),
                "cooldownSuppressed": True,
            }

    # If near boundary of a hazard/restricted zone
    if matched_boundary_zone:
        b_zone, b_dist, b_radius, b_cat = matched_boundary_zone
        return {
            "status": "BOUNDARY_NOISE",
            "zone": b_zone,
            "zoneCategory": b_cat,
            "alert": None,  # Boundary noise does not generate false alarms
            "distanceM": round(b_dist, 2),
            "radiusM": round(b_radius, 2),
            "boundaryMarginM": round(b_radius - b_dist, 2),
            "accuracyM": round(acc, 2),
        }

    # If GPS accuracy is too degraded to confirm incursion
    if matched_uncertain_zone:
        u_zone, u_dist, u_radius, u_cat, u_acc = matched_uncertain_zone
        return {
            "status": "UNCERTAIN_GPS",
            "zone": u_zone,
            "zoneCategory": u_cat,
            "alert": None,  # Uncertain GPS does not generate false alarms
            "distanceM": round(u_dist, 2),
            "radiusM": round(u_radius, 2),
            "boundaryMarginM": round(u_radius - u_dist, 2),
            "accuracyM": round(u_acc, 2),
        }

    # If inside ordinary (safe) zone
    if matched_ordinary_zone:
        return {
            "status": "ORDINARY_ZONE",
            "zone": matched_ordinary_zone,
            "zoneCategory": "ORDINARY",
            "alert": None,
            "distanceM": None,
            "radiusM": float(matched_ordinary_zone.get("radiusMeters", 0.0)),
        }

    # Open area outside all configured zones: Not classified as unsafe
    return {
        "status": "SAFE_OUTSIDE",
        "zone": None,
        "zoneCategory": "NONE",
        "alert": None,
    }


def check_zones(
    tourist_id: str,
    latitude: float,
    longitude: float,
    timestamp_ms: int,
    blockchain_client=None,
    accuracy: float = 0.0,
) -> Optional[dict]:
    """
    Backwards-compatible API for existing callers.
    Evaluates zones and returns the matched zone dict if an alert was fired, else None.
    """
    result = evaluate_geofence(
        tourist_id=tourist_id,
        latitude=latitude,
        longitude=longitude,
        timestamp_ms=timestamp_ms,
        accuracy=accuracy,
        blockchain_client=blockchain_client,
    )
    if result["status"] == "CONFIRMED_VIOLATION" and result.get("alert") is not None:
        return result["zone"]
    return None
