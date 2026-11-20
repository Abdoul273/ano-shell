"""Propriétés d'un fichier, sauvegarde et restauration des données d'Onde."""
import json
import os
import socket
import time
from pathlib import Path

import mutagen

from . import VERSION, bibliotheque as bib, config

FORMAT_SAUVEGARDE = 1


# ── propriétés d'un titre ───────────────────────────────────────────
def _codec(f, fmt):
    i = getattr(f, "info", None)
    if i is None:
        return fmt.upper()
    if getattr(i, "codec_description", None):  # MP4 : « AAC LC », « ALAC »…
        return i.codec_description
    nom = type(f).__name__
    if nom in ("MP3", "EasyMP3"):
        return f"MP3 (MPEG {getattr(i, 'version', 1):g} couche {getattr(i, 'layer', 3)})"
    return {"FLAC": "FLAC", "OggVorbis": "Vorbis", "OggOpus": "Opus", "WAVE": "PCM (WAV)", "AIFF": "PCM (AIFF)",
            "OggFLAC": "FLAC (Ogg)", "AAC": "AAC (ADTS)"}.get(nom, fmt.upper())


def _encodeur(f):
    tags = getattr(f, "tags", None)
    if not tags:
        return None
    for cle in ("TSSE", "\xa9too", "encoder", "ENCODER", "encoded_by"):
        try:
            v = tags.get(cle)
        except Exception:
            v = None
        if v:
            v = v.text if hasattr(v, "text") else v
            return str(v[0] if isinstance(v, (list, tuple)) else v)
    return None


def proprietes(pid):
    p = bib.piste(pid)
    if not p:
        return None
    chemin = Path(p["chemin"])
    res = {**p, "existe": chemin.exists(), "dossier": str(chemin.parent), "fichier": chemin.name}
    try:
        st = chemin.stat()
        res.update(taille=st.st_size, mtime=st.st_mtime)
    except OSError:
        pass
    try:
        f = mutagen.File(chemin)
    except Exception:
        f = None
    if f is not None:
        i = f.info
        res.update(bib.qualite(f), codec=_codec(f, p["format"] or ""), encodeur=_encodeur(f),
                   debit=int(i.bitrate / 1000) if getattr(i, "bitrate", 0) else p["debit"],
                   mode_debit={0: None, 1: "constant", 2: "variable", 3: "variable"}.get(getattr(getattr(i, "bitrate_mode", None), "value", 0)),
                   duree=getattr(i, "length", None) or p["duree"])
    ec = bib.requete("SELECT COUNT(*) n, MIN(date) premiere, MAX(date) derniere FROM ecoutes WHERE piste_id=?", (pid,), un=True)
    res.update(ecoutes=ec["n"], premiere_ecoute=ec["premiere"], derniere_ecoute=ec["derniere"],
               favori=bool(bib.requete("SELECT 1 FROM favoris WHERE piste_id=?", (pid,), un=True)),
               playlists=[r["nom"] for r in bib.requete(
                   "SELECT DISTINCT p.nom FROM playlist_pistes x JOIN playlists p ON p.id = x.playlist_id WHERE x.piste_id=?", (pid,))])
    try:
        n = bib.requete("SELECT gain, source FROM niveaux WHERE piste_id=? AND erreur IS NULL", (pid,), un=True)
        res["niveau"] = dict(n) if n and n["gain"] is not None else None
    except Exception:
        res["niveau"] = None
    try:
        par = json.loads((config.PAROLES / f"{pid}.json").read_text())
        res["paroles"] = "synchronisées" if par.get("synchro") else "instrumental" if par.get("instrumental") else "texte" if par.get("texte") else "aucune"
        res["paroles_source"] = par.get("source")
    except (OSError, ValueError):
        res["paroles"] = "synchronisées (.lrc)" if chemin.with_suffix(".lrc").exists() else None
    if p["pochette"]:
        try:
            res["pochette_taille"] = (config.POCHETTES / p["pochette"]).stat().st_size
        except OSError:
            pass
    return res


# ── sauvegarde ──────────────────────────────────────────────────────
# Les titres sont désignés par leur chemin (et non leur id) : la sauvegarde reste valable
# après une réinstallation ou une base reconstruite.
PAR_ID = ("onde.decalages", "onde.ancresParoles", "onde.positions")  # données du navigateur indexées par id de titre


def _chemins():
    return {r["id"]: r["chemin"] for r in bib.requete("SELECT id, chemin FROM pistes")}


def creer(client):
    chemins = _chemins()
    vers_chemin = lambda i: chemins.get(i)  # noqa: E731
    client = dict(client or {})
    for cle in PAR_ID:
        if isinstance(client.get(cle), dict):
            client[cle] = {vers_chemin(int(k)): v for k, v in client[cle].items() if str(k).isdigit() and vers_chemin(int(k))}
    lec = client.get("onde.lecture")
    if isinstance(lec, dict):
        client["onde.lecture"] = {**lec, "file": [vers_chemin(i) for i in lec.get("file") or [] if vers_chemin(i)],
                                  "ordre": [vers_chemin(i) for i in lec.get("ordre") or [] if vers_chemin(i)]}
    return {
        "onde_sauvegarde": FORMAT_SAUVEGARDE, "version": VERSION, "date": time.time(), "machine": socket.gethostname(),
        "reglages": config.lire_reglages(),
        "playlists": [{"nom": pl["nom"], "description": pl["description"], "cree": pl["cree"], "modifie": pl["modifie"],
                       "pistes": [chemins[i] for i in pl["pistes"] if i in chemins]} for pl in bib.playlists()],
        "favoris": [[chemins[r["piste_id"]], r["date"]] for r in bib.requete("SELECT piste_id, date FROM favoris") if r["piste_id"] in chemins],
        "ecoutes": [[chemins[r["piste_id"]], r["date"]] for r in bib.requete("SELECT piste_id, date FROM ecoutes") if r["piste_id"] in chemins],
        "radios": bib.radios(),
        "client": client,
    }


def _resolveur():
    """chemin (ou à défaut nom de fichier, si la musique a été déplacée) → id visible."""
    lignes = bib.requete("SELECT id, chemin, fusion_vers FROM pistes")
    par_chemin = {r["chemin"]: r["fusion_vers"] or r["id"] for r in lignes}
    par_nom = {}
    for r in lignes:
        par_nom.setdefault(os.path.basename(r["chemin"]), set()).add(r["fusion_vers"] or r["id"])
    manquants = set()

    def trouver(chemin):
        if chemin in par_chemin:
            return par_chemin[chemin]
        candidats = par_nom.get(os.path.basename(chemin or ""), ())
        if len(candidats) == 1:
            return next(iter(candidats))
        manquants.add(chemin)
        return None
    return trouver, manquants


def restaurer(s):
    if not isinstance(s, dict) or s.get("onde_sauvegarde") != FORMAT_SAUVEGARDE:
        raise ValueError("Ce fichier n'est pas une sauvegarde Onde")
    trouver, manquants = _resolveur()
    reglages = {k: v for k, v in (s.get("reglages") or {}).items() if k in config.REGLAGES_DEFAUT}
    if "dossiers" in reglages:
        reglages["dossiers"] = [d for d in reglages["dossiers"] if Path(d).expanduser().is_dir()] or config.lire_reglages()["dossiers"]
    config.ecrire_reglages(reglages)
    n_ecoutes = 0
    with bib._verrou, bib._db as db:
        db.execute("DELETE FROM playlist_pistes")
        db.execute("DELETE FROM playlists")
        for pl in s.get("playlists") or []:
            cur = db.execute("INSERT INTO playlists (nom, description, cree, modifie) VALUES (?, ?, ?, ?)",
                             (str(pl.get("nom") or "Playlist"), str(pl.get("description") or ""), pl.get("cree") or time.time(), pl.get("modifie") or time.time()))
            ids = list(dict.fromkeys(i for i in map(trouver, pl.get("pistes") or []) if i))
            db.executemany("INSERT INTO playlist_pistes VALUES (?, ?, ?)", [(cur.lastrowid, i, n) for n, i in enumerate(ids)])
        db.execute("DELETE FROM favoris")
        for chemin, date in s.get("favoris") or []:
            i = trouver(chemin)
            if i:
                db.execute("INSERT OR IGNORE INTO favoris VALUES (?, ?)", (i, date))
        deja = {(r[0], round(r[1], 3)) for r in db.execute("SELECT piste_id, date FROM ecoutes")}
        for chemin, date in s.get("ecoutes") or []:  # fusion : on n'efface pas l'historique existant
            i = trouver(chemin)
            if i and (i, round(date, 3)) not in deja:
                db.execute("INSERT INTO ecoutes VALUES (?, ?)", (i, date))
                n_ecoutes += 1
        db.execute("DELETE FROM radios")
        for r in s.get("radios") or []:
            db.execute("INSERT OR IGNORE INTO radios (nom, url, logo, pays, tags) VALUES (?, ?, ?, ?, ?)",
                       (r.get("nom"), r.get("url"), r.get("logo"), r.get("pays"), r.get("tags")))
    bib._toucher()

    client = dict(s.get("client") or {})
    for cle in PAR_ID:
        if isinstance(client.get(cle), dict):
            client[cle] = {str(i): v for c, v in client[cle].items() if (i := trouver(c))}
    lec = client.get("onde.lecture")
    if isinstance(lec, dict):
        file = [i for i in map(trouver, lec.get("file") or []) if i]
        client["onde.lecture"] = {**lec, "file": file, "ordre": [i for i in map(trouver, lec.get("ordre") or []) if i],
                                  "index": min(lec.get("index", -1), len(file) - 1)}
    return {"client": client, "playlists": len(s.get("playlists") or []), "favoris": len(s.get("favoris") or []),
            "ecoutes": n_ecoutes, "radios": len(s.get("radios") or []), "manquants": len(manquants)}
