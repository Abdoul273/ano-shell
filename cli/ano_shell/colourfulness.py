"""Évaluation de la richesse chromatique d'une image pour choisir la variante Material You."""

from __future__ import annotations

import math

from PIL import Image


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float], mean_val: float) -> float:
    return math.sqrt(sum((x - mean_val) ** 2 for x in values) / len(values)) if values else 0.0


def calc_colourfulness(image: Image.Image) -> float:
    pixels = list(image.convert("RGB").getdata())
    rg_diffs = [abs(r - g) for r, g, _ in pixels]
    yb_diffs = [abs(0.5 * (r + g) - b) for r, g, b in pixels]
    mean_rg, mean_yb = _mean(rg_diffs), _mean(yb_diffs)
    std_rg, std_yb = _stddev(rg_diffs, mean_rg), _stddev(yb_diffs, mean_yb)
    return math.sqrt(std_rg**2 + std_yb**2) + 0.3 * math.sqrt(mean_rg**2 + mean_yb**2)


def get_variant(image: Image.Image) -> str:
    colourfulness = calc_colourfulness(image)
    if colourfulness < 10:
        return "neutral"
    if colourfulness < 20:
        return "content"
    return "tonalspot"
