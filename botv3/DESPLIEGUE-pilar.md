---
tipo: procedimiento
proyecto: ProyectoPi5
actualizado: 2026-09-13
estado: DESPLEGADO y verificado
---

# Despliegue de `botv3@pilar` — Fase 1 del diseño 15

> ✅ **Desplegado el 2026-09-13 21:22 y con el aislamiento comprobado.**
> `botv3@pilar` activo con `@Pilar_v2bot`, perfil `pilar`, usuario `botpilar`, rutas
> `claude, gpt, ha, web` y **ningún vault**. `@Dcs_v3bot` reiniciado sobre el
> `botv3.py` nuevo y andando con sus dos vaults y sus seis rutas.
> Respaldo del código anterior en
> `datos/botv3/deploy-backups/perfiles-20260913_212117`.

> ⚠️ **Syncthing sincroniza el vault, no `/etc` ni `/opt`** — es la tercera vez que este
> proyecto se tropieza con lo mismo, así que cada paso termina verificando **en el
> destino**.

## Tres cosas que se aprendieron desplegándolo

1. **`InaccessiblePaths` NO borra la ruta: monta encima un nodo con permisos 000.** La
   ruta **sigue existiendo** y `Path.exists()` devuelve `True`. La primera versión de la
   guarda de arranque preguntaba eso y el servicio **no levantó**, acusando a la unidad de
   estar mal desplegada cuando la unidad estaba bien. La pregunta correcta es si se puede
   **listar**, no si está.
2. **`sudo ls /proc/<pid>/root/<ruta>` es una prueba ambigua.** root atraviesa un
   directorio 000 igual, así que una ruta enmascarada se lista **vacía** en vez de dar
   error — indistinguible de un directorio realmente vacío. La prueba que concluye es
   entrar al namespace *y* dejar de ser root:
   `sudo nsenter -t <pid> -m -- runuser -u botpilar -- ls <ruta>`
3. **`casa.md` no existe todavía** y `nodo-memoria/` estaba `drwxr-x--- dcifu004:captura`,
   o sea invisible para `botpilar`. Se abrió con `chmod o+rx` sobre el **directorio**, no
   metiendo `botpilar` al grupo `captura` — eso le habría dado de yapa el `captura.env`.
   ⚠️ Cuando se cree `casa.md`, tiene que quedar **644**: con la `UMask=0077` del bot
   nacería `600` y Camila no lo vería.

## Alcance, y lo que deliberadamente NO se hace

Se levanta **sólo el perfil `pilar`** sobre la unidad plantilla. **`@Dcs_v3bot` sigue en
su `botv3.service` dedicado y no se toca.** Migrarlo a `botv3@jaime` es la Fase 1b, y
sólo después de que la plantilla haya funcionado con Camila una semana: una etapa a la
vez, y la que puede romper el bot que ya usás todos los días va última.

Consecuencia práctica: `jaime.toml` existe y lo carga el `botv3.py` nuevo —por eso las
pruebas lo cubren— pero la unidad que lo consume todavía es la vieja.

## Lo que ya está hecho

| | |
|---|---|
| Bot | `@Pilar_v2bot`, bot id `8951022717`, nombre visible `PI-lar` |
| Dueño en BotFather | **Camila** — puede regenerar el token o borrar el bot |
| `chat_id` = `user_id` | `8935354372` |
| Token | `/opt/nodo/datos/secretos/botv3-pilar.env`, `640 root:captura` |
| Cuenta de Claude | `<correo-camila>`, **con plan pagado** (confirmado 13-09-2026) |

## 1. El usuario Unix

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin botpilar
```

**No se agrega a ningún grupo, y eso es a propósito.** El token lo lee systemd (PID 1)
por `EnvironmentFile=` **antes** de armar el namespace, así que llega igual aunque
`secretos/` esté en `InaccessiblePaths` y aunque `botpilar` no tenga permiso de leerlo.
Si se lo metiera al grupo `captura` para "que pueda leer su `.env`", de paso podría leer
`captura.env`, que tiene el token del bot personal y la `GROQ_API_KEY`.

## 2. El directorio de estado

```bash
sudo install -d -o botpilar -g botpilar -m 0700 /opt/nodo/datos/botv3-pilar
sudo install -d -o botpilar -g botpilar -m 0700 /opt/nodo/datos/botv3-pilar/claude-config
```

**Hermano de `botv3`, no anidado.** Si colgara de él, enmascarar el directorio del otro
perfil taparía también el `ReadWritePaths` propio. Y el `0700` es la segunda capa: el
aislamiento no depende sólo de systemd.

## 3. Completar el `.env`

Los tres valores no secretos:

```bash
printf "BOTV3_STATE_DIR=/opt/nodo/datos/botv3-pilar\nBOTV3_SCHEMA=/opt/botv3/proposal.schema.json\n" | sudo tee -a /opt/nodo/datos/secretos/botv3-pilar.env
```

Y los que se copian del `.env` de Jaime **sin que pasen por pantalla** — `GROQ_API_KEY`
(transcripción de notas de voz), `BOTV3_N8N_QUERY_URL` y `BOTV3_N8N_SHARED_SECRET`:

```bash
sudo grep -E '^(GROQ_API_KEY|BOTV3_N8N_QUERY_URL|BOTV3_N8N_SHARED_SECRET)=' \
  /opt/nodo/datos/secretos/botv3.env | sudo tee -a /opt/nodo/datos/secretos/botv3-pilar.env >/dev/null
sudo chmod 640 /opt/nodo/datos/secretos/botv3-pilar.env
sudo chown root:captura /opt/nodo/datos/secretos/botv3-pilar.env
```

Verificación (sin mostrar valores): `sudo cut -d= -f1 /opt/nodo/datos/secretos/botv3-pilar.env`

## 4. Código y unidad

```bash
sudo install -d -m 0755 /opt/botv3/perfiles
sudo install -m 0644 botv3.py /opt/botv3/botv3.py
sudo install -m 0644 perfiles/jaime.toml perfiles/pilar.toml /opt/botv3/perfiles/
sudo install -m 0644 'botv3@.service' /etc/systemd/system/'botv3@.service'
sudo systemctl daemon-reload
```

⚠️ **`botv3.py` es compartido con `@Dcs_v3bot`, que está corriendo.** Antes de copiarlo:
respaldo en `datos/botv3/deploy-backups/perfiles-$(date +%Y%m%d_%H%M%S)`, `py_compile` y
las 38 pruebas **en la Pi**. Después, `systemctl restart botv3` y comprobar que Jaime
sigue contestando: el refactor toca su código aunque no toque su unidad.

## 5. Autenticar Claude en la cuenta de Camila

Esto lo hace Diego, es interactivo y **no lo puede hacer un asistente**:

```bash
sudo -u botpilar CLAUDE_CONFIG_DIR=/opt/nodo/datos/botv3-pilar/claude-config \
  /opt/botv3/bin/claude
```

Iniciar sesión con **`<correo-camila>`**, no con la cuenta de Diego. Si se
autentica con la equivocada, las preguntas de Camila le comen la cuota a Diego y el
error no se ve por ningún lado.

> Un `OAuth session expired` probando `claude` a mano **sin** exportar ese
> `CLAUDE_CONFIG_DIR` no significa nada: está leyendo otra credencial.

## 6. Encender

```bash
sudo systemctl enable --now botv3@pilar
systemctl status botv3@pilar --no-pager
```

## Verificación — cada una responde una pregunta distinta

**1. El perfil cargó lo que dice el archivo.**

⚠️ **Un perfil sin vaults NO se puede diagnosticar fuera del sandbox.** `--check` y
`--test-agent` corren `validate_startup()`, que aborta si los vaults se ven — y fuera del
namespace **siempre** se ven. Un `sudo -u botpilar … --check` a secas da un rojo que no
significa nada. Hay que reproducir las directivas de la unidad, igual que se hizo para
bisecar el sandbox de Codex:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --unit=pilar-check --service-type=oneshot \
  -p User=botpilar -p Group=botpilar \
  -p EnvironmentFile=/opt/nodo/datos/secretos/botv3-pilar.env \
  -p Environment=BOTV3_PERFIL=pilar \
  -p ProtectSystem=strict -p ProtectHome=true -p PrivateTmp=true \
  -p ReadWritePaths=/opt/nodo/datos/botv3-pilar \
  -p "InaccessiblePaths=-/home -/opt/nodo/datos/secretos -/opt/nodo/datos/srv/vault_personal -/opt/nodo/datos/srv/vault_trabajo -/opt/nodo/datos/botv3" \
  /usr/bin/python3 /opt/botv3/botv3.py --check
```

Salida esperada, verificada el 13-09-2026:
`Perfil pilar (Pilar, @Pilar_v2bot) válido: sin vaults. Rutas: claude, gpt, ha, web.`

⚠️ **Si cambia `botv3@.service`, este comando hay que regenerarlo** con las directivas
nuevas. Ya pasó con `botv3-work-check`: la unidad de prueba conserva las directivas con las
que se escribió y falla —o pasa— por una causa que ya no existe.

**2. El namespace, que es la prueba que de verdad importa.** El `if` puede tener un bug:

```bash
P=$(pgrep -f 'botv3.py' -u botpilar | head -1)
for d in /opt/nodo/datos/srv/vault_personal /opt/nodo/datos/srv/vault_trabajo \
         /opt/nodo/datos/botv3 /opt/nodo/datos/secretos /opt/nodo/datos/botv3-pilar; do
  printf "%-45s " "$d"
  sudo nsenter -t $P -m -- runuser -u botpilar -- ls "$d" >/dev/null 2>&1 \
    && echo "LEGIBLE" || echo "bloqueado"
done
```

Los cuatro primeros **bloqueados**, el último **LEGIBLE**. `botv3` incluye el
`claude-config` de Diego, que es lo más caro de la lista.

⚠️ **No uses `sudo ls /proc/<pid>/root/...` para esto** — ver arriba: root atraviesa el
nodo 000 y te muestra un directorio vacío, que parece lo mismo y no lo es.

Resultado del 13-09-2026: los cuatro bloqueados, `botv3-pilar` legible. ✅

**4. Desde el Telegram de Camila:** pedirle algo de un vault —*«qué dice mi nota de
plantas»*— y que **se niegue**. Después una pregunta normal, que tiene que contestar por
`gpt`, mostrando `Ruta: gpt`.

**5. Que el bot de Jaime siga entero:** `journalctl -u botv3 -n 20` sin errores nuevos, y
una consulta de prueba a `@Dcs_v3bot` que cite una fuente de vault.

**6. Que la unidad desplegada sea la del vault** — la trampa de las tres tardes:

```bash
systemctl show botv3@pilar -p User -p ReadWritePaths -p InaccessiblePaths
```

## Credencial por ruta — decidido el 13-09-2026

La ruta **`web` de Jaime** usa la cuenta de Camila (`<correo-camila>`) con su
propio `CLAUDE_CONFIG_DIR` en `/opt/nodo/datos/botv3/claude-config-web`, declarado en
`jaime.toml` como `claude_config_web`.

**Por qué es admisible justo ahí y en ningún otro lado:** la ruta `web` **nunca ve los
vaults** —corre sobre un directorio vacío, sin `Read/Grep/Glob`, y su prompt ni nombra sus
rutas—, así que no hay contenido de CyD que pueda llegar a una cuenta de Anthropic que la
autorización del documento 11 no cubre. En las rutas `claude` y `codex`, que sí leen
archivos, la credencial es la del perfil y **no se comparte**.

Lo que se gana: las búsquedas de Diego dejan de gastar su propia cuota de Claude, y el
respaldo de la ruta `web` pasa a ser una cuenta distinta de verdad — antes, si se agotaba
ChatGPT, el respaldo caía sobre la misma cuenta que se reserva para leer los vaults.

**Regla que quedó en el código:** el permiso de una ruta no puede ser más ancho que el de
la ruta que usa por dentro. Por eso un perfil sin permiso de Codex va directo a Claude en
la ruta `web`, en vez de entrar a Codex por la puerta de atrás y gastar el ChatGPT Plus de
Diego — se descubrió en producción el 13-09, cuando la primera búsqueda de Camila falló
por un directorio que faltaba y delató el camino.

> **Actualizado el 19-09-2026:** ese permiso ya **no** se deduce de que `codex` esté o no
> en `rutas`. Se declara con la llave **`web_codex`** del perfil. El motivo es que `jaime`
> tampoco tiene ya la ruta `codex` —Codex dejó de leer vaults— y sin embargo su búsqueda
> web sigue yendo por ahí: son dos permisos distintos sobre la misma cuenta. Para Camila
> no cambia nada, y lo que la protege es que su perfil **no declara la llave**.

## Memoria compartida

`casa.md` **se creó el 13-09-2026** en `/opt/nodo/datos/nodo-memoria/`, `644
dcifu004:captura`, legible por los dos bots. Hasta ese momento cada uno tenía su silo:
el mecanismo de memoria funcionaba pero **no compartía nada**.

⚠️ **Ningún bot escribe ese archivo**, a propósito: es carpeta de Syncthing y ahí nacen
los `.sync-conflict`. Cada bot agrega a su `casa-<perfil>.md` en su propio directorio de
estado, y **lo confirmado lo pasa Diego a mano** a `casa.md`. Si alguna vez se crea desde
un bot, ojo con la `UMask=0077`: nacería `600` y el otro perfil no lo vería.

## Pendiente al cerrar

- [x] ✅ **`pilar`/`jaime` en `PROPIO`** *(13-09-2026 21:55)*, **más el borrado del
      vocativo antes de clasificar**: los bots se llaman por su nombre, y «Pilar, ¿qué
      hora es?» **no** es una pregunta sobre Pilar. Sin eso, el caso más frecuente de
      todos se iba a la ruta `claude`, que para su perfil no lee archivos. Probado contra
      el webhook real: `Pilar, que hora es`→`gpt`, `…clima manana…`→`web`, `como quedo el
      perfil de pilar`→`claude`. El JSON canónico del vault quedó igual al desplegado en
      código ejecutable (difiere sólo en un bloque de comentarios que nunca se publicó).
- [x] ✅ **`botv3@pilar` en la tupla de `pi/estado.py`** y verificado en
      `/opt/nodo/datos/estado.json`, que es lo que leen el panel y los avisos. Ojo: el
      JSON lo escribe `estado.timer`, así que hasta la corrida siguiente muestra la lista
      vieja — se fuerza con `sudo systemctl start estado.service`.
- [ ] Elegirle una voz Piper distinta (hoy comparte la de Jaime). Están medidas las tres
      instaladas: `es_MX-ald-medium` 1.322 ms, `es_MX-claude-high` 1.737 ms (la de Jaime),
      `es_AR-daniela-high` 4.397 ms.
- [x] ✅ **Jaime migrado a la plantilla el 13-09-2026 22:25** — `botv3@jaime` activo,
      `botv3.service` retirado de `/etc` (respaldo
      `deploy-backups/botv3.service-pre-plantilla-20260913_222556`, canónico en
      `_archivo/unidad-botv3-pre-plantilla-20260913/`). **Pero NO con usuario propio**, y
      esa parte se revirtió a conciencia — ver abajo.

## Jaime se queda como `dcifu004`, y el motivo se midió

La idea original era `botjaime`, por simetría con `botpilar`. **Medido antes de hacerlo:
en `vault_personal` hay 398 archivos a 644 y 43 a 600** (en `00-Inbox/2026-09`,
`20-Areas/21-Huerto` y los adjuntos). Con un usuario distinto de `dcifu004`, esos 43 dejan
de existir para el bot — **sin error y sin aviso**: contesta «no encontré nada» y no hay
forma de saber que mintió. Es el peor modo de falla para un bot de consultas.

Son archivos viejos (`captura-web` y `captura-telegram` ya escriben con `UMask=0022`), así
que un `chmod` los arreglaría. Aun así **la separación no compra casi nada para Jaime**: el
usuario `dcifu004` **es** Diego, y contener al proceso expuesto a internet ya lo hacen
`ProtectSystem=strict`, `ProtectHome` y un `ReadWritePaths` de un solo elemento. Para
Camila era imprescindible por lo contrario: es **otra persona**, y ahí el límite es entre
personas, no entre procesos.

**La plantilla nace cerrada y el perfil abre lo que necesita**, en
`botv3@jaime.service.d/10-perfil.conf`. ⚠️ **Las listas de systemd se acumulan entre
plantilla y drop-in**: hay que vaciarlas con una línea sin valor (`ReadWritePaths=`) antes
de redeclararlas. Sin eso queda también el `ReadWritePaths` de la plantilla apuntando a un
directorio inexistente, y con `ProtectSystem=strict` el namespace se arma **antes** de
ejecutar: `226/NAMESPACE` y el servicio no arranca.

Verificado dentro de los dos namespaces: Jaime lee ambos vaults **incluido un `.md` a
600**, y no ve `secretos/` ni el estado de Camila; Camila sigue sin ver nada de lo de él.

⚠️ **`botv3.service` se borró de `/etc` a propósito**, no sólo se deshabilitó: dejarlo
permitía arrancar por error un segundo lector del mismo bot, y dos lectores de `getUpdates`
se roban los mensajes sin error y sin aviso.

⚠️ **`pi/estado.py`: se quitó `botv3` a secas y se pusieron `botv3@jaime` y `botv3@pilar`.**
Dejar el viejo lo reportaba caído para siempre.
