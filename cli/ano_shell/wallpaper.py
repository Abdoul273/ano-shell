"""Gestion du fond d'écran et extraction de palette Material You pour Ano Shell."""

from __future__ import annotations

import json
import os
import random
import subprocess
from pathlib import Path
from typing import Any, cast

from PIL import Image

from ano_shell.colourfulness import get_variant
from ano_shell.hypr import message
from ano_shell.material import get_colours_for_image
from ano_shell.paths import (
    compute_hash,
    get_config,
    wallpaper_link_path,
    wallpaper_path_path,
    wallpaper_thumbnail_path,
    wallpapers_cache_dir,
)
from ano_shell.scheme import Scheme, get_scheme
from ano_shell.theme import apply_colours

VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".gif"}


def is_valid_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VALID_EXTS


def get_wallpaper() -> str | None:
    try:
        return wallpaper_path_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def convert_gif(wall: Path) -> Path:
    cache = wallpapers_cache_dir / compute_hash(wall)
    out = cache / "first_frame.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(wall) as img:
            try:
                img.seek(0)
            except EOFError:
                pass
            img.convert("RGB").save(out, "PNG")
    return out


def get_thumb(wall: Path, cache: Path) -> Path:
    thumb = cache / "thumbnail.jpg"
    if not thumb.exists():
        with Image.open(wall) as img:
            img = img.convert("RGB")
            img.thumbnail((128, 128), Image.Resampling.NEAREST)
            thumb.parent.mkdir(parents=True, exist_ok=True)
            img.save(thumb, "JPEG")
    return thumb


def get_smart_opts(wall: Path, cache: Path) -> dict[str, str]:
    opts_cache = cache / "smart.json"
    try:
        return json.loads(opts_cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    from materialyoucolor.hct import Hct
    from materialyoucolor.utils.color_utils import argb_from_rgb

    with Image.open(get_thumb(wall, cache)) as img:
        variant = get_variant(img)
        img.thumbnail((1, 1), Image.Resampling.LANCZOS)
        pixel = cast(tuple[int, int, int], img.getpixel((0, 0)))
        hct = Hct.from_int(argb_from_rgb(*pixel))
        mode = "light" if hct.tone > 60 else "dark"

    opts = {"variant": variant, "mode": mode}
    opts_cache.parent.mkdir(parents=True, exist_ok=True)
    opts_cache.write_text(json.dumps(opts), encoding="utf-8")
    return opts


def get_colours_for_wall(wall: Path | str, no_smart: bool = False) -> dict[str, Any]:
    wall_p = Path(wall)
    scheme = get_scheme()
    cache = wallpapers_cache_dir / compute_hash(wall_p)
    if wall_p.suffix.lower() == ".gif":
        wall_p = convert_gif(wall_p)

    if not no_smart:
        smart = get_smart_opts(wall_p, cache)
        scheme = Scheme(
            {
                "name": "dynamic",
                "flavour": scheme.flavour,
                "mode": smart["mode"],
                "variant": smart["variant"],
                "colours": scheme.colours,
            }
        )

    return {
        "name": "dynamic",
        "flavour": scheme.flavour,
        "mode": scheme.mode,
        "variant": scheme.variant,
        "colours": get_colours_for_image(get_thumb(wall_p, cache), scheme),
    }


def set_wallpaper(wall: Path | str, no_smart: bool = False) -> None:
    wall_p = Path(wall).resolve()
    if not is_valid_image(wall_p):
        raise ValueError(f'"{wall_p}" is not a valid image')

    wall_cache = convert_gif(wall_p) if wall_p.suffix.lower() == ".gif" else wall_p
    wallpaper_path_path.parent.mkdir(parents=True, exist_ok=True)
    wallpaper_path_path.write_text(str(wall_p), encoding="utf-8")

    wallpaper_link_path.unlink(missing_ok=True)
    wallpaper_link_path.symlink_to(wall_p)

    cache = wallpapers_cache_dir / compute_hash(wall_cache)
    thumb = get_thumb(wall_cache, cache)
    wallpaper_thumbnail_path.unlink(missing_ok=True)
    wallpaper_thumbnail_path.symlink_to(thumb)

    scheme = get_scheme()
    if scheme.name == "dynamic" and not no_smart:
        smart = get_smart_opts(wall_cache, cache)
        scheme.mode = smart["mode"]
        scheme.variant = smart["variant"]

    scheme.update_colours()
    apply_colours(scheme.colours, scheme.mode)

    cfg = get_config().get("wallpaper", {})
    if post_hook := cfg.get("postHook"):
        subprocess.run(
            post_hook,
            shell=True,
            env={
                **os.environ,
                "WALLPAPER_PATH": str(wall_p),
                "SCHEME_NAME": scheme.name,
                "SCHEME_FLAVOUR": scheme.flavour,
                "SCHEME_MODE": scheme.mode,
                "SCHEME_VARIANT": scheme.variant,
                "SCHEME_COLOURS": json.dumps(scheme.colours),
                "THUMBNAIL_PATH": str(thumb),
            },
            stderr=subprocess.DEVNULL,
            check=False,
        )


def set_random(directory: Path | str, threshold: float = 0.8, no_filter: bool = False, no_smart: bool = False) -> None:
    d = Path(directory)
    if not d.is_dir():
        raise ValueError(f"Wallpaper directory not found: {d}")
    walls = [f for f in d.rglob("*") if is_valid_image(f)]
    if not no_filter:
        monitors = message("monitors") or []
        if monitors:
            min_w = min(m["width"] for m in monitors)
            min_h = min(m["height"] for m in monitors)
            filtered = []
            for w in walls:
                try:
                    with Image.open(w) as img:
                        if img.size[0] >= min_w * threshold and img.size[1] >= min_h * threshold:
                            filtered.append(w)
                except OSError:
                    pass
            walls = filtered or walls
    if not walls:
        raise ValueError("No valid wallpapers found")
    cur = get_wallpaper()
    if cur and len(walls) > 1:
        walls = [w for w in walls if str(w.resolve()) != str(Path(cur).resolve())] or walls
    set_wallpaper(random.choice(walls), no_smart=no_smart)
