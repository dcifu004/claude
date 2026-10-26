# Encargo 88e + 92c: RESULTADO (cierre de las revisiones 88dnr1 y 92bnr1)

Hecho por Claude (Diego) en la nube el 26-10-2026, en la rama `claude/encargo-88e-92c-arreglos`, creada desde `base-88e`
(`a23ea8e`). El primer commit es el PLAN.

El alcance quedó cerrado en los cuatro arreglos, en bloques chicos. No toqué los hallazgos 4 y 5 de la 88dn,
`cola-run.py`, `pi/`, nada de 96, 97 o 101, ni los correos tapados.

## Qué cambió

### 1. 88dn h1 [Media]: la unidad propuesta (`encargos-nube/88d-spotify@.service.propuesta`)

- `ProtectHome=tmpfs` se mantiene.
- Agregué `BindReadOnlyPaths=%t/pulse`: vuelve a exponer **sólo** la carpeta del socket de PipeWire de
  `$XDG_RUNTIME_DIR`, de sólo lectura. Conectar a un socket Unix funciona igual sobre un montaje de sólo lectura,
  como probó la 88dnr1.
- El comentario ahora dice lo correcto: `ProtectHome=` tapa `/home`, `/root` **y `/run/user`**. Lo demás de
  `/run/user/<uid>` (`bus`, `gnupg`, `openssh_agent`, `credentials`) sigue tapado.
- Sólo cambió el archivo de propuesta: no se activó ni se dio de alta nada.

### 2. 88dn h2 [Media]: «sigue» a secas con el receptor propio caído (`botv3/botv3.py`, `atender_spotify`)

- En la rama de error del `/status` propio (`if base == cfg["api"]:`), la condición pasa de `if inicial:` a
  `if inicial and not inicial.get("sola"):`.
- Así «sigue», «continúa» o «reanuda» a secas con el receptor propio caído devuelven `False` sin decir nada: la frase
  sigue como conversación, igual que «pausa» a secas.
- Una frase de música, como «sigue con la música» o «reproduce …», sigue respondiendo «No pude usar Spotify ahora.».
- Son 3 líneas, dentro de esa función.
- **Prueba nueva**, junto a `test_hallazgo_5_sigue_a_secas_solo_en_pausa` en `botv3/test_spotify.py`:
  `test_88e_sigue_a_secas_con_el_propio_caido_es_conversacion`.
  - Pasa por «sigue», «Sigue.», «continúa», «reanuda», «Jaime, continúa» y «Jaime, sigue» con el propio caído
    (`SpotifyError`): da `(False, [], [])`.
  - Repite el caso hermano «pausa» y fija «sigue con la música», que da el error.
  - Contra el `botv3.py` anterior falla 6 veces (una por variante): muerde.

### 3. 88dn h3 [Media]: posesivos después del segundo «de» (`botv3/spotify.py`, `interpretar`)

- El filtro pasa de `re.match(…, m.group(2))`, que miraba sólo lo que sigue al **primer** «de», a
  `re.search(r"\bde\s+(?:mis?|tus?|sus?|nuestr[oa]s?|est[eao]s?|es[eao]s?|ayer|hoy|manana|anoche|recien)\b", frase)`.
- Ahora busca en **cualquier** « de <palabra> » de la frase, y suma «anoche» y «recién» (en `frase`, que ya viene sin
  tildes). Sigue aplicando sólo si no se dijo «en Spotify».
- **`NO_88D`** suma:
  - «reproduce la nota de voz de mi mamá»;
  - «reproduce la canción de cuna de mi hija»;
  - «reproduce la grabación de anoche»;
  - «reproduce el mensaje de voz de recién»;
  - «reproducir la clase de hoy de mi hijo».
- **`SI_88D`** suma «reproduce Mi Gente de J Balvin», «reproduce Hoy de Gloria Trevi» y «reproduce la nota de voz de
  mi mamá en Spotify»: dicho con Spotify, sigue siendo canción. Ya estaban «Tren al sur de Los Prisioneros» y
  «Mentira de La Ley», y siguen pasando.
- **Barrido**, igual que la revisión: pasé por `interpretar(…, False)` y `interpretar(…, True)` las 4.736 cadenas
  literales de `botv3/test_*.py`, antes y después:

  ```
  antes:   4736 cadenas; 24 capturadas
  después: 4744 cadenas; 27 capturadas      (las 8 de más son las frases nuevas de NO_88D/SI_88D)
  cadenas comunes: 4736 | capturas nuevas: 0 | dejan de capturarse o cambian: 0
  ```

  **0 capturas nuevas.** Las 3 capturas de más del después son las tres de `SI_88D` nuevas, que son música a
  propósito.

### 4. 92bn h1 [Grave]: `test_contador.py` en rojo con Spotify presente (`botv3/test_contador.py`)

- En el `setUp` de `Base`, cuando `b.spotify_mod` existe, se simulan con `mock.patch.object` (y su `stop` en
  `addCleanup`) las dos lecturas que usa `/spotify`:
  - `estado` contesta con `status_detenido`, la forma real del fixture de go-librespot v0.10.5 de la 88b;
  - `codigo` contesta `None`.

  Las dos anotan la llamada en `self.receptor`.
- `test_cada_comando` afirma que `/spotify` pasó **una vez** por `estado` con la URL del bloque `spotify` del perfil
  Jaime (`http://127.0.0.1:3678`), y que el bot contestó «vinculado, sin música».
- **La guarda de red no se tocó:** sigue siendo la última barrera.
- Comprobé que la afirmación corre con la forma real (`spotify.py` importable y el bloque `spotify` de
  `perfiles/jaime.toml`): si la cambio por un valor falso, la prueba falla con
  `[('estado', 'http://127.0.0.1:3678')] != ['MUTANTE']`.

## Las suites, antes y después

La salida completa está en `encargos-nube/88e-fallas-antes-despues.txt`.
- **Cómo corrí:** las 7 desde la raíz, como la cola, con `NODO_PRUEBAS=1` y `BOTV3_STATE_DIR`, `BOTV3_USO_CUENTAS` y
  `BOTV3_USO_RUTAS` en un `mktemp -d`.
- **`rapidfuzz`:** aquí no está instalado. Corrí cada suite de dos formas: con una copia de `rapidfuzz` en el
  scratchpad (`PYTHONPATH`), que deja `botv3/spotify.py` importable y es la forma real de la Pi, y sin ella.

| Suite | Antes (con `rapidfuzz`) | Después (con `rapidfuzz`) |
|---|---|---|
| `botv3/test_spotify.py` | 13 OK | **14 OK** (la prueba nueva) |
| `botv3/test_contador.py` | **FAILED (1)**: `["socket.getaddrinfo ('127.0.0.1', 3678)"] != []` | **20 OK** |
| `botv3/test_botv3.py` | 491, FAILED (7 F, 34 E) | 491, FAILED (7 F, 34 E): la misma lista |
| `botv3/test_sala.py` | 33 OK (1 saltada) | 33 OK (1 saltada) |
| `botv3/test_selectores.py` | 31, FAILED (1 E) | 31, FAILED (1 E): la misma |
| `botv3/test_bluetooth.py` | no se importa | no se importa: lo mismo |
| `pi/spotify-web/test_spotify_web.py` | 20 OK | 20 OK |

Sin `rapidfuzz`, `test_spotify.py` no se importa (`ModuleNotFoundError: No module named 'rapidfuzz'`), antes y
después. `test_contador.py` daba OK antes y después, porque sin `spotify.py` el camino de `/spotify` no se ejercita:
por eso el hallazgo no se veía en la nube. Las demás suites dan lo mismo que con `rapidfuzz`.

**Ninguna falla nueva.** Las que quedan son del entorno de esta copia y son idénticas antes y después:
- `test_botv3`:
  - `VisionTests` y `NoticiasTests`: la nube corre como root, y un modo 000 no le impide nada;
  - el puente de agenda (66r1, 68r1, 73);
  - `ClimaAvisoTests`;
  - `ParaPilarTests`;
  - `CadenaDeCuentasTests`.
- `test_selectores`: `bots_info_96b` no tiene `cuenta_tecnica_de`, porque el `pi/bots-info.py` de esta base es el
  anterior al 96.
- `test_bluetooth`: falta `encargos/fixtures/101/secuencia-s22.json`.

## Archivos tocados

- `botv3/botv3.py`: `atender_spotify`, 3 líneas.
- `botv3/spotify.py`: `interpretar`, el filtro de posesivos.
- `botv3/test_spotify.py`: `NO_88D`, `SI_88D` y la prueba nueva.
- `botv3/test_contador.py`: el `import mock`, `RECEPTOR_DETENIDO`, la simulación en `Base.setUp` y la afirmación en
  `test_cada_comando`.
- `encargos-nube/88d-spotify@.service.propuesta`.
- `encargos-nube/88e-PLAN.md`, `88e-fallas-antes-despues.txt` y este RESULTADO.

## Pendientes

- **88dn h4 [Baja], artículos:** «reproduce el audio de la reunión», «… de la semana», «… de los niños» y
  «… de economía» siguen poniendo música. Queda para que el usuario decida si un título que empieza con artículo de
  cosa (`el audio`, `la nota`, `el video`, `la grabación`, `el resumen`) también exige «en Spotify». No lo toqué.
- **88dn h5 [Baja], «sigue» sin pausar el otro receptor:** la rama `sigue` reanuda el propio sin pausar el otro que
  suena. No lo toqué.
- **La unidad propuesta:** falta probarla en la Pi con el go-librespot real y `BindReadOnlyPaths=%t/pulse`: que suene
  y que escriba `state.json` y el lockfile. Recién ahí se reemplaza `pi/spotify/spotify@.service`, se recalcula su
  hash y se pide el alta. Si se despliega el 100 (`spotify-web@`), esta unidad queda sólo para la vuelta atrás.
- **El hallazgo 2 de la 88r** (`POST /token` del receptor): sigue esperando la decisión del usuario.
- Falta correr las suites en la Pi, donde `rapidfuzz` está y no faltan fixtures. La revisión cruzada y el despliegue
  los hace la Pi.
