"""Point d'entrée principal de la CLI `ano-shell`."""

from __future__ import annotations

import argparse
import json
import sys

from ano_shell import __version__
from ano_shell.doctor import run_doctor
from ano_shell.glass import detect_hardware_profile, set_glass
from ano_shell.migrate import run_migrate
from ano_shell.paths import pictures_dir
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ano-shell",
        description="Ano Shell — Shell Wayland/Hyprland Liquid Glass autonome",
    )
    p.add_argument("-v", "--version", action="version", version=f"ano-shell {__version__}")
    sub = p.add_subparsers(dest="command")

    # shell
    sp_shell = sub.add_parser("shell", help="Lancer, arrêter ou piloter Ano Shell (IPC Quickshell)")
    sp_shell.add_argument("-d", "--daemon", action="store_true", help="Lancer en arrière-plan")
    sp_shell.add_argument("-k", "--kill", action="store_true", help="Arrêter le shell (bloqué si écran verrouillé)")
    sp_shell.add_argument("--force", action="store_true", help="Forcer l'arrêt même verrouillé")
    sp_shell.add_argument("-s", "--show", action="store_true", help="Afficher les cibles IPC")
    sp_shell.add_argument("-l", "--log", action="store_true", help="Afficher les logs du shell")
    sp_shell.add_argument("--log-rules", default=None, help="Règles de filtrage Qt")
    sp_shell.add_argument("message", nargs="*", help="Commande IPC : <cible> <fonction> [args...]")

    # wallpaper
    sp_wall = sub.add_parser("wallpaper", help="Définir le fond d'écran et générer la palette dynamique")
    sp_wall.add_argument("-f", "--file", help="Chemin vers l'image")
    sp_wall.add_argument("-r", "--random", nargs="?", const=str(pictures_dir / "Wallpapers"), help="Dossier aléatoire")
    sp_wall.add_argument("-p", "--print", help="Afficher les couleurs Material You JSON d'une image")
    sp_wall.add_argument("-N", "--no-smart", action="store_true", help="Ne pas choisir auto clair/sombre et variante")
    sp_wall.add_argument("--no-filter", action="store_true", help="Ne pas filtrer par résolution")
    sp_wall.add_argument("-t", "--threshold", type=float, default=0.8, help="Seuil de taille minimale")

    # scheme
    sp_sch = sub.add_parser("scheme", help="Gérer le thème de couleurs")
    sch_sub = sp_sch.add_subparsers(dest="scheme_cmd")
    sp_set = sch_sub.add_parser("set", help="Définir le schéma")
    sp_set.add_argument("-n", "--name", help="Nom du schéma")
    sp_set.add_argument("-f", "--flavour", help="Variante/saveur")
    sp_set.add_argument("-m", "--mode", choices=["dark", "light"], help="Mode clair/sombre")
    sp_set.add_argument("-v", "--variant", choices=SCHEME_VARIANTS, help="Variante Material You")
    sp_set.add_argument("-r", "--random", action="store_true", help="Schéma aléatoire")
    sp_set.add_argument("--notify", action="store_true", help="Notifier en cas d'erreur")

    sp_get = sch_sub.add_parser("get", help="Lire le schéma courant")
    sp_get.add_argument("-n", "--name", action="store_true")
    sp_get.add_argument("-f", "--flavour", action="store_true")
    sp_get.add_argument("-m", "--mode", action="store_true")
    sp_get.add_argument("-v", "--variant", action="store_true")

    sp_list = sch_sub.add_parser("list", help="Lister les schémas disponibles")
    sp_list.add_argument("-n", "--names", action="store_true")
    sp_list.add_argument("-f", "--flavours", action="store_true")
    sp_list.add_argument("-m", "--modes", action="store_true")
    sp_list.add_argument("-v", "--variants", action="store_true")

    # screenshot
    sp_shot = sub.add_parser("screenshot", help="Capture d'écran plein écran ou par zone")
    sp_shot.add_argument("-r", "--region", nargs="?", const="slurp", help="Zone (slurp ou géométrie)")
    sp_shot.add_argument("-f", "--freeze", action="store_true", help="Figer l'écran pendant la sélection")

    # record
    sp_rec = sub.add_parser("record", help="Enregistrer l'écran (gpu-screen-recorder)")
    sp_rec.add_argument("-r", "--region", nargs="?", const="slurp", help="Zone (slurp ou géométrie)")
    sp_rec.add_argument("-s", "--sound", action="store_true", help="Capturer le son système")
    sp_rec.add_argument("-p", "--pause", action="store_true", help="Mettre en pause / reprendre")
    sp_rec.add_argument("-c", "--clipboard", action="store_true", help="Copier le chemin de la vidéo")

    # glass
    sp_glass = sub.add_parser("glass", help="Configurer le rendu Liquid Glass (shell, GTK, Qt/Darkly)")
    sp_glass.add_argument("--shell", dest="shell_mode", choices=["ios", "classic", "off"])
    sp_glass.add_argument("--gtk", dest="gtk_mode", choices=["nautilus", "complet", "off"])
    sp_glass.add_argument("--density", type=float, help="Densité du verre (0.0 à 1.0)")
    sp_glass.add_argument("--auto", action="store_true", help="Appliquer le profil optimal pour ce matériel")
    sp_glass.add_argument("--hardware", action="store_true", help="Afficher la détection GPU/batterie en JSON")

    # theme
    sp_theme = sub.add_parser("theme", help="Régénérer les thèmes GTK, Qt/Darkly, Hyprland et outils")
    sp_theme.add_argument("--gtk-only", action="store_true", help="Régénérer uniquement le verre GTK/Qt")
    sp_theme.add_argument("--no-reload", action="store_true", help="Ne pas recharger dconf/portail")

    # doctor
    sp_doc = sub.add_parser("doctor", help="Vérifier l'état des libs, Qt6, configs JSON et Hyprland")
    sp_doc.add_argument("-q", "--quiet", action="store_true", help="Afficher uniquement les erreurs")

    # migrate
    sp_mig = sub.add_parser("migrate", help="Importer les réglages existants depuis ~/.config/caelestia")
    sp_mig.add_argument("--force", action="store_true", help="Écraser les fichiers déjà présents")
    sp_mig.add_argument("--dry-run", action="store_true", help="Simuler sans écrire")

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
            print("Précisez --name, --flavour, --mode, --variant ou --random.", file=sys.stderr)
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

    print("Sous-commande scheme attendue : set | get | list", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
            print(get_wallpaper() or "No wallpaper set")
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
        conf = set_glass(args.shell_mode, args.gtk_mode, args.density, auto=args.auto)
        print(
            f"Liquid Glass : shell={conf.get('shell')}, gtk={conf.get('gtk')}, "
            f"intensité={round(float(conf.get('density', 0.5)) * 100)} %"
        )
        return 0
    if args.command == "theme":
        if args.gtk_only:
            mode, dens = apply_glass_gtk_qt(reload_desktop=not args.no_reload)
            print(f"Verre GTK/Qt appliqué : {mode} ({round(dens * 100)} %)")
        else:
            s = get_scheme()
            apply_colours(s.colours, s.mode, reload_desktop=not args.no_reload)
            print(f"Thème appliqué : {s.name}/{s.flavour} ({s.mode})")
        return 0
    if args.command == "doctor":
        return run_doctor(quiet=args.quiet)
    if args.command == "migrate":
        return run_migrate(force=args.force, dry_run=args.dry_run)

    parser.print_help()
    return 0
