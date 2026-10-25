#!/usr/bin/env python3
"""Configuración interactiva del token y propietario de Bot V3."""

from __future__ import annotations

import getpass
import grp
import argparse
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time

import requests


ENV_PATH = Path("/opt/nodo/datos/secretos/botv3.env")
STATE_DIR = Path("/opt/nodo/datos/botv3")


def prepare_agent_homes() -> None:
    owner = pwd.getpwnam("dcifu004")
    group = grp.getgrnam("captura")
    mappings = [
        (
            STATE_DIR / "codex-home" / "auth.json",
            Path("/opt/nodo/datos/agentes/codex-home/auth.json"),
        ),
        (
            STATE_DIR / "claude-config" / ".credentials.json",
            Path("/opt/nodo/datos/agentes/claude-config/.credentials.json"),
        ),
    ]
    runtime_home = STATE_DIR / "runtime-home"
    runtime_home.mkdir(parents=True, exist_ok=True)
    os.chown(runtime_home, owner.pw_uid, group.gr_gid)
    os.chmod(runtime_home, 0o700)
    for link, target in mappings:
        if not target.is_file():
            raise RuntimeError(f"No existe la autenticación requerida: {target}")
        link.parent.mkdir(parents=True, exist_ok=True)
        os.chown(link.parent, owner.pw_uid, group.gr_gid)
        os.chmod(link.parent, 0o700)
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
        os.lchown(link, owner.pw_uid, group.gr_gid)


def api(token: str, method: str, payload: dict | None = None, timeout: int = 35):
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload or {}, timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram devolvió error"))
    return data.get("result")


def write_env(token: str, chat_id: int, user_id: int) -> None:
    owner = pwd.getpwnam("dcifu004")
    group = grp.getgrnam("captura")
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.chown(ENV_PATH.parent, 0, group.gr_gid)
    os.chmod(ENV_PATH.parent, 0o750)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(STATE_DIR, owner.pw_uid, group.gr_gid)
    os.chmod(STATE_DIR, 0o770)
    content = "\n".join([
        f"BOTV3_TOKEN={token}",
        f"BOTV3_CHAT_ID={chat_id}",
        f"BOTV3_USER_ID={user_id}",
        "BOTV3_PERSONAL_VAULT=/opt/nodo/datos/srv/vault_personal",
        "BOTV3_WORK_VAULT=/opt/nodo/datos/srv/vault_trabajo",
        "BOTV3_ALLOW_WORK_VAULT=0",
        "BOTV3_STATE_DIR=/opt/nodo/datos/botv3",
        "BOTV3_SCHEMA=/opt/botv3/proposal.schema.json",
        "BOTV3_MODEL_TIMEOUT=600",
        "BOTV3_N8N_QUERY_URL=",
        "BOTV3_N8N_AUDIT_URL=",
        "BOTV3_N8N_SHARED_SECRET=",
        "",
    ])
    temp = ENV_PATH.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temp, 0, group.gr_gid)
        os.chmod(temp, 0o640)
        os.replace(temp, ENV_PATH)
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-agent-homes", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Ejecuta: sudo python3 /opt/botv3/configure.py", file=sys.stderr)
        return 2
    if not os.path.ismount("/opt/nodo/datos"):
        print("El volumen cifrado no está montado. Ejecuta sudo abrir-datos.", file=sys.stderr)
        return 2
    if args.prepare_agent_homes:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        owner = pwd.getpwnam("dcifu004")
        group = grp.getgrnam("captura")
        os.chown(STATE_DIR, owner.pw_uid, group.gr_gid)
        os.chmod(STATE_DIR, 0o770)
        prepare_agent_homes()
        print("Perfiles operativos de Bot V3 preparados.")
        return 0
    print("Configuración segura de Bot V3")
    print("El token se escribirá oculto y no quedará en el historial.")
    token = getpass.getpass("Token entregado por BotFather: ").strip()
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
        print("El formato del token no parece válido.", file=sys.stderr)
        return 2
    try:
        me = api(token, "getMe", timeout=15)
    except Exception as exc:
        print(f"Telegram no aceptó el token: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    print(f"Bot verificado: @{me.get('username', '(sin username)')}")
    webhook = api(token, "getWebhookInfo", timeout=15)
    if webhook.get("url"):
        print("Se eliminará el webhook anterior para usar long polling privado.")
        api(token, "deleteWebhook", {"drop_pending_updates": False}, timeout=15)
    input("Envía /start al Bot V3 desde tu cuenta y luego presiona Enter aquí... ")
    print("Buscando tu mensaje…")
    selected = None
    offset = 0
    deadline = time.time() + 90
    while time.time() < deadline and selected is None:
        updates = api(token, "getUpdates", {
            "offset": offset, "timeout": 10, "allowed_updates": ["message"],
        }, timeout=15)
        for update in updates:
            offset = max(offset, int(update["update_id"]) + 1)
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            sender = message.get("from") or {}
            if chat.get("type") == "private" and sender.get("is_bot") is not True:
                selected = {
                    "chat_id": int(chat["id"]),
                    "user_id": int(sender["id"]),
                    "name": sender.get("first_name", "usuario"),
                }
        if selected is None:
            print("Aún no aparece. Envía /start nuevamente si es necesario.")
    if selected is None:
        print("No se recibió un mensaje privado en 90 segundos.", file=sys.stderr)
        return 2
    print(
        f"Cuenta detectada: {selected['name']} · chat {selected['chat_id']} · "
        f"usuario {selected['user_id']}"
    )
    confirm = input("¿Autorizar exclusivamente esta cuenta? [s/N]: ").strip().lower()
    if confirm not in {"s", "si", "sí"}:
        print("Configuración cancelada.")
        return 1
    commands = [
        {"command": "estado", "description": "Ver estado general de la Pi"},
        {"command": "uso", "description": "Ver consumo de Claude y Codex"},
        {"command": "claude", "description": "Consultar ambos vaults con Claude"},
        {"command": "codex", "description": "Consultar ambos vaults con Codex"},
        {"command": "sql", "description": "Consultar PostgreSQL vía n8n"},
        {"command": "ha", "description": "Consultar Home Assistant vía n8n"},
        {"command": "gpt", "description": "Consultar OpenAI vía n8n"},
        {"command": "acciones", "description": "Ver alcance de solo lectura"},
        {"command": "ayuda", "description": "Mostrar instrucciones"},
    ]
    api(token, "setMyCommands", {"commands": commands}, timeout=15)
    write_env(token, selected["chat_id"], selected["user_id"])
    prepare_agent_homes()
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "botv3.service"], check=True)
    time.sleep(2)
    status = subprocess.run(
        ["systemctl", "is-active", "botv3.service"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if status != "active":
        print("El servicio no quedó activo. Revisa:")
        print("sudo journalctl -u botv3 -n 80 --no-pager")
        return 2
    api(token, "sendMessage", {
        "chat_id": selected["chat_id"],
        "text": "✅ Dcs_v3bot quedó activo en modo de sólo lectura. Usa /ayuda.",
    }, timeout=15)
    print("Bot V3 activo. El token quedó dentro del volumen cifrado con permisos 640.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
