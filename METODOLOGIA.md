# Metodología y glosario

Aquí está la parte técnica. El relato corto está en el [README](README.md); las tablas completas, en la [evaluación](reports/evaluation.md) y el [informe del año demo](reports/analysis.md). Las palabras en *cursiva* están en el [glosario](#glosario).

## 1. Los datos

- `src/generate_synthetic_scada.py` simula un año horario (2025) de una unidad hidroeléctrica de 820 kW, 2300 V y 60 Hz. Produce 365 archivos CSV como los de un *historiador*, con 20 señales identificadas por *tag* (lista en [src/common.py](src/common.py)).
- Cada señal tiene error de instrumento. Las tres fases no son idénticas y el factor de potencia varía.
- Los primeros 180 días no tienen fallas: son la *referencia*. Después aparecen de 2 a 4 *episodios de degradación*, en momentos y con *severidades* sorteados. En cada uno, la temperatura del devanado y el desbalance de corrientes suben en *rampa* durante 48 a 120 h hasta un *disparo*.
- El generador también introduce defectos de historiador: horas faltantes, horas duplicadas que se contradicen, marcas de tiempo adelantadas y un sensor congelado.

Todo depende de una *semilla*: la misma semilla produce el mismo año, byte a byte.

## 2. La calidad de los registros

- Cada archivo se inventaría con su huella SHA-256 y se lee con un esquema estricto.
- Nada se interpola ni se borra. Las horas dudosas se conservan con su procedencia y quedan fuera de la estadística.
- Solo se comparan horas de *generación estable*: potencia, corriente, tensión y frecuencia positivas en la hora actual y en las tres anteriores.

## 3. Los indicadores y el umbral

Dos *indicadores* resumen el estado del devanado:

- **Elevación térmica** = temperatura media de los devanados − temperatura ambiente.
- **Dispersión de corriente** = 100 × (fase máxima − fase mínima) / promedio de las tres fases.

Con la referencia, las horas se agrupan en *celdas* de carga (0–200–300–400–500–600–700–900 kW) y de ambiente (10–26,5–29,5–45 °C). Una celda necesita al menos 30 horas para tener umbral. El *umbral* de cada indicador es el *percentil* 95 de su celda.

## 4. La alarma (conceptos de ISA-18.2)

| Tag | Prioridad | Se activa cuando… |
|---|---|---|
| `G1_TW_HI` | baja | la elevación térmica supera su umbral |
| `G1_IUNB_HI` | baja | la dispersión de corriente supera su umbral |
| `G1_DEG_HH` | alta | los dos indicadores superan su umbral a la vez |

- *Retardo de activación*: 2 h seguidas sobre el umbral.
- *Banda muerta*: una vez activa, la alarma solo se repone cuando el indicador baja 1,0 °C (elevación térmica) o 0,4 puntos porcentuales (dispersión) por debajo del umbral.
- La prioridad baja informa; la alta pide acción. **Todas las cifras de resultados son de la prioridad alta.**

Los datos son horarios, así que los tiempos de la norma, pensados en segundos y minutos, están escalados a horas.

## 5. La evaluación

1. Con 20 simulaciones de un año de *calibración* se probaron 9 combinaciones: percentil 95, 99 o 99,5 y retardo de 2, 3 o 4 h. La regla de elección se fijó antes de ver resultados: la mayor detección con un máximo de 1 falsa alarma por 1000 h. Ganó **percentil 95 con 2 h**.
2. Esa configuración se aplicó sin cambios a 100 simulaciones de un año de *evaluación*, distintas de las anteriores.
3. Un episodio está *detectado* si la alarma alta se activa entre el inicio de su rampa y el disparo. Una *falsa alarma* es una activación fuera de las rampas y de las paradas posteriores.
4. Los *intervalos de confianza* del 95 % salen de *remuestrear* simulaciones completas 2000 veces.

### Resultados

Sobre 100 simulaciones de un año de evaluación (291 episodios), con percentil 95 y 2 h de retardo:

| Umbral | Detección [IC 95 %] | Detectados | Falsas alarmas por 1000 h [IC 95 %] | Anticipación mediana [IC 95 %] | Anticipación P10–P90 |
|---|---|---:|---|---|---|
| Condicionado por carga y ambiente | 64 % [58; 70] | 186/291 | 0,47 [0,38; 0,56] | 37 h [31; 41] | 11–70 h |
| Condicionado solo por carga | 60 % [54; 66] | 174/291 | 0,10 [0,07; 0,14] | 32 h [29; 36] | 9–65 h |
| Fijo (línea base) | 28 % [23; 34] | 82/291 | 0,15 [0,11; 0,20] | 30 h [24; 38] | 4–67 h |

- Con las mismas simulaciones, condicionar el umbral detecta 36 puntos más que el umbral fijo (IC 95 %: 30 a 42).
- Por severidad (de menor a mayor): 32 %, 61 %, 70 % y 90 % de episodios detectados.
- En calibración, la misma configuración detectaba el 77 %. La caída hasta el 64 % es la razón de medir con simulaciones distintas: el primer número es el mejor de nueve intentos.

## 6. Causas típicas de daño en devanados, y qué puede decir el método

Cuando un generador sale de servicio por daño en los devanados, estas son causas que suelen considerarse:

| Causa típica | Señal SCADA que la delataría | ¿La cubre este proyecto? |
|---|---|---|
| Sobrecarga | Potencia frente a la nominal | Sí: el umbral depende de la carga, así que la descarta como explicación única |
| Ambiente caluroso | Temperatura de la sala | Sí: el umbral también depende del ambiente |
| Refrigeración obstruida | Temperatura alta *para esa carga y ese ambiente* | Sí: es justo lo que detecta |
| Sobreexcitación | Potencia reactiva o corriente de campo | Todavía no: `G1_Q` existe pero no se usa en el umbral |
| Espiras en cortocircuito en el rotor | Más corriente de campo para el mismo punto de operación; vibración | Solo de forma indirecta, por la temperatura del estator |
| Falla a tierra del rotor | Relé de falla a tierra del rotor, resistencia de aislamiento | No: no se ve con estas señales |
| Arranques y paradas frecuentes | Conteo de arranques en el historiador | Todavía no |
| Inestabilidad de tensión o frecuencia | Tensiones de línea y frecuencia | Todavía no: las señales existen, pero no se analizan |

## 7. Decisiones, en una línea cada una

- **¿Por qué datos simulados?** Con datos reales casi nunca se sabe cuándo empezó una falla. Al simular se conoce el inicio exacto de cada degradación y se puede calificar al detector.
- **¿Por qué tantas simulaciones?** Un año trae solo 2 a 4 fallas. Con unas pocas, el porcentaje de detección cambiaría mucho de una prueba a otra; hacen falta cientos para que sea confiable. Por eso se usan 100 simulaciones de un año para medir (291 fallas en total).
- **¿Por qué separar calibración y evaluación?** Si eliges y mides con los mismos datos, te calificas con el examen que ya viste. Por eso el 77 % de calibración bajó al 64 % en simulaciones nuevas.
- **¿Por qué el ambiente cuesta falsas alarmas?** La elevación térmica ya resta el ambiente, así que dividir también por ambiente aporta poca información nueva. Además, cada celda queda con menos horas de referencia y con un umbral más ajustado: detecta un poco más y también se cruza más veces por azar.
- **¿Por qué dos prioridades?** Si la prioridad baja contara como detección, se detectarían todos los episodios, pero con decenas de falsas alarmas por cada 1000 h. La alta, que exige los dos indicadores a la vez, es la que se puede atender.

## Glosario

| Término | Qué significa, en simple |
|---|---|
| SCADA | Sistema que supervisa la planta y registra sus mediciones. |
| Historiador | Base de datos donde el SCADA guarda las mediciones con su fecha y hora. |
| Tag | Nombre corto de una señal en el historiador, como `G1_IA` (corriente de la fase A). |
| Semilla | Número que fija el azar de la simulación: la misma semilla produce el mismo año. |
| Episodio de degradación | Falla simulada que empieza pequeña y crece hasta un disparo. |
| Rampa | La subida gradual del episodio, de 48 a 120 h. |
| Disparo | Salida de servicio de la unidad por protección. |
| Severidad | Tamaño del episodio: 1 es la falla más grande que simula el generador; las pequeñas quedan escondidas en el ruido. |
| Generación estable | Hora en la que la unidad genera de forma continua, sin arranques ni paradas. |
| Indicador | Número que resume el estado del devanado: elevación térmica o dispersión de corriente. |
| Referencia | Los primeros 180 días del año, sin fallas: es lo que se considera normal. |
| Celda | Grupo de horas con carga y ambiente parecidos. |
| Percentil 95 | Valor que solo el 5 % de las horas normales de la celda supera. |
| Umbral condicionado | Un umbral distinto para cada celda, en lugar de un único número. |
| Umbral fijo (línea base) | Un solo umbral para todas las horas. Sirve para comparar. |
| Retardo de activación | Tiempo que la condición debe mantenerse antes de anunciar la alarma, como un relé con temporizador. |
| Banda muerta | Histéresis: la alarma se apaga solo cuando la señal baja claramente del umbral. |
| Prioridad | Qué tan urgente es atender la alarma: baja informa, alta pide acción. |
| Alarma fugaz | Se apaga sola en 2 h o menos. Muchas fugaces cansan al operador. |
| Alarma persistente | Sigue activa 24 h o más. |
| Reactivación | La alarma vuelve a sonar menos de 6 h después de apagarse. |
| Detección | La alarma alta suena entre el inicio de la rampa y el disparo. |
| Falsa alarma | La alarma alta suena cuando no hay ningún episodio en curso. |
| Falsas alarmas por 1000 h | Cuántas falsas alarmas hay por cada 1000 h de operación normal. Un año tiene 8760 h. |
| Anticipación | Horas entre la primera alarma alta y el disparo. |
| Mediana | El valor del medio: la mitad de los casos está por encima y la otra mitad por debajo. |
| P10–P90 | Rango que contiene el 80 % central de los casos. |
| Calibración | Simulaciones de un año usadas para elegir la configuración. |
| Evaluación | Simulaciones de un año distintas, usadas una sola vez para medir. |
| Intervalo de confianza del 95 % | Rango en el que probablemente estaría el resultado si se repitiera el experimento con otras simulaciones. |
| Remuestreo (*bootstrap*) | Repetir el cálculo muchas veces sorteando simulaciones con reemplazo para ver cuánto varía el resultado. |

## Alcance

Los datos salen de un generador con ecuaciones simples, no de una planta. La evaluación es ciega respecto al momento y al tamaño de cada episodio, pero el mismo autor diseñó el generador y el detector, y la forma de la degradación (una rampa lineal) es conocida. Los porcentajes describen este escenario; en una unidad real habría que repetir la medición con sus propios datos.
