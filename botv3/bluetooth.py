"""Cliente del socket de bt-control (encargo 101b).

El bot no toca BlueZ: todo pasa por `bt-control` (pi/bt/, encargo 101a), un servicio de
`dcifu004` que escucha en `casa/bt.sock`. El protocolo está en `pi/bt/LEEME.md`: una línea
JSON por pedido y una por respuesta, de 4 KB como máximo.

No conoce Telegram: devuelve datos, y los errores son `BluetoothError` con un `codigo`
corto, sin la ruta del socket ni el texto de la excepción. El texto para el chat lo arma
el bot.

`casa/` es `root:casa 2770` sin bit sticky: cualquier miembro de `casa` podría cambiar el
socket por uno propio. Por eso, al conectar se mira con SO_PEERCRED que del otro lado esté
el usuario de bt-control (pendiente 2 de la 101a).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import socket
import struct
import time
import unicodedata
from typing import Any


TIMEOUT = 3
MAX_LINEA = 4096
MAX_NOMBRE = 40
MAX_EVENTOS = 32
VENTANA_S = 180
RE_MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
RE_ID = re.compile(r"^[0-9a-f]{8}$")
RE_CODIGO = re.compile(r"^[0-9]{6}$")
EVENTOS = ("codigo", "emparejado", "descartado", "cerrada")


def ruta_socket() -> str:
    """Se lee al llamar, como el resto del entorno de las pruebas."""
    return os.environ.get("BOTV3_BT_SOCKET") or str(
        Path(os.environ.get("BOTV3_CASA_DIR", "/opt/nodo/datos/casa")) / "bt.sock")


def dueno() -> str:
    """El usuario con el que corre bt-control."""
    return os.environ.get("BOTV3_BT_DUENO", "dcifu004")


class BluetoothError(RuntimeError):
    """Error esperado. `codigo` es uno de:

    - del cliente: `caido` (no hay socket o no conecta), `tiempo` (no contestó en TIMEOUT),
      `ajeno` (del otro lado no está bt-control) y `respuesta` (llegó algo que no es el protocolo);
    - del servicio: el `error` de `{"ok": false}` (`mac`, `bluez`, `sin_bluez`, `ocupado`, `id`…).
    """

    def __init__(self, codigo: str):
        self.codigo = codigo if re.fullmatch(r"[a-z_]{1,16}", str(codigo)) else "respuesta"
        super().__init__(self.codigo)


def limpiar(valor: Any, largo: int = MAX_NOMBRE) -> str:
    """Un texto que mandó un equipo ajeno, otra vez a salvo: sin controles, invisibles ni
    saltos, y recortado. bt-control ya lo hace; esto es la segunda llave del lado del chat."""
    texto = " ".join(str(valor or "").split())
    texto = "".join(c for c in texto if unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    return texto[:largo].strip()


def _uid_dueno() -> int:
    try:
        return pwd.getpwnam(dueno()).pw_uid
    except KeyError:
        raise BluetoothError("ajeno") from None


def pedir(datos: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
    """Un pedido y su respuesta. Lanza BluetoothError; nunca deja pasar OSError ni ValueError."""
    plazo = TIMEOUT if timeout is None else timeout
    fin = time.monotonic() + plazo
    linea = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    if len(linea) > MAX_LINEA:
        raise BluetoothError("respuesta")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(plazo)
        try:
            s.connect(ruta_socket())
        except socket.timeout:
            raise BluetoothError("tiempo") from None
        except OSError:
            raise BluetoothError("caido") from None
        try:
            _, uid, _ = struct.unpack("3i", s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                         struct.calcsize("3i")))
        except (OSError, struct.error):
            raise BluetoothError("ajeno") from None
        if uid != _uid_dueno():
            raise BluetoothError("ajeno")
        buf = b""
        try:
            s.sendall(linea)
            while b"\n" not in buf and len(buf) <= MAX_LINEA:
                queda = fin - time.monotonic()
                if queda <= 0:
                    raise socket.timeout()
                s.settimeout(queda)
                trozo = s.recv(MAX_LINEA + 1)
                if not trozo:
                    break
                buf += trozo
        except socket.timeout:
            raise BluetoothError("tiempo") from None
        except OSError:
            raise BluetoothError("caido") from None
    finally:
        s.close()
    cuerpo, salto, _ = buf.partition(b"\n")
    if not salto or len(cuerpo) > MAX_LINEA:
        raise BluetoothError("respuesta")
    try:
        r = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise BluetoothError("respuesta") from None
    if not isinstance(r, dict) or not isinstance(r.get("ok"), bool):
        raise BluetoothError("respuesta")
    if not r["ok"]:
        raise BluetoothError(str(r.get("error") or "respuesta"))
    return r


def _mac(valor: Any) -> str | None:
    return valor if isinstance(valor, str) and RE_MAC.fullmatch(valor) else None


def _entero(valor: Any, tope: int = 3600) -> int:
    return max(0, min(tope, valor)) if isinstance(valor, int) and not isinstance(valor, bool) else 0


def _ventana(r: dict[str, Any]) -> dict[str, Any]:
    ident = r.get("id")
    return {"abierta": r.get("abierta") is True,
            "id": ident if isinstance(ident, str) and RE_ID.fullmatch(ident) else None,
            "quedan": _entero(r.get("quedan"))}


def estado() -> dict[str, Any]:
    """Equipos emparejados, ventana y lo que suena (`sonando` es None si no se pudo leer)."""
    r = pedir({"verbo": "estado"})
    dispositivos = []
    for d in r.get("dispositivos") if isinstance(r.get("dispositivos"), list) else []:
        mac = _mac(d.get("mac")) if isinstance(d, dict) else None
        if mac:
            dispositivos.append({"mac": mac, "nombre": limpiar(d.get("nombre")) or mac,
                                 "conectado": d.get("conectado") is True,
                                 "confiable": d.get("confiable") is True})
    sonando = None
    if isinstance(r.get("sonando"), list):
        sonando = []
        for s in r["sonando"]:
            mac = _mac(s.get("mac")) if isinstance(s, dict) else None
            if mac:
                sonando.append({"mac": mac, "nombre": limpiar(s.get("nombre")) or mac,
                                "codec": limpiar(s.get("codec"), 16) or None,
                                "salida": limpiar(s.get("salida"), 60) or None})
    ventana = _ventana(r.get("ventana") if isinstance(r.get("ventana"), dict) else {})
    return {"bluez": r.get("bluez") is True, "dispositivos": dispositivos,
            "ventana": ventana, "sonando": sonando}


def abrir(segundos: int = VENTANA_S) -> dict[str, Any]:
    """Abre la ventana de emparejamiento. Si ya estaba abierta, la misma (`ya_abierta`)."""
    r = pedir({"verbo": "abrir", "segundos": int(segundos)})
    v = _ventana(r)
    if v["id"] is None:
        raise BluetoothError("respuesta")
    return {**v, "ya_abierta": r.get("ya_abierta") is True}


def ventana(ident: str, desde: int = 0) -> dict[str, Any]:
    """Los eventos de la ventana `ident` con `n` mayor que `desde`, ya validados."""
    if not isinstance(ident, str) or not RE_ID.fullmatch(ident):
        raise BluetoothError("id")
    r = pedir({"verbo": "ventana", "id": ident, "desde": int(desde)})
    eventos = []
    for e in r.get("eventos") if isinstance(r.get("eventos"), list) else []:
        if not isinstance(e, dict) or e.get("tipo") not in EVENTOS or not _entero(e.get("n"), 10**6):
            continue
        limpio: dict[str, Any] = {"n": e["n"], "tipo": e["tipo"]}
        if e["tipo"] != "cerrada":
            limpio["mac"] = _mac(e.get("mac"))
            if limpio["mac"] is None:
                continue
        if e["tipo"] in ("codigo", "emparejado"):
            codigo = e.get("codigo")
            limpio["codigo"] = codigo if isinstance(codigo, str) and RE_CODIGO.fullmatch(codigo) else None
        if e["tipo"] == "emparejado":
            limpio["nombre"] = limpiar(e.get("nombre")) or limpio["mac"]
        if e["tipo"] == "cerrada":
            limpio["motivo"] = limpiar(e.get("motivo"), 16)
        eventos.append(limpio)
    return {**_ventana(r), "eventos": sorted(eventos, key=lambda e: e["n"])[:MAX_EVENTOS]}


def cerrar() -> dict[str, Any]:
    return _ventana(pedir({"verbo": "cerrar"}))


def _con_mac(verbo: str, mac: str) -> dict[str, Any]:
    if not _mac(mac):
        raise BluetoothError("mac")
    r = pedir({"verbo": verbo, "mac": mac})
    return {"en_curso": r.get("en_curso") is True}


def conectar(mac: str) -> dict[str, Any]:
    """`en_curso` si BlueZ siguió trabajando después de contestar."""
    return _con_mac("conectar", mac)


def desconectar(mac: str) -> dict[str, Any]:
    return _con_mac("desconectar", mac)


def olvidar(mac: str) -> dict[str, Any]:
    """`RemoveDevice`. Ojo: bt-control lo espera sin tope (hallazgo 2 de 101ar), así que un
    BlueZ lento puede dar `tiempo` aunque el equipo se termine olvidando."""
    return _con_mac("olvidar", mac)
