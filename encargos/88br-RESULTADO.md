# 88b — Revisión 2 (Codex, 25-10-2026)

Sólo revisión: no se modificó código. Leí primero el diff propio
`~/encargos-logs/cola88-88b-diff.txt`, incluidas la autoría y
`fix1`; excluí lo declarado bajo «Cambios ajenos». No existe
`encargos/88b-PLAN.md` ni `encargos/88b-decisiones.md`.

## Cierre de la revisión anterior

Los tres hallazgos de `encargos/88br1-RESULTADO.md` están cerrados en `fix1`:

| Hallazgo previo | Comprobación de cierre |
|---|---|
| Consultas a receptores para frases ajenas | `botv3/botv3.py:6751-6762` decide antes de construir bases. Reproducción con «agrega leche a la lista» y vocativo ajeno: `status=0`, `search=0`. |
| Vocativo del otro perfil | `botv3/spotify.py:42-46` y `botv3/botv3.py:6746-6750` lo rechazan antes de interpretar. «Hola Pilar. reproduce Oxytocin de Billie Eilish» en el perfil Jaime devolvió `False`, sin red local. |
| Dobles de receptor reducidos | `botv3/fixtures/spotify-receptor-v0.10.5.json` y `botv3/test_spotify.py:17-69` usan y validan todos los campos requeridos de `status`, `track` y `deviceAuth` del OpenAPI oficial v0.10.5. |

## Seguridad y alcance

- Los perfiles validan literalmente `http://127.0.0.1:<puerto>` en
  `botv3/botv3.py:181-197`; se rechazaron `http://10.0.0.5:3678`, HTTPS y el
  puerto 65536.
- `botv3/spotify.py:121-138` entrega la consulta mediante `params=`, limita la
  entrada y no la concatena a una URL. El Client Secret queda sólo en memoria;
  una excepción que contenía el secreto de prueba produjo únicamente «No pude usar
  Spotify ahora.».
- El OpenAPI oficial confirma los cuerpos JSON y las rutas utilizadas:
  `/status`, `/auth/code`, `/player/play`, `/player/pause` y `/player/resume`.
- No hay JavaScript propio en el diff. El tokenizador de la guía HTML encontró
  `script_blocks=0`, por lo que no hay paréntesis, llaves ni template literals JS
  que validar.
- No existen `encargos/88b-busquedas.jsonl` ni
  `encargos/manual-busquedas.jsonl`; por tanto, no hay búsqueda Tavily ni manual
  atribuible a la ventana de autor (16:28–16:40). Tampoco aparecen tokens reales
  en el diff ni en los archivos nuevos.

## Reproducciones aisladas

Cada script se ejecutó bajo un `mktemp -d` con `BOTV3_USO_CUENTAS`,
`BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` dentro de ese directorio. No se leyó ni
escribió el libro real.

- C1/C2: las diez frases positivas dieron la intención esperada y las ocho
  negativas devolvieron `None` (salvo «pausa» con música, que dio `pausa`).
- C3: el fixture de búsqueda eligió *Oxytocin — Billie Eilish* para «oxitocina»
  y «billi eilish».
- C4: con receptores simulados, el orden fue
  `GET propio`, `GET otro`, `POST_PAUSE otro`, `POST_PLAY propio`; la respuesta
  fue `▶️ Oxytocin — Billie Eilish · Spotify de <persona>`.
- C5: la excepción con un secreto sintético no filtró su texto al chat.
- C6: las tres configuraciones no loopback/HTTPS/puerto inválido fueron rechazadas.
- C7: `test_spotify.py` consume el fixture completo de `/auth/code` y comprueba
  que `/spotify` envía enlace y código; también cubre el estado vinculado y la
  canción actual.

El sandbox no permite abrir puertos loopback, por lo que el servidor HTTP efímero
de la integración C4 queda correctamente marcado como un salto (`skipped=1`), no
como un falso verde. La reproducción equivalente con dobles verificó el orden de
las llamadas anterior sin abrir red.

## Suites (salida real)

```text
$ python3 -m py_compile botv3/spotify.py botv3/botv3.py botv3/test_spotify.py pi/cargar-clave.py
rc=0

$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 93 tests in 4.710s
OK

$ python3 botv3/test_botv3.py
Ran 490 tests in 16.638s
OK (skipped=4)

$ python3 botv3/test_temporizadores.py
✅ todo en verde

$ python3 botv3/test_compras.py
✅ todo en verde

$ python3 botv3/test_spotify.py
Ran 8 tests in 0.080s
OK (skipped=1)
```

La línea base registraba sólo `botv3/test_spotify.py::no corrió (rc 2)`; esa suite
ahora pasa. Los cuatro saltos de la suite grande son los sockets locales ya
conocidos del sandbox, no fallas nuevas. Las pruebas de respuestas largas con
fuentes, rutas y voz siguen en verde dentro de `test_botv3.py`.

## Hallazgos

No hay hallazgos. Queda como condición externa conocida que la etapa 88a debe
materializar y desplegar los receptores antes de probar reproducción física; no es
un defecto del diff de 88b ni autoriza desplegar 88b en solitario.

VEREDICTO: DESPLEGABLE
