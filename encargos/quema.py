#!/usr/bin/env python3
"""Aviso acotado para usar capacidad que vence, sin sudo ni texto del vault fuera de LUKS.

La ejecución real usa ``nodo-desplegar consultar`` y valida el resultado que escribe el escucha.
Las funciones
que hablan con el nodo se reciben por parámetro en ``Quema`` para que la suite no use Telegram,
tmux ni /opt/nodo/datos.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import math
import os
import re
import subprocess
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

DATOS = Path(os.environ.get("QUEMA_DATOS", "/opt/nodo/datos"))
PROYECTO = Path(os.environ.get("QUEMA_PROYECTO", "/opt/nodo/datos/srv/vault_personal/10-Proyectos/11-Pi5"))
# datetime.weekday(): lunes=0, miércoles=2, viernes=4.
CUENTAS = {2: ("codex",), 4: ("claude_diego", "claude_cami")}
NOMBRES = {"claude_diego": "Claude (Diego)", "claude_cami": "Claude (Cami)", "codex": "Codex"}
REVISORES = {"claude_diego": "codex", "claude_cami": "codex", "codex": "claude_cami"}
RE_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
RE_COLA = re.compile(r"cola[0-9]{2}[a-z0-9]*")
SUFIJOS = {"claude_diego": "d", "claude_cami": "c", "codex": "x"}


def _hora(valor) -> datetime | None:
    if not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _semana(momento: datetime) -> str:
    y, n, _ = momento.isocalendar()
    return f"{y}-W{n:02d}"


def _linea_cerrada(texto: str) -> bool:
    """Sólo los cuatro nombres aprobados, una cuenta, porcentaje y hora pueden salir del LUKS."""
    permitidas = ("Memoria y vault", "Auditoría de la Pi", "Revisión cruzada", "Preparar encargos", "No quemar",
                  *NOMBRES.values())
    resto = texto
    for trozo in permitidas:
        resto = resto.replace(trozo, "")
    return re.fullmatch(r"[ 0-9%:·]*", resto) is not None


def _porcentaje_cerrado(valor: float) -> str:
    """El texto fuera de LUKS no lleva decimales; se redondea hacia abajo, nunca al alza."""
    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not math.isfinite(valor):
        raise ValueError("capacidad inválida")
    return str(math.floor(valor))


class Quema:
    def __init__(self, datos: Path = DATOS, proyecto: Path = PROYECTO, *, montado: Callable[[], bool] | None = None,
                 panel: Callable[[], dict] | None = None, simular: Callable[[Path], tuple[int, str]] | None = None,
                 consultar: Callable[[str, list[tuple[str, str]]], str | None] | None = None,
                 esperar: Callable[[str], dict | None] | None = None,
                 lanzar: Callable[[list[str]], int] | None = None, sesion: Callable[[str], bool] | None = None):
        self.datos, self.proyecto = Path(datos), Path(proyecto)
        self.carpeta = self.datos / "quema"
        self.registro, self.manifiestos = self.carpeta / "registro.jsonl", self.carpeta / "manifiestos"
        self.plantillas_ruta = self.proyecto / "encargos/quema/plantillas.toml"
        self.montado = montado or self.datos.is_mount
        self.panel = panel or self._panel_real
        self.simular = simular or self._simular_real
        self.consultar = consultar or self._consultar_real
        self.esperar = esperar or self._esperar_real
        self.lanzar = lanzar or self._lanzar_real
        self.sesion = sesion or self._sesion_real

    def plantillas(self) -> dict:
        datos = tomllib.loads(self.plantillas_ruta.read_text(encoding="utf-8")).get("plantilla", {})
        buenas = {}
        for clave, p in datos.items():
            if (re.fullmatch(r"[a-z]{1,12}", clave) and isinstance(p, dict)
                    and p.get("despliegue") == "nada" and p.get("vueltas") == 1
                    and p.get("naturaleza") in ("investigacion", "menor")
                    and isinstance(p.get("etiqueta"), str) and isinstance(p.get("encargo"), str)):
                buenas[clave] = p
        return buenas

    def _leer_registro(self) -> list[dict]:
        try:
            return [x for x in (json.loads(l) for l in self.registro.read_text(encoding="utf-8").splitlines()) if isinstance(x, dict)]
        except (OSError, ValueError):
            return []

    def anotar(self, evento: str, cuenta: str, momento: datetime, **extra) -> None:
        self.carpeta.mkdir(mode=0o755, parents=True, exist_ok=True)
        fila = {"momento": momento.isoformat(timespec="seconds"), "semana": _semana(momento),
                "cuenta": cuenta, "evento": evento} | extra
        fd = os.open(self.registro, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
        try:
            os.fchmod(fd, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, (json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def _reservar(self, cuenta: str, momento: datetime, clase: str, intento: int | None = None) -> bool:
        """Reserva bajo el mismo flock que el registro: dos timers no pueden lanzar dos veces."""
        self.carpeta.mkdir(mode=0o755, parents=True, exist_ok=True)
        fd = os.open(self.registro, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
        try:
            os.fchmod(fd, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                filas = [json.loads(x) for x in os.read(fd, 4 * 1024 * 1024).decode("utf-8").splitlines()]
            except (UnicodeDecodeError, ValueError):
                # Un registro compartido a medias no es «sin historia»: detenerse conserva el
                # tope y evita que una recuperación borre la memoria de tres lanzamientos.
                return False
            if not all(isinstance(r, dict) for r in filas):
                return False
            hoy = momento.date().isoformat()
            if clase == "aviso":
                if any(r.get("evento") == "reserva_aviso" and r.get("cuenta") == cuenta
                       and r.get("momento", "")[:10] == hoy and r.get("intento") == intento for r in filas):
                    return False
                fila = {"momento": momento.isoformat(timespec="seconds"), "semana": _semana(momento),
                        "cuenta": cuenta, "evento": "reserva_aviso", "intento": intento}
            else:
                # Una reserva es una quema: el lanzamiento posterior sólo informa su resultado.
                # Contar ambos dejaba el límite efectivo en dos.
                if sum(r.get("evento") == "reserva_lanzamiento" and r.get("cuenta") == cuenta
                       and r.get("semana") == _semana(momento) for r in filas) >= 3:
                    return False
                fila = {"momento": momento.isoformat(timespec="seconds"), "semana": _semana(momento),
                        "cuenta": cuenta, "evento": "reserva_lanzamiento"}
            os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, (json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n").encode())
            os.fsync(fd)
            return True
        finally:
            os.close(fd)

    def candidatas(self, cuenta: str, capacidad: float, momento: datetime) -> list[tuple[str, dict, Path, str]]:
        buenas = []
        for clave, plantilla in self.plantillas().items():
            ruta = self._manifestar(cuenta, clave, plantilla, momento, temporal=True)
            resultado = self.simular(ruta)
            if not (isinstance(resultado, tuple) and len(resultado) == 2):
                continue
            rc, salida = resultado
            carga = self._carga_autor(salida, cuenta) if isinstance(salida, str) else None
            # La forma de --simular lista autor y fix por separado. Ambos gastan la cuenta
            # que quema; un rc distinto de cero o una fila ausente nunca es una alternativa.
            if rc == 0 and carga is not None and carga <= capacidad:
                buenas.append((clave, plantilla, ruta, salida))
        return buenas[:3]

    @staticmethod
    def _carga_autor(salida: str, cuenta: str) -> float | None:
        gastos = {}
        patron = re.compile(rf"^\s*(autor|fix)\s+{re.escape(NOMBRES[cuenta])}\s+.*?\+"
                            r"([0-9]+(?:[.,][0-9]+)?)\s+% 5 h.*?\+([0-9]+(?:[.,][0-9]+)?)\s+% sem", re.M)
        for rol, _h5, semanal in patron.findall(salida):
            gastos[rol] = float(semanal.replace(",", "."))
        return gastos["autor"] + gastos["fix"] if set(gastos) == {"autor", "fix"} else None

    def _manifestar(self, cuenta: str, clave: str, plantilla: dict, momento: datetime, temporal: bool = False) -> Path:
        base = self.carpeta / "simular" if temporal else self.manifiestos
        base.mkdir(mode=0o755, parents=True, exist_ok=True)
        sello = momento.strftime("%Y%m%d%H%M%S") + SUFIJOS[cuenta]
        nombre = f"cola99q{sello}"
        ruta = base / f"cola-{nombre}.toml"
        # Está fuera de encargos/: una cola viva nunca lo incluye en su diff propio.
        texto = (f'nombre = "{nombre}"\n'
                 f'motivo = "Quema: {plantilla["etiqueta"]}"\n'
                 'resumen = "Informe y propuesta; sin cambios ni despliegue."\n'
                 'despliegue = "nada"\n'
                 'afinado = "ligero"\n'
                 'alcance = "minimo"\n'
                 'paciencia_h = 1\n'
                 'pruebas = []\n\n'
                 '[[etapa]]\n'
                 f'id = "99q{sello}"\n'
                 f'encargo = "quema/{plantilla["encargo"]}"\n'
                 f'autor = "{cuenta}"\n'
                 f'revisor = "{REVISORES[cuenta]}"\n'
                 'vueltas = 1\n'
                 f'naturaleza = "{plantilla["naturaleza"]}"\n')
        tmp = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
        tmp.write_text(texto, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, ruta)
        return ruta

    def _cuentas_hoy(self, panel: dict, momento: datetime) -> list[tuple[str, dict]]:
        if momento.weekday() not in CUENTAS:
            return []
        cap = panel.get("capacidad_por_vencer") if isinstance(panel, dict) else None
        if not isinstance(cap, dict):
            return []
        out = []
        for cuenta in CUENTAS[momento.weekday()]:
            d = cap.get(cuenta)
            if not isinstance(d, dict) or not isinstance(d.get("capacidad"), (int, float)):
                continue
            vence = _hora(d.get("renueva"))
            if vence and 0 < (vence - momento).total_seconds() < 72 * 3600 and d["capacidad"] >= 15:
                out.append((cuenta, d))
        return out

    def _historial_hoy(self, cuenta: str, momento: datetime) -> list[dict]:
        return [r for r in self._leer_registro() if r.get("cuenta") == cuenta and r.get("momento", "")[:10] == momento.date().isoformat()]

    @staticmethod
    def _debe_intentar(historial: list[dict], momento: datetime) -> int | None:
        avisos = [r for r in historial if r.get("evento") == "aviso"]
        if momento.hour == 16 and not avisos:
            return 1
        respuestas = [r for r in historial if r.get("evento") == "respuesta"]
        ultima = respuestas[-1] if respuestas else {}
        if momento.hour == 18 and len(avisos) == 1 and ultima.get("intento") == 1 \
                and ultima.get("resultado") in ("vencida", "ausente"):
            return 2
        if momento.hour == 20 and len(avisos) == 2 and ultima.get("intento") == 2 \
                and ultima.get("resultado") in ("vencida", "ausente"):
            return 3
        return None

    def ejecutar(self, momento: datetime | None = None) -> list[str]:
        momento = momento or datetime.now().astimezone()
        if not self.montado():
            logging.getLogger("quema").warning("LUKS cerrado: /opt/nodo/datos no está montado; no se avisa")
            return []
        try:
            panel = self.panel()
        except Exception as e:  # una medición ausente no justifica avisar a ciegas
            logging.getLogger("quema").warning("panel no disponible: %s", type(e).__name__)
            return []
        hechos = []
        for cuenta, dato in self._cuentas_hoy(panel, momento):
            intento = self._debe_intentar(self._historial_hoy(cuenta, momento), momento)
            if intento is None:
                continue
            if not self._reservar(cuenta, momento, "aviso", intento):
                continue
            try:
                capacidad = _porcentaje_cerrado(float(dato["capacidad"]))
                candidatas = self.candidatas(cuenta, float(dato["capacidad"]), momento)
            except (TypeError, ValueError, OSError):
                self.anotar("aviso", cuenta, momento, intento=intento, resultado="sin_alternativa")
                continue
            if not candidatas:
                # consultar exige entre dos y cuatro opciones; con sólo «No quemar» no se manda un
                # pedido inválido ni se vuelve a intentar como si fuera un vencimiento.
                self.anotar("aviso", cuenta, momento, intento=intento, resultado="sin_alternativa")
                continue
            opciones = [(k, f"{p['etiqueta']} · {NOMBRES[cuenta]} {capacidad} % { _hora(dato['renueva']).astimezone():%H:%M}")
                        for k, p, _, _ in candidatas]
            opciones.append(("no_quemar", "No quemar"))
            motivo = f"{NOMBRES[cuenta]} {capacidad} % { _hora(dato['renueva']).astimezone():%H:%M}"
            if not all(_linea_cerrada(x) for _, x in opciones) or not _linea_cerrada(motivo):
                self.anotar("aviso", cuenta, momento, intento=intento, resultado="texto_invalido")
                continue
            pedido = self.consultar(motivo, opciones)
            self.anotar("aviso", cuenta, momento, intento=intento, pedido=pedido or "")
            if not pedido:
                self.anotar("respuesta", cuenta, momento, intento=intento, resultado="ausente")
                continue
            respuesta = self.esperar(pedido) or {}
            opcion = respuesta.get("opcion") if isinstance(respuesta, dict) else None
            if not isinstance(respuesta, dict) or respuesta.get("estado") != "hecho" or not isinstance(opcion, str):
                self.anotar("respuesta", cuenta, momento, intento=intento, resultado="vencida", pedido=pedido)
                continue
            letras = {chr(ord("A") + i): clave for i, (clave, _) in enumerate(opciones)}
            if respuesta.get("id") != pedido or respuesta.get("letra") not in letras \
                    or letras[respuesta["letra"]] != opcion:
                self.anotar("respuesta", cuenta, momento, intento=intento, resultado="invalida", pedido=pedido)
                continue
            if opcion == "no_quemar":
                self.anotar("respuesta", cuenta, momento, intento=intento, resultado="no_quemar", pedido=pedido)
                continue
            p = self.plantillas().get(opcion)
            if p is None or opcion not in {x[0] for x in candidatas}:
                self.anotar("respuesta", cuenta, momento, intento=intento, resultado="invalida", opcion=opcion, pedido=pedido)
                continue
            if not self._reservar(cuenta, momento, "lanzamiento"):
                self.anotar("respuesta", cuenta, momento, intento=intento, resultado="tope", opcion=opcion, pedido=pedido)
                continue
            self.anotar("respuesta", cuenta, momento, intento=intento, resultado="elegida", opcion=opcion, pedido=pedido)
            ruta = self._manifestar(cuenta, opcion, p, momento)
            nombre = tomllib.loads(ruta.read_text(encoding="utf-8"))["nombre"]
            argv = ["tmux", "new-session", "-d", "-s", nombre, "python3", str(self.proyecto / "encargos/cola-run.py"), str(ruta)]
            rc = self.lanzar(argv)
            viva = rc == 0 and self.sesion(nombre)
            self.anotar("lanzamiento", cuenta, momento, opcion=opcion, cola=nombre, resultado="hecho" if viva else "fallida")
            if viva:
                hechos.append(nombre)
        return hechos

    def _panel_real(self) -> dict:
        p = subprocess.run(["python3", str(self.proyecto / "encargos/cola-run.py"), "--panel"], text=True, capture_output=True, check=True, timeout=120)
        return json.loads(p.stdout)

    def _simular_real(self, ruta: Path) -> tuple[int, str]:
        p = subprocess.run(["python3", str(self.proyecto / "encargos/cola-run.py"), str(ruta), "--simular"], text=True, capture_output=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def _consultar_real(self, motivo: str, opciones: list[tuple[str, str]]) -> str | None:
        argv = ["nodo-desplegar", "consultar", "--motivo", motivo]
        for clave, etiqueta in opciones:
            argv += ["--opcion", f"{clave}={etiqueta}"]
        p = subprocess.run(argv, text=True, capture_output=True, timeout=30)
        return p.stdout.strip() if p.returncode == 0 and RE_ID.fullmatch(p.stdout.strip()) else None

    @staticmethod
    def _esperar_real(pid: str) -> dict | None:
        p = subprocess.run(["nodo-desplegar", "esperar", pid], text=True, capture_output=True, timeout=2100)
        try:
            return json.loads(p.stdout)
        except ValueError:
            return None

    @staticmethod
    def _lanzar_real(argv: list[str]) -> int:
        # Una sesión creada dentro del cgroup del oneshot muere cuando termina la unidad.
        # La unidad transitoria queda como dueña de tmux y de la cola, fuera de ese cgroup.
        nombre = argv[4] if len(argv) > 4 else ""
        if not RE_COLA.fullmatch(nombre):
            return 1
        unidad = f"quema-{nombre}"
        return subprocess.run(["systemd-run", "--user", f"--unit={unidad}", "--collect", "--service-type=exec",
                               "--no-block", "-p", "KillMode=process", "--", *argv], capture_output=True,
                              timeout=30).returncode

    @staticmethod
    def _sesion_real(nombre: str) -> bool:
        try:
            for _ in range(20):
                if subprocess.run(["tmux", "has-session", "-t", f"={nombre}"], capture_output=True, timeout=15).returncode == 0:
                    return True
                time.sleep(0.1)
            return False
        except OSError:
            return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ahora", help="Sólo para prueba: fecha ISO-8601")
    a = ap.parse_args()
    momento = _hora(a.ahora) if a.ahora else None
    if a.ahora and momento is None:
        ap.error("--ahora debe ser ISO-8601")
    Quema().ejecutar(momento)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
