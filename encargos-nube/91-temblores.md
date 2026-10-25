# Encargo 91: aviso de temblores (Claude (Diego) en la nube, 25-10-2026)

Naturaleza `bot`/`investigación`. La idea es del 12-10 y Diego la aprobó el 25-10, **solo la parte de
software**. La caja con el ESP32 (acelerómetro) queda para más adelante.

## Qué se pide

Un servicio chico, `pi/temblores.py`, que consulte los sismos recientes y avise por el canal de avisos
del nodo cuando un temblor sea relevante para la casa.

1. **Investiga las fuentes** (la nube tiene red) y deja la conclusión en el PLAN:
   - el Centro Sismológico Nacional (CSN, sismologia.cl), es decir, qué expone de forma estable y legible
     por máquina;
   - el feed GeoJSON del USGS (`earthquake.usgs.gov/earthquakes/feed/...`).

   Elige una fuente principal y una de respaldo. Guarda respuestas reales como fixtures en
   `pi/fixtures/temblores/`.
2. **La ubicación de la casa** se toma del bloque `clima` del perfil (`botv3/perfiles/jaime.toml`: comuna,
   lat y lon a nivel de comuna). No pongas coordenadas más precisas en ningún archivo.
3. **Cuándo avisar:** configurable en un `pi/temblores.toml`. Por ejemplo, magnitud ≥ 5,0 a menos de 300
   km, o magnitud ≥ 6,5 en cualquier parte de Chile. Propón umbrales razonables, justifícalos en el plan y
   déjalos como valores por defecto.
   - Sin duplicados: un sismo avisado no se repite, aunque lo traigan las dos fuentes o lo corrijan
     después (dedup por hora y lugar con tolerancia).
   - El mensaje es corto: magnitud, lugar, distancia a la casa, hora local y enlace a la fuente.
4. **Respetar el modo descanso** (`pi/descanso.py`): de noche no se avisa, salvo lo urgente. Define qué es
   urgente (por ejemplo, magnitud ≥ 6,5 a menos de 300 km) y usa la biblioteca real de descanso, sin copiar
   el horario.
5. **Canal:** mira cómo publica hoy `pi/avisos.py` (el registro único y la bandeja) y usa lo mismo. No
   inventes un canal nuevo.
6. **Unidades:** `pi/temblores.service` y `pi/temblores.timer` (por ejemplo, cada 5 min), siguiendo el
   estilo de `pi/avisos.service`/`.timer`. Quedan como archivos, sin instalar.

## Reglas

- Pruebas en `pi/test_temblores.py`, con los fixtures reales y la red simulada. Cubren: umbrales,
  distancia (haversine), dedup entre fuentes, una fuente caída (se usa la otra y queda registrado),
  respuesta rota, descanso de noche frente a urgente, y que nunca se escriba fuera de un directorio temporal.
- El estado (sismos ya avisados) va en un archivo cuya ruta se pueda configurar, con escritura atómica.
- Nada laboral ni datos personales en los mensajes.
