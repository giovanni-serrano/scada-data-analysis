# Verificación de esta versión

Entorno: Windows, Python 3.13.5, NumPy 2.5.1, pandas 3.0.5, Matplotlib 3.11.1, Chromium 149.0.7827.55.

## Comprobado

| Control | Resultado |
| --- | --- |
| Pruebas automatizadas | 56 aprobadas |
| Dos ejecuciones independientes del pipeline | 379 de 379 artefactos idénticos byte a byte, incluidas las cuatro figuras |
| Artefactos del repositorio frente a una ejecución nueva | 379 de 379 idénticos |
| Evaluación de 120 años repetida | Resultados idénticos |
| JSON del dashboard | El exportador regenera el año demo y la evaluación y compara 375 entradas antes de escribir |
| Navegador a 390, 768 y 1440 px | 145 comprobaciones en las seis vistas: sin errores de JavaScript, sin peticiones externas, sin desbordamiento horizontal |
| Patrones de credenciales, claves privadas, correos y rutas de usuario en los 47 archivos versionados | Sin coincidencias |
| Metadatos de las siete figuras PNG | Solo el campo de software genérico |
| Plotly.js 3.7.0 | SHA-256 igual al documentado en `docs/assets/vendor/THIRD_PARTY.md`; licencia MIT incluida |

## Procedencia de los datos

Todos los valores salen de `src/generate_synthetic_scada.py` con semillas fijas. El generador no lee ningún archivo externo.
Los tags (`G1_P`, `G1_IA`, …) son inventados para este proyecto.

## Sin comprobar

- Instalación desde cero, otros sistemas operativos y otros navegadores.
- Auditoría de accesibilidad con lectores de pantalla.
- El sitio público, que no cambia hasta fusionar esta rama.
