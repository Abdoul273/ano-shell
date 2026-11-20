"""Extraction et mise en cache Material You pour un fond d'écran."""

from __future__ import annotations

import json
from pathlib import Path

from ano_shell.paths import compute_hash, scheme_cache_dir, wallpaper_thumbnail_path


def get_score_for_image(image: Path | str, cache_base: Path):
    from materialyoucolor.hct import Hct

    cache = cache_base / "score.json"
    try:
        return Hct.from_int(int(cache.read_text(encoding="utf-8").strip()))
    except (OSError, TypeError, ValueError):
        pass

    from ano_shell.material.score import score

    s = score(str(image))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(str(s.to_int()), encoding="utf-8")
    return s


def get_colours_for_image(image: Path | str = wallpaper_thumbnail_path, scheme=None) -> dict[str, str]:
    if scheme is None:
        from ano_shell.scheme import get_scheme

        scheme = get_scheme()

    cache_base = scheme_cache_dir / compute_hash(image)
    cache = (cache_base / scheme.variant / scheme.flavour / scheme.mode).with_suffix(".json")
    try:
        return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    from ano_shell.material.generator import gen_scheme

    primary = get_score_for_image(image, cache_base)
    colours = gen_scheme(scheme, primary)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(colours), encoding="utf-8")
    return colours
