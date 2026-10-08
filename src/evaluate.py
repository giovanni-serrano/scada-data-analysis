"""Blind evaluation of the alarm rule over many simulated years.

Calibration seeds choose the operating point; evaluation seeds measure it once.
The detector never receives the event list: scoring happens afterwards.
"""
import numpy as np
import pandas as pd

from .alarms import DEADBAND, NO_DEADBAND, alarm_kpis, annunciate, episodes
from .analyze_scada import apply_reference, derive, event_windows
from .generate_synthetic_scada import selected_measurements, simulate

CALIBRATION_SEEDS = list(range(1000, 1020))
EVALUATION_SEEDS = list(range(2000, 2100))
PERCENTILES = [95, 99, 99.5]
ON_DELAYS = [2, 3, 4]
METHODS = ["load_ambient", "load", "none"]
PRIMARY, BASELINE = "load_ambient", "none"
# Declared before looking at any result: best detection within this false-alarm budget.
MAX_FALSE_ALARMS_PER_1000H = 1.0
BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED = 2000, 20250101
SEVERITY_BINS = [.15, .35, .55, .75, 1.0]


def score(state, eligible, times, truth):
    """Compare one alarm state series with the ground truth of one simulated year."""
    reference_end = pd.Timestamp(truth["reference_end_exclusive"])
    normal = (times >= reference_end).to_numpy().copy()
    events = []
    for start, trip, restart, event in event_windows(truth):
        ramp = ((times >= start) & (times < trip)).to_numpy()
        normal &= ~((times >= start) & (times < restart)).to_numpy()
        active = times[ramp & state]
        lead = float((trip - active.iloc[0]).total_seconds() / 3600) if len(active) else None
        events.append({"severity": event["severity"], "ramp_hours": event["ramp_hours"],
                       "detected": lead is not None, "lead_hours": lead})
    # A false alarm is an activation that starts outside every ramp and trip stop.
    inside = set(times[normal])
    false_alarms = sum(episode["start"] in inside for episode in episodes(state, times))
    return {"events": events, "false_alarms": false_alarms, "normal_hours": int((normal & eligible).sum()),
            "normal_alarm_hours": int((normal & state).sum())}


def evaluate_seed(seed, percentiles=PERCENTILES, on_delays=ON_DELAYS, methods=METHODS):
    """All detector configurations for one simulated year: {(method, percentile, on_delay): score}."""
    frame, truth = simulate(seed)
    derived = derive(selected_measurements(frame))
    cutoff = pd.Timestamp(truth["reference_end_exclusive"])
    results = {}
    for method in methods:
        for percentile in percentiles:
            thresholds, _ = apply_reference(derived, cutoff, percentile=percentile, conditioning=method)
            for on_delay in on_delays:
                out = annunciate(thresholds, on_delay=on_delay, deadband=DEADBAND)
                eligible = out.eligible.to_numpy()
                results[(method, percentile, on_delay)] = {
                    "high": score(out.alarm_high.to_numpy(), eligible, out.t, truth),
                    "any": score((out.priority > 0).to_numpy(), eligible, out.t, truth)}
    return results


def aggregate(per_seed):
    """Point estimates from a list of per-year scores."""
    events = [event for year in per_seed for event in year["events"]]
    leads = [event["lead_hours"] for event in events if event["detected"]]
    hours = sum(year["normal_hours"] for year in per_seed)
    return {
        "events": len(events), "detected": len(leads),
        "detection_rate": len(leads) / len(events) if events else None,
        "false_alarms": sum(year["false_alarms"] for year in per_seed), "normal_hours": hours,
        "false_alarms_per_1000h": 1000 * sum(year["false_alarms"] for year in per_seed) / hours if hours else None,
        "normal_time_in_alarm_pct": 100 * sum(year["normal_alarm_hours"] for year in per_seed) / hours if hours else None,
        "lead_hours_median": float(np.median(leads)) if leads else None,
        "lead_hours_p10": round(float(np.percentile(leads, 10)), 2) if leads else None,
        "lead_hours_p90": round(float(np.percentile(leads, 90)), 2) if leads else None,
    }


def bootstrap(per_seed, other=None, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """95 % intervals by resampling whole years, so events of one year stay together.

    With `other`, the same resampled years are used for both detectors and the
    interval is for the paired difference (per_seed minus other).
    """
    rng = np.random.default_rng(seed)
    keys = ["detection_rate", "false_alarms_per_1000h", "lead_hours_median"]
    draws = {key: [] for key in keys}
    for _ in range(resamples):
        pick = rng.integers(0, len(per_seed), len(per_seed))
        sample = aggregate([per_seed[i] for i in pick])
        reference = aggregate([other[i] for i in pick]) if other is not None else None
        for key in keys:
            value = sample[key]
            if reference is not None and value is not None and reference[key] is not None:
                value -= reference[key]
            elif reference is not None:
                value = None
            if value is not None:
                draws[key].append(value)
    return {key: [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))] if values else None
            for key, values in draws.items()}


def by_severity(per_seed):
    events = [event for year in per_seed for event in year["events"]]
    rows = []
    for low, high in zip(SEVERITY_BINS[:-1], SEVERITY_BINS[1:]):
        inside = [e for e in events if low <= e["severity"] < high or (high == SEVERITY_BINS[-1] and e["severity"] == high)]
        rows.append({"severity_from": low, "severity_to": high, "events": len(inside),
                     "detected": sum(e["detected"] for e in inside),
                     "detection_rate": sum(e["detected"] for e in inside) / len(inside) if inside else None})
    return rows


def choose_operating_point(calibration, method=PRIMARY, budget=MAX_FALSE_ALARMS_PER_1000H):
    """Highest calibration detection within the false-alarm budget; ties go to the longer lead."""
    candidates = []
    for (name, percentile, on_delay), per_seed in calibration.items():
        if name != method:
            continue
        stats = aggregate(per_seed)
        if stats["false_alarms_per_1000h"] <= budget:
            candidates.append((stats["detection_rate"], stats["lead_hours_median"] or 0, percentile, on_delay))
    if not candidates:
        raise ValueError("No configuration meets the false-alarm budget on the calibration seeds.")
    _, _, percentile, on_delay = max(candidates)
    return percentile, on_delay


def alarm_review(seeds, percentile, on_delay, method=PRIMARY):
    """Alarm counts after the reference period, summed over years, with and without deadband."""
    totals = {}
    for seed in seeds:
        frame, truth = simulate(seed)
        cutoff = pd.Timestamp(truth["reference_end_exclusive"])
        thresholds, _ = apply_reference(derive(selected_measurements(frame)), cutoff, percentile=percentile, conditioning=method)
        for label, deadband in [("with_deadband", DEADBAND), ("without_deadband", NO_DEADBAND)]:
            out = annunciate(thresholds, on_delay=on_delay, deadband=deadband)
            kpis = alarm_kpis(out, out.t >= cutoff)
            total = totals.setdefault(label, {"eligible_hours": 0, "points": {}})
            total["eligible_hours"] += kpis["eligible_hours"]
            for point in kpis["points"]:
                entry = total["points"].setdefault(point["tag"], {"tag": point["tag"], "priority": point["priority"],
                                                                 "activations": 0, "fleeting": 0, "stale": 0, "repeats": 0})
                for key in ("activations", "fleeting", "stale", "repeats"):
                    entry[key] += point[key]
    for total in totals.values():
        total["points"] = list(total["points"].values())
        for key in ("activations", "fleeting", "stale", "repeats"):
            total[key] = sum(point[key] for point in total["points"])
        total["activations_per_hour"] = total["activations"] / total["eligible_hours"]
        total["high_priority_share"] = (sum(point["activations"] for point in total["points"] if point["priority"] == "alta")
                                        / total["activations"]) if total["activations"] else None
    return totals


def evaluate(calibration_seeds=CALIBRATION_SEEDS, evaluation_seeds=EVALUATION_SEEDS, resamples=BOOTSTRAP_RESAMPLES, progress=None):
    calibration_seeds, evaluation_seeds = list(calibration_seeds), list(evaluation_seeds)
    if set(calibration_seeds) & set(evaluation_seeds):
        raise ValueError("Calibration and evaluation seeds must not overlap.")
    per_priority = {"calibration": {}, "evaluation": {}}
    for label, seeds in [("calibration", calibration_seeds), ("evaluation", evaluation_seeds)]:
        for seed in seeds:
            if progress:
                progress(label, seed)
            for key, value in evaluate_seed(seed).items():
                for priority in ("high", "any"):
                    per_priority[label].setdefault(priority, {}).setdefault(key, []).append(value[priority])
    calibration, held_out = per_priority["calibration"]["high"], per_priority["evaluation"]["high"]
    percentile, on_delay = choose_operating_point(calibration)

    def row(table, method, p, delay, with_interval=True):
        per_seed = table[(method, p, delay)]
        entry = {"method": method, "percentile": p, "on_delay_hours": delay, **aggregate(per_seed)}
        if with_interval:
            entry["ci95"] = bootstrap(per_seed, resamples=resamples)
        return entry

    methods = {method: row(held_out, method, percentile, on_delay) for method in METHODS}
    for method in METHODS:
        methods[method]["by_severity"] = by_severity(held_out[(method, percentile, on_delay)])
    primary, baseline = held_out[(PRIMARY, percentile, on_delay)], held_out[(BASELINE, percentile, on_delay)]
    difference = {key: (methods[PRIMARY][key] - methods[BASELINE][key]
                        if methods[PRIMARY][key] is not None and methods[BASELINE][key] is not None else None)
                  for key in ("detection_rate", "false_alarms_per_1000h", "lead_hours_median")}
    difference["ci95"] = bootstrap(primary, other=baseline, resamples=resamples)
    leads = [e["lead_hours"] for year in primary for e in year["events"] if e["detected"]]
    return {
        "synthetic_only": True,
        "protocol": {
            "calibration_seeds": calibration_seeds, "evaluation_seeds": evaluation_seeds,
            "selection_rule": "highest detection rate on calibration seeds within the false-alarm budget",
            "false_alarm_budget_per_1000h": MAX_FALSE_ALARMS_PER_1000H,
            "grid": {"percentile": PERCENTILES, "on_delay_hours": ON_DELAYS},
            "deadband": DEADBAND, "bootstrap_resamples": resamples, "bootstrap_seed": BOOTSTRAP_SEED,
            "primary_method": PRIMARY, "baseline_method": BASELINE,
        },
        "operating_point": {"percentile": percentile, "on_delay_hours": on_delay},
        "calibration": [row(calibration, PRIMARY, p, delay, with_interval=False) for p in PERCENTILES for delay in ON_DELAYS],
        "evaluation": methods,
        "primary_minus_baseline": difference,
        "any_priority": row(per_priority["evaluation"]["any"], PRIMARY, percentile, on_delay),
        "sensitivity": [row(held_out, method, p, delay, with_interval=False)
                        for method in (PRIMARY, BASELINE) for p in PERCENTILES for delay in ON_DELAYS],
        "lead_hours": sorted(leads),
        "alarm_review": alarm_review(evaluation_seeds, percentile, on_delay),
    }
