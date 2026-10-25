/*
 * 🏠 Inicio de "🍇 Raspberry Pi" (encargo 18, documento 26): el modelo del bento.
 *
 * Acá no hay DOM ni lecturas: `modeloInicio(fuentes, ahora)` recibe lo que ya leyó
 * sistema.js y devuelve las seis baldosas, cada una como una LISTA DE ESTADO: filas
 * «dato → valor» y un punto verde, ámbar o gris. sistema.js sólo las dibuja.
 *
 * Fuentes (ninguna es nueva; todas las lee ya alguna página):
 *   estado     /opt/nodo/datos/estado.json        (🍇 Estado)
 *   uso        /opt/nodo/datos/uso.json           (👾)
 *   bots       sudo -n /usr/local/bin/bots-info   (🤖, 💳, 👾)
 *   luces      luces estado                       (🌈)
 *   noticias   noticias-cockpit estado            (📰 Entregas)
 *   propuestas cuántas hay por aplicar, y sinVotar: los dos números de la barra
 *   programados {total, fallo, vencido, huerfano} de ⏰ (encargo 22): la baldosa sólo existe si hay problemas
 *
 * Regla dura: una fuente que falta o falla llega como null y sus filas dicen «sin
 * datos». NUNCA se muestra como 0 ni deja la baldosa en verde:
 *  - cada valor pasa por filaInicio(), que es la única que escribe «sin datos»;
 *  - el punto sale de las filas: ámbar si alguna avisa; gris si alguna no tiene dato;
 *    verde sólo si todas tienen dato y ninguna avisa;
 *  - acá no hay valores por defecto: ni `|| 0` ni `?? 0` (hay una prueba).
 * Un 0 que sí se leyó (0 noticias nuevas, 0 rpm) se muestra como 0.
 */
"use strict";

const SIN_DATOS = "sin datos";
// estado.timer arma estado.json cada 5 min: pasado este rato, el dato está viejo.
const ESTADO_VIEJO_MIN = 20;

/* ---------- piezas ---------- */

// Una fila «dato → valor». Sin valor dice «sin datos» y queda gris; `avisa` la deja ámbar.
function filaInicio(dato, valor, avisa) {
    const falta = valor == null || valor === "" || (typeof valor === "number" && !Number.isFinite(valor));
    return { dato, valor: falta ? SIN_DATOS : String(valor), nivel: falta ? "gris" : avisa ? "ojo" : "" };
}

function puntoInicio(filas) {
    if (filas.some(f => f.nivel === "ojo")) return "ojo";
    return !filas.length || filas.some(f => f.nivel === "gris") ? "gris" : "ok";
}

function minutosDesde(iso, ahora) {
    const t = iso ? new Date(iso).getTime() : NaN;
    return Number.isNaN(t) ? null : Math.max(0, Math.round((ahora - t) / 60000));
}

function haceInicio(min) {
    if (min == null) return null;
    if (min < 1) return "recién";
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;
}

function comaInicio(x, dec) {
    return Number(x).toFixed(dec).replace(".", ",");
}

// Día y hora locales: «03-10 16:05».
function fechaInicio(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    const pad = n => String(n).padStart(2, "0");
    return `${pad(d.getDate())}-${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* ---------- 🍇 Raspberry Pi: la baldosa alta ---------- */

function filasPi(e, ahora) {
    const serv = e && e.servicios ? Object.entries(e.servicios) : null;
    const cont = e && Array.isArray(e.contenedores) ? e.contenedores : null;
    const caidos = serv && cont
        ? serv.filter(([, ok]) => !ok).map(([n]) => n).concat(cont.filter(c => !c.ok).map(c => c.nombre))
        : null;
    const m = e && e.medidores ? e.medidores : {};
    const temp = m.temp_soc, raiz = m.raiz;
    const vent = e ? e.ventilador : null;
    const luks = e ? e.luks : null;
    const r = e ? e.respaldo : null;
    const alertas = e && Array.isArray(e.alertas) ? e.alertas : null;
    const edad = e ? minutosDesde(e.momento, ahora) : null;
    return [
        filaInicio("Servicios", caidos && (caidos.length
            ? `${caidos.length} caído(s): ${caidos.join(", ")}` : `${serv.length + cont.length} arriba`),
            caidos && caidos.length > 0),
        filaInicio("Temperatura", temp && temp.v != null ? `${comaInicio(temp.v, 1)} °C` : null,
            temp && temp.am != null && temp.v >= temp.am),
        filaInicio("Ventilador", vent && vent.rpm != null
            ? `${vent.rpm} rpm` + (vent.pct != null ? ` · ${vent.pct} %` : "") : null),
        filaInicio("Disco raíz", raiz && raiz.v != null ? `${Math.round(raiz.v)} % usado` : null,
            raiz && raiz.am != null && raiz.v >= raiz.am),
        filaInicio("Volumen cifrado", luks ? (luks.abierto
            ? "abierto" + (luks.pct != null ? ` · ${luks.pct} % usado` : "") : "CERRADO") : null,
            luks && !luks.abierto),
        filaInicio("Respaldo", r && r.ultimo ? haceInicio(minutosDesde(r.ultimo, ahora)) : null),
        filaInicio("Disco de respaldo", r ? (r.montado ? "montado" : "no montado") : null, r && !r.montado),
        filaInicio("Alertas", alertas && (alertas.length
            ? `${alertas.length}: ${alertas[0].texto || alertas[0].id}` : "ninguna"),
            alertas && alertas.length > 0),
        filaInicio("Medido", haceInicio(edad), edad != null && edad > ESTADO_VIEJO_MIN),
    ];
}

/* ---------- 👾 IA Agents ---------- */

function filasAgentes(e, u, ahora) {
    const agentes = e && Array.isArray(e.agentes) ? e.agentes : null;
    const alertas = e && Array.isArray(e.alertas) ? e.alertas : [];
    const sesion = nombre => {
        if (!agentes) return filaInicio(nombre, null);
        const suyos = agentes.filter(a => String(a.agente).toLowerCase() === nombre.toLowerCase());
        if (!suyos.length) return filaInicio(nombre, "sin sesión");
        const horas = suyos.map(a => a.horas).filter(h => typeof h === "number");
        // estado.py avisa del agente que lleva demasiado tiempo vivo: la alerta `agente:<pid>`.
        const avisa = suyos.some(a => alertas.some(x => x.id === `agente:${a.pid}`));
        return filaInicio(nombre, (suyos.length > 1 ? `${suyos.length} procesos · ` : "") + "corriendo" +
            (horas.length ? ` ${haceInicio(Math.round(60 * Math.max(...horas)))}` : ""), avisa);
    };
    const hoy = u && u.claude && u.claude.disponible ? u.claude.hoy : null;
    return [
        sesion("Claude"),
        sesion("Codex"),
        filaInicio("Claude hoy en la Pi", hoy && hoy.mensajes != null ? `${hoy.mensajes} mensajes` : null),
        filaInicio("Uso medido", u ? haceInicio(minutosDesde(u.momento, ahora)) : null),
    ];
}

/* ---------- 🤖 Asistentes ---------- */

function filasAsistentes(b, propuestas) {
    const perfiles = b && b.perfiles ? Object.entries(b.perfiles) : null;
    const bots = perfiles ? perfiles.map(([id, p]) => {
        const activo = p.servicio ? p.servicio.ActiveState : null;
        return filaInicio((p.toml && p.toml.nombre) || id,
            activo ? (activo === "active" ? "activo" : activo) : null, !!activo && activo !== "active");
    }) : [filaInicio("Bots", null)];
    const deriva = b && Array.isArray(b.deriva) ? b.deriva.filter(d => !d.igual && !d.mismos_valores) : null;
    return [
        ...bots,
        filaInicio("Propuestas", propuestas == null ? null
            : propuestas ? `${propuestas} por aplicar` : "ninguna por aplicar", propuestas > 0),
        filaInicio("Vault y desplegado", deriva && (deriva.length
            ? `${deriva.length} archivo(s) distintos` : "iguales"), deriva && deriva.length > 0),
    ];
}

/* ---------- 💳 Cuentas ---------- */

// Los nombres de las cuentas llegan de bots-info (`margen.cuentas[id].nombre`): acá no
// se escribe ninguno.
function filasCuentas(b) {
    const m = b ? b.margen : null;
    const pagadas = m && Array.isArray(m.orden) && m.cuentas
        ? m.orden.map(id => m.cuentas[id]).filter(c => c && c.pagada) : null;
    const mejor = m && m.con_margen && m.cuentas ? m.cuentas[m.con_margen] : null;
    const uso = b ? b.uso_cuentas : null;
    return [
        filaInicio("Con más margen", m ? (mejor ? mejor.nombre : "ninguna bajo el umbral") : null, !!m && !mejor),
        ...(pagadas ? pagadas.map(c => filaInicio(c.nombre,
            c.libre_pct != null ? `${Math.round(c.libre_pct)} % libre` : null, !!c.sobre))
            : [filaInicio("Margen por cuenta", null)]),
        filaInicio("Costo del mes", uso && uso.total_mes_usd != null ? `US$ ${comaInicio(uso.total_mes_usd, 2)}` : null),
    ];
}

/* ---------- 🌈 Luces ---------- */

function filasLuces(l) {
    const MODOS = { arcoiris: "arcoíris", respiracion: "respiración", paleta: "paleta de colores",
                    fijo: "color fijo", apagado: "apagadas" };
    // `vigente` falso con un modo anotado: la Pi se reinició y las luces aún no se restauran.
    const sinRestaurar = !!l && !!l.modo && !l.vigente;
    const detenida = !!l && l.animacion_viva === false;
    const modo = !l ? null : sinRestaurar ? "apagadas tras el reinicio"
        : detenida ? "animación detenida" : (MODOS[l.modo] || l.modo);
    const movimiento = l && l.modo
        ? ([l.girar ? "gira" : null, l.respira ? "respira" : null].filter(Boolean).join(" y ") || "quieto") : null;
    return [
        filaInicio("Modo", modo, sinRestaurar || detenida),
        filaInicio("Brillo", l && l.brillo != null ? `${l.brillo} %` : null),
        filaInicio("Movimiento", movimiento),
    ];
}

/* ---------- 🧵 Encargos ---------- */

function filasEncargos(q) {
    if (!q) return [filaInicio("Cola", null)];
    // Encargo 22, parte B: cada cola con barra (vivo/<cola>.json) dice dónde va y cuándo termina.
    const conBarra = (Array.isArray(q.colas) ? q.colas : []).filter(cola => cola.tipo === "barra");
    return [filaInicio("Cola", q.viva ? "corriendo" : q.detenida ? "detenida" : "nada corriendo",
        !!q.viva || !!q.detenida),
        ...conBarra.map(cola => filaInicio(cola.cola, `${cola.fase || cola.estado} · ~${cola.pct} % · termina ~${cola.termina.esperado}`, true))];
}

/* ---------- ⏰ Programados: sólo si algo falló, quedó vencido o huérfano ---------- */

// `prog` = {total, fallo, vencido, huerfano} de barraNodo (leerProgramados). Sin dato o todo al día,
// no hay baldosa: devuelve null y el bento la omite. Acá sí se muestra un 0 que se leyó.
function filasProgramados(prog) {
    if (!prog || prog.fallo + prog.vencido + prog.huerfano === 0) return null;
    return [filaInicio("La última falló", prog.fallo, prog.fallo > 0), filaInicio("Vencidas", prog.vencido, prog.vencido > 0),
            filaInicio("Huérfanas", prog.huerfano, prog.huerfano > 0), filaInicio("Programadas en total", prog.total)];
}

/* ---------- 📰 Noticias: a lo ancho ---------- */

function filasNoticias(n, sinVotar) {
    const corridas = n ? n.corridas : null;
    const ultima = corridas && Array.isArray(corridas.lista) ? corridas.lista[0] : null;
    let caidas = null;
    if (ultima) {
        try {
            const ciegos = JSON.parse(ultima.ciegos || "{}");
            caidas = Array.isArray(ciegos.fuentes_caidas) ? ciegos.fuentes_caidas : null;
        } catch (x) {
            caidas = null;
        }
    }
    const entrega = n && Array.isArray(n.entregas) ? n.entregas[0] : null;
    const elegidos = entrega && Array.isArray(entrega.elegidos) ? entrega.elegidos : null;
    const pref = n ? n.preferencias : null;
    const turno = n && n.turnos ? n.turnos["noticias-seleccion"] : null;
    return [
        filaInicio("Última cosecha", ultima && fechaInicio(ultima.cuando)
            ? `${fechaInicio(ultima.cuando)} · ${ultima.items} ítems` : null),
        filaInicio("Nuevas hoy", corridas ? corridas.nuevos_hoy : null),
        filaInicio("Fuentes caídas", caidas && (caidas.length ? `${caidas.length}: ${caidas.join(", ")}` : "ninguna")),
        filaInicio("Última entrega", elegidos
            ? `${String(entrega.archivo).replace(/ - noticias - .*\.md$/, "")} · ${elegidos.length} elegidas · ` +
              `${elegidos.filter(x => x.marcado).length} marcadas` : null, sinVotar > 0),
        filaInicio("Votos", pref && pref.items != null && pref.marcados != null
            ? `${pref.marcados} de ${pref.items} entregadas` : null,
            !!pref && pref.items > 0 && !pref.marcados),
        filaInicio("Próxima selección", turno ? turno.proximo : null),
    ];
}

/* ---------- el bento ---------- */

// `fuentes` = {estado, uso, bots, luces, noticias, propuestas, sinVotar, encargos, programados}; null = no se pudo leer.
// `forma`: "alta" (🍇), "ancha" (📰, abajo) o "" (chica). `destino` es el de cockpit.jump.
function modeloInicio(fuentes, ahora) {
    const baldosa = (id, titulo, destino, forma, filas) =>
        ({ id, titulo, destino, forma, filas, estado: puntoInicio(filas) });
    return [
        baldosa("sistema", "🍇 Raspberry Pi", "/sistema", "alta", filasPi(fuentes.estado, ahora)),
        baldosa("nodo", "👾 IA Agents", "/nodo", "", filasAgentes(fuentes.estado, fuentes.uso, ahora)),
        baldosa("bots", "🤖 Asistentes", "/bots", "", filasAsistentes(fuentes.bots, fuentes.propuestas)),
        baldosa("cuentas", "💳 Cuentas", "/cuentas", "", filasCuentas(fuentes.bots)),
        baldosa("encargos", "🧵 Encargos", "/encargos", "", filasEncargos(fuentes.encargos)),
        baldosa("luces", "🌈 Luces", "/luces", "", filasLuces(fuentes.luces)),
        ...(filasProgramados(fuentes.programados)
            ? [baldosa("programados", "⏰ Programados", "/sistema", "", filasProgramados(fuentes.programados))] : []),
        baldosa("noticias", "📰 Noticias", "/noticias", "ancha", filasNoticias(fuentes.noticias, fuentes.sinVotar)),
    ];
}
