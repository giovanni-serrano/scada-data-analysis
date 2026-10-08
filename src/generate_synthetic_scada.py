"""Generate an invented hourly history without reading any external dataset."""
import csv
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .common import RAW_FIELDS, SIGNALS, SIGNAL_TO_TAG, TAGS, TRIP_MESSAGE, write_json

SEED = 781
START = datetime(2025, 1, 1)
HOURS = 365 * 24
# Degradation episodes are only scheduled after this event-free reference period.
REFERENCE_HOURS = 180 * 24
NOMINAL_KW, NOMINAL_V, NOMINAL_HZ = 820.0, 2300.0, 60.0
CURRENT_FULL_SCALE_A = 250.0
PLANNED_STOP_PERIOD, PLANNED_STOP_HOURS = 41 * 24, 12
EVENT_COUNT = (2, 4)
RAMP_HOURS = (48, 120)
TRIP_STOP_HOURS = (12, 36)
MIN_EVENT_GAP_HOURS = 240
# Severity 1.0 adds these amounts at the trip; smaller episodes stay inside normal scatter.
SEVERITY = (.15, 1.0)
FULL_WINDING_DELTA_C = 9.0
FULL_CURRENT_SPREAD_DELTA_PCT = 4.5
FULL_VOLTAGE_SPREAD_DELTA_PCT = .4
MISSING_HOURS = set(range(931, 934)) | set(range(2609, 2611)) | set(range(4481, 4486)) | set(range(6138, 6141))
DUPLICATE_HOURS = {319, 1144, 2390, 3694, 4888, 5782, 6917}
EARLY_HOURS = {744, 1550, 2704, 3115, 4220, 5071, 6022, 7033, 8444}
COMMUNICATION_HOURS = {932, 2610, 4483, 6140}
FREEZE_START, FREEZE_END = 3820, 3838
FROZEN_SENSOR = "bearing_temperature_b_c"


def timestamp(hour):
    return (START + timedelta(hours=int(hour))).isoformat(timespec="seconds")


def ar1(rng, n, phi, sigma):
    """Stationary autocorrelated noise: slow drifts instead of independent hourly jumps."""
    shocks = rng.normal(0, sigma * np.sqrt(1 - phi**2), n).tolist()
    state, out = float(rng.normal(0, sigma)), []
    for shock in shocks:
        state = phi * state + shock
        out.append(state)
    return np.array(out)


def lag(target, coefficient):
    """First-order thermal inertia: state += coefficient * (target - state)."""
    state, out = 0.0, []
    for goal in target.tolist():
        state += coefficient * (goal - state)
        out.append(state)
    return np.array(out)


def draw_events(rng):
    """Schedule degradation episodes at random hours and sizes after the reference period."""
    count = int(rng.integers(EVENT_COUNT[0], EVENT_COUNT[1] + 1))
    while True:
        trips = np.sort(rng.integers(REFERENCE_HOURS + RAMP_HOURS[1] + 48, HOURS - TRIP_STOP_HOURS[1] - 24, count))
        ramps = rng.integers(RAMP_HOURS[0], RAMP_HOURS[1] + 1, count)
        stops = rng.integers(TRIP_STOP_HOURS[0], TRIP_STOP_HOURS[1] + 1, count)
        starts, ends = trips - ramps, trips + stops
        spaced = all(starts[i] - ends[i - 1] >= MIN_EVENT_GAP_HOURS for i in range(1, count))
        clear = all(not np.any(np.arange(lo - 6, hi + 6) % PLANNED_STOP_PERIOD < PLANNED_STOP_HOURS)
                    for lo, hi in zip(starts, ends))
        if spaced and clear:
            break
    events = []
    for number, (trip, ramp, stop) in enumerate(zip(trips, ramps, stops), start=1):
        severity = float(rng.uniform(*SEVERITY))
        winding, current = severity * rng.uniform(.8, 1.2, 2) * [FULL_WINDING_DELTA_C, FULL_CURRENT_SPREAD_DELTA_PCT]
        events.append({"id": number, "ramp_start_hour": int(trip - ramp), "trip_hour": int(trip),
                       "ramp_hours": int(ramp), "shutdown_hours": int(stop), "severity": severity,
                       "winding_rise_delta_c": float(winding), "current_spread_delta_pct": float(current),
                       "voltage_spread_delta_pct": severity * FULL_VOLTAGE_SPREAD_DELTA_PCT,
                       "phase": "abc"[int(rng.integers(3))]})
    return events


def simulate(seed=SEED):
    """Return the hourly plant history in memory plus the event list the detector never sees."""
    noise = np.random.default_rng([seed, 0])
    # Independent stream: event times and sizes do not depend on the noise realisation.
    events = draw_events(np.random.default_rng([seed, 1]))
    hour = np.arange(HOURS)
    day, clock = hour / 24, hour % 24
    stopped = hour % PLANNED_STOP_PERIOD < PLANNED_STOP_HOURS
    thermal_extra = np.zeros(HOURS)
    current_extra, voltage_extra = np.zeros((HOURS, 3)), np.zeros((HOURS, 3))
    for event in events:
        start, trip = event["ramp_start_hour"], event["trip_hour"]
        stopped[trip:trip + event["shutdown_hours"]] = True
        progress = (np.arange(start, trip) - start) / event["ramp_hours"]
        # One phase departs from the other two; the three-phase mean is unchanged.
        direction = np.full(3, -1 / 3)
        direction["abc".index(event["phase"])] = 2 / 3
        thermal_extra[start:trip] = progress * event["winding_rise_delta_c"]
        current_extra[start:trip] = np.outer(progress, direction) * event["current_spread_delta_pct"] / 100
        voltage_extra[start:trip] = np.outer(progress, direction) * event["voltage_spread_delta_pct"] / 100
    running = ~stopped

    # Tropical ambient: small annual swing, dominant daily cycle, autocorrelated weather.
    room = 27 + 1.5 * np.sin(2 * np.pi * day / 365) + 2.5 * np.sin(2 * np.pi * (clock - 9) / 24) + ar1(noise, HOURS, .92, .7)
    load = np.clip(.60 + .23 * np.sin(2 * np.pi * day / 19) + .09 * np.sin(2 * np.pi * clock / 24)
                   + ar1(noise, HOURS, .6, .025), .18, .95) * running
    power = NOMINAL_KW * load
    # Reactive power follows voltage-control needs, so the power factor wanders instead of being fixed.
    reactive = power * np.clip(.30 + .08 * np.sin(2 * np.pi * day / 13) + ar1(noise, HOURS, .95, .07), .05, .60)
    grid_voltage = NOMINAL_V * (1 + ar1(noise, HOURS, .97, .005))
    current = np.hypot(power, reactive) * 1000 / (np.sqrt(3) * grid_voltage)

    def three_phase(fixed_sigma, drift_sigma):
        fixed = noise.normal(0, fixed_sigma, 3)
        drift = np.column_stack([ar1(noise, HOURS, .985, drift_sigma) for _ in range(3)])
        return 1 + fixed - fixed.mean() + drift

    # Instrument accuracy = fraction of reading + fraction of full scale.
    currents = (current[:, None] * (three_phase(.008, .004) + current_extra) * (1 + noise.normal(0, .003, (HOURS, 3)))
                + noise.normal(0, .0012 * CURRENT_FULL_SCALE_A, (HOURS, 3)))
    voltages = grid_voltage[:, None] * (three_phase(.002, .001) + voltage_extra) * (1 + noise.normal(0, .001, (HOURS, 3)))
    power_read = power * (1 + noise.normal(0, .003, HOURS)) + noise.normal(0, .8, HOURS)
    reactive_read = reactive * (1 + noise.normal(0, .003, HOURS)) + noise.normal(0, .5, HOURS)
    frequency = NOMINAL_HZ + ar1(noise, HOURS, .6, .02)

    # Copper resistance grows with temperature, so heating rises slightly on hot days.
    winding_target = (7 * running + 33 * load**1.25) * (1 + .004 * (room - 27)) + thermal_extra
    winding_rise = lag(winding_target, .28) + ar1(noise, HOURS, .8, .35) * running
    bearing_rise = lag(5 * running + 18 * load, .12)
    oil_rise = lag(3 * running + 14 * load, .08)
    windings = (room + winding_rise)[:, None] + np.array([.4, -.3, .1]) + noise.normal(0, .2, (HOURS, 3))
    level = 8 + .8 * np.sin(2 * np.pi * day / 47) + ar1(noise, HOURS, .99, .05)

    electrical = running[:, None]
    columns = np.column_stack([
        power_read * running, reactive_read * running, currents * electrical, voltages * electrical,
        frequency * running, level + noise.normal(0, .01, HOURS),
        # Pressure head = static head from the reservoir minus friction losses (flow squared).
        102 + level - 12 * load**2 + noise.normal(0, .15, HOURS),
        # A lower reservoir means less head, so the same power needs a wider opening.
        (86 * load * (8 / level) ** .5 + noise.normal(0, .4, HOURS)) * running,
        (82 * load * (8 / level) ** .5 + noise.normal(0, .4, HOURS)) * running,
        room + noise.normal(0, .1, HOURS), windings,
        room + bearing_rise + noise.normal(0, .15, HOURS),
        room + bearing_rise + .7 + noise.normal(0, .15, HOURS),
        room + oil_rise + noise.normal(0, .15, HOURS),
    ])
    frame = pd.DataFrame(columns + 0.0, columns=SIGNALS)  # + 0.0 turns -0.0 into 0.0
    # A stuck transmitter repeats its last reading (to the logged resolution).
    held = round(float(frame.at[FREEZE_START, FROZEN_SENSOR]), 4)
    frame.loc[FREEZE_START:FREEZE_END - 1, FROZEN_SENSOR] = held
    frame.insert(0, "logical_hour", [timestamp(h) for h in hour])
    truth = {
        "synthetic_only": True, "seed": seed, "start": START.isoformat(), "expected_hours": HOURS,
        "nominal_frequency_hz": NOMINAL_HZ, "reference_end_exclusive": timestamp(REFERENCE_HOURS),
        "event_semantics": "Artificial degradation ramp ending in a trip; no validated physical failure mechanism.",
        "events": [{"id": e["id"], "ramp_start": timestamp(e["ramp_start_hour"]), "trip_time": timestamp(e["trip_hour"]),
                    **{key: e[key] for key in ("ramp_hours", "shutdown_hours", "severity", "winding_rise_delta_c",
                                                "current_spread_delta_pct", "voltage_spread_delta_pct", "phase")}}
                   for e in events],
        "missing_measurement_hours": [timestamp(h) for h in sorted(MISSING_HOURS)],
        "conflicting_duplicate_hours": [timestamp(h) for h in sorted(DUPLICATE_HOURS)],
        "early_by_two_seconds": [timestamp(h) for h in sorted(EARLY_HOURS)],
        "communication_fault_hours": [timestamp(h) for h in sorted(COMMUNICATION_HOURS)],
        "frozen_sensor": {"column": FROZEN_SENSOR, "tag": SIGNAL_TO_TAG[FROZEN_SENSOR], "start": timestamp(FREEZE_START),
                          "end_exclusive": timestamp(FREEZE_END), "value": held},
    }
    return frame, truth


def selected_measurements(frame):
    """Hours the pipeline keeps for statistics: no missing rows and no contradictory duplicates."""
    return frame.drop(index=sorted(MISSING_HOURS | DUPLICATE_HOURS)).reset_index(drop=True)


def generate(root, seed=SEED):
    root = Path(root)
    raw = root / "data/raw"
    if raw.exists() and any(raw.iterdir()):
        raise FileExistsError("RAW directory is not empty; choose a new output root.")
    frame, truth = simulate(seed)
    trips = {pd.Timestamp(event["trip_time"]).to_pydatetime() for event in truth["events"]}
    power_tag = SIGNAL_TO_TAG["active_power_kw"]
    buckets = {}
    for hour, values in enumerate(frame[SIGNALS].to_numpy().tolist()):
        logical = START + timedelta(hours=hour)
        signals = dict(zip(TAGS, (f"{value:.4f}" for value in values)))
        observed = logical - timedelta(seconds=2) if hour in EARLY_HOURS else logical
        base = {"date": observed.date().isoformat(), "time": observed.time().isoformat(),
                "record_type": "measurement", "event_message": "", **signals}
        # File placement follows the invented logical day, not the shifted timestamp.
        bucket = buckets.setdefault(logical.date().isoformat(), [])
        if hour not in MISSING_HOURS:
            bucket.append(base)
            if hour in DUPLICATE_HOURS:
                alternative = dict(base)
                alternative[power_tag] = f"{values[0] + 9.0:.4f}"
                bucket.append(alternative)
        for message, applies in [("communication_fault", hour in COMMUNICATION_HOURS), (TRIP_MESSAGE, logical in trips)]:
            if applies:
                bucket.append({"date": logical.date().isoformat(), "time": logical.time().isoformat(),
                               "record_type": "event", "event_message": message, **dict.fromkeys(TAGS, "")})
    raw.mkdir(parents=True, exist_ok=True)
    for day, rows in buckets.items():
        with (raw / f"history_{day}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS, delimiter=";", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    write_json(root / "data/synthetic_scenario.json", truth)
    return truth
