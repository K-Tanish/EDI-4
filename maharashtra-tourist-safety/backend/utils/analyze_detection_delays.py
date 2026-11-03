"""
Analyze detection delays for all configurations A-D
Reports mean, median, per-event breakdown
"""
import json
import sys
import statistics
from pathlib import Path

backend_root = Path(__file__).parent.parent
data_dir = backend_root / "data" / "synthetic"

# Load evaluation results
eval_file = data_dir / "evaluation_comparison.json"
with open(eval_file, "r") as f:
    eval_data = json.load(f)

print("=" * 100)
print("DETECTION DELAY ANALYSIS")
print("=" * 100)

for config_key, config_name in [
    ("configA", "A: Movement Rules Only"),
    ("configB", "B: Movement + Geospatial"),
    ("configC", "C: Full Pipeline (Refined)"),
    ("configD", "D: Isolation Forest")
]:
    config = eval_data["configurations"][config_key]
    
    if config.get("status") != "COMPLETED":
        print(f"\n{config_name}: UNAVAILABLE")
        continue
    
    event_metrics = config["eventMetrics"]
    per_event = event_metrics.get("perEventBreakdown", [])
    
    # Collect delays from detected events
    delays = []
    for event in per_event:
        if event["detected"] and event.get("detectionDelaySec") is not None:
            delays.append(event["detectionDelaySec"])
    
    print(f"\n{'=' * 100}")
    print(f"{config_name}")
    print(f"{'=' * 100}")
    
    if not delays:
        print("No detection delays (no events detected or all delays are None)")
        print(f"Detected events: {event_metrics['detectedEvents']}/{event_metrics['totalEvents']}")
        continue
    
    mean_delay = statistics.mean(delays)
    median_delay = statistics.median(delays)
    
    print(f"Detected Events: {event_metrics['detectedEvents']}/{event_metrics['totalEvents']}")
    print(f"Avg Detection Delay (Mean): {event_metrics.get('avgDetectionDelaySec', 'N/A')} seconds")
    print(f"Median Detection Delay: {median_delay:.2f} seconds")
    
    if len(delays) > 1:
        stdev = statistics.stdev(delays)
        print(f"Std Deviation: {stdev:.2f} seconds")
        print(f"Min Delay: {min(delays):.2f} seconds")
        print(f"Max Delay: {max(delays):.2f} seconds")
    
    print(f"\nPer-Event Breakdown:")
    print(f"{'Event ID':<45} {'Type':<25} {'Detected':<10} {'Delay (s)':<12}")
    print("-" * 100)
    
    for event in per_event:
        event_id = event["eventId"]
        event_type = event["anomalyType"]
        detected = "Yes" if event["detected"] else "No"
        delay = event.get("detectionDelaySec")
        delay_str = f"{delay:.2f}" if delay is not None else "N/A"
        
        print(f"{event_id:<45} {event_type:<25} {detected:<10} {delay_str:<12}")

print("\n" + "=" * 100)
print("SUMMARY COMPARISON")
print("=" * 100)
print(f"{'Configuration':<35} {'Events Detected':<18} {'Mean Delay (s)':<18} {'Median Delay (s)':<18}")
print("-" * 100)

for config_key, config_name in [
    ("configA", "A: Movement Rules Only"),
    ("configB", "B: Movement + Geospatial"),
    ("configC", "C: Full Pipeline (Refined)"),
    ("configD", "D: Isolation Forest")
]:
    config = eval_data["configurations"][config_key]
    
    if config.get("status") != "COMPLETED":
        print(f"{config_name:<35} {'N/A':<18} {'N/A':<18} {'N/A':<18}")
        continue
    
    event_metrics = config["eventMetrics"]
    per_event = event_metrics.get("perEventBreakdown", [])
    
    delays = [e["detectionDelaySec"] for e in per_event if e["detected"] and e.get("detectionDelaySec") is not None]
    
    detected_str = f"{event_metrics['detectedEvents']}/{event_metrics['totalEvents']}"
    mean_str = f"{statistics.mean(delays):.2f}" if delays else "N/A"
    median_str = f"{statistics.median(delays):.2f}" if delays else "N/A"
    
    print(f"{config_name:<35} {detected_str:<18} {mean_str:<18} {median_str:<18}")

print("\n" + "=" * 100)
