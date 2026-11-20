"""Tests automatisés pour Ano Shell (CLI, thèmes GTK CSS, absence de fuite Caelestia/libcava, i18n)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli"))

from ano_shell.glass import detect_hardware_profile
from ano_shell.main import build_parser
from ano_shell.scheme import SCHEME_VARIANTS, get_scheme_names
from ano_shell.theme import (
    gen_conf,
    gen_lua,
    glass_strength,
    render_glass_css,
)


def test_no_caelestia_plugin_or_libcava_dependency():
    """Aucun import Caelestia/M3Shapes ni référence libcava/aubio dans plugin/, cli/ ou packaging/."""
    plugin_cmake = (ROOT / "plugin/CMakeLists.txt").read_text(encoding="utf-8")
    services_cmake = (ROOT / "plugin/src/AnoShell/Services/CMakeLists.txt").read_text(encoding="utf-8")
    pkgbuild = (ROOT / "packaging/aur/PKGBUILD").read_text(encoding="utf-8")

    deps_match = re.search(r"depends=\((.*?)\)", pkgbuild, flags=re.DOTALL)
    assert deps_match is not None
    deps_block = deps_match.group(1)

    for forbidden in ("libcava", "PkgConfig::Cava", "PkgConfig::Aubio", "caelestia-shell", "caelestia-cli"):
        assert forbidden not in plugin_cmake, f"{forbidden} trouvé dans plugin/CMakeLists.txt"
        assert forbidden not in services_cmake, f"{forbidden} trouvé dans Services/CMakeLists.txt"
        assert forbidden not in deps_block, f"{forbidden} trouvé dans PKGBUILD depends"

    for qml in (ROOT / "shell").rglob("*.qml"):
        text = qml.read_text(encoding="utf-8")
        assert "import Caelestia" not in text, f"import Caelestia restant dans {qml}"
        assert "import M3Shapes" not in text, f"import M3Shapes restant dans {qml}"
        assert "qs -c caelestia" not in text, f"qs -c caelestia restant dans {qml}"


def test_no_60fps_idle_colon_animation():
    """Le séparateur ':' de l'île au repos ne doit pas animer à 60 FPS en continu."""
    island = (ROOT / "shell/modules/island/Island.qml").read_text(encoding="utf-8")
    assert 'running: root.mode === "idle" && !root.hidden' not in island
    assert "id: battProc" not in island
    assert "id: camProc" not in island
    assert "service: SystemWatch" in island


def test_content_window_mask_not_live():
    """windowMaskTex doit être en live: false (événementiel Hyprland) pour éviter 15 % CPU au repos."""
    cw = (ROOT / "shell/modules/drawers/ContentWindow.qml").read_text(encoding="utf-8")
    m = re.search(r"id:\s*windowMaskTex[\s\S]{0,400}", cw)
    assert m is not None
    assert "live: false" in m.group(0)


def test_cli_parser_subcommands():
    parser = build_parser()
    for argv in (
        ["shell", "-d"],
        ["wallpaper", "-f", "/tmp/a.png"],
        ["scheme", "list", "-n"],
        ["screenshot"],
        ["record", "-p"],
        ["glass", "--hardware"],
        ["theme", "--gtk-only", "--no-reload"],
        ["doctor", "-q"],
        ["migrate", "--dry-run"],
    ):
        args = parser.parse_args(argv)
        assert args.command == argv[0]


def test_hardware_profile_structure():
    hw = detect_hardware_profile()
    assert hw["profile"] in ("igpu-eco", "high")
    assert hw["recommended"]["shell"] in ("ios", "classic", "off")
    assert hw["recommended"]["gtk"] in ("nautilus", "complet", "off")


def test_schemes_and_generators():
    names = get_scheme_names()
    assert "dynamic" in names
    assert "catppuccin" in names
    assert "tonalspot" in SCHEME_VARIANTS

    sample = {"primary": "89b4fa", "surface": "1e1e2e", "onSurface": "cdd6f4"}
    assert "$primary = 89b4fa" in gen_conf(sample)
    assert 'primary = "89b4fa"' in gen_lua(sample)


def test_glass_css_templates_valid():
    """Les modèles CSS Liquid Glass (nautilus, complet, portal) se rendent sans jeton non résolu."""
    gtk_glass = ROOT / "cli/ano_shell/data/gtk-glass"
    colours = {
        "window_bg_color": (18, 20, 26),
        "popover_bg_color": (24, 27, 34),
        "view_bg_color": (15, 17, 22),
    }
    assert 0.0 < glass_strength(0.5, 0.5) < 1.0

    for css_file in sorted(gtk_glass.glob("*.css")):
        body = re.sub(r"\A\s*/\*.*?\*/\n?", "", css_file.read_text(encoding="utf-8"), count=1, flags=re.DOTALL)
        rendered = render_glass_css(body, colours, 0.62)
        assert "{{" not in rendered, f"Jeton non résolu dans {css_file.name}"
        assert "rgba(" in rendered


def test_gtk_css_parses_with_gtk_if_available():
    """Valide le rendu CSS avec Gtk.CssProvider sans ouvrir de fenêtre si PyGObject/GTK est installé."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
    except (ImportError, ValueError):
        return

    gtk_glass = ROOT / "cli/ano_shell/data/gtk-glass"
    colours = {
        "window_bg_color": (18, 20, 26),
        "popover_bg_color": (24, 27, 34),
        "view_bg_color": (15, 17, 22),
    }
    for name in ("nautilus-gtk4.css", "complet-gtk4.css"):
        rendered = render_glass_css((gtk_glass / name).read_text(encoding="utf-8"), colours, 0.6)
        errors: list[str] = []
        provider = Gtk.CssProvider()
        provider.connect("parsing-error", lambda _p, _sec, err, errs=errors: errs.append(err.message))
        provider.load_from_string(rendered)
        assert not errors, f"Erreurs CSS GTK4 dans {name}: {errors}"
