# Encargo 88r: PLAN de la revisión cruzada de Spotify (sin cambios de código)

Rama `claude/encargo-88r-revision`, creada desde `base-88r`.

1. Leer el encargo y los resultados de la 88a, 88b y 88c, más sus revisiones (`88ar1–3`, `88br*`, `88cr`).
2. Revisar los diffs reales (`encargos-nube/88r-diffs/`) y el código vigente:
   - `pi/nodo-desplegar.py` (`RE_FUENTE` con `@`, `alta-enlace`, tope de tamaño, ligazón ✅ ↔ texto);
   - `pi/spotify/spotify@.service`, las plantillas y el bootstrap del LEEME;
   - `botv3/spotify.py` y la parte de Spotify de `botv3/botv3.py` (solo `127.0.0.1`, aislamiento entre
     perfiles, frases que no roben intenciones, nada de tokens ni textos en logs);
   - `pi/cargar-clave.py` y `update_telegram_commands.py`.
3. Correr las cuatro suites como la cola y separar las fallas del entorno de las reales.
4. Reproducir cada hallazgo con una prueba o un script en el scratchpad, sin tocar el repositorio.
5. Dejar `encargos-nube/88r-RESULTADO.md` con hallazgos [Grave]/[Media]/[Menor], «Lo que revisé y está bien»
   y la última línea `VEREDICTO: …`.
