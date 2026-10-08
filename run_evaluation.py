"""Run the blind multi-seed evaluation and write its tables, figures and report."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analyze_scada import ALERT, CONTEXT, GRID, SERIES, figure_save
from src.common import spanish as number, write_json
from src.evaluate import BASELINE, CALIBRATION_SEEDS, EVALUATION_SEEDS, MAX_FALSE_ALARMS_PER_1000H, METHODS, PRIMARY, evaluate

NAMES = {"load_ambient": "Condicionado por carga y ambiente", "load": "Condicionado solo por carga",
         "none": "Línea base: umbral fijo"}
# Categorical slots 1 and 2 of the dashboard palette, with a different marker each.
STYLE = {PRIMARY: ("#2a78d6", "o"), BASELINE: ("#eb6834", "s")}
INK = "#1e2030"


def percent(value):
    return "—" if value is None else number(100 * value, 0) + " %"


def interval(pair, scale=1, digits=2):
    return "—" if pair is None else f"[{number(scale * pair[0], digits)}; {number(scale * pair[1], digits)}]"


def figures(summary, reports):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "text.color": INK,
                         "axes.labelcolor": INK, "xtick.color": CONTEXT, "ytick.color": CONTEXT,
                         "axes.edgecolor": CONTEXT, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True})
    point = summary["operating_point"]
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    for method in (PRIMARY, BASELINE):
        color, marker = STYLE[method]
        rows = [row for row in summary["sensitivity"] if row["method"] == method]
        ax.scatter([row["false_alarms_per_1000h"] for row in rows], [100 * row["detection_rate"] for row in rows],
                   s=46, color=color, marker=marker, edgecolor="white", linewidth=1.2, label=NAMES[method], zorder=3)
        chosen = summary["evaluation"][method]
        low, high = chosen["ci95"]["detection_rate"]
        ax.errorbar(chosen["false_alarms_per_1000h"], 100 * chosen["detection_rate"],
                    yerr=[[100 * (chosen["detection_rate"] - low)], [100 * (high - chosen["detection_rate"])]],
                    color=color, lw=1.4, capsize=3, zorder=2)
        ax.annotate(f"P{point['percentile']}, {point['on_delay_hours']} h", (chosen["false_alarms_per_1000h"], 100 * chosen["detection_rate"]),
                    textcoords="offset points", xytext=(9, -4), fontsize=9, color=INK)
    ax.axvline(MAX_FALSE_ALARMS_PER_1000H, color=CONTEXT, lw=1, ls="--")
    ax.annotate("Límite usado al calibrar", (MAX_FALSE_ALARMS_PER_1000H, 3), textcoords="offset points", xytext=(-6, 0),
                ha="right", fontsize=8, color=CONTEXT)
    ax.set(xlabel="Falsas alarmas por 1000 h de operación normal", ylabel="Episodios detectados (%)", ylim=(0, 100))
    ax.legend(fontsize=9, loc="center right", frameon=False)
    fig.suptitle("Cada punto es una combinación de percentil y retardo; la barra es el IC 95 % del punto elegido", fontsize=10)
    figure_save(fig, reports / "05_operating_points.png")

    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    for method in (PRIMARY, BASELINE):
        color, marker = STYLE[method]
        rows = summary["evaluation"][method]["by_severity"]
        ax.plot(range(len(rows)), [100 * row["detection_rate"] if row["detection_rate"] is not None else np.nan for row in rows],
                color=color, marker=marker, lw=2, ms=7, markeredgecolor="white", label=NAMES[method])
    rows = summary["evaluation"][PRIMARY]["by_severity"]
    ax.set_xticks(range(len(rows)), [f"{number(row['severity_from'])}–{number(row['severity_to'])}\n{row['events']} episodios" for row in rows])
    ax.set(xlabel="Severidad del episodio (1 = incremento máximo simulado)", ylabel="Episodios detectados (%)", ylim=(0, 100))
    ax.legend(fontsize=9, loc="upper left", frameon=False)
    fig.suptitle("La detección crece con el tamaño del episodio", fontsize=10)
    figure_save(fig, reports / "06_detection_by_severity.png")

    leads = summary["lead_hours"]
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    ax.hist(leads, bins=np.arange(0, max(leads, default=12) + 12, 12), color=SERIES, edgecolor="white", linewidth=1.5)
    median = summary["evaluation"][PRIMARY]["lead_hours_median"]
    if median is not None:
        ax.axvline(median, color=ALERT, lw=1.6)
        ax.annotate(f"Mediana: {number(median, 0)} h", (median, ax.get_ylim()[1]), textcoords="offset points",
                    xytext=(6, -12), fontsize=9, color=INK)
    ax.set(xlabel="Horas entre la primera alarma alta y el disparo", ylabel="Episodios detectados")
    fig.suptitle("Anticipación de la alarma en los episodios detectados", fontsize=10)
    figure_save(fig, reports / "07_lead_time.png")


def report(summary):
    protocol, point, results = summary["protocol"], summary["operating_point"], summary["evaluation"]
    primary, difference = results[PRIMARY], summary["primary_minus_baseline"]
    main = "\n".join(
        f"| {NAMES[m]} | {percent(r['detection_rate'])} {interval(r['ci95']['detection_rate'], 100, 0)} | {r['detected']}/{r['events']} | "
        f"{number(r['false_alarms_per_1000h'])} {interval(r['ci95']['false_alarms_per_1000h'])} | {number(r['normal_time_in_alarm_pct'])} % | "
        f"{number(r['lead_hours_median'], 0)} {interval(r['ci95']['lead_hours_median'], 1, 0)} | "
        f"{number(r['lead_hours_p10'], 0)}–{number(r['lead_hours_p90'], 0)} |"
        for m, r in ((m, results[m]) for m in METHODS))
    low, high = difference["ci95"]["detection_rate"]
    if low > 0:
        verdict = "El intervalo excluye el cero: condicionar por carga y ambiente detecta más episodios que un umbral fijo."
    elif high < 0:
        verdict = "El intervalo excluye el cero: en este escenario el umbral fijo detecta más episodios."
    else:
        verdict = "El intervalo incluye el cero: con estos datos no se distingue una ventaja en detección."
    severity = "\n".join(
        f"| {number(a['severity_from'])}–{number(a['severity_to'])} | {a['events']} | {percent(a['detection_rate'])} | {percent(b['detection_rate'])} |"
        for a, b in zip(primary["by_severity"], results[BASELINE]["by_severity"]))
    grid = {(row["method"], row["percentile"], row["on_delay_hours"]): row for row in summary["sensitivity"]}
    sensitivity = "\n".join(
        f"| P{p} | {delay} | {percent(grid[PRIMARY, p, delay]['detection_rate'])} | {number(grid[PRIMARY, p, delay]['false_alarms_per_1000h'])} | "
        f"{number(grid[PRIMARY, p, delay]['lead_hours_median'], 0)} | {percent(grid[BASELINE, p, delay]['detection_rate'])} | "
        f"{number(grid[BASELINE, p, delay]['false_alarms_per_1000h'])} |"
        for p in protocol["grid"]["percentile"] for delay in protocol["grid"]["on_delay_hours"])
    calibration = "\n".join(
        f"| P{row['percentile']} | {row['on_delay_hours']} | {percent(row['detection_rate'])} | {number(row['false_alarms_per_1000h'])} |"
        for row in summary["calibration"])
    held, plain, any_priority = summary["alarm_review"]["with_deadband"], summary["alarm_review"]["without_deadband"], summary["any_priority"]
    points = "\n".join(
        f"| `{a['tag']}` | {a['priority']} | {a['activations']} | {number(1000 * a['activations'] / held['eligible_hours'])} | "
        f"{a['fleeting']} | {a['stale']} | {a['repeats']} | {b['repeats']} |"
        for a, b in zip(held["points"], plain["points"]))
    return f"""# Evaluación ciega de la regla de alarma

Los datos son sintéticos. Esta evaluación mide la regla sobre {len(protocol['evaluation_seeds'])} simulaciones de un año que no se usaron para ajustarla.

## Protocolo

1. Cada semilla genera un año con 2 a 4 episodios de degradación en momentos y tamaños sorteados.
2. Los umbrales de cada año salen de sus primeros 180 días. El detector no recibe la lista de episodios.
3. Con {len(protocol['calibration_seeds'])} semillas de calibración se eligió percentil y retardo con una regla fijada de antemano:
   la mayor detección con un máximo de {number(MAX_FALSE_ALARMS_PER_1000H, 0)} falsa alarma por 1000 h. Resultado: **P{point['percentile']} y {point['on_delay_hours']} h**.
4. Esa configuración se aplicó a {len(protocol['evaluation_seeds'])} semillas de evaluación distintas y se comparó con la verdad.

Un episodio cuenta como detectado si la alarma de prioridad alta está activa en algún momento entre el inicio de su rampa y el disparo.
Una falsa alarma es una activación fuera de las rampas y de las paradas posteriores.
Los intervalos son del 95 %, por remuestreo de años completos ({protocol['bootstrap_resamples']} repeticiones).

## Resultado

| Método | Detección [IC 95 %] | Episodios | Falsas alarmas por 1000 h [IC 95 %] | Horas normales en alarma | Anticipación mediana h [IC 95 %] | Anticipación P10–P90 h |
|---|---|---:|---|---:|---|---|
{main}

Diferencia entre el método condicionado y la línea base, con los mismos años:
detección {number(100 * difference['detection_rate'], 0)} puntos {interval(difference['ci95']['detection_rate'], 100, 0)},
falsas alarmas {number(difference['false_alarms_per_1000h'])} por 1000 h {interval(difference['ci95']['false_alarms_per_1000h'])}.
{verdict}

![Puntos de operación](05_operating_points.png)

## Detección según el tamaño del episodio

| Severidad | Episodios | Condicionado | Línea base |
|---|---:|---:|---:|
{severity}

![Detección por severidad](06_detection_by_severity.png)

![Anticipación](07_lead_time.png)

## Sensibilidad al percentil y al retardo

Sobre las semillas de evaluación. Esta tabla es informativa: no se usó para elegir la configuración.

| Percentil | Retardo h | Detección (condicionado) | Falsas alarmas / 1000 h | Anticipación mediana h | Detección (base) | Falsas alarmas / 1000 h (base) |
|---|---:|---:|---:|---:|---:|---:|
{sensitivity}

Tabla usada para elegir, con las semillas de calibración (método condicionado):

| Percentil | Retardo h | Detección | Falsas alarmas / 1000 h |
|---|---:|---:|---:|
{calibration}

## Revisión de alarmas (ISA-18.2)

Activaciones desde el fin de la referencia en los años de evaluación ({held['eligible_hours']} horas elegibles):

| Tag | Prioridad | Activaciones | Por 1000 h | Fugaces (≤ 2 h) | Persistentes (≥ 24 h) | Reactivaciones (≤ 6 h) | Reactivaciones sin banda muerta |
|---|---|---:|---:|---:|---:|---:|---:|
{points}

- Tasa total: {number(held['activations_per_hour'], 3)} activaciones por hora para esta unidad. La referencia habitual de ISA-18.2 y EEMUA 191
  es de hasta unas 12 por hora por operador para toda la planta.
- La banda muerta reduce las activaciones de {plain['activations']} a {held['activations']} y las reactivaciones de {plain['repeats']} a {held['repeats']}.
- El {percent(held['high_priority_share'])} de las activaciones es de prioridad alta (referencia habitual: en torno al 5 % en el nivel más alto).
- Si también se cuenta la prioridad baja como detección, se detecta el {percent(any_priority['detection_rate'])} de los episodios,
  con {number(any_priority['false_alarms_per_1000h'])} falsas alarmas por 1000 h: por eso la baja informa y la alta pide acción.

Los datos son horarios, así que los tiempos de la norma (segundos y minutos) están escalados a horas.
Referencias: [Alarm management by the numbers](https://www.chemengonline.com/alarm-management-numbers/) y
[Why should I use an alarm deadband](https://www.exida.com/Blog/why-should-i-use-an-alarm-deadband).

## Alcance

La evaluación es ciega respecto a cuándo ocurre cada episodio y a su tamaño, pero el mismo autor diseñó el generador
y el detector: el tipo de degradación (rampa lineal en temperatura y desbalance) es conocido. Los resultados describen
este escenario sintético y no una instalación real.

Detalle numérico: `evaluation_summary.json`, `evaluation_methods.csv`, `evaluation_sensitivity.csv`.
"""


def write_outputs(root, summary, with_figures=True):
    reports = Path(root) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    write_json(reports / "evaluation_summary.json", summary)
    methods = [{key: value for key, value in row.items() if key not in ("ci95", "by_severity")}
               | {f"{key}_ci95_{side}": bound for key, pair in row["ci95"].items() if pair for side, bound in zip(("low", "high"), pair)}
               for row in summary["evaluation"].values()]
    pd.DataFrame(methods).to_csv(reports / "evaluation_methods.csv", index=False, lineterminator="\n")
    pd.DataFrame(summary["sensitivity"]).to_csv(reports / "evaluation_sensitivity.csv", index=False, lineterminator="\n")
    if with_figures:
        figures(summary, reports)
    (reports / "evaluation.md").write_text(report(summary), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    total = len(CALIBRATION_SEEDS) + len(EVALUATION_SEEDS)
    done = []

    def progress(label, seed):
        done.append(seed)
        if len(done) % 20 == 0:
            print(f"{len(done)}/{total} simulated years ({label})...")

    result = evaluate(progress=progress)
    write_outputs(args.output_dir.resolve(), result)
    chosen = result["evaluation"][PRIMARY]
    print(f"Completed: detection {chosen['detection_rate']:.2f}, {chosen['false_alarms_per_1000h']:.2f} false alarms per 1000 h, "
          f"median lead {chosen['lead_hours_median']} h.")
