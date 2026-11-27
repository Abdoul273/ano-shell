"""Diagnostic rapide d'Ano Shell (`ano-shell doctor`) : libs, ABI Qt6, JSON, services et Hyprland."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ano_shell.i18n import tr
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

    # 1. Quickshell + Qt6 alignment
    qs_bin = shutil.which("qs") or shutil.which("quickshell")
    if not qs_bin:
        err(tr("quickshell (qs) introuvable dans le PATH.", "quickshell (qs) not found in PATH."))
    else:
        rc, out = _run(["ldd", qs_bin])
        missing = [line.strip() for line in out.splitlines() if "not found" in line]
        if missing:
            err(
                tr(
                    f"Bibliothèques manquantes pour {qs_bin} : {'; '.join(missing)}",
                    f"Missing shared libraries for {qs_bin}: {'; '.join(missing)}",
                )
            )
        else:
            ok(tr(f"quickshell présent ({qs_bin})", f"quickshell found ({qs_bin})"))

        _, qt_pkg = _run(["pacman", "-Q", "qt6-base"])
        m_sys = re.search(r"(\d+\.\d+\.\d+)", qt_pkg)
        qbin = shutil.which("quickshell") or qs_bin
        _, qstr = _run(["strings", qbin])
        m_built = re.search(r"/QtCore/(\d+\.\d+\.\d+)/QtCore/private", qstr)
        if m_sys and m_built and m_sys.group(1) != m_built.group(1):
            err(
                tr(
                    f"quickshell compilé contre Qt {m_built.group(1)} alors que qt6-base est en {m_sys.group(1)} "
                    "— mettez à jour quickshell ou recompilez quickshell-git.",
                    f"quickshell built against Qt {m_built.group(1)} while qt6-base is {m_sys.group(1)} "
                    "— update quickshell or rebuild quickshell-git.",
                )
            )
        elif m_sys:
            ok(tr(f"Alignement Qt6 OK ({m_sys.group(1)})", f"Qt6 ABI alignment OK ({m_sys.group(1)})"))

    # 2. Native C++ plugins AnoShell
    qml_dir = Path("/usr/lib/qt6/qml/AnoShell")
    required_modules = (
        "qmldir",
        "Blobs/qmldir",
        "Components/qmldir",
        "Config/qmldir",
        "Images/qmldir",
        "Internal/qmldir",
        "Models/qmldir",
        "Services/qmldir",
        "Shapes/qmldir",
    )
    if not qml_dir.is_dir():
        warn(
            tr(
                "Plugins C++ /usr/lib/qt6/qml/AnoShell non encore installés (lancez `makepkg -si` ou cmake --install).",
                "C++ plugins /usr/lib/qt6/qml/AnoShell not installed yet (run `makepkg -si` or cmake --install).",
            )
        )
    else:
        missing_mods = [m for m in required_modules if not (qml_dir / m).is_file()]
        if missing_mods:
            err(
                tr(
                    "Modules QML AnoShell manquants : " + ", ".join(missing_mods) + " (relancez `./install --rebuild`).",
                    "Missing AnoShell QML modules: " + ", ".join(missing_mods) + " (run `./install --rebuild`).",
                )
            )
        so_files = sorted(qml_dir.rglob("*.so"))
        broken = []
        for so in so_files:
            _, out = _run(["ldd", str(so)])
            for line in out.splitlines():
                if "not found" in line:
                    broken.append(f"{so.name}: {line.strip()}")
        if broken:
            err(
                tr(
                    "Bibliothèques manquantes dans les plugins AnoShell : " + " ; ".join(broken),
                    "Missing libraries in AnoShell plugins: " + "; ".join(broken),
                )
            )
        elif not missing_mods:
            ok(
                tr(
                    f"{len(so_files)} plugins C++ AnoShell vérifiés (0 lib manquante, Shapes OK)",
                    f"{len(so_files)} AnoShell C++ plugins verified (0 missing libs, Shapes OK)",
                )
            )

    # 3. User JSON configs
    if app_config_dir.is_dir():
        for jf in sorted(app_config_dir.glob("*.json")):
            try:
                json.loads(jf.read_text(encoding="utf-8"))
                ok(tr(f"JSON valide : {jf.name}", f"Valid JSON: {jf.name}"))
            except (OSError, json.JSONDecodeError) as exc:
                err(tr(f"JSON invalide dans {jf} : {exc}", f"Invalid JSON in {jf}: {exc}"))

    # 4. QML shell config
    qs_conf_user = config_dir / "quickshell/ano-shell/shell.qml"
    qs_conf_sys = Path("/etc/xdg/quickshell/ano-shell/shell.qml")
    if qs_conf_user.is_file() or qs_conf_sys.is_file():
        found = qs_conf_user if qs_conf_user.is_file() else qs_conf_sys
        ok(tr(f"Shell QML trouvé ({found})", f"QML shell found ({found})"))
    else:
        warn(
            tr(
                "Aucun shell.qml installé dans ~/.config/quickshell/ano-shell ou /etc/xdg/quickshell/ano-shell (lancez `ano-shell setup`).",
                "No shell.qml found in ~/.config/quickshell/ano-shell or /etc/xdg/quickshell/ano-shell (run `ano-shell setup`).",
            )
        )

    # 5. Core runtime dependencies
    for tool in ("Hyprland", "kitty", "grim", "slurp", "wl-copy", "wpctl", "nmcli", "jq", "wtype"):
        if not shutil.which(tool):
            warn(tr(f"Outil runtime absent du PATH : {tool}", f"Runtime tool missing from PATH: {tool}"))

    # 6. Hyprland config errors (if active session)
    if shutil.which("hyprctl"):
        rc, out = _run(["hyprctl", "configerrors"])
        if rc == 0 and out.strip():
            warn(
                tr(
                    f"Hyprland signale des erreurs de config : {out.splitlines()[0]}",
                    f"Hyprland reported config errors: {out.splitlines()[0]}",
                )
            )
        elif rc == 0:
            ok(tr("Hyprland : 0 erreur de configuration", "Hyprland: 0 config errors"))

    if not quiet:
        print()
        if issues:
            print(
                tr(
                    f"Résultat : {len(issues)} problème(s) bloquant(s) détecté(s).",
                    f"Result: {len(issues)} blocking issue(s) detected.",
                )
            )
        else:
            print(
                tr(
                    f"Résultat : Ano Shell est sain ({len(notes)} avertissement(s)).",
                    f"Result: Ano Shell is healthy ({len(notes)} warning(s)).",
                )
            )

    return 1 if issues else 0
