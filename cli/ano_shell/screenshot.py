"""Captures d'écran plein écran et par zone pour Ano Shell."""

from __future__ import annotations

import subprocess
from argparse import Namespace
from datetime import UTC, datetime

from ano_shell.hypr import message
from ano_shell.notify import notify
from ano_shell.paths import APP_NAME, screenshots_dir


def run_screenshot(args: Namespace) -> int:
    if args.region:
        if args.region == "slurp":
            action = "openFreeze" if args.freeze else "open"
            return subprocess.run(["qs", "-c", APP_NAME, "ipc", "call", "picker", action], check=False).returncode
        sc_data = subprocess.check_output(["grim", "-l", "0", "-g", args.region.strip(), "-"])
        proc = subprocess.Popen(["swappy", "-f", "-"], stdin=subprocess.PIPE, start_new_session=True)
        if proc.stdin:
            proc.stdin.write(sc_data)
            proc.stdin.close()
        return 0

    cmd = ["grim"]
    monitors = message("monitors") or []
    focused = next((m for m in monitors if m.get("focused")), None)
    if focused:
        cmd += ["-o", focused["name"]]
    cmd += ["-"]
    sc_data = subprocess.check_output(cmd)
    subprocess.run(["wl-copy"], input=sc_data, check=False)

    dest = (screenshots_dir / datetime.now(tz=UTC).astimezone().strftime("%Y%m%d%H%M%S")).with_suffix(".png")
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sc_data)

    action = notify(
        "-i",
        "image-x-generic-symbolic",
        "-h",
        f"STRING:image-path:{dest}",
        "--action=open=Ouvrir",
        "Capture d'écran effectuée",
        f"Enregistrée dans {dest} et copiée dans le presse-papiers",
    )
    if action == "open":
        subprocess.Popen(["swappy", "-f", str(dest)], start_new_session=True)
    return 0
