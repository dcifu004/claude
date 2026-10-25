# Encargo 87b: arreglos de la revisión de Codex al 87 (Claude (Diego) en la nube, 25-10-2026)

Partes de esta rama (`base-87b`), que es el 87 tal como lo dejaste más este archivo. La revisión cruzada de
Codex en la Pi (`encargos-nube/87nr-RESULTADO.md`, léelo entero) lo dejó NO DESPLEGABLE. **Las 7 suites pasan
en la Pi**, así que lo que hay que hacer es cerrar los tres hallazgos, con pruebas nuevas en
`encargos/test_cierre_barato.py`:

1. **[Grave] Enlaces simbólicos.** Al leer `<id>-RESULTADO.md` y los informes previo y final del cierre
   (`cola-run.py` ~2456-2481, 2520, 2743, 2747), abrirlos con `O_NOFOLLOW`, comprobar con `fstat` que sean
   archivos regulares de tamaño acotado y que la ruta resuelta quede bajo `encargos/`. Ante un enlace o
   cualquier error, ESCALAR a la revisión completa. Prueba: con un enlace en `<id>-RESULTADO.md`, `correr()`
   no se llama para el cierre y el texto externo no aparece en el prompt.
2. **[Grave] Procesos hijos.** **Decisión del usuario: en TODAS las fases, no solo en el cierre.** Lanzar el
   CLI en una sesión o grupo de procesos propio (`start_new_session=True`) y, al vencer el tiempo o al
   terminar, matar el grupo entero (TERM, espera acotada, KILL) y confirmar que no quedan hijos. Prueba: un
   `claude` falso que lanza un hijo con PID conocido; al volver, ese PID ya no existe (la prueba actual con
   `exec sleep` no cubre esto). Prueba también que las fases normales (autor, rev, fix) sigan funcionando
   igual. C1 sigue valiendo para la salida de `--simular` y el flujo de fases.
3. **[Media] Colas vivas.** `decidir_cierre()` tiene que cruzar `f['vivas']` con la atribución que ya existe
   (`_fases_ajenas()` / `_propios_atribuidos()`). Si la foto del fix registra otra cola viva y su registro
   falta, está abierto, no se lee o comparte una ruta con el fix, va revisión completa. Pruebas con una
   cola ajena con foto cerrada, abierta e ilegible.

Al final, agrega a `encargos/87-RESULTADO.md` una sección «Arreglos vuelta 1» con lo cambiado y la salida
real de las pruebas. Commit y push en una rama nueva creada desde `base-87b`.
