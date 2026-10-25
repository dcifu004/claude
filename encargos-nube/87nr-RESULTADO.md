# Revisión 87n — cierre barato del encargo 87 (Codex, 25-10-2026)

Revisión 1, sin modificar código. El diff propio que generó la cola sólo dice que no pudo reconstruir las
fotos de 87n. Conforme a `87n-revision-nube.md`, revisé como diff de la implementación
`encargos/87n-diff-nube.txt` y contrasté `encargos/cola-run.py` con
`encargos/cola-run.py.antes-87nube`.

Leí el encargo y el plan aprobado `87-PLAN.md` completo. No hay revisiones `87nr` anteriores que cerrar,
ni `87n-decisiones.md`, `87n-busquedas.jsonl` o `manual-busquedas.jsonl`; por tanto no hubo decisión del
usuario ni búsqueda Tavily que descontar o auditar. El diff de nube sólo toca los archivos previstos por
el plan: `cola-run.py`, plantilla, prueba, fixtures, plan e informe.

## Reproducciones

Todas las reproducciones se corrieron en un `mktemp -d`, con `BOTV3_USO_CUENTAS`,
`BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` apuntando ahí. Usan el mismo arnés temporal, fotos Git reales y
forma de `GIT_BASE` que `test_cierre_barato.py`; no leen el libro ni datos reales.

1. Un `fix1` reemplazó el `87-RESULTADO.md` ya creado por el autor por un enlace simbólico a un archivo
   regular fuera del árbol temporal cuyo contenido era una sección válida «Arreglos vuelta 1» y un texto
   señuelo. El flujo real llegó a cierre y el texto señuelo quedó en su prompt:

```text
etapa= True
rol_final= ('rev2', 'cierre')
secreto_en_prompt= True
motivo_cierre= ['87: rev2 va como cierre: fix1 cambia 22 línea(s) en 2 archivo(s) ya revisados']
```

2. Un ejecutable `claude` temporal creó `sleep 15` como hijo y esperó por él. `_correr(...,
limite_s=.2)` devolvió el corte, pero el hijo seguía vivo; se terminó inmediatamente al finalizar la
prueba:

```text
resultado= (124, 'tiempo', False)
segundos_reales= 0.2
hijo_sigue_vivo= True
```

3. En una corrida temporal normal, la foto de `fix1` contenía `vivas = ['cola-ajena']`, exactamente el
campo que persiste `git_base_guardar`. Con un cambio de 20 líneas en un archivo ya tocado por el autor,
la cola no escaló y ejecutó el cierre:

```text
etapa= True
fases= [('autor', 'autor'), ('rev1', 'rev'), ('fix1', 'fix'), ('rev2', 'cierre')]
decision= ['87: rev2 va como cierre: fix1 cambia 20 línea(s) en 1 archivo(s) ya revisados']
```

## Pruebas (salida real)

Las siete suites se ejecutaron con `NODO_PRUEBAS=1` y las tres variables de estado aisladas. La plataforma
corta un proceso de consola a los 30 segundos, por lo que `test_consultas.py` se ejecutó en sus tres grupos
de clases y `test_acciones_cola.py` en tres grupos; cubren la totalidad de 80 y 48 pruebas, respectivamente.

```text
$ python3 -B -m unittest encargos/test_cierre_barato.py
Ran 33 tests in 4.311s
OK

$ python3 -B -m unittest encargos/test_fase_plan.py
Ran 8 tests in 0.267s
OK

$ python3 -B -m unittest encargos/test_diff_propio.py
Ran 19 tests in 1.990s
OK

$ python3 -B -m unittest encargos/test_balance.py
Ran 22 tests in 0.307s
OK

$ python3 -B -m unittest encargos/test_pronostico.py
Ran 6 tests in 0.141s
OK

$ python3 -B -m unittest encargos.test_consultas.C1Disparador ... C5Despliegue
Ran 28 tests in 16.589s
OK

$ python3 -B -m unittest encargos.test_consultas.Invariantes ... Hallazgo3RondaCompletaONada
Ran 31 tests in 19.617s
OK

$ python3 -B -m unittest encargos.test_consultas.ConConsultar ... PuntaAPunta71
Ran 21 tests in 11.611s
OK (skipped=1)

$ python3 -B -m unittest encargos.test_acciones_cola.C1Nombres ... C3Pausar
Ran 23 tests in 3.380s
OK

$ python3 -B -m unittest encargos.test_acciones_cola.C4Detener ... Pagina
Ran 24 tests in 3.980s
OK

$ python3 -B -m unittest encargos.test_acciones_cola.TmuxDeVerdad
Ran 1 test in 0.021s
OK (skipped=1; el sandbox no permite socket tmux)
```

La línea base de `cola87n` es `[]`: no apareció una falla de esas suites que pueda atribuirse a una
falla previa. Como regresión adicional de respuestas largas, fuentes, rutas y voz, `botv3/test_botv3.py`
corrió aislada: `Ran 490 tests in 17.286s`, `OK (skipped=4)`. Incluye en verde
`test_respuesta_larga_con_cuenta_llega_entera_con_fuentes_y_sin_preview`, las rutas web y las pruebas de
voz. El diff de nube no modifica JavaScript, por lo que no hubo bloque JS nuevo que tokenizar.

## Hallazgos, de mayor a menor gravedad

### 1. [Grave] El cierre sigue enlaces simbólicos y puede enviar contenido fuera del encargo al motor revisor

`encargos/cola-run.py:2456-2466` lee `encargos/<id>-RESULTADO.md` con `Path.read_text()` sin comprobar
que sea un archivo regular ni que ningún tramo sea un enlace. `:2474-2481` incorpora esa sección al
prompt, que `:2510` entrega al motor. E1 sólo compara nombres de rutas (`:2427-2435`): como el resultado
ya lo creó el autor, un `fix` puede sustituirlo por un enlace sin activar E1 ni E2.

La reproducción 1 demuestra la fuga con la forma real de las fotos Git: el contenido externo llegó al
prompt del cierre. En producción, un enlace hacia un archivo legible fuera del proyecto puede terminar en
el prompt de Claude (Diego) o Codex; eso rompe el límite de lectura del encargo y puede exponer datos o
secretos. También deben validarse sin seguir enlaces los informes previo y final que se leen en
`:2476`, `:2520`, `:2743` y `:2747`.

Arreglo: abrir cada informe por descriptor con `O_NOFOLLOW`, comprobar `fstat` regular, tamaño acotado y
que su ruta resuelta permanezca bajo `encargos/`; ante cualquier enlace, error de lectura o forma no
esperada, devolver ESCALAR y ejecutar la revisión completa. Agregar una prueba con un enlace en
`<id>-RESULTADO.md` que compruebe que no se invoca `correr()` para el cierre y que el texto externo no
aparece en el prompt.

### 2. [Grave] El supuesto corte duro deja procesos hijos del revisor ejecutándose

`encargos/cola-run.py:1811-1816` usa `subprocess.run(..., timeout=...)`, que mata únicamente el proceso
principal. No crea un grupo de procesos ni mata su grupo al capturar `TimeoutExpired`. Después
`:2523-2529` lo transforma en ESCALAR y `:2731-2752` empieza una revisión completa. Un hijo del cierre
queda así con permiso de escritura sobre el mismo árbol y puede escribir el resultado o código en paralelo
con la revisión fuerte.

La reproducción 2 confirma que el retorno ocurre a los 0,2 s mientras el hijo permanece vivo. La prueba
actual `test_correr_corta_por_tiempo_de_verdad` usa `exec sleep`, que reemplaza al padre y por eso no cubre
la forma real de un CLI que deja subprocesos.

Arreglo: lanzar el CLI en una nueva sesión/grupo de procesos y, ante timeout, terminar el grupo completo
(TERM, espera acotada y KILL si corresponde), recoger su salida y confirmar que ya no quedan hijos antes
de escalar. Agregar al test un CLI temporal que lance un hijo con PID comprobable y exigir que ese PID no
exista al retornar.

### 3. [Media] La decisión barata ignora la atribución de otras colas vivas exigida por el plan

`encargos/cola-run.py:1420-1448` registra las otras colas vivas en `f['vivas']`. Existe incluso la lógica
conservadora que cruza sus fotos y marca archivos compartidos en `:2986-3027`. Pero
`decidir_cierre()` (`:2417-2443`) no consulta `vivas`, `_fases_ajenas()` ni
`_propios_atribuidos()`: sólo ve que el nombre del archivo ya estaba en el diff del autor. Por eso la
reproducción 3 llega a `rev2/cierre` pese a que la foto del arreglo registra una cola ajena.

Contradice el plan aprobado (`encargos/87-PLAN.md:11`): los archivos de otra cola viva dentro del diff del
arreglo deben escalar por E1. Un cambio ajeno sobre un archivo que el autor ya tocó puede pasar por la
revisión barata sin atribución verificable.

Arreglo: al decidir el cierre, cruzar las fotos de `vivas` igual que `_propios_atribuidos()`; si el
registro ajeno falta, está abierto, es ilegible o comparte una ruta del `fix`, devolver revisión completa.
Agregar los casos de cola ajena con foto cerrada, abierta e ilegible a `test_cierre_barato.py`.

VEREDICTO: NO DESPLEGABLE
