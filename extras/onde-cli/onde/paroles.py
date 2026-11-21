"""Paroles : fichier .lrc/.txt voisin, tags audio intégrés, puis LRCLIB + NetEase (mot-à-mot YRC/KRC)
et Genius en secours, avec validation stricte de durée et recalage acoustique sur la voix réelle."""
import contextlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path

import mutagen
import numpy as np
try:
    import webrtcvad
except ImportError:
    webrtcvad = None
from scipy.ndimage import maximum_filter1d
from scipy.signal import butter, sosfiltfilt

from . import VERSION, bibliotheque, config

UA = {"User-Agent": f"Onde/{VERSION} (lecteur de musique local)"}
UA_NAV = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}
LIGNE = re.compile(r"^\s*((?:\[\d{1,3}:\d{1,2}(?:[.:,]\d{1,3})?\])+)(.*)$")
STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:,](\d{1,3}))?\]")
MOT = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:,](\d{1,3}))?>")
OFFSET = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)

CREDITS = re.compile(
    r"^\s*(?:作词|作曲|编曲|制作|混音|母带|录音|和声|监制|出品|词|曲|written by|composed by|produced by|lyrics by|lyricist|mixed by|mastered by)\s*[:：]",
    re.IGNORECASE,
)
VOYELLES = re.compile(r"[aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿœ]+", re.IGNORECASE)
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
MARQUEURS_VERSION = (
    "live", "remix", "acoustic", "acoustique", "instrumental", "karaoke",
    "sped up", "slowed", "nightcore", "gospel", "cover", "freestyle",
)
MOTS_VIDES = {"and", "et", "the", "le", "la", "les", "un", "une", "de", "du", "des", "a"}
ERREURS_IO = (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError)

_HOME = Path.home()
AURA_DB = _HOME / ".local/share/com.abdoul273.aura/aura.db"
AURA_LYRICS = _HOME / ".cache/com.abdoul273.aura/lyrics"


def _lire_paroles_aura(chemin_audio, p):
    """Récupère les paroles déjà en cache dans Aura (prédécesseur d'Onde)."""
    if not AURA_DB.exists() or not AURA_LYRICS.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{AURA_DB}?mode=ro", uri=True, timeout=1)
        row = None
        chemin_str = str(chemin_audio) if chemin_audio else ""
        if chemin_str:
            row = db.execute("select id, path from tracks where path = ?", (chemin_str,)).fetchone()
        if not row and p.get("titre"):
            rows = db.execute(
                "select id, path, artist from tracks where lower(title) = lower(?)",
                (p["titre"],),
            ).fetchall()
            if p.get("artiste"):
                rows = [r for r in rows if p["artiste"].lower() in (r[2] or "").lower()] or rows
            row = rows[0][:2] if rows else None
        db.close()
    except (sqlite3.Error, OSError):
        return None
    if not row:
        return None
    track_id, path = row
    for v in ("v4", "v3", "v2"):
        f = AURA_LYRICS / f"{v}-{track_id}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text())
                if data.get("synced") and data.get("text"):
                    txt = data["text"]
                    donnees = _depuis_lrc(txt)
                    if donnees.get("synchro"):
                        res = {
                            "source": f"Aura ({data.get('source', 'cache')})",
                            **donnees,
                            "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", txt)).strip(),
                        }
                        if data.get("approximate"):
                            res["approximatif"] = True
                        return res
            except (OSError, ValueError):
                pass
    lrc = Path(path).with_suffix(".lrc")
    if lrc.exists():
        try:
            txt = lrc.read_text(errors="replace")
            donnees = _depuis_lrc(txt)
            if donnees.get("synchro"):
                return {
                    "source": "Aura (.lrc)",
                    **donnees,
                    "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", txt)).strip(),
                }
        except OSError:
            pass
    return None


def _secondes_match(s):
    frac = s.group(3) or "0"
    return int(s.group(1)) * 60 + int(s.group(2)) + int(frac) / (10 ** len(frac))


def _formater_stamp(ms):
    ms = max(0, round(ms))
    return f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}.{ms % 1000:03d}"


def yrc_vers_lrc(yrc):
    """Convertit le format mot-à-mot NetEase (yrc) en LRC enrichi <mm:ss.xxx> avec pauses internes."""
    sortie = []
    for brute in (yrc or "").splitlines():
        brute = brute.strip()
        if not brute.startswith("[") or brute.startswith('{"'):
            continue
        ferme = brute.find("]")
        if ferme < 0:
            continue
        entete = brute[1:ferme].split(",")
        if len(entete) < 2:
            continue
        try:
            debut_l, dur_l = int(entete[0].strip()), int(entete[1].strip())
        except ValueError:
            continue
        reste = brute[ferme + 1:]
        mots_l = []
        while "(" in reste:
            i = reste.find("(")
            j = reste.find(")", i)
            if j < 0:
                break
            meta = reste[i + 1:j].split(",")
            apres = reste[j + 1:]
            suiv = apres.find("(")
            mot = apres[:suiv] if suiv >= 0 else apres
            reste = apres[suiv:] if suiv >= 0 else ""
            try:
                debut_m = int(meta[0].strip())
                dur_m = int(meta[1].strip()) if len(meta) > 1 else 0
            except ValueError:
                continue
            if mot:
                mots_l.append((debut_m, max(40, dur_m), mot))
        if not mots_l:
            continue
        texte_propre = "".join(m for _, _, m in mots_l).strip()
        if not texte_propre or CREDITS.match(texte_propre):
            continue
        corps = []
        for idx, (dm, dur_m, mot) in enumerate(mots_l):
            corps.append(f"<{_formater_stamp(dm)}>{mot}")
            fin_m = dm + dur_m
            if idx + 1 < len(mots_l) and mots_l[idx + 1][0] - fin_m >= 160:
                corps.append(f"<{_formater_stamp(fin_m)}>")
        fin_ligne = (mots_l[-1][0] + mots_l[-1][1]) if mots_l[-1][1] > 40 else max(debut_l + dur_l, mots_l[-1][0] + 200)
        corps.append(f"<{_formater_stamp(fin_ligne)}>")
        sortie.append(f"[{_formater_stamp(debut_l)}]{''.join(corps)}")
    return "\n".join(sortie) if sortie else None


def klyric_vers_lrc(klyric):
    """Convertit le format karaoké NetEase (klyric) en LRC enrichi <mm:ss.xxx>."""
    sortie = []
    reg_mot = re.compile(r"<(\d+),(\d+)(?:,\d+)?>([^<]*)")
    for brute in (klyric or "").splitlines():
        brute = brute.strip()
        if not brute.startswith("["):
            continue
        ferme = brute.find("]")
        if ferme < 0:
            continue
        entete = brute[1:ferme].split(",")
        if len(entete) < 2:
            continue
        try:
            debut_l, dur_l = int(entete[0].strip()), int(entete[1].strip())
        except ValueError:
            continue
        mots_l = []
        for m in reg_mot.finditer(brute[ferme + 1:]):
            off_m, dur_m, mot = int(m.group(1)), int(m.group(2)), m.group(3)
            if mot:
                mots_l.append((debut_l + off_m, max(40, dur_m), mot))
        if not mots_l:
            continue
        corps = []
        for idx, (dm, dur_m, mot) in enumerate(mots_l):
            corps.append(f"<{_formater_stamp(dm)}>{mot}")
            fin_m = dm + dur_m
            if idx + 1 < len(mots_l) and mots_l[idx + 1][0] - fin_m >= 160:
                corps.append(f"<{_formater_stamp(fin_m)}>")
        fin_ligne = (mots_l[-1][0] + mots_l[-1][1]) if mots_l[-1][1] > 40 else max(debut_l + dur_l, mots_l[-1][0] + 200)
        corps.append(f"<{_formater_stamp(fin_ligne)}>")
        sortie.append(f"[{_formater_stamp(debut_l)}]{''.join(corps)}")
    return "\n".join(sortie) if sortie else None


def analyser_lrc(texte, avec_mots=False):
    """LRC → [[secondes, ligne], …] trié, ou [] si non synchronisé."""
    lignes = []
    offsets = OFFSET.findall(texte or "")
    # LRC : un offset positif avance les paroles (millisecondes).
    offset = int(offsets[-1]) / 1000 if offsets else 0

    for brut in (texte or "").splitlines():
        m = LIGNE.match(brut)
        if not m:
            continue
        brut_mots = m.group(2)
        contenu = MOT.sub("", brut_mots).strip()
        if contenu.startswith('{"') or CREDITS.match(contenu):
            continue
        reperes = list(MOT.finditer(brut_mots))
        mots = []
        # Un préfixe sans repère ou des temps décroissants : rester à la ligne.
        if reperes and not brut_mots[:reperes[0].start()].strip():
            for i, repere in enumerate(reperes):
                fin = reperes[i + 1].start() if i + 1 < len(reperes) else len(brut_mots)
                mot = brut_mots[repere.end():fin]
                mots.append([_secondes_match(repere), mot])
            if any(b[0] < a[0] for a, b in pairwise(mots)):
                mots = []
        debut = _secondes_match(STAMP.search(m.group(1)))
        for s in STAMP.finditer(m.group(1)):
            t = _secondes_match(s)
            mots_decales = [[round(a + t - debut - offset, 3), mot]
                            for a, mot in mots]
            lignes.append((round(t - offset, 3), contenu, mots_decales))
    lignes.sort(key=lambda ligne: ligne[0])
    synchro = [[t, ligne] for t, ligne, _ in lignes]
    return (synchro, [m for _, _, m in lignes]) if avec_mots else synchro


def _depuis_lrc(texte):
    synchro, mots = analyser_lrc(texte, avec_mots=True)
    return {"synchro": synchro, "mots": mots, "version_synchro": 2}


# ── analyse acoustique de la voix et alignement syllabique ───────────
_cache_profils = OrderedDict()
_verrou_profils = threading.Lock()


def _poids_phonetique(mot):
    """Poids temporel relatif d'un mot selon ses syllabes prononcées et sa ponctuation."""
    net = mot.strip()
    if not net:
        return 0.0
    cjk = len(CJK.findall(net))
    sans_cjk = CJK.sub("", net)
    groupes = VOYELLES.findall(sans_cjk)
    n = cjk + len(groupes)
    propre = sans_cjk.strip(".,!?;:\"'()[]{}-–—…")
    if len(groupes) > 1 and re.search(r"[^aeiouyàáâäèéêëìíîïòóôöùúûü]es?$", propre, re.IGNORECASE):
        n = max(1.0, n - 0.6)
    poids = max(0.75, float(n)) + min(len(propre), 12) * 0.055
    if re.search(r"[,;:—–…]$", net):
        poids += 0.42
    elif re.search(r"[.!?]$", net):
        poids += 0.62
    return poids


def _syllabes_ligne(texte):
    mots = re.findall(r"\S+", texte or "")
    return sum(max(1, len(VOYELLES.findall(m)) + len(CJK.findall(m))) for m in mots)


def _debit_syllabique(synchro):
    """Débit chanté du morceau (syllabes / seconde) sur les phrases enchaînées."""
    debits = []
    for (t1, l1), (t2, _) in pairwise(synchro):
        if not (l1 or "").strip():
            continue
        ecart = t2 - t1
        if 0.7 <= ecart <= 9.5:
            syl = _syllabes_ligne(l1)
            if syl >= 2:
                debits.append(syl / ecart)
    if len(debits) < 3:
        return 4.3
    debits.sort()
    return float(np.clip(debits[int(len(debits) * 0.72)], 2.7, 8.8))


_SOS_VOCAL = butter(4, [260, 3600], btype="bandpass", fs=8000, output="sos").astype(np.float32)
_NICE = shutil.which("nice")


def _profil_vocal(chemin):
    """Extrait à 100 Hz (pas de 10 ms) l'enveloppe vocale centrale et les attaques de voix."""
    chemin = str(chemin)
    try:
        st = Path(chemin).stat()
    except OSError:
        return None
    cle = (chemin, st.st_mtime, st.st_size)
    with _verrou_profils:
        if cle in _cache_profils:
            _cache_profils.move_to_end(cle)
            return _cache_profils[cle]

    sr = 8000
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-filter_threads", "1", "-i", chemin,
           "-vn", "-ac", "2", "-ar", str(sr), "-f", "s16le", "-"]
    if _NICE:
        cmd = [_NICE, "-n", "15", *cmd]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or len(r.stdout) < sr * 4:
        return None

    raw = np.frombuffer(r.stdout, dtype=np.int16)
    n_pairs = len(raw) // 2
    stereo = raw[:n_pairs * 2].reshape(-1, 2).astype(np.float32) / np.float32(32768.0)
    mid = (stereo[:, 0] + stereo[:, 1]) * np.float32(0.5)
    side = (stereo[:, 0] - stereo[:, 1]) * np.float32(0.5)

    vm = sosfiltfilt(_SOS_VOCAL, mid)
    vs = sosfiltfilt(_SOS_VOCAL, side)

    hop = sr // 100  # 10 ms (100 Hz)
    n = len(vm) // hop
    if n < 50:
        return None
    em = np.sqrt(np.mean(vm[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    es = np.sqrt(np.mean(vs[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    voix = np.maximum(0.0, em - 0.48 * es)
    p95 = float(np.percentile(voix, 95)) or 1e-6
    env = np.clip(voix / p95, 0.0, 1.5).astype(np.float32)

    # Détection d'activité vocale WebRTC par trames de 20 ms (uniquement hors silence)
    if webrtcvad is not None:
        vad = webrtcvad.Vad(2)
        pcm16 = np.clip(vm[:n * hop] * 32767.0, -32768, 32767).astype(np.int16)
        vad_flags = np.zeros(n, dtype=np.float32)
        hop20 = hop * 2
        for i in range(0, n - 1, 2):
            if env[i] <= 0.04 and env[i + 1] <= 0.04:
                continue
            trame = pcm16[i * hop:i * hop + hop20].tobytes()
            try:
                if vad.is_speech(trame, sr):
                    vad_flags[i] = vad_flags[i + 1] = 1.0
            except ValueError:
                pass
    else:
        vad_flags = (env > 0.08).astype(np.float32)

    presence = (env * (0.4 + 0.6 * vad_flags)).astype(np.float32)

    # Courbe d'attaque vocale vectorisée (comparaison fenêtre [-220ms..-20ms] vs [0..+150ms])
    cs = np.concatenate(([0.0], np.cumsum(presence, dtype=np.float64)))
    idx = np.arange(n)
    i_av0 = np.maximum(0, idx - 22)
    i_av1 = np.maximum(1, idx - 2)
    i_ap1 = np.minimum(n, idx + 15)
    avant = (cs[i_av1] - cs[i_av0]) / np.maximum(1, i_av1 - i_av0)
    apres = (cs[i_ap1] - cs[idx]) / np.maximum(1, i_ap1 - idx)
    montee = np.maximum(0.0, apres - avant)
    facteur_silence = np.where(avant < 0.20, 1.65, np.where(avant < 0.35, 1.1, 0.65))
    onset = (montee * facteur_silence).astype(np.float32)

    profil = {"env": env, "presence": presence, "onset": onset, "duree": n / 100.0}
    with _verrou_profils:
        _cache_profils[cle] = profil
        while len(_cache_profils) > 4:
            _cache_profils.popitem(last=False)
    return profil


def _mesurer_decalage(synchro, profil, cherche_large=False):
    """Compare toutes les phrases : corriger seulement si une majorité concorde.

    L'énergie d'un mix ne permet pas de reconnaître les mots. Un pic isolé ou
    plusieurs refrains également plausibles ne justifient donc pas un recalage.
    Les fenêtres sont pré-calculées pour éviter des millions de moyennes Python.
    """
    env, onset = profil["presence"], profil["onset"]
    n = len(env)
    ancres = np.array([round(t * 100) for t, l in synchro
                       if (l or "").strip() and not re.match(r"^[♪♫·.\s]+$", l)], dtype=int)
    if len(ancres) < 3 or n < 40:
        return 0.0, 0.0
    idx = np.arange(n)
    cum = np.concatenate(([0.0], np.cumsum(env, dtype=np.float64)))
    fin = np.minimum(n, idx + 18)
    apres = (cum[fin] - cum[idx]) / np.maximum(1, fin - idx)
    deb, fin = np.maximum(0, idx - 16), np.maximum(0, idx - 2)
    avant = (cum[fin] - cum[deb]) / np.maximum(1, fin - deb)
    evidence = maximum_filter1d(onset, size=5) * 1.35 + apres * .45 - avant * .22
    lags = np.arange(-1800, 3501, 2) if cherche_large else np.arange(-160, 161)
    positions = ancres[None, :] + lags[:, None]
    valides = (positions >= 8) & (positions < n - 20)
    valeurs = evidence[np.clip(positions, 0, n - 1)]
    comptes = valides.sum(axis=1)
    scores = (valeurs * valides).sum(axis=1) / np.maximum(1, comptes)
    scores -= (.008 if cherche_large else .04) * np.abs(lags) / 100
    # Ne pas favoriser une fin de fichier qui ne conserve qu'une poignée de phrases.
    scores[comptes < max(3, int(np.ceil(len(ancres) * .8)))] = -np.inf
    meilleur = int(np.argmax(scores))
    if not np.isfinite(scores[meilleur]):
        return 0.0, 0.0
    zero = int(np.flatnonzero(lags == 0)[0])
    lag = int(lags[meilleur])
    communs = valides[meilleur] & valides[zero]
    gains = valeurs[meilleur, communs] - valeurs[zero, communs]
    accord = float(np.mean(gains > .025)) if len(gains) else 0.0
    # Une autre solution éloignée presque aussi bonne signale une ambiguïté musicale.
    autres = scores[np.abs(lags - lag) > 35]
    ambigu = len(autres) and scores[meilleur] - float(np.max(autres)) < .025
    gain_min = .08 if cherche_large else .045
    if abs(lag) < 4 or scores[meilleur] < scores[zero] + gain_min or accord < .6 or ambigu:
        return 0.0, 0.0
    return round(lag / 100, 3), round(accord, 3)


def _estimer_decalage_global(synchro, profil, cherche_large=False):
    return _mesurer_decalage(synchro, profil, cherche_large)[0]


def _signature_audio(chemin):
    stat = Path(chemin).stat()
    return [stat.st_size, stat.st_mtime_ns]


VERSION_ALIGNEMENT = 3


def _alignement_a_refaire(donnees, chemin):
    return (donnees.get("version_alignement") != VERSION_ALIGNEMENT
            or donnees.get("signature_audio") != _signature_audio(chemin))


def _decouper_mots_ligne(txt, t_debut, t_suiv, env, debit):
    """Calcule les repères mot-à-mot [t, mot] + [fin_chant, ''] guidés par l'énergie vocale réelle."""
    morceaux = re.findall(r"\S+\s*", txt)
    if not morceaux:
        return []
    n_env = len(env)
    poids = [_poids_phonetique(m) for m in morceaux]
    total_poids = sum(poids) or 1.0
    syl = _syllabes_ligne(txt)
    dur_estimee = max(0.45, syl / debit)
    dispo = max(0.25, t_suiv - t_debut - 0.06)
    dur_max = min(dispo, max(dur_estimee * 1.45, dur_estimee + 0.9))

    i0 = max(0, min(n_env - 1, round(t_debut * 100)))
    i_max = max(i0 + 1, min(n_env, round((t_debut + dur_max) * 100)))
    i_min_fin = max(i0 + 1, min(i_max, round((t_debut + min(dispo, dur_estimee * 0.62)) * 100)))

    # La première respiration n'est pas la fin de phrase : rechercher la dernière
    # zone d'activité durable pour conserver les mots chantés après une pause interne.
    tranche_fin = env[i0:i_max]
    if len(tranche_fin) < 4 or float(np.max(tranche_fin)) < .18:
        return []
    actives = np.convolve((tranche_fin >= .18).astype(float), np.ones(6), mode="same") >= 4
    indices = np.flatnonzero(actives)
    i_fin = min(i_max, i0 + int(indices[-1]) + 4) if len(indices) else i_max
    i_fin = max(min(i_min_fin, i_max), i_fin)
    fin_chant = round(min(t_suiv, t_debut + dur_max, i_fin / 100.0), 3)
    if fin_chant <= t_debut:
        return []

    if len(morceaux) == 1:
        return [[round(t_debut, 3), morceaux[0]], [fin_chant, ""]]

    i_fin_idx = max(i0 + 2, min(n_env, round(fin_chant * 100)))
    tranche = env[i0:i_fin_idx]
    if len(tranche) < 4:
        acc = 0.0
        out = []
        for m, p in zip(morceaux, poids):
            out.append([round(t_debut + (acc / total_poids) * (fin_chant - t_debut), 3), m])
            acc += p
        out.append([fin_chant, ""])
        return out

    # Répartition hybride : 55 % énergie vocale active + 45 % cadence syllabique régulière,
    # avec accrochage des frontières de mots sur les creux d'articulation (consonnes / respirations).
    densite = np.where(tranche < .13, 0.0, 0.45 + 0.55 * np.clip(tranche, 0.05, 1.2))
    cum = np.concatenate(([0.0], np.cumsum(densite)))
    total_cum = float(cum[-1]) or 1.0

    reperes = [[round(t_debut, 3), morceaux[0]]]
    acc = poids[0]
    idx_prec = 0
    for k in range(1, len(morceaux)):
        cible = (acc / total_poids) * total_cum
        idx_brut = int(np.searchsorted(cum, cible))
        idx_brut = max(idx_prec + 1, min(len(tranche) - 1, idx_brut))
        # Chercher un creux d'énergie vocale autour de la frontière théorique
        rayon = max(6, min(22, len(tranche) // (len(morceaux) * 2)))
        r_deb = max(idx_prec + 3, idx_brut - rayon)
        r_fin = min(len(tranche) - 2, idx_brut + rayon + 1)
        if r_fin > r_deb:
            local = tranche[r_deb:r_fin]
            idx_creux = r_deb + int(np.argmin(local))
            # Une pause chantée existe même sans virgule dans les paroles.
            if float(tranche[idx_creux]) < 0.13:
                fin_mot_prec = round(t_debut + idx_creux / 100.0, 3)
                idx_reprise = idx_creux
                while idx_reprise < min(len(tranche) - 1, idx_creux + 60) and tranche[idx_reprise] < 0.18:
                    idx_reprise += 1
                if idx_reprise - idx_creux >= 8:
                    reperes.append([fin_mot_prec, ""])
                    idx_brut = idx_reprise
                else:
                    idx_brut = idx_creux
            else:
                idx_brut = idx_creux
        t_mot = round(t_debut + idx_brut / 100.0, 3)
        if t_mot <= reperes[-1][0]:
            t_mot = round(reperes[-1][0] + 0.04, 3)
        reperes.append([t_mot, morceaux[k]])
        idx_prec = idx_brut
        acc += poids[k]

    # Réserver de la place aux mots restants, même pour un passage de rap très dense.
    # Aucun repère estimé ne peut dépasser la fin de phrase ou la ligne suivante.
    pas = min(.02, (fin_chant - t_debut) / (len(reperes) + 1))
    precedent = t_debut - pas
    for i, repere in enumerate(reperes):
        plafond = fin_chant - (len(reperes) - i) * pas
        repere[0] = round(max(precedent + pas, min(plafond, repere[0])), 3)
        precedent = repere[0]
    reperes.append([fin_chant, ""])
    return reperes


def aligner_sur_audio(chemin, donnees, duree=None, forcer_recalage=False):
    """Recalage prudent et reproductible, toujours depuis les repères de la source."""
    if not chemin or not Path(chemin).is_file():
        return donnees
    # Ne jamais réutiliser les mots estimés ni cumuler un ancien décalage.
    origine = donnees.get("reperes_source")
    if origine is None:
        origine = {"synchro": donnees.get("synchro") or [],
                   "mots": donnees.get("mots") or []}
        if donnees.get("aligne_audio"):
            origine = {"synchro": [[round(t - donnees.get("decalage_audio", 0), 3), l]
                                   for t, l in origine["synchro"]], "mots": []}
    synchro = origine["synchro"]
    if not synchro:
        return donnees
    mots_orig = origine.get("mots") or []
    lignes_riches = [bool(m) for m in mots_orig]
    est_local_manuel = donnees.get("source") in ("fichier .lrc", "tag audio") and not donnees.get("auto_lrc")
    # Les repères mot-à-mot éditoriaux et les LRC personnels sont prioritaires.
    proteger = est_local_manuel or any(lignes_riches)
    toutes_riches = proteger and not forcer_recalage and all(
        bool(mots_orig[i] if i < len(mots_orig) else None)
        for i, (_, l) in enumerate(synchro)
        if (l or "").strip() and not re.match(r"^[♪♫·.\s]+$", l)
    )
    if toutes_riches:
        origines = ["source" if (i < len(mots_orig) and mots_orig[i]) else "ligne" for i in range(len(synchro))]
        return {
            **donnees, "synchro": [[round(t, 3), l] for t, l in synchro],
            "mots": [[[round(a, 3), m] for a, m in (mots_orig[i] if i < len(mots_orig) else [])] for i in range(len(synchro))],
            "reperes_source": origine, "origine_mots": origines,
            "aligne_audio": True, "analyse_audio": "disponible",
            "version_alignement": VERSION_ALIGNEMENT, "signature_audio": _signature_audio(chemin),
            "decalage_audio": 0.0, "confiance_recalage": 0.0,
            "precision": "mot-a-mot" if "source" in origines else "ligne",
        }
    profil = _profil_vocal(chemin)
    if not profil:
        return {**donnees, "analyse_audio": "indisponible",
                "version_alignement": VERSION_ALIGNEMENT, "signature_audio": _signature_audio(chemin)}

    env = profil["presence"]
    duree_audio = min(duree or profil["duree"], profil["duree"])
    delta, confiance = (0.0, 0.0) if proteger and not forcer_recalage else _mesurer_decalage(
        synchro, profil, cherche_large=bool(donnees.get("approximatif") or forcer_recalage))

    debit = _debit_syllabique(synchro)
    nouv_synchro = [[round(t + delta, 3), l] for t, l in synchro]
    nouv_mots, origines = [], []
    for i, (t_debut, ligne) in enumerate(nouv_synchro):
        txt = (ligne or "").strip()
        # Chercher le prochain instant distinct : traductions/duos au même instant.
        t_suiv = next((t for t, _ in nouv_synchro[i + 1:] if t > t_debut), duree_audio)
        t_suiv = min(t_suiv, duree_audio)
        rep_orig = mots_orig[i] if i < len(mots_orig) else []
        if rep_orig:
            # Aucun écrasement des fins de mots, pauses, chevauchements ou préfixes.
            nouv_mots.append([[round(a + delta, 3), m] for a, m in rep_orig])
            origines.append("source")
        elif not txt or re.match(r"^[♪♫·.\s]+$", txt) or t_suiv - max(0, t_debut) < .12:
            nouv_mots.append([])
            origines.append("ligne")
        else:
            reperes = _decouper_mots_ligne(txt, max(0, t_debut), t_suiv, env, debit)
            nouv_mots.append(reperes)
            origines.append("estimation" if reperes else "ligne")

    precision = "mixte" if "source" in origines and "estimation" in origines else (
        "mot-a-mot" if "source" in origines else "estimee" if "estimation" in origines else "ligne")
    return {
        **donnees, "synchro": nouv_synchro, "mots": nouv_mots,
        "reperes_source": origine, "origine_mots": origines,
        "aligne_audio": True, "analyse_audio": "disponible",
        "version_alignement": VERSION_ALIGNEMENT, "signature_audio": _signature_audio(chemin),
        "decalage_audio": delta, "confiance_recalage": confiance,
        "precision": precision,
    }


# ── requêtes HTTP et sources en ligne (LRCLIB, NetEase, Genius) ─────
def _get(url, essais=2, headers=None, timeout=7):
    hdrs = headers or UA
    for i in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and i < essais - 1:
                time.sleep(0.5 * (i + 1))
                continue
            raise


def _lrclib(p):
    """Compatibilité directe : interroge LRCLIB pour un dictionnaire piste `p`."""
    q = {"track_name": p["titre"], "artist_name": p["artiste"]}
    if p.get("album"):
        q["album_name"] = p["album"]
    if p.get("duree"):
        q["duration"] = round(p["duree"])
    direct = None
    with contextlib.suppress(*ERREURS_IO):
        direct = _get("https://lrclib.net/api/get?" + urllib.parse.urlencode(q))
        if (
            direct
            and (direct.get("syncedLyrics") or direct.get("instrumental"))
            and (not p.get("duree") or _etendue_compatible(direct.get("syncedLyrics"), p["duree"]))
        ):
            return direct
    termes = f"{p['artiste']} {p['titre']}" if p["artiste"] != "Artiste inconnu" else p["titre"]
    try:
        res = _get("https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": termes}))
    except ERREURS_IO:
        return direct
    res = [r for r in res if r.get("syncedLyrics") or r.get("plainLyrics")]
    if not res:
        return direct
    duree = p.get("duree")
    if duree:
        res.sort(key=lambda r: (
            not r.get("syncedLyrics"),
            not _etendue_compatible(r.get("syncedLyrics"), duree),
            abs((r.get("duration") or 0) - duree),
        ))
        if abs((res[0].get("duration") or 0) - duree) > 15 and not _etendue_compatible(res[0].get("syncedLyrics"), duree):
            return direct if direct and direct.get("plainLyrics") else None
    return res[0]


def _etendue_lrc(texte_lrc):
    """(nb_lignes_chantees, dernier_temps_chante, a_des_mots) pour vérifier la cohérence d'un LRC."""
    if not texte_lrc:
        return 0, 0.0, False
    synchro, mots = analyser_lrc(texte_lrc, avec_mots=True)
    chantees = [t for t, l in synchro if (l or "").strip()]
    if len(set(chantees)) < 2:
        return 0, 0.0, False
    a_mots = sum(1 for m in mots if len(m) >= 2) >= max(2, len(chantees) // 3)
    return len(chantees), max(chantees), a_mots


def _etendue_compatible(texte_lrc, duree):
    if not texte_lrc or not duree or duree <= 0:
        return True
    nb, dernier_t, _ = _etendue_lrc(texte_lrc)
    return nb >= 3 and dernier_t <= duree + 4.5


# ── normalisation et variantes artiste / titre ──────────────────────
FEAT = re.compile(r"\s*[\(\[]?\s*\b(?:feat|ft|featuring)\b\.?\s.*$", re.IGNORECASE)
CHAINE = re.compile(r"(?:\s*-\s*topic|vevo|\s*officiel(?:le)?|\s*official|\s*music|\s*tv)+$", re.IGNORECASE)


def _propre(t):
    t = bibliotheque.PARASITES.sub(" ", t or "")
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t)
    t = re.sub(r"\b(?:19|20)\d{2}\b|\b\d{2,3}[kp]\b", " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", FEAT.sub("", t)).strip(" .-–—|")


def _artiste_propre(a):
    a = CHAINE.sub("", (a or "").strip()).strip()
    return re.sub(r"(?<=[a-zà-ÿ])(?=[A-Z])", " ", a) if " " not in a else a


def _tokens(s):
    s = (s or "").lower().replace("$", "s")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"['’.]+", "", s)
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in MOTS_VIDES]


def _marqueurs_version(*textes):
    joint = " ".join(t or "" for t in textes).lower()
    joint = "".join(c for c in unicodedata.normalize("NFKD", joint) if not unicodedata.combining(c))
    trouves = set()
    for m in MARQUEURS_VERSION:
        if re.search(rf"\b{re.escape(m)}\b", joint):
            trouves.add("acoustic" if m == "acoustique" else m)
    return trouves


def _meme_mot(a, b):
    if a == b:
        return True
    la, lb = len(a), len(b)
    if la >= 3 and lb >= 3 and (a in b or b in a) and abs(la - lb) <= 2:
        return True
    if la >= 5 and lb >= 5 and abs(la - lb) <= 1:
        diffs = sum(1 for x, y in zip(a, b) if x != y) + abs(la - lb)
        if diffs <= 1:
            return True
    return False


def _couverture(aiguille, botte):
    ta = _tokens(aiguille)
    if not ta:
        return 0.0
    tb = _tokens(botte)
    if not tb:
        return 0.0
    return sum(1 for w in ta if any(_meme_mot(w, x) for x in tb)) / len(ta)


def _similarite_artiste(attendus, candidat):
    cand_compact = "".join(_tokens(candidat))
    if not cand_compact:
        return 0.0
    meilleur = 0.0
    for a in attendus:
        if not a:
            continue
        ac = "".join(_tokens(a))
        if len(ac) >= 3 and (ac in cand_compact or (cand_compact in ac and len(cand_compact) >= 3)):
            return 1.0
        meilleur = max(meilleur, _couverture(a, candidat), _couverture(candidat, a))
    return meilleur


def variantes(p):
    """(artiste, titre) à essayer, du plus précis au plus large."""
    artiste = "" if p.get("artiste") == "Artiste inconnu" else (p.get("artiste") or "")
    vus, res = set(), []

    def ajouter(a, t):
        a, t = (a or "").strip(), (t or "").strip()
        if t and (a.lower(), t.lower()) not in vus:
            vus.add((a.lower(), t.lower()))
            res.append((a, t))

    ajouter(artiste, p["titre"])
    a_nom, t_nom = bibliotheque.nettoyer_nom(p["titre"])
    if a_nom:
        ajouter(_artiste_propre(a_nom), _propre(t_nom))
    if p.get("chemin"):
        a_fic, t_fic = bibliotheque.nettoyer_nom(Path(p["chemin"]).stem)
        if a_fic:
            ajouter(_artiste_propre(a_fic), _propre(t_fic))
        elif t_fic:
            ajouter(_artiste_propre(artiste), _propre(t_fic))
    ajouter(_artiste_propre(artiste), _propre(p["titre"]))
    principal = re.split(r"\s+(?:x|&|feat\.?|ft\.?|avec)\s+|,", _artiste_propre(artiste), maxsplit=1, flags=re.IGNORECASE)[0]
    ajouter(principal, _propre(t_nom if a_nom else p["titre"]))
    ajouter("", _propre(t_nom if a_nom else p["titre"]))
    return res


def _noter_candidat(p, vars_p, cand):
    """Note la pertinence d'un candidat (titre, artiste, marqueurs de version, durée et étendue LRC)."""
    ver_piste = _marqueurs_version(p.get("titre"), Path(p["chemin"]).stem if p.get("chemin") else "")
    ver_cand = _marqueurs_version(cand.get("titre"), cand.get("album"))
    if ver_piste != ver_cand:
        return None

    titre_cand = cand.get("titre") or ""
    art_cand = cand.get("artiste") or ""
    if " - " in titre_cand:
        g, d = titre_cand.split(" - ", 1)
        if _similarite_artiste([g], art_cand) >= 0.9:
            titre_cand = d
    ct = _propre(titre_cand) or titre_cand.strip()
    if not ct:
        return None

    artistes_piste = [a for a, _ in vars_p if a]
    titres_piste = list(dict.fromkeys(t for _, t in vars_p if t))
    duree_piste = float(p.get("duree") or 0.0)
    duree_cand = float(cand.get("duree") or 0.0)

    syn_texte = cand.get("syncedLyrics")
    nb_lignes, dernier_t, a_mots = _etendue_lrc(syn_texte) if syn_texte else (0, 0.0, False)
    deborde = bool(duree_piste > 0 and dernier_t > duree_piste + 4.5)
    if deborde:
        duree_cand = max(duree_cand, dernier_t + 3.0)

    ecart = abs(duree_cand - duree_piste) if (duree_piste > 0 and duree_cand > 0) else None
    exact = bool(ecart is not None and ecart <= max(3.2, duree_piste * 0.02) and not deborde)

    meilleur_base = None
    for idx_t, t_cherche in enumerate(titres_piste):
        cov_t = _couverture(t_cherche, ct)
        cov_ret = _couverture(ct, t_cherche)
        sim_a = _similarite_artiste(artistes_piste, art_cand) if artistes_piste else 0.0
        nb_mots_t = len(_tokens(ct))

        base = None
        if artistes_piste:
            if cov_t >= 0.84 and cov_ret >= 0.72 and sim_a >= 0.65:
                base = cov_t * 42.0 + cov_ret * 20.0 + sim_a * 32.0 - idx_t * 1.5
            elif cov_t >= 0.99 and cov_ret >= 0.99 and ecart is not None and ecart <= 2.2 and nb_mots_t >= 2:
                base = 62.0 - idx_t * 1.5
        else:
            tout = _couverture(t_cherche, f"{art_cand} {ct}")
            art_dans_q = _couverture(art_cand, t_cherche) >= 0.95
            if tout >= 0.98 and cov_ret >= 0.95:
                if art_dans_q and (ecart is None or ecart <= 20.0):
                    base = 82.0
                elif ecart is not None and ecart <= 3.0 and (nb_mots_t >= 2 or ecart <= 1.5):
                    base = 58.0
        if base is not None and (meilleur_base is None or base > meilleur_base):
            meilleur_base = base

    if meilleur_base is None:
        return None

    penalite_ecart = min(ecart if ecart is not None else 25.0, 120.0) * 0.35
    if deborde:
        penalite_ecart += 35.0
    bonus_exact = 18.0 if exact else 0.0
    bonus_mots = 14.0 if (a_mots and not deborde) else 0.0
    return {
        "score": meilleur_base + bonus_exact + bonus_mots - penalite_ecart,
        "exact": exact,
        "ecart": ecart,
        "deborde": deborde,
        "nb_lignes": nb_lignes,
        "a_mots": a_mots,
    }


def _netease_rechercher(termes, limite=8):
    url = "https://music.163.com/api/cloudsearch/pc?" + urllib.parse.urlencode(
        {"s": termes, "type": "1", "limit": str(limite)}
    )
    d = _get(url, essais=1, headers=UA_NAV, timeout=5)
    chansons = (d or {}).get("result", {}).get("songs") or []
    res = []
    for s in chansons:
        sid = s.get("id")
        nom = (s.get("name") or "").strip()
        if not sid or not nom:
            continue
        artistes = ", ".join(a.get("name", "").strip() for a in (s.get("ar") or []) if a.get("name"))
        album = (s.get("al") or {}).get("name") or ""
        duree = (s.get("dt") or 0) / 1000.0
        res.append({
            "id": f"netease:{sid}",
            "netease_id": sid,
            "titre": nom,
            "artiste": artistes,
            "album": album,
            "duree": duree,
            "source": "NetEase",
        })
    return res


def _netease_paroles(sid):
    url = (
        f"https://music.163.com/api/song/lyric/v1?id={int(sid)}"
        "&cp=false&lv=1&kv=1&tv=1&rv=1&yv=1&ytv=1&yrv=1"
    )
    d = _get(url, essais=1, headers=UA_NAV, timeout=5)
    if not d:
        return None
    if d.get("nolyric") or d.get("pureMusic"):
        return {"instrumental": True, "syncedLyrics": None, "plainLyrics": None, "source": "NetEase"}
    yrc = (d.get("yrc") or {}).get("lyric")
    krc = (d.get("klyric") or {}).get("lyric")
    lrc = ((d.get("lrc") or {}).get("lyric") or "").strip()
    enrichi = (yrc_vers_lrc(yrc) if yrc else None) or (klyric_vers_lrc(krc) if krc else None)
    texte_synchro = enrichi or (lrc if _etendue_lrc(lrc)[0] >= 3 else None)
    if lrc and "纯音乐，请欣赏" in lrc:
        return {"instrumental": True, "syncedLyrics": None, "plainLyrics": None, "source": "NetEase"}
    texte_brut = MOT.sub("", re.sub(r"\[[^\]]*\]", "", texte_synchro or lrc)).strip()
    return {
        "instrumental": False,
        "syncedLyrics": texte_synchro,
        "plainLyrics": texte_brut or None,
        "source": "NetEase",
        "mot_a_mot": bool(enrichi),
    }


def _extraire_genius_html(page_html):
    blocs = []
    pos = 0
    marqueur = 'data-lyrics-container="true"'
    while True:
        i = page_html.find(marqueur, pos)
        if i < 0:
            break
        deb = page_html.find(">", i)
        if deb < 0:
            break
        j = deb + 1
        profondeur = 1
        ignorer = None
        morceau = []
        while profondeur > 0 and j < len(page_html):
            k = page_html.find("<", j)
            if k < 0:
                break
            if ignorer is None:
                morceau.append(page_html[j:k])
            fin_tag = page_html.find(">", k)
            if fin_tag < 0:
                break
            tag = page_html[k + 1:fin_tag]
            j = fin_tag + 1
            fermant = tag.startswith("/")
            nom = re.match(r"[a-zA-Z0-9]+", tag.lstrip("/"))
            nom = nom.group(0).lower() if nom else ""
            if nom == "br":
                if ignorer is None:
                    morceau.append("\n")
            elif nom in ("img", "hr", "input", "meta", "link", "wbr", "source") or tag.endswith("/") or not nom:
                pass
            elif fermant:
                profondeur -= 1
                if ignorer is not None and profondeur < ignorer:
                    ignorer = None
            else:
                profondeur += 1
                if ignorer is None and 'data-exclude-from-selection="true"' in tag:
                    ignorer = profondeur
        blocs.append(html.unescape("".join(morceau)))
        pos = j
    texte = "\n".join(l.strip() for l in "\n".join(blocs).splitlines())
    texte = re.sub(r"\n{3,}", "\n\n", texte).strip()
    return texte if len(_tokens(texte)) >= 8 else None


def _genius_secours(termes):
    url = "https://genius.com/api/search/song?" + urllib.parse.urlencode({"q": termes, "per_page": "3"})
    try:
        d = _get(url, essais=1, headers=UA_NAV, timeout=5)
    except ERREURS_IO:
        return []
    hits = []
    for sec in (d or {}).get("response", {}).get("sections") or []:
        for h in sec.get("hits") or []:
            res = h.get("result") or {}
            if res.get("instrumental") or not res.get("url") or not res.get("title"):
                continue
            hits.append({
                "titre": res["title"],
                "artiste": res.get("artist_names") or (res.get("primary_artist") or {}).get("name") or "",
                "album": "",
                "duree": 0.0,
                "url": res["url"],
                "source": "Genius",
            })
    return hits[:2]


def _trouver(p):
    """Recherche multi-sources (LRCLIB + NetEase mot-à-mot + Genius en repli) avec notation stricte."""
    vars_p = variantes(p)
    if not vars_p:
        return None

    # Compatibilité avec les tests qui remplacent `_lrclib` par un mock
    if _lrclib is not _LRCLIB_ORIGINAL:
        for a, t in vars_p:
            r = _lrclib({
                **p,
                "artiste": a or "Artiste inconnu",
                "titre": t,
                "album": p.get("album") if a == p.get("artiste") else "",
            })
            if r:
                return r
        return None

    candidats_bruts = []
    candidats_netease = []
    verrou = threading.Lock()
    requetes_vues = set()

    def tache_lrclib_get(a, t, alb):
        q = {"track_name": t, "artist_name": a}
        if alb:
            q["album_name"] = alb
        if p.get("duree"):
            q["duration"] = round(p["duree"])
        with contextlib.suppress(*ERREURS_IO):
            r = _get("https://lrclib.net/api/get?" + urllib.parse.urlencode(q), essais=2, timeout=6)
            if r and (r.get("syncedLyrics") or r.get("plainLyrics") or r.get("instrumental")):
                with verrou:
                    candidats_bruts.append({
                        **r,
                        "titre": r.get("trackName") or t,
                        "artiste": r.get("artistName") or a,
                        "album": r.get("albumName") or "",
                        "duree": r.get("duration") or 0.0,
                        "source": "lrclib",
                    })

    def tache_lrclib_search(params):
        with contextlib.suppress(*ERREURS_IO):
            res = _get("https://lrclib.net/api/search?" + urllib.parse.urlencode(params), essais=2, timeout=6)
            if isinstance(res, list):
                with verrou:
                    for r in res:
                        if r.get("syncedLyrics") or r.get("plainLyrics") or r.get("instrumental"):
                            candidats_bruts.append({
                                **r,
                                "titre": r.get("trackName") or "",
                                "artiste": r.get("artistName") or "",
                                "album": r.get("albumName") or "",
                                "duree": r.get("duration") or 0.0,
                                "source": "lrclib",
                            })

    def tache_netease(termes):
        with contextlib.suppress(*ERREURS_IO):
            res = _netease_rechercher(termes, limite=8)
            with verrou:
                candidats_netease.extend(res)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = []
        for idx, (a, t) in enumerate(vars_p[:4]):
            if idx == 0 and a:
                futures.append(pool.submit(tache_lrclib_get, a, t, p.get("album") or ""))
            termes = f"{a} {t}".strip() if a else t
            cle_q = f"q:{termes.lower()}"
            if cle_q not in requetes_vues:
                requetes_vues.add(cle_q)
                futures.append(pool.submit(tache_lrclib_search, {"q": termes}))
                futures.append(pool.submit(tache_netease, termes))
            if a:
                cle_ta = f"ta:{a.lower()}:{t.lower()}"
                if cle_ta not in requetes_vues:
                    requetes_vues.add(cle_ta)
                    futures.append(pool.submit(tache_lrclib_search, {"track_name": t, "artist_name": a}))
        for f in futures:
            f.result()

    # Pré-filtrer les meilleurs candidats NetEase et récupérer leurs paroles (yrc/klyric/lrc)
    ne_notes = []
    ids_ne_vus = set()
    for c in candidats_netease:
        sid = c["netease_id"]
        if sid in ids_ne_vus:
            continue
        ids_ne_vus.add(sid)
        note = _noter_candidat(p, vars_p, c)
        if note:
            ne_notes.append((note["score"], c))
    ne_notes.sort(key=lambda x: x[0], reverse=True)

    if ne_notes:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [(c, pool.submit(_netease_paroles, c["netease_id"])) for _, c in ne_notes[:3]]
            for c, fut in futs:
                with contextlib.suppress(*ERREURS_IO):
                    lyr = fut.result()
                    if lyr:
                        candidats_bruts.append({**c, **lyr})

    # Noter tous les candidats avec paroles
    notes = []
    for c in candidats_bruts:
        note = _noter_candidat(p, vars_p, c)
        if note:
            notes.append((note, c))

    # Sélection par palier :
    # 1. Synchronisé de durée exacte (avec bonus pour le mot-à-mot YRC/LRC enrichi)
    synchro_exacts = [(n, c) for n, c in notes if n["nb_lignes"] >= 3 and n["exact"]]
    if synchro_exacts:
        synchro_exacts.sort(key=lambda x: (x[0]["a_mots"], x[0]["score"]), reverse=True)
        _, meilleur = synchro_exacts[0]
        return {**meilleur, "approximatif": False}

    duree_piste = float(p.get("duree") or 0.0)
    # 2. Synchronisé d'une version proche (écart <= 45 s et pas de débordement absurde)
    # Un débordement modéré (ex: outro de l'album vs clip/radio edit) reste parfaitement synchronisé
    # sur toute la partie chantée : on n'exclut que les débordements excessifs (> 50s après la piste).
    synchro_approx = [
        (n, c) for n, c in notes
        if n["nb_lignes"] >= 3
        and (n["ecart"] is None or n["ecart"] <= 45.0)
        and (
            not n["deborde"]
            or (
                n["ecart"] is not None
                and n["ecart"] <= 45.0
                and (not duree_piste or float(c.get("duree") or 0.0) <= duree_piste + 50.0)
            )
        )
    ]
    if synchro_approx:
        synchro_approx.sort(key=lambda x: x[0]["score"] - (x[0]["ecart"] or 15.0) * 1.5, reverse=True)
        _, meilleur = synchro_approx[0]
        return {**meilleur, "approximatif": True}

    # 3. Secours Genius si aucun texte n'a été trouvé
    textes = [(n, c) for n, c in notes if c.get("plainLyrics") or c.get("syncedLyrics")]
    if not textes:
        a0, t0 = vars_p[0]
        for h in _genius_secours(f"{a0} {t0}".strip()):
            note = _noter_candidat(p, vars_p, h)
            if note:
                with contextlib.suppress(*ERREURS_IO):
                    req = urllib.request.Request(h["url"], headers=UA_NAV)
                    with urllib.request.urlopen(req, timeout=5) as r:
                        page = r.read().decode("utf-8", errors="replace")
                    extrait = _extraire_genius_html(page)
                    if extrait:
                        textes.append((note, {**h, "plainLyrics": extrait}))
                        break

    if textes:
        textes.sort(key=lambda x: x[0]["score"], reverse=True)
        _, meilleur = textes[0]
        brut = meilleur.get("plainLyrics") or MOT.sub("", re.sub(r"\[[^\]]*\]", "", meilleur.get("syncedLyrics") or "")).strip()
        return {**meilleur, "syncedLyrics": None, "plainLyrics": brut}

    instr = [(n, c) for n, c in notes if c.get("instrumental")]
    if instr:
        instr.sort(key=lambda x: x[0]["score"], reverse=True)
        return instr[0][1]

    return None


_LRCLIB_ORIGINAL = _lrclib


def _resultat(r, source=None):
    src = source or (r.get("source") if isinstance(r, dict) else None) or "lrclib"
    if r and r.get("instrumental"):
        return {"source": src, "instrumental": True, "synchro": [], "texte": ""}
    if r:
        donnees = _depuis_lrc(r.get("syncedLyrics"))
        texte_brut = r.get("plainLyrics") or (
            MOT.sub("", re.sub(r"\[[^\]]*\]", "", r.get("syncedLyrics") or "")).strip()
            if r.get("syncedLyrics")
            else ""
        )
        res = {
            "source": src,
            **donnees,
            "texte": texte_brut,
        }
        if r.get("approximatif"):
            res["approximatif"] = True
        return res
    return {"source": None, "synchro": [], "texte": ""}


def _lire_paroles_tag(chemin):
    """Extrait les paroles intégrées aux tags du fichier audio (MP4 ©lyr, ID3 USLT/SYLT, Vorbis LYRICS)."""
    try:
        f = mutagen.File(chemin)
    except (OSError, mutagen.MutagenError):
        return None
    if f is None or not getattr(f, "tags", None):
        return None
    tags = f.tags
    with contextlib.suppress(*ERREURS_IO, mutagen.MutagenError):
        if tags.get("\xa9lyr"):
            return str(tags["\xa9lyr"][0]).strip()
        if hasattr(tags, "getall"):
            for u in tags.getall("USLT"):
                if getattr(u, "text", None) and str(u.text).strip():
                    return str(u.text).strip()
        for cle in ("lyrics", "LYRICS", "unsyncedlyrics", "UNSYNCEDLYRICS", "©lyr"):
            if tags.get(cle):
                v = tags[cle]
                return str(v[0] if isinstance(v, list) else v).strip()
    return None


def _fichier_lrc_voisin(chemin_audio):
    p = Path(chemin_audio)
    for ext in (".lrc", ".LRC"):
        cand = p.with_suffix(ext)
        if cand.exists():
            return cand
    return p.with_suffix(".lrc")


def paroles(piste_id, forcer=False):
    p = bibliotheque.piste(piste_id)
    if not p:
        return None
    cache = config.PAROLES / f"{piste_id}.json"
    chemin_audio = Path(p["chemin"])
    lrc = _fichier_lrc_voisin(chemin_audio)
    duree = p.get("duree")

    if cache.exists() and not forcer:
        try:
            res = json.loads(cache.read_text())
        except (OSError, ValueError):
            res = {}
        if lrc.exists() and (
            res.get("version_synchro") != 2
            or lrc.stat().st_mtime > cache.stat().st_mtime
            or (chemin_audio.is_file() and res.get("synchro") and _alignement_a_refaire(res, chemin_audio))
        ):
            texte = lrc.read_text(errors="replace")
            res = {
                "source": "fichier .lrc",
                **_depuis_lrc(texte),
                "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", texte)).strip(),
            }
            if "[re:Onde" in texte[:120]:
                res["auto_lrc"] = True
            if chemin_audio.is_file():
                res = aligner_sur_audio(chemin_audio, res, duree=duree)
            cache.write_text(json.dumps(res, ensure_ascii=False))
            return res

        # Auto-réparation des anciens caches en ligne incomplets ou décalés
        if chemin_audio.is_file() and res.get("source") and not lrc.exists():
            syn = res.get("synchro") or []
            deborde = bool(duree and syn and syn[-1][0] > duree + 50.0)
            sans_synchro = not syn and not res.get("instrumental") and res.get("source") == "lrclib"
            if deborde or sans_synchro:
                res_aura = _lire_paroles_aura(chemin_audio, p)
                if res_aura and res_aura.get("synchro"):
                    if chemin_audio.is_file():
                        res_aura = aligner_sur_audio(chemin_audio, res_aura, duree=duree)
                    cache.write_text(json.dumps(res_aura, ensure_ascii=False))
                    return res_aura
                trouve = _trouver(p)
                if trouve:
                    res = _resultat(trouve)
                    res = aligner_sur_audio(chemin_audio, res, duree=duree)
                    cache.write_text(json.dumps(res, ensure_ascii=False))
                    return res
            if syn and _alignement_a_refaire(res, chemin_audio):
                res = aligner_sur_audio(chemin_audio, res, duree=duree)
                cache.write_text(json.dumps(res, ensure_ascii=False))
                return res

        # Si le cache est vide ("source": null ou sans paroles) : vérifier Aura avant d'attendre 6 h
        if (not res.get("source") or (not res.get("synchro") and not res.get("texte"))) and not lrc.exists():
            res_aura = _lire_paroles_aura(chemin_audio, p)
            if res_aura and (res_aura.get("synchro") or res_aura.get("texte")):
                if chemin_audio.is_file() and res_aura.get("synchro"):
                    res_aura = aligner_sur_audio(chemin_audio, res_aura, duree=duree)
                cache.write_text(json.dumps(res_aura, ensure_ascii=False))
                return res_aura

        # « rien trouvé » ne reste pas pour toujours : on retente après 6 h (ou si le .lrc est apparu)
        if res.get("source") or (time.time() - cache.stat().st_mtime < 6 * 3600 and not lrc.exists()):
            return res

    if lrc.exists():
        texte = lrc.read_text(errors="replace")
        res = {
            "source": "fichier .lrc",
            **_depuis_lrc(texte),
            "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", texte)).strip(),
        }
        if "[re:Onde" in texte[:120]:
            res["auto_lrc"] = True
    else:
        texte_tag = _lire_paroles_tag(chemin_audio) if chemin_audio.is_file() else None
        donnees_tag = _depuis_lrc(texte_tag) if texte_tag else None
        if donnees_tag and len(donnees_tag["synchro"]) >= 3:
            res = {
                "source": "tag audio",
                **donnees_tag,
                "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", texte_tag)).strip(),
            }
        else:
            # 1. Vérifier si Aura a déjà les paroles pour ce morceau
            res_aura = _lire_paroles_aura(chemin_audio, p)
            if res_aura and (res_aura.get("synchro") or res_aura.get("texte")):
                res = res_aura
            else:
                trouve = _trouver(p)
                res = _resultat(trouve)
                if not res.get("synchro") and not res.get("texte") and texte_tag:
                    res = {"source": "tag audio", "synchro": [], "mots": [], "version_synchro": 2, "texte": texte_tag}

    if chemin_audio.is_file() and res.get("synchro"):
        res = aligner_sur_audio(chemin_audio, res, duree=duree)
    cache.write_text(json.dumps(res, ensure_ascii=False))
    return res


def recaler(piste_id):
    """Relance l'analyse vocale complète sur le fichier audio pour recaler les paroles."""
    p = bibliotheque.piste(piste_id)
    if not p:
        return None
    chemin_audio = Path(p["chemin"])
    lrc = _fichier_lrc_voisin(chemin_audio)
    if lrc.exists():
        texte = lrc.read_text(errors="replace")
        res = {
            "source": "fichier .lrc",
            **_depuis_lrc(texte),
            "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", texte)).strip(),
        }
    else:
        res = paroles(piste_id, forcer=False) or {}
        if not res.get("synchro"):
            res = paroles(piste_id, forcer=True) or {}
    if chemin_audio.is_file() and res.get("synchro"):
        res = aligner_sur_audio(chemin_audio, res, duree=p.get("duree"), forcer_recalage=True)
        (config.PAROLES / f"{piste_id}.json").write_text(json.dumps(res, ensure_ascii=False))
    return res


# ── recherche manuelle ──────────────────────────────────────────────
def proposition(piste_id):
    """Artiste / titre nettoyés pour pré-remplir la recherche manuelle."""
    p = bibliotheque.piste(piste_id)
    if not p:
        return None
    v = variantes(p)
    meilleur = next((x for x in v[1:] if x[0]), v[0])
    return {"artiste": meilleur[0], "titre": meilleur[1], "duree": p.get("duree")}


def chercher(q, duree=None):
    resultats = []
    erreur_lrclib = None

    def chercher_lrc():
        nonlocal erreur_lrclib
        try:
            res = _get("https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": q}))
            for r in res or []:
                if r.get("syncedLyrics") or r.get("plainLyrics") or r.get("instrumental"):
                    _, _, a_mots = _etendue_lrc(r.get("syncedLyrics"))
                    resultats.append({
                        "id": r["id"],
                        "source": "LRCLIB",
                        "artiste": r.get("artistName"),
                        "titre": r.get("trackName"),
                        "album": r.get("albumName"),
                        "duree": r.get("duration"),
                        "synchro": bool(r.get("syncedLyrics")),
                        "mot_a_mot": a_mots,
                        "instrumental": bool(r.get("instrumental")),
                        "extrait": " / ".join(
                            l for l in re.sub(r"\[[^\]]*\]", "", r.get("syncedLyrics") or r.get("plainLyrics") or "").splitlines()
                            if l.strip()
                        )[:120],
                    })
        except ERREURS_IO as e:
            erreur_lrclib = e

    def chercher_ne():
        if _get is not _GET_ORIGINAL:
            return
        with contextlib.suppress(*ERREURS_IO):
            ne = _netease_rechercher(q, limite=6)
            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = [(c, pool.submit(_netease_paroles, c["netease_id"])) for c in ne[:4]]
                for c, fut in futs:
                    lyr = fut.result()
                    if not lyr:
                        continue
                    syn = lyr.get("syncedLyrics")
                    brut = lyr.get("plainLyrics") or ""
                    if not syn and not brut and not lyr.get("instrumental"):
                        continue
                    resultats.append({
                        "id": f"netease:{c['netease_id']}",
                        "source": "NetEase",
                        "artiste": c["artiste"],
                        "titre": c["titre"],
                        "album": c["album"],
                        "duree": c["duree"],
                        "synchro": bool(syn),
                        "mot_a_mot": bool(lyr.get("mot_a_mot")),
                        "instrumental": bool(lyr.get("instrumental")),
                        "extrait": " / ".join(l for l in brut.splitlines() if l.strip())[:120],
                    })

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(chercher_lrc)
        f2 = pool.submit(chercher_ne)
        f1.result()
        f2.result()

    if not resultats and erreur_lrclib is not None:
        raise RuntimeError(f"lrclib.net injoignable ({erreur_lrclib})") from erreur_lrclib

    if duree:
        resultats.sort(key=lambda r: (
            not r.get("synchro"),
            abs((r.get("duration" if "duration" in r else "duree") or 0) - duree) > 4,
            not r.get("mot_a_mot"),
            abs((r.get("duree") or 0) - duree),
        ))
    else:
        resultats.sort(key=lambda r: (not r.get("synchro"), not r.get("mot_a_mot")))
    return resultats[:25]


_GET_ORIGINAL = _get


def _enregistrer(piste_id, res, texte_lrc=None):
    p = bibliotheque.piste(piste_id)
    chemin_audio = Path(p["chemin"]) if p and p.get("chemin") else None
    if texte_lrc and chemin_audio:
        with contextlib.suppress(OSError):
            automatique = res.get("source") != "fichier .lrc"
            if automatique and "[re:Onde" not in texte_lrc[:120]:
                texte_lrc = "[re:Onde]\n" + texte_lrc
            chemin_audio.with_suffix(".lrc").write_text(texte_lrc)
            res["source"] = "fichier .lrc"
            res["auto_lrc"] = automatique
    if chemin_audio and chemin_audio.is_file() and res.get("synchro"):
        res = aligner_sur_audio(chemin_audio, res, duree=p.get("duree"))
    (config.PAROLES / f"{piste_id}.json").write_text(json.dumps(res, ensure_ascii=False))
    return res


def choisir(piste_id, identifiant):
    s_id = str(identifiant)
    if s_id.startswith("netease:"):
        sid = int(s_id.split(":", 1)[1])
        r = _netease_paroles(sid)
        if not r:
            raise RuntimeError("Paroles NetEase introuvables")
        res = _resultat(r, source="NetEase")
        return _enregistrer(piste_id, res, r.get("syncedLyrics") or None)
    r = _get(f"https://lrclib.net/api/get/{int(s_id.removeprefix('lrclib:'))}")
    res = _resultat(r)
    return _enregistrer(piste_id, res, r.get("syncedLyrics") or None)


def importer(piste_id, texte):
    """Texte collé ou fichier .lrc importé (synchronisé ou non)."""
    texte = (texte or "").strip()
    donnees = _depuis_lrc(texte)
    synchro = donnees["synchro"]
    res = {
        "source": "fichier .lrc" if synchro else "texte importé",
        **donnees,
        "texte": MOT.sub("", re.sub(r"\[[^\]]*\]", "", texte)).strip(),
    }
    return _enregistrer(piste_id, res, texte if synchro else None)


# ── recherche dans le texte des paroles de toute la bibliothèque ────
def _normal(s):
    return re.sub(r"[^a-z0-9]+", " ", bibliotheque.sans_accents(s)).strip()


_index = {"signature": None, "pistes": {}}
_verrou_index = threading.Lock()


def _signature():
    try:
        fichiers = list(os.scandir(config.PAROLES))
    except OSError:
        fichiers = []
    return (bibliotheque.REV["n"], len(fichiers), max((f.stat().st_mtime for f in fichiers), default=0))


def _lignes_piste(pid, chemin):
    """[(secondes ou None, ligne)] depuis le cache d'Onde, sinon le .lrc à côté du morceau."""
    with contextlib.suppress(OSError, ValueError):
        d = json.loads((config.PAROLES / f"{pid}.json").read_text())
        if d.get("synchro"):
            return [(t, l) for t, l in d["synchro"] if l.strip()]
        if d.get("texte"):
            return [(None, l) for l in d["texte"].splitlines() if l.strip()]
    lrc = _fichier_lrc_voisin(chemin)
    if lrc.exists():
        with contextlib.suppress(OSError):
            return [(t, l) for t, l in analyser_lrc(lrc.read_text(errors="replace")) if l.strip()]
    return []


def _indexer():
    sig = _signature()
    with _verrou_index:
        if _index["signature"] == sig:
            return _index["pistes"]
        pistes = {}
        for r in bibliotheque.requete("SELECT id, chemin FROM pistes WHERE fusion_vers IS NULL"):
            lignes = _lignes_piste(r["id"], r["chemin"])
            if lignes:
                pistes[r["id"]] = [(t, l, _normal(l)) for t, l in lignes]
        _index.update(signature=sig, pistes=pistes)
        return pistes


def rechercher_texte(q, limite=30):
    """Titres dont les paroles contiennent la phrase (accents et ponctuation ignorés)."""
    q = _normal(q)
    if len(q) < 3:
        return []
    res = []
    for pid, lignes in _indexer().items():
        for k, (t, l, n) in enumerate(lignes):
            suiv = lignes[k + 1] if k + 1 < len(lignes) else None
            if q in n:
                texte, zone = l, n
            elif suiv and q not in suiv[2] and q in f"{n} {suiv[2]}":
                texte, zone = f"{l} / {suiv[1]}", f"{n} {suiv[2]}"
            else:
                continue
            res.append({
                "id": pid,
                "t": t,
                "ligne": texte,
                "debut": re.search(rf"(^| ){re.escape(q)}( |$)", zone) is not None,
            })
            break
    res.sort(key=lambda r: not r["debut"])
    return res[:limite]


def couverture():
    """Nombre de titres dont les paroles sont connues (donc cherchables)."""
    total = bibliotheque.requete("SELECT COUNT(*) n FROM pistes WHERE fusion_vers IS NULL", un=True)["n"]
    return {"avec": len(_indexer()), "total": total}


# ── récupération des paroles de toute la bibliothèque, en arrière-plan ─
ETAT_TOUT = {"en_cours": False, "fait": 0, "total": 0, "trouvees": 0}


def recuperer_tout():
    if ETAT_TOUT["en_cours"]:
        return ETAT_TOUT

    def tache():
        manquants = [
            r["id"] for r in bibliotheque.requete("SELECT id, chemin FROM pistes WHERE fusion_vers IS NULL")
            if not (config.PAROLES / f"{r['id']}.json").exists()
        ]
        ETAT_TOUT.update(en_cours=True, fait=0, total=len(manquants), trouvees=0)
        try:
            for pid in manquants:
                with contextlib.suppress(*ERREURS_IO):
                    r = paroles(pid)
                    if r and (r.get("synchro") or r.get("texte")):
                        ETAT_TOUT["trouvees"] += 1
                ETAT_TOUT["fait"] += 1
                time.sleep(0.25)
        finally:
            ETAT_TOUT["en_cours"] = False

    ETAT_TOUT["en_cours"] = True
    threading.Thread(target=tache, daemon=True, name="paroles-tout").start()
    return ETAT_TOUT
