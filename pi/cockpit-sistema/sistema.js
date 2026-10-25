/*
 * Pestaña "🍇 Raspberry Pi" de Cockpit (antes "🖥️ Sistema"): Inicio, Estado, Servicios,
 * Respaldo, Programados (⏰, encargo 22) y Turno. Las noticias salieron a su propia herramienta, 📰 Noticias
 * (pi/cockpit-noticias/), el 25-09-2026.
 *
 * Canónico en el vault (10-Proyectos/11-Pi5/pi/cockpit-sistema/); se instala copiando la
 * carpeta a ~/.local/share/cockpit/sistema, junto con `comun` (tokens, base, tema, `el()`
 * y la barra compartida). Diseño: documentos 21 y 26.
 *
 * 🏠 Inicio (encargo 18) es la pestaña que abre: un vistazo de las seis herramientas. Su
 * modelo está en inicio.js; acá se leen las fuentes y se dibuja.
 *
 * Doctrina, la misma de las otras páginas:
 *  - Lo que necesita root pasa por UN script fijo con lista blanca (`nodo-servicio`,
 *    `nodo-respaldo`), llamado con `sudo -n`. Nunca un comando armado con texto del
 *    usuario: lo que viaja son nombres elegidos de una lista o ids validados allá.
 *  - Lo que no necesita root no lo pide: estado.json es 644, dcifu004 está en `adm` y en
 *    `docker` (logs). Desde el 28-09-2026 ya no: los logs de contenedores van por
 *    `sudo -n nodo-servicio logs <nombre>`, porque el grupo docker equivalía a root.
 *  - Estado lee lo que ya arma el timer de estado.py: la página no recolecta nada.
 */
"use strict";

const ESTADO_JSON = "/opt/nodo/datos/estado.json";
const USO_JSON = "/opt/nodo/datos/uso.json";
const BOTS_INFO = ["sudo", "-n", "/usr/local/bin/bots-info"];
const LUCES = ["/home/dcifu004/.local/bin/luces", "estado"];
const $ = sel => document.querySelector(sel);
let estado = null;
let panelActual = "inicio";

/* ---------- utilidades ---------- */

// `el()` está en ../comun/dom.js y el tema lo aplica ../comun/tema.js (encargo 18).

function error(msg) {
    $("#error").hidden = !msg;
    $("#error").textContent = msg || "";
}

const coma = (x, d = 1) => Number(x).toFixed(d).replace(".", ",");

function bytes(n) {
    if (n == null) return "—";
    const u = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${coma(n, i ? 1 : 0)} ${u[i]}`;
}

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

async function raiz(...args) {
    // Los scripts de root devuelven JSON aun cuando fallan: {ok:false, error}.
    let out;
    try {
        out = await correr(["sudo", "-n", ...args]);
    } catch (e) {
        try { out = e.message && JSON.parse(e.message); } catch (x) { out = null; }
        if (out && out.error) throw new Error(out.error);
        throw new Error((e.message || String(e)) +
            ". Si sudo ya pide contraseña, falta la línea de este script en sudoers.");
    }
    const d = JSON.parse(out);
    if (d && d.ok === false) throw new Error(d.error || "falló");
    return d;
}

async function leerEstado() {
    try {
        estado = await cockpit.file(ESTADO_JSON, { syntax: JSON }).read();
    } catch (e) {
        estado = null;
    }
    if (estado) {
        $("#sub").textContent = `${estado.host} · encendida hace ${traducirUptime(estado.encendida_hace)}`;
        barraNodo.leido(estado.momento, "Es la hora de estado.json: el panel se arma cada 5 min.");
    }
    return estado;
}

function traducirUptime(s) {
    return (s || "").replace(/(\d+) days?/, "$1 d").replace(/(\d+) hours?/, "$1 h")
        .replace(/(\d+) minutes?/, "$1 min").replace(/,/g, "");
}

/* ---------- pestañas ---------- */

const PANELES = { inicio: pintarInicio, estado: pintarEstado, servicios: pintarServicios,
                  respaldo: pintarRespaldo, programados: pintarProgramados, turno: pintarTurno };

function mostrar(p) {
    panelActual = p;
    document.querySelectorAll("#pestanas button").forEach(b => b.classList.toggle("activa", b.dataset.p === p));
    document.querySelectorAll("[data-panel]").forEach(s => { s.hidden = s.dataset.panel !== p; });
    error(null);
    PANELES[p]().catch(e => error(e.message || String(e)));
}
document.querySelectorAll("#pestanas button").forEach(b => b.addEventListener("click", () => mostrar(b.dataset.p)));
// «Inicio» en la barra compartida, estando ya en esta página, vuelve a la pestaña 🏠.
window.addEventListener("barra:actual", () => mostrar("inicio"));

/* ---------- 🏠 Inicio ---------- */

// Cada fuente se lee por separado y la que falla o falta queda en null: modeloInicio
// (inicio.js) la muestra como «sin datos», nunca como 0 ni en verde. Ninguna es nueva:
// son las que ya leen 🍇, 👾, 🤖, 💳, 🌈 y 📰, con los mismos comandos fijos.
async function leerFuentes() {
    const oNada = promesa => Promise.resolve(promesa).then(v => (v == null ? null : v), () => null);
    const json = args => cockpit.spawn(args, { err: "message" }).then(salida => JSON.parse(salida));
    const [e, uso, bots, luces, pendientes] = await Promise.all([
        oNada(leerEstado()),
        oNada(cockpit.file(USO_JSON, { syntax: JSON }).read()),
        oNada(json(BOTS_INFO)),
        oNada(json(LUCES)),
        oNada(barraNodo.refrescar()),
    ]);
    const noticias = pendientes ? pendientes.noticias : null;
    return { estado: e, uso, bots, luces, noticias,
             propuestas: pendientes ? pendientes.propuestas : null,
             sinVotar: barraNodo.sinVotar(noticias), encargos: pendientes ? pendientes.encargos : null,
             programados: pendientes ? pendientes.programados : null };
}

const PUNTO_INICIO = {
    ok: ["", "todo con dato y sin avisos"],
    ojo: ["ojo", "hay algo que mirar"],
    gris: ["gris", "sin datos: alguna fuente no se pudo leer"],
};

function baldosa(b) {
    // 🍇 es esta misma página: su baldosa abre la pestaña 📊 Estado.
    const ir = () => (b.id === "sistema" ? mostrar("estado") : b.id === "programados" ? mostrar("programados") : cockpit.jump(b.destino));
    const [clase, titulo] = PUNTO_INICIO[b.estado];
    return el("article", { class: "tarjeta baldosa" + (b.forma ? " " + b.forma : ""), role: "link", tabindex: "0",
        "aria-label": `Abrir ${b.titulo}`, onclick: ir,
        onkeydown: ev => { if (ev.key === "Enter") ir(); } },
        el("h2", {}, el("span", { class: "punto" + (clase ? " " + clase : ""), title: titulo }), b.titulo),
        el("dl", { class: "lista-estado" }, b.filas.flatMap(f =>
            [el("dt", {}, f.dato), el("dd", { class: f.nivel }, f.valor)])));
}

async function pintarInicio() {
    const cont = $("[data-panel=inicio]");
    if (!cont.childElementCount) cont.replaceChildren(el("p", { class: "tenue" }, "leyendo…"));
    const modelo = modeloInicio(await leerFuentes(), Date.now());
    cont.replaceChildren(
        el("div", { class: "bento" }, modelo.map(baldosa)),
        el("p", { class: "tenue" }, "Punto verde: todo con dato y sin avisos. Ámbar: hay algo que mirar. ",
           "Gris: sin datos (la fuente no se pudo leer). Cada baldosa abre su página."));
}

/* ---------- 📊 Estado ---------- */

// Las claves son las de estado.py (medidores); una clave nueva se muestra con su nombre crudo.
const NOMBRE_MEDIDOR = {
    temp_soc: "🌡️ Temperatura CPU", temp_nvme: "💽 Temperatura NVMe", nvme_vida: "💽 Vida del NVMe usada",
    carga: "📈 Carga", memoria: "🧠 Memoria", swap: "🔄 Swap", raiz: "💾 Disco raíz",
    "datos cifrados": "🔐 Datos cifrados", "disco respaldo": "💾 Disco de respaldo",
};

function medidor(clave, m) {
    const lo = m.min ?? 0, hi = m.max ?? 100;
    const pct = Math.max(0, Math.min(100, 100 * ((m.v ?? 0) - lo) / ((hi - lo) || 1)));
    const nivel = m.v >= (m.ro ?? Infinity) ? "ro" : m.v >= (m.am ?? Infinity) ? "am" : "";
    const barra = el("div", { class: `barra ${nivel}` });
    barra.style.width = `${pct}%`;
    return el("div", { class: "medidor" },
        el("div", { class: "fila" }, el("span", {}, NOMBRE_MEDIDOR[clave] || clave),
           el("span", { class: "num" }, `${coma(m.v, m.u === "%" ? 0 : 1)} ${m.u || ""}`)),
        el("div", { class: "barra-cont" }, barra),
        m.nota ? el("div", { class: "tenue" }, m.nota) : null);
}

function filas(pares) {
    return el("dl", { class: "dato" }, pares.filter(Boolean).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
}

// 🌀 Temperatura y ventilador: estaba en 🌈 Luces y pasó acá (encargo 18). Sale de
// estado.json, como el resto de Estado: se actualiza con el timer o con «Medir ahora»,
// ya no cada 5 s. Sin dato dice «sin datos», no 0.
function tarjetaVentilador(e) {
    const t = (e.medidores || {}).temp_soc;
    const v = e.ventilador;
    const pct = v && v.pct != null ? Math.max(0, Math.min(100, Number(v.pct))) : null;
    const barra = el("div", { class: "barra" });
    if (pct != null) barra.style.width = `${pct}%`;
    return el("div", { class: "tarjeta" }, el("h2", {}, "🌀 Temperatura y ventilador"),
        el("div", { class: "ventilador" },
            el("div", {}, el("span", { class: "grande" }, t && t.v != null ? `${coma(t.v)} °C` : "sin datos"),
               el("span", { class: "tenue" }, " CPU")),
            el("div", {}, el("span", { class: "grande" }, v && v.rpm != null ? String(v.rpm) : "sin datos"),
               el("span", { class: "tenue" }, " rpm")),
            el("div", { class: "barra-cont" }, barra),
            el("span", { class: "tenue" }, pct != null ? `el kernel le pide ${Math.round(pct)} %` : "")),
        el("p", { class: "tenue" }, "El ventilador lo maneja el kernel según la temperatura (umbrales 50, 60, 67,5 y ",
           "75 °C). Las luces del case van por otra línea: no dependen de que gire."));
}

async function pintarEstado() {
    const cont = $("[data-panel=estado]");
    const e = await leerEstado();
    if (!e) {
        cont.replaceChildren(el("div", { class: "aviso rojo" },
            "No pude leer estado.json. Si el volumen cifrado está cerrado, corre `sudo abrir-datos`."));
        return;
    }
    const alertas = e.alertas || [];
    const serv = Object.entries(e.servicios || {});
    const caidos = serv.filter(([, ok]) => !ok).map(([n]) => n)
        .concat((e.contenedores || []).filter(c => !c.ok).map(c => c.nombre));
    const s = e.salud || {};
    const r = e.respaldo || {};
    const actualizar = el("button", { class: "mini", onclick: async (ev) => {
        ev.target.disabled = true;
        try { await raiz("systemctl", "start", "estado.service"); } catch (x) { error(x.message); }
        ev.target.disabled = false;
        pintarEstado();
    } }, "↻ Medir ahora");

    cont.replaceChildren(
        el("div", { class: "tarjeta" },
            el("div", { class: "resumen" }, alertas.length ? `🔴 ${alertas.length} alerta(s)` : "🟢 Todo en orden",
               el("span", { class: "tenue" }, `medido ${hace(e.momento)}`), actualizar),
            alertas.length ? el("ul", {}, alertas.map(a => el("li", {}, a.texto || a.id || JSON.stringify(a)))) : null),
        el("div", { class: "rejilla" },
            el("div", { class: "tarjeta" }, el("h2", {}, "Temperaturas y carga"),
               Object.entries(e.medidores || {}).map(([k, m]) => medidor(k, m)),
               e.throttled ? el("p", { class: "aviso ojo" }, "⚠️ El firmware reporta limitación (throttling) desde el arranque: revisar la fuente de poder.") : null),
            tarjetaVentilador(e),
            el("div", { class: "tarjeta" }, el("h2", {}, "Servicios"),
               el("p", { class: "resumen" }, caidos.length ? `🔴 ${caidos.length} caído(s)` : `🟢 ${serv.length + (e.contenedores || []).length} arriba`),
               caidos.length ? el("p", {}, caidos.join(", ")) : null,
               el("p", {}, el("button", { class: "mini", onclick: () => mostrar("servicios") }, "Ver y reiniciar →")),
               filas([
                   ["Unidades fallidas", (s.unidades_fallidas || []).length ? s.unidades_fallidas.join(", ") : "ninguna"],
                   ["Reloj (NTP)", s.reloj_ntp ? "sincronizado" : "⚠️ sin sincronizar"],
                   ["Errores de disco", String((s.errores_io || 0) + (e.nvme_errores || 0))],
                   ["Actualizaciones", String(s.actualizaciones ?? "—")],
                   s.reinicio_pendiente ? ["Reinicio", "⚠️ pendiente"] : null,
               ])),
            el("div", { class: "tarjeta" }, el("h2", {}, "Disco y respaldo"),
               filas([
                   ["Volumen cifrado", e.luks?.abierto ? `abierto · ${e.luks.pct} % usado (${bytes(e.luks.usado)} de ${bytes(e.luks.total)})` : "🔴 CERRADO"],
                   ["Último respaldo", r.ultimo ? `${cuando(r.ultimo)} (${hace(r.ultimo)})` : "—"],
                   ["Disco de respaldo", r.montado ? `${r.dispositivo || ""} · ${bytes(r.libre)} libres` : "🔴 no montado"],
               ]),
               el("p", {}, el("button", { class: "mini", onclick: () => mostrar("respaldo") }, "Ver respaldo →"))),
            el("div", { class: "tarjeta" }, el("h2", {}, "Red y sincronización"),
               filas([
                   ["Tailscale", e.red?.tailscale || "—"],
                   ["IP local", e.red?.ip_local || "—"],
                   e.red?.clave_vence ? ["Clave Tailscale", `⚠️ vence ${e.red.clave_vence}`] : null,
                   ...((e.sync?.carpetas) || []).map(c => [`Syncthing · ${c.label}`,
                       `${c.ok ? "🟢" : "🔴"} ${c.estado}${c.faltan ? ` · faltan ${c.faltan}` : ""}`]),
               ])),
            el("div", { class: "tarjeta" }, el("h2", {}, "Captura y agentes"),
               filas([
                   ["Bot de captura", e.captura?.activo ? `escuchando · ${e.captura.hoy} hoy` : "🔴 detenido"],
                   ["Inbox sin procesar", e.inbox ? `${e.inbox.pendientes}${e.inbox.mas_vieja_dias ? ` · la más vieja de ${e.inbox.mas_vieja_dias} d` : ""}` : "—"],
                   ...((e.agentes) || []).map(a => [`Agente ${a.agente}`, `${coma(a.horas)} h · ${a.usuario}${a.sub ? " · " + a.sub : ""}`]),
                   e.luces ? ["Luces", `${e.luces.modo}${e.luces.brillo && e.luces.brillo < 100 ? ` · ${e.luces.brillo} %` : ""}`] : null,
               ]))));
}

/* ---------- 🔁 Servicios ---------- */

async function pintarServicios() {
    const cont = $("[data-panel=servicios]");
    await leerEstado();
    let lista = [];
    try { lista = await raiz("/usr/local/bin/nodo-servicio", "lista"); }
    catch (e) { error(e.message); }
    const vivo = n => {
        if (!estado) return null;
        if (n in (estado.servicios || {})) return estado.servicios[n];
        const c = (estado.contenedores || []).find(x => x.nombre === n);
        return c ? c.ok : null;
    };
    const detalleC = n => ((estado?.contenedores || []).find(x => x.nombre === n) || {}).estado;
    const log = el("pre", { class: "log", hidden: true });
    const tituloLog = el("h3", { hidden: true });

    async function verLog(item) {
        tituloLog.hidden = log.hidden = false;
        tituloLog.textContent = `Últimas líneas de ${item.nombre}`;
        log.textContent = "leyendo…";
        try {
            // Contenedores por el script de root: dcifu004 ya no está en el grupo docker
            // (28-09-2026), que equivalía a root. Los de systemd siguen por el grupo adm.
            log.textContent = (item.tipo === "systemd"
                ? await correr(["journalctl", "-u", item.nombre, "-n", "80", "--no-pager", "-o", "short-iso"], { err: "out" })
                : (await raiz("/usr/local/bin/nodo-servicio", "logs", item.nombre)).texto) || "(vacío)";
            log.scrollTop = log.scrollHeight;
        } catch (e) { log.textContent = "No pude leer el log: " + (e.message || e); }
    }

    async function reiniciar(item, boton) {
        if (!confirm(`¿Reiniciar ${item.nombre}?\n\nSi está atendiendo algo (una consulta del bot, un flujo de n8n), se corta.`)) return;
        boton.disabled = true;
        boton.textContent = "reiniciando…";
        try {
            const r = await raiz("/usr/local/bin/nodo-servicio", "reiniciar", item.nombre);
            boton.textContent = r.estado === "active" ? "✓ reiniciado" : `quedó ${r.estado}`;
            await raiz("systemctl", "start", "estado.service").catch(() => {});
        } catch (e) {
            error(e.message);
            boton.textContent = "Reiniciar";
        }
        setTimeout(pintarServicios, 1500);
    }

    cont.replaceChildren(el("div", { class: "tarjeta" },
        el("h2", {}, "Servicios del nodo"),
        el("p", { class: "tenue" }, "La lista es la misma de /estado: un servicio nuevo aparece acá cuando entra al panel. ",
           "Los marcados 🔒 no se reinician desde el navegador porque cortarían el camino por el que llega esta página."),
        el("table", {},
            el("tr", {}, el("th", {}, "Servicio"), el("th", {}, "Estado"), el("th", {}, "")),
            lista.map(item => {
                const ok = vivo(item.nombre);
                const boton = el("button", { class: "mini" }, "Reiniciar");
                boton.addEventListener("click", () => reiniciar(item, boton));
                return el("tr", {},
                    el("td", {}, el("span", { class: "punto" + (ok === false ? " mal" : ok == null ? " gris" : "") }),
                       item.nombre, item.tipo === "contenedor" ? el("span", { class: "chip" }, "contenedor") : null),
                    el("td", { class: "tenue" }, ok === false ? "CAÍDO" : item.tipo === "contenedor" ? (detalleC(item.nombre) || "") : "activo"),
                    el("td", { class: "acciones" },
                       el("button", { class: "mini", onclick: () => verLog(item) }, "Log"), " ",
                       item.protegido ? el("span", { class: "tenue", title: item.protegido }, "🔒 " + item.protegido) : boton));
            })),
        tituloLog, log));
}

/* ---------- 💾 Respaldo ---------- */

let respaldoSondeo = null;

async function pintarRespaldo() {
    const cont = $("[data-panel=respaldo]");
    await leerEstado();
    let st = null;
    try { st = await raiz("/usr/local/bin/nodo-respaldo", "estado"); } catch (e) { error(e.message); }
    const r = estado?.respaldo || {};
    const corriendo = st && (st.activo === "active" || st.activo === "activating");
    const log = el("pre", { class: "log" }, "…");
    correr(["journalctl", "-u", "respaldo.service", "-n", corriendo ? "30" : "25", "--no-pager", "-o", "short-iso"], { err: "out" })
        .then(t => { log.textContent = t || "(sin registro)"; log.scrollTop = log.scrollHeight; })
        .catch(e => { log.textContent = String(e.message || e); });

    const boton = el("button", { disabled: corriendo }, corriendo ? "⏳ Respaldando…" : "💾 Respaldar ahora");
    boton.addEventListener("click", async () => {
        if (!confirm("¿Hacer un respaldo ahora? Es el mismo del turno de las 03:30: incluye un volcado de Postgres y una verificación.")) return;
        try { await raiz("/usr/local/bin/nodo-respaldo", "ahora"); } catch (e) { error(e.message); }
        pintarRespaldo();
    });
    clearTimeout(respaldoSondeo);
    if (corriendo) respaldoSondeo = setTimeout(() => { if (panelActual === "respaldo") pintarRespaldo(); }, 4000);

    const ultimoOk = st && st.resultado === "success" && st.salida === "0";
    cont.replaceChildren(
        el("div", { class: "aviso ojo" }, "🔑 Recordatorio (Hueco 7): la única copia de la clave de restic va dentro del ",
           "repositorio que abre. Si muere el NVMe, sin la frase en tu gestor de contraseñas este respaldo no se puede leer."),
        el("div", { class: "rejilla" },
            el("div", { class: "tarjeta" }, el("h2", {}, "Estado"),
               filas([
                   ["Ahora", corriendo ? "⏳ corriendo" : "en espera"],
                   ["Último", st?.ultimo_fin || estado?.respaldo?.ultimo || "—"],
                   ["Cómo terminó", st ? (ultimoOk ? "🟢 bien" : `🔴 ${st.resultado} (código ${st.salida})`) : "—"],
                   ["Próximo turno", st?.proximo || "—"],
                   ["Disco", r.montado ? `${r.dispositivo || ""} · ${bytes(r.libre)} libres de ${bytes(r.total)}` : "🔴 no montado"],
               ]),
               el("p", {}, boton)),
            el("div", { class: "tarjeta" }, el("h2", {}, "Registro del último respaldo"), log)),
        el("div", { class: "tarjeta", id: "snaps" }, el("h2", {}, "Snapshots"), el("p", { class: "tenue" }, "leyendo…")));
    pintarSnapshots();
}

async function pintarSnapshots() {
    const cont = $("#snaps");
    let snaps = [];
    try { snaps = await raiz("/usr/local/bin/nodo-respaldo", "snapshots"); }
    catch (e) { cont.replaceChildren(el("h2", {}, "Snapshots"), el("div", { class: "aviso rojo" }, e.message)); return; }
    const deArchivos = snaps.filter(s => s.etiquetas.includes("archivos"));
    const explorador = el("div", {});
    cont.replaceChildren(el("h2", {}, `Snapshots (${snaps.length})`),
        el("p", { class: "tenue" }, "Restaurar NUNCA escribe encima: deja la copia en /opt/nodo/datos/restaurado/<fecha>/ ",
           "y de ahí la mueves tú. Los secretos no se restauran desde acá."),
        el("table", {},
            el("tr", {}, el("th", {}, "Cuándo"), el("th", {}, "Id"), el("th", {}, "Qué"), el("th", {}, "")),
            snaps.slice(0, 15).map(s => el("tr", {},
                el("td", { class: "num" }, cuando(s.cuando)),
                el("td", {}, el("code", {}, s.corto)),
                el("td", {}, s.etiquetas.map(t => el("span", { class: "chip" }, t)), el("span", { class: "tenue" }, ` ${s.rutas} ruta(s)`)),
                el("td", { class: "acciones" }, s.etiquetas.includes("archivos")
                    ? el("button", { class: "mini", onclick: () => explorar(explorador, s, "/opt/nodo/datos") }, "Explorar")
                    : el("span", { class: "tenue" }, "volcado SQL"))))),
        snaps.length > 15 ? el("p", { class: "tenue" }, `… y ${snaps.length - 15} más antiguos (se guardan 7 diarios, 4 semanales y 6 mensuales).`) : null,
        explorador);
    if (!deArchivos.length) explorador.replaceChildren(el("p", { class: "tenue" }, "No hay snapshots de archivos."));
}

async function explorar(cont, snap, carpeta) {
    cont.replaceChildren(el("p", { class: "tenue" }, `leyendo ${carpeta}…`));
    let items;
    try { items = await raiz("/usr/local/bin/nodo-respaldo", "ls", snap.id, carpeta); }
    catch (e) { cont.replaceChildren(el("div", { class: "aviso rojo" }, e.message)); return; }
    const partes = carpeta.split("/").filter(Boolean);
    const migas = el("div", { class: "migas" }, el("strong", {}, `📦 ${snap.corto} · ${cuando(snap.cuando)}:`),
        el("button", { class: "mini", onclick: () => explorar(cont, snap, "/") }, "/"),
        partes.map((p, i) => el("button", { class: "mini",
            onclick: () => explorar(cont, snap, "/" + partes.slice(0, i + 1).join("/")) }, p)));
    const resultado = el("div", {});
    const restaurar = async (item) => {
        if (!confirm(`¿Restaurar ${item.ruta} tal como estaba el ${cuando(snap.cuando)}?\n\nSe copia a una carpeta nueva; no toca el original.`)) return;
        resultado.replaceChildren(el("p", { class: "tenue" }, "restaurando…"));
        try {
            const r = await raiz("/usr/local/bin/nodo-respaldo", "restaurar", snap.id, item.ruta);
            resultado.replaceChildren(el("div", { class: "aviso ok" }, "✓ Restaurado en ", el("code", {}, r.destino)));
        } catch (e) { resultado.replaceChildren(el("div", { class: "aviso rojo" }, e.message)); }
    };
    cont.replaceChildren(el("h3", {}, "Explorar"), migas, resultado,
        items.length ? el("table", {}, items.map(it => el("tr", {},
            el("td", {}, it.tipo === "dir"
                ? el("button", { class: "mini", onclick: () => explorar(cont, snap, it.ruta) }, `📁 ${it.nombre}`)
                : `📄 ${it.nombre}`),
            el("td", { class: "tenue num" }, it.tipo === "dir" ? "" : bytes(it.bytes)),
            el("td", { class: "tenue num" }, it.modificado ? cuando(it.modificado) : ""),
            el("td", { class: "acciones" }, el("button", { class: "mini", onclick: () => restaurar(it) }, "Restaurar")))))
        : el("p", { class: "tenue" }, "Vacía, o no estaba en este snapshot."));
}

/* ---------- 🔎 Turno ---------- */

async function pintarTurno() {
    $("[data-panel=turno]").replaceChildren(el("div", { class: "tarjeta" },
        el("h2", {}, "🔎 Visor del turno"),
        el("div", { class: "aviso ojo" }, "🚧 En construcción: todavía no hay nada que mirar desde la Pi."),
        el("p", {}, "Las corridas largas de los arneses viven en ", el("strong", {}, "Windows"), " y escriben en ",
           el("strong", {}, "Google Drive"), " (el de CyD, que en la Pi está en pausa hasta que TI dé el visto bueno). ",
           "Por eso en su momento la Pi quedó fuera del diseño del turno: el guardia sólo necesita estar vivo mientras vive la corrida."),
        el("h3", {}, "Para que esta pestaña tenga datos, una de estas:"),
        el("ul", {},
            el("li", {}, "Que el arnés escriba su manifiesto y su bitácora (CAMBIOS.md) también en una carpeta de Syncthing que la Pi vea, como ",
               el("code", {}, "ingesta"), " (compartida sólo entre el PC y la Pi)."),
            el("li", {}, "O activar el Drive de CyD en la Pi, cuando TI lo autorice."),
            el("li", {}, "Y el hook ", el("code", {}, "notify"), " de Codex (turn-ended) podría avisar a la Pi en vez de sondear."))));
}

/* ---------- arranque ---------- */

barraNodo.alActualizar(() => PANELES[panelActual]().catch(e => error(e.message || String(e))));

cockpit.transport.wait(() => {
    mostrar("inicio");
    setInterval(() => {
        if (!document.hidden && (panelActual === "inicio" || panelActual === "estado" || panelActual === "programados"))
            PANELES[panelActual]().catch(e => error(e.message || String(e)));
    }, 60000);
});
