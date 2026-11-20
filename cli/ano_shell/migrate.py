"""Migration douce et non destructive des réglages de Caelestia vers Ano Shell."""

from __future__ import annotations

import shutil
from pathlib import Path

from ano_shell.paths import (
    app_config_dir,
    app_data_dir,
    app_state_dir,
    config_dir,
    data_dir,
    state_dir,
)

CONFIG_FILES = [
    "glass.json",
    "island.json",
    "shell.json",
    "power.json",
    "lang.json",
    "cli.json",
]

STATE_FILES = [
    "scheme.json",
    "dock.json",
    "caffeine.json",
    "focus.json",
    "nightlight.json",
    "battery.json",
    "record-prefs.json",
    "task-reminders.json",
    "wallpaper/path.txt",
    "wallpaper/animated.txt",
]


def _copy_if_missing(src: Path, dst: Path, force: bool, dry_run: bool) -> str | None:
    if not src.exists():
        return None
    if dst.exists() and not force:
        return None
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return f"{src} -> {dst}"


def run_migrate(force: bool = False, dry_run: bool = False) -> int:
    old_cfg = config_dir / "caelestia"
    old_state = state_dir / "caelestia"
    old_data = data_dir / "caelestia"

    copied: list[str] = []

    for rel in CONFIG_FILES:
        res = _copy_if_missing(old_cfg / rel, app_config_dir / rel, force, dry_run)
        if res:
            copied.append(res)

    for rel in STATE_FILES:
        res = _copy_if_missing(old_state / rel, app_state_dir / rel, force, dry_run)
        if res:
            copied.append(res)

    # Liens symboliques du fond d'écran courant
    for name in ("current", "thumbnail.jpg"):
        src = old_state / "wallpaper" / name
        dst = app_state_dir / "wallpaper" / name
        if src.is_symlink() and (force or not dst.exists()):
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.unlink(missing_ok=True)
                dst.symlink_to(src.resolve())
            copied.append(f"{src} -> {dst}")

    # Sons personnalisés
    old_sounds = old_data / "sounds"
    new_sounds = app_data_dir / "sounds"
    if old_sounds.exists() and (force or not new_sounds.exists()):
        if not dry_run:
            new_sounds.parent.mkdir(parents=True, exist_ok=True)
            if old_sounds.is_symlink():
                new_sounds.unlink(missing_ok=True)
                new_sounds.symlink_to(old_sounds.resolve())
            else:
                shutil.copytree(old_sounds, new_sounds, dirs_exist_ok=True)
        copied.append(f"{old_sounds} -> {new_sounds}")

    prefix = "[dry-run] " if dry_run else ""
    if not copied:
        print(f"{prefix}Aucun nouveau fichier à migrer depuis Caelestia.")
    else:
        for line in copied:
            print(f"{prefix}Migré : {line}")
        print(f"{prefix}{len(copied)} élément(s) migré(s) sans modifier Caelestia.")
    return 0
