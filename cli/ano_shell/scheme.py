"""Gestion des palettes de couleurs et schémas Material You pour Ano Shell."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from ano_shell.notify import notify
from ano_shell.paths import atomic_dump, scheme_data_dir, scheme_path

SCHEME_VARIANTS = [
    "tonalspot",
    "vibrant",
    "expressive",
    "fidelity",
    "fruitsalad",
    "monochrome",
    "neutral",
    "rainbow",
    "content",
]


def read_colours_from_file(path: Path) -> dict[str, str]:
    colours: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        k, _, v = line.partition(" ")
        if k and v:
            colours[k.strip()] = v.strip()
    return colours


def get_scheme_names() -> list[str]:
    names = sorted(f.name for f in scheme_data_dir.iterdir() if f.is_dir()) if scheme_data_dir.is_dir() else []
    return [*names, "dynamic"]


def get_scheme_flavours(name: str | None = None) -> list[str]:
    if name is None:
        name = get_scheme().name
    if name == "dynamic":
        return ["default", "hard"]
    d = scheme_data_dir / name
    return sorted(f.name for f in d.iterdir() if f.is_dir()) if d.is_dir() else ["default"]


def get_scheme_modes(name: str | None = None, flavour: str | None = None) -> list[str]:
    if name is None or flavour is None:
        cur = get_scheme()
        name = name or cur.name
        flavour = flavour or cur.flavour
    if name == "dynamic":
        return ["light", "dark"]
    d = scheme_data_dir / name / flavour
    return sorted(f.stem for f in d.iterdir() if f.is_file()) if d.is_dir() else ["dark"]


class Scheme:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        if data is None:
            self._name = "catppuccin"
            self._flavour = "mocha"
            self._mode = "dark"
            self._variant = "tonalspot"
            self._colours = read_colours_from_file(self.get_colours_path())
        else:
            self._name = data.get("name", "catppuccin")
            self._flavour = data.get("flavour", "mocha")
            self._mode = data.get("mode", "dark")
            self._variant = data.get("variant", "tonalspot")
            self._colours = dict(data.get("colours", {}))
        self.notify = False

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if value == self._name:
            return
        if value not in get_scheme_names():
            if self.notify:
                notify("-u", "critical", "Schéma invalide", f'"{value}" n\'existe pas.')
            raise ValueError(f"Invalid scheme name: {value}")
        self._name = value
        self._check_flavour()
        self._check_mode()
        self.update_colours()

    @property
    def flavour(self) -> str:
        return self._flavour

    @flavour.setter
    def flavour(self, value: str) -> None:
        if value == self._flavour:
            return
        valid = get_scheme_flavours(self._name)
        if value not in valid:
            raise ValueError(f"Invalid scheme flavour: {value} (valid: {valid})")
        self._flavour = value
        self._check_mode()
        self.update_colours()

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value == self._mode:
            return
        valid = get_scheme_modes(self._name, self._flavour)
        if value not in valid:
            raise ValueError(f"Invalid scheme mode: {value} (valid: {valid})")
        self._mode = value
        self.update_colours()

    @property
    def variant(self) -> str:
        return self._variant

    @variant.setter
    def variant(self, value: str) -> None:
        if value == self._variant:
            return
        self._variant = value
        self.update_colours()

    @property
    def colours(self) -> dict[str, str]:
        return self._colours

    def get_colours_path(self) -> Path:
        return (scheme_data_dir / self._name / self._flavour / self._mode).with_suffix(".txt")

    def save(self) -> None:
        scheme_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_dump(
            scheme_path,
            {
                "name": self._name,
                "flavour": self._flavour,
                "mode": self._mode,
                "variant": self._variant,
                "colours": self._colours,
            },
        )

    def set_random(self) -> None:
        names = [n for n in get_scheme_names() if n != "dynamic"]
        self._name = random.choice(names)
        self._flavour = random.choice(get_scheme_flavours(self._name))
        self._mode = random.choice(get_scheme_modes(self._name, self._flavour))
        self.update_colours()

    def update_colours(self) -> None:
        self._update_colours()
        self.save()

    def _check_flavour(self) -> None:
        flavours = get_scheme_flavours(self._name)
        if self._flavour not in flavours:
            self._flavour = flavours[0]

    def _check_mode(self) -> None:
        modes = get_scheme_modes(self._name, self._flavour)
        if self._mode not in modes:
            self._mode = modes[0]

    def _update_colours(self) -> None:
        if self._name == "dynamic":
            from ano_shell.material import get_colours_for_image

            try:
                self._colours = get_colours_for_image(scheme=self)
            except FileNotFoundError as exc:
                if self.notify:
                    notify(
                        "-u",
                        "critical",
                        "Schéma dynamique indisponible",
                        "Définis d'abord un fond d'écran avec `ano-shell wallpaper -f <image>`.",
                    )
                raise ValueError("No wallpaper set for dynamic scheme") from exc
        else:
            self._colours = read_colours_from_file(self.get_colours_path())

    def __str__(self) -> str:
        return (
            f"Current scheme:\n"
            f"    Name: {self.name}\n"
            f"    Flavour: {self.flavour}\n"
            f"    Mode: {self.mode}\n"
            f"    Variant: {self.variant}\n"
        )


_cached_scheme: Scheme | None = None


def get_scheme(reload: bool = False) -> Scheme:
    global _cached_scheme
    if _cached_scheme is None or reload:
        try:
            data = json.loads(scheme_path.read_text(encoding="utf-8"))
            _cached_scheme = Scheme(data)
        except (OSError, json.JSONDecodeError):
            _cached_scheme = Scheme(None)
            _cached_scheme.save()
    return _cached_scheme


def list_all_schemes() -> dict[str, dict[str, dict[str, str]]]:
    cur = get_scheme()
    out: dict[str, dict[str, dict[str, str]]] = {}
    for name in get_scheme_names():
        out[name] = {}
        for flavour in get_scheme_flavours(name):
            s = Scheme(
                {
                    "name": name,
                    "flavour": flavour,
                    "mode": cur.mode,
                    "variant": cur.variant,
                    "colours": cur.colours,
                }
            )
            modes = get_scheme_modes(name, flavour)
            if s.mode not in modes:
                s._mode = modes[0]
            try:
                s._update_colours()
                out[name][flavour] = s.colours
            except (ValueError, FileNotFoundError):
                pass
    return out
