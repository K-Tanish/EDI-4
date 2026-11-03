"""
Evaluate Configuration B + Cooldown Only (no persistence)
This is the ablation to understand the impact of cooldown vs persistence separately
"""
import json
import sys
import time
import uuid
from pathlib import Path
from collections import defaultdict

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from workers.anomaly_detector import (
    _evaluate_raw_rules,
    reset_state,
    validate_point,
    _DUPLICATE_SUPPRESSION_SECONDS,
)
from utils.evaluate_pipeline import PipelineEvaluator

# Load data
data_dir = backend_root / "data" / "synthetic"
with open(data_dir / "trajectories.json", "r") as f:
    trajectories = json.load(f)

with open(data_dir / "ground_truth_labels.json", "r") as f:
    ground_truth = json.load(f)

print("=" * 100)
print("CONFIGURATION B + COOLDOWN ONLY (No Persistence)")
print("=" * 100)
print("This configuration applies:")
print("  - Movement rules (speed, inactivity, direction, route)")
print("  - Geofence hazard/restricted zone checks")
print("  - Cooldown suppression (5 min)")
print("  - NO temporal persistence requirement")
print()

# Implement B + Cooldown
def run_config_b_cooldown() -> list:
    """
    Configuration B + Cooldown: Movement + Geospatial + Cooldown, but NO persistence
    """
    reset_state()
    results = []
    
    # Cooldown tracking: (touristId, rule_name) -> last_alert_timestamp_s
    alert_cooldowns = {}
    
    # Group by tourist
    tourist_pts = defaultdict(list)
    for pt in trajectories:
        tourist_pts[pt["touristId"]].append(pt)
    
    for tid, pts in tourist_pts.items():
        reset_state(tid)
        sorted_pts = sorted(pts, key=lambda p: p["timestamp"])
        
        for pt in sorted_pts:
            is_valid, _ = validate_point(pt)
            if not is_valid:
                results.append({"touristId": tid, "timestamp": pt.get("timestamp", 0), "alert": None})
                continue
            
            # Generate raw candidates (movement + geospatial)
            raw_candidates = _evaluate_raw_rules(tid, pt)
            
            # Apply cooldown only (no persistence check)
            now_s = time.time()
            primary_alert = None
            
            if raw_candidates:
                # Take first candidate
                cand = raw_candidates[0]
                rule_name = cand.get("ruleName", cand.get("type", "UNKNOWN"))
                zone_id = cand.get("evidence", {}).get("details", {}).get("zoneId")
                rule_key = f"{rule_name}_{zone_id}" if zone_id else rule_name
                
                key = (tid, rule_key)
                last_alert_time = alert_cooldowns.get(key, 0.0)
                
                # Check cooldown
                if now_s - last_alert_time >= _DUPLICATE_SUPPRESSION_SECONDS:
                    # Emit alert
                    primary_alert = cand
                    alert_cooldowns[key] = now_s
                # else: suppressed by cooldown
            
            results.append({"touristId": tid, "timestamp": pt["timestamp"], "alert": primary_alert})
    
    return results

# Run the configuration
b_cooldown_predictions = run_config_b_cooldown()

# Evaluate using the standard evaluator
class SimpleEvaluator:
    """Minimal evaluator wrapper"""
    def __init__(self, trajectories, ground_truth):
        self.trajectories = trajectories
        self.ground_truth = ground_truth
        
        # Standard evaluator
        self.evaluator = PipelineEvaluator(trajectories, ground_truth)
    
    def evaluate(self, predictions):
        """Use existing evaluation logic"""
        return self.evaluator.evaluate_configuration(
            "B + Cooldown Only (No Persistence)",
            predictions
        )

evaluator = SimpleEvaluator(trajectories, ground_truth)
result = evaluator.evaluate(b_cooldown_predictions)

# Print results
print("=" * 100)
print("RESULTS")
print("=" * 100)

if result.get("status") == "COMPLETED":
    pm = result["pointMetrics"]
    em = result["eventMetrics"]
    om = result["operationalMetrics"]
    
    print("\nPOINT-LEVEL METRICS:")
    print(f"  Precision:       {pm['precision']:.4f}" if pm['precision'] is not None else "  Precision:       N/A")
    print(f"  Recall:          {pm['recall']:.4f}" if pm['recall'] is not None else "  Recall:          N/A")
    print(f"  F1-Score:        {pm['f1Score']:.4f}" if pm['f1Score'] is not None else "  F1-Score:        N/A")
    print(f"  FPR:             {pm['falsePositiveRate']:.4f}" if pm['falsePositiveRate'] is not None else "  FPR:             N/A")
    print(f"  TP / FP / FN:    {pm['truePositives']} / {pm['falsePositives']} / {pm['falseNegatives']}")
    
    print("\nEVENT-LEVEL METRICS:")
    print(f"  Precision:       {em['eventPrecision']:.4f}" if em['eventPrecision'] is not None else "  Precision:       N/A")
    print(f"  Recall:          {em['eventRecall']:.4f}" if em['eventRecall'] is not None else "  Recall:          N/A")
    print(f"  F1-Score:        {em['eventF1Score']:.4f}" if em['eventF1Score'] is not None else "  F1-Score:        N/A")
    print(f"  Detected:        {em['detectedEvents']}/{em['totalEvents']}")
    print(f"  Missed:          {em['missedEvents']}")
    print(f"  FP Events:       {em['falsePositiveEvents']}")
    print(f"  Avg Delay:       {em['avgDetectionDelaySec']:.2f} seconds" if em['avgDetectionDelaySec'] is not None else "  Avg Delay:       N/A")
    
    print("\nOPERATIONAL METRICS:")
    print(f"  Total Alerts:    {om['totalAlerts']}")
    print(f"  Alerts/Hour:     {om['alertsPerHour']:.2f}")
    
    print("\n" + "=" * 100)
    print("COMPARISON WITH OTHER CONFIGURATIONS")
    print("=" * 100)
    
    # Load original evaluation for comparison
    eval_file = data_dir / "evaluation_comparison.json"
    with open(eval_file, "r") as f:
        eval_data = json.load(f)
    
    print(f"{'Configuration':<35} {'Point F1':<12} {'Event F1':<12} {'Alerts':<10} {'Alerts/Hr':<12}")
    print("-" * 100)
    
    # B + Cooldown
    print(f"{'B + Cooldown Only (No Persist.)':<35} "
          f"{pm['f1Score'] if pm['f1Score'] is not None else 'N/A':<12} "
          f"{em['eventF1Score'] if em['eventF1Score'] is not None else 'N/A':<12} "
          f"{om['totalAlerts']:<10} "
          f"{om['alertsPerHour']:<12.2f}")
    
    # Original B
    config_b = eval_data["configurations"]["configB"]
    if config_b.get("status") == "COMPLETED":
        b_pm = config_b["pointMetrics"]
        b_em = config_b["eventMetrics"]
        b_om = config_b["operationalMetrics"]
        print(f"{'B: Movement + Geospatial (raw)':<35} "
              f"{b_pm['f1Score'] if b_pm['f1Score'] is not None else 'N/A':<12} "
              f"{b_em['eventF1Score'] if b_em['eventF1Score'] is not None else 'N/A':<12} "
              f"{b_om['totalAlerts']:<10} "
              f"{b_om['alertsPerHour']:<12.2f}")
    
    # Original C
    config_c = eval_data["configurations"]["configC"]
    if config_c.get("status") == "COMPLETED":
        c_pm = config_c["pointMetrics"]
        c_em = config_c["eventMetrics"]
        c_om = config_c["operationalMetrics"]
        print(f"{'C: Full Pipeline (Persist+Cool)':<35} "
              f"{c_pm['f1Score'] if c_pm['f1Score'] is not None else 'N/A':<12} "
              f"{c_em['eventF1Score'] if c_em['eventF1Score'] is not None else 'N/A':<12} "
              f"{c_om['totalAlerts']:<10} "
              f"{c_om['alertsPerHour']:<12.2f}")
    
    print("\n" + "=" * 100)
    print("KEY INSIGHTS")
    print("=" * 100)
    print("Comparing B (raw) vs B+Cooldown vs C (Persist+Cooldown):")
    print(f"  - B (raw) generated {b_om['totalAlerts']} alerts")
    print(f"  - B + Cooldown generated {om['totalAlerts']} alerts")
    print(f"  - C (Persist+Cooldown) generated {c_om['totalAlerts']} alerts")
    print()
    print(f"Alert reduction from cooldown alone: {b_om['totalAlerts']} → {om['totalAlerts']} "
          f"({(1 - om['totalAlerts']/b_om['totalAlerts'])*100:.1f}% reduction)")
    print(f"Alert reduction from persistence+cooldown: {b_om['totalAlerts']} → {c_om['totalAlerts']} "
          f"({(1 - c_om['totalAlerts']/b_om['totalAlerts'])*100:.1f}% reduction)")

print("\n" + "=" * 100)
