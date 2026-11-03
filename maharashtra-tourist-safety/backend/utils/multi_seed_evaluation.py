"""
Run evaluation over 20 random seeds and report statistics
"""
import json
import statistics
import sys
import tempfile
from pathlib import Path
from collections import defaultdict

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from utils.synthetic_generator import SyntheticTrajectoryGenerator
from utils.evaluate_pipeline import PipelineEvaluator

NUM_SEEDS = 20
SEEDS = range(42, 42 + NUM_SEEDS)

print("=" * 100)
print(f"MULTI-SEED EVALUATION ({NUM_SEEDS} seeds: {min(SEEDS)} to {max(SEEDS)})")
print("=" * 100)

# Storage for all runs
all_results = {
    "configA": defaultdict(list),
    "configB": defaultdict(list),
    "configC": defaultdict(list),
    "configD": defaultdict(list),
}

for seed_idx, seed in enumerate(SEEDS, 1):
    print(f"\n[{seed_idx}/{NUM_SEEDS}] Running seed {seed}...", end=" ", flush=True)
    
    # Generate dataset
    generator = SyntheticTrajectoryGenerator(seed=seed)
    dataset = generator.generate_dataset()
    
    trajectories = dataset["trajectories"]
    ground_truth = dataset["ground_truth"]
    
    # Run evaluation
    evaluator = PipelineEvaluator(trajectories, ground_truth)
    results = evaluator.run_all()
    
    # Extract metrics for each configuration
    for config_key in ["configA", "configB", "configC", "configD"]:
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
        
        # Operational metrics
        all_results[config_key]["total_alerts"].append(om["totalAlerts"])
        all_results[config_key]["alerts_per_hour"].append(om["alertsPerHour"])
        
        # Event counts
        all_results[config_key]["detected_events"].append(em["detectedEvents"])
        all_results[config_key]["missed_events"].append(em["missedEvents"])
        all_results[config_key]["fp_events"].append(em["falsePositiveEvents"])
    
    print("✓")

print("\n" + "=" * 100)
print("AGGREGATED RESULTS OVER 20 SEEDS")
print("=" * 100)

def format_stat(values, as_percent=False):
    """Format mean ± std"""
    if not values:
        return "N/A"
    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values) if len(values) > 1 else 0.0
    if as_percent:
        return f"{mean_val*100:.2f}% ± {std_val*100:.2f}%"
    return f"{mean_val:.4f} ± {std_val:.4f}"

def format_count(values):
    """Format mean ± std for counts"""
    if not values:
        return "N/A"
    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"{mean_val:.2f} ± {std_val:.2f}"

for config_key, config_name in [
    ("configA", "A: Movement Rules Only"),
    ("configB", "B: Movement + Geospatial"),
    ("configC", "C: Full Pipeline (Refined)"),
    ("configD", "D: Isolation Forest")
]:
    res = all_results[config_key]
    
    if not res["point_precision"]:
        print(f"\n{config_name}: UNAVAILABLE")
        continue
    
    print(f"\n{'=' * 100}")
    print(f"{config_name}")
    print(f"{'=' * 100}")
    
    print("\nPOINT-LEVEL METRICS:")
    print(f"  Precision:  {format_stat(res['point_precision'], as_percent=True)}")
    print(f"  Recall:     {format_stat(res['point_recall'], as_percent=True)}")
    print(f"  F1-Score:   {format_stat(res['point_f1'], as_percent=True)}")
    print(f"  FPR:        {format_stat(res['point_fpr'], as_percent=True)}")
    
    print("\nEVENT-LEVEL METRICS:")
    print(f"  Precision:  {format_stat(res['event_precision'], as_percent=True)}")
    print(f"  Recall:     {format_stat(res['event_recall'], as_percent=True)}")
    print(f"  F1-Score:   {format_stat(res['event_f1'], as_percent=True)}")
    print(f"  Detected:   {format_count(res['detected_events'])}")
    print(f"  Missed:     {format_count(res['missed_events'])}")
    print(f"  FP Events:  {format_count(res['fp_events'])}")
    
    print("\nOPERATIONAL METRICS:")
    print(f"  Total Alerts:      {format_count(res['total_alerts'])}")
    print(f"  Alerts per Hour:   {format_count(res['alerts_per_hour'])}")

print("\n" + "=" * 100)
print("SUMMARY TABLE")
print("=" * 100)
print(f"{'Config':<8} {'Point P':<18} {'Point R':<18} {'Point F1':<18} {'Event F1':<18} {'Alerts/Hr':<18}")
print("-" * 100)

for config_key, config_name in [
    ("configA", "Conf A"),
    ("configB", "Conf B"),
    ("configC", "Conf C"),
    ("configD", "Conf D")
]:
    res = all_results[config_key]
    
    if not res["point_precision"]:
        continue
    
    p_p = format_stat(res['point_precision'])
    p_r = format_stat(res['point_recall'])
    p_f1 = format_stat(res['point_f1'])
    e_f1 = format_stat(res['event_f1'])
    alerts = format_count(res['alerts_per_hour'])
    
    print(f"{config_name:<8} {p_p:<18} {p_r:<18} {p_f1:<18} {e_f1:<18} {alerts:<18}")

print("\n" + "=" * 100)
