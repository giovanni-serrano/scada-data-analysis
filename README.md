# ¿Pueden los datos del SCADA avisar antes de que se dañe un generador?

Un caso de estudio de monitoreo de condición con datos SCADA de una unidad hidroeléctrica simulada.

**[Ver el dashboard interactivo](https://giovanni-serrano.github.io/scada-data-analysis/)** · [Metodología y glosario](METODOLOGIA.md) · [Evaluación completa](reports/evaluation.md)

## El problema

En centrales hidroeléctricas es común que un generador salga de servicio por daño en los devanados sin que se pueda determinar la causa con certeza: sobrecarga, calor, refrigeración deficiente, sobreexcitación… Este proyecto explora si los datos que ya registra el SCADA cada hora **podrían avisar antes**.

## Por qué es difícil

La temperatura de un devanado sube con la carga. Es como la fiebre: 37,8 °C no significa lo mismo después de correr que en reposo. Un umbral fijo o suena a plena carga sin que pase nada, o no ve un calentamiento anormal a media carga. Y una falla empieza pequeña, escondida en el ruido de las mediciones.

## Qué hice

1. **Simulé los datos.** Con datos reales casi nunca se sabe cuándo empezó una falla; al simular conozco el inicio exacto y puedo calificar al detector. Cada simulación es un año horario de SCADA (20 señales, 60 Hz, ruido y defectos de historiador) con 2 a 4 fallas que calientan el devanado y desbalancean las corrientes hasta un disparo.
2. **Revisé los registros.** Las horas faltantes, duplicadas o con un sensor congelado se marcan y no entran en la estadística; nada se borra ni se inventa.
3. **Comparé cada hora con horas parecidas.** El umbral cambia según la carga y el ambiente. Si el devanado está caliente *para esa carga y ese ambiente*, esas dos causas no bastan para explicarlo.
4. **Diseñé la alarma como en una sala de control** (ISA-18.2): retardo para ignorar picos, histéresis para que no parpadee y dos prioridades.
5. **La medí en simulaciones que nunca vio.** Ajusté la alarma con 20 simulaciones de un año y la medí una sola vez en otras 100. Son tantas porque un año trae solo 2 a 4 fallas, y hacen falta cientos para que el porcentaje de detección sea confiable.

## Qué encontré

En esas 100 simulaciones de un año (291 degradaciones):

- **Avisó en 64 de cada 100 degradaciones.** Un umbral fijo avisó en 28 de cada 100.
- **Se equivocó poco:** 0,47 falsas alarmas por cada 1000 h de operación normal, unas 4 al año.
- **Avisó con tiempo:** en la mitad de los casos, 37 h o más antes del disparo.

Las más pequeñas son las que se escapan: se detectó el 32 % de las más leves y el 90 % de las más fuertes.

## Limitaciones

> Los datos son simulados y la forma de la falla la definí yo: una rampa de pocos días, cuando los daños reales suelen desarrollarse durante meses. Las señales simuladas son del estator, así que un daño en el rotor solo se vería de forma indirecta y una falla a tierra casi no se vería. Las cifras valen para este escenario; en una unidad real habría que repetir la medición con sus datos.

## Qué sigue

- Usar la potencia reactiva (`G1_Q`) para separar la hipótesis de sobreexcitación.
- Añadir señales del rotor al generador (corriente de campo y vibración) y contar arranques y paradas.
- Repetir la evaluación con datos reales que tengan fallas registradas.

---

## Para profundizar

- [Metodología y glosario](METODOLOGIA.md): cómo funciona cada paso, en palabras simples y con la tabla de qué fallas ve el método.
- [Evaluación](reports/evaluation.md) e [informe del año demo](reports/analysis.md): todas las tablas, generadas por el código.
- [Verificación](reports/verification.md): qué se comprobó en esta versión.

Proyecto personal desarrollado con asistencia de IA (Codex y Claude Code).

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

El dashboard queda en `http://127.0.0.1:8000/`. La evaluación tarda unos dos minutos. Cada ejecución necesita una carpeta de salida nueva. Las **56 pruebas** cubren reproducibilidad, conservación de registros, lógica de alarmas, puntuación de la evaluación, exportación web y que las cifras de este README y del dashboard coincidan con los resultados.
