# Spotify Connect por perfil (88a)

Esta carpeta deja dos receptores `go-librespot v0.10.5`: Jaime en `127.0.0.1:3678` y Pilar en
`127.0.0.1:3679`. No expone la API en la red ni usa zeroconf/mDNS. El audio usa `pulseaudio`,
que en la Pi es `pipewire-pulse`, y por tanto conserva el *sink* (salida) por defecto.

## Instalación

La cola instala el binario armado en `/usr/local/lib/go-librespot/v0.10.5/go-librespot` y deja
`/usr/local/bin/go-librespot` como enlace simbólico a esa versión. Instala esta unidad en
`/etc/systemd/user/spotify@.service` y las dos plantillas en el volumen LUKS:

| Origen | Destino | Dueño y modo |
|---|---|---|
| `config-jaime.yml` | `/opt/nodo/datos/spotify/jaime/config.yml` | `dcifu004:dcifu004 0600` (carpeta `0700`) |
| `config-pilar.yml` | `/opt/nodo/datos/spotify/pilar/config.yml` | `dcifu004:dcifu004 0600` (carpeta `0700`) |
| `spotify@.service` | `/etc/systemd/user/spotify@.service` | `root:root 0644` |

### Bootstrap único del escucha

Antes de reiniciar por primera vez `desplegar-escucha` con esta versión, su carpeta de binarios
debe existir: `ReadWritePaths=-/usr/local/lib/go-librespot` la tolera ausente, pero no la crea
bajo `ProtectSystem=strict`. La cola debe pedir —sin ejecutarlo desde esta etapa— este único
comando manual mediante `nodo-desplegar sugerir`:

```bash
nodo-desplegar sugerir --motivo "Preparar directorio root seguro para instalar go-librespot" -- "sudo install -d -m 0755 -o root -g root /usr/local/lib/go-librespot && sudo install -m 0755 -o root -g root /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/pi/nodo-desplegar.py /usr/local/bin/nodo-desplegar && sudo install -m 0644 -o root -g root /opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/pi/desplegar-escucha.service /etc/systemd/system/desplegar-escucha.service && sudo systemctl daemon-reload && sudo systemctl restart desplegar-escucha"
```

Sólo después de que el usuario confirme ese paso, el catálogo puede instalar el binario y la unidad.
La unidad vive en `/etc/systemd/user`, por lo que el escucha no necesita ver `/home`.

### Altas, en este orden

No se ejecutan desde este encargo. Después del bootstrap, el usuario puede pedir estas altas una
por una; los hashes fijan exactamente cada fuente. La unidad y las configuraciones llevan
`--despues` vacío para que el escucha del sistema no intente reiniciar una unidad de usuario.

```bash
nodo-desplegar alta spotify-binario=9130ee00613abeb9620cc06fe9bc7080eba73618d547b0c71ec991f3504dc5ff 10-Proyectos/11-Pi5/pi/spotify/go-librespot-v0.10.5-linux-arm64 /usr/local/lib/go-librespot/v0.10.5/go-librespot --modo 0755 --dueno root:root --motivo "Instalar binario Spotify v0.10.5 verificado"
nodo-desplegar alta-enlace spotify-enlace=ded4581c06ac51458b67946717f7b7d80c9186aa9394817b9e26319671eed499 /usr/local/bin/go-librespot /usr/local/lib/go-librespot/v0.10.5/go-librespot --motivo "Publicar enlace del binario Spotify v0.10.5"
nodo-desplegar alta spotify-unidad=2802c2eec07aa6508f659c8ebb8503c0d1109a8189baf41f44fdad9be215ce79 10-Proyectos/11-Pi5/pi/spotify/spotify@.service /etc/systemd/user/spotify@.service --modo 0644 --dueno root:root --despues --motivo "Instalar unidad de usuario Spotify"
nodo-desplegar alta spotify-jaime=d870872bda05ac186c638a7e5bfe8e596d0231bd72e2773369504fbd6acfe3c0 10-Proyectos/11-Pi5/pi/spotify/config-jaime.yml /opt/nodo/datos/spotify/jaime/config.yml --modo 0600 --dueno dcifu004:dcifu004 --despues --motivo "Instalar configuración privada Spotify Jaime"
nodo-desplegar alta spotify-pilar=8b0367c7efea4d62842da326babaf02be96f3ca5c2cf667707c839455941d48a 10-Proyectos/11-Pi5/pi/spotify/config-pilar.yml /opt/nodo/datos/spotify/pilar/config.yml --modo 0600 --dueno dcifu004:dcifu004 --despues --motivo "Instalar configuración privada Spotify Pilar"
```

El hash del enlace es el SHA-256 del objetivo literal:
`ded4581c06ac51458b67946717f7b7d80c9186aa9394817b9e26319671eed499`.

### Subir go-librespot de versión

La versión está fijada tanto en el enlace permitido del `nodo-desplegar` instalado como en estas
rutas. Para subirla, primero deja en el vault el binario y su hash verificados; luego actualiza
la versión y el objetivo permitido en `pi/nodo-desplegar.py`, las rutas y documentación Spotify,
y repite el bootstrap para instalar ese `nodo-desplegar` antes de pedir el binario y el enlace
nuevos. No se reemplaza el enlace existente: se rechaza si apunta a otro objetivo.

Después de que la cola haya desplegado todo, como `dcifu004` se habilitan y arrancan las dos
instancias una sola vez:

```bash
systemctl --user daemon-reload && systemctl --user enable --now spotify@jaime spotify@pilar
```

## Vincular una cuenta (después de 88b)

No vincules desde esta etapa. Mientras un perfil esté esperando autorización, la forma que usa
`/spotify` para mostrarla es:

```bash
curl -s 127.0.0.1:3678/auth/code
curl -s 127.0.0.1:3679/auth/code
```

Cada respuesta contiene la URL de Spotify y un código temporal. Jaime lo aprueba con la cuenta
del usuario; Pilar, con la cuenta asociada a ese perfil. La credencial no se pone en YAML: go-librespot la guarda en
`state.json` bajo la carpeta privada del perfil.

## Desvincular

Detén sólo la instancia correspondiente, borra su credencial guardada y vuelve a iniciarla:

```bash
systemctl --user stop spotify@jaime && rm -f /opt/nodo/datos/spotify/jaime/state.json && systemctl --user start spotify@jaime
```

Para Pilar se sustituye `jaime` por `pilar`. Esto no borra `config.yml`; al reiniciar vuelve a
entregar un código nuevo. No borres la carpeta: también contiene el lockfile mientras la unidad
está activa.

## Después de abrir LUKS

`ConditionPathExists` evita reinicios cuando el volumen está cerrado, pero systemd no vuelve a
evaluar esa condición al abrirlo. Si la Pi arrancó con LUKS cerrado, ejecuta una vez, como
`dcifu004`, `systemctl --user start spotify@jaime spotify@pilar` después de `abrir-datos`.
