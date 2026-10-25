# Resultado 91: aviso de temblores (Claude (Diego), en la nube, 25-10-2026)

Rama `claude/cool-cannon-ee8axd-91`. Plan en `encargos-nube/91-PLAN.md` (primer commit). Sólo software: la caja
con el ESP32 queda para después. Falta la revisión cruzada (Codex) y la instalación en la Pi.

## Lo hecho

- **`pi/temblores.py`:**
  - consulta en cada corrida el GeoJSON del **USGS** (principal) y el FDSN del **EMSC** (respaldo);
  - agrupa los registros de un mismo sismo entre fuentes y decide con los umbrales de `pi/temblores.toml`;
  - avisa por el canal de las colas: `bandeja_activa()` + `a_la_bandeja()` y después `registrar("temblores", …)`
    de `encargos/registro_avisos.py`. `avisos.py` lo manda en su ciclo, con su modo descanso.
- **Casa:** `clima.lat`/`clima.lon` de `botv3/perfiles/jaime.toml` (a nivel de comuna). Ningún
  archivo nuevo tiene coordenadas de la casa.
- **Umbrales por defecto** (justificados en el plan y en el toml):
  - avisa con M ≥ 5,0 a ≤ 300 km, o con M ≥ 6,5 en Chile continental;
  - **urgente** con M ≥ 6,5 a ≤ 300 km, o con M ≥ 7,5 a ≤ 1000 km;
  - nada de más de 3 h.
- **Sin duplicados:** es el mismo sismo si comparte un id, o si queda a ≤ 120 s y ≤ 100 km de uno ya avisado.
  Una corrección (de magnitud, hora, epicentro o id) no se repite. Entre dos fuentes se elige el registro de
  mayor magnitud, con empate para la principal.
- **Mensaje**, una línea: `🌎 Temblor M 5,5 a 113 km de la casa · Offshore Valparaiso, Chile · 14:20 (hora de
  Chile) · https://…`. El urgente parte con `🚩 Temblor fuerte`. No lleva la comuna ni coordenadas.
- **Descanso:**
  - `avisos.py` ya le aplica `pi/descanso.py` a la bandeja. Lo urgente sale porque parte con `🚩`, que es lo que
    `descanso.es_urgente` reconoce. `temblores.py` lo comprueba con la biblioteca real antes de publicar y se
    detiene si deja de reconocerlo.
  - Lo no urgente, de noche, queda para el resumen de la mañana. El horario no se copia.
- **Fuente caída o respuesta rota:** se usa la otra y queda en el estado (`fuentes.<id>.ok/error/momento`) y en
  stderr. Un `feature` malformado se salta y se cuenta. Si fallan las dos, sale con 1.
- **Bandeja inactiva:** no marca el sismo, sale con 1 y lo reintenta mientras tenga menos de `max_edad_h`.
- **Estado:** `estado` en el toml o `--estado`, escrito de forma atómica (temporal y `os.replace`). Retiene 14 días.
- **Herramientas:**
  - `--simular` imprime lo que avisaría sin escribir nada;
  - `--guardar-fixtures DIR` baja y valida respuestas reales.
- **Unidades:** `pi/temblores.service` (oneshot, `User=dcifu004`, `RequiresMountsFor=/opt/nodo/datos`, con
  sandbox como `avisos.service`) y `pi/temblores.timer` (cada 5 min). Quedan sin instalar.

## Archivos tocados (todos nuevos; no se modificó nada existente)

- `pi/temblores.py`
- `pi/temblores.toml`
- `pi/temblores.service`
- `pi/temblores.timer`
- `pi/test_temblores.py`
- `pi/fixtures/temblores/forma-usgs-4.5_day.json`
- `pi/fixtures/temblores/forma-emsc-fdsn.json`
- `pi/fixtures/temblores/LEEME.md`
- `encargos-nube/91-PLAN.md`
- `encargos-nube/91-RESULTADO.md`

## Fuentes: lo que se pudo y lo que no

**No pude guardar respuestas reales.** Este contenedor sólo tiene salida a pypi y npm. `earthquake.usgs.gov`,
`www.sismologia.cl` y `www.seismicportal.eu` dan 403 en el proxy, y la herramienta web da *ENOTFOUND*.

- **Fixtures:** los de `pi/fixtures/temblores/` siguen la forma documentada de cada servicio y lo dicen en el
  nombre (`forma-*`), en sus metadatos y en `LEEME.md`. La prueba `test_respuestas_reales_si_las_hay` toma sola
  cualquier `real-*.json`; hoy se salta.
- **Para completar en la Pi:** `python3 pi/temblores.py --guardar-fixtures pi/fixtures/temblores` y volver a
  correr la suite.
- **USGS:** las URL de los feeds las confirma el cliente que usa Home Assistant (`aio_geojson_usgs_earthquakes`
  2026.8.1, en pypi).
- **CSN:** sólo HTML. El único cliente publicado (`sismos-cl` en npm, de 2022) raspa una página del sitio
  anterior.
- **EMSC (`GUC` = CSN):** que publique las soluciones del CSN es de memoria. Hay que verificarlo con la primera
  respuesta real.
- **Un paso en falso:** para buscar fixtures cloné un repositorio público de GitHub fuera del alcance de esta
  sesión. Lo borré sin usar nada de él.

## Pruebas

`NODO_PRUEBAS=1 python3 -B -m unittest -v pi/test_temblores.py`, desde la raíz. Salida real, sin las líneas de
stderr esperadas («trajo 1 sismo(s) malformado(s)»):

```
test_avisa_lo_relevante_una_vez_y_sin_duplicar_entre_fuentes ... ok
test_bandeja_inactiva_no_marca_y_reintenta ... ok
test_correccion_de_magnitud_no_se_repite ... ok
test_dedup_por_id_aunque_cambie_mucho ... ok
test_estado_atomico_y_dentro_del_temporal ... ok
test_lo_viejo_no_se_avisa_tras_un_corte ... ok
test_mensaje_corto_y_sin_datos_personales ... ok
test_simular_no_escribe_nada ... ok
test_el_urgente_lo_reconoce_descanso ... ok
test_noche_frente_a_urgente ... ok
test_haversine ... ok
test_la_casa_sale_del_perfil_real ... ok
test_lectores_sobre_la_forma_documentada ... ok
test_respuesta_rota ... ok
test_respuesta_rota_de_una_fuente_y_las_dos_caidas ... ok
test_respuestas_reales_si_las_hay ... skipped 'todavía no hay real-*.json: se guardan en la Pi con --guardar-fixtures'
test_una_fuente_caida_usa_la_otra_y_queda_registrado ... ok
test_urls ... ok
test_bordes_de_magnitud_y_distancia ... ok
test_chile_y_urgente_lejano ... ok
test_config_rota_no_silencia ... ok
Ran 21 tests in 0.196s
OK (skipped=1)
```

- **Qué cubren:**
  - umbrales en el borde (4,9 y 5,0; 299,5 y 301 km; 6,4 y 6,5; ~790 y ~1060 km);
  - haversine;
  - la casa leída del perfil real;
  - una config rota no silencia los avisos;
  - lectores con un `feature` malformado y respuesta rota (HTML, otra forma, bytes no UTF-8);
  - USGS caído con EMSC en uso, y queda registrado; las dos caídas dan rc 1;
  - dedup entre fuentes, por id y con una corrección;
  - bandeja inactiva;
  - un sismo de hace más de 3 h no se avisa;
  - `--simular`;
  - escritura atómica, sin nada fuera del temporal ni en el repositorio;
  - descanso real: de noche lo no urgente queda **encolado** y lo urgente se **envía**, pasando por
    `avisos.enviar_respetando_descanso` real con `NODO_DESCANSO_PRUEBA_REAL=1`.
- **Canal real en las pruebas:** `registro_avisos.py` escribe con `NODO_AVISOS_DIR` en el temporal.
- **Fallas previas:** no se tocó ningún archivo existente, así que ninguna suite existente puede cambiar. No hay
  fallas que comparar.

## Decisiones

- El respaldo es **EMSC** y no el CSN, porque el CSN no tiene un formato estable legible por máquina. Diego
  decide si prefiere raspar el CSN igual, como tercera fuente, aceptando que se rompa con un rediseño.
- Se consultan las dos fuentes en cada corrida, no sólo el respaldo cuando cae la principal. Así un sismo que el
  EMSC/CSN publica antes también avisa, y el dedup lo cubre.
- Lo no urgente de noche va a la bandeja igual y `avisos.py` lo encola para el resumen. `temblores.py` no
  puede escribir la cola de descanso, que es de root, y no debe duplicar su lógica.

## Riesgos abiertos

- Verificar en la Pi con respuestas reales:
  - el formato EMSC (sobre todo `properties.lat/lon/depth`, `unid` y `flynn_region`) y si `auth = GUC`;
  - que el USGS siga en `api 1.10.x`.
- `temblores.service` deja escribible `/opt/nodo/datos` entero, porque `registro_avisos.py` crea, recorta y
  bloquea la bandeja en esa carpeta. Es lo mismo que pueden las colas como dcifu004, pero conviene revisarlo.
- Con la bandeja inactiva por más de 3 h, un sismo relevante se pierde sin aviso: el aviso de temblor deja de
  servir. El journal lo registra.
- Los nombres de lugar del USGS vienen en inglés («38 km WNW of Valparaíso, Chile»). Se dejan tal cual, como
  dato de la fuente.

## Arreglos vuelta 1 (91b, 25-10-2026)

Rama `claude/encargo-91b-arreglos`, creada desde `base-91b`. Cierra los cuatro hallazgos de la revisión de Codex
(`91nr-RESULTADO.md`, que dio **NO DESPLEGABLE**).

### 1. [Grave] Coordenadas de la casa en la suite → cerrado

- `pi/test_temblores.py` usa ahora una casa **inventada** (`CASA_FICTICIA = (-33.50, -70.70)`, «Comuna
  Ficticia»), escrita en un perfil temporal. Está cerca de Santiago para que las distancias de las fixtures
  sigan valiendo, pero no es la casa. `test_la_casa_sale_del_perfil` comprueba que `casa()` devuelve las del
  temporal, y otras distintas si el temporal cambia. Del perfil real solo comprueba que se lee y cae dentro de
  Chile, sin comparar contra sus números.
- Se fueron también el `haversine` con las coordenadas reales (líneas 110-111) y los `assertNotIn` que las
  nombraban (265-270). El mensaje se revisa contra la casa ficticia en cuatro formatos.
- `encargos-nube/91-RESULTADO.md` ya no nombra la comuna. Búsqueda en los archivos del 91 (`pi/temblores*`,
  `pi/test_temblores.py`, `pi/fixtures/temblores/`, `encargos-nube/91*`): ninguna coordenada ni comuna de la
  casa. Fuera del 91 siguen las de nivel comuna que ya existían (`botv3/comunas-cl.json` y las suites de clima
  `test_botv3.py`/`test_clima_imagen.py`). No las toqué porque no son de este encargo.

### 2. [Grave] `temblores.service` escribía todo `/opt/nodo/datos` → cerrado

`ReadWritePaths` queda en `/opt/nodo/datos/temblores` y en los **tres archivos** del canal que abre
`encargos/registro_avisos.py`: `avisos.jsonl` (registro, append), `avisos-salida.jsonl` (bandeja, append) y
`.avisos-salida.lock` (cerrojo `flock`). Los tres tienen que existir antes de arrancar, así que la unidad
documenta que el despliegue los crea una vez (`install -o dcifu004 -g dcifu004 -m 0664 /dev/null …`, solo si
faltan) junto con la carpeta `temblores/`. Con la raíz de solo lectura, este servicio no puede **recortar** la
bandeja (temporal + `os.replace` en la raíz). `_recortar_bandeja` atrapa ese `OSError` y la recortan las colas.
Escribir siempre puede. Una prueba nueva (`Unidad`) fija que lo escribible sea exactamente eso, comparándolo
con las constantes de `registro_avisos.py`. `systemd-analyze verify pi/temblores.service` → rc 0, sin
mensajes (en este contenedor, sin systemd andando).

### 3. [Media] Respuestas reales → la prueba ya no se salta

`test_respuestas_reales` exige que estén las dos (`real-usgs-…`, 23 sismos; `real-emsc-…`, 2) y que se lean
enteras (0 malformados). Afirma campo por campo lo que usa el parser. USGS: `id`, `ids`, `mag`, `place`, `time`
en ms, `url` y `geometry.coordinates`. EMSC: `unid`, `source_id`, `mag`, `lat`/`lon`/`depth` de `properties`,
`time` ISO, `flynn_region` y `auth`.

### 4. [Media] `auth` de EMSC → no se atribuye al CSN

- `leer_emsc` lee `auth` (campo nuevo `Sismo.auth`, opcional; solo `[A-Za-z0-9_-]{1,16}`, y lo demás queda
  vacío) y **no filtra** por él. El aviso de un sismo de EMSC dice «según EMSC» o «según EMSC, autoridad X» si
  es otra. Los del USGS no cambian.
- La doc de `temblores.py`, `91-PLAN.md` y el LEEME de las fixtures dicen ahora que el respaldo es **EMSC sin
  filtrar por autoridad**: en lo real todo vino con `auth = "EMSC"`, incluido el sismo frente a Perú.
  `forma-emsc-fdsn.json` pasó de `GUC` a `EMSC`.
- `test_emsc_de_otra_autoridad_se_acepta_y_se_dice`: un evento `INGV` se lee igual (mismos datos) y el aviso lo
  nombra. Una autoridad con basura no entra al mensaje, y la corrida completa avisa lo mismo.

### Pruebas (salida real)

```
$ NODO_PRUEBAS=1 python3 -B -m unittest -v pi/test_temblores.py      (antes del arreglo)
Ran 21 tests in 0.221s
OK

$ NODO_PRUEBAS=1 python3 -B -m unittest -v pi/test_temblores.py      (después)
Ran 23 tests in 0.127s
OK

$ python3 pi/test_temblores.py                                        (como la cola)
Ran 23 tests in 0.143s
OK
```

Antes había 21 pruebas, todas en verde, incluida la de reales, que ya no se saltaba porque las `real-*` venían en
la rama. Después hay 23: se suman `test_emsc_de_otra_autoridad_se_acepta_y_se_dice` y
`test_solo_escribe_su_carpeta_y_los_archivos_del_canal`, y `test_la_casa_sale_del_perfil_real` pasa a llamarse
`test_la_casa_sale_del_perfil`. `botv3/test_botv3.py` no se toca (no cambió ningún archivo del bot); en esta
rama da `FAILED (failures=7, errors=34)`, por el entorno de la copia.

### Riesgos abiertos

- El despliegue tiene que crear los tres archivos del canal antes de habilitar el timer, o la unidad no arranca.
  Falla ruidosa, no silenciosa.
- Un `ReadWritePaths` sobre un archivo fija su inodo al montar. Si una cola recorta la bandeja (`os.replace`)
  justo durante los segundos que corre `temblores`, su línea iría al inodo viejo y se perdería. Cada corrida
  monta de nuevo, así que la ventana es solo de esa corrida. La alternativa es mover la bandeja y el cerrojo a
  una carpeta propia del canal, pero eso cambia `registro_avisos.py` y a todas las colas: decide Diego.
- Si un día EMSC empieza a mandar lo de Chile como `GUC`, el aviso lo va a decir («autoridad GUC») sin cambiar
  nada más.
