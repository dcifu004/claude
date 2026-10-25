# Encargo 92b: las dos medias de la revisión de Codex al 90+92 (Claude (Diego) en la nube, 25-10-2026)

Partes de esta rama (`base-92b`): el 90 y el 92 ya mezclados sobre la 88b (que trajo Spotify), más este
archivo y la revisión de Codex (`encargos-nube/9092nr-RESULTADO.md`, léela entera). Salió **DESPLEGABLE**, con
dos medias que hay que cerrar antes de desplegar:

1. **[Media] `botv3/test_contador.py` sale a la red.** El recorrido de botones toca `menu:clima` sin
   reemplazar `datos_clima` (termina en `botv3.py` ~4507-4526, open-meteo), y el caso de voz no reemplaza
   `send_voice` (`SES_TELEGRAM.post`, ~5205-5214). En el `setUp`, reemplaza `datos_clima`, `send_voice` y
   cualquier transporte que pueda llegar a la red (`SES_TELEGRAM`, el buscador), y afirma las llamadas
   simuladas. Agrega una guarda que haga **fallar** la suite si algo intenta abrir una conexión real (por
   ejemplo, parchear `socket.socket.connect` o `urllib.request.urlopen` para que lance error).
2. **[Media] `/usos` deja fuera a `spotify` y `boleta` en «Sin usar nunca».** El catálogo que se arma en
   `botv3.py` ~8489-8498 no los incluye. Incluye `boleta` cuando esa ruta está activa en el perfil y
   `spotify` cuando el perfil tiene `spotify` configurado, o deriva el catálogo de lo que de verdad se puede
   alcanzar, con esas mismas condiciones. Prueba los dos casos (con y sin cada uno).

Cambia solo `botv3/test_contador.py` y el bloque del catálogo de `botv3/botv3.py`, en bloques chicos. Corre
`python3 botv3/test_botv3.py`, `python3 botv3/test_contador.py` y `python3 botv3/test_spotify.py` desde la
raíz, **como la cola**. Agrega a `encargos-nube/92-RESULTADO.md` una sección «Arreglos vuelta 1». Commit y
push en una rama nueva creada desde `base-92b`.
