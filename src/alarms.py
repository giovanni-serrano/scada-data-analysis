"""Alarm logic in ISA-18.2 vocabulary: on-delay, deadband, priority and performance counts.

The data are hourly, so the standard's time definitions (seconds and minutes) are
scaled to hours here; the concepts are the same.
"""
import numpy as np
import pandas as pd

# Alarm list: tag, state column, priority, description.
ALARM_POINTS = [
    ("G1_TW_HI", "winding_rise_c_alarm", "baja", "Elevación térmica sobre su referencia"),
    ("G1_IUNB_HI", "current_spread_pct_alarm", "baja", "Dispersión de corriente sobre su referencia"),
    ("G1_DEG_HH", "alarm_high", "alta", "Exceso conjunto de elevación térmica y dispersión de corriente"),
]
# Deadband in indicator units: an active alarm clears only below threshold - deadband.
DEADBAND = {"winding_rise_c": 1.0, "current_spread_pct": .4}
NO_DEADBAND = dict.fromkeys(DEADBAND, 0.0)
# On-delay chosen on the calibration seeds (src/evaluate.py); a test keeps it in step.
ON_DELAY_HOURS, OFF_DELAY_HOURS = 2, 1
FLEETING_MAX_HOURS, STALE_MIN_HOURS, REPEAT_WITHIN_HOURS = 2, 24, 6


def sustained(mask, times, length=3):
    """Mark the third and subsequent consecutive positive hourly observations."""
    flag = np.asarray(mask, dtype=bool)
    index = mask.index if isinstance(mask, pd.Series) else None
    if not len(flag):
        return pd.Series(flag, index=index, dtype=bool)
    step = pd.Series(times).diff().eq(pd.Timedelta(hours=1)).to_numpy()
    # The count restarts wherever the run of consecutive positive hours is broken.
    restart = ~(flag & step)
    position = np.arange(len(flag))
    origin = np.maximum.accumulate(np.where(restart, position, 0))
    count = position - origin + flag[origin]
    return pd.Series(count >= length, index=index, dtype=bool)


def latch(set_condition, hold_condition, times, on_delay=ON_DELAY_HOURS, off_delay=OFF_DELAY_HOURS):
    """Alarm state per hour.

    Activates on the on_delay-th consecutive hour that meets set_condition and stays
    active until hold_condition has failed for off_delay consecutive hours. A missing
    hour clears the alarm: the state is never carried across a gap.
    """
    armed = sustained(set_condition, times, on_delay).to_numpy().tolist()
    hold = np.asarray(hold_condition, dtype=bool).tolist()
    contiguous = pd.Series(times).diff().eq(pd.Timedelta(hours=1)).to_numpy().tolist()
    active, below, state = False, 0, []
    for start, keep, joined in zip(armed, hold, contiguous):
        if not joined:
            active, below = False, 0
        if active:
            below = 0 if keep else below + 1
            active = below < off_delay
        if start and not active:
            active, below = True, 0
        state.append(active)
    return np.array(state, dtype=bool)


def annunciate(d, on_delay=ON_DELAY_HOURS, deadband=DEADBAND, off_delay=OFF_DELAY_HOURS):
    """Add the three alarm states and the hourly priority to a frame that carries thresholds.

    Low priority: one indicator stays above its threshold. High priority: winding
    rise and current spread stay above their thresholds together.
    """
    out = d.copy()
    hold = {}
    for metric in DEADBAND:
        hold[metric] = (out.eligible & out[metric].gt(out[metric + "_threshold"] - deadband[metric])).to_numpy()
        out[metric + "_alarm"] = latch(out[metric + "_high"], hold[metric], out.t, on_delay, off_delay)
    out["alarm_high"] = latch(out.joint_high, np.logical_and.reduce(list(hold.values())), out.t, on_delay, off_delay)
    single = np.logical_or.reduce([out[metric + "_alarm"].to_numpy() for metric in DEADBAND])
    out["priority"] = np.where(out.alarm_high, 2, np.where(single, 1, 0))
    return out


def episodes(state, times):
    """One row per alarm activation: start, duration and hours since the previous clear."""
    state = np.asarray(state, dtype=bool)
    times = pd.Series(times).reset_index(drop=True)
    edges = np.diff(np.concatenate([[0], state.astype(int), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1
    rows, previous_clear = [], None
    for start, end in zip(starts, ends):
        cleared = times[end] + pd.Timedelta(hours=1)
        rows.append({"start": times[start], "duration_hours": float((cleared - times[start]).total_seconds() / 3600),
                     "hours_since_clear": None if previous_clear is None
                     else float((times[start] - previous_clear).total_seconds() / 3600)})
        previous_clear = cleared
    return rows


def alarm_kpis(d, mask=None):
    """Counts an alarm-system review asks for, over the hours selected by mask."""
    part = d if mask is None else d[np.asarray(mask)]
    inside, hours = set(part.t), int(part.eligible.sum())
    points, by_priority = [], {"baja": 0, "alta": 0}
    for tag, column, priority, description in ALARM_POINTS:
        # Episodes come from the whole series so the edge of a mask does not invent activations.
        listed = [e for e in episodes(d[column], d.t) if e["start"] in inside]
        durations = [e["duration_hours"] for e in listed]
        by_priority[priority] += len(listed)
        points.append({
            "tag": tag, "priority": priority, "description": description, "activations": len(listed),
            "activations_per_1000h": 1000 * len(listed) / hours if hours else None,
            "hours_active": int(part[column].sum()),
            "median_duration_hours": float(np.median(durations)) if durations else None,
            "fleeting": sum(value <= FLEETING_MAX_HOURS for value in durations),
            "stale": sum(value >= STALE_MIN_HOURS for value in durations),
            "repeats": sum(e["hours_since_clear"] is not None and e["hours_since_clear"] <= REPEAT_WITHIN_HOURS for e in listed),
        })
    total = sum(by_priority.values())
    return {"eligible_hours": hours, "activations": total,
            "activations_per_hour": total / hours if hours else None,
            "activations_by_priority": by_priority,
            "fleeting": sum(p["fleeting"] for p in points), "stale": sum(p["stale"] for p in points),
            "repeats": sum(p["repeats"] for p in points), "points": points}
