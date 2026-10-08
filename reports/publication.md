# Preparación de Git y GitHub Pages

## Estado y autorización

Git local no está inicializado. No se creó un commit ni se configuró un remoto. El usuario declaró que creó el repositorio de destino; no se consultó su contenido ni se verificó si está vacío. El autor declara desarrollo con asistencia de Codex. La revisión técnica no identificó restricciones concretas de terceros; el alcance de esa conclusión y los pendientes documentales se detallan en privacy_audit.md. No se ha añadido una licencia para el código propio.

**No ejecutar los pasos siguientes sin autorización explícita.** Si queda incertidumbre material de confidencialidad, procedencia o derechos, no se debe publicar.

## Inventario

El cierre de integración confirma 405 archivos: 36 incluidos y 369 excluidos, sin faltantes ni archivos adicionales sin clasificar. Las 18 pruebas Python y 74 comprobaciones propias de navegador aprobaron. El rediseño se conserva y la figura anual usa puntos porcentuales para los residuales de dispersión. El conjunto está listo para solicitar autorización de commit y push.

`publication_manifest.json` enumera exactamente los archivos propuestos en su propiedad `included`. Se excluyen los 369 archivos regenerables de data y también runs, entornos, cachés y evidencia temporal. El JSON acotado del explorador en docs sí se incluye. Las reglas actuales de `.gitignore` no excluyen docs ni el exportador o sus tests.

## Pasos Git condicionados a autorización

Desde la raíz del proyecto, y solo después de aprobar el inventario:

```powershell
$publishFiles = (Get-Content -LiteralPath reports/publication_manifest.json -Raw | ConvertFrom-Json).included
git init -b main
git add -- $publishFiles
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
git ls-files -- data runs .venv
git diff --cached
```

La lista preparada debe coincidir exactamente con included y la consulta de data/runs/.venv debe estar vacía. Revisar el diff textual completo y abrir las cuatro figuras existentes. No continuar si hay archivos inesperados o posibles secretos. No usar git add . ni excluir la revisión por confiar únicamente en .gitignore.

Después de autorizar la conexión al remoto:

```powershell
git remote add origin https://github.com/giovanni-serrano/scada-data-analysis.git
git ls-remote --heads --tags origin
```

Si el remoto tiene historia, detenerse y revisar sus ramas y contenido antes de integrar. No asumir que está vacío. No forzar push, no sobrescribir historia y no aplicar automáticamente allow-unrelated-histories. Si está vacío y se ha autorizado el commit y el push:

```powershell
git commit -m "Add synthetic SCADA analysis and interactive explorer"
git push -u origin main
```

No se modificó la identidad Git. Si falta configuración de autor o permisos, debe resolverse con el usuario. Tras el push autorizado, comprobar la rama remota y la coincidencia del commit local.

## GitHub Pages: exposición pública separada

Solo después del push y de la autorización final para exposición pública:

1. En GitHub, abrir Settings → Pages.
2. En Build and deployment, elegir Deploy from a branch.
3. Seleccionar main y /docs; guardar.
4. Esperar el despliegue y comprobar que la URL responde correctamente.
5. Revisar las cinco vistas, assets locales y ventanas 72/24/6 en la URL pública.
6. Solo después de esa comprobación, cambiar el estado del enlace en README de pendiente a publicado.

Ruta prevista: https://giovanni-serrano.github.io/scada-data-analysis/

El sitio usa rutas relativas y docs/.nojekyll para servir los archivos estáticos sin transformación de Jekyll. Si la configuración requiere permisos o intervención manual, detenerse e informar. GitHub Pages puede exponer públicamente los archivos del sitio aunque el repositorio fuente sea privado.

Referencia oficial: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## Pruebas previas

Los resultados verificables están en web_validation.md y la auditoría ampliada en privacy_audit.md. La configuración de Pages, la URL pública y la historia remota permanecen NO VERIFICADAS. La revisión editorial no sustituye la revisión humana ni una certificación jurídica.
