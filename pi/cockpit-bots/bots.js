/*
 * Pestaña "🤖 Jaime y Pilar" de Cockpit.
 *
 * Canónico en el vault (10-Proyectos/11-Pi5/pi/cockpit-bots/); se instala copiando la
 * carpeta a ~/.local/share/cockpit/bots. Diseño completo y fases: documento 20.
 *
 * Doctrina:
 *  - La página LEE y PROPONE. Nunca aplica: escribe un JSON en
 *    ~/.local/share/bots-propuestas/ y lo aplica `sudo aplicar-propuesta <id>` por SSH.
 *    Mientras sudo no pida contraseña (Hueco 1), el navegador no puede ser donde se
 *    amplían permisos.
 *  - Todo lo del sistema sale de `sudo -n /usr/local/bin/bots-info` (script fijo, sólo
 *    lectura). La página no arma comandos con texto del usuario: el único texto libre es
 *    la frase de prueba de la voz, que va a Piper por stdin, como dato.
 *  - Lo que aún no existe se muestra como "próximamente", con la fase que lo destraba,
 *    para que no se pierda.
 *  - Encargo 13: `el()`, `proponer()`, la lista de propuestas y los nombres de las
 *    cuentas viven en comun.js (se carga antes que este archivo). La matriz de cuentas,
 *    el uso y el costo se mudaron a la herramienta 💳 Cuentas (pi/cockpit-cuentas/); acá
 *    queda un resumen de lectura por ruta, con el enlace.
 */
"use strict";

const PIPER = "/usr/local/bin/piper";
const RUTAS = {
    claude: "Claude (lee vaults si el perfil los tiene)",
    web: "Búsqueda web",
    gpt: "General: Groq por n8n; el respaldo gratis se elige en 💳 Cuentas",
    sql: "Base SQL",
    ha: "Home Assistant",
    google: "Agenda y correo",
    plantas: "Monitor de plantas",
    codex: "Codex leyendo vaults",
    // 06b: foto o PDF → texto. Aislada como la web: no ve vaults. Ningún perfil la trae.
    vision: "Foto o PDF → texto (sin vaults)",
    // 07: sólo lo que ya seleccionó el agente de noticias; sin web ni archivos. Ningún perfil la trae.
    noticias: "Noticias ya seleccionadas → resumen (sin web ni vaults)",
};

const enc = new TextEncoder();
let info = null;
let perfilActual = null;
let audio = null;

/* ---------- lectura ---------- */

async function cargar() {
    const boton = document.getElementById("actualizar");
    boton.disabled = true;
    try {
        info = await leerBotsInfo();
        mostrarError(null);
    } catch (e) {
        mostrarError("No pude leer el estado de los bots (sudo -n /usr/local/bin/bots-info): " +
                     (e.message || e) + ". Si sudo ya pide contraseña, falta su línea en sudoers.");
        boton.disabled = false;
        return;
    }
    boton.disabled = false;
    if (!info.cuentas)
        mostrarError("El bots-info desplegado es anterior al encargo 13: no trae la lista de cuentas. Falta desplegarlo; mientras, las cuentas salen con su id.");
    barraNodo.leido(info.momento);
    const nombres = Object.keys(info.perfiles);
    if (!perfilActual || !nombres.includes(perfilActual)) perfilActual = nombres[0];
    pintarDeriva();
    pintarPestanas();
    await pintarPerfil();
    await pintarPropuestas();
    await pintarCasa();
}

/* ---------- deriva vault ↔ desplegado ---------- */

function pintarDeriva() {
    const cont = document.getElementById("deriva");
    cont.replaceChildren();
    const distintos = info.deriva.filter(d => !d.igual);
    if (!distintos.length) return;
    const serios = distintos.filter(d => !d.mismos_valores);
    const leves = distintos.filter(d => d.mismos_valores);
    if (serios.length) {
        cont.append(el("div", { class: "aviso rojo" },
            el("strong", {}, "Lo desplegado no es lo que dice el vault"),
            el("ul", {}, serios.map(d => el("li", {},
                el("code", {}, d.archivo), " — ",
                d.falta_vault ? "desplegado sin fuente en el vault"
                    : d.falta_desplegado ? "está en el vault y no desplegado"
                    : "el contenido difiere")))));
    }
    if (leves.length) {
        cont.append(el("div", { class: "aviso ojo" },
            "Sólo cambian comentarios (los valores son iguales): ",
            leves.map(d => el("code", {}, d.archivo)),
            ". No cambia el comportamiento; se iguala al próximo despliegue."));
    }
}

/* ---------- pestañas y perfil ---------- */

function pintarPestanas() {
    const nav = document.getElementById("pestanas");
    nav.replaceChildren(...Object.entries(info.perfiles).map(([id, p]) =>
        el("button", {
            class: id === perfilActual ? "activa" : "",
            onclick: () => { perfilActual = id; pintarPestanas(); pintarPerfil(); },
        }, `${p.toml.nombre || id} · ${p.toml.persona || ""}`)));
}

async function pintarPerfil() {
    const p = info.perfiles[perfilActual];
    const cont = document.getElementById("perfil");
    // El ritmo y el diccionario en edición son de la pestaña: al cambiar de perfil
    // se parte de lo desplegado, no de lo que se estaba tocando en el otro.
    ritmo = {
        ls: numero(p.toml.voz_length_scale, 1.0),
        pausa: numero(p.toml.voz_pausa_s, 0.2),
    };
    diccionario = Object.entries(p.pronunciacion || {}).map(([e, d]) => ({ escrito: e, dicho: d }));
    cont.replaceChildren(el("div", { class: "rejilla" },
        tarjetaResumen(p), tarjetaPermisos(p)),
        tarjetaRutas(p), tarjetaCuentasResumen(p), tarjetaVoz(p), tarjetaPronunciacion(p),
        el("div", { class: "rejilla" }, tarjetaPersonalidad(p), tarjetaModeloYTope(p)),
        tarjetaCarpeta(p),
        el("section", { class: "tarjeta", id: "diag" }, el("h2", {}, "📊 Últimas consultas"),
           el("p", { class: "tenue" }, "leyendo el journal…")));
    pintarDiagnostico();
}

function tarjetaResumen(p) {
    const s = p.servicio;
    const activo = s.ActiveState === "active";
    const c = p.cuentas;
    return el("section", { class: "tarjeta" },
        el("h2", {}, "Resumen"),
        el("dl", { class: "dato" },
            el("dt", {}, "Servicio"),
            el("dd", {}, el("span", { class: "estado " + (activo ? "ok" : "mal") },
                activo ? "● activo" : "● " + s.ActiveState),
                activo && s.ActiveEnterTimestamp ? `  desde ${s.ActiveEnterTimestamp}` : ""),
            el("dt", {}, "Bot"), el("dd", {}, p.toml.bot || "—"),
            el("dt", {}, "Usuario Unix"), el("dd", {}, el("code", {}, s.User || "—")),
            p.toml.cuentas
                ? [el("dt", {}, "Cuentas"), el("dd", {}, Object.entries(p.toml.cuentas)
                    .map(([r, ids]) => `${r}: ${ids.map(nombreCuenta).join(" → ")}`).join(" · "))]
                : [el("dt", {}, "Claude"), el("dd", {}, c.claude || "sin cuenta"),
                   el("dt", {}, "Búsqueda web"), el("dd", {},
                       p.toml.web_codex ? "Codex, respaldo " + (c.claude_web || "—")
                                        : (c.claude_web || "—")),
                   el("dt", {}, "Codex"), el("dd", {}, c.codex ? "tiene codex-home" : "no")],
            el("dt", {}, "Vaults declarados"),
            el("dd", {}, (p.toml.vaults || []).length ? p.toml.vaults.join(", ") : "ninguno"),
            el("dt", {}, "Drive"),
            el("dd", {}, (p.toml.drive || []).length ? p.toml.drive.join(", ") : "ninguno")));
}

function tarjetaPermisos(p) {
    const filas = p.sonda.map(s => {
        const coincide = s.debe === null || s.visible === s.debe;
        const vis = s.visible === null ? "no se pudo medir" : s.visible ? "✅ lo ve" : "⛔ no lo ve";
        return el("tr", {},
            el("td", {}, s.etiqueta),
            el("td", {}, vis),
            el("td", {}, el("span", { class: "estado " + (coincide ? "ok" : "mal") },
                coincide ? "coincide" : "NO coincide con el perfil")));
    });
    const malos = p.sonda.filter(s => s.debe !== null && s.visible !== s.debe).length;
    const s = p.servicio;
    return el("section", { class: "tarjeta" },
        el("h2", {}, "🔒 Permisos del sistema"),
        el("p", { class: "tenue" },
            "Medido desde adentro del servicio (/proc/<pid>/root), no leído de la configuración. ",
            "Se cambian en systemd: acá sólo se ven."),
        malos ? el("div", { class: "aviso rojo" },
            `${malos} permiso(s) no coinciden con lo que declara el perfil.`) : null,
        el("table", {}, el("tr", {}, el("th", {}, "Qué"), el("th", {}, "Desde el bot"),
            el("th", {}, "")), filas),
        el("details", {}, el("summary", {}, "Directivas de systemd"),
            el("pre", {}, [
                `ReadWritePaths=${s.ReadWritePaths}`,
                `ReadOnlyPaths=${s.ReadOnlyPaths}`,
                `InaccessiblePaths=${s.InaccessiblePaths}`,
                s.BindReadOnlyPaths ? `BindReadOnlyPaths=${s.BindReadOnlyPaths}` : "",
                `Drop-ins: ${s.DropInPaths || "ninguno"}`,
            ].filter(Boolean).join("\n"))));
}

function tarjetaRutas(p) {
    const actuales = new Set(p.toml.rutas || []);
    return el("section", { class: "tarjeta" },
        el("h2", {}, "🧭 Rutas"),
        el("p", { class: "tenue" }, "A quién puede preguntarle el bot. Quitar restringe; agregar amplía y ",
           "el script lo marca con ⚠️ al aplicarlo."),
        el("div", { class: "chips" }, Object.entries(RUTAS).map(([r, desc]) => {
            const activa = actuales.has(r);
            return el("span", { class: "chip" + (activa ? " activa" : ""), title: desc },
                r,
                el("button", {
                    class: "mini",
                    onclick: () => proponerPerfil({
                        tipo: activa ? "quitar_ruta" : "agregar_ruta", valor: r,
                        antes: [...actuales].join(", "),
                        despues: activa ? [...actuales].filter(x => x !== r).join(", ")
                                        : [...actuales, r].join(", "),
                        clave: "rutas",
                    }),
                }, activa ? "quitar" : "+ agregar"));
        })));
}

/* ---------- 💳 cuentas: resumen de lectura (la matriz vive en 💳 Cuentas) ---------- */

// Sólo se lee: quién contesta cada ruta de este perfil, en orden. Todo llega resuelto
// de bots-info (`p.matriz`); para cambiarlo se va a 💳 Cuentas, donde están los dos
// perfiles juntos, el margen de cada cuenta y los atajos.
function tarjetaCuentasResumen(p) {
    const enlace = el("button", { class: "mini", id: "ir-cuentas",
        title: "Abre la herramienta 💳 Cuentas de Cockpit",
        onclick: () => cockpit.jump("/cuentas") }, "Abrir 💳 Cuentas");
    const filas = ((p.matriz && p.matriz.rutas) || []).map(f => {
        const fijos = (f.celdas || []).filter(c => c.permitida).map(c => nombreCuenta(c.cuenta));
        return el("div", { class: "cuenta-ruta" },
            el("span", { class: "nombre" }, f.nombre),
            f.fija
                ? el("span", { class: "tenue", title: f.fija }, fijos.length ? `fijo: ${fijos.join(", ")}` : "fijo: herramienta")
                : el("span", {}, "contesta ", (f.cadena || []).map(nombreCuenta).join(" → ") || "nadie",
                     f.declarada ? null : el("span", { class: "tenue" }, " · por defecto")));
    });
    return el("section", { class: "tarjeta", id: "cuentas-resumen" },
        el("h2", {}, "💳 Cuentas"),
        el("p", { class: "tenue" }, "Quién contesta cada ruta de este bot: la primera contesta y las demás ",
           "son el respaldo. Acá sólo se lee; el reparto, el margen de cada cuenta, el uso y el costo ",
           "están en 💳 Cuentas."),
        filas.length ? filas : el("div", { class: "aviso ojo" }, p.toml.cuentas
            ? "bots-info no trae el reparto por ruta: falta desplegar su última versión."
            : "Este perfil todavía usa las llaves viejas (web_codex, claude_config_web)."),
        el("div", { class: "controles-voz separado" }, enlace));
}

// Estado en edición de la pestaña actual (se reinicia en pintarPerfil).
let ritmo = { ls: 1.0, pausa: 0.2 };
let diccionario = [];

function numero(x, defecto) {
    return typeof x === "number" && isFinite(x) ? x : defecto;
}

function vozActual(p) {
    return info.voces.find(v => v.ruta === p.toml.voz) || info.voces[0];
}

function tablaDiccionario() {
    const t = {};
    for (const { escrito, dicho } of diccionario) {
        if (escrito.trim() && dicho.trim()) t[escrito.trim()] = dicho.trim();
    }
    return t;
}

// Mismo criterio que pronunciar() en botv3.py: palabras enteras, sin importar
// mayúsculas, la más larga primero y con letras Unicode (ñ y tildes) como letra.
function pronunciarJS(texto, tabla) {
    const claves = Object.keys(tabla).sort((a, b) => b.length - a.length);
    if (!claves.length) return texto;
    const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(?<![\\p{L}\\p{N}_])(?:${claves.map(esc).join("|")})(?![\\p{L}\\p{N}_])`, "giu");
    const bajo = {};
    for (const k of claves) bajo[k.toLowerCase()] = tabla[k];
    return texto.replace(re, m => bajo[m.toLowerCase()] ?? m);
}

function tarjetaVoz(p) {
    const actual = p.toml.voz || "";
    const texto = el("input", { type: "text", value: `Hola, soy ${p.toml.nombre || "tu asistente"}. ¿En qué te ayudo?` });

    const vel = el("input", { type: "range", min: "0.6", max: "1.6", step: "0.05", value: String(ritmo.ls) });
    const velTxt = el("span", { class: "tenue" });
    const pau = el("input", { type: "range", min: "0", max: "1.5", step: "0.05", value: String(ritmo.pausa) });
    const pauTxt = el("span", { class: "tenue" });
    const lsDesplegado = numero(p.toml.voz_length_scale, 1.0);
    const pausaDesplegada = numero(p.toml.voz_pausa_s, 0.2);
    const botonRitmo = el("button", { class: "mini", onclick: () => proponerPerfil({
        tipo: "voz_ritmo",
        valor: { voz_length_scale: Math.round(ritmo.ls * 100) / 100,
                 voz_pausa_s: Math.round(ritmo.pausa * 100) / 100 },
        clave: "ritmo",
        antes: `length_scale ${coma(lsDesplegado)}, pausa ${coma(pausaDesplegada)} s`,
        despues: `length_scale ${coma(ritmo.ls)}, pausa ${coma(ritmo.pausa)} s`,
    }) }, "Proponer este ritmo");
    const refrescarRitmo = () => {
        ritmo.ls = parseFloat(vel.value);
        ritmo.pausa = parseFloat(pau.value);
        // length_scale alarga los fonemas: 1,2 es MÁS LENTO. Se muestra como velocidad.
        velTxt.textContent = `velocidad ×${coma(1 / ritmo.ls)}`;
        pauTxt.textContent = `pausa ${coma(ritmo.pausa)} s`;
        botonRitmo.disabled = Math.abs(ritmo.ls - lsDesplegado) < 0.001 &&
                              Math.abs(ritmo.pausa - pausaDesplegada) < 0.001;
    };
    vel.addEventListener("input", refrescarRitmo);
    pau.addEventListener("input", refrescarRitmo);
    refrescarRitmo();

    return el("section", { class: "tarjeta" },
        el("h2", {}, "🗣️ Voz"),
        el("p", { class: "tenue" }, "La latencia la manda el tamaño del modelo, no la calidad. ",
           "«Escuchar» usa el ritmo y el diccionario tal como están acá, antes de proponerlos."),
        el("div", { class: "controles-voz" }, texto),
        el("div", { class: "controles-voz" }, vel, velTxt, pau, pauTxt, botonRitmo),
        info.voces.map(v => {
            const esActual = v.ruta === actual;
            const estado = el("span", { class: "tenue" });
            // Multi-hablante: un botón por hablante. El bot usa siempre el 0.
            const hablantes = Object.entries(v.hablantes || {}).sort((a, b) => a[1] - b[1]);
            const botones = hablantes.length > 1
                ? hablantes.map(([h, id]) => el("button", { class: "mini",
                      onclick: () => escuchar(v, texto.value, estado, id) }, `▶ ${h}`))
                : [el("button", { class: "mini", onclick: () => escuchar(v, texto.value, estado) },
                      "▶ Escuchar")];
            const detalle = `${v.mb} MB · ${v.calidad || "—"}` + (hablantes.length > 1
                ? ` · hablantes ${hablantes.map(([h]) => h).join(" y ")}; el bot usa ${hablantes[0][0]}`
                : "");
            return el("div", { class: "voz" },
                el("div", { class: "nombre" }, v.nombre,
                    esActual ? el("span", { class: "actual" }, "en uso") : null,
                    el("div", { class: "tenue" }, detalle)),
                estado,
                ...botones,
                esActual ? null : el("button", {
                    class: "mini",
                    onclick: () => proponerPerfil({ tipo: "voz", valor: v.nombre + ".onnx",
                        antes: actual.split("/").pop(), despues: v.nombre + ".onnx", clave: "voz" }),
                }, "Proponer"));
        }));
}

function tarjetaPronunciacion(p) {
    const desplegado = JSON.stringify(Object.fromEntries(
        Object.entries(p.pronunciacion || {}).sort()));
    const cuerpo = el("tbody");
    const frase = el("input", { type: "text",
        value: "Pregúntale a Codex por el contrato de CyD en Ñuble." });
    const estadoFrase = el("span", { class: "tenue" });
    const cuenta = el("span", { class: "tenue" });
    const boton = el("button", { class: "mini", onclick: () => {
        const tabla = tablaDiccionario();
        proponerPerfil({ tipo: "pronunciacion", valor: tabla, clave: "diccionario",
                   antes: `${Object.keys(p.pronunciacion || {}).length} palabras`,
                   despues: `${Object.keys(tabla).length} palabras` });
    } }, "Proponer diccionario");

    const actualizar = () => {
        const tabla = tablaDiccionario();
        cuenta.textContent = `${Object.keys(tabla).length} palabras`;
        boton.disabled = JSON.stringify(Object.fromEntries(Object.entries(tabla).sort())) === desplegado;
    };
    const fila = (item) => {
        const estado = el("span", { class: "tenue" });
        const escrito = el("input", { type: "text", value: item.escrito, maxlength: "40",
                                      placeholder: "se escribe" });
        const dicho = el("input", { type: "text", value: item.dicho, maxlength: "80",
                                    placeholder: "se dice" });
        escrito.addEventListener("input", () => { item.escrito = escrito.value; actualizar(); });
        dicho.addEventListener("input", () => { item.dicho = dicho.value; actualizar(); });
        const tr = el("tr", {},
            el("td", {}, escrito), el("td", {}, dicho),
            el("td", {},
                el("button", { class: "mini", title: "escuchar cómo queda",
                    onclick: () => escuchar(vozActual(p), item.escrito, estado) }, "▶"), " ",
                el("button", { class: "mini", title: "quitar", onclick: () => {
                    diccionario.splice(diccionario.indexOf(item), 1);
                    tr.remove();
                    actualizar();
                } }, "✕"), " ", estado));
        return tr;
    };
    for (const item of diccionario) cuerpo.append(fila(item));
    actualizar();

    return el("section", { class: "tarjeta" },
        el("h2", {}, "🔤 Pronunciación"),
        el("p", { class: "tenue" }, "Se aplica sólo a lo que dice Piper; el chat muestra la palabra ",
           "bien escrita. Palabras enteras y sin importar mayúsculas. Escribe cómo SUENA: ",
           "«ce y de», «códex»."),
        el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Se escribe"),
            el("th", {}, "Se dice"), el("th", {}, ""))), cuerpo),
        el("div", { class: "controles-voz separado" },
            el("button", { class: "mini", onclick: () => {
                const item = { escrito: "", dicho: "" };
                diccionario.push(item);
                const tr = fila(item);
                cuerpo.append(tr);
                tr.querySelector("input").focus();
            } }, "+ Agregar palabra"), cuenta, boton),
        el("h3", {}, "Probar una frase con la voz en uso"),
        el("div", { class: "controles-voz" }, frase,
            el("button", { class: "mini",
                onclick: () => escuchar(vozActual(p), frase.value, estadoFrase) }, "▶ Probar"),
            estadoFrase));
}

function tarjetaCarpeta(p) {
    const titulo = el("h2", {}, "📁 Carpetas de lectura");
    if ((p.toml.vaults || []).includes("personal")) {
        return el("section", { class: "tarjeta" }, titulo,
            el("p", { class: "tenue" }, `${p.toml.nombre} ya ve vault_personal entero: una carpeta `,
               "suelta no le agrega nada. Esto es para un perfil sin vault, como Pilar."));
    }
    const actuales = p.toml.carpetas || [];
    const sonda = Object.fromEntries(p.sonda.filter(s => s.etiqueta.startsWith("carpeta "))
        .map(s => [s.etiqueta.slice(8), s.visible]));
    const ruta = el("input", { type: "text", placeholder: "p. ej. 20-Areas/Recetas" });
    return el("section", { class: "tarjeta" }, titulo,
        el("p", { class: "tenue" }, "Una subcarpeta de vault_personal, en sólo lectura y nada más: ",
           "systemd la monta aparte y el vault entero sigue tapado. Amplía permisos, así que al ",
           "aplicarla el script verifica desde adentro del bot que se ve la carpeta y NO el vault. ",
           "Si hay archivos con permiso 600 lo avisa: el bot no los podría leer."),
        actuales.length ? el("table", {}, actuales.map(c => el("tr", {},
            el("td", {}, el("code", {}, c)),
            el("td", {}, el("span", { class: "estado " + (sonda[c] ? "ok" : "mal") },
                sonda[c] ? "✅ montada" : "no se ve desde el bot")),
            el("td", {}, el("button", { class: "mini", onclick: () => proponerPerfil({
                tipo: "quitar_carpeta", valor: c, clave: "carpetas",
                antes: actuales.join(", "), despues: actuales.filter(x => x !== c).join(", ") || "ninguna",
            }) }, "quitar")))))
            : el("p", { class: "tenue" }, "No tiene carpetas abiertas."),
        el("div", { class: "controles-voz separado" }, el("span", {}, "vault_personal/"), ruta,
           el("button", { class: "mini", onclick: () => {
               const v = ruta.value.trim().replace(/^\/+|\/+$/g, "");
               if (!v || v.split("/").some(x => x === ".." || x.startsWith("."))) { ruta.focus(); return; }
               proponerPerfil({ tipo: "carpeta_lectura", valor: v, clave: "carpetas",
                          antes: actuales.join(", ") || "ninguna",
                          despues: [...actuales, v].join(", ") });
           } }, "Proponer abrirla")),
        el("p", { class: "tenue" }, "Para que el bot la use, pregunta nombrándola como tuya: ",
           "«busca en mis recetas…». El clasificador manda lo propio a claude."));
}

function tarjetaPersonalidad(p) {
    const opciones = (valores, actual) => valores.map(([v, t]) =>
        el("option", { value: v, selected: v === actual }, t));
    const tono = el("select", {}, opciones([["neutro", "Neutro"], ["cercano", "Cercano (de tú)"],
        ["formal", "Formal"]], p.toml.tono || "neutro"));
    const largo = el("select", {}, opciones([["normal", "Normal"], ["breve", "Breve (1 a 3 frases)"],
        ["detallado", "Detallado"]], p.toml.largo || "normal"));
    const sobre = el("textarea", { rows: "5", maxlength: "1500",
        placeholder: `Lo que ${p.toml.nombre} debería saber de ${p.toml.persona}: gustos, rutinas, cómo prefiere que le respondan.` });
    sobre.value = (p.sobre || "").trim();
    const cuenta = el("span", { class: "tenue" });
    const contar = () => { cuenta.textContent = `${sobre.value.length}/1500`; };
    sobre.addEventListener("input", contar);
    contar();
    return el("section", { class: "tarjeta" },
        el("h2", {}, "🎭 Personalidad"),
        el("p", { class: "tenue" }, "El tono y el largo van a todas las rutas. El «sobre mí» va SÓLO a ",
           "claude y codex: no a la web (se podría colar en una búsqueda) ni a Groq (vive en el vault)."),
        el("div", { class: "controles-voz" }, el("label", {}, "Tono ", tono),
           el("label", {}, "Largo ", largo),
           el("button", { class: "mini", onclick: () => proponerPerfil({
               tipo: "personalidad", valor: { tono: tono.value, largo: largo.value }, clave: "estilo",
               antes: `${p.toml.tono || "neutro"} · ${p.toml.largo || "normal"}`,
               despues: `${tono.value} · ${largo.value}` }) }, "Proponer estilo")),
        el("h3", {}, `Sobre ${p.toml.persona}`),
        sobre,
        el("div", { class: "controles-voz separado" }, cuenta,
           el("button", { class: "mini", onclick: () => proponerPerfil({
               tipo: "sobre", valor: sobre.value, clave: "sobre mí",
               antes: `${(p.sobre || "").trim().length} caracteres`,
               despues: `${sobre.value.trim().length} caracteres` }) }, "Proponer «sobre mí»")));
}

function tarjetaModeloYTope(p) {
    const modelo = el("select", {}, [["", "El de la cuenta"], ["sonnet", "Sonnet"],
        ["opus", "Opus"], ["haiku", "Haiku"]].map(([v, t]) =>
        el("option", { value: v, selected: v === (p.toml.modelo_claude || "") }, t)));
    const rutas = ["claude", "codex", "web", "gpt", "vision", "noticias"].filter(r => (p.toml.rutas || []).includes(r));
    const topes = p.toml.tope_diario || {};
    const uso = p.uso_hoy || {};
    const entradas = {};
    const filas = rutas.map(r => {
        entradas[r] = el("input", { type: "number", min: "0", max: "1000", step: "1",
                                    value: String(topes[r] || 0), class: "numero" });
        const n = uso[r] || 0, t = topes[r];
        return el("tr", {},
            el("td", {}, r, r === "codex" ? el("div", { class: "tenue" }, "topado cae a claude") : null),
            el("td", { class: "num" }, t ? `${n} / ${t}` : String(n)),
            el("td", {}, entradas[r]));
    });
    return el("section", { class: "tarjeta" },
        el("h2", {}, "🧮 Modelo y tope diario"),
        el("div", { class: "controles-voz" }, el("label", {}, "Modelo de Claude ", modelo),
           el("button", { class: "mini", onclick: () => proponerPerfil({
               tipo: "modelo_claude", valor: modelo.value, clave: "modelo",
               antes: p.toml.modelo_claude || "el de la cuenta",
               despues: modelo.value || "el de la cuenta" }) }, "Proponer modelo")),
        el("p", { class: "tenue" }, "Aplica a la ruta claude y a la web por Claude. Codex usa el de su cuenta; ",
           "la ruta general, el que fija n8n (Groq)."),
        el("h3", {}, "Consultas de hoy y tope (0 = sin tope)"),
        el("table", {}, el("tr", {}, el("th", {}, "Ruta"), el("th", {}, "Hoy"), el("th", {}, "Tope")), filas),
        el("p", { class: "tenue" }, "Al llegar al tope, codex cae a claude (leen lo mismo). Las demás ",
           "contestan que se llegó al tope: mandarlas a Groq daría respuestas inventadas."),
        el("div", { class: "controles-voz separado" },
           el("button", { class: "mini", onclick: () => {
               const valor = Object.fromEntries(rutas.map(r => [r, parseInt(entradas[r].value, 10) || 0]));
               proponerPerfil({ tipo: "tope_diario", valor, clave: "topes",
                   antes: Object.entries(topes).map(([r, n]) => `${r} ${n}`).join(", ") || "sin topes",
                   despues: Object.entries(valor).filter(([, n]) => n).map(([r, n]) => `${r} ${n}`).join(", ") || "sin topes" });
           } }, "Proponer topes")));
}

/* ---------- voz: vista previa con Piper ---------- */

// Se reproduce con Web Audio y NO con <audio src=blob:…>. El CSP de Cockpit deja
// media-src en 'self', así que un blob: se bloquea y el navegador sólo dice "no
// supported source was found" — que parece un WAV roto y no lo es (24-09-2026).
let contextoAudio = null;

async function escuchar(voz, texto, estado, hablante = null) {
    if (audio) { try { audio.stop(); } catch (e) { /* ya terminó */ } audio = null; }
    if (!texto.trim()) { estado.textContent = "no hay texto"; return; }
    estado.textContent = "sintetizando…";
    const t0 = performance.now();
    let bytes = 0;
    try {
        // Las mismas tres cosas que aplica el bot: diccionario, velocidad y pausa.
        const dicho = pronunciarJS(texto.slice(0, 400), tablaDiccionario());
        const proc = cockpit.spawn([PIPER, "--model", voz.ruta,
                                    "--length_scale", String(ritmo.ls),
                                    "--sentence_silence", String(ritmo.pausa),
                                    ...(hablante === null ? [] : ["--speaker", String(hablante)]),
                                    "--output_file", "-", "--quiet"],
                                   { binary: true, err: "message" });
        proc.input(enc.encode(dicho + "\n"));
        const wav = await proc;
        bytes = wav.byteLength || wav.length || 0;
        const ms = performance.now() - t0;
        contextoAudio = contextoAudio || new AudioContext();
        if (contextoAudio.state === "suspended") await contextoAudio.resume();
        // decodeAudioData se queda con el buffer: se le pasa una copia exacta.
        const copia = new Uint8Array(wav).buffer;
        const buffer = await contextoAudio.decodeAudioData(copia);
        const fuente = contextoAudio.createBufferSource();
        fuente.buffer = buffer;
        fuente.connect(contextoAudio.destination);
        fuente.start();
        audio = fuente;
        estado.textContent = `${(ms / 1000).toFixed(1).replace(".", ",")} s · ${buffer.duration.toFixed(1).replace(".", ",")} s de audio`;
    } catch (e) {
        // Los bytes dicen de quién es la culpa: 0 = Piper no entregó nada; >0 = el navegador.
        estado.textContent = `falló (${bytes} bytes): ` + (e.message || e);
    }
}

/* ---------- diagnóstico: latencias del journal ---------- */

async function pintarDiagnostico() {
    const cont = document.getElementById("diag");
    const perfil = perfilActual;
    let out = "";
    try {
        out = await cockpit.spawn(["journalctl", "-u", `botv3@${perfil}`, "-n", "2000",
                                   "-o", "cat", "--no-pager"], { err: "ignore" });
    } catch (e) { /* sin journal: tabla vacía */ }
    if (perfil !== perfilActual) return;
    // Dos líneas por consulta: la vieja (`ruta= latencia= voz=`, que no se toca) y,
    // desde el 24-09-2026, `etapas ruta= whisper= router= agente= tts=` justo después.
    // Se emparejan por orden: cada `etapas` pertenece a la `latencia` anterior.
    const filas = [];
    const reTotal = /^(\d{4}-\d\d-\d\d) (\d\d:\d\d):\d\d,\d+ INFO ruta=(\S+) latencia=([\d.]+)s voz=(\w+)/;
    const reEtapas = /INFO etapas ruta=\S+ whisper=([\d.]+) router=([\d.]+) agente=([\d.]+) tts=([\d.]+)/;
    // Desde el 29-09-2026 `cuenta ruta= cuenta=` sale ANTES de la línea de latencia
    // de la misma consulta: se guarda y se le pega a la próxima.
    const reCuenta = /INFO cuenta ruta=\S+ cuenta=(\S+)/;
    let cuentaPendiente = null;
    for (const l of out.split("\n")) {
        const c = l.match(reCuenta);
        if (c) { cuentaPendiente = c[1]; continue; }
        const m = l.match(reTotal);
        if (m) { filas.push({ m, e: null, cuenta: cuentaPendiente }); cuentaPendiente = null; continue; }
        const e = l.match(reEtapas);
        if (e && filas.length && !filas[filas.length - 1].e) filas[filas.length - 1].e = e;
    }
    const ultimas = filas.slice(-10).reverse();
    const seg = x => x == null ? "—" : Number(x).toFixed(1).replace(".", ",");
    const barra = e => {
        if (!e) return el("span", { class: "tenue" }, "sin desglose (anterior al 24-09)");
        const partes = [["whisper", +e[1]], ["router", +e[2]], ["agente", +e[3]], ["tts", +e[4]]];
        const total = partes.reduce((s, [, v]) => s + v, 0) || 1;
        return el("div", { class: "etapas", title: partes.map(([n, v]) => `${n} ${seg(v)} s`).join(" · ") },
            partes.filter(([, v]) => v > 0.005).map(([n, v]) =>
                el("span", { class: `etapa etapa-${n}`, style: false,
                             "data-ancho": String(Math.max(2, Math.round(100 * v / total))) },
                   `${n} ${seg(v)}`)));
    };
    const tabla = ultimas.length ? el("table", {},
        el("tr", {}, el("th", {}, "Cuándo"), el("th", {}, "Ruta"), el("th", {}, "Total"),
           el("th", {}, "Voz"), el("th", {}, "Por etapa (s)")),
        ultimas.map(({ m, e, cuenta }) => el("tr", {},
            el("td", {}, `${m[1].slice(8)}-${m[1].slice(5, 7)} ${m[2]}`),
            el("td", {}, m[3], cuenta ? el("div", { class: "tenue" }, nombreCuenta(cuenta)) : null),
            el("td", { class: "num" }, seg(m[4]) + " s"),
            el("td", {}, m[5] === "True" ? "sí" : "no"),
            el("td", {}, barra(e)))))
        : el("p", { class: "tenue" }, "Sin consultas en el journal reciente.");
    cont.replaceChildren(el("h2", {}, "⏱️ Últimas consultas, por etapa"), tabla,
        el("p", { class: "tenue" }, "Whisper = transcribir la nota de voz · router = el clasificador de n8n · ",
           "agente = la ruta que contesta · tts = Piper. El umbral de 5 s para hablar mide sólo la ruta."));
    // El ancho va por CSSOM y no por atributo style: el CSP de Cockpit bloquea estilos en línea.
    cont.querySelectorAll(".etapa").forEach(s => { s.style.flexGrow = s.dataset.ancho; });
}

/* ---------- propuestas ---------- */

// `proponer()`, el diálogo y la lista de propuestas viven en comun.js, que también usa
// 💳 Cuentas. Acá sólo se le dice a qué perfil va: el de la pestaña abierta.
function proponerPerfil(cambio) {
    proponer(cambio, perfilActual);
}

/* ---------- 🏠 casa: lista, memoria del hogar, pendientes y buzón ---------- */

// Todo lo que escribe va por `casa-cockpit` (usa el flock de compras.py, igual que
// los bots) o por cockpit.file con su etiqueta, que falla si el archivo cambió
// entre que se leyó y se guarda: casa.md vive en una carpeta de Syncthing.
const CASA_CLI = "/usr/local/bin/casa-cockpit";
const CASA_MD = "/opt/nodo/datos/nodo-memoria/casa.md";
const DESCARTADOS = "/home/dcifu004/.local/share/bots-casa-descartados.json";

function normalizarTexto(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
        .replace(/[^\p{L}\p{N} ]/gu, " ").replace(/\s+/g, " ").trim();
}

async function casaCli(...args) {
    return JSON.parse(await cockpit.spawn([CASA_CLI, ...args], { err: "message" }));
}

async function pintarCasa() {
    const cont = document.getElementById("casa");
    let estado, md = "", tag = null, descartados = [];
    try {
        estado = await casaCli("estado");
    } catch (e) {
        cont.replaceChildren(el("h2", {}, "🏠 Casa"),
            el("div", { class: "aviso rojo" }, "No pude leer la casa: " + (e.message || e)));
        return;
    }
    const archivoMd = cockpit.file(CASA_MD);
    try { [md, tag] = await new Promise((ok, mal) => archivoMd.read().then((c, t) => ok([c || "", t])).catch(mal)); }
    catch (e) { md = ""; }
    try { descartados = (await cockpit.file(DESCARTADOS, { syntax: JSON }).read()) || []; }
    catch (e) { descartados = []; }

    // --- lista de compras ---
    const nuevo = el("input", { type: "text", placeholder: "tomates, aceite y queso", maxlength: "300" });
    const aviso = el("span", { class: "tenue" });
    const agregar = async () => {
        if (!nuevo.value.trim()) return;
        const r = await casaCli("agregar", nuevo.value);
        aviso.textContent = r.repetidos.length ? `ya estaban: ${r.repetidos.join(", ")}` : "";
        nuevo.value = "";
        pintarCasa();
    };
    nuevo.addEventListener("keydown", ev => { if (ev.key === "Enter") agregar(); });
    const lista = estado.items.length ? el("table", {}, estado.items.map(i => el("tr", {},
        el("td", {}, i.texto),
        el("td", { class: "tenue" }, i.quien),
        el("td", { class: "tenue num" }, i.viejo ? `⏳ ${Math.floor(i.dias)} d` : `${Math.floor(i.dias)} d`),
        el("td", {}, el("button", { class: "mini", title: "quitar", onclick: async () => {
            await casaCli("quitar", i.id); pintarCasa();
        } }, "✕")))))
        : el("p", { class: "tenue" }, "La lista está vacía.");

    // --- por confirmar: lo que los bots anotaron y nadie pasó a casa.md ---
    const mdNorm = normalizarTexto(md);
    const todos = [...estado.pendientes, ...((info && info.casa_legado) || [])];
    const pendientes = todos.filter(p => !descartados.includes(p.sha)
        && !mdNorm.includes(normalizarTexto(p.texto)));
    const confirmar = async (p) => {
        const fecha = (p.meta.match(/\d{4}-\d\d-\d\d/) || [""])[0];
        const linea = `- ${p.texto.replace(/^que\s+/i, "")} (anotado por ${p.perfil}${fecha ? " el " + fecha : ""})`;
        try {
            await archivoMd.modify(viejo => {
                const texto = viejo || "# Memoria de la casa\n\n## Hechos\n";
                return texto.replace(/\s*$/, "") + "\n" + linea + "\n";
            });
        } catch (e) {
            mostrarError("No pude escribir casa.md: " + (e.message || e));
            return;
        }
        await quitarPendiente(p);
    };
    const quitarPendiente = async (p) => {
        if (p.origen === "casa") {
            await casaCli("descartar", p.perfil, p.sha);
        } else {
            // El legado es del STATE_DIR viejo, que el bot ya no lee: no se toca el
            // archivo (el de pilar ni siquiera es nuestro), sólo se recuerda la decisión.
            await cockpit.file(DESCARTADOS, { syntax: JSON }).modify(v => [...(v || []), p.sha]);
        }
        pintarCasa();
    };
    const porConfirmar = pendientes.length ? el("table", {}, pendientes.map(p => el("tr", {},
        el("td", {}, p.texto, p.origen === "legado"
            ? el("div", { class: "tenue" }, "del directorio viejo: el bot ya no la lee") : null),
        el("td", { class: "tenue" }, `${p.perfil} · ${p.meta.split("·")[0].trim()}`),
        el("td", {}, el("button", { class: "mini", onclick: () => confirmar(p) }, "✅ A la memoria"), " ",
            el("button", { class: "mini", onclick: () => quitarPendiente(p) }, "✖")))))
        : el("p", { class: "tenue" }, "Nada pendiente.");

    // --- memoria de la casa (casa.md) ---
    const area = el("textarea", { rows: "10", spellcheck: "false" });
    area.value = md;
    const estadoMd = el("span", { class: "tenue" });
    const guardarMd = el("button", { class: "mini", onclick: async () => {
        try {
            await archivoMd.replace(area.value, tag);
            estadoMd.textContent = "guardado ✓";
            pintarCasa();
        } catch (e) {
            estadoMd.textContent = "no se guardó: cambió en disco (Syncthing o un bot). Recarga y vuelve a editar.";
        }
    } }, "Guardar casa.md");

    // --- buzón ---
    const buzon = estado.buzon.length ? el("ul", {}, estado.buzon.map(b =>
        el("li", {}, `${b.de} → ${b.para} · ${b.tipo}${b.texto ? ": " + b.texto : ""} · ${b.ts}`)))
        : el("p", { class: "tenue" }, "Vacío: no hay pedidos entre los bots esperando entrega.");

    cont.replaceChildren(
        el("h2", {}, "🏠 Casa"),
        el("p", { class: "tenue" }, "Compartida por los dos bots. Lo que se cambia acá lo ven los dos al tiro."),
        el("div", { class: "rejilla" },
            el("div", {},
                el("h3", {}, `🛒 Lista de compras (${estado.items.length}/${estado.max_items})`),
                lista,
                el("div", { class: "controles-voz separado" }, nuevo,
                    el("button", { class: "mini", onclick: agregar }, "Agregar"), aviso)),
            el("div", {},
                el("h3", {}, `📝 Por confirmar (${pendientes.length})`),
                el("p", { class: "tenue" }, "Lo que un bot anotó «de la casa». Confirmar lo pasa a casa.md, ",
                   "que leen los dos."),
                porConfirmar,
                el("h3", {}, "📬 Buzón entre bots"), buzon)),
        el("details", {}, el("summary", {}, "🧠 Memoria de la casa (casa.md): editar"),
            el("p", { class: "tenue" }, "Es contexto, no órdenes. Vive fuera de los vaults a propósito: ",
               "por eso puede viajar también a la ruta general."),
            area, el("div", { class: "controles-voz separado" }, guardarMd, estadoMd)));
}

/* ---------- 🚧 en construcción, y lo que viene ---------- */

function pintarProximo() {
    const obras = [
        ["🔔", "Sonidos de estado", "Un tono al escucharte, otro si piensa más de 3 s y otro si hay error.",
         "Necesita el micrófono de la sala (escucha.py)."],
        ["👂", "Wake word", "«Hola Jaime» / «Hola Pilar»: sensibilidad por perfil con medidor en vivo y registro de falsos positivos con su audio.",
         "Necesita el micrófono de la sala (escucha.py)."],
        ["⚡", "Atajos de voz", "Una frase dispara una rutina: «buenas noches» apaga luces, lee la agenda de mañana y activa el silencio.",
         "Necesita el micrófono y las acciones de Home Assistant con confirmación (N4)."],
        ["📢", "Avisos del nodo por el parlante", "Lo que hoy manda @Dcs_v5bot, dicho en voz alta y sólo en el horario que definas.",
         "Necesita un parlante fijo en la Pi y el horario de silencio."],
        ["🎙️", "Voz propia para Piper", "Entrenar una voz a partir de grabaciones, para que Jaime y Pilar suenen distintos y propios.",
         "Se entrena en un PC con GPU (backlog: GPU + Ollama); el resultado sí corre en la Pi."],
    ];
    const ideas = [
        "🧳 Modo invitado — sólo rutas inofensivas y sin memoria de la casa",
        "🌙 Horario de silencio — de noche no escucha, o escucha y no habla",
        "☀️ Resumen matinal hablado — calendario, clima y noticias por perfil",
        "🗂️ Historial con privacidad — búsqueda, «olvidar esto» y retención",
        "🧪 Laboratorio A/B — la misma pregunta con dos configuraciones",
        "🧬 Plantillas de perfil — exportar uno como base de otro",
        "✅ Aplicar desde acá — con el modo administrativo, cuando sudo pida clave",
    ];
    document.getElementById("proximo").replaceChildren(
        el("h2", {}, "🚧 En construcción"),
        el("div", { class: "obras" }, obras.map(([ico, nombre, que, falta]) =>
            el("div", { class: "obra" },
                el("div", { class: "obra-titulo" }, el("span", { class: "obra-ico" }, ico), nombre,
                   el("span", { class: "insignia" }, "🚧 en construcción")),
                el("p", {}, que),
                el("p", { class: "tenue" }, falta)))),
        el("details", {}, el("summary", {}, "Otras ideas anotadas"),
            el("ul", { class: "ideas" }, ideas.map(i => el("li", {}, i)))));
}

/* ---------- arranque ---------- */

document.getElementById("actualizar").addEventListener("click", cargar);
pintarProximo();
cockpit.transport.wait(cargar);
