# Análisis de una unidad hidroeléctrica ficticia

Todos los datos de este informe son completamente sintéticos y educativos.
El evento `2042-11-18T20:00:00` y sus señales previas se inyectaron artificialmente.
No representan un mecanismo físico de fallo validado.

## Calidad y conservación

Se conservan 8759 filas: 8754 mediciones y 5 eventos.
Hay 7 horas con mediciones alternativas, 9 registros adelantados dos segundos
y 13 horas sin medición. Los eventos no rellenan mediciones faltantes.
La selección estadística contiene 8740 mediciones, sin modificar processed.
Se excluyen de esa selección todas las alternativas de horas ambiguas y los eventos.
Las observaciones a hasta tres segundos antes de la hora reciben hora lógica derivada;
la fecha y hora originales permanecen intactas. No hay interpolación ni deduplicación.
La meseta exacta de un sensor comprende 18 horas. Es una bandera retrospectiva
de calidad (mínimo seis horas contiguas), no evidencia de una avería térmica.

## Referencia y comparación

Estados: generación cuando potencia, corriente, tensión y frecuencia son positivas;
parada cuando las cuatro son cero; combinaciones restantes son intermedias.
Se requieren la observación actual y tres horas previas consecutivas en generación.
Las primeras 240 jornadas forman la referencia, cerrada antes del cambio artificial.
Se usan cuatro bandas de potencia (0–200–400–600–900 kW) y tres de ambiente
(10–18–26–40 °C), con al menos 30 observaciones por celda. Hay 9 celdas admitidas.
Las horas de generación estable sin soporte histórico son 2.
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
| reference | 5613/5760 | 0.00 | 0.24 | 0.10 | 0 |
| normal_holdout | 1824/1868 | 0.08 | 0.24 | 0.10 | 0 |
| pre_event_72h | 72/72 | 6.82 | 11.37 | 0.93 | 31 |
| pre_event_24h | 24/24 | 11.32 | 15.81 | 1.21 | 21 |
| pre_event_6h | 6/6 | 17.81 | 17.50 | 1.36 | 6 |

Las ventanas son [evento − duración, evento), se solapan y excluyen la parada en el instante del evento.
La primera alerta persistente dentro del cambio inyectado aparece en
`2042-11-17T10:00:00`, con 34.0 horas de antelación.
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
