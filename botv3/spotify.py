"""Spotify local: frases, búsqueda Web API y receptor go-librespot.

No conoce Telegram ni escribe estado: el token Client Credentials vive sólo en
memoria de este proceso.  La API del receptor es siempre loopback y la Web API
recibe la búsqueda mediante ``params``, nunca interpolada en una URL.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from typing import Any

import requests
from rapidfuzz.fuzz import WRatio


TIMEOUT = 3
MAX_CONSULTA = 120
TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
_TOKEN = ""
_TOKEN_HASTA = 0.0


class SpotifyError(RuntimeError):
    """Error esperado; su texto nunca incluye una credencial ni una URL."""


def plano(valor: object) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(valor or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", plano(texto).strip(" ¿?¡!.,;:\"'“”«»"))


def vocativo_ajeno(texto: str, nombre: str) -> bool:
    """Indica si el comienzo llama explícitamente al otro asistente."""
    frase = _limpiar(texto)
    encontrado = re.match(r"^(?:(?:hola|hey|oye|buenas)\s+)?(jaime|pilar)(?:\s+|[.,:;]+\s*)", frase)
    return bool(encontrado and encontrado.group(1) != plano(nombre))


def interpretar(texto: str, sonando: bool) -> dict[str, str] | None:
    """Interpreta sólo las frases completas de música aprobadas en diseño 36."""
    frase = _limpiar(texto)
    # El filtro del bot ya rechazó un vocativo dirigido al otro perfil. Aquí se
    # acepta el vocativo inicial para conservar la función pura sobre la forma
    # real que entrega Whisper.
    frase = re.sub(r"^(?:(?:hola|hey|oye|buenas)\s+)?(?:jaime|pilar)(?:\s+|[.,:;]+\s*)", "", frase)
    if len(frase) > MAX_CONSULTA or not frase:
        return None

    en_spotify = bool(re.search(r"\s+en\s+spotify$", frase))
    frase = re.sub(r"\s+en\s+spotify$", "", frase)
    if re.fullmatch(r"(?:pausa(?:\s+(?:la\s+)?(?:musica|spotify))?|para\s+(?:la\s+)?(?:musica|spotify))", frase):
        return {"accion": "pausa"} if sonando or frase != "pausa" else None
    if re.fullmatch(r"(?:sigue|continua|reanuda)(?:\s+(?:con\s+)?(?:la\s+)?(?:musica|spotify))?", frase):
        # 88d: «sigue» a secas también es conversación; el bot la toma sólo si su receptor está en pausa.
        return {"accion": "sigue", "sola": True} if frase in ("sigue", "continua", "reanuda") else {"accion": "sigue"}

    verbo = r"(?:reproduce|reproducir|pon|pone|toca|tocame)"
    # «pon una alarma/temporizador» ya pertenece a temporizadores: poner música
    # exige nombrar Spotify incluso si trae un «de …» que parece artista.
    # 88d: «toca» igual. En Chile «toca pagar la cuenta de la luz» es «es hora de…»;
    # «tócame …» sí es música y no entra acá (`\b` no corta «tocame»).
    if re.match(r"^(?:pon|pone|toca)\b", frase) and not en_spotify:
        return None
    m = re.fullmatch(rf"{verbo}\s+(?:musica\s+de|a)\s+(.+?)", frase)
    if m and m.group(1).strip():
        return {"accion": "artista", "artista": m.group(1).strip()}

    # Una canción sin artista necesita decir Spotify; con «de artista» ya es
    # inequívoca. Así «reproducir la última nota» sigue al router.
    m = re.fullmatch(rf"{verbo}\s+(.+?)\s+de\s+(.+?)", frase)
    # 88d: «reproduce la última nota de mi proyecto»: un «artista» con posesivo,
    # demostrativo o día no es un artista, salvo que se haya dicho Spotify. Los
    # artículos no cuentan: «Los Prisioneros» y «La Ley» son artistas.
    # 88e: en CUALQUIER « de <palabra> » de la frase, no sólo tras el primer «de»
    # («la nota de voz de mi mamá»), y también «anoche» y «recién».
    if m and not en_spotify and re.search(r"\bde\s+(?:mis?|tus?|sus?|nuestr[oa]s?|est[eao]s?|es[eao]s?|ayer|hoy|manana|anoche|recien)\b", frase):
        return None
    if m and m.group(1).strip() and m.group(2).strip():
        return {"accion": "cancion", "titulo": m.group(1).strip(), "artista": m.group(2).strip()}
    m = re.fullmatch(rf"{verbo}\s+(.+?)", frase)
    if en_spotify and m and m.group(1).strip():
        return {"accion": "cancion", "titulo": m.group(1).strip()}
    return None


def _token(sesion: requests.Session) -> str:
    global _TOKEN, _TOKEN_HASTA
    if _TOKEN and time.monotonic() < _TOKEN_HASTA:
        return _TOKEN
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    secreto = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not secreto:
        raise SpotifyError("faltan las claves de Spotify")
    try:
        respuesta = sesion.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                                auth=(client_id, secreto), timeout=TIMEOUT)
        respuesta.raise_for_status()
        datos = respuesta.json()
        token = str(datos.get("access_token", ""))
        vence = int(datos.get("expires_in", 0))
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise SpotifyError("no pude buscar en Spotify") from exc
    if not token or vence <= 60:
        raise SpotifyError("no pude buscar en Spotify")
    _TOKEN, _TOKEN_HASTA = token, time.monotonic() + vence - 60
    return _TOKEN


def _items(datos: dict[str, Any], tipo: str) -> list[dict[str, Any]]:
    bloque = datos.get(f"{tipo}s", {})
    return list(bloque.get("items", [])) if isinstance(bloque, dict) else []


def buscar(consulta: dict[str, str] | str, sesion: requests.Session) -> list[dict[str, Any]]:
    """Busca hasta cinco pistas o artistas; prueba campos y luego texto libre."""
    if isinstance(consulta, dict):
        accion = consulta.get("accion", "cancion")
        tipo = "artist" if accion == "artista" else "track"
        titulo = str(consulta.get("titulo", "")).strip()[:MAX_CONSULTA]
        artista = str(consulta.get("artista", "")).strip()[:MAX_CONSULTA]
        campos = " ".join(x for x in ([f"track:{titulo}"] if titulo else []) +
                           ([f"artist:{artista}"] if artista else []))
        libre = " ".join(x for x in (titulo, artista) if x)
    else:
        tipo, campos, libre = "track", str(consulta).strip()[:MAX_CONSULTA], str(consulta).strip()[:MAX_CONSULTA]
    if not campos:
        return []
    headers = {"Authorization": f"Bearer {_token(sesion)}"}
    try:
        respuesta = sesion.get(SEARCH_URL, headers=headers,
                               params={"q": campos, "type": tipo, "market": "CL", "limit": 5}, timeout=TIMEOUT)
        respuesta.raise_for_status()
        datos = respuesta.json()
        encontrados = _items(datos, tipo)
        if encontrados or libre == campos:
            return encontrados
        respuesta = sesion.get(SEARCH_URL, headers=headers,
                               params={"q": libre, "type": tipo, "market": "CL", "limit": 5}, timeout=TIMEOUT)
        respuesta.raise_for_status()
        return _items(respuesta.json(), tipo)
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise SpotifyError("no pude buscar en Spotify") from exc


def elegir(resultados: list[dict[str, Any]], titulo: str = "", artista: str = "") -> dict[str, Any] | None:
    """Elige por título y artista, tolerando las tildes y errores de Whisper."""
    mejor: dict[str, Any] | None = None
    puntaje_mejor = -1.0
    for item in resultados:
        nombre = plano(item.get("name", ""))
        autores = " ".join(plano(a.get("name", "")) for a in item.get("artists", []) if isinstance(a, dict)) or nombre
        pt = WRatio(plano(titulo), nombre) if titulo else 100
        pa = WRatio(plano(artista), autores) if artista else 100
        puntaje = pt * 0.7 + pa * 0.3
        if puntaje > puntaje_mejor:
            mejor, puntaje_mejor = item, puntaje
    return mejor


def _url(base: str, ruta: str) -> str:
    return base.rstrip("/") + ruta


def _peticion(metodo: str, base: str, ruta: str, **kwargs: Any) -> tuple[int, dict[str, Any] | None]:
    try:
        respuesta = requests.request(metodo, _url(base, ruta), timeout=TIMEOUT, **kwargs)
        if respuesta.status_code == 204:
            return 204, None
        respuesta.raise_for_status()
        return respuesta.status_code, respuesta.json() if respuesta.content else {}
    except (requests.RequestException, ValueError) as exc:
        raise SpotifyError("el receptor Spotify no está disponible") from exc


def estado(base: str) -> dict[str, Any] | None:
    _, datos = _peticion("GET", base, "/status")
    return datos


def codigo(base: str) -> dict[str, Any] | None:
    _, datos = _peticion("GET", base, "/auth/code")
    return datos


def reproducir(base: str, uri: str) -> None:
    _peticion("POST", base, "/player/play", json={"uri": uri})


def pausar(base: str) -> None:
    _peticion("POST", base, "/player/pause")


def reanudar(base: str) -> None:
    _peticion("POST", base, "/player/resume")


def volumen(base: str, valor: int) -> None:
    """Reservado para la ampliación de volumen por voz."""
    _peticion("POST", base, "/player/volume", json={"volume": int(valor)})
