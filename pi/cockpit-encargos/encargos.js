/* Doc. 28: vista sólo de lectura, salvo «⚙️ Reparto y modelos» (encargo 23a), que propone. «🔔 Avisos» (encargo 23b) es de lectura, salvo el aviso previo de cuota (encargo 24), que propone. «Ahora» acciona las colas con Reanudar, Pausar y Detener (encargo 46c) y el despacho con Pausar despacho y Abrir despacho (encargo 50a). Las rutas y los argumentos de spawn son fijos. */
"use strict";
const DIR = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos";
const USO = "/opt/nodo/datos/uso.json", CUENTAS = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3/cuentas.toml";
const $ = s => document.querySelector(s); let d, panel = "ahora";
const falta = () => el("span", { class: "tenue" }, "sin datos");
const val = x => x == null || x === "" ? "sin datos" : String(x);
function aviso(x) { $("#error").hidden = !x; $("#error").textContent = x || ""; }
async function archivo(p, json) { try { const x = await cockpit.file(p).read(); return json ? JSON.parse(x) : x; } catch (e) { return null; } }
function nombres(t) { const r = {}; let k; for (const l of (t || "").split("\n")) { let m = l.match(/^\[([^\]]+)\]/); if (m) { k = m[1]; r[k] = k; } m = l.match(/^nombre\s*=\s*"([^"]+)"/); if (m && k) r[k] = m[1]; } return r; }
function historia(t) { try { return (t || "").split("\n").filter(Boolean).map(x => JSON.parse(x)); } catch (e) { return null; } }
function espera(ts) { return ts.filter(Boolean).map(t => { const n = (t.match(/^nombre\s*=\s*"([^"]+)"/m) || [])[1]; const a = (t.match(/^esperar\s*=\s*\[([^\]]*)\]/m) || [])[1]; return n ? { n, a: [...(a || "").matchAll(/"([^"]+)"/g)].map(x => x[1]) } : null; }).filter(Boolean); }
function fase(bit, sesion) { const etapa = sesion.replace(/^cola/, ""); const ls = (bit || "").split("\n").reverse(); const re = new RegExp(`\\b(${etapa}): (autor|rev\\d+|fix\\d+) con .*?\\(pronóstico (\\d+(?:\\.\\d+)?) min`, "i"); const l = ls.find(x => re.test(x)); const m = l && l.match(re), fecha = l && l.match(/- (\d\d)-(\d\d) (\d\d:\d\d) ·/); return m ? { etapa: m[1], fase: m[2], inicio: fecha ? `${new Date().getFullYear()}-${fecha[2]}-${fecha[1]}T${fecha[3]}:00-03:00` : null, pronostico: { min: Number(m[3]) }, deducido: true } : {}; }
function manifiesto(t) { const r = []; for (const b of (t || "").split("[[etapa]]").slice(1)) { const dato = k => (b.match(new RegExp(`^${k}\\s*=\\s*"([^"]+)"`, "m")) || [])[1]; const id = dato("id"); if (id) r.push({ id, autor: dato("autor"), revisor: dato("revisor") }); } return r; }
// Encargo 34: qué hace cada cola y cada etapa, y la barra de uso por fase. Todo es de lectura.
// Lo que viene de un .toml o de un .md lo escribe cualquier agente: se muestra como texto (nunca como HTML)
// y pasa por seguro(), el criterio de la lista blanca de la 22b/22c (programados.py) llevado a prosa: un token se
// muestra sólo si es de signos, un número, una ruta o una palabra legibles; lo demás es «oculto». Las reglas duras
// son las mismas (ninguna corrida de más de 16, ni más de 16 letras y dígitos en un token que no sea ruta, ni
// tramos que mezclen letras y dígitos, ni el valor que sigue a una clave sensible). Los RE_ los lee la prueba.
const OCULTO = "«oculto»";
const RE_TRAMO = /[A-Za-z0-9_À-ÿ]+/g;
const RE_PALABRA = /^[A-Za-z0-9_À-ÿ]+(?:[._\/–—-][A-Za-z0-9_À-ÿ]+)*$/;
const RE_SEGMENTO = /^\.?[A-Za-z0-9_À-ÿ]+(?:[._-][A-Za-z0-9_À-ÿ]+)*$/;
const RE_NUMERO = /^[0-9]+(?:[.,:\/-][0-9]+)*$/;
const RE_RUTA = /^(?:\/|~\/|\.\/)/;
const RE_PREFIJO = /^(?:(?:sk|pk|rk)-|gh[pousr]_|github_pat_|xox[abprs]-|akia|eyj|[0-9]{6,}:)/i;
const RE_SENSIBLE = /token|key|secret|password|pass|pwd|auth|bearer|api/i;
const RE_BORDE = /^(?!~\/|\.\/)[^A-Za-z0-9_À-ÿ\/-]+|[^A-Za-z0-9_À-ÿ]+$/g;
const RE_ESQUEMA = /^(?:bearer|basic|token|-{1,2}p|-pw)$/i;
const RE_CLAVE = /[:=]["'”»)\]]*$/;
const RE_MAYUSCULA_Y_DIGITO = /[A-Z].*[0-9]|[0-9].*[A-Z]/;
const RE_TITULO_PREFIJO = /^Encargo\s+[A-Za-z0-9_.-]+\s*[:—–-]\s*/;
const RE_TITULO_AUTOR = /\s*\((?:[^()]|\([^()]*\))*[0-9]{2}-[0-9]{2}-[0-9]{4}\)\s*$/;
const RE_TITULO_FECHA = /\s*[—–-]\s*[0-9]{2}-[0-9]{2}-[0-9]{4}\s*$/;
const mixto = s => /[A-Za-z_À-ÿ]/.test(s) && /[0-9]/.test(s);
function tramosMalos(t) { const rs = t.match(RE_TRAMO) || [], n = rs.filter(mixto).length; return rs.some(r => r.length > 16) || n >= 3 || (rs.length >= 3 && n >= 1); }
function rutaSegura(t) {
    let seguidos = 0;
    for (const s of t.replace(RE_RUTA, "").split("/").filter(Boolean)) {
        seguidos = mixto(s) ? seguidos + 1 : 0;
        if (seguidos >= 4 || tramosMalos(s) || !RE_SEGMENTO.test(s) || (!/[-_]/.test(s) && s.length >= 14 && RE_MAYUSCULA_Y_DIGITO.test(s))) return false;
    }
    return true;
}
function tokenSeguro(t) {
    const c = t.replace(RE_BORDE, ""), rs = c.match(RE_TRAMO) || [];
    if (!rs.length) return true;                                        // sólo signos o emoji
    if (RE_PREFIJO.test(c)) return false;
    if (RE_RUTA.test(c)) return rutaSegura(c);
    if (tramosMalos(c) || rs.join("").length > 16) return false;
    if (RE_NUMERO.test(c)) return true;
    const i = c.indexOf("=");
    if (i >= 0) { const n = c.slice(0, i).replace(/^-+/, ""); return RE_SEGMENTO.test(n) && !RE_SENSIBLE.test(n) && tokenSeguro(c.slice(i + 1)); }
    if (c.startsWith("-")) return !/^-p./i.test(c) && RE_SEGMENTO.test(c.replace(/^-+/, ""));
    return RE_PALABRA.test(c);
}
function seguro(texto) {
    let previo = "";
    return String(texto).split(/(\s+)/).map(p => {
        if (!p.trim()) return p;
        const a = previo.replace(RE_BORDE, "");
        const marcado = RE_ESQUEMA.test(a) || (RE_CLAVE.test(previo) && RE_SENSIBLE.test(previo)) || (a.startsWith("--") && RE_SENSIBLE.test(a.split("=")[0]));
        previo = p;
        return marcado || !tokenSeguro(p) ? OCULTO : p;
    }).join("");
}
const unaLinea = x => seguro(String(x).replace(/\s+/g, " ").trim());
// `resumen` es opcional en la raíz del manifiesto y en cada [[etapa]]. La raíz es lo que va antes de la primera tabla.
function cadena(b, k) { const m = b.match(new RegExp(`^${k}\\s*=\\s*"((?:[^"\\\\]|\\\\.)*)"`, "m")); return m && m[1] ? m[1].replace(/\\(["\\])/g, "$1") : null; }
function resumenes(t) {
    const raiz = (t || "").split(/^\s*\[/m)[0], cola = cadena(raiz, "nombre");
    if (!cola) return null;
    return { cola, resumen: cadena(raiz, "resumen"), motivo: cadena(raiz, "motivo"),
        etapas: t.split("[[etapa]]").slice(1).map(b => ({ id: cadena(b, "id"), resumen: cadena(b, "resumen"), encargo: cadena(b, "encargo") })).filter(x => x.id) };
}
// El título del encargo: la primera línea «# », sin «Encargo NN:» ni el autor y la fecha del final.
function tituloLimpio(md) { const m = (md || "").match(/^# +(.+)$/m); return m ? m[1].replace(RE_TITULO_PREFIJO, "").replace(RE_TITULO_AUTOR, "").replace(RE_TITULO_FECHA, "").trim() || null : null; }
// Los .md se leen una vez (el título no cambia) y sólo los de las etapas sin `resumen`. El nombre no puede salir de DIR.
const titulos = new Map();
async function leerTitulos(rs) {
    const fs = [...new Set(rs.flatMap(c => c.etapas).filter(e => !e.resumen && /^[A-Za-z0-9_.-]+\.md$/.test(e.encargo || "")).map(e => e.encargo))].filter(f => !titulos.has(f));
    await Promise.all(fs.map(async f => { const t = await archivo(`${DIR}/${f}`); if (t != null) titulos.set(f, tituloLimpio(t)); }));
}
function resumenCola(nombre) { const c = (d.resumenes || []).find(x => x.cola === nombre), t = c && (c.resumen || c.motivo); return t ? unaLinea(t) : "sin resumen"; }
// Si dos colas traen la misma etapa (una la cierra después), vale la cola más nueva.
function etapaDe(id) {
    const xs = (d.resumenes || []).flatMap(c => c.etapas.filter(e => e.id === String(id)).map(e => ({ cola: c.cola, ...e })));
    return xs.sort((a, b) => a.cola.localeCompare(b.cola, "es", { numeric: true })).at(-1) || null;
}
function resumenEtapa(e) { const t = e && (e.resumen || titulos.get(e.encargo)); return t ? unaLinea(t) : "sin resumen"; }
function lineaResumen(texto, antes) { return el("p", { class: `resumen${texto === "sin resumen" ? " tenue" : ""}`, title: texto }, antes ? el("span", { class: "tenue" }, antes) : null, texto); }
function cuentaFase(etapa, fase) { const x = (d.etapas || []).find(x => x.id === String(etapa)); return x ? (/^rev/i.test(fase) ? x.revisor : x.autor) : null; }
function cuenta(id) { return d.nombres && d.nombres[id] ? d.nombres[id] : "sin datos"; }
function uso(id) { try { const x = d.uso.cuentas_interactivo[id].limites; return `5 h ${x.ventana_5h.usado_pct} % · semanal ${x.semanal.usado_pct} %`; } catch (e) { return "sin datos"; } }
// La cola «deducida» de la bitácora: sólo para sesiones viejas que no escriben vivo/<cola>.json.
function vivo() { const s = d.sesiones.find(x => !d.vivos.some(v => v.nombre === x)); if (!s) return null; return { cola: s, ...fase(d.estado, s) }; }
function min(iso) { const n = new Date(iso).getTime(); return Number.isNaN(n) ? null : Math.max(0, Math.round((Date.now() - n) / 60000)); }
// Encargos 24 y 46b: la matriz «Carga vs. capacidad» sale de `cola-run.py --panel` (`reglas`, `colas_fuera` y `cuentas`),
// que la calcula con lo que publica cada cola en vivo/<cola>.json. La página sólo la dibuja. reglas null = no se pudo leer.
// Encargo 34: del mismo panel salen los modelos de [niveles.*] de modelos.toml, para la paleta de la barra de uso.
const esObjeto = x => !!x && typeof x === "object" && !Array.isArray(x);
async function leerPanel() { try { const x = JSON.parse(await cockpit.spawn(["python3", `${DIR}/cola-run.py`, "--panel"], { err: "ignore" })); return { reglas: Array.isArray(x.reglas) ? x.reglas : [], fuera: Array.isArray(x.colas_fuera) ? x.colas_fuera : [], capacidad: esObjeto(x.capacidad_por_vencer) ? x.capacidad_por_vencer : {}, despacho: esObjeto(x.despacho) ? x.despacho : null, pasado: esObjeto(x.pasado) ? x.pasado : null, cuentas: x.cuentas || {}, colas: x.colas && typeof x.colas === "object" ? x.colas : {}, paleta: modelosPaleta(x.modelos) }; } catch (e) { return { reglas: null, fuera: [], capacidad: {}, despacho: null, pasado: null, cuentas: {}, colas: {}, paleta: [] }; } }
async function leer() { const [h, estado, vivos, u, c, tmux, paths, panelColas] = await Promise.all([
    archivo(`${DIR}/historial.jsonl`), archivo(`${DIR}/COLA-ESTADO.md`), barraNodo.leerVivos(), archivo(USO, true), archivo(CUENTAS),
    cockpit.spawn(["tmux", "ls", "-F", "#{session_name}"], { err: "ignore" }).catch(() => ""),
    cockpit.spawn(["find", DIR, "-maxdepth", "1", "-name", "cola-*.toml", "-print"], { err: "ignore" }).catch(() => ""), leerPanel()]);
    const tomls = await Promise.all(paths.split("\n").filter(Boolean).map(x => archivo(x)));
    const rs = tomls.map(resumenes).filter(Boolean); await leerTitulos(rs);
    d = { h: historia(h), estado, vivos, uso: u, nombres: nombres(c), sesiones: tmux.split("\n").filter(x => /^cola[\w-]+$/.test(x)), colas: espera(tomls), etapas: tomls.flatMap(manifiesto), reglas: panelColas.reglas, fuera: panelColas.fuera, capacidad: panelColas.capacidad, cuentasPanel: panelColas.cuentas, colasPanel: panelColas.colas, despacho: panelColas.despacho, pasado: panelColas.pasado, resumenes: rs, paleta: panelColas.paleta }; barraNodo.leido(); pintar();
}
function ahoraDeducida(v, hayColas) { const e = d.colas ? d.colas.filter(x => x.a.length).map(x => `${x.n}: espera ${x.a.join(", ")}`).join(" · ") : "sin datos"; if (!v) { return hayColas ? [] : [el("section", { class: "tarjeta" }, el("h2", {}, "Ahora"), el("p", {}, "nada corriendo"), el("p", { class: "tenue" }, d.h && d.h.length ? `Última fase: ${d.h.at(-1).encargo} · ${d.h.at(-1).fase}` : "El historial aún no tiene datos; los encargos anteriores al 19 se ven sólo en la Bitácora."), el("p", {}, e || "sin datos"))]; }
    const h = (d.h || []).filter(x => String(x.encargo) === String(v.etapa) && x.fase === v.fase).at(-1), pr = v.pronostico || (h || {}).pronostico, cid = v.cuenta || cuentaFase(v.etapa, v.fase) || (h || {}).cuenta;
    return [el("section", { class: "tarjeta" }, el("h2", {}, `Cola viva: ${v.cola}`), lineaResumen(resumenCola(v.cola)), el("div", { class: "encargo-resumen" },
        el("div", {}, el("strong", {}, "Etapa y fase"), el("div", {}, v.etapa && v.fase ? `${v.etapa} · ${v.fase}` : "sin datos"), v.deducido ? el("span", { class: "insignia" }, "deducido") : null),
        el("div", {}, el("strong", {}, "Corridos / pronóstico"), el("div", {}, v.inicio ? `${min(v.inicio)} min / ${pr && pr.min != null ? pr.min + " min" : "sin datos"}` : `sin datos / ${pr && pr.min != null ? pr.min + " min" : "sin datos"}`)),
        el("div", {}, el("strong", {}, "Cuenta"), el("div", {}, cuenta(cid)), el("div", { class: "tenue" }, uso(cid))), el("div", {}, el("strong", {}, "Colas en espera"), el("div", {}, e || "sin datos"))))];
}

// Encargo 22, parte B: una tarjeta por cola con vivo/<cola>.json. El modelo (barraNodo.modeloCola)
// interpola el avance con el reloj; acá sólo se dibuja. El ancho y las marcas van por CSSOM.
function fraccion(nodo, nombre, valor) { nodo.style.setProperty(nombre, `${Math.round(valor * 1000) / 10}%`); return nodo; }
const minTxt = x => (x == null ? "sin datos" : `${(Math.round(x * 10) / 10).toLocaleString("es-CL")} min`);
function barraCola(m) {
    const caja = el("div", { class: `cola-barra ${m.tipo === "llena" ? (m.estado === "terminada" ? "ok" : "mal") : ""}` });
    fraccion(caja, "--fill", m.tipo === "llena" ? 1 : m.fill);
    if (m.marcas) {
        caja.append(fraccion(el("i", { class: "marca", title: "ETA mínimo" }), "--pos", m.marcas.min),
                    fraccion(el("i", { class: "marca esperada", title: "ETA esperado" }), "--pos", m.marcas.esperado));
    }
    return caja;
}
function segmentos(m) {
    const tope = Math.max(1, ...m.segmentos.flatMap(x => [x.min || 0, x.pronostico || 0]));
    return el("div", { class: "encargo-fases" }, m.segmentos.map(x => {
        const real = el("i", { class: x.veredicto === "mal" ? "cola-seg mal" : "cola-seg" }), pron = el("i", { class: "cola-seg pronostico" });
        fraccion(real, "--ancho", (x.min || 0) / tope); fraccion(pron, "--ancho", (x.pronostico || 0) / tope);
        const v = x.veredicto === "ok" ? " ✅" : x.veredicto === "mal" ? " ❌" : "";
        return el("div", { class: "encargo-fase" }, el("span", {}, `${x.fase} · ${x.cuenta || "sin datos"}`),
            el("div", { class: "encargo-barra cola-seg-caja" }, pron, real),
            el("span", { class: "tenue" }, `${minTxt(x.min)} / pronóstico ${minTxt(x.pronostico)}${x.enCurso ? " (en curso)" : ""}${v}`));
    }));
}
function tarjetaCola(m) {
    // Encargo 46c: `pausada_por_usuario` es un estado final que barra.js todavía no conoce (lo daría por «sin señal» a las 2 h).
    const porUsuario = m.estado === "pausada_por_usuario";
    // Encargo 50a: lo mismo con `retenida_por_despacho`, la cola que no partió porque el despacho estaba en pausa.
    const retenida = m.estado === "retenida_por_despacho", suVivo = d.vivos.find(v => v.nombre === m.cola) || {};
    const titulo = porUsuario ? "pausada por el usuario" : retenida ? "retenida por el despacho" : { barra: m.fase ? `${m.fase}` : m.estado, llena: m.estado, sin_barra: m.estado, sin_senal: "sin señal", espera_cuota: "Esperando cuota" }[m.tipo];
    const cuerpo = [];
    if (porUsuario) {
        cuerpo.push(el("p", {}, `La pausaste desde esta página. Se reanuda desde ${fasePanel((d.vivos.find(v => v.nombre === m.cola) || {}).reanuda_desde)} con el botón Reanudar.`));
    } else if (retenida) {
        cuerpo.push(el("p", {}, `No partió: ${delPanel(suVivo.motivo_pausa)}. No corrió ninguna fase. Se reanuda desde ${fasePanel(suVivo.reanuda_desde)} con el botón Reanudar.`));
    } else if (m.tipo === "barra") {
        cuerpo.push(barraCola(m), el("p", {}, `~${m.pct} % · termina ~${m.termina.esperado} (entre ${m.termina.min} y ${m.termina.max})`));
    } else if (m.tipo === "llena") {
        cuerpo.push(barraCola(m), el("p", {}, `${m.estado === "terminada" ? "Terminó" : "Se detuvo"}${m.fin ? ` a las ${m.fin}` : ""}.`));
    } else if (m.tipo === "espera_cuota") {
        const e = m.espera;
        cuerpo.push(el("p", {}, `${e.cuenta || "sin datos"}: ${e.calculo || "sin datos"}`),
            el("p", {}, e.reanuda ? `Sigue ${e.reanuda.length > 5 ? "el" : "a las"} ${e.reanuda}.` : "Sigue cuando se renueve la cuota."),
            el("p", { class: "tenue" }, e.termina ? `Termina ~${e.termina}, con la espera incluida.` : "sin datos"),
            e.debil ? el("p", { class: "tenue" }, "Pronóstico débil: la cuenta tiene pocas mediciones de este modelo.") : null);
    } else {
        cuerpo.push(el("p", {}, m.detalle || m.estado), m.fin ? el("p", { class: "tenue" }, `Desde las ${m.fin}.`) : null);
    }
    return el("section", { class: "tarjeta cola-tarjeta" }, el("h2", {}, `${m.cola} · ${titulo}`), lineaResumen(resumenCola(m.cola)),
        el("p", { class: "tenue" }, [m.etapa ? `etapa ${m.etapa}` : null, m.tipo === "espera_cuota" ? m.fase : null, m.cuenta, m.modelo].filter(Boolean).join(" · ") || "sin datos"),
        ...cuerpo, botonesCola(m.cola, ["pausar", "detener"]), m.segmentos.length ? segmentos(m) : null);
}
// Encargo 46b: «Carga vs. capacidad». Filas por cuenta y columnas por cola; cada celda es la carga comprometida que el
// panel ya trae calculada (`reglas[*].celdas`). Acá sólo se calcula la Holgura (tope − uso − carga comprometida) y, si se
// marca «¿y si la reanudo?» en una cola de `colas_fuera`, su carga proyectada: la misma suma de la 46a (prob × pct, separado
// por ventana con la renovación de la cuenta). La casilla no escribe nada: `marcadas` vive en la memoria de la pestaña.
// Todo texto que viene del panel (cola, estado, motivo, fase, fuente, nombre) es un dato: se muestra como texto y pasa por
// delPanel(), o sea por la lista blanca (seguro()) y por la regla de nombres (un nombre de persona sólo dentro de la
// etiqueta de su cuenta).
const marcadas = new Set();
const VENTANAS = [["5h", "5 h", "pct_5h"], ["semanal", "sem", "pct_sem"]];
const CLAVES_CELDA = ["pct_5h", "pct_5h_min", "pct_5h_max", "pct_sem", "pct_sem_min", "pct_sem_max", "proxima_5h"];
const ESTADOS_FUERA = new Map([["pausada_sin_timer", "pausada, sin reanudación programada"], ["detenida", "detenida"], ["en_candado", "espera autorización"],
    ["caida", "caída"], ["sin_autorizacion", "sin autorización"], ["ilegible", "no se pudo leer"], ["pausada_por_usuario", "pausada por el usuario"], ["retenida_por_despacho", "retenida por el despacho"]]);
const AYUDA_CARGA = [
    ["Capacidad", "lo que permite la cuenta en cada ventana (5 h y semana), hasta su tope."],
    ["Uso", "lo que ya se midió de la cuenta; si la medición está vieja, dice «medido hace N h»."],
    ["Carga comprometida", "lo que van a gastar las colas que corren solas: el valor esperado y, debajo, su rango."],
    ["Carga proyectada", "lo que sumaría reanudar una cola detenida o pausada; se ve al marcar «¿y si la reanudo?» y no se guarda."],
    ["Holgura", "tope menos uso menos carga comprometida. Verde si sobra, ámbar si quedan 10 puntos o menos y rojo si es negativa."],
    ["Renovación", "↻ «desde las HH:MM» es lo que cae en la próxima ventana de 5 h; no cuenta en la de ahora."]];
function conEtiqueta(t) { return String(t).split(/(Claude \((?:(?:Diego)|(?:Cami))\))/).map((p, i) => (i % 2 ? p : p.replace(/(^|[^A-Za-z0-9_À-ÿ])(?:(?:Diego)|(?:Camila)|(?:Cami))(?![A-Za-z0-9_À-ÿ])/g, `$1${OCULTO}`))).join(""); }
const delPanel = x => (x == null || x === "" ? "sin datos" : conEtiqueta(unaLinea(x)));
// `fase` viene como «etapa:fase» («41:rev3»), y la lista blanca oculta una palabra con «:» en medio: cada parte pasa sola.
const fasePanel = x => (x == null || x === "" ? "sin datos" : String(x).split(":").map(delPanel).join(":"));
const propio = (o, k) => (o && typeof o === "object" && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined);
const n1 = x => String(Math.round(x * 10) / 10).replace(".", ",").replace("-", "−");
const horaCorta = iso => { const t = new Date(iso); return typeof iso !== "string" || Number.isNaN(t.getTime()) ? null : t.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false }); };
const renovacion = (pct, iso) => { const h = horaCorta(iso); return `↻ ${n1(pct)} % ${h ? `desde las ${h}` : "en la próxima ventana"}`; };
// El color de una cola es su lugar entre las activas del panel: el mismo orden y los mismos cuatro tonos que usa 💳 Cuentas.
const colorCola = i => `cola-c${i % 4 + 1}`;
const nivelHolgura = h => (h < 0 ? "mal" : h <= 10 ? "ojo" : "ok");
// La suma de la 46a para una cola de `colas_fuera`: {cuenta: celda}. Una fase en PC-2503 (`donde`) no gasta cuota. Sin hora
// de renovación todo cuenta en la ventana de ahora y la celda sale débil; una fase sin la forma esperada se salta y también.
function proyectar(cola, cuentas) {
    const porCuenta = Object.create(null); let debil = !!cola.debil;       // sin prototipo: la clave es un dato del panel
    for (const f of Array.isArray(cola.fases_restantes) ? cola.fases_restantes : []) {
        const cu = f && propio(cuentas, f.cuenta), ini = f ? Date.parse(f.inicio_esperado) : NaN;
        if (!cu || Number.isNaN(ini) || ![f.prob, f.pct_5h, f.pct_sem].every(Number.isFinite)) { debil = true; continue; }
        if (f.donde) continue;
        const c = porCuenta[f.cuenta] ||= { ...Object.fromEntries(CLAVES_CELDA.map(k => [k, 0])), debil: false };
        for (const k of ["pct_5h", "pct_sem"]) {
            const ren = Date.parse(k === "pct_5h" ? cu.renueva_5h : cu.renueva_sem);
            if (Number.isNaN(ren)) c.debil = true;
            if (Number.isNaN(ren) || ini < ren) { c[k] += f.prob * f[k]; c[`${k}_max`] += f[k]; if (f.prob >= 1) c[`${k}_min`] += f[k]; }
            else if (k === "pct_5h") c.proxima_5h += f.prob * f[k];
        }
        if (f.debil) c.debil = true;
    }
    if (debil) for (const c of Object.values(porCuenta)) c.debil = true;
    return porCuenta;
}
// Holgura por ventana, con un decimal como publica el panel. `extra` es la carga proyectada de la cuenta (o null).
function holguras(regla, extra) {
    return VENTANAS.map(([id, etiqueta, k]) => {
        const w = (regla && Array.isArray(regla.ventanas) ? regla.ventanas : []).find(x => x && x.ventana === id);
        if (!w || ![w.tope, w.actual, w.pronostico].every(Number.isFinite)) return { etiqueta, sinDatos: true };
        const real = Math.round((w.tope - w.actual - w.pronostico) * 10) / 10;
        return { etiqueta, tope: w.tope, uso: w.actual, real, nivel: nivelHolgura(real), proyectada: extra ? Math.round((w.tope - w.actual - w.pronostico - extra[k]) * 10) / 10 : null };
    });
}
function celdaCarga(c, proyectada, renueva) {
    if (!c || typeof c !== "object") return el("td", { class: `vacia${proyectada ? " proyectada" : ""}` }, "—");
    const v = k => (Number.isFinite(c[k]) ? n1(c[k]) : "sin datos");
    return el("td", { class: `num${proyectada ? " proyectada" : ""}`, title: `${proyectada ? "Carga proyectada" : "Carga comprometida"}: valor esperado y rango` },
        c.pct_5h > 0 ? [el("span", { class: "linea grande" }, `+${v("pct_5h")} % 5 h`), el("span", { class: "linea tenue" }, `${v("pct_5h_min")}–${v("pct_5h_max")}`)] : null,
        el("span", { class: "linea" }, `+${v("pct_sem")} % sem `, el("span", { class: "tenue" }, `(${v("pct_sem_min")}–${v("pct_sem_max")})`)),
        c.proxima_5h > 0 ? el("span", { class: "chip" }, renovacion(c.proxima_5h, renueva)) : null,
        c.debil ? el("span", { class: "chip ojo" }, "débil") : null);
}
// La Holgura real va con su color; la que incluye carga proyectada va aparte, con borde punteado y sin color.
function celdaHolgura(r, extra, renueva) {
    const hs = holguras(r, extra), prox = r && Number.isFinite(r.proxima_5h) ? r.proxima_5h : 0;
    return el("td", { class: "holgura num" },
        hs.map(h => el("span", { class: "linea" }, `${h.etiqueta}: `, h.sinDatos ? falta() : [el("b", { class: `valor ${h.nivel}` }, `${n1(h.real)} %`), el("span", { class: "tenue" }, ` · tope ${n1(h.tope)} %`)])),
        prox > 0 ? el("span", { class: "linea tenue" }, renovacion(prox, renueva)) : null,
        extra ? el("span", { class: "linea proyectada" }, "con carga proyectada: ",
            [...hs.map(h => `${h.etiqueta} ${h.sinDatos ? "sin datos" : `${n1(h.proyectada)} %`}`), extra.proxima_5h > 0 ? renovacion(extra.proxima_5h, renueva) : null].filter(Boolean).join(" · ")) : null);
}
function matrizCarga(reglas, fuera) {
    const cuentas = d.cuentasPanel && typeof d.cuentasPanel === "object" ? d.cuentasPanel : {};
    reglas = reglas.filter(r => r && typeof r === "object" && typeof r.cuenta === "string");
    const activas = [...new Set(reglas.flatMap(r => Object.keys(r.celdas || {})))];
    const proy = fuera.filter(x => marcadas.has(String(x.cola))).map(x => ({ cola: String(x.cola), porCuenta: proyectar(x, cuentas) })).filter(p => Object.keys(p.porCuenta).length);
    if (!activas.length && !proy.length) return el("p", { class: "tenue" }, "Ninguna cola activa tiene carga comprometida.");
    const columnas = [...activas.map(cola => ({ cola })), ...proy];
    const ids = [...new Set([...Object.keys(cuentas), ...reglas.map(r => r.cuenta)])].filter(cid => reglas.some(r => r.cuenta === cid) || proy.some(p => propio(p.porCuenta, cid)));
    const cabeza = el("tr", {}, el("th", { class: "fila", scope: "col" }, "Cuenta"),
        columnas.map((c, i) => el("th", { class: `col-cola ${colorCola(i)}${c.porCuenta ? " proyectada" : ""}`, scope: "col" }, delPanel(c.cola), el("span", { class: "carga-nota" }, c.porCuenta ? "carga proyectada" : "carga comprometida"))),
        el("th", { class: "holgura", scope: "col" }, "Holgura", el("span", { class: "carga-nota" }, "tope − uso − carga comprometida")));
    const filas = ids.map(cid => {
        const r = reglas.find(x => x.cuenta === cid), renueva = (r || propio(cuentas, cid) || {}).renueva_5h;
        const suyas = proy.map(p => propio(p.porCuenta, cid)).filter(Boolean);
        const extra = suyas.length ? Object.fromEntries(CLAVES_CELDA.map(k => [k, suyas.reduce((s, c) => s + c[k], 0)])) : null;
        const uso = holguras(r, null).filter(h => !h.sinDatos).map(h => `${n1(h.uso)} % ${h.etiqueta}`).join(" · ");
        const vieja = r && typeof r.fuente === "string" && r.fuente.startsWith("medido hace ");
        const celdasDebiles = r && Object.values(r.celdas || {}).some(c => c && c.debil);
        return el("tr", {}, el("th", { class: "fila", scope: "row" }, delPanel(r ? r.nombre : (propio(cuentas, cid) || {}).nombre),
                el("span", { class: "carga-nota" }, `Uso: ${uso || "sin datos"}`),
                vieja ? el("span", { class: "chip ojo" }, delPanel(r.fuente)) : r && r.debil && !celdasDebiles ? el("span", { class: "chip ojo" }, "débil") : null),
            columnas.map(c => celdaCarga(c.porCuenta ? propio(c.porCuenta, cid) : propio(r && r.celdas, c.cola), !!c.porCuenta, renueva)),
            celdaHolgura(r, extra, renueva));
    });
    return [el("div", { class: "carga-envoltura" }, el("table", { class: "carga-matriz" }, el("thead", {}, cabeza), el("tbody", {}, filas))),
        proy.length ? el("p", { class: "tenue carga-leyenda" }, el("span", { class: "carga-muestra proyectada" }), `incluye carga proyectada: ${proy.map(p => delPanel(p.cola)).join(", ")}. Es un cálculo de esta pestaña; no se guarda.`) : null];
}
function bloqueFuera(fuera) {
    const cuentas = d.cuentasPanel && typeof d.cuentasPanel === "object" ? d.cuentasPanel : {};
    return el("div", { class: "carga-fuera" }, el("h3", {}, "Detenidas o pausadas"),
        el("p", { class: "tenue" }, "No suman a la carga comprometida. La casilla muestra, como carga proyectada, lo que sumarían si se reanudaran ahora: no reanuda ni guarda nada. Reanudar sí lanza la cola, después de confirmar."),
        el("ul", {}, fuera.map(x => {
            const id = String(x.cola), n = Object.keys(proyectar(x, cuentas)).length;
            const casilla = el("input", { type: "checkbox", checked: n > 0 && marcadas.has(id), disabled: !n, onchange: ev => { if (ev.target.checked) marcadas.add(id); else marcadas.delete(id); ahora(); } });
            return el("li", {}, el("strong", {}, delPanel(x.cola)), " ", el("span", { class: "chip dato" }, ESTADOS_FUERA.get(x.estado) || delPanel(String(x.estado ?? "").replace(/_/g, " "))),
                x.debil ? el("span", { class: "chip ojo" }, "débil") : null,
                el("span", { class: "carga-nota" }, `fase ${fasePanel(x.fase)} · ${x.motivo ? delPanel(x.motivo) : "sin motivo"}`),
                el("label", { class: "carga-casilla" }, casilla, n ? " ¿y si la reanudo?" : " ¿y si la reanudo? (no hay fases que proyectar)"),
                botonesCola(id, ["reanudar"]));
        })));
}
function capacidadPorVencer() {
    const filas = Object.values(d.capacidad || {}).filter(x => x && Number.isFinite(x.capacidad));
    return filas.map(x => el("p", { class: x.debil ? "tenue" : "" }, `Capacidad por vencer: ${n1(x.capacidad)} % de `,
        delPanel(x.nombre), ` antes de las ${horaCorta(x.renueva) || "sin datos"}`,
        Array.isArray(x.colas_que_caben) && x.colas_que_caben.length ? ` · caben: ${x.colas_que_caben.map(delPanel).join(", ")}` : ""));
}
function tarjetaCarga(ms) {
    const reglas = d.reglas, fuera = (d.fuera || []).filter(x => x && typeof x === "object");
    const vence = capacidadPorVencer();
    if (!ms.length && !fuera.length && !(reglas || []).length && !vence.length) return [];
    return [el("section", { class: "tarjeta" }, el("h2", {}, "Carga vs. capacidad"),
        el("p", { class: "tenue" }, "Por cuenta y por ventana: el uso ya medido más la carga comprometida de las colas que corren solas, contra el tope. La holgura es lo que queda."),
        ...vence,
        el("details", { class: "carga-ayuda" }, el("summary", {}, "Qué significa cada término"), el("dl", {}, AYUDA_CARGA.flatMap(([t, x]) => [el("dt", {}, t), el("dd", {}, x)]))),
        reglas == null ? falta() : matrizCarga(reglas, fuera),
        fuera.length ? bloqueFuera(fuera) : null)];
}
function ahora() {
    const p = $("[data-panel=ahora]"), ms = barraNodo.modelosColas(d.vivos, d.sesiones, Date.now(), d.h);
    p.replaceChildren(...avisoAccion(), tarjetaDespacho(), ...ms.map(tarjetaCola), ...tarjetaCarga(ms), ...ahoraDeducida(vivo(), ms.length > 0));
}
// Encargo 50a: el estado del despacho y la mirada de pasado de «Capacidad». Los dos salen de `cola-run.py --panel`:
// `despacho` es vivo/despacho.json ya leído ({estado, desde, motivo, autorizadas, por} y `aviso` si el archivo no se pudo leer)
// y `pasado`, lo que calcula encargos/balance.py (lo mismo que `balance.py --json`). La página no calcula nada de eso: dibuja.
// El despacho se cambia sólo con `cola-run.py --despacho {pausar|abrir}`, con argv fijo y sin shell; el motivo que escribe el
// usuario viaja entero en un solo argumento. Con el despacho en pausa una cola que arranca queda `retenida_por_despacho`;
// Reanudar (46c) pide ahí una confirmación más, que la autoriza. Todo texto del panel pasa por delPanel().
const POR_PAGINA = "el usuario, desde 🧵 Encargos";
const ORDENES_DESPACHO = new Map([["pausar", "Pausar despacho"], ["abrir", "Abrir despacho"]]);
const argvDespacho = (orden, motivo) => ["python3", COLA_RUN, "--despacho", orden, "--por", POR_PAGINA, ...(motivo ? ["--motivo", motivo] : [])];
// «las 16:55» si fue hoy y «el 11-10 a las 16:55» si no.
function desdeDespacho(iso) {
    const h = horaCorta(iso); if (!h) return "una hora sin datos";
    const t = new Date(iso), dos = n => String(n).padStart(2, "0");
    return t.toDateString() === new Date().toDateString() ? `las ${h}` : `el ${dos(t.getDate())}-${dos(t.getMonth() + 1)} a las ${h}`;
}
const motivoDespacho = x => (x && typeof x.motivo === "string" && x.motivo.trim() ? delPanel(x.motivo) : "sin motivo");
function textoDespacho(x) { return x.estado === "pausa" ? `Despacho en pausa desde ${desdeDespacho(x.desde)} — ${motivoDespacho(x)}` : "Despacho abierto"; }
function textoOrdenDespacho(orden) {
    if (orden === "pausar") return "¿Pausar el despacho?\n\nDesde ahora, una cola que arranque queda retenida sin correr ninguna fase ni gastar cuota: también la que lance un timer o la cadena de reanudación. Las que ya están corriendo siguen. Durante la pausa, Reanudar pide autorizar esa cola.\n\nMotivo (puede quedar vacío):";
    return "¿Abrir el despacho?\n\nLas colas vuelven a arrancar sin pedir autorización y se borran las autorizadas de esta pausa. Una cola que quedó retenida no parte sola: se reanuda con el botón Reanudar.";
}
// La confirmación extra de Reanudar durante una pausa: sólo si la cola todavía no está autorizada.
const faltaAutorizar = sim => !!sim && esObjeto(sim.despacho) && sim.despacho.estado === "pausa" && sim.despacho.autorizada !== true;
function textoAutorizar(cola, x) { return `El despacho está en pausa desde ${desdeDespacho(x.desde)} — ${motivoDespacho(x)}.\n\n¿Autorizar ${cola} a correr igual? Queda entre las autorizadas mientras dure esta pausa y parte ahora. Las demás colas siguen retenidas.`; }
async function correrDespacho(orden, motivo) {
    if (!ORDENES_DESPACHO.has(orden) || (motivo != null && typeof motivo !== "string")) throw new Error("orden de despacho inválida");
    return respuestaCola(cockpit.spawn(argvDespacho(orden, motivo), { err: "message" }));
}
// Sin confirmación no se ejecuta nada. Pausar pregunta con prompt(): Aceptar confirma y lo escrito es el motivo; Cancelar no hace nada.
async function ordenarDespacho(orden) {
    if (accionEnCurso) return;
    accionEnCurso = true; resultadoAccion = null; pintar();
    try {
        let motivo = null;
        if (orden === "pausar") { const escrito = prompt(textoOrdenDespacho(orden), ""); if (escrito === null) return; motivo = escrito.replace(/\s+/g, " ").trim().slice(0, 200); }
        else if (!confirm(textoOrdenDespacho(orden))) return;
        const r = await correrDespacho(orden, motivo);
        resultadoAccion = { cola: "Despacho", mal: false, texto: delPanel(r.mensaje) };
    } catch (e) { resultadoAccion = { cola: "Despacho", mal: true, texto: delPanel(e.message || String(e)) }; }
    finally { accionEnCurso = false; await leer().catch(() => pintar()); }
}
// Arriba de «Ahora». Sin el panel no se sabe el estado: no se ofrece ningún botón.
function tarjetaDespacho() {
    const x = d.despacho;
    if (!x || !["abierto", "pausa"].includes(x.estado)) return el("div", { class: "aviso neutro despacho" }, el("strong", {}, "Despacho: "), "sin datos");
    const pausa = x.estado === "pausa", orden = pausa ? "abrir" : "pausar";
    const autorizadas = (Array.isArray(x.autorizadas) ? x.autorizadas : []).filter(c => typeof c === "string" && COLA_VALIDA.test(c));
    const notas = [x.desde && !pausa ? `desde ${desdeDespacho(x.desde)}` : null, x.por ? `lo dejó así ${delPanel(x.por)}` : null,
        pausa ? (autorizadas.length ? `autorizadas: ${autorizadas.join(", ")}` : "ninguna cola autorizada") : null].filter(Boolean).join(" · ");
    return el("div", { class: `aviso ${pausa ? "ojo" : "ok"} despacho` },
        el("div", {}, el("strong", {}, textoDespacho(x)), notas ? el("span", { class: "carga-nota" }, notas) : null,
            x.aviso ? el("span", { class: "chip ojo" }, delPanel(x.aviso)) : null),
        el("button", { class: "mini", disabled: accionEnCurso, onclick: () => ordenarDespacho(orden) }, ORDENES_DESPACHO.get(orden)));
}
// «Precisión del pronóstico»: la mirada de pasado. Cada número viene calculado en `pasado`; acá sólo se le da formato.
const EXPERIMENTO = "esfuerzo-v1";
const numPasado = (x, dec) => (Number.isFinite(x) ? x.toLocaleString("es-CL", { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 }) : null);
const pctPasado = x => (Number.isFinite(x) ? `${numPasado(x)} %` : "sin datos");
const usdPasado = x => (Number.isFinite(x) ? `US$ ${numPasado(x, 2)}` : "—");
const kPasado = x => (Number.isFinite(x) ? `${numPasado(x)} k` : "—");
const nombrePasado = x => propio(BONITO, x) || delPanel(x);
const primeraPasado = f => (Number.isFinite(f.aprobados) && Number.isFinite(f.revisados) ? `${numPasado(f.aprobados)} de ${numPasado(f.revisados)}` : "sin datos");
const filasPasado = xs => (Array.isArray(xs) ? xs.filter(esObjeto) : []);
function tablaPasado(cabezas, filas) { return el("div", { class: "config-ancho" }, el("table", { class: "pasado-tabla" }, el("thead", {}, el("tr", {}, cabezas.map(x => el("th", {}, x)))), el("tbody", {}, filas))); }
function filaFamilia(f) { return el("tr", {}, el("td", {}, nombrePasado(f.nombre)), el("td", {}, numPasado(f.encargos) ?? "sin datos"), el("td", {}, primeraPasado(f)), el("td", {}, pctPasado(f.ret_min_pct)), el("td", {}, usdPasado(f.usd_por_encargo)), el("td", {}, kPasado(f.tok_k_por_encargo)), el("td", {}, pctPasado(f.error_pct))); }
function filaCombo(c) { return el("tr", {}, el("td", {}, nombrePasado(c.motor)), el("td", {}, delPanel(c.modelo)), el("td", {}, delPanel(c.esfuerzo)), el("td", {}, delPanel(c.rol)), el("td", {}, numPasado(c.fases) ?? "sin datos"), el("td", {}, numPasado(c.min_por_fase, 1) ?? "sin datos"), el("td", {}, usdPasado(c.usd_por_fase)), el("td", {}, kPasado(c.tok_k_por_fase))); }
function lineaExperimento(f) { return `${delPanel(f.nombre)}: ${numPasado(f.encargos) ?? "sin datos"} casos · aprobados en la 1ª revisión ${primeraPasado(f)} · retrabajo ${pctPasado(f.ret_min_pct)} de los minutos · error del pronóstico ${pctPasado(f.error_pct)}`; }
function tarjetaPasado() {
    const x = d.pasado, t = x && esObjeto(x.total) ? x.total : null;
    const cabeza = [el("h2", {}, "Precisión del pronóstico"), el("p", { class: "tenue" }, "La mirada de pasado de «Capacidad»: qué costó cada encargo y cuánto se equivocó el plan. Lo calcula balance.py sobre el historial; acá sólo se muestra.")];
    if (!x) return el("section", { class: "tarjeta" }, cabeza, falta());
    if (!t) return el("section", { class: "tarjeta" }, cabeza, el("p", {}, "El historial todavía no tiene fases que contar."));
    const experimentos = filasPasado(x.experimento).filter(f => !["ninguno", "sin dato"].includes(f.nombre));
    const notas = [x.saltadas > 0 ? `${numPasado(x.saltadas)} líneas del historial se saltaron por rotas o incompletas` : null,
        Array.isArray(x.sin_manifiesto) && x.sin_manifiesto.length ? `${numPasado(x.sin_manifiesto.length)} encargos sin manifiesto (su naturaleza sale del historial o queda sin dato)` : null,
        Array.isArray(x.ilegibles) && x.ilegibles.length ? `${numPasado(x.ilegibles.length)} manifiestos no se pudieron leer` : null].filter(Boolean);
    return el("section", { class: "tarjeta" }, cabeza,
        el("p", { class: "tenue" }, `Encargos ${delPanel(x.primero)} a ${delPanel(x.ultimo)}: ${numPasado(t.encargos) ?? "sin datos"} encargos y ${numPasado(t.fases) ?? "sin datos"} fases.`),
        el("div", { class: "encargo-resumen" },
            el("div", {}, el("strong", {}, "Aprobación en la 1ª revisión"), el("div", {}, primeraPasado(t)), el("div", { class: "tenue" }, "encargos aprobados sin arreglos, de los que tuvieron revisión")),
            el("div", {}, el("strong", { "data-term": "Rework rate" }, "Retrabajo"), el("div", {}, `${pctPasado(t.ret_min_pct)} de los minutos`),
                el("div", { class: "tenue" }, `${numPasado(t.min_ret) ?? "sin datos"} de ${numPasado(t.min) ?? "sin datos"} min en arreglos y revisiones desde la 2ª · Claude: ${pctPasado(t.ret_usd_pct)} de sus USD · Codex: ${pctPasado(t.ret_tok_pct)} de sus tokens`)),
            el("div", {}, el("strong", { "data-term": "Estimation error" }, "Error del pronóstico"), el("div", {}, pctPasado(t.error_pct)), el("div", { class: "tenue" }, "mediana, por fase, de la diferencia entre los minutos reales y los pronosticados"))),
        el("h3", { "data-term": "Cost per task" }, "Costo por naturaleza"),
        tablaPasado(["Naturaleza", "Encargos", "Aprobación en la 1ª revisión", "Retrabajo (min)", "Claude, por encargo", "Codex, tokens por encargo", "Error del pronóstico"], filasPasado(x.naturaleza).map(filaFamilia)),
        el("h3", {}, "Costo por modelo y esfuerzo"),
        el("p", { class: "tenue" }, "Por fase, de más a menos minutos en total. Claude se mide en USD y Codex en tokens: no se suman."),
        tablaPasado(["Motor", "Modelo", "Esfuerzo", "Rol", "Fases", "Min por fase", "USD por fase", "Tokens por fase"], filasPasado(x.combos).map(filaCombo)),
        el("h3", {}, `Experimento ${EXPERIMENTO}`),
        experimentos.some(f => f.nombre === EXPERIMENTO) ? null : el("p", {}, `${EXPERIMENTO}: 0 casos. Ningún encargo del historial lleva ese experimento en su manifiesto.`),
        experimentos.map(f => el("p", {}, lineaExperimento(f))),
        notas.length ? el("p", { class: "tenue" }, `${notas.join(" · ")}.`) : null);
}
// Encargo 46c: Reanudar, Pausar y Detener. Todo pasa por `cola-run.py --accion <acción> <cola>`, con argv fijo y sin shell:
// la página no decide nada. Qué botón se ofrece en cada cola lo dice `colas` del panel (la misma regla con que la acción
// vuelve a decidir al momento de actuar) y, después de actuar, la página relee todo. El nombre de la cola es un dato: no
// llega a spawn si no calza con COLA_VALIDA. Reanudar muestra antes la carga proyectada de `--simular`; Detener pide
// escribir el nombre de la cola. Los timers se ven en modo sólo lectura: accionarlos es de ⏰ Programados.
const COLA_VALIDA = /^cola[0-9]{2}[a-z0-9]*$/;
const ACCIONES_COLA = new Map([["reanudar", "Reanudar"], ["pausar", "Pausar"], ["detener", "Detener"]]);
let accionEnCurso = false, resultadoAccion = null;
const argvAccion = (accion, cola, simular, autorizar) => ["python3", COLA_RUN, "--accion", accion, cola, ...(simular ? ["--simular"] : []), ...(autorizar ? ["--autorizar", cola] : [])];
const nombreConfirmado = (escrito, cola) => typeof escrito === "string" && escrito === cola;
// cola-run.py contesta siempre un JSON de una línea; si la acción no se hizo, sale con código 1 y lo repite por stderr.
// `autorizar` (50a) sólo vale para la reanudación de verdad: es la confirmación extra del despacho en pausa.
async function correrAccion(accion, cola, simular, autorizar) {
    if (!ACCIONES_COLA.has(accion) || typeof cola !== "string" || !COLA_VALIDA.test(cola)) throw new Error("nombre de cola inválido");
    return respuestaCola(cockpit.spawn(argvAccion(accion, cola, simular, autorizar === true && accion === "reanudar" && !simular), { err: "message" }));
}
async function respuestaCola(lanzado) {
    let salida;
    try { salida = await lanzado; }
    catch (e) { let r = null; try { r = JSON.parse(e.message); } catch (x) { /* la salida no era JSON */ } throw new Error(r && typeof r.error === "string" ? r.error : e.message || String(e)); }
    const r = JSON.parse(salida);
    if (!r || r.ok !== true) throw new Error(r && typeof r.error === "string" ? r.error : "la acción no se hizo");
    return r;
}
function textoConfirmacion(accion, cola, sim) {
    if (accion === "reanudar") return [`¿Reanudar ${cola} desde ${fasePanel(sim.desde)}?`, "", "Carga proyectada:", ...(Array.isArray(sim.texto) ? sim.texto : []).map(delPanel), "",
        "Lanza la cola ahora y gasta cuota. Si usa un modelo con candado, la cola pide su ✅ por Telegram."].join("\n");
    if (accion === "pausar") return `¿Pausar ${cola}?\n\nTermina la fase en curso y no empieza la siguiente. Queda pausada por el usuario y sigue cuando la reanudes.`;
    return `Detener ${cola} corta su sesión de inmediato: lo que lleva la fase en curso se pierde y esa fase se repite al reanudar.\n\nPara confirmar, escribe el nombre de la cola:`;
}
// Sin confirmación no se ejecuta nada. Con ella, la acción corre una vez y, salga como salga, se relee el estado.
async function accionar(accion, cola) {
    if (accionEnCurso) return;
    accionEnCurso = true; resultadoAccion = null; pintar();
    try {
        let autorizar = false;
        if (accion === "reanudar") { const sim = await correrAccion("reanudar", cola, true); if (!confirm(textoConfirmacion(accion, cola, sim))) return; autorizar = faltaAutorizar(sim); if (autorizar && !confirm(textoAutorizar(cola, sim.despacho))) return; }
        else if (accion === "pausar") { if (!confirm(textoConfirmacion(accion, cola))) return; }
        else { const escrito = prompt(textoConfirmacion(accion, cola), ""); if (escrito === null) return; if (!nombreConfirmado(escrito, cola)) { resultadoAccion = { cola, mal: true, texto: "No se detuvo nada: lo escrito no es el nombre de la cola." }; return; } }
        const r = await correrAccion(accion, cola, false, autorizar);
        resultadoAccion = { cola, mal: false, texto: delPanel(r.mensaje) };
    } catch (e) { resultadoAccion = { cola, mal: true, texto: delPanel(e.message || String(e)) }; }
    finally { accionEnCurso = false; await leer().catch(() => pintar()); }
}
// La unidad de un timer («orden-renov-1122.timer») pasa la lista blanca parte por parte, como la fase.
const timerPanel = x => (typeof x === "string" && x ? x.split(/([.-])/).map((p, i) => (i % 2 ? p : delPanel(p))).join("") : "sin datos");
function timersCola(info, reanudable) {
    return (Array.isArray(info.timers) ? info.timers : []).filter(t => t && typeof t === "object").map(t => el("p", { class: "tenue cola-timer" },
        `⏰ ${timerPanel(t.unidad)}: `, t.vencido ? (reanudable ? "vencido: usa Reanudar" : "vencido") : `próxima ${cuando(t.proxima) || "sin datos"}`, " · ",
        el("button", { class: "mini", title: "Abre 🍇 Raspberry Pi; los timers se accionan en su pestaña ⏰ Programados", onclick: () => cockpit.jump("/sistema") }, "ver en ⏰ Programados")));
}
// `cuales` son los botones que caben en ese lugar de la página; se dibujan los que además valen ahora para la cola.
function botonesCola(cola, cuales) {
    const info = propio(d.colasPanel, cola) || {}, valido = typeof cola === "string" && COLA_VALIDA.test(cola);
    const ofrecidas = valido && Array.isArray(info.acciones) ? cuales.filter(a => info.acciones.includes(a)) : [];
    const partes = [ofrecidas.length ? el("div", { class: "cola-botones" }, ofrecidas.map(a => el("button", { class: a === "detener" ? "mini peligro" : "mini", disabled: accionEnCurso, onclick: () => accionar(a, cola) }, ACCIONES_COLA.get(a)))) : null,
        info.pausa_pedida ? el("span", { class: "chip ojo" }, "pausa pedida: se detiene al terminar la fase en curso") : null,
        cuales.includes("reanudar") && !ofrecidas.length && info.no_reanuda ? el("span", { class: "carga-nota" }, `No se reanuda desde acá: ${delPanel(info.no_reanuda)}`) : null,
        ...timersCola(info, ofrecidas.includes("reanudar"))].filter(Boolean);
    return partes.length ? el("div", { class: "cola-acciones" }, partes) : null;
}
// El resultado de la última acción, arriba de «Ahora», hasta la próxima: lo que contestó cola-run.py después de actuar.
function avisoAccion() { const r = resultadoAccion; return r ? [el("div", { class: `aviso ${r.mal ? "rojo" : "ok"} accion-resultado` }, el("strong", {}, `${delPanel(r.cola)}: `), r.texto)] : []; }
// Encargo 34: la barra de uso. Un tramo por fila del historial, en orden de inicio. Largo = uso medido (minutos o
// Δ % de la ventana de 5 h de su cuenta); color = modelo; intensidad = esfuerzo. El color de cada modelo sale del
// orden en que aparece en [niveles.*] de modelos.toml, leído en vivo con `cola-run.py --panel`: los tonos .uso-m1…m8 de encargos.css.
const TONOS = 8, ESFUERZOS = ["low", "medium", "high", "xhigh"];
const MEDIDAS = [["min", "minutos"], ["delta", "Δ % 5 h de su cuenta"]];
let medidaUso = "min";
// Los modelos de [niveles.*], sin repetir y en el orden del archivo (claude primero): el N-ésimo usa el tono N.
function modelosPaleta(modelos) { return [...new Set(Object.values((modelos || {}).niveles || {}).flatMap(t => Object.values(t || {}).map(x => x && x.modelo)).filter(Boolean))]; }
const modeloFila = x => x.modelo_real || x.modelo || null;
// Un modelo que no está en modelos.toml (o el noveno en adelante: no hay más tonos) va en gris, con su nombre.
function tono(modelo) { const i = modelo ? (d.paleta || []).indexOf(modelo) : -1; return i >= 0 && i < TONOS ? `uso-m${i + 1}` : "uso-gris"; }
const claseEsfuerzo = e => (ESFUERZOS.includes(e) ? `uso-e-${e}` : "uso-e-vacio");
function deltaUso(x) { const p = x.pct_5h; return Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) ? Math.round((p[1] - p[0]) * 10) / 10 : null; }
// null = sin medida: el tramo va con el ancho mínimo y rayado (Δ ≤ 0 o ausente, p. ej. porque la ventana se renovó).
function medidaTramo(x, medida) { const v = medida === "delta" ? deltaUso(x) : x.min; return Number.isFinite(v) && v > 0 ? v : null; }
// Los tokens van tal como vienen: la forma cambia según el motor y no se suman entre motores.
const tokensTxt = t => (t && typeof t === "object" && Object.keys(t).length ? Object.entries(t).map(([k, v]) => `${k} ${v}`).join(", ") : "sin datos");
function tituloTramo(x) {
    const dl = deltaUso(x);
    return [val(x.fase), cuenta(x.cuenta), modeloFila(x) || "modelo desconocido", x.esfuerzo ? `esfuerzo ${x.esfuerzo}` : x.esfuerzo === "" ? "sin esfuerzo" : "esfuerzo sin datos",
        Number.isFinite(x.min) ? `${x.min} min` : "minutos sin datos", `Δ 5 h ${dl != null && dl > 0 ? `+${dl} %` : "sin cambio medido"}`, `tokens: ${tokensTxt(x.tokens)}`].join(" · ");
}
const porInicio = fs => [...fs].sort((a, b) => (Date.parse(a.inicio) || 0) - (Date.parse(b.inicio) || 0));
function barraDeUso(fs, medida) {
    return el("div", { class: "uso-barra" }, porInicio(fs).map(x => {
        const v = medidaTramo(x, medida), t = tituloTramo(x);
        const i = el("i", { class: `uso-tramo ${tono(modeloFila(x))} ${claseEsfuerzo(x.esfuerzo)}${v == null ? " uso-sin-medida" : ""}`, title: t, role: "img", "aria-label": t });
        if (v != null) i.style.setProperty("--peso", String(v));
        return i;
    }));
}
function leyendaUso(fs, medida) {
    const muestra = (clase, texto) => el("span", { class: "uso-clave" }, el("i", { class: `uso-muestra ${clase}` }), texto);
    const nombre = m => (!m ? "modelo desconocido" : tono(m) === "uso-gris" ? `${m} (no está en modelos.toml)` : m);
    return el("div", { class: "uso-leyenda tenue" }, [...new Set(porInicio(fs).map(modeloFila))].map(m => muestra(`${tono(m)} uso-e-high`, nombre(m))),
        el("span", { class: "uso-clave" }, "esfuerzo:"), ESFUERZOS.map(e => muestra(`uso-gris uso-e-${e}`, e)),
        fs.some(x => !ESFUERZOS.includes(x.esfuerzo)) ? muestra("uso-gris uso-e-vacio", "sin esfuerzo") : null,
        fs.some(x => medidaTramo(x, medida) == null) ? muestra("uso-gris uso-e-medium uso-sin-medida", medida === "delta" ? "sin cambio medido" : "sin datos") : null);
}
function agrupar(xs, clave) { return xs.reduce((r, x) => { const k = clave(x); (r[k] ||= []).push(x); return r; }, {}); }
function tiempo() {
    const p = $("[data-panel=tiempo]"); if (!d.h) { p.replaceChildren(falta()); return; }
    const avisoHistorial = el("p", { class: "tenue" }, "El historial empieza en el encargo 19; los anteriores se ven sólo en la Bitácora.");
    if (!d.h.length) { p.replaceChildren(avisoHistorial, falta()); return; }
    const tarjetas = Object.entries(agrupar(d.h, x => x.encargo)).map(([id, fs]) => {
        const ini = Math.min(...fs.map(x => new Date(x.inicio).getTime()));
        const fin = Math.max(...fs.map(x => new Date(x.inicio).getTime() + Math.max(x.min, (x.pronostico || {}).min || 0) * 60000));
        const rango = Math.max(1, fin - ini);
        const fases = fs.map(x => {
            const pos = 100 * (new Date(x.inicio).getTime() - ini) / rango;
            const ancho = Math.max(2, 100 * x.min * 60000 / rango);
            const pron = x.pronostico && Number.isFinite(x.pronostico.min) ? Math.max(2, 100 * x.pronostico.min * 60000 / rango) : null;
            const b = el("i", { class: `cuenta-${x.cuenta}` }); b.style.setProperty("--inicio", `${pos}%`); b.style.setProperty("--ancho", `${ancho}%`);
            const q = el("i", { class: "pronostico" }); if (pron != null) { q.style.setProperty("--inicio", `${pos}%`); q.style.setProperty("--ancho", `${pron}%`); }
            const v = x.rol === "rev" ? (x.veredicto === "DESPLEGABLE" ? "✅" : x.veredicto ? "❌" : "sin datos") : "";
            return el("div", { class: "encargo-fase" }, el("span", {}, `${x.fase} · ${cuenta(x.cuenta)}`), el("div", { class: "encargo-barra" }, q, b), el("span", { class: "tenue" }, `${x.min} min / pronóstico ${pron != null ? x.pronostico.min : "sin datos"} ${v}`));
        });
        const e = etapaDe(id);
        return el("section", { class: "tarjeta" }, el("h2", {}, `Encargo ${id}`), lineaResumen(e ? resumenCola(e.cola) : "sin resumen"), lineaResumen(resumenEtapa(e), `Etapa ${id} · `),
            el("div", { class: "encargo-fases" }, fases), barraDeUso(fs, medidaUso), leyendaUso(fs, medidaUso));
    });
    const sel = el("select", { "aria-label": "Medir por" }, MEDIDAS.map(([v, t]) => el("option", { value: v }, t)));
    sel.value = medidaUso; sel.onchange = () => { medidaUso = sel.value; tiempo(); };
    p.replaceChildren(avisoHistorial, el("label", { class: "uso-medida" }, "Medir por: ", sel), ...tarjetas);
}
// Encargo 86: Traces y Flow comparten las diez columnas, su orden y la URL. Los datos ausentes siempre quedan al final.
// Las filas sin ese dato van siempre al final, en cualquier sentido. El selector y el clic en el encabezado comparten `orden`.
const COLUMNAS_ORDEN = { fecha: "Fecha", encargo: "Encargo", cuenta: "Cuenta", rol: "Rol", min: "Min", tokens: "Tokens", usd: "USD", pct_5h: "Δ 5 h", pct_sem: "Δ semanal", veredicto: "Veredicto" };
const OPCIONES_ORDEN = [["fecha:desc", "Fecha (más reciente)"], ["fecha:asc", "Fecha (más antigua)"], ["encargo:asc", "Encargo (menor a mayor)"], ["encargo:desc", "Encargo (mayor a menor)"],
    ["cuenta:asc", "Cuenta (A a Z)"], ["cuenta:desc", "Cuenta (Z a A)"], ["rol:asc", "Rol (flujo ascendente)"], ["rol:desc", "Rol (flujo descendente)"], ["min:desc", "Minutos (más a menos)"], ["min:asc", "Minutos (menos a más)"], ["tokens:desc", "Tokens (más a menos)"], ["tokens:asc", "Tokens (menos a más)"], ["usd:desc", "USD (más a menos)"], ["usd:asc", "USD (menos a más)"], ["pct_5h:desc", "Δ 5 h (más a menos)"], ["pct_5h:asc", "Δ 5 h (menos a más)"], ["pct_sem:desc", "Δ semanal (más a menos)"], ["pct_sem:asc", "Δ semanal (menos a más)"], ["veredicto:asc", "Veredicto (DESPLEGABLE primero)"], ["veredicto:desc", "Veredicto (NO DESPLEGABLE primero)"]];
const orden = { clave: "fecha", desc: true };
const fechaCorta = iso => { const m = /^\d{4}-(\d\d)-(\d\d)T(\d\d:\d\d)/.exec(iso || ""); return m ? `${m[2]}-${m[1]} ${m[3]}` : "sin datos"; };
function valorOrden(x, clave) {
    if (clave === "fecha") { const t = Date.parse(x.inicio); return Number.isNaN(t) ? null : t; }
    if (clave === "encargo") return x.encargo == null || x.encargo === "" ? null : String(x.encargo);      // «22b» va después de «22» y antes de «23»
    if (clave === "cuenta") return x.cuenta == null || x.cuenta === "" ? null : cuenta(x.cuenta);
    if (clave === "rol") return Object.prototype.hasOwnProperty.call({ autor: 0, rev: 1, fix: 2, plan: 3, revplan: 4 }, x.rol) ? { autor: 0, rev: 1, fix: 2, plan: 3, revplan: 4 }[x.rol] : null;
    if (clave === "min") return Number.isFinite(x.min) ? x.min : null;
    if (clave === "tokens") { const t = x.tokens && (Number.isFinite(x.tokens.total) ? x.tokens.total : ["entrada", "salida", "cache_lectura", "cache_escritura"].map(k => x.tokens[k]).filter(Number.isFinite)); return Number.isFinite(t) ? t : Array.isArray(t) && t.length ? t.reduce((n, y) => n + y, 0) : null; }
    if (clave === "usd") { const usd = x.tokens && x.tokens.usd; return Number.isFinite(usd) ? usd : null; }
    if (clave === "pct_5h" || clave === "pct_sem") return Array.isArray(x[clave]) && x[clave].length === 2 && x[clave].every(Number.isFinite) ? x[clave][1] - x[clave][0] : null;
    return x.rol === "rev" && (x.veredicto === "DESPLEGABLE" || x.veredicto === "NO DESPLEGABLE") ? (x.veredicto === "DESPLEGABLE" ? 0 : 1) : null;
}
function ordenar(xs, clave, desc) {
    const con = [], sin = [];
    for (const x of xs) (valorOrden(x, clave) == null ? sin : con).push(x);
    const cmp = (a, b) => { const u = valorOrden(a, clave), v = valorOrden(b, clave); return typeof u === "string" ? u.localeCompare(v, "es", { numeric: true }) : u - v; };
    return [...con].sort((a, b) => (desc ? -1 : 1) * cmp(a, b)).concat(sin);
}
function cambiarOrden(clave, desc) { if (desc == null) { if (orden.clave === clave) orden.desc = !orden.desc; else { orden.clave = clave; orden.desc = ["fecha", "min", "tokens", "usd", "pct_5h", "pct_sem"].includes(clave); } } else { orden.clave = clave; orden.desc = desc; } const q = new URLSearchParams(location.hash.split("?")[1] || ""); q.set("o", `${orden.clave}:${orden.desc ? "desc" : "asc"}`); history.replaceState(null, "", `#/${panel}?${q.toString().replace(/%3A/gi, ":")}`); }
// Encargo 84b: la fila y las columnas del Historial salen de hist() para que el Historial de 🕸️ Flujo las llame tal cual.
const CABEZAS_HISTORIAL = ["Fecha", "Encargo", "Cuenta", "Rol", "Min", "Tokens", "USD", "Δ 5 h", "Δ semanal", "Veredicto"];
function filaHistorial(x) { const tok = x.tokens && (x.tokens.total != null ? x.tokens.total : ["entrada", "salida", "cache_lectura", "cache_escritura"].map(k => x.tokens[k]).filter(Number.isFinite).reduce((n, y) => n + y, 0)), usd = x.tokens && x.tokens.usd; const delta = k => Array.isArray(x[k]) && x[k].every(Number.isFinite) ? `${Math.round((x[k][1] - x[k][0]) * 10) / 10} %` : "sin datos"; return el("tr", {}, el("td", {}, fechaCorta(x.inicio)), el("td", {}, x.encargo), el("td", {}, cuenta(x.cuenta)), el("td", {}, x.rol), el("td", {}, x.min), el("td", {}, Number.isFinite(tok) ? tok.toLocaleString("es-CL") : "sin datos"), el("td", {}, Number.isFinite(usd) ? `US$ ${usd.toLocaleString("es-CL", { maximumFractionDigits: 2 })}` : "—"), el("td", {}, delta("pct_5h")), el("td", {}, delta("pct_sem")), el("td", {}, x.rol === "rev" ? val(x.veredicto) : "—")); }
const cabeza = (t, dib) => { const clave = Object.keys(COLUMNAS_ORDEN).find(k => COLUMNAS_ORDEN[k] === t), activa = orden.clave === clave; if (!clave) return el("th", {}, t); const th = el("th", { class: "ordenable", tabindex: "0", role: "button", title: `Ordenar por ${t.toLowerCase()}`, "data-term": t === "Tokens" ? "Tokens" : null, "aria-sort": activa ? (orden.desc ? "descending" : "ascending") : "none" }, activa ? `${t} ${orden.desc ? "▼" : "▲"}` : t); const ir = () => { cambiarOrden(clave); dib(); }; th.onclick = ir; th.onkeydown = ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ir(); } }; return th; };
function hist() {
    const p = $("[data-panel=historial]"); if (!d.h) { p.replaceChildren(tarjetaPasado(), falta()); return; }
    const a = el("select", { "aria-label": "Encargo" }, el("option", { value: "" }, "Todos los encargos"), [...new Set(d.h.map(x => x.encargo))].map(x => el("option", { value: x }, `Encargo ${x}`)));
    const c = el("select", { "aria-label": "Cuenta" }, el("option", { value: "" }, "Todas las cuentas"), [...new Set(d.h.map(x => x.cuenta))].map(x => el("option", { value: x }, cuenta(x))));
    const o = el("select", { "aria-label": "Ordenar por" }, OPCIONES_ORDEN.map(([v, t]) => el("option", { value: v }, t)));
    const out = el("div", {});
    const dib = () => { o.value = `${orden.clave}:${orden.desc ? "desc" : "asc"}`; const fs = ordenar(d.h.filter(x => (!a.value || x.encargo === a.value) && (!c.value || x.cuenta === c.value)), orden.clave, orden.desc); const tot = Object.entries(agrupar(d.h, x => x.cuenta)).map(([k, xs]) => `${cuenta(k)}: ${xs.reduce((n, x) => n + (x.min || 0), 0).toFixed(1)} min`).join(" · "); const tabla = el("table", {}, el("thead", {}, el("tr", {}, ...CABEZAS_HISTORIAL.map(t => cabeza(t, dib)))), el("tbody", {}, fs.map(filaHistorial))); out.replaceChildren(el("p", { class: "tenue" }, "El historial empieza en el encargo 19; los anteriores se ven sólo en la Bitácora."), el("p", { class: "encargo-total tenue" }, tot || "sin datos"), tabla); activarGlosario(out); };
    a.onchange = c.onchange = dib; o.onchange = () => { const [clave, sentido] = o.value.split(":"); cambiarOrden(clave, sentido === "desc"); dib(); };
    dib(); p.replaceChildren(tarjetaPasado(), el("section", { class: "tarjeta" }, el("div", { class: "encargo-filtros" }, a, c, o), out));
}
function bitacora() { $("[data-panel=bitacora]").replaceChildren(el("section", { class: "tarjeta" }, el("h2", {}, "Bitácora"), el("pre", { class: "encargo-bitacora" }, d.estado ? d.estado.split("\n").reverse().join("\n") : "sin datos"))); }
// Encargo 23a: «⚙️ Reparto y modelos». La configuración de los encargos (encargos/modelos.toml) se
// cambia desde acá y no a mano. La pestaña LEE con `cola-run.py --panel`, SIMULA con
// `cola-run.py ejemplo-reparto.toml --simular --con-cambios` (los cambios sin aplicar van por la
// entrada estándar y pasan por la misma validación de aplicar-propuesta) y PROPONE `encargos_config`
// con proponer() de comun.js, como 💳. Los comandos son fijos; lo único que se escribe es la propuesta.
const COLA_RUN = `${DIR}/cola-run.py`, EJEMPLO = `${DIR}/ejemplo-reparto.toml`;
const ROLES = [["autor", "Autor"], ["rev", "Revisión"], ["fix", "Arreglo"]];
const BONITO = { diseno: "diseño", pagina: "página", investigacion: "investigación", maximo: "máximo", agil: "ágil", claude: "Claude (las dos cuentas)", codex: "Codex" };
const bonito = x => BONITO[x] || x;
let cfg = null, edit = null, sim = null, perfilPropuesta = null, configPedida = false, errorConfig = "";
const contadorPropuestas = el("div", { id: "propuestas-contador", class: "aviso neutro" });
const copia = x => JSON.parse(JSON.stringify(x));
// El mismo criterio que cola-run.py: candado por nombre exacto o por trozo del nombre.
function conCandado(modelo, aut) {
    const m = String(modelo).toLowerCase();
    return (aut.modelos || []).some(x => String(x).toLowerCase() === m) || (aut.patrones || []).some(x => m.includes(String(x).toLowerCase()));
}
// La propuesta: sólo lo que cambió entre lo leído (a) y lo editado (b). Los candados van como la
// lista completa, porque aplicar-propuesta rechaza una lista a la que le falte alguno.
function valorConfig(a, b) {
    const v = {}, pon = (parte, k1, k2, x) => { ((v[parte] ||= {})[k1] ||= {})[k2] = x; };
    for (const [nat, roles] of Object.entries(b.naturaleza)) for (const [rol, nivel] of Object.entries(roles)) if (nivel !== a.naturaleza[nat][rol]) pon("naturaleza", nat, rol, nivel);
    for (const [motor, tabla] of Object.entries(b.niveles)) for (const [nivel, x] of Object.entries(tabla)) {
        const y = a.niveles[motor][nivel];
        if (x.modelo !== y.modelo || (x.esfuerzo || "") !== (y.esfuerzo || "")) pon("niveles", motor, nivel, { modelo: x.modelo, esfuerzo: x.esfuerzo || "" });
    }
    for (const [nat, r] of Object.entries(b.reparto)) for (const rol of ["autor", "revisor"]) if (r[rol] !== a.reparto[nat][rol]) pon("reparto", nat, rol, r[rol]);
    if (b.autorizacion.modelos.length !== a.autorizacion.modelos.length) v.autorizacion = { modelos: b.autorizacion.modelos };
    for (const [modelo, k] of Object.entries(b.factor_modelo)) if (k !== a.factor_modelo[modelo]) (v.factor_modelo ||= {})[modelo] = k;
    return v;
}
// [[qué, antes, después]] para el diálogo y la lista de cambios pendientes.
function cambiosConfig(a, v) {
    const r = [], modelo = x => `${x.modelo} ${x.esfuerzo || ""}`.trim();
    for (const [nat, roles] of Object.entries(v.naturaleza || {})) for (const [rol, nivel] of Object.entries(roles)) r.push([`${bonito(nat)} · ${rol}`, bonito(a.naturaleza[nat][rol]), bonito(nivel)]);
    for (const [motor, tabla] of Object.entries(v.niveles || {})) for (const [nivel, x] of Object.entries(tabla)) r.push([`${motor} · ${bonito(nivel)}`, modelo(a.niveles[motor][nivel]), modelo(x)]);
    for (const [nat, x] of Object.entries(v.reparto || {})) for (const [rol, c] of Object.entries(x)) r.push([`reparto ${bonito(nat)} · ${rol}`, nombreCfg(a.reparto[nat][rol]), nombreCfg(c)]);
    if (v.autorizacion) r.push(["candados", a.autorizacion.modelos.join(", ") || "ninguno", v.autorizacion.modelos.join(", ")]);
    for (const [modelo, k] of Object.entries(v.factor_modelo || {})) r.push([`factor de ${modelo}`, a.factor_modelo[modelo] == null ? "sin factor" : coma(a.factor_modelo[modelo]), coma(k)]);
    return r;
}
function nombreCfg(id) { return cfg && cfg.cuentas[id] ? cfg.cuentas[id].nombre : val(id); }
// Factores que no sirven: no es un número, o no es mayor que 0 (un factor 0 pronosticaría que la fase no cuesta nada).
function factoresRotos(m) { return Object.entries(m.factor_modelo).filter(([, k]) => !(Number.isFinite(k) && k > 0)).map(([modelo]) => modelo); }
// Naturalezas donde el reparto editado deja la misma cuenta escribiendo y revisando: no se propone.
function repartoRoto(m) { return Object.entries(m.reparto).filter(([, r]) => r.autor === r.revisor).map(([nat]) => nat); }
function selector(opciones, valor, alCambiar, apagado) {
    const s = el("select", { disabled: !!apagado }, opciones.map(([v, t]) => el("option", { value: v }, t)));
    if (!opciones.some(([v]) => v === valor)) s.append(el("option", { value: valor }, `${val(valor)} (fuera de la lista)`));
    s.value = valor; s.addEventListener("change", () => { alCambiar(s.value); pintarConfig(); }); return s;
}
async function cargarConfig() {
    configPedida = true; cfg = null; sim = null; errorConfig = ""; pintarConfig();
    try {
        const [crudo] = await Promise.all([cockpit.spawn(["python3", COLA_RUN, "--panel"], { err: "message" }), leerBotsInfo().catch(() => null)]);
        const leido = JSON.parse(crudo);
        for (const k of ["niveles", "naturaleza", "reparto", "autorizacion", "factor_modelo"]) leido.modelos[k] ||= {};
        leido.pronosticos ||= {};
        leido.modelos.autorizacion.modelos ||= []; leido.catalogo ||= {}; leido.cuentas ||= {};
        cfg = leido; edit = copia(cfg.modelos);
        perfilPropuesta = (botsInfo && botsInfo.perfiles && Object.keys(botsInfo.perfiles)[0]) || null;
    } catch (e) { errorConfig = "No pude leer la configuración de los encargos: " + (e.message || String(e)); }
    pintarConfig();
    if (cfg) { pintarContadorPropuestas().catch(() => {}); simular(); }
}
async function simular() {
    const clave = JSON.stringify(valorConfig(cfg.modelos, edit)), esta = sim = { clave, texto: "simulando…" };
    pintarConfig();
    try { esta.texto = await cockpit.spawn(["python3", COLA_RUN, EJEMPLO, "--simular", "--con-cambios"], { err: "message" }).input(clave); }
    catch (e) { esta.texto = "⛔ Con estos cambios la propuesta se rechazaría: " + (e.message || String(e)); esta.mal = true; }
    if (sim === esta) pintarConfig();
}
function tablaConfig(cabezas, filas) {
    return el("div", { class: "config-ancho" }, el("table", { class: "config-tabla" }, el("thead", {}, el("tr", {}, cabezas.map(x => el("th", {}, x)))), el("tbody", {}, filas)));
}
function pintarConfig() {
    const p = $("[data-panel=config]");
    if (!cfg) {
        p.replaceChildren(el("section", { class: "tarjeta" }, el("h2", {}, "⚙️ Reparto y modelos"), errorConfig ? el("div", { class: "aviso rojo" }, errorConfig) : el("p", { class: "tenue" }, "leyendo…"),
            errorConfig ? el("button", { class: "mini", onclick: cargarConfig }, "Reintentar") : null), glosario());
        return;
    }
    const a = cfg.modelos, m = edit, niveles = Object.keys(Object.values(a.niveles)[0] || {}).map(n => [n, bonito(n)]);
    const cuentas = Object.entries(cfg.cuentas).map(([id, c]) => [id, c.nombre]);
    const marca = distinto => (distinto ? "config-cambiado" : "");
    const matriz = tablaConfig(["Naturaleza", ...ROLES.map(([, t]) => t)], Object.entries(m.naturaleza).map(([nat, roles]) =>
        el("tr", {}, el("td", {}, bonito(nat)), ROLES.map(([rol]) => el("td", { class: marca(roles[rol] !== a.naturaleza[nat][rol]) },
            selector(niveles, roles[rol], x => { roles[rol] = x; }))))));
    const motores = Object.keys(m.niveles);
    const celdaNivel = (motor, nivel) => {
        const x = m.niveles[motor][nivel], y = a.niveles[motor][nivel], cat = cfg.catalogo[motor];
        if (!x) return el("td", {}, falta());
        const modelos = Object.keys(cat || {}).map(n => [n, conCandado(n, m.autorizacion) ? `🔒 ${n}` : n]);
        const esfuerzos = [["", "(sin esfuerzo)"], ...((cat || {})[x.modelo] || []).map(e => [e, e])];
        return el("td", { class: marca(x.modelo !== y.modelo || (x.esfuerzo || "") !== (y.esfuerzo || "")) }, el("div", { class: "config-par" },
            selector(modelos, x.modelo, n => { x.modelo = n; if (!(cat[n] || []).includes(x.esfuerzo)) x.esfuerzo = ""; }, !cat),
            selector(esfuerzos, x.esfuerzo || "", e => { x.esfuerzo = e; }, !cat)));
    };
    const tablaNiveles = tablaConfig(["Nivel", ...motores.map(bonito)], niveles.map(([n, t]) => el("tr", {}, el("td", {}, t), motores.map(motor => celdaNivel(motor, n)))));
    const sinCatalogo = motores.filter(x => !cfg.catalogo[x]);
    const rotas = repartoRoto(m);
    const reparto = tablaConfig(["Naturaleza", "Escribe", "Revisa"], Object.keys(m.naturaleza).map(nat => {
        const r = m.reparto[nat];
        if (!r) return el("tr", {}, el("td", {}, bonito(nat)), el("td", { colspan: "2" }, el("span", { class: "tenue" }, "sin datos: modelos.toml no trae esta tabla")));
        return el("tr", { class: rotas.includes(nat) ? "config-roto" : "" }, el("td", {}, bonito(nat)), ["autor", "revisor"].map(rol =>
            el("td", { class: marca(r[rol] !== a.reparto[nat][rol]) }, selector(cuentas, r[rol], x => { r[rol] = x; }))));
    }));
    const libres = [...new Set(Object.values(cfg.catalogo).flatMap(x => Object.keys(x || {})))].filter(x => !m.autorizacion.modelos.includes(x));
    const nuevoCandado = el("select", {}, libres.map(x => el("option", { value: x }, x)));
    const candados = el("div", {}, el("div", { class: "chips" }, m.autorizacion.modelos.map(x => a.autorizacion.modelos.includes(x) ? el("span", { class: "chip dato" }, `🔒 ${x}`)
        : el("span", { class: "chip ojo" }, `🔒 ${x} (nuevo) `, el("button", { class: "mini", title: "Deshacer: todavía no está propuesto", onclick: () => { m.autorizacion.modelos = m.autorizacion.modelos.filter(y => y !== x); pintarConfig(); } }, "✕")))),
        el("p", { class: "tenue" }, `También tiene candado todo modelo cuyo nombre contenga: ${(m.autorizacion.patrones || []).join(", ") || "sin datos"}. La cola pide la autorización por Telegram y espera hasta ${val(m.autorizacion.espera_max_min)} min.`),
        el("div", { class: "controles-voz" }, nuevoCandado, el("button", { class: "mini", disabled: !libres.length, onclick: () => { m.autorizacion.modelos = [...m.autorizacion.modelos, nuevoCandado.value]; pintarConfig(); } }, "Agregar candado")),
        el("p", { class: "tenue" }, "Desde acá sólo se agregan candados. Quitar uno no se hace desde la página."));
    // El factor de cuota de cada modelo (encargo 24): vacío = sin factor, vale 1. Los de Codex no tienen medida.
    const rotos = factoresRotos(m);
    const filaFactor = modelo => {
        const p = cfg.pronosticos[modelo], k = m.factor_modelo[modelo];
        const campo = el("input", { type: "number", min: "0.01", max: "100", step: "0.01", class: "numero", "aria-label": `Factor de ${modelo}`, placeholder: "sin factor", value: k == null ? "" : String(k) });
        campo.addEventListener("change", () => { if (campo.value === "") { if (a.factor_modelo[modelo] == null) delete m.factor_modelo[modelo]; else m.factor_modelo[modelo] = a.factor_modelo[modelo]; } else m.factor_modelo[modelo] = Number(campo.value); pintarConfig(); });
        return el("tr", { class: rotos.includes(modelo) ? "config-roto" : "" }, el("td", {}, modelo), el("td", { class: marca(k !== a.factor_modelo[modelo]) }, campo),
            el("td", { class: "tenue" }, p ? `autor ${p.cuenta in cfg.cuentas ? cfg.cuentas[p.cuenta].nombre : p.cuenta}: +${coma(p.pct_5h, 1)} % 5 h, +${coma(p.pct_sem, 1)} % sem${p.etiqueta ? ` [${p.etiqueta}]` : " (medido)"}` : "sin datos"));
    };
    const factores = tablaConfig(["Modelo", "Factor", "Pronóstico de autor, con lo aplicado"], Object.values(cfg.catalogo).flatMap(x => Object.keys(x || {})).map(filaFactor));
    const valor = valorConfig(a, m), cambios = cambiosConfig(a, valor), hay = cambios.length > 0;
    const vieja = sim && sim.clave !== JSON.stringify(valor);
    const efecto = el("section", { class: "tarjeta" }, el("h2", {}, "Efecto antes de proponer"),
        el("p", { class: "tenue" }, "Lo que diría cola-run.py --simular para un manifiesto de ejemplo con una etapa por naturaleza y sin autor ni revisor escritos: cuenta, modelo, nivel y pronóstico de cada rol."),
        hay ? el("ul", {}, cambios.map(([que, antes, despues]) => el("li", {}, el("strong", {}, que), `: ${antes} → ${despues}`))) : el("p", {}, "Sin cambios pendientes."),
        rotas.length ? el("div", { class: "aviso rojo" }, `En ${rotas.map(bonito).join(", ")} escribe y revisa la misma cuenta. El reparto por defecto nunca lo acepta.`) : null,
        rotos.length ? el("div", { class: "aviso rojo" }, `El factor de ${rotos.join(", ")} tiene que ser un número mayor que 0.`) : null,
        perfilPropuesta ? null : el("div", { class: "aviso ojo" }, "No pude leer los perfiles (bots-info): sin eso la propuesta no se puede guardar."),
        el("div", { class: "fila-botones" },
            el("button", { class: "secundario", onclick: simular }, hay ? "Simular con estos cambios" : "Simular de nuevo"),
            el("button", { disabled: !hay || rotas.length > 0 || rotos.length > 0 || !perfilPropuesta, onclick: () => proponer({ tipo: "encargos_config", valor, clave: "modelos.toml",
                antes: cambios.map(([que, antes]) => `${que}: ${antes}`).join(" · "), despues: cambios.map(([que, , despues]) => `${que}: ${despues}`).join(" · ") }, perfilPropuesta) }, "Proponer cambios"),
            el("button", { class: "secundario", disabled: !hay, onclick: () => { edit = copia(cfg.modelos); pintarConfig(); } }, "Descartar cambios"),
            el("button", { class: "secundario", onclick: cargarConfig }, "Releer el archivo")),
        vieja ? el("div", { class: "aviso ojo" }, "La simulación de abajo es anterior a tus últimos cambios.") : null,
        el("pre", { class: `encargo-bitacora config-simulacion${sim && sim.mal ? " config-mal" : ""}` }, sim ? sim.texto : "sin datos"), glosario());
    p.replaceChildren(contadorPropuestas,
        el("section", { class: "tarjeta" }, el("h2", {}, "Nivel por naturaleza y rol"), el("p", { class: "tenue" }, "Con qué nivel corre cada rol según la naturaleza del encargo. El criterio: la revisión nunca por debajo del autor."), matriz),
        el("section", { class: "tarjeta" }, el("h2", {}, "Modelo y esfuerzo de cada nivel"), el("p", { class: "tenue" }, "Sólo modelos que existen: los de Claude ya conocidos y el catálogo que publica Codex. El esfuerzo, sólo los que acepta ese modelo."),
            sinCatalogo.length ? el("div", { class: "aviso ojo" }, `Sin datos del catálogo de ${sinCatalogo.map(bonito).join(", ")}: sus modelos no se pueden cambiar.`) : null, tablaNiveles),
        el("section", { class: "tarjeta" }, el("h2", {}, "Reparto por defecto"), el("p", { class: "tenue" }, "Quién escribe y quién revisa cuando el manifiesto no lo dice. Es una sugerencia para la cola y para la skill encargar."), reparto),
        el("section", { class: "tarjeta" }, el("h2", {}, "Candados"), candados),
        el("section", { class: "tarjeta" }, el("h2", {}, "Factor de cuota por modelo"),
            el("p", { class: "tenue" }, "Cuánta cuota gasta un modelo frente al de referencia de su motor (Claude Opus 5.5 = 1). Se usa sólo cuando no hay 3 mediciones del mismo modelo: el pronóstico sale de las de la cuenta, ajustadas por este factor, y queda marcado como débil. Afecta los % de cuota, no los minutos. El esfuerzo no entra. Los modelos de Codex no tienen medida: sin factor valen 1."),
            factores), efecto);
}
// Encargo 24: el aviso previo de cuota se edita en las filas de cuota, con la propuesta `registro_cuentas` de 💳 Cuentas.
let camposAviso = [];
function campoAviso(x) {
    const campo = el("input", { type: "number", min: "1", max: String(x.tope - 1), step: "1", class: "numero", "aria-label": `Aviso previo de ${x.alarma}`, placeholder: "sin aviso", value: x.aviso == null ? "" : String(x.aviso) });
    camposAviso.push({ x, campo });
    return el("div", { class: "aviso-previo" }, el("label", {}, "Aviso previo % ", campo), el("div", { class: "tenue" }, x.aviso_previo));
}
// Lo que cambió: {cuenta: {aviso_5h|aviso_semanal: entero|null}}. Vacío = quitar el aviso. null si algún valor no sirve.
function valorAvisos() {
    const valor = {};
    for (const { x, campo } of camposAviso) {
        const t = campo.value.trim(), n = t === "" ? null : Number(t);
        if (n !== null && !(Number.isInteger(n) && n >= 1 && n < x.tope)) { aviso(`${x.alarma}: el aviso tiene que ser un entero de 1 a ${x.tope - 1}, menor que el tope (${x.tope} %).`); return null; }
        if (n !== (x.aviso == null ? null : x.aviso)) (valor[x.cuenta] ||= {})[x.aviso_campo] = n;
    }
    aviso("");
    return valor;
}
async function proponerAvisos() {
    const valor = valorAvisos();
    if (valor === null) return;
    if (!Object.keys(valor).length) { aviso("No hay avisos distintos de los que ya están."); return; }
    try { if (!botsInfo) await leerBotsInfo(); } catch (e) { aviso("No pude leer los perfiles (bots-info): sin eso la propuesta no se puede guardar."); return; }
    const perfil = botsInfo && botsInfo.perfiles && Object.keys(botsInfo.perfiles)[0];
    if (!perfil) { aviso("No hay un perfil válido para guardar la propuesta."); return; }
    const hojas = f => Object.entries(valor).flatMap(([cuenta, v]) => Object.entries(v).map(([campo, n]) => `${cuenta} ${campo} ${f(cuenta, campo, n)}`)).join(" · ");
    const antes = Object.fromEntries(camposAviso.map(({ x }) => [`${x.cuenta} ${x.aviso_campo}`, x.aviso]));
    proponer({ tipo: "registro_cuentas", valor, clave: "avisos previos", antes: hojas((c, k) => antes[`${c} ${k}`] ?? "sin aviso"), despues: hojas((c, k, n) => n ?? "sin aviso") }, perfil);
}
// Encargo 23b: «🔔 Avisos». Sólo lectura. Todo sale de `registro_avisos.py --panel` (comando fijo, sin
// argumentos de la página): el registro único /opt/nodo/datos/avisos.jsonl, más lo que nodo-desplegar
// y el agente de noticias dejan en su propio estado. Los umbrales de las alarmas vienen ya leídos de
// donde viven (cuentas.toml, estado.py…): acá no hay ningún número escrito.
const REGISTRO_AVISOS = `${DIR}/registro_avisos.py`;
const ORIGENES = { cola: "Colas", paginas: "Páginas de Cockpit", nodo: "Nodo", cuota: "Cuota", "nodo-desplegar": "nodo-desplegar", noticias: "Noticias" };
const NIVELES = { info: ["info", "chip dato"], ok: ["ok", "chip dato activa"], alerta: ["alerta", "chip dato ojo"], error: ["error", "chip dato mal"] };
let av = null, avLeido = 0, avCargando = false, errorAvisos = "";
const filtroAvisos = { origen: "", nivel: "" };
const origenTxt = x => ORIGENES[x] || val(x);
function filtrarAvisos(xs, f) { return xs.filter(x => (!f.origen || x.origen === f.origen) && (!f.nivel || x.nivel === f.nivel)); }
const momentoAviso = iso => cuando(iso) || "sin datos";      // cuando() es de comun.js
async function cargarAvisos() {
    avCargando = true; errorAvisos = ""; pintarAvisos();
    try {
        const leido = JSON.parse(await cockpit.spawn(["python3", REGISTRO_AVISOS, "--panel"], { err: "message" }));
        for (const k of ["avisos", "pendientes", "alarmas"]) if (!Array.isArray(leido[k])) leido[k] = [];
        av = leido; avLeido = Date.now();
    } catch (e) { errorAvisos = "No pude leer el registro de avisos: " + (e.message || String(e)); }
    avCargando = false; pintarAvisos();
}
function nivelAviso(x) { const n = NIVELES[x] || [val(x), "chip dato"]; return el("span", { class: n[1] }, n[0]); }
function copiar(boton, texto) { navigator.clipboard.writeText(texto).then(() => { boton.textContent = "copiado ✓"; }, () => { boton.textContent = "no se pudo copiar"; }); }
// El mensaje de Telegram es texto simple; lo que hay que copiar (p. ej. reanudar una pausa) viaja aparte, en `linea`.
function cuerpoAviso(x) { return [el("div", { class: "aviso-texto" }, val(x.texto)), x.linea ? el("div", { class: "aviso-copiable" }, el("code", { class: "aviso-linea" }, x.linea), el("button", { class: "mini", title: "Copiar la línea", onclick: ev => copiar(ev.target, x.linea) }, "Copiar")) : null]; }
function pintarAvisos() {
    camposAviso = [];
    const p = $("[data-panel=avisos]");
    if (!av) {
        p.replaceChildren(el("section", { class: "tarjeta" }, el("h2", {}, "🔔 Avisos"), errorAvisos ? el("div", { class: "aviso rojo" }, errorAvisos) : el("p", { class: "tenue" }, "leyendo…"),
            errorAvisos ? el("button", { class: "mini", onclick: cargarAvisos }, "Reintentar") : null));
        return;
    }
    const pendientes = el("section", { class: "tarjeta" }, el("h2", {}, "Esperan tu ✅ en Telegram"),
        av.pendientes.length ? el("ul", { class: "avisos-pendientes" }, av.pendientes.map(x => el("li", {}, el("div", { class: "tenue" }, `${momentoAviso(x.momento)} · ${origenTxt(x.origen)} · pedido ${val(x.id)}`), cuerpoAviso(x))))
            : el("p", {}, "Ningún aviso tiene una línea o un pedido esperando respuesta."),
        el("p", { class: "tenue" }, "El estado sale de los resultados que publica nodo-desplegar. Un pedido que hizo un agente a mano, sin pasar por una cola, aparece recién cuando se cierra."));
    const origenes = [...new Set(av.avisos.map(x => x.origen))], niveles = (av.niveles || Object.keys(NIVELES)).filter(n => av.avisos.some(x => x.nivel === n));
    const so = el("select", { "aria-label": "Origen" }, el("option", { value: "" }, "Todos los orígenes"), origenes.map(x => el("option", { value: x }, origenTxt(x))));
    const sn = el("select", { "aria-label": "Nivel" }, el("option", { value: "" }, "Todos los niveles"), niveles.map(x => el("option", { value: x }, (NIVELES[x] || [x])[0])));
    so.value = origenes.includes(filtroAvisos.origen) ? filtroAvisos.origen : (filtroAvisos.origen = "");
    sn.value = niveles.includes(filtroAvisos.nivel) ? filtroAvisos.nivel : (filtroAvisos.nivel = "");
    const out = el("div", { class: "config-ancho" });
    const dib = () => {
        filtroAvisos.origen = so.value; filtroAvisos.nivel = sn.value;
        const fs = filtrarAvisos(av.avisos, filtroAvisos);
        out.replaceChildren(el("p", { class: "tenue" }, `${fs.length} de ${av.avisos.length} avisos${av.total > av.avisos.length ? ` (los más nuevos de ${av.total})` : ""}.`),
            fs.length ? el("table", { class: "avisos-tabla" }, el("thead", {}, el("tr", {}, ["Momento", "Origen", "Nivel", "Aviso", "Estado"].map(x => el("th", {}, x)))),
                el("tbody", {}, fs.map(x => el("tr", {}, el("td", {}, momentoAviso(x.momento)), el("td", {}, origenTxt(x.origen)), el("td", {}, nivelAviso(x.nivel)), el("td", {}, cuerpoAviso(x)), el("td", {}, x.estado || "—"))))) : falta());
    };
    so.onchange = sn.onchange = dib; dib();
    const notas = [av.ilegibles ? `${av.ilegibles} líneas del registro no se pudieron leer.` : null,
        av.sin_volcar ? `${av.sin_volcar} avisos del nodo todavía están fuera del registro (se escribieron con el volumen cerrado o sin permiso) y se muestran igual.` : null].filter(Boolean);
    const historial = el("section", { class: "tarjeta" }, el("h2", {}, "Historial"),
        el("div", { class: "encargo-filtros" }, so, sn, el("button", { class: "mini", disabled: avCargando, onclick: cargarAvisos }, avCargando ? "leyendo…" : "Releer")),
        notas.length ? el("div", { class: "aviso ojo" }, notas.join(" ")) : null, out,
        el("p", { class: "tenue" }, `Registro: ${val(av.registro)}. El aviso por curl de un encargo viejo y lo que contestan los bots no pasan por acá.`));
    const grupos = agrupar(av.alarmas, x => x.grupo);
    const alarmas = el("section", { class: "tarjeta" }, el("h2", {}, "Alarmas configuradas"),
        el("p", { class: "tenue" }, "Cada umbral se lee de donde vive; acá no se edita, salvo el aviso previo de cuota: un % por cuenta y por ventana, menor que el tope, que avisa solo si una cola activa usa esa cuenta. Los topes son los de 💳 Cuentas."),
        el("div", { class: "fila-botones" }, el("button", { class: "mini", onclick: proponerAvisos }, "Proponer avisos previos")),
        av.alarmas.length ? el("div", { class: "config-ancho" }, el("table", { class: "avisos-tabla" }, el("thead", {}, el("tr", {}, ["Alarma", "Umbral", "Ahora", "Fuente"].map(x => el("th", {}, x)))),
            el("tbody", {}, Object.entries(grupos).flatMap(([g, xs]) => [el("tr", { class: "avisos-grupo" }, el("th", { colspan: "4" }, g)),
                ...xs.map(x => el("tr", {}, el("td", {}, val(x.alarma)), el("td", {}, val(x.umbral), x.aviso_campo ? campoAviso(x) : null), el("td", {}, x.ahora || "—"),
                    el("td", { class: "tenue" }, val(x.fuente), x.nota ? el("div", { class: "aviso-nota" }, x.nota) : null)))])))) : falta());
    p.replaceChildren(pendientes, historial, alarmas);
}
// Se relee al entrar a la pestaña si lo leído tiene más de medio minuto, y con «Releer».
function avisos() { if (!avCargando && Date.now() - avLeido > 30000) cargarAvisos(); else pintarAvisos(); }
// pintar() llega acá con cada relectura de la página: la pestaña se lee una vez y no se redibuja sola,
// para no borrar lo que se está editando.
function glosario() {
    const cabeza = el("thead", {}, el("tr", {}, ["Nombre de hoy", "Término", "Definición"].map(x => el("th", {}, x))));
    const cuerpo = el("tbody", {}, GLOSARIO_MAPEO.map(x => el("tr", {}, el("td", {}, x[0]), el("td", { "data-term": x[1] }, x[1]), el("td", {}, x[2]))));
    return el("section", { class: "tarjeta glosario" }, el("h2", {}, "Glosario"), el("p", { class: "tenue" }, "Nombres de hoy y términos de la industria usados en AI Ops."),
        el("div", { class: "config-ancho" }, el("table", {}, cabeza, cuerpo)));
}
function config() { if (!configPedida) cargarConfig(); }
// Encargo 84b: 🕸️ Flujo, la portada. La red y sus luces viven en red.js (redEncargos); acá sólo se le pasa lo ya leído.
// Compatibilidad 84b: function flujo() { redEncargos.pintar($("[data-panel=flujo]"), d); }
function alcanceFlujo() {
    const q = new URLSearchParams((location.hash.split("?")[1] || ""));
    if (q.has("curso")) return { tipo: "curso", valor: "" };
    if (q.has("e")) return { tipo: "encargo", valor: seguro(q.get("e")) };
    if (q.has("n")) return { tipo: "naturaleza", valor: seguro(q.get("n")) };
    if (q.has("c")) return { tipo: "cuenta", valor: seguro(q.get("c")) };
    return { tipo: "todo", valor: "" };
}
function hashFlujo(tipo, valor = "") {
    const q = new URLSearchParams(location.hash.split("?")[1] || ""); ["curso", "e", "n", "c"].forEach(k => q.delete(k));
    if (tipo === "curso") q.set("curso", "1");
    if (tipo === "encargo") q.set("e", valor);
    if (tipo === "naturaleza") q.set("n", valor);
    if (tipo === "cuenta") q.set("c", valor);
    return `#/flujo${q.size ? `?${q.toString().replace(/%3A/gi, ":")}` : ""}`;
}
function flujo() { redEncargos.pintar($("[data-panel=flujo]"), d, alcanceFlujo(), hashFlujo); }
function pintar() { pintarConsola(); if (!d) return; ({ flujo, ahora, tiempo, historial: hist, bitacora, avisos, config })[panel](); activarGlosario($("[data-panel=" + panel + "]")); verPendiente(); }
// Encargo 84a: la consola del nodo. Encargo 85a deja una sola barra: las pestañas conservan su data-p y el hash; Ctrl+K conserva los destinos
// de barra.js como «Ir a». Nada de este marco ejecuta ni escribe: sólo navega, muestra el pulso y aplica el tema.
const PAQUETE = "encargos", PORTADA = "flujo";
const MODULOS = barraNodo.GRUPOS.flat();
const RUTA = /^#\/([a-z]+)(?:\?(?:(?:e|n|c|o)=[^#&]*|curso=1)(?:&(?:(?:e|n|c|o)=[^#&]*|curso=1))*)?$/;
const CUENTAS_BARRA = ["claude_diego", "claude_cami", "codex"];
const ESTILO = "shell:style", TEMAS = [["auto", "◐", "automático, como Cockpit"], ["light", "☀", "claro"], ["dark", "☾", "oscuro"]];
const botonesPestanas = () => [...document.querySelectorAll("#pestanas [data-p]")];
function rutaDeHash(h) { const m = RUTA.exec(h || ""); return m && botonesPestanas().some(b => b.dataset.p === m[1]) ? m[1] : null; }
function nombreSub(p) { const b = botonesPestanas().find(x => x.dataset.p === p); return b ? b.textContent.trim().replace(/\s+\d+$/, "") : p; }
function mostrar(p) {
    const [clave, sentido] = (new URLSearchParams(location.hash.split("?")[1] || "").get("o") || "").split(":");
    if (Object.prototype.hasOwnProperty.call(COLUMNAS_ORDEN, clave) && (sentido === "asc" || sentido === "desc")) { orden.clave = clave; orden.desc = sentido === "desc"; }
    panel = p;
    for (const b of botonesPestanas()) { b.classList.toggle("activa", b.dataset.p === p); b.setAttribute("aria-selected", String(b.dataset.p === p)); }
    document.querySelectorAll("[data-panel]").forEach(x => { x.hidden = x.dataset.panel !== p; });
    $("#miga").textContent = $("#titulo").textContent = nombreSub(p);
    $("#pestanas-select").value = p;
    $(".consola-trabajo").scrollTop = 0;
    pintar();
}
// Navegar es cambiar el hash: Cockpit lo copia en su URL, y al recargar se vuelve al mismo submódulo.
function ir(p) { const h = `#/${p}?o=${orden.clave}:${orden.desc ? "desc" : "asc"}`; if (location.hash === h) mostrar(p); else location.hash = h; }
function irModulo(m) { if (m.id === PAQUETE) ir(PORTADA); else cockpit.jump(m.destino); }
function armarPestanas() {
    const s = $("#pestanas-select");
    s.replaceChildren(...botonesPestanas().map(b => el("option", { value: b.dataset.p }, nombreSub(b.dataset.p))));
    s.addEventListener("change", () => ir(s.value));
}
// El pulso del nodo: cinco puntos que se encienden si hay una cola viva. «Viva» es lo mismo que en barra.js y en
// «Ahora»: una sesión cola* de tmux (d.sesiones). Va en SVG con atributos; la animación es de encargos.css.
const SVG = "http://www.w3.org/2000/svg", PUNTOS = [[8, 15], [27, 7], [27, 23], [49, 15], [36, 15]];
function svg(tag, attrs) { const e = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v)); return e; }
function armarPulso() {
    const s = svg("svg", { viewBox: "0 0 58 30", "aria-hidden": "true" });
    for (const [a, b] of [[0, 1], [0, 2], [1, 3], [2, 3]]) s.append(svg("line", { x1: PUNTOS[a][0], y1: PUNTOS[a][1], x2: PUNTOS[b][0], y2: PUNTOS[b][1] }));
    for (const [cx, cy] of PUNTOS) s.append(svg("circle", { cx, cy, r: 3 }));
    $("#pulso").replaceChildren(s);
}
function badge(nodo, n, titulo) { nodo.hidden = !(n > 0); nodo.textContent = n > 0 ? String(n) : ""; nodo.title = n > 0 ? titulo : ""; }
// El chip de cuentas: las tres cuentas de los encargos, con uso() (el % de 5 h y semanal de uso.json).
let cuentasAbiertas = false;
const cuentasResumen = el("button", { class: "cuentas-resumen", "aria-expanded": "false", "aria-controls": "cuentas-lista", onclick: ev => { ev.stopPropagation(); abrirCuentas(!cuentasAbiertas); } }, "💳 Cuentas ▾");
const cuentasLista = el("div", { id: "cuentas-lista", class: "cuentas-lista" });
function abrirCuentas(si) { cuentasAbiertas = si; $("#cuentas").classList.toggle("abierta", si); cuentasResumen.setAttribute("aria-expanded", String(si)); }
function pintarCuentas() {
    const filas = () => (d ? CUENTAS_BARRA.map(id => el("div", { class: `cuenta-chip c-${id}` }, el("strong", {}, cuenta(id)), el("span", {}, uso(id)))) : [falta()]);
    cuentasLista.replaceChildren(...filas());
    cuentasResumen.title = d ? CUENTAS_BARRA.map(id => `${cuenta(id)}: ${uso(id)}`).join("\n") : "sin datos";
}
function pintarConsola() {
    const vivas = d ? d.sesiones.length : 0, pendientes = av ? av.pendientes.length : 0;
    const pulso = $("#pulso"), texto = !d ? "Pulso del nodo: sin datos" : vivas ? `Pulso del nodo: ${vivas} cola(s) viva(s)` : "Pulso del nodo: ninguna cola viva";
    pulso.classList.toggle("viva", vivas > 0); pulso.title = texto; pulso.setAttribute("aria-label", texto);
    badge($('#pestanas [data-p="ahora"] .riel-badge'), vivas, `${vivas} cola(s) viva(s)`);
    badge($('#pestanas [data-p="avisos"] .riel-badge'), pendientes, `${pendientes} aviso(s) esperan tu ✅ en Telegram`);
    badge($("#campana-badge"), pendientes, `${pendientes} aviso(s) esperan tu ✅ en Telegram`);
    pintarCuentas();
}
// El selector de tema cambia el de Cockpit (auto, claro u oscuro), el mismo que elige su menú; tema.js lo aplica.
function estiloTema() { let s = null; try { s = localStorage.getItem(ESTILO); } catch (e) { /* sin storage */ } return TEMAS.find(t => t[0] === s) || TEMAS[0]; }
function pintarTema() { const [, icono, nombre] = estiloTema(); for (const b of document.querySelectorAll("[data-tema]")) { b.textContent = b.dataset.tema === "corto" ? icono : `${icono} Tema ${nombre}`; b.title = `Tema ${nombre}: cambia el de Cockpit`; b.setAttribute("aria-label", b.title); } }
function cambiarTema() { const t = TEMAS[(TEMAS.indexOf(estiloTema()) + 1) % TEMAS.length]; try { localStorage.setItem(ESTILO, t[0]); } catch (e) { /* sin storage: queda como está */ } aplicarTema(); pintarTema(); }
// Actualizar relee lo mismo que relee la página cada minuto. Mientras corre, el botón se apaga.
let releyendo = false;
async function releer() {
    if (releyendo) return;
    releyendo = true; document.querySelectorAll("[data-releer]").forEach(b => { b.disabled = true; });
    try { await leer(); } catch (e) { aviso(e.message || String(e)); } finally { releyendo = false; document.querySelectorAll("[data-releer]").forEach(b => { b.disabled = false; }); }
}
// Buscador Ctrl+K sobre lo que la página ya leyó: módulos, submódulos, colas, encargos y avisos. Elegir un resultado
// sólo navega (cambia el submódulo o abre otra página); nunca ejecuta. El texto que viene del historial, de los
// manifiestos o de los avisos pasa por delPanel() (la lista blanca y la regla de nombres) y se pone como texto.
const normal = t => String(t).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
function entradasBusqueda() {
    const r = [...MODULOS.map(m => ({ tipo: "módulo", texto: `${m.icono} ${m.texto}`, ir: () => irModulo(m) })),
        ...botonesPestanas().map(b => ({ tipo: "sección", texto: `🏭 AI Ops › ${nombreSub(b.dataset.p)}`, ir: () => ir(b.dataset.p) }))];
    if (d) {
        const colas = [...new Set([...d.sesiones, ...d.vivos.map(v => v.nombre), ...(d.resumenes || []).map(c => c.cola)])].filter(c => typeof c === "string" && COLA_VALIDA.test(c));
        r.push(...colas.map(c => ({ tipo: "cola", texto: `${c} · ${conEtiqueta(resumenCola(c))}`, ir: () => irA("ahora", c) })));
        const ids = [...new Set([...(d.h || []).map(x => String(x.encargo)), ...(d.resumenes || []).flatMap(c => c.etapas.map(e => String(e.id)))])];
        r.push(...ids.map(id => ({ tipo: "encargo", texto: `Encargo ${delPanel(id)} · ${conEtiqueta(resumenEtapa(etapaDe(id)))}`, ir: () => irA("tiempo", `Encargo ${id}`) })));
    }
    if (av) r.push(...av.avisos.map(x => ({ tipo: "aviso", texto: `${momentoAviso(x.momento)} · ${delPanel(String(x.texto ?? "").split("\n")[0])}`, ir: () => ir("avisos") })));
    return r;
}
// Tras navegar desde el buscador, la tarjeta de esa cola o de ese encargo queda a la vista, si está dibujada.
let pendienteVer = null;
function irA(p, encabezado) { pendienteVer = { p, encabezado }; ir(p); }
function verPendiente() {
    const x = pendienteVer; if (!x || x.p !== panel) return; pendienteVer = null;
    const h = [...document.querySelectorAll(`[data-panel="${panel}"] h2`)].find(t => t.textContent === x.encabezado || t.textContent.startsWith(`${x.encabezado} ·`));
    if (h) h.scrollIntoView({ block: "start" });
}
let buscador = null;
function cerrarBuscador() { if (buscador) { buscador.remove(); buscador = null; } }
function abrirBuscador() {
    cerrarBuscador();
    const entrada = el("input", { type: "search", class: "buscador-entrada", placeholder: "Buscar colas, encargos, avisos o módulos…", "aria-label": "Buscar" });
    const lista = el("div", { class: "buscador-lista" }), todas = entradasBusqueda();
    const elegir = x => { cerrarBuscador(); x.ir(); };
    const dib = () => {
        const q = normal(entrada.value.trim()), fs = todas.filter(x => !q || normal(`${x.tipo} ${x.texto}`).includes(q)).slice(0, 30);
        lista.replaceChildren(...(fs.length ? fs.map(x => el("button", { class: "buscador-item", onclick: () => elegir(x) }, el("span", { class: "buscador-texto" }, x.texto), el("small", {}, x.tipo)))
            : [el("p", { class: "tenue" }, "Nada coincide.")]));
    };
    entrada.addEventListener("input", dib);
    entrada.addEventListener("keydown", ev => { const b = lista.querySelector("button"); if (ev.key === "Enter" && b) b.click(); else if (ev.key === "ArrowDown" && b) { ev.preventDefault(); b.focus(); } });
    lista.addEventListener("keydown", ev => {
        const bs = [...lista.querySelectorAll("button")], i = bs.indexOf(document.activeElement);
        if (ev.key === "ArrowDown" && i >= 0 && i < bs.length - 1) { ev.preventDefault(); bs[i + 1].focus(); }
        else if (ev.key === "ArrowUp" && i >= 0) { ev.preventDefault(); (i > 0 ? bs[i - 1] : entrada).focus(); }
    });
    const capa = el("div", { class: "buscador", role: "dialog", "aria-modal": "true", "aria-label": "Buscar" }, el("div", { class: "buscador-caja" }, entrada, lista));
    capa.addEventListener("click", ev => { if (ev.target === capa) cerrarBuscador(); });
    buscador = capa; document.body.append(capa); dib(); entrada.focus();
}
document.addEventListener("keydown", ev => {
    if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && String(ev.key).toLowerCase() === "k") { ev.preventDefault(); if (buscador) cerrarBuscador(); else abrirBuscador(); }
    else if (ev.key === "Escape") { if (buscador) cerrarBuscador(); else if (cuentasAbiertas) abrirCuentas(false); }
});
document.addEventListener("click", ev => { if (cuentasAbiertas && !$("#cuentas").contains(ev.target)) abrirCuentas(false); });
// Un solo tooltip para términos fijos. Funciona con puntero, foco y presión sostenida táctil.
function ocultarTooltip() { $("#term-tooltip").hidden = true; }
function mostrarTooltip(ev) { const origen = ev.currentTarget, termino = origen.dataset.term, definicion = GLOSARIO[termino]; if (!definicion) return; const t = $("#term-tooltip"); t.replaceChildren(el("strong", {}, termino), el("span", {}, definicion)); t.hidden = false; }
function activarGlosario(raiz = document) {
    raiz.querySelectorAll("[data-term]").forEach(n => {
        if (!GLOSARIO[n.dataset.term] || n.dataset.tooltip) return;
        n.dataset.tooltip = "si"; n.setAttribute("aria-describedby", "term-tooltip");
        if (!n.matches("button, a, input, select, textarea, [tabindex]")) n.setAttribute("tabindex", "0");
        n.addEventListener("pointerenter", mostrarTooltip); n.addEventListener("pointerleave", ocultarTooltip);
        n.addEventListener("focus", mostrarTooltip); n.addEventListener("blur", ocultarTooltip);
        let espera = null;
        n.addEventListener("pointerdown", ev => { const origen = ev.currentTarget; if (ev.pointerType !== "mouse") espera = setTimeout(() => mostrarTooltip({ currentTarget: origen }), 450); });
        for (const evento of ["pointerup", "pointercancel", "pointerleave"]) n.addEventListener(evento, () => { clearTimeout(espera); });
    });
}
// Arranque: el marco, la ruta del hash y la primera lectura.
armarPestanas(); armarPulso(); activarGlosario();
$("#cuentas").replaceChildren(cuentasResumen, cuentasLista);
$("#tema").addEventListener("click", cambiarTema);
$("#releer").addEventListener("click", releer);
$("#campana").addEventListener("click", () => ir("avisos"));
pintarTema(); window.addEventListener("storage", pintarTema);
botonesPestanas().forEach(b => b.addEventListener("click", () => ir(b.dataset.p)));
$("#buscar").addEventListener("click", abrirBuscador);
window.addEventListener("hashchange", () => mostrar(rutaDeHash(location.hash) || PORTADA));
mostrar(rutaDeHash(location.hash) || PORTADA);
if (!rutaDeHash(location.hash)) location.replace(`#/${panel}`);
leer().catch(e => aviso(e.message || String(e)));
// El badge de 🔔 y el buscador usan los avisos: se leen al abrir, con el mismo comando fijo de la pestaña.
cargarAvisos().then(pintarConsola);
// La barra avanza con el reloj sin releer (cada 20 s) y los archivos se releen cada minuto.
setInterval(() => { if (!document.hidden && panel === "ahora") pintar(); }, 20000);
// Encargo 84b: 🕸️ Flujo también relee cada minuto, porque su modo «En vivo» dibuja la fase en curso de cada cola.
setInterval(() => { if (!document.hidden && (panel === "ahora" || panel === "flujo")) leer().catch(e => aviso(e.message || String(e))); }, 60000);
setInterval(() => { if (!document.hidden && panel !== "ahora") pintarConsola(); }, 20000);
// Ya no hay #barra, así que barra.js no refresca solo (su arranque exige el nodo): fuera de «Ahora» se relee igual, cada 5 min
// como hacía la barra, para que el pulso y el badge de «Ahora» no queden con un estado viejo.
setInterval(() => { if (!document.hidden && panel !== "ahora" && panel !== "flujo") leer().catch(e => aviso(e.message || String(e))); }, 5 * 60 * 1000);
