"""Load-conditioned descriptive analysis with a frozen early reference period."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .alarms import DEADBAND, NO_DEADBAND, OFF_DELAY_HOURS, ON_DELAY_HOURS, alarm_kpis, annunciate, sustained  # noqa: F401
from .common import SIGNALS, TAG_TO_SIGNAL, TRIP_MESSAGE, write_json

METRICS = ["winding_rise_c", "current_spread_pct", "voltage_spread_pct"]
LABELS = ["Elevación térmica (°C)", "Dispersión de corriente (%)", "Dispersión de tensión (%)"]
LOAD_EDGES = [0, 200, 300, 400, 500, 600, 700, 900]
AMBIENT_EDGES = [10, 26.5, 29.5, 45]
# Threshold percentile chosen on the calibration seeds (src/evaluate.py); a test keeps it in step.
PERCENTILE = 95
# What a threshold is conditioned on; "none" is the fixed-threshold baseline.
CONDITIONING = {"load_ambient": ["load_bin", "ambient_bin"], "load": ["load_bin"], "none": []}
# Same roles and values as the dashboard tokens in docs/styles.css.
SERIES, CONTEXT, ALERT, GRID = "#33375c", "#7d8298", "#d03b3b", "#e6e7ef"


def flat_sensor(values, times, minimum=6):
    """Retrospective quality flag for an exact plateau; never bridge missing hours."""
    breaks = values.ne(values.shift()) | times.diff().ne(pd.Timedelta(hours=1))
    groups = breaks.cumsum()
    return values.notna() & groups.map(groups.value_counts()).ge(minimum)


def derive(frame):
    d = frame.rename(columns=TAG_TO_SIGNAL)
    d["t"] = pd.to_datetime(d["logical_hour"])
    for key in SIGNALS:
        d[key] = pd.to_numeric(d[key], errors="raise")
    order = ["t"] + [key for key in ("source_file", "source_line") if key in d]
    d = d.sort_values(order, kind="stable").reset_index(drop=True)
    current = d[[f"phase_current_{phase}" for phase in "abc"]]
    voltage = d[[f"phase_voltage_{phase}" for phase in ["ab", "bc", "ca"]]]
    d["mean_current_a"] = current.mean(axis=1)
    d["mean_voltage_v"] = voltage.mean(axis=1)
    generating = (d.active_power_kw > 0) & (d.mean_current_a > 0) & (d.mean_voltage_v > 0) & (d.frequency_hz > 0)
    stopped = (d.active_power_kw == 0) & (d.mean_current_a == 0) & (d.mean_voltage_v == 0) & (d.frequency_hz == 0)
    d["state"] = np.select([generating, stopped], ["generating", "stopped"], default="intermediate")
    d["current_spread_pct"] = 100 * (current.max(axis=1) - current.min(axis=1)) / d.mean_current_a.replace(0, np.nan)
    d["voltage_spread_pct"] = 100 * (voltage.max(axis=1) - voltage.min(axis=1)) / d.mean_voltage_v.replace(0, np.nan)
    d["winding_rise_c"] = d[[f"winding_temperature_{p}_c" for p in "abc"]].mean(axis=1) - d.room_temperature_c
    d["sensor_flat"] = flat_sensor(d.bearing_temperature_b_c, d.t)
    steady = generating.copy()
    for lag in (1, 2, 3):
        steady &= generating.shift(lag, fill_value=False) & d.t.sub(d.t.shift(lag)).eq(pd.Timedelta(hours=lag))
    d["steady_generation"] = steady
    d["load_bin"] = pd.cut(d.active_power_kw, LOAD_EDGES, labels=False, include_lowest=True)
    d["ambient_bin"] = pd.cut(d.room_temperature_c, AMBIENT_EDGES, labels=False, include_lowest=True)
    return d


def apply_reference(d, cutoff, minimum=30, percentile=PERCENTILE, conditioning="load_ambient"):
    """Thresholds from observations before cutoff only, one set per conditioning cell."""
    keys = CONDITIONING[conditioning]
    out = d.copy()
    # Cell code: -1 marks observations outside every band; "none" puts everything in cell 0.
    cell = pd.Series(0, index=out.index)
    for key in keys:
        cell = cell * 100 + out[key].fillna(-1e6)
    cell = cell.where(cell >= 0, -1).astype(int)
    usable = (out.t < cutoff) & out.steady_generation & ~out.sensor_flat & cell.ge(0)
    grouped = out.loc[usable, METRICS].groupby(cell[usable])
    counts = grouped.size()
    admitted = counts[counts >= minimum].index
    medians, uppers = grouped.median().loc[admitted], grouped.quantile(percentile / 100).loc[admitted]
    out["reference_count"] = cell.map(counts.loc[admitted]).fillna(0).astype(int)
    for metric in METRICS:
        out[metric + "_median"] = cell.map(medians[metric])
        out[metric + "_threshold"] = cell.map(uppers[metric])
    cells = []
    for code in admitted:
        entry = {key: int(code // 100 ** (len(keys) - 1 - index) % 100) for index, key in enumerate(keys)}
        entry["n"] = int(counts[code])
        for metric in METRICS:
            entry[metric + "_median"] = float(medians.at[code, metric])
            entry[metric + "_threshold"] = float(uppers.at[code, metric])
        cells.append(entry)
    out["eligible"] = out.steady_generation & ~out.sensor_flat & out.reference_count.ge(minimum)
    for metric in METRICS:
        out[metric + "_residual"] = out[metric] - out[metric + "_median"]
        out[metric + "_high"] = out.eligible & out[metric].gt(out[metric + "_threshold"])
    out["joint_high"] = out.winding_rise_c_high & out.current_spread_pct_high
    return out, cells


def detect(d, cutoff, percentile=PERCENTILE, conditioning="load_ambient", on_delay=ON_DELAY_HOURS, deadband=DEADBAND):
    """Thresholds plus alarm states. Nothing here reads the event list."""
    out, cells = apply_reference(d, cutoff, percentile=percentile, conditioning=conditioning)
    return annunciate(out, on_delay=on_delay, deadband=deadband), cells


def event_windows(truth):
    """Ground-truth windows used only to score the alerts, never to compute them."""
    return [(pd.Timestamp(e["ramp_start"]), pd.Timestamp(e["trip_time"]),
             pd.Timestamp(e["trip_time"]) + pd.Timedelta(hours=e["shutdown_hours"]), e) for e in truth["events"]]


def first_lead(ramp, trip, state):
    active = ramp[state]
    return float((trip - active.t.min()).total_seconds() / 3600) if len(active) else None


def score_events(d, truth):
    rows = []
    for start, trip, _, event in event_windows(truth):
        ramp = d[(d.t >= start) & (d.t < trip)]
        lead = first_lead(ramp, trip, ramp.alarm_high)
        last_day = ramp[(ramp.t >= trip - pd.Timedelta(hours=24)) & ramp.eligible]
        rows.append({**event, "eligible_hours": int(ramp.eligible.sum()),
                     "alarm_high_hours": int(ramp.alarm_high.sum()),
                     "detected": lead is not None, "lead_hours": lead,
                     "lead_hours_any_priority": first_lead(ramp, trip, ramp.priority > 0),
                     "winding_rise_c_residual_last_24h": float(last_day.winding_rise_c_residual.median()) if len(last_day) else None,
                     "current_spread_pct_residual_last_24h": float(last_day.current_spread_pct_residual.median()) if len(last_day) else None})
    return rows


def normal_operation(d, truth, ref_end):
    """Hours after the reference period that lie outside every degradation ramp and trip stop."""
    mask = d.t >= ref_end
    for start, _, restart, _ in event_windows(truth):
        mask &= ~((d.t >= start) & (d.t < restart))
    return mask


def figure_save(fig, path):
    fig.text(.01, .006, "Datos sintéticos", fontsize=8, color=CONTEXT)
    fig.tight_layout(rect=[0, .03, 1, 1])
    fig.savefig(path, dpi=145, metadata={"Software": "Synthetic SCADA portfolio"})
    plt.close(fig)


def make_figures(d, ref_end, truth, root):
    windows = event_windows(truth)
    normal = d[(d.t < ref_end) & d.eligible]
    recent = pd.concat([d[(d.t >= trip - pd.Timedelta(hours=48)) & (d.t < trip) & d.eligible] for _, trip, _, _ in windows])
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": CONTEXT, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True})
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, y, ylabel in zip(axes, ["mean_current_a", "guide_opening_a_pct", "winding_rise_c"],
                             ["Corriente media (A)", "Apertura del distribuidor (%)", "Elevación térmica (°C)"]):
        ax.scatter(normal.active_power_kw, normal[y], s=5, alpha=.18, color=CONTEXT, rasterized=True, label="Período de referencia")
        ax.scatter(recent.active_power_kw, recent[y], s=12, color=ALERT, alpha=.75, label="48 h previas a cada disparo")
        ax.set(xlabel="Potencia activa (kW)", ylabel=ylabel)
    axes[0].legend(fontsize=8)
    fig.suptitle("Relaciones con la carga: referencia frente a las horas previas a los disparos")
    figure_save(fig, root / "01_physical_relationships.png")

    # Daily medians summarize retained observations, not replacement rows in processed.
    daily = d[d.eligible].set_index("t")[[m + "_residual" for m in METRICS]].resample("D").median()
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    for ax, metric, label in zip(axes, METRICS, LABELS):
        ax.plot(daily.index, daily[metric + "_residual"], color=SERIES, lw=1.2)
        ax.axvspan(d.t.min(), ref_end, alpha=.10, color=CONTEXT, label="Período de referencia")
        for index, (_, trip, _, _) in enumerate(windows):
            ax.axvline(trip, color=ALERT, lw=1.2, label="Disparo" if not index else None)
        ax.axhline(0, color=CONTEXT, lw=.6)
        ax.set_ylabel("Residual\n" + label.replace("(%)", "(pp)"))
    axes[0].legend(fontsize=8, loc="upper left")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.suptitle("Mediana diaria del residual frente a carga y ambiente similares")
    figure_save(fig, root / "02_conditioned_history.png")

    fig, axes = plt.subplots(2, len(windows), figsize=(3.3 * len(windows) + 1, 6.2), sharex="col", sharey="row", squeeze=False)
    for column, (start, trip, _, event) in enumerate(windows):
        view = d[(d.t >= start - pd.Timedelta(hours=24)) & (d.t < trip)]
        hours = (view.t - trip).dt.total_seconds() / 3600
        for row, (metric, label) in enumerate(zip(METRICS[:2], LABELS[:2])):
            ax = axes[row][column]
            ax.plot(hours, view[metric].where(view.eligible), color=SERIES, lw=1.4, label="Indicador")
            ax.plot(hours, view[metric + "_threshold"].where(view.eligible), color=CONTEXT, lw=1.2, ls="--", label=f"Umbral P{PERCENTILE} de su celda")
            alerts = view.alarm_high.to_numpy()
            ax.scatter(hours[alerts], view[metric][alerts], color=ALERT, s=14, zorder=3, label="Alarma de prioridad alta")
            ax.axvline(-event["ramp_hours"], color=CONTEXT, lw=.8, ls=":")
            if not column:
                ax.set_ylabel(label)
        axes[0][column].set_title(f"Evento {event['id']} · severidad {event['severity']:.2f}", fontsize=10)
        axes[1][column].set_xlabel("Horas respecto del disparo")
    axes[0][0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Indicadores y umbrales antes de cada disparo (línea punteada: inicio de la rampa)")
    figure_save(fig, root / "03_pre_event_windows.png")

    fig, axes = plt.subplots(2, 1, figsize=(11, 7))
    calendar = pd.date_range(d.t.min().normalize(), d.t.max().normalize(), freq="D")
    counts = d.groupby(d.t.dt.normalize()).size().reindex(calendar, fill_value=0)
    axes[0].plot(counts.index, counts.values, color=SERIES, lw=1)
    axes[0].axhline(24, color=CONTEXT, lw=.8)
    axes[0].set(ylabel="Horas sin ambigüedad por día", ylim=(14, 25))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    frozen = d[d.sensor_flat]
    if not frozen.empty:
        lo, hi = frozen.t.min(), frozen.t.max()
        view = d[(d.t >= lo - pd.Timedelta(hours=18)) & (d.t <= hi + pd.Timedelta(hours=18))]
        for key, label, color in [("bearing_temperature_a_c", "Cojinete A (G1_TB_A)", "#2a78d6"),
                                  ("bearing_temperature_b_c", "Cojinete B (G1_TB_B)", "#eb6834"),
                                  ("room_temperature_c", "Ambiente (SM_TAMB)", CONTEXT)]:
            axes[1].plot(view.t, view[key], label=label, color=color)
        axes[1].axvspan(lo, hi, alpha=.12, color=CONTEXT, label="Lectura congelada detectada")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    axes[1].set_ylabel("Temperatura (°C)")
    axes[1].legend(fontsize=8, ncol=2)
    fig.suptitle("Cobertura diaria y lectura congelada de un sensor")
    figure_save(fig, root / "04_quality_and_sensor.png")


def analyze(root, figures=True):
    root = Path(root)
    truth = json.loads((root / "data/synthetic_scenario.json").read_text(encoding="utf-8"))
    start, ref_end = pd.Timestamp(truth["start"]), pd.Timestamp(truth["reference_end_exclusive"])
    source = pd.read_csv(root / "data/processed/scada.csv", keep_default_na=False)
    logged = source[(source.record_type == "event") & (source.event_message == TRIP_MESSAGE)].logical_hour
    if sorted(pd.to_datetime(logged)) != sorted(pd.Timestamp(e["trip_time"]) for e in truth["events"]) or not len(logged):
        raise ValueError("Synthetic event anchor is missing or inconsistent.")
    review = source.requires_review.astype(str).str.lower().eq("true")
    # Selection for statistics only: all source rows remain in the processed CSV.
    selected = source[(source.record_type == "measurement") & ~review]
    derived = derive(selected)
    d, cells = detect(derived, ref_end)
    events = score_events(d, truth)
    end = start + pd.Timedelta(hours=truth["expected_hours"])
    normal = normal_operation(d, truth, ref_end)
    periods = {"reference": (d.t < ref_end, start, ref_end), "normal_operation": (normal, ref_end, end)}
    summaries = []
    for name, (mask, lo, hi) in periods.items():
        part = d[mask & d.eligible]
        entry = {"period": name, "start_inclusive": lo.isoformat(), "end_exclusive": hi.isoformat(),
                 "available_hours": int(mask.sum()), "eligible_hours": len(part),
                 "joint_high_hours": int(part.joint_high.sum()), "alarm_high_hours": int(part.alarm_high.sum())}
        for metric in METRICS:
            entry[metric + "_median"] = float(part[metric].median()) if len(part) else None
            entry[metric + "_p99"] = float(part[metric].quantile(.99)) if len(part) else None
        summaries.append(entry)
    # Same thresholds with and without deadband: the difference is the repeated activations it removes.
    plain, _ = detect(derived, ref_end, deadband=NO_DEADBAND)
    alarms = {
        "settings": {"percentile": PERCENTILE, "conditioning": "load_ambient", "on_delay_hours": ON_DELAY_HOURS,
                     "off_delay_hours": OFF_DELAY_HOURS, "deadband": DEADBAND},
        "after_reference": alarm_kpis(d, d.t >= ref_end),
        "after_reference_without_deadband": alarm_kpis(plain, plain.t >= ref_end),
        "normal_operation": alarm_kpis(d, normal),
    }
    raw_measurements = source[source.record_type == "measurement"]
    summary = {
        "synthetic_only": True, "seed": truth["seed"], "reference_end_exclusive": ref_end.isoformat(),
        "source_rows": len(source), "selected_measurements": len(d),
        "measurement_hours_missing": truth["expected_hours"] - raw_measurements.logical_hour.nunique(),
        "state_counts_selected": {k: int(v) for k, v in d.state.value_counts().items()},
        "sensor_flat_hours": int(d.sensor_flat.sum()), "reference_cells": len(cells),
        "generating_hours_without_reference": int((d.steady_generation & d.reference_count.eq(0)).sum()),
        "events_total": len(events), "events_detected": sum(e["detected"] for e in events),
        "periods": summaries, "events": events, "alarms": alarms,
    }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json(reports / "analysis_summary.json", summary)
    pd.DataFrame(cells).to_csv(reports / "historical_reference.csv", index=False, lineterminator="\n")
    pd.DataFrame(summaries).to_csv(reports / "period_comparison.csv", index=False, lineterminator="\n")
    pd.DataFrame(events).to_csv(reports / "event_detection.csv", index=False, lineterminator="\n")
    if figures:
        make_figures(d, ref_end, truth, reports)
    write_report(root, summary)
    return summary


def write_report(root, s):
    q = json.loads((root / "reports/quality_summary.json").read_text(encoding="utf-8"))
    def number(value, digits=2):
        return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")
    periods = "\n".join(
        f"| {p['period']} | {p['eligible_hours']} | {number(p['winding_rise_c_median'])} | {number(p['current_spread_pct_median'])} | {number(p['current_spread_pct_p99'])} | {number(p['voltage_spread_pct_median'])} | {p['alarm_high_hours']} |"
        for p in s["periods"]
    )
    events = "\n".join(
        f"| {e['id']} | {e['trip_time'].replace('T', ' ')[:16]} | {e['ramp_hours']} | {number(e['severity'])} | {number(e['winding_rise_delta_c'], 1)} | {number(e['current_spread_delta_pct'], 1)} | {'sí' if e['detected'] else 'no'} | {number(e['lead_hours'], 0)} | {number(e['lead_hours_any_priority'], 0)} |"
        for e in s["events"]
    )
    a = s["alarms"]
    setting, kpi, plain = a["settings"], a["after_reference"], a["after_reference_without_deadband"]
    points = "\n".join(
        f"| `{p['tag']}` | {p['description']} | {p['priority']} | {p['activations']} | {number(p['activations_per_1000h'])} | {number(p['median_duration_hours'], 0)} | {p['fleeting']} | {p['stale']} | {p['repeats']} |"
        for p in kpi["points"]
    )
    report = f"""# Análisis de una unidad hidroeléctrica sintética

Año demo generado con la semilla {s['seed']}. Los datos son sintéticos.

## Calidad y conservación

Se conservan {q['rows']} filas: {q['measurements']} mediciones y {q['events']} eventos.
Hay {q['multiple_hours']} horas con mediciones contradictorias, {q['shifted_rows']} registros adelantados dos segundos
y {s['measurement_hours_missing']} horas sin medición. No se interpola ni se deduplica: la selección estadística
({s['selected_measurements']} mediciones) excluye las horas ambiguas y los eventos, y el archivo procesado queda intacto.
Una lectura congelada del cojinete B ({s['sensor_flat_hours']} horas idénticas seguidas) excluye esas horas de la comparación.

## Referencia y umbrales

- Generación estable: potencia, corriente, tensión y frecuencia positivas en la hora actual y las tres anteriores.
- Referencia: los primeros 180 días, sin episodios de degradación. Se agrupa por bandas de potencia
  ({'–'.join(str(v) for v in LOAD_EDGES)} kW) y de ambiente ({'–'.join(str(v).replace('.', ',') for v in AMBIENT_EDGES)} °C), con al menos
  30 observaciones por celda: {s['reference_cells']} celdas admitidas, {s['generating_hours_without_reference']} horas sin soporte.
- Indicadores: elevación térmica = media de devanados − ambiente; dispersión = 100 × (máx − mín) / media de las tres fases.
- Umbral: percentil {setting['percentile']} del indicador en su celda de referencia.

| Período | Horas elegibles | Elevación térmica mediana °C | Dispersión de corriente mediana % | Dispersión de corriente P99 % | Dispersión de tensión mediana % | Horas con alarma alta |
|---|---:|---:|---:|---:|---:|---:|
{periods}

## Alarmas

La lógica usa los conceptos de gestión de alarmas de ISA-18.2, adaptados a datos horarios:

- **Retardo de activación**: {setting['on_delay_hours']} horas seguidas sobre el umbral.
- **Banda muerta**: la alarma se repone al bajar de umbral − {number(setting['deadband']['winding_rise_c'], 1)} °C (térmica)
  o umbral − {number(setting['deadband']['current_spread_pct'], 1)} pp (dispersión), para que no oscile alrededor del umbral.
- **Prioridad**: baja si un solo indicador está en alarma; alta si ambos lo están a la vez.

Desde el fin de la referencia ({kpi['eligible_hours']} horas elegibles, episodios incluidos):

| Tag | Alarma | Prioridad | Activaciones | Por 1000 h | Duración mediana h | Fugaces (≤ 2 h) | Persistentes (≥ 24 h) | Reactivaciones (≤ 6 h) |
|---|---|---|---:|---:|---:|---:|---:|---:|
{points}

Sin banda muerta, las mismas alarmas se activan {plain['activations']} veces y se reactivan {plain['repeats']} veces
en menos de 6 h; con banda muerta, {kpi['activations']} y {kpi['repeats']}.
Fuera de los episodios hay {a['normal_operation']['activations']} activaciones en {a['normal_operation']['eligible_hours']} horas
({a['normal_operation']['activations_by_priority']['alta']} de prioridad alta).

## Episodios de degradación del año demo

El generador sortea el momento y el tamaño de cada episodio; la regla no los conoce.
La alarma de prioridad alta detecta {s['events_detected']} de {s['events_total']}.
El percentil y el retardo se fijaron con otras semillas; el desempeño sobre 100 años está en [evaluation.md](evaluation.md).

| Evento | Disparo | Rampa h | Severidad | Δ térmico °C | Δ dispersión pp | Detectado | Anticipación h (alta) | Anticipación h (cualquiera) |
|---:|---|---:|---:|---:|---:|---|---:|---:|
{events}

Los incrementos (Δ) son los valores alcanzados al final de la rampa.

## Figuras

![Relaciones con la carga](01_physical_relationships.png)

![Residuales diarios](02_conditioned_history.png)

![Indicadores antes de cada disparo](03_pre_event_windows.png)

![Calidad y sensor](04_quality_and_sensor.png)

Detalle numérico: `analysis_summary.json`, `historical_reference.csv`, `period_comparison.csv`, `event_detection.csv`.
"""
    (root / "reports/analysis.md").write_text(report, encoding="utf-8")
