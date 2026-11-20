"""Chemins XDG et écritures atomiques pour Ano Shell."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

APP_NAME = "ano-shell"
HOME = Path.home()

config_dir = Path(os.getenv("XDG_CONFIG_HOME") or HOME / ".config")
data_dir = Path(os.getenv("XDG_DATA_HOME") or HOME / ".local/share")
state_dir = Path(os.getenv("XDG_STATE_HOME") or HOME / ".local/state")
cache_dir = Path(os.getenv("XDG_CACHE_HOME") or HOME / ".cache")
pictures_dir = Path(os.getenv("XDG_PICTURES_DIR") or HOME / "Images")
videos_dir = Path(os.getenv("XDG_VIDEOS_DIR") or HOME / "Vidéos")

app_config_dir = config_dir / APP_NAME
app_data_dir = data_dir / APP_NAME
app_state_dir = state_dir / APP_NAME
app_cache_dir = cache_dir / APP_NAME

cli_config_path = app_config_dir / "cli.json"
glass_config_path = app_config_dir / "glass.json"
island_config_path = app_config_dir / "island.json"
shell_config_path = app_config_dir / "shell.json"
user_templates_dir = app_config_dir / "templates"

scheme_path = app_state_dir / "scheme.json"
theme_dir = app_state_dir / "theme"
wallpaper_dir = app_state_dir / "wallpaper"
wallpaper_path_path = wallpaper_dir / "path.txt"
wallpaper_link_path = wallpaper_dir / "current"
wallpaper_thumbnail_path = wallpaper_dir / "thumbnail.jpg"
recording_path = app_state_dir / "record/recording.mp4"
recording_notif_path = app_state_dir / "record/notifid.txt"

scheme_cache_dir = app_cache_dir / "schemes"
wallpapers_cache_dir = app_cache_dir / "wallpapers"

screenshots_dir = pictures_dir / "Captures"
recordings_dir = videos_dir / "ENREGISTREMENTS ECRAN"

pkg_data_dir = Path(__file__).resolve().parent / "data"
scheme_data_dir = pkg_data_dir / "schemes"
templates_dir = pkg_data_dir / "templates"
gtk_glass_dir = pkg_data_dir / "gtk-glass"


def compute_hash(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def atomic_dump(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, indent=4, ensure_ascii=False) + "\n")


def write_if_changed(path: Path, content: str) -> bool:
    try:
        if not path.is_symlink() and path.read_text(encoding="utf-8") == content:
            return False
    except OSError:
        pass
    if path.is_symlink():
        path.unlink()
    atomic_write(path, content)
    return True


def get_config() -> dict[str, Any]:
    try:
        return json.loads(cli_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else (default or {})
    except (OSError, json.JSONDecodeError):
        return dict(default) if default else {}
