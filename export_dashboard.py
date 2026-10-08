"""Export a small, verified synthetic presentation; reuse the scientific pipeline."""
import argparse
import json
from pathlib import Path
import tempfile

import pandas as pd

from run_pipeline import run
from src.alarms import ALARM_POINTS
from src.analyze_scada import METRICS, derive, detect, event_windows
from src.common import SIGNALS, TAG_CATALOG, digest
from src.evaluate import evaluate
from src.generate_synthetic_scada import SEED

TABLES = ("quality_summary.json", "analysis_summary.json", "historical_reference.csv",
          "period_comparison.csv", "event_detection.csv")


def verify_synthetic(root):
    """Compare every data/table input with a fresh public generation, not a label."""
    root = Path(root)
    truth = json.loads((root / "data/synthetic_scenario.json").read_text(encoding="utf-8"))
    if truth.get("synthetic_only") is not True or truth.get("seed") != SEED:
        raise ValueError("Only the documented synthetic scenario is supported")
    with tempfile.TemporaryDirectory(prefix="scada-export-") as temporary:
        fresh = Path(temporary)
        run(fresh, figures=False)
        expected = sorted(p.relative_to(fresh) for p in (fresh / "data").rglob("*") if p.is_file())
        actual = sorted(p.relative_to(root) for p in (root / "data").rglob("*") if p.is_file())
        if actual != expected:
            raise ValueError("Synthetic input file set differs from public regeneration")
        expected += [Path("reports") / name for name in TABLES]
        for relative in expected:
            if (root / relative).read_text(encoding="utf-8") != (fresh / relative).read_text(encoding="utf-8"):
                raise ValueError(f"Input differs from synthetic regeneration: {relative.as_posix()}")
    return truth, {p.as_posix(): digest(root / p) for p in expected}


def verified_evaluation(root, rerun=True):
    """Load the multi-seed summary and, unless told otherwise, recompute it from its own seeds."""
    path = Path(root) / "reports/evaluation_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    if summary.get("synthetic_only") is not True:
        raise ValueError("Only the documented synthetic evaluation is supported")
    if rerun:
        protocol = summary["protocol"]
        fresh = evaluate(protocol["calibration_seeds"], protocol["evaluation_seeds"], resamples=protocol["bootstrap_resamples"])
        if json.loads(json.dumps(fresh)) != summary:
            raise ValueError("Evaluation summary differs from regeneration")
    return summary, digest(path)


def records(frame, columns):
    # JSON null represents missing/undefined values, never zero or nonstandard NaN.
    return json.loads(frame[columns].to_json(orient="records", date_format="iso", double_precision=12))


def build_payload(root, verify_evaluation=True):
    root = Path(root)
    truth, hashes = verify_synthetic(root)
    evaluation, hashes["reports/evaluation_summary.json"] = verified_evaluation(root, rerun=verify_evaluation)
    summary = json.loads((root / "reports/analysis_summary.json").read_text(encoding="utf-8"))
    quality = json.loads((root / "reports/quality_summary.json").read_text(encoding="utf-8"))
    source = pd.read_csv(root / "data/processed/scada.csv", keep_default_na=False)
    review = source.requires_review.astype(str).str.lower().eq("true")
    selected = source[(source.record_type == "measurement") & ~review]
    d, _ = detect(derive(selected), pd.Timestamp(summary["reference_end_exclusive"]))
    reference_start = pd.Timestamp(truth["start"]) + pd.Timedelta(days=150)
    reference_end = reference_start + pd.Timedelta(days=14)
    reference = d[(d.t >= reference_start) & (d.t < reference_end) & d.eligible]
    relation_columns = ["t", "active_power_kw", "reactive_power_kvar", "phase_current_a", "phase_current_b",
                        "phase_current_c", "mean_current_a", "mean_voltage_v", "room_temperature_c",
                        "winding_temperature_a_c", "winding_temperature_b_c", "winding_temperature_c_c", "winding_rise_c"]
    timeline_columns = ["t", "hours_to_trip", "eligible", "alarm_high", "priority"]
    for metric in METRICS:
        timeline_columns += [metric, metric + "_threshold"]
    events, recent = [], []
    for (start, trip, _, _), scored in zip(event_windows(truth), summary["events"]):
        timeline = d[(d.t >= start - pd.Timedelta(hours=24)) & (d.t < trip)].copy()
        timeline["hours_to_trip"] = (timeline.t - trip).dt.total_seconds() / 3600
        events.append({**scored, "timeline": records(timeline, timeline_columns)})
        recent.append(d[(d.t >= trip - pd.Timedelta(hours=48)) & (d.t < trip) & d.eligible])
    calendar = pd.date_range(pd.Timestamp(truth["start"]), periods=365, freq="D")
    coverage = pd.DataFrame({"t": calendar})
    coverage["selected"] = d.groupby(d.t.dt.normalize()).size().reindex(calendar, fill_value=0).values
    coverage["eligible"] = d[d.eligible].groupby(d.t.dt.normalize()).size().reindex(calendar, fill_value=0).values
    measurements = source[source.record_type == "measurement"].copy()
    measurements["day"] = pd.to_datetime(measurements.logical_hour).dt.normalize()
    coverage["preserved"] = measurements.groupby("day").size().reindex(calendar, fill_value=0).values
    frozen = d[d.sensor_flat]
    if frozen.empty:
        raise ValueError("Documented synthetic sensor plateau is missing")
    sensor = d[(d.t >= frozen.t.min() - pd.Timedelta(hours=18)) & (d.t <= frozen.t.max() + pd.Timedelta(hours=18))]
    return {
        "schema_version": 2, "synthetic_only": True, "seed": truth["seed"], "signal_count": len(SIGNALS),
        "tags": [dict(zip(("tag", "signal", "unit", "description"), row)) for row in TAG_CATALOG],
        "summary": {key: value for key, value in summary.items() if key != "events"}, "quality": quality,
        "provenance": {"exporter": "export_dashboard.py", "source_sha256": hashes,
                       "verification": f"{len(hashes) - 1} data/table inputs checked against fresh synthetic regeneration",
                       "evaluation_recomputed": verify_evaluation,
                       "presentation": "No sampling: all eligible hourly observations in each displayed period; daily coverage is a count."},
        "relationships": {"reference_start": reference_start.isoformat(), "reference_end_exclusive": reference_end.isoformat(),
                          "reference": records(reference, relation_columns), "pre_event": records(pd.concat(recent), relation_columns)},
        "coverage": records(coverage, ["t", "preserved", "selected", "eligible"]),
        "sensor": {"start": frozen.t.min().isoformat(), "end_exclusive": (frozen.t.max() + pd.Timedelta(hours=1)).isoformat(),
                   "rows": records(sensor, ["t", "bearing_temperature_a_c", "bearing_temperature_b_c", "room_temperature_c", "sensor_flat"])},
        "events": events,
        "alarm_points": [dict(zip(("tag", "column", "priority", "description"), row)) for row in ALARM_POINTS],
        "evaluation": evaluation,
        "incidents": {"missing": truth["missing_measurement_hours"], "conflicts": truth["conflicting_duplicate_hours"],
                      "shifted": truth["early_by_two_seconds"], "communication": truth["communication_fault_hours"]},
    }


def export(root, output, verify_evaluation=True):
    payload = build_payload(root, verify_evaluation=verify_evaluation)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Binary write keeps LF and identical bytes on different operating systems.
    output.write_bytes((json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8"))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "docs/assets/dashboard-data.json")
    parser.add_argument("--skip-evaluation-check", action="store_true",
                        help="trust reports/evaluation_summary.json instead of recomputing every simulated year")
    args = parser.parse_args()
    payload = export(args.source_root, args.output, verify_evaluation=not args.skip_evaluation_check)
    print(f"Web export: {len(payload['events'])} events; {len(payload['coverage'])} daily coverage counts; "
          f"{len(payload['evaluation']['protocol']['evaluation_seeds'])} evaluation years.")
