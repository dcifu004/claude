# Plan 91: aviso de temblores

## Fuentes (lo investigado)

**Límite de esta sesión.** El contenedor de la nube sólo tiene salida a los registros de paquetes (pypi,
npm). `curl` y la herramienta web dan *403* o *ENOTFOUND* para `earthquake.usgs.gov`, `www.sismologia.cl` y
`www.seismicportal.eu`. **No pude guardar respuestas reales.** Los fixtures de `pi/fixtures/temblores/`
siguen la forma documentada de cada servicio y lo dicen en su nombre (`forma-*.json`).
`pi/temblores.py --guardar-fixtures DIR` baja las respuestas reales en la Pi, y la suite corre sola
también sobre cualquier `real-*.json` que encuentre en esa carpeta.

- **USGS** (`earthquake.usgs.gov/earthquakes/feed/v1.0/summary/<mag>_<periodo>.geojson`):
  - es GeoJSON versionado (`v1.0`), documentado, sin clave y actualizado cada minuto;
  - cada `feature` trae `id`, `properties.mag`, `place`, `time` y `updated` (ms UTC), `url` y
    `geometry.coordinates = [lon, lat, prof]`;
  - las URL las confirma el cliente que usa Home Assistant (`aio_geojson_usgs_earthquakes` 2026.8.1, en pypi).
  - **Principal.** Se usa `4.5_day`, o `2.5_day` si algún umbral queda bajo 4,5.
- **CSN** (sismologia.cl): es la fuente oficial de Chile, pero sólo expone **HTML**. No encontré una API
  documentada ni legible por máquina. El único cliente publicado (`sismos-cl` en npm, último cambio en 2022)
  raspa `/links/ultimos_sismos.html`, una página del sitio anterior. Raspar HTML se rompe en silencio con
  cada rediseño, así que **no es respaldo**.
- **Respaldo: EMSC** (`seismicportal.eu/fdsnws/event/1/query?format=json`): el estándar FDSN, documentado y
  sin clave, independiente de USGS. Para Chile publica las soluciones de la agencia `GUC` (el CSN, de la
  Universidad de Chile), así que en la práctica es la vía legible por máquina hacia el dato del CSN.
  Hay que verificarlo en la Pi con la primera respuesta real.

## Comportamiento

- **Casa:** `clima.lat`/`clima.lon` de `botv3/perfiles/jaime.toml` (ruta configurable), a nivel de comuna.
  `temblores.toml` no repite coordenadas.
- **`pi/temblores.toml`** (valores por defecto):
  - `cerca`: M ≥ 5,0 a ≤ 300 km. Desde M 5 a esa distancia se suele sentir en Santiago; bajo eso hay
    varios por día en Chile y el aviso se volvería ruido.
  - `chile`: M ≥ 6,5 dentro de la caja de Chile continental (lat −56…−17,5, lon −76…−66). Interesa aunque
    no se sienta en la casa (familia, rutas).
  - **Urgente**: M ≥ 6,5 a ≤ 300 km, o M ≥ 7,5 a ≤ 1000 km. Es un remezón que despierta o que puede hacer
    daño en la zona central. Sale también en descanso.
  - `max_edad_h = 3`: tras un corte, un sismo de ayer no se avisa hoy.
- **Dedup:** un sismo avisado se guarda con hora, lat, lon y los ids que trae. Otro registro de cualquier
  fuente es el mismo sismo si cae a ≤ 120 s y ≤ 100 km, o si trae el mismo id. Una corrección de magnitud o
  de lugar no se vuelve a avisar.
- **Mensaje**, una línea:
  `🌎 Temblor M 5,4 a 120 km de la casa · 45 km NE of Valparaíso, Chile · 14:32 · <url de la fuente>`.
  El urgente parte con `🚩 Temblor fuerte`. No lleva el nombre de la comuna ni nada personal.
- **Canal:** el mismo de las colas, vía `encargos/registro_avisos.py`.
  - Primero `bandeja_activa()` y `a_la_bandeja(texto)` (`avisos.py` lo manda en su ciclo); después
    `registrar("temblores", …)` en el registro único.
  - Si la bandeja no está activa o no acepta, el sismo **no** se marca como avisado y se reintenta en la
    corrida siguiente, mientras no pase `max_edad_h`.
- **Descanso:** `avisos.py` ya pasa la bandeja por `pi/descanso.py`. El urgente se marca con `🚩`, que es lo que
  `descanso.es_urgente` reconoce. `temblores.py` carga la biblioteca real para:
  1. comprobar con `es_urgente(texto)` que el mensaje urgente se va a reconocer;
  2. anotar con `en_descanso(ahora)` que el no urgente irá al resumen de la mañana.

  No copia el horario.
- **Fuente caída o respuesta rota:** se usa la otra y queda en el estado (`fuentes.<id>.ok/error/momento`) y
  en stderr (el journal). Un `feature` malformado se salta y se cuenta. Si las dos fallan, sale con código 1.
- **Estado:** `estado` en el toml o `--estado`, escrito de forma atómica (temporal y `os.replace`). Guarda
  los avisados de 14 días.
- **Unidades:** `pi/temblores.service` (oneshot, `User=dcifu004`, `RequiresMountsFor=/opt/nodo/datos`,
  red) y `pi/temblores.timer` (cada 5 min), en el estilo de `avisos.*`. Quedan sin instalar.

## Pruebas (`pi/test_temblores.py`)

Con red simulada (`abrir` inyectado), cubre:
- umbrales en el borde (4,9 y 5,0; 300 y 301 km);
- haversine (Santiago–Valparaíso ≈ 100 km; antípodas ≈ 20 015 km);
- dedup entre USGS y EMSC, y con una corrección de magnitud;
- USGS caído con EMSC en uso, y queda registrado;
- JSON roto y `features` malformados;
- descanso de noche frente a urgente, con `descanso.py` real y `avisos.enviar_respetando_descanso` real con
  `NODO_DESCANSO_PRUEBA_REAL=1`;
- bandeja inactiva que no marca;
- que todo se escribe dentro del temporal;
- el formato del mensaje sin datos personales.
