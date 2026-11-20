"""Enregistrement vidéo d'écran via gpu-screen-recorder."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

from ano_shell.hypr import message
from ano_shell.notify import close_notification, notify
from ano_shell.paths import (
    get_config,
    recording_notif_path,
    recording_path,
    recordings_dir,
)

RECORDER = "gpu-screen-recorder"


def _running() -> bool:
    return subprocess.run(["pidof", RECORDER], stdout=subprocess.DEVNULL, check=False).returncode == 0


def _intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def run_record(args: Namespace) -> int:
    if args.pause:
        subprocess.run(["pkill", "-USR2", "-x", RECORDER], stdout=subprocess.DEVNULL, check=False)
        return 0
    if _running():
        return _stop(args)
    return _start(args)


def _start(args: Namespace) -> int:
    rec_args = ["-w"]
    monitors = message("monitors") or []
    if args.region:
        region = (
            subprocess.check_output(["slurp", "-f", "%wx%h+%x+%y"], text=True).strip()
            if args.region == "slurp"
            else args.region.strip()
        )
        m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", region)
        if not m:
            raise ValueError(f"Invalid region: {region}")
        w, h, x, y = map(int, m.groups())
        max_rr = 60
        for mon in monitors:
            if _intersects((mon["x"], mon["y"], mon["width"], mon["height"]), (x, y, w, h)):
                max_rr = max(max_rr, round(mon["refreshRate"]))
        rec_args += ["region", "-region", region, "-f", str(max_rr)]
    else:
        focused = next((m for m in monitors if m.get("focused")), None)
        if focused:
            rec_args += [focused["name"], "-f", str(round(focused["refreshRate"]))]

    if args.sound:
        rec_args += ["-a", "default_output"]

    cfg = get_config()
    extra = cfg.get("record", {}).get("extraArgs", [])
    if isinstance(extra, list):
        rec_args += [str(x) for x in extra]

    recording_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([RECORDER, *rec_args, "-o", str(recording_path)], start_new_session=True)

    notif_id = notify("-p", "Enregistrement démarré", "Enregistrement en cours...")
    recording_notif_path.parent.mkdir(parents=True, exist_ok=True)
    recording_notif_path.write_text(notif_id, encoding="utf-8")

    try:
        if proc.wait(1.0) != 0:
            close_notification(notif_id)
            notify("Échec de l'enregistrement", f"{RECORDER} s'est arrêté (code {proc.returncode}).")
            return proc.returncode
    except subprocess.TimeoutExpired:
        pass
    return 0


def _stop(args: Namespace) -> int:
    subprocess.run(["pkill", "-INT", "-x", RECORDER], stdout=subprocess.DEVNULL, check=False)
    for _ in range(100):
        if not _running():
            break
        time.sleep(0.1)

    if not recording_path.exists():
        return 0

    recordings_dir.mkdir(parents=True, exist_ok=True)
    new_path = recordings_dir / f"recording_{datetime.now(tz=UTC).astimezone().strftime('%Y%m%d_%H-%M-%S')}.mp4"
    shutil.move(str(recording_path), str(new_path))

    try:
        close_notification(recording_notif_path.read_text(encoding="utf-8"))
    except OSError:
        pass

    if args.clipboard:
        uri = Path(new_path).resolve().as_uri() + "\n"
        subprocess.run(["wl-copy", "--type", "text/uri-list"], input=uri.encode("utf-8"), check=False)

    action = notify(
        "--action=watch=Regarder",
        "--action=open=Ouvrir",
        "--action=delete=Supprimer",
        "Enregistrement terminé",
        f"Sauvegardé dans {new_path}",
    )
    if action == "watch":
        subprocess.Popen(["xdg-open", str(new_path)], start_new_session=True)
    elif action == "open":
        subprocess.Popen(["xdg-open", str(new_path.parent)], start_new_session=True)
    elif action == "delete":
        new_path.unlink(missing_ok=True)
    return 0
