# SCADA | Explorador de señales

Análisis de señales SCADA de una unidad hidroeléctrica simulada: de los CSV crudos del historiador a una regla de alarma cuyo desempeño se mide en años que no se usaron para ajustarla.

**[Dashboard interactivo](https://giovanni-serrano.github.io/scada-data-analysis/)** · [Evaluación](reports/evaluation.md) · [Informe del año demo](reports/analysis.md)

Los datos son sintéticos: los produce un generador con semilla fija. Proyecto desarrollado con asistencia de IA (Codex y Claude Code).

## El problema

La temperatura de un devanado sube con la carga. Un umbral fijo o se dispara a plena carga sin que pase nada, o no ve una degradación a media carga. ¿Se puede avisar antes de un disparo comparando cada hora con horas parecidas? ¿Y cuánto acierta esa regla cuando la degradación es pequeña?

## Qué hice

- **Datos.** Un año horario de 20 señales con tags de historiador (`G1_P`, `G1_IA`, `G1_VAB`, `G1_TW_A`…; lista en [src/common.py](src/common.py)), a 60 Hz, con error de instrumento, desbalance entre fases del orden del 1 % y factor de potencia variable. Cada año tiene de 2 a 4 episodios de degradación en momentos y tamaños sorteados.
- **Calidad de registros.** Inventario con SHA-256, lectura estricta y procedencia por fila. Huecos, duplicados contradictorios, marcas de tiempo desplazadas y un sensor congelado se marcan y se excluyen de la comparación; nada se interpola ni se borra.
- **Regla de alarma.** Dos indicadores (elevación térmica y dispersión entre corrientes de fase) se comparan con un percentil de su celda de carga y ambiente, calculado con los primeros 180 días. La lógica sigue los conceptos de ISA-18.2: retardo de activación, banda muerta y dos prioridades.
- **Evaluación ciega.** 20 años simulados para elegir percentil y retardo, con una regla fijada de antemano; 100 años distintos para medir. El detector no recibe la lista de episodios.

## Qué encontré

Sobre 100 años de evaluación (291 episodios), con percentil 95 y 2 h de retardo:

| Umbral | Episodios detectados [IC 95 %] | Falsas alarmas por 1000 h [IC 95 %] | Anticipación mediana [IC 95 %] |
| --- | --- | --- | --- |
| Condicionado por carga y ambiente | **64 %** [58; 70] | 0,47 [0,38; 0,56] | 37 h [31; 41] |
| Condicionado solo por carga | 60 % [54; 66] | 0,10 [0,07; 0,14] | 32 h [29; 36] |
| Fijo (línea base) | 28 % [23; 34] | 0,15 [0,11; 0,20] | 30 h [24; 38] |

- Condicionar el umbral detecta 36 puntos más que un umbral fijo (IC 95 %: 30 a 42).
- Añadir el ambiente a la carga suma 4 puntos de detección y multiplica por 4,6 las falsas alarmas.
- La detección depende del tamaño del episodio: 32 % en el tramo de menor severidad, 90 % en el mayor.
- La anticipación va de 11 a 70 h en el 80 % central de los episodios detectados.
- Subir el percentil o el retardo casi elimina las falsas alarmas y baja la detección (P99 y 3 h: 44 %).
- La banda muerta reduce las reactivaciones de alarma de 4.893 a 3.660 en los años de evaluación.

![Detección frente a falsas alarmas](reports/05_operating_points.png)

## Qué aprendí

- **Elegir con unos datos y medir con otros.** En las semillas de calibración la configuración elegida detectaba el 77 %; en las de evaluación, el 64 %. El primer número es optimista porque es el mejor de nueve.
- **Condicionar por lo que domina.** La elevación térmica depende sobre todo de la carga; el ambiente aporta poco y cuesta falsas alarmas.
- **Una alarma es un compromiso.** Retardo, banda muerta y prioridad deciden cuántas veces suena y cuántas se puede atender, tanto como el umbral.
- **Conservar no es aceptar.** Una fila dudosa se guarda con su procedencia, pero no entra en la estadística.

## Limitaciones

> Los datos salen de un generador con ecuaciones simples, no de una planta. La evaluación es ciega respecto al momento y al tamaño de cada episodio, pero el mismo autor diseñó el generador y el detector, y el tipo de degradación (una rampa lineal en temperatura y desbalance) es conocido. Los datos son horarios, así que los tiempos de ISA-18.2 están escalados a horas. Los porcentajes describen este escenario; en una unidad real habría que repetir la medición con sus datos.

## Cómo reproducirlo

Verificado en Windows con Python 3.13.5 y las versiones fijadas en [requirements.txt](requirements.txt).

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -B run_pipeline.py --output-dir runs/demo
.\.venv\Scripts\python -B run_evaluation.py --output-dir runs/demo
.\.venv\Scripts\python -B export_dashboard.py --source-root runs/demo
.\.venv\Scripts\python -B -m unittest discover
.\.venv\Scripts\python -B -m http.server 8000 --bind 127.0.0.1 --directory docs
```

El dashboard queda en `http://127.0.0.1:8000/`. La evaluación tarda unos dos minutos y el exportador la repite para comprobarla. Cada ejecución necesita una carpeta de salida nueva.

Las **56 pruebas** cubren reproducibilidad, conservación de registros, lógica de alarmas, puntuación de la evaluación y exportación web. Lo comprobado en esta versión está en [reports/verification.md](reports/verification.md); la licencia de Plotly.js, en [docs/assets/vendor/THIRD_PARTY.md](docs/assets/vendor/THIRD_PARTY.md).
