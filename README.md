# SCADA | Explorador de señales

Análisis exploratorio de **20 variables de una unidad hidroeléctrica ficticia**, desde los registros horarios hasta su interpretación en un dashboard interactivo. El proyecto combina Python, conceptos eléctricos y controles de calidad para estudiar cómo cambian las señales según la carga y las condiciones ambientales.

El recorrido permite seguir cada observación hasta su archivo de origen, reconocer registros que requieren revisión y comparar cambios con una referencia histórica. Es un proyecto de aprendizaje aplicado que muestra comprensión técnica, criterio en el tratamiento de datos y capacidad para comunicar resultados.

> Los datos son completamente sintéticos, generados desde cero para esta demostración educativa y de portafolio.

## Explorador interactivo

El dashboard organiza el análisis en cinco vistas: **Resumen, Variables eléctricas, Calidad de datos, Anomalías y Metodología**. Permite explorar fases eléctricas, ampliar periodos, alternar temperaturas absolutas y elevación térmica, y examinar las 72, 24 y 6 horas anteriores al evento artificial.

**Dirección prevista del sitio — pendiente de publicación y comprobación:** https://giovanni-serrano.github.io/scada-data-analysis/

La aplicación estática está en [`docs/`](docs/). Presenta los resultados calculados en Python y utiliza una copia local de Plotly.js. Las instrucciones de [reproducción local](#reproducción-local) permiten ejecutar el análisis y abrir el dashboard.

## La pregunta de análisis

**¿Cómo reconocer un cambio relevante cuando las señales también responden a la carga, al ambiente y a la calidad del registro?**

Una corriente mayor puede acompañar a una mayor potencia generada. Del mismo modo, la temperatura de un devanado depende tanto de la carga como del ambiente y de su evolución reciente. Comparar condiciones similares ayuda a interpretar esas variaciones.

El proyecto aborda primero la calidad de los datos: duplicados contradictorios, desfases horarios, huecos, eventos de comunicación y un sensor con lectura congelada. Después construye una referencia por carga y ambiente para estudiar los cambios introducidos en el escenario.

## Variables y modelo sintético

El conjunto representa **365 días del año ficticio 2042**, con resolución horaria y semilla `781`. Los valores nominales elegidos son 820 kW, 2300 V y 50 Hz durante generación.

| Grupo | Magnitudes | Relación representada |
|---|---|---|
| Potencia | Activa (kW) y reactiva (kvar) | Carga periódica con ruido acotado; reactiva proporcional a activa |
| Corrientes | Fases A, B y C (A) | Corriente calculada a partir de potencia aparente y tensión, con diferencias entre fases |
| Tensiones | Pares AB, BC y CA (V) | Variaciones alrededor de la tensión nominal ficticia |
| Frecuencia | Frecuencia eléctrica (Hz) | Variación alrededor de 50 Hz durante generación y cero en la parada |
| Hidráulica | Nivel (m), variable de presión con etiqueta didáctica (m) y dos aperturas (%) | Nivel con ciclo lento; presión y aperturas dependientes de la carga |
| Temperaturas | Ambiente, tres devanados, dos cojinetes y aceite (°C) | Efecto del ambiente y de la carga con inercia térmica de primer orden |

La corriente media se aproxima mediante `1000 × √(P² + Q²) / (√3 × V)`. Las temperaturas evolucionan con la regla `estado += coeficiente × (objetivo − estado)` y coeficientes distintos para devanados, cojinetes y aceite.

Dos indicadores guían la comparación: la **elevación térmica**, calculada como temperatura media de devanados menos temperatura ambiente, y la **dispersión entre corrientes**, definida como `100 × (máximo − mínimo) / media`. Esta última describe la separación relativa entre las tres lecturas; su interpretación se limita a ese indicador descriptivo.

La variable `penstock_pressure_m` sigue la expresión `110 − 12 × (P/820)² + ruido`. Su unidad en metros es una etiqueta didáctica del generador. La interpretación física como altura de presión requeriría definir la conversión y validar el modelo hidráulico.

El [esquema de señales](src/common.py) contiene los nombres exactos. El generador también produce `data/synthetic_scenario.json`, que documenta las incidencias y sus posiciones.

## Tratamiento y comparación de datos

```text
Generador → CSV diarios → inventario → registros trazables → datos procesados → análisis y figuras
```

1. **Generación e inventario.** Se crean los CSV diarios y se registran sus rutas relativas, tamaños y hashes SHA-256 para comprobar su integridad.
2. **Lectura trazable.** Cada registro conserva el texto original, el archivo, la línea física y la fecha interpretada. La lectura estricta detiene la ejecución ante un registro inválido.
3. **Revisión de calidad.** Se añaden la hora lógica, el desfase y las banderas de revisión. Todas las filas y celdas originales permanecen disponibles, incluidos los eventos y las alternativas contradictorias. Los huecos de cobertura se documentan y las mediciones ausentes quedan sin interpolar.
4. **Selección estadística.** La comparación utiliza horas sin ambigüedad, con generación estable y soporte histórico. La estabilidad exige la hora actual y tres horas previas consecutivas en generación. La meseta detectada en el sensor de cojinete B excluye la observación horaria completa de esta comparación.
5. **Referencia y alertas.** Las primeras 240 jornadas forman la referencia, agrupada por bandas de potencia y ambiente con al menos 30 observaciones por grupo. Se comparan la elevación térmica y la dispersión de corriente con sus percentiles 99 históricos. La alerta persistente se activa a partir de la tercera hora consecutiva con exceso conjunto.

Las observaciones que carecen de soporte histórico se identifican explícitamente. Los umbrales se ajustan con el periodo de referencia; el instante del evento se utiliza para situar las ventanas de evaluación.

## Escenario y resultados

El generador introduce siete horas con mediciones contradictorias, nueve registros adelantados dos segundos —uno cruza medianoche—, trece horas sin medición, cuatro eventos de comunicación y una meseta de sensor de dieciocho horas.

La parada artificial comienza el **18 de noviembre de 2042 a las 20:00** y dura 36 horas. El escenario incorpora un aumento gradual de la dispersión de corriente y tensión durante las 96 horas previas, y de la temperatura objetivo de devanados durante las 72 horas previas. Estos cambios deliberados permiten comprobar el comportamiento del análisis frente a un caso conocido.

| Resultado | Valor |
|---|---|
| Registros conservados | 8.759: 8.754 mediciones y 5 eventos |
| Mediciones en la selección estadística | 8.740 |
| Primera alerta persistente | 34 horas antes de la parada artificial |
| Horas elegibles en las ventanas de 72 / 24 / 6 horas | 72 / 24 / 6 |
| Horas con alerta persistente en esas ventanas | 31 / 21 / 6 |
| Tramo normal posterior a la referencia | 1.824 horas elegibles; 0 alertas persistentes y 2 excesos conjuntos aislados |
| Meseta de sensor identificada | 18 horas |
| Horas de generación estable sin soporte histórico | 2 |

Las ventanas se solapan. Los resultados describen la respuesta al escenario sintético y deben interpretarse dentro de ese alcance.

## Visualizaciones

### Carga y respuesta de las señales

![Relaciones entre carga, corriente, apertura y elevación térmica](reports/01_physical_relationships.png)

La corriente y la apertura siguen la carga según las relaciones del generador. El periodo previo a la parada muestra la elevación térmica adicional introducida en el escenario.

### Evolución previa a la parada artificial

![Indicadores y alertas en las ventanas previas al evento](reports/03_pre_event_windows.png)

La comparación por carga y ambiente sitúa los indicadores frente a sus P99 históricos. Los puntos marcados permiten seguir la persistencia del exceso conjunto en las tres ventanas.

### Cobertura y revisión del sensor

![Cobertura diaria y meseta de temperatura del sensor](reports/04_quality_and_sensor.png)

La cobertura diaria muestra la disponibilidad de horas sin ambigüedad. El detalle de temperaturas permite examinar la lectura congelada del cojinete junto con las señales de contexto.

El [informe técnico](reports/analysis.md) desarrolla los resultados e incluye una cuarta figura con la evolución anual condicionada. En ella, los residuales de dispersión se expresan en puntos porcentuales (pp), como diferencia respecto a la mediana histórica. Los valores de apoyo están en la [comparación de ventanas](reports/window_comparison.csv) y la [referencia histórica](reports/historical_reference.csv).

## Reproducción local

El análisis y las pruebas se verificaron en Windows con Python 3.13.5, NumPy 2.5.1, pandas 3.0.5 y Matplotlib 3.11.1. Las versiones están fijadas en [`requirements.txt`](requirements.txt).

Desde la carpeta del proyecto, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -B run_pipeline.py --output-dir runs/demo
.\.venv\Scripts\python -B export_dashboard.py --source-root runs/demo
.\.venv\Scripts\python -B -m unittest discover -v
.\.venv\Scripts\python -B -m http.server 8000 --bind 127.0.0.1 --directory docs
```

El dashboard queda disponible en `http://127.0.0.1:8000/`. Los datos y las figuras generados se guardan en `runs/demo/data/` y `runs/demo/reports/`; el exportador actualiza `docs/assets/dashboard-data.json` tras contrastar sus fuentes con una regeneración independiente.

Cada ejecución requiere una carpeta de salida nueva, por ejemplo `runs/demo2`. El procesamiento funciona sin red una vez instaladas las dependencias. Los CSV regenerables de `data/` están excluidos mediante `.gitignore`.

Las **18 pruebas automatizadas** cubren reproducibilidad, integridad de archivos, conservación y procedencia de registros, tratamiento de incidencias, referencia temporal, detección del cambio artificial y exportación web. El dashboard se comprobó en Chromium con anchos de 390, 768 y 1440 píxeles. La instalación desde cero, otros navegadores y el despliegue público quedan pendientes de verificación; el detalle figura en el [informe de validación web](reports/web_validation.md).

## Alcance y aprendizaje

El trabajo reúne lectura de variables eléctricas, preparación de datos, análisis exploratorio y visualización reproducible. Documenta un proceso de aprendizaje aplicado; la experiencia que presenta se circunscribe a esta demostración.

La interpretación está condicionada por un único evento diseñado, la dependencia entre observaciones horarias y la elección de bandas de comparación. Los P99 son umbrales empíricos y la detección de mesetas es retrospectiva. El modelo simplifica las relaciones físicas y su aplicación industrial requeriría validación con datos reales, criterios de operación y revisión especializada. La capacidad de diagnóstico o predicción de fallas queda fuera de lo demostrado.

## Herramientas de apoyo

Codex asistió en programación, desarrollo del dashboard y preparación de la demostración pública, con una participación intensiva en la construcción del dashboard. Los datos de esta versión se generan desde cero y se mantienen separados de los datos operativos privados. El foco del proyecto está en comprender las variables, justificar el tratamiento de los registros e interpretar los resultados.

## Procedencia y documentación

El conjunto publicado se genera desde cero mediante ecuaciones y una semilla fija. Todos sus valores, incidencias y eventos son ficticios. La [auditoría de privacidad](reports/privacy_audit.md) documenta los controles y el alcance de la revisión.

La [guía de publicación](reports/publication.md) recoge el estado de preparación del repositorio y del sitio. La [documentación de Plotly.js](docs/assets/vendor/THIRD_PARTY.md) detalla la procedencia y licencia de la biblioteca incluida.
