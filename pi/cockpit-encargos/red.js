/*
 * Encargo 84b: 🕸️ Flujo, la portada de 🧵 Encargos (C · Híbrida). Una red de cinco capas, cuenta → modelo · esfuerzo →
 * naturaleza · rol → encargo → resultado, armada con el historial que encargos.js ya leyó en leer(), y luces que avanzan
 * por las conexiones (plan «Red de encargos con luces»: D1 A arco ámbar del retrabajo, D2 A densidad = cantidad con
 * velocidad constante). Arriba, la franja «Ahora» con las colas vivas; debajo, el Historial filtrado por lo que se toque.
 *
 * Sólo dibuja lo que le pasa encargos.js: no llama a cockpit, no lanza procesos ni lee archivos. Lo único que guarda es
 * la preferencia ⏸ Luces en localStorage. Los ids de encargo, fase, cuenta y modelo los escriben los agentes: pasan por
 * delPanel() (la lista blanca de seguro() y la regla de nombres) y van como texto (textContent o <title>), nunca como HTML.
 * Sin estilos en línea: el SVG lleva atributos y clases, el color sale de encargos.css y lo único que se fija por CSSOM es
 * el latido del pulso. Usa el(), svg(), delPanel(), cuenta(), bonito(), ordenar(), filaHistorial(), CABEZAS_HISTORIAL,
 * CUENTAS_BARRA, ESFUERZOS y COLA_VALIDA de encargos.js, que se carga después: sólo se llaman al pintar.
 */
"use strict";
const redEncargos = (() => {
    // La misma regla que encargos/balance.py (RETRABAJO), en coincidencia completa sobre `fase` (prueba C1).
    const RETRABAJO = /^(fix\d*|rev([2-9]|\d{2,})|plan2|revplan2)$/;
    const TOPE_LUCES = 120;                  // máximo de luces a la vez, en cualquier modo
    const CUADRO_MS = 8;                     // si mover las luces de un cuadro tarda más, la densidad baja sola
    const VUELTA_MS = 2200;                  // lo que tarda una luz en cruzar una conexión: igual en todas (D2 A) y el período del pulso
    const RECIENTES = 10;                    // encargos con nodo propio; el resto va en «Otros»
    const MUESTRAS = 64;                     // puntos por curva, muestreados una vez
    const LUCES_GUARDADAS = "encargos-luces";
    // Etiquetas de modelo: el mapa y, para un id nuevo, la regla general de etiquetaModelo() (prueba C4).
    const MODELOS = { "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-4-5": "Haiku 4.5", "opus-5-5": "Opus 5.5", "sonnet-5-5": "Sonnet 5.5", "haiku-4-5": "Haiku 4.5", "gpt-5.6-terra": "Terra", "terra": "Terra", "gpt-reserve": "GPT Reserve" };
    const METRICAS = [["min", "Minutos"], ["usd", "USD"], ["tokens", "Tokens"], ["pct", "Puntos de % semanal"]];
    const PERIODOS = [["7", "7 días"], ["30", "30 días"], ["todo", "Todo"]];
    const MODOS = [["vivo", "En vivo"], ["ambiente", "Ambiente"]];
    const ROLES_RED = { autor: "autor", rev: "revisión", fix: "arreglo" };
    const BRILLO = { low: 0.45, medium: 0.65, high: 0.85, xhigh: 1 };
    const CAPAS = ["Cuenta", "Modelo · esfuerzo", "Naturaleza · rol", "Encargo", "Resultado"];
    const ANCHO_NODO = [136, 152, 204, 136, 168], ALTO_NODO = [36, 36, 24, 36, 36];
    const SEPARACION = 8, MARGEN_Y = 34, MARGEN_X = 104, ARCO = 64;
    const RESULTADOS = {
        "En curso": "una cola lo está corriendo ahora",
        "Pausa por falta de cuota": "alguna fase quedó sin cuota",
        "Retrabajo": "tuvo arreglos o revisiones desde la 2ª",
        "Verde a la primera": "la 1ª revisión dijo DESPLEGABLE",
        "Detenido o rechazado": "sin aprobación registrada: se detuvo, se rechazó o la revisión no dejó veredicto",
    };
    // El estado de la red. `reloj` queda para «Repetir la historia» (D3, ampliación prevista): con un instante, la red
    // se arma sólo con las fases que empezaron antes. Hoy siempre es null.
    const S = { d: null, alcance: { tipo: "todo", valor: "" }, escribirHash: null, metrica: "min", periodo: "todo", modo: "vivo", luces: true, reloj: null, foco: null, pagina: 0,
        raiz: null, seccion: null, envoltura: null, lienzo: null, firma: "", red: null, particulas: [], enVivo: false, escala: 1, raf: 0, visible: true, iniciada: false, observador: null };

    const num = v => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : 0);
    const textoId = v => ((typeof v === "string" || (typeof v === "number" && Number.isFinite(v))) && String(v).trim() ? String(v) : "");
    const valida = x => !!x && typeof x === "object" && !!textoId(x.encargo) && !!textoId(x.fase);
    const esRetrabajo = x => RETRABAJO.test(textoId(x.fase));
    const fecha = v => { const t = typeof v === "string" ? Date.parse(v) : NaN; return Number.isNaN(t) ? null : t; };
    const quieto = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
    const corto = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
    const es = (v, dec) => v.toLocaleString("es-CL", { maximumFractionDigits: dec });

    function etiquetaModelo(id) {
        const crudo = typeof id === "string" ? id.trim().toLowerCase() : "";
        if (!crudo) return "sin datos";
        if (Object.prototype.hasOwnProperty.call(MODELOS, crudo)) return MODELOS[crudo];
        const limpio = crudo.replace(/^(?:claude|anthropic|openai)-/, "").replace(/(\d+)-(\d+)/g, "$1.$2");
        const partes = limpio.split(/[-_\s]+/).filter(Boolean).map((p, i) => (/^(?:gpt|api|ia)$/.test(p) ? p.toUpperCase() : i === 0 ? p.charAt(0).toUpperCase() + p.slice(1) : p));
        return partes.length ? delPanel(partes.join(" ")) : "sin datos";
    }
    const etiquetaModeloFila = x => { const m = etiquetaModelo(x.modelo || x.modelo_real); return ESFUERZOS.includes(x.esfuerzo) ? `${m} · ${x.esfuerzo}` : m; };
    const rolDe = x => (Object.prototype.hasOwnProperty.call(ROLES_RED, x.rol) ? x.rol : (/^(autor|rev|fix)\d*$/.exec(textoId(x.fase)) || [])[1] || null);
    const etiquetaRol = x => { const r = rolDe(x); return `${typeof x.naturaleza === "string" && x.naturaleza ? delPanel(bonito(x.naturaleza)) : "sin naturaleza"} · ${r ? ROLES_RED[r] : delPanel(textoId(x.fase).replace(/\d+$/, "")) || "sin rol"}`; };
    const claseCuenta = id => (CUENTAS_BARRA.includes(id) ? `c-${id}` : "c-otra");
    function etiquetaCuenta(id) { const n = cuenta(id); return typeof n === "string" && n !== "sin datos" ? delPanel(n) : id ? delPanel(id) : "sin datos"; }

    function valor(x, m) {
        if (m === "min") return num(x.min);
        const t = x.tokens && typeof x.tokens === "object" ? x.tokens : {};
        if (m === "usd") return num(t.usd);
        if (m === "pct") return Array.isArray(x.pct_sem) && x.pct_sem.length === 2 ? Math.max(0, num(x.pct_sem[1]) - num(x.pct_sem[0])) : 0;
        return t.total != null ? num(t.total) : ["entrada", "salida", "cache_lectura", "cache_escritura"].reduce((n, k) => n + num(t[k]), 0);
    }
    function formato(v, m) {
        if (m === "usd") return `US$ ${es(v, 2)}`;
        if (m === "tokens") return v >= 1e6 ? `${es(v / 1e6, 1)} M tok` : `${es(Math.round(v / 1000), 0)} k tok`;
        if (m === "pct") return `${es(v, 1)} pp`;
        return `${es(v, v >= 100 ? 0 : 1)} min`;
    }

    // Las fases que entran: válidas (encargo y fase, como en balance.py), del período elegido y, si hay reloj, anteriores a él.
    function filasDelPeriodo() {
        const h = Array.isArray(S.d && S.d.h) ? S.d.h.filter(valida) : [];
        const desde = S.periodo === "todo" ? null : Date.now() - Number(S.periodo) * 86400000;
        const base = h.filter(x => { const t = fecha(x.inicio); return (desde == null || (t != null && t >= desde)) && (S.reloj == null || (t != null && t <= S.reloj)); });
        const a = S.alcance || { tipo: "todo", valor: "" };
        const activas = new Set(colasActivas().map(v => String(v.etapa)));
        if (a.tipo === "encargo") return base.filter(x => encargoCoincide(x.encargo, a.valor));
        if (a.tipo === "naturaleza") return base.filter(x => String(x.naturaleza || "") === String(a.valor));
        if (a.tipo === "cuenta") return base.filter(x => String(x.cuenta || "") === String(a.valor));
        if (a.tipo === "curso") return base.filter(x => activas.has(String(x.encargo)));
        return base;
    }
    // `e=84` es el número de encargo; permite agrupar sus etapas 84a/84b, pero no acepta
    // prefijos ambiguos como `8`.
    function encargoCoincide(id, buscado) {
        const a = String(id), b = String(buscado || "");
        return a === b || (/^\d+$/.test(b) && new RegExp(`^${b}[a-z]$`, "i").test(a));
    }
    function idCuenta(nombre) { const n = S.d && S.d.nombres ? Object.entries(S.d.nombres).find(([, v]) => v === nombre) : null; return n ? n[0] : null; }
    // Las colas vivas: un vivo/<cola>.json con su sesión de tmux abierta, el mismo «viva» del pulso y de «Ahora».
    function colasVivas() {
        const d = S.d; if (!d || !Array.isArray(d.vivos) || !Array.isArray(d.sesiones)) return [];
        return d.vivos.filter(v => v && typeof v === "object" && d.sesiones.includes(v.nombre));
    }
    // `cola-run.py` considera activos los estados que necesitan una sesión; las pausas y consultas son
    // activas aunque la sesión ya haya terminado, porque quedan esperando una decisión del usuario.
    const ESTADOS_CON_SESION = ["partiendo", "esperando autorización", "esperando", "línea base de pruebas", "corriendo",
        "esperando_cuota", "pruebas finales", "desplegando"];
    const ESTADOS_ESTACIONADOS = ["pausada", "pausada_por_usuario", "retenida_por_despacho", "en_consulta"];
    function colaActiva(v, sesiones) {
        if (!v || typeof v !== "object" || !textoId(v.nombre) || !textoId(v.etapa)) return false;
        const estado = String(v.estado);
        if (ESTADOS_ESTACIONADOS.includes(estado)) return true;
        return ESTADOS_CON_SESION.includes(estado) && Array.isArray(sesiones) && sesiones.includes(v.nombre);
    }
    function colasActivas() {
        const d = S.d; if (!d || !Array.isArray(d.vivos)) return [];
        return d.vivos.filter(v => colaActiva(v, d.sesiones));
    }
    // Regla pura del pipeline (C2): sólo la etapa elegida entra en los tres tramos. Una etapa que
    // aparece en `etapas` pero ya terminó no hereda la fase viva de otra etapa de la misma cola.
    // Hecho = historial de esa etapa; corriendo = vivo cuya etapa es esa; pronosticado = fases_restantes
    // válidas de esa etapa, excepto la fase que ya está corriendo. Sin fases restantes no hay pronóstico.
    function fasesTramos(dato, encargo) {
        const id = String(encargo || "");
        const vivos = Array.isArray(dato && dato.vivos) ? dato.vivos : [];
        const etapas = new Set([id, ...(Array.isArray(dato && dato.h) ? dato.h : []).map(x => textoId(x && x.encargo)).filter(x => encargoCoincide(x, id)), ...vivos.map(x => textoId(x && x.etapa)).filter(x => encargoCoincide(x, id))]);
        const vivo = vivos.find(v => colaActiva(v, dato && dato.sesiones) && textoId(v.fase) && etapas.has(String(v.etapa)));
        const hechas = (Array.isArray(dato && dato.h) ? dato.h : []).filter(x => valida(x) && etapas.has(String(x.encargo))).map(x => ({ ...x, tramo: "hecho" }));
        const corriendo = vivo ? { etapa: String(vivo.etapa), fase: textoId(vivo.fase), cuenta: textoId(vivo.cuenta), modelo: textoId(vivo.modelo), min: num(vivo.pronostico_fase_min), tramo: "corriendo", vivo: vivo.estado === "corriendo" } : null;
        const validaPronostico = x => x && typeof x === "object" && textoId(x.etapa) && textoId(x.fase) && textoId(x.cuenta) &&
            textoId(x.modelo) && typeof x.min === "number" && Number.isFinite(x.min) && x.min >= 0 && typeof x.prob === "number" && Number.isFinite(x.prob) && x.prob >= 0 && x.prob <= 1;
        const pronosticadas = vivo && Array.isArray(vivo.fases_restantes) ? vivo.fases_restantes.filter(validaPronostico)
            .filter(x => etapas.has(String(x.etapa)) && !(String(x.etapa) === String(vivo.etapa) && String(x.fase) === String(vivo.fase))).map(x => ({ ...x, tramo: "pronosticado" })) : [];
        return { hechas, corriendo, pronosticadas, publica: !!(vivo && Array.isArray(vivo.fases_restantes)) };
    }
    // La fase en curso de cada cola viva, como una fila más de la red (sin minutos): así su camino existe aunque el
    // encargo todavía no tenga filas en el historial. No entra en los KPI ni en el Historial.
    function filasVivas(reales) {
        const a = S.alcance || { tipo: "todo" };
        return colasActivas().filter(v => textoId(v.etapa) && textoId(v.fase) &&
            (a.tipo !== "encargo" || encargoCoincide(v.etapa, a.valor))).map(v => {
            const previa = reales.filter(x => String(x.encargo) === String(v.etapa)).at(-1) || {};
            const [modelo, esfuerzo] = typeof v.modelo === "string" ? v.modelo.trim().split(/\s+/) : [];
            return { encargo: String(v.etapa), fase: String(v.fase), cuenta: idCuenta(v.cuenta) || v.cuenta, modelo, esfuerzo, naturaleza: previa.naturaleza,
                inicio: v.inicio_fase, min: 0, _activo: String(v.nombre), _vivo: v.estado === "corriendo" ? String(v.nombre) : "" };
        });
    }
    function resultado(filas, vivo) {
        if (vivo) return "En curso";
        if (filas.some(x => x.sin_cuota === true)) return "Pausa por falta de cuota";
        if (filas.some(esRetrabajo)) return "Retrabajo";
        const rev = filas.filter(x => x.fase === "rev1" && x.veredicto);
        return rev.length && String(rev.at(-1).veredicto).toUpperCase() === "DESPLEGABLE" ? "Verde a la primera" : "Detenido o rechazado";
    }

    function construir() {
        const reales = filasDelPeriodo(), vivas = filasVivas(reales), filas = [...reales, ...vivas];
        const porEncargo = new Map();
        filas.forEach(x => { const k = String(x.encargo); if (!porEncargo.has(k)) porEncargo.set(k, []); porEncargo.get(k).push(x); });
        const ultimo = fs => Math.max(0, ...fs.map(x => fecha(x.inicio) || 0));
        const orden = [...porEncargo].sort((a, b) => ultimo(b[1]) - ultimo(a[1])).map(([k]) => k);
        const recientes = new Set(orden.slice(0, RECIENTES)), otros = orden.length - recientes.size;
        const res = new Map([...porEncargo].map(([k, fs]) => [k, resultado(fs, fs.some(x => x._activo))]));
        const capas = CAPAS.map(() => new Map()), enlaces = new Map();
        const nodo = (c, clave, etiqueta, clase) => {
            if (!capas[c].has(clave)) capas[c].set(clave, { id: `${c}:${clave}`, capa: c, etiqueta, clase, total: 0, filas: new Set(), vivo: false });
            return capas[c].get(clave);
        };
        filas.forEach((x, i) => {
            const cu = textoId(x.cuenta), mod = etiquetaModeloFila(x), rol = etiquetaRol(x), enc = String(x.encargo);
            const ns = [nodo(0, cu, etiquetaCuenta(cu), claseCuenta(cu)), nodo(1, mod, mod), nodo(2, rol, rol),
                recientes.has(enc) ? nodo(3, enc, `Encargo ${delPanel(enc)}`) : nodo(3, " otros", `Otros (${otros} encargos)`),
                nodo(4, res.get(enc), res.get(enc), res.get(enc) === "Retrabajo" ? "retrabajo" : "")];
            const v = valor(x, S.metrica);
            ns.forEach(n => { n.total += v; n.filas.add(i); if (x._vivo) n.vivo = true; });
            for (let c = 0; c < 4; c++) {
                const k = `${ns[c].id}>${ns[c + 1].id}`;
                if (!enlaces.has(k)) enlaces.set(k, { id: k, a: ns[c], b: ns[c + 1], valor: 0, filas: new Set(), clase: claseCuenta(cu), brillos: [] });
                const e = enlaces.get(k); e.valor += v; e.filas.add(i); e.brillos.push(Object.prototype.hasOwnProperty.call(BRILLO, x.esfuerzo) ? BRILLO[x.esfuerzo] : 0.6);
            }
        });
        // D1 A: el retrabajo vuelve desde «Retrabajo» por un arco ámbar hasta el rol que más retrabajo carga.
        const ret = filas.map((x, i) => [x, i]).filter(([x]) => !x._vivo && esRetrabajo(x));
        let vuelta = null;
        if (ret.length && capas[4].has("Retrabajo")) {
            const porRol = new Map(); ret.forEach(([x]) => porRol.set(etiquetaRol(x), (porRol.get(etiquetaRol(x)) || 0) + valor(x, S.metrica) + 1e-9));
            const destino = capas[2].get([...porRol].sort((a, b) => b[1] - a[1])[0][0]);
            vuelta = { id: "vuelta", a: capas[4].get("Retrabajo"), b: destino, valor: ret.reduce((n, [x]) => n + valor(x, S.metrica), 0), filas: new Set(ret.map(([, i]) => i)), clase: "retrabajo", brillos: [1] };
        }
        return { filas, reales, capas, enlaces: [...enlaces.values()], vuelta };
    }

    // La altura sale de la capa más poblada: cada nodo con su alto y al menos SEPARACION px con el vecino (ronda 3, opción c).
    function ubicar(red, ancho) {
        const util = Math.max(...red.capas.map((m, c) => m.size * ALTO_NODO[c] + Math.max(0, m.size - 1) * SEPARACION));
        const alto = MARGEN_Y * 2 + Math.max(util, 300) + ARCO, paso = (ancho - MARGEN_X * 2) / 4;
        red.capas.forEach((m, c) => {
            const ns = [...m.values()].sort((a, b) => b.total - a.total || a.etiqueta.localeCompare(b.etiqueta, "es", { numeric: true }));
            const libre = alto - ARCO - MARGEN_Y * 2 - ALTO_NODO[c], salto = ns.length > 1 ? libre / (ns.length - 1) : 0;
            ns.forEach((n, i) => { n.w = ANCHO_NODO[c]; n.h = ALTO_NODO[c]; n.x = MARGEN_X + c * paso; n.y = MARGEN_Y + ALTO_NODO[c] / 2 + (ns.length > 1 ? i * salto : libre / 2); });
        });
        return alto;
    }
    // Una curva cúbica: los puntos de control para dibujarla y MUESTRAS + 1 puntos equidistantes para mover las luces.
    function curva(p0, p1, p2, p3) {
        const en = t => { const u = 1 - t; return [u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0], u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]]; };
        const finos = Array.from({ length: MUESTRAS * 4 + 1 }, (_, i) => en(i / (MUESTRAS * 4))), largo = [0];
        for (let i = 1; i < finos.length; i++) largo.push(largo[i - 1] + Math.hypot(finos[i][0] - finos[i - 1][0], finos[i][1] - finos[i - 1][1]));
        const muestras = []; let j = 0;
        for (let i = 0; i <= MUESTRAS; i++) { const meta = largo.at(-1) * i / MUESTRAS; while (j < largo.length - 2 && largo[j + 1] < meta) j++; muestras.push(finos[j + 1] && largo[j + 1] - largo[j] > 0 ? [finos[j][0] + (finos[j + 1][0] - finos[j][0]) * (meta - largo[j]) / (largo[j + 1] - largo[j]), finos[j][1] + (finos[j + 1][1] - finos[j][1]) * (meta - largo[j]) / (largo[j + 1] - largo[j])] : finos[j]); }
        return { d: `M${p0} C${p1} ${p2} ${p3}`, muestras };
    }
    function trazo(e, alto) {
        if (e.id === "vuelta") { const a = [e.a.x - e.a.w / 2 + 18, e.a.y + e.a.h / 2], b = [e.b.x, e.b.y + e.b.h / 2]; return curva(a, [a[0] - 30, alto - 30], [b[0] + 60, alto - 30], b); }
        const x1 = e.a.x + e.a.w / 2, x2 = e.b.x - e.b.w / 2, c = (x2 - x1) * 0.5;
        return curva([x1, e.a.y], [x1 + c, e.a.y], [x2 - c, e.b.y], [x2, e.b.y]);
    }

    // El foco es un conjunto de filas: las de un nodo, las de una conexión o la fase en curso de una cola («Ahora»).
    function resolverFoco(red) {
        const f = S.foco; if (!f) return null;
        if (f.tipo === "cola") { const i = red.filas.findIndex(x => x._vivo === f.cola); return i < 0 ? null : { ...f, filas: new Set([i]) }; }
        const x = f.tipo === "nodo" ? red.capas.flatMap(m => [...m.values()]).find(n => n.id === f.id) : [...red.enlaces, red.vuelta].find(e => e && e.id === f.id);
        return x ? { ...f, filas: x.filas } : null;
    }
    const cruza = (a, b) => { for (const x of a) if (b.has(x)) return true; return false; };
    function vivasDe(red) { return new Set(red.filas.map((x, i) => (x._vivo ? i : -1)).filter(i => i >= 0)); }

    function dibujar() {
        const ancho = Math.max(1160, Math.floor(S.envoltura.clientWidth || 0)), red = construir(), alto = ubicar(red, ancho);
        S.red = red;
        const lienzo = svg("svg", { class: "red", viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto, role: "group", "aria-label": "Red de los encargos: cuenta, modelo y esfuerzo, naturaleza y rol, encargo y resultado" });
        const defs = svg("defs", {}), flecha = svg("marker", { id: "red-flecha", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
        flecha.append(svg("path", { d: "M0,0 L10,5 L0,10 z", class: "red-flecha" })); defs.append(flecha);
        const capaEnlaces = svg("g", {}), capaLuces = svg("g", { class: "red-luces", "aria-hidden": "true" }), capaNodos = svg("g", {}), cabezas = svg("g", { "aria-hidden": "true" });
        lienzo.append(defs, cabezas, capaEnlaces, capaLuces, capaNodos);
        red.capas.forEach((m, c) => { const n = [...m.values()][0], t = svg("text", { x: n ? n.x : MARGEN_X, y: 16, class: "red-capa", "text-anchor": "middle" }); t.textContent = CAPAS[c]; cabezas.append(t); });
        const maximo = Math.max(1e-9, ...red.enlaces.map(e => e.valor)), flechas = quieto() || !S.luces;
        for (const e of [...red.enlaces].sort((a, b) => b.valor - a.valor).concat(red.vuelta ? [red.vuelta] : [])) {
            const t = trazo(e, alto); e.muestras = t.muestras;
            const brillo = e.brillos.reduce((n, x) => n + x, 0) / e.brillos.length;
            e.trazo = svg("path", { d: t.d, class: `red-enlace ${e.clase}`, "stroke-width": e.id === "vuelta" ? 2 : (1.2 + 6 * Math.sqrt(e.valor / maximo)).toFixed(2), "stroke-opacity": e.id === "vuelta" ? 0.8 : (0.18 + 0.4 * brillo).toFixed(2) });
            if (flechas) e.trazo.setAttribute("marker-end", "url(#red-flecha)");
            const toque = svg("path", { d: t.d, class: "red-toque", tabindex: 0, role: "button" }), titulo = svg("title", {});
            titulo.textContent = e.id === "vuelta" ? `Retrabajo: vuelve a ${e.b.etiqueta} · ${e.filas.size} fases · ${formato(e.valor, S.metrica)} · tocar para filtrar el Historial`
                : `${e.a.etiqueta} → ${e.b.etiqueta} · ${e.filas.size} fases · ${formato(e.valor, S.metrica)} · tocar para filtrar el Historial`;
            toque.setAttribute("aria-label", titulo.textContent); toque.append(titulo);
            const elegir = ev => { ev.stopPropagation(); enfocar({ tipo: "enlace", id: e.id, titulo: e.id === "vuelta" ? `Retrabajo → ${e.b.etiqueta}` : `${e.a.etiqueta} → ${e.b.etiqueta}` }); };
            toque.addEventListener("click", elegir); toque.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); elegir(ev); } });
            capaEnlaces.append(e.trazo, toque);
        }
        if (red.vuelta) {
            const tot = red.reales.reduce((n, x) => n + num(x.min), 0), re = red.reales.filter(esRetrabajo).reduce((n, x) => n + num(x.min), 0);
            const t = svg("text", { x: (red.vuelta.a.x + red.vuelta.b.x) / 2, y: alto - 6, class: "red-vuelta-texto", "text-anchor": "middle" });
            t.textContent = `↺ ${tot > 0 ? Math.round(100 * re / tot) : "–"} % de los minutos vuelve a arreglo y revisión`; capaEnlaces.append(t);
        }
        for (const n of red.capas.flatMap(m => [...m.values()])) {
            const g = svg("g", { class: `red-nodo ${n.clase || ""}${n.capa === 2 ? " compacto" : ""}${n.vivo ? " vivo" : ""}`, transform: `translate(${(n.x - n.w / 2).toFixed(1)} ${(n.y - n.h / 2).toFixed(1)})`, tabindex: 0, role: "button" });
            const detalle = `${n.filas.size} fases · ${formato(n.total, S.metrica)}${n.capa === 4 ? ` · ${RESULTADOS[n.etiqueta] || ""}` : ""}`, titulo = svg("title", {});
            titulo.textContent = `${n.etiqueta} · ${detalle}`; g.setAttribute("aria-label", titulo.textContent);
            g.append(titulo, svg("rect", { width: n.w, height: n.h, rx: 7 }));
            // Recortes por ancho: ~6,4 px por letra en el texto principal y ~5,6 px en el secundario (el texto entero va en <title>).
            const cifra = formato(n.total, S.metrica), t = svg("text", { x: 8, y: n.capa === 2 ? 16 : 15 });
            t.textContent = corto(n.etiqueta, Math.floor((n.w - 16 - (n.capa === 2 ? cifra.length * 5.6 + 6 : 0)) / 6.4)); g.append(t);
            const s = n.capa === 2 ? svg("text", { x: n.w - 8, y: 16, class: "red-sub", "text-anchor": "end" }) : svg("text", { x: 8, y: n.h - 7, class: "red-sub" });
            s.textContent = n.capa === 2 ? cifra : corto(`${n.filas.size} fases · ${cifra}`, Math.floor((n.w - 16) / 5.6)); g.append(s);
            const elegir = ev => { ev.stopPropagation(); enfocar({ tipo: "nodo", id: n.id, titulo: n.etiqueta }); };
            g.addEventListener("click", elegir); g.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); elegir(ev); } });
            n.g = g; capaNodos.append(g);
        }
        lienzo.addEventListener("click", ev => { if (ev.target === lienzo && S.foco) enfocar(null); });
        S.lienzo = lienzo; S.capaLuces = capaLuces; S.envoltura.replaceChildren(lienzo);
        aplicarFoco();
    }

    // Qué conexiones llevan luces: en Foco, las de sus filas; en vivo, las de la fase en curso; si no, todas (Ambiente).
    function enlacesConLuces() {
        const red = S.red; if (!red) return { lista: [], vivo: false };
        const foco = resolverFoco(red), vivas = vivasDe(red), todos = red.enlaces.concat(red.vuelta ? [red.vuelta] : []);
        if (foco) return { lista: todos.filter(e => cruza(e.filas, foco.filas)).map(e => ({ e, n: Math.max(1, densidad(e, 2)) })), vivo: false };
        if (S.modo === "vivo" && vivas.size) return { lista: red.enlaces.filter(e => cruza(e.filas, vivas)).map(e => ({ e, n: 2 })), vivo: true };
        return { lista: todos.map(e => ({ e, n: densidad(e, 1) })), vivo: false };
    }
    function densidad(e, por) { const m = Math.max(1e-9, ...S.red.enlaces.map(x => x.valor)); return e.valor > 0 ? Math.min(6, Math.round((1 + 4 * Math.sqrt(Math.min(1, e.valor / m))) * por)) : 0; }
    function aplicarFoco() {
        const red = S.red; if (!red) return;
        const foco = resolverFoco(red); if (S.foco && !foco) S.foco = null;
        const vivas = vivasDe(red), resalta = foco ? foco.filas : S.modo === "vivo" && vivas.size ? vivas : null;
        const apaga = (nodo, no) => { nodo.classList.toggle("apagado", !!foco && no); nodo.classList.toggle("suave", !foco && no); };
        for (const n of red.capas.flatMap(m => [...m.values()])) { apaga(n.g, !!resalta && !cruza(n.filas, resalta)); n.g.classList.toggle("elegido", !!foco && foco.tipo === "nodo" && foco.id === n.id); }
        for (const e of red.enlaces.concat(red.vuelta ? [red.vuelta] : [])) { const si = !resalta || cruza(e.filas, resalta); apaga(e.trazo, !si); e.trazo.classList.toggle("activo", !!resalta && si); }
        armarLuces();
    }
    function armarLuces() {
        S.particulas = [];
        const id = S.alcance && S.alcance.tipo === "encargo" ? S.alcance.valor : "";
        const tramos = id ? fasesTramos(S.d, id) : null;
        S.lucesPipeline = tramos ? Math.min(24, tramos.hechas.length + (tramos.corriendo ? 1 : 0) + tramos.pronosticadas.length) : 0;
        if (!S.capaLuces) return;
        S.capaLuces.replaceChildren();
        if (!S.luces || quieto()) { soltarPulso(); return; }
        const { lista, vivo } = enlacesConLuces(), tope = Math.max(0, Math.floor(TOPE_LUCES * S.escala) - (S.lucesPipeline || 0));
        S.enVivo = vivo;
        const candidatas = [];
        lista.sort((a, b) => b.e.valor - a.e.valor).forEach(({ e, n }, k) => { for (let i = 0; i < n; i++) candidatas.push({ e, fase: vivo ? i / n : (i / n + (k * 0.137) % 1) % 1 }); });
        for (const c of candidatas.slice(0, tope)) {
            const halo = svg("circle", { r: 5, class: `red-halo ${c.e.clase}` }), luz = svg("circle", { r: 2.3, class: `red-luz ${c.e.clase}` });
            S.capaLuces.append(halo, luz); S.particulas.push({ ...c, halo, luz });
        }
        seguir();
    }
    const animable = () => S.luces && S.visible && !document.hidden && !quieto() && S.particulas.length > 0 && !!S.lienzo && S.lienzo.isConnected;
    function seguir() { if (!S.raf && animable()) S.raf = requestAnimationFrame(cuadro); if (!animable()) soltarPulso(); }
    function punto(ms, t) { const p = t * MUESTRAS, i = Math.min(MUESTRAS - 1, Math.floor(p)), f = p - i; return [ms[i][0] + (ms[i + 1][0] - ms[i][0]) * f, ms[i][1] + (ms[i + 1][1] - ms[i][1]) * f]; }
    function cuadro(ahora) {
        S.raf = 0;
        if (!animable()) { soltarPulso(); return; }
        const t0 = performance.now(), base = (ahora % VUELTA_MS) / VUELTA_MS;
        for (const p of S.particulas) { const [x, y] = punto(p.e.muestras, (p.fase + base) % 1); p.halo.setAttribute("cx", x.toFixed(1)); p.halo.setAttribute("cy", y.toFixed(1)); p.luz.setAttribute("cx", x.toFixed(1)); p.luz.setAttribute("cy", y.toFixed(1)); }
        // El pulso de la barra late cuando las luces de la fase en curso llegan a un nodo (dos por vuelta).
        const pulso = document.getElementById("pulso");
        if (pulso) { pulso.classList.toggle("sincro", !!S.enVivo); if (S.enVivo) pulso.style.setProperty("--latido", Math.max(0, 1 - ((base * 2) % 1) / 0.35).toFixed(2)); }
        if (performance.now() - t0 > CUADRO_MS && S.escala > 0.2) {
            S.escala *= 0.75;
            const quedan = Math.max(4, Math.floor(S.particulas.length * 0.75));
            S.particulas.splice(quedan).forEach(p => { p.halo.remove(); p.luz.remove(); });
        }
        S.raf = requestAnimationFrame(cuadro);
    }
    function soltarPulso() { const p = document.getElementById("pulso"); if (p) { p.classList.remove("sincro"); p.style.removeProperty("--latido"); } }

    function enfocar(f) {
        S.foco = f && S.foco && S.foco.tipo === f.tipo && S.foco.id === f.id && S.foco.cola === f.cola ? null : f;
        S.pagina = 0; aplicarFoco(); pintarFranja(); pintarHistorial();
        if (S.foco && S.foco.tipo !== "cola") S.raiz.querySelector(".red-historial")?.scrollIntoView({ block: "nearest", behavior: quieto() ? "auto" : "smooth" });
    }

    function pintarFranja() {
        const vivas = colasActivas(), corriendo = new Set((S.red ? S.red.filas : []).filter(x => x._activo).map(x => x._activo));
        const pastillas = vivas.map(v => {
            const r = v.restante_min && typeof v.restante_min === "object" ? v.restante_min.esperado : null;
            const fase = `${delPanel(v.etapa)} · ${delPanel(v.fase)} · ${delPanel(String(v.estado ?? "").replace(/_/g, " "))}`;
            const texto = ` · ${fase}${typeof r === "number" && Number.isFinite(r) && r >= 0 ? ` · ~${es(r, 0)} min` : ""}`;
            const activa = !!S.foco && S.foco.tipo === "cola" && S.foco.cola === v.nombre;
            // 95: la cola va con mencionCola(); su tarjeta es el tooltip del botón (sin `title`, que pondría un segundo tooltip encima).
            return el("button", { class: `red-pastilla${activa ? " activa" : ""}`, "aria-pressed": String(activa),
                onclick: () => elegirEncargo(v.etapa, v.nombre) }, el("i", { class: "red-punto", "aria-hidden": "true" }), mencionCola(v.nombre), texto);
        });
        S.franja.replaceChildren(el("strong", {}, "Ahora"), ...(pastillas.length ? pastillas : [el("span", { class: "tenue" }, "sin colas en curso")]),
            el("span", { class: "red-franja-nota tenue" }, pastillas.length ? "Toca una cola para ver su camino." : "La red muestra el pasado."));
        activarGlosario(S.franja);
    }
    function etiquetaFase(fase) {
        const f = textoId(fase); if (/^autor$/i.test(f)) return "Author";
        const r = /^rev(\d*)$/i.exec(f); if (r) return `Review ${r[1] || ""}`.trim();
        const a = /^fix(\d*)$/i.exec(f); return a ? `Fix ${a[1] || ""}`.trim() : delPanel(f);
    }
    function pintarPipeline() {
        const a = S.alcance || {}, id = a.tipo === "encargo" ? a.valor : null;
        if (!id) { S.lucesPipeline = 0; S.pipeline.replaceChildren(); return; }
        const p = fasesTramos(S.d, id), todos = [...p.hechas, ...(p.corriendo ? [p.corriendo] : []), ...p.pronosticadas];
        const paso = (x, i) => el("article", { class: `pipeline-paso ${x.tramo}${x.tramo === "corriendo" && x.vivo ? " vivo" : ""}${x.tramo === "pronosticado" ? ` peso-${Math.max(1, Math.min(6, Math.round(num(x.min) * x.prob / 5) + 1))}` : ""}` }, ...(i < 24 ? [el("i", { class: "pipeline-luz", "aria-hidden": "true" })] : []),
            el("strong", {}, etiquetaFase(x.fase)), el("span", {}, etiquetaCuenta(x.cuenta)),
            el("small", {}, x.tramo === "hecho" ? `${formato(num(x.min), "min")} reales` : x.tramo === "corriendo" ? `${formato(num(x.min), "min")} · en curso` : `${formato(num(x.min), "min")} · ${Math.round(x.prob * 100)} %${x.debil === true ? " · débil" : ""}`));
        const nota = !p.publica ? "Esta cola no publica fases restantes; no se dibuja pronóstico." : !p.pronosticadas.length ? "Esta cola no tiene fases futuras válidas publicadas; no se dibuja pronóstico." : "Hecho: minutos reales. Corriendo: fase viva. Pronosticado: minutos × probabilidad.";
        S.pipeline.replaceChildren(el("section", { class: "tarjeta pipeline-tarjeta" }, el("div", { class: "pipeline-cabeza" }, el("h2", {}, `Pipeline · encargo ${delPanel(id)}`), el("span", { "data-term": "Pipeline" }, "Pipeline"), el("span", { class: "tenue", "data-term": "Forecast" }, "Forecast")),
            el("div", { class: "pipeline", "aria-label": `Pipeline del encargo ${delPanel(id)}` }, ...(todos.length ? todos.map(paso) : [el("p", { class: "tenue" }, "Este encargo todavía no tiene fases publicadas.")])), el("p", { class: "tenue" }, nota)));
        activarGlosario(S.pipeline);
    }
    function elegirEncargo(id, cola = "") {
        if (!textoId(id)) return; const h = S.escribirHash && S.escribirHash("encargo", String(id));
        S.foco = cola ? { tipo: "cola", cola: String(cola), titulo: `Encargo ${delPanel(id)}` } : null;
        if (h && location.hash !== h) location.hash = h;
        else { S.alcance = { tipo: "encargo", valor: String(id) }; rehacer(); }
    }
    function pintarCabeza() {
        const reales = S.red ? S.red.reales : [], tot = reales.reduce((n, x) => n + num(x.min), 0), re = reales.filter(esRetrabajo).reduce((n, x) => n + num(x.min), 0);
        const kpi = (v, t, term) => el("span", {}, el("b", {}, v), " ", el("span", { "data-term": term }, t));
        S.kpis.replaceChildren(kpi(es(reales.length, 0), "Steps", "Steps"), kpi(es(new Set(reales.map(x => String(x.encargo))).size, 0), "Tasks", "Task"), kpi(es(Math.round(tot), 0), "min", "Minutes"),
            kpi(`${tot > 0 ? Math.round(100 * re / tot) : "–"} %`, "Rework rate", "Rework rate"));
        activarGlosario(S.kpis);
        const notas = [];
        if (S.metrica === "tokens") notas.push("Los tokens de Claude y de Codex se cuentan distinto: compararlos entre proveedores es orientativo.");
        if (S.metrica === "usd") notas.push("Sólo Claude informa USD: las fases de Codex suman 0.");
        if (S.metrica === "pct") notas.push("Puntos del % semanal de su cuenta (después − antes); si la medición no cambió, suma 0.");
        if (S.modo === "vivo" && !(S.red && S.red.filas.some(x => x._vivo))) notas.push("En vivo: sin colas en curso, así que las luces muestran todo el flujo (Ambiente).");
        if (quieto()) notas.push("Movimiento reducido: las conexiones llevan flechas fijas.");
        S.nota.replaceChildren(...notas.map(t => el("span", {}, t))); S.nota.hidden = !notas.length;
        S.modos.forEach(b => { const si = b.dataset.modo === S.modo; b.classList.toggle("activa", si); b.setAttribute("aria-pressed", String(si)); });
        S.raiz.classList.toggle("sin-luces", !S.luces || quieto()); S.boton.textContent = S.luces ? "⏸ Luces" : "▶ Luces"; S.boton.setAttribute("aria-pressed", String(!S.luces));
        S.boton.title = S.luces ? "Apagar las luces (se recuerda)" : "Encender las luces (se recuerda)";
    }
    function pintarAlcance() {
        const a = S.alcance || { tipo: "todo", valor: "" }, o = opcionesAlcance();
        const tipos = [["todo", "Todo"], ["curso", `En curso (${colasActivas().length})`], ["encargo", "Encargo…"], ["naturaleza", "Naturaleza"], ["cuenta", "Cuenta"]];
        const selector = el("select", { "aria-label": "Scope" }, tipos.map(([v, t]) => el("option", { value: v }, t))); selector.value = a.tipo;
        selector.addEventListener("change", () => cambiarAlcance(selector.value, selector.value === "todo" || selector.value === "curso" ? "" : (selector.value === "encargo" ? o.ids[0] || "" : selector.value === "naturaleza" ? o.naturales[0] || "" : o.cuentas[0] || "")));
        const controles = [el("label", { class: "red-control" }, el("span", { "data-term": "Scope" }, "Scope"), " ", selector)];
        if (a.tipo === "encargo") { const busca = el("input", { type: "search", list: "red-encargos", value: a.valor, placeholder: "Número o título", "aria-label": "Buscar encargo" }), lista = el("datalist", { id: "red-encargos" }, o.ids.map(x => el("option", { value: x }, `Encargo ${x} · ${resumenEtapa(etapaDe(x))}`)));
            busca.addEventListener("change", () => { const escrito = busca.value.trim().toLowerCase(), id = o.ids.find(x => escrito === x.toLowerCase() || `encargo ${x} · ${resumenEtapa(etapaDe(x))}`.toLowerCase().includes(escrito)); cambiarAlcance("encargo", id || escrito); }); controles.push(el("label", { class: "red-control" }, "Encargo ", busca), lista); }
        if (a.tipo === "naturaleza") { const s = el("select", { "aria-label": "Naturaleza" }, o.naturales.map(x => el("option", { value: x }, delPanel(x)))); s.value = a.valor; s.addEventListener("change", () => cambiarAlcance("naturaleza", s.value)); controles.push(el("label", { class: "red-control" }, "Naturaleza ", s)); }
        if (a.tipo === "cuenta") { const s = el("select", { "aria-label": "Cuenta" }, o.cuentas.map(x => el("option", { value: x }, etiquetaCuenta(x)))); s.value = a.valor; s.addEventListener("change", () => cambiarAlcance("cuenta", s.value)); controles.push(el("label", { class: "red-control" }, "Cuenta ", s)); }
        S.alcanceCaja.replaceChildren(...controles); activarGlosario(S.alcanceCaja);
    }
    function pintarHistorial() {
        const red = S.red, foco = red ? resolverFoco(red) : null;
        // Con una cola de «Ahora», el Historial muestra las fases ya terminadas de su encargo (la de ahora entra al terminar).
        const deCola = foco && foco.tipo === "cola" ? String(red.filas[[...foco.filas][0]].encargo) : null;
        const filas = ordenar(red ? red.filas.filter((x, i) => !x._vivo && (!foco || (deCola != null ? String(x.encargo) === deCola : foco.filas.has(i)))) : [], orden.clave, orden.desc);
        const POR = 50, paginas = Math.max(1, Math.ceil(filas.length / POR)); S.pagina = Math.min(S.pagina, paginas - 1);
        const desde = S.pagina * POR, trozo = filas.slice(desde, desde + POR);
        const titulo = el("div", { class: "red-historial-cabeza" }, el("h2", {}, "Historial"),
            foco ? el("span", { class: "chip dato red-filtro" }, `filtrado por ${foco.titulo}`, el("button", { class: "red-limpiar", title: "Quitar el filtro", "aria-label": "Quitar el filtro", onclick: () => enfocar(null) }, "✕"))
                : el("span", { class: "tenue" }, `${PERIODOS.find(p => p[0] === S.periodo)[1].toLowerCase()} · toca un nodo o una conexión para filtrar`));
        const pie = el("div", { class: "red-paginas" },
            el("button", { class: "mini", disabled: S.pagina === 0, onclick: () => { S.pagina--; pintarHistorial(); } }, "‹ Anteriores"),
            el("span", { class: "tenue" }, filas.length ? `${es(desde + 1, 0)}–${es(desde + trozo.length, 0)} de ${es(filas.length, 0)} fases` : "ninguna fase"),
            el("button", { class: "mini", disabled: S.pagina >= paginas - 1, onclick: () => { S.pagina++; pintarHistorial(); } }, "Siguientes ›"));
        S.historial.replaceChildren(titulo, filas.length ? el("div", { class: "red-tabla" }, el("table", {}, el("thead", {}, el("tr", {}, CABEZAS_HISTORIAL.map(t => cabeza(t, () => { S.pagina = 0; pintarHistorial(); })))), el("tbody", {}, trozo.map(filaHistorial))))
            : el("p", { class: "tenue" }, deCola != null ? "Este encargo todavía no tiene fases terminadas: la fase en curso entra al historial al terminar." : "sin datos"), pie); activarGlosario(S.historial);
    }

    function guardarLuces() { try { localStorage.setItem(LUCES_GUARDADAS, S.luces ? "si" : "no"); } catch (e) { /* sin storage: vale para esta pestaña */ } }
    function leerLuces() { try { return localStorage.getItem(LUCES_GUARDADAS) !== "no"; } catch (e) { return true; } }
    function selectorRed(etiqueta, opciones, actual, alCambiar) {
        const s = el("select", { "aria-label": etiqueta }, opciones.map(([v, t]) => el("option", { value: v }, t)));
        s.value = actual; s.addEventListener("change", () => alCambiar(s.value));
        return el("label", { class: "red-control" }, `${etiqueta} `, s);
    }
    function rehacer() { S.firma = ""; pintar(S.seccion, S.d, S.alcance, S.escribirHash); }
    function opcionesAlcance() {
        const hs = Array.isArray(S.d && S.d.h) ? S.d.h : [], vivos = colasActivas();
        const ids = new Set([...hs.map(x => textoId(x && x.encargo)), ...vivos.map(x => textoId(x.etapa)), ...(S.d && S.d.resumenes || []).flatMap(c => (c.etapas || []).map(e => textoId(e.id)))].filter(Boolean));
        const naturales = new Set(hs.map(x => textoId(x && x.naturaleza)).filter(Boolean)), cuentas = new Set(hs.map(x => textoId(x && x.cuenta)).filter(Boolean));
        return { ids: [...ids].sort((a, b) => a.localeCompare(b, "es", { numeric: true })), naturales: [...naturales].sort(), cuentas: [...cuentas].sort() };
    }
    function cambiarAlcance(tipo, valor) {
        const h = S.escribirHash && S.escribirHash(tipo, valor);
        S.foco = null;
        if (h && location.hash !== h) location.hash = h;
        else { S.alcance = { tipo, valor }; rehacer(); }
    }
    function armar(seccion) {
        S.seccion = seccion; S.luces = leerLuces();
        S.franja = el("div", { class: "red-franja", "aria-live": "polite" });
        S.alcanceCaja = el("div", { class: "red-alcance" });
        S.kpis = el("p", { class: "red-kpis" });
        S.modos = MODOS.map(([m, t]) => el("button", { class: "mini red-modo", "data-modo": m, onclick: () => { S.modo = m; S.foco = null; rehacer(); } }, t));
        S.boton = el("button", { class: "mini red-boton-luces", onclick: () => { S.luces = !S.luces; guardarLuces(); rehacer(); } });
        S.nota = el("p", { class: "red-nota tenue", hidden: true });
        S.envoltura = el("div", { class: "red-envoltura" });
        S.pipeline = el("div", { class: "red-pipeline" });
        S.historial = el("section", { class: "tarjeta red-historial" });
        S.raiz = el("div", { class: "red-portada" },
            el("section", { class: "tarjeta red-tarjeta" }, S.alcanceCaja, S.franja,
                el("div", { class: "red-cabeza" }, el("div", {}, el("h2", {}, "Flujo por fase"), S.kpis),
                    el("div", { class: "red-controles" },
                        selectorRed("Métrica", METRICAS, S.metrica, v => { S.metrica = v; rehacer(); }),
                        selectorRed("Período", PERIODOS, S.periodo, v => { S.periodo = v; S.pagina = 0; rehacer(); }),
                        el("span", { class: "red-modos", role: "group", "aria-label": "Modo de las luces" }, S.modos), S.boton)),
                S.nota, S.pipeline, S.envoltura,
                el("p", { class: "tenue red-ayuda" }, "Toca un nodo para el modo Foco (sólo sus caminos llevan luces) y una conexión para filtrar el Historial. En el teléfono se desplaza sólo la red.")),
            S.historial);
        seccion.replaceChildren(S.raiz);
        // Las luces se pausan con la pestaña oculta y con la red fuera de la pantalla (o en otro submódulo).
        if (!S.observador) S.observador = new IntersectionObserver(xs => { S.visible = xs.some(x => x.isIntersecting); seguir(); });
        S.observador.disconnect(); S.observador.observe(S.envoltura);
        if (!S.iniciada) {
            S.iniciada = true;
            document.addEventListener("visibilitychange", seguir);
            matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", rehacer);
            let espera = 0;
            window.addEventListener("resize", () => { clearTimeout(espera); espera = setTimeout(() => { if (S.seccion && !S.seccion.hidden) rehacer(); }, 250); });
        }
    }
    // Lo llama pintar() de encargos.js con cada relectura. El alcance forma parte de la firma: cambiar el hash
    // reconstruye la red, no sólo sus textos laterales.
    function pintar(seccion, d, alcance = { tipo: "todo", valor: "" }, escribirHash = null) {
        if (S.seccion !== seccion || !S.raiz || !seccion.contains(S.raiz)) armar(seccion);
        S.d = d; S.alcance = alcance; S.escribirHash = escribirHash;
        if (!d || !Array.isArray(d.h)) { S.red = null; S.firma = ""; S.envoltura.replaceChildren(el("p", { class: "tenue" }, d && d.h === null ? "sin datos: el historial no se pudo leer" : "sin datos")); }
        else {
            const vivas = colasVivas().map(v => `${v.nombre}:${v.estado}:${v.etapa}:${v.fase}`).join(","), h = d.h;
            const firma = [h.length, h.length ? (h.at(-1) || {}).inicio : "", S.metrica, S.periodo, S.modo, S.luces, quieto(), vivas,
                S.alcance && S.alcance.tipo, S.alcance && S.alcance.valor, Math.floor((S.envoltura.clientWidth || 0) / 40)].join("|");
            if (firma !== S.firma) { S.firma = firma; dibujar(); }
        }
        pintarAlcance(); pintarCabeza(); pintarFranja(); pintarPipeline(); pintarHistorial(); seguir();
    }
    return { pintar, RETRABAJO, etiquetaModelo, fasesTramos };
})();
