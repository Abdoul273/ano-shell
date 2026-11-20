"""Recherche iTunes, rapprochement par durée et écriture atomique des tags."""
import base64
import functools
import json
import os
import re
import shutil
import tempfile
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
from mutagen.mp4 import MP4, MP4Cover

from . import bibliotheque as bib
from . import config

_reseau = threading.Lock()
_dernier = 0.0
CHAMPS = {"titre": "title", "artiste": "artist", "album": "album", "artiste_album": "albumartist",
          "annee": "date", "genre": "genre", "numero": "tracknumber"}


@functools.lru_cache(maxsize=128)
def _itunes(parametres):
    global _dernier
    with _reseau:
        time.sleep(max(0, 3.1 - (time.monotonic() - _dernier)))
        _dernier = time.monotonic()
        chemin, args = parametres
        req = Request("https://itunes.apple.com/" + chemin + "?" + args, headers={"User-Agent": "Onde/1.0"})
        try:
            with urlopen(req, timeout=8) as r:
                return json.load(r).get("results", [])
        except (OSError, ValueError) as e:
            raise RuntimeError("iTunes ne répond pas. Réessaie dans un instant.") from e


def _resultat(r):
    return {"itunes": r.get("trackId"), "collection": r.get("collectionId"), "titre": r.get("trackName", ""),
            "artiste": r.get("artistName", ""), "album": r.get("collectionName", ""),
            "annee": (r.get("releaseDate") or "")[:4], "genre": r.get("primaryGenreName", ""),
            "numero": r.get("trackNumber"), "duree": (r.get("trackTimeMillis") or 0) / 1000,
            "image": r.get("artworkUrl100", ""), "source": "iTunes"}


def _norm(s):
    return bib.cle_nom(bib.nettoyer_texte(s))


def score(p, r):
    titre = SequenceMatcher(None, _norm(p["titre"]), _norm(r["titre"])).ratio()
    artiste = SequenceMatcher(None, _norm(p["artiste"]), _norm(r["artiste"])).ratio()
    ecart = abs(p["duree"] - r["duree"]) if p.get("duree") and r.get("duree") else None
    return round(100 * (.65 * titre + .2 * artiste + .15 * (max(0, 1 - ecart / 15) if ecart is not None else 0))), ecart


def rechercher(pid, q="", album=False):
    p = bib.piste(pid)
    if not p:
        raise ValueError("Titre introuvable")
    q = q.strip() or " ".join([p["artiste"] if p["artiste"] != "Artiste inconnu" else "",
                              p["album"] if album else p["titre"]]).strip()
    if not q or len(q) > 300:
        raise ValueError("Indique un titre ou un artiste")
    rs = _itunes(("search", urlencode({"term": q, "entity": "album" if album else "song", "media": "music", "country": "FR", "limit": 25})))
    res = [_resultat(r) for r in rs]
    recherche_initiale = q == " ".join([p["artiste"], p["titre"]]).strip()
    if not album and recherche_initiale and p["artiste"] != "Artiste inconnu" and max((score(p, r)[0] for r in res), default=0) < 80:
        # Les rips contiennent souvent une faute dans le titre : chercher l'album de l'artiste.
        secours = " ".join([p["artiste"], p["album"]]).strip()
        autres = _itunes(("search", urlencode({"term": secours, "entity": "song", "media": "music", "country": "FR", "limit": 100})))
        deja = {r["itunes"] for r in res}
        res.extend(_resultat(r) for r in autres if r.get("trackId") not in deja)
    for r in res:
        r["score"], r["ecart"] = score(p, r)
    return sorted(res, key=lambda r: -r["score"]) if not album else res


def pistes_album(collection, ids):
    rs = [_resultat(r) for r in _itunes(("lookup", urlencode({"id": int(collection), "entity": "song", "country": "FR"}))) if r.get("trackId")]
    resultat, utilises = [], set()
    for pid in ids:
        p = bib.piste(pid)
        if not p:
            continue
        candidats = [r for r in rs if r["itunes"] not in utilises]
        if not candidats:
            continue
        r = max(candidats, key=lambda r: score(p, r)[0])
        s, ecart = score(p, r)
        # Un album contient parfois plusieurs versions du même titre : ne pas deviner au numéro seul.
        if SequenceMatcher(None, _norm(p["titre"]), _norm(r["titre"])).ratio() < .65:
            continue
        utilises.add(r["itunes"])
        resultat.append({"id": pid, "avant": p["titre"], **r, "score": s, "ecart": ecart})
    return resultat


def _pochette(url):
    u = urlparse(url)
    if u.scheme != "https" or not (u.hostname or "").endswith(".mzstatic.com"):
        raise ValueError("Pochette iTunes invalide")
    with urlopen(Request(url, headers={"User-Agent": "Onde/1.0"}), timeout=8) as r:
        octets = r.read(5_000_001)
    if len(octets) > 5_000_000 or not octets.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        raise ValueError("Pochette invalide ou trop volumineuse")
    return octets


def image_locale(b64):
    """Image choisie par l'utilisateur (déjà recadrée en JPEG ou PNG par l'interface)."""
    try:
        octets = base64.b64decode(str(b64).split(",", 1)[-1], validate=True)
    except ValueError as e:
        raise ValueError("Image illisible") from e
    if len(octets) > 8_000_000 or not octets.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        raise ValueError("Image JPEG ou PNG de 8 Mo maximum attendue")
    return octets


def _ecrire(fichier, valeurs, image):
    f = mutagen.File(fichier)
    if f is None:
        raise ValueError("Format sans prise en charge des tags")
    if f.tags is None:
        f.add_tags()
    if hasattr(f.tags, "getall"):  # MP3, WAV, AIFF : ID3
        frames = {"titre": TIT2, "artiste": TPE1, "album": TALB, "artiste_album": TPE2,
                  "annee": TDRC, "genre": TCON, "numero": TRCK}
        for c, cls in frames.items():
            f.tags.delall(cls.__name__)
            if valeurs[c]:
                f.tags.add(cls(encoding=3, text=str(valeurs[c])))
        if image:
            f.tags.delall("APIC")
            f.tags.add(APIC(encoding=3, mime="image/png" if image.startswith(b"\x89PNG") else "image/jpeg", type=3, data=image))
    elif isinstance(f, MP4):
        cles = {"titre": "\xa9nam", "artiste": "\xa9ART", "album": "\xa9alb", "artiste_album": "aART", "annee": "\xa9day", "genre": "\xa9gen"}
        for c, cle in cles.items():
            if cle in f.tags:
                del f.tags[cle]
            if valeurs[c]:
                f.tags[cle] = [str(valeurs[c])]
        f.tags.pop("trkn", None)
        if valeurs["numero"]:
            f.tags["trkn"] = [(valeurs["numero"], 0)]
        if image:
            f.tags["covr"] = [MP4Cover(image, imageformat=MP4Cover.FORMAT_PNG if image.startswith(b"\x89PNG") else MP4Cover.FORMAT_JPEG)]
    elif isinstance(f, FLAC) or fichier.suffix.lower() in {".ogg", ".oga", ".opus"}:
        for c, cle in CHAMPS.items():
            if cle in f.tags:
                del f.tags[cle]
            if valeurs[c]:
                f.tags[cle] = [str(valeurs[c])]
        if image:
            pic = Picture()
            pic.type, pic.mime, pic.data = 3, "image/png" if image.startswith(b"\x89PNG") else "image/jpeg", image
            if isinstance(f, FLAC):
                f.clear_pictures()
                f.add_picture(pic)
            else:
                f.tags["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
    else:
        raise ValueError("Écriture des tags non prise en charge pour ce format")
    f.save()


def modifier(pid, d):
    image = None
    # L'image et les infos proviennent d'un lookup vérifié, jamais d'une URL fournie par le client.
    if d.get("itunes"):
        rs = _itunes(("lookup", urlencode({"id": int(d["itunes"]), "country": "FR"})))
        r = next((r for r in rs if r.get("trackId") == int(d["itunes"])), None)
        if not r:
            raise ValueError("Résultat iTunes introuvable")
        d = _resultat(r)
        d["artiste_album"] = r.get("collectionArtistName") or r.get("artistName", "")
        if d["image"]:
            image = _pochette(re.sub(r"/100x100bb\.(jpg|png)$", r"/600x600bb.\1", d["image"]))
    elif d.get("pochette_b64"):
        image = image_locale(d["pochette_b64"])
    with bib._verrou:
        p = bib.piste(pid)
        if not p:
            raise ValueError("Titre introuvable")
        valeurs = {c: d.get(c, p.get(c)) for c in CHAMPS}
        for c in CHAMPS:
            if c != "numero":
                valeurs[c] = str(valeurs[c] or "").strip()
                if len(valeurs[c]) > 500:
                    raise ValueError("Champ trop long")
        if not valeurs["titre"] or not valeurs["artiste"]:
            raise ValueError("Titre et artiste obligatoires")
        if valeurs["annee"] and (len(valeurs["annee"]) != 4 or not valeurs["annee"].isdigit()):
            raise ValueError("L'année doit contenir quatre chiffres")
        valeurs["numero"] = int(valeurs["numero"]) if valeurs["numero"] not in (None, "") else None
        if valeurs["numero"] is not None and not 1 <= valeurs["numero"] <= 9999:
            raise ValueError("Numéro de piste invalide")
        original = Path(p["chemin"]).resolve()
        fd, nom = tempfile.mkstemp(prefix=".onde-tags-", suffix=original.suffix, dir=original.parent)
        os.close(fd)
        tmp = Path(nom)
        try:
            shutil.copy2(original, tmp)
            _ecrire(tmp, valeurs, image)
            # Vérifier les tags avant de remplacer le fichier original.
            info = bib.lire_fichier(tmp, config.lire_reglages())
            if not info["tags"]:
                raise ValueError("Les tags écrits ne peuvent pas être relus")
            tmp.replace(original)
            st = original.stat()
            bib.ecrire("UPDATE pistes SET titre=?, artiste=?, album=?, artiste_album=?, annee=?, genre=?, numero=?, pochette=?, tags=1, mtime=?, taille=? WHERE id=?",
                       (*(valeurs[c] for c in CHAMPS), info["pochette"], st.st_mtime, st.st_size, pid))
        finally:
            tmp.unlink(missing_ok=True)
        return bib.piste(pid)
