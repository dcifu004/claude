# Encargo 88b — Revisión 1 (Codex, 25-10-2026)

Sólo revisión: no se modificó código. Leí primero el diff propio
`~/encargos-logs/cola88-88b-diff.txt`; no hay plan de 88b ni decisiones
de esta etapa, ni revisiones `88br*` anteriores que cerrar. Los registros
`encargos/88b-busquedas.jsonl` y `encargos/manual-busquedas.jsonl` no existen: no hubo
consulta a Tavily ni búsqueda manual atribuible a la fase de autor (16:28:43–16:40:47).

Todas las reproducciones usaron directorios creados con `mktemp -d`, con
`BOTV3_USO_CUENTAS`, `BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` dentro de ellos. No se leyó ni
escribió el libro real. La especificación oficial de go-librespot v0.10.5 confirma las
rutas `/status`, `/auth/code`, `/player/play`, `/player/pause` y `/player/resume`; no
hay JavaScript propio en el diff, por lo que no correspondía tokenizar JS.

## Pruebas (salida real)

```text
python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

python3 pi/test_nodo_desplegar.py
Ran 93 tests in 4.649s
OK

python3 botv3/test_botv3.py
Ran 490 tests in 16.722s
OK (skipped=4)

python3 botv3/test_temporizadores.py
✅ todo en verde

python3 botv3/test_compras.py
✅ todo en verde

python3 botv3/test_spotify.py
Ran 6 tests in 0.079s
OK (skipped=1)
```

No hubo fallas que contrastar con la línea base: su único ítem era
`botv3/test_spotify.py::no corrió (rc 2)`, y esta vez esa suite sí pasó. La suite
grande conserva en verde la prueba de respuestas largas con fuentes y sin vista previa,
las rutas y las pruebas de voz; los cuatro saltos son sockets locales que este sandbox
no permite abrir.

Las reproducciones adicionales comprobaron C1/C2, el orden `pause` antes de `play`, el
texto de voz por chat, el código de vinculación y que una excepción que contiene un
secreto no lo reenvía. El orden correcto dio:

```text
GET receptor propio, GET otro receptor, PAUSE otro receptor, PLAY receptor propio
error_atendido=True mensajes=1 secreto_filtrado=False
auth_code_enviado=True
```

## Hallazgos, de más grave a menos grave

### 1. [Grave] Toda frase normal consulta Spotify antes de continuar su ruta

`botv3/botv3.py:6746-6762`. Aunque `interpretar(..., sonando=False)` ya determina que
una frase no es música, el código arma `bases` y hace `GET /status` a ambos receptores
antes de evaluar la intención final. La intención se inserta antes de hora/clima, gastos,
agenda, nodo, compras y el router (`botv3/botv3.py:8127-8167` y `8205-8225`). Por tanto,
un receptor lento puede sumar su timeout de 3 s a mensajes que ya funcionaban, incluidos
temporizadores, compras y consultas por voz. Si el primero no responde, el flujo se
detiene ahí durante el timeout antes de seguir; si ambos responden, todos los mensajes
no musicales hacen dos peticiones inútiles.

**Reproducción:** con el estado y las rutas en `mktemp -d`, se sustituyeron sólo los
clientes de receptor por dobles locales y se llamó
`atender_spotify(1, "agrega leche a la lista", False)`. El resultado fue
`no_spotify=False consultas_estado=2`. La frase es C2 y debe seguir a compras, pero ya
había consultado los dos receptores. `botv3/test_spotify.py:33-38` prueba sólo la función
pura `interpretar`, por eso queda verde y no detecta las peticiones ni el timeout.

**Arreglo:** decidir primero si la frase es una orden explícita de música. Consultar
`/status` sólo para esas órdenes y para el caso especial de «pausa» sola, que necesita
saber si algo suena. Agregar una prueba de integración que afirme cero llamadas a
`estado()` para cada frase C2.

### 2. [Media] El vocativo del otro perfil activa Spotify en el perfil equivocado

`botv3/spotify.py:44-47` elimina indistintamente `jaime` y `pilar`. Eso contradice el
patrón previo `VOCATIVO_RE` de `botv3/botv3.py:1246-1248`, que sólo elimina el nombre del
perfil que está atendiendo. El resultado es que una frase dirigida al otro perfil no
sigue al flujo normal: activa el receptor del perfil que recibió el mensaje.

**Reproducción:** en un `mktemp -d`, con el perfil configurado con sus propios dos
receptores y clientes falsos, se ejecutó
`atender_spotify(1, "Hola Jaime. reproduce Oxytocin de Billie Eilish", False)` desde
el otro perfil. Dio `vocativo_ajeno_atendido=True plays=1`. Las pruebas actuales sólo
cubren el vocativo que corresponde (`botv3/test_spotify.py:20-38`); falta el caso
negativo ya cubierto por otras intenciones del bot.

**Arreglo:** aplicar `sin_vocativo()` antes de interpretar, o entregar a
`spotify.interpretar()` únicamente el nombre permitido del perfil actual. Agregar la
prueba de que el vocativo ajeno devuelve `False` y no toca ningún receptor.

### 3. [Media] C4 y C7 no prueban la forma canónica del receptor

`botv3/test_spotify.py:58-61` inventa un `/status` reducido a `stopped`, `paused` y un
`track` reducido a dos campos; `:113-117` inventa un `/auth/code` sin `expires_at`.
La especificación fijada v0.10.5 declara más campos obligatorios en `status`, un `track`
completo y `url`, `code`, `expires_at` para el código de dispositivo. El manifiesto exige
que C4/C7 usen la forma real tomada de 88a; como 88a no pudo observarla, el autor dice
haberla confirmado contra OpenAPI, pero no dejó un fixture canónico ni hizo que la prueba
lo consumiera.

**Reproducción:** al contrastar las respuestas construidas en esas líneas con
`api-spec.yml` v0.10.5, faltan los campos obligatorios indicados. Una reproducción con
la forma completa de `/auth/code` sí permitió a `/spotify` enviar el enlace y el código,
pero eso no convierte el doble reducido actual en prueba de contrato.

**Arreglo:** guardar un fixture recortado sólo en campos usados, pero derivado
literalmente del OpenAPI v0.10.5 e incluyendo todos los campos obligatorios, o validar el
fixture contra ese esquema durante la suite. Usarlo tanto para C4 como para C7.

## Lo que revisé y está bien

- Las URLs de receptor se validan como `http://127.0.0.1:<puerto>` en
  `botv3/botv3.py:178-199`; se rechazan red remota, HTTPS y puertos fuera de rango.
- El orden efectivo de una reproducción de canción fue pausa del otro receptor antes de
  reproducir en el propio. La respuesta por voz queda escrita y no invoca el sintetizador.
- La búsqueda limita la consulta a 120 caracteres y la entrega como `params=`, no la
  interpola en una URL (`botv3/spotify.py:106-134`). Los errores de red y credenciales
  se convierten a texto fijo; la reproducción con un secreto centinela no lo imprimió ni
  lo mandó al chat.
- Los perfiles son simétricos, no se agregaron callbacks, y `/spotify` sólo se incorpora
  al menú cuando el perfil declara Spotify. No se detectaron lecturas nuevas de vaults,
  archivos temporales fuera del aislamiento ni tokens en el diff.
- El fixture de búsqueda declara honestamente ser de documentación, como permite el
  manifiesto cuando no hay credenciales; no se lo contó como captura real.

VEREDICTO: NO DESPLEGABLE
