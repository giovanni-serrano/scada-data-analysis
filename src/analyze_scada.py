"""Load-conditioned descriptive analysis with a frozen early reference period."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import SIGNALS, write_json

METRICS = ["winding_rise_c", "current_spread_pct", "voltage_spread_pct"]
LABELS = ["Elevación térmica (°C)", "Dispersión de corriente (%)", "Dispersión de tensión (%)"]


def sustained(mask, times, length=3):
    """Mark the third and subsequent consecutive positive hourly observations."""
    result, count, previous = [], 0, None
    for flag, time in zip(mask, times):
        consecutive = previous is not None and time - previous == pd.Timedelta(hours=1)
        count = count + 1 if flag and consecutive else int(bool(flag))
        result.append(count >= length)
        previous = time
    return pd.Series(result, index=mask.index, dtype=bool)


def flat_sensor(values, times, minimum=6):
    """Retrospective quality flag for an exact plateau; never bridge missing hours."""
    breaks = values.ne(values.shift()) | times.diff().ne(pd.Timedelta(hours=1))
    groups = breaks.cumsum()
    return values.notna() & groups.map(groups.value_counts()).ge(minimum)


def derive(frame):
    d = frame.copy()
    d["t"] = pd.to_datetime(d["logical_hour"])
    for key in SIGNALS:
        d[key] = pd.to_numeric(d[key], errors="raise")
    d = d.sort_values(["t", "source_file", "source_line"], kind="stable").reset_index(drop=True)
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
    d["load_bin"] = pd.cut(d.active_power_kw, [0, 200, 400, 600, 900], labels=False, include_lowest=True)
    d["ambient_bin"] = pd.cut(d.room_temperature_c, [10, 18, 26, 40], labels=False, include_lowest=True)
    return d


def apply_reference(d, cutoff, minimum=30):
    baseline = d[(d.t < cutoff) & d.steady_generation & ~d.sensor_flat]
    cells = []
    out = d.copy()
    for metric in METRICS:
        out[metric + "_median"] = np.nan
        out[metric + "_p99"] = np.nan
    out["reference_count"] = 0
    for (load, ambient), group in baseline.groupby(["load_bin", "ambient_bin"]):
        if len(group) < minimum:
            continue
        match = out.load_bin.eq(load) & out.ambient_bin.eq(ambient)
        cell = {"load_bin": int(load), "ambient_bin": int(ambient), "n": len(group)}
        out.loc[match, "reference_count"] = len(group)
        for metric in METRICS:
            median, upper = group[metric].median(), group[metric].quantile(.99)
            cell[metric + "_median"], cell[metric + "_p99"] = float(median), float(upper)
            out.loc[match, metric + "_median"] = median
            out.loc[match, metric + "_p99"] = upper
        cells.append(cell)
    out["eligible"] = out.steady_generation & ~out.sensor_flat & out.reference_count.ge(minimum)
    for metric in METRICS:
        out[metric + "_residual"] = out[metric] - out[metric + "_median"]
        out[metric + "_high"] = out.eligible & out[metric].gt(out[metric + "_p99"])
    out["joint_high"] = out.winding_rise_c_high & out.current_spread_pct_high
    out["persistent_alert"] = sustained(out.joint_high, out.t)
    return out, cells


def figure_save(fig, path):
    fig.text(.01, .006, "Datos completamente sintéticos · fines educativos · sin mecanismo de fallo validado", fontsize=8, color="#444444")
    fig.tight_layout(rect=[0, .03, 1, 1])
    fig.savefig(path, dpi=145, metadata={"Software": "Synthetic SCADA portfolio"})
    plt.close(fig)


def make_figures(d, ref_end, event, ramp_start, root):
    normal = d[(d.t < ref_end) & d.eligible]
    recent = d[(d.t >= event - pd.Timedelta(hours=72)) & (d.t < event) & d.eligible]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, y, ylabel in zip(axes, ["mean_current_a", "guide_opening_a_pct", "winding_rise_c"],
                             ["Corriente media (A)", "Apertura hidráulica (%)", "Elevación térmica (°C)"]):
        ax.scatter(normal.active_power_kw, normal[y], s=5, alpha=.14, color="#226988", rasterized=True, label="Referencia histórica")
        ax.scatter(recent.active_power_kw, recent[y], s=12, color="#c45126", alpha=.75, label="72 h previas al evento")
        ax.set(xlabel="Potencia activa (kW)", ylabel=ylabel)
    axes[0].legend(fontsize=8)
    fig.suptitle("¿Qué relaciones dependen de la carga y cuál cambia antes del evento?")
    figure_save(fig, root / "01_physical_relationships.png")

    # Daily medians summarize retained observations, not replacement rows in processed.
    daily = d[d.eligible].set_index("t")[[m + "_residual" for m in METRICS]].resample("D").median()
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    for ax, metric, label in zip(axes, METRICS, LABELS):
        ax.plot(daily.index, daily[metric + "_residual"], color="#226988", lw=1)
        ax.axvspan(d.t.min(), ref_end, alpha=.10, color="#226988", label="Período de referencia")
        ax.axvline(event, color="#c45126", ls="--", label="Evento artificial")
        ax.axhline(0, color="gray", lw=.6)
        ax.set_ylabel("Residual\n" + label.replace("(%)", "(pp)"))
    axes[0].legend(fontsize=8, loc="upper left")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    fig.suptitle("¿Persiste el cambio al comparar carga y ambiente similares?")
    figure_save(fig, root / "02_conditioned_history.png")

    window = d[(d.t >= event - pd.Timedelta(hours=120)) & (d.t <= event + pd.Timedelta(hours=12))].copy()
    window["hours_to_event"] = (window.t - event).dt.total_seconds() / 3600
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    for ax, metric, label in zip(axes, METRICS, LABELS):
        valid = window.eligible
        ax.plot(window.hours_to_event, window[metric].where(valid), color="#226988", label="Observado elegible")
        ax.plot(window.hours_to_event, window[metric + "_p99"].where(valid), color="#76659a", ls="--", label="P99 histórico por carga/ambiente")
        for start, alpha in [(-72, .035), (-24, .055), (-6, .10)]:
            ax.axvspan(start, 0, color="#c45126", alpha=alpha)
        ax.axvline(0, color="#c45126", lw=1.4)
        alerts = window[window.persistent_alert]
        ax.scatter(alerts.hours_to_event, alerts[metric], color="#c45126", s=11, label="Alerta conjunta persistente")
        ax.set_ylabel(label)
    axes[0].legend(fontsize=8, loc="upper left")
    axes[-1].set(xlabel="Horas respecto del evento artificial (0)", xticks=[-120, -96, -72, -48, -24, -6, 0, 12])
    fig.suptitle("¿Cómo evolucionan las señales en las ventanas de 72, 24 y 6 horas?")
    figure_save(fig, root / "03_pre_event_windows.png")

    fig, axes = plt.subplots(2, 1, figsize=(11, 7))
    calendar = pd.date_range(d.t.min().normalize(), d.t.max().normalize(), freq="D")
    counts = d.groupby(d.t.dt.normalize()).size().reindex(calendar, fill_value=0)
    axes[0].plot(counts.index, counts.values, color="#226988", lw=.9)
    axes[0].axhline(24, color="gray", ls="--", lw=.8)
    axes[0].set(ylabel="Horas sin ambigüedad por día", ylim=(14, 25))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    frozen = d[d.sensor_flat]
    if not frozen.empty:
        lo, hi = frozen.t.min(), frozen.t.max()
        view = d[(d.t >= lo - pd.Timedelta(hours=18)) & (d.t <= hi + pd.Timedelta(hours=18))]
        for key, label in [("bearing_temperature_a_c", "Cojinete A"), ("bearing_temperature_b_c", "Cojinete B"), ("room_temperature_c", "Ambiente")]:
            axes[1].plot(view.t, view[key], label=label)
        axes[1].axvspan(lo, hi, alpha=.12, color="#c45126", label="Meseta exacta detectada")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    axes[1].set_ylabel("Temperatura (°C)")
    axes[1].legend(fontsize=8, ncol=2)
    fig.suptitle("¿Qué problemas de calidad limitan la interpretación?")
    figure_save(fig, root / "04_quality_and_sensor.png")


def analyze(root, figures=True):
    root = Path(root)
    truth = json.loads((root / "data/synthetic_scenario.json").read_text(encoding="utf-8"))
    event = pd.Timestamp(truth["synthetic_event_time"])
    ref_end = pd.Timestamp(truth["start"]) + pd.Timedelta(days=240)
    ramp_start = pd.Timestamp(truth["current_ramp_start"])
    source = pd.read_csv(root / "data/processed/scada.csv", keep_default_na=False)
    messages = source[(source.record_type == "event") & (source.event_message == "synthetic_shutdown")]
    if len(messages) != 1 or pd.Timestamp(messages.iloc[0].logical_hour) != event:
        raise ValueError("Synthetic event anchor is missing or inconsistent.")
    review = source.requires_review.astype(str).str.lower().eq("true")
    # Selection for statistics only: all source rows remain in the processed CSV.
    selected = source[(source.record_type == "measurement") & ~review]
    d, cells = apply_reference(derive(selected), ref_end)
    periods = {
        "reference": (pd.Timestamp(truth["start"]), ref_end),
        "normal_holdout": (ref_end, ramp_start),
        "pre_event_72h": (event - pd.Timedelta(hours=72), event),
        "pre_event_24h": (event - pd.Timedelta(hours=24), event),
        "pre_event_6h": (event - pd.Timedelta(hours=6), event),
    }
    summaries = []
    for name, (start, end) in periods.items():
        full = d[(d.t >= start) & (d.t < end)]
        part = full[full.eligible]
        entry = {"period": name, "start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
                 "calendar_hours": int((end - start).total_seconds() / 3600), "available_hours": len(full),
                 "eligible_hours": len(part), "joint_high_hours": int(part.joint_high.sum()),
                 "persistent_alert_hours": int(part.persistent_alert.sum())}
        for metric in METRICS:
            entry[metric + "_median"] = float(part[metric].median()) if len(part) else None
            entry[metric + "_residual_median"] = float(part[metric + "_residual"].median()) if len(part) else None
        summaries.append(entry)
    pre = d[(d.t >= ramp_start) & (d.t < event) & d.persistent_alert]
    first = pre.t.min() if len(pre) else None
    raw_measurements = source[source.record_type == "measurement"]
    summary = {
        "synthetic_only": True, "synthetic_event_time": event.isoformat(), "reference_end_exclusive": ref_end.isoformat(),
        "source_rows": len(source), "selected_measurements": len(d),
        "measurement_hours_missing": truth["expected_hours"] - raw_measurements.logical_hour.nunique(),
        "state_counts_selected": {k: int(v) for k, v in d.state.value_counts().items()},
        "sensor_flat_hours": int(d.sensor_flat.sum()), "reference_cells": len(cells),
        "generating_hours_without_reference": int((d.steady_generation & d.reference_count.eq(0)).sum()),
        "synthetic_change_detected": first is not None,
        "first_persistent_pre_event_alert": first.isoformat() if first is not None else None,
        "lead_hours": float((event - first).total_seconds() / 3600) if first is not None else None,
        "periods": summaries,
    }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json(reports / "analysis_summary.json", summary)
    pd.DataFrame(cells).to_csv(reports / "historical_reference.csv", index=False, lineterminator="\n")
    pd.DataFrame(summaries).to_csv(reports / "window_comparison.csv", index=False, lineterminator="\n")
    if figures:
        make_figures(d, ref_end, event, ramp_start, reports)
    write_report(root, summary)
    return summary


def write_report(root, s):
    q = json.loads((root / "reports/quality_summary.json").read_text(encoding="utf-8"))
    def number(value):
        return "sin soporte" if value is None else f"{value:.2f}"
    table = "\n".join(
        f"| {p['period']} | {p['eligible_hours']}/{p['calendar_hours']} | {number(p['winding_rise_c_residual_median'])} | {number(p['current_spread_pct_median'])} | {number(p['voltage_spread_pct_median'])} | {p['persistent_alert_hours']} |"
        for p in s["periods"]
    )
    report = f"""# Análisis de una unidad hidroeléctrica ficticia

Todos los datos de este informe son completamente sintéticos y educativos.
El evento `{s['synthetic_event_time']}` y sus señales previas se inyectaron artificialmente.
No representan un mecanismo físico de fallo validado.

## Calidad y conservación

Se conservan {q['rows']} filas: {q['measurements']} mediciones y {q['events']} eventos.
Hay {q['multiple_hours']} horas con mediciones alternativas, {q['shifted_rows']} registros adelantados dos segundos
y {s['measurement_hours_missing']} horas sin medición. Los eventos no rellenan mediciones faltantes.
La selección estadística contiene {s['selected_measurements']} mediciones, sin modificar processed.
Se excluyen de esa selección todas las alternativas de horas ambiguas y los eventos.
Las observaciones a hasta tres segundos antes de la hora reciben hora lógica derivada;
la fecha y hora originales permanecen intactas. No hay interpolación ni deduplicación.
La meseta exacta de un sensor comprende {s['sensor_flat_hours']} horas. Es una bandera retrospectiva
de calidad (mínimo seis horas contiguas), no evidencia de una avería térmica.

## Referencia y comparación

Estados: generación cuando potencia, corriente, tensión y frecuencia son positivas;
parada cuando las cuatro son cero; combinaciones restantes son intermedias.
Se requieren la observación actual y tres horas previas consecutivas en generación.
Las primeras 240 jornadas forman la referencia, cerrada antes del cambio artificial.
Se usan cuatro bandas de potencia (0–200–400–600–900 kW) y tres de ambiente
(10–18–26–40 °C), con al menos 30 observaciones por celda. Hay {s['reference_cells']} celdas admitidas.
Las horas de generación estable sin soporte histórico son {s['generating_hours_without_reference']}.
Se excluye del análisis comparativo la observación horaria completa cuando se activa
la bandera de meseta exacta del sensor de cojinete B; no solo su columna.
También se excluyen las horas sin soporte histórico. Las filas originales permanecen en processed.

Elevación térmica = media de los tres devanados menos ambiente.
Dispersión de fases = 100 × (máximo − mínimo) / media; no es una medida normativa de secuencia negativa.
Residual = observado menos mediana de su celda histórica.
Una alerta requiere elevación térmica y dispersión de corriente superiores a sus P99 históricos
durante tres observaciones horarias consecutivas. La tensión se utiliza como contexto adicional.
La regla se calcula sobre todas las observaciones; el calendario del evento solo ancla la evaluación.
El registro del evento debe coincidir con el manifiesto sintético o el análisis se detiene.

| Período | Horas elegibles/calendario | Residual térmico mediano °C | Dispersión corriente mediana % | Dispersión tensión mediana % | Horas con alerta persistente |
|---|---:|---:|---:|---:|---:|
{table}

Las ventanas son [evento − duración, evento), se solapan y excluyen la parada en el instante del evento.
La primera alerta persistente dentro del cambio inyectado aparece en
`{s['first_persistent_pre_event_alert']}`, con {s['lead_hours']} horas de antelación.
Las horas de alerta de referencia y del tramo normal posterior se muestran para contextualizar
la especificidad de la regla. La referencia es una evaluación dentro de muestra; el tramo normal posterior
sí queda fuera del ajuste. Las horas sucesivas están correlacionadas y no equivalen a ensayos independientes.

## Lectura de las figuras

![Relaciones físicas](01_physical_relationships.png)

La corriente y la apertura aumentan con la carga por construcción. La temperatura también responde al ambiente
y a una dinámica de primer orden. Las 72 horas previas muestran una elevación térmica adicional.

![Comparación condicionada](02_conditioned_history.png)

Las medianas diarias de residuales permiten separar variaciones de carga de cambios persistentes.
Son agregados de presentación; no sustituyen las observaciones conservadas en processed.

![Ventanas previas](03_pre_event_windows.png)

Las zonas sombreadas identifican 72, 24 y 6 horas. Las líneas de P99 corresponden a la carga
y ambiente de cada observación, por lo que pueden cambiar de una hora a otra.

![Calidad y sensor](04_quality_and_sensor.png)

La cobertura muestra horas sin ambigüedad, incluidas las paradas. Su reducción puede deberse a huecos
o a exclusión de alternativas contradictorias. La meseta pertenece a un problema de sensor inventado.

## Alcance

La detección demuestra trazabilidad y una comparación interpretable en un escenario diseñado para ello.
No estima precisión en una instalación, causa raíz ni probabilidad de fallo. No hay validación ciega:
el diseñador conoce las inyecciones. Las bandas discretas, la inercia térmica, el único año y el único evento
limitan la interpretación. El modelo no reproduce protecciones, transitorios subhorarios, topología eléctrica
ni mantenimiento. Una evaluación de capacidad predictiva exigiría escenarios independientes y múltiples eventos.

Reproducción y definición del modelo: README.md de la carpeta del proyecto.
Detalle numérico: `analysis_summary.json`, `historical_reference.csv`, `window_comparison.csv`.
"""
    (root / "reports/analysis.md").write_text(report, encoding="utf-8")
