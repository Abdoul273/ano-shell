"""Chemins et réglages persistants."""
import json
import os
import subprocess
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "onde"
CONFIG = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "onde"
POCHETTES = DONNEES / "pochettes"
PAROLES = DONNEES / "paroles"
for d in (DONNEES, CONFIG, POCHETTES, PAROLES):
    d.mkdir(parents=True, exist_ok=True)
BASE = DONNEES / "onde.db"
FICHIER_REGLAGES = CONFIG / "reglages.json"


def _dossier_musique():
    try:
        r = subprocess.run(["xdg-user-dir", "MUSIC"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0 and r.stdout.strip() and r.stdout.strip() != str(Path.home()):
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return str(Path.home() / "Musique")


REGLAGES_DEFAUT = {
    "dossiers": [_dossier_musique()],
    "normalisation": True,  # ReplayGain ou niveau EBU R128 mis en cache
    "lecture_continue": True,
    "reprendre_longs": True,
    "fondu": 0,              # secondes de fondu enchaîné (0 = coupé)
    "titres_fichier": True,  # reconstruire titre/artiste depuis le nom si pas de tags
}
_verrou = threading.Lock()


def lire_reglages():
    with _verrou:
        try:
            r = json.loads(FICHIER_REGLAGES.read_text())
        except (OSError, ValueError):
            r = {}
    return {**REGLAGES_DEFAUT, **{k: v for k, v in r.items() if k in REGLAGES_DEFAUT}}


def ecrire_reglages(modifs):
    r = lire_reglages()
    for k, v in modifs.items():
        if k not in REGLAGES_DEFAUT:
            continue
        d = REGLAGES_DEFAUT[k]
        if isinstance(d, bool):
            v = bool(v)
        elif isinstance(d, int):
            try:
                v = max(0, min(12, int(v)))
            except (TypeError, ValueError):
                continue
        elif isinstance(d, list):
            v = [str(Path(x).expanduser()) for x in v if str(x).strip()]
        r[k] = v
    with _verrou:
        tmp = FICHIER_REGLAGES.with_suffix(".tmp")
        tmp.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        tmp.replace(FICHIER_REGLAGES)
    return r
