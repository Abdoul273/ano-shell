"""ReplayGain ou mesure EBU R128 différée, sans réencoder les fichiers."""
import math
import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path

import mutagen

from . import bibliotheque as bib

with bib._verrou:
    bib._db.execute("CREATE TABLE IF NOT EXISTS niveaux (piste_id INTEGER PRIMARY KEY, signature TEXT, gain REAL, source TEXT, erreur TEXT)")
    bib._db.commit()

_file = queue.Queue(maxsize=8)
_en_cours = set()
_verrou = threading.Lock()
_thread = None


def limiter_gain(gain, pic=None):
    if not math.isfinite(gain):
        return 0.0
    gain = max(-30, min(12, gain))
    # Sans pic connu, pas d'amplification susceptible d'écrêter le signal.
    gain = min(gain, -1 - pic) if pic is not None and math.isfinite(pic) else min(0, gain)
    return round(gain, 2)


def _nombre(v):
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    if isinstance(v, bytes):
        v = v.decode("utf-8", errors="replace")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(v))
    return float(m[0]) if m else None


def replaygain(chemin):
    f = mutagen.File(chemin)
    if not f or not f.tags:
        return None
    tags = {str(k).lower().split(":")[-1]: v for k, v in f.tags.items()}
    gain = _nombre(tags.get("replaygain_track_gain", ""))
    peak = _nombre(tags.get("replaygain_track_peak", ""))
    if gain is None:
        return None
    pic = 20 * math.log10(peak) if peak and peak > 0 else None
    return limiter_gain(gain, pic)


def analyser(chemin):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("FFmpeg est nécessaire pour mesurer les titres sans ReplayGain")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-nostats", "-threads", "1", "-filter_threads", "1", "-i", str(chemin),
           "-map", "0:a:0", "-vn", "-sn", "-dn", "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-"]
    if shutil.which("nice"):
        cmd = ["nice", "-n", "15", *cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if r.returncode:
        raise ValueError("Impossible de mesurer le niveau de ce fichier")
    mesures = re.findall(r"I:\s*([-+\d.]+)\s*LUFS", r.stderr)
    pics = re.findall(r"Peak:\s*([-+\d.]+)\s*dBFS", r.stderr)
    if not mesures or not pics:
        raise ValueError("Mesure du niveau indisponible")
    niveau, pic = float(mesures[-1]), float(pics[-1])
    return 0.0 if niveau < -60 else limiter_gain(-18 - niveau, pic)


def _signature(chemin):
    st = Path(chemin).stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def _sauver(pid, signature, gain, source, erreur=None):
    with bib._verrou:
        bib._db.execute("INSERT OR REPLACE INTO niveaux VALUES (?,?,?,?,?)", (pid, signature, gain, source, erreur))
        bib._db.commit()


def _ouvrier():
    while True:
        pid, chemin, signature = _file.get()
        try:
            gain = analyser(chemin)
            if _signature(chemin) == signature:
                _sauver(pid, signature, gain, "EBU R128")
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            _sauver(pid, signature, 0, "", str(e))
        finally:
            with _verrou:
                _en_cours.discard(pid)
            _file.task_done()


def niveau(pid):
    global _thread
    p = bib.piste(pid)
    if not p:
        raise ValueError("Titre introuvable")
    chemin = p["chemin"]
    signature = _signature(chemin)
    r = bib.requete("SELECT * FROM niveaux WHERE piste_id=? AND signature=?", (pid, signature), un=True)
    if r:
        return {"etat": "erreur" if r["erreur"] else "pret", "gain_db": r["gain"], "source": r["source"], "erreur": r["erreur"]}
    try:
        gain = replaygain(chemin)
    except (mutagen.MutagenError, OSError, ValueError):
        gain = None
    if gain is not None:
        _sauver(pid, signature, gain, "ReplayGain")
        return {"etat": "pret", "gain_db": gain, "source": "ReplayGain"}
    with _verrou:
        if pid not in _en_cours:
            try:
                _file.put_nowait((pid, chemin, signature))
            except queue.Full:
                return {"etat": "en_attente", "gain_db": 0}
            _en_cours.add(pid)
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_ouvrier, daemon=True, name="niveaux-audio")
            _thread.start()
    return {"etat": "analyse", "gain_db": 0}
