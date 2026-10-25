# Encargo 91b: arreglos de la revisión de Codex al 91 (Claude (Diego) en la nube, 25-10-2026)

Partes de esta rama (`base-91b`), que es el 91 tal como lo dejaste más este archivo, la revisión
(`encargos-nube/91nr-RESULTADO.md`, léela entera) y **dos respuestas reales** que Claude (Diego) bajó en la Pi
el 25-10 a las 17:39 con `pi/temblores.py --guardar-fixtures`:
`pi/fixtures/temblores/real-usgs-20261025-2039.json` (23 sismos) y `real-emsc-20261025-2039.json` (2 sismos).
Los dos los leyó bien tu parser. **Dato importante:** en EMSC los dos eventos traen `auth = "EMSC"` y
`source_catalog = "EMSC-RTS"`, incluido uno frente a Perú. No hay evidencia de que vengan como `GUC`/CSN.

Hay que cerrar los cuatro hallazgos:

1. **[Grave]** `pi/test_temblores.py:114-115` compara contra las coordenadas reales de la casa. Usa un perfil
   temporal con coordenadas inventadas y comprueba que `casa()` devuelve las del temporal. No puede quedar
   **ninguna** coordenada de la casa en la suite ni en archivos nuevos.
2. **[Grave]** `pi/temblores.service:29` da escritura sobre todo `/opt/nodo/datos`. Limítalo a
   `/opt/nodo/datos/temblores` y a lo estrictamente necesario para la bandeja y el registro de `avisos`
   (mira qué crea y bloquea `encargos/registro_avisos.py`). Si hace falta un archivo en la raíz del volumen,
   deja documentado que se crea antes por el despliegue, en vez de abrir el directorio padre.
3. **[Media]** Con los `real-*.json`, la prueba `test_respuestas_reales_si_las_hay` ya no se salta: que
   pase, y que la suite afirme los campos que de verdad usa el parser.
4. **[Media]** `auth` de EMSC: con lo que muestran los datos reales, **no atribuyas el respaldo al CSN**.
   Documenta en el plan y en el RESULTADO que el respaldo es EMSC sin filtrar por autoridad, lee `auth`
   para mostrarlo en el aviso si sirve, y cubre con una prueba un evento de otra autoridad.

Agrega a `encargos-nube/91-RESULTADO.md` una sección «Arreglos vuelta 1» con lo cambiado y la salida
real de las pruebas. Commit y push en una rama nueva creada desde `base-91b`.
