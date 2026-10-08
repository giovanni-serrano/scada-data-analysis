# Auditoría de privacidad de la entrega

## Cierre de integración: controles actuales

La revisión abarca los 405 archivos del proyecto público: 36 propuestos para publicación y 369 archivos regenerables de `data/` excluidos del commit. Se revisaron también los archivos ocultos y excluidos. El proyecto privado permanece fuera de alcance y no se accedió a él.

La comparación con la copia conservada de la auditoría anterior confirmó que el rediseño de Claude Code cambió únicamente `docs/styles.css`, `docs/index.html` y `docs/app.js`. Se inspeccionaron sus cambios de navegación, controles, gráficos y tablas. Los datos, el exportador y la dependencia Plotly conservaban sus hashes anteriores.

| Control efectuado en esta integración | Resultado |
|---|---|
| Pruebas Python en una copia temporal | 18 aprobadas, 0 fallidas |
| Dos regeneraciones completas e independientes | 378/378 artefactos idénticos entre ambas ejecuciones |
| Comparación con la entrega recibida | 377/378 artefactos idénticos; solo cambia la figura anual por la corrección de unidades de residuales a puntos porcentuales |
| Resultados numéricos, CSV y demás figuras | Permanecen idénticos |
| Exportación del JSON web desde una generación nueva | Idéntico byte a byte al incluido |
| Hashes de procedencia del JSON | 373/373 coinciden con los archivos públicos |
| Navegador local sobre el frontend rediseñado | 74 comprobaciones propias aprobadas; cero errores JavaScript y cero solicitudes externas |
| Patrones de credenciales, claves privadas y rutas sensibles | Sin indicios detectados; la coincidencia aparente de ruta en Plotly corresponde a sintaxis JavaScript |
| Metadatos de las cuatro figuras PNG | Solo identificación genérica del software |
| Manifiesto de publicación | 36 incluidos y 369 excluidos; sin archivos faltantes ni adicionales sin clasificar |

Las ejecuciones que generan archivos se realizaron en directorios temporales aislados. Únicamente se incorporó al proyecto la figura corregida y se actualizaron código de rotulación y documentos. La inspección visual puntual comprobó la figura en pp y la disposición de las claves y tablas del nuevo frontend.

Los nombres de señales, las fechas ficticias de 2042 y los valores incluidos se reconstruyen desde el generador público con semilla 781. No se detectaron identificadores operativos reales, registros privados ni resultados que dependan de históricos privados en el conjunto revisado. Las búsquedas por patrones y la reproducción sintética tienen un alcance técnico limitado; no equivalen a una garantía universal de confidencialidad.

## Procedencia declarada por el autor

El autor declara que el código se desarrolló con asistencia de Codex. La asistencia comprendió programación, dashboard y preparación de la demostración pública. El refinamiento visual posterior fue realizado con Claude Code, según el informe aportado por el usuario.

Los valores de la demostración pública se generan desde cero. Esta procedencia se comprobó mediante regeneración independiente; no se describe el conjunto como una anonimización de registros operativos reales.

## Antecedentes y controles históricos

El cierre anterior, previo al explorador, documentó 392 archivos, 13 pruebas aprobadas y reproducibilidad de 378 artefactos. La primera integración web añadió el exportador, sus cinco pruebas y el frontend. La auditoría independiente posterior comprobó 405 archivos, 18 pruebas y la reproducción completa de los artefactos.

Los siguientes cotejos contra otras fuentes permanecen **NO REPRODUCIDOS EN ESTA INTEGRACIÓN**. Sus listas y scripts de referencia no forman parte de la entrega:

- Nombres originales de señales, prefijos e identificadores operacionales.
- Cronología y nombres de archivos de fuentes excluidas.
- Hashes de archivos de fuentes excluidas.
- Fragmentos de 14 palabras consecutivas de documentación excluida.
- Secuencias de seis valores consecutivos con al menos cuatro valores distintos no nulos.

Los cierres anteriores también documentaron guardas Python con cero intentos de acceso privado o conexiones de red. Esas guardas temporales no se reejecutaron en esta integración y no constituían aislamiento universal del sistema operativo. Los controles actuales de red corresponden a las solicitudes observadas en el navegador local.

Los 18 tests y la regeneración sí se ejecutaron nuevamente. Esto no convierte los cotejos históricos contra material privado en verificaciones actuales.

## Dependencias y restricciones concretas

Plotly.js 3.7.0 se distribuye localmente con su licencia MIT, cabecera y avisos conservados. Su procedencia y hash están documentados en [THIRD_PARTY.md](../docs/assets/vendor/THIRD_PARTY.md). El bundle y el texto de licencia permanecen idénticos a la versión auditada. La verificación upstream documentada es un antecedente; no se descargó nuevamente la dependencia.

La revisión no identificó restricciones concretas de terceros sobre el código propio o la metodología. La declaración del autor describe el proceso de elaboración; no certifica titularidad ni descarta por sí sola obligaciones contractuales. No se ha aportado una confirmación adicional sobre tales obligaciones, ni se ha identificado un material o acuerdo específico afectado. Este pendiente documental no se clasifica como un bloqueo material sin evidencia adicional.

La obligación identificada para la dependencia es conservar los avisos de su licencia, incluidos en el manifiesto. No se ha incorporado una licencia de distribución para el código propio. La revisión no constituye asesoramiento ni certificación jurídica.

## Estado de publicación y límites

Git no está inicializado: no hay historial, ramas, etiquetas ni remotos locales que revisar. No se creó un commit, no se conectó el remoto y no se publicó contenido. El contenido del repositorio remoto y GitHub Pages permanecen sin verificar. No se instalaron dependencias ni se realizaron conexiones externas durante esta integración.

La instalación desde cero, otros sistemas, otros navegadores y una auditoría completa con lectores de pantalla permanecen fuera de las verificaciones efectuadas. Tampoco se ha validado experimentalmente el modelo físico ni la capacidad de diagnóstico o predicción industrial.

La revisión técnica permite solicitar autorización de commit y push del conjunto enumerado en [publication_manifest.json](publication_manifest.json). La ejecución de esas operaciones y la habilitación de Pages siguen sujetas a autorización explícita.
