/*
 * Lo común de las páginas 🤖 Asistentes, 💳 Cuentas y 👾 IA Agents (encargo 13). Desde el 23a
 * también lo carga 🧵 Encargos, por `proponer()`.
 *
 * ÚNICO archivo fuente: desde el encargo 18 vive en el paquete `comun` (antes, en
 * `bots`) y las tres páginas lo cargan como `../comun/comun.js`. Cockpit sirve todos los
 * paquetes desde el mismo origen (igual que `../base1/cockpit.js`), así que el CSP
 * `default-src 'self'` lo deja pasar. No hay copias: una prueba exige que este archivo
 * exista una sola vez. Va después de dom.js (`el()`) y de barra.js (`barraNodo`); el
 * tema lo aplica tema.js. 🍇, 📰 y 🌈 no lo cargan: tienen sus propios `hace`, `coma` y
 * `cuando`, con otro formato.
 *
 * Doctrina:
 *  - Las reglas (cuentas, nombres, muros, alias de rutas) llegan de `bots-info`, que las
 *    lee de recetas.py y de cuentas.toml. Acá no se escribe ninguna lista de cuentas.
 *  - Las páginas LEEN y PROPONEN. `proponer()` escribe un JSON en
 *    ~/.local/share/bots-propuestas/ y lo aplica `sudo aplicar-propuesta <id>` por SSH.
 *  - Los nombres de arriba de este archivo son globales de las tres páginas: ninguna
 *    los vuelve a declarar (hay una prueba).
 */
"use strict";

const PROPUESTAS = barraNodo.CARPETA_PROPUESTAS;
const BOTS_INFO = ["sudo", "-n", "/usr/local/bin/bots-info"];

// La última salida de bots-info que leyó la página. De acá salen las cuentas.
let botsInfo = null;

/* ---------- utilidades ---------- */

// `el()` está en dom.js y `aplicarTema()`, en tema.js (encargo 18).

function hace(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "recién";
    const m = Math.floor(s / 60);
    if (m < 60) return `hace ${m} min`;
    const h = Math.floor(m / 60);
    return h < 48 ? `hace ${h} h ${m % 60} min` : `hace ${Math.floor(h / 24)} días`;
}

// «en 5 h 20 min», para las renovaciones. Vacío si la fecha no se entiende o ya pasó.
function faltan(iso) {
    const s = (new Date(iso).getTime() - Date.now()) / 1000;
    if (!Number.isFinite(s) || s <= 0) return "";
    const m = Math.floor(s / 60);
    if (m < 60) return `en ${Math.max(1, m)} min`;
    const h = Math.floor(m / 60);
    return h < 48 ? `en ${h} h ${m % 60} min` : `en ${Math.floor(h / 24)} días`;
}

// Día y hora locales de una fecha ISO con zona: «vie 03-10 03:59».
function cuando(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const pad = n => String(n).padStart(2, "0");
    return `${["dom", "lun", "mar", "mié", "jue", "vie", "sáb"][d.getDay()]} ` +
        `${pad(d.getDate())}-${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function pct(x) {
    return x == null ? "sin dato" : `${Math.round(x)} %`;
}

function coma(x, dec = 2) {
    return Number(x).toFixed(dec).replace(".", ",");
}

const usd = x => "US$ " + coma(x || 0);

function mostrarError(msg) {
    const e = document.getElementById("error");
    e.hidden = !msg;
    e.textContent = msg || "";
}

// Los anchos van por CSSOM y no por atributo: el CSP de Cockpit bloquea los estilos en
// línea. Se marca el elemento con data-ancho y acá se le pone el flex-grow.
function aplicarAnchos(cont) {
    cont.querySelectorAll("[data-ancho]").forEach(s => { s.style.flexGrow = s.dataset.ancho; });
}

/* ---------- bots-info: la única fuente de cuentas, nombres, muros y alias ---------- */

async function leerBotsInfo() {
    const out = await cockpit.spawn(BOTS_INFO, { err: "message" });
    botsInfo = JSON.parse(out);
    return botsInfo;
}

// {id: {nombre, motor, dueno, pagada, interactiva}} tal como llega. Vacío si bots-info
// es anterior al encargo 13: las páginas lo dicen en vez de inventar una lista.
function cuentasConocidas() {
    return (botsInfo && botsInfo.cuentas) || {};
}

function nombreCuenta(id) {
    return (cuentasConocidas()[id] || {}).nombre || id;
}

// Cuenta pagada (con login, precio y límite semanal). Groq no lo es.
function pagada(id) {
    return !!(cuentasConocidas()[id] || {}).pagada;
}

function duenoCuenta(id) {
    return (cuentasConocidas()[id] || {}).dueno || "";
}

// Nombre nuevo de una ruta (06a): `claude` → `archivos`. La tabla sale de bots-info
// (recetas.ALIAS_RUTA del bot); si falta, queda el nombre de siempre.
function nombreRuta(interna) {
    const alias = (botsInfo && botsInfo.alias_rutas) || {};
    return Object.keys(alias).find(n => alias[n] === interna) || interna;
}

// Las cuentas con las que 👾 puede abrir la sesión interactiva: [[id, {nombre, dir}]].
// `dir` es relativo al home ("" = la configuración de siempre). Se vuelve a validar acá
// porque termina en una línea de shell: sólo letras, números, punto, guion y «/».
function cuentasInteractivas(cuentas = cuentasConocidas()) {
    const limpio = /^[A-Za-z0-9._-]+(\/[A-Za-z0-9._-]+)*$/;
    return Object.entries(cuentas).filter(([, c]) => {
        const d = c && c.interactiva && c.interactiva.config_dir;
        return typeof d === "string" && (d === "" || (limpio.test(d) && !d.includes("..")));
    }).map(([id, c]) => [id, { nombre: c.nombre || id, dir: c.interactiva.config_dir }]);
}

/* ---------- chips y barras ---------- */

// Barra de uso: la parte usada y la libre, de 0 a 100.
function barraUso(usado, titulo) {
    const u = Math.max(0, Math.min(100, Number(usado) || 0));
    return el("div", { class: "barra-ciclo" + (u >= 90 ? " lleno" : u >= 75 ? " justo" : ""), title: titulo || "" },
        el("span", { class: "usado", "data-ancho": String(Math.round(10 * u)) }),
        el("span", { class: "ocioso", "data-ancho": String(Math.round(10 * (100 - u))) }));
}

// Dos chips, «5 h» y «semana», con el margen de una cuenta. `m` es una entrada de
// `bots-info.margen.cuentas`; sin dato lo dice, no inventa un 0.
function chipsMargen(m) {
    if (!m || !m.pagada) return el("span", { class: "chips" }, el("span", { class: "chip dato" }, "sin límite semanal"));
    const chip = (etiqueta, v) => {
        const texto = !v ? "sin dato" : v.renovada ? "renovada" : `${pct(v.libre_pct)} libre`;
        const clase = !v || v.libre_pct == null ? "" : v.libre_pct <= 10 ? " mal" : v.libre_pct <= 25 ? " ojo" : " activa";
        return el("span", { class: "chip dato" + clase,
            title: v && v.renueva ? `se renueva ${cuando(v.renueva)}` : "" }, `${etiqueta}: ${texto}`);
    };
    return el("span", { class: "chips" }, chip("5 h", m.ventana_5h), chip("semana", m.semanal));
}

/* ---------- propuestas ---------- */

let pendienteDialogo = null;

function resumenValor(tipo, valor) {
    if (tipo === "voz_ritmo" && valor && typeof valor === "object")
        return `length_scale ${coma(valor.voz_length_scale)} · pausa ${coma(valor.voz_pausa_s)} s`;
    if (tipo === "pronunciacion" && valor && typeof valor === "object") {
        const k = Object.keys(valor);
        return `${k.length} palabras` + (k.length ? `: ${k.slice(0, 4).join(", ")}${k.length > 4 ? "…" : ""}` : "");
    }
    if (tipo === "personalidad" && valor && typeof valor === "object")
        return `tono ${valor.tono} · largo ${valor.largo}`;
    if (tipo === "sobre") return `«sobre mí», ${String(valor || "").trim().length} caracteres`;
    if (tipo === "modelo_claude") return valor || "el de la cuenta";
    if (tipo === "tope_diario" && valor && typeof valor === "object")
        return Object.entries(valor).filter(([, n]) => n).map(([r, n]) => `${r} ${n}`).join(", ") || "sin topes";
    if (tipo === "registro_cuentas" && valor && typeof valor === "object")
        return Object.entries(valor).map(([c, v]) => [c, v.precio_mes_usd != null ? `US$${v.precio_mes_usd}` : null, v.renueva != null ? (v.renueva || "—") : null,
            v.aviso_semanal !== undefined ? `aviso sem ${v.aviso_semanal ?? "sin"}` : null, v.aviso_5h !== undefined ? `aviso 5h ${v.aviso_5h ?? "sin"}` : null]
            .filter(Boolean).join(" ")).join(" · ");
    if (tipo === "cuentas" && valor && typeof valor === "object")
        return Object.entries(valor).map(([r, ids]) => `${r} ${ids.join("→")}`).join(" · ");
    if (tipo === "recetas" && valor && typeof valor === "object")
        return Object.entries(valor).map(([r, v]) => `${r} ${v.automatico ? "auto" : "cadena"}` +
            (v.umbral_semanal != null ? ` sem${v.umbral_semanal}` : "") +
            (v.umbral_5h != null ? ` 5h${v.umbral_5h}` : "")).join(" · ");
    if (tipo === "encargos_config" && valor && typeof valor === "object") {
        // {parte: {a: {b: x}}} → un texto por hoja. Las cuentas, con su nombre.
        const hojas = (t, f) => Object.entries(t || {}).flatMap(([a, x]) => Object.entries(x || {}).map(([b, v]) => f(a, b, v)));
        return [...hojas(valor.naturaleza, (n, rol, nivel) => `${n}.${rol} ${nivel}`),
                ...hojas(valor.niveles, (m, n, v) => `${m}.${n} ${v.modelo} ${v.esfuerzo || ""}`.trim()),
                ...hojas(valor.reparto, (n, rol, c) => `${n}.${rol} ${nombreCuenta(c)}`),
                ...(valor.autorizacion ? [`candados: ${(valor.autorizacion.modelos || []).join(", ")}`] : []),
                ...Object.entries(valor.factor_modelo || {}).map(([m, k]) => `factor ${m} ${coma(k)}`)].join(" · ");
    }
    return String(valor);
}

// El diálogo se arma una vez, acá, para que 🤖 y 💳 no repitan su HTML.
function dialogoPropuesta() {
    let d = document.getElementById("dialogo");
    if (d) return d;
    d = el("dialog", { id: "dialogo" },
        el("form", { method: "dialog", id: "form-propuesta" },
            el("h2", { id: "d-titulo" }),
            el("div", { id: "d-cuerpo" }),
            el("label", {}, "Motivo (opcional)",
                el("input", { id: "d-motivo", type: "text", maxlength: "200", placeholder: "por qué la quieres" })),
            el("div", { class: "fila-botones" },
                el("button", { value: "cancelar", class: "secundario", formnovalidate: true }, "Cancelar"),
                el("button", { value: "guardar", id: "d-guardar" }, "Guardar propuesta"))));
    d.addEventListener("close", guardarPropuesta);
    document.body.append(d);
    return d;
}

// `perfil` es el id del perfil (jaime, pilar) al que va la propuesta. Cada propuesta es
// de UN perfil, también cuando 💳 muestra los dos juntos. El registro de cuentas es común
// a los dos, pero aplicar-propuesta igual pide un perfil válido. Lo mismo `encargos_config`
// (🧵 Encargos, encargo 23a), que no es de ningún perfil.
function proponer(cambio, perfil) {
    const p = botsInfo.perfiles[perfil];
    pendienteDialogo = { cambio, perfil };
    const d = dialogoPropuesta();
    const amplia = cambio.tipo === "agregar_ruta" || cambio.tipo === "carpeta_lectura" || !!cambio.amplia;
    document.getElementById("d-titulo").textContent = (amplia ? "⚠️ " : "") +
        (cambio.tipo === "registro_cuentas" ? "Propuesta para el registro de cuentas"
            : cambio.tipo === "encargos_config" ? "Propuesta para el reparto y los modelos de los encargos"
            : `Propuesta para ${p.toml.nombre || perfil}`);
    document.getElementById("d-cuerpo").replaceChildren(
        el("div", { class: "antes-despues" },
            el("div", {}, el("strong", {}, "Cambio: "), cambio.tipo.replace("_", " "), " · ",
               el("code", {}, resumenValor(cambio.tipo, cambio.valor))),
            el("div", {}, el("strong", {}, `${cambio.clave} antes: `), cambio.antes || "—"),
            el("div", {}, el("strong", {}, `${cambio.clave} después: `), cambio.despues || "—"),
            amplia ? el("div", { class: "aviso ojo" }, "Esto amplía lo que puede hacer el bot.") : null,
            el("p", { class: "tenue" }, "El diff completo lo muestra el script al aplicarla.")));
    document.getElementById("d-motivo").value = "";
    d.showModal();
}

async function guardarPropuesta() {
    const d = document.getElementById("dialogo");
    const pendiente = pendienteDialogo;
    pendienteDialogo = null;
    if (d.returnValue !== "guardar" || !pendiente) return;
    const { cambio, perfil } = pendiente;
    const ahora = new Date();
    const pad = n => String(n).padStart(2, "0");
    const id = [
        `${ahora.getFullYear()}${pad(ahora.getMonth() + 1)}${pad(ahora.getDate())}`,
        `${pad(ahora.getHours())}${pad(ahora.getMinutes())}${pad(ahora.getSeconds())}`,
        perfil, cambio.tipo.replace("_", "-"),
    ].join("-").toLowerCase().replace(/[^a-z0-9-]/g, "");
    const prop = {
        id, perfil, tipo: cambio.tipo, valor: cambio.valor,
        motivo: document.getElementById("d-motivo").value.trim(),
        creada: ahora.toISOString(),
    };
    try {
        await cockpit.spawn(["mkdir", "-p", PROPUESTAS]);
        await cockpit.file(`${PROPUESTAS}/${id}.json`, { syntax: JSON }).replace(prop);
        await pintarPropuestas();
        await pintarContadorPropuestas();
    } catch (e) {
        mostrarError("No pude guardar la propuesta: " + (e.message || e));
    }
}

// Cuántas propuestas quedan por aplicar, con el enlace a 🤖 Asistentes, que es el único
// lugar donde se listan (encargo 18). Va en el <div id="propuestas-contador"> de la página
// que lo tenga (💳). Refresca también el contador de la barra. Si la carpeta no se pudo
// leer dice «sin datos»: nunca 0.
async function pintarContadorPropuestas() {
    const { propuestas } = await barraNodo.refrescar();
    const cont = document.getElementById("propuestas-contador");
    if (!cont) return;
    cont.className = "aviso " + (propuestas ? "ojo" : "neutro");
    cont.replaceChildren(
        propuestas == null ? "📝 Propuestas por aplicar: sin datos (no pude leer la carpeta). "
            : propuestas ? el("strong", {}, `📝 ${propuestas} propuesta${propuestas > 1 ? "s" : ""} por aplicar. `)
            : "📝 No hay propuestas por aplicar. ",
        "Se listan y se copian sus comandos en ",
        el("button", { class: "mini", onclick: () => cockpit.jump("/bots") }, "🤖 Asistentes →"));
}

// La lista de propuestas, en el <div id="propuestas"> de la página que la tenga.
async function pintarPropuestas() {
    const cont = document.getElementById("propuestas");
    if (!cont) return;
    let lista = "";
    try {
        lista = await cockpit.spawn(["find", PROPUESTAS, "-maxdepth", "1", "-name", "*.json",
                                     "-not", "-name", "*.resultado.json"], { err: "ignore" });
    } catch (e) { /* carpeta aún no existe */ }
    const archivos = lista.split("\n").filter(Boolean).sort().reverse();
    if (!archivos.length) {
        cont.replaceChildren(el("p", { class: "tenue" }, "No hay propuestas todavía."));
        return;
    }
    const props = [];
    for (const a of archivos.slice(0, 30)) {
        try {
            props.push(await cockpit.file(a, { syntax: JSON }).read());
        } catch (e) { /* ilegible: se omite */ }
    }
    const resultados = (botsInfo && botsInfo.resultados) || {};
    cont.replaceChildren(el("table", {},
        el("tr", {}, el("th", {}, "Propuesta"), el("th", {}, "Estado"), el("th", {}, "")),
        props.filter(Boolean).map(p => {
            const r = resultados[p.id];
            const estado = r ? r.estado : "pendiente";
            const clase = { aplicada: "ok", revertida: "mal", rechazada: "tenue" }[estado] || "";
            const cmd = `sudo aplicar-propuesta ${p.id}`;
            return el("tr", {},
                el("td", {}, el("strong", {}, p.perfil), " · ", p.tipo.replace("_", " "), " · ",
                   el("code", {}, resumenValor(p.tipo, p.valor)),
                   p.motivo ? el("div", { class: "tenue" }, p.motivo) : null,
                   r ? el("div", { class: "tenue" }, r.detalle) : null),
                el("td", {}, el("span", { class: "estado " + clase }, estado)),
                el("td", {}, r ? null : [
                    el("button", { class: "mini", title: cmd, onclick: ev => {
                        navigator.clipboard.writeText(cmd).then(() => {
                            ev.target.textContent = "copiado ✓";
                        }, () => { ev.target.textContent = cmd; });
                    } }, "Copiar comando"), " ",
                    el("button", { class: "mini", onclick: async () => {
                        await cockpit.file(`${PROPUESTAS}/${p.id}.json`).replace(null);
                        pintarPropuestas();
                        pintarContadorPropuestas();
                    } }, "Descartar"),
                ]));
        })));
}
