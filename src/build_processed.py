"""Append logical time and review flags while preserving every input cell and row."""
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .common import TAGS, write_csv, write_json


def logical_time(value):
    stamp = datetime.fromisoformat(value)
    following = stamp.replace(minute=0, second=0) + timedelta(hours=1)
    delta = (following - stamp).total_seconds()
    return following if 0 < delta <= 3 else stamp


def build(root):
    root = Path(root)
    with (root / "data/interim/records.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    exact, logical = defaultdict(list), defaultdict(list)
    for i, row in enumerate(rows):
        stamp = datetime.fromisoformat(row["timestamp"])
        hour = logical_time(row["timestamp"])
        row.update(logical_hour=hour.isoformat(), offset_seconds=int((stamp - hour).total_seconds()))
        if row["record_type"] == "measurement":
            exact[row["timestamp"]].append(i)
            logical[row["logical_hour"]].append(i)
    for row in rows:
        ids = logical[row["logical_hour"]] if row["record_type"] == "measurement" else []
        vectors = {tuple(Decimal(rows[i][key]) for key in TAGS) for i in ids}
        row.update(exact_timestamp_multiple=len(exact[row["timestamp"]]) > 1 if ids else False,
                   logical_hour_count=len(ids), logical_hour_multiple=len(ids) > 1,
                   logical_hour_conflict=len(vectors) > 1,
                   date_requires_review=row["logical_hour"][:10] != row["nominal_date"])
        row["requires_review"] = (row["logical_hour_multiple"] or row["date_requires_review"]
                                  or row["backward_timestamp"] == "True" or row["record_type"] == "event")
    extra = ["logical_hour", "offset_seconds", "exact_timestamp_multiple", "logical_hour_count",
             "logical_hour_multiple", "logical_hour_conflict", "date_requires_review", "requires_review"]
    write_csv(root / "data/processed/scada.csv", rows, fields + extra)
    summary = {"rows": len(rows), "measurements": sum(r["record_type"] == "measurement" for r in rows),
               "events": sum(r["record_type"] == "event" for r in rows),
               "measurement_hours": len(logical),
               "multiple_hours": sum(len(ids) > 1 for ids in logical.values()),
               "shifted_rows": sum(r["offset_seconds"] != 0 for r in rows),
               "review_rows": sum(r["requires_review"] for r in rows)}
    write_json(root / "reports/quality_summary.json", summary)
    return summary
