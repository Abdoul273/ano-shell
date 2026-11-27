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


def test_bare_arch_bundle_complete_and_clean():
    """Vérifie la présence d'onde-cli, fastfetch, fish, starship, kitty, bootstrap.sh et 0 chemin personnel."""
    required = [
        ROOT / "bootstrap.sh",
        ROOT / "extras/onde-cli/onde-cli",
        ROOT / "extras/onde-cli/onde/cli.py",
        ROOT / "config/fastfetch/config.jsonc",
        ROOT / "config/fastfetch/logo.png",
        ROOT / "config/fish/config.fish",
        ROOT / "config/starship/starship.toml",
        ROOT / "config/kitty/kitty.conf",
        ROOT / "config/kitty/liquid-glass.conf",
        ROOT / "config/kitty/tab_bar.py",
        ROOT / "config/hypr/standalone/hyprland.conf",
        ROOT / "config/sddm/install-login-screen",
    ]
    for path in required:
        assert path.is_file(), f"Fichier attendu absent : {path}"

    for cfg in (
        ROOT / "bootstrap.sh",
        ROOT / "install",
        ROOT / "config/fastfetch/config.jsonc",
        ROOT / "config/fish/config.fish",
        ROOT / "config/kitty/kitty.conf",
        ROOT / "config/hypr/shell.conf",
        ROOT / "config/hypr/standalone/hyprland.conf",
    ):
        assert "/home/anonymous" not in cfg.read_text(encoding="utf-8"), f"Chemin personnel dans {cfg}"


def test_standalone_arch_and_conf_hyprland_ready():
    """Vérifie emojis.txt embarqué, compatibilité Hyprland .conf (sans Lua requis) et installateur complet."""
    emojis = ROOT / "cli/ano_shell/data/emojis.txt"
    assert emojis.is_file() and emojis.stat().st_size > 1000

    assert (ROOT / "packaging/aur/.SRCINFO").is_file()

    assert "ano-shell/wallpaper" in (ROOT / "bin/ano-animwall").read_text(encoding="utf-8")
    assert "ano-shell/caffeine.json" in (ROOT / "shell/services/IdleInhibitor.qml").read_text(encoding="utf-8")
    assert "ano-shell:refreshDevices" in (ROOT / "shell/services/Hypr.qml").read_text(encoding="utf-8")
    assert "hyprctl dispatch exit" in (ROOT / "bin/ano-logout").read_text(encoding="utf-8")
    assert '"keyword", "monitor"' in (ROOT / "bin/ano-display-pro").read_text(encoding="utf-8")
    assert "keyword decoration:blur:passes" in (ROOT / "shell/services/BatteryInfo.qml").read_text(encoding="utf-8")
    assert "keyword decoration:screen_shader" in (ROOT / "shell/services/NightLight.qml").read_text(encoding="utf-8")
    assert '["hyprctl", "dispatch", "global", name]' in (ROOT / "bin/ano-spotlight").read_text(encoding="utf-8")

    paroles = (ROOT / "extras/onde-cli/onde/paroles.py").read_text(encoding="utf-8")
    assert "except ImportError:" in paroles and "webrtcvad = None" in paroles

    install_sh = (ROOT / "install").read_text(encoding="utf-8")
    for pkg in ("python-gobject", "gtk4", "jq", "psmisc", "libxml2", "wtype", "ydotool", "sound-theme-freedesktop", "hyprsunset"):
        assert pkg in install_sh, f"Paquet manquant dans install : {pkg}"
    assert "s|@HOME@|$HOME|g" in install_sh


def test_no_qml_singleton_shadowing_on_instantiation():
    """Aucun composant QML instancié sans préfixe ne doit entrer en collision avec un Singleton qs.* importé (Qt 6.12+)."""
    shell_root = ROOT / "shell"
    mod_singletons: dict[str, set[str]] = {}
    for qml in shell_root.rglob("*.qml"):
        head = qml.read_text(encoding="utf-8")[:500]
        if "pragma Singleton" in head:
            rel_dir = qml.parent.relative_to(shell_root)
            mod = "qs" if str(rel_dir) == "." else "qs." + ".".join(rel_dir.parts)
            mod_singletons.setdefault(mod, set()).add(qml.stem)

    collisions: list[str] = []
    for qml in sorted(shell_root.rglob("*.qml")):
        txt = re.sub(r"//.*", "", qml.read_text(encoding="utf-8"))
        imported_singletons: set[str] = set()
        for m in re.finditer(r"^import\s+(qs(?:\.[A-Za-z0-9_]+)*)(?:\s+as\s+([A-Za-z0-9_]+))?", txt, re.MULTILINE):
            mod, alias = m.group(1), m.group(2)
            if not alias:
                imported_singletons |= mod_singletons.get(mod, set())
        inline_comps = set(re.findall(r"\bcomponent\s+([A-Z][A-Za-z0-9_]*)\s*:", txt))
        for inst in set(re.findall(r"(?<![.\w])([A-Z][A-Za-z0-9_]*)\s*\{", txt)) - inline_comps:
            if inst in imported_singletons:
                collisions.append(f"{qml.relative_to(shell_root)} instancie `{inst} {{}}` alors que `{inst}` est un Singleton importé")

    assert not collisions, "\n".join(collisions)


def test_custom_shortcut_registers_primary_and_legacy_appids():
    """CustomShortcut doit enregistrer ano-shell:* et l'alias caelestia:* (compatibilité HyprLua)."""
    cs = (ROOT / "shell/components/misc/CustomShortcut.qml").read_text(encoding="utf-8")
    assert 'appid: "ano-shell"' in cs
    assert 'appid: "caelestia"' in cs
    shortcuts = (ROOT / "shell/modules/Shortcuts.qml").read_text(encoding="utf-8")
    for name in ("launcher", "spotlight", "dashboard", "controlCenter", "nexus", "session"):
        assert f'name: "{name}"' in shortcuts, f"Raccourci {name} manquant dans Shortcuts.qml"


