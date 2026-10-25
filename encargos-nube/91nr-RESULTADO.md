# Revisión 91n — aviso de temblores (Codex, 25-10-2026)

Revisión 1, sin modificar código. El diff entregado en
`~/encargos-logs/cola91n-91n-diff.txt` no trae fotos propias por
el fallo de Git; conforme al encargo, revisé como alcance completo los ocho
archivos nuevos enumerados en `encargos/91n-revision-nube.md`, incluidos los
borrados (no hay ninguno indicado). También contrasté contra
`encargos/91-PLAN.md` y `encargos/91-RESULTADO.md`. No hay resultados de
revisiones anteriores `91nr*` que cerrar, ni existen decisiones o registros de
búsqueda de esta etapa (`91n-decisiones.md`, `91n-busquedas.jsonl` y
`manual-busquedas.jsonl` están ausentes).

Todas las ejecuciones se hicieron con `BOTV3_USO_CUENTAS`,
`BOTV3_USO_RUTAS` y `BOTV3_STATE_DIR` bajo un `mktemp -d`; no se usó el libro
real. La reproducción de red también usó un temporal. No hubo JavaScript en el
alcance, por lo que no corresponde tokenizar JS.

## Pruebas (salida real)

```text
$ NODO_PRUEBAS=1 BOTV3_USO_CUENTAS=<tmp>/uso-cuentas.jsonl BOTV3_USO_RUTAS=<tmp>/uso-rutas.jsonl BOTV3_STATE_DIR=<tmp>/state python3 -B -m unittest -v pi/test_temblores.py
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

----------------------------------------------------------------------
Ran 21 tests in 0.116s

OK (skipped=1)
```

La línea base de la cola es `[]`, por lo que no hay una falla previa que
separar. Los mensajes esperados de features malformados se imprimieron durante
las pruebas que usan los fixtures de forma.

## Hallazgos, de más grave a menos grave

### 1. [Grave] La prueba nueva publica las coordenadas de la casa fuera del perfil autorizado

`pi/test_temblores.py:114-115` compara el perfil real contra el literal
`(las coordenadas de la comuna)`. Esas coordenadas de comuna ya existían sólo en el perfil,
pero ahora quedan repetidas en un archivo nuevo del repositorio y de la rama
en la nube. Contradice el plan (`encargos/91-PLAN.md:30`) y el encargo
(`encargos/91-temblores.md:17`), que exigen obtenerlas desde el perfil y no
poner coordenadas de la casa en archivos nuevos. Aunque el aviso al usuario no
las muestra, el dato personal ya quedó expuesto a más superficies de código.

**Reproducción:** `NODO_PRUEBAS=1 ... python3 -B -m unittest -v
pi/test_temblores.py` ejecuta `test_la_casa_sale_del_perfil_real` en verde, y
la fuente de esa aserción contiene ambos números literales. La prueba pasa
precisamente porque compara contra la ubicación real, no contra una forma
aislada. **Arreglo:** usar en esa prueba un perfil temporal con coordenadas
ficticias, y verificar que `casa()` devuelve los valores de ese temporal; no
dejar coordenadas de la casa en la suite.

### 2. [Grave] La unidad abre escritura sobre todo el volumen cifrado, incluidos vaults ajenos al aviso

`pi/temblores.service:29` declara
`ReadWritePaths=/opt/nodo/datos/temblores /opt/nodo/datos`. El segundo prefijo
contiene al primero y convierte en escribible todo `/opt/nodo/datos`: los dos
vaults, estados de otros servicios y cualquier secreto que el UID pueda abrir.
Así, las protecciones `ProtectSystem=strict` y `ProtectHome=true` no aíslan el
proceso de los datos que el encargo exige no leer ni tocar. El propio resultado
ya reconoce este riesgo, pero no lo resuelve.

**Reproducción:** inspeccionar la unidad muestra ambos prefijos en la línea 29;
la semántica de `ReadWritePaths` hace que el prefijo más amplio autorice cada
ruta bajo él. `systemd-analyze verify pi/temblores.service
pi/temblores.timer` no pudo validar en este sandbox porque el bus devuelve
`SO_PASSCRED failed: Operation not permitted`; eso no altera la declaración
inequívoca de la unidad. **Arreglo:** limitar las rutas a
`/opt/nodo/datos/temblores` y a los archivos estrictamente necesarios para la
bandeja y el registro; si el cerrojo necesita crearse en la raíz del volumen,
precrearlo por el mecanismo de despliegue o moverlo a un directorio dedicado,
en vez de conceder el directorio padre completo.

### 3. [Media] La condición de fuentes reales del plan sigue sin estar verificada ni protegida por la suite

`pi/fixtures/temblores/` sólo contiene `forma-*.json` inventados y
`pi/test_temblores.py:177-184` omite la única prueba real si no existe un
`real-*.json`; la ejecución efectiva quedó con `skipped=1`. Por ello no se
cumplió la exigencia del encargo de guardar respuestas reales y probar la forma
que llega desde cada fuente.

**Reproducción:** en un `mktemp -d`, con las tres variables `BOTV3_*`
aisladas, ejecuté `pi/temblores.py --guardar-fixtures <tmp>/fixtures`. Ambas
descargas terminaron con `URLError: [Errno -3] Temporary failure in name
resolution`, rc 1 y no crearon fixtures. La documentación oficial sí respalda
la forma programada: USGS documenta `FeatureCollection`, `properties.mag`,
`properties.time` y `geometry.coordinates`; EMSC documenta JSON GeoJSON con
`lat`, `lon`, `depth`, `unid`, `flynn_region` y `auth`, y que `start` es alias
de `starttime`. Eso no sustituye una respuesta real de esta Pi. **Arreglo:**
cuando la resolución DNS esté disponible, guardar una respuesta real de cada
origen bajo `real-*.json`, comprobar que se parsea y dejar que la suite deje de
omitir esa prueba antes de instalar.

### 4. [Media] El código acepta cualquier autoridad EMSC aunque el diseño justifica el respaldo por las soluciones GUC/CSN

`pi/temblores.py:176-193` lee `unid`, `lat`, `lon`, `depth`, `time`,
`mag` y `flynn_region`, pero nunca lee ni valida `properties.auth`. Sin embargo,
el plan y el resultado presentan EMSC como la vía de las soluciones CSN/GUC.
Una respuesta con la misma forma y `auth` de otra autoridad se acepta igual y
puede disparar un aviso; la prueba de forma (`pi/test_temblores.py:171-175`)
tampoco afirma el campo ni su valor.

**Reproducción:** cambiar sólo `auth` del fixture EMSC por otro texto no altera
la salida de `leer_emsc`, porque ese campo no participa en ninguna condición.
**Arreglo:** decidir y documentar explícitamente si el respaldo es EMSC sin
restricción de autoridad —entonces no atribuirlo a CSN/GUC—, o validar
`auth == "GUC"` para los eventos chilenos y cubrir ambos caminos con fixtures.

## Lo que revisé y está bien

- El canal es el existente: `publicar()` exige `bandeja_activa()` y
  `a_la_bandeja()` antes de `registrar()`. La prueba de bandeja inactiva confirma
  que no marca el sismo y lo reintenta.
- El modo descanso usa `pi/descanso.py` real. La prueba de noche verifica que
  sólo los mensajes con `🚩` salen de inmediato y que los demás quedan para el
  resumen.
- El estado se escribe por temporal en el mismo directorio y `os.replace`;
  la prueba deja intacto el repositorio y el estado real.
- Los lectores rechazan una respuesta que no sea `FeatureCollection`, limitan la
  descarga a 5 MiB y acotan lugar y mensajes. No encontré impresión de tokens.
- La documentación oficial de USGS y EMSC coincide con los campos que realmente
  consume el parser; la observación pendiente es que no se pudo confirmarla con
  una muestra descargada desde esta Pi.

VEREDICTO: NO DESPLEGABLE
