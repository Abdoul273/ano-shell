"""Diagnostic rapide d'Ano Shell (`ano-shell doctor`) : libs, ABI Qt6, JSON, services et Hyprland."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ano_shell.paths import app_config_dir, config_dir


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def run_doctor(quiet: bool = False) -> int:
    issues: list[str] = []
    notes: list[str] = []

    def ok(msg: str) -> None:
        if not quiet:
            print(f"  [OK]  {msg}")

    def warn(msg: str) -> None:
        notes.append(msg)
        if not quiet:
            print(f"  [!]   {msg}")

    def err(msg: str) -> None:
        issues.append(msg)
        print(f"  [ERR] {msg}")

    # 1. Quickshell + alignement Qt6
    qs_bin = shutil.which("qs") or shutil.which("quickshell")
    if not qs_bin:
        err("quickshell (qs) introuvable dans le PATH.")
    else:
        rc, out = _run(["ldd", qs_bin])
        missing = [line.strip() for line in out.splitlines() if "not found" in line]
        if missing:
            err(f"Bibliothèques manquantes pour {qs_bin} : {'; '.join(missing)}")
        else:
            ok(f"quickshell présent ({qs_bin})")

        # Comparer version Qt système vs version compilée dans quickshell
        _, qt_pkg = _run(["pacman", "-Q", "qt6-base"])
        m_sys = re.search(r"(\d+\.\d+\.\d+)", qt_pkg)
        qbin = shutil.which("quickshell") or qs_bin
        _, qstr = _run(["strings", qbin])
        m_built = re.search(r"/QtCore/(\d+\.\d+\.\d+)/QtCore/private", qstr)
        if m_sys and m_built and m_sys.group(1) != m_built.group(1):
            err(
                f"quickshell compilé contre Qt {m_built.group(1)} alors que qt6-base est en {m_sys.group(1)} "
                "— mettez à jour quickshell ou recompilez quickshell-git."
            )
        elif m_sys:
            ok(f"Alignement Qt6 OK ({m_sys.group(1)})")

    # 2. Plugins C++ AnoShell
    qml_dir = Path("/usr/lib/qt6/qml/AnoShell")
    if not qml_dir.is_dir():
        warn("Plugins C++ /usr/lib/qt6/qml/AnoShell non encore installés (lancez `makepkg -si` ou cmake --install).")
    else:
        so_files = sorted(qml_dir.rglob("*.so"))
        broken = []
        for so in so_files:
            _, out = _run(["ldd", str(so)])
            for line in out.splitlines():
                if "not found" in line:
                    broken.append(f"{so.name}: {line.strip()}")
        if broken:
            err("Bibliothèques manquantes dans les plugins AnoShell : " + " ; ".join(broken))
        else:
            ok(f"{len(so_files)} plugins C++ AnoShell vérifiés (0 lib manquante)")

    # 3. Fichiers JSON utilisateur
    if app_config_dir.is_dir():
        for jf in sorted(app_config_dir.glob("*.json")):
            try:
                json.loads(jf.read_text(encoding="utf-8"))
                ok(f"JSON valide : {jf.name}")
            except (OSError, json.JSONDecodeError) as exc:
                err(f"JSON invalide dans {jf} : {exc}")

    # 4. Configuration QML présente
    qs_conf_user = config_dir / "quickshell/ano-shell/shell.qml"
    qs_conf_sys = Path("/etc/xdg/quickshell/ano-shell/shell.qml")
    if qs_conf_user.is_file() or qs_conf_sys.is_file():
        ok(f"Shell QML trouvé ({qs_conf_user if qs_conf_user.is_file() else qs_conf_sys})")
    else:
        warn("Aucun shell.qml installé dans ~/.config/quickshell/ano-shell ou /etc/xdg/quickshell/ano-shell.")

    # 5. Dépendances runtime essentielles
    for tool in ("Hyprland", "kitty", "grim", "slurp", "wl-copy", "wpctl", "nmcli", "jq", "wtype"):
        if not shutil.which(tool):
            warn(f"Outil runtime absent du PATH : {tool}")

    # 6. Erreurs Hyprland (si session active)
    if shutil.which("hyprctl"):
        rc, out = _run(["hyprctl", "configerrors"])
        if rc == 0 and out.strip():
            warn(f"Hyprland signale des erreurs de config : {out.splitlines()[0]}")
        elif rc == 0:
            ok("Hyprland : 0 erreur de configuration")

    if not quiet:
        print()
        if issues:
            print(f"Résultat : {len(issues)} problème(s) bloquant(s) détecté(s).")
        else:
            print(f"Résultat : Ano Shell est sain ({len(notes)} avertissement(s)).")

    return 1 if issues else 0
