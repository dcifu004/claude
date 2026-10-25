# 88c — resultado del arreglo tras revisión 3

## Estado

**Listo en el vault; no desplegado.** No se ejecutó `sudo`, el bootstrap ni las altas, no se
escribió en `/etc` o `/usr/local`, y no se tocó el binario. El volumen LUKS estaba montado. Se
verificaron los artefactos recibidos:

```text
9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff  pi/spotify/go-librespot-v0.10.5-linux-arm64
e6a3cf037c27af877c35183b51e8df82c88ef0e2fb88ecd38ee2cca3a5ee50cc  pi/spotify/fixtures/config_schema.v0.10.5.json
```

El binario conserva modo `0755` y tamaño `17.491.240 B`. El fixture es el esquema real completo
de v0.10.5 (13.895 B); también se corrigió el texto histórico de `88a-RESULTADO.md` que aún decía
que era un extracto y el `|| test` que sobraba en C6.

## Cambios por archivo

- `pi/nodo-desplegar.py`: `RE_FUENTE` acepta sólo el carácter adicional `@`; una ruta absoluta y
  `..` siguen rechazados. Se sacó el prefijo Spotify redundante de `PERMITIDOS`. Los enlaces se
  revisan antes de `validar_destino`: uno ya correcto queda sin cambios, uno distinto se rechaza,
  el hash pedido se valida y una creación deja su objetivo como respaldo. Al iniciar, el escucha
  limpia únicamente temporales regulares con la forma `.nombre.nodo-desplegar-<16 hex>` en las
  carpetas derivadas del catálogo, abiertas sin seguir enlaces.
- `pi/test_nodo_desplegar.py`: de 87 a 93 pruebas. Cubren la fuente real con `@`, el catálogo de
  `unidad-botv3-at-service`, el bootstrap partido como shell, enlace repetido/distinto/hash,
  respaldo de reversión y limpieza de un temporal aun con el enlace instalado.
- `pi/spotify/LEEME.md`: bootstrap completo y entre comillas, cinco altas con sus hashes en el
  orden seguro, y nota de actualización de versión. Los nombres personales sueltos se cambiaron
  por «el usuario» o la etiqueta del perfil.
- `encargos/88a-RESULTADO.md`: corrigió la descripción/hash del fixture real y el comando C6.

## Hallazgos de rev3

| Hallazgo | Estado |
|---|---|
| 1. `@` en fuentes | Cerrado: la ruta real `pi/spotify/spotify@.service` pasa por `leer_fuente`; absoluta y `..` fallan. La entrada real `unidad-botv3-at-service` prepara. |
| 2. Bootstrap partido e incompleto | Cerrado: una sola cadena citada llega a `sugerir` con sus cinco pasos. |
| 3. Binario y altas | Cerrado en el vault: binario verificado y cinco líneas de alta documentadas, sin ejecutarlas. |
| 4. Enlace ya existente | Cerrado: objetivo igual se omite; otro objetivo se rechaza; se exige el hash y se conserva respaldo al revertir. |
| 5. Fixture | Cerrado por el antecedente: fixture real v0.10.5 y texto corregido. |
| 6. Actualización de versión | Cerrado: `LEEME.md` explica que se actualiza el objetivo permitido, fuentes y bootstrap antes de la nueva alta. |
| 7. Nombre de pila | Cerrado en `LEEME.md`. |
| 8. Detalles | Cerrados: limpieza de temporales al inicio, prefijo redundante retirado y C6 sin `|| test`. |

El `O_NONBLOCK` de `leer_fuente` no se modificó: queda deliberadamente fuera de alcance.

## Para copiar al desplegar

Primero, enviar esta única sugerencia; las comillas aseguran que la shell entrega una sola orden a
`sugerir`:

```bash
nodo-desplegar sugerir --motivo "Preparar directorio root seguro para instalar go-librespot" -- "sudo install -d -m 0755 -o root -g root /usr/local/lib/go-librespot && sudo install -m 0755 -o root -g root /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/pi/nodo-desplegar.py /usr/local/bin/nodo-desplegar && sudo install -m 0644 -o root -g root /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/pi/desplegar-escucha.service /etc/systemd/system/desplegar-escucha.service && sudo systemctl daemon-reload && sudo systemctl restart desplegar-escucha"
```

Después de su confirmación, pedir las altas en este orden. Las configuraciones y la unidad llevan
`--despues` vacío; el hash del enlace es el SHA-256 de su objetivo literal.

```bash
nodo-desplegar alta spotify-binario=9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff 10-Proyectos/11-Pi5/pi/spotify/go-librespot-v0.10.5-linux-arm64 /usr/local/lib/go-librespot/v0.10.5/go-librespot --modo 0755 --dueno root:root --motivo "Instalar binario Spotify v0.10.5 verificado"
nodo-desplegar alta-enlace spotify-enlace=ded4581c06ac51458b67946717f7b7d80c9186aa9394817b9e26319671eed499 /usr/local/bin/go-librespot /usr/local/lib/go-librespot/v0.10.5/go-librespot --motivo "Publicar enlace del binario Spotify v0.10.5"
nodo-desplegar alta spotify-unidad=2802c2eec07aa6508f659c8ebb8503c0d1109a8189baf41f44fdad9be215ce79 10-Proyectos/11-Pi5/pi/spotify/spotify@.service /etc/systemd/user/spotify@.service --modo 0644 --dueno root:root --despues --motivo "Instalar unidad de usuario Spotify"
nodo-desplegar alta spotify-jaime=d870872bda05ac186c638a7e5bfe8e596d0231bd72e2773369504fbd6acfe3c0 10-Proyectos/11-Pi5/pi/spotify/config-jaime.yml /opt/nodo/datos/spotify/jaime/config.yml --modo 0600 --dueno dcifu004:dcifu004 --despues --motivo "Instalar configuración privada Spotify Jaime"
nodo-desplegar alta spotify-pilar=8b0367c7efea4d62842da326babaf02be96f3ca5c2cf667707c839455941d48a 10-Proyectos/11-Pi5/pi/spotify/config-pilar.yml /opt/nodo/datos/spotify/pilar/config.yml --modo 0600 --dueno dcifu004:dcifu004 --despues --motivo "Instalar configuración privada Spotify Pilar"
```

## Suites ejecutadas

```text
$ python3 pi/spotify/test_plantillas.py
Ran 3 tests in 0.001s
OK

$ python3 pi/test_nodo_desplegar.py
Ran 93 tests in 4.715s
OK

$ python3 botv3/test_botv3.py
Ran 490 tests in 16.533s
OK (skipped=4)

$ python3 botv3/test_temporizadores.py
✅ todo en verde

$ python3 botv3/test_compras.py
✅ todo en verde

$ python3 botv3/test_spotify.py
python3: can't open file '.../botv3/test_spotify.py': [Errno 2] No such file or directory

rc: plantillas=0 nodo=0 botv3=0 temporizadores=0 compras=0 spotify=2
```

La sexta suite no existe en este árbol y el rc 2 es el mismo de la línea base; no es una falla
nueva del arreglo. Los cuatro `skipped` del bot corresponden a sockets locales que el sandbox no
permite.

## Pendientes

Sólo queda el despliegue manual descrito arriba y luego las verificaciones C1--C6 en la Pi. La
vinculación de cuentas sigue fuera de esta etapa, en 88b.
