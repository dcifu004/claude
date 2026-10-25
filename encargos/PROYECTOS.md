# proyectos.json: reglas (encargo 99)

`encargos/proyectos.json` es la fuente de la pestaña **📋 Projects** de 🏭 AI Ops. La mantiene Claude (Diego) cuando
prepara cada encargo (skill `encargar`). La página sólo lo lee, y si falta o está roto lo dice en una línea.

## Forma

```json
{
  "version": 1,
  "columnas": ["Idea", "Ready", "In progress", "Review", "Done"],
  "tope_wip": { "In progress": 2, "Review": 3 },
  "aging_dias": 7,
  "proyectos": [
    { "id": "voz", "nombre": "Asistente de voz",
      "resultado": "Decir «Hola Jaime, pon un temporizador de 10 minutos» en la sala y que suene",
      "docs": ["13", "15"], "encargos": ["06b", "16", "96", "97"],
      "abiertos": { "97": "Ready" },
      "ideas": ["parlante.service"], "bloqueo": "El micrófono de la sala no existe todavía" }
  ],
  "archivos_compartidos": { "botv3/botv3.py": ["96", "97"] }
}
```

- `columnas` es fija y `tope_wip` es el tope de trabajo en curso.
- `aging_dias` es desde cuántos días quieta una tarjeta se pone roja.
- Cada proyecto se define por su **resultado**, en una frase.
- `docs` lista los documentos del proyecto.
- `ideas` alimenta el «Later».
- `bloqueo` es una línea que se ve en rojo.
- El proyecto `otros` se muestra como «Sueltos».

## Agregar un encargo

Pon su id en `encargos` de **un solo** proyecto. Se escribe como el archivo: `96`, `22b` o `9092n`.

- Un número sin letra cubre sus variantes (`23` cubre `23a` a `23h`). Si una variante va en otro proyecto, ponla con su
  letra.
- No hace falta tocar `abiertos`: la columna se deduce sola.

## Mover un encargo

Saca el id del proyecto viejo y ponlo en el nuevo. Un id en dos proyectos es un error.

## Cómo se deduce la columna

1. **`abiertos` manda**: si el id está ahí, va a esa columna.
2. Si hay una cola viva (`vivo/<cola>.json`, corriendo o pausada) con esa etapa:
   - en fase autor o fix, va a **In progress**;
   - en fase rev, va a **Review**.
3. Si su última revisión fue DESPLEGABLE, va a **Done**.
4. Si es un `NN-*.md` sin historial y sin RESULTADO, va a **Ready**.
5. Si tiene historial sin DESPLEGABLE, va a Done con la marca «sin DESPLEGABLE», fuera del throughput y del cycle
   time. Si no tiene historial pero sí RESULTADO, va a Done «sin fechas».

## Qué es `abiertos` y cuándo se borra

Es un **override** para lo que la deducción no ve.

**Cuándo se usa:**
- un encargo de la nube, que no tiene historial en la Pi;
- uno que espera algo de afuera, como una revisión o un despliegue;
- una idea que todavía no es un `.md`.

**Cuándo se borra:** cuando el encargo queda desplegado, o cuando la deducción ya lo pone donde corresponde (por
ejemplo, cuando corre en la Pi). Un id que queda olvidado en `abiertos` sigue mandando sobre el historial.

## Validar

```
python3 encargos/proyectos_check.py
```

Sólo lee. Termina con rc 1 si encuentra cualquiera de estos errores:

- JSON inválido o de más de 1 MB;
- columnas o topes que no existen;
- ids con mala forma o repetidos entre proyectos;
- una columna inventada en `abiertos`;
- `archivos_compartidos` mal formado;
- encargos del índice (`NN-*.md`) sin proyecto.

Pasarse del tope de WIP es un **aviso** (rc 0): el tablero lo muestra en rojo.
