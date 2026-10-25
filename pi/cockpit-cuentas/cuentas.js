/*
 * Herramienta "💳 Cuentas" de Cockpit (encargo 13, decisión de Diego del 30-09-2026).
 *
 * Canónico en el vault (10-Proyectos/11-Pi5/pi/cockpit-cuentas/); se instala copiando
 * la carpeta a ~/.local/share/cockpit/cuentas, junto con `comun`, de donde carga
 * tokens.css, base.css, tema.js, dom.js, barra.js y comun.js (encargo 18: ya no depende
 * del paquete `bots`). Antes todo esto vivía dentro de 🤖 Asistentes: se mudó porque las
 * cuentas son comunes a los dos bots, a n8n y a las sesiones interactivas.
 *
 * Encargo 18: «⏳ ¿Quién tiene margen?» queda fijo arriba y lo demás va en pestañas
 * (Rutas · Proveedores · Uso y costo · Renovación). Las propuestas se listan sólo en
 * 🤖 Asistentes: acá queda cuántas hay por aplicar, con el enlace.
 *
 * Doctrina:
 *  - La página PINTA lo que trae `bots-info` y PROPONE. No decide nada: qué proveedor
 *    puede ir en qué ruta llega resuelto, celda por celda, en `matriz` (sale de
 *    recetas.py): filas = rutas y columnas = asistentes, como lo decidió Diego el 01-10.
 *    La lista de cuentas llega en `cuentas` y el margen, en `margen`. Acá no hay ninguna
 *    lista de cuentas ni de rutas escrita a mano (hay una prueba).
 *  - Cada propuesta sigue siendo de UN perfil y la aplica `sudo aplicar-propuesta <id>`
 *    por SSH, que vuelve a validar los muros.
 *  - Al abrir, lo primero es quién tiene margen: % de 5 h, % semanal y cuándo se renuevan.
 *  - Encargo 15: los proveedores gratis y la recomendación por función. Qué proveedor
 *    hay, si tiene key en cada bot, cómo se carga, qué se recomienda en cada ruta y por
 *    qué llega de `bots-info` (recetas.recomendada): acá no se repite ninguna regla.
 */
"use strict";

let info = null;
// En el teléfono la matriz muestra una sola columna (pestañas): la de este asistente.
let perfilVisible = null;

const fechaCorta = iso => `${iso.slice(8, 10)}-${iso.slice(5, 7)} ${iso.slice(11, 16)}`;
const NOMBRE_RUTA = { "pi/interactivo": "Sesiones de la Pi (👾)" };
const esPc = clave => clave.startsWith("pc:");

/* ---------- pestañas: el margen queda fijo arriba, lo demás se elige ---------- */

// Cada sección dice de qué pestaña es con data-pestana (index.html). Todas se pintan al
// leer bots-info; la pestaña sólo decide cuáles se ven.
let panelVisible = "rutas";

function mostrarPanel(p) {
    panelVisible = p;
    document.querySelectorAll("#paneles button").forEach(b => b.classList.toggle("activa", b.dataset.p === p));
    document.querySelectorAll("section[data-pestana]").forEach(s => { s.hidden = s.dataset.pestana !== p; });
}
document.querySelectorAll("#paneles button").forEach(b => b.addEventListener("click", () => mostrarPanel(b.dataset.p)));

/* ---------- lectura ---------- */

async function cargar() {
    const boton = document.getElementById("actualizar");
    boton.disabled = true;
    const carga = leerCarga();          // en paralelo con bots-info; nunca falla (sin dato = null)
    // El contador no depende de bots-info: se ve aunque sudo falle.
    pintarContadorPropuestas();
    try {
        info = await leerBotsInfo();
        mostrarError(null);
    } catch (e) {
        mostrarError("No pude leer las cuentas (sudo -n /usr/local/bin/bots-info): " +
                     (e.message || e) + ". Si sudo ya pide contraseña, falta su línea en sudoers.");
        boton.disabled = false;
        return;
    }
    boton.disabled = false;
    cargaColas = await carga;
    if (!info.cuentas)
        mostrarError("El bots-info desplegado es anterior al encargo 13: no trae la lista de cuentas ni el margen. Falta desplegarlo.");
    barraNodo.leido(info.momento);
    const nombres = Object.keys(info.perfiles);
    if (!perfilVisible || !nombres.includes(perfilVisible)) perfilVisible = nombres[0];
    pintarMargen();
    pintarMatriz();
    pintarProveedores();
    pintarUso();
    pintarRendimiento();
    pintarPcs();
    pintarRegistro();
    mostrarPanel(panelVisible);
}

/* ---------- carga comprometida de las colas, sobre las barras del margen (encargo 46b) ---------- */

// Sale de `cola-run.py --panel`, el mismo origen que la matriz «Carga vs. capacidad» de 🧵 Encargos: acá se dibuja sólo
// `reglas`, la carga comprometida de las colas activas (las proyecciones de «¿y si la reanudo?» no llegan a esta página).
// null = no se pudo leer o no hay colas activas: las barras quedan como siempre. La página sólo lee.
const COLA_RUN = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/cola-run.py";
let cargaColas = null;

async function leerCarga() {
    try {
        const x = JSON.parse(await cockpit.spawn(["python3", COLA_RUN, "--panel"], { err: "ignore" }));
        return Array.isArray(x.reglas) && x.reglas.length ? x.reglas.filter(r => r && typeof r === "object") : null;
    } catch (e) {
        return null;
    }
}

// El nombre de una cola es un dato del panel. Se muestra sólo si tiene la forma de un nombre de cola (letras, hasta
// cuatro dígitos y un sufijo corto, como «cola43r») y no trae un nombre de persona; si no, «oculto». Es más estricto
// que la lista blanca de 🧵 Encargos (hay una prueba).
const RE_COLA = /^[a-z]{1,12}[0-9]{0,4}[a-z]{0,2}$/;
const RE_PERSONA = /(?:diego)|(?:cami)/;
const colaSegura = x => (typeof x === "string" && RE_COLA.test(x) && !RE_PERSONA.test(x) ? x : "«oculto»");
const n1 = x => String(Math.round(x * 10) / 10).replace(".", ",").replace("-", "−");
const horaCorta = iso => {
    const t = new Date(iso);
    return typeof iso !== "string" || Number.isNaN(t.getTime()) ? null
        : t.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false });
};
// El color de una cola es su lugar entre las activas del panel: el mismo orden y los mismos tonos que en 🧵 Encargos.
const colorCola = i => `cola-c${i % 4 + 1}`;
const colasActivas = () => [...new Set((cargaColas || []).flatMap(r => Object.keys(r.celdas && typeof r.celdas === "object" ? r.celdas : {})))];

// Lo que las colas activas le suman a una cuenta: {h5, sem, colas}. Cada ventana trae el uso y el tope que publica el
// panel y un tramo por cola; la de 5 h, además, lo que cae tras la renovación. Una ventana sin carga es null, y una
// cuenta que ninguna cola activa usa también: su barra no cambia.
function cargaDe(cid) {
    const r = (cargaColas || []).find(x => x.cuenta === cid);
    if (!r || !r.celdas || typeof r.celdas !== "object") return null;
    const colas = colasActivas();
    const ventana = (id, k, proxima) => {
        const w = (Array.isArray(r.ventanas) ? r.ventanas : []).find(x => x && x.ventana === id);
        if (!w || ![w.actual, w.tope, w.pronostico].every(Number.isFinite)) return null;
        const partes = colas.map((cola, i) => ({ cola, i, pct: Object.prototype.hasOwnProperty.call(r.celdas, cola) ? (r.celdas[cola] || {})[k] : null }))
            .filter(x => Number.isFinite(x.pct) && x.pct > 0);
        const despues = proxima && Number.isFinite(r.proxima_5h) && r.proxima_5h > 0 ? r.proxima_5h : 0;
        return partes.length || despues ? { uso: w.actual, tope: w.tope, carga: w.pronostico, partes, despues, renueva: r.renueva_5h } : null;
    };
    const h5 = ventana("5h", "pct_5h", true), sem = ventana("semanal", "pct_sem", false);
    const usadas = new Set([h5, sem].flatMap(w => (w ? w.partes.map(x => x.cola) : [])));
    return h5 || sem ? { h5, sem, colas: colas.map((cola, i) => ({ cola, i })).filter(x => usadas.has(x.cola)) } : null;
}

// La barra de una ventana. Sin carga (`w` null) es la de siempre, sola. Con carga es la de «Capacidad»: el uso, un
// tramo fantasma por cola con su color, la línea del tope y, si algo cae tras la renovación, la barra chica «↻ desde
// las HH:MM». Los anchos van por data-ancho (aplicarAnchos) y la posición del tope, por CSSOM.
function barraVentana(usado, titulo, w) {
    if (!w) return [barraUso(usado, titulo)];
    const tope = () => {
        const marca = el("i", { class: "capacidad-tope", title: `tope ${n1(w.tope)} %` });
        marca.style.setProperty("--pos", `${Math.max(0, Math.min(100, w.tope))}%`);
        return marca;
    };
    const u = Math.max(0, Math.min(100, w.uso));
    let x = u;
    const tramos = w.partes.map(p => {
        const ancho = Math.max(0, Math.min(p.pct, 100 - x));
        x += p.pct;
        return ancho > 0 ? el("span", { class: `fantasma ${colorCola(p.i)}`, "data-ancho": String(Math.round(10 * ancho)),
                                         title: `${colaSegura(p.cola)}: carga comprometida ${n1(p.pct)} %` }) : null;
    });
    const suma = Math.round((w.uso + w.carga) * 10) / 10;
    return [el("div", { class: "tenue num" }, el("strong", {}, "Capacidad"),
                `: uso ${n1(w.uso)} % + carga comprometida ${n1(w.carga)} % = `,
                el("span", { class: suma > w.tope ? "estado mal" : "" }, `${n1(suma)} %`), ` · tope ${n1(w.tope)} %`),
            el("div", { class: "capacidad-pista" },
                el("div", { class: "barra-ciclo" + (u >= 90 ? " lleno" : u >= 75 ? " justo" : ""), title: titulo || "" },
                    el("span", { class: "usado", "data-ancho": String(Math.round(10 * u)) }), tramos,
                    el("span", { class: "ocioso", "data-ancho": String(Math.round(10 * Math.max(0, 100 - Math.max(u, x)))) })),
                tope()),
            // el() aplana un solo nivel: lo de la renovación va desplegado, no como lista dentro de la lista.
            ...(w.despues ? [
                el("div", { class: "tenue num" }, `↻ ${horaCorta(w.renueva) ? `desde las ${horaCorta(w.renueva)}` : "en la próxima ventana"}: `,
                   `carga comprometida ${n1(w.despues)} %`),
                el("div", { class: "capacidad-pista chica" },
                    el("div", { class: "barra-ciclo" },
                        el("span", { class: "fantasma proxima", "data-ancho": String(Math.round(10 * Math.min(100, w.despues))) }),
                        el("span", { class: "ocioso", "data-ancho": String(Math.round(10 * Math.max(0, 100 - w.despues))) })),
                    tope())] : [])];
}

// Qué cola es cada color. Sin carga no hay leyenda.
function leyendaCarga(carga) {
    if (!carga || !carga.colas.length) return null;
    return el("div", { class: "capacidad-leyenda tenue" }, "Carga comprometida: ",
        carga.colas.map(c => el("span", {}, el("span", { class: `capacidad-punto ${colorCola(c.i)}` }), colaSegura(c.cola))));
}

/* ---------- ⏳ quién tiene margen: lo primero que se ve ---------- */

function pintarMargen() {
    const cont = document.getElementById("margen");
    const titulo = el("h2", {}, "⏳ ¿Quién tiene margen?");
    const m = info.margen;
    if (!m) {
        cont.replaceChildren(titulo, el("div", { class: "aviso ojo" },
            "bots-info no trae el margen por cuenta: falta desplegar su versión del encargo 13."));
        return;
    }
    const ventana = (etiqueta, v, umbral, w) => {
        if (!v) return el("div", { class: "margen-ventana tenue" }, `${etiqueta}: sin dato`);
        const renueva = v.renueva ? cuando(v.renueva) : "";
        if (v.renovada) {
            return el("div", { class: "margen-ventana" },
                el("div", {}, el("strong", {}, etiqueta), ": ya se renovó",
                   renueva ? el("span", { class: "tenue" }, ` (${renueva}) y no se midió desde entonces`) : null),
                barraVentana(0, `${etiqueta}: sin medir desde la renovación`, w));
        }
        const en = v.renueva ? faltan(v.renueva) : "";
        return el("div", { class: "margen-ventana" },
            el("div", {}, el("strong", {}, etiqueta), `: ${pct(v.usado_pct)} usado · `,
               el("strong", {}, `${pct(v.libre_pct)} libre`),
               umbral != null && v.usado_pct >= umbral
                   ? el("span", { class: "estado mal" }, ` · sobre el umbral (${umbral} %)`) : null),
            barraVentana(v.usado_pct, `${etiqueta}: ${pct(v.usado_pct)} usado`, w),
            el("div", { class: "tenue" }, renueva ? `se renueva ${renueva}${en ? ` (${en})` : ""}`
                : "sin ventana abierta: empieza con el próximo uso"));
    };
    // Los proveedores sin cuenta pagada no tienen límite semanal: van en una línea, abajo.
    const gratis = [];
    const tarjetas = m.orden.map(cid => {
        const c = m.cuentas[cid];
        if (!c.pagada) {
            gratis.push(c.nombre);
            return null;
        }
        const rs = c.renueva_semana;
        const carga = cargaDe(cid);
        return el("div", { class: "cuenta-uso margen-cuenta" + (c.sobre ? " sobre" : "") },
            el("h3", {}, c.nombre,
               cid === m.con_margen ? el("span", { class: "insignia ok" }, "la con más margen") : null,
               c.sobre ? el("span", { class: "insignia", title: "Pasó el umbral: el bot la salta y usa la siguiente de la cadena" },
                   "el bot la salta") : null),
            ventana("5 h", c.ventana_5h, c.umbral_5h, carga && carga.h5),
            ventana("Semana", c.semanal, c.umbral_semanal, carga && carga.sem),
            leyendaCarga(carga),
            // Sin límite semanal medido, la renovación sale del ciclo con que se reparte el precio.
            rs && rs.origen !== "medido" ? el("div", { class: "tenue" },
                `semana: próxima renovación ${cuando(rs.cuando)} `,
                el("span", { class: "insignia" }, rs.origen === "registro" ? "del registro" : "supuesta")) : null,
            el("div", { class: "tenue" }, c.momento ? `medido ${hace(c.momento)}` : "sin medición",
               c.viejo ? " · dato viejo" : ""));
    });
    const mejor = m.con_margen && m.cuentas[m.con_margen];
    cont.replaceChildren(titulo,
        el("p", { class: mejor ? "" : "tenue" }, mejor
            ? [el("strong", {}, mejor.nombre), ` es la que tiene más margen: ${pct(mejor.libre_pct)} libre `,
               "en su ventana más apretada."]
            : "Ninguna cuenta pagada tiene margen medido bajo el umbral."),
        el("div", { class: "rejilla tres" }, tarjetas),
        gratis.length ? el("p", { class: "tenue" }, `Sin cuenta pagada (no tienen límite semanal ni renovación): ${gratis.join(", ")}. `,
            "Su límite es el gratis de cada proveedor, por minuto o por día; al llegar, el bot pasa al siguiente de la cadena.") : null,
        el("p", { class: "tenue" }, "El % es del límite de la cuenta entera (bots, sesiones de la Pi y los PC ",
           "que reportan), leído de uso.json. «El bot la salta» usa el umbral global de la cuenta; una ",
           "receta de ruta puede ponerle excepción (abajo)."));
    aplicarAnchos(cont);
}

/* ---------- 🧭 matriz común: filas = rutas, columnas = asistentes ---------- */

// La forma la decidió Diego el 01-10 (encargos/13-notas-diego.md): UNA sola tabla, una
// fila por ruta y una columna por asistente; cada celda trae los servicios de esa ruta
// en ese asistente, en orden. Qué filas hay, en qué orden y qué asistente tiene cada
// una llega resuelto en `info.matriz` (bots-info.matriz_comun): acá sólo se pinta.
function pintarMatriz() {
    const cont = document.getElementById("matriz");
    const titulo = el("h2", {}, "🧭 Quién contesta cada ruta");
    const comun = info.matriz;
    if (!comun || !Array.isArray(comun.rutas) || !Array.isArray(comun.perfiles)) {
        cont.replaceChildren(titulo, el("div", { class: "aviso ojo" },
            "bots-info no trae la matriz común ruta × asistente: falta desplegar bots-info ",
            "del encargo 13 (y botv3/recetas.py del 10)."));
        return;
    }
    const cuerpo = el("tbody");
    const pie = el("tfoot");
    // En el teléfono se ve UNA columna de la misma tabla: la del asistente elegido.
    const elegir = id => {
        perfilVisible = id;
        cont.querySelectorAll("[data-perfil]").forEach(n => n.classList.toggle("activa", n.dataset.perfil === id));
    };
    const pintar = () => {
        cuerpo.replaceChildren(...comun.rutas.map(fila => el("tr", {},
            el("th", { scope: "row", class: "ruta" }, fila.nombre,
               fila.nombre !== fila.interna ? el("div", { class: "tenue" }, `antes ${fila.interna}`) : null),
            columnas.map(col => col.celda(fila)))));
        pie.replaceChildren(el("tr", {}, el("th", { scope: "row", class: "ruta" }, "Reparto"),
            columnas.map(col => col.pie())));
        elegir(perfilVisible);
    };
    const columnas = comun.perfiles.map(c => columnaPerfil(c, info.perfiles[c.id], comun, pintar));
    // Las pestañas sólo se ven en pantalla angosta (cuentas.css); en ancho van las columnas.
    const pestanas = el("nav", { class: "pestanas solo-angosto" }, comun.perfiles.map(c =>
        el("button", { "data-perfil": c.id, onclick: () => elegir(c.id) },
           `${c.nombre}${c.persona ? ` · ${c.persona}` : ""}`)));
    cont.replaceChildren(titulo,
        el("p", { class: "tenue" }, "Una fila por ruta y una columna por asistente. En cada celda, los servicios ",
           "de esa ruta en ese asistente: el 1º contesta y los demás son el respaldo si falla o se agota. ",
           "Se edita tocando: un servicio con «+» se agrega al final; uno ya elegido pasa a primero; la ✕ lo ",
           "quita. ● es la sesión y el % es lo usado de la semana. ⭐ marca lo recomendado para la función de ",
           "la ruta (primero lo gratis que sirve y tiene key, después las cuentas pagadas de respaldo): toca la ",
           "⭐ para ver por qué. Un proveedor gratis «sin key» no existe para ese bot: tócalo para ver cómo ",
           "cargarla. En gris, lo que no se permite. Una celda vacía es una ruta que ese asistente no tiene. ",
           "No cambia lo que la ruta puede leer. Cada propuesta es de un asistente; sumar una cuenta amplía ",
           "y el script lo marca con ⚠️."),
        pestanas,
        el("table", { class: "matriz-comun" },
            el("thead", {}, el("tr", {}, el("th", { class: "ruta" }, "Ruta"), columnas.map(col => col.cabeza()))),
            cuerpo, pie),
        ...columnas.map(col => col.recetas()));
    pintar();
}

// Una columna de la matriz: el asistente `c` (`info.matriz.perfiles[]`). Devuelve cómo se
// pinta su cabeza, su celda de cada fila y su pie (atajos, avisos y «Proponer»), y guarda
// la edición de ESE asistente: lo que se toca en su columna genera su propuesta.
// Qué proveedor puede ir en qué ruta NO se decide acá: cada celda trae sus servicios ya
// resueltos (permitida, motivo, aviso, lista), de la tabla de recetas.py que aplica el
// bot y que vuelve a validar aplicar-propuesta.
function columnaPerfil(c, p, comun, repintar) {
    const perfil = c.id;
    const nombre = c.nombre || perfil;
    const attrs = clase => ({ class: "col-perfil" + (clase ? " " + clase : ""), "data-perfil": perfil });
    const propias = comun.rutas.map(fila => fila.celdas[perfil]).filter(Boolean);
    const problema = !p.toml.cuentas
        ? "todavía usa las llaves viejas (web_codex, claude_config_web). Falta la migración del documento 20"
        : !p.matriz || propias.some(f => !Array.isArray(f.celdas))
            ? "bots-info no trae sus celdas resueltas: falta desplegar bots-info del encargo 13" : "";
    const editables = problema ? [] : propias.filter(f => !f.fija);
    const rutas = editables.map(f => f.interna);
    const desplegado = Object.fromEntries(editables.map(f => [f.interna, [...f.cadena]]));
    const declarada = Object.fromEntries(editables.map(f => [f.interna, !!f.declarada]));
    const nombreDe = Object.fromEntries(propias.map(f => [f.interna, f.nombre]));
    const leeCyd = ruta => (p.lee_cyd || []).includes(ruta);
    // En edición: una copia por ruta. Se parte de lo desplegado cada vez que se lee bots-info.
    const edicion = Object.fromEntries(rutas.map(r => [r, [...desplegado[r]]]));
    let notaAtajo = "";
    // Qué servicio tiene abierta su explicación (el motivo de la ⭐ o cómo cargar la key).
    let detalle = "";
    // Si la cuenta puede contestar en este bot, por ruta: llega medido en cada servicio.
    const lista = Object.fromEntries(editables.map(f =>
        [f.interna, Object.fromEntries(f.celdas.map(muro => [muro.cuenta, !!muro.lista]))]));
    const aviso = Object.fromEntries(editables.map(f =>
        [f.interna, Object.fromEntries(f.celdas.map(muro => [muro.cuenta, muro.aviso || ""]))]));
    // Lo que le falta a un proveedor gratis en este bot y la línea para cargar su key.
    const falta = Object.fromEntries(editables.map(f =>
        [f.interna, Object.fromEntries(f.celdas.map(muro => [muro.cuenta, muro]))]));
    const sesion = p.por_cuenta || {};
    const uso = (info.uso_cuentas && info.uso_cuentas.cuentas) || {};
    const margen = (info.margen && info.margen.cuentas) || {};

    const semanal = cid => {
        if (!pagada(cid)) return "sin límite";
        const s = (margen[cid] || {}).semanal;
        return s && s.usado_pct != null ? `${Math.round(s.usado_pct)} %` : "sin dato";
    };
    // Lo que esta ruta de este bot lleva gastado de la cuenta en el ciclo actual.
    const costo = (r, cid) => {
        const actual = ((uso[cid] || {}).ciclos || []).find(x => x.actual);
        const gasto = actual && actual.rutas[`${perfil}/${r}`];
        return usd(gasto ? gasto.usd : 0);
    };
    const cambio = r => JSON.stringify(edicion[r]) !== JSON.stringify(desplegado[r]);
    const cambiadas = () => rutas.filter(cambio);
    const agregadas = () => rutas.flatMap(r =>
        edicion[r].filter(cid => !desplegado[r].includes(cid)).map(cid => [r, cid]));
    const tocar = hacer => { hacer(); notaAtajo = ""; repintar(); };
    const explicar = clave => { detalle = detalle === clave ? "" : clave; repintar(); };

    // Un servicio de la celda: chip con su lugar en la cadena, ⭐, sesión y % semanal.
    const servicio = (f, muro) => {
        const r = f.interna, cid = muro.cuenta, ids = edicion[r];
        if (!muro.permitida) {
            return el("span", { class: "chip servicio prohibida", title: muro.motivo },
                el("button", { class: "servicio-boton", disabled: true, title: muro.motivo },
                    el("span", { class: "servicio-nombre" }, nombreCuenta(cid))));
        }
        const pos = ids.indexOf(cid);
        const con = !!muro.lista;
        // 15: un proveedor gratis que no está listo (sin key) no existe para este bot: no se
        // puede agregar a la cadena. Tocarlo muestra qué le falta y cómo se carga, que llega
        // de bots-info (`muro.falta`, `muro.estado`, `muro.cargar`).
        const ausente = !con && pos < 0 && !!muro.falta;
        const clave = `${r}/${cid}`;
        // La ⭐ es la recomendación por función (recetas.recomendada, vía bots-info): la página
        // sólo mira si el servicio está en esa cadena y muestra el motivo que trae.
        const recomendado = (f.recomendada || []).includes(cid);
        const accion = ausente ? "No se puede agregar: " + muro.falta
            : pos < 0 ? "Agregar al final de la cadena" : pos === 0 ? "Ya es la primera: contesta" : "Dejarla primera";
        return el("span", { class: "chip servicio " + (ausente ? "ausente" : pos === 0 ? "primera" : pos > 0 ? "respaldo" : "libre") },
            recomendado ? el("button", { class: "estrella", title: (f.motivos || {})[cid] || "Recomendado para esta ruta",
                "aria-label": `Por qué se recomienda ${nombreCuenta(cid)} en ${f.nombre}`,
                onclick: () => explicar(clave) }, "⭐") : null,
            el("button", { class: "servicio-boton",
                title: [accion, con ? ((sesion[cid] || {}).correo || (pagada(cid) ? "con sesión" : "listo"))
                            : ausente ? "" : (muro.falta || "sin sesión"),
                        `${costo(r, cid)} en este ciclo`, muro.aviso].filter(Boolean).join(" · "),
                onclick: () => ausente ? explicar(clave) : tocar(() => {
                    if (pos < 0) ids.push(cid);
                    else if (pos > 0) { ids.splice(pos, 1); ids.unshift(cid); }
                }) },
                el("span", { class: "orden" }, pos >= 0 ? `${pos + 1}º` : ausente ? "" : "+"),
                el("span", { class: "servicio-nombre" }, nombreCuenta(cid)),
                el("span", { class: "estado " + (con ? "ok" : "mal") }, "●"),
                el("span", { class: "servicio-dato" + ((margen[cid] || {}).sobre ? " sobre" : "") },
                   !con && muro.estado ? muro.estado : semanal(cid))),
            pos >= 0 && ids.length > 1 ? el("button", { class: "quitar", title: "Quitar de la cadena",
                "aria-label": `Quitar ${nombreCuenta(cid)} de ${f.nombre} en ${nombre}`,
                onclick: () => tocar(() => { ids.splice(pos, 1); }) }, "✕") : null);
    };

    // La celda ruta × asistente. Sin la ruta queda vacía y tenue: no se oculta.
    const celda = fila => {
        const f = fila.celdas[perfil];
        if (problema || !f)
            return el("td", attrs("vacia"), problema ? "sin matriz" : `${nombre} no tiene esta ruta`);
        if (f.fija) {
            // Fija: no hay qué elegir. Si un proveedor la contesta (la general), se nombra.
            const quien = f.celdas.filter(muro => muro.permitida).map(muro => nombreCuenta(muro.cuenta));
            return el("td", attrs("fija"),
                el("span", { class: "insignia" }, quien.length ? `fijo: ${quien.join(", ")}` : "fijo: herramienta"),
                el("div", { class: "tenue" }, f.fija));
        }
        const r = f.interna;
        const de = cid => f.celdas.find(muro => muro.cuenta === cid) || { cuenta: cid, permitida: true, lista: false };
        // Primero la cadena, en su orden; después lo que se puede agregar; al final, lo prohibido.
        const orden = [...edicion[r].map(de),
                       ...f.celdas.filter(muro => muro.permitida && !edicion[r].includes(muro.cuenta)),
                       ...f.celdas.filter(muro => !muro.permitida)];
        // La explicación abierta de esta celda: el motivo de una ⭐ o cómo cargar una key.
        const abierto = detalle.startsWith(r + "/") ? de(detalle.slice(r.length + 1)) : null;
        return el("td", attrs(cambio(r) ? "en-edicion" : ""),
            el("div", { class: "servicios" }, orden.map(muro => servicio(f, muro))),
            abierto ? el("div", { class: "celda-detalle" },
                (f.recomendada || []).includes(abierto.cuenta) && (f.motivos || {})[abierto.cuenta]
                    ? el("div", {}, "⭐ ", f.motivos[abierto.cuenta], ".") : null,
                !abierto.lista && abierto.falta ? el("div", {}, `${nombreCuenta(abierto.cuenta)} en ${nombre}: ${abierto.falta}. `,
                    abierto.cargar ? ["Para cargarla, por SSH: ", el("code", {}, abierto.cargar),
                                      " y después reiniciar el bot."] : null) : null) : null,
            el("div", { class: "tenue celda-nota" },
               f.lee_archivos ? ((p.toml.vaults || []).length ? "lee " + p.toml.vaults.join(" y ") : "sin vaults")
                   : "nunca ve archivos",
               leeCyd(f.nombre) ? el("span", { class: "insignia",
                   title: "Marcada a mano (decisión de Diego): esta ruta lee datos de CyD" }, "lee datos de CyD") : null,
               edicion[r].length ? "" : " · ninguna en `cuentas` (corre con las llaves viejas)",
               cambio(r) ? " · en edición" : declarada[r] ? "" : " · por defecto (el perfil no la declara)"));
    };

    // Avisos: lo mismo que va a advertir aplicar-propuesta, pero antes de proponer.
    const avisos = () => {
        const lista_avisos = [];
        for (const r of rutas) {
            for (const cid of edicion[r]) {
                if (aviso[r][cid])
                    lista_avisos.push(el("li", {}, `ℹ️ ${nombreCuenta(cid)} en ${nombreDe[r]}: ${aviso[r][cid]}.`));
                if (lista[r][cid]) continue;
                if (pagada(cid))
                    lista_avisos.push(el("li", {}, `${nombreCuenta(cid)} no tiene sesión en ${nombre}. `,
                        "Una vez, por SSH: ", el("code", {}, `sudo aplicar-propuesta --login ${perfil} ${cid}`)));
                else
                    lista_avisos.push(el("li", {}, `${nombreCuenta(cid)} no está listo en ${nombre} para ${nombreDe[r]}: `,
                        (falta[r][cid] || {}).falta || "el bot no tiene su key en el entorno",
                        (sesion[cid] || {}).medido === false ? " (no se pudo medir: el bot no está corriendo)" : "", ". ",
                        (falta[r][cid] || {}).cargar ? ["Se carga con ", el("code", {}, falta[r][cid].cargar), "."] : null));
            }
            // Sólo informativo desde el 29-09-2026: Diego decidió que una cuenta de otra
            // persona puede leer datos de CyD. Por eso no va en rojo ni marca «amplía».
            const ajenas = edicion[r].filter(cid => (cuentasConocidas()[cid] || {}).ajena_a_cyd).map(nombreCuenta);
            if (leeCyd(nombreDe[r]) && ajenas.length)
                lista_avisos.push(el("li", {}, `ℹ️ ${nombreDe[r]} lee datos de CyD: con ${ajenas.join(" y ")}, fragmentos `,
                    "quedan en el historial de esa cuenta. Permitido por decisión de Diego."));
        }
        const unicos = [...new Map(lista_avisos.map(li => [li.textContent, li])).values()];
        return unicos.length ? el("ul", { class: "avisos-cuentas" }, unicos) : null;
    };

    const texto = cadenas => rutas.map(r => `${nombreDe[r]}: ${cadenas[r].map(nombreCuenta).join(" → ")}`).join(" · ");
    const proponerCuentas = () => {
        // Las rutas que el perfil no declara (vision, noticias) viajan sólo si cambiaron.
        const tocadas = cambiadas();
        proponer({
            tipo: "cuentas",
            valor: Object.fromEntries(rutas.filter(r => declarada[r] || tocadas.includes(r))
                .map(r => [r, [...edicion[r]]])),
            clave: "cuentas",
            amplia: agregadas().length > 0,
            antes: texto(desplegado),
            despues: texto(edicion),
        }, perfil);
    };

    // El pie de la columna: los atajos sólo llenan la edición; se revisa y después se propone.
    const pie = () => {
        if (problema) return el("td", attrs(), el("div", { class: "aviso ojo" }, `${nombre} ${problema}.`));
        return el("td", attrs(),
            el("div", { class: "atajos" }, el("span", { class: "tenue" }, "Atajos:"),
                Object.values(p.matriz.atajos || {}).map(a => el("button", { class: "mini", title: a.nota || "",
                    onclick: () => {
                        for (const r of rutas)
                            if (Array.isArray(a.cadenas[r]) && a.cadenas[r].length) edicion[r] = [...a.cadenas[r]];
                        notaAtajo = `«${a.etiqueta}» llenó la edición` + (a.nota ? ` (${a.nota})` : "") +
                            ". Revisa y después propone.";
                        repintar();
                    } }, a.etiqueta))),
            notaAtajo ? el("div", { class: "tenue" }, notaAtajo) : null,
            avisos(),
            el("div", { class: "controles-voz separado" },
                el("button", { class: "mini", disabled: !cambiadas().length, onclick: proponerCuentas },
                   `Proponer cuentas de ${nombre}`)));
    };

    return {
        cabeza: () => el("th", attrs(), nombre, c.persona ? el("span", { class: "tenue" }, ` · ${c.persona}`) : null),
        celda, pie,
        recetas: () => bloqueRecetas(perfil, p),
    };
}

/* ---------- 🆓 proveedores gratis: listo o «sin key», y el botón «probar» (15) ---------- */

// Todo llega de bots-info (`info.proveedores`, que sale de recetas.py): qué es cada uno, en
// qué rutas puede ir, la variable de su key, su modelo, si está listo en cada asistente y
// la línea para cargar la key. «Probar» hace UNA llamada con la key de ese bot y muestra el
// modelo que contestó o el error tal cual, con su clase: «modelo retirado» y «key inválida»
// se parecen y no son lo mismo.
function pintarProveedores() {
    const cont = document.getElementById("proveedores");
    const titulo = el("h2", {}, "🆓 Proveedores gratis");
    const t = info.proveedores;
    if (!t || !t.proveedores) {
        cont.replaceChildren(titulo, el("div", { class: "aviso ojo" },
            "bots-info no trae los proveedores gratis: falta desplegar bots-info y botv3/recetas.py del encargo 15."));
        return;
    }
    const columnas = (info.matriz && info.matriz.perfiles) || [];
    const probar = async (id, perfil, salida, boton) => {
        boton.disabled = true;
        salida.className = "prueba tenue";
        salida.textContent = "probando…";
        try {
            const r = JSON.parse(await cockpit.spawn([...t.probar, id, perfil], { err: "message" }));
            salida.className = "prueba " + (r.ok ? "ok" : "mal");
            salida.textContent = r.ok
                ? `✅ contestó ${r.modelo}${r.segundos != null ? ` en ${coma(r.segundos, 1)} s` : ""}`
                : `❌ ${[r.explicacion, r.error].filter(Boolean).join(" — ")}`;
        } catch (e) {
            salida.className = "prueba mal";
            salida.textContent = "No pude probar: " + (e.message || e) +
                ". El script se instala con la página (probar-proveedor.py).";
        }
        boton.disabled = false;
    };
    const filas = Object.entries(t.proveedores).map(([id, p]) => el("tr", {},
        el("td", {}, el("strong", {}, p.nombre), el("div", { class: "tenue" }, p.que_es),
           el("div", { class: "tenue" }, p.rutas.length ? "va en: " + p.rutas.join(", ") : "no va en ninguna ruta")),
        columnas.map(c => {
            const x = (p.por_perfil || {})[c.id] || {};
            const salida = el("div", { class: "prueba" });
            const boton = el("button", { class: "mini", onclick: () => probar(id, c.id, salida, boton) }, "probar");
            return el("td", {},
                el("span", { class: "insignia" + (x.listo ? " ok" : "") }, x.estado || "sin dato"),
                x.modelo ? el("div", { class: "tenue" }, x.modelo.split(",").join(", ")) : null,
                !x.listo && x.falta ? el("div", { class: "tenue" }, x.falta,
                    !x.medido ? " (el bot no está corriendo)" : "") : null,
                !x.key && x.cargar ? el("div", { class: "tenue" }, "Se carga con ", el("code", {}, x.cargar)) : null,
                el("div", { class: "controles-voz" }, boton), salida);
        }),
        el("td", { class: "tenue" }, p.nota, p.modelo_var ? el("div", {}, "modelo: ", el("code", {}, p.modelo_var)) : null)));
    cont.replaceChildren(titulo,
        el("p", { class: "tenue" }, "APIs externas sin cuenta pagada y sin tarjeta. Nunca van en una ruta que lee ",
           "vaults. Sin key cargada en un bot, un proveedor no existe para ese bot: no entra en ninguna cadena. ",
           "La key se carga por SSH, sin eco, y el bot la toma al reiniciar. «probar» hace una llamada con la ",
           "key del archivo de entorno de ese bot."),
        el("table", { class: "proveedores" },
            el("tr", {}, el("th", {}, "Proveedor"),
               columnas.map(c => el("th", {}, c.nombre)), el("th", {}, "Medido")),
            filas));
}

/* ---------- 🧪 recetas por ruta: automático, umbral y quién contestaría (06a) ---------- */

// «¿Quién contestaría ahora?» NO se calcula acá: lo trae bots-info con
// recetas.elegir_orden, la misma función con la que decide el bot en cada consulta.
// Las rutas con receta son las que trae `p.recetas.rutas`: tampoco se listan acá.
function bloqueRecetas(perfil, p) {
    const calc = (p.recetas && p.recetas.rutas) || {};
    const sesion = p.por_cuenta || {};
    const titulo = el("h4", {}, `🧪 Receta por ruta de ${p.toml.nombre || perfil}`);
    if (!p.recetas) {
        return el("div", { class: "recetas" }, titulo, el("p", { class: "tenue" },
            "bots-info no trae recetas: falta desplegar botv3/recetas.py en /opt/botv3."));
    }
    const controles = {};
    const filas = Object.entries(calc).map(([nombre, c]) => {
        const r = c.interna;
        const receta = c.receta || { automatico: false };
        const auto = el("input", { type: "checkbox", checked: !!receta.automatico });
        const sem = el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                                  placeholder: "global", value: receta.umbral_semanal != null ? String(receta.umbral_semanal) : "" });
        const h5 = el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                                 placeholder: "global", value: receta.umbral_5h != null ? String(receta.umbral_5h) : "" });
        controles[nombre] = { auto, sem, h5, receta, cadena: c.cadena || [] };
        const d = (c.detalle || {})[c.contesta] || {};
        const contesta = c.contesta
            ? [nombreCuenta(c.contesta), el("span", { class: "tenue" },
                ` · semanal ${pct(d.semanal)}, 5 h ${pct(d["5h"])}`)]
            : c.sin_sesion ? "nadie (ninguna cuenta con sesión)" : "nadie (sin cuentas)";
        const orden = (c.orden || []).slice(1).map(nombreCuenta).join(" → ");
        return el("tr", {},
            el("td", {}, nombre, nombre !== r ? el("div", { class: "tenue" }, `antes ${r}`) : null),
            el("td", {}, el("label", {}, auto, " automático")),
            el("td", {}, sem, " % sem · ", h5, " % 5 h"),
            el("td", {}, contesta,
               c.aviso ? el("div", { class: "estado mal" }, c.aviso) : null,
               orden ? el("div", { class: "tenue" }, "respaldo: " + orden) : null));
    });

    const leer = n => {
        const v = parseInt(n.value, 10);
        return Number.isInteger(v) ? v : null;
    };
    const boton = el("button", { class: "mini", onclick: () => {
        const valor = {};
        let amplia = false;
        for (const [nombre, x] of Object.entries(controles)) {
            valor[nombre] = { automatico: x.auto.checked, umbral_semanal: leer(x.sem), umbral_5h: leer(x.h5) };
            // Encender el automático amplía si hay cuentas con sesión fuera de la
            // cadena: es lo mismo que va a calcular aplicar-propuesta.
            if (x.auto.checked && !x.receta.automatico &&
                    Object.keys(cuentasConocidas()).some(c => pagada(c) && (sesion[c] || {}).sesion &&
                                                              !x.cadena.includes(c)))
                amplia = true;
        }
        const texto = rs => Object.entries(rs).map(([n, v]) =>
            `${n} ${v.automatico ? "automático" : "cadena"}` +
            (v.umbral_semanal != null ? ` sem ${v.umbral_semanal}` : "") +
            (v.umbral_5h != null ? ` 5h ${v.umbral_5h}` : "")).join(" · ");
        proponer({ tipo: "recetas", valor, clave: "recetas", amplia,
            antes: texto(Object.fromEntries(Object.entries(controles).map(([n, x]) => [n, x.receta]))),
            despues: texto(valor) }, perfil);
    } }, `Proponer recetas de ${p.toml.nombre || perfil}`);

    return el("details", { class: "recetas" }, el("summary", {},
            `🧪 Receta por ruta de ${p.toml.nombre || perfil}: automático, umbral y quién contestaría ahora`),
        el("p", { class: "tenue" }, "Automático: usa cualquier cuenta con sesión, la menos cargada primero. ",
           "Si no, sigue la cadena de la matriz pero salta la cuenta que pasa el umbral (global en ",
           "cuentas.toml; acá va la excepción de la ruta). Si todas lo pasan, contesta la menos cargada ",
           "y avisa. Sin dato de límites no se salta nada."),
        filas.length ? el("table", {}, el("tr", {}, el("th", {}, "Ruta"), el("th", {}, "Modo"),
            el("th", {}, "Umbral (excepción)"), el("th", {}, "¿Quién contestaría ahora?")), filas)
            : el("p", { class: "tenue" }, "Este bot no tiene rutas con receta."),
        (p.recetas.problemas || []).length
            ? el("ul", { class: "avisos-cuentas" }, p.recetas.problemas.map(x => el("li", {}, x))) : null,
        filas.length ? el("div", { class: "controles-voz separado" }, boton,
           el("span", { class: "tenue" }, "«Quién contestaría» es con lo desplegado, no con lo que estás editando.")) : null);
}

/* ---------- 💳 cuentas y proveedores: historial por ciclo y costo por ruta ---------- */

function faltaHistorial(id, titulo) {
    document.getElementById(id).replaceChildren(el("h2", {}, titulo), el("p", { class: "tenue" },
        "bots-info todavía no entrega el historial (falta desplegar la versión del 30-09)."));
}

function tablaPorRuta(rutas, primera) {
    return el("table", {},
        el("tr", {}, el("th", {}, primera), el("th", {}, "Cuentas"), el("th", {}, "Semana"),
           el("th", {}, ""), el("th", {}, "Mes"), el("th", {}, "")),
        rutas.map(([clave, r]) => el("tr", {},
            el("td", {}, esPc(clave) ? clave.slice(3) : (NOMBRE_RUTA[clave] || clave)),
            el("td", { class: "tenue" }, Object.entries(r.cuentas).map(([c, n]) => `${nombreCuenta(c)} ${n}`).join(" · ")),
            el("td", { class: "num" }, String(r.consultas_semana)),
            el("td", { class: "num" }, usd(r.semana_usd)),
            el("td", { class: "num" }, String(r.consultas_mes)),
            el("td", { class: "num" }, usd(r.mes_usd)))));
}

function pintarUso() {
    const cont = document.getElementById("cuentas-uso");
    const u = info.uso_cuentas;
    const titulo = "💳 Cuentas y proveedores: uso y costo";
    if (!u) { faltaHistorial("cuentas-uso", titulo); return; }
    // Un proveedor sin cuenta pagada aparece con US$ 0 y sin renovación.
    const tarjetas = Object.entries(u.cuentas).map(([cid, c]) => {
        const actual = c.ciclos.find(x => x.actual) || c.ciclos[0];
        const consultas = Object.values(actual.rutas).reduce((s, r) => s + r.consultas, 0);
        const fallidas = Object.values(actual.rutas).reduce((s, r) => s + r.fallidas, 0);
        // Una barra por ciclo, más nuevo arriba: cuánto se CONSUMIÓ, contra el ciclo más
        // cargado de la lista. El precio se paga entero igual; la barra dice si se aprovechó.
        const volumen = ci => Object.values(ci.rutas).reduce((s, r) => s + r.peso, 0);
        const tope = Math.max(1, ...c.ciclos.map(volumen));
        const barras = c.ciclos.map(ci => {
            const n = Object.values(ci.rutas).reduce((s, r) => s + r.consultas, 0);
            const v = volumen(ci);
            return el("div", { class: "ciclo" },
                el("span", { class: "tenue" }, fechaCorta(ci.inicio).slice(0, 5)),
                el("div", { class: "barra-ciclo", title: Object.entries(ci.rutas)
                        .map(([k, r]) => `${NOMBRE_RUTA[k] || k}: ${r.consultas} · ${usd(r.usd)}`).join("\n") || "sin uso" },
                    el("span", { class: "usado", "data-ancho": String(Math.round(1000 * v / tope)) }),
                    el("span", { class: "ocioso", "data-ancho": String(Math.round(1000 * (tope - v) / tope)) })),
                el("span", { class: "num tenue" }, n ? `${n} consultas` : "sin uso"));
        });
        return el("div", { class: "cuenta-uso" },
            el("h3", {}, c.nombre),
            el("dl", { class: "dato" },
                el("dt", {}, "Precio"), el("dd", {}, !pagada(cid)
                    ? `${usd(0)} · proveedor sin cuenta pagada`
                    : `${usd(c.precio_mes_usd)} /mes · ${usd(c.usd_semana)} /semana`),
                el("dt", {}, "Renueva"), el("dd", {}, !pagada(cid) ? "no tiene límite semanal" : [
                    c.renueva || (c.renueva_origen === "medido" ? "cada 7 días" : "lun 00:00"),
                    c.renueva_origen === "medido" ? el("span", { class: "insignia", title: "Leído del límite de la cuenta" }, "medido")
                    : c.renueva_supuesto ? el("span", { class: "insignia", title: "Pon el real en «Precio y renovación»" }, "supuesto") : null,
                    el("div", { class: "tenue" }, "próxima: " + fechaCorta(c.proxima_renovacion))]),
                el("dt", {}, "Este ciclo"), el("dd", {}, `${consultas} consultas`,
                    fallidas ? el("span", { class: "tenue" }, ` · ${fallidas} fallidas`) : null,
                    el("div", { class: "tenue" }, `ocioso ${usd(actual.ocioso_usd)}`,
                       actual.reparto === "consultas" ? " · repartido por consultas (faltan tokens)" : ""))),
            el("div", { class: "ciclos" }, barras));
    });

    const rutas = Object.entries(u.por_ruta).filter(([clave]) => !esPc(clave))
        .sort((a, b) => b[1].mes_usd - a[1].mes_usd);
    cont.replaceChildren(el("h2", {}, titulo),
        el("p", { class: "tenue" }, `Total ${usd(u.total_mes_usd)} /mes. Cada semana se reparte el precio de la cuenta `,
           "entre las rutas que la usaron en ese ciclo, según los tokens (salida 5× entrada, caché 0,1× en Claude; total en Codex). ",
           "Lo que nadie usó queda como «ocioso»: también se pagó. Un proveedor sin cuenta pagada aparece con US$ 0."),
        el("div", { class: "rejilla tres" }, tarjetas),
        el("h3", {}, "Por ruta (bots y sesiones de la Pi)"),
        rutas.length ? tablaPorRuta(rutas, "Ruta")
            : el("p", { class: "tenue" }, "Todavía no hay consultas anotadas: el libro empieza con el despliegue del 30-09."));
    aplicarAnchos(cont);
}

/* ---------- ⚙️ rendimiento por motor ---------- */

function pintarRendimiento() {
    const u = info.uso_cuentas;
    const titulo = "⚙️ Rendimiento por motor";
    if (!u) { faltaHistorial("rendimiento", titulo); return; }
    const rendimiento = Array.isArray(u.rendimiento) ? u.rendimiento : [];
    const tabla = rendimiento.length ? el("table", {},
        el("tr", {}, el("th", {}, "Cuenta / motor / modelo"),
           el("th", {}, "Intentos"), el("th", {}, "Falla"), el("th", {}, "p50 s"),
           el("th", {}, "p90 s"), el("th", {}, "Tokens med."), el("th", {}, "👍"),
           el("th", {}, "👎"), el("th", {}, "Costo útil")),
        rendimiento.map(r => el("tr", {},
            el("td", {}, `${nombreCuenta(r.cuenta)} · ${r.motor || "—"} · ${r.modelo || "sin modelo"}`),
            el("td", { class: "num" }, String(r.intentos || 0)),
            el("td", { class: "num" }, `${Math.round(100 * Number(r.tasa_falla || 0))} %`),
            el("td", { class: "num" }, r.p50_s == null ? "—" : String(r.p50_s)),
            el("td", { class: "num" }, r.p90_s == null ? "—" : String(r.p90_s)),
            el("td", { class: "num" }, r.tokens_medianos == null ? "—" : String(r.tokens_medianos)),
            el("td", { class: "num" }, String(r.positivos || 0)),
            el("td", { class: "num" }, String(r.negativos || 0)),
            el("td", { class: "num" }, r.costo_respuesta_util_usd == null ? "—"
                : `${usd(r.costo_respuesta_util_usd)} / ${r.base}`))))
        : el("p", { class: "tenue" }, "Todavía no hay intentos de los últimos 30 días.");
    document.getElementById("rendimiento").replaceChildren(el("h2", {}, titulo),
        el("p", { class: "tenue" }, "Las consultas de los bots de los últimos 30 días, por cuenta y motor: ",
           "cuánto fallan, cuánto demoran y lo que cuesta cada respuesta útil."),
        tabla);
}

/* ---------- 🖥️ uso desde los PC (encargo 08) ---------- */

function pintarPcs() {
    const u = info.uso_cuentas;
    const titulo = "🖥️ Uso desde los PC";
    if (!u) { faltaHistorial("pcs", titulo); return; }
    const pcs = Object.entries(u.por_ruta).filter(([clave]) => esPc(clave))
        .sort((a, b) => b[1].mes_usd - a[1].mes_usd);
    document.getElementById("pcs").replaceChildren(el("h2", {}, titulo),
        el("div", { class: "aviso ojo" }, u.alcance),
        pcs.length ? tablaPorRuta(pcs, "Equipo")
            : el("p", { class: "tenue" }, "Ningún PC reportó uso en los ciclos que se muestran."));
}

/* ---------- 🗓️ registro: precio, renovación y topes de cada cuenta ---------- */

function pintarRegistro() {
    const u = info.uso_cuentas;
    const titulo = "🗓️ Precio, renovación y topes";
    if (!u) { faltaHistorial("registro", titulo); return; }
    const campos = {};
    const pagadas = Object.entries(u.cuentas).filter(([cid]) => pagada(cid));
    // El registro es común a los dos bots, pero aplicar-propuesta pide un perfil válido.
    const perfil = Object.keys(info.perfiles)[0];
    const form = el("div", { class: "registro" }, pagadas.map(([cid, c]) => {
        campos[cid] = {
            precio: el("input", { type: "number", min: "0", max: "1000", step: "1", class: "numero",
                                  value: String(c.precio_mes_usd ?? "") }),
            renueva: el("input", { type: "text", maxlength: "9", placeholder: "lun 09:00",
                                   value: c.renueva || "" }),
            semanal: el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                                    value: String((info.margen.cuentas[cid] || {}).umbral_semanal ?? "") }),
            h5: el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                               value: String((info.margen.cuentas[cid] || {}).umbral_5h ?? "") }),
            encargosSem: el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                                        placeholder: "igual al bot", value: String(c.tope_encargos_semanal ?? "") }),
            encargos5h: el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                                       placeholder: "igual al bot", value: String(c.tope_encargos_5h ?? "") }),
            quemarHoras: el("input", { type: "number", min: "0", max: "48", step: "1", class: "numero",
                                        value: String(c.quemar_horas ?? "") }),
            quemarTope: el("input", { type: "number", min: "1", max: "100", step: "1", class: "numero",
                                       value: String(c.quemar_tope ?? "") }),
        };
        return el("div", { class: "controles-voz registro-cuenta" }, el("strong", {}, c.nombre),
            el("label", {}, "US$/mes ", campos[cid].precio),
            el("label", {}, "renueva ", campos[cid].renueva),
            el("label", {}, "Tope semanal % ", campos[cid].semanal),
            el("label", {}, "Tope 5 h % ", campos[cid].h5),
            el("label", {}, "Encargos semanal % ", campos[cid].encargosSem),
            el("label", {}, "Encargos 5 h % ", campos[cid].encargos5h),
            el("label", {}, "Quemar últimas h ", campos[cid].quemarHoras),
            el("label", {}, "Quemar hasta % ", campos[cid].quemarTope),
            el("span", { class: "tenue" }, "cada tope de arriba lo usan el bot y los encargos; los cuatro siguientes sólo encargos"));
    }), el("div", { class: "controles-voz separado" },
        el("button", { class: "mini", disabled: !perfil, onclick: () => {
            const umbral = campo => campo.value === "" ? undefined : Number(campo.value);
            const opcional = campo => campo.value === "" ? null : Number(campo.value);
            const valor = Object.fromEntries(Object.entries(campos).map(([cid, f]) =>
                [cid, { precio_mes_usd: parseInt(f.precio.value, 10) || 0,
                        renueva: f.renueva.value.trim().toLowerCase(),
                        umbral_semanal: umbral(f.semanal), umbral_5h: umbral(f.h5),
                        tope_encargos_semanal: opcional(f.encargosSem), tope_encargos_5h: opcional(f.encargos5h),
                        quemar_horas: opcional(f.quemarHoras), quemar_tope: opcional(f.quemarTope) }]));
            proponer({ tipo: "registro_cuentas", valor, clave: "registro",
                antes: pagadas.map(([cid, c]) => `${cid} ${c.precio_mes_usd} ${c.renueva || "—"} sem ${(info.margen.cuentas[cid] || {}).umbral_semanal ?? "—"} 5h ${(info.margen.cuentas[cid] || {}).umbral_5h ?? "—"}`).join(" · "),
                despues: Object.entries(valor).map(([cid, v]) => `${cid} ${v.precio_mes_usd} ${v.renueva || "—"} sem ${v.umbral_semanal ?? "—"} 5h ${v.umbral_5h ?? "—"} encargos ${v.tope_encargos_semanal ?? "bot"}/${v.tope_encargos_5h ?? "bot"} quemar ${v.quemar_horas ?? 0}h→${v.quemar_tope ?? "—"}`).join(" · ") },
                perfil);
        } }, "Proponer cambios de registro")));
    document.getElementById("registro").replaceChildren(el("h2", {}, titulo),
        el("p", { class: "tenue" }, "«Renueva» es el día y la hora en que se reinicia el límite semanal, p. ej. ",
           "«jue 14:00»: ahí empieza cada ciclo del historial. Se ve en la app (Claude: Ajustes → Uso; Codex: ",
           "chatgpt.com/codex/settings/usage). Vacío, se usa lo medido en la cuenta o, si no hay, lunes 00:00. ",
           "Los topes se aplican sin reiniciar: el bot los relee dentro de un minuto."),
        form,
        el("p", { class: "tenue" }, "Las colas de encargos esperan cuando el % de ahora más el pronóstico de su próxima fase pasa el tope: ",
           "cada cola dice en 🧵 Encargos cuánto le falta y cuándo sigue. El aviso previo antes de llegar al tope se pone en 🧵 Encargos → 🔔 Avisos."));
}

/* ---------- arranque ---------- */

document.getElementById("actualizar").addEventListener("click", cargar);
cockpit.transport.wait(cargar);
