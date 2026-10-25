/*
 * ⏰ Programados de "🍇 Raspberry Pi" (encargo 22, documento 29): todo lo que la Pi tiene
 * programado, en un solo lugar y con todos sus datos.
 *
 * Lo junta programados.py (stdlib, sin sudo): timers de systemd del sistema y del usuario, cron
 * y los temporizadores del bot. Esta página lo llama con cockpit.spawn (comando fijo, sin
 * argumentos que vengan de afuera) y dibuja lo que trae:
 *   {momento, tareas: [{estado, nombre, fuente, legible, proxima, ultima, resultado, …}], no_visibles}
 * Lee sólo campos que el recolector escribe (una prueba lo cuida).
 *
 * Un `Environment=` nunca llega acá con su valor: el recolector entrega sólo los nombres.
 * Las acciones pasan por órdenes fijas: sólo los timers del sistema requieren `sudo -n`.
 *
 * Usa `$`, `el`, `error`, `correr`, `cuando` y `hace` de sistema.js y barraNodo de la barra.
 */
"use strict";

const PROGRAMADOS = ["python3", "/home/dcifu004/.local/share/cockpit/sistema/programados.py"];

// El orden es el del documento 29: ✅ al día, ❌ la última falló, ⏳ nunca corrió, 💤 vencido, ⚠️ huérfano.
const ESTADOS_PROG = {
    al_dia: ["✅", "Al día"], fallo: ["❌", "La última falló"], nunca: ["⏳", "Nunca corrió"],
    vencido: ["💤", "Vencido"], huerfano: ["⚠️", "Huérfano"], pausado: ["⏸️", "Pausado"],
};

const progVista = { datos: null, estado: "", fuente: "", abiertas: new Set() };

const claveTarea = t => `${t.fuente}|${t.nombre}`;
const NOMBRE_SEGURO = /^[A-Za-z0-9@_.-]{1,64}$/;
let autorizacionTimers = null;

function timerBase(t) {
    return String(t.nombre || "").replace(/\.timer$/, "");
}

// `sudo -l` sin terminal corta las líneas y `NOPASSWD:` queda solo en la primera del bloque: se
// juntan los espacios y cada entrada vale si el último tag antes de ella es NOPASSWD.
function autorizaTimers(salida) {
    const s = String(salida).replace(/\s+/g, " ");
    return ["timer-pausar", "timer-reanudar", "timer-correr"].every(a => {
        const i = s.search(new RegExp(`/usr/local/bin/nodo-servicio ${a} \\*(?:[,\\s]|$)`));
        if (i < 0) return false;
        const tags = [...s.slice(0, i).matchAll(/\b(NOPASSWD|PASSWD|SETENV|NOSETENV|NOEXEC|EXEC):/g)].map(m => m[1]);
        return tags.length > 0 && tags.lastIndexOf("NOPASSWD") > tags.lastIndexOf("PASSWD");
    });
}

async function puedeAccionarTimers() {
    if (!autorizacionTimers) autorizacionTimers = cockpit.spawn(["sudo", "-n", "-l"], { err: "message" })
        .then(autorizaTimers, () => false);
    return autorizacionTimers;
}

function accionBoton(t, accion, texto, boton) {
    const nombres = { pausar: "pausar", reanudar: "reanudar", correr: "correr ahora" };
    boton.addEventListener("click", async () => {
        const detalle = t.fuente === "timer del sistema"
            ? (accion === "pausar" ? "Se ejecutará stop + disable: no correrá hasta reanudar, tampoco después de reiniciar."
                : accion === "reanudar" ? "Se ejecutará enable --now: si es Persistent, puede correr al tiro."
                : `Se arrancará ahora ${t.servicio || `${timerBase(t)}.service`} con --no-block.`)
            : t.fuente === "timer de usuario"
                ? (accion === "pausar" ? "Se ejecutará stop + disable (systemctl --user): no correrá hasta reanudar, tampoco después de reiniciar."
                    : accion === "reanudar" ? "Se ejecutará enable --now (systemctl --user): si es Persistent, puede correr al tiro."
                    : `Se arrancará ahora ${t.servicio || `${timerBase(t)}.service`} con --no-block.`)
                : (accion === "pausar" ? "Dejará de contar hasta que lo reanudes."
                    : accion === "reanudar" ? "Volverá a contar desde donde quedó."
                    : "Se marcará para sonar ahora.");
        if (!confirm(`¿${nombres[accion]} ${t.nombre}?\n\n${detalle}`)) return;
        boton.disabled = true;
        try {
            let salida;
            if (t.fuente === "timer del sistema") {
                salida = await raizProgramado(accion, timerBase(t));
            } else if (t.fuente === "timer de usuario") {
                if (!NOMBRE_SEGURO.test(timerBase(t)) || timerBase(t).includes("..")) throw new Error("nombre de timer inválido");
                salida = await accionLocal(["usuario", accion, timerBase(t)]);
            } else if (t.fuente === "bot" && NOMBRE_SEGURO.test(t.identificador || "")) {
                salida = await accionLocal(["bot", accion, t.identificador]);
            } else throw new Error("tarea no accionable");
            boton.textContent = "✓ hecho";
            await pintarProgramados();
        } catch (e) { error(e.message || String(e)); boton.disabled = false; }
    });
    return boton;
}

// programado-accion.py responde JSON aun cuando falla ({ok:false, error}); el usuario ve solo el error.
async function accionLocal(args) {
    let salida;
    try { salida = await correr(["python3", "/home/dcifu004/.local/share/cockpit/sistema/programado-accion.py", ...args]); }
    catch (e) {
        let d = null;
        try { d = JSON.parse(e.message); } catch (x) { /* salida no JSON */ }
        throw new Error(d?.error || e.message || String(e));
    }
    const resultado = JSON.parse(salida);
    if (!resultado.ok) throw new Error(resultado.error || "falló");
    return resultado;
}

// Pasa por programado-accion.py: él hace el `sudo -n nodo-servicio` y deja la línea en avisos.jsonl.
async function raizProgramado(accion, nombre) {
    if (!(await puedeAccionarTimers())) throw new Error("falta autorizar en sudoers");
    return accionLocal(["sistema", accion, nombre]);
}

// «en 4 h», «en 12 min»; fechas pasadas, «hace 3 h». Sin fecha, «—».
function relativoProg(iso) {
    const ms = new Date(iso).getTime() - Date.now();
    if (!iso || Number.isNaN(ms)) return "—";
    const min = Math.round(Math.abs(ms) / 60000);
    const txt = min < 1 ? "ahora" : min < 60 ? `${min} min` : min < 2880 ? `${Math.floor(min / 60)} h` : `${Math.floor(min / 1440)} días`;
    return min < 1 ? txt : ms >= 0 ? `en ${txt}` : `hace ${txt}`;
}

// Orden por próxima corrida; las que no tienen, al final.
function ordenarProg(tareas) {
    const t = x => (x.proxima ? new Date(x.proxima).getTime() : Infinity);
    return [...tareas].sort((a, b) => t(a) - t(b) || String(a.nombre).localeCompare(String(b.nombre)));
}

function contarProg(tareas) {
    const r = {};
    for (const t of tareas) r[t.estado] = (r[t.estado] || 0) + 1;
    return r;
}

function dato(valor) {
    return valor == null || valor === "" ? "—" : String(valor);
}

function detalleProg(t) {
    const si = x => (x == null ? "—" : x ? "sí" : "no");
    const e = t.entorno || { variables: [], archivos: [] };
    const filasDetalle = [
        ["Descripción", t.descripcion], ["Expresión original", t.expresion], ["Se lee así", t.legible],
        ["Próxima", t.proxima ? `${cuando(t.proxima)} (${relativoProg(t.proxima)})` : null],
        ["Última", t.ultima ? `${cuando(t.ultima)} (${relativoProg(t.ultima)})` : null],
        ["Resultado de la última", t.resultado ? t.resultado + (t.codigo_salida != null ? ` · código ${t.codigo_salida}` : "") : null],
        ["Duración", t.duracion_s != null ? `${String(t.duracion_s).replace(".", ",")} s` : null],
        ["Usuario", t.usuario], ["Comando", t.comando], ["Archivo de la unidad", t.unidad],
        ["Persistent", si(t.persistente)], ["Habilitado", si(t.habilitado)], ["Proyecto", t.proyecto],
        ["Variables de entorno", e.variables.length ? e.variables.join(", ") + " (los valores no se muestran)" : null],
        ["Archivos de entorno", e.archivos.length ? e.archivos.join(", ") : null],
    ];
    const root = t.fuente === "timer del sistema";
    const protegido = Boolean(t.protegido);
    const motivoAccion = protegido ? (t.motivo_accion || "protegido: no se modifica desde el navegador") : root ? "falta autorizar en sudoers" : null;
    const accionable = t.fuente === "timer del sistema" || t.fuente === "timer de usuario" || t.fuente === "bot";
    const permite = a => !Array.isArray(t.acciones) || t.acciones.includes(a);
    const acciones = accionable && (!Array.isArray(t.acciones) || t.acciones.length) && !t.banderas.includes("huerfano")
        ? el("div", { class: "fila-botones prog-acciones", "data-root-action": root ? "true" : "false", "data-protegido": protegido ? "true" : "false" },
            el("span", { class: "tenue" }, motivoAccion || ""),
            t.estado === "al_dia" && permite("pausar") ? accionBoton(t, "pausar", "Pausar", el("button", { class: "mini", disabled: Boolean(motivoAccion) }, "⏸ Pausar")) : null,
            t.estado === "pausado" && permite("reanudar") ? accionBoton(t, "reanudar", "Reanudar", el("button", { class: "mini", disabled: Boolean(motivoAccion) }, "▶ Reanudar")) : null,
            permite("correr") ? accionBoton(t, "correr", "Correr ahora", el("button", { class: "mini", disabled: Boolean(motivoAccion) }, "▶ Ahora")) : null) : null;
    return el("div", { class: "prog-detalle" },
        t.motivo ? el("div", { class: "aviso ojo" }, t.motivo) : null,
        el("dl", { class: "dato prog-datos" }, filasDetalle.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, dato(v))])),
        acciones,
        t.journal.length ? el("pre", { class: "log" }, t.journal.join("\n")) : el("p", { class: "tenue" }, "Sin líneas de journal."));
}

function filaProg(t) {
    const [icono, texto] = ESTADOS_PROG[t.estado] || ["•", t.estado];
    const abierta = progVista.abiertas.has(claveTarea(t));
    const alternar = () => {
        const k = claveTarea(t);
        if (progVista.abiertas.has(k)) progVista.abiertas.delete(k); else progVista.abiertas.add(k);
        dibujarProg();
    };
    const fila = el("tr", { class: "prog-fila", "data-estado": t.estado, tabindex: "0", role: "button",
                            "aria-expanded": abierta ? "true" : "false", onclick: alternar,
                            onkeydown: ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alternar(); } } },
        el("td", { title: texto }, `${icono} ${texto}`),
        el("td", {}, el("strong", {}, t.nombre), t.proyecto ? el("span", { class: "chip" }, t.proyecto) : null),
        el("td", { class: "tenue" }, t.fuente),
        el("td", {}, dato(t.legible)),
        el("td", { class: "num" }, t.proxima ? `${cuando(t.proxima)} · ${relativoProg(t.proxima)}` : "—"),
        el("td", { class: "num tenue" }, t.ultima ? relativoProg(t.ultima) : "nunca"),
        el("td", { class: "tenue" }, dato(t.resultado)));
    return abierta ? [fila, el("tr", { class: "prog-extra" }, el("td", { colspan: "7" }, detalleProg(t)))] : [fila];
}

function resumenProg(d) {
    const por = contarProg(d.tareas);
    const proxima = ordenarProg(d.tareas).find(t => t.proxima);
    return el("div", { class: "tarjeta" },
        el("div", { class: "resumen" }, `${d.tareas.length} tareas programadas`,
            el("span", { class: "tenue" }, `medido ${hace(d.momento)}`),
            el("button", { class: "mini", onclick: () => pintarProgramados().catch(e => error(e.message || String(e))) }, "↻ Refrescar")),
        el("p", {}, Object.entries(ESTADOS_PROG).map(([k, [icono, texto]]) =>
            el("span", { class: "chip" }, `${icono} ${texto}: ${por[k] || 0}`))),
        el("p", { class: "tenue" }, proxima
            ? `Lo próximo: ${proxima.nombre} (${dato(proxima.legible)}) ${relativoProg(proxima.proxima)}, a las ${cuando(proxima.proxima)}.`
            : "Ninguna tiene próxima corrida."));
}

function filtrosProg(d) {
    const fuentes = [...new Set(d.tareas.map(t => t.fuente))].sort();
    const sel = (valor, primera, opciones, alCambiar) => {
        const s = el("select", { onchange: ev => alCambiar(ev.target.value) }, el("option", { value: "" }, primera),
            opciones.map(([v, txt]) => el("option", { value: v }, txt)));
        s.value = valor;
        return s;
    };
    return el("div", { class: "prog-filtros" },
        sel(progVista.fuente, "Todas las fuentes", fuentes.map(f => [f, f]), v => { progVista.fuente = v; dibujarProg(); }),
        sel(progVista.estado, "Todos los estados", Object.entries(ESTADOS_PROG).map(([k, [i, t]]) => [k, `${i} ${t}`]),
            v => { progVista.estado = v; dibujarProg(); }));
}

// Vencidas y huérfanas, con su motivo: son las candidatas a limpiar (en la fase 2, desde acá).
function limpiezaProg(d) {
    const malas = ordenarProg(d.tareas).filter(t => t.banderas.includes("vencido") || t.banderas.includes("huerfano"));
    if (!malas.length) return null;
    return el("div", { class: "tarjeta" }, el("h2", {}, "💤 Candidatas a limpiar"),
        el("p", { class: "tenue" }, "Vencidas (sin próxima corrida) o huérfanas (el timer existe, su servicio no). ",
           "Por ahora sólo se ven: borrarlas es de la fase 2."),
        el("ul", {}, malas.map(t => el("li", {}, el("strong", {}, t.nombre), ` · ${t.fuente} · `, dato(t.motivo),
            t.unidad ? el("span", { class: "tenue" }, ` (${t.unidad})`) : null))));
}

function noVisiblesProg(d) {
    return el("div", { class: "tarjeta" }, el("h2", {}, "No visible desde acá"),
        el("ul", {}, d.no_visibles.map(n => el("li", {}, el("strong", {}, n.fuente), ` — ${n.motivo}`))));
}

function dibujarProg() {
    const d = progVista.datos;
    if (!d) return;
    const cont = $("[data-panel=programados]");
    const visibles = ordenarProg(d.tareas).filter(t => (!progVista.estado || t.estado === progVista.estado)
        && (!progVista.fuente || t.fuente === progVista.fuente));
    const tabla = el("table", { class: "prog-tabla" },
        el("thead", {}, el("tr", {}, ["Estado", "Tarea", "Fuente", "Cuándo", "Próxima", "Última", "Resultado"].map(x => el("th", {}, x)))),
        el("tbody", {}, visibles.flatMap(filaProg)));
    cont.replaceChildren(resumenProg(d), limpiezaProg(d),
        el("div", { class: "tarjeta" }, el("h2", {}, "Tareas, por próxima corrida"), filtrosProg(d),
            visibles.length ? tabla : el("p", { class: "tenue" }, "Ninguna tarea con ese filtro."),
            el("p", { class: "tenue" }, "Toca una fila para ver el detalle y el journal.")),
        noVisiblesProg(d));
    if (d.tareas.some(t => t.fuente === "timer del sistema")) {
        puedeAccionarTimers().then(ok => {
            if (!ok) return;
            cont.querySelectorAll('[data-root-action="true"][data-protegido="false"]').forEach(caja => {
                caja.querySelector("span").textContent = "";
                caja.querySelectorAll("button").forEach(b => { b.disabled = false; });
            });
        });
    }
    barraNodo.leido(d.momento, "Es la hora en que corrió el recolector.");
}

async function pintarProgramados() {
    const cont = $("[data-panel=programados]");
    if (!progVista.datos) cont.replaceChildren(el("p", { class: "tenue" }, "leyendo…"));
    try {
        progVista.datos = JSON.parse(await correr(PROGRAMADOS));
    } catch (e) {
        cont.replaceChildren(el("div", { class: "aviso rojo" },
            "No pude leer las tareas programadas: " + (e.message || e) +
            ". ¿Está programados.py instalado junto a la página (~/.local/share/cockpit/sistema)?"));
        return;
    }
    dibujarProg();
}
