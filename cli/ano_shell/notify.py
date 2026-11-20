"""Notifications bureau via notify-send."""

from __future__ import annotations

import shutil
import subprocess


def notify(*args: str) -> str:
    if not shutil.which("notify-send"):
        return ""
    try:
        out = subprocess.check_output(
            ["notify-send", "-a", "ano-shell", *args],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def close_notification(notif_id: str) -> None:
    nid = notif_id.strip()
    if not nid.isdigit() or not shutil.which("gdbus"):
        return
    subprocess.run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.freedesktop.Notifications",
            "--object-path",
            "/org/freedesktop/Notifications",
            "--method",
            "org.freedesktop.Notifications.CloseNotification",
            nid,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
