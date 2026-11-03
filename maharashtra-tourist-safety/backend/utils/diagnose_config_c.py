"""
Diagnostic script to understand why Config C detects only ~5 of 82 anomalous points
and few SOS-labelled points.

Analyzes:
1. Candidate generation vs final alert emission
2. Persistence filtering behavior
3. Cooldown suppression patterns
4. SOS handling path
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

# Add backend to path
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from workers.anomaly_detector import (
    _evaluate_raw_rules,
    _analyse_all,
    reset_state,
    get_candidate_status,
    get_cooldown_status,
    _PERSISTENCE_MIN_CONSECUTIVE,
    _PERSISTENCE_WINDOW_MS,
    _DUPLICATE_SUPPRESSION_SECONDS,
)

# Load data
data_dir = backend_root / "data" / "synthetic"
with open(data_dir / "trajectories.json", "r") as f:
    trajectories = json.load(f)

with open(data_dir / "ground_truth_labels.json", "r") as f:
    ground_truth = json.load(f)

# Build ground truth map
gt_map = {}
for pt in ground_truth.get("pointLabels", []):
    gt_map[(pt["touristId"], pt["timestamp"])] = pt

# Group by tourist
tourist_groups = defaultdict(list)
for pt in trajectories:
    tourist_groups[pt["touristId"]].append(pt)

# Diagnostic counters
stats = {
    "total_points": 0,
    "anomalous_ground_truth": 0,
    "raw_candidates_generated": 0,
    "persistence_filtered": 0,
    "cooldown_suppressed": 0,
    "final_alerts_emitted": 0,
    "sos_labeled_points": 0,
    "sos_alerts_emitted": 0,
    "sos_bypassed_successfully": 0,
}

# Per-tourist detailed tracking
tourist_diagnostics = {}

# Per-rule tracking
rule_stats = defaultdict(lambda: {
    "candidates_generated": 0,
    "persistence_pending": 0,
    "persistence_confirmed": 0,
    "cooldown_suppressed": 0,
    "emitted": 0
})

print("=" * 80)
print("CONFIG C DETECTION DIAGNOSTIC")
print("=" * 80)
print(f"\nPersistence Settings:")
print(f"  MIN_CONSECUTIVE: {_PERSISTENCE_MIN_CONSECUTIVE}")
print(f"  WINDOW_MS: {_PERSISTENCE_WINDOW_MS}")
print(f"  COOLDOWN_SECONDS: {_DUPLICATE_SUPPRESSION_SECONDS}")
print()

for tid, points in tourist_groups.items():
    reset_state(tid)
    sorted_pts = sorted(points, key=lambda p: p["timestamp"])
    
    tourist_diag = {
        "points": len(sorted_pts),
        "anomalous_gt": 0,
        "raw_candidates": 0,
        "final_alerts": 0,
        "sos_points": 0,
        "sos_alerts": 0,
        "detailed_trace": []
    }
    
    for pt in sorted_pts:
        stats["total_points"] += 1
        key = (tid, pt["timestamp"])
        gt = gt_map.get(key)
        
        is_anomalous_gt = gt and gt.get("isAnomaly", False)
        is_sos = pt.get("type") == "SOS" or pt.get("isSos") or (gt and gt.get("groundTruthType") in ("SOS_TRIGGERED", "SOS_ACTIVE"))
        
        if is_anomalous_gt:
            stats["anomalous_ground_truth"] += 1
            tourist_diag["anomalous_gt"] += 1
        
        if is_sos:
            stats["sos_labeled_points"] += 1
            tourist_diag["sos_points"] += 1
        
        # Check raw candidates
        from workers.anomaly_detector import validate_point
        is_valid, _ = validate_point(pt)
        
        if not is_valid:
            continue
            
        raw_candidates = _evaluate_raw_rules(tid, pt)
        
        if raw_candidates:
            stats["raw_candidates_generated"] += len(raw_candidates)
            tourist_diag["raw_candidates"] += len(raw_candidates)
            
            for cand in raw_candidates:
                rule_name = cand.get("ruleName", cand.get("type", "UNKNOWN"))
                rule_stats[rule_name]["candidates_generated"] += 1
        
        # Check final alerts
        final_alerts = _analyse_all(tid, pt)
        
        if final_alerts:
            stats["final_alerts_emitted"] += len(final_alerts)
            tourist_diag["final_alerts"] += len(final_alerts)
            
            for alert in final_alerts:
                rule_name = alert.get("ruleName", alert.get("type", "UNKNOWN"))
                rule_stats[rule_name]["emitted"] += 1
                
                if "SOS" in rule_name or alert.get("type") == "SOS":
                    stats["sos_alerts_emitted"] += 1
                    tourist_diag["sos_alerts"] += 1
        
        # Calculate filtering
        if raw_candidates and not final_alerts:
            # Check if persistence filtering or cooldown
            for cand in raw_candidates:
                rule_name = cand.get("ruleName", cand.get("type", "UNKNOWN"))
                zone_id = cand.get("evidence", {}).get("details", {}).get("zoneId")
                rule_key = f"{rule_name}_{zone_id}" if zone_id else rule_name
                
                cand_status = get_candidate_status(tid, rule_key)
                cooldown_status = get_cooldown_status(tid, rule_key)
                
                if cand_status:
                    count = cand_status.get("count", 0)
                    duration_ms = pt["timestamp"] - cand_status.get("first_seen_ms", pt["timestamp"])
                    
                    is_persistent = (
                        rule_name in ("PROLONGED_INACTIVITY", "STATIONARY")
                        or count >= _PERSISTENCE_MIN_CONSECUTIVE
                        or duration_ms >= _PERSISTENCE_WINDOW_MS
                    )
                    
                    if not is_persistent:
                        rule_stats[rule_name]["persistence_pending"] += 1
                    else:
                        rule_stats[rule_name]["persistence_confirmed"] += 1
                        if cooldown_status.get("inCooldown"):
                            stats["cooldown_suppressed"] += 1
                            rule_stats[rule_name]["cooldown_suppressed"] += 1
        
        # Detailed trace for anomalous points
        if is_anomalous_gt or is_sos:
            trace_entry = {
                "timestamp": pt["timestamp"],
                "gt_type": gt.get("groundTruthType") if gt else "UNKNOWN",
                "is_sos": is_sos,
                "raw_candidates": len(raw_candidates),
                "final_alerts": len(final_alerts),
                "rules_generated": [c.get("ruleName") for c in raw_candidates],
                "rules_emitted": [a.get("ruleName") for a in final_alerts],
            }
            tourist_diag["detailed_trace"].append(trace_entry)
    
    tourist_diagnostics[tid] = tourist_diag
    
    # Reset state for next tourist
    reset_state(tid)

# Calculate filtered counts
stats["persistence_filtered"] = stats["raw_candidates_generated"] - stats["final_alerts_emitted"] - stats["cooldown_suppressed"]

print("\n" + "=" * 80)
print("OVERALL STATISTICS")
print("=" * 80)
print(f"Total points processed: {stats['total_points']}")
print(f"Anomalous ground truth points: {stats['anomalous_ground_truth']}")
print(f"SOS-labeled points: {stats['sos_labeled_points']}")
print()
print(f"Raw candidates generated: {stats['raw_candidates_generated']}")
print(f"Final alerts emitted: {stats['final_alerts_emitted']}")
print(f"  → Persistence filtered: {stats['persistence_filtered']}")
print(f"  → Cooldown suppressed: {stats['cooldown_suppressed']}")
print()
print(f"SOS alerts emitted: {stats['sos_alerts_emitted']} / {stats['sos_labeled_points']} SOS-labeled points")
print()
print(f"Detection rate: {stats['final_alerts_emitted']}/{stats['anomalous_ground_truth']} = {stats['final_alerts_emitted']/stats['anomalous_ground_truth']*100:.1f}%")

print("\n" + "=" * 80)
print("PER-RULE BREAKDOWN")
print("=" * 80)
print(f"{'Rule':<30} {'Raw':<8} {'Pend':<8} {'Conf':<8} {'Cool':<8} {'Emit':<8}")
print("-" * 80)
for rule_name, rule_stat in sorted(rule_stats.items()):
    print(f"{rule_name:<30} "
          f"{rule_stat['candidates_generated']:<8} "
          f"{rule_stat['persistence_pending']:<8} "
          f"{rule_stat['persistence_confirmed']:<8} "
          f"{rule_stat['cooldown_suppressed']:<8} "
          f"{rule_stat['emitted']:<8}")

print("\n" + "=" * 80)
print("PER-TOURIST SUMMARY")
print("=" * 80)
for tid, diag in sorted(tourist_diagnostics.items()):
    print(f"\n{tid}:")
    print(f"  Points: {diag['points']}")
    print(f"  Anomalous GT: {diag['anomalous_gt']}")
    print(f"  Raw candidates: {diag['raw_candidates']}")
    print(f"  Final alerts: {diag['final_alerts']}")
    print(f"  SOS points: {diag['sos_points']} → SOS alerts: {diag['sos_alerts']}")
    
    if diag['anomalous_gt'] > 0 and len(diag['detailed_trace']) <= 20:
        print(f"  Detailed trace:")
        for trace in diag['detailed_trace']:
            print(f"    {trace['gt_type']:<25} Raw:{trace['raw_candidates']} Final:{trace['final_alerts']} "
                  f"Rules:{','.join(trace['rules_generated'][:2]) if trace['rules_generated'] else 'none'}")

print("\n" + "=" * 80)
print("KEY FINDINGS")
print("=" * 80)
print(f"1. Persistence filtering removes {stats['persistence_filtered']} candidates")
print(f"2. Cooldown suppresses {stats['cooldown_suppressed']} alerts")
print(f"3. SOS detection: {stats['sos_alerts_emitted']}/{stats['sos_labeled_points']} points")
print(f"4. Overall detection rate: {stats['final_alerts_emitted']/stats['anomalous_ground_truth']*100:.1f}%")
