# Encargo 88d: PLAN de los arreglos de la revisión 88r (opción A)

Rama `claude/encargo-88d-arreglos-spotify`, creada desde `base-88r`. Lo pidió el usuario el 25-10 («A»): arreglar
lo que se puede arreglar acá y dejar escrito lo que hay que probar en la Pi.

1. **Hallazgo 3 (frases):** en `botv3/spotify.py:interpretar`, «toca» se trata como «pon». Sin «en Spotify» no es
   música; «tócame» se queda igual. Además, un «artista» que empieza con posesivo o artículo de cosa (`mi`, `mis`,
   `tu`, `nuestro`, `la`, `el`…) no se toma sin «en Spotify». Nuevos casos de C2 en `botv3/test_spotify.py`.
2. **Hallazgo 4 (otro receptor caído):** en `botv3.py:atender_spotify`, el `/status` del otro sólo sirve para
   decidir si hay que pausarlo. Si falla, cuenta como «no suena» y queda en el log, sin URL. Sólo la falla del
   receptor propio contesta «No pude usar Spotify ahora.». Prueba con el otro puerto cerrado.
3. **Hallazgo 5 (menor, «sigue» a secas):** el verbo solo se toma únicamente si el receptor propio está en pausa
   (`paused: true`). Si no, la frase sigue su camino.
4. **Hallazgo 1:** la unidad endurecida queda escrita como propuesta (`pi/spotify/spotify@.service.propuesta`), con
   los comandos para probarla en la Pi. No reemplaza la unidad: no se puede probar sin systemd de usuario.
5. **Hallazgo 2 (`/token`):** no se toca; lo decide Diego.

Suites: `botv3/test_spotify.py` y `botv3/test_botv3.py`, como la cola, con la lista de fallas antes y después.
