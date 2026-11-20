"""Communication IPC légère avec Hyprland."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

from ano_shell.paths import config_dir


def is_lua_config() -> bool:
    return (config_dir / "hypr/hyprland.lua").is_file()


def _socket_path() -> Path | None:
    sig = os.getenv("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return None
    runtime = Path(os.getenv("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    sock = runtime / "hypr" / sig / ".socket.sock"
    return sock if sock.exists() else None


def message(cmd: str, json_out: bool = True) -> Any:
    sock_path = _socket_path()
    if sock_path is None:
        return [] if json_out else ""
    payload = f"j/{cmd}" if json_out else cmd
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        s.connect(str(sock_path))
        s.sendall(payload.encode("utf-8"))
        chunks: list[bytes] = []
        while data := s.recv(65536):
            chunks.append(data)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return json.loads(text) if json_out and text.strip() else text
