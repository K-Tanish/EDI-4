"""
AnomalyDetector async worker — Task 8.1
Implements: Requirements 7.1–7.7
Runs as a separate asyncio task; consumes from a shared asyncio.Queue.

Movement Detection Rules:
  1. ABNORMAL_SPEED: Speed exceeds threshold (default: 30.0 m/s)
  2. PROLONGED_INACTIVITY: Tourist remains within small radius (< 10 m) for >= 10 minutes
  3. DIRECTION_CHANGE: Acute/erratic heading change (> 120.0 degrees) during movement
  4. ROUTE_DEVIATION: Deviation from reference route (> 500.0 m) when reference route is available
  5. GEOFENCE_ENGINE: RESTRICTED and HAZARD zone violations
  6. GPS_LOSS: Timeout without GPS updates (> 5 minutes)

Alert Refinement Policy:
  - Temporal Persistence: Anomaly candidates must persist across >= PERSISTENCE_MIN_CONSECUTIVE
    observations or span >= PERSISTENCE_WINDOW_MS to confirm. Transient anomalies are filtered.
  - Missing Observations: Missing/invalid observations do NOT reset candidate state to normal.
  - Duplicate Suppression: Alerts for the same rule & tourist are suppressed during
    DUPLICATE_SUPPRESSION_SECONDS (default: 300s / 5 minutes).
  - SOS Bypass: Emergency SOS events bypass ordinary persistence and cooldown filtering,
    immediately executing the emergency-handling path.
"""
from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from config import settings

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

from services.geofence_engine import evaluate_geofence, reset_geofence_state

# ── Configured Thresholds ──────────────────────────────────────────────────────
_STATIONARY_DIST_M: float = getattr(settings, "ANOMALY_STATIONARY_DIST_M", 10.0)
_STATIONARY_WINDOW_MS: int = getattr(settings, "ANOMALY_STATIONARY_WINDOW_MS", 600_000)
_ABNORMAL_SPEED_MS: float = getattr(settings, "ANOMALY_SPEED_MS", 30.0)
_GPS_LOSS_TIMEOUT_MS: int = getattr(settings, "ANOMALY_GPS_LOSS_TIMEOUT_MS", 300_000)
_ROUTE_DEVIATION_M: float = getattr(settings, "ANOMALY_ROUTE_DEVIATION_M", 500.0)
_DIRECTION_CHANGE_DEG: float = getattr(settings, "ANOMALY_DIRECTION_CHANGE_DEG", 120.0)
_MIN_POINTS: int = getattr(settings, "ANOMALY_MIN_POINTS", 3)
_MIN_DISPLACEMENT_FOR_BEARING_M: float = 3.0

# ── Alert Refinement & Temporal Persistence Thresholds ────────────────────────
_PERSISTENCE_MIN_CONSECUTIVE: int = getattr(settings, "PERSISTENCE_MIN_CONSECUTIVE", 2)
_PERSISTENCE_WINDOW_MS: int = getattr(settings, "PERSISTENCE_WINDOW_MS", 15_000)
_DUPLICATE_SUPPRESSION_SECONDS: int = getattr(settings, "DUPLICATE_SUPPRESSION_SECONDS", 300)

# Shared queue — location events are pushed here by the location router
location_queue: asyncio.Queue = asyncio.Queue()

# Per-tourist sliding window of recent location points
_history: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=50))
_last_gps: Dict[str, int] = {}  # touristId -> last timestamp_ms

# Per-tourist reference routes: touristId -> list of (lat, lng)
_reference_routes: Dict[str, List[Tuple[float, float]]] = {}

# Alert Refinement State
# (tourist_id, rule_name) -> {first_seen_ms, last_seen_ms, count, alert}
_candidate_tracker: Dict[Tuple[str, str], dict] = {}
# (tourist_id, rule_name) -> last_alert_timestamp_s
_alert_cooldowns: Dict[Tuple[str, str], float] = {}


# ── Reference Route Management ─────────────────────────────────────────────────
def _normalize_route(route: Any) -> List[Tuple[float, float]]:
    """Normalize route representations into a clean list of (lat, lng) tuples."""
    normalized: List[Tuple[float, float]] = []
    if not isinstance(route, list):
        return normalized

    for wp in route:
        if isinstance(wp, dict):
            lat = wp.get("latitude", wp.get("lat"))
            lng = wp.get("longitude", wp.get("lng"))
        elif isinstance(wp, (list, tuple)) and len(wp) >= 2:
            lat, lng = wp[0], wp[1]
        else:
            continue

        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            if not (math.isnan(lat) or math.isnan(lng) or math.isinf(lat) or math.isinf(lng)):
                if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                    normalized.append((float(lat), float(lng)))

    return normalized


def set_reference_route(tourist_id: str, route: Any) -> None:
    """Set or update the reference route for a tourist."""
    normalized = _normalize_route(route)
    if normalized:
        _reference_routes[tourist_id] = normalized
    elif tourist_id in _reference_routes:
        del _reference_routes[tourist_id]


def get_reference_route(tourist_id: str) -> Optional[List[Tuple[float, float]]]:
    """Get the reference route for a tourist if available, else None."""
    return _reference_routes.get(tourist_id)


def clear_reference_route(tourist_id: str) -> None:
    """Clear reference route for a tourist."""
    _reference_routes.pop(tourist_id, None)


def reset_state(tourist_id: Optional[str] = None) -> None:
    """Reset tracking history, last known GPS, routes, candidates, and cooldowns."""
    if tourist_id:
        _history.pop(tourist_id, None)
        _last_gps.pop(tourist_id, None)
        _reference_routes.pop(tourist_id, None)
        for k in list(_candidate_tracker.keys()):
            if k[0] == tourist_id:
                del _candidate_tracker[k]
        for k in list(_alert_cooldowns.keys()):
            if k[0] == tourist_id:
                del _alert_cooldowns[k]
        reset_geofence_state(tourist_id)
    else:
        _history.clear()
        _last_gps.clear()
        _reference_routes.clear()
        _candidate_tracker.clear()
        _alert_cooldowns.clear()
        reset_geofence_state(None)


def get_candidate_status(tourist_id: str, rule_name: str) -> Optional[dict]:
    """Inspect active candidate persistence tracking state."""
    return _candidate_tracker.get((tourist_id, rule_name))


def get_cooldown_status(tourist_id: str, rule_name: str) -> Dict[str, Any]:
    """Check duplicate-suppression cooldown status."""
    now_s = time.time()
    last_alert = _alert_cooldowns.get((tourist_id, rule_name), 0.0)
    in_cooldown = (now_s - last_alert < _DUPLICATE_SUPPRESSION_SECONDS)
    remaining_s = max(0.0, _DUPLICATE_SUPPRESSION_SECONDS - (now_s - last_alert)) if in_cooldown else 0.0
    return {
        "inCooldown": in_cooldown,
        "remainingSeconds": round(remaining_s, 2),
        "lastAlertTimestampS": last_alert,
    }


# ── Validation ─────────────────────────────────────────────────────────────────
def validate_point(point: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate coordinates and timestamps before feature computation.
    Returns (True, None) if valid, or (False, reason) if invalid.
    """
    if not isinstance(point, dict):
        return False, "Point must be a dictionary"

    ts = point.get("timestamp")
    if ts is None:
        return False, "Missing timestamp"
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return False, "Timestamp must be a number"
    if math.isnan(ts) or math.isinf(ts) or ts <= 0:
        return False, f"Invalid timestamp value: {ts}"

    lat = point.get("latitude")
    if lat is None:
        return False, "Missing latitude"
    if not isinstance(lat, (int, float)) or isinstance(lat, bool):
        return False, "Latitude must be a number"
    if math.isnan(lat) or math.isinf(lat):
        return False, f"Invalid latitude value: {lat}"
    if not (-90.0 <= lat <= 90.0):
        return False, f"Latitude {lat} out of range [-90, 90]"

    lng = point.get("longitude")
    if lng is None:
        return False, "Missing longitude"
    if not isinstance(lng, (int, float)) or isinstance(lng, bool):
        return False, "Longitude must be a number"
    if math.isnan(lng) or math.isinf(lng):
        return False, f"Invalid longitude value: {lng}"
    if not (-180.0 <= lng <= 180.0):
        return False, f"Longitude {lng} out of range [-180, 180]"

    return True, None


# ── Spatial & Heading Helpers ──────────────────────────────────────────────────
def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in metres between two coordinate points."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2.0) ** 2
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute forward azimuth bearing in degrees [0, 360) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def _angle_diff(b1: float, b2: float) -> float:
    """Calculate the absolute angular difference [0, 180] degrees between two bearings."""
    diff = (b2 - b1 + 180.0) % 360.0 - 180.0
    return abs(diff)


def _min_route_distance_meters(lat: float, lng: float, route: List[Tuple[float, float]]) -> Optional[float]:
    """Calculate minimum distance from coordinate to polyline route."""
    if not route:
        return None
    if len(route) == 1:
        return _haversine(lat, lng, route[0][0], route[0][1])

    min_dist = float("inf")
    for i in range(len(route) - 1):
        lat_a, lng_a = route[i]
        lat_b, lng_b = route[i + 1]

        mid_lat = math.radians((lat_a + lat_b) / 2.0)
        cos_mid = math.cos(mid_lat)

        dx = math.radians(lng_b - lng_a) * 6_371_000.0 * cos_mid
        dy = math.radians(lat_b - lat_a) * 6_371_000.0

        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-6:
            dist = _haversine(lat, lng, lat_a, lng_a)
        else:
            px = math.radians(lng - lng_a) * 6_371_000.0 * cos_mid
            py = math.radians(lat - lat_a) * 6_371_000.0
            t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
            closest_lat = lat_a + t * (lat_b - lat_a)
            closest_lng = lng_a + t * (lng_b - lng_a)
            dist = _haversine(lat, lng, closest_lat, closest_lng)

        if dist < min_dist:
            min_dist = dist

    return min_dist


# ── Alerts & SOS Dispatch ──────────────────────────────────────────────────────
def _write_alert(alert: dict):
    """Persist alert to MongoDB and Firebase Realtime Database."""
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


def dispatch_sos(
    tourist_id: str,
    latitude: float = 0.0,
    longitude: float = 0.0,
    timestamp_ms: Optional[int] = None,
    sos_id: Optional[str] = None,
) -> dict:
    """
    Emergency SOS trigger: bypasses ordinary anomaly persistence and cooldown filtering,
    writes to Firebase/Mongo, and registers incident following the emergency-handling path.
    """
    now_ms = timestamp_ms or int(time.time() * 1000)
    event_id = sos_id or str(uuid.uuid4())

    # Write to MongoDB incidents collection
    db = get_db()
    if db is not None:
        try:
            db["incidents"].insert_one({
                "incidentId": event_id,
                "linkedSosId": event_id,
                "touristId": tourist_id,
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": now_ms,
                "status": "OPEN",
                "createdAt": now_ms,
                "resolvedAt": None,
                "officerId": None,
                "blockchainTxHash": None,
            })
        except Exception:
            pass

    # Write to Firebase SOS and Alerts paths
    fb = get_firebase_db()
    if fb:
        try:
            fb.child(f"SOS/{tourist_id}").set({
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": now_ms,
                "status": "ACTIVE",
            })
            fb.child("Alerts").push({
                "touristId": tourist_id,
                "type": "SOS",
                "ruleName": "EMERGENCY_SOS",
                "riskLevel": "HIGH",
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": now_ms,
                "sosId": event_id,
            })
        except Exception:
            pass

    # Structured alert object explicitly bypassing persistence and cooldown
    alert = {
        "alertId": str(uuid.uuid4()),
        "touristId": tourist_id,
        "type": "SOS",
        "ruleName": "EMERGENCY_SOS",
        "riskLevel": "HIGH",
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": now_ms,
        "sosId": event_id,
        "measuredValue": 1.0,
        "threshold": 1.0,
        "evidence": {
            "ruleName": "EMERGENCY_SOS",
            "timestamp": now_ms,
            "measuredValue": 1.0,
            "threshold": 1.0,
            "unit": "emergency_trigger",
            "details": {
                "sosId": event_id,
                "status": "EMERGENCY_DISPATCHED",
                "bypassedPersistence": True,
                "bypassedCooldown": True,
            },
        },
        "acknowledged": False,
        "escalatedAt": None,
        "createdAt": now_ms,
    }
    return alert


def _make_alert(
    tourist_id: str,
    alert_type: str,
    risk_level: str,
    point: dict,
    rule_name: str,
    measured_value: Any,
    threshold: Any,
    unit: str = "",
    details: Optional[dict] = None,
) -> dict:
    """Generate an alert with structured anomaly evidence."""
    now_ms = int(time.time() * 1000)
    pt_ts = point.get("timestamp", now_ms)

    evidence = {
        "ruleName": rule_name,
        "timestamp": pt_ts,
        "measuredValue": measured_value,
        "threshold": threshold,
        "unit": unit,
        "details": details or {},
    }

    return {
        "alertId": str(uuid.uuid4()),
        "touristId": tourist_id,
        "type": alert_type,
        "ruleName": rule_name,
        "riskLevel": risk_level,
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "timestamp": pt_ts,
        "measuredValue": measured_value,
        "threshold": threshold,
        "evidence": evidence,
        "acknowledged": False,
        "escalatedAt": None,
        "createdAt": now_ms,
    }


# ── Movement Rule Evaluation & Refinement Pipeline ─────────────────────────────
def _evaluate_raw_rules(tourist_id: str, point: dict) -> List[dict]:
    """
    Evaluate feature-level detection rules on a valid point without refinement.
    Returns list of unrefined candidate alerts.
    """
    history = _history[tourist_id]
    pts = list(history)
    latest = pts[-1]
    now_ms = latest["timestamp"]
    candidates: List[dict] = []

    # Rule 1: ABNORMAL SPEED
    if len(pts) >= 2:
        prev = pts[-2]
        dt_s = (latest["timestamp"] - prev["timestamp"]) / 1000.0
        if dt_s > 0:
            dist_m = _haversine(prev["latitude"], prev["longitude"], latest["latitude"], latest["longitude"])
            speed_mps = dist_m / dt_s
            if speed_mps > _ABNORMAL_SPEED_MS:
                candidates.append(_make_alert(
                    tourist_id=tourist_id,
                    alert_type="ABNORMAL_SPEED",
                    risk_level="MEDIUM",
                    point=latest,
                    rule_name="ABNORMAL_SPEED",
                    measured_value=round(speed_mps, 2),
                    threshold=_ABNORMAL_SPEED_MS,
                    unit="m/s",
                    details={
                        "distanceMeters": round(dist_m, 2),
                        "timeDeltaSeconds": round(dt_s, 2),
                    },
                ))

    # Rule 2: PROLONGED INACTIVITY (STATIONARY)
    window = [p for p in pts if now_ms - p["timestamp"] <= _STATIONARY_WINDOW_MS]
    if len(window) >= _MIN_POINTS:
        window_duration_ms = window[-1]["timestamp"] - window[0]["timestamp"]
        if window_duration_ms >= _STATIONARY_WINDOW_MS:
            max_disp = max(
                _haversine(p["latitude"], p["longitude"], latest["latitude"], latest["longitude"])
                for p in window
            )
            if max_disp < _STATIONARY_DIST_M:
                candidates.append(_make_alert(
                    tourist_id=tourist_id,
                    alert_type="STATIONARY",
                    risk_level="LOW",
                    point=latest,
                    rule_name="PROLONGED_INACTIVITY",
                    measured_value=round(max_disp, 2),
                    threshold=_STATIONARY_DIST_M,
                    unit="metres",
                    details={
                        "stationaryDurationMs": window_duration_ms,
                        "stationaryDurationThresholdMs": _STATIONARY_WINDOW_MS,
                        "pointsInWindow": len(window),
                    },
                ))

    # Rule 3: DIRECTION CHANGES
    if len(pts) >= 3:
        p_prev2 = pts[-3]
        p_prev1 = pts[-2]
        d1 = _haversine(p_prev2["latitude"], p_prev2["longitude"], p_prev1["latitude"], p_prev1["longitude"])
        d2 = _haversine(p_prev1["latitude"], p_prev1["longitude"], latest["latitude"], latest["longitude"])

        if d1 >= _MIN_DISPLACEMENT_FOR_BEARING_M and d2 >= _MIN_DISPLACEMENT_FOR_BEARING_M:
            b1 = _bearing(p_prev2["latitude"], p_prev2["longitude"], p_prev1["latitude"], p_prev1["longitude"])
            b2 = _bearing(p_prev1["latitude"], p_prev1["longitude"], latest["latitude"], latest["longitude"])
            delta_angle = _angle_diff(b1, b2)

            if delta_angle > _DIRECTION_CHANGE_DEG:
                candidates.append(_make_alert(
                    tourist_id=tourist_id,
                    alert_type="DIRECTION_CHANGE",
                    risk_level="MEDIUM",
                    point=latest,
                    rule_name="DIRECTION_CHANGE",
                    measured_value=round(delta_angle, 2),
                    threshold=_DIRECTION_CHANGE_DEG,
                    unit="degrees",
                    details={
                        "previousBearingDeg": round(b1, 2),
                        "currentBearingDeg": round(b2, 2),
                        "displacement1M": round(d1, 2),
                        "displacement2M": round(d2, 2),
                    },
                ))

    # Rule 4: ROUTE DEVIATION
    ref_route = get_reference_route(tourist_id)
    if ref_route:
        route_dist_m = _min_route_distance_meters(latest["latitude"], latest["longitude"], ref_route)
        if route_dist_m is not None and route_dist_m > _ROUTE_DEVIATION_M:
            candidates.append(_make_alert(
                tourist_id=tourist_id,
                alert_type="ROUTE_DEVIATION",
                risk_level="HIGH",
                point=latest,
                rule_name="ROUTE_DEVIATION",
                measured_value=round(route_dist_m, 2),
                threshold=_ROUTE_DEVIATION_M,
                unit="metres",
                details={"referenceRouteWaypoints": len(ref_route)},
            ))

    # Rule 5: GEOFENCE ZONE EVALUATION
    acc = float(point.get("accuracy", 0.0) or 0.0)
    geofence_res = evaluate_geofence(
        tourist_id=tourist_id,
        latitude=latest["latitude"],
        longitude=latest["longitude"],
        timestamp_ms=latest["timestamp"],
        accuracy=acc,
        history=pts,
        apply_cooldown=False,
    )
    if geofence_res.get("alert"):
        candidates.append(geofence_res["alert"])

    return candidates


def _analyse_all(tourist_id: str, point: dict) -> List[dict]:
    """
    Main movement-anomaly pipeline with explicit temporal persistence,
    missing-observation freezing, duplicate suppression, and SOS emergency bypass.
    """
    # ── Path 1: Emergency SOS Bypass ──────────────────────────────────────────
    # SOS events MUST bypass ordinary persistence and cooldown filtering
    if point.get("type") == "SOS" or point.get("isSos") or point.get("sosId"):
        sos_alert = dispatch_sos(
            tourist_id=tourist_id,
            latitude=point.get("latitude", 0.0),
            longitude=point.get("longitude", 0.0),
            timestamp_ms=point.get("timestamp"),
            sos_id=point.get("sosId"),
        )
        return [sos_alert]

    # ── Path 2: Coordinate & Timestamp Validation ─────────────────────────────
    is_valid, reason = validate_point(point)
    if not is_valid:
        # Crucial: Missing observations do NOT automatically count as normal movement.
        # Candidate persistence tracker state is preserved unchanged.
        return []

    # Optional dynamic route update from point payload
    if "referenceRoute" in point and point["referenceRoute"]:
        set_reference_route(tourist_id, point["referenceRoute"])
    elif "route" in point and point["route"]:
        set_reference_route(tourist_id, point["route"])

    history = _history[tourist_id]
    history.append(point)
    _last_gps[tourist_id] = point["timestamp"]

    # ── Path 3: Evaluate Raw Anomaly Candidates ───────────────────────────────
    raw_candidates = _evaluate_raw_rules(tourist_id, point)
    triggered_rules = set()

    confirmed_alerts: List[dict] = []
    pt_ts = point["timestamp"]
    now_s = time.time()

    # ── Path 4: Apply Temporal Persistence & Duplicate Suppression ────────────
    for raw_alert in raw_candidates:
        rule_name = raw_alert.get("ruleName") or raw_alert.get("type")
        zone_id = raw_alert.get("evidence", {}).get("details", {}).get("zoneId")
        rule_key = f"{rule_name}_{zone_id}" if zone_id else rule_name
        triggered_rules.add(rule_key)
        key = (tourist_id, rule_key)

        # 1. Update candidate persistence tracking
        if key not in _candidate_tracker:
            _candidate_tracker[key] = {
                "first_seen_ms": pt_ts,
                "last_seen_ms": pt_ts,
                "count": 1,
                "alert": raw_alert,
            }
        else:
            _candidate_tracker[key]["count"] += 1
            _candidate_tracker[key]["last_seen_ms"] = pt_ts
            _candidate_tracker[key]["alert"] = raw_alert

        candidate = _candidate_tracker[key]
        count = candidate["count"]
        duration_ms = pt_ts - candidate["first_seen_ms"]

        # Inactivity/Stationary already validates a 10-minute window; other rules
        # require configured consecutive detections or temporal window span.
        is_persistent = (
            rule_name in ("PROLONGED_INACTIVITY", "STATIONARY")
            or count >= _PERSISTENCE_MIN_CONSECUTIVE
            or duration_ms >= _PERSISTENCE_WINDOW_MS
        )

        if not is_persistent:
            # Transient anomaly pending confirmation — do not emit alert yet
            continue

        # 2. Duplicate Suppression Cooldown Check
        last_alert_time = _alert_cooldowns.get(key, 0.0)
        if now_s - last_alert_time < _DUPLICATE_SUPPRESSION_SECONDS:
            # Duplicate alert suppressed during cooldown window
            continue

        # 3. Confirmed Persistent Alert — emit and update cooldown timestamp
        _alert_cooldowns[key] = now_s

        if "evidence" in raw_alert:
            raw_alert["evidence"]["refinement"] = {
                "status": "CONFIRMED_PERSISTENT",
                "consecutiveDetections": count,
                "persistenceDurationMs": duration_ms,
                "bypassedCooldown": False,
                "duplicateSuppressed": False,
                "cooldownWindowSeconds": _DUPLICATE_SUPPRESSION_SECONDS,
            }

        confirmed_alerts.append(raw_alert)

    # ── Path 5: Reset Candidate State for Rules with Verified Normal Movement ──
    for key in list(_candidate_tracker.keys()):
        if key[0] == tourist_id and key[1] not in triggered_rules:
            # Verified normal movement on a valid observation resets the candidate tracker
            del _candidate_tracker[key]

    return confirmed_alerts


def _analyse(tourist_id: str, point: dict) -> Optional[dict]:
    """Preserve existing interface: returns the primary refined alert if any, else None."""
    alerts = _analyse_all(tourist_id, point)
    return alerts[0] if alerts else None


# ── Async Worker Loop ─────────────────────────────────────────────────────────
async def run_worker():
    """Main worker loop — consume from location_queue indefinitely."""
    while True:
        try:
            event = await asyncio.wait_for(location_queue.get(), timeout=5.0)
            tourist_id = event.get("touristId")
            if not tourist_id:
                continue

            alerts = _analyse_all(tourist_id, event)
            for alert in alerts:
                _write_alert(alert)

        except asyncio.TimeoutError:
            # Check GPS loss for all tracked tourists
            now_ms = int(time.time() * 1000)
            for tid, last_ts in list(_last_gps.items()):
                elapsed_ms = now_ms - last_ts
                if elapsed_ms > _GPS_LOSS_TIMEOUT_MS:
                    alert = _make_alert(
                        tourist_id=tid,
                        alert_type="GPS_LOSS",
                        risk_level="HIGH",
                        point={"latitude": 0.0, "longitude": 0.0, "timestamp": now_ms},
                        rule_name="GPS_LOSS",
                        measured_value=elapsed_ms,
                        threshold=_GPS_LOSS_TIMEOUT_MS,
                        unit="ms",
                        details={
                            "lastObservedTimestamp": last_ts,
                            "elapsedSinceLastGpsMs": elapsed_ms,
                        },
                    )
                    _write_alert(alert)
                    del _last_gps[tid]
        except Exception:
            pass
