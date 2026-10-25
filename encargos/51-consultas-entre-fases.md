# Encargo 51: consultas al usuario entre fases, versión mínima (Claude (Diego), 12-10-2026)

Naturaleza `seguridad`. **Alcance mínimo**, elegido por el usuario el 12-10. La ampliación
prevista es el botón «Comentar», ver y contestar la consulta en 🧵, y preguntas del autor antes
de escribir.

## Valor y costo

Varias vueltas caras salieron de dudas que el usuario contestaba en segundos: la 46a, la 36 y la
43b. Cada vuelta evitada ahorra ~17 % de la ventana de 5 h de Claude (Cami) y horas de espera.
Pronóstico: 1 etapa, ~6–8 % semanal de Claude (Cami).

## Decisiones del usuario (cerradas el 12-10)

- **Cuándo se pregunta:** al terminar una revisión NO DESPLEGABLE **sin ningún grave de
  seguridad ni de datos**, es decir, sólo con hallazgos medios o bajos, de alcance o de
  atribución.
- **Preguntas cerradas:** «Aceptar y seguir», «Que lo arregle» y «Saltar».
- **«Saltar»** estaciona la cola en el estado `en_consulta`, la cadena sigue con la siguiente,
  y la cola se retoma con `cola-run.py --accion reanudar` (46c) cuando llega la respuesta.
- **Plazo de 2 h.** La cola queda estacionada apenas pregunta. Al vencer el plazo se aplica el
  defecto: **saltar** si hay otras colas esperando, **arreglar** si es la última.
- **Un grave nunca se salta ni se acepta:** va al arreglo, como hoy.
- **Tope:** 2 preguntas por cola. **Sólo contesta el usuario** (su chat).
- **«Modo descanso»** (encargo 52): en descanso no se pregunta y se aplica el defecto en
  silencio.

## Leer primero

- `encargos/52-RESULTADO.md`: `en_descanso()` y cómo se encolan los avisos.
- En `encargos/cola-run.py`:
  - dónde se lee el veredicto de una revisión y se decide el arreglo;
  - `--accion` (46c);
  - `despacho.json` (50a);
  - el diff propio (53).
- **Premisa por comprobar primero:** ¿cómo llegan hoy los botones ✅ de `nodo-desplegar pedir` y
  quién recibe la respuesta? Busca el mecanismo en el vault, sin tocar `nodo-desplegar`.
  - Si hay una vía sin root para recibir la respuesta de un botón, se usa.
  - **Si no la hay, el supuesto alternativo es una respuesta por texto**:
    `/consulta <cola> aceptar|arreglar|saltar`, leída por el mismo canal por el que hoy llegan
    los mensajes al nodo.
  - Lo que se encontró, con su `grep` y su salida, va en el RESULTADO antes de construir.
- `encargos/trampas.md`: «Cola y encargos».

**No toques** `nodo-desplegar` ni el router de `botv3`. Si la única vía exige tocarlos, detente y
déjalo escrito en el RESULTADO.

## Qué hacer

1. **En la cola:**
   - el disparador, con la gravedad tomada de los títulos `[Grave]`, `[Media]` y `[Baja]` del
     resultado de la revisión;
   - la pregunta **la arma la cola** con esos títulos (nunca el agente), con un tope de 600
     caracteres;
   - el estado `en_consulta` en `vivo`, con la pregunta, el plazo y el defecto;
   - `encargos/<id>-decisiones.md` con cada respuesta (quién, cuándo y qué), que reciben el autor
     y el revisor siguientes. Una regla nueva en la plantilla dice que lo decidido no se vuelve a
     marcar.
2. **Al contestar:**
   - «aceptar» marca la etapa como aceptada por el usuario y sigue con la siguiente etapa o con
     el despliegue (el despliegue igual pide su ✅);
   - «arreglar» sigue con el arreglo;
   - «saltar» deja la cola estacionada.
   Las respuestas que no vienen del chat del usuario se ignoran y se anotan.
3. **Al vencer el plazo** (un timer de usuario o la cadena misma; elige y justifica): se aplica
   el defecto según si hay más colas esperando.

## Criterios de aceptación

- C1. **Disparador:**
  - una revisión con sólo `[Media]` y `[Baja]` pregunta;
  - una con un `[Grave]` no pregunta y va al arreglo;
  - una tercera pregunta en la misma cola no se hace (tope de 2).
- C2. Con `en_descanso()` en verdadero no se pregunta y se aplica el defecto (reloj inyectado).
- C3. **Las tres respuestas** dejan el estado correcto y la línea en `decisiones.md`. Una respuesta
  que no viene del chat del usuario se ignora.
- C4. **Plazo vencido:** con otras colas esperando → `en_consulta` (saltar); siendo la última →
  arreglo.
- C5. Una «aceptación» no salta el ✅ del despliegue, ni lo pide si la etapa tocó root o secretos.
- C6. La premisa del canal (botón o texto) está en el RESULTADO con su evidencia.
- C7. `encargos/test_consultas.py` (nuevo) y las suites del manifiesto pasan. El RESULTADO dice
  cada criterio cumplido o no, con su salida.

## Invariantes

- **Archivos compartidos:** `vivo` y `despacho.json`, con escritura atómica; `decisiones.md` por
  anexado con `flock`.
- **Pruebas:** canal de Telegram falso, `tmp_path`, reloj inyectado, sin colas reales y sin
  avisos reales.
- **Entradas hostiles:**
  - la respuesta se valida contra una lista cerrada;
  - el nombre de la cola, con el mismo patrón de la 46c;
  - el texto de la pregunta sale de los títulos, escapado.
- **Root:** ninguna. Una respuesta nunca autoriza root, secretos ni ampliar el alcance.

## Reglas

- **Un arreglo no agrega funciones nuevas.**
- No cambies la pausa por cuota, el despacho, el diff de la 53 ni la fase `plan` de la 54.
- Cuentas siempre como «Claude (Diego)», «Claude (Cami)» y «Codex». Sin buscador web.

## Fuera de alcance

«Comentar», la vista en 🧵 y las preguntas del autor (ampliación prevista).

## Resultado

`encargos/51-RESULTADO.md` con la premisa del canal, los cambios y C1–C7 uno por uno.
