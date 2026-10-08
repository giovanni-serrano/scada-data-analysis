"""Generate an invented hourly history without reading any external dataset."""
import csv
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .common import RAW_FIELDS, SIGNALS, write_json

SEED = 781
START = datetime(2042, 1, 1)
HOURS = 365 * 24
SYNTHETIC_EVENT_TIME = datetime(2042, 11, 18, 20)
EVENT_HOUR = int((SYNTHETIC_EVENT_TIME - START).total_seconds() / 3600)
MISSING_HOURS = set(range(931, 934)) | set(range(2609, 2611)) | set(range(4481, 4486)) | set(range(6138, 6141))
DUPLICATE_HOURS = {319, 1144, 2390, 3694, 4888, 5782, 6917}
EARLY_HOURS = {744, 1550, 2704, 3115, 4220, 5071, 6022, 7033, 8444}
COMMUNICATION_HOURS = {932, 2610, 4483, 6140}
FREEZE_START, FREEZE_END = 3820, 3838
FROZEN_SENSOR = "bearing_temperature_b_c"


def timestamp(hour):
    return (START + timedelta(hours=hour)).isoformat(timespec="seconds")


def generate(root, seed=SEED):
    root = Path(root)
    raw = root / "data/raw"
    if raw.exists() and any(raw.iterdir()):
        raise FileExistsError("RAW directory is not empty; choose a new output root.")
    rng = np.random.default_rng(seed)
    buckets = {}
    winding_rise, bearing_rise, oil_rise = 0.0, 0.0, 0.0
    for hour in range(HOURS):
        logical = START + timedelta(hours=hour)
        day, clock = hour / 24, hour % 24
        room = 22 + 5 * np.sin(2 * np.pi * day / 365) + 2 * np.sin(2 * np.pi * clock / 24) + rng.normal(0, .25)
        load = np.clip(.60 + .23 * np.sin(2 * np.pi * day / 19) + .09 * np.sin(2 * np.pi * clock / 24) + rng.normal(0, .018), .18, .95)
        stopped = (hour % (41 * 24) < 12) or EVENT_HOUR <= hour < EVENT_HOUR + 36
        if EVENT_HOUR - 96 <= hour < EVENT_HOUR:
            stopped = False
        if stopped:
            load = 0.0
        ramp = max(0.0, 1 - (EVENT_HOUR - hour) / 96) if hour < EVENT_HOUR else 0.0
        thermal_ramp = max(0.0, 1 - (EVENT_HOUR - hour) / 72) if hour < EVENT_HOUR else 0.0
        power = 820 * load
        reactive = power * (.24 + .02 * np.sin(2 * np.pi * day / 13))
        voltage = 2300 + rng.normal(0, 3) if load else 0.0
        current = np.hypot(power, reactive) * 1000 / (np.sqrt(3) * voltage) if load else 0.0
        currents = current * (np.array([1.001, .999, 1.0]) + rng.normal(0, .001, 3) + ramp * np.array([.11, -.07, -.04]))
        voltages = voltage * (np.array([1.0005, .9995, 1.0]) + rng.normal(0, .00025, 3) + ramp * np.array([.008, -.005, -.003]))
        winding_rise += .28 * (7 * (load > 0) + 33 * load**1.25 + 17 * thermal_ramp - winding_rise)
        bearing_rise += .12 * (5 * (load > 0) + 18 * load - bearing_rise)
        oil_rise += .08 * (3 * (load > 0) + 14 * load - oil_rise)
        windings = room + winding_rise + np.array([.4, -.3, .1]) + rng.normal(0, .12, 3)
        values = [power, reactive, *currents, *voltages,
                  50 + rng.normal(0, .015) if load else 0,
                  8 + .8 * np.sin(2 * np.pi * day / 47) + rng.normal(0, .025),
                  110 - 12 * load**2 + rng.normal(0, .15),
                  86 * load + rng.normal(0, .2) if load else 0,
                  82 * load + rng.normal(0, .2) if load else 0,
                  room, *windings,
                  room + bearing_rise + rng.normal(0, .1),
                  room + bearing_rise + .7 + rng.normal(0, .1),
                  room + oil_rise + rng.normal(0, .1)]
        signals = dict(zip(SIGNALS, (f"{value:.4f}" for value in values)))
        if FREEZE_START <= hour < FREEZE_END:
            signals[FROZEN_SENSOR] = "74.2500"
        observed = logical - timedelta(seconds=2) if hour in EARLY_HOURS else logical
        base = {"date": observed.date().isoformat(), "time": observed.time().isoformat(),
                "record_type": "measurement", "event_message": "", **signals}
        # File placement follows the invented logical day, not the shifted timestamp.
        bucket = buckets.setdefault(logical.date().isoformat(), [])
        if hour not in MISSING_HOURS:
            bucket.append(base)
            if hour in DUPLICATE_HOURS:
                alternative = dict(base)
                alternative["active_power_kw"] = f"{power + 9.0:.4f}"
                bucket.append(alternative)
        if hour in COMMUNICATION_HOURS:
            bucket.append({"date": logical.date().isoformat(), "time": logical.time().isoformat(),
                           "record_type": "event", "event_message": "communication_fault",
                           **dict.fromkeys(SIGNALS, "")})
        if hour == EVENT_HOUR:
            bucket.append({"date": logical.date().isoformat(), "time": logical.time().isoformat(),
                           "record_type": "event", "event_message": "synthetic_shutdown",
                           **dict.fromkeys(SIGNALS, "")})
    raw.mkdir(parents=True, exist_ok=True)
    for day, rows in buckets.items():
        with (raw / f"history_{day}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS, delimiter=";", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    truth = {
        "synthetic_only": True, "seed": seed, "start": START.isoformat(), "expected_hours": HOURS,
        "synthetic_event_time": SYNTHETIC_EVENT_TIME.isoformat(),
        "event_semantics": "Artificial shutdown; no validated physical failure mechanism.",
        "current_ramp_start": timestamp(EVENT_HOUR - 96),
        "thermal_ramp_start": timestamp(EVENT_HOUR - 72),
        "shutdown_hours": 36,
        "missing_measurement_hours": [timestamp(h) for h in sorted(MISSING_HOURS)],
        "conflicting_duplicate_hours": [timestamp(h) for h in sorted(DUPLICATE_HOURS)],
        "early_by_two_seconds": [timestamp(h) for h in sorted(EARLY_HOURS)],
        "communication_fault_hours": [timestamp(h) for h in sorted(COMMUNICATION_HOURS)],
        "frozen_sensor": {"column": FROZEN_SENSOR, "start": timestamp(FREEZE_START),
                          "end_exclusive": timestamp(FREEZE_END), "value": 74.25},
    }
    write_json(root / "data/synthetic_scenario.json", truth)
    return truth
