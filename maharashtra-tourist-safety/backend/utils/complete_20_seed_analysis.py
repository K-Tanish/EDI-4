"""
Complete 20-seed evaluation for configs A, B, C, D, and B+cooldown
Reports all requested metrics with exact values
"""
import json
import statistics
import sys
import time
from pathlib import Path
from collections import defaultdict, Counter

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from utils.synthetic_generator import SyntheticTrajectoryGenerator
from utils.evaluate_pipeline import PipelineEvaluator
from workers.anomaly_detector import (
    _evaluate_raw_rules,
    reset_state,
    validate_point,
    _DUPLICATE_SUPPRESSION_SECONDS,
)

NUM_SEEDS = 20
SEEDS = range(42, 42 + NUM_SEEDS)

print("=" * 120)
print(f"COMPLETE 20-SEED EVALUATION (seeds {min(SEEDS)} to {max(SEEDS)})")
print("=" * 120)

# Storage for all runs
all_results = {
    "configA": defaultdict(list),
    "configB": defaultdict(list),
    "configC": defaultdict(list),
    "configD": defaultdict(list),
    "configBCooldown": defaultdict(list),
}

# Track which events C misses per seed
config_c_missed_events = defaultdict(lambda: defaultdict(int))

# Track seed changes
seed_analysis = {
    "tourist_ids": [],
    "total_points": [],
    "event_types": [],
    "event_positions": [],
}

for seed_idx, seed in enumerate(SEEDS, 1):
    print(f"[{seed_idx}/{NUM_SEEDS}] Processing seed {seed}...", flush=True)
    
    # Generate dataset
    generator = SyntheticTrajectoryGenerator(seed=seed)
    dataset = generator.generate_dataset()
    
    trajectories = dataset["trajectories"]
    ground_truth = dataset["ground_truth"]
    
    # Track what changes with seed
    tourist_ids = sorted(list(set(p["touristId"] for p in trajectories)))
    seed_analysis["tourist_ids"].append(str(tourist_ids))
    seed_analysis["total_points"].append(len(trajectories))
    
    event_types = sorted([e["anomalyType"] for e in ground_truth["scenarioEventSummaries"]])
    seed_analysis["event_types"].append(str(event_types))
    
    # Track event positions (first timestamp of each event type)
    event_positions = {}
    for event in ground_truth["scenarioEventSummaries"]:
        etype = event["anomalyType"]
        tid = event["touristId"]
        # Get first relevant timestamp
        if etype == "PROLONGED_INACTIVITY":
            ts = event.get("stationaryStartTime", 0)
        elif etype == "ABNORMAL_SPEED":
            pts = event.get("anomalyPoints", [])
            ts = pts[0]["timestamp"] if pts else 0
        elif etype == "RESTRICTED_ZONE_ENTRY":
            ts = event.get("crossingTimestamp", 0)
        elif etype == "SOS_EVENT":
            ts = event.get("triggerTimestamp", 0)
        elif etype == "MISSING_GPS_OBSERVATION":
            ts = event.get("gapStartTimestamp", 0)
        elif etype == "GPS_BOUNDARY_NOISE":
            ts = 0  # No specific start
        else:
            ts = 0
        event_positions[f"{etype}_{tid}"] = ts
    seed_analysis["event_positions"].append(str(event_positions))
    
    # Run standard evaluation (A, B, C, D)
    evaluator = PipelineEvaluator(trajectories, ground_truth)
    results = evaluator.run_all()
    
    # Run B+Cooldown configuration
    def run_config_b_cooldown(trajectories):
        reset_state()
        results = []
        alert_cooldowns = {}
        
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
                
                raw_candidates = _evaluate_raw_rules(tid, pt)
                now_s = time.time()
                primary_alert = None
                
                if raw_candidates:
                    cand = raw_candidates[0]
                    rule_name = cand.get("ruleName", cand.get("type", "UNKNOWN"))
                    zone_id = cand.get("evidence", {}).get("details", {}).get("zoneId")
                    rule_key = f"{rule_name}_{zone_id}" if zone_id else rule_name
                    
                    key = (tid, rule_key)
                    last_alert_time = alert_cooldowns.get(key, 0.0)
                    
                    if now_s - last_alert_time >= _DUPLICATE_SUPPRESSION_SECONDS:
                        primary_alert = cand
                        alert_cooldowns[key] = now_s
                
                results.append({"touristId": tid, "timestamp": pt["timestamp"], "alert": primary_alert})
        
        return results
    
    b_cooldown_predictions = run_config_b_cooldown(trajectories)
    b_cooldown_result = evaluator.evaluate_configuration(
        "B + Cooldown Only",
        b_cooldown_predictions
    )
    
    # Extract metrics for each configuration
    for config_key, config_name in [
        ("configA", "A"),
        ("configB", "B"),
        ("configC", "C"),
        ("configD", "D"),
    ]:
        config = results["configurations"][config_key]
        
        if config.get("status") != "COMPLETED":
            continue
        
        pm = config["pointMetrics"]
        em = config["eventMetrics"]
        om = config["operationalMetrics"]
        
        # Point-level metrics
        all_results[config_key]["point_precision"].append(pm["precision"] if pm["precision"] is not None else 0.0)
        all_results[config_key]["point_recall"].append(pm["recall"] if pm["recall"] is not None else 0.0)
        all_results[config_key]["point_f1"].append(pm["f1Score"] if pm["f1Score"] is not None else 0.0)
        all_results[config_key]["point_fpr"].append(pm["falsePositiveRate"] if pm["falsePositiveRate"] is not None else 0.0)
        
        # Event-level metrics
        all_results[config_key]["event_precision"].append(em["eventPrecision"] if em["eventPrecision"] is not None else 0.0)
        all_results[config_key]["event_recall"].append(em["eventRecall"] if em["eventRecall"] is not None else 0.0)
        all_results[config_key]["event_f1"].append(em["eventF1Score"] if em["eventF1Score"] is not None else 0.0)
        
        # Alert count
        all_results[config_key]["total_alerts"].append(om["totalAlerts"])
        
        # Detection delay
        per_event = em.get("perEventBreakdown", [])
        delays = [e["detectionDelaySec"] for e in per_event if e["detected"] and e.get("detectionDelaySec") is not None]
        
        if delays:
            all_results[config_key]["delay_mean"].append(statistics.mean(delays))
            all_results[config_key]["delay_median"].append(statistics.median(delays))
        else:
            all_results[config_key]["delay_mean"].append(None)
            all_results[config_key]["delay_median"].append(None)
        
        # Events detected
        all_results[config_key]["events_detected"].append(em["detectedEvents"])
        
        # Track which events C misses
        if config_key == "configC":
            for event in per_event:
                if not event["detected"]:
                    event_id = event["eventId"]
                    event_type = event["anomalyType"]
                    config_c_missed_events[event_type][event_id] += 1
    
    # B+Cooldown metrics
    if b_cooldown_result.get("status") == "COMPLETED":
        pm = b_cooldown_result["pointMetrics"]
        em = b_cooldown_result["eventMetrics"]
        om = b_cooldown_result["operationalMetrics"]
        
        all_results["configBCooldown"]["point_precision"].append(pm["precision"] if pm["precision"] is not None else 0.0)
        all_results["configBCooldown"]["point_recall"].append(pm["recall"] if pm["recall"] is not None else 0.0)
        all_results["configBCooldown"]["point_f1"].append(pm["f1Score"] if pm["f1Score"] is not None else 0.0)
        all_results["configBCooldown"]["point_fpr"].append(pm["falsePositiveRate"] if pm["falsePositiveRate"] is not None else 0.0)
        
        all_results["configBCooldown"]["event_precision"].append(em["eventPrecision"] if em["eventPrecision"] is not None else 0.0)
        all_results["configBCooldown"]["event_recall"].append(em["eventRecall"] if em["eventRecall"] is not None else 0.0)
        all_results["configBCooldown"]["event_f1"].append(em["eventF1Score"] if em["eventF1Score"] is not None else 0.0)
        
        all_results["configBCooldown"]["total_alerts"].append(om["totalAlerts"])
        
        per_event = em.get("perEventBreakdown", [])
        delays = [e["detectionDelaySec"] for e in per_event if e["detected"] and e.get("detectionDelaySec") is not None]
        
        if delays:
            all_results["configBCooldown"]["delay_mean"].append(statistics.mean(delays))
            all_results["configBCooldown"]["delay_median"].append(statistics.median(delays))
        else:
            all_results["configBCooldown"]["delay_mean"].append(None)
            all_results["configBCooldown"]["delay_median"].append(None)
        
        all_results["configBCooldown"]["events_detected"].append(em["detectedEvents"])

print("\n" + "=" * 120)
print("RESULTS TABLE")
print("=" * 120)

def format_stat(values, decimal=4):
    """Format mean ± std"""
    if not values or all(v is None for v in values):
        return "N/A"
    clean_values = [v for v in values if v is not None]
    if not clean_values:
        return "N/A"
    mean_val = statistics.mean(clean_values)
    std_val = statistics.stdev(clean_values) if len(clean_values) > 1 else 0.0
    return f"{mean_val:.{decimal}f} ± {std_val:.{decimal}f}"

def format_count(values):
    """Format mean ± std for integer counts"""
    if not values:
        return "N/A"
    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"{mean_val:.2f} ± {std_val:.2f}"

# Generate markdown table
print("\n### Complete Metrics Table (20 seeds: 42-61)\n")
print("| Config | Event Precision | Event Recall | Event F1 | Point Precision | Point Recall | Point F1 | Point FPR | Alert Count | Delay Mean (s) | Delay Median (s) | Events Detected |")
print("|--------|----------------|--------------|----------|----------------|--------------|----------|-----------|-------------|----------------|------------------|-----------------|")

for config_key, config_name in [
    ("configA", "A: Movement Only"),
    ("configB", "B: Movement + Geospatial"),
    ("configC", "C: Full Pipeline"),
    ("configD", "D: Isolation Forest"),
    ("configBCooldown", "B + Cooldown Only"),
]:
    res = all_results[config_key]
    
    if not res["point_precision"]:
        print(f"| {config_name} | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |")
        continue
    
    event_p = format_stat(res['event_precision'])
    event_r = format_stat(res['event_recall'])
    event_f1 = format_stat(res['event_f1'])
    
    point_p = format_stat(res['point_precision'])
    point_r = format_stat(res['point_recall'])
    point_f1 = format_stat(res['point_f1'])
    point_fpr = format_stat(res['point_fpr'])
    
    alerts = format_count(res['total_alerts'])
    
    delay_mean = format_stat(res['delay_mean'], 2)
    delay_median = format_stat(res['delay_median'], 2)
    
    events_det = format_count(res['events_detected'])
    
    print(f"| {config_name} | {event_p} | {event_r} | {event_f1} | {point_p} | {point_r} | {point_f1} | {point_fpr} | {alerts} | {delay_mean} | {delay_median} | {events_det} |")

print("\n" + "=" * 120)
print("CONFIG C MISSED EVENTS ANALYSIS")
print("=" * 120)

print("\n### Events Missed by Config C Across 20 Seeds\n")
print("| Event Type | Event ID | Times Missed (out of 20) |")
print("|------------|----------|--------------------------|")

for event_type, event_ids in sorted(config_c_missed_events.items()):
    for event_id, count in sorted(event_ids.items()):
        print(f"| {event_type} | {event_id} | {count}/20 |")

if not config_c_missed_events:
    print("| (none) | - | 0/20 |")

print("\n" + "=" * 120)
print("SEED VARIATION ANALYSIS")
print("=" * 120)

# Check what changes across seeds
tourist_ids_unique = set(seed_analysis["tourist_ids"])
total_points_unique = set(seed_analysis["total_points"])
event_types_unique = set(seed_analysis["event_types"])
event_positions_unique = set(seed_analysis["event_positions"])

print(f"\nTourist IDs variation: {len(tourist_ids_unique)} unique patterns")
print(f"  Same across all seeds: {len(tourist_ids_unique) == 1}")
if len(tourist_ids_unique) == 1:
    print(f"  Value: {list(tourist_ids_unique)[0]}")

print(f"\nTotal points variation: {len(total_points_unique)} unique values")
print(f"  Same across all seeds: {len(total_points_unique) == 1}")
if len(total_points_unique) == 1:
    print(f"  Value: {list(total_points_unique)[0]}")
else:
    print(f"  Range: {min(seed_analysis['total_points'])} to {max(seed_analysis['total_points'])}")

print(f"\nEvent types variation: {len(event_types_unique)} unique patterns")
print(f"  Same across all seeds: {len(event_types_unique) == 1}")
if len(event_types_unique) == 1:
    print(f"  Value: {list(event_types_unique)[0]}")

print(f"\nEvent positions variation: {len(event_positions_unique)} unique patterns")
print(f"  Same across all seeds: {len(event_positions_unique) == 1}")

print("\n### Seed Changes Summary\n")
print("| Aspect | Changes Across Seeds |")
print("|--------|---------------------|")
print(f"| Tourist IDs | {'No - same 8 tourists' if len(tourist_ids_unique) == 1 else 'Yes - varies'} |")
print(f"| Total Points | {'No - always ' + str(list(total_points_unique)[0]) if len(total_points_unique) == 1 else 'Yes - varies'} |")
print(f"| Event Types | {'No - same 6 event types' if len(event_types_unique) == 1 else 'Yes - varies'} |")
print(f"| Event Positions | {'No - deterministic placement' if len(event_positions_unique) == 1 else 'Yes - timing varies'} |")

print("\nConclusion:")
if len(event_positions_unique) == 1:
    print("  → Seed changes GPS NOISE only (coordinates jitter)")
    print("  → Event placement, timing, and structure are DETERMINISTIC")
else:
    print("  → Seed changes event timing and/or placement")

print("\n" + "=" * 120)
