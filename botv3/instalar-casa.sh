#!/usr/bin/env bash
# Abre el canal compartido entre los perfiles de la casa: el directorio donde
# viven la lista de compras y los appends de memoria de hogar.
#
#     sudo bash instalar-casa.sh            # instala y verifica
#     sudo bash instalar-casa.sh --verificar # sólo comprueba, no toca nada
#
# LO QUE ESTO CAMBIA, dicho sin adornos: hasta hoy los dos bots no compartían
# NADA. Cada uno escribía en su STATE_DIR y la unidad del otro lo tenía en
# InaccessiblePaths; eso es deliberado y está documentado en botv3@.service —
# ahí adentro está claude-config, con una credencial. Este script abre UN
# directorio nuevo, chico y de propósito único. No toca los STATE_DIR, que
# siguen tapados entre sí.
#
# Es idempotente: se puede correr de nuevo sin romper nada.
set -euo pipefail

CASA=/opt/nodo/datos/casa
GRUPO=casa
# jaime corre como dcifu004 (la excepción documentada en su drop-in), pilar como
# botpilar. Un perfil nuevo suma su usuario acá.
USUARIOS=(dcifu004 botpilar)
DROPIN_DIR=/etc/systemd/system/botv3@.service.d
DROPIN="$DROPIN_DIR/20-casa.conf"

rojo() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

verificar() {
  local fallas=0
  echo "— verificación —"

  if getent group "$GRUPO" >/dev/null; then
    verde "  ok  existe el grupo $GRUPO"
  else
    rojo "  FALTA el grupo $GRUPO"; fallas=$((fallas + 1))
  fi

  for u in "${USUARIOS[@]}"; do
    if ! id "$u" >/dev/null 2>&1; then
      echo "  --  el usuario $u no existe en esta Pi (¿perfil no desplegado?)"
    elif id -nG "$u" | tr ' ' '\n' | grep -qx "$GRUPO"; then
      verde "  ok  $u está en $GRUPO"
    else
      rojo "  FALTA $u en el grupo $GRUPO"; fallas=$((fallas + 1))
    fi
  done

  if [[ -d $CASA ]]; then
    local modo; modo=$(stat -c '%a' "$CASA")
    local grupo; grupo=$(stat -c '%G' "$CASA")
    # El setgid (el 2 de 2770) es lo que hace que los archivos NAZCAN con el
    # grupo casa. Sin él heredan el grupo primario de quien escribe —botpilar—
    # y el otro perfil queda afuera de lo que Camila guardó.
    if [[ $modo == 2770 && $grupo == "$GRUPO" ]]; then
      verde "  ok  $CASA es 2770 y del grupo $GRUPO"
    else
      rojo "  MAL  $CASA es $modo $grupo, se esperaba 2770 $GRUPO"
      fallas=$((fallas + 1))
    fi
  else
    rojo "  FALTA el directorio $CASA"; fallas=$((fallas + 1))
  fi

  if [[ -f $DROPIN ]]; then
    verde "  ok  existe el drop-in $DROPIN"
  else
    rojo "  FALTA el drop-in $DROPIN"; fallas=$((fallas + 1))
  fi

  # La verificación que de verdad concluye: lo que systemd APLICA, no lo que
  # dice el archivo. Es la misma lección de las tres directivas del kernel —
  # el vault decía una cosa y /etc otra durante tres tardes.
  # ⚠️ Acá había un bug el 20-09-2026 y vale más que el arreglo: la guarda era
  # `systemctl list-unit-files botv3@jaime.service`, que con una INSTANCIA de
  # plantilla no encuentra nada y sale con error — sólo está listada la
  # plantilla `botv3@.service`. El `continue` se comía la comprobación entera y
  # el script imprimía ✅ sin haber mirado nunca lo que systemd aplica, que es
  # justo lo que este bloque existe para mirar. Una verificación que se salta
  # sola es peor que no tenerla: da permiso para dejar de dudar.
  # La pregunta correcta es LoadState, que sí responde por instancia.
  for inst in botv3@jaime botv3@pilar; do
    local estado; estado=$(systemctl show "$inst" -p LoadState --value 2>/dev/null || true)
    if [[ $estado != "loaded" ]]; then
      echo "  --  $inst no está cargada ($estado): se omite"
      continue
    fi
    local rw; rw=$(systemctl show "$inst" -p ReadWritePaths --value 2>/dev/null || true)
    if [[ $rw == *"$CASA"* ]]; then
      verde "  ok  $inst tiene $CASA en ReadWritePaths"
    else
      rojo "  MAL  $inst NO aplica $CASA (¿falta daemon-reload o restart?)"
      fallas=$((fallas + 1))
    fi
    # El grupo se toma al arrancar el proceso, así que la unidad puede
    # declararlo y el proceso vivo no tenerlo. Se comprueba lo declarado acá y
    # lo efectivo abajo, contra el PID real.
    local sg; sg=$(systemctl show "$inst" -p SupplementaryGroups --value 2>/dev/null || true)
    if [[ $sg == *"$GRUPO"* ]]; then
      verde "  ok  $inst declara el grupo $GRUPO"
    else
      rojo "  MAL  $inst NO declara el grupo $GRUPO"
      fallas=$((fallas + 1))
    fi
    local pid; pid=$(systemctl show "$inst" -p MainPID --value 2>/dev/null || echo 0)
    if [[ ${pid:-0} -gt 0 && -r /proc/${pid}/status ]]; then
      # Los grupos EFECTIVOS del proceso vivo, por GID. Es la única lectura que
      # no se puede confundir con una intención: /proc/<pid>/status trae la
      # línea `Groups:` con los gid suplementarios que el kernel le dio.
      local gid; gid=$(getent group "$GRUPO" | cut -d: -f3)
      local grupos; grupos=$(awk '/^Groups:/{$1=""; print}' "/proc/$pid/status")
      if [[ " $grupos " == *" $gid "* ]]; then
        verde "  ok  el proceso vivo de $inst tiene el grupo $GRUPO (gid $gid)"
      else
        rojo "  MAL  $inst corre SIN el grupo $GRUPO: falta un restart"
        fallas=$((fallas + 1))
      fi
    fi
  done

  echo
  if (( fallas )); then
    rojo "❌ $fallas cosas por arreglar"
    return 1
  fi
  verde "✅ el canal de la casa está abierto"
  echo
  echo "Prueba de extremo a extremo, que es la única que prueba algo:"
  echo "  desde el bot de Diego:  /compras agregar pan"
  echo "  desde el bot de Camila: /compras          → tiene que aparecer el pan"
}

if [[ ${1:-} == --verificar ]]; then
  verificar
  exit $?
fi

if [[ $EUID -ne 0 ]]; then
  rojo "corre esto con sudo"
  exit 1
fi

echo "— instalación —"

if ! getent group "$GRUPO" >/dev/null; then
  groupadd --system "$GRUPO"
  echo "  creado el grupo $GRUPO"
fi

for u in "${USUARIOS[@]}"; do
  if id "$u" >/dev/null 2>&1; then
    usermod -aG "$GRUPO" "$u"
    echo "  $u agregado a $GRUPO"
  else
    echo "  -- $u no existe todavía, se omite"
  fi
done

mkdir -p "$CASA"
chgrp "$GRUPO" "$CASA"
chmod 2770 "$CASA"
echo "  $CASA listo (2770 root:$GRUPO)"

mkdir -p "$DROPIN_DIR"
# La fuente es el archivo versionado junto a este script, no un heredoc: con el
# texto metido acá, el revisor de deriva de Cockpit (bots-info) veía el drop-in
# desplegado "sin fuente en el vault", porque compara archivo contra archivo.
# Una sola fuente: editar `botv3@.service.d/20-casa.conf` y volver a correr esto.
# Si se corre la copia desplegada en /opt/botv3, la fuente no está al lado: se
# cae a la del vault, que es la canónica.
FUENTE="$(dirname "$(readlink -f "$0")")/botv3@.service.d/20-casa.conf"
[[ -f "$FUENTE" ]] || FUENTE=/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5/botv3/botv3@.service.d/20-casa.conf
if [[ ! -f "$FUENTE" ]]; then
  rojo "  FALTA botv3@.service.d/20-casa.conf (ni junto al script ni en el vault)"
  exit 1
fi
install -m 0644 "$FUENTE" "$DROPIN"
echo "  escrito $DROPIN"

systemctl daemon-reload
echo "  daemon-reload hecho"

# El grupo suplementario se toma al ARRANCAR el proceso: sin reinicio, el bot
# sigue corriendo sin el grupo y escribir falla con EACCES sobre un directorio
# que en el disco se ve perfecto.
for inst in botv3@jaime botv3@pilar; do
  if systemctl is-active --quiet "$inst"; then
    systemctl restart "$inst"
    echo "  $inst reiniciado"
  fi
done

echo
verificar
