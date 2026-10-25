/*
 * Pestaña "Nodo" de Cockpit: botones para entrar a Claude y a Codex en la Pi.
 *
 * Lo canónico vive en el vault (10-Proyectos/11-Pi5/pi/cockpit-nodo/). Se instala
 * copiando la carpeta, sin compilar nada:
 *     rm -rf ~/.local/share/cockpit/nodo && cp -r <esta carpeta> ~/.local/share/cockpit/nodo
 * y recargando Cockpit en el navegador.
 *
 * Doctrina:
 *  - Cada botón entra a UNA sesión de tmux fija o la crea (`new-session -A`). Cerrar la
 *    terminal mata al cliente de tmux, no a la sesión: el agente sigue trabajando.
 *  - El agente se lanza dentro de `bash -lc '<cli>; exec bash -l'`, igual que la sesión
 *    `pi` que ya existía. Si el agente termina, queda el shell y la sesión no desaparece.
 *  - Si el agente terminó y la sesión quedó en bash, el botón lo relanza escribiendo el
 *    mismo comando fijo en el pane (sólo con bash ocioso en primer plano).
 *  - Nada corre como root. Los comandos son fijos; la página no arma comandos con texto
 *    que escribe el usuario (ver 16 - Plan de seguridad: sudo sigue sin contraseña).
 */
"use strict";

const AGENTES = {
    claude: {
        nombre: "Claude",
        sesion: "pi",
        // Igual que la sesión que corría el 24-09-2026: Remote Control la deja visible
        // en la app de Claude y en claude.ai/code.
        // Con la cuenta elegida en la tarjeta: el CLAUDE_CONFIG_DIR que trae bots-info
        // para esa cuenta (validado en comun.js), nunca texto escrito en la página.
        get lanzar() {
            const d = dirCuenta(cuentaClaude);
            return (d ? `CLAUDE_CONFIG_DIR=${d} ` : "") +
                "claude --remote-control Pi --permission-mode default";
        },
        esAgente: p => p.comm === "claude",
    },
    codex: {
        nombre: "Codex",
        sesion: "codex",
        lanzar: "codex",
        // /usr/local/bin/codex es un ELF nativo (verificado el 24-09-2026), así que
        // su comm es "codex". Nunca matchear por args: el bash que lo lanza también
        // lleva "codex" en la línea de comandos.
        esAgente: p => p.comm === "codex",
    },
};

/* ---------- cuenta de la sesión interactiva (29-09-2026) ---------- */

// Con qué cuenta se lanza Claude en la sesión `pi`. Se guarda como preferencia de
// dcifu004 y NO pasa por aplicar-propuesta: esta sesión ya corre como dcifu004 y
// lee lo mismo con cualquier cuenta, así que elegirla no amplía ningún permiso,
// sólo cambia quién paga (la regla de las propuestas es para lo que corre como
// otro usuario o pide root). Codex tiene una sola cuenta: no hay nada que elegir.
// El primer lanzamiento con una cuenta sin sesión muestra el login de Claude en la
// misma terminal.
//
// Encargo 13: la lista de cuentas (nombre y config dir) ya no se escribe acá. Llega de
// bots-info por ../comun/comun.js, la misma lista que usan 🤖 y 💳. Como esta página es la que se
// usa cuando algo anda mal, la última lista leída se guarda en este navegador: si
// bots-info no contesta se usa esa, y se dice. Sin lista ni copia, Claude se abre con
// la configuración de siempre de esta Pi y el selector queda apagado.
const CACHE_CUENTAS = "nodo:cuentas-interactivas";
const PREFERENCIAS = ".config/nodo/cuentas-interactivas.json";
let cuentasClaude = {};
let origenCuentas = "ninguna";
let cuentaClaude = null;
let limitesCuentas = {};

function dirCuenta(id) {
    const d = cuentasClaude[id] && cuentasClaude[id].dir;
    return d ? `${home}/${d}` : null;
}

async function leerCuentas() {
    let lista = [];
    try {
        const info = await leerBotsInfo();
        lista = cuentasInteractivas(info.cuentas || {});
        limitesCuentas = (info.margen && info.margen.cuentas) || {};
        if (lista.length) {
            origenCuentas = "bots-info";
            try { localStorage.setItem(CACHE_CUENTAS, JSON.stringify(info.cuentas)); } catch (e) { /* sin storage */ }
        }
    } catch (e) { /* sudo pide clave o bots-info falló: se prueba la copia */ }
    if (!lista.length) {
        try {
            lista = cuentasInteractivas(JSON.parse(localStorage.getItem(CACHE_CUENTAS)) || {});
            if (lista.length) origenCuentas = "copia";
        } catch (e) { lista = []; }
    }
    cuentasClaude = Object.fromEntries(lista);
    // Por defecto, la que usa la configuración de siempre (config dir vacío).
    const deSiempre = lista.find(([, c]) => !c.dir);
    cuentaClaude = deSiempre ? deSiempre[0] : (lista[0] || [null])[0];
}

async function leerPreferencia() {
    try {
        const p = await cockpit.file(`${home}/${PREFERENCIAS}`, { syntax: JSON }).read();
        if (p && cuentasClaude[p.claude]) cuentaClaude = p.claude;
    } catch (e) { /* sin archivo: la de siempre */ }
}

async function guardarPreferencia(id) {
    await cockpit.spawn(["mkdir", "-p", `${home}/.config/nodo`]);
    await cockpit.file(`${home}/${PREFERENCIAS}`, { syntax: JSON })
        .modify(v => ({ ...(v || {}), claude: id }));
    cuentaClaude = id;
}

async function correoDe(id) {
    const d = dirCuenta(id);
    try {
        const c = await cockpit.file(d ? `${d}/.claude.json` : `${home}/.claude.json`,
                                     { syntax: JSON }).read();
        return (c && c.oauthAccount && c.oauthAccount.emailAddress) || null;
    } catch (e) {
        return null;
    }
}

// Medido en el proceso, no en la preferencia: la sesión abierta sigue con la cuenta
// con que nació hasta que se relance. /proc/<pid>/environ es legible por su dueño.
async function cuentaDelProceso(pid) {
    const env = await correr(["cat", `/proc/${pid}/environ`]);
    const m = env.split("\0").find(v => v.startsWith("CLAUDE_CONFIG_DIR="));
    const dir = m ? m.slice("CLAUDE_CONFIG_DIR=".length).replace(/\/+$/, "") : null;
    return Object.keys(cuentasClaude).find(id => dirCuenta(id) === dir) || dir;
}

const REFRESCO_MS = 10000;
const enc = new TextEncoder();

let home = "/";
let canal = null;
let term = null;
let ajuste = null;
let observador = null;

// El tema (sigue al de Cockpit) lo aplica ../comun/tema.js al cargarse.

/* ---------- estado de las sesiones ---------- */

function correr(args) {
    // tmux sin servidor sale con error: eso es "no hay sesiones", no una falla.
    return cockpit.spawn(args, { err: "ignore" }).catch(() => "");
}

function duracion(seg) {
    const min = Math.floor(seg / 60);
    if (min < 1) return "menos de un minuto";
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    if (h < 48) return `${h} h ${min % 60} min`;
    return `${Math.floor(h / 24)} días`;
}

function miles(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".", ",") + " M";
    if (n >= 1e3) return Math.round(n / 1e3) + " k";
    return String(n);
}

async function leerEstado() {
    // Separador "|" y no tab: tmux 3.5 reemplaza los caracteres de control del
    // formato por "_" (sale "pi_1"), y el split no encontraba nada.
    const [ses, panes, psArgs, psComm] = await Promise.all([
        correr(["tmux", "list-sessions", "-F", "#{session_name}|#{session_attached}"]),
        correr(["tmux", "list-panes", "-a", "-F", "#{session_name}|#{pane_pid}"]),
        correr(["ps", "-eo", "pid=,ppid=,etimes=,args="]),
        correr(["ps", "-eo", "pid=,comm="]),
    ]);

    const sesiones = {};
    for (const l of ses.split("\n")) {
        const [n, conectados] = l.split("|");
        if (n) sesiones[n] = { conectados: parseInt(conectados, 10) || 0, pids: [] };
    }
    for (const l of panes.split("\n")) {
        const [n, pid] = l.split("|");
        if (sesiones[n]) sesiones[n].pids.push(parseInt(pid, 10));
    }

    // comm es el último campo, así que puede traer espacios sin romper el parseo.
    const comm = {};
    for (const l of psComm.split("\n")) {
        const m = l.trim().match(/^(\d+)\s+(.*)$/);
        if (m) comm[m[1]] = m[2];
    }
    const procesos = {};
    const hijos = {};
    for (const l of psArgs.split("\n")) {
        const m = l.trim().match(/^(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/);
        if (!m) continue;
        const p = { pid: +m[1], ppid: +m[2], seg: +m[3], args: m[4], comm: comm[m[1]] || "" };
        procesos[p.pid] = p;
        (hijos[p.ppid] = hijos[p.ppid] || []).push(p.pid);
    }

    // Recorre en anchura desde el pane (que puede ser el agente mismo o el bash que
    // lo lanzó): el primero que calza es el agente de más arriba.
    function buscar(raiz, calza) {
        const cola = [raiz];
        while (cola.length) {
            const pid = cola.shift();
            const p = procesos[pid];
            if (p && calza(p)) return p;
            cola.push(...(hijos[pid] || []));
        }
        return null;
    }

    const res = {};
    for (const [id, a] of Object.entries(AGENTES)) {
        const s = sesiones[a.sesion];
        let proc = null;
        if (s) for (const pid of s.pids) { proc = proc || buscar(pid, a.esAgente); }
        res[id] = { sesion: s || null, proc };
    }
    return res;
}

async function leerUso() {
    try {
        return await cockpit.file("/opt/nodo/datos/uso.json", { syntax: JSON }).read();
    } catch (e) {
        return null; // volumen cerrado o timer sin correr: no es motivo para romper la página
    }
}

function pintar(id, info, uso) {
    const t = document.getElementById("t-" + id);
    const punto = t.querySelector('[data-rol="punto"]');
    const estado = t.querySelector('[data-rol="estado"]');
    const extra = t.querySelector('[data-rol="extra"]');
    const a = AGENTES[id];

    punto.classList.toggle("vivo", !!info.proc);
    const conectados = info.sesion && info.sesion.conectados
        ? ` · ${info.sesion.conectados} conectado${info.sesion.conectados > 1 ? "s" : ""}`
        : "";

    if (info.proc) {
        estado.textContent = `Corriendo hace ${duracion(info.proc.seg)}${conectados}`;
    } else if (info.sesion) {
        estado.textContent = `Sesión "${a.sesion}" abierta, sin ${a.nombre} adentro${conectados}`;
    } else {
        estado.textContent = `Sin sesión: el botón la crea`;
    }

    const notas = [];
    if (id === "claude") {
        pintarRemoto(info);
        pintarCuenta(info);
        if (info.proc && info.proc.args.includes("--remote-control"))
            notas.push("Remote Control activo: también la ves en la app de Claude.");
        const hoy = uso && uso.claude && uso.claude.disponible && uso.claude.hoy;
        if (hoy)
            notas.push(`Hoy en esta Pi: ${hoy.mensajes} mensajes, ${miles(hoy.salida)} de salida.`);
    } else {
        notas.push("Usa la cuota de tu cuenta de ChatGPT.");
    }
    extra.textContent = notas.join(" ");
}

async function pintarCuenta(info) {
    const sel = document.getElementById("cuenta-claude");
    const nota = document.getElementById("cuenta-nota");
    const margen = document.getElementById("cuenta-margen");
    if (!sel.options.length) {
        for (const [id, c] of Object.entries(cuentasClaude))
            sel.append(new Option(c.nombre, id));
    }
    if (!cuentaClaude) {
        sel.disabled = true;
        margen.replaceChildren();
        nota.textContent = "No pude leer la lista de cuentas (sudo -n /usr/local/bin/bots-info) y no hay " +
            "una copia en este navegador: Claude se abre con la configuración de siempre de esta Pi.";
        return;
    }
    sel.value = cuentaClaude;
    // Cuánto margen le queda a la cuenta elegida (lo mismo que muestra 💳 Cuentas).
    margen.replaceChildren(limitesCuentas[cuentaClaude] ? chipsMargen(limitesCuentas[cuentaClaude]) : "");
    const correo = await correoDe(cuentaClaude);
    const partes = [correo ? `Sesión: ${correo}.` : "Sin sesión: al abrir, Claude pide el login ahí mismo."];
    if (origenCuentas === "copia")
        partes.push("La lista de cuentas es la última que guardó este navegador: bots-info no contestó.");
    if (info.proc) {
        const vigente = await cuentaDelProceso(info.proc.pid);
        // null = la configuración de siempre; un texto que no es una cuenta = un config dir desconocido.
        const idVigente = vigente === null ? Object.keys(cuentasClaude).find(id => !cuentasClaude[id].dir) : vigente;
        if (idVigente !== cuentaClaude)
            partes.push(`La sesión abierta sigue con ${cuentasClaude[idVigente] ? cuentasClaude[idVigente].nombre : idVigente}: ` +
                        "cierra Claude (/exit) y vuelve a abrirlo para cambiarla.");
    }
    // El aviso es para toda cuenta con config dir propio: la de siempre es la de Diego.
    if (cuentasClaude[cuentaClaude].dir)
        partes.push("⚠️ Esta sesión lee los dos vaults: lo de CyD que se lea queda en el historial de esa cuenta, " +
                    "y Remote Control la muestra en la app de Claude donde esté abierta esa cuenta.");
    nota.textContent = partes.join(" ");
}

document.getElementById("cuenta-claude").addEventListener("change", async ev => {
    try {
        await guardarPreferencia(ev.target.value);
    } catch (e) {
        alert("No pude guardar la preferencia: " + (e.message || e));
    }
    refrescar();
});

/* ---------- Remote Control de Claude ---------- */

// Tres casos, según lo que hay corriendo en la sesión `pi`:
//  - Claude con --remote-control → el botón abre claude.ai/code, donde está la sesión.
//  - Claude SIN Remote Control → lo activa escribiendo `/remote-control` en la sesión,
//    previa confirmación, sin reiniciarla (se perdería lo que estuviera haciendo).
//  - Sin Claude → no hace falta: «Abrir Claude» ya lanza con --remote-control.
// Hay una sesión de Claude que NO es la de `pi`: la del notebook o la del bot no se tocan.
const CLAUDE_WEB = "https://claude.ai/code";
let modoRemoto = null;

function pintarRemoto(info) {
    const b = document.getElementById("remoto");
    if (!info.proc) {
        b.hidden = true;
        modoRemoto = null;
        return;
    }
    b.hidden = false;
    if (info.proc.args.includes("--remote-control") || remotoActivado) {
        modoRemoto = "abrir";
        b.textContent = "📱 Abrir en claude.ai";
        b.title = "La sesión de la Pi aparece en claude.ai/code y en la app de Claude del teléfono";
    } else {
        modoRemoto = "activar";
        b.textContent = "📱 Activar Remote Control";
        b.title = "Escribe /remote-control en la sesión de Claude, sin reiniciarla";
    }
}

// La activación por /remote-control no deja rastro en los args del proceso: se recuerda
// acá para que el botón pase a «Abrir» sin esperar un reinicio.
let remotoActivado = false;

document.getElementById("remoto").addEventListener("click", async () => {
    if (modoRemoto === "abrir") {
        window.open(CLAUDE_WEB, "_blank", "noopener");
        return;
    }
    if (modoRemoto !== "activar") return;
    const pane = (await correr(["tmux", "display-message", "-p", "-t", AGENTES.claude.sesion,
        "#{pane_current_command}"])).trim();
    if (pane !== "claude") {
        alert("Claude no está en primer plano en la sesión «pi»; ábrela y actívalo desde ahí.");
        return;
    }
    if (!confirm("Esto escribe /remote-control en la sesión de Claude de la Pi.\n\n" +
                 "Si estabas escribiendo algo en su prompt, se mezcla con eso. ¿Seguir?")) return;
    await correr(["tmux", "send-keys", "-t", AGENTES.claude.sesion, "-l", "/remote-control"]);
    await correr(["tmux", "send-keys", "-t", AGENTES.claude.sesion, "Enter"]);
    remotoActivado = true;
    refrescar();
});

async function refrescar() {
    const [estado, uso] = await Promise.all([leerEstado(), leerUso()]);
    for (const id of Object.keys(AGENTES)) pintar(id, estado[id], uso);
    barraNodo.leido();
}

/* ---------- terminal ---------- */

const TECLAS = {
    esc: "\x1b", tab: "\t", stab: "\x1b[Z", ctrlc: "\x03",
    arriba: "\x1b[A", abajo: "\x1b[B", enter: "\r",
};

// En el celular el toque no genera rueda: se pagina con el copy-mode de tmux.
// `-e` sale solo al volver al fondo; page-down fuera de copy-mode falla y se ignora.
let sesionAbierta = null;
const PAGINAR = {
    subir: s => ["tmux", "copy-mode", "-e", "-u", "-t", s],
    bajar: s => ["tmux", "send-keys", "-t", s, "-X", "page-down"],
};

function cerrar() {
    sesionAbierta = null;
    if (canal) { canal.close(); canal = null; }
    if (observador) { observador.disconnect(); observador = null; }
    if (term) { term.dispose(); term = null; }
    document.getElementById("consola").hidden = true;
}

// Si la sesión existe pero el agente se cerró, el pane quedó en el `exec bash -l`
// y `new-session -A` sólo se ancla: nadie relanza el CLI. Se le escribe el mismo
// comando fijo, pero únicamente si el pane está en bash ocioso (con otra cosa en
// primer plano, como vim o un comando, las teclas caerían donde no deben).
async function relanzarSiHaceFalta(id) {
    const a = AGENTES[id];
    const info = (await leerEstado())[id];
    if (!info.sesion || info.proc) return;
    const pane = (await correr(["tmux", "display-message", "-p", "-t", a.sesion,
        "#{pane_current_command}"])).trim();
    if (pane !== "bash") return;
    await correr(["tmux", "send-keys", "-t", a.sesion, "-l", a.lanzar]);
    await correr(["tmux", "send-keys", "-t", a.sesion, "Enter"]);
}

async function abrir(id) {
    cerrar();
    const a = AGENTES[id];
    await relanzarSiHaceFalta(id);
    const consola = document.getElementById("consola");
    const el = document.getElementById("terminal");
    consola.hidden = false;
    document.getElementById("consola-titulo").textContent = `${a.nombre} · sesión ${a.sesion}`;

    const angosto = window.innerWidth < 600;
    term = new Terminal({
        fontFamily: 'ui-monospace, "Cascadia Mono", "DejaVu Sans Mono", Menlo, Consolas, monospace',
        fontSize: angosto ? 12 : 14,
        cursorBlink: true,
        scrollback: 5000,
        theme: { background: "#0f0f0e", foreground: "#e8e6df" },
    });
    ajuste = new FitAddon.FitAddon();
    term.loadAddon(ajuste);
    term.open(el);
    ajuste.fit();

    // `mouse on` por sesión: el historial vive en tmux, no en el scrollback de xterm.js
    // (tmux dibuja en pantalla alternativa). Sin esto la rueda llega como ↑/↓ y en
    // Claude recorre el historial de prompts en vez de desplazar. Seleccionar: Shift+arrastrar.
    const cmd = `${a.lanzar}; exec bash -l`;
    const c = cockpit.channel({
        payload: "stream",
        spawn: ["tmux", "new-session", "-A", "-s", a.sesion, "bash", "-lc", cmd,
                ";", "set-option", "-t", a.sesion, "mouse", "on"],
        environ: ["TERM=xterm-256color"],
        directory: home,
        pty: true,
        binary: true,
        window: { rows: term.rows, cols: term.cols },
    });
    canal = c;
    sesionAbierta = a.sesion;
    const t = term;

    c.addEventListener("message", (ev, data) => t.write(data));
    c.addEventListener("close", (ev, opciones) => {
        const motivo = opciones && opciones.problem ? `: ${opciones.problem}` : "";
        if (canal === c) {
            t.write(`\r\n\x1b[2m[desanclado${motivo} — la sesión sigue viva en tmux]\x1b[0m\r\n`);
            canal = null;
        }
        refrescar();
    });
    t.onData(d => { if (canal === c && c.valid) c.send(enc.encode(d)); });
    t.onResize(({ cols, rows }) => { if (canal === c && c.valid) c.control({ window: { rows, cols } }); });

    let pendiente = false;
    observador = new ResizeObserver(() => {
        if (pendiente) return;
        pendiente = true;
        requestAnimationFrame(() => { pendiente = false; if (term === t) ajuste.fit(); });
    });
    observador.observe(el);

    consola.scrollIntoView({ behavior: "smooth", block: "start" });
    t.focus();
    setTimeout(refrescar, 1500);
}

/* ---------- arranque ---------- */

document.querySelectorAll("[data-agente]").forEach(b =>
    b.addEventListener("click", () => abrir(b.dataset.agente)));
document.getElementById("cerrar").addEventListener("click", cerrar);
document.querySelectorAll("[data-tecla]").forEach(b =>
    b.addEventListener("click", () => {
        if (canal && canal.valid) canal.send(enc.encode(TECLAS[b.dataset.tecla]));
        if (term) term.focus();
    }));
document.querySelectorAll("[data-paginar]").forEach(b =>
    b.addEventListener("click", async () => {
        if (sesionAbierta) await correr(PAGINAR[b.dataset.paginar](sesionAbierta));
        if (term) term.focus();
    }));

// Actualizar (barra compartida): vuelve a pedir las cuentas y su margen a bots-info, que
// al abrir se leen una sola vez, y después el estado de las sesiones.
barraNodo.alActualizar(async () => {
    await leerCuentas();
    await leerPreferencia();
    await refrescar();
});

cockpit.transport.wait(async () => {
    // El home antes que nada: la preferencia y los config dirs de las cuentas cuelgan de él.
    try { home = (await cockpit.user()).home || "/"; } catch (e) { /* queda "/" */ }
    await leerCuentas();
    await leerPreferencia();
    refrescar();
    setInterval(() => { if (!document.hidden) refrescar(); }, REFRESCO_MS);
});
