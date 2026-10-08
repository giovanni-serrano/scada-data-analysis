"""Shared schema and small file helpers. All paths are relative to an output root."""
import csv
from decimal import ROUND_HALF_UP, Decimal
import hashlib
import json
from pathlib import Path

# Historian tag, descriptive column used by the analysis, unit, description.
TAG_CATALOG = [
    ("G1_P", "active_power_kw", "kW", "Potencia activa del generador"),
    ("G1_Q", "reactive_power_kvar", "kvar", "Potencia reactiva del generador"),
    ("G1_IA", "phase_current_a", "A", "Corriente de fase A"),
    ("G1_IB", "phase_current_b", "A", "Corriente de fase B"),
    ("G1_IC", "phase_current_c", "A", "Corriente de fase C"),
    ("G1_VAB", "phase_voltage_ab", "V", "Tensión de línea A-B"),
    ("G1_VBC", "phase_voltage_bc", "V", "Tensión de línea B-C"),
    ("G1_VCA", "phase_voltage_ca", "V", "Tensión de línea C-A"),
    ("G1_F", "frequency_hz", "Hz", "Frecuencia eléctrica"),
    ("EMB_LVL", "water_level_m", "m", "Nivel del embalse"),
    ("TP_PRES", "penstock_pressure_m", "m", "Altura de presión en la tubería forzada"),
    ("G1_GV_A", "guide_opening_a_pct", "%", "Apertura del distribuidor, servomotor A"),
    ("G1_GV_B", "guide_opening_b_pct", "%", "Apertura del distribuidor, servomotor B"),
    ("SM_TAMB", "room_temperature_c", "°C", "Temperatura ambiente de la sala de máquinas"),
    ("G1_TW_A", "winding_temperature_a_c", "°C", "Temperatura del devanado, fase A"),
    ("G1_TW_B", "winding_temperature_b_c", "°C", "Temperatura del devanado, fase B"),
    ("G1_TW_C", "winding_temperature_c_c", "°C", "Temperatura del devanado, fase C"),
    ("G1_TB_A", "bearing_temperature_a_c", "°C", "Temperatura del cojinete A"),
    ("G1_TB_B", "bearing_temperature_b_c", "°C", "Temperatura del cojinete B"),
    ("G1_TOIL", "oil_temperature_c", "°C", "Temperatura del aceite"),
]
TAGS = [row[0] for row in TAG_CATALOG]
SIGNALS = [row[1] for row in TAG_CATALOG]
TAG_TO_SIGNAL = dict(zip(TAGS, SIGNALS))
SIGNAL_TO_TAG = dict(zip(SIGNALS, TAGS))
# RAW files carry historian tags; the analysis renames them to descriptive columns.
RAW_FIELDS = ["date", "time", "record_type", "event_message", *TAGS]
TRIP_MESSAGE = "unit_trip"


def spanish(value, digits=2):
    """Decimal comma, rounding halves up like the dashboard's number formatter does."""
    if value is None:
        return "—"
    return str(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)).replace(".", ",")


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
