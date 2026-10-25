# Fixtures de temblores (encargo 91)

`forma-*.json` **no son respuestas reales**: el contenedor de la nube donde se hizo el encargo no tenía salida
a `earthquake.usgs.gov` ni a `www.seismicportal.eu` (proxy con 403). Siguen la forma documentada de cada
servicio (GeoJSON del USGS `summary/*.geojson` y FDSN-WS `format=json` del EMSC), con sismos inventados
alrededor de Chile central, uno malformado en cada una y un par que es el mismo sismo en las dos fuentes.

En la Pi, para guardar respuestas reales (la suite las toma solas: `real-*.json`):

    python3 pi/temblores.py --guardar-fixtures pi/fixtures/temblores

91b: en los `forma-*` el `auth` de EMSC pasó de `GUC` a `EMSC`, que es lo que traen las respuestas reales del
25-10 (`real-*-20261025-2039.json`, bajadas en la Pi). Un evento de otra autoridad se prueba aparte.
