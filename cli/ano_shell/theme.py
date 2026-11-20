"""Moteur de thèmes unifié d'Ano Shell : GTK4/3, portail GTK3, Qt/Darkly, Hyprland, terminaux et outils."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from ano_shell.colour import get_dynamic_colours
from ano_shell.hypr import is_lua_config
from ano_shell.paths import (
    app_config_dir,
    app_state_dir,
    atomic_write,
    config_dir,
    data_dir,
    glass_config_path,
    gtk_glass_dir,
    load_json,
    templates_dir,
    theme_dir,
    user_templates_dir,
    write_if_changed,
)

GLASS_GTK_MODES = ("nautilus", "complet", "off")
GTK4_DIR = config_dir / "gtk-4.0"
GTK3_DIR = config_dir / "gtk-3.0"
QT_COLORS_PATH = config_dir / "qtengine/ano-shell.colors"
QT_CONFIG_PATH = config_dir / "qtengine/config.json"
DARKLYRC_PATH = config_dir / "darklyrc"
PORTAL_THEME = "AnoShell-Glass-Portal"
PORTAL_THEME_CSS = data_dir / f"themes/{PORTAL_THEME}/gtk-3.0/gtk.css"
PORTAL_DROPIN = config_dir / "systemd/user/xdg-desktop-portal-gtk.service.d/ano-shell-glass.conf"

QT_GLASS = {"Window": 0.55, "View": 0.30, "Header": 0.45, "Header][Inactive": 0.45}
GTK_VARIANTS = {
    "nautilus": {GTK4_DIR: "nautilus-gtk4.css", GTK3_DIR: None},
    "complet": {GTK4_DIR: "complet-gtk4.css", GTK3_DIR: "complet-gtk3.css"},
    "off": {GTK4_DIR: None, GTK3_DIR: None},
}


def gen_conf(colours: dict[str, str]) -> str:
    return "".join(f"${name} = {colour}\n" for name, colour in colours.items())


def gen_lua(colours: dict[str, str]) -> str:
    lines = ["return {"]
    for name, colour in colours.items():
        lines.append(f'  {name} = "{colour}",')
    lines.append("}")
    return "\n".join(lines) + "\n"


def gen_replace(colours: dict[str, str], template: Path, with_hash: bool = False) -> str:
    text = template.read_text(encoding="utf-8")
    for name, colour in colours.items():
        text = text.replace(f"{{{{ ${name} }}}}", f"#{colour}" if with_hash else colour)
    return text


def gen_replace_dynamic(colours: dict[str, str], template: Path, mode: str) -> str:
    colours_dyn = get_dynamic_colours(colours)

    def fill(match: re.Match[str]) -> str:
        parts = match.group(1).strip().split(".")
        if len(parts) != 2:
            return match.group(0)
        col, form = parts
        if col not in colours_dyn or not hasattr(colours_dyn[col], form):
            return match.group(0)
        return str(getattr(colours_dyn[col], form))

    text = template.read_text(encoding="utf-8")
    text = re.sub(r"\{\{((?:(?!\{\{|\}\}).)*)\}\}", fill, text)
    text = re.sub(r"\{\{\s*mode\s*\}\}", mode, text)
    return text


def _hex_to_ansi(c: str, *codes: int) -> str:
    return f"\x1b]{';'.join(map(str, codes))};rgb:{c[0:2]}/{c[2:4]}/{c[4:6]}\x1b\\"


def gen_sequences(colours: dict[str, str]) -> str:
    if "onSurface" not in colours or "surface" not in colours:
        return ""
    seq = (
        _hex_to_ansi(colours["onSurface"], 10)
        + _hex_to_ansi(colours["surface"], 11)
        + _hex_to_ansi(colours.get("secondary", colours["primary"]), 12)
        + _hex_to_ansi(colours.get("secondary", colours["primary"]), 17)
    )
    for i in range(16):
        key = f"term{i}"
        if key in colours:
            seq += _hex_to_ansi(colours[key], 4, i)
    for idx, role in enumerate(("primary", "secondary", "tertiary"), start=16):
        if role in colours:
            seq += _hex_to_ansi(colours[role], 4, idx)
    return seq


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255.0 for c in rgb)
    return 0.299 * r + 0.587 * g + 0.114 * b


def glass_strength(base: float, density: float) -> float:
    if density <= 0.5:
        return base * (0.35 + 1.3 * density)
    return base + (0.95 - base) * (density - 0.5) * 2.0


def render_glass_css(template: str, colours: dict[str, tuple[int, int, int]], density: float) -> str:
    window = colours.get("window_bg_color", (12, 14, 18))
    light = _luminance(window) > 0.5
    roles = {
        "bg": window,
        "pop": colours.get("popover_bg_color", window),
        "view": colours.get("view_bg_color", window),
        "shade": (255, 255, 255) if light else (0, 0, 0),
        "ink": (0, 0, 0) if light else (255, 255, 255),
    }

    def repl(match: re.Match[str]) -> str:
        role, base = match.group(1), float(match.group(2))
        if role != "ink":
            if light:
                base = min(0.95, base + 0.12)
            base = glass_strength(base, density)
            if role == "pop":
                base = max(base, 0.72)
        r, g, b = roles[role]
        return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, base)):.3f})"

    return re.sub(r"\{\{(bg|pop|view|shade|ink):([0-9.]+)\}\}", repl, template)


def read_gtk_colours() -> dict[str, tuple[int, int, int]]:
    colours: dict[str, tuple[int, int, int]] = {}
    for d in (GTK4_DIR, GTK3_DIR):
        try:
            text = (d / "gtk.css").read_text(encoding="utf-8")
        except OSError:
            continue
        for name, hexa in re.findall(r"@define-color\s+(\w+)\s+#([0-9a-fA-F]{6})\s*;", text):
            colours.setdefault(name, (int(hexa[0:2], 16), int(hexa[2:4], 16), int(hexa[4:6], 16)))
    return colours


def _qt_colour(value: str) -> tuple[int, int, int] | None:
    value = value.strip()
    if m := re.fullmatch(r"#([0-9a-fA-F]{6})", value):
        h = m.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    if m := re.fullmatch(r"(\d+),\s*(\d+),\s*(\d+)(?:,\s*\d+)?", value):
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def apply_glass_gtk_qt(
    mode: str | None = None,
    density: float | None = None,
    reload_desktop: bool = False,
) -> tuple[str, float]:
    """Génère liquid-glass.css (GTK4/3), le thème du portail GTK3, qtengine/ano-shell.colors et darklyrc."""
    conf = load_json(glass_config_path, {"gtk": "nautilus", "density": 0.5, "shell": "ios"})
    eff_mode = mode if mode in GLASS_GTK_MODES else conf.get("gtk", "nautilus")
    if eff_mode not in GLASS_GTK_MODES:
        eff_mode = "nautilus"
    try:
        eff_density = max(0.0, min(1.0, float(density if density is not None else conf.get("density", 0.5))))
    except (TypeError, ValueError):
        eff_density = 0.5

    colours = read_gtk_colours()
    changed = False

    for gtk_dir, tpl_name in GTK_VARIANTS[eff_mode].items():
        header = (
            f"/* Généré par ano-shell ({eff_mode}, intensité {round(eff_density * 100)} %) — ne pas modifier */\n"
        )
        tpl_path = gtk_glass_dir / tpl_name if tpl_name else None
        if tpl_path and tpl_path.is_file():
            body = re.sub(r"\A\s*/\*.*?\*/\n?", "", tpl_path.read_text(encoding="utf-8"), count=1, flags=re.DOTALL)
            content = header + render_glass_css(body, colours, eff_density)
        else:
            content = header
        changed |= write_if_changed(gtk_dir / "liquid-glass.css", content)

    # Portail GTK3 (Ouvrir / Enregistrer)
    light = _luminance(colours.get("window_bg_color", (12, 14, 18))) > 0.5
    base_theme = "adw-gtk3" if light else "adw-gtk3-dark"
    portal_css = (
        f"/* Généré par ano-shell ({eff_mode}) — thème du portail GTK uniquement */\n"
        f'@import url("file:///usr/share/themes/{base_theme}/gtk-3.0/gtk.css");\n'
    )
    portal_tpl = gtk_glass_dir / "portal-gtk3.css"
    if eff_mode == "complet" and portal_tpl.is_file():
        body = re.sub(r"\A\s*/\*.*?\*/\n?", "", portal_tpl.read_text(encoding="utf-8"), count=1, flags=re.DOTALL)
        portal_css += render_glass_css(body, colours, eff_density)
    portal_changed = write_if_changed(PORTAL_THEME_CSS, portal_css)

    dropin = (
        "# Ano Shell : thème verre pour les fenêtres Ouvrir / Enregistrer\n"
        f"[Service]\nEnvironment=GTK_THEME={PORTAL_THEME}\n"
    )
    if write_if_changed(PORTAL_DROPIN, dropin) and reload_desktop:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        portal_changed = True

    if portal_changed and reload_desktop:
        busy = False
        try:
            out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, check=False).stdout
            busy = any(c.get("class") == "xdg-desktop-portal-gtk" for c in json.loads(out or "[]"))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if not busy:
            subprocess.run(["systemctl", "--user", "try-restart", "xdg-desktop-portal-gtk.service"], check=False)

    # Qt / Darkly
    if QT_COLORS_PATH.is_file():
        text = QT_COLORS_PATH.read_text(encoding="utf-8")
        qt_light = False
        section = ""
        out_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("["):
                section = line[len("[Colors:") : -1] if line.startswith("[Colors:") else ""
            key, _, val = line.partition("=")
            rgb = _qt_colour(val) if key in ("BackgroundNormal", "BackgroundAlternate") else None
            if rgb and section == "Window" and key == "BackgroundNormal":
                qt_light = _luminance(rgb) > 0.5
            if rgb and section in QT_GLASS:
                if eff_mode == "complet":
                    base = QT_GLASS[section] + (0.12 if qt_light else 0.0)
                    alpha = round(255 * max(0.0, min(1.0, glass_strength(min(0.95, base), eff_density))))
                    line = f"{key}={rgb[0]},{rgb[1]},{rgb[2]},{alpha}"
                else:
                    line = f"{key}=#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            out_lines.append(line)
        write_if_changed(QT_COLORS_PATH, "\n".join(out_lines) + "\n")

    win_op = round(100 * glass_strength(QT_GLASS["Window"], eff_density)) if eff_mode == "complet" else 100
    menu_op = max(72, round(100 * glass_strength(0.86, eff_density))) if eff_mode == "complet" else 100
    darkly = (
        "# Généré par ano-shell\n"
        "[Style]\n"
        f"MenuOpacity={menu_op}\nMenuBarOpacity={win_op}\nToolBarOpacity={win_op}\nTabBarOpacity={win_op}\n"
        "TransparentDolphinView=true\n"
        f"DolphinSidebarOpacity={win_op}\nDolphinViewOpacity={win_op}\n"
    )
    write_if_changed(DARKLYRC_PATH, darkly)

    if changed and reload_desktop:
        key = "/org/gnome/desktop/interface/gtk-theme"
        try:
            cur = subprocess.run(["dconf", "read", key], capture_output=True, text=True, check=False).stdout.strip()
            cur = cur or "'adw-gtk3-dark'"
            subprocess.run(["dconf", "write", key, "'Adwaita'"], check=False)
            time.sleep(0.3)
            subprocess.run(["dconf", "write", key, cur], check=False)
        except FileNotFoundError:
            pass

    return eff_mode, eff_density


def apply_colours(colours: dict[str, str], mode: str, reload_desktop: bool = True) -> None:
    """Applique la palette active à Hyprland, GTK4/3 (+ Liquid Glass), Qt/Darkly, terminaux et outils."""
    theme_dir.mkdir(parents=True, exist_ok=True)

    # 1. Hyprland colors (natif .conf + .lua si config Lua présente)
    atomic_write(app_config_dir / "hypr/colors.conf", gen_conf(colours))
    if is_lua_config():
        atomic_write(config_dir / "hypr/scheme/current.lua", gen_lua(colours))
    else:
        atomic_write(config_dir / "hypr/scheme/current.conf", gen_conf(colours))

    # 2. GTK4 / GTK3 (notre modèle inclut nativement @import "liquid-glass.css")
    gtk_tpl = templates_dir / "gtk.css"
    if gtk_tpl.is_file():
        gtk_css = gen_replace(colours, gtk_tpl, with_hash=True)
        write_if_changed(GTK4_DIR / "gtk.css", gtk_css)
        write_if_changed(GTK3_DIR / "gtk.css", gtk_css)

    # 3. Qt / KDE (fond noir pur intégré dans qtdark.colors)
    qt_tpl = templates_dir / ("qtlight.colors" if mode == "light" else "qtdark.colors")
    if qt_tpl.is_file():
        write_if_changed(QT_COLORS_PATH, gen_replace(colours, qt_tpl, with_hash=True))

    # 4. Outils Ano Shell CSS (ano-tools.css)
    tools_tpl = templates_dir / "ano-tools.css"
    if tools_tpl.is_file():
        write_if_changed(theme_dir / "ano-tools.css", gen_replace_dynamic(colours, tools_tpl, mode))

    # 5. Templates utilisateur personnalisés (~/.config/ano-shell/templates/*)
    if user_templates_dir.is_dir():
        for tpl in user_templates_dir.iterdir():
            if tpl.is_file():
                write_if_changed(theme_dir / tpl.name, gen_replace_dynamic(colours, tpl, mode))

    # 6. Séquences ANSI terminaux
    sequences = gen_sequences(colours)
    if sequences:
        atomic_write(app_state_dir / "sequences.txt", sequences)
        if reload_desktop and Path("/dev/pts").is_dir():
            for pt in Path("/dev/pts").iterdir():
                if pt.name.isdigit():
                    try:
                        fd = os.open(str(pt), os.O_WRONLY | os.O_NONBLOCK | os.O_NOCTTY)
                        try:
                            os.write(fd, sequences.encode("ascii"))
                        finally:
                            os.close(fd)
                    except OSError:
                        pass

    # 7. Liquid Glass GTK / Portail / Darkly Qt (toujours synchronisé avec la nouvelle palette)
    apply_glass_gtk_qt(reload_desktop=reload_desktop)
