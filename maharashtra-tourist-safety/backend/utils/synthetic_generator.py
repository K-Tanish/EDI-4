"""
Synthetic Tourist Trajectory Data Generator
Maharashtra Tourist Safety Project

Generates reproducible synthetic trajectory data with multi-tourist scenarios:
  1. normal_movement: Normal walking/touring trajectories
  2. prolonged_inactivity: Stationary duration exceeding 10-minute threshold
  3. abnormal_speed: Sudden speed jumps exceeding 30 m/s threshold
  4. restricted_zone_entry: Incursion into restricted geofence (Tadoba Reserve)
  5. gps_boundary_noise: Oscillations across geofence border caused by high GPS noise
  6. missing_gps_observations: Signal dropout exceeding 5-minute timeout threshold
  7. sos_event: Distress panic button trigger during transit

Output structure strictly separates:
  - scenario_config.json: Random seed, scenario definitions, thresholds
  - trajectories.json: Raw observable GPS trajectory points
  - ground_truth_labels.json: Ground-truth event & point-level anomaly annotations
  - detector_outputs.json: (Optional) alerts produced by baseline rules
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Geodesic Math ──────────────────────────────────────────────────────────────
EARTH_RADIUS_M = 6_371_000.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two coordinates in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def move_point(lat: float, lon: float, distance_m: float, bearing_deg: float) -> Tuple[float, float]:
    """Calculate target latitude & longitude given distance (m) and bearing (degrees)."""
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    d_over_r = distance_m / EARTH_RADIUS_M

    phi2 = math.asin(
        math.sin(phi1) * math.cos(d_over_r) +
        math.cos(phi1) * math.sin(d_over_r) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(d_over_r) * math.cos(phi1),
        math.cos(d_over_r) - math.sin(phi1) * math.sin(phi2)
    )
    return math.degrees(phi2), math.degrees(lambda2)


# ── Reference Zones (Matching routers/zones.py) ────────────────────────────────
ZONES = {
    "TADOBA_RESERVE": {
        "zoneId": "zone-tadoba-restricted",
        "name": "Tadoba Tiger Reserve",
        "riskLevel": "RESTRICTED",
        "centerLat": 20.2280,
        "centerLng": 79.3950,
        "radiusMeters": 30_000.0,
    },
    "DHARAVI": {
        "zoneId": "zone-dharavi-high",
        "name": "Dharavi",
        "riskLevel": "HIGH",
        "centerLat": 19.0390,
        "centerLng": 72.8530,
        "radiusMeters": 2_000.0,
    },
    "PUNE_CORE": {
        "zoneId": "zone-pune-urban",
        "name": "Pune Urban Core",
        "riskLevel": "MEDIUM",
        "centerLat": 18.5204,
        "centerLng": 73.8567,
        "radiusMeters": 12_000.0,
    },
    "MUMBAI_CORE": {
        "zoneId": "zone-mumbai-urban",
        "name": "Mumbai Urban Core",
        "riskLevel": "MEDIUM",
        "centerLat": 19.0760,
        "centerLng": 72.8777,
        "radiusMeters": 15_000.0,
    },
}

# ── Threshold Constants (Matching backend workers and detectors) ───────────────
DETECTOR_THRESHOLDS = {
    "stationary_dist_meters": 10.0,
    "stationary_window_ms": 600_000,     # 10 minutes
    "abnormal_speed_mps": 30.0,          # ~108 km/h
    "gps_loss_timeout_ms": 300_000,      # 5 minutes
    "geofence_cooldown_seconds": 300,    # 5 minutes
}


class SyntheticTrajectoryGenerator:
    """
    Lightweight, reproducible generator for synthetic tourist trajectories.
    Generates labelled scenarios with strict separation between observations
    and ground-truth labels.
    """

    def __init__(self, seed: int = 42, base_time_ms: Optional[int] = None):
        self.seed = seed
        self.rng = random.Random(seed)
        # Default base time: 2026-10-26 09:00:00 UTC if unspecified
        self.base_time_ms = base_time_ms or 1_793_005_200_000

    def reset_seed(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed)

    # ── Scenario 1: Normal Movement ───────────────────────────────────────────
    def generate_normal_movement(
        self,
        tourist_id: str = "tourist_normal_001",
        start_lat: float = 18.5204,
        start_lng: float = 73.8567,
        num_points: int = 40,
        interval_seconds: int = 15,
        speed_range: Tuple[float, float] = (1.1, 1.6),
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Pedestrian moving at normal walking speed with smooth directional drift."""
        observations = []
        point_labels = []
        cur_lat, cur_lng = start_lat, start_lng
        cur_time = self.base_time_ms
        bearing = self.rng.uniform(0, 360)

        for idx in range(num_points):
            speed = self.rng.uniform(*speed_range)
            dist = speed * interval_seconds
            bearing = (bearing + self.rng.gauss(0, 8)) % 360
            cur_lat, cur_lng = move_point(cur_lat, cur_lng, dist, bearing)
            cur_time += interval_seconds * 1000

            accuracy = round(self.rng.uniform(3.0, 7.5), 2)
            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": accuracy,
                "speedMps": round(speed, 2),
                "isOfflineBuffered": False,
            }
            observations.append(obs)

            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "normal_movement",
                "isAnomaly": False,
                "groundTruthType": "NORMAL",
                "details": {"speedMps": round(speed, 2), "accuracy": accuracy},
            })

        return observations, point_labels

    # ── Scenario 2: Prolonged Inactivity ──────────────────────────────────────
    def generate_prolonged_inactivity(
        self,
        tourist_id: str = "tourist_inactivity_001",
        start_lat: float = 18.5250,
        start_lng: float = 73.8600,
        walk_points: int = 15,
        stationary_points: int = 50,
        interval_seconds: int = 15,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Tourist walks, then remains stationary (<10m movement) for >10 minutes."""
        observations = []
        point_labels = []
        cur_lat, cur_lng = start_lat, start_lng
        cur_time = self.base_time_ms
        bearing = self.rng.uniform(0, 360)
        idx = 0

        # Phase 1: Walking
        for _ in range(walk_points):
            speed = self.rng.uniform(1.2, 1.5)
            dist = speed * interval_seconds
            cur_lat, cur_lng = move_point(cur_lat, cur_lng, dist, bearing)
            cur_time += interval_seconds * 1000

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(3.0, 6.0), 2),
                "speedMps": round(speed, 2),
                "isOfflineBuffered": False,
            }
            observations.append(obs)
            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "prolonged_inactivity",
                "isAnomaly": False,
                "groundTruthType": "NORMAL",
                "details": {"phase": "walking", "speedMps": round(speed, 2)},
            })
            idx += 1

        # Phase 2: Stationary (stationary anchor point with sub-3m GPS jitter)
        anchor_lat, anchor_lng = cur_lat, cur_lng
        stationary_start_time = cur_time
        threshold_met_idx: Optional[int] = None

        for s_idx in range(stationary_points):
            cur_time += interval_seconds * 1000
            jitter_dist = self.rng.uniform(0.1, 2.5)  # well below 10m threshold
            jitter_bearing = self.rng.uniform(0, 360)
            jit_lat, jit_lng = move_point(anchor_lat, anchor_lng, jitter_dist, jitter_bearing)

            elapsed_stationary_ms = cur_time - stationary_start_time
            is_anomaly = elapsed_stationary_ms >= DETECTOR_THRESHOLDS["stationary_window_ms"]
            if is_anomaly and threshold_met_idx is None:
                threshold_met_idx = idx

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(jit_lat, 6),
                "longitude": round(jit_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(4.0, 8.0), 2),
                "speedMps": round(jitter_dist / interval_seconds, 2),
                "isOfflineBuffered": False,
            }
            observations.append(obs)
            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "prolonged_inactivity",
                "isAnomaly": is_anomaly,
                "groundTruthType": "PROLONGED_INACTIVITY" if is_anomaly else "NORMAL",
                "details": {
                    "phase": "stationary",
                    "elapsedStationaryMs": elapsed_stationary_ms,
                    "distFromAnchorM": round(jitter_dist, 2),
                },
            })
            idx += 1

        event_summary = {
            "eventId": f"event_{tourist_id}_inactivity",
            "touristId": tourist_id,
            "scenario": "prolonged_inactivity",
            "anomalyType": "PROLONGED_INACTIVITY",
            "stationaryStartTime": stationary_start_time,
            "thresholdExceededTime": stationary_start_time + DETECTOR_THRESHOLDS["stationary_window_ms"],
            "totalDurationMs": stationary_points * interval_seconds * 1000,
            "anchorLatitude": round(anchor_lat, 6),
            "anchorLongitude": round(anchor_lng, 6),
        }
        return observations, point_labels, event_summary

    # ── Scenario 3: Abnormal Speed ────────────────────────────────────────────
    def generate_abnormal_speed(
        self,
        tourist_id: str = "tourist_speed_001",
        start_lat: float = 19.0760,
        start_lng: float = 72.8777,
        num_points: int = 30,
        anomaly_indices: Tuple[int, ...] = (14, 15),
        interval_seconds: int = 15,
        normal_speed: float = 1.3,
        abnormal_speed: float = 48.0,  # 48 m/s (~172 km/h > 30 m/s threshold)
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Pedestrian pace with abrupt impossible speed jumps between steps."""
        observations = []
        point_labels = []
        cur_lat, cur_lng = start_lat, start_lng
        cur_time = self.base_time_ms
        bearing = 90.0

        anomaly_points_meta = []

        for idx in range(num_points):
            is_jump = idx in anomaly_indices
            step_speed = abnormal_speed if is_jump else normal_speed + self.rng.uniform(-0.2, 0.2)
            dist = step_speed * interval_seconds

            cur_lat, cur_lng = move_point(cur_lat, cur_lng, dist, bearing)
            cur_time += interval_seconds * 1000

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(3.0, 6.0), 2),
                "speedMps": round(step_speed, 2),
                "isOfflineBuffered": False,
            }
            observations.append(obs)

            label_entry = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "abnormal_speed",
                "isAnomaly": is_jump,
                "groundTruthType": "ABNORMAL_SPEED" if is_jump else "NORMAL",
                "details": {
                    "calculatedSpeedMps": round(step_speed, 2),
                    "thresholdMps": DETECTOR_THRESHOLDS["abnormal_speed_mps"],
                },
            }
            point_labels.append(label_entry)
            if is_jump:
                anomaly_points_meta.append({
                    "pointIndex": idx,
                    "timestamp": cur_time,
                    "speedMps": round(step_speed, 2),
                })

        event_summary = {
            "eventId": f"event_{tourist_id}_speed",
            "touristId": tourist_id,
            "scenario": "abnormal_speed",
            "anomalyType": "ABNORMAL_SPEED",
            "anomalyPoints": anomaly_points_meta,
            "speedThresholdMps": DETECTOR_THRESHOLDS["abnormal_speed_mps"],
        }
        return observations, point_labels, event_summary

    # ── Scenario 4: Restricted Zone Entry ─────────────────────────────────────
    def generate_restricted_zone_entry(
        self,
        tourist_id: str = "tourist_restricted_001",
        zone_key: str = "TADOBA_RESERVE",
        num_points: int = 35,
        interval_seconds: int = 15,
        entry_speed_mps: float = 12.0,  # vehicle ingress towards reserve center
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Tourist heads from outside the perimeter directly into a restricted zone."""
        zone = ZONES[zone_key]
        center_lat, center_lng = zone["centerLat"], zone["centerLng"]
        radius = zone["radiusMeters"]

        # Place initial point ~1,500m outside boundary
        initial_distance = radius + 1500.0
        # Approach from North (bearing 180 degrees moves South towards center)
        start_lat, start_lng = move_point(center_lat, center_lng, initial_distance, 0.0)

        observations = []
        point_labels = []
        cur_lat, cur_lng = start_lat, start_lng
        cur_time = self.base_time_ms
        crossing_point_idx: Optional[int] = None

        for idx in range(num_points):
            dist_to_center = haversine_meters(cur_lat, cur_lng, center_lat, center_lng)
            is_inside = dist_to_center <= radius

            if is_inside and crossing_point_idx is None:
                crossing_point_idx = idx

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(3.5, 7.0), 2),
                "speedMps": round(entry_speed_mps, 2),
                "isOfflineBuffered": False,
            }
            observations.append(obs)

            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "restricted_zone_entry",
                "isAnomaly": is_inside,
                "groundTruthType": "RESTRICTED_ZONE_ENTRY" if is_inside else "NORMAL",
                "details": {
                    "zoneName": zone["name"],
                    "riskLevel": zone["riskLevel"],
                    "distanceToCenterM": round(dist_to_center, 2),
                    "zoneRadiusM": radius,
                    "isInsideZone": is_inside,
                },
            })

            # Move south towards center
            cur_lat, cur_lng = move_point(cur_lat, cur_lng, entry_speed_mps * interval_seconds, 180.0)
            cur_time += interval_seconds * 1000

        event_summary = {
            "eventId": f"event_{tourist_id}_zone_entry",
            "touristId": tourist_id,
            "scenario": "restricted_zone_entry",
            "anomalyType": "RESTRICTED_ZONE_ENTRY",
            "zoneName": zone["name"],
            "zoneRiskLevel": zone["riskLevel"],
            "boundaryRadiusM": radius,
            "crossingPointIndex": crossing_point_idx,
            "crossingTimestamp": observations[crossing_point_idx]["timestamp"] if crossing_point_idx is not None else None,
        }
        return observations, point_labels, event_summary

    # ── Scenario 5: GPS Noise Near Boundary ───────────────────────────────────
    def generate_gps_boundary_noise(
        self,
        tourist_id: str = "tourist_boundary_noise_001",
        zone_key: str = "DHARAVI",
        num_points: int = 30,
        interval_seconds: int = 15,
        noise_std_meters: float = 35.0,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Tourist walks along the outer perimeter; heavy GPS noise causes false crossings."""
        zone = ZONES[zone_key]
        center_lat, center_lng = zone["centerLat"], zone["centerLng"]
        radius = zone["radiusMeters"]

        # True path is just outside the border (radius + 5m)
        true_dist = radius + 5.0
        angular_speed = 0.5  # degrees per step around circle

        observations = []
        point_labels = []
        cur_angle = 0.0
        cur_time = self.base_time_ms
        border_crossing_counts = 0

        for idx in range(num_points):
            true_lat, true_lng = move_point(center_lat, center_lng, true_dist, cur_angle)

            # Inject 2D Gaussian GPS noise
            noise_dist = abs(self.rng.gauss(0, noise_std_meters))
            noise_bearing = self.rng.uniform(0, 360)
            obs_lat, obs_lng = move_point(true_lat, true_lng, noise_dist, noise_bearing)

            obs_dist_to_center = haversine_meters(obs_lat, obs_lng, center_lat, center_lng)
            apparent_inside = obs_dist_to_center <= radius
            if apparent_inside:
                border_crossing_counts += 1

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(obs_lat, 6),
                "longitude": round(obs_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(noise_dist + self.rng.uniform(5.0, 15.0), 2),
                "speedMps": 1.4,
                "isOfflineBuffered": False,
            }
            observations.append(obs)

            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "gps_boundary_noise",
                "isAnomaly": True,
                "groundTruthType": "GPS_BOUNDARY_NOISE",
                "details": {
                    "trueDistToCenterM": round(true_dist, 2),
                    "observedDistToCenterM": round(obs_dist_to_center, 2),
                    "noiseInjectedM": round(noise_dist, 2),
                    "boundaryRadiusM": radius,
                    "apparentInside": apparent_inside,
                    "trueInside": False,
                },
            })

            cur_angle += angular_speed
            cur_time += interval_seconds * 1000

        event_summary = {
            "eventId": f"event_{tourist_id}_boundary_noise",
            "touristId": tourist_id,
            "scenario": "gps_boundary_noise",
            "anomalyType": "GPS_BOUNDARY_NOISE",
            "zoneName": zone["name"],
            "noiseStdMeters": noise_std_meters,
            "totalCrossingsFromNoise": border_crossing_counts,
        }
        return observations, point_labels, event_summary

    # ── Scenario 6: Missing GPS Observations ──────────────────────────────────
    def generate_missing_gps(
        self,
        tourist_id: str = "tourist_missing_gps_001",
        start_lat: float = 18.5204,
        start_lng: float = 73.8567,
        pre_gap_points: int = 12,
        post_gap_points: int = 12,
        interval_seconds: int = 15,
        gap_seconds: int = 420,  # 7 minutes (> 5 min timeout)
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Normal tracking followed by signal blackout exceeding the 5-minute timeout."""
        observations = []
        point_labels = []
        cur_lat, cur_lng = start_lat, start_lng
        cur_time = self.base_time_ms
        bearing = 45.0
        idx = 0

        # Phase 1: Pre-gap points
        for _ in range(pre_gap_points):
            dist = 1.3 * interval_seconds
            cur_lat, cur_lng = move_point(cur_lat, cur_lng, dist, bearing)
            cur_time += interval_seconds * 1000

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(3.0, 5.0), 2),
                "speedMps": 1.3,
                "isOfflineBuffered": False,
            }
            observations.append(obs)
            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "missing_gps_observations",
                "isAnomaly": False,
                "groundTruthType": "NORMAL",
                "details": {"phase": "pre_blackout"},
            })
            idx += 1

        gap_start_time = cur_time
        gap_start_coords = (cur_lat, cur_lng)

        # Blackout period (gap occurs here - NO observations recorded)
        cur_time += gap_seconds * 1000
        # Tourist actually walked during blackout
        cur_lat, cur_lng = move_point(cur_lat, cur_lng, 1.3 * gap_seconds, bearing)
        gap_end_time = cur_time

        # Phase 2: Signal restored
        for _ in range(post_gap_points):
            dist = 1.3 * interval_seconds
            cur_lat, cur_lng = move_point(cur_lat, cur_lng, dist, bearing)
            cur_time += interval_seconds * 1000

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(3.0, 5.0), 2),
                "speedMps": 1.3,
                "isOfflineBuffered": False,
            }
            observations.append(obs)
            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "missing_gps_observations",
                "isAnomaly": False,
                "groundTruthType": "NORMAL",
                "details": {"phase": "post_blackout"},
            })
            idx += 1

        event_summary = {
            "eventId": f"event_{tourist_id}_missing_gps",
            "touristId": tourist_id,
            "scenario": "missing_gps_observations",
            "anomalyType": "MISSING_GPS_OBSERVATION",
            "gapStartTimestamp": gap_start_time,
            "gapEndTimestamp": gap_end_time,
            "gapDurationSeconds": gap_seconds,
            "timeoutThresholdSeconds": DETECTOR_THRESHOLDS["gps_loss_timeout_ms"] // 1000,
            "isTimeoutExceeded": gap_seconds > (DETECTOR_THRESHOLDS["gps_loss_timeout_ms"] / 1000),
            "lastObservedLatitude": round(gap_start_coords[0], 6),
            "lastObservedLongitude": round(gap_start_coords[1], 6),
        }
        return observations, point_labels, event_summary

    # ── Scenario 7: SOS Distress Event ────────────────────────────────────────
    def generate_sos_event(
        self,
        tourist_id: str = "tourist_sos_001",
        start_lat: float = 16.9902,
        start_lng: float = 73.3120,
        num_points: int = 25,
        sos_trigger_index: int = 12,
        interval_seconds: int = 15,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Tourist moves along coast and triggers panic SOS at specific timestamp."""
        observations = []
        point_labels = []
        cur_lat, cur_lng = start_lat, start_lng
        cur_time = self.base_time_ms
        bearing = 210.0
        sos_meta = {}

        for idx in range(num_points):
            is_sos_point = idx == sos_trigger_index
            is_post_sos = idx >= sos_trigger_index

            # Slow down or become stationary after panic
            speed = 0.2 if is_post_sos else 1.3
            dist = speed * interval_seconds
            cur_lat, cur_lng = move_point(cur_lat, cur_lng, dist, bearing)
            cur_time += interval_seconds * 1000

            obs = {
                "pointIndex": idx,
                "touristId": tourist_id,
                "latitude": round(cur_lat, 6),
                "longitude": round(cur_lng, 6),
                "timestamp": cur_time,
                "accuracy": round(self.rng.uniform(3.0, 5.0), 2),
                "speedMps": round(speed, 2),
                "isOfflineBuffered": False,
            }
            observations.append(obs)

            ground_truth_type = "SOS_TRIGGERED" if is_sos_point else ("SOS_ACTIVE" if is_post_sos else "NORMAL")
            point_labels.append({
                "pointIndex": idx,
                "touristId": tourist_id,
                "timestamp": cur_time,
                "scenario": "sos_event",
                "isAnomaly": is_post_sos,
                "groundTruthType": ground_truth_type,
                "details": {
                    "isSosTriggerPoint": is_sos_point,
                    "isSosActive": is_post_sos,
                },
            })

            if is_sos_point:
                sos_meta = {
                    "eventId": f"event_{tourist_id}_sos",
                    "touristId": tourist_id,
                    "scenario": "sos_event",
                    "anomalyType": "SOS_EVENT",
                    "triggerIndex": idx,
                    "triggerTimestamp": cur_time,
                    "latitude": round(cur_lat, 6),
                    "longitude": round(cur_lng, 6),
                }

        return observations, point_labels, sos_meta

    # ── Master Dataset Generation ─────────────────────────────────────────────
    def generate_dataset(self) -> Dict[str, Any]:
        """Runs all 7 scenarios and produces separate ground truth & trajectory bundles."""
        all_observations: List[Dict[str, Any]] = []
        all_point_labels: List[Dict[str, Any]] = []
        event_summaries: List[Dict[str, Any]] = []

        # 1. Normal movement (2 tourists)
        obs_norm1, lbl_norm1 = self.generate_normal_movement("tourist_normal_001", 18.5204, 73.8567)
        obs_norm2, lbl_norm2 = self.generate_normal_movement("tourist_normal_002", 19.0760, 72.8777)
        all_observations.extend(obs_norm1 + obs_norm2)
        all_point_labels.extend(lbl_norm1 + lbl_norm2)

        # 2. Prolonged inactivity
        obs_inac, lbl_inac, evt_inac = self.generate_prolonged_inactivity("tourist_inactivity_001")
        all_observations.extend(obs_inac)
        all_point_labels.extend(lbl_inac)
        event_summaries.append(evt_inac)

        # 3. Abnormal speed
        obs_spd, lbl_spd, evt_spd = self.generate_abnormal_speed("tourist_speed_001")
        all_observations.extend(obs_spd)
        all_point_labels.extend(lbl_spd)
        event_summaries.append(evt_spd)

        # 4. Restricted zone entry
        obs_rst, lbl_rst, evt_rst = self.generate_restricted_zone_entry("tourist_restricted_001")
        all_observations.extend(obs_rst)
        all_point_labels.extend(lbl_rst)
        event_summaries.append(evt_rst)

        # 5. GPS boundary noise
        obs_bnd, lbl_bnd, evt_bnd = self.generate_gps_boundary_noise("tourist_boundary_noise_001")
        all_observations.extend(obs_bnd)
        all_point_labels.extend(lbl_bnd)
        event_summaries.append(evt_bnd)

        # 6. Missing GPS observations
        obs_mis, lbl_mis, evt_mis = self.generate_missing_gps("tourist_missing_gps_001")
        all_observations.extend(obs_mis)
        all_point_labels.extend(lbl_mis)
        event_summaries.append(evt_mis)

        # 7. SOS event
        obs_sos, lbl_sos, evt_sos = self.generate_sos_event("tourist_sos_001")
        all_observations.extend(obs_sos)
        all_point_labels.extend(lbl_sos)
        event_summaries.append(evt_sos)

        # Sort observations by timestamp for deterministic streaming order
        all_observations.sort(key=lambda p: (p["timestamp"], p["touristId"]))

        tourist_ids = sorted(list({p["touristId"] for p in all_observations}))

        scenario_config = {
            "randomSeed": self.seed,
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "baseTimeMs": self.base_time_ms,
            "touristCount": len(tourist_ids),
            "touristIds": tourist_ids,
            "scenarios": [
                "normal_movement",
                "prolonged_inactivity",
                "abnormal_speed",
                "restricted_zone_entry",
                "gps_boundary_noise",
                "missing_gps_observations",
                "sos_event",
            ],
            "detectorThresholds": DETECTOR_THRESHOLDS,
            "zonesConfigured": ZONES,
        }

        ground_truth_labels = {
            "datasetSeed": self.seed,
            "totalLabelledPoints": len(all_point_labels),
            "totalAnomalousPoints": sum(1 for p in all_point_labels if p["isAnomaly"]),
            "scenarioEventSummaries": event_summaries,
            "pointLabels": all_point_labels,
        }

        return {
            "config": scenario_config,
            "trajectories": all_observations,
            "ground_truth": ground_truth_labels,
        }

    # ── Baseline Detector Simulation ──────────────────────────────────────────
    def simulate_baseline_detector(self, trajectories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes baseline heuristic detection rules purely on observed points.
        Saved strictly separate from ground truth to allow precision/recall evaluation.
        """
        from collections import defaultdict

        history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        alerts: List[Dict[str, Any]] = []

        for pt in trajectories:
            tid = pt["touristId"]
            history[tid].append(pt)
            pts = history[tid]

            # Rule 1: Geofence check
            for _, zone in ZONES.items():
                if zone["riskLevel"] in ("HIGH", "RESTRICTED"):
                    dist = haversine_meters(pt["latitude"], pt["longitude"], zone["centerLat"], zone["centerLng"])
                    if dist <= zone["radiusMeters"]:
                        alerts.append({
                            "detector": "GEOFENCE_ENGINE",
                            "alertType": "ZONE_ENTRY",
                            "riskLevel": zone["riskLevel"],
                            "touristId": tid,
                            "timestamp": pt["timestamp"],
                            "zoneName": zone["name"],
                            "distanceToCenterM": round(dist, 2),
                        })

            # Rule 2: Abnormal speed check
            if len(pts) >= 2:
                prev = pts[-2]
                dt_s = (pt["timestamp"] - prev["timestamp"]) / 1000.0
                if dt_s > 0:
                    d_m = haversine_meters(prev["latitude"], prev["longitude"], pt["latitude"], pt["longitude"])
                    speed = d_m / dt_s
                    if speed > DETECTOR_THRESHOLDS["abnormal_speed_mps"]:
                        alerts.append({
                            "detector": "ANOMALY_WORKER",
                            "alertType": "ABNORMAL_SPEED",
                            "riskLevel": "MEDIUM",
                            "touristId": tid,
                            "timestamp": pt["timestamp"],
                            "calculatedSpeedMps": round(speed, 2),
                        })

            # Rule 3: Prolonged stationary check (window: 10 min)
            if len(pts) >= 3:
                now_ms = pt["timestamp"]
                window = [p for p in pts if now_ms - p["timestamp"] <= DETECTOR_THRESHOLDS["stationary_window_ms"]]
                if len(window) >= 3:
                    window_span_ms = window[-1]["timestamp"] - window[0]["timestamp"]
                    if window_span_ms >= DETECTOR_THRESHOLDS["stationary_window_ms"]:
                        max_d = max(
                            haversine_meters(p["latitude"], p["longitude"], pt["latitude"], pt["longitude"])
                            for p in window
                        )
                        if max_d < DETECTOR_THRESHOLDS["stationary_dist_meters"]:
                            alerts.append({
                                "detector": "ANOMALY_WORKER",
                                "alertType": "STATIONARY",
                                "riskLevel": "LOW",
                                "touristId": tid,
                                "timestamp": pt["timestamp"],
                                "maxDispMeters": round(max_d, 2),
                            })

        return {
            "detectorName": "BaselineMaharashtraRuleSet",
            "totalAlertsFired": len(alerts),
            "alerts": alerts,
        }

    # ── File Output ───────────────────────────────────────────────────────────
    def save_dataset(
        self,
        output_dir: str | Path,
        simulate_detector: bool = True,
    ) -> Dict[str, str]:
        """Saves generated dataset into separate JSON files in the specified directory."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        bundle = self.generate_dataset()

        # 1. Save scenario configuration and seed
        config_file = out_path / "scenario_config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(bundle["config"], f, indent=2)

        # 2. Save raw observable trajectories
        traj_file = out_path / "trajectories.json"
        with open(traj_file, "w", encoding="utf-8") as f:
            json.dump(bundle["trajectories"], f, indent=2)

        # 3. Save ground-truth labels separately
        gt_file = out_path / "ground_truth_labels.json"
        with open(gt_file, "w", encoding="utf-8") as f:
            json.dump(bundle["ground_truth"], f, indent=2)

        saved_files = {
            "scenario_config": str(config_file),
            "trajectories": str(traj_file),
            "ground_truth_labels": str(gt_file),
        }

        # 4. Save detector outputs separately if enabled
        if simulate_detector:
            detector_results = self.simulate_baseline_detector(bundle["trajectories"])
            detector_file = out_path / "detector_outputs.json"
            with open(detector_file, "w", encoding="utf-8") as f:
                json.dump(detector_results, f, indent=2)
            saved_files["detector_outputs"] = str(detector_file)

        return saved_files


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic, reproducible tourist trajectory datasets with ground-truth labels."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation (default: 42)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(__file__).parent.parent / "data" / "synthetic"),
        help="Output directory path (default: backend/data/synthetic)",
    )
    parser.add_argument(
        "--no-detector",
        action="store_true",
        help="Skip simulating baseline detector outputs",
    )

    args = parser.parse_args()

    generator = SyntheticTrajectoryGenerator(seed=args.seed)
    saved = generator.save_dataset(
        output_dir=args.output_dir,
        simulate_detector=not args.no_detector,
    )

    print(f"Dataset generated successfully with seed={args.seed}:")
    for key, path in saved.items():
        print(f"  - {key}: {path}")


if __name__ == "__main__":
    main()
