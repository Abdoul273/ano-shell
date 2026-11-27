"""Pilotage de l'instance Quickshell `ano-shell` avec garde-fou anti-verrouillage."""

from __future__ import annotations

import subprocess
import sys
from argparse import Namespace

from ano_shell.i18n import tr
from ano_shell.paths import APP_NAME, app_cache_dir


def is_locked() -> bool:
    try:
        out = subprocess.check_output(
            ["qs", "-c", APP_NAME, "ipc", "call", "lock", "isLocked"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        return out.strip().lower() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def qs_call(*args: str) -> str:
    return subprocess.check_output(["qs", "-c", APP_NAME, *args], text=True)


def run_shell(args: Namespace) -> int:
    if args.show:
        print(qs_call("ipc", "show"), end="")
        return 0

    if args.log:
        log_args = ["log", "-r", args.log_rules] if args.log_rules else ["log"]
        for line in qs_call(*log_args).splitlines():
            if f"Cannot open: file://{app_cache_dir}/imagecache/" not in line:
                print(line)
        return 0

    if args.kill:
        if not getattr(args, "force", False) and is_locked():
            print(
                tr(
                    "Refus d'arrêter ano-shell pendant que l'écran est verrouillé (utilisez --force pour outrepasser).",
                    "Refusing to stop ano-shell while the screen is locked (use --force to override).",
                ),
                file=sys.stderr,
            )
            return 2
        subprocess.run(["qs", "-c", APP_NAME, "kill"], check=False)
        return 0

    if args.message:
        print(qs_call("ipc", "call", *args.message), end="")
        return 0

    cmd = ["qs", "-c", APP_NAME, "-n"]
    if args.log_rules:
        cmd.extend(["--log-rules", args.log_rules])
    if args.daemon:
        cmd.append("-d")
        return subprocess.run(cmd, check=False).returncode

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    if proc.stdout:
        for line in proc.stdout:
            if f"Cannot open: file://{app_cache_dir}/imagecache/" not in line:
                print(line, end="")
    return proc.wait()
