"""
Isolation Forest Movement Anomaly Detection Baseline
Maharashtra Tourist Safety Project

Standalone unsupervised ML baseline for trajectory anomaly detection using scikit-learn.
Operates independently from the rule-based anomaly detector without touching the production
alert path.

Documented Trajectory Features Extracted:
  1. speed_mps: Point-to-point velocity (metres/sec)
  2. acceleration_mps2: Rate of speed change between successive steps
  3. turn_angle_deg: Angular bearing deviation between consecutive segments
  4. window_displacement_m: Maximum displacement over recent sliding window (captures inactivity)
  5. accuracy_m: GPS measurement error/uncertainty
  6. nearest_danger_zone_dist_m: Distance to the closest restricted or hazard geofence

Outputs predictions in a machine-readable JSON format suitable for comparison
with ground-truth labels.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Dependency Inspection ──────────────────────────────────────────────────────
try:
    import numpy as np
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
    SKLEARN_ERROR = None
except ImportError as err:
    np = None  # type: ignore
    IsolationForest = None  # type: ignore
    SKLEARN_AVAILABLE = False
    SKLEARN_ERROR = str(err)

# ── Geodesic Distance Helper ───────────────────────────────────────────────────
EARTH_RADIUS_M = 6_371_000.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two coordinates in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return EARTH_RADIUS_M * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute forward azimuth bearing in degrees [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


# ── Reference Hazard/Restricted Zones ──────────────────────────────────────────
DANGER_ZONES = [
    {"name": "Dharavi", "lat": 19.0390, "lng": 72.8530, "radius": 2000.0},
    {"name": "Ratnagiri Coastal", "lat": 16.9902, "lng": 73.3120, "radius": 10000.0},
    {"name": "Tadoba Tiger Reserve", "lat": 20.2280, "lng": 79.3950, "radius": 30000.0},
    {"name": "Melghat Tiger Reserve", "lat": 21.5000, "lng": 77.0000, "radius": 40000.0},
]


class IsolationForestBaseline:
    """
    Configurable Isolation Forest baseline for trajectory anomaly detection.
    """

    FEATURE_NAMES = [
        "speed_mps",
        "acceleration_mps2",
        "turn_angle_deg",
        "window_displacement_m",
        "accuracy_m",
        "nearest_danger_zone_dist_m",
    ]

    def __init__(
        self,
        contamination: float = 0.20,
        n_estimators: int = 100,
        max_samples: str | int = "auto",
        random_state: int = 42,
    ):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state
        self.model: Optional[Any] = None

    def check_dependencies(self) -> Tuple[bool, Optional[str]]:
        """Verify that scikit-learn and numpy are installed."""
        if not SKLEARN_AVAILABLE:
            return False, (
                f"Missing required ML dependency: {SKLEARN_ERROR}. "
                "Please ensure scikit-learn and numpy are installed "
                "(pip install scikit-learn numpy)."
            )
        return True, None

    def extract_features(
        self,
        trajectories: List[Dict[str, Any]],
    ) -> Tuple[Any, List[Dict[str, Any]]]:
        """
        Extract documented trajectory movement features for each point.
        Processes points grouped by touristId in chronological order.
        """
        from collections import defaultdict

        tourist_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for pt in trajectories:
            tourist_groups[pt["touristId"]].append(pt)

        feature_matrix = []
        point_metadata = []

        for tid, points in tourist_groups.items():
            # Sort chronologically
            sorted_pts = sorted(points, key=lambda p: p["timestamp"])
            history_window: List[Dict[str, Any]] = []

            prev_speed = 0.0
            prev_bearing: Optional[float] = None

            for i, pt in enumerate(sorted_pts):
                lat = float(pt["latitude"])
                lng = float(pt["longitude"])
                ts = pt["timestamp"]
                acc = float(pt.get("accuracy", 5.0) or 5.0)

                history_window.append(pt)
                # Keep sliding window within 10 minutes
                while history_window and (ts - history_window[0]["timestamp"] > 600_000):
                    history_window.pop(0)

                # 1. Speed
                if i > 0:
                    prev_pt = sorted_pts[i - 1]
                    dt_s = (ts - prev_pt["timestamp"]) / 1000.0
                    if dt_s > 0:
                        dist_m = haversine_meters(prev_pt["latitude"], prev_pt["longitude"], lat, lng)
                        speed_mps = dist_m / dt_s
                    else:
                        speed_mps = prev_speed
                else:
                    speed_mps = float(pt.get("speedMps", 0.0) or 0.0)
                    dt_s = 15.0

                # 2. Acceleration
                if i > 0 and dt_s > 0:
                    accel_mps2 = abs(speed_mps - prev_speed) / dt_s
                else:
                    accel_mps2 = 0.0
                prev_speed = speed_mps

                # 3. Turn Angle
                if i > 0:
                    prev_pt = sorted_pts[i - 1]
                    cur_bearing = calculate_bearing(prev_pt["latitude"], prev_pt["longitude"], lat, lng)
                    if prev_bearing is not None and haversine_meters(prev_pt["latitude"], prev_pt["longitude"], lat, lng) >= 3.0:
                        diff = (cur_bearing - prev_bearing + 180.0) % 360.0 - 180.0
                        turn_angle_deg = abs(diff)
                    else:
                        turn_angle_deg = 0.0
                    prev_bearing = cur_bearing
                else:
                    turn_angle_deg = 0.0
                    prev_bearing = None

                # 4. Window Displacement (captures inactivity / stationary state)
                if len(history_window) >= 2:
                    window_disp_m = max(
                        haversine_meters(p["latitude"], p["longitude"], lat, lng)
                        for p in history_window
                    )
                else:
                    window_disp_m = 50.0  # nominal default for initial point

                # 5. Distance to nearest hazard/restricted zone
                min_danger_dist_m = min(
                    haversine_meters(lat, lng, z["lat"], z["lng"])
                    for z in DANGER_ZONES
                )

                row = [
                    round(speed_mps, 4),
                    round(accel_mps2, 4),
                    round(turn_angle_deg, 2),
                    round(window_disp_m, 2),
                    round(acc, 2),
                    round(min_danger_dist_m, 2),
                ]
                feature_matrix.append(row)

                point_metadata.append({
                    "pointIndex": pt.get("pointIndex", i),
                    "touristId": tid,
                    "timestamp": ts,
                    "latitude": lat,
                    "longitude": lng,
                    "features": {
                        "speed_mps": round(speed_mps, 2),
                        "acceleration_mps2": round(accel_mps2, 2),
                        "turn_angle_deg": round(turn_angle_deg, 1),
                        "window_displacement_m": round(window_disp_m, 1),
                        "accuracy_m": round(acc, 1),
                        "nearest_danger_zone_dist_m": round(min_danger_dist_m, 1),
                    },
                })

        return np.array(feature_matrix), point_metadata

    def fit_predict(
        self,
        X: Any,
        point_metadata: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Fit Isolation Forest model and generate predictions.
        Returns prediction list with scores and binary anomaly flags.
        """
        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            max_samples=self.max_samples,
            random_state=self.random_state,
        )

        preds = self.model.fit_predict(X)  # -1 for anomaly, 1 for inlier
        scores = self.model.decision_function(X)  # lower = more abnormal

        results = []
        for i, meta in enumerate(point_metadata):
            is_anomaly = bool(preds[i] == -1)
            score = float(scores[i])
            results.append({
                "pointIndex": meta["pointIndex"],
                "touristId": meta["touristId"],
                "timestamp": meta["timestamp"],
                "latitude": meta["latitude"],
                "longitude": meta["longitude"],
                "rawAnomalyScore": round(score, 5),
                "isAnomaly": is_anomaly,
                "predictionLabel": "ANOMALY" if is_anomaly else "NORMAL",
                "features": meta["features"],
            })

        return results

    def evaluate_ground_truth(
        self,
        predictions: List[Dict[str, Any]],
        ground_truth: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare predictions against ground-truth point labels.
        Computes precision, recall, F1, and confusion matrix.
        """
        gt_points = ground_truth.get("pointLabels", [])
        gt_map = {(p["touristId"], p["timestamp"]): p for p in gt_points}

        tp = 0
        fp = 0
        fn = 0
        tn = 0
        matched_count = 0

        for pred in predictions:
            key = (pred["touristId"], pred["timestamp"])
            gt = gt_map.get(key)
            if gt is None:
                continue

            matched_count += 1
            pred_anomaly = pred["isAnomaly"]
            true_anomaly = bool(gt.get("isAnomaly", False))
            pred["groundTruth"] = {
                "isAnomaly": true_anomaly,
                "groundTruthType": gt.get("groundTruthType", "UNKNOWN"),
                "scenario": gt.get("scenario", "UNKNOWN"),
            }

            if pred_anomaly and true_anomaly:
                tp += 1
            elif pred_anomaly and not true_anomaly:
                fp += 1
            elif not pred_anomaly and true_anomaly:
                fn += 1
            else:
                tn += 1

        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
        recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
        f1 = round(2.0 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

        return {
            "totalPointsEvaluated": matched_count,
            "truePositives": tp,
            "falsePositives": fp,
            "falseNegatives": fn,
            "trueNegatives": tn,
            "precision": precision,
            "recall": recall,
            "f1Score": f1,
        }

    def run_pipeline(
        self,
        trajectories_path: str | Path,
        ground_truth_path: Optional[str | Path] = None,
        output_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """
        End-to-end pipeline: load data, check dependencies, extract features,
        generate predictions, evaluate ground truth, and save machine-readable JSON.
        """
        # Step 1: Check dependencies
        deps_ok, error_msg = self.check_dependencies()
        if not deps_ok:
            return {
                "status": "ERROR",
                "message": error_msg,
            }

        # Step 2: Validate input trajectory file
        traj_file = Path(trajectories_path)
        if not traj_file.exists():
            return {
                "status": "ERROR",
                "message": f"Required input trajectory file not found: {traj_file.resolve()}",
            }

        try:
            with open(traj_file, "r", encoding="utf-8") as f:
                trajectories = json.load(f)
        except Exception as err:
            return {
                "status": "ERROR",
                "message": f"Failed to parse trajectory JSON file: {err}",
            }

        if not isinstance(trajectories, list) or len(trajectories) == 0:
            return {
                "status": "ERROR",
                "message": "Trajectory file is empty or does not contain a list of points.",
            }

        # Step 3: Extract documented movement features
        X, point_metadata = self.extract_features(trajectories)

        # Step 4: Fit model & generate predictions
        predictions = self.fit_predict(X, point_metadata)

        # Step 5: Optional ground truth evaluation
        metrics = None
        if ground_truth_path:
            gt_file = Path(ground_truth_path)
            if gt_file.exists():
                try:
                    with open(gt_file, "r", encoding="utf-8") as f:
                        gt_data = json.load(f)
                    metrics = self.evaluate_ground_truth(predictions, gt_data)
                except Exception as err:
                    metrics = {"status": "ERROR", "reason": f"Ground-truth evaluation failed: {err}"}
            else:
                metrics = {
                    "status": "SKIPPED",
                    "reason": f"Ground-truth file not found: {gt_file.resolve()}",
                }

        # Step 6: Build machine-readable output bundle
        output_bundle = {
            "modelName": "IsolationForestBaseline",
            "timestampUtc": datetime.now(timezone.utc).isoformat(),
            "config": {
                "contamination": self.contamination,
                "n_estimators": self.n_estimators,
                "max_samples": self.max_samples,
                "random_state": self.random_state,
                "featuresExtracted": self.FEATURE_NAMES,
            },
            "datasetSummary": {
                "trajectorySourceFile": str(traj_file.resolve()),
                "totalPoints": len(predictions),
                "totalAnomaliesPredicted": sum(1 for p in predictions if p["isAnomaly"]),
            },
            "evaluationMetrics": metrics,
            "predictions": predictions,
        }

        # Step 7: Save to output file if specified
        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(output_bundle, f, indent=2)
            output_bundle["savedOutputFile"] = str(out_file.resolve())

        return output_bundle


def main():
    parser = argparse.ArgumentParser(
        description="Run standalone Isolation Forest baseline on trajectory data."
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
        help="Path to ground truth labels JSON file (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path(__file__).parent.parent / "data" / "synthetic" / "isolation_forest_predictions.json"),
        help="Path to output predictions JSON file",
    )
    parser.add_argument(
        "--contamination",
        type=float,
        default=0.20,
        help="Expected anomaly proportion (default: 0.20)",
    )
    parser.add_argument(
        "--estimators",
        type=int,
        default=100,
        help="Number of trees in Isolation Forest (default: 100)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random state seed (default: 42)",
    )

    args = parser.parse_args()

    baseline = IsolationForestBaseline(
        contamination=args.contamination,
        n_estimators=args.estimators,
        random_state=args.seed,
    )

    result = baseline.run_pipeline(
        trajectories_path=args.trajectories,
        ground_truth_path=args.ground_truth,
        output_path=args.output,
    )

    if result.get("status") == "ERROR":
        print(f"[IsolationForestBaseline] ERROR: {result.get('message')}", file=sys.stderr)
        sys.exit(1)

    print(f"Isolation Forest Baseline executed successfully:")
    print(f"  - Points analyzed: {result['datasetSummary']['totalPoints']}")
    print(f"  - Anomalies predicted: {result['datasetSummary']['totalAnomaliesPredicted']}")
    if result.get("evaluationMetrics"):
        m = result["evaluationMetrics"]
        print(f"  - Precision: {m.get('precision', 'N/A')}")
        print(f"  - Recall:    {m.get('recall', 'N/A')}")
        print(f"  - F1-Score:  {m.get('f1Score', 'N/A')}")
    print(f"  - Predictions saved to: {result.get('savedOutputFile')}")


if __name__ == "__main__":
    main()
