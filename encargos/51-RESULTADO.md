# Resultado 51 — consultas al usuario entre fases, versión mínima

Autor: Claude (Diego). 16/17-10-2026. Revisión prevista según el manifiesto.
Copias de los originales antes de editar: `~/encargos-logs/autor51/antes/encargos/` (`cola-run.py`,
`revision-plantilla-v2.md`, `test_acciones_cola.py`).

## 1. Premisa del canal (C6), con evidencia

Se usa la **vía de botones sin root**: los botones de `nodo-desplegar sugerir`. `nodo-desplegar` no se tocó.

**Quién atiende los botones.** Sólo el escucha root; el binario instalado es idéntico al del vault:

```text
$ sha256sum pi/nodo-desplegar.py /usr/local/bin/nodo-desplegar
fd51822111d7cca7b9398177d8564e7dbb0d46bfb63a50e11a06ef76fb02ee5c  pi/nodo-desplegar.py
fd51822111d7cca7b9398177d8564e7dbb0d46bfb63a50e11a06ef76fb02ee5c  /usr/local/bin/nodo-desplegar
$ ps -eo user,pid,args | grep 'desplegar escuchar'
root       71836 /usr/bin/python3 /usr/local/bin/nodo-desplegar escuchar
$ grep -n -E 'VENCE_S|allowed_updates|callback_query|CHAT_ID|nonce|RESULTADOS|Listo, lo corr|No lo voy' pi/nodo-desplegar.py
42:4. El callback vale solo si viene del CHAT_ID de [el usuario], con el nonce del pedido, antes de
43:   que venza y una vez. El token no puede fabricar un toque: Telegram firma el from.id.
95:RESULTADOS = SPOOL / "resultados"  # root 755, archivos 644 — lo lee `esperar`
105:VENCE_S = 30 * 60
814:            return {"inline_keyboard": [[{"text": "✅ Listo, lo corrí", "callback_data": cb("ok2")},
815:                                         {"text": "❌ No lo voy a correr", "callback_data": cb("no")}]]}
828:                      allowed_updates=["callback_query"])
832:            q = u.get("callback_query")
845:        if str(q["from"]["id"]) != self.chat or str(q["message"]["chat"]["id"]) != self.chat:
853:        if not p or not secrets.compare_digest(nonce, p["nonce"]):
857:            return self.cerrar(p, "rechazado", "rechazado por [el usuario]")
869:            return self.cerrar(p, "hecho", "[el usuario] dice que lo corrió")
```

(En la salida de arriba, el nombre propio que trae el código se reemplazó por «[el usuario]»: 51r1, hallazgo 4.)

`sugerir` trae «✅ Listo, lo corrí» (`hecho`) y «❌ No lo voy a correr» (`rechazado`); `limpiar()` cierra
en `vencido` a los 30 min (`VENCE_S`, línea 105). El precedente ya está en la cola:
`pedir_autorizacion()` (`encargos/cola-run.py`) pide los modelos con candado con un `sugerir` + `echo` + `esperar`.

**Un agente no puede fabricar un `hecho`.** Los resultados son de root:

```text
$ ls -ld /var/spool/nodo-desplegar/resultados; ls -l /var/spool/nodo-desplegar/resultados | tail -1
drwxr-xr-x 2 root root      4096 Oct 16 22:57 /var/spool/nodo-desplegar/resultados
-rw-r--r-- 1 root root 120 Oct 16 22:57 20261016-225750-e1c8.json
$ id
uid=1000(dcifu004) gid=1000(dcifu004) groups=...
$ touch /var/spool/nodo-desplegar/resultados/x.json
touch: cannot touch '/var/spool/nodo-desplegar/resultados/x.json': Permission denied
```

Además la cola sólo acepta un resultado que sea archivo corriente, sin enlaces (`O_NOFOLLOW`), con dueño
uid 0, con el `id` del pedido y estado `hecho` (`leer_resultado()`).

**Descartado: texto por el bot de captura.** Corre con el mismo uid que los agentes y escribe en `00-Inbox`:

```text
$ systemctl show -p User,ExecStart captura-telegram.service
ExecStart={ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 /opt/captura/captura_telegram.py ; ... }
User=dcifu004
$ grep -n 'POR_DEFECTO' /opt/captura/captura_telegram.py
71:POR_DEFECTO = "00-Inbox"
```

Cualquier agente (uid dcifu004) escribiría en `00-Inbox` una «respuesta» indistinguible: no sirve para
«sólo contesta el usuario». Tampoco se usa `/consulta …` por botv3 (no se toca su router).

## 2. Diseño y decisiones justificadas

- **Una consulta = una ronda de 3 `sugerir`**, uno por opción, en orden aceptar / arreglar / saltar. Cada línea
  es un `echo` con un único argumento que nombra la opción (`echo 'consulta cola46 #1: arreglar'`). La
  pregunta (≤ 600 caracteres) viaja en la línea de «Aceptar y seguir»: el motivo de `sugerir` se corta en
  200 caracteres (CLI y escucha), y la línea admite 1000; así la ronda sigue siendo de 3 mensajes. El motivo
  dice «tocar ✅ en ESTE mensaje = «…». ❌ no cuenta como respuesta». La respuesta es el primer `hecho` de
  cualquier ronda (por la `hora` del resultado; empate: arreglar > saltar > aceptar, lo más conservador).
- **Plazo de 2 h vs. 30 min de cada botón:** se **reenvía la ronda al vencer**, como máximo hasta el plazo:
  rondas a los 0, 30, 60 y 90 min (tope `CONSULTA_PLAZO_S // CONSULTA_RONDA_S` = 4, 3 mensajes cada una).
  Respeta la decisión cerrada del usuario (2 h) y siempre hay botones vivos; la alternativa «30 min + defecto»
  le habría acortado el plazo a la cuarta parte. Los botones de rondas anteriores siguen valiendo mientras no
  venzan.
- **Quién recoge la respuesta y aplica el defecto:** un **timer de usuario nuevo** (`consultas.timer`, cada 5
  min) que corre `cola-run.py --consultas`. No el despachador de la 55: el despachador puede estar en pausa
  (pausa general del 11-10) y su regla es «una cola por pasada si no hay ninguna viva»; una respuesta tiene
  que atenderse aunque haya otra cola corriendo, y así no se toca el código ni las pruebas de la 55. El
  despachador ya ignora una cola `en_consulta` («está en «en_consulta», se salta; lo decide el usuario»).
- **Estacionar:** la cola sale con código 6 y el vivo queda `estado = en_consulta`, `reanuda_desde =
  <etapa>:fix<N>`, `consulta = {n, etapa, fase, pregunta, hallazgos, desde, plazo, defecto,
  otras_esperando, rondas[{enviada, ids}]}` y `consultas_n`. La sesión tmux termina: la cadena sigue.
- **Al contestar:** `aceptar` y `arreglar` relanzan por `accion_cola("reanudar")` (46c): mismo camino del botón
  Reanudar, que respeta el despacho de la 50a y deja su línea en `acciones.jsonl`. `aceptar` además anota
  `aceptadas_usuario` en el vivo; al relanzar, `etapa()` salta ese arreglo **sólo si vuelve a leer el ✅ del
  escucha root** para ese pedido (una aceptación escrita a mano en el vivo no salta nada). `saltar` deja la
  cola estacionada; se retoma con Reanudar (`_puede()` acepta ahora `en_consulta`).
- **Defecto:** «otras colas esperando» = otro vivo activo y fresco (< 2 h), una pausada por cuota, o una cola
  de `prioridad.txt` que nunca partió. Con otras → saltar; si es la última → arreglar.
- **Descanso:** al disparar en descanso no se pregunta y se aplica el defecto en el momento (arreglar sigue en
  el mismo proceso; saltar estaciona). No cuenta para el tope. Si el descanso empieza con una consulta abierta,
  no se manda otra ronda: al vencer la ronda viva se aplica el defecto en silencio.
- **Cuándo se pregunta:** sólo en una revisión NO DESPLEGABLE a la que le sigue un arreglo (`rev1`/`rev2` con 2
  vueltas). La última revisión no pregunta: no hay arreglo que ofrecer y agregar fases sería una función nueva.

## 3. Cambios por archivo

- `encargos/cola-run.py` (3742 → 4187 líneas):
  - sección nueva «consultas entre fases (encargo 51)» (línea 2769), antes de los botones de la 46c:
    `_es_cola`, `hallazgos`/`disparador` (títulos `### N. [Grave|Media|Baja]`; se lee la primera palabra de
    la etiqueta: `[Media, y es lo que…]` es media, `[Menor]` es baja, `[Importante, …]` es «otra» y no
    pregunta), `armar_pregunta` (≤ 600, títulos escapados), `lineas_consulta`, `SUGERIR_CONSULTA`
    (`nodo-desplegar sugerir`, inyectable; un agente con `NODO_PRUEBAS=1` no manda nada), `enviar_ronda`,
    `en_descanso` (`EN_DESCANSO` inyectable; si no, `pi/descanso.py`), `leer_resultado`, `respuesta_de`,
    `otras_esperando`, `anotar_decision` (anexado con `flock`, `O_NOFOLLOW`, 0644), `_aceptada`,
    `consultar_o_seguir`, `_atender`, `atender_consultas` (bajo `flock` de `vivo/consultas.lock`; el vivo
    se reemplaza con `_escribir_vivo`, atómico).
  - `etapa()`: tras un NO DESPLEGABLE con arreglo detrás llama a `consultar_o_seguir` (línea 2614); al
    reanudar desde un `fix` aceptado y verificado, la etapa termina en verde sin arreglar (línea 2469).
  - `prompt_de()` del arreglo: si existe `encargos/<id>-decisiones.md`, lo manda a leer (línea 2308).
  - `desplegar()`: con alguna etapa aceptada, si hay entradas del catálogo (root), si no hay diff propio
    verificable o si se tocaron secretos, no se pide el despliegue ni se manda la línea (línea 2708).
  - `_puede()`: Reanudar vale para `en_consulta`. `heredar_vivo()`: conserva `consultas_n` y
    `aceptadas_usuario`. `main()`: `except Consulta` → `en_consulta`, código 6; opción `--consultas`.
  - No se tocó la pausa por cuota, el despacho, el diff de la 53, la fase plan de la 54 ni `nodo-desplegar`.
- `encargos/revision-plantilla-v2.md`: dos viñetas nuevas, sin marcadores nuevos (la rev3 de `cola41` la
  lee con el `cola-run.py` viejo en memoria): leer `encargos/{ID}-decisiones.md` y **lo decidido no se vuelve
  a marcar**; y el formato obligatorio `### N. [Grave|Media|Baja] …` con qué es [Grave].
- `encargos/consultas.service` y `encargos/consultas.timer` (nuevos, de usuario, **no instalados**).
  `KillMode=process` porque la reanudación crea la sesión tmux (55r1, hallazgo 1).
- `encargos/test_consultas.py` (nuevo, 33 pruebas).
- `encargos/test_acciones_cola.py`: **una línea**. Esa prueba cuenta los `RE_COLA.<método>(` de todo
  `cola-run.py` (eran 4, todos `fullmatch`); la 51 agrega uno (`_es_cola()`, también `fullmatch`) y la
  cuenta pasa a 5, con el comentario. La otra prueba estructural que fallaba (sin `os.environ` en la sección
  de botones) se arregló moviendo la sección 51 fuera de ese tramo, sin tocar la prueba.

## 4. Criterios

Pruebas con canal falso (`SUGERIR_CONSULTA` que devuelve ids con la forma `\d{8}-\d{6}-[0-9a-f]{4}`), resultados
del escucha en un `resultados/` temporal (dueño esperado: el uid de la prueba; en producción, 0), reloj
inyectado, `principal()` real con motor de mentira y títulos copiados de revisiones reales.

| Criterio | Estado | Pruebas (`encargos/test_consultas.py`) |
| --- | --- | --- |
| C1 | Cumplido | `C1Disparador`: sólo Media/Baja pregunta (3 mensajes, `en_consulta`, `46a:fix1`, pregunta ≤ 600, sin avisos extra); un `[Grave]` (57br1) va al arreglo sin mensajes; `[Importante, pide decisión]` (55r2) y la revisión sin títulos, como antes; la última revisión no pregunta; la tercera pregunta de la cola no se hace (#1 en 46a:rev1, #2 en 46a:rev2, la de 46b:rev1 va al arreglo). Revisiones reales: 57br1, 52br1 y 55r2 no preguntan; 58r2 sí. |
| C2 | Cumplido | `C2Descanso`: con descanso no hay mensajes; siendo la última corre `fix1` y anota «defecto, en silencio: modo descanso»; con otra cola esperando queda `en_consulta` con `saltar`. Se consultó con la hora inyectada. Con la biblioteca real `pi/descanso.py` (config y caché en temporal): martes 02:00 → descanso, 18:55 → no; a las 01:30 no pregunta. |
| C3 | Cumplido | `C3Respuestas`: aceptar relanza `--desde 46a:fix1` y la corrida siguiente salta a `46b-autor`; arreglar corre `46a-fix1` y el prompt del arreglo nombra `46a-decisiones.md`; saltar no relanza y Reanudar (46c) la retoma; las tres dejan su línea en `46a-decisiones.md`. ❌ no es respuesta; el primer ✅ gana. Un resultado que no es de root, con otro id o enlazado se ignora y se anota una sola vez («respuesta IGNORADA (no viene del chat del usuario)»). Una aceptación fabricada en el vivo no salta el arreglo. Con la sesión viva no se toca nada. |
| C4 | Cumplido | `C4Plazo`: 4 rondas en 2 h (12 mensajes) y un botón de la primera ronda sigue valiendo; plazo vencido con `cola47` esperando → `saltar`, sin relanzar, `en_consulta`; siendo la última → `arreglar`, relanzada desde `46a:fix1`; descanso con la ronda vencida → defecto sin preguntar; `cola-run.py --consultas` por la línea de comandos. |
| C5 | Cumplido | `C5Despliegue`: sin aceptación el despliegue sigue llamando `nodo-desplegar pedir` y `esperar` (el ✅); con aceptación y una entrada del catálogo (root), con secretos o sin diff verificable no se llama a `nodo-desplegar` ni se manda la línea; con aceptación y nada desplegable termina como siempre. |
| C6 | Cumplido | Sección 1 de este informe. |
| C7 | Cumplido | Salida abajo: la suite nueva y las del manifiesto en verde. |

Invariantes (`Invariantes`): la pregunta con títulos hostiles (`<script>`, salto de línea, `'; rm -rf ~ #`,
`XXX TODO`, U+202E, 400 caracteres ×5) sale sin `< > ' \n U+202E XXX TODO`, ≤ 600, y **el `sugerir()` real de
`pi/nodo-desplegar.py`** acepta las tres líneas (con `_dejar` reemplazado: nada llega al spool), cada una un
`echo` con un solo argumento y motivo ≤ 200; una respuesta fuera de la lista cerrada (`root`) se ignora y se
anota; una etapa `../x` se rechaza; los nombres hostiles de la 46c no leen resultados; 20 hilos anexan a
`decisiones.md` sin perder líneas; el panel ofrece Reanudar a una cola en consulta; la plantilla conserva sus
marcadores.

### Salida real (17-10, 00:38, `NODO_PRUEBAS=1`)

```text
== encargos/test_consultas.py
Ran 33 tests in 17.366s
OK
== pi/test_descanso.py
Ran 16 tests in 0.375s
OK
== pi/test_avisos.py
Ran 93 tests in 0.332s
OK
== encargos/test_matriz_cuota.py
Ran 28 tests in 4.326s
OK
== encargos/test_acciones_cola.py
Ran 48 tests in 7.560s
OK
== encargos/test_pronostico.py
Ran 6 tests in 0.137s
OK
== encargos/test_fase_plan.py
Ran 8 tests in 0.248s
OK
== encargos/test_diff_propio.py
Ran 9 tests in 0.769s
OK
== encargos/test_despachador.py
Ran 21 tests in 0.069s
OK
== pi/test_cockpit_paginas.py
Ran 161 tests in 28.864s
OK
== botv3/test_botv3.py
Ran 233 tests in 1.463s
OK
== encargos/test_despacho.py            (extra, no estaba en la lista)
Ran 36 tests in 6.086s
OK
== encargos/test_versiones.py           (extra, no estaba en la lista)
FAIL: test_el_arbol_real_no_tiene_git_dentro (__main__.RecuperarTests.test_el_arbol_real_no_tiene_git_dentro)
Ran 45 tests in 1.677s
FAILED (failures=1)
```

La falla de `test_versiones.py` es previa: la línea base tomada a las 23:30 del 16-10, antes de editar, dio la
misma (`~/encargos-logs/autor51/base.txt`); depende del `.git` del árbol, no de este encargo. Las suites de
`cola41` (`botv3/test_compras.py` «✅ todo en verde», `pi/test_cuentas_uso.py` 74 OK, `pi/test_uso.py` 7 OK)
también siguen en verde. Las pruebas no dejaron nada en el `vivo/` real ni un `*-decisiones.md` en `encargos/`.

## 5. Instalación (no ejecutada)

**Obsoleta desde los arreglos de la vuelta 1:** `consultas.service` y `consultas.timer` se retiraron; la cola
arma un timer transitorio y no hay nada que instalar (ver «Arreglos vuelta 1», hallazgo 2).

No se instaló ni habilitó nada. Con `cola41` viva y la pausa general vigente, conviene hacerlo cuando
`cola41` termine y el usuario levante la pausa. Es de usuario, sin root:

```text
mkdir -p ~/.config/systemd/user && cp /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/consultas.service /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/consultas.timer ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now consultas.timer
```

Sin el timer, una cola que pregunta queda `en_consulta` hasta que alguien toque Reanudar en 🧵 Encargos (que
equivale a «arreglar»); nada se pierde. El código nuevo de `cola-run.py` corre desde la próxima cola que parta;
la `cola41` en marcha sigue con el que cargó al partir.

## 6. Límites y pendientes

- **Mismo uid:** un agente puede reescribir el vivo (estado, `reanuda_desde`). Lo que decide —que hubo una
  respuesta y cuál— sale siempre del resultado de root; una aceptación sin ✅ verificable no salta nada. Al
  relanzar, la aceptación se vuelve a verificar contra `resultados/`, que el escucha borra a los 7 días: pasado
  eso, una aceptación ya no salta el arreglo (falla hacia lo conservador). Es el mismo límite aceptado del
  buscador (09-10).
- **La vista:** `pi/cockpit-encargos/encargos.js` no tiene etiqueta para `en_consulta` (sí para
  `pausada_por_usuario` y `retenida_por_despacho`); no se verificó cómo lo pinta. El botón Reanudar sí se
  ofrece (lo decide `_puede()`, probado). Ver y contestar la consulta en 🧵 es la ampliación prevista, fuera de
  alcance.
- **Aviso del defecto:** al vencer el plazo el defecto se aplica sin mensaje extra (queda en
  `<id>-decisiones.md`, en el vivo y en el journal del timer), para no pasar de 3 mensajes por ronda.
- El botón dice «✅ Listo, lo corrí» porque es el de `sugerir`; el motivo de cada mensaje explica que ✅ elige
  esa opción. Cambiar el texto del botón exige tocar `nodo-desplegar`, fuera de alcance.

## Arreglos vuelta 1

Autor: Claude (Diego), 17-10-2026, sobre `encargos/51r1-RESULTADO.md` (Codex, NO DESPLEGABLE). Sin sudo, sin desplegar,
sin tocar `nodo-desplegar`, n8n ni los perfiles. Reemplazos puntuales, LF. La versión revisada quedó copiada en
`~/encargos-logs/autor51/arreglo1-retirados/` (`cola-run.py.revisado-51r1`, `test_consultas.py.revisado-51r1`, sacadas de
la foto git `bdb41219` de la fase fix1), junto con las dos unidades retiradas.

Todo el cambio de `cola-run.py` cae en la sección «consultas entre fases (encargo 51)», más un comentario y tres líneas
en `main()`: +177/−37 líneas (4187 → 4327). No se tocó la pausa por cuota, el despacho, el diff de la 53, la fase plan de la 54, la
sección de botones de la 46c ni la plantilla.

### Hallazgo 1 [Grave] — la pregunta salía del volumen cifrado por `sugerir`

**Qué cambió.** Lo que va a `nodo-desplegar sugerir` (motivo y línea) ya no lleva texto de la revisión. Sale de un
vocabulario cerrado, `resumen_canal()`: el nombre de la cola (`RE_COLA`), el id de la etapa (`RE_ETAPA`), la fase
(`rev[0-9]`), el número de consulta y **cuántos** hallazgos hay de cada gravedad, más el archivo donde leerlos. Por ejemplo:

```text
echo 'consulta cola46 #1: aceptar · etapa 46a, rev1 NO DESPLEGABLE sin graves: 2 [Media] y 2 [Baja]. Los títulos están en encargos/46ar1-RESULTADO.md (no salen del volumen cifrado). Sin respuesta en 2 h: saltar si hay otras colas esperando; si no, que lo arregle.'
```

`resumen_canal()` y `lineas_consulta()` rechazan (`ValueError`) una cola, etapa, fase o número fuera de patrón. Las
rondas siguientes rehacen el resumen con lo validado (etapa, fase y el conteo de `hallazgos`): no copian ningún texto
del vivo. La pregunta con los títulos (`armar_pregunta()`, ≤ 600, escapada) sigue armándola la cola, pero queda sólo
dentro del volumen: en el vivo y en `<etapa>-decisiones.md`.

**Decisión conservadora (ambigua, anotada).** El encargo pedía que la pregunta llevara los títulos, y 51r1 pide que no
salgan del volumen. Se prefirió no sacarlos: el usuario ve en Telegram cuántos hallazgos hay y de qué gravedad, y lee
los títulos en el vault. Se descartó mandarlos por la bandeja de `avisos.py`: está dentro del cifrado, pero en descanso
`descanso.encolar()` los deja en `/var/lib/nodo/descanso-cola.jsonl`, fuera de él (basta que el aviso salga después de
las 23:45 o que un envío falle y se reintente de noche). Si el usuario quiere los títulos en el mensaje, hace falta un
canal que no persista fuera de LUKS: es una decisión suya, no un arreglo.

**Pruebas** (`Hallazgo1NadaDeLaRevisionFueraDelVolumen`, en `encargos/test_consultas.py`):

- `test_la_consulta_no_lleva_titulos_y_el_escucha_real_no_los_guarda`: la cola de verdad (`principal()`) pregunta sobre
  una revisión con tres títulos reales de 52br1 y uno con la forma de los reales, que trae una ruta de
  `vault_personal/20-Personas` y un RUT. Los tres motivos y las tres líneas calzan **enteros** con la expresión del
  vocabulario cerrado. Después cada mensaje pasa por el `sugerir()` del CLI real y por `Escucha.preparar_sugerencia()`
  del `pi/nodo-desplegar.py` real, con `ESTADO` en un temporal (`guardar()` escribe ahí `pendientes.json`), `_dejar`
  capturando lo que iría al spool y `log` capturando lo que iría a `logger`. Ni `pendientes.json`, ni el spool, ni el
  journal contienen la ruta, `20-Personas`, el RUT ni ningún título; el vivo sí tiene la pregunta completa.
- `test_el_detector_no_es_vacuo_la_pregunta_vieja_si_se_habria_guardado`: control. Con lo que mandaba la versión
  revisada (la pregunta en la línea), el mismo arnés sí encuentra la ruta en `pendientes.json` y en el spool, y un
  título en el journal (los 120 primeros caracteres).
- `test_las_rondas_siguientes_rehacen_el_resumen_y_no_copian_el_vivo`: con la `pregunta` del vivo alterada a una
  ruta y un RUT, la segunda ronda sigue con el vocabulario cerrado.
- `Invariantes.test_la_pregunta_hostil_sale_escapada_y_sugerir_real_la_acepta` (ajustada): el `sugerir()` real acepta
  las tres líneas del resumen y ningún pedazo de un título hostil llega a `comando` ni a `motivo`; nombres hostiles dan `ValueError`.

### Hallazgo 2 [Media] — nadie instalaba el timer que recoge la respuesta y vence el plazo

**Qué cambió.** Se retiraron `encargos/consultas.service` y `encargos/consultas.timer` (copia en
`~/encargos-logs/autor51/arreglo1-retirados/`). En su lugar, la cola arma un **timer transitorio de usuario** con
`systemd-run --user` (`argv_vigilante()`): `encargos-consultas-<fecha>-<hex>`, cada 5 min
(`--on-active` y `--on-unit-active`), `Type=oneshot`, `KillMode=process` (la razón de 55r1, hallazgo 1, se conserva) y
`TimeoutStartSec=3min`, que corre `/usr/bin/python3 …/encargos/cola-run.py --consultas`. Así no queda nada que
instalar ni que desplegar, y no se agregó un mecanismo de despliegue nuevo. Elegido sobre «meter la unidad al
despliegue»: eso era ampliar `desplegar()` (una función nueva) y, con `despliegue = "pedir"`, igual dependía de un ✅
que la cola 51 no tiene cómo provocar para archivos de `encargos/`.

- `consultar_o_seguir()`, bajo el candado `vivo/consultas.lock`, **primero** arma el timer y verifica que
  `systemctl --user list-timers` lo lista activo (`armar_vigilante()`); recién entonces pregunta. Si no se puede
  armar, no pregunta y aplica el defecto («no se pudo armar el timer que recoge la respuesta»): nunca queda una
  consulta estacionada sin nadie que la recoja.
- `atender_consultas()`, al terminar su pasada y con el mismo candado, detiene el timer si ya no queda ninguna
  consulta abierta (`_abierta()`: sin contestar, válida, y con la cola `en_consulta` o aún escribiendo ese estado).
  El candado impide que una pasada lo detenga entre que la cola lo arma y el vivo anota la consulta.
- Un reinicio se lleva el timer transitorio: `main()` llama `rearmar_vigilante()` al partir cualquier cola, que lo
  rearma si otra quedó con una consulta abierta.
- `SYSTEMD` es inyectable; con `NODO_PRUEBAS=1` y las rutas reales (un agente) no arma ni detiene nada.

**Verificación con el systemd real de la Pi** (fuera de la suite, inofensiva: mismas opciones que arma
`argv_vigilante()`, otro nombre y `/bin/true` como comando; se detuvo al final):

```text
cola arma: systemd-run --user --unit=encargos-consultas-20261017-103706-6943 --description=Consultas entre fases (encargo 51) --on-active=300s --on-unit-active=300s --timer-property=AccuracySec=30s -p Type=oneshot -p KillMode=process -p TimeoutStartSec=3min -- /usr/bin/python3 /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/cola-run.py --consultas
rc 0 Running timer as unit: prueba51r1-20261017-103706-6943.timer
Will run service as unit: prueba51r1-20261017-103706-6943.service
timer TimersMonotonic={ OnUnitActiveUSec=5min ; next_elapse=0 } | TimersMonotonic={ OnActiveUSec=5min ; ... } | AccuracyUSec=30s | Description=Consultas entre fases (encargo 51) | LoadState=loaded | ActiveState=active |
service Type=oneshot | TimeoutStartUSec=3min | KillMode=process | Description=Consultas entre fases (encargo 51) | LoadState=loaded | ActiveState=inactive |
list-timers: [{"next":1792244526224742,"left":1792244526224742,"last":0,"passed":0,"unit":"prueba51r1-20261017-103706-6943.timer","activates":"prueba51r1-20261017-103706-6943.service"}]
stop rc 0
después: []
```

Antes, con `--on-active=2s --on-unit-active=3s` y `/bin/true`, se vio que un timer transitorio dispara repetido
(`last` avanzó de …654 a …658 s) y que `stop` deja timer y servicio en `LoadState=not-found`. `Linger=yes` para
`dcifu004`, así que el administrador de usuario sigue vivo sin sesión abierta.

**Pruebas** (`Hallazgo2ElTimerQueRecogeLaRespuesta`; el systemd de mentira devuelve la forma real de
`list-timers --output=json` copiada de la Pi):

- `test_arma_el_timer_antes_de_preguntar_y_lo_verifica`: `list-timers` → `systemd-run` → `list-timers`, y recién
  entonces el primer mensaje; opciones y comando exactos (`/usr/bin/python3 <cola-run.py real> --consultas`).
- `test_la_orden_del_timer_procesa_un_resultado_del_escucha_y_lo_detiene`: se toma el comando que se le dio a
  `systemd-run`, se corre por la línea de comandos (`principal()` con `--consultas`) contra un `resultados/` temporal
  con un ✅ del escucha: aplica «aceptar», relanza desde `46a:fix1`, anota el pedido en `decisiones.md` y detiene el
  timer.
- `test_con_la_consulta_abierta_el_timer_sigue`, `test_sin_timer_no_se_pregunta_y_se_aplica_el_defecto`,
  `test_un_reinicio_se_lleva_el_timer_y_la_proxima_cola_lo_rearma` (corre otra cola, `cola47`, por `principal()`),
  `test_la_cola_que_parte_sin_consultas_ajenas_no_toca_systemd`.

### Hallazgo 3 [Media] — una ronda a medias estacionaba la cola

**Qué cambió.** `enviar_ronda()` reintenta una vez cada opción que el canal no aceptó y devuelve `(ronda, faltan)`.

- **Primera ronda:** la cola se estaciona sólo con las tres opciones. Si falta alguna, no se estaciona: se aplica el
  defecto en el momento, se anota en `decisiones.md` («no aceptó la consulta completa (faltan: …); los botones que
  llegaron no cuentan») y, si llegó algún mensaje, un aviso de texto lo dice («llegaron N de 3 botones y no cuentan»,
  por `avisar_texto`, también de vocabulario cerrado) y la consulta cuenta para el tope (el usuario sí fue
  interrumpido). Si no llegó ninguno, como antes: no cuenta.
- **Rondas siguientes** (la cola ya está estacionada): una ronda a medias se guarda con `faltan`; las pasadas
  siguientes reintentan sólo esas opciones (hasta `CONSULTA_REINTENTOS = 3`), sin tocar `plazo`. Un botón que llegó
  tarde vale. La ronda siguiente se cuenta desde que se completó.

**Pruebas** (`Hallazgo3RondaCompletaONada`): las 7 combinaciones incompletas (falta 1, faltan 2, faltan las 3), cada una
siendo la última cola (va al arreglo) y con otra cola esperando (queda saltada): 14 pruebas que verifican mensajes,
reintentos, estado, `consultas_n`, la línea de `decisiones.md`, el aviso, que `--consultas` no encuentre nada abierto y
que el timer se detenga. Más `test_una_falla_pasajera_se_reintenta_y_la_ronda_queda_completa`,
`test_una_ronda_siguiente_a_medias_reintenta_lo_que_falta_con_el_mismo_plazo` y
`test_si_el_canal_no_vuelve_se_deja_de_reintentar_y_el_plazo_aplica_el_defecto`.

### Hallazgo 4 [Baja] — nombre personal sin etiqueta

`test_consultas.py`: el `detalle` falso dice «el usuario dice que lo corrió» (la cola no lee `detalle`). En este
informe, la salida del `grep` de la sección 1 lleva «[el usuario]» en lugar del nombre, con una nota. Ni el código
nuevo ni la suite nombran a nadie fuera de las etiquetas.

### Las pruebas nuevas no pasan con el código revisado

La suite nueva, corrida en un árbol temporal contra el `cola-run.py` que revisó Codex (foto `bdb41219`):

```text
Ran 59 tests in 32.786s
FAILED (failures=20, errors=5)
```

Fallan 25 de las 26 pruebas nuevas o ajustadas (H1: 2, H2: 5, H3: 17, la de invariantes). Pasan con ambas versiones el
control de H1 (está para mostrar que el detector encuentra la fuga) y `test_la_cola_que_parte_sin_consultas_ajenas_no_toca_systemd`;
las 33 originales pasan con ambas.

### Salida real de las suites (17-10, 10:35, `NODO_PRUEBAS=1`)

```text
== encargos/test_consultas.py
Ran 59 tests in 36.931s
OK
== pi/test_descanso.py
Ran 16 tests in 0.369s
OK
== encargos/test_matriz_cuota.py
Ran 28 tests in 4.022s
OK
== encargos/test_acciones_cola.py
Ran 48 tests in 8.098s
OK
== pi/test_cockpit_paginas.py
Ran 161 tests in 29.612s
OK
```

Extras (también tocan `cola-run.py` o el canal): `test_despacho.py` 36 OK, `test_despachador.py` 21 OK,
`test_diff_propio.py` 9 OK, `test_fase_plan.py` 8 OK, `test_pronostico.py` 6 OK, `pi/test_avisos.py` 93 OK,
`botv3/test_botv3.py` 237 OK. `encargos/test_versiones.py`: 45 con 1 falla, `test_el_arbol_real_no_tiene_git_dentro`, la
misma de la línea base (`~/encargos-logs/autor51/base.txt`), ajena a este encargo. Después de las suites: ningún
`encargos/*-decisiones.md`, ningún timer `encargos-consultas-*` real, y `encargos/vivo/` sin archivos nuevos.

### Criterios después de los arreglos

| Criterio | Estado |
| --- | --- |
| C1 | Cumplido: dispara igual y ahora sólo estaciona con las tres opciones (H3). |
| C2 | Cumplido, sin cambios. |
| C3 | Cumplido en el arnés: el comando que arma la cola procesa un ✅ del escucha (H2). En la Pi queda por verse en la primera consulta real: no se lanzó ninguna. |
| C4 | Cumplido en el arnés: el timer existe mientras haya una consulta abierta; tras un reinicio, hasta que parte la próxima cola. |
| C5 | Cumplido, sin cambios. |
| C6 | Cumplido; la premisa del canal se mantiene, pero sólo con vocabulario cerrado (H1). |
| C7 | Cumplido: las cinco suites en verde, salida arriba. |

### Límites y pendientes de esta vuelta

- **Reinicio sin colas:** si la Pi reinicia con una consulta abierta y no parte ninguna cola, nadie la recoge hasta que
  parta una o el usuario toque Reanudar. Falla hacia lo conservador: no se aplica nada sin el usuario.
- **Botones huérfanos:** los botones de una primera ronda a medias siguen vivos 30 min en Telegram; un ✅ ahí no hace
  nada (el aviso lo dice). Retirarlos exigiría tocar `nodo-desplegar`.
- **Fuera de alcance, previo al 51:** `~/encargos-logs/` vive en el disco raíz, sin cifrar
  (`findmnt`: `/dev/nvme0n1p2`), y guarda la transcripción completa de cada fase: `51-rev1.log` trae los títulos de
  51r1. Otros avisos de la cola por `sugerir` llevan texto libre (el `motivo` del manifiesto, el de una pausa). Este
  arreglo cierra el camino nuevo que abría el 51, no esos; decidir si se mueven dentro de LUKS le corresponde al
  usuario (sería otro encargo).
- La vista de 🧵 sigue sin etiqueta para `en_consulta` (sección 6).
