"""
Lightweight Pipeline & Baseline Evaluator
Maharashtra Tourist Safety Project

Compares four anomaly detection configurations on the same labelled trajectory dataset:
  (A) Movement rules only (Kinematics: Speed, Inactivity, Direction, Route Deviation)
  (B) Movement rules + Geospatial context (Kinematics + Geofence hazard/restricted zones)
  (C) Full pipeline including alert refinement (Temporal persistence + Duplicate suppression + SOS bypass)
  (D) Isolation Forest baseline (Unsupervised ML on documented movement features)

Calculates:
  - Precision, Recall, F1-Score
  - False Positive Rate (FPR)
  - Total Alerts & Alerts per Trajectory-Hour
  - Event Detection Delay (seconds from event onset to first alert)

Evaluation Unit:
  1. Point-Level: Every observation evaluated against point ground truth.
  2. Event-Level: Evaluates distinct ground-truth anomaly events. Multiple alerts
     during the same active event window are consolidated to avoid counting
     repeated alerts as separate successful detections.

Outputs a structured CSV results table and comprehensive JSON comparison.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Import Project Detectors ───────────────────────────────────────────────────
try:
    from workers.anomaly_detector import (
        _evaluate_raw_rules,
        _analyse_all,
        reset_state,
        set_reference_route,
        validate_point,
    )
except ImportError:
    # If running from a different root, ensure backend is in sys.path
    backend_root = str(Path(__file__).parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from workers.anomaly_detector import (
        _evaluate_raw_rules,
        _analyse_all,
        reset_state,
        set_reference_route,
        validate_point,
    )

from services.geofence_engine import reset_geofence_state
from utils.isolation_forest_baseline import IsolationForestBaseline, SKLEARN_AVAILABLE


# ── Metric Calculation Helpers ─────────────────────────────────────────────────
def safe_div(numerator: float, denominator: float) -> Optional[float]:
    """Safe division returning None (reported as N/A) when denominator is zero."""
    if denominator == 0 or math.isnan(denominator):
        return None
    return round(numerator / denominator, 4)


def format_metric(val: Optional[float], as_percent: bool = False) -> str:
    """Format numeric values or report undefined metrics honestly as N/A."""
    if val is None:
        return "N/A"
    if as_percent:
        return f"{val * 100.0:.2f}%"
    return f"{val:.4f}"


def is_alert_compatible_with_event(alert: dict, event_type: str) -> bool:
    """
    Verify that an alert's rule or type is semantically compatible with the ground-truth anomaly type.
    An unrelated alert (e.g. speed alert during inactivity, or zone violation during speed) must not count as detection.
    Unsupervised ML baseline (ISOLATION_FOREST) predicts generic anomaly scores on kinematic features,
    so it matches kinematic movement anomalies (speed, inactivity, boundary noise, zone entry).
    """
    rule_name = str(alert.get("ruleName", "")).upper()
    alert_type = str(alert.get("type", "")).upper()

    if rule_name == "ISOLATION_FOREST" or alert_type == "ML_ANOMALY":
        return event_type in (
            "ABNORMAL_SPEED",
            "PROLONGED_INACTIVITY",
            "RESTRICTED_ZONE_ENTRY",
            "GPS_BOUNDARY_NOISE",
            "SOS_EVENT",
        )

    if event_type == "PROLONGED_INACTIVITY":
        return (
            rule_name in ("PROLONGED_INACTIVITY", "STATIONARY")
            or alert_type in ("STATIONARY", "PROLONGED_INACTIVITY")
        )

    if event_type == "ABNORMAL_SPEED":
        return (
            rule_name in ("ABNORMAL_SPEED", "SPEED")
            or alert_type in ("ABNORMAL_SPEED", "SPEED")
        )

    if event_type == "RESTRICTED_ZONE_ENTRY":
        return (
            "RESTRICTED" in rule_name
            or rule_name in ("RESTRICTED_ZONE_VIOLATION", "ZONE_ENTRY", "ZONE_VIOLATION")
            or alert_type in ("ZONE_ENTRY", "ZONE_VIOLATION")
        )

    if event_type == "GPS_BOUNDARY_NOISE":
        return (
            rule_name in ("HAZARD_ZONE_VIOLATION", "RESTRICTED_ZONE_VIOLATION", "ZONE_ENTRY", "ZONE_VIOLATION")
            or alert_type in ("ZONE_ENTRY", "ZONE_VIOLATION")
        )

    if event_type == "SOS_EVENT":
        return (
            rule_name in ("EMERGENCY_SOS", "SOS")
            or alert_type == "SOS"
        )

    if event_type == "MISSING_GPS_OBSERVATION":
        return (
            rule_name in ("GPS_LOSS", "MISSING_GPS")
            or alert_type in ("GPS_LOSS", "GPS_DROPOUT")
        )

    return False


class PipelineEvaluator:
    """
    Evaluates trajectory anomaly detection configurations against ground-truth labels.
    """

    def __init__(
        self,
        trajectories: List[Dict[str, Any]],
        ground_truth: Dict[str, Any],
    ):
        self.trajectories = trajectories
        self.ground_truth = ground_truth

        # Build point-level ground truth map: (touristId, timestamp) -> ground_truth_dict
        self.point_gt_map: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for pt in ground_truth.get("pointLabels", []):
            self.point_gt_map[(pt["touristId"], pt["timestamp"])] = pt

        # Extract ground-truth scenario events for event-level evaluation
        self.events: List[Dict[str, Any]] = ground_truth.get("scenarioEventSummaries", [])

        # Calculate total trajectory operating hours across all tourists
        tourist_times: Dict[str, List[int]] = defaultdict(list)
        for pt in self.trajectories:
            tourist_times[pt["touristId"]].append(pt["timestamp"])

        total_duration_ms = 0
        for tid, times in tourist_times.items():
            if len(times) >= 2:
                total_duration_ms += (max(times) - min(times))
        self.total_trajectory_hours = max(0.001, total_duration_ms / (3600.0 * 1000.0))

    # ── Runner: Configuration A (Movement Rules Only) ──────────────────────────
    def run_config_a(self) -> List[Dict[str, Any]]:
        """
        Configuration A: Kinematic movement rules only (Speed, Inactivity, Direction, Route).
        Excludes geofence hazard/restricted checks and alert refinement.
        """
        reset_state()
        results: List[Dict[str, Any]] = []

        # Group by tourist and process in chronological order
        tourist_pts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for pt in self.trajectories:
            tourist_pts[pt["touristId"]].append(pt)

        for tid, pts in tourist_pts.items():
            reset_state(tid)
            sorted_pts = sorted(pts, key=lambda p: p["timestamp"])
            for pt in sorted_pts:
                is_valid, _ = validate_point(pt)
                if not is_valid:
                    results.append({"touristId": tid, "timestamp": pt.get("timestamp", 0), "alert": None})
                    continue

                raw_candidates = _evaluate_raw_rules(tid, pt)
                # Filter out geofence zone violation rules
                movement_alerts = [
                    c for c in raw_candidates
                    if c.get("ruleName") not in ("RESTRICTED_ZONE_VIOLATION", "HAZARD_ZONE_VIOLATION")
                    and c.get("type") not in ("ZONE_ENTRY", "ZONE_VIOLATION")
                ]
                primary_alert = movement_alerts[0] if movement_alerts else None
                results.append({"touristId": tid, "timestamp": pt["timestamp"], "alert": primary_alert})

        return results

    # ── Runner: Configuration B (Movement + Geospatial Context) ────────────────
    def run_config_b(self) -> List[Dict[str, Any]]:
        """
        Configuration B: Movement rules + Geofence hazard/restricted zones.
        Raw detections before temporal persistence and duplicate suppression.
        """
        reset_state()
        results: List[Dict[str, Any]] = []

        tourist_pts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for pt in self.trajectories:
            tourist_pts[pt["touristId"]].append(pt)

        for tid, pts in tourist_pts.items():
            reset_state(tid)
            sorted_pts = sorted(pts, key=lambda p: p["timestamp"])
            for pt in sorted_pts:
                is_valid, _ = validate_point(pt)
                if not is_valid:
                    results.append({"touristId": tid, "timestamp": pt.get("timestamp", 0), "alert": None})
                    continue

                raw_candidates = _evaluate_raw_rules(tid, pt)
                primary_alert = raw_candidates[0] if raw_candidates else None
                results.append({"touristId": tid, "timestamp": pt["timestamp"], "alert": primary_alert})

        return results

    # ── Runner: Configuration C (Full Pipeline Refined) ────────────────────────
    def run_config_c(self) -> List[Dict[str, Any]]:
        """
        Configuration C: Full production pipeline including temporal persistence,
        duplicate suppression cooldown, missing observation freezing, and SOS bypass.
        """
        reset_state()
        results: List[Dict[str, Any]] = []

        tourist_pts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for pt in self.trajectories:
            tourist_pts[pt["touristId"]].append(pt)

        for tid, pts in tourist_pts.items():
            reset_state(tid)
            sorted_pts = sorted(pts, key=lambda p: p["timestamp"])
            for pt in sorted_pts:
                refined_alerts = _analyse_all(tid, pt)
                primary_alert = refined_alerts[0] if refined_alerts else None
                results.append({
                    "touristId": tid,
                    "timestamp": pt.get("timestamp", 0),
                    "alert": primary_alert,
                })

        return results

    # ── Runner: Configuration D (Isolation Forest) ─────────────────────────────
    def run_config_d(self) -> Optional[List[Dict[str, Any]]]:
        """
        Configuration D: Isolation Forest baseline using documented movement features.
        """
        if not SKLEARN_AVAILABLE:
            return None

        baseline = IsolationForestBaseline(contamination=0.20, n_estimators=100, random_state=42)
        X, metadata = baseline.extract_features(self.trajectories)
        predictions = baseline.fit_predict(X, metadata)

        results = []
        for pred in predictions:
            alert_obj = {
                "ruleName": "ISOLATION_FOREST",
                "type": "ML_ANOMALY",
                "riskLevel": "MEDIUM",
                "measuredValue": pred["rawAnomalyScore"],
                "threshold": 0.0,
            } if pred["isAnomaly"] else None

            results.append({
                "touristId": pred["touristId"],
                "timestamp": pred["timestamp"],
                "alert": alert_obj,
            })
        return results

    # ── Evaluation Engine (Point-Level & Event-Level) ──────────────────────────
    def evaluate_configuration(
        self,
        config_name: str,
        predictions: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Compute point-level and event-level metrics for a configuration run.
        """
        if predictions is None:
            return {
                "configName": config_name,
                "status": "UNAVAILABLE",
                "reason": "Required dependency (scikit-learn/numpy) not installed",
            }

        # ── 1. Point-Level Evaluation ─────────────────────────────────────────
        tp_pts = 0
        fp_pts = 0
        fn_pts = 0
        tn_pts = 0
        total_alerts = 0

        # Map predictions by (touristId, timestamp)
        pred_map: Dict[Tuple[str, int], bool] = {}
        alert_map: Dict[Tuple[str, int], dict] = {}

        for p in predictions:
            key = (p["touristId"], p["timestamp"])
            is_pred_anomaly = (p.get("alert") is not None)
            pred_map[key] = is_pred_anomaly
            if is_pred_anomaly:
                total_alerts += 1
                alert_map[key] = p["alert"]

            gt = self.point_gt_map.get(key)
            if gt is None:
                continue

            true_anomaly = bool(gt.get("isAnomaly", False))
            if is_pred_anomaly and true_anomaly:
                tp_pts += 1
            elif is_pred_anomaly and not true_anomaly:
                fp_pts += 1
            elif not is_pred_anomaly and true_anomaly:
                fn_pts += 1
            else:
                tn_pts += 1

        precision_pt = safe_div(tp_pts, tp_pts + fp_pts)
        recall_pt = safe_div(tp_pts, tp_pts + fn_pts)
        f1_pt = None
        if precision_pt is not None and recall_pt is not None and (precision_pt + recall_pt) > 0:
            f1_pt = round(2.0 * precision_pt * recall_pt / (precision_pt + recall_pt), 4)
        fpr_pt = safe_div(fp_pts, fp_pts + tn_pts)
        alerts_per_hr = round(total_alerts / self.total_trajectory_hours, 2)

        # ── 2. Event-Level Evaluation & Detection Delay ───────────────────────
        # Definition & Matching Rule:
        # Each ground-truth scenario event E in self.events represents 1 distinct incident unit.
        # Event Window: [E.start_ts, E.end_ts]
        # An event is DETECTED (TP_event) if >= 1 alert is generated for that touristId
        # within [E.start_ts, E.end_ts].
        # Repeated alerts during the event window do NOT count as multiple detections (consolidated to 1 TP).
        # An event is MISSED (FN_event) if no alert is generated within its active window.
        #
        # False Positive Events (FP_event):
        # Alerts generated outside all ground-truth event windows for that tourist represent
        # ungrounded false alarms. Consecutive/repeated ungrounded alerts within a clustering
        # window (300s / 5 min cooldown window) are consolidated into 1 FP event episode.

        event_windows: List[Dict[str, Any]] = []
        for evt in self.events:
            tid = evt["touristId"]
            evt_type = evt.get("anomalyType", "UNKNOWN")
            evt_id = evt.get("eventId", f"event_{tid}")

            start_ts = None
            end_ts = None

            if evt_type == "PROLONGED_INACTIVITY":
                start_ts = evt.get("thresholdExceededTime") or evt.get("stationaryStartTime")
                start_stat = evt.get("stationaryStartTime", start_ts)
                duration = evt.get("totalDurationMs", 750000)
                end_ts = start_stat + duration
            elif evt_type == "ABNORMAL_SPEED":
                pts_meta = evt.get("anomalyPoints", [])
                if pts_meta:
                    start_ts = pts_meta[0]["timestamp"]
                    end_ts = pts_meta[-1]["timestamp"] + 15000  # 1-step tolerance for persistence window
            elif evt_type == "RESTRICTED_ZONE_ENTRY":
                start_ts = evt.get("crossingTimestamp")
                tourist_timestamps = [p["timestamp"] for p in self.trajectories if p["touristId"] == tid]
                end_ts = max(tourist_timestamps) if tourist_timestamps else start_ts
            elif evt_type == "SOS_EVENT":
                start_ts = evt.get("triggerTimestamp")
                tourist_timestamps = [p["timestamp"] for p in self.trajectories if p["touristId"] == tid]
                end_ts = max(tourist_timestamps) if tourist_timestamps else start_ts
            elif evt_type == "MISSING_GPS_OBSERVATION":
                start_ts = evt.get("gapStartTimestamp", 0) + (evt.get("timeoutThresholdSeconds", 300) * 1000)
                end_ts = evt.get("gapEndTimestamp", start_ts)
            elif evt_type == "GPS_BOUNDARY_NOISE":
                tourist_timestamps = [p["timestamp"] for p in self.trajectories if p["touristId"] == tid]
                start_ts = min(tourist_timestamps) if tourist_timestamps else 0
                end_ts = max(tourist_timestamps) if tourist_timestamps else 0

            if start_ts is not None and end_ts is not None:
                event_windows.append({
                    "eventId": evt_id,
                    "touristId": tid,
                    "anomalyType": evt_type,
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "detected": False,
                    "firstAlertTs": None,
                    "alertCount": 0,
                })

        # Collect all alerts generated by this configuration
        generated_alerts = []
        for p in predictions:
            if p.get("alert") is not None:
                generated_alerts.append((p["touristId"], p["timestamp"], p["alert"]))

        # Sort alerts chronologically
        generated_alerts.sort(key=lambda a: a[1])

        # Match alerts to event windows
        ungrounded_alerts: List[Tuple[str, int, dict]] = []

        for tid, ts, alert in generated_alerts:
            matched_event = False
            for ew in event_windows:
                if (
                    ew["touristId"] == tid
                    and (ew["startTs"] <= ts <= ew["endTs"])
                    and is_alert_compatible_with_event(alert, ew["anomalyType"])
                ):
                    matched_event = True
                    ew["alertCount"] += 1
                    if not ew["detected"]:
                        ew["detected"] = True
                        ew["firstAlertTs"] = ts
                    # Consolidated: repeated alerts during this event window do not count as separate detections
                    break
            if not matched_event:
                ungrounded_alerts.append((tid, ts, alert))

        # True Positives & Missed Events
        tp_events = sum(1 for ew in event_windows if ew["detected"])
        fn_events = sum(1 for ew in event_windows if not ew["detected"])

        # Detection delays
        detection_delays_sec = [
            max(0.0, (ew["firstAlertTs"] - ew["startTs"]) / 1000.0)
            for ew in event_windows
            if ew["detected"] and ew["firstAlertTs"] is not None
        ]
        avg_detection_delay_s = (
            round(sum(detection_delays_sec) / len(detection_delays_sec), 2)
            if detection_delays_sec else None
        )

        # Cluster ungrounded alerts into False Positive Event episodes
        # Ungrounded alerts for the same tourist within 300s (cooldown window) count as 1 FP event
        fp_event_episodes = 0
        tourist_ungrounded: Dict[str, List[int]] = defaultdict(list)
        for tid, ts, _ in ungrounded_alerts:
            tourist_ungrounded[tid].append(ts)

        for tid, timestamps in tourist_ungrounded.items():
            sorted_ts = sorted(timestamps)
            last_cluster_ts = None
            for ts in sorted_ts:
                if last_cluster_ts is None or (ts - last_cluster_ts) > 300_000:
                    fp_event_episodes += 1
                    last_cluster_ts = ts
                else:
                    last_cluster_ts = ts

        event_precision = safe_div(tp_events, tp_events + fp_event_episodes)
        event_recall = safe_div(tp_events, tp_events + fn_events)
        event_f1 = None
        if event_precision is not None and event_recall is not None and (event_precision + event_recall) > 0:
            event_f1 = round(2.0 * event_precision * event_recall / (event_precision + event_recall), 4)

        return {
            "configName": config_name,
            "status": "COMPLETED",
            "pointMetrics": {
                "precision": precision_pt,
                "recall": recall_pt,
                "f1Score": f1_pt,
                "falsePositiveRate": fpr_pt,
                "truePositives": tp_pts,
                "falsePositives": fp_pts,
                "falseNegatives": fn_pts,
                "trueNegatives": tn_pts,
            },
            "operationalMetrics": {
                "totalAlerts": total_alerts,
                "totalTrajectoryHours": round(self.total_trajectory_hours, 2),
                "alertsPerHour": alerts_per_hr,
            },
            "eventMetrics": {
                "totalEvents": len(event_windows),
                "detectedEvents": tp_events,
                "missedEvents": fn_events,
                "falsePositiveEvents": fp_event_episodes,
                "eventPrecision": event_precision,
                "eventRecall": event_recall,
                "eventF1Score": event_f1,
                "avgDetectionDelaySec": avg_detection_delay_s,
                "matchingRule": "An event is detected (TP) if >= 1 compatible alert (matching tourist ID and anomaly type) is generated within [eventOnset, eventEnd]. Repeated alerts within an event window are consolidated. Alerts outside all compatible event windows are clustered into false positive episodes (300s window).",
                "perEventBreakdown": [
                    {
                        "eventId": ew["eventId"],
                        "touristId": ew["touristId"],
                        "anomalyType": ew["anomalyType"],
                        "detected": ew["detected"],
                        "firstAlertTimestamp": ew["firstAlertTs"],
                        "totalAlertsFired": ew["alertCount"],
                        "detectionDelaySec": (
                            round((ew["firstAlertTs"] - ew["startTs"]) / 1000.0, 2)
                            if ew["detected"] and ew["firstAlertTs"] is not None else None
                        ),
                    }
                    for ew in event_windows
                ],
            },
        }

    def run_all(self) -> Dict[str, Any]:
        """Execute evaluation across all four configurations."""
        res_a = self.evaluate_configuration("A: Movement Rules Only", self.run_config_a())
        res_b = self.evaluate_configuration("B: Movement + Geospatial", self.run_config_b())
        res_c = self.evaluate_configuration("C: Full Pipeline (Refined)", self.run_config_c())
        res_d = self.evaluate_configuration("D: Isolation Forest", self.run_config_d())

        return {
            "evaluatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "totalTrajectoryPoints": len(self.trajectories),
            "totalLabelledPoints": len(self.point_gt_map),
            "totalGroundTruthEvents": len(self.events),
            "totalTrajectoryHours": round(self.total_trajectory_hours, 3),
            "configurations": {
                "configA": res_a,
                "configB": res_b,
                "configC": res_c,
                "configD": res_d,
            },
        }


# ── Report Generation Helpers ──────────────────────────────────────────────────
def save_csv_report(eval_results: Dict[str, Any], output_path: str | Path) -> None:
    """Save formatted comparative metrics table into CSV for both Point-level and Event-level units."""
    rows = []
    headers = [
        "Configuration",
        "EvaluationUnit",
        "Precision",
        "Recall",
        "F1Score",
        "FalsePositiveRate",
        "TotalAlerts",
        "AlertsPerTrajectoryHour",
        "AvgDetectionDelaySec",
        "TruePositives",
        "FalsePositives",
        "FalseNegatives",
        "TrueNegatives",
    ]

    for key, cfg in eval_results["configurations"].items():
        name = cfg.get("configName", key)
        if cfg.get("status") == "UNAVAILABLE":
            for unit in ("Point-level", "Event-level"):
                rows.append({
                    "Configuration": name,
                    "EvaluationUnit": unit,
                    "Precision": "N/A (sklearn missing)",
                    "Recall": "N/A",
                    "F1Score": "N/A",
                    "FalsePositiveRate": "N/A",
                    "TotalAlerts": "N/A",
                    "AlertsPerTrajectoryHour": "N/A",
                    "AvgDetectionDelaySec": "N/A",
                    "TruePositives": "N/A",
                    "FalsePositives": "N/A",
                    "FalseNegatives": "N/A",
                    "TrueNegatives": "N/A",
                })
            continue

        pm = cfg["pointMetrics"]
        om = cfg["operationalMetrics"]
        em = cfg["eventMetrics"]

        # Point-level row
        rows.append({
            "Configuration": name,
            "EvaluationUnit": "Point-level",
            "Precision": format_metric(pm["precision"]),
            "Recall": format_metric(pm["recall"]),
            "F1Score": format_metric(pm["f1Score"]),
            "FalsePositiveRate": format_metric(pm["falsePositiveRate"]),
            "TotalAlerts": om["totalAlerts"],
            "AlertsPerTrajectoryHour": om["alertsPerHour"],
            "AvgDetectionDelaySec": format_metric(em["avgDetectionDelaySec"]),
            "TruePositives": pm["truePositives"],
            "FalsePositives": pm["falsePositives"],
            "FalseNegatives": pm["falseNegatives"],
            "TrueNegatives": pm["trueNegatives"],
        })

        # Event-level row
        rows.append({
            "Configuration": name,
            "EvaluationUnit": "Event-level",
            "Precision": format_metric(em.get("eventPrecision")),
            "Recall": format_metric(em.get("eventRecall")),
            "F1Score": format_metric(em.get("eventF1Score")),
            "FalsePositiveRate": "N/A (discrete events)",
            "TotalAlerts": om["totalAlerts"],
            "AlertsPerTrajectoryHour": om["alertsPerHour"],
            "AvgDetectionDelaySec": format_metric(em.get("avgDetectionDelaySec")),
            "TruePositives": em["detectedEvents"],
            "FalsePositives": em["falsePositiveEvents"],
            "FalseNegatives": em["missedEvents"],
            "TrueNegatives": "N/A",
        })

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def print_comparison_table(eval_results: Dict[str, Any]) -> None:
    """Print readable side-by-side terminal comparison for both point-level and event-level."""
    total_pts = eval_results.get("totalTrajectoryPoints", 0)
    total_hrs = eval_results.get("totalTrajectoryHours", 0)
    total_evts = eval_results.get("totalGroundTruthEvents", 6)

    print("=" * 105)
    print("COMPARATIVE EVALUATION: 4 ANOMALY DETECTION CONFIGURATIONS")
    print(f"Dataset Points: {total_pts} | Trajectory Hours: {total_hrs}h | Ground-Truth Events: {total_evts}")
    print("=" * 105)

    print("\n[POINT-LEVEL CLASSIFICATION METRICS] (Every trajectory observation evaluated individually)")
    print("-" * 105)
    fmt_pt = "{:<28} | {:<9} | {:<8} | {:<8} | {:<8} | {:<10} | {:<16}"
    print(fmt_pt.format("Configuration", "Precision", "Recall", "F1", "FPR", "Alerts/Hr", "TP / FP / FN / TN"))
    print("-" * 105)

    for _, cfg in eval_results["configurations"].items():
        name = cfg.get("configName", "Unknown")
        if cfg.get("status") == "UNAVAILABLE":
            print(f"{name:<28} | N/A (scikit-learn not installed)")
            continue

        pm = cfg["pointMetrics"]
        om = cfg["operationalMetrics"]

        p_str = format_metric(pm["precision"])
        r_str = format_metric(pm["recall"])
        f_str = format_metric(pm["f1Score"])
        fpr_str = format_metric(pm["falsePositiveRate"])
        rate_str = str(om["alertsPerHour"])
        cm_str = f"{pm['truePositives']} / {pm['falsePositives']} / {pm['falseNegatives']} / {pm['trueNegatives']}"

        print(fmt_pt.format(name, p_str, r_str, f_str, fpr_str, rate_str, cm_str))

    print("-" * 105)

    print("\n[EVENT-LEVEL OPERATIONAL METRICS] (Consolidated events; repeated alerts do not increment TP)")
    print("-" * 105)
    fmt_ev = "{:<28} | {:<9} | {:<8} | {:<8} | {:<10} | {:<10} | {:<16}"
    print(fmt_ev.format("Configuration", "Precision", "Recall", "F1", "Delay (s)", "Alerts/Hr", "TP / FP / FN"))
    print("-" * 105)

    for _, cfg in eval_results["configurations"].items():
        name = cfg.get("configName", "Unknown")
        if cfg.get("status") == "UNAVAILABLE":
            print(f"{name:<28} | N/A (scikit-learn not installed)")
            continue

        om = cfg["operationalMetrics"]
        em = cfg["eventMetrics"]

        p_str = format_metric(em.get("eventPrecision"))
        r_str = format_metric(em.get("eventRecall"))
        f_str = format_metric(em.get("eventF1Score"))
        delay_str = format_metric(em.get("avgDetectionDelaySec"))
        rate_str = str(om["alertsPerHour"])
        cm_str = f"{em['detectedEvents']} / {em['falsePositiveEvents']} / {em['missedEvents']}"

        print(fmt_ev.format(name, p_str, r_str, f_str, delay_str, rate_str, cm_str))

    print("=" * 105)


def main():
    parser = argparse.ArgumentParser(
        description="Lightweight evaluation comparing 4 anomaly detection configurations."
    )
    parser.add_argument(
        "--trajectories",
        type=str,
        default=str(Path(__file__).parent.parent / "data" / "synthetic" / "trajectories.json"),
        help="Path to input trajectories JSON file",
    )
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=str(Path(__file__).parent.parent / "data" / "synthetic" / "ground_truth_labels.json"),
        help="Path to ground truth labels JSON file",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=str(Path(__file__).parent.parent / "data" / "synthetic" / "evaluation_comparison.csv"),
        help="Path to output CSV results file",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=str(Path(__file__).parent.parent / "data" / "synthetic" / "evaluation_comparison.json"),
        help="Path to output JSON summary file",
    )

    args = parser.parse_args()

    traj_path = Path(args.trajectories)
    gt_path = Path(args.ground_truth)

    # Validate inputs exist
    if not traj_path.exists():
        print(f"[Evaluator] ERROR: Trajectory input file not found: {traj_path.resolve()}", file=sys.stderr)
        sys.exit(1)

    if not gt_path.exists():
        print(f"[Evaluator] ERROR: Ground truth input file not found: {gt_path.resolve()}", file=sys.stderr)
        sys.exit(1)

    with open(traj_path, "r", encoding="utf-8") as f:
        trajectories = json.load(f)

    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    evaluator = PipelineEvaluator(trajectories, ground_truth)
    eval_results = evaluator.run_all()

    # Save outputs
    save_csv_report(eval_results, args.output_csv)

    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=2)

    print_comparison_table(eval_results)
    print(f"\nOutputs successfully saved:")
    print(f"  - CSV Table:  {Path(args.output_csv).resolve()}")
    print(f"  - JSON Bundle: {out_json.resolve()}")


if __name__ == "__main__":
    main()
