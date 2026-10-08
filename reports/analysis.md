# Análisis de una unidad hidroeléctrica sintética

Año demo generado con la semilla 781. Los datos son sintéticos.

## Calidad y conservación

Se conservan 8762 filas: 8754 mediciones y 8 eventos.
Hay 7 horas con mediciones contradictorias, 9 registros adelantados dos segundos
y 13 horas sin medición. No se interpola ni se deduplica: la selección estadística
(8740 mediciones) excluye las horas ambiguas y los eventos, y el archivo procesado queda intacto.
Una lectura congelada del cojinete B (18 horas idénticas seguidas) excluye esas horas de la comparación.

## Referencia y regla de alerta

- Generación estable: potencia, corriente, tensión y frecuencia positivas en la hora actual y las tres anteriores.
- Referencia: los primeros 180 días, sin episodios de degradación. Se agrupa por bandas de potencia
  (0–200–300–400–500–600–700–900 kW) y de ambiente (10–26.5–29.5–45 °C), con al menos
  30 observaciones por celda: 16 celdas admitidas, 131 horas sin soporte.
- Indicadores: elevación térmica = media de devanados − ambiente; dispersión = 100 × (máx − mín) / media de las tres fases.
- Alerta: ambos indicadores por encima del P99 de su celda durante tres horas seguidas.

| Período | Horas elegibles | Elevación térmica mediana °C | Dispersión de corriente mediana % | Dispersión de corriente P99 % | Dispersión de tensión mediana % | Activaciones de alerta |
|---|---:|---:|---:|---:|---:|---:|
| reference | 4179 | 24.88 | 1.08 | 2.74 | 0.73 | 0 |
| normal_operation | 3765 | 24.64 | 1.06 | 2.43 | 0.65 | 0 |

## Episodios de degradación del año demo

El generador sortea el momento y el tamaño de cada episodio; la regla no los conoce.
Se detectan 4 de 4.

| Evento | Disparo | Rampa h | Severidad | Δ térmico °C | Δ dispersión pp | Detectado | Anticipación h |
|---:|---|---:|---:|---:|---:|---|---:|
| 1 | 2025-07-22 11:00 | 100 | 0.52 | 5.0 | 2.7 | sí | 5 |
| 2 | 2025-09-21 11:00 | 113 | 0.93 | 9.7 | 3.5 | sí | 24 |
| 3 | 2025-10-23 17:00 | 95 | 0.86 | 6.2 | 4.5 | sí | 53 |
| 4 | 2025-12-12 10:00 | 112 | 0.49 | 3.7 | 1.9 | sí | 18 |

Los incrementos (Δ) son los valores alcanzados al final de la rampa. Un año no basta para estimar tasas.

## Figuras

![Relaciones con la carga](01_physical_relationships.png)

![Residuales diarios](02_conditioned_history.png)

![Indicadores antes de cada disparo](03_pre_event_windows.png)

![Calidad y sensor](04_quality_and_sensor.png)

Detalle numérico: `analysis_summary.json`, `historical_reference.csv`, `period_comparison.csv`, `event_detection.csv`.
