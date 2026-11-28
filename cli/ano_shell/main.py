"""Point d'entrée principal de la CLI `ano-shell` (bilingue FR/EN)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ano_shell import __version__
from ano_shell.doctor import run_doctor
from ano_shell.glass import detect_hardware_profile, set_glass
from ano_shell.i18n import (
    VALID_LANGS,
    get_lang,
    get_lang_mode,
    get_system_lang,
    set_lang,
    tr,
)
from ano_shell.migrate import run_migrate
from ano_shell.paths import HOME, pictures_dir
from ano_shell.record import run_record
from ano_shell.scheme import (
    SCHEME_VARIANTS,
    get_scheme,
    get_scheme_flavours,
    get_scheme_modes,
    get_scheme_names,
    list_all_schemes,
)
from ano_shell.screenshot import run_screenshot
from ano_shell.shell import run_shell
from ano_shell.theme import apply_colours, apply_glass_gtk_qt
from ano_shell.wallpaper import (
    get_colours_for_wall,
    get_wallpaper,
    set_random,
    set_wallpaper,
)


def _find_installer() -> Path | None:
    candidates = [
        Path("/usr/share/ano-shell/install"),
        Path(__file__).resolve().parents[2] / "install",
        HOME / ".local/src/ano-shell/install",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def run_setup(extra_args: list[str]) -> int:
    installer = _find_installer()
    if installer is None:
        print(
            tr(
                "Script d'installation introuvable (/usr/share/ano-shell/install).",
                "Installer script not found (/usr/share/ano-shell/install).",
            ),
            file=sys.stderr,
        )
        return 1
    return subprocess.run(["bash", str(installer), *extra_args], check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ano-shell",
        description=tr(
            "Ano Shell — Shell Wayland/Hyprland Liquid Glass autonome",
            "Ano Shell — Standalone Liquid Glass desktop shell for Wayland/Hyprland",
        ),
    )
    p.add_argument("-v", "--version", action="version", version=f"ano-shell {__version__}")
    sub = p.add_subparsers(dest="command")

    # setup (post-install AUR ou déploiement des configs utilisateur)
    sp_setup = sub.add_parser(
        "setup",
        help=tr(
            "Déployer les configs utilisateur (Hyprland, Kitty, Fastfetch, Nautilus, GTK, SDDM, langue)",
            "Deploy user configs (Hyprland, Kitty, Fastfetch, Nautilus, GTK, SDDM, language)",
        ),
    )
    sp_setup.add_argument("--lang", choices=list(VALID_LANGS), help=tr("Langue (auto, en, fr)", "Language (auto, en, fr)"))
    sp_setup.add_argument("--profile", choices=["ultra", "eco", "auto"], help=tr("Profil Liquid Glass", "Liquid Glass profile"))
    sp_setup.add_argument("--yes", "-y", action="store_true", help=tr("Mode non interactif", "Non-interactive mode"))
    sp_setup.add_argument("--full", action="store_true", help=tr("Installer aussi les paquets système/AUR", "Also install system/AUR packages"))
    sp_setup.add_argument("--standalone-hypr", action="store_true", help=tr("Installer la config Hyprland complète", "Install standalone Hyprland config"))
    sp_setup.add_argument("--with-plymouth", action="store_true", help=tr("Installer Plymouth Liquid Glass", "Install Liquid Glass Plymouth splash"))
    sp_setup.add_argument("--migrate-caelestia", action="store_true", help=tr("Migrer depuis Caelestia", "Migrate from Caelestia"))
    sp_setup.add_argument("--no-deps", action="store_true", help=tr("Ne pas installer les dépendances", "Skip package installation"))
    sp_setup.add_argument("--no-build", action="store_true", help=tr("Ne pas recompiler les plugins C++", "Skip C++ plugin build"))
    sp_setup.add_argument("--rebuild", action="store_true", help=tr("Forcer la recompilation C++", "Force C++ rebuild"))
    sp_setup.add_argument("--dry-run", action="store_true", help=tr("Simuler sans modifier le disque", "Simulate without modifying disk"))

    # lang
    sp_lang = sub.add_parser(
        "lang",
        help=tr("Afficher ou changer la langue (auto, en, fr)", "Show or switch interface language (auto, en, fr)"),
    )
    sp_lang.add_argument("value", nargs="?", choices=list(VALID_LANGS), help="auto | en | fr")

    # shell
    sp_shell = sub.add_parser(
        "shell",
        help=tr("Lancer, arrêter ou piloter Ano Shell (IPC Quickshell)", "Start, stop or control Ano Shell (Quickshell IPC)"),
    )
    sp_shell.add_argument("-d", "--daemon", action="store_true", help=tr("Lancer en arrière-plan", "Run in background"))
    sp_shell.add_argument(
        "-k",
        "--kill",
        action="store_true",
        help=tr("Arrêter le shell (bloqué si écran verrouillé)", "Stop the shell (blocked while screen is locked)"),
    )
    sp_shell.add_argument(
        "-r",
        "--restart",
        action="store_true",
        help=tr("Redémarrer proprement le shell (bloqué si écran verrouillé)", "Cleanly restart the shell (blocked while screen is locked)"),
    )
    sp_shell.add_argument("--force", action="store_true", help=tr("Forcer l'arrêt même verrouillé", "Force stop even when locked"))
    sp_shell.add_argument("-s", "--show", action="store_true", help=tr("Afficher les cibles IPC", "Show IPC targets"))
    sp_shell.add_argument("-l", "--log", action="store_true", help=tr("Afficher les logs du shell", "Show shell logs"))
    sp_shell.add_argument("--log-rules", default=None, help=tr("Règles de filtrage Qt", "Qt logging rules"))
    sp_shell.add_argument("message", nargs="*", help=tr("Commande IPC : <cible> <fonction> [args...]", "IPC command: <target> <fn> [args...]"))

    # wallpaper
    sp_wall = sub.add_parser(
        "wallpaper",
        help=tr("Définir le fond d'écran et générer la palette dynamique", "Set wallpaper and generate dynamic colour palette"),
    )
    sp_wall.add_argument("-f", "--file", help=tr("Chemin vers l'image", "Path to image"))
    sp_wall.add_argument(
        "-r",
        "--random",
        nargs="?",
        const=str(pictures_dir / "Wallpapers"),
        help=tr("Dossier aléatoire", "Random folder"),
    )
    sp_wall.add_argument("-p", "--print", help=tr("Afficher les couleurs Material You JSON d'une image", "Print Material You JSON colours for an image"))
    sp_wall.add_argument("-N", "--no-smart", action="store_true", help=tr("Ne pas choisir auto clair/sombre et variante", "Disable automatic light/dark & variant detection"))
    sp_wall.add_argument("--no-filter", action="store_true", help=tr("Ne pas filtrer par résolution", "Do not filter by resolution"))
    sp_wall.add_argument("-t", "--threshold", type=float, default=0.8, help=tr("Seuil de taille minimale", "Minimum size threshold"))

    # scheme
    sp_sch = sub.add_parser("scheme", help=tr("Gérer le thème de couleurs", "Manage colour schemes"))
    sch_sub = sp_sch.add_subparsers(dest="scheme_cmd")
    sp_set = sch_sub.add_parser("set", help=tr("Définir le schéma", "Set colour scheme"))
    sp_set.add_argument("-n", "--name", help=tr("Nom du schéma", "Scheme name"))
    sp_set.add_argument("-f", "--flavour", help=tr("Variante/saveur", "Flavour"))
    sp_set.add_argument("-m", "--mode", choices=["dark", "light"], help=tr("Mode clair/sombre", "Light or dark mode"))
    sp_set.add_argument("-v", "--variant", choices=SCHEME_VARIANTS, help=tr("Variante Material You", "Material You variant"))
    sp_set.add_argument("-r", "--random", action="store_true", help=tr("Schéma aléatoire", "Random scheme"))
    sp_set.add_argument("--notify", action="store_true", help=tr("Notifier en cas d'erreur", "Notify on error"))

    sp_get = sch_sub.add_parser("get", help=tr("Lire le schéma courant", "Show current scheme"))
    sp_get.add_argument("-n", "--name", action="store_true")
    sp_get.add_argument("-f", "--flavour", action="store_true")
    sp_get.add_argument("-m", "--mode", action="store_true")
    sp_get.add_argument("-v", "--variant", action="store_true")

    sp_list = sch_sub.add_parser("list", help=tr("Lister les schémas disponibles", "List available schemes"))
    sp_list.add_argument("-n", "--names", action="store_true")
    sp_list.add_argument("-f", "--flavours", action="store_true")
    sp_list.add_argument("-m", "--modes", action="store_true")
    sp_list.add_argument("-v", "--variants", action="store_true")

    # screenshot
    sp_shot = sub.add_parser("screenshot", help=tr("Capture d'écran plein écran ou par zone", "Take a fullscreen or region screenshot"))
    sp_shot.add_argument("-r", "--region", nargs="?", const="slurp", help=tr("Zone (slurp ou géométrie)", "Region (slurp or geometry)"))
    sp_shot.add_argument("-f", "--freeze", action="store_true", help=tr("Figer l'écran pendant la sélection", "Freeze screen while selecting"))

    # record
    sp_rec = sub.add_parser("record", help=tr("Enregistrer l'écran (gpu-screen-recorder)", "Record screen (gpu-screen-recorder)"))
    sp_rec.add_argument("-r", "--region", nargs="?", const="slurp", help=tr("Zone (slurp ou géométrie)", "Region (slurp or geometry)"))
    sp_rec.add_argument("-s", "--sound", action="store_true", help=tr("Capturer le son système", "Capture system audio"))
    sp_rec.add_argument("-p", "--pause", action="store_true", help=tr("Mettre en pause / reprendre", "Pause / resume"))
    sp_rec.add_argument("-c", "--clipboard", action="store_true", help=tr("Copier le chemin de la vidéo", "Copy video path to clipboard"))

    # glass
    sp_glass = sub.add_parser("glass", help=tr("Configurer le rendu Liquid Glass (shell, GTK, Qt/Darkly)", "Configure Liquid Glass rendering (shell, GTK, Qt/Darkly)"))
    sp_glass.add_argument("--shell", dest="shell_mode", choices=["ios", "classic", "off"])
    sp_glass.add_argument("--gtk", dest="gtk_mode", choices=["nautilus", "complet", "off"])
    sp_glass.add_argument("--density", type=float, help=tr("Densité du verre (0.0 à 1.0)", "Glass density (0.0 to 1.0)"))
    sp_glass.add_argument(
        "--performance",
        "--profile",
        dest="performance",
        choices=["ultra", "eco", "auto"],
        help=tr("Profil de performance (ultra, eco, auto)", "Performance profile (ultra, eco, auto)"),
    )
    sp_glass.add_argument("--auto", action="store_true", help=tr("Appliquer le profil optimal pour ce matériel", "Apply optimal profile for this hardware"))
    sp_glass.add_argument("--hardware", action="store_true", help=tr("Afficher la détection GPU/batterie en JSON", "Print GPU/battery hardware detection as JSON"))

    # theme
    sp_theme = sub.add_parser("theme", help=tr("Régénérer les thèmes GTK, Qt/Darkly, Hyprland et outils", "Regenerate GTK, Qt/Darkly, Hyprland and tool themes"))
    sp_theme.add_argument("--gtk-only", action="store_true", help=tr("Régénérer uniquement le verre GTK/Qt", "Regenerate GTK/Qt glass only"))
    sp_theme.add_argument("--no-reload", action="store_true", help=tr("Ne pas recharger dconf/portail", "Skip dconf/portal reload"))

    # doctor
    sp_doc = sub.add_parser("doctor", help=tr("Vérifier l'état des libs, Qt6, configs JSON et Hyprland", "Check libraries, Qt6 ABI, JSON configs and Hyprland"))
    sp_doc.add_argument("-q", "--quiet", action="store_true", help=tr("Afficher uniquement les erreurs", "Show errors only"))

    # migrate
    sp_mig = sub.add_parser("migrate", help=tr("Importer les réglages existants depuis ~/.config/caelestia", "Import existing settings from ~/.config/caelestia"))
    sp_mig.add_argument("--force", action="store_true", help=tr("Écraser les fichiers déjà présents", "Overwrite existing files"))
    sp_mig.add_argument("--dry-run", action="store_true", help=tr("Simuler sans écrire", "Simulate without writing"))

    return p


def _handle_scheme(args: argparse.Namespace) -> int:
    cmd = args.scheme_cmd
    if cmd == "set":
        scheme = get_scheme()
        if args.notify:
            scheme.notify = True
        if args.random:
            scheme.set_random()
            apply_colours(scheme.colours, scheme.mode)
        elif args.name or args.flavour or args.mode or args.variant:
            if args.name:
                scheme.name = args.name
            if args.flavour:
                scheme.flavour = args.flavour
            if args.mode:
                scheme.mode = args.mode
            if args.variant:
                scheme.variant = args.variant
            apply_colours(scheme.colours, scheme.mode)
        else:
            print(
                tr(
                    "Précisez --name, --flavour, --mode, --variant ou --random.",
                    "Specify --name, --flavour, --mode, --variant or --random.",
                ),
                file=sys.stderr,
            )
            return 1
        return 0

    if cmd == "get":
        scheme = get_scheme()
        if args.name or args.flavour or args.mode or args.variant:
            if args.name:
                print(scheme.name)
            if args.flavour:
                print(scheme.flavour)
            if args.mode:
                print(scheme.mode)
            if args.variant:
                print(scheme.variant)
        else:
            print(scheme)
        return 0

    if cmd == "list":
        flags = [args.names, args.flavours, args.modes, args.variants]
        if any(flags):
            multi = sum(bool(x) for x in flags) > 1
            if args.names:
                print(("Names: " + " ".join(get_scheme_names())) if multi else "\n".join(get_scheme_names()))
            if args.flavours:
                print(("Flavours: " + " ".join(get_scheme_flavours())) if multi else "\n".join(get_scheme_flavours()))
            if args.modes:
                print(("Modes: " + " ".join(get_scheme_modes())) if multi else "\n".join(get_scheme_modes()))
            if args.variants:
                print(("Variants: " + " ".join(SCHEME_VARIANTS)) if multi else "\n".join(SCHEME_VARIANTS))
        else:
            print(json.dumps(list_all_schemes()))
        return 0

    print(tr("Sous-commande scheme attendue : set | get | list", "Expected scheme subcommand: set | get | list"), file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "setup":
        extra: list[str] = []
        if args.lang:
            extra.extend(["--lang", args.lang])
        if args.profile:
            extra.extend(["--profile", args.profile])
        for flag, attr in (
            ("--yes", "yes"),
            ("--full", "full"),
            ("--standalone-hypr", "standalone_hypr"),
            ("--with-plymouth", "with_plymouth"),
            ("--migrate-caelestia", "migrate_caelestia"),
            ("--no-deps", "no_deps"),
            ("--no-build", "no_build"),
            ("--rebuild", "rebuild"),
            ("--dry-run", "dry_run"),
        ):
            if getattr(args, attr, False):
                extra.append(flag)
        return run_setup(extra)
    if args.command == "lang":
        if args.value:
            val = set_lang(args.value)
            print(
                tr(
                    f"Langue enregistrée : {val} (active : {get_lang()})",
                    f"Language saved: {val} (active: {get_lang()})",
                )
            )
        else:
            print(
                tr(
                    f"Langue : {get_lang_mode()} (active : {get_lang()}, système : {get_system_lang()})",
                    f"Language: {get_lang_mode()} (active: {get_lang()}, system: {get_system_lang()})",
                )
            )
        return 0
    if args.command == "shell":
        return run_shell(args)
    if args.command == "wallpaper":
        if args.print:
            print(json.dumps(get_colours_for_wall(args.print, args.no_smart)))
        elif args.file:
            set_wallpaper(args.file, args.no_smart)
        elif args.random:
            set_random(args.random, threshold=args.threshold, no_filter=args.no_filter, no_smart=args.no_smart)
        else:
            print(get_wallpaper() or tr("Aucun fond d'écran défini", "No wallpaper set"))
        return 0
    if args.command == "scheme":
        return _handle_scheme(args)
    if args.command == "screenshot":
        return run_screenshot(args)
    if args.command == "record":
        return run_record(args)
    if args.command == "glass":
        if args.hardware:
            print(json.dumps(detect_hardware_profile(), indent=2, ensure_ascii=False))
            return 0
        conf = set_glass(args.shell_mode, args.gtk_mode, args.density, performance=args.performance, auto=args.auto)
        pct = round(float(conf.get("density", 0.5)) * 100)
        print(
            tr(
                f"Liquid Glass : shell={conf.get('shell')}, gtk={conf.get('gtk')}, intensité={pct} %, profil={conf.get('performance', 'auto')}",
                f"Liquid Glass: shell={conf.get('shell')}, gtk={conf.get('gtk')}, density={pct}%, profile={conf.get('performance', 'auto')}",
            )
        )
        return 0
    if args.command == "theme":
        if args.gtk_only:
            mode, dens = apply_glass_gtk_qt(reload_desktop=not args.no_reload)
            pct = round(dens * 100)
            print(tr(f"Verre GTK/Qt appliqué : {mode} ({pct} %)", f"GTK/Qt glass applied: {mode} ({pct}%)"))
        else:
            s = get_scheme()
            apply_colours(s.colours, s.mode, reload_desktop=not args.no_reload)
            print(tr(f"Thème appliqué : {s.name}/{s.flavour} ({s.mode})", f"Theme applied: {s.name}/{s.flavour} ({s.mode})"))
        return 0
    if args.command == "doctor":
        return run_doctor(quiet=args.quiet)
    if args.command == "migrate":
        return run_migrate(force=args.force, dry_run=args.dry_run)

    parser.print_help()
    return 0
