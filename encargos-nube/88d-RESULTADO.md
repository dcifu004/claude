# Encargo 88d: RESULTADO de los arreglos de la revisión 88r (opción A)

Rama `claude/encargo-88d-arreglos-spotify`, creada desde `base-88r`. Plan en `88d-PLAN.md`. La revisión es
`encargos-nube/88r-RESULTADO.md` (rama `claude/encargo-88r-revision`), que dio **NO DESPLEGABLE** con 4 hallazgos
medios y 3 menores. El usuario eligió la **A** el 25-10: arreglar acá lo que se puede y dejar escrito lo de la Pi.

## Lo hecho, hallazgo por hallazgo

| Hallazgo de la 88r | Estado | Qué cambió |
|---|---|---|
| 1 [Media] `spotify@.service` sin aislamiento | **Escrito para la Pi** | `encargos-nube/88d-spotify@.service.propuesta`: `PrivateUsers`, `ProtectSystem=strict`, `ProtectHome=tmpfs`, `TemporaryFileSystem=/opt/nodo/datos` y `BindPaths` sólo de la carpeta de la instancia, más `NoNewPrivileges`, `RestrictAddressFamilies` y `SystemCallFilter`. No reemplaza la unidad: sin systemd de usuario no se puede probar acá (pasos abajo). |
| 2 [Media] `POST /token` de la API local | **Lo decide Diego** | Sin cambios: reabre el diseño 36 §5. |
| 3 [Media] «toca … de …» y «… de mi …» ponían música | **Arreglado** | `spotify.py:interpretar`: «toca» exige «en Spotify», como «pon» («tócame» queda igual). Un «artista» que empieza con posesivo, demostrativo o día (`mi/tu/su/nuestro`, `este/ese`, `ayer/hoy/mañana`) no se toma sin «en Spotify». Los artículos quedan fuera a propósito: «Tren al sur de Los Prisioneros» y «Mentira de La Ley» siguen siendo canciones. |
| 4 [Media] el otro receptor caído apagaba el propio | **Arreglado** | `botv3.py:atender_spotify`: el `/status` del otro sólo decide si hay que pausarlo. Si no contesta, cuenta como callado y queda en el log, sin URL. Sólo la falla del receptor propio contesta «No pude usar Spotify ahora.». |
| 5 [Menor] «sigue» a secas | **Arreglado** | `interpretar` marca el verbo solo (`sigue`, `continúa`, `reanuda`) con `sola: True`, y el bot lo toma únicamente si su receptor está en pausa (`paused: true`). Si no, la frase sigue su camino. «sigue con la música» no cambia. |
| 6 [Menor] sin `rapidfuzz` Spotify se apaga en silencio | Pendiente en la Pi | Comprobar `python3 -c "import rapidfuzz"` (paquete Debian `python3-rapidfuzz`) antes de desplegar. |
| 7 [Menor] `leer_fuente` sin `O_NONBLOCK` | Sin cambios | Viene de antes de la 88; vale un encargo aparte de `nodo-desplegar`. |

## Archivos tocados

- `botv3/spotify.py`: `interpretar`, dos bloques chicos.
- `botv3/botv3.py`: sólo `atender_spotify`, en un bloque.
- `botv3/test_spotify.py`: 5 pruebas nuevas.
  - `test_88d_frases_que_ya_no_roba` (9 frases, con y sin música sonando, más 5 que siguen siendo música);
  - `test_88d_sigue_a_secas_queda_marcado`;
  - `OtroReceptorYSigue88dTests`, con 3 pruebas (el otro caído, el propio caído y «sigue» a secas), todas con
    `spotify.estado` simulado y sin sockets.
- `encargos-nube/88d-PLAN.md`, `88d-RESULTADO.md` y `88d-spotify@.service.propuesta`.

## Pruebas (salida real, como la cola, desde la raíz)

```
                                          antes (base-88r)                          después
botv3/test_spotify.py                     ModuleNotFoundError: rapidfuzz            ModuleNotFoundError: rapidfuzz
botv3/test_spotify.py (con rapidfuzz)     OK  Ran 8 tests                           OK  Ran 13 tests in 1.279s
botv3/test_botv3.py                       FAILED (failures=7, errors=34) Ran 490    FAILED (failures=7, errors=34) Ran 490
botv3/test_botv3.py (con rapidfuzz)       igual                                     igual
```

La lista de fallas de `test_botv3.py` es **idéntica** antes y después (`diff` vacío). Son las del entorno de esta
copia: faltan archivos de la Pi, se corre como root y el huso es UTC. `rapidfuzz` no viene en esta copia: lo instalé
sólo en el scratchpad (`PYTHONPATH`) para correr `test_spotify.py`.

**Las pruebas nuevas contra el código anterior:** con `botv3.py` y `spotify.py` de `base-88r` y el
`test_spotify.py` nuevo, sale `FAILED (failures=21)`. Fallan las 18 comprobaciones de frases (9 frases, con y sin
música), la marca de «sigue» a secas, el otro receptor caído y «sigue» sin pausa. Cubren de verdad los tres
hallazgos.

## Hallazgo 1: cómo probar la unidad propuesta en la Pi

Como `dcifu004`, con la instancia de Jaime detenida (`systemctl --user stop spotify@jaime`):

```bash
systemd-run --user --wait --collect --pipe -p PrivateUsers=yes -p ProtectSystem=strict -p ProtectHome=tmpfs \
  -p TemporaryFileSystem=/opt/nodo/datos -p BindPaths=/opt/nodo/datos/spotify/jaime -p PrivateTmp=yes \
  -p NoNewPrivileges=yes -p "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" -p LockPersonality=yes \
  -p SystemCallFilter=@system-service \
  /bin/sh -c 'ls /opt/nodo/datos/spotify; cat /opt/nodo/datos/spotify/pilar/state.json; ls ~; ls $XDG_RUNTIME_DIR/pulse'
```

Lo esperado:
- sólo se ve `jaime`;
- `pilar/state.json` da «No such file»;
- `~` sale vacío;
- `pulse/native` está.

Después, la prueba de verdad: la misma línea con
`/usr/local/bin/go-librespot --config_dir /opt/nodo/datos/spotify/jaime` en vez del `sh`. Tiene que arrancar,
escuchar en `127.0.0.1:3678` (`ss -ltnp`), sonar y escribir `state.json`. Si `TemporaryFileSystem`/`BindPaths` no
funcionan en la unidad de usuario, la alternativa es un usuario de sistema por perfil, como dice la 88r. Recién
con eso andando se reemplaza `pi/spotify/spotify@.service`, se recalcula su hash en el LEEME y se pide el alta otra
vez.

## Lo que queda para la revisión cruzada

- Revisar 3, 4 y 5 en el diff de esta rama (`spotify.py`, `atender_spotify`, `test_spotify.py`).
- Probar el 1 en la Pi con los pasos de arriba.
- La decisión de Diego sobre el 2 (`/token`).
- Comprobar `python3-rapidfuzz` en la Pi (el 6).

## Riesgos abiertos

- La lista de palabras que no pueden empezar un «artista» es cerrada: un artista que de verdad empiece con «Mi»
  («Mi Banda …») necesita decir «en Spotify». Es el mismo costo que ya tiene «pon».
- «sigue» a secas con el receptor en pausa se toma como Spotify, aunque el usuario quisiera seguir una conversación.
  Es el caso en que lo más probable es la música.
- Si el receptor del otro perfil está caído y sonando de verdad (no contesta, pero suena), no se pausa antes del
  play propio. Queda en el log.
