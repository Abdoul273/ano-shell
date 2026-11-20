"""Bibliothèque musicale : scan des dossiers, tags, pochettes, base SQLite."""
import hashlib
import os
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote_plus

import mutagen

from . import config

EXTENSIONS = {".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav", ".webm"}
NOMS_POCHETTE = ("cover", "folder", "front", "album", "pochette")

_verrou = threading.RLock()
_db = sqlite3.connect(config.BASE, check_same_thread=False)
_db.row_factory = sqlite3.Row
_db.executescript("""
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -8000;
CREATE TABLE IF NOT EXISTS pistes (
  id INTEGER PRIMARY KEY, chemin TEXT UNIQUE NOT NULL, titre TEXT, artiste TEXT, album TEXT,
  artiste_album TEXT, duree REAL, annee TEXT, genre TEXT, numero INTEGER, format TEXT, debit INTEGER,
  taille INTEGER, mtime REAL, ajoute REAL, pochette TEXT, tags INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS favoris (piste_id INTEGER PRIMARY KEY, date REAL);
CREATE TABLE IF NOT EXISTS ecoutes (piste_id INTEGER, date REAL);
CREATE INDEX IF NOT EXISTS ecoutes_date ON ecoutes(date);
CREATE INDEX IF NOT EXISTS ecoutes_piste ON ecoutes(piste_id);
CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, nom TEXT, description TEXT, cree REAL, modifie REAL);
CREATE TABLE IF NOT EXISTS playlist_pistes (playlist_id INTEGER, piste_id INTEGER, position INTEGER);
CREATE INDEX IF NOT EXISTS playlist_pistes_pl ON playlist_pistes(playlist_id, position);
CREATE TABLE IF NOT EXISTS radios (id INTEGER PRIMARY KEY, nom TEXT, url TEXT UNIQUE, logo TEXT, pays TEXT, tags TEXT);
""")
for colonne in ("externe INTEGER DEFAULT 0",  # titres ouverts depuis l'explorateur, hors bibliothèque
                "frequence INTEGER", "bits INTEGER", "canaux INTEGER"):  # qualité audio (badge, propriétés)
    try:
        _db.execute(f"ALTER TABLE pistes ADD COLUMN {colonne}")
    except sqlite3.OperationalError:
        pass
_db.commit()

ETAT_SCAN = {"en_cours": False, "fait": 0, "total": 0, "ajoutees": 0, "supprimees": 0, "fin": None}
REV = {"n": 0}  # change à chaque modification de la bibliothèque


_cache_instantane = {"cle": None, "donnees": None}


def _toucher():
    REV["n"] += 1
    _cache_instantane["cle"] = None


def requete(sql, params=(), un=False):
    with _verrou:
        cur = _db.execute(sql, params)
        return cur.fetchone() if un else cur.fetchall()


def ecrire(sql, params=()):
    with _verrou:
        cur = _db.execute(sql, params)
        _db.commit()
        _toucher()
        return cur


# ── titres reconstruits depuis le nom de fichier ─────────────────────
PARASITES = re.compile(
    r"\((?:\d{3,4}p|\d{2,3}k|\d)\)|\[(?:\d{3,4}p|\d{2,3}k)\]"
    r"|[\(\[](?:clip|video|vid[ée]o|audio|lyrics?|paroles|visuali[sz]er|official|officiel|music video|hd|hq|4k)[^\)\]]*[\)\]]"
    r"|\b(?:clip|vid[ée]o)\s+officiel(?:le)?\b|\bofficial\s+(?:music\s+)?video\b|\bmusic\s+video\b|\baudio\s+visuali[sz]er\b"
    r"|\s-\s*copie\b|\bcopie\b(?=\s*$)",
    re.I,
)


_EXT_RE = re.compile(r"\.(mp3|m4a|mp4|webm|opus)$", re.IGNORECASE)
_MC_RE = re.compile(r"\s*-\s*mc\s*$", re.IGNORECASE)
_DRAPEAUX_RE = re.compile(r"[🇦-🇿]{2}")
_PARENS_VIDES_RE = re.compile(r"[\(\[]\s*[\)\]]")
_SITE_NOM_RE = re.compile(r"(?:^|[\s-])(?:www\.)?[\w-]+\.(?:com|net|org|fr|info|biz|io)\b", re.IGNORECASE)
_SITE_TXT_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+\.(?:com|net|org|fr|info|biz|io)\b(?:/[^\s]*)?", re.IGNORECASE)
_ESPACES_RE = re.compile(r"\s+")
_NUM_PISTE_RE = re.compile(r"^\d{1,3}\s*[-.)]\s*")
_SEP_LARGE_RE = re.compile(r"^(.+?)\s+[-–—]\s+(.+)$")
_SEP_COURT_RE = re.compile(r"^([^-]{2,30}?)\s*-\s*([^-]{2,})$")
_VEVO_FIN_RE = re.compile(r"VEVO$", re.IGNORECASE)
_VEVO_OFF_RE = re.compile(r"(?:VEVO|\s+Official)$", re.IGNORECASE)
_CAMEL_RE = re.compile(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Ý])")
_NON_MOT_RE = re.compile(r"[^\w]+")


def nettoyer_nom(nom):
    """« Alonzo_-_Assurance_vie(360p) » → (« Alonzo », « Assurance vie »)."""
    s = unquote_plus(nom) if "%" in nom or "+" in nom else nom
    s = _EXT_RE.sub("", s)
    s = s.replace("_", " ")
    s = PARASITES.sub(" ", s)
    s = _MC_RE.sub("", s)
    s = _DRAPEAUX_RE.sub(" ", s)          # drapeaux
    s = _PARENS_VIDES_RE.sub(" ", s)      # parenthèses vidées
    s = _SITE_NOM_RE.sub(" ", s)          # sites
    s = _ESPACES_RE.sub(" ", s).strip(" .-–—|")
    s = _NUM_PISTE_RE.sub("", s)          # « 06 - », « 04- », « 12) »
    artiste, titre = None, s
    m = _SEP_LARGE_RE.match(s) or _SEP_COURT_RE.match(s)
    if m:
        artiste, titre = m.group(1).strip(), m.group(2).strip()
    titre = _ESPACES_RE.sub(" ", titre).strip(" .-–—|") or nom
    if artiste and artiste.isupper() and len(artiste) > 3:
        artiste = artiste.title()
    if titre.isupper() and len(titre) > 4:
        titre = titre.capitalize()
    return artiste, titre


def nettoyer_texte(s, artiste=False):
    """Retire les sites et les séparateurs de rips, sans couper les noms composés isolés."""
    if not s:
        return ""
    s = _SITE_TXT_RE.sub(" ", s)
    if "_" in s:
        s = s.replace("_", " ")
    if s.count("-") >= 2 and " - " not in s:
        s = s.replace("-", " ")
    if artiste:
        vevo = bool(_VEVO_FIN_RE.search(s))
        s = _VEVO_OFF_RE.sub("", s)
        if vevo:
            s = _CAMEL_RE.sub(" ", s)
    return _ESPACES_RE.sub(" ", s).strip(" .-–—|")


def cle_nom(s):
    return _NON_MOT_RE.sub(" ", "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()).strip()


# ── lecture des tags ─────────────────────────────────────────────────
VIDES = {"<unknown>", "unknown", "unknown artist", "artiste inconnu", "various", "n/a", "-", "untitled"}


def _premier(tags, *cles):
    for c in cles:
        v = tags.get(c) if tags else None
        if v:
            v = v[0] if isinstance(v, list) else v
            v = str(v).strip()
            if v and v.lower() not in VIDES:
                return v
    return None


def _image_integree(f):
    """Octets de la pochette intégrée (ID3 APIC, MP4 covr, FLAC/Vorbis)."""
    try:
        tags = f.tags
        if tags is None:
            return None
        if hasattr(tags, "getall"):  # ID3
            apics = tags.getall("APIC")
            if apics:
                return max(apics, key=lambda a: (a.type == 3, len(a.data))).data
        if "covr" in tags:
            return bytes(tags["covr"][0])
        if getattr(f, "pictures", None):
            return f.pictures[0].data
        if "metadata_block_picture" in tags:
            import base64

            from mutagen.flac import Picture
            return Picture(base64.b64decode(tags["metadata_block_picture"][0])).data
    except Exception:
        return None
    return None


def _sauver_pochette(octets):
    h = hashlib.sha1(octets).hexdigest()[:20]
    ext = ".png" if octets[:4] == b"\x89PNG" else ".jpg"
    f = config.POCHETTES / f"{h}{ext}"
    if not f.exists():
        f.write_bytes(octets)
    return f.name


def _pochette_dossier(dossier, cache={}):
    if dossier in cache:
        return cache[dossier]
    trouvee = None
    try:
        for f in Path(dossier).iterdir():
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and f.stem.lower() in NOMS_POCHETTE:
                trouvee = _sauver_pochette(f.read_bytes())
                break
    except OSError:
        pass
    cache[dossier] = trouvee
    return trouvee


def qualite(f):
    """Fréquence, résolution et canaux lus dans l'en-tête (None si inconnus)."""
    i = getattr(f, "info", None)
    bits = getattr(i, "bits_per_sample", None) or getattr(i, "bits_per_raw_sample", None)
    return {"frequence": getattr(i, "sample_rate", None) or None, "bits": bits or None, "canaux": getattr(i, "channels", None) or None}


def _noter_qualite(chemin, info):
    _db.execute("UPDATE pistes SET frequence=?, bits=?, canaux=? WHERE chemin=?",
                (info.get("frequence"), info.get("bits"), info.get("canaux"), chemin))


def completer_qualite():
    """Une fois : lit la qualité des titres déjà indexés avant l'ajout de ces colonnes."""
    def tache():
        manquants = requete("SELECT id, chemin FROM pistes WHERE frequence IS NULL")
        for n, r in enumerate(manquants, 1):
            try:
                q = qualite(mutagen.File(r["chemin"]))
            except Exception:
                q = {}
            with _verrou:  # 0 = lu mais inconnu, pour ne pas relire à chaque démarrage
                _db.execute("UPDATE pistes SET frequence=?, bits=?, canaux=? WHERE id=?",
                            (q.get("frequence") or 0, q.get("bits"), q.get("canaux"), r["id"]))
                if n % 100 == 0:
                    _db.commit()
        with _verrou:
            _db.commit()
        if manquants:
            _toucher()
    threading.Thread(target=tache, daemon=True, name="qualite").start()


def lire_fichier(chemin, reglages):
    p = Path(chemin)
    info = {"chemin": str(p), "format": p.suffix[1:].lower(), "taille": p.stat().st_size, "mtime": p.stat().st_mtime}
    titre = artiste = album = artiste_album = annee = genre = None
    numero, duree, debit, pochette = None, None, None, None
    info.update(qualite(None))
    try:
        f = mutagen.File(p)
        if f is not None:
            duree = getattr(f.info, "length", None)
            debit = getattr(f.info, "bitrate", None)
            info.update(qualite(f))
            pochette_octets = _image_integree(f)
            if pochette_octets:
                pochette = _sauver_pochette(pochette_octets)
        fe = mutagen.File(p, easy=True)
        tags = fe.tags if fe is not None else None
        if tags and hasattr(tags, "getall"):
            tags = {cle: [str(tags[frame])] for cle, frame in {
                "title": "TIT2", "artist": "TPE1", "album": "TALB", "albumartist": "TPE2",
                "date": "TDRC", "genre": "TCON", "tracknumber": "TRCK"}.items() if frame in tags}
        if tags:
            titre = _premier(tags, "title")
            artiste = _premier(tags, "artist")
            album = _premier(tags, "album")
            artiste_album = _premier(tags, "albumartist")
            annee = (_premier(tags, "date", "year") or "")[:4] or None
            genre = _premier(tags, "genre")
            n = _premier(tags, "tracknumber")
            numero = int(re.match(r"\d+", n).group()) if n and re.match(r"\d+", n) else None
    except Exception:
        pass
    a_des_tags = bool(titre and artiste)
    if reglages.get("titres_fichier", True):
        if not titre:
            artiste_f, titre = nettoyer_nom(p.stem)
            artiste = artiste or artiste_f
        elif not artiste:
            # tag « titre » qui est en réalité un nom de fichier (« Booba - Comme Une Etoile », « X_-_Y(360p) »)
            artiste_f, titre_f = nettoyer_nom(titre)
            if artiste_f:
                artiste, titre = artiste_f, titre_f
            elif titre_f:
                titre = titre_f
            if not artiste:
                artiste = nettoyer_nom(p.stem)[0]
    titre = nettoyer_texte(titre) if titre else titre
    artiste = nettoyer_texte(artiste, artiste=True) if artiste else artiste
    album = nettoyer_texte(album)
    artiste_album = nettoyer_texte(artiste_album, artiste=True) if artiste_album else None
    info.update(
        titre=titre or p.stem, artiste=artiste or "Artiste inconnu", album=album or "", artiste_album=artiste_album,
        annee=annee, genre=genre, numero=numero, duree=duree, debit=int(debit / 1000) if debit else None,
        pochette=pochette or _pochette_dossier(str(p.parent)), tags=int(a_des_tags),
    )
    return info


# ── scan ─────────────────────────────────────────────────────────────
def _fichiers(dossiers):
    for d in dossiers:
        for racine, sous, noms in os.walk(Path(d).expanduser()):
            sous[:] = [s for s in sous if not s.startswith(".")]
            for n in noms:
                if Path(n).suffix.lower() in EXTENSIONS and not n.startswith("."):
                    yield os.path.join(racine, n)


def scanner(complet=False):
    if ETAT_SCAN["en_cours"]:
        return False
    threading.Thread(target=_scanner, args=(complet,), daemon=True, name="scan").start()
    return True


def _scanner(complet):
    reglages = config.lire_reglages()
    ETAT_SCAN.update(en_cours=True, fait=0, total=0, ajoutees=0, supprimees=0)
    try:
        fichiers = list(_fichiers(reglages["dossiers"]))
        ETAT_SCAN["total"] = len(fichiers)
        lignes = requete("SELECT chemin, mtime, externe FROM pistes")
        connus = {r["chemin"]: r["mtime"] for r in lignes}
        externes = {r["chemin"] for r in lignes if r["externe"]}
        presents = set(fichiers)
        maintenant = time.time()
        for i, chemin in enumerate(fichiers, 1):
            ETAT_SCAN["fait"] = i
            try:
                mtime = os.stat(chemin).st_mtime
            except OSError:
                continue
            if not complet and chemin in connus and abs(connus[chemin] - mtime) < 1:
                continue
            with _verrou:
                info = lire_fichier(chemin, reglages)
                if chemin in connus:
                    _db.execute(
                        "UPDATE pistes SET titre=?, artiste=?, album=?, artiste_album=?, duree=?, annee=?, genre=?, numero=?, "
                        "format=?, debit=?, taille=?, mtime=?, pochette=?, tags=? WHERE chemin=?",
                        (info["titre"], info["artiste"], info["album"], info["artiste_album"], info["duree"], info["annee"],
                         info["genre"], info["numero"], info["format"], info["debit"], info["taille"], info["mtime"],
                         info["pochette"], info["tags"], chemin))
                else:
                    _db.execute(
                        "INSERT INTO pistes (chemin, titre, artiste, album, artiste_album, duree, annee, genre, numero, "
                        "format, debit, taille, mtime, ajoute, pochette, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (chemin, info["titre"], info["artiste"], info["album"], info["artiste_album"], info["duree"],
                         info["annee"], info["genre"], info["numero"], info["format"], info["debit"], info["taille"],
                         info["mtime"], maintenant, info["pochette"], info["tags"]))
                    ETAT_SCAN["ajoutees"] += 1
                _noter_qualite(chemin, info)
            if i % 50 == 0:
                with _verrou:
                    _db.commit()
                _toucher()
        disparus = [c for c in connus if c not in presents and not (c in externes and os.path.exists(c))]
        with _verrou:
            for c in disparus:
                _db.execute("DELETE FROM pistes WHERE chemin=?", (c,))
            _db.execute("UPDATE pistes SET fusion_vers=NULL WHERE fusion_vers NOT IN (SELECT id FROM pistes)")
            _db.execute("DELETE FROM favoris WHERE piste_id NOT IN (SELECT id FROM pistes)")
            _db.execute("DELETE FROM playlist_pistes WHERE piste_id NOT IN (SELECT id FROM pistes)")
            _db.commit()
        ETAT_SCAN["supprimees"] = len(disparus)
    finally:
        ETAT_SCAN.update(en_cours=False, fin=time.time())
        _toucher()


def importer(chemins):
    """Ids des fichiers donnés (ouverts avec Onde) ; ceux hors bibliothèque sont ajoutés comme « externes »."""
    reglages = config.lire_reglages()
    racines = [str(Path(d).expanduser().resolve()) for d in reglages["dossiers"]]
    ids = []
    for c in chemins:
        try:
            chemin = str(Path(c).expanduser().resolve())
        except (OSError, RuntimeError):
            continue
        if Path(chemin).suffix.lower() not in EXTENSIONS or not os.path.isfile(chemin):
            continue
        r = requete("SELECT id FROM pistes WHERE chemin=?", (chemin,), un=True)
        if r:
            cible = requete("SELECT fusion_vers FROM pistes WHERE id=?", (r["id"],), un=True)
            ids.append(cible["fusion_vers"] or r["id"])
            continue
        info = lire_fichier(chemin, reglages)
        externe = int(not any(chemin.startswith(x + os.sep) for x in racines))
        cur = ecrire(
            "INSERT INTO pistes (chemin, titre, artiste, album, artiste_album, duree, annee, genre, numero, format, debit, "
            "taille, mtime, ajoute, pochette, tags, externe) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (chemin, info["titre"], info["artiste"], info["album"], info["artiste_album"], info["duree"], info["annee"],
             info["genre"], info["numero"], info["format"], info["debit"], info["taille"], info["mtime"], time.time(),
             info["pochette"], info["tags"], externe))
        with _verrou:
            _noter_qualite(chemin, info)
            _db.commit()
        ids.append(cur.lastrowid)
    return ids


# ── lecture de la bibliothèque ──────────────────────────────────────
CHAMPS = ("id", "titre", "artiste", "album", "artiste_album", "duree", "annee", "genre", "numero", "format",
          "debit", "taille", "ajoute", "pochette", "tags", "chemin", "frequence", "bits", "canaux")


def instantane():
    racines = tuple(str(Path(d).expanduser()) for d in config.lire_reglages()["dossiers"])
    with _verrou:
        rev = REV["n"]
        cle = (rev, racines)
        if _cache_instantane["cle"] == cle and _cache_instantane["donnees"] is not None:
            return _cache_instantane["donnees"]
        pistes = [dict(r) for r in requete(f"SELECT {', '.join(CHAMPS)} FROM pistes WHERE fusion_vers IS NULL ORDER BY artiste COLLATE NOCASE, titre COLLATE NOCASE")]
        for p in pistes:
            chemin = p.pop("chemin")
            dossier = os.path.dirname(chemin)
            for r in racines:
                if dossier == r or dossier.startswith(r + os.sep):
                    dossier = os.path.relpath(dossier, os.path.dirname(r))
                    break
            p["dossier"] = dossier
            p["fichier"] = os.path.basename(chemin)
        ecoutes = {r["piste_id"]: (r["n"], r["der"]) for r in requete(
            "SELECT piste_id, COUNT(*) n, MAX(date) der FROM ecoutes GROUP BY piste_id")}
        for p in pistes:
            n, der = ecoutes.get(p["id"], (0, None))
            p["ecoutes"], p["derniere"] = n, der
        res = {
            "pistes": pistes,
            "favoris": [r["piste_id"] for r in requete("SELECT piste_id FROM favoris ORDER BY date DESC")],
            "playlists": playlists(),
            "rev": rev,
            "fusions": {str(r["id"]): r["fusion_vers"] for r in requete("SELECT id, fusion_vers FROM pistes WHERE fusion_vers IS NOT NULL")},
        }
        _cache_instantane.update(cle=cle, donnees=res)
        return res


def chemin_piste(piste_id):
    r = requete("SELECT chemin FROM pistes WHERE id=?", (piste_id,), un=True)
    return r["chemin"] if r else None


def piste(piste_id):
    r = requete(f"SELECT {', '.join(CHAMPS)} FROM pistes WHERE id=?", (piste_id,), un=True)
    return dict(r) if r else None


# ── favoris, écoutes, statistiques ───────────────────────────────────
def basculer_favori(piste_id):
    if requete("SELECT 1 FROM favoris WHERE piste_id=?", (piste_id,), un=True):
        ecrire("DELETE FROM favoris WHERE piste_id=?", (piste_id,))
        return False
    ecrire("INSERT INTO favoris VALUES (?, ?)", (piste_id, time.time()))
    return True


def noter_ecoute(piste_id):
    with _verrou:
        _db.execute("INSERT INTO ecoutes VALUES (?, ?)", (piste_id, time.time()))
        _db.commit()
        _cache_instantane["cle"] = None


def statistiques():
    depuis = time.time() - 30 * 86400
    total = requete("SELECT COUNT(*) n, COALESCE(SUM(p.duree), 0) s FROM ecoutes e JOIN pistes p ON p.id = e.piste_id", un=True)
    mois = requete("SELECT COUNT(*) n, COALESCE(SUM(p.duree), 0) s FROM ecoutes e JOIN pistes p ON p.id = e.piste_id WHERE e.date > ?",
                   (depuis,), un=True)
    top_titres = requete("SELECT piste_id id, COUNT(*) n FROM ecoutes GROUP BY piste_id ORDER BY n DESC LIMIT 10")
    top_artistes = requete("SELECT p.artiste artiste, COUNT(*) n, COALESCE(SUM(p.duree), 0) s FROM ecoutes e JOIN pistes p ON p.id = e.piste_id "
                           "GROUP BY p.artiste ORDER BY n DESC LIMIT 10")
    return {
        "ecoutes": total["n"], "temps": total["s"], "ecoutes_mois": mois["n"], "temps_mois": mois["s"],
        "top_titres": [dict(r) for r in top_titres], "top_artistes": [dict(r) for r in top_artistes],
    }


# ── playlists ────────────────────────────────────────────────────────
def playlists():
    par_pl = {}
    for x in requete("SELECT playlist_id, piste_id FROM playlist_pistes ORDER BY playlist_id, position"):
        par_pl.setdefault(x["playlist_id"], []).append(x["piste_id"])
    return [{**dict(r), "pistes": par_pl.get(r["id"], [])} for r in requete("SELECT * FROM playlists ORDER BY modifie DESC")]


def creer_playlist(nom, ids=()):
    t = time.time()
    cur = ecrire("INSERT INTO playlists (nom, description, cree, modifie) VALUES (?, '', ?, ?)", (nom.strip() or "Nouvelle playlist", t, t))
    if ids:
        ajouter_a_playlist(cur.lastrowid, ids)
    return cur.lastrowid


def modifier_playlist(pid, nom=None, description=None):
    if nom is not None:
        ecrire("UPDATE playlists SET nom=?, modifie=? WHERE id=?", (nom.strip() or "Sans nom", time.time(), pid))
    if description is not None:
        ecrire("UPDATE playlists SET description=?, modifie=? WHERE id=?", (description, time.time(), pid))


def supprimer_playlist(pid):
    ecrire("DELETE FROM playlist_pistes WHERE playlist_id=?", (pid,))
    ecrire("DELETE FROM playlists WHERE id=?", (pid,))


def ajouter_a_playlist(pid, ids):
    with _verrou:
        n = _db.execute("SELECT COALESCE(MAX(position), -1) FROM playlist_pistes WHERE playlist_id=?", (pid,)).fetchone()[0]
        deja = {r[0] for r in _db.execute("SELECT piste_id FROM playlist_pistes WHERE playlist_id=?", (pid,))}
        ajoutes = 0
        for i in ids:
            if i in deja:
                continue
            n += 1
            ajoutes += 1
            _db.execute("INSERT INTO playlist_pistes VALUES (?, ?, ?)", (pid, i, n))
        _db.execute("UPDATE playlists SET modifie=? WHERE id=?", (time.time(), pid))
        _db.commit()
    _toucher()
    return ajoutes


def ordonner_playlist(pid, ids):
    with _verrou:
        _db.execute("DELETE FROM playlist_pistes WHERE playlist_id=?", (pid,))
        _db.executemany("INSERT INTO playlist_pistes VALUES (?, ?, ?)", [(pid, i, n) for n, i in enumerate(ids)])
        _db.execute("UPDATE playlists SET modifie=? WHERE id=?", (time.time(), pid))
        _db.commit()
    _toucher()


# ── radios favorites ─────────────────────────────────────────────────
def radios():
    return [dict(r) for r in requete("SELECT * FROM radios ORDER BY nom COLLATE NOCASE")]


def ajouter_radio(r):
    ecrire("INSERT OR IGNORE INTO radios (nom, url, logo, pays, tags) VALUES (?, ?, ?, ?, ?)",
           (r.get("nom"), r.get("url"), r.get("logo"), r.get("pays"), r.get("tags")))


def supprimer_radio(url):
    ecrire("DELETE FROM radios WHERE url=?", (url,))


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


# Les copies fusionnées restent indexées afin qu'un prochain scan ne les réimporte pas.
try:
    _db.execute("ALTER TABLE pistes ADD COLUMN fusion_vers INTEGER")
except sqlite3.OperationalError:
    pass
_db.execute("CREATE INDEX IF NOT EXISTS pistes_fusion ON pistes(fusion_vers)")
_db.commit()


def nettoyer_bibliotheque():
    n = 0
    with _verrou:
        for r in requete("SELECT id, titre, artiste, album, artiste_album FROM pistes"):
            valeurs = (nettoyer_texte(r["titre"]), nettoyer_texte(r["artiste"], True),
                       nettoyer_texte(r["album"]), nettoyer_texte(r["artiste_album"], True) or None)
            if valeurs != (r["titre"], r["artiste"], r["album"], r["artiste_album"]):
                _db.execute("UPDATE pistes SET titre=?, artiste=?, album=?, artiste_album=? WHERE id=?", (*valeurs, r["id"]))
                n += 1
        if n:
            _db.commit()
            _toucher()
    return n


def doublons():
    groupes = {}
    for r in requete("SELECT * FROM pistes WHERE fusion_vers IS NULL"):
        p = dict(r)
        if not p["duree"] or p["artiste"].lower() in VIDES:
            continue
        cle = (cle_nom(p["artiste"]).replace(" ", ""), cle_nom(p["titre"]))
        groupes.setdefault(cle, []).append(p)
    res = []
    for ps in groupes.values():
        ps.sort(key=lambda p: p["duree"])
        paquets = []
        for p in ps:
            if not paquets or p["duree"] - paquets[-1][0]["duree"] > 2:
                paquets.append([])
            paquets[-1].append(p)
        for paquet in paquets:
            if len(paquet) > 1:
                paquet.sort(key=lambda p: (p["format"] in {"flac", "wav"}, p["debit"] or 0, p["taille"] or 0), reverse=True)
                res.append([{c: p[c] for c in ("id", "titre", "artiste", "album", "duree", "format", "debit", "chemin")} for p in paquet])
    return res


def fusionner(garder, ids):
    ids = set(ids) | {garder}
    if len(ids) < 2 or not any(ids <= {p["id"] for p in g} for g in doublons()):
        raise ValueError("Ces titres ne sont pas des doublons de même artiste, titre et durée")
    with _verrou, _db:
        for pid in ids - {garder}:
            _db.execute("INSERT OR IGNORE INTO favoris SELECT ?, date FROM favoris WHERE piste_id=?", (garder, pid))
            _db.execute("DELETE FROM favoris WHERE piste_id=?", (pid,))
            _db.execute("UPDATE ecoutes SET piste_id=? WHERE piste_id=?", (garder, pid))
            for r in _db.execute("SELECT DISTINCT playlist_id FROM playlist_pistes WHERE piste_id=?", (pid,)).fetchall():
                pl = r[0]
                position = _db.execute("SELECT MIN(position) FROM playlist_pistes WHERE playlist_id=? AND piste_id IN (?,?)", (pl, garder, pid)).fetchone()[0]
                _db.execute("DELETE FROM playlist_pistes WHERE playlist_id=? AND piste_id IN (?,?)", (pl, garder, pid))
                _db.execute("INSERT INTO playlist_pistes VALUES (?,?,?)", (pl, garder, position))
                _db.execute("UPDATE playlists SET modifie=? WHERE id=?", (time.time(), pl))
            _db.execute("UPDATE pistes SET fusion_vers=? WHERE id=? OR fusion_vers=?", (garder, pid, pid))
    _toucher()
    return {str(i): garder for i in ids - {garder}}


nettoyer_bibliotheque()
