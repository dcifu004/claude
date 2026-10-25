/*
 * Herramienta "📰 Noticias" de Cockpit (separada de 🍇 Raspberry Pi el 25-09-2026, para
 * trabajar sobre ella con gráficos).
 *
 * Canónico en el vault (10-Proyectos/11-Pi5/pi/cockpit-noticias/); se instala copiando la
 * carpeta a ~/.local/share/cockpit/noticias. Habla SÓLO con `noticias-cockpit` (corre como
 * dcifu004, sin root). Votar = marcar [x] en la entrega del vault, el mismo canal que
 * Obsidian y que lee votos_previos() en 13-Agente-Noticias/pi/seleccion.py.
 *
 * Pestañas: 🗞️ Portada (estilo Ground News: quién cubre cada historia), 📊 Gráficos,
 * 🏷️ Medios (clasificar y marcar preferencia → _medios.json y _preferencias.md) y 🗳️ Entregas.
 * «Ordenar con mis preferencias» es una SIMULACIÓN: seleccion.py todavía no usa las
 * preferencias (decisión del 25-09: primero juntar y ver).
 * 📌 Seguimientos (27-09): historias temporales que se siguen mientras duren; franja arriba
 * de la Portada, filtro por hilo y «📌 Seguir» en cada tarjeta. Ver su sección más abajo.
 */
"use strict";

const $ = sel => document.querySelector(sel);
const CMD = "/usr/local/bin/noticias-cockpit";

/* ---------- utilidades ---------- */

// `el()` está en ../comun/dom.js y el tema lo aplica ../comun/tema.js (encargo 18).

const SVGNS = "http://www.w3.org/2000/svg";
function sv(tag, attrs = {}, ...hijos) {
    const e = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === "fill") e.style.fill = v;          // CSSOM: la CSP de Cockpit bloquea style="…"
        else if (k === "class") e.setAttribute("class", v);
        else if (v != null) e.setAttribute(k, v);
    }
    for (const h of hijos.flat()) {
        if (h == null || h === false) continue;
        e.append(h instanceof Node ? h : document.createTextNode(String(h)));
    }
    return e;
}

function error(msg) {
    $("#error").hidden = !msg;
    $("#error").textContent = msg || "";
}

const coma = (x, d = 1) => Number(x).toFixed(d).replace(".", ",");
const miles = n => Number(n).toLocaleString("es-CL");
const pct = (a, b) => b ? `${Math.round(100 * a / b)} %` : "—";

function cuando(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function hace(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const min = Math.round((Date.now() - d) / 60000);
    if (min < 1) return "recién";
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;
}

async function correr(args, opciones = {}) {
    return cockpit.spawn(args, { err: "message", ...opciones });
}
// Cada respuesta de noticias-cockpit pone al día el «leído hace X» de la barra compartida.
const pedir = async (...args) => {
    const d = JSON.parse(await correr([CMD, ...args]));
    barraNodo.leido();
    return d;
};

function filas(pares) {
    return el("dl", { class: "dato" }, pares.filter(Boolean).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
}

function segmento(opciones, actual, alCambiar) {
    const cont = el("div", { class: "segmento", role: "group" });
    for (const o of opciones) {
        const b = el("button", { class: o.v === actual ? "activo" : "", disabled: !!o.off, title: o.titulo || null }, o.t);
        b.addEventListener("click", () => {
            cont.querySelectorAll("button").forEach(x => x.classList.toggle("activo", x === b));
            alCambiar(o.v);
        });
        cont.append(b);
    }
    return cont;
}

/* tooltip único (#tip), posicionado por CSSOM */
const tip = {
    mostrar(ev, contenido) {
        const t = $("#tip");
        t.replaceChildren(...[].concat(contenido).map(x => x instanceof Node ? x : el("div", {}, x)));
        t.hidden = false;
        this.mover(ev);
    },
    mover(ev) {
        const t = $("#tip");
        const x = Math.min(ev.clientX + 14, window.innerWidth - t.offsetWidth - 8);
        const y = ev.clientY + 16 + t.offsetHeight > window.innerHeight ? ev.clientY - t.offsetHeight - 10 : ev.clientY + 16;
        t.style.left = `${Math.max(8, x)}px`;
        t.style.top = `${y}px`;
    },
    ocultar() { $("#tip").hidden = true; },
};
function conTip(nodo, contenido) {
    nodo.addEventListener("mouseenter", ev => tip.mostrar(ev, typeof contenido === "function" ? contenido() : contenido));
    nodo.addEventListener("mousemove", ev => tip.mover(ev));
    nodo.addEventListener("mouseleave", () => tip.ocultar());
    return nodo;
}

/* ---------- vocabulario ---------- */

const EVENTOS = {
    plata: "💰 Financiamiento", "inicio-avance": "🏗️ Inicio o avance", conflicto: "⚔️ Conflicto",
    emergencia: "🚨 Emergencia", problema: "⚠️ Problema", ceremonia: "🎗️ Ceremonia",
    accidente: "💥 Accidente", institucional: "🏛️ Institucional", decision: "⚖️ Decisión",
    planificacion: "🗺️ Planificación", proyecto: "📐 Proyecto", otro: "Sin evento reconocido",
};
const TEMAS = {
    general: "General", inversion: "💹 Inversión", obras: "🏗️ Obras", tecnologia: "💻 Tecnología",
    emergencia: "🚨 Emergencia", "obras-ext": "🌍 Obras (extranjero)", "emergencia-ext": "🌍 Emergencia (extranjero)",
};
const REGIONES = { CL: "Chile (nacional)", EXT: "Extranjero", LATAM: "Latinoamérica" };
/* la cosecha a veces trae el código ISO en vez del nombre (CL-LL junto a «Los Lagos»): se unifican acá */
const ISO_REGION = {
    "CL-AP": "Arica y Parinacota", "CL-TA": "Tarapacá", "CL-AN": "Antofagasta", "CL-AT": "Atacama",
    "CL-CO": "Coquimbo", "CL-VS": "Valparaíso", "CL-RM": "Metropolitana", "CL-LI": "O'Higgins",
    "CL-ML": "Maule", "CL-NB": "Ñuble", "CL-BI": "Biobío", "CL-AR": "Araucanía", "CL-LR": "Los Ríos",
    "CL-LL": "Los Lagos", "CL-AI": "Aysén", "CL-MA": "Magallanes",
};
const normRegion = k => ISO_REGION[k] || k;
const evento = k => EVENTOS[k] || k || "—";
const tema = k => TEMAS[k] || k || "—";
const region = k => REGIONES[k] || k || "sin región";

/* Colores por dimensión. Tipo = categórica (orden fijo); tendencia = divergente azul↔rojo
   con gris al medio; alcance y audiencia = secuencial de un solo tono. */
const DIMS = {
    tipo: { t: "Tipo", valores: ["nacional", "regional", "internacional", "oficial", "especializado", "agregador"],
            colores: ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"] },
    tendencia: { t: "Tendencia", valores: ["izquierda", "centro-izquierda", "centro", "centro-derecha", "derecha"],
                 colores: ["--div-izq", "--div-cizq", "--div-centro", "--div-cder", "--div-der"] },
    alcance: { t: "Alcance", valores: ["local", "regional", "nacional", "internacional"],
               colores: ["--ord-1", "--ord-2", "--ord-3", "--ord-4"] },
    audiencia: { t: "Audiencia", valores: ["baja", "media", "alta"], colores: ["--ord-1", "--ord-3", "--ord-4"] },
};
function colorDe(dim, valor) {
    const d = DIMS[dim];
    const i = d.valores.indexOf(valor);
    return i < 0 ? null : `var(${d.colores[i]})`;
}
function leyenda(dim, extra = true) {
    const d = DIMS[dim];
    const items = d.valores.map(v => el("span", {}, muestra(colorDe(dim, v)), v));
    if (extra) items.push(el("span", {}, muestra(null), "sin clasificar"));
    return el("div", { class: "leyenda" }, items);
}
function muestra(color) {
    const i = el("i", { class: color ? "" : "sin-clasificar" });
    if (color) i.style.background = color;
    return i;
}

/* ---------- pestañas ---------- */

const pintores = { portada: pintarPortada, graficos: pintarGraficos, medios: pintarMedios, entregas: pintarEntregas };
const pintadas = new Set();
let pestanaActual = "portada";

function irA(p) {
    pestanaActual = p;
    document.querySelectorAll("#pestanas button").forEach(b => b.classList.toggle("activa", b.dataset.p === p));
    document.querySelectorAll("[data-panel]").forEach(s => { s.hidden = s.dataset.panel !== p; });
    error("");
    if (!pintadas.has(p)) {
        pintadas.add(p);
        pintores[p]().catch(e => { pintadas.delete(p); error(e.message || String(e)); });
    }
}
document.querySelectorAll("#pestanas button").forEach(b => b.addEventListener("click", () => irA(b.dataset.p)));

function cargando(panel, texto = "Cargando…") {
    $(`[data-panel=${panel}]`).replaceChildren(el("p", { class: "tenue" }, texto));
}

/* ---------- 🗞️ Portada ---------- */

const portada = {
    horas: 48, dim: "tipo", tema: "", evento: "", region: "", texto: "", orden: "cobertura",
    varios: false, ciegos: false, simular: false, mostrar: 60, datos: null,
    hilo: "", primero: true,
};
const seg = { datos: null };   // 📌 seguimientos: ver la sección de más abajo

async function cargarHistorias() {
    cargando("portada", `Juntando las historias de las últimas ${portada.horas} h…`);
    [portada.datos, seg.datos] = await Promise.all([
        pedir("historias", String(portada.horas)), pedir("seguimientos")]);
    for (const h of portada.datos.historias) h.region = h.region ? normRegion(h.region) : null;
    portada.mostrar = 60;
}

async function pintarPortada() {
    if (!portada.datos || portada.datos.horas !== portada.horas) await cargarHistorias();
    const cont = $("[data-panel=portada]");
    const d = portada.datos;
    const H = d.hilos || {};
    if (portada.hilo && !H[portada.hilo]) portada.hilo = "";
    const contrato = new Set(d.regiones_con_contrato || []);
    const M = d.medios || {};

    const cuenta = campo => {
        const c = {};
        for (const h of d.historias) c[h[campo] || ""] = (c[h[campo] || ""] || 0) + 1;
        return Object.entries(c).sort((a, b) => b[1] - a[1]);
    };
    const selector = (etq, campo, nombre, extras = []) => {
        const s = el("select", { "aria-label": etq },
            el("option", { value: "" }, `${etq}: todos`), extras,
            cuenta(campo).filter(([k]) => k).map(([k, n]) =>
                el("option", { value: k, selected: portada[campo] === k }, `${nombre(k)} (${n})`)));
        s.value = portada[campo];
        s.addEventListener("change", () => { portada[campo] = s.value; portada.mostrar = 60; pintarLista(); });
        return s;
    };
    const casilla = (campo, texto, titulo) => {
        const c = el("input", { type: "checkbox", checked: portada[campo] });
        c.addEventListener("change", () => { portada[campo] = c.checked; portada.mostrar = 60; pintarLista(); });
        return el("label", { title: titulo || null }, c, texto);
    };
    const buscar = el("input", { type: "search", placeholder: "Buscar en títulos…", value: portada.texto });
    buscar.addEventListener("input", () => { portada.texto = buscar.value; portada.mostrar = 60; pintarLista(); });

    const selRegion = selector("Región", "region", k => (contrato.has(k) ? "📌 " : "") + region(k),
        [el("option", { value: "@contrato", selected: portada.region === "@contrato" }, "📌 Sólo regiones con contrato"),
         el("option", { value: "@sin", selected: portada.region === "@sin" }, "Sin región")]);

    const selHilo = el("select", { "aria-label": "Seguimiento" },
        el("option", { value: "" }, "📌 Hilo: todos"),
        Object.entries(H).map(([k, n]) => el("option", { value: k, selected: portada.hilo === k },
            `📌 ${n} (${d.historias.filter(h => h.hilos?.includes(k)).length})`)));
    selHilo.value = portada.hilo;
    selHilo.addEventListener("change", () => { portada.hilo = selHilo.value; portada.mostrar = 60; pintarLista(); });

    const lista = el("div");
    cont.replaceChildren(
        franjaSeguimientos(k => { portada.hilo = k; selHilo.value = k; portada.mostrar = 60; pintarLista(); }),
        el("div", { class: "tarjeta" },
            el("div", { class: "controles" },
                segmento([{ v: 24, t: "24 h" }, { v: 48, t: "48 h" }, { v: 168, t: "7 días" }], portada.horas, async v => {
                    portada.horas = v;
                    try { await cargarHistorias(); await pintarPortada(); } catch (e) { error(e.message || String(e)); }
                }),
                el("span", { class: "tenue" }, "Barra de cobertura por:"),
                segmento([...Object.entries(DIMS).map(([v, x]) => ({ v, t: x.t })),
                          { v: "tonalidad", t: "Tonalidad 🚧", off: true,
                            titulo: "En construcción: un léxico determinista que lea si el titular es positivo, neutro o negativo." }],
                         portada.dim, v => { portada.dim = v; pintarLista(); }),
                segmento([{ v: "cobertura", t: "Más cubiertas" }, { v: "recientes", t: "Más recientes" }],
                         portada.orden, v => { portada.orden = v; pintarLista(); })),
            el("div", { class: "controles" },
                buscar, Object.keys(H).length ? selHilo : null,
                selector("Tema", "tema", tema), selector("Evento", "evento", evento), selRegion),
            el("div", { class: "controles" },
                Object.keys(H).length ? casilla("primero", "📌 Primero lo que sigo",
                    "Las historias de tus seguimientos activos suben al principio, conservando el orden elegido entre ellas.") : null,
                casilla("varios", "Sólo con 2 o más medios"),
                casilla("ciegos", "🕳 Sólo puntos ciegos",
                        "Historias con 2 o más medios clasificados en la dimensión elegida, todos del mismo valor."),
                casilla("simular", "⭐ Ordenar con mis preferencias (simulación)",
                        "No cambia lo que elige el agente: muestra cómo quedaría la portada si tus ⭐ y 🚫 pesaran."))),
        lista);

    function pasa(h) {
        if (portada.hilo && !h.hilos?.includes(portada.hilo)) return false;
        if (portada.tema && h.tema !== portada.tema) return false;
        if (portada.evento && h.evento !== portada.evento) return false;
        if (portada.region === "@contrato" ? !contrato.has(h.region)
            : portada.region === "@sin" ? h.region
            : portada.region && h.region !== portada.region) return false;
        if (portada.varios && h.medios.length < 2) return false;
        if (portada.ciegos && !puntoCiego(h)) return false;
        if (portada.texto && !h.titulo.toLowerCase().includes(portada.texto.toLowerCase())) return false;
        return true;
    }
    function puntoCiego(h) {
        const vals = h.medios.map(k => M[k]?.[portada.dim]).filter(Boolean);
        return vals.length >= 2 && new Set(vals).size === 1 ? vals[0] : null;
    }
    function puntaje(h) {
        const fav = h.medios.filter(k => M[k]?.preferencia === "favorito").length;
        const evi = h.medios.filter(k => M[k]?.preferencia === "evitar").length;
        return { n: h.medios.length + 3 * fav - 3 * evi + (contrato.has(h.region) ? 1 : 0), fav, evi };
    }
    const sigo = h => portada.primero && h.hilos?.length ? 1 : 0;
    const base = (a, b) => sigo(b) - sigo(a) || (portada.orden === "cobertura"
        ? b.medios.length - a.medios.length || (b.visto < a.visto ? -1 : 1)
        : (b.visto < a.visto ? -1 : 1));

    function pintarLista() {
        const todas = d.historias;
        const vistas = todas.filter(pasa).sort(base);
        const puesto = new Map(vistas.map((h, i) => [h.hash, i]));
        if (portada.simular) vistas.sort((a, b) => puntaje(b).n - puntaje(a).n || base(a, b));

        const conVarios = todas.filter(h => h.medios.length > 1).length;
        const sinRegion = todas.filter(h => !h.region).length;
        const claves = new Set(todas.flatMap(h => h.medios));
        const sinDim = [...claves].filter(k => !M[k]?.[portada.dim]).length;
        const cifra = (n, t) => el("div", { class: "cifra" }, el("div", { class: "n" }, n), el("div", { class: "t" }, t));

        lista.replaceChildren(
            el("div", { class: "tarjeta" },
                el("div", { class: "cifras" },
                    cifra(miles(vistas.length), vistas.length === todas.length ? "historias" : `de ${miles(todas.length)} historias`),
                    cifra(pct(conVarios, todas.length), "con 2 o más medios"),
                    cifra(miles(todas.filter(puntoCiego).length), `🕳 puntos ciegos (${DIMS[portada.dim].t.toLowerCase()})`),
                    cifra(miles(todas.filter(h => h.elegida).length), "elegidas por el agente"),
                    cifra(miles(todas.filter(h => h.marcada).length), "marcadas por ti"),
                    cifra(`${miles(claves.size - sinDim)} / ${miles(claves.size)}`, `medios con ${DIMS[portada.dim].t.toLowerCase()}`)),
                sinDim > claves.size / 2 ? el("p", { class: "tenue" },
                    `La barra de cobertura se ve gris porque ${miles(sinDim)} de ${miles(claves.size)} medios no tienen `,
                    `${DIMS[portada.dim].t.toLowerCase()}. `,
                    el("a", { href: "#", onclick: ev => { ev.preventDefault(); irA("medios"); } }, "Clasifícalos en 🏷️ Medios"),
                    ` (${pct(sinRegion, todas.length)} de las historias tampoco trae región).`) : null,
                leyenda(portada.dim)),
            vistas.length ? el("div", { class: "historias" },
                vistas.slice(0, portada.mostrar).map((h, i) => tarjetaHistoria(h, i, puesto))) :
                el("p", { class: "tenue" }, "Nada con esos filtros."),
            vistas.length > portada.mostrar ? el("p", {}, el("button", {
                onclick: () => { portada.mostrar += 60; pintarLista(); },
            }, `Mostrar 60 más (quedan ${miles(vistas.length - portada.mostrar)})`)) : null);
    }

    function tarjetaHistoria(h, i, puesto) {
        const ciego = puntoCiego(h);
        const orden = h.medios.slice().sort((a, b) => {
            const ia = DIMS[portada.dim].valores.indexOf(M[a]?.[portada.dim] ?? "");
            const ib = DIMS[portada.dim].valores.indexOf(M[b]?.[portada.dim] ?? "");
            return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
        });
        const barra = el("div", { class: "cobertura", "aria-label": `cubierta por ${h.medios.length} medio(s)` },
            orden.map(k => {
                const s = el("span", { class: colorDe(portada.dim, M[k]?.[portada.dim]) ? "" : "sin-clasificar" });
                const c = colorDe(portada.dim, M[k]?.[portada.dim]);
                if (c) s.style.background = c;
                s.style.flex = "1";
                return s;
            }));
        conTip(barra, () => [el("strong", {}, `${h.medios.length} medio(s)`),
            ...orden.map(k => `${M[k]?.nombre || k} — ${M[k]?.[portada.dim] || "sin clasificar"}`)]);

        let mueve = null;
        const p = puntaje(h);
        if (portada.simular) {
            const antes = puesto.get(h.hash);
            if (antes > i) mueve = el("span", { class: "sube", title: `subió desde el puesto ${antes + 1}` }, `▲${antes - i}`);
            else if (antes < i) mueve = el("span", { class: "baja", title: `bajó desde el puesto ${antes + 1}` }, `▼${i - antes}`);
        }
        return el("article", { class: "historia" + (h.elegida ? " elegida" : "") },
            el("div", { class: "meta" },
                (h.hilos || []).map(k => el("button", {
                    class: "chip hilo", title: `Ver sólo «${H[k]}»`,
                    onclick: () => { portada.hilo = k; selHilo.value = k; portada.mostrar = 60; pintarLista(); window.scrollTo(0, 0); },
                }, `📌 ${H[k]}`)),
                h.evento && h.evento !== "otro" ? el("span", { class: "chip" }, evento(h.evento)) : null,
                h.tema && h.tema !== "general" ? el("span", { class: "chip" }, tema(h.tema)) : null,
                h.region ? el("span", {}, (contrato.has(h.region) ? "📌 " : "") + region(h.region)) : null,
                el("span", {}, hace(h.visto)), mueve),
            el("h3", {}, el("a", { href: h.url, target: "_blank", rel: "noopener" }, h.titulo)),
            barra,
            el("div", { class: "medios" },
                orden.slice(0, 6).flatMap((k, j) => [j ? " · " : "",
                    M[k]?.preferencia === "favorito" ? "⭐" : M[k]?.preferencia === "evitar" ? "🚫" : "",
                    M[k]?.nombre || k]),
                orden.length > 6 ? ` y ${orden.length - 6} más` : ""),
            el("div", { class: "meta" },
                h.elegida ? el("span", { class: "insignia agente" }, "✔ elegida por el agente") : null,
                h.marcada ? el("span", { class: "insignia" }, "🗳 marcada") : null,
                ciego ? el("span", { class: "insignia ciego" }, `🕳 punto ciego: sólo ${ciego}`) : null,
                portada.simular && (p.fav || p.evi) ? el("span", { class: "insignia" },
                    [p.fav ? `⭐×${p.fav}` : "", p.evi ? `🚫×${p.evi}` : ""].filter(Boolean).join(" ")) : null),
            el("div", { class: "acciones-historia" },
                el("button", { class: "mini", title: "Seguir esta historia en el tiempo, o sumarla a un seguimiento que ya tienes",
                               onclick: () => abrirEditor({ titulo: h.titulo }) }, "📌 Seguir"),
                el("button", { class: "mini", title: "Esta noticia está mal etiquetada (región, país, evento, tema). Queda anotado en _errores.md como caso de prueba.",
                               onclick: () => abrirReporte(h) }, "🚩 Está mal"),
                (h.hilos || []).map(k => el("button", {
                    class: "mini", title: `Sacar esta noticia de «${H[k]}». Queda anotado en _seguimientos.md y se puede deshacer ahí.`,
                    onclick: async ev => {
                        ev.target.disabled = true;
                        try {
                            await pedir("seguimiento", k, "fuera", h.hash);
                            h.hilos = h.hilos.filter(x => x !== k);
                            seg.datos = await pedir("seguimientos");
                            await pintarPortada();
                        } catch (e) { error(e.message || String(e)); ev.target.disabled = false; }
                    },
                }, `✂️ No es de «${H[k]}»`))));
    }

    pintarLista();
}

/* ---------- 📌 Seguimientos (27-09-2026) ----------
 * Historias TEMPORALES que se siguen mientras duren (Ucrania, Ormuz, acuerdos de IA). No son
 * temas. Viven en 13-Agente-Noticias/_seguimientos.md, que la página escribe en nombre de
 * Diego. Lo temporal lo decide el mundo: un hilo se duerme solo tras 21 días sin noticias y
 * se despierta solo si vuelve. No marcar nada nunca baja ni apaga nada; cerrar es lo único
 * manual. Etapa 1: sólo la Portada — seleccion.py todavía no los usa.
 */

const STOP_JS = new Set(("a al algo ante antes asi aun bajo como con contra cual cuando de del desde donde dos durante el " +
    "ella ellas ellos en entre era es esa ese eso esta este esto estos fue han hasta hay la las le les lo los mas me " +
    "mientras muy ni no nos o otra otro para pero por porque que quien se segun ser si sin sobre su sus tambien tiene " +
    "tras tres un una uno unos y ya the of to and in for on with is at by from as its after over new says said will be " +
    "are was dice hoy ayer chile anos ano dia dias parte menos cinco cuatro seis siete ocho nueve diez mil " +
    "millones miles cientos primer primera segundo nuevo nueva nuevos gran grandes solo todo todos").split(" "));
const normTxt = t => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, " ").trim();
const palabrasDe = t => [...new Set(normTxt(t).split(" "))].filter(w => w.length > 2 && !STOP_JS.has(w) && !/^\d+$/.test(w));

function chispa(por_dia, ancho = 98, alto = 24) {
    const max = Math.max(1, ...por_dia.map(x => x.n));
    const w = ancho / por_dia.length;
    const g = sv("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, class: "chispa", role: "img",
                          "aria-label": `noticias por día, últimos ${por_dia.length} días` });
    por_dia.forEach((x, i) => {
        const h = x.n ? Math.max(2, (alto - 2) * x.n / max) : 1;
        const r = sv("rect", { x: i * w + 0.5, y: alto - h, width: Math.max(1, w - 1.5), height: h, rx: 1,
                               class: x.n ? "barra-chispa" : "barra-chispa cero" });
        r.append(sv("title", {}, `${x.dia}: ${x.n}`));
        g.append(r);
    });
    return g;
}

function franjaSeguimientos(verHilo) {
    const L = seg.datos?.lista || [];
    const activos = L.filter(s => s.estado_calc === "activo").sort((a, b) => b.n48 - a.n48 || b.n14 - a.n14);
    const dormidos = L.filter(s => s.estado_calc === "dormido");
    const cerrados = L.filter(s => s.estado_calc === "cerrado");
    const fila = s => el("div", { class: "hilo-fila" + (s.estado_calc !== "activo" ? " apagado" : "") },
        el("div", { class: "hilo-nombre" },
            s.estado_calc === "cerrado" ? el("strong", {}, s.nombre)
                : el("button", { class: "enlace", title: "Ver sólo este hilo en la Portada", onclick: () => verHilo(s.id) },
                     el("strong", {}, s.nombre)),
            el("span", { class: "tenue num" }, ` ${s.n48} en 48 h · ${s.n14} en 14 días`),
            s.estado_calc === "dormido" ? el("span", { class: "insignia" }, "💤 dormido") : null,
            s.estado_calc === "cerrado" ? el("span", { class: "insignia" }, "cerrado") : null),
        chispa(s.por_dia),
        el("div", { class: "hilo-ultimo tenue" },
            s.ultimo ? [el("a", { href: s.ultimo.url, target: "_blank", rel: "noopener" }, s.ultimo.titulo), ` · ${hace(s.ultimo.visto)}`]
                     : `sin noticias en ${seg.datos.dormir_dias} días`),
        el("div", { class: "hilo-acciones" },
            el("button", { class: "mini", onclick: () => abrirEditor({ hilo: s }) }, "✏️ Afinar"),
            el("button", {
                class: "mini",
                title: s.estado === "cerrado" ? "Volver a seguirlo" : "Dejar de seguirlo. Se conserva en _seguimientos.md y se puede reabrir.",
                onclick: async ev => {
                    ev.target.disabled = true;
                    try {
                        await pedir("seguimiento", s.id, "estado", s.estado === "cerrado" ? "activo" : "cerrado");
                        await cargarHistorias(); await pintarPortada();
                    } catch (e) { error(e.message || String(e)); ev.target.disabled = false; }
                },
            }, s.estado === "cerrado" ? "↺ Reabrir" : "Cerrar")));

    return el("div", { class: "tarjeta franja" },
        el("div", { class: "fila" },
            el("h2", {}, "📌 En seguimiento"),
            el("span", { class: "tenue" }, L.length
                ? "Historias que sigues mientras duren. Se duermen solas cuando el mundo deja de hablar de ellas, y despiertan solas."
                : "Todavía nada. Toca «📌 Seguir» en cualquier noticia para seguir esa historia en el tiempo — la guerra de Ucrania, el estrecho de Ormuz, los acuerdos de IA.")),
        activos.map(fila),
        dormidos.length ? el("details", {}, el("summary", { class: "tenue" }, `💤 Dormidos (${dormidos.length})`), dormidos.map(fila)) : null,
        cerrados.length ? el("details", {}, el("summary", { class: "tenue" }, `Cerrados (${cerrados.length})`), cerrados.map(fila)) : null);
}

/* Editor: crear un hilo desde una noticia, sumar esa noticia a uno existente («más como esta»)
   o afinar uno. Cada fila de términos = alternativas (basta una); todas las filas deben calzar. */
/* ---------- 🚩 Reportar un error de etiquetado (28-09-2026) ----------
 *
 * Nace de una etiqueta `📌 Araucanía` sobre una noticia de Milei: `elperiodico` es un diario
 * de la Araucanía y la región se heredaba del feed sin mirar el texto. No era un fallo de esa
 * noticia sino de la regla, y tocaba 545 ítems.
 *
 * Dos decisiones que sostienen el canal:
 *  - ACÁ SÓLO VA LO QUE TIENE RESPUESTA CORRECTA. «No me sirve» es preferencia y ya tiene su
 *    canal —marcar `[x]` en la entrega—. Mezclarlos arruina los dos: el conteo de errores se
 *    infla con gustos y la preferencia se diluye con reclamos.
 *  - POR ESO `correcto` ES OBLIGATORIO. Sin respuesta correcta un reporte no se puede volver a
 *    probar, y un reporte que no se puede probar es una queja que nadie va a cerrar nunca.
 */
const TIPOS_ERROR = {
    region: { t: "Región equivocada", ayuda: "La noticia no es de esa región.",
              op: h => ["ninguna", ...(h.region ? [] : [])] },
    pais: { t: "País equivocado", ayuda: "Chilena marcada como extranjera, o al revés.",
            op: () => ["CL", "EXT", "?"] },
    evento: { t: "Evento mal clasificado", ayuda: "El hecho no es ése.",
              op: () => ["otro", "problema", "inicio-avance", "decision", "accidente",
                         "emergencia", "planificacion", "gestion", "plata", "conflicto"] },
    tema: { t: "Tema equivocado", ayuda: "", op: () => ["general", "obras", "emergencia",
            "tecnologia", "economia", "geopolitica", "empleo"] },
    "no-noticia": { t: "No es noticia", ayuda: "Aviso de empleo, publirreportaje, panorama.",
                    op: () => ["descartar"] },
    basura: { t: "Título cortado o con URL pegada", ayuda: "Típico de los toots de Mastodon.",
              op: () => ["descartar"] },
};

function abrirReporte(h) {
    const dlg = el("dialog", { class: "editor" });
    const cerrar = () => { dlg.close(); dlg.remove(); };
    dlg.addEventListener("cancel", ev => { ev.preventDefault(); cerrar(); });
    document.body.append(dlg);

    let tipo = h.region ? "region" : "evento";
    let correcto = "";
    const cuerpo = el("div");
    const nota = el("input", { type: "text", placeholder: "Qué está mal, en una línea (opcional)" });

    function pintar() {
        const spec = TIPOS_ERROR[tipo];
        const ops = spec.op(h);
        if (!ops.includes(correcto)) correcto = ops[0] || "";
        cuerpo.replaceChildren(
            el("p", { class: "tenue" }, h.titulo),
            filas([["Dice ahora", [h.region ? `región ${region(h.region)}` : "sin región",
                                   h.evento ? `evento ${evento(h.evento)}` : null,
                                   h.tema ? `tema ${tema(h.tema)}` : null].filter(Boolean).join(" · ")]]),
            el("label", {}, "Qué salió mal"),
            segmento(Object.entries(TIPOS_ERROR).map(([k, v]) => [k, v.t]), tipo,
                     k => { tipo = k; pintar(); }),
            spec.ayuda ? el("p", { class: "tenue" }, spec.ayuda) : null,
            el("label", {}, "Lo correcto es"),
            segmento(ops.map(o => [o, o]), correcto, o => { correcto = o; pintar(); }),
            nota);
    }

    const enviar = el("button", {
        onclick: async () => {
            enviar.disabled = true;
            try {
                await pedir("reportar", JSON.stringify(
                    { hash: h.hash, tipo, correcto, nota: nota.value.trim() }));
                cerrar();
            } catch (err) {
                cuerpo.prepend(el("p", { class: "aviso rojo" }, err.message || String(err)));
                enviar.disabled = false;
            }
        },
    }, "Reportar");

    dlg.append(
        el("h2", {}, "🚩 Reportar un error"),
        cuerpo,
        el("div", { class: "fila pie" }, enviar,
           el("button", { class: "secundario", onclick: cerrar }, "Cancelar"),
           el("span", { class: "tenue" }, "Se guarda en ", el("code", {}, "_errores.md"),
              ". Si la noticia está bien clasificada y sólo no te sirve, no la reportes: "
              + "eso se dice dejándola sin marcar en la entrega.")));
    pintar();
    dlg.showModal();
}

function abrirEditor({ titulo = null, hilo = null }) {
    const L = (seg.datos?.lista || []).filter(s => s.estado !== "cerrado");
    const nuevo = () => ({ id: null, nombre: "", terminos: [[]], excluir: [], bajada: true, sugeridas: [] });
    const copia = s => ({ id: s.id, nombre: s.nombre, terminos: s.terminos.map(g => [...g]), excluir: [...s.excluir],
                          bajada: s.bajada !== false, sugeridas: s.sugeridas || [] });
    let e = hilo ? copia(hilo) : nuevo();
    let fila = 0;                 // a qué fila van las palabras que se tocan
    let temporizador = null;

    const dlg = el("dialog", { class: "editor" });
    const cerrar = () => { dlg.close(); dlg.remove(); };
    dlg.addEventListener("cancel", ev => { ev.preventDefault(); cerrar(); });
    const vista = el("div", { class: "vista-previa" });
    const cuerpo = el("div");
    document.body.append(dlg);

    let foco = null;              // qué casilla recupera el cursor después de repintar
    function agregar(w, dest = "terminos", desdeTeclado = false) {
        w = w.trim().toLowerCase();
        if (!w) return;
        if (dest === "excluir") { if (!e.excluir.includes(w)) e.excluir.push(w); }
        else if (!e.terminos[fila].includes(w)) e.terminos[fila].push(w);
        foco = desdeTeclado ? (dest === "excluir" ? "x" : `t${fila}`) : null;
        pintar(); previsualizar();
    }
    const chipTermino = (w, quitar) => el("span", { class: "termino" }, w,
        el("button", { class: "quitar", title: "Quitar", onclick: () => { quitar(); pintar(); previsualizar(); } }, "×"));
    const entrada = (ph, dest, clave) => {
        const i = el("input", { type: "text", placeholder: ph, class: "entrada-termino", "data-foco": clave });
        i.addEventListener("keydown", ev => { if (ev.key === "Enter") { ev.preventDefault(); agregar(i.value, dest, true); } });
        i.addEventListener("focus", () => { if (dest === "terminos") fila = Number(clave.slice(1)); });
        return i;
    };

    function pintar() {
        const ya = new Set([...e.terminos.flat(), ...e.excluir].map(t => t.replace(/\*$/, "")));
        const propuestas = [...new Set([...(titulo ? palabrasDe(titulo) : []), ...(e.sugeridas || [])])].filter(w => !ya.has(w));
        // Dentro de el(): replaceChildren no aplana listas ni se salta los null.
        cuerpo.replaceChildren(el("div", {},
            titulo ? el("p", { class: "tenue" }, "Noticia: ", el("em", {}, titulo)) : null,
            titulo && !hilo && L.length ? el("label", { class: "fila" }, "Esta noticia va a:",
                (() => {
                    const s = el("select", {}, el("option", { value: "" }, "un seguimiento nuevo"),
                        L.map(x => el("option", { value: x.id, selected: e.id === x.id }, `sumarla a «${x.nombre}»`)));
                    s.value = e.id || "";
                    s.addEventListener("change", () => {
                        const x = L.find(y => y.id === s.value);
                        e = x ? copia(x) : nuevo(); fila = 0; pintar(); previsualizar();
                    });
                    return s;
                })()) : null,
            el("label", { class: "campo" }, "Nombre",
                (() => {
                    const i = el("input", { type: "text", value: e.nombre, maxlength: 60, placeholder: "p. ej. Estrecho de Ormuz" });
                    i.addEventListener("input", () => { e.nombre = i.value; guardar.disabled = !listo(); });
                    return i;
                })()),
            propuestas.length ? el("div", {},
                el("p", { class: "tenue" }, `Toca las palabras que definen la historia (van a la fila ${fila + 1}):`),
                el("div", { class: "propuestas" }, propuestas.slice(0, 24).map(w =>
                    el("button", { class: "mini", onclick: () => agregar(w) }, w)))) : null,
            el("p", { class: "tenue" }, "Cada fila: basta con una de sus palabras. Entre filas: tienen que estar todas. ",
               "Termina en ", el("code", {}, "*"), " para aceptar variantes (", el("code", {}, "ucrania*"), " → ucraniano)."),
            e.terminos.map((g, i) => el("div", { class: "grupo" + (i === fila ? " activo" : ""), onclick: ev => {
                    if (ev.target.closest("button, input")) return;
                    fila = i; pintar();
                } },
                el("span", { class: "grupo-etq" }, i === 0 ? "Alguna de:" : "y alguna de:"),
                g.map((w, j) => chipTermino(w, () => g.splice(j, 1))),
                entrada("agregar…", "terminos", `t${i}`),
                e.terminos.length > 1 ? el("button", { class: "mini", title: "Quitar esta fila",
                    onclick: () => { e.terminos.splice(i, 1); fila = 0; pintar(); previsualizar(); } }, "quitar fila") : null)),
            e.terminos.length < 4 ? el("button", { class: "mini", onclick: () => { e.terminos.push([]); fila = e.terminos.length - 1; pintar(); } },
                "+ Y además…") : null,
            el("div", { class: "grupo excluir" },
                el("span", { class: "grupo-etq" }, "Excluir si aparece:"),
                e.excluir.map((w, j) => chipTermino(w, () => e.excluir.splice(j, 1))),
                entrada("agregar…", "excluir", "x")),
            el("label", {}, (() => {
                const c = el("input", { type: "checkbox", checked: e.bajada });
                c.addEventListener("change", () => { e.bajada = c.checked; previsualizar(); });
                return c;
            })(), " Buscar también en la bajada (más alcance; si trae ruido, desmárcalo)")),
            vista);
        guardar.disabled = !listo();
        if (foco) { cuerpo.querySelector(`[data-foco="${foco}"]`)?.focus(); foco = null; }
    }
    const listo = () => e.nombre.trim() && e.terminos.some(g => g.length);
    const payload = () => ({ terminos: e.terminos.filter(g => g.length), excluir: e.excluir, bajada: e.bajada });

    function previsualizar() {
        clearTimeout(temporizador);
        if (!e.terminos.some(g => g.length)) { vista.replaceChildren(el("p", { class: "tenue" }, "Agrega al menos una palabra para ver qué juntaría.")); return; }
        vista.replaceChildren(el("p", { class: "tenue" }, "Midiendo…"));
        temporizador = setTimeout(async () => {
            try {
                const m = await pedir("previsualizar", JSON.stringify(payload()));
                vista.replaceChildren(el("div", {},
                    el("div", { class: "fila" },
                        el("strong", { class: "num" }, `${m.n48} en 48 h · ${m.n14} en 14 días`),
                        el("span", { class: "tenue" }, `(~${coma(m.promedio_dia)} al día)`), chispa(m.por_dia, 140, 28)),
                    m.amplio ? el("p", { class: "aviso ojo" }, "Muy amplio: esto se va a comer la portada. Agrega una fila «Y además…» o palabras a excluir.") : null,
                    !m.n14 ? el("p", { class: "aviso ojo" }, "No juntaría nada en 14 días. Revisa las palabras, o guárdalo igual: quedará 💤 dormido hasta que aparezca.") : null,
                    m.ejemplos.length ? el("ul", { class: "ejemplos" }, m.ejemplos.map(x =>
                        el("li", {}, el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.titulo), el("span", { class: "tenue" }, ` · ${hace(x.visto)}`)))) : null));
            } catch (err) { vista.replaceChildren(el("p", { class: "aviso rojo" }, err.message || String(err))); }
        }, 400);
    }

    const guardar = el("button", {
        onclick: async () => {
            guardar.disabled = true;
            try {
                const r = await pedir("seguir", JSON.stringify({ id: e.id, nombre: e.nombre.trim(), ...payload() }));
                cerrar();
                await cargarHistorias();
                portada.hilo = r.id;
                await pintarPortada();
                window.scrollTo(0, 0);
            } catch (err) { vista.prepend(el("p", { class: "aviso rojo" }, err.message || String(err))); guardar.disabled = false; }
        },
    }, "Guardar");
    dlg.append(
        el("h2", {}, hilo ? `✏️ Afinar «${hilo.nombre}»` : "📌 Seguir una historia"),
        cuerpo,
        el("div", { class: "fila pie" }, guardar, el("button", { class: "secundario", onclick: cerrar }, "Cancelar"),
           el("span", { class: "tenue" }, "Se guarda en ", el("code", {}, "_seguimientos.md"), "; también lo puedes editar en Obsidian.")));
    pintar();
    previsualizar();
    dlg.showModal();
}

/* ---------- 📊 Gráficos (SVG a mano: una escala, marcas finas, tooltip y tabla) ---------- */

function tablaDe(cabeza, filasT) {
    return el("details", {}, el("summary", { class: "tenue" }, "Ver tabla"),
        el("table", {}, el("thead", {}, el("tr", {}, cabeza.map(c => el("th", {}, c)))),
           el("tbody", {}, filasT.map(f => el("tr", {}, f.map(c => el("td", {}, c)))))));
}

/* barras verticales, una serie; datos = [{etq, n, tip}] */
function barrasV(datos, { alto = 170, color = "var(--s1)", W = 640 } = {}) {
    const H = alto, m = { i: 34, d: 8, a: 14, b: 22 };
    const max = Math.max(1, ...datos.map(x => x.n));
    const banda = (W - m.i - m.d) / Math.max(1, datos.length);
    const ancho = Math.max(4, Math.min(34, banda - 6));
    const y = n => m.a + (H - m.a - m.b) * (1 - n / max);
    const g = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" },
        sv("line", { class: "eje", x1: m.i, x2: W - m.d, y1: m.a, y2: m.a, "stroke-dasharray": "2 4" }),
        sv("text", { x: m.i - 6, y: m.a + 4, "text-anchor": "end" }, miles(max)),
        sv("line", { class: "eje", x1: m.i, x2: W - m.d, y1: H - m.b, y2: H - m.b }));
    datos.forEach((x, i) => {
        const cx = m.i + banda * i + banda / 2;
        const r = sv("rect", { class: "marca", x: cx - ancho / 2, y: y(x.n), width: ancho,
                                height: Math.max(0, H - m.b - y(x.n)), rx: 3, fill: color });
        const zona = sv("rect", { x: m.i + banda * i, y: m.a, width: banda, height: H - m.a - m.b, fill: "transparent" });
        conTip(zona, x.tip || [`${x.etq}: ${miles(x.n)}`]);
        g.append(r, zona);
        if (datos.length <= 16 || i % Math.ceil(datos.length / 16) === 0)
            g.append(sv("text", { x: cx, y: H - 6, "text-anchor": "middle" }, x.etq));
    });
    const ult = datos[datos.length - 1];
    if (ult) g.append(sv("text", { class: "valor", x: m.i + banda * (datos.length - .5), y: y(ult.n) - 4, "text-anchor": "middle" }, miles(ult.n)));
    return el("div", { class: "grafico" }, g);
}

/* barras horizontales; datos = [{etq, n, color, tip}] */
function barrasH(datos, { etiqueta = 150, color = "var(--s1)", W = 420 } = {}) {
    const fila = 22, H = datos.length * fila + 4;
    const max = Math.max(1, ...datos.map(x => x.n));
    const x0 = etiqueta, largo = W - x0 - 56;
    const g = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" },
        sv("line", { class: "eje", x1: x0, x2: x0, y1: 0, y2: H }));
    datos.forEach((x, i) => {
        const y = i * fila + 3, w = largo * x.n / max;
        g.append(
            sv("text", { x: x0 - 8, y: y + 13, "text-anchor": "end" }, x.etq.length > etiqueta / 6.2 ? x.etq.slice(0, Math.floor(etiqueta / 6.2) - 1) + "…" : x.etq),
            sv("rect", { class: "marca", x: x0, y: y + 3, width: Math.max(x.n ? 2 : 0, w), height: fila - 9, rx: 3, fill: x.color || color }),
            sv("text", { class: "valor", x: x0 + w + 6, y: y + 13 }, miles(x.n)));
        const zona = sv("rect", { x: 0, y, width: W, height: fila, fill: "transparent" });
        conTip(zona, x.tip || [`${x.etq}: ${miles(x.n)}`]);
        g.append(zona);
    });
    return el("div", { class: "grafico" }, g);
}

async function pintarGraficos() {
    cargando("graficos");
    const d = await pedir("graficos");
    const contrato = new Set(d.regiones_con_contrato || []);
    const tarjeta = (titulo, sub, ...cuerpo) => el("div", { class: "tarjeta" }, el("h2", {}, titulo),
        sub ? el("p", { class: "tenue" }, sub) : null, cuerpo);
    const sinDominante = (lista, clave) => {
        const dom = lista.find(x => x.k === clave);
        return { resto: lista.filter(x => x.k !== clave), dom: dom ? dom.n : 0 };
    };

    // 1. cosecha en el tiempo
    const dias = d.por_dia.map(x => ({
        etq: x.dia.slice(8, 10) + "/" + x.dia.slice(5, 7), n: x.n,
        tip: [`${new Date(x.dia + "T12:00").toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long" })}`,
              `${miles(x.n)} ítems nuevos`],
    }));
    const hoy = d.por_dia[d.por_dia.length - 1];

    // 2. tema y evento, sin la barra que aplasta al resto
    const t = sinDominante(d.por_tema, "general");
    const e = sinDominante(d.por_evento, "otro");

    // 3. región: las con contrato siempre aparecen, aunque tengan 0 (eso ES el punto ciego)
    const reg = [];
    for (const x of d.por_region) {
        const k = normRegion(x.k), y = reg.find(r => r.k === k);
        if (y) y.n += x.n; else reg.push({ k, n: x.n });
    }
    for (const r of contrato) if (!reg.some(x => x.k === r)) reg.push({ k: r, n: 0 });
    reg.sort((a, b) => b.n - a.n);
    const totalReg = reg.reduce((s, x) => s + x.n, 0);

    // 4. medios por tipo + fuentes caídas
    const caidasCuenta = {};
    for (const c of d.corridas) for (const f of c.caidas) caidasCuenta[f] = (caidasCuenta[f] || 0) + 1;
    const tipos = new Set(d.top_medios.map(m => m.tipo));

    // 5. embudo
    const cosechadas = d.por_dia.reduce((s, x) => s + x.n, 0);
    const cand = d.embudo.reduce((s, x) => s + x.candidatos, 0);
    const eleg = d.embudo.reduce((s, x) => s + x.elegidas, 0);
    const marc = d.embudo.reduce((s, x) => s + x.marcadas, 0);
    const etapas = [
        { etq: "Cosechadas (14 días)", n: cosechadas },
        { etq: "Candidatas (suma por entrega)", n: cand },
        { etq: "Elegidas por el agente", n: eleg },
        { etq: "Marcadas por ti", n: marc },
    ];

    $("[data-panel=graficos]").replaceChildren(
        tarjeta("1 · Cosecha en el tiempo", `Ítems vistos por primera vez cada día, últimos 14 días. Hoy van ${miles(hoy?.n || 0)} (el día no ha terminado).`,
            barrasV(dias), tablaDe(["Día", "Ítems"], d.por_dia.map(x => [x.dia, miles(x.n)]))),
        el("div", { class: "rejilla" },
            tarjeta("2 · Tema", `Últimos 7 días. Fuera del gráfico: ${miles(t.dom)} ítems de tema «General».`,
                barrasH(t.resto.map(x => ({ etq: tema(x.k), n: x.n }))),
                tablaDe(["Tema", "Ítems"], d.por_tema.map(x => [tema(x.k), miles(x.n)]))),
            tarjeta("2 · Evento", `«Plata» es 💰 Financiamiento: licitaciones, adjudicaciones, presupuestos, créditos e inversión anunciada. Fuera del gráfico: ${miles(e.dom)} ítems sin evento reconocido.`,
                barrasH(e.resto.map(x => ({ etq: evento(x.k), n: x.n }))),
                tablaDe(["Evento", "Ítems"], d.por_evento.map(x => [evento(x.k), miles(x.n)])))),
        tarjeta("3 · Región", `📌 = región con contrato. ${miles(d.sin_region)} ítems (${pct(d.sin_region, d.sin_region + totalReg)}) no traen región y no están en el gráfico.`,
            el("div", { class: "leyenda" }, el("span", {}, muestra("var(--s1)"), "📌 con contrato"), el("span", {}, muestra("var(--sin)"), "otras")),
            barrasH(reg.map(x => ({ etq: (contrato.has(x.k) ? "📌 " : "") + region(x.k), n: x.n,
                                    color: contrato.has(x.k) ? "var(--s1)" : "var(--sin)",
                                    tip: [`${region(x.k)}: ${miles(x.n)} ítems`, contrato.has(x.k) ? (x.n ? "región con contrato" : "🕳 región con contrato y sin noticias") : ""] })),
                    { W: 760, etiqueta: 180 }),
            tablaDe(["Región", "Con contrato", "Ítems"], reg.map(x => [region(x.k), contrato.has(x.k) ? "sí" : "", miles(x.n)]))),
        el("div", { class: "rejilla" },
            tarjeta("4 · Medios que más aportan", "Últimos 7 días, ya unificados (un medio con varios feeds cuenta una vez). Color = tipo.",
                el("div", { class: "leyenda" }, DIMS.tipo.valores.filter(v => tipos.has(v)).map(v => el("span", {}, muestra(colorDe("tipo", v)), v)),
                   tipos.has(null) ? el("span", {}, muestra(null), "sin clasificar") : null),
                barrasH(d.top_medios.map(m => ({ etq: m.nombre, n: m.n, color: colorDe("tipo", m.tipo) || "var(--sin)",
                                                 tip: [`${m.nombre}: ${miles(m.n)} ítems`, m.tipo || "sin tipo"] }))),
                el("p", {}, el("a", { href: "#", onclick: ev => { ev.preventDefault(); irA("medios"); } }, "🏷️ Marcar preferencias y buscar medios nuevos →")),
                tablaDe(["Medio", "Tipo", "Ítems"], d.top_medios.map(m => [m.nombre, m.tipo || "—", miles(m.n)]))),
            tarjeta("4 · Fuentes caídas por corrida", "Feeds que respondieron vacío o con error en cada una de las últimas corridas.",
                barrasV(d.corridas.map(c => ({ etq: cuando(c.cuando).slice(0, 5), n: c.caidas.length,
                                              tip: [cuando(c.cuando), `${c.caidas.length} caída(s)`, ...c.caidas] })),
                        { alto: 130, color: "var(--s2)", W: 420 }),
                filas(Object.entries(caidasCuenta).sort((a, b) => b[1] - a[1]).slice(0, 6)
                    .map(([f, n]) => [f, `${n} de ${d.corridas.length} corridas`])))),
        tarjeta("5 · Embudo", "De lo que se cosecha a lo que te sirvió. Cada etapa con su % respecto de la anterior.",
            barrasH(etapas.map((x, i) => ({ ...x, etq: x.etq,
                tip: [`${x.etq}: ${miles(x.n)}`, i ? `${pct(x.n, etapas[i - 1].n)} de la etapa anterior` : ""] })),
                    { W: 760, etiqueta: 210 }),
            marc === 0 && eleg ? el("div", { class: "aviso ojo" },
                `🗳 ${miles(eleg)} elegidas y ninguna marcada: el agente todavía no ha recibido un solo voto. `,
                el("a", { href: "#", onclick: ev => { ev.preventDefault(); irA("entregas"); } }, "Marcar en 🗳️ Entregas")) : null,
            tablaDe(["Entrega", "Candidatas", "Elegidas", "Marcadas"],
                d.embudo.slice().reverse().map(x => [x.entrega, miles(x.candidatos), miles(x.elegidas), miles(x.marcadas)]))));
}

/* ---------- 🏷️ Medios ---------- */

const medios = { filtro: "todos", texto: "", mostrar: 80, datos: null };

async function pintarMedios() {
    cargando("medios");
    medios.datos = await pedir("medios");
    const cont = $("[data-panel=medios]");
    const L = medios.datos.medios;
    const cuenta = f => L.filter(f).length;
    const FILTROS = {
        todos: [() => true, "Todos"],
        nuevos: [m => !m.en_catalogo, "🔎 Nuevos (fuera del catálogo)"],
        sin: [m => !m.tipo || !m.tendencia, "Sin clasificar"],
        favorito: [m => m.preferencia === "favorito", "⭐ Favoritos"],
        evitar: [m => m.preferencia === "evitar", "🚫 Evitar"],
        evaluar: [m => m.preferencia === "evaluar", "📋 Para evaluar"],
    };
    const buscar = el("input", { type: "search", placeholder: "Buscar medio…", value: medios.texto });
    buscar.addEventListener("input", () => { medios.texto = buscar.value; medios.mostrar = 80; pintarTabla(); });
    const tabla = el("div");

    cont.replaceChildren(
        el("div", { class: "tarjeta" },
            el("p", {}, `${miles(L.length)} medios distintos en la cosecha, `,
               `${miles(cuenta(m => m.en_catalogo))} con feed propio en el catálogo. `,
               "Los que están «fuera del catálogo» llegan sólo por agregadores (Google News y otros): ",
               "son los candidatos a medio nuevo. Márcalos 📋 y quedan en la lista para evaluar de ",
               el("code", {}, "_preferencias.md"), "."),
            el("p", { class: "tenue" }, "Lo que clasificas va a ", el("code", {}, "_medios.json"),
               "; ⭐ y 🚫 van a ", el("code", {}, "_preferencias.md"),
               " (sección Medios). El agente todavía no los usa para elegir: por ahora sólo alimentan la simulación de la Portada. ",
               "El tipo marcado ≈ es estimado desde el catálogo de feeds; elige uno para dejarlo fijo."),
            el("div", { class: "controles" }, buscar,
               segmento(Object.entries(FILTROS).map(([v, [f, t]]) => ({ v, t: `${t} (${cuenta(f)})` })), medios.filtro,
                        v => { medios.filtro = v; medios.mostrar = 80; pintarTabla(); }))),
        tabla);

    function pintarTabla() {
        const q = medios.texto.toLowerCase();
        const vistos = L.filter(FILTROS[medios.filtro][0])
            .filter(m => !q || m.nombre.toLowerCase().includes(q) || m.clave.includes(q));
        tabla.replaceChildren(el("div", { class: "tarjeta" },
            el("table", { class: "tabla-medios" },
                el("thead", {}, el("tr", {}, ["Medio", "7 días", "Visto", ...Object.values(DIMS).map(x => x.t), "Preferencia"]
                    .map(c => el("th", {}, c)))),
                el("tbody", {}, vistos.slice(0, medios.mostrar).map(filaMedio))),
            vistos.length > medios.mostrar ? el("p", {}, el("button", {
                onclick: () => { medios.mostrar += 80; pintarTabla(); },
            }, `Mostrar 80 más (quedan ${miles(vistos.length - medios.mostrar)})`)) :
            vistos.length ? null : el("p", { class: "tenue" }, "Ninguno.")));
    }

    function reflejar(m, campo, valor) {
        m[campo] = valor || null;
        const p = portada.datos?.medios?.[m.clave];
        if (p) p[campo] = valor || null;
    }

    function filaMedio(m) {
        const nombre = el("input", { type: "text", value: m.nombre, "aria-label": "nombre", maxlength: "80" });
        nombre.addEventListener("change", async () => {
            const v = nombre.value.trim();
            if (!v || v === m.nombre) { nombre.value = m.nombre; return; }
            try { await correr([CMD, "clasificar", m.clave, "nombre", v]); reflejar(m, "nombre", v); }
            catch (e) { nombre.value = m.nombre; error("No pude renombrar: " + (e.message || e)); }
        });
        const selects = Object.entries(DIMS).map(([campo, dd]) => {
            const s = el("select", { "aria-label": dd.t },
                el("option", { value: "" }, "—"),
                dd.valores.map(v => el("option", { value: v },
                    (campo === "tipo" && m.tipo_estimado && m.tipo === v ? "≈ " : "") + v)));
            s.value = m[campo] || "";
            s.addEventListener("change", async () => {
                const antes = m[campo] || "";
                s.disabled = true;
                try {
                    await correr([CMD, "clasificar", m.clave, campo, s.value]);
                    reflejar(m, campo, s.value);
                    if (campo === "tipo") m.tipo_estimado = false;
                } catch (e) { s.value = antes; error("No pude clasificar: " + (e.message || e)); }
                s.disabled = false;
            });
            return el("td", {}, s);
        });
        const pref = el("td", { class: "pref" });
        const pintarPref = () => pref.replaceChildren(...[["favorito", "⭐", "Favorito"], ["evitar", "🚫", "Evitar"],
                                                         ["evaluar", "📋", "Evaluar para el catálogo"]].map(([v, t, titulo]) =>
            el("button", { class: m.preferencia === v ? "on" : "", title: titulo, onclick: async ev => {
                const nuevo = m.preferencia === v ? "nada" : v;
                ev.currentTarget.disabled = true;
                try { await correr([CMD, "preferir", m.clave, nuevo]); reflejar(m, "preferencia", nuevo === "nada" ? null : nuevo); }
                catch (e) { error("No pude guardar la preferencia: " + (e.message || e)); }
                pintarPref();
            } }, t)));
        pintarPref();
        return el("tr", {},
            el("td", {}, nombre, el("div", { class: "tenue" }, m.clave, " · ",
                m.en_catalogo ? `catálogo (${m.feeds.length} feed${m.feeds.length > 1 ? "s" : ""})` : "🔎 fuera del catálogo")),
            el("td", {}, miles(m.recientes)),
            el("td", { class: "tenue" }, hace(m.ultimo)),
            selects, pref);
    }

    pintarTabla();
}

/* ---------- 🗳️ Entregas ---------- */

async function pintarEntregas() {
    const cont = $("[data-panel=entregas]");
    cargando("entregas");
    let d;
    try { d = await pedir("estado"); }
    catch (e) { cont.replaceChildren(el("div", { class: "aviso rojo" }, "No pude leer las noticias: " + (e.message || e))); return; }
    const c = d.corridas || { lista: [] };
    const pref = d.preferencias || {};
    const ult = c.lista[0];
    let ciegos = {};
    try { ciegos = ult ? JSON.parse(ult.ciegos || "{}") : {}; } catch (e) { ciegos = {}; }

    const marcar = async (entrega, n, casilla) => {
        casilla.disabled = true;
        try {
            await correr([CMD, "marcar", entrega.archivo, n.hash, casilla.checked ? "si" : "no"]);
            n.marcado = casilla.checked;
            const h = portada.datos?.historias.find(x => x.hash === n.hash);
            if (h) h.marcada = casilla.checked;
        } catch (e) {
            casilla.checked = !casilla.checked;
            error("No pude marcar: " + (e.message || e));
        }
        casilla.disabled = false;
    };

    cont.replaceChildren(
        pref.items && !pref.marcados ? el("div", { class: "aviso ojo" },
            `🗳 Llevas ${pref.items} noticias entregadas y ninguna marcada. El agente aprende de estas marcas: `,
            "marca las que te sirvieron (es lo mismo que marcar [x] en Obsidian).") : null,
        el("div", { class: "rejilla" },
            el("div", { class: "tarjeta" }, el("h2", {}, "Cosecha"),
               filas([
                   ["Última corrida", ult ? `${cuando(ult.cuando)} · ${ult.items} ítems, ${ult.grupos} grupos` : "—"],
                   ["Nuevas hoy", String(c.nuevos_hoy ?? "—")],
                   ["En la base", String(c.total ?? "—")],
                   ["Próxima cosecha", d.turnos?.["noticias-cosecha"]?.proximo || "—"],
                   ["Próxima selección", d.turnos?.["noticias-seleccion"]?.proximo || "—"],
               ])),
            el("div", { class: "tarjeta" }, el("h2", {}, "Puntos ciegos de la cosecha"),
               filas([
                   ["Fuentes caídas", (ciegos.fuentes_caidas || []).length ? ciegos.fuentes_caidas.join(", ") : "ninguna"],
                   ["Regiones con contrato sin fuente", (ciegos.regiones_con_contrato_sin_fuente_sana || []).length ? ciegos.regiones_con_contrato_sin_fuente_sana.join(", ") : "ninguna"],
                   ["Barrido amplio / dirigido", ciegos.razon_barrido_sobre_dirigida != null ? `${coma(ciegos.razon_barrido_sobre_dirigida)}×` : "—"],
               ]),
               el("p", { class: "tenue" }, "Si la razón baja de 1, la cosecha mira sólo lo que ya sabe que le interesa."))),
        el("div", { class: "tarjeta" }, el("h2", {}, "Entregas: marca las que te sirvieron"),
           (d.entregas || []).map((en, i) => el("details", { open: i === 0 },
               el("summary", {}, el("strong", {}, en.archivo.replace(/ - noticias - .*\.md$/, "")),
                  el("span", { class: "tenue" }, ` · ${en.elegidos.length} elegidas · ${en.elegidos.filter(x => x.marcado).length} marcadas`)),
               en.elegidos.length ? en.elegidos.map(n => {
                   const casilla = el("input", { type: "checkbox", checked: n.marcado, "aria-label": "me sirvió" });
                   casilla.addEventListener("change", () => marcar(en, n, casilla));
                   return el("div", { class: "noticia" }, casilla,
                       el("div", {}, el("div", {}, n.titulo, " ", el("a", { href: n.url, target: "_blank", rel: "noopener" }, "ver ↗")),
                          el("div", { class: "meta" }, el("span", { class: "chip" }, evento(n.evento)), el("span", { class: "chip" }, tema(n.tema)),
                             `${n.medio} · ${n.cobertura} medio(s)`)));
               }) : el("p", { class: "tenue" }, "Sin señal en esta corrida."),
               en.descartados.length ? el("details", {}, el("summary", { class: "tenue" }, "Descartadas (muestra)"),
                   el("ul", {}, en.descartados.map(x => el("li", { class: "tenue" }, `${x.titulo} · ${evento(x.evento)} · ${coma(x.puntaje, 3)}`)))) : null))));
}

/* ---------- arranque ---------- */

// Actualizar (barra compartida): vuelve a pedir lo de la pestaña que se está mirando.
barraNodo.alActualizar(async () => {
    pintadas.clear();
    portada.datos = null;
    irA(pestanaActual);
});

cockpit.transport.wait(() => irA("portada"));
