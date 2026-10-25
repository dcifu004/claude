---
tipo: guía
proyecto: ProyectoPi5
actualizado: 2026-10-25
estado: VIGENTE. Se actualiza en cada encargo que agregue o cambie una función del bot (regla del 19-10).
---

# 35 — Guía de uso de Jaime y Pilar

> Qué se le puede pedir a cada bot, con comando y con voz, y hasta dónde llega cada función.
> **Mantenimiento:** todo encargo que agregue, quite o cambie una función de los bots actualiza
> esta guía (tabla, sección de Pilar y «Próximamente») y la vuelve a enviar. Origen: plan
> [[34 - Comandos del bot y voz de sala (plan)]].

**Regla general:** los comandos «/» **se escriben**. Lo que se dicta nunca se ejecuta como
comando: por voz se usa la frase natural. Hoy la voz es la nota de voz de Telegram; antes de
contestar, el bot muestra «🎤 Entendí: …» con lo que entendió. Cuando lleguen el micrófono y el
parlante, son las mismas frases con «Hola Jaime» o «Hola Pilar» al principio.

**Lo que pide ✅:** gastos y boletas, crear eventos y borradores, cambiar la comuna del clima, sacar
cosas o terminar la compra, las órdenes dictadas por voz, guardar en memoria y los mensajes de las IA
a Pilar. Nada de eso se escribe sin tu toque.

- **Jaime** = bot de Diego (`@Dcs_v3bot`).
- **Pilar** = bot de Camila. Ver «Pilar (Camila)» más abajo.

| Función | Comando «/» | Por voz (frase natural) | Ejemplos | Alcance |
|---|---|---|---|---|
| 🏠 **Menú** | `/menu` | — (son botones) | `/menu` → Compras · Gastos · Google (Jaime) · Temporizadores · Órdenes · Buscar · Clima · Estado · Uso · Remote Control (Jaime) · Ayuda | Cada botón hace lo mismo que su comando. En Pilar no aparecen Google ni Remote Control. Clima, además, manda la imagen de 3 días |
| 🛒 **Compras** | `/compras`, `/compras agrega…`, `/compras saca…`, `/compras listo` | «falta leche», «agrégame pan y huevos», «qué hay en la lista», «saca el pan» | «se acabó el café» · «hay que comprar tomates» · «mándale la lista a Camila» · `/compras leche, pan y huevos` (sin verbo: pregunta antes de anotar) | Una sola lista para la casa: la ven y la escriben los dos bots. **Agregar es directo**, incluso por voz; sacar, terminar la compra, vaciar y deshacer **piden un botón**. Se ve como una lista para marcar: marcar no borra, y «Terminar compra» guarda el historial. Por voz lee hasta 5 cosas; el resto va al chat. Aguanta un error de tipeo en el verbo («agrgar»). «El carrito» y «la lista del súper» son la lista; «el carro» no, porque es el auto. Se resuelve en la casa, sin IA |
| 💳 **Gastos** | `/gastos` (saldo + ➕ Anotar / 🧾 Últimos), `/gastos 15000 feria, 50/50` | «gasté 15 lucas en la feria», «anota un gasto de quince mil en el súper, paga Cami» | «pagué mil quinientos de estacionamiento» · `/gastos 8000 farmacia, fecha 18/10` | Paga Diego por defecto en Jaime y Cami en Pilar. **Siempre termina en ✅ Anotar**: nada se escribe sin tu toque. Por voz sólo dice «Te dejé el gasto para confirmar en el chat»; los montos y el saldo nunca se dicen en voz alta. Sin monto no es un gasto («anota leche» va a compras). Tope: $10.000.000 |
| 🧾 **Boleta por foto** | — (se manda la foto) | — | una foto o un PDF de la boleta, sin texto o con «boleta» en el pie | Prepara la fila del gasto con lo que lee de la boleta y **la anota sólo cuando tocas ✅**; antes se pueden corregir la fecha y el monto. Una foto con otro pie no se lee: hoy ninguno de los dos bots tiene activa la lectura de fotos en general |
| 📅 **Agenda** | `/google` (botones Hoy · Mañana · Semana · Próximo · ➕ Evento), `/google <pedido>` | «qué tengo mañana», «cuál es mi próxima reunión», «a qué hora es la reunión con Pedro», «agenda dentista el jueves a las 4» | «tengo algo el viernes» · «cuándo es el dentista» · `/google crea una reunión el lunes a las 10` | **Sólo Jaime.** Consultar es instantáneo y sin IA. **Crear un evento o un borrador pide ✅.** Por voz dice cuántos eventos hay y la hora y el título del primero; el lugar y el resto van al chat. No mueve ni borra eventos |
| ✉️ **Correo** | `/google` → ✉️ No leídos · 📝 Borrador | «tengo correos nuevos», «me escribió Juan» | «algún correo de la constructora» · `/google deja un borrador para …` | **Sólo Jaime.** Muestra remitente, asunto y un extracto; no lee el correo entero. Por voz sólo dice cuántos hay. **Enviar no existe**: sólo deja borradores, con ✅ |
| 🔎 **Buscar** | `/buscar <consulta>` o `/menu` → 🔎 Buscar | — (se escribe) | `/buscar feriados Chile 2026` | Busca en internet con el buscador propio de la casa, sin IA y sin mirar tus archivos. Muestra hasta 5 resultados con título, sitio, fecha si la hay y enlace. Si el buscador está apagado, lo dice. Lo que buscas no queda guardado |
| 🌦️ **Clima** | `/menu` → 🌦️ Clima | «va a llover hoy», «cómo va a estar mañana», «hace frío afuera», «va a llover mañana en Puerto Montt», «cambia la comuna del clima a Ñuñoa» | «qué temperatura va a hacer mañana» · «el pronóstico de la semana» · «clima en Ñuñoa» · «pon el clima de Valdivia» · «restablece la comuna del clima» | En Las Condes **o la comuna que elijan**, sin IA. **Otra comuna, una vez:** «clima en Ñuñoa», «el pronóstico de la semana en Valdivia»; contesta en texto y no cambia nada. Sirve con el nombre exacto de una comuna de Chile (las 345 están en la casa; lo que se dice no sale a internet): «clima en Buenos Aires» sigue el camino de una pregunta normal. **Cambiar la comuna fija:** «cambia la comuna del clima a Ñuñoa», «el clima de ahora en adelante en Viña del Mar», o el botón «📍 Comuna» bajo la imagen (compartir la ubicación —vale 10 min—, escribir la comuna o «Volver a Las Condes»); **siempre pide ✅**. Con un nombre a medias («Puerto», «San») muestra hasta 6 comunas para elegir. De la ubicación se guarda sólo la comuna más cercana. Cada bot tiene la suya: la de Jaime no cambia la de Pilar. **El botón manda una imagen de hoy, mañana y pasado** (cuándo llueve, hora a hora, con horarios aproximados «~12:15») y un pie de dos líneas; si la imagen no se puede hacer, manda el texto del clima de hoy. **Debajo de la imagen, «⏰ Programar aviso»**: «L–V 7:30 · S–D 10:00», «Todos los días 8:00» u «Otro horario…»; con un aviso puesto aparecen «Cambiar» y «Pausar»/«Reanudar». **El aviso llega solo, a esa hora, como la misma imagen**; los feriados usan el horario de fin de semana. También se pide escrito o dictado: «mándame el clima de lunes a viernes a las 7:30», «pausa el aviso del clima», «qué avisos de clima tengo». Las frases siguen en texto y se dicen por voz, salvo la semana, que va al chat. «temperatura del living» sigue yendo a la casa (sensores); «clima laboral», a una pregunta normal |
| 🕐 **Hora y fecha** | — | «qué hora es», «qué día es hoy» | → «Son las 7 y 20 de la tarde» · «Hoy es martes 21 de octubre» | Instantáneo y sin internet |
| ⏰ **Temporizadores** | `/temporizadores` (`/timer 10 min tallarines`, `/alarmas`) | «temporizador de 10 minutos para los tallarines», «cuánto le queda», «cancela el de los huevos» | «avísame en 20 minutos» · «alarma a las 7 de la mañana» · «agrega 5 minutos» | Cada bot ve sólo los suyos. Cancelar no pide confirmación. Hoy el aviso llega por Telegram; con el parlante, va a sonar. Hasta 10 activos, de 5 segundos a 24 horas |
| 🔁 **Órdenes que se repiten** | `/ordenes` (pausar, reanudar, borrar, renovar) | «despiértame de lunes a viernes a las 6:30», «cada domingo recuérdame regar» | «pausa la alarma de los lunes» · «cada 2 horas recuérdame tomar agua» · «… por 2 semanas» · «… hasta fin de mes» | Por voz, **crear pide ✅** en el chat; escrita, se crea y trae ↩️ Deshacer. Pausar, reanudar y borrar no piden confirmación y se pueden deshacer durante una hora. Hasta 10 por bot, y como mucho una cada hora (más seguido es un temporizador). Los avisos del clima aparecen acá con 🌦️ y los mismos botones |
| 🩺 **Estado del nodo** | `/estado` | «cómo está la Pi» | — | Cómo está la Pi de la casa. Por voz dice la versión corta; el detalle va escrito |
| 💳 **Uso de cuotas** | `/uso` | «cuánta cuota queda» | — | Cuánto queda de las cuentas de Claude y de Codex. **La respuesta es escrita**, también si se pregunta por voz (decisión del 19-10) |
| 📱 **Remote Control** | `/remoto` | — | `/remoto` → Abrir Remote Control (8 h) · ⏹ Cerrar ahora | **Sólo Jaime.** Abre una sesión de Claude en la Pi para seguirla desde la app de Claude en el teléfono. Mientras está abierta, Claude puede editar archivos sin preguntar cada vez. Vence sola a las 8 h y se puede cerrar antes. El bot sólo deja el pedido: no la maneja |
| 🧠 **Memoria de la casa** | — | «guardar en memoria que la llave de paso está bajo el lavaplatos» | — | Nada se guarda al decirlo: llega al chat con el texto tal cual y los botones 🏠 De la casa · 👤 Mía · ✖️ Descartar. Si no se toca ninguno, vence a los 10 minutos |
| 💬 **Pregunta libre** | `/cami`, `/codex`, `/diego <pregunta>` | cualquier otra pregunta, o «pregúntale a Codex…», «que conteste Claude (Cami)…» | «cómo se dice cuchara en inglés» · «¿y mañana?» (sigue el hilo) · en Jaime: «pregúntale a Claude qué dice el contrato X» | Se elige sola quién contesta, y la respuesta dice por dónde fue. Si la cuenta pedida no está en ese bot, contesta la de siempre y lo dice. Las respuestas rápidas se dicen por voz; las que leen archivos o la web van **siempre al chat**. Recuerda el hilo: hasta 10 turnos, y se corta solo tras 15 minutos sin hablar; `/olvidar` lo corta antes. Debajo de algunas respuestas hay 👍 / 👎 para calificarla. **Jaime** lee los archivos personales y del trabajo de Diego y su Drive; **Pilar** no lee archivos de nadie |
| 📨 **Mensajes de las IA** | — (los manda Claude o Codex) | — | «📨 Para Pilar, de Claude (Diego): te mando la guía» en Jaime · después «🤖 Claude (Diego) te manda:» y el documento en Pilar | A **Jaime**, directo. A **Pilar**, **sólo con ✅ de Diego**: la vista previa llega a Jaime y el botón ✅ al bot de avisos (@Dcs_v5bot); sin ✅ no sale nada y vence en 30 min. Documentos sólo de los archivos personales (pdf, imágenes, texto; hasta 20 MB), nunca de los del trabajo. Pilar no ejecuta nada de lo que llega: lo muestra |
| ❓ **Ayuda** | `/ayuda`, `/acciones` | — | — | La ayuda completa y el alcance y los límites de ese bot. «qué puedes hacer» por voz llega con el parlante |

## Pilar (Camila)

**Tiene:**

- La misma lista de compras de la casa que Jaime.
- Gastos y boletas, con Cami como quien paga por defecto.
- Buscar, clima (con su propia comuna y su propio aviso), hora y fecha.
- Sus propios temporizadores y órdenes: no ve los de Jaime, ni Jaime los suyos.
- Estado del nodo, uso de cuotas, memoria (🏠 De la casa o 👤 Mía) y ayuda.
- Preguntas libres con Claude (Cami) y Codex, sin leer archivos.
- Mensajes y documentos de las IA, sólo con ✅ de Diego.

**No tiene:**

- Agenda y correo (su cuenta de Google no está conectada).
- Remote Control.
- Leer archivos o el Drive.

## Próximamente

- Agenda y correo en Pilar.
- Mover o borrar eventos.
- Avisos antes de una reunión (llegan con el parlante).
- «Repite», «cancela» y «qué puedes hacer» por voz (llegan con el parlante).
- El parlante y el micrófono de sala.
- Mercado Libre: vigilar el precio de un producto y avisar cuando baje. Está hecho, pero todavía no consta encendido en los bots.

## Historial

- **19-10-2026:** primera versión, después de los encargos 61 y 64–69: `/menu`, gastos por voz, agenda y correo locales, clima y hora.
- **19-10-2026 (encargo 70):** fila 📨 *Mensajes de las IA*: a Jaime directo; a Pilar, sólo con ✅ de Diego.
- **20-10-2026 (encargo 73):** fila 📱 *Remote Control*: `/remoto` sólo en Jaime, hasta 8 h y con cierre manual.
- **23-10-2026 (encargo 78b):** fila 🔎 *Buscar*: `/buscar <consulta>` y botón para Jaime y Pilar, sin IA.
- **25-10-2026 (encargo 93):** revisada contra lo que hacen hoy los bots: filas nuevas 🧾 *Boleta por foto*; en *Pregunta libre*, el hilo de 10 turnos, `/olvidar` y 👍/👎; en *Órdenes*, los límites; sección *Pilar (Camila)*; Mercado Libre en *Próximamente*; sin nombres internos.
