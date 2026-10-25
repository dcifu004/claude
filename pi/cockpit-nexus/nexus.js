/* Herramienta Cockpit Nexus: sólo lee fuentes ya existentes y recomienda. */
"use strict";

const ESTADO_JSON = "/opt/nodo/datos/estado.json";
const USO_JSON = "/opt/nodo/datos/uso.json";
const ACTUALIZAR_CADA_MS = 5 * 60 * 1000;
const $ = selector => document.querySelector(selector);

let datos = { info: null, estado: null, uso: null, fuentes: {} };
let panelActual = "recomendar";

function el(tag, attrs = {}, ...hijos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") e.className = v;
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
    }
    for (const h of hijos.flat()) {
        if (h == null || h === false) continue;
        e.append(h instanceof Node ? h : document.createTextNode(String(h)));
    }
    return e;
}

function aplicarTema() {
    let estilo = null;
    try { estilo = localStorage.getItem("shell:style"); } catch (e) { /* sin storage */ }
    const oscuro = estilo === "dark" || ((!estilo || estilo === "auto") && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = oscuro ? "dark" : "light";
}

function hace(iso) {
    if (!iso) return "sin fecha";
    const d = new Date(iso);
    if (isNaN(d)) return "fecha inválida";
    const min = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
    if (min < 1) return "recién";
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;
}

function numero(n) {
    return new Intl.NumberFormat("es-CL").format(Number(n || 0));
}

async function leerArchivo(ruta, nombre) {
    try {
        const data = await cockpit.file(ruta, { syntax: JSON }).read();
        return { ok: Boolean(data), data, nombre, detalle: data ? "leída" : "vacía" };
    } catch (e) {
        return { ok: false, data: null, nombre, detalle: e.message || String(e) };
    }
}

async function leerBots() {
    try {
        const out = await cockpit.spawn(["sudo", "-n", "/usr/local/bin/bots-info"], { err: "message" });
        return { ok: true, data: JSON.parse(out), nombre: "bots-info", detalle: "lectura real de perfiles" };
    } catch (e) {
        return { ok: false, data: null, nombre: "bots-info", detalle: e.message || String(e) };
    }
}

async function cargar() {
    const boton = $("#actualizar");
    boton.disabled = true;
    const [bots, estado, uso] = await Promise.all([
        leerBots(), leerArchivo(ESTADO_JSON, "estado.json"), leerArchivo(USO_JSON, "uso.json"),
    ]);
    datos = {
        info: bots.data,
        estado: estado.data,
        uso: uso.data,
        fuentes: { bots, estado, uso },
    };
    boton.disabled = false;
    $("#leido").textContent = `actualizado ${hace((bots.data || estado.data || {}).momento)}`;
    pintarAdvertencias();
    pintarPerfiles();
    pintarTodo();
}

function pintarAdvertencias() {
    const cont = $("#advertencias");
    cont.replaceChildren();
    const fallas = Object.values(datos.fuentes).filter(f => !f.ok);
    if (fallas.length) cont.append(el("div", { class: "aviso ojo" },
        el("strong", {}, "Datos parciales. "),
        fallas.map(f => `${f.nombre}: no disponible`).join(" · ")));
    $("#error").hidden = true;
}

function pintarPerfiles() {
    const select = $("#perfil");
    const anterior = select.value;
    const perfiles = Object.entries((datos.info && datos.info.perfiles) || {});
    select.replaceChildren(...perfiles.map(([id, p]) =>
        el("option", { value: id }, (p.toml || {}).nombre || id)));
    if (perfiles.some(([id]) => id === anterior)) select.value = anterior;
    if (!perfiles.length) select.append(el("option", { value: "jaime" }, "Jaime (sin datos)"));
}

function entradaActual() {
    return { perfil: $("#perfil").value, tarea: $("#tarea").value,
        prioridad: $("#prioridad").value, datos: $("#datos").value };
}

function pintarRecomendacion() {
    const r = NexusLogic.recomendar(entradaActual(), datos.info || {});
    const cont = $("#resultado");
    if (!r.posible) {
        cont.replaceChildren(
            el("div", { class: "eyebrow" }, "RECOMENDACIÓN"),
            el("h2", { class: "resultado-titulo" }, r.titulo),
            el("p", {}, r.explicacion),
            el("ul", {}, (r.razones || []).map(x => el("li", {}, x))),
            el("div", { class: "aviso ojo" }, r.advertencia));
        return;
    }
    cont.replaceChildren(
        el("div", { class: "eyebrow" }, "RUTA SUGERIDA"),
        el("div", { class: "resultado-linea" },
            el("h2", { class: "resultado-titulo" }, r.titulo),
            el("span", { class: `estado-pill ${r.estado.estado}` }, r.estado.estado.replace("_", " "))),
        el("p", { class: "resultado-foco" }, r.foco),
        el("dl", { class: "dato compacto" },
            el("dt", {}, "Proveedor"), el("dd", {}, r.proveedor),
            el("dt", {}, "Tratamiento"), el("dd", {}, r.salida),
            el("dt", {}, "Alternativa"), el("dd", {}, r.alternativa ? `${r.alternativa.titulo} · ${r.alternativa.estado.estado.replace("_", " ")}` : "sin alternativa verificada")),
        el("h3", {}, "Por qué"),
        el("ul", { class: "razones" }, r.razones.map(x => el("li", {}, x))),
        r.advertencia ? el("div", { class: "aviso ojo" }, r.advertencia) : null,
        el("p", { class: "no-accion" }, "Resultado informativo · no se ejecutó ninguna acción"));
}

function buscarServicio(nombre) {
    const estado = datos.estado || {};
    if (nombre in (estado.servicios || {})) return estado.servicios[nombre] ? "activo" : "caído";
    const c = (estado.contenedores || []).find(x => (x.nombre || "").toLowerCase().includes(nombre));
    return c ? (c.ok ? "activo" : "caído") : "no verificado";
}

function tarjetaEstado(nombre, estado, detalle) {
    const clase = estado === "activo" || estado === "disponible" ? "ok" : estado === "caído" ? "mal" : "ojo";
    return el("article", { class: "tarjeta mini-tarjeta" },
        el("div", { class: "mini-titulo" }, el("h2", {}, nombre), el("span", { class: `estado ${clase}` }, estado)),
        el("p", { class: "tenue" }, detalle));
}

function pintarEstado() {
    const perfiles = Object.values((datos.info && datos.info.perfiles) || {});
    const activos = perfiles.filter(p => (p.servicio || {}).ActiveState === "active").length;
    const claude = datos.uso && datos.uso.claude;
    const codex = datos.uso && datos.uso.codex;
    $("#resumen-estado").replaceChildren(
        tarjetaEstado("Perfiles", perfiles.length ? `${activos}/${perfiles.length} activos` : "no verificado", "Jaime y Pilar según bots-info"),
        tarjetaEstado("n8n", buscarServicio("n8n"), "Router operativo; Nexus no lo reemplaza"),
        tarjetaEstado("PostgreSQL", buscarServicio("postgres"), "Base existente del nodo"),
        tarjetaEstado("Claude", claude && claude.disponible ? "disponible" : "no verificado", claude && claude.disponible ? `${numero(claude.hoy.mensajes)} mensajes medidos hoy` : (claude && claude.razon) || "sin telemetría"),
        tarjetaEstado("Codex", codex && codex.disponible ? "disponible" : "no verificado", (codex && codex.razon) || "consumo no verificable"),
        tarjetaEstado("Groq", buscarServicio("n8n") === "activo" ? "no verificado" : "no verificado", "Configurado detrás de n8n; falta salud directa"));

    const rutas = NexusLogic.usoPorRuta(datos.info || {});
    $("#tabla-rutas").replaceChildren(rutas.length ? el("table", {},
        el("tr", {}, el("th", {}, "Ruta"), el("th", {}, "Consultas hoy")),
        rutas.map(x => el("tr", {}, el("td", {}, x.ruta), el("td", { class: "num" }, numero(x.cantidad)))))
        : el("p", { class: "tenue" }, "Sin conteos disponibles. Esto no significa consumo cero."));

    const rutasComparables = ["codex", "claude", "web", "gpt"];
    $("#tabla-modelos").replaceChildren(el("table", { class: "tabla-ancha" },
        el("tr", {}, el("th", {}, "Ruta"), el("th", {}, "Foco"), el("th", {}, "Datos"), el("th", {}, "Estado")),
        rutasComparables.map(ruta => {
            const meta = NexusLogic.RUTAS[ruta];
            const p = NexusLogic.perfil(datos.info || {}, $("#perfil").value);
            const s = NexusLogic.disponible(p, ruta);
            return el("tr", {}, el("td", {}, el("strong", {}, meta.nombre)), el("td", {}, meta.foco),
                el("td", {}, meta.salida), el("td", {}, el("span", { class: `estado-pill ${s.estado}` }, s.estado.replace("_", " "))));
        })));
}

function pintarFuentes() {
    const descripciones = {
        bots: "Perfiles, rutas autorizadas, estado de servicios y conteos diarios.",
        estado: "Salud del nodo, servicios y contenedores; se arma cada cinco minutos.",
        uso: "Consumo local observado de Claude; Codex permanece no verificado.",
    };
    $("#fuentes").replaceChildren(...Object.entries(datos.fuentes).map(([id, f]) =>
        el("article", { class: "tarjeta mini-tarjeta" },
            el("div", { class: "mini-titulo" }, el("h2", {}, f.nombre),
                el("span", { class: `estado ${f.ok ? "ok" : "mal"}` }, f.ok ? "disponible" : "sin datos")),
            el("p", {}, descripciones[id]),
            el("p", { class: "tenue recorte" }, f.detalle))));
}

function pintarTodo() {
    pintarRecomendacion();
    pintarEstado();
    pintarFuentes();
}

function mostrar(panel) {
    panelActual = panel;
    document.querySelectorAll("#pestanas button").forEach(b => b.classList.toggle("activa", b.dataset.p === panel));
    document.querySelectorAll("[data-panel]").forEach(s => { s.hidden = s.dataset.panel !== panel; });
}

document.querySelectorAll("#pestanas button").forEach(b => b.addEventListener("click", () => mostrar(b.dataset.p)));
["perfil", "tarea", "prioridad", "datos"].forEach(id => $("#" + id).addEventListener("change", pintarTodo));
$("#actualizar").addEventListener("click", cargar);
document.addEventListener("visibilitychange", () => { if (!document.hidden) cargar(); });
window.addEventListener("storage", aplicarTema);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", aplicarTema);
aplicarTema();
cargar();
setInterval(cargar, ACTUALIZAR_CADA_MS);
