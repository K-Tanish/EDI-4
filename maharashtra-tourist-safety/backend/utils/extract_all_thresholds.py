"""
Extract all thresholds and parameters from the system
"""
import json
import sys
from pathlib import Path

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

# Import all modules
from config import settings
from workers import anomaly_detector
from services import geofence_engine
from utils import isolation_forest_baseline

print("=" * 100)
print("COMPLETE THRESHOLD AND PARAMETER REFERENCE")
print("=" * 100)

print("\n" + "=" * 100)
print("1. MOVEMENT ANOMALY DETECTION THRESHOLDS")
print("=" * 100)
print(f"{'Parameter':<40} {'Value':<20} {'Unit':<20} {'Source'}")
print("-" * 100)
print(f"{'Stationary Distance Threshold':<40} {anomaly_detector._STATIONARY_DIST_M:<20} {'metres':<20} config.py")
print(f"{'Stationary Window Duration':<40} {anomaly_detector._STATIONARY_WINDOW_MS:<20} {'milliseconds':<20} config.py")
print(f"{'Stationary Window Duration':<40} {anomaly_detector._STATIONARY_WINDOW_MS/1000:<20} {'seconds':<20} (converted)")
print(f"{'Stationary Window Duration':<40} {anomaly_detector._STATIONARY_WINDOW_MS/60000:<20} {'minutes':<20} (converted)")
print(f"{'Abnormal Speed Threshold':<40} {anomaly_detector._ABNORMAL_SPEED_MS:<20} {'m/s':<20} config.py")
print(f"{'Abnormal Speed Threshold':<40} {anomaly_detector._ABNORMAL_SPEED_MS*3.6:<20} {'km/h':<20} (converted)")
print(f"{'GPS Loss Timeout':<40} {anomaly_detector._GPS_LOSS_TIMEOUT_MS:<20} {'milliseconds':<20} config.py")
print(f"{'GPS Loss Timeout':<40} {anomaly_detector._GPS_LOSS_TIMEOUT_MS/1000:<20} {'seconds':<20} (converted)")
print(f"{'GPS Loss Timeout':<40} {anomaly_detector._GPS_LOSS_TIMEOUT_MS/60000:<20} {'minutes':<20} (converted)")
print(f"{'Route Deviation Threshold':<40} {anomaly_detector._ROUTE_DEVIATION_M:<20} {'metres':<20} config.py")
print(f"{'Direction Change Threshold':<40} {anomaly_detector._DIRECTION_CHANGE_DEG:<20} {'degrees':<20} config.py")
print(f"{'Minimum Points Required':<40} {anomaly_detector._MIN_POINTS:<20} {'count':<20} config.py")
print(f"{'Min Displacement for Bearing Calc':<40} {anomaly_detector._MIN_DISPLACEMENT_FOR_BEARING_M:<20} {'metres':<20} anomaly_detector.py")

print("\n" + "=" * 100)
print("2. ALERT REFINEMENT & TEMPORAL PERSISTENCE")
print("=" * 100)
print(f"{'Parameter':<40} {'Value':<20} {'Unit':<20} {'Source'}")
print("-" * 100)
print(f"{'Persistence Min Consecutive Detections':<40} {anomaly_detector._PERSISTENCE_MIN_CONSECUTIVE:<20} {'count':<20} config.py")
print(f"{'Persistence Time Window':<40} {anomaly_detector._PERSISTENCE_WINDOW_MS:<20} {'milliseconds':<20} config.py")
print(f"{'Persistence Time Window':<40} {anomaly_detector._PERSISTENCE_WINDOW_MS/1000:<20} {'seconds':<20} (converted)")
print(f"{'Duplicate Suppression Cooldown':<40} {anomaly_detector._DUPLICATE_SUPPRESSION_SECONDS:<20} {'seconds':<20} config.py")
print(f"{'Duplicate Suppression Cooldown':<40} {anomaly_detector._DUPLICATE_SUPPRESSION_SECONDS/60:<20} {'minutes':<20} (converted)")

print("\n" + "=" * 100)
print("3. GEOFENCE ENGINE THRESHOLDS")
print("=" * 100)
print(f"{'Parameter':<40} {'Value':<20} {'Unit':<20} {'Source'}")
print("-" * 100)
print(f"{'Max Uncertain GPS Accuracy':<40} {geofence_engine.MAX_UNCERTAIN_GPS_ACCURACY_M:<20} {'metres':<20} geofence_engine.py")
print(f"{'Default Boundary Buffer':<40} {geofence_engine.DEFAULT_BOUNDARY_BUFFER_M:<20} {'metres':<20} geofence_engine.py")
print(f"{'Cooldown Duration':<40} {geofence_engine._COOLDOWN_SECONDS:<20} {'seconds':<20} geofence_engine.py")
print(f"{'Cooldown Duration':<40} {geofence_engine._COOLDOWN_SECONDS/60:<20} {'minutes':<20} (converted)")

print("\n" + "=" * 100)
print("4. CONFIGURED GEOFENCE ZONES")
print("=" * 100)
print(f"{'Zone Name':<30} {'Risk Level':<15} {'Radius (m)':<15} {'Center (lat, lng)'}")
print("-" * 100)

# Load zones from the actual data
zones_data = [
    {"name": "Mumbai Urban Core", "riskLevel": "MEDIUM", "radiusMeters": 15000.0, "centerLat": 19.0760, "centerLng": 72.8777},
    {"name": "Dharavi", "riskLevel": "HIGH", "radiusMeters": 2000.0, "centerLat": 19.0390, "centerLng": 72.8530},
    {"name": "Ratnagiri Coastal", "riskLevel": "HIGH", "radiusMeters": 10000.0, "centerLat": 16.9902, "centerLng": 73.3120},
    {"name": "Tadoba Tiger Reserve", "riskLevel": "RESTRICTED", "radiusMeters": 30000.0, "centerLat": 20.2280, "centerLng": 79.3950},
    {"name": "Pune Urban Core", "riskLevel": "MEDIUM", "radiusMeters": 12000.0, "centerLat": 18.5204, "centerLng": 73.8567},
]

for zone in zones_data:
    print(f"{zone['name']:<30} {zone['riskLevel']:<15} {zone['radiusMeters']:<15.1f} "
          f"({zone['centerLat']:.4f}, {zone['centerLng']:.4f})")

print("\n" + "=" * 100)
print("5. ISOLATION FOREST BASELINE PARAMETERS")
print("=" * 100)

# Load from evaluation comparison JSON
data_dir = backend_root / "data" / "synthetic"
iso_pred_file = data_dir / "isolation_forest_predictions.json"

if iso_pred_file.exists():
    with open(iso_pred_file, "r") as f:
        iso_data = json.load(f)
    
    config = iso_data.get("config", {})
    print(f"{'Parameter':<40} {'Value':<20} {'Source'}")
    print("-" * 100)
    print(f"{'Contamination':<40} {config.get('contamination', 'N/A'):<20} isolation_forest_baseline.py")
    print(f"{'Number of Estimators':<40} {config.get('n_estimators', 'N/A'):<20} isolation_forest_baseline.py")
    print(f"{'Max Samples':<40} {config.get('max_samples', 'N/A'):<20} isolation_forest_baseline.py")
    print(f"{'Random State':<40} {config.get('random_state', 'N/A'):<20} isolation_forest_baseline.py")
    print(f"{'Features Used':<40} {len(config.get('featuresExtracted', [])):<20} isolation_forest_baseline.py")
    print("\nFeatures Extracted:")
    for feat in config.get('featuresExtracted', []):
        print(f"  - {feat}")
else:
    print("Isolation Forest predictions file not found")
    print(f"Default values from isolation_forest_baseline.py:")
    print(f"{'Parameter':<40} {'Value':<20}")
    print("-" * 100)
    print(f"{'Contamination':<40} {'0.20':<20}")
    print(f"{'Number of Estimators':<40} {'100':<20}")
    print(f"{'Max Samples':<40} {'auto':<20}")
    print(f"{'Random State':<40} {'42':<20}")

print("\n" + "=" * 100)
print("6. SYNTHETIC DATA GENERATION PARAMETERS")
print("=" * 100)

scenario_config_file = data_dir / "scenario_config.json"
if scenario_config_file.exists():
    with open(scenario_config_file, "r") as f:
        scenario_config = json.load(f)
    
    print(f"{'Parameter':<40} {'Value':<20} {'Source'}")
    print("-" * 100)
    print(f"{'Random Seed':<40} {scenario_config.get('randomSeed', 'N/A'):<20} synthetic_generator.py")
    print(f"{'Tourist Count':<40} {scenario_config.get('touristCount', 'N/A'):<20} generated")
    print(f"{'Total Trajectory Points':<40} {scenario_config.get('touristCount', 'N/A'):<20} (see evaluation)")
    
    thresholds = scenario_config.get('detectorThresholds', {})
    print(f"\nDetector Thresholds (matching backend):")
    for key, val in thresholds.items():
        print(f"  {key}: {val}")
else:
    print("Scenario config file not found")

print("\n" + "=" * 100)
print("7. EVALUATION DATASET STATISTICS")
print("=" * 100)

eval_file = data_dir / "evaluation_comparison.json"
if eval_file.exists():
    with open(eval_file, "r") as f:
        eval_data = json.load(f)
    
    print(f"{'Metric':<40} {'Value':<20}")
    print("-" * 100)
    print(f"{'Total Trajectory Points':<40} {eval_data.get('totalTrajectoryPoints', 'N/A'):<20}")
    print(f"{'Total Labelled Points':<40} {eval_data.get('totalLabelledPoints', 'N/A'):<20}")
    print(f"{'Total Ground Truth Events':<40} {eval_data.get('totalGroundTruthEvents', 'N/A'):<20}")
    print(f"{'Total Trajectory Hours':<40} {eval_data.get('totalTrajectoryHours', 'N/A'):<20}")

print("\n" + "=" * 100)
