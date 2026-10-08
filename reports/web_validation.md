# Validación del explorador web

## Fuentes y correspondencia de visualizaciones

El explorador es una capa de presentación sobre el pipeline científico existente. Las fórmulas y los criterios de elegibilidad permanecen intactos; la integración final corrige exclusivamente los rótulos de residuales de dispersión de la figura anual. El exportador reutiliza `derive` y `apply_reference` de `src/analyze_scada.py`; JavaScript presenta series, filtra períodos y cambia visibilidad.

| Vista | Fuente pública | Presentación |
|---|---|---|
| Resumen: carga/corriente | Observaciones elegibles de processed, derivadas con el análisis existente | 328 horas de los 14 días del 1 al 15 de julio de 2042 (fin excluido); sin muestreo |
| Variables eléctricas | Las mismas 328 observaciones o las 72 horas elegibles previas al evento | P frente a corrientes A/B/C y temperaturas; Q y tensión media como contexto del tooltip |
| Resumen y calidad: cobertura | Filas de medición conservadas, selección estadística y elegibilidad | Conteos por cada uno de los 365 días; las categorías no son sumables |
| Calidad: sensor | Serie seleccionada y bandera `sensor_flat` del análisis Python | 18 horas marcadas y contexto de 18 horas a cada lado (54 observaciones) |
| Anomalías | Indicadores, P99 y persistencia de `apply_reference`; resumen original | 133 observaciones de contexto exportadas; ventanas [evento − 72/24/6 h, evento), sin reiniciar la persistencia |
| Métricas | `analysis_summary.json`, `quality_summary.json` y manifiesto comprobado | Conteos y estadísticas existentes, no estimaciones del navegador |

Los valores numéricos se serializan con hasta 12 decimales; los tooltips de señales presentan cuatro decimales y los resúmenes dos cuando procede. Los valores indefinidos se representan como JSON `null`, nunca como cero ni NaN. La referencia visual de 14 días no sustituye las primeras 240 jornadas utilizadas para ajustar los umbrales.

## Procedencia del JSON

Antes de exportar, se regeneran los datos públicos en un directorio temporal y se contrastan 373 entradas: 365 RAW, manifiesto, dos tablas interim, processed, dos resúmenes JSON y dos tablas de resultados. El conjunto de archivos de data debe coincidir; una etiqueta synthetic_only no es suficiente. Las comparaciones textuales normalizan saltos de línea de plataforma; se registran además hashes SHA-256 de los archivos originales en el JSON.

El JSON publicado ocupa 278.213 bytes. No contiene las 20 señales horarias completas del año ni datos operativos auténticos. Todas las series mostradas corresponden a observaciones del generador público.

## Integración del rediseño de Claude Code

El usuario aportó un informe de Claude Code con **18/18 pruebas Python y 61/61 verificaciones de navegador aprobadas**. Esas 61 comprobaciones se registran como **reportadas por Claude**; no se presentan como una reproducción de su misma suite.

La comparación con la copia de la auditoría anterior confirmó cambios únicamente en `docs/styles.css`, `docs/index.html` y `docs/app.js`. Se revisaron:

- Navegación segmentada, desplazable horizontalmente en móvil, con selección y foco por teclado.
- Claves HTML con botones y `aria-pressed` que sustituyen las leyendas internas de Plotly. La selección de visibilidad se conserva al restablecer la vista.
- Colores compartidos entre CSS y gráficos: fases con símbolos huecos distintos, indicadores con línea continua, P99 discontinuo, alertas con rombos rojos y evento con línea vertical oscura.
- Paneles y tablas adaptables; la descripción del caso permanece en móvil.
- Tabla simultánea de ventanas de 72/24/6 horas, fila activa identificada y advertencia explícita de solapamiento.
- Títulos completos de dispersión de corriente y tensión en porcentaje. Los residuales de esos indicadores en la figura anual se expresan en puntos porcentuales (pp); el residual térmico conserva °C.

### Comprobaciones propias de integración

Se ejecutaron **18/18 pruebas Python** y **74/74 comprobaciones de navegador propias**, en copias temporales y con las dependencias ya disponibles. Las comprobaciones propias son independientes del conteo de 61 reportado por Claude.

El navegador Chromium 149.0.7827.55 cargó únicamente recursos locales bajo `/scada-data-analysis/`. Se comprobaron las cinco vistas a 390, 768 y 1440 px sin desbordamiento horizontal de página, las fases y su estado vacío, los periodos de 328 y 72 puntos, zoom/restablecimiento, las cuatro series térmicas y las 13 claves HTML interactivas. Cada clave se desactivó, se verificó su estado tras restablecer el gráfico y se reactivó.

La tabla mostró 72/72, 24/24 y 6/6 horas elegibles/calendario; 31/21/6 horas con alerta y residuales térmicos de 6,82/11,32/17,81 °C. Las series filtradas terminaron en −1 h, con los mismos marcadores que Python. Se verificaron navegación con flechas y Home, error HTTP 503 y recuperación. No se registraron errores JavaScript ni solicitudes externas.

Los conteos conservan la distinción entre **8.759 registros totales**, **8.754 mediciones** y **5 eventos**. La cobertura acumula 8.740 horas seleccionadas y 8.513 elegibles; estas categorías no son sumables. El total del resumen y las series del gráfico coinciden con sus fuentes JSON.

Dos ejecuciones completas produjeron **378/378 artefactos idénticos entre sí**. Respecto de la entrega recibida, **377/378 permanecen idénticos**: solo cambia `02_conditioned_history.png` por sus dos rótulos en pp. Los algoritmos, resultados numéricos, otras tres figuras y JSON web permanecen idénticos. Los 373 hashes de procedencia del JSON coinciden con sus fuentes.

Hashes SHA-256 relevantes:

- Figura anual corregida: `e14bbd6eb1f86bd9695ca9b1ebee7691df42248f174ee43bd951cdb4abb65196`.
- JSON web: `7be9a6ef8474de6c745293d65ac5b94608456bbb0b4ea302c6841e94c9d20137`.
- Plotly: `8ef4c6ab1369f0019611cbcd2d5b8aafef23e5d19ef58c39d4b4249831fe2180`.

### Inspección visual y alcance

Se inspeccionaron capturas de variables eléctricas en escritorio, calidad y anomalías en móvil, además de la figura anual corregida. Las claves quedan fuera del área de trazado y la tabla de ventanas es legible. Esta revisión puntual confirma la integración; no constituye otra auditoría estética completa ni una certificación WCAG.

Los scripts y las capturas de estas comprobaciones se conservaron temporalmente fuera del conjunto de publicación. Los resultados de las secciones siguientes corresponden al cierre anterior al rediseño y se conservan como antecedentes.

## Antecedente: pruebas anteriores al rediseño

Entorno: Windows, Python 3.13.5, NumPy 2.5.1, pandas 3.0.5, Matplotlib 3.11.1 y Chromium 149.0.7827.55 disponible localmente. No se instalaron dependencias.

Comandos sobre una copia temporal:

```text
python -B -m unittest discover -v
python -B run_pipeline.py --output-dir <temporal_nuevo>
python -B export_dashboard.py --source-root <temporal_nuevo> --output <json_temporal>
```

- 18 pruebas aprobadas: 13 originales y cinco del exportador.
- 378/378 artefactos científicos idénticos byte a byte a los existentes, incluidas las cuatro figuras.
- JSON web idéntico byte a byte desde una regeneración independiente.
- Guardas Python activas en suite, pipeline y exportación: cero intentos registrados de acceso al directorio privado o conexiones de red. No equivalen a un aislamiento universal del sistema operativo.

Las cinco pruebas nuevas cubren conteos y ventanas exactas, conservación/cobertura y sensor, determinismo y valores finitos/null, rechazo de manifiesto no sintético y rechazo de valores procesados alterados.

## Antecedente: navegador anterior al rediseño

Se comprobó también el arranque de `python -B -m http.server` limitado a loopback y docs. Para verificar la subruta se sirvió únicamente docs mediante HTTP de loopback bajo `/scada-data-analysis/`. La prueba automatizada inspeccionó el DOM y las series reales de Plotly y comprobó:

- Tres series de corriente con nombres y fases correctas; activación y desactivación.
- Estado vacío al desactivar todas las fases.
- Cambio a 72 puntos elegibles previos al evento.
- Ampliación 2× y restablecimiento del rango.
- Cambio entre elevación térmica y cuatro series de temperaturas absolutas.
- Ventanas 72/24/6: puntos, indicadores y 31/21/6 marcadores persistentes; máximo temporal −1 h, excluyendo el evento.
- Cobertura anual: sumas de 8.754 mediciones conservadas y 8.740 horas seleccionadas.
- Navegación con flechas y Home, estado de pestaña y foco.
- Cinco vistas a 390, 768 y 1440 px sin desbordamiento horizontal.
- Preferencia de movimiento reducido.
- Error de carga 503 y recuperación mediante reintento.
- Cero errores JavaScript y cero solicitudes externas en las sesiones comprobadas.

La revisión visual se complementó con capturas de escritorio y móvil. Se corrigieron separadores de miles, restablecimiento del zoom, tamaño de gráficos al cambiar de vista y posición del eje temporal. Los resultados y capturas de la comprobación se conservaron temporalmente fuera del conjunto de publicación.

## Límites

No se verificaron instalación desde cero, otros sistemas, otros navegadores ni el sitio público. La evaluación editorial del resumen no sustituye una prueba de comprensión con reclutadores reales. La aplicación puede necesitar ajustes de accesibilidad específicos con lectores de pantalla; no se efectuó una auditoría WCAG completa.

Plotly.js 3.7.0 se sirve localmente y su licencia/procedencia están en `docs/assets/vendor/THIRD_PARTY.md`. No se incorporó una licencia de distribución para el código propio. La procedencia declarada por el autor es desarrollo en este proyecto con asistencia de Codex; la revisión no identificó restricciones concretas de terceros; las declaraciones y límites de derechos se detallan en privacy_audit.md. La URL de GitHub Pages no está habilitada ni se ha comprobado en este trabajo.
