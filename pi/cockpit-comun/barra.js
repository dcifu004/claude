/*
 * Barra compartida de las seis páginas propias de Cockpit (encargo 18, documento 26):
 * Inicio · Agents · Asistentes · Cuentas · Noticias · Luces, en grupos separados por un
 * punto, con la página actual resaltada, un contador ámbar cuando hay algo pendiente y,
 * a la derecha, «leído hace X» y el botón Actualizar.
 *
 * ÚNICO componente: vive acá y cada página sólo pone <nav id="barra" data-pagina="…">.
 * Se arma al cargarse este archivo (antes que el script de la página), así que
 * #leido y #actualizar ya existen cuando la página los busca.
 *
 * Doctrina:
 *  - Sólo LEE, y sin root: la carpeta de propuestas (de dcifu004) y `noticias-cockpit
 *    estado` (corre como dcifu004). Nada de sudo: la barra va en las seis páginas.
 *  - Lo que no se pudo leer no muestra contador y se entrega como null: quien lo use
 *    (🏠 Inicio) dice «sin datos», nunca 0.
 *  - Todo queda dentro de `barraNodo`: este archivo no declara ningún otro nombre global,
 *    para no chocar con los de cada página.
 */
"use strict";

const barraNodo = (() => {
    const CARPETA_PROPUESTAS = "/home/dcifu004/.local/share/bots-propuestas";
    const NOTICIAS = ["/usr/local/bin/noticias-cockpit", "estado"];
    const ENCARGOS = "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/encargos/COLA-ESTADO.md";
    const VIVO_DIR = ENCARGOS.slice(0, ENCARGOS.lastIndexOf("/")) + "/vivo";
    const PROGRAMADOS = ["python3", "/home/dcifu004/.local/share/cockpit/sistema/programados.py"];
    const REFRESCO_MS = 5 * 60 * 1000;
    // encargos/vivo/<cola>.json lo escribe vivo() de cola-run.py (encargo 22, parte B).
    const FINALES = ["terminada", "detenida", "pausada", "caída", "sin autorización"];
    const CON_BARRA = ["corriendo", "pruebas finales", "desplegando"];
    const RECIENTE_MS = 12 * 3600 * 1000;
    const SIN_SENAL_MS = 2 * 3600 * 1000;
    // Cockpit no deja poner separadores en «Herramientas»: los grupos se ven acá.
    // `id` es el nombre del paquete (data-pagina) y `destino`, la ruta de cockpit.jump.
    const GRUPOS = [
        [{ id: "sistema", icono: "🏠", texto: "Inicio", destino: "/sistema" }],
        [{ id: "nodo", icono: "👾", texto: "Agents", destino: "/nodo" },
         { id: "bots", icono: "🤖", texto: "Asistentes", destino: "/bots" },
         { id: "cuentas", icono: "💳", texto: "Cuentas", destino: "/cuentas" }],
        [{ id: "encargos", icono: "🧵", texto: "Encargos", destino: "/encargos" }],
        [{ id: "noticias", icono: "📰", texto: "Noticias", destino: "/noticias" }],
        [{ id: "luces", icono: "🌈", texto: "Luces", destino: "/luces" }],
    ];

    const nav = document.getElementById("barra");
    const actual = nav ? nav.dataset.pagina : "";
    const contadores = {};
    const leidoTexto = el("span", { id: "leido", class: "tenue" });
    const actualizar = el("button", { id: "actualizar", class: "secundario mini" }, "Actualizar");
    let marca = null;
    let ultima = null;

    /* ---------- navegación ---------- */

    function ir(p) {
        // En la propia página no hay salto que hacer: se avisa, y 🍇 vuelve a 🏠 Inicio.
        if (p.id === actual) window.dispatchEvent(new CustomEvent("barra:actual"));
        else cockpit.jump(p.destino);
    }

    function enlace(p) {
        contadores[p.id] = el("span", { class: "barra-contador", hidden: true });
        return el("button", { class: "barra-enlace" + (p.id === actual ? " actual" : ""),
            "aria-current": p.id === actual ? "page" : null, onclick: () => ir(p) },
            el("span", { "aria-hidden": "true" }, p.icono), p.texto, contadores[p.id]);
    }

    /* ---------- «leído hace X» ---------- */

    function haceTexto(d) {
        const min = Math.round((Date.now() - d.getTime()) / 60000);
        if (min < 1) return "recién";
        if (min < 60) return `hace ${min} min`;
        const h = Math.floor(min / 60);
        return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;
    }

    function pintarLeido() {
        leidoTexto.textContent = marca && !Number.isNaN(marca.getTime()) ? "leído " + haceTexto(marca) : "";
    }

    // `cuando` es la fecha del dato que muestra la página (ISO o Date); sin ella, ahora.
    // `detalle` queda como texto emergente (p. ej. cada cuánto se arma el dato).
    function leido(cuando, detalle) {
        marca = cuando ? new Date(cuando) : new Date();
        leidoTexto.title = detalle || "";
        pintarLeido();
    }

    // La página dice qué hace su botón Actualizar. Mientras corre, el botón se apaga.
    function alActualizar(hacer) {
        actualizar.addEventListener("click", async () => {
            actualizar.disabled = true;
            try { await hacer(); } finally { actualizar.disabled = false; }
        });
    }

    /* ---------- lo pendiente ---------- */

    // Propuestas por aplicar: las de la carpeta que todavía no tienen su
    // `<id>.resultado.json` (lo deja aplicar-propuesta). null = no se pudo leer.
    async function leerPropuestas() {
        let lista;
        try {
            lista = await cockpit.spawn(["find", CARPETA_PROPUESTAS, "-maxdepth", "1", "-name", "*.json"],
                                        { err: "ignore" });
        } catch (e) {
            return null;
        }
        const cola = ".resultado.json";
        const nombres = lista.split("\n").filter(Boolean).map(r => r.slice(r.lastIndexOf("/") + 1));
        const resueltas = new Set(nombres.filter(n => n.endsWith(cola)).map(n => n.slice(0, -cola.length)));
        return nombres.filter(n => !n.endsWith(cola))
            .filter(n => !resueltas.has(n.slice(0, -".json".length))).length;
    }

    // Lo mismo que lee la pestaña 🗳️ Entregas de 📰. null = no se pudo leer.
    async function leerNoticias() {
        try {
            const d = JSON.parse(await cockpit.spawn(NOTICIAS, { err: "message" }));
            return d && d.ok !== false ? d : null;
        } catch (e) {
            return null;
        }
    }

    // Una sesión cola-* está viva. Sin ella, el último «se detuvo» de la bitácora
    // mantiene el aviso; no se interpreta ninguna otra fase humana. `colas` son los
    // vivo/*.json recientes (o de una sesión viva), ya como modelo de barra de progreso.
    async function leerEncargos() {
        try {
            const [tmux, estado, colas] = await Promise.all([
                cockpit.spawn(["tmux", "ls", "-F", "#{session_name}"], { err: "ignore" }),
                cockpit.file(ENCARGOS).read(),
                leerVivos(),
            ]);
            const sesiones = tmux.split("\n").filter(x => /^cola[\w-]+$/.test(x));
            const modelos = modelosColas(colas, sesiones, Date.now());
            const viva = sesiones.length > 0;
            const ultimas = estado.split("\n").filter(Boolean).slice(-12).join("\n");
            return { viva, detenida: !viva && /⛔[^\n]*(se detuvo|detenida)/i.test(ultimas), sesiones, colas: modelos };
        } catch (e) { return null; }
    }

    // Los vivo/*.json (uno por cola). Uno ilegible o a medias se salta; sin carpeta, lista vacía.
    async function leerVivos() {
        let lista = "";
        try { lista = await cockpit.spawn(["find", VIVO_DIR, "-maxdepth", "1", "-name", "*.json"], { err: "ignore" }); }
        catch (e) { return []; }
        const leidos = await Promise.all(lista.split("\n").filter(Boolean).map(async ruta => {
            try { return JSON.parse(await cockpit.file(ruta).read()); } catch (e) { return undefined; }
        }));
        return leidos.filter(v => v && v.nombre && v.estado);
    }

    // Las colas que se muestran: las de una sesión viva o con el archivo escrito hace menos de 12 h,
    // la más nueva primero.
    function modelosColas(vivos, sesiones, ahoraMs, historial) {
        return vivos.filter(v => sesiones.includes(v.nombre) || ahoraMs - Date.parse(v.escrito) < RECIENTE_MS)
            .map(v => modeloCola(v, ahoraMs, sesiones.includes(v.nombre), historial))
            .sort((a, b) => b.escrito - a.escrito);
    }

    function horaLocal(iso) {
        const d = new Date(iso);
        return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hour12: false });
    }

    // La hora de un ISO, con el día si no es hoy (una espera por la cuota semanal cruza días).
    function horaFecha(iso, ahoraMs) {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return null;
        const dia = x => x.toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit" });
        return d.toDateString() === new Date(ahoraMs).toDateString() ? horaLocal(iso) : `${dia(d)} ${horaLocal(iso)}`;
    }

    // «autor», «revisión 2», «arreglo 1»: la fase como la dice cola-run.py (autor, rev2, fix1).
    function nombreFase(f) {
        const m = /^(autor|rev|fix)(\d*)$/.exec(f || "");
        if (!m) return f || null;
        return m[1] === "autor" ? "autor" : `${m[1] === "rev" ? "revisión" : "arreglo"} ${m[2]}`.trim();
    }

    // Veredicto de cada fase de revisión: del historial si lo tiene; si no, se deduce de lo que
    // vino después (un arreglo detrás = ❌; la última con la cola terminada = ✅). Sin eso, null.
    function veredictoFase(v, i, historial) {
        const h = fh => /^rev/.test(fh.fase);
        const f = v.fases_hechas[i];
        if (!h(f)) return null;
        const fila = (historial || []).filter(x => String(x.encargo) === String(f.etapa) && x.fase === f.fase && x.veredicto).at(-1);
        if (fila) return fila.veredicto === "DESPLEGABLE" ? "ok" : "mal";
        const sigue = v.fases_hechas[i + 1];
        if (sigue && /^fix/.test(sigue.fase)) return "mal";
        if (i === v.fases_hechas.length - 1 && ["terminada", "desplegando", "pruebas finales"].includes(v.estado)) return "ok";
        if (i === v.fases_hechas.length - 1 && v.estado === "detenida") return "mal";
        return null;
    }

    // El modelo de UNA cola para dibujarla (🧵 Ahora y la baldosa de 🏠). Sólo lee campos que
    // vivo() escribe. `ahoraMs` y `viva` entran de afuera: así el avance se interpola con el reloj
    // sin tocar el archivo. tipo: barra | llena | sin_barra | sin_senal | espera_cuota.
    function modeloCola(v, ahoraMs, viva, historial) {
        const escrito = Date.parse(v.escrito);
        const final = FINALES.includes(v.estado);
        const m = { cola: v.nombre, estado: v.estado, escrito: Number.isNaN(escrito) ? 0 : escrito, cuenta: v.cuenta || null,
                    modelo: v.modelo || null, fase: nombreFase(v.fase), etapa: v.etapa || null, tipo: "sin_barra",
                    detalle: null, pct: null, fill: 0, marcas: null, termina: null, fin: v.fin ? horaLocal(v.fin) : null,
                    segmentos: [], deducido: false };
        m.segmentos = (v.fases_hechas || []).map((f, i) => ({ fase: nombreFase(f.fase), cuenta: f.cuenta, min: f.min,
            pronostico: f.pronostico_min, veredicto: veredictoFase(v, i, historial) }));
        if (v.estado === "corriendo" && v.fase) {
            m.segmentos.push({ fase: nombreFase(v.fase), cuenta: v.cuenta, min: Math.max(0, (ahoraMs - Date.parse(v.inicio_fase)) / 60000),
                               pronostico: v.pronostico_fase_min, veredicto: null, enCurso: true });
        }
        if (!final && !viva && ahoraMs - m.escrito > SIN_SENAL_MS) {
            m.tipo = "sin_senal";
            m.detalle = `sin señal desde las ${horaLocal(v.escrito)}: la sesión ya no está viva`;
            return m;
        }
        if (final) {
            m.tipo = ["terminada", "detenida"].includes(v.estado) ? "llena" : "sin_barra";
            m.pct = m.tipo === "llena" ? 100 : null;
            m.detalle = v.estado === "pausada" ? `${v.motivo_pausa || "pausada"}${v.reanuda_desde ? ` · se reanuda desde ${v.reanuda_desde}` : ""}`
                : v.estado === "caída" ? (v.error || "caída") : v.estado === "sin autorización" ? "no se autorizó el modelo: no corrió nada" : null;
            return m;
        }
        if (v.estado === "esperando") { m.detalle = `esperando a que termine «${v.esperando}»`; return m; }
        if (v.estado === "esperando autorización") { m.detalle = `esperando autorización por Telegram${v.candado ? ` (${v.candado.join(", ")})` : ""}`; return m; }
        if (v.estado === "esperando_cuota") {
            // Encargo 24: la cola espera la renovación de una cuota. No es un estado final ni lleva la barra de
            // «corriendo»: dice la cuenta, el cálculo que la frena, cuándo sigue y la ETA corrida por la espera.
            m.tipo = "espera_cuota";
            m.modelo = null;
            m.espera = { cuenta: v.cuenta || null, calculo: v.calculo_texto || null, reanuda: v.reanuda ? horaFecha(v.reanuda, ahoraMs) : null,
                         termina: v.eta ? horaFecha(v.eta.esperado, ahoraMs) : null, debil: !!v.pronostico_debil };
            m.detalle = `${m.espera.cuenta || "sin datos"}: ${m.espera.calculo || "sin datos"}`;
            return m;
        }
        const t0 = Date.parse(v.inicio_trabajo), e = v.eta;
        if (CON_BARRA.includes(v.estado) && e && !Number.isNaN(t0)) {
            const [eMin, eEsp, eMax] = [Date.parse(e.min), Date.parse(e.esperado), Date.parse(e.max)];
            const fin = Math.max(eMax, ahoraMs), span = Math.max(1, fin - t0);
            m.tipo = "barra";
            m.fill = Math.min(1, Math.max(0, (ahoraMs - t0) / span));
            m.marcas = { min: (eMin - t0) / span, esperado: (eEsp - t0) / span };
            // Esperado = lo que va del trabajo sobre lo que va más lo que se espera que falte; nunca 100 antes de terminar.
            m.pct = Math.min(99, Math.max(0, Math.round(100 * (ahoraMs - t0) / Math.max(1, Math.max(eEsp, ahoraMs + 30000) - t0))));
            m.termina = { esperado: horaLocal(e.esperado), min: horaLocal(e.min), max: horaLocal(e.max) };
            return m;
        }
        m.detalle = v.estado;
        return m;
    }

    // Tareas programadas con problemas (⏰ en 🍇): las que fallaron, quedaron vencidas o huérfanas.
    // El recolector es de sólo lectura y corre sin sudo. null = no se pudo leer (sin contador).
    async function leerProgramados() {
        try {
            const d = JSON.parse(await cockpit.spawn(PROGRAMADOS, { err: "message" }));
            const cuenta = e => d.tareas.filter(t => t.estado === e).length;
            return { total: d.tareas.length, fallo: cuenta("fallo"), vencido: cuenta("vencido"), huerfano: cuenta("huerfano") };
        } catch (e) { return null; }
    }

    // Noticias sin votar: las elegidas de la ÚLTIMA entrega cuando ninguna tiene marca.
    // Con al menos una marca, esa entrega ya se votó (las demás son «no me sirvió»).
    // null = sin datos; 0 = nada pendiente.
    function sinVotar(noticias) {
        if (!noticias || !Array.isArray(noticias.entregas)) return null;
        const ultima = noticias.entregas[0];
        if (!ultima) return 0;
        if (!Array.isArray(ultima.elegidos)) return null;
        return ultima.elegidos.some(n => n.marcado) ? 0 : ultima.elegidos.length;
    }

    function contar(id, n, titulo) {
        const c = contadores[id];
        if (!c) return;
        c.hidden = !(n > 0);
        c.textContent = n > 0 ? String(n) : "";
        c.title = n > 0 ? titulo : "";
    }

    // Vuelve a leer lo pendiente y actualiza los contadores. Devuelve lo leído, tal cual,
    // para que 🏠 Inicio y 💳 no lo lean dos veces: {propuestas: n|null, noticias: {...}|null}.
    function refrescar() {
        ultima = Promise.all([leerPropuestas(), leerNoticias(), leerEncargos(), leerProgramados()]).then(([propuestas, noticias, encargos, programados]) => {
            contar("bots", propuestas, `${propuestas} propuesta(s) por aplicar`);
            const votar = sinVotar(noticias);
            contar("noticias", votar, `${votar} noticia(s) de la última entrega sin votar`);
            contar("encargos", encargos && (encargos.viva || encargos.detenida) ? 1 : 0,
                encargos && encargos.viva ? "Hay una cola viva" : "Hay una cola detenida");
            const malas = programados ? programados.fallo + programados.vencido + programados.huerfano : 0;
            contar("sistema", malas, `${malas} tarea(s) programada(s) con problemas: ver ⏰ en 🍇`);
            return { propuestas, noticias, encargos, programados };
        });
        return ultima;
    }

    /* ---------- arranque ---------- */

    if (nav) {
        nav.classList.add("barra-nodo");
        nav.setAttribute("aria-label", "Herramientas del nodo");
        nav.replaceChildren(
            el("div", { class: "barra-enlaces" }, GRUPOS.flatMap((grupo, i) => [
                i ? el("span", { class: "barra-punto", "aria-hidden": "true" }, "·") : null,
                ...grupo.map(enlace)])),
            el("div", { class: "barra-lado" }, leidoTexto, actualizar));
        actualizar.addEventListener("click", () => { refrescar(); });
        setInterval(pintarLeido, 30000);
        cockpit.transport.wait(() => {
            refrescar();
            setInterval(() => { if (!document.hidden) refrescar(); }, REFRESCO_MS);
        });
    }

    return {
        CARPETA_PROPUESTAS, GRUPOS, actual, leerEncargos, leerVivos, modeloCola, modelosColas,
        leido, alActualizar, refrescar, sinVotar,
        // Lo último leído (o lo lee): no dispara otra lectura si ya hay una.
        pendientes: () => ultima || refrescar(),
    };
})();
