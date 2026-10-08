"""Shared schema and small file helpers. All paths are relative to an output root."""
import csv
import hashlib
import json
from pathlib import Path

SIGNALS = [
    "active_power_kw", "reactive_power_kvar",
    "phase_current_a", "phase_current_b", "phase_current_c",
    "phase_voltage_ab", "phase_voltage_bc", "phase_voltage_ca",
    "frequency_hz", "water_level_m", "penstock_pressure_m",
    "guide_opening_a_pct", "guide_opening_b_pct", "room_temperature_c",
    "winding_temperature_a_c", "winding_temperature_b_c", "winding_temperature_c_c",
    "bearing_temperature_a_c", "bearing_temperature_b_c", "oil_temperature_c",
]
RAW_FIELDS = ["date", "time", "record_type", "event_message", *SIGNALS]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
