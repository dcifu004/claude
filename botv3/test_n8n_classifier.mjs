import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const workflowPath = new URL("./n8n-dcs-v3bot-router.workflow.json", import.meta.url);
const raw = fs.readFileSync(workflowPath, "utf8");
const workflow = JSON.parse(raw);

let pasadas = 0;
const ok = (cond, msg) => {
  if (!cond) throw new Error(msg);
  pasadas += 1;
};

// --- El workflow no puede ejecutar shell ni leer Telegram por su cuenta ---
const forbiddenTypes = new Set([
  "n8n-nodes-base.executeCommand",
  "n8n-nodes-base.telegramTrigger",
]);
ok(
  !workflow.nodes.some((candidate) => forbiddenTypes.has(candidate.type)),
  "El workflow contiene ejecución de shell o un segundo lector de Telegram",
);

// --- Ningún secreto viaja en el archivo: las credenciales van por n8n ---
ok(!/gsk_[A-Za-z0-9]/.test(raw), "Hay una API key de Groq escrita en el workflow");
ok(
  !/(sk-|Bearer\s+[A-Za-z0-9_-]{12,})/.test(raw),
  "Hay un token escrito en el workflow",
);

const conCredencial = workflow.nodes.filter((n) => n.credentials);
ok(conCredencial.length === 2, "Se esperaban 2 nodos con credencial (webhook y Groq)");
ok(
  conCredencial.every((n) =>
    Object.values(n.credentials).every((c) => c.id === "REEMPLAZAR_ANTES_DE_ACTIVAR"),
  ),
  "Una credencial quedó con un id real: no debe viajar al vault",
);

// --- El clasificador ---
const node = workflow.nodes.find((candidate) => candidate.id === "classify-request");
ok(Boolean(node), "No se encontró el clasificador");

// El JSON canónico conserva la versión sin publicar. La forma que se publicará se
// obtiene aplicando los tres parches sobre SU jsCode, igual que el mantenimiento.
// Si Python o un ancla fallan, esta suite falla: nunca se saltan los casos 06a/09.
const py = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const parcheado = spawnSync(py, ["-c", String.raw`
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).parent))
import parche_codex_por_perfil as codex
import parche_rutas_funcion as rutas
import parche_cuentas_por_ruta as cuentas
w = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
n = next(x for x in w["nodes"] if x.get("id") == "classify-request")
print(cuentas.parchear(rutas.parchear(codex.parchear(n["parameters"]["jsCode"]))))
`, fileURLToPath(new URL("./n8n-dcs-v3bot-router.workflow.json", import.meta.url))],
  { encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
ok(parcheado.status === 0, `No se pudo parchear el jsCode real: ${parcheado.stderr}`);
node.parameters.jsCode = parcheado.stdout;
ok(node.parameters.jsCode.includes("NOMBRE_NUEVO"), "No quedó aplicado el parche de rutas");
ok(node.parameters.jsCode.includes("CUENTAS_POR_RUTA"), "No quedó aplicado el parche de cuentas");

const classify = new Function("$json", node.parameters.jsCode);

// En modo auto el clasificador SIEMPRE devuelve una decisión {route}, nunca la
// respuesta final: el bot espera esa forma y hace el segundo viaje él mismo.
const rutaDe = (prompt, source = "auto") => {
  const r = classify({ body: { source, prompt } })[0].json;
  ok(r.mode === "decision", `auto devolvió ${r.mode} en vez de una decisión: ${prompt}`);
  return r.payload.route;
};

const cases = [
  ["¿Cuál es la humedad del sensor del huerto?", "ha"],
  ["¿Cuántos registros de tarifas hay en PostgreSQL?", "sql"],
  ["Consulta esto con ChatGPT", "gpt"],
  // La rama técnica apuntaba a `codex` hasta el 19-09-2026. Codex dejó de leer
  // vaults y quedó sólo como motor de la ruta `web`, así que estas preguntas
  // —que son sobre los propios archivos— las contesta `claude`.
  ["Revisa el error del script Python", "claude"],
  ["arregla el error de systemd del bot", "claude"],
  // Agenda y correo (24-09-2026): ruta google, antes que PROPIO y que web.
  ["Crear un evento sin titulo mañana a las 12", "google"],
  ["que tengo en mi agenda mañana", "google"],
  ["agendame una reunion el viernes a las 10", "google"],
  ["busca correos de Falabella de esta semana", "google"],
  ["deja un borrador para Camila diciendo que llego tarde", "google"],
  ["tengo correos sin leer?", "google"],
  ["que hay en mi inbox", "claude"],
  // Nombre de archivo sin palabra clave (24-09-2026: se iba a gpt).
  ["Que hace respaldo.sh", "claude"],
  ["explicame captura.env", "claude"],
  ["para que sirve rclone-drive@.service", "claude"],
  ["que dice jaime.toml sobre drive", "claude"],
  // Y los sufijos sueltos no cazan: sin nombre pegado no es archivo.
  ["que significa md en medicina", "gpt"],
  ["Resume las últimas notas del proyecto", "claude"],
  // `drive` entró a PROPIO el 19-09-2026, cuando los mounts pasaron a ser una
  // fuente que el bot puede leer. Sin esto, "busca el contrato en el drive" no
  // trae posesivo ni sustantivo documental y se iba a la ruta general, que no ve
  // un solo archivo.
  ["busca el contrato en el drive", "claude"],
  // El fallback es gpt, no claude: lo enciclopédico no debe gastar un agente.
  ["¿Cuál es la capital de Mongolia?", "gpt"],
  ["Cuantos habitantes hay en chile en 1993?", "gpt"],
  ["¿Cuándo se fundó Santiago?", "gpt"],
  ["explicame como funciona un motor diesel", "gpt"],
  // Datos que caducan: ruta web (Claude con WebSearch).
  ["quien es el presidente de Chile", "web"],
  ["a cuanto esta el dolar hoy", "web"],
  ["cual es la ultima noticia importante de Chile", "web"],
  // Ojo con las colisiones: "Calama" está en PROPIO porque es una licitación, así
  // que una noticia sobre la ciudad se va igual a claude. Es el compromiso
  // aceptado: ante la duda gana lo propio, y se reformula si hace falta.
  ["cual es la ultima noticia de Calama", "claude"],
  ["cuanto vale la UF actualmente", "web"],
  ["que paso en las elecciones de 2025", "web"],
  // Pero lo propio gana aunque suene a actualidad: se responde leyendo el vault.
  ["cual es la ultima nota de mi proyecto", "claude"],
  ["resumeme el ultimo informe del arnes", "claude"],
  // Señal de dominio propio: posesivo, sustantivo documental o nombre de proyecto.
  ["¿qué dice mi IA_INSTRUCCIONES?", "claude"],
  ["compara las dos propuestas", "claude"],
  ["que quedó pendiente del arnés", "claude"],
  ["busca en mis apuntes lo de Calama", "claude"],
  ["resume el informe del nodo", "claude"],
  // El vocativo con signo de apertura (20-09-2026). El primero es el caso real que
  // destapó el bug: llegó por nota de voz, y Whisper puntúa lo que transcribe, así
  // que en ese canal el `¿` está SIEMPRE. Sin saltarlo, `pilar` caza en PROPIO y la
  // pregunta se va a un agente que en ese perfil no tiene archivos ni buscador.
  ["¿Pilar, qué películas de actualidad hay en streaming?", "web"],
  ["¡Jaime, cuánto está el dólar!", "web"],
  ["¿Pilar, a qué hora abre el mall?", "web"],
  // Y el vocativo sólo se salta al principio: nombrar al bot dentro de la frase
  // sigue siendo una pregunta sobre él, o sea dominio propio.
  ["qué rutas tiene pilar", "claude"],
  // Vocabulario de cine y streaming: el plural no caza con el singular.
  ["qué películas nuevas hay en Netflix", "web"],
  ["recomiéndame series de actualidad", "web"],
  ["qué estrenos hay este fin de semana", "web"],
  // Sin caer en lo genérico: una pregunta atemporal sigue siendo enciclopédica.
  ["quién dirigió el padrino", "gpt"],
];

// --- La rama técnica según el perfil (24-09-2026) ---
// `codex` volvió a las rutas de jaime, pero el clasificador es uno para todos los
// bots: sólo el perfil que tiene la ruta la recibe. Pilar —y una versión vieja del
// bot que no manda perfil— siguen en claude, que es lo que tenían los casos de arriba.
const rutaPara = (perfil, prompt) => {
  const r = classify({ body: { source: "auto", prompt, perfil } })[0].json;
  ok(r.mode === "decision", `auto devolvió ${r.mode} para ${perfil}: ${prompt}`);
  return r.payload.route;
};
for (const prompt of ["Revisa el error del script Python", "Que hace respaldo.sh",
                      "arregla el error de systemd del bot", "pregúntale a codex"]) {
  ok(rutaPara("jaime", prompt) === "codex", `jaime debió ir a codex: ${prompt}`);
  ok(rutaPara("JAIME ", prompt) === "codex", `el perfil se normaliza: ${prompt}`);
  ok(rutaPara("pilar", prompt) === "claude", `pilar no tiene codex: ${prompt}`);
}
// Lo que no es técnico no cambia por tener codex: lo propio sigue en claude.
ok(rutaPara("jaime", "Resume las últimas notas del proyecto") === "claude",
   "jaime: lo propio no técnico sigue en claude");
ok(rutaPara("jaime", "a cuanto esta el dolar hoy") === "web", "jaime: web sigue en web");

for (const [prompt, expected] of cases) {
  const obtenida = rutaDe(prompt);
  ok(obtenida === expected, `${prompt}: esperaba ${expected}, obtuvo ${obtenida}`);
}

// --- La ruta general llega a Groq con modelo y prompt ---
const groq = classify({ body: { source: "gpt", prompt: "explicame que es un quasar" } })[0].json;
ok(groq.mode === "groq", "source=gpt no fue a la ruta de Groq");
ok(
  typeof groq.model === "string" && groq.model.length > 3,
  "La llamada a Groq salió sin modelo",
);
ok(groq.prompt === "explicame que es un quasar", "El prompt no llegó intacto a Groq");

// --- Un solo modelo, y NO puede ser un compound ---
// Medido el 12-09-2026: compound/compound-mini casi nunca ejecutan búsqueda en el
// tier gratis, y cuando la ejecutan devuelven 413 con cuota de sobra. Un buscador
// que no busca y encima falla es peor que no tenerlo; el dato desactualizado se
// resuelve haciendo que el modelo lo declare, en el system prompt del nodo HTTP.
const modeloDe = (prompt) => classify({ body: { source: "gpt", prompt } })[0].json.model;
for (const p of ["quien es el presidente de Chile en 2026", "explicame que es un quasar"]) {
  ok(modeloDe(p) === "openai/gpt-oss-120b", `modelo inesperado para: ${p}`);
  ok(!modeloDe(p).includes("compound"), `no debe usar compound: ${p}`);
}

// El system prompt tiene que exigir que declare la antigüedad de los datos.
const httpNode = workflow.nodes.find((n) => n.id === "groq-call");
const body = httpNode.parameters.jsonBody;
ok(/desactualizad/i.test(body), "El system prompt no exige avisar que los datos caducan");
ok(/no tenes acceso a internet/i.test(body), "El system prompt no declara que no hay internet");

// --- Las rutas todavía cerradas fallan de forma explícita, sin degradar ---
const pendingSql = classify({ body: { source: "sql", prompt: "consulta" } })[0].json;
ok(
  pendingSql.mode === "answer" && pendingSql.payload.kind === "answer",
  "La ruta SQL cerrada no devolvió un answer",
);
ok(
  pendingSql.payload.message.toLowerCase().includes("catalogo") ||
    pendingSql.payload.message.toLowerCase().includes("catálogo"),
  "La ruta SQL cerrada no explicó qué falta",
);
ok(pendingSql.payload.sources.length === 0, "Una ruta cerrada devolvió fuentes");

const pendingHa = classify({ body: { source: "ha", prompt: "temperatura" } })[0].json;
ok(pendingHa.mode === "answer", "La ruta HA cerrada no devolvió un answer");

// --- Entradas inválidas: rechazo explícito, nunca degradación ni 200 vacío ---
// El rechazo NO puede ser un throw: cortaría el flujo antes del nodo Respond y
// n8n contestaría 200 con cuerpo vacío. Tiene que volver como answer.
const rechaza = (payload, que) => {
  const r = classify({ body: payload })[0].json;
  ok(r.mode === "answer", `El rechazo de ${que} no volvió como answer`);
  ok(
    r.payload.kind === "answer" && r.payload.message.length > 0,
    `El rechazo de ${que} salió sin mensaje`,
  );
  ok(!("route" in r.payload), `El rechazo de ${que} degradó a una ruta`);
};

rechaza({ source: "shell", prompt: "id" }, "una ruta prohibida");
rechaza({ source: "auto", prompt: "" }, "un prompt vacío");
rechaza({ source: "auto", prompt: "x".repeat(4001) }, "un prompt sobre el límite");
rechaza({ prompt: "sin source" }, "una petición sin source");

// --- El formateador de Groq nunca deja pasar una respuesta vacía ---
const fmtNode = workflow.nodes.find((n) => n.id === "groq-format");
ok(Boolean(fmtNode), "No se encontró el formateador de Groq");
const format = new Function("$json", fmtNode.parameters.jsCode);

const buena = format({ choices: [{ message: { content: "  un quasar es...  " } }] })[0].json;
ok(buena.message === "un quasar es...", "No extrajo el texto de la respuesta de Groq");
ok(buena.kind === "answer" && buena.sources.length === 0, "El answer de Groq salió mal formado");

const conError = format({ error: { message: "model_decommissioned" } })[0].json;
ok(
  conError.message.includes("model_decommissioned"),
  "Un error de Groq no llegó al usuario",
);

const vacia = format({})[0].json;
ok(vacia.message.length > 0, "Una respuesta vacía de Groq produjo un mensaje vacío");

// --- Nombres por función (06a), sobre el jsCode realmente parcheado ---
// Un bot con `nombres_nuevos: true` recibe `archivos`/`tecnica`; uno viejo, lo de
// siempre. `source` acepta los dos nombres.
const decide = (body) => classify({ body: { source: "auto", ...body } })[0].json.payload.route;
ok(decide({ prompt: "busca en mis notas la minuta de gop", nombres_nuevos: true }) === "archivos",
  "Con nombres_nuevos, claude tiene que volver como archivos");
ok(decide({ prompt: "busca en mis notas la minuta de gop" }) === "claude",
  "Sin nombres_nuevos, un bot viejo tiene que seguir recibiendo claude");
ok(decide({ prompt: "Revisa el error del script Python", perfil: "jaime", nombres_nuevos: true }) === "tecnica",
  "Con nombres_nuevos, codex tiene que volver como tecnica");
ok(decide({ prompt: "clima de mañana", nombres_nuevos: true }) === "web", "web no cambia de nombre");
const general = classify({ body: { source: "general", prompt: "explicame que es un quasar" } })[0].json;
ok(general.mode === "groq", "source=general tiene que ir a Groq igual que gpt");

// Los aliases de entrada toman la rama directa: no pueden quedar cubiertos sólo
// por el webhook, porque éste revertiría recién después de publicar.
for (const [source, expected] of [["archivos", "archivos"], ["tecnica", "tecnica"],
                                  ["claude", "archivos"], ["codex", "tecnica"]]) {
  const directo = classify({ body: { source, prompt: "minuta", nombres_nuevos: true } })[0].json;
  ok(directo.mode === "decision", `${source} no devolvió decisión local`);
  ok(directo.payload.route === expected, `${source} devolvió ${directo.payload.route}`);
}

// --- Cuenta por perfil y ruta (09) ---
// La cuenta es una preferencia del bot (con respaldo), no una orden del usuario.
const decisionConCuenta = (body) => classify({ body: { source: "auto", ...body } })[0].json.payload;
const jaimeArchivos = decisionConCuenta({
  prompt: "busca en mis notas la minuta de gop", perfil: "jaime", nombres_nuevos: true,
});
ok(jaimeArchivos.route === "archivos", "jaime: la ruta nueva de archivos cambió");
ok(jaimeArchivos.cuenta === "claude_diego", "jaime: archivos debe elegir Claude (Diego)");
const pilarWeb = decisionConCuenta({
  prompt: "a cuanto esta el dolar hoy", perfil: "pilar", nombres_nuevos: true,
});
ok(pilarWeb.route === "web", "pilar: web cambió de ruta");
ok(pilarWeb.cuenta === "claude_cami", "pilar: web debe elegir Claude (Cami)");
const sinCuenta = decisionConCuenta({ prompt: "explicame que es un quasar", perfil: "jaime" });
ok(sinCuenta.route === "gpt", "la ruta general cambió");
ok(!Object.hasOwn(sinCuenta, "cuenta"), "la ruta general no debe devolver cuenta");

console.log(`Clasificador n8n: ${pasadas} pruebas pasadas`);
