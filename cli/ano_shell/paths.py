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


def _xdg_user_dir(key: str, *fallbacks: str) -> Path:
    if env := os.getenv(key):
        return Path(env)
    user_dirs = config_dir / "user-dirs.dirs"
    try:
        for line in user_dirs.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(HOME))
                if val:
                    return Path(val)
    except OSError:
        pass
    for name in fallbacks:
        p = HOME / name
        if p.exists():
            return p
    return HOME / fallbacks[0]


pictures_dir = _xdg_user_dir("XDG_PICTURES_DIR", "Pictures", "Images")
videos_dir = _xdg_user_dir("XDG_VIDEOS_DIR", "Videos", "Vidéos")

app_config_dir = config_dir / APP_NAME
app_data_dir = data_dir / APP_NAME
app_state_dir = state_dir / APP_NAME
app_cache_dir = cache_dir / APP_NAME

cli_config_path = app_config_dir / "cli.json"
glass_config_path = app_config_dir / "glass.json"
island_config_path = app_config_dir / "island.json"
lang_config_path = app_config_dir / "lang.json"
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


def _localized_media_dir(base: Path, fr_name: str, en_name: str) -> Path:
    fr_path = base / fr_name
    en_path = base / en_name
    if fr_path.exists():
        return fr_path
    if en_path.exists():
        return en_path
    from ano_shell.i18n import is_fr

    return fr_path if is_fr() else en_path


screenshots_dir = _localized_media_dir(pictures_dir, "Captures", "Screenshots")
recordings_dir = _localized_media_dir(videos_dir, "ENREGISTREMENTS ECRAN", "Recordings")

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
