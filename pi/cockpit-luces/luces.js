/*
 * Pestaña "🌈 Luces" de Cockpit: sólo los LED. La temperatura y el ventilador pasaron a
 * 🍇 Raspberry Pi → Estado (encargo 18).
 *
 * Canónico en el vault (10-Proyectos/11-Pi5/pi/cockpit-luces/); se instala copiando la
 * carpeta a ~/.local/share/cockpit/luces, junto con `comun` (tokens, base, tema y la
 * barra compartida). Receta de las luces: documento 18.
 *
 * Doctrina: la página NUNCA escribe los LEDs directo — todo pasa por el comando
 * `luces`, que es el único que anota el registro. Los WS2812 son de sólo escritura:
 * si algo los cambia por otro camino, /estado y esta página describen un color que ya
 * no está. Corre como dcifu004 (grupo gpio), sin root, con argumentos fijos: los
 * colores viajan por su nombre, nunca como texto libre.
 *
 * Todo se aplica SOLO, sin botón (pedido de Diego, 24-09-2026). Para que eso no haga
 * parpadear las luces: los toques de color esperan un momento por si viene otro, los
 * deslizadores se aplican al soltar, y si llega un cambio mientras otro se aplica, se
 * aplica sólo el ÚLTIMO estado — nunca una fila de estados viejos.
 */
"use strict";

const LUCES = "/home/dcifu004/.local/bin/luces";
const NOMBRES = {
    rojo: "Rojo", naranja: "Naranja", amarillo: "Amarillo", verde: "Verde", cian: "Cian",
    azul: "Azul", morado: "Morado", rosado: "Rosado", blanco: "Blanco",
};
const ESPERA_COLOR_MS = 450;

let estado = null;
let seleccion = [];          // nombres de color en orden, o ["arcoiris"]
let sembrada = false;
let pendiente = { colores: false, brillo: false };
let corriendo = false;
let temporizador = null;
let reglas = null;
let catalogo = {};
let reglaMostrada = null;
let guardadoReglas = null;
let reglasSucias = false;
let versionReglas = 0;
const REGLAS_DEFECTO = [
    ["encargo_corriendo", "estado", "base", "respira", 8, 0, 1, 0, 3],
    ["jaime_escuchando", "estado", "#0000ff", "fijo", 5, 0, 1, 0, 4],
    ["jaime_respondiendo", "estado", "#0000ff", "girar", 5, 0, 1, 0, 4],
    ["pilar_escuchando", "estado", "#ff4fa3", "fijo", 5, 0, 1, 0, 4],
    ["pilar_respondiendo", "estado", "#ff4fa3", "girar", 5, 0, 1, 0, 4],
    ["temporizador_sonando", "estado", "naranja", "destello", 8, 0, 1, 0, 5],
    ["aviso_error", "toque", "rojo", "destello", 8, 3, 1, 0, 5],
    ["cpu_caliente", "estado", "rojo", "respira", 5, 0, 1, 0, 4],
    ["luks_cerrado", "estado", "morado", "fijo", 5, 0, 1, 0, 5],
    ["boleta_registrada", "toque", "verde", "destello", 5, 1, 1, 0, 3],
    ["cola_terminada", "toque", "verde", "fijo", 5, 1, 10, 0, 3],
    ["cola_detenida", "toque", "rojo", "fijo", 5, 1, 10, 0, 3],
];
// La página sólo publica nombres del catálogo y mensajes breves conocidos; nunca el texto
// libre que pueda traer stderr de otro proceso.
const RE_TEXTO_REGLAS = /^[A-Za-zÁÉÍÓÚáéíóúñÑ0-9 _.,;:/()[\]#%+\-]{1,180}$/;
function textoReglasSeguro(valor, defecto = "No se pudo guardar las reglas") {
    const texto = String(valor || "").trim();
    return RE_TEXTO_REGLAS.test(texto) ? texto : defecto;
}

// reglas_activas se conserva: sólo el interruptor general lo cambia (57br3).
function configuracionDefecto(reglasActivas) {
    return { reglas: REGLAS_DEFECTO.map(([id, tipo, color, animacion, nivel, repetir, dura_s, cada_s, prioridad]) => {
        const regla = { id, evento: id, activa: true, tipo, color, animacion, nivel, repetir, dura_s, cada_s, prioridad };
        if (id === "cpu_caliente") regla.umbral_c = 67;
        return regla;
    }), reglas_activas: reglasActivas, horario_brillo: [{ hora: "07:00", brillo: 100 }, { hora: "20:00", brillo: 75 }, { hora: "23:00", brillo: 45 }] };
}

function reglasEstanActivas(configuracion) {
    return configuracion.reglas_activas !== false;
}

// El tema lo aplica ../comun/tema.js (encargo 18).

const $ = id => document.getElementById(id);
const hex = rgb => "#" + rgb.map(x => Math.round(x).toString(16).padStart(2, "0")).join("");

function error(msg) {
    $("error").hidden = !msg;
    $("error").textContent = msg ? textoReglasSeguro(msg, "No se pudieron actualizar las luces") : "";
}

async function luces(...args) {
    return cockpit.spawn([LUCES, ...args], { err: "message" });
}

/* ---------- leer y pintar ---------- */

async function leer() {
    let reglasActualizadas = false;
    try {
        estado = JSON.parse(await luces("estado"));
        barraNodo.leido();
    } catch (e) {
        error("No pude leer las luces: " + (e.message || e));
        return;
    }
    try {
        const respuestaReglas = JSON.parse(await luces("reglas"));
        if (!reglasSucias) {
            reglas = respuestaReglas.configuracion;
            catalogo = respuestaReglas.catalogo || {};
            reglasActualizadas = true;
        }
    } catch (e) {
        // La página vieja y el compositor siempre deben seguir mostrando la base aunque
        // todavía no exista el subcomando `reglas` en la instalación.
        error("No pude leer las reglas: " + (e.message || e));
    }
    // `regla_visible` es parte de `estado`, la misma fuente que usa la tira física.
    reglaMostrada = estado.regla_visible || null;
    let habilitado = "";
    try {
        habilitado = (await cockpit.spawn(["systemctl", "is-enabled", "luces.service"],
                                          { err: "ignore" })).trim();
    } catch (e) { habilitado = "no"; }
    if (!sembrada) sembrar();
    pintar(habilitado === "enabled");
    pintarAvisoConfiguracion();
    if (reglasActualizadas && !reglasSucias) pintarReglas();
}

function pintarAvisoConfiguracion() {
    const aviso = $("config-error");
    const mensaje = estado && estado.config_error;
    aviso.hidden = typeof mensaje !== "string";
    aviso.textContent = aviso.hidden ? "" : textoReglasSeguro(mensaje, "La configuración de reglas no es válida; se usa la última guardada");
}

// La primera vez, los controles parten de lo que está puesto. Después son de quien
// usa la página: el refresco periódico no los pisa mientras alguien los mueve.
function sembrar() {
    sembrada = true;
    const e = estado;
    if (e.modo === "arcoiris") {
        seleccion = ["arcoiris"];
    } else if (e.modo !== "apagado") {
        const porRgb = Object.fromEntries(Object.entries(e.colores).map(([n, rgb]) => [rgb.join(","), n]));
        const paleta = e.paleta || (e.rgb ? [e.rgb] : []);
        // Sólo los colores con nombre: la página ya no ofrece colores sueltos.
        seleccion = paleta.map(rgb => porRgb[rgb.join(",")]).filter(Boolean);
    }
    $("girar").value = String(e.girar || 0);
    $("respira").value = String(e.respira || 0);
    $("brillo").value = String(e.brillo ?? 100);
    rotular();
}

function rotular() {
    const g = +$("girar").value, r = +$("respira").value;
    $("girar-txt").textContent = g ? `${g} · ${g <= 3 ? "lento" : g <= 7 ? "medio" : "rápido"}` : "quieto";
    $("respira-txt").textContent = r ? `${r} · ${r <= 3 ? "lenta" : r <= 7 ? "media" : "rápida"}` : "no";
    $("brillo-txt").textContent = `${$("brillo").value} %`;
}

function describir(e) {
    if (!e.vigente && e.modo) return "Apagadas (la Pi se reinició y aún no se restauran)";
    if (e.animacion_viva === false) return "Animación detenida";
    const mov = [e.girar ? "girando" : null, e.respira ? "respirando" : null].filter(Boolean).join(" y ");
    switch (e.modo) {
        case "arcoiris": return `Arcoíris ${mov || "quieto"}`;
        case "respiracion": return `${NOMBRES[e.nombre] || (e.rgb ? hex(e.rgb) : "")} respirando`;
        case "paleta": return `${(e.paleta || []).length} colores ${mov || "quietos"}`;
        case "fijo": return `${NOMBRES[e.nombre] || (e.rgb ? hex(e.rgb) : "")} fijo`;
        case "apagado": return "Apagadas";
        default: return "Sin registro";
    }
}

function coloresPorLed(e) {
    if (!e.vigente || e.modo === "apagado") return Array(6).fill(null);
    if (e.modo === "arcoiris") return Array.from({ length: 6 }, (_, i) => `hsl(${i * 60}, 100%, 50%)`);
    const paleta = e.paleta || (e.rgb ? [e.rgb] : []);
    if (!paleta.length) return Array(6).fill(null);
    return Array.from({ length: 6 }, (_, i) => `rgb(${paleta[i % paleta.length].join(",")})`);
}

function colorRegla(color, e) {
    if (color === "base") {
        if (e.modo === "apagado") {
            const tenue = [32, 32, 32];
            return { ...e, vigente: true, modo: "fijo", nombre: null, rgb: tenue, paleta: [tenue] };
        }
        return { ...e };
    }
    const rgb = color.startsWith("#")
        ? color.slice(1).match(/.{2}/g).map(x => parseInt(x, 16))
        : (e.colores[color] || [0, 0, 0]);
    return { ...e, vigente: true, modo: "fijo", nombre: color, rgb, paleta: [rgb],
        girar: 0, respira: 0, animacion_viva: true };
}

function estadoReglaVisible(e) {
    if (!reglaMostrada || !reglas) return e;
    const regla = reglas.reglas.find(r => r.id === reglaMostrada);
    if (!regla) return e;
    const visual = colorRegla(regla.color, e);
    visual.girar = regla.animacion === "girar" ? regla.nivel
        : (regla.color === "base" && regla.animacion === "respira" ? (e.girar || 0) : 0);
    visual.respira = regla.animacion === "respira" ? regla.nivel : 0;
    return visual;
}

function pintar(seRestaura) {
    const e = estadoReglaVisible(estado);
    const tira = $("tira");
    const viva = e.vigente && e.animacion_viva !== false;
    tira.className = "tira" + (viva && e.girar ? " gira" : "") + (viva && e.respira ? " respira" : "");
    const b = (e.brillo ?? 100) / 100;
    tira.replaceChildren(...coloresPorLed(e).map(c => {
        const led = document.createElement("div");
        led.className = "led";
        if (c) {
            // Por CSSOM: el CSP de Cockpit bloquea el atributo style en línea.
            led.style.setProperty("--c", c);
            led.style.setProperty("--brillo-sombra", c);
            led.style.opacity = String(0.35 + 0.65 * b);
        }
        return led;
    }));
    $("estado-texto").textContent = reglaMostrada ? `Regla activa: ${nombreRegla(reglaMostrada)}` : describir(e);
    if (!corriendo) {
        const hora = e.momento ? e.momento.slice(11, 16) : "";
        $("estado-sub").textContent = [
            `brillo ${e.brillo ?? 100} %`,
            hora ? `desde las ${hora}` : "",
            seRestaura ? "se restaura al reiniciar ✓" : "⚠️ luces.service no está habilitado: al reiniciar se apagan",
        ].filter(Boolean).join(" · ");
    }
    pintarMuestras();
}

function nombreRegla(id) {
    const regla = reglas && reglas.reglas.find(r => r.id === id);
    return regla ? `${regla.evento.replaceAll("_", " ")}` : id.replaceAll("_", " ");
}

function entrada(tipo, valor, opciones = []) {
    const campo = document.createElement(tipo === "select" ? "select" : "input");
    if (tipo === "select") opciones.forEach(([v, texto]) => campo.append(el("option", { value: v }, texto)));
    else campo.type = tipo;
    campo.value = String(valor);
    return campo;
}

function marcarFila(fila, motivo) {
    motivo = motivo ? textoReglasSeguro(motivo) : null;
    fila.classList.toggle("error-regla", !!motivo);
    fila.title = motivo || "";
    const detalle = fila.querySelector(".error-detalle");
    if (detalle) detalle.textContent = motivo || "";
}

function programarReglas(fila, ahora = false) {
    clearTimeout(guardadoReglas);
    actualizarInterruptorReglas();
    const version = versionReglas;
    guardadoReglas = setTimeout(async () => {
        try {
            await guardarReglasAhora(version, fila);
        } catch (e) {
            marcarFila(fila, e.message || String(e));
            actualizarInterruptorReglas();
        }
    }, ahora ? 0 : ESPERA_COLOR_MS);
}

function actualizarInterruptorReglas() {
    const control = $("reglas-activas");
    if (control) control.disabled = reglasSucias;
}

async function guardarReglasAhora(version = versionReglas, fila = null) {
    // `input` no es opción de cockpit.spawn: se ignoraba y `guardar` quedaba esperando
    // stdin para siempre (13-10-2026). .input() escribe y cierra.
    await cockpit.spawn([LUCES, "reglas", "guardar"], { err: "message" }).input(JSON.stringify(reglas));
    if (version === versionReglas) {
        reglasSucias = false;
        actualizarInterruptorReglas();
        if (fila) marcarFila(fila, null);
        error(null);
    }
}

function vincular(campo, fila, cambio, deslizador = false) {
    const cambiar = (guardarAhora) => {
        cambio(campo); reglasSucias = true; versionReglas += 1; programarReglas(fila, guardarAhora);
    };
    campo.addEventListener("input", () => { if (!deslizador) cambiar(false); });
    campo.addEventListener("change", () => cambiar(deslizador));
}

function pintarReglas() {
    if (!reglas) return;
    const activas = reglasEstanActivas(reglas);
    $("reglas-activas").checked = activas;
    $("reglas-estado").textContent = `Reglas: ${activas ? "prendidas" : "apagadas"}`;
    $("reglas-apagadas").hidden = activas;
    for (const id of ["contenido-reglas", "contenido-horario"]) $(id).classList.toggle("reglas-apagadas", !activas);
    const tabla = $("tabla-reglas");
    tabla.replaceChildren(el("tr", {}, ...["Activa", "Evento", "Color", "Animación", "Nivel", "Repetir", "Dura", "Cada", "Prioridad", "Franja", ""].map(x => el("th", {}, x))),
        ...reglas.reglas.map((regla, i) => filaRegla(regla, i)));
    const horario = $("tabla-horario");
    horario.replaceChildren(el("tr", {}, el("th", {}, "Hora"), el("th", {}, "Brillo"), el("th", {}, "")),
        ...reglas.horario_brillo.map((marca, i) => filaHorario(marca, i)));
}

async function cambiarReglasActivas() {
    if (!reglas) return;
    const control = $("reglas-activas");
    const anterior = reglasEstanActivas(reglas);
    const prendidas = control.checked;
    // Una edición pendiente tiene prioridad: el temporizador ya programado la guardará.
    // El interruptor queda bloqueado mientras tanto y jamás inicia un guardado completo.
    if (reglasSucias) {
        control.checked = anterior;
        control.disabled = true;
        $("reglas-error").textContent = "Espera que se guarde la edición";
        return;
    }
    control.disabled = true;
    try {
        await cockpit.spawn([LUCES, "reglas", prendidas ? "prender" : "apagar"], { err: "message" });
        $("reglas-error").textContent = "";
        await leer();
    } catch (e) {
        control.checked = anterior;
        $("reglas-estado").textContent = `Reglas: ${anterior ? "prendidas" : "apagadas"}`;
        $("reglas-error").textContent = textoReglasSeguro(e.message || e);
    } finally {
        control.disabled = false;
    }
}

function filaRegla(regla, i) {
    const fila = document.createElement("tr");
    const activa = entrada("checkbox", regla.activa); activa.checked = regla.activa;
    vincular(activa, fila, x => { regla.activa = x.checked; });
    const eventos = Object.keys(catalogo).map(k => [k, k.replaceAll("_", " ")]);
    const evento = entrada("select", regla.evento, eventos);
    vincular(evento, fila, x => { regla.evento = x.value; regla.tipo = catalogo[x.value].tipo; });
    const color = entrada("text", regla.color); vincular(color, fila, x => { regla.color = x.value; });
    const animacion = entrada("select", regla.animacion, ["fijo", "respira", "girar", "destello", "parpadeo"].map(x => [x, x]));
    vincular(animacion, fila, x => { regla.animacion = x.value; });
    const numero = (clave, min, max) => { const x = entrada("number", regla[clave]); x.min = min; x.max = max; vincular(x, fila, y => { regla[clave] = Number(y.value); }, true); return x; };
    const conexion = catalogo[regla.evento] && !catalogo[regla.evento].conectado ? el("span", { class: "sin-conexion" }, "no conectado") : null;
    const desde = entrada("time", regla.desde || ""); const hasta = entrada("time", regla.hasta || "");
    vincular(desde, fila, x => { if (x.value) { regla.desde = x.value; regla.hasta = hasta.value || x.value; } else { delete regla.desde; delete regla.hasta; } });
    vincular(hasta, fila, x => { if (x.value) { regla.desde = desde.value || x.value; regla.hasta = x.value; } else { delete regla.desde; delete regla.hasta; } });
    const prueba = regla.activa && regla.tipo === "toque"
        ? el("button", { class: "mini secundario", onclick: () => probarRegla(regla, fila) }, "Disparar toque") : null;
    const duplicar = el("button", { class: "mini secundario", onclick: () => {
        const usados = new Set(reglas.reglas.map(r => r.id)); let id = `${regla.id}-copia`, n = 2;
        while (usados.has(id)) { id = `${regla.id}-copia-${n}`; n += 1; }
        reglas.reglas.splice(i + 1, 0, { ...regla, id }); reglasSucias = true; versionReglas += 1; pintarReglas(); programarReglas($("tabla-reglas").rows[i + 2]);
    } }, "Duplicar");
    const borrar = el("button", { class: "mini secundario", onclick: () => { reglas.reglas.splice(i, 1); reglasSucias = true; versionReglas += 1; pintarReglas(); programarReglas($("tabla-reglas")); } }, "Borrar");
    const detalle = el("span", { class: "error-detalle", role: "alert" });
    fila.append(el("td", {}, activa), el("td", {}, evento, conexion), el("td", {}, color), el("td", {}, animacion),
        el("td", {}, numero("nivel", 1, 10)), el("td", {}, numero("repetir", 0, 100)), el("td", {}, numero("dura_s", 1, 300)),
        el("td", {}, numero("cada_s", 0, 300)), el("td", {}, numero("prioridad", 1, 5)), el("td", {}, desde, hasta), el("td", {}, prueba, duplicar, borrar, detalle));
    return fila;
}

async function probarRegla(regla, fila) {
    try {
        // Un toque se envía al compositor; una regla de estado no tiene emisor artificial,
        // por lo que se previsualiza sin alterar sus fuentes reales.
        if (regla.tipo === "toque") await luces("evento", regla.evento);
        marcarFila(fila, null);
        const anterior = reglaMostrada; reglaMostrada = regla.id; pintar(true);
        setTimeout(() => { reglaMostrada = anterior; pintar(true); }, 5000);
    } catch (e) { marcarFila(fila, e.message || String(e)); }
}

function filaHorario(marca, i) {
    const fila = document.createElement("tr");
    const hora = entrada("time", marca.hora); vincular(hora, fila, x => { marca.hora = x.value; });
    const brillo = entrada("number", marca.brillo); brillo.min = 0; brillo.max = 100; vincular(brillo, fila, x => { marca.brillo = Number(x.value); }, true);
    const borrar = el("button", { class: "mini secundario", onclick: () => { reglas.horario_brillo.splice(i, 1); reglasSucias = true; versionReglas += 1; pintarReglas(); programarReglas($("tabla-horario")); } }, "Borrar");
    fila.append(el("td", {}, hora), el("td", {}, brillo), el("td", {}, borrar, el("span", { class: "error-detalle", role: "alert" }))); return fila;
}

function pintarMuestras() {
    const opciones = [["arcoiris", null, "Arcoíris"],
        ...Object.entries(estado.colores).map(([n, rgb]) => [n, rgb, NOMBRES[n] || n])];
    $("muestras").replaceChildren(...opciones.map(([clave, rgb, etiqueta]) => {
        const orden = seleccion.indexOf(clave);
        const btn = document.createElement("button");
        btn.className = "muestra" + (orden >= 0 ? " marcada" : "");
        btn.setAttribute("aria-pressed", orden >= 0 ? "true" : "false");
        const punto = document.createElement("span");
        punto.className = "punto" + (clave === "arcoiris" ? " arcoiris" : "");
        if (rgb) punto.style.setProperty("--c", `rgb(${rgb.join(",")})`);
        if (orden >= 0 && clave !== "arcoiris" && seleccion.length > 1) punto.textContent = String(orden + 1);
        else if (orden >= 0) punto.textContent = "✓";
        btn.append(punto, etiqueta);
        btn.addEventListener("click", () => tocar(clave));
        return btn;
    }));
    const n = seleccion[0] === "arcoiris" ? 0 : seleccion.length;
    $("cuenta").textContent = n > 1 ? `· ${n} en la tira` : "";
}

/* ---------- aplicar solo ---------- */

function tocar(clave) {
    const i = seleccion.indexOf(clave);
    if (i >= 0) seleccion.splice(i, 1);
    else if (clave === "arcoiris") seleccion = ["arcoiris"];     // el arcoíris va solo
    else seleccion = [...seleccion.filter(c => c !== "arcoiris"), clave];  // se suma al final
    pintarMuestras();
    programar("colores", ESPERA_COLOR_MS);
}

function programar(que, espera) {
    pendiente[que] = true;
    clearTimeout(temporizador);
    temporizador = setTimeout(correr, espera);
}

function argumentos() {
    const mov = [`girar:${$("girar").value}`, `respira:${$("respira").value}`];
    if (!seleccion.length) return ["apagar"];
    if (seleccion[0] === "arcoiris") return ["arcoiris", ...mov];
    return ["paleta", ...seleccion, ...mov];
}

async function correr() {
    if (corriendo) return;              // al terminar, vuelve a mirar si hay algo pendiente
    corriendo = true;
    $("estado-sub").textContent = "aplicando…";
    try {
        while (pendiente.colores || pendiente.brillo) {
            const tarea = pendiente;
            pendiente = { colores: false, brillo: false };
            // El brillo primero: `luces` lo guarda y la paleta que sigue ya lo usa.
            if (tarea.brillo) await luces("brillo", $("brillo").value);
            if (tarea.colores) await luces(...argumentos());
        }
        error(null);
    } catch (e) {
        error("No se pudo: " + (e.message || e));
    } finally {
        corriendo = false;
        await leer();
    }
}

$("apagar").addEventListener("click", () => {
    seleccion = [];
    pintarMuestras();
    programar("colores", 0);
});
$("reglas-activas").addEventListener("change", cambiarReglasActivas);
$("regla-agregar").addEventListener("click", () => {
    const usados = new Set(reglas.reglas.map(r => r.id));
    let n = 1; while (usados.has(`regla-${n}`)) n += 1;
    reglas.reglas.push({ id: `regla-${n}`, evento: "aviso_error", activa: true, tipo: "toque",
        color: "rojo", animacion: "destello", nivel: 5, repetir: 1, dura_s: 5, cada_s: 0, prioridad: 3 });
    reglasSucias = true; versionReglas += 1; pintarReglas(); programarReglas($("tabla-reglas").lastElementChild);
});
$("reglas-defecto").addEventListener("click", async () => {
    try {
        reglas = configuracionDefecto(reglasEstanActivas(reglas));
        reglasSucias = true; versionReglas += 1;
        await cockpit.spawn([LUCES, "reglas", "guardar"], { err: "message" }).input(JSON.stringify(reglas));
        reglasSucias = false; pintarReglas(); error(null);
    } catch (e) { error("No pude volver a los valores por defecto: " + textoReglasSeguro(e.message || e)); }
});
$("horario-agregar").addEventListener("click", () => {
    reglas.horario_brillo.push({ hora: "12:00", brillo: 75 }); reglasSucias = true; versionReglas += 1; pintarReglas();
    programarReglas($("tabla-horario").lastElementChild);
});
for (const id of ["girar", "respira", "brillo"]) {
    $(id).addEventListener("input", rotular);
    // Al SOLTAR, no en cada paso: cada aplicación reinicia la animación.
    $(id).addEventListener("change", () => programar(id === "brillo" ? "brillo" : "colores", 150));
}

barraNodo.alActualizar(leer);

cockpit.transport.wait(() => {
    leer();
    // La temperatura y el ventilador pasaron a 🍇 → Estado (encargo 18): acá ya no hay
    // nada que cambie solo cada 5 s. Se vuelve a leer cada medio minuto por si alguien
    // cambió las luces por otro lado (el bot, la terminal); Actualizar lo hace al tiro.
    setInterval(() => { if (!document.hidden && !corriendo) leer(); }, 30000);
});
