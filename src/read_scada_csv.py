"""Strict parsing with original text, physical row provenance, and no deduplication."""
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .common import RAW_FIELDS, TAGS, write_csv
from .file_inventory import verify

META = ["source_file", "source_line", "nominal_date", "timestamp", "date_mismatch", "backward_timestamp"]


def read_records(root):
    root = Path(root)
    records = []
    for entry in verify(root):
        source = entry["source_file"]
        nominal = Path(source).stem.removeprefix("history_")
        previous = None
        with (root / source).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames != RAW_FIELDS:
                raise ValueError(f"Unexpected header: {source}")
            for row in reader:
                if None in row or None in row.values():
                    raise ValueError(f"Unexpected row width: {source}:{reader.line_num}")
                stamp = datetime.strptime(row["date"] + "T" + row["time"], "%Y-%m-%dT%H:%M:%S")
                if row["record_type"] == "measurement":
                    try:
                        if any(not Decimal(row[key]).is_finite() for key in TAGS):
                            raise ValueError("Non-finite measurement")
                    except InvalidOperation as error:
                        raise ValueError(f"Invalid number: {source}:{reader.line_num}") from error
                    if row["event_message"]:
                        raise ValueError("Measurement carries an event message")
                elif row["record_type"] == "event":
                    if any(row[key] for key in TAGS) or not row["event_message"]:
                        raise ValueError("Event must contain a message and empty measurements")
                else:
                    raise ValueError("Unknown record type")
                records.append({"source_file": source, "source_line": reader.line_num,
                                "nominal_date": nominal, "timestamp": stamp.isoformat(),
                                "date_mismatch": stamp.date().isoformat() != nominal,
                                "backward_timestamp": previous is not None and stamp < previous,
                                **row})
                previous = stamp
    verify(root)
    write_csv(root / "data/interim/records.csv", records, META + RAW_FIELDS)
    return records
