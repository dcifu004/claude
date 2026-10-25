# Encargo 88c: arreglo de la 88a tras su revisión 3 (Claude (Diego), 25-10-2026)

Etapa de arreglo. La 88a terminó sus vueltas con `88ar3-RESULTADO.md` en NO DESPLEGABLE, sin
graves. Esta etapa cierra esos hallazgos y nada más. **Un arreglo no agrega funciones nuevas.**
Después viene la 88b, que no cambia.

## Leer primero

- `encargos/88ar3-RESULTADO.md` entero: es la especificación de esta etapa.
- `encargos/88a-spotify-receptores.md` (criterios C1–C6) y `encargos/88a-RESULTADO.md`.
- `pi/nodo-desplegar.py`: `RE_FUENTE` (~174), `leer_fuente` (~622), `preparar` (~911),
  `aplicar` (~1261), `despues()` (~1333), `ENLACES_PERMITIDOS` (~164) y `PERMITIDOS` (~151).
- `pi/spotify/LEEME.md` y `pi/test_nodo_desplegar.py`.
- `encargos/trampas.md`, sección «nodo-desplegar».

## No hace falta leer

El bot, Cockpit, la 88b ni las notas numeradas fuera de la 36.

## Antecedentes

- **El binario ya está en el vault.** Claude (Diego) lo bajó con red el 25-10:
  `pi/spotify/go-librespot-v0.10.5-linux-arm64` (`0755`, 17 491 240 B). El sha256 del ejecutable es
  `9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff` y el del `.tar.gz` del release es
  `35274c1d3576090096d3459ecf76ee9c025258d19dc76f0bf724f95c525467e1`. **No lo bajes ni lo
  reemplaces**: tu shell no tiene red. Verifica el hash y úsalo.
- **El fixture ya es el real.** `pi/spotify/fixtures/config_schema.v0.10.5.json` es ahora el
  `config_schema.json` bajado del tag v0.10.5 (13 895 B, sha256
  `e6a3cf037c27af877c35183b51e8df82c88ef0e2fb88ecd38ee2cca3a5ee50cc`). Con él, `test_plantillas.py`
  sigue en verde. Esto cierra el hallazgo 5: sólo corrige cualquier texto que diga otra cosa.
- El catálogo publicado ya tiene `unidad-botv3-at-service` y `unidad-rclone-drive-at-service`, con `@`
  en la fuente. Hoy tampoco se pueden desplegar.
- La línea de flags va con dos guiones (`--config_dir`), por pflag (rev 88ar).

## Qué hacer

1. **Hallazgo 1:** `RE_FUENTE` acepta `@`, sin abrir nada más (nada de `..`, ni rutas absolutas, ni
   espacios nuevos). Prueba que pase **la ruta real** `pi/spotify/spotify@.service` por
   `leer_fuente`, y otra que confirme que `unidad-botv3-at-service` ya prepara.
2. **Hallazgo 2:** en `LEEME.md`, una **sola** línea entre comillas para `nodo-desplegar sugerir`,
   en este orden: `install -d` de `/usr/local/lib/go-librespot`, `install -m 0755` del
   `nodo-desplegar.py` del vault en `/usr/local/bin/nodo-desplegar`, `install -m 0644` del
   `desplegar-escucha.service` del vault, `daemon-reload` y `restart desplegar-escucha`. Agrega
   una prueba que parta la línea como lo hace la shell y verifique que `sugerir` recibe todo.
3. **Hallazgo 3:** escribe, **sin ejecutarlas**, las líneas exactas de las altas en `LEEME.md` y en
   el resultado: dos configs, la unidad, el binario y el enlace. Van con `--despues` vacío en la
   unidad y en las configs, y en el orden bootstrap → binario → enlace → unidad → configs. Cada una
   lleva su `=<sha256>`.
4. **Hallazgo 4:** que el enlace ya instalado no bloquee un pedido. Para `tipo == "enlace"`, se
   compara el objetivo actual con el esperado antes de `validar_destino`. Si coincide, se omite;
   si no, se rechaza. Se respeta el `=<sha256>` y `revertir` deja un respaldo.
5. **Hallazgos 6–8:** anotar en `LEEME.md` cómo subir de versión; reemplazar el nombre de pila por
   «el usuario» o la etiqueta de la cuenta; limpiar los temporales `.nodo-desplegar-*` huérfanos
   al arrancar el escucha; quitar `"/opt/nodo/datos/spotify/"` de `PERMITIDOS`; y el `|| test`
   de C6. El `O_NONBLOCK` de `leer_fuente` **no** va aquí.

## Criterios de aceptación

- **C1.** `leer_fuente("pi/spotify/spotify@.service")` devuelve el contenido, y una fuente con `..`
  o absoluta sigue rechazada.
- **C2.** La línea de bootstrap de `LEEME.md`, partida con `shlex`, le entrega a `sugerir` un único
  comando con los cinco pasos.
- **C3.** El sha256 del binario del vault es `9130ee00…dc5ff` y la línea de alta del binario
  lleva ese hash.
- **C4.** Repedir un pedido que incluye el enlace ya creado no se rechaza, y un enlace que apunta
  a otro objetivo sí.
- **C5.** Las seis suites del manifiesto quedan sin fallas nuevas.

## Invariantes

- Las 92 entradas del catálogo siguen preparando, aplicando y revirtiendo igual que antes.
- `PROHIBIDOS` no cambia. Nada nuevo corre como root fuera del catálogo.

## Fuera de alcance

- Ejecutar el bootstrap, las altas o cualquier `sudo`: lo hace el usuario al desplegar.
- Bajar archivos de la red, cambiar la versión o tocar el binario.
- El `O_NONBLOCK` de `leer_fuente` (encargo aparte), el bot y la 88b.

## Reglas

- No escribas credenciales en el vault.
- Prueba con rutas reales, en `mktemp -d` o bajo `unshare -r`, nunca en `/etc` ni en `/usr/local`.

## Resultado

Escribe `encargos/88c-RESULTADO.md` con: cambios por archivo; cómo quedó cada hallazgo de la rev3;
la línea de bootstrap y las de alta, listas para copiar; la salida de las suites; y los pendientes.
