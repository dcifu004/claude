---
tipo: guía
proyecto: ProyectoPi5
actualizado: 2026-10-23
estado: VIGENTE. Se actualiza en cada encargo que agregue o cambie una función del bot (regla del 19-10).
---

# 35 — Guía de uso de Jaime y Pilar

> Qué se le puede pedir a cada bot, con comando y con voz, y hasta dónde llega cada función.
> **Mantenimiento:** todo encargo que agregue, quite o cambie una función de `botv3` actualiza
> esta guía (tabla y «lo que no está todavía») y la vuelve a enviar. Origen: plan
> [[34 - Comandos del bot y voz de sala (plan)]].

**Regla general:** los comandos «/» **se escriben**. Lo que se dicta nunca se ejecuta como
comando: por voz se usa la frase natural. Hoy la voz es la nota de voz de Telegram. Cuando lleguen
el micrófono y el parlante, son las mismas frases con «Hola Jaime» o «Hola Pilar» al principio.

- **Jaime** = bot de Diego (`@Dcs_v3bot`).
- **Pilar** = bot de Camila. No tiene agenda ni correo, porque su cuenta de Google no está conectada.

| Función | Comando «/» | Por voz (frase natural) | Ejemplos | Alcance |
|---|---|---|---|---|
| 🏠 **Menú** | `/menu` | — (es sólo botones) | `/menu` → Compras · Gastos · Google · Temporizadores · Órdenes · Buscar · Clima · Estado · Uso · Remote Control (Jaime) · Ayuda | Jaime y Pilar (Pilar sin Google ni Remote Control). Cada botón hace lo mismo que su comando; Clima, además, manda la imagen de 3 días |
| 🛒 **Compras** | `/compras`, `/compras agrega…`, `/compras saca…`, `/compras listo` | «falta leche», «agrégame pan y huevos», «qué hay en la lista», «saca el pan» | `/compras` abre la lista con botones · «se acabó el café» · «mándale la lista a Camila» | Lista compartida de la casa (los dos bots). Agregar es directo, incluso por voz; sacar, terminar, vaciar y deshacer piden un botón. Por voz lee hasta 5 ítems; el resto va al chat. Todo local, sin IA |
| 💳 **Gastos** | `/gastos` (saldo + ➕ Anotar / 🧾 Últimos), `/gastos 15000 feria, 50/50` | «gasté 15 lucas en la feria», «anota un gasto de quince mil en el súper, paga Cami» | «pagué mil quinientos de estacionamiento» · `/gastos 8000 farmacia, fecha 18/10` | Jaime (paga Diego por defecto) y Pilar (paga Cami). **Siempre termina en ✅ Anotar**: nada se escribe sin tu toque. Por voz sólo dice «te dejé el gasto para confirmar en el chat»; montos y saldo nunca se dicen. Sin monto no es un gasto («anota leche» va a compras). Tope: $10.000.000 |
| 📅 **Agenda** | `/google` (botones Hoy · Mañana · Semana · Próximo · ➕ Evento), `/google <pedido>` | «qué tengo mañana», «cuál es mi próxima reunión», «a qué hora es la reunión con Pedro», «agenda dentista el jueves a las 4» | «tengo algo el viernes» · «cuándo es el dentista» · `/google crea una reunión el lunes a las 10` | **Sólo Jaime.** Consultar no usa IA y es instantáneo. Crear evento o borrador pide ✅. Por voz dice cuántos eventos hay y la hora y el título del primero; el lugar y el resto van al chat (se apaga con `voz_habla_agenda`). No mueve ni borra eventos |
| ✉️ **Correo** | `/google` → ✉️ No leídos · 📝 Borrador | «tengo correos nuevos», «me escribió Juan» | «algún correo de la constructora» · `/google deja un borrador a x@y.cl…` | **Sólo Jaime.** Lee remitente, asunto y extracto; no lee el cuerpo. Por voz sólo dice cuántos. Enviar no existe: sólo borradores con ✅ |
| 🔎 **Buscar** | `/buscar <consulta>` o `/menu` → 🔎 Buscar | — (se escribe) | `/buscar feriados Chile 2026` | Jaime y Pilar. Busca con SearXNG local, sin IA ni acceso a vaults, y muestra hasta 5 resultados con título, dominio, fecha si existe y enlace. Si el buscador está apagado, lo avisa; no envía la consulta a ningún contador. |
| 🌦️ **Clima** | `/menu` → 🌦️ Clima | «va a llover hoy», «cómo va a estar mañana», «hace frío afuera», «va a llover mañana en Puerto Montt», «cambia la comuna del clima a Ñuñoa» | «qué temperatura va a hacer mañana» · «el pronóstico de la semana» · «clima en Ñuñoa» · «pon el clima de Valdivia» · «restablece la comuna del clima» | Jaime y Pilar, **en Las Condes o la comuna que elijan** (Open-Meteo, caché de 30 min, sin IA). **Otra comuna, una vez:** «clima en Ñuñoa», «el pronóstico de la semana en Valdivia», «cómo va a estar mañana en Isla de Pascua»; contesta en texto y no cambia nada. Sirve sólo con el nombre exacto de una comuna de Chile (tabla local de 345; lo que se dice nunca sale a internet): «clima en Buenos Aires» sigue la ruta de siempre. **Cambiar la comuna fija:** «cambia la comuna del clima a Ñuñoa», «el clima de ahora en adelante en Viña del Mar», o el botón «📍 Comuna» bajo la imagen (compartir la ubicación —vale 10 min—, escribir la comuna o «Volver a Las Condes»); **siempre pide ✅**. Con un nombre a medias («Puerto», «San») muestra hasta 6 comunas para elegir. De la ubicación se guarda sólo la comuna más cercana y el punto redondeado (≈ 1 km). «vuelve el clima a Las Condes» o «restablece la comuna del clima» vuelven al lugar de siempre. La imagen, su pie («📍 Ñuñoa»), las frases y el aviso usan la comuna elegida, por bot (la de Jaime no cambia la de Pilar). **El botón manda una imagen de hoy, mañana y pasado** (cuándo llueve, hora a hora, con horarios aproximados «~12:15») y un pie de dos líneas; si la imagen no se puede hacer, manda el texto de «clima hoy». **Debajo de la imagen, «⏰ Programar aviso»**: «L–V 7:30 · S–D 10:00», «Todos los días 8:00» u «Otro horario…»; con un aviso puesto, el pie suma «⏰ Aviso: lun–vie 7:30 · sáb–dom 10:00» y los botones «Cambiar» y «Pausar»/«Reanudar». **El aviso llega solo, a esa hora, como la misma imagen** (nunca por el parlante); los feriados usan el horario de fin de semana. También se pide escrito o dictado: «mándame el clima de lunes a viernes a las 7:30», «avísame el clima los fines de semana a las 10»; «pausa el aviso del clima», «qué avisos de clima tengo». Las frases escritas o dictadas siguen en texto. Se dice completo por voz, salvo la semana, que va al chat. «temperatura del living» sigue yendo a Home Assistant; «clima laboral», a la ruta de siempre |
| 🕐 **Hora y fecha** | — | «qué hora es», «qué día es hoy» | → «Son las 7 y 20 de la tarde» · «Hoy es martes 21 de octubre» | Jaime y Pilar. Instantáneo y local |
| ⏰ **Temporizadores** | `/temporizadores` (`/timer 10 min tallarines`, `/alarmas`) | «temporizador de 10 minutos para los tallarines», «cuánto le queda», «cancela el de los huevos» | «avísame en 20 minutos» · «alarma a las 7 de la mañana» · «agrega 5 minutos» | Cada bot ve sólo los suyos. Cancelar no pide confirmación. Hoy el aviso llega por Telegram; con el parlante, va a sonar. Máximo 10 activos, de 5 s a 24 h |
| 🔁 **Órdenes que se repiten** | `/ordenes` (pausar, reanudar, borrar, renovar) | «despiértame de lunes a viernes a las 6:30», «cada domingo recuérdame regar» | «pausa la alarma de los lunes» · «cada 2 horas recuérdame tomar agua» | Por voz, **crear pide ✅** en el chat; escrita, se crea con botón ↩️ Deshacer. Pausar y borrar se pueden deshacer durante una hora. Los avisos del clima salen acá con 🌦️ («🌦️ Clima · lun–vie 7:30», «🌦️ Clima · sáb–dom 10:00 (feriados también)») y los mismos botones |
| 🩺 **Estado del nodo** | `/estado` | «cómo está la Pi» | — | Diagnóstico de la Pi. Por voz dice la versión corta; el detalle va escrito |
| 💳 **Uso de cuotas** | `/uso` | «cuánta cuota queda» | — | Cuota de Claude y Codex. **Sólo escrito** (decisión del 19-10) |
| 📱 **Remote Control** | `/remoto` | — | `/remoto` → Abrir Remote Control (8 h) · ⏹ Cerrar ahora | **Sólo Jaime.** Abre una sesión de Claude en la Pi para verla en la app de Claude → Code del teléfono. Tiene permiso `acceptEdits`, vence sola a las 8 h y se puede cerrar antes. El bot sólo pide la acción; no ejecuta Claude ni servicios. |
| 🧠 **Memoria de la casa** | — | «guardar en memoria que la llave de paso está bajo el lavaplatos» | — | Propone y se guarda sólo con ✅ en el chat |
| ❓ **Ayuda** | `/ayuda`, `/acciones` | — | — | Texto completo de uso y límites. «qué puedes hacer» por voz llega con el parlante |
| 💬 **Pregunta libre** | `/cami`, `/codex`, `/diego <pregunta>` | cualquier otra pregunta, o «pregúntale a Codex…» | «cómo se dice cuchara en inglés» · «pregúntale a Claude qué dice el contrato X» | Va al clasificador. Las respuestas rápidas se dicen por voz; las que leen tus archivos o la web van **siempre al chat** |
| 📨 **Mensajes de las IA** | — (los manda Claude o Codex con `mensaje`) | — | «📨 Para Pilar, de Claude (Diego): te mando la guía» en Jaime · después «🤖 Claude (Diego) te manda:» y el documento en Pilar | A **Jaime**, directo. A **Pilar**, **sólo con ✅ de Diego**: la vista previa llega a Jaime y el botón ✅ a @Dcs_v5bot; sin ✅ no sale nada y vence en 30 min. Documentos **sólo desde `vault_personal`** (pdf, png, jpg, webp, md, txt, html; hasta 20 MB), nunca del vault laboral. Pilar no ejecuta nada de lo que llega: lo publica |

## Lo que no está todavía

- Google (agenda y correo) en Pilar.
- Mover o borrar eventos.
- Avisos antes de una reunión (llegan con el parlante).
- «Repite», «cancela» y «qué puedes hacer» por voz (llegan con el parlante).
- El parlante y el micrófono de sala (diseños 15 y 25).

## Historial

- **19-10-2026:** primera versión, después de los encargos 61 y 64–69: `/menu`, gastos por voz, agenda y
  correo locales, clima y hora.
- **19-10-2026 (encargo 70):** fila 📨 *Mensajes de las IA*: a Jaime directo; a Pilar, mensajes y
  documentos de `vault_personal` sólo con ✅ de Diego (`mensaje --a pilar`).
- **20-10-2026 (encargo 73):** fila 📱 *Remote Control*: `/remoto` sólo en Jaime, con apertura
  máxima de 8 h y cierre manual.
- **23-10-2026 (encargo 78b):** fila 🔎 *Buscar*: `/buscar <consulta>` y botón para Jaime y
  Pilar, con SearXNG local y sin IA.
