# ¿Podían los datos del SCADA avisar antes de que se dañara el generador?

Un caso de estudio de monitoreo de condición con datos SCADA de una unidad hidroeléctrica simulada.

**[Ver el dashboard interactivo](https://giovanni-serrano.github.io/scada-data-analysis/)** · [Metodología y glosario](METODOLOGIA.md) · [Evaluación completa](reports/evaluation.md)

## El problema real

Mi primer acercamiento a un fallo real fue en las visitas de familiarización a una central hidroeléctrica. Un generador salió de servicio con los devanados del rotor gravemente dañados, y el informe dejó varias causas posibles abiertas: sobrecarga, ambiente caluroso, refrigeración obstruida, sobreexcitación… Me quedé con una pregunta: **¿el SCADA, que registra la unidad cada hora, podía haber avisado antes?**

## Por qué es difícil

La temperatura de un devanado sube con la carga. Es como la fiebre: 37,8 °C no significa lo mismo después de correr que en reposo. Un umbral fijo o suena a plena carga sin que pase nada, o no ve un calentamiento anormal a media carga. Y una falla empieza pequeña, escondida en el ruido de las mediciones.

## Qué hice

1. **Construí datos parecidos, pero no iguales.** No puedo publicar los de la planta, así que simulé años horarios de SCADA (20 señales, 60 Hz, con ruido y defectos de historiador) con 2 a 4 fallas por año que calientan el devanado y desbalancean las corrientes hasta un disparo. Así sé cuándo empieza cada una y puedo calificar al detector.
2. **Revisé los registros.** Las horas faltantes, duplicadas o con un sensor congelado se marcan y no entran en la estadística; nada se borra ni se inventa.
3. **Comparé cada hora con horas parecidas.** El umbral cambia según la carga y el ambiente. Si el devanado está caliente *para esa carga y ese ambiente*, esas dos causas no bastan para explicarlo.
4. **Diseñé la alarma como en una sala de control** (ISA-18.2): retardo para ignorar picos, histéresis para que no parpadee y dos prioridades.
5. **La medí en años que nunca vio.** Ajusté la alarma con 20 años simulados y la medí una sola vez en otros 100.

## Qué encontré

En esos 100 años simulados (291 degradaciones):

- **Avisó en 64 de cada 100 degradaciones.** Un umbral fijo avisó en 28 de cada 100.
- **Se equivocó poco:** 0,47 falsas alarmas por cada 1000 h de operación normal, unas 4 al año.
- **Avisó con tiempo:** en la mitad de los casos, 37 h o más antes del disparo, suficiente para planear una parada.

Las degradaciones pequeñas son las que más se escapan: se detectó el 32 % de las más leves y el 90 % de las más fuertes.

## Limitaciones

> Los datos son simulados y la forma de la falla la definí yo: una rampa de pocos días, cuando un daño como el de la planta tarda meses. El fallo real fue en el rotor y aquí uso señales del estator como indicio indirecto: una falla a tierra casi no se vería. Las cifras valen para este escenario; en una unidad real habría que repetir la medición con sus datos.

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
