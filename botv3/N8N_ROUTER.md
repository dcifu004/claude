# Contrato del router n8n para Dcs_v3bot

El bot hace `POST` a `BOTV3_N8N_QUERY_URL` con `Content-Type: application/json` y el
header `X-BotV3-Secret`. Los esquemas exactos viven en `router-request.schema.json` y
`router-response.schema.json`.

Para `source: auto`, n8n devuelve primero `{"route": "claude|codex|sql|ha|gpt"}`.
Dcs_v3bot ejecuta Claude/Codex mediante sus adaptadores locales fijos; las otras tres
rutas vuelven a n8n para obtener una respuesta estructurada. El usuario no necesita
escribir comandos con `/`.

El clasificador debe aplicar esta precedencia: datos estructurados y conteos del nodo
van a `sql`; estados domóticos a `ha`; una petición explícita por conocimiento general
o generación sin archivos va a `gpt`; lectura o análisis profundo de archivos va a
`claude` o `codex`. Si la intención es ambigua, el workflow pregunta una sola aclaración
en vez de ejecutar más de una ruta.

El webhook no se importa ni publica hasta que exista autenticación. Debe permanecer
accesible sólo desde la Pi y rechazar antes de rutear si el secreto no coincide.

La plantilla `n8n-dcs-v3bot-router.workflow.json` deja el workflow desactivado y exige
una credencial Header Auth llamada `Dcs_v3bot interno`. No contiene tokens. Su primera
versión clasifica con reglas locales transparentes, por lo que no envía cada consulta a
un modelo sólo para decidir la ruta. Los adaptadores aún no configurados responden con
un estado pendiente explícito.

## Adaptadores

### `sql`

- Rol separado con `default_transaction_read_only=on`.
- Sólo `SELECT` sobre vistas expresamente aprobadas.
- La pregunta se traduce a un `query_id` de catálogo; no se ejecuta SQL libre generado
  por el modelo ni expresiones de n8n dentro del campo SQL.
- Timeout y límite de filas obligatorios.

### `ha`

- El workflow llama a un proxy local que sólo admite endpoints GET aprobados.
- No se entrega al workflow una ruta para `services`, automatizaciones ni acciones.
- Las respuestas se reducen a estados y atributos necesarios.

### `gpt` — la ruta general va por **Groq**, no por OpenAI

Decidido el 12-09-2026. El endpoint de Groq es compatible con el de OpenAI
(`https://api.groq.com/openai/v1/chat/completions`), así que el nodo HTTP no cambia de
forma; lo que cambia es el proveedor, la credencial y el modelo.

**Por qué Groq y no la API de OpenAI:** la key de Groq ya existe en el nodo para
transcribir audio y su tier gratis alcanza de sobra (~2.000 req/día), mientras que la API
de OpenAI es gasto nuevo. Y **no sirve apoyarse en Codex para esto**: Codex corre en la Pi
con la cuenta de ChatGPT de Diego, así que cada consulta casual del bot le comería la cuota
que usa para trabajar — ya pasó el 12-09, con `You've hit your usage limit` en plena prueba.

- La key va en una credencial Header Auth de n8n llamada `Groq API`, **nunca en el vault**.
  El archivo del workflow se versiona con `REEMPLAZAR_ANTES_DE_ACTIVAR` y una prueba
  falla si aparece un `gsk_…` escrito adentro.
- El modelo vive en **un solo lugar**: la constante `GROQ_MODEL` del nodo *Validar y
  clasificar*. Groq retira modelos sin aviso; si la ruta empieza a devolver
  `model_decommissioned`, se listan los vigentes con `/v1/models` y se cambia ahí.
- **Esta ruta no recibe contenido de ningún vault.** El bot manda solo la pregunta, y el
  system prompt le dice al modelo que no tiene acceso a archivos y que no invente su
  contenido. Es deliberado: la autorización del 12-09 cubre enviar fragmentos laborales a
  **Claude, Codex u OpenAI**, y Groq no estaba en esa lista. Para documentos está `claude`.
- Timeout de 25 s y `neverError`: un fallo de Groq vuelve como un `answer` que lo explica,
  nunca como un 200 vacío ni como una caída del workflow.

## Criterio de activación

La publicación exige cuatro pruebas negativas: header ausente, `source` desconocido,
consulta SQL fuera del catálogo e intento de acción Home Assistant. Las cuatro deben
fallar sin degradar a otro adaptador.
