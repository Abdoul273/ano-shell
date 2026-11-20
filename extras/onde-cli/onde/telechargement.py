"""Téléchargement de musique (même système qu'Aura) : recherche YouTube via yt-dlp, audio m4a en
qualité maximale, tags propres (métadonnées musicales de YouTube en priorité), pochette carrée et
paroles synchronisées écrites à côté (.lrc) pour qu'elles s'affichent dès la première écoute.
Robuste : cookies, reprises, attente croissante sur « 429 », fragments parallèles, annulation."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import bibliotheque as bib, config, paroles

MAX_PARALLELE = 2  # au-delà, YouTube répond vite « 429 »
MAX_ESSAIS = 4
SOUS_DOSSIER = "Téléchargements Onde"
TRAVAIL = config.DONNEES / "telechargements"
COOKIES = config.CONFIG / "cookies.txt"

TACHES = []                 # plus récentes d'abord (lues par l'interface)
_verrou = threading.Lock()
_places = threading.Semaphore(MAX_PARALLELE)
_pids, _annules, _sondes = {}, set(), {}


def _ytdlp():
    # lancé depuis le menu, ~/.local/bin n'est pas toujours dans le PATH
    local = Path.home() / ".local/bin/yt-dlp"
    return str(local) if local.exists() else shutil.which("yt-dlp") or "yt-dlp"


def _base():
    cmd = [_ytdlp(), "--no-warnings", "--color", "never", "--socket-timeout", "30", "--extractor-retries", "5"]
    if COOKIES.exists() and COOKIES.stat().st_size > 100:  # vidéos à limite d'âge, « pas un robot »
        cmd += ["--cookies", str(COOKIES)]
    return cmd


def _message(stderr):
    """Dernière erreur utile de yt-dlp, en clair."""
    bas = stderr.lower()
    if "429" in bas or "too many requests" in bas:
        return "YouTube limite les requêtes (429)"
    if "sign in to confirm" in bas or "not a bot" in bas:
        return f"YouTube demande une connexion : place un cookies.txt dans {config.CONFIG}"
    if "video unavailable" in bas or "private video" in bas:
        return "Vidéo indisponible"
    if "ffmpeg" in bas and "not found" in bas:
        return "ffmpeg est requis pour extraire l'audio"
    lignes = [l for l in stderr.splitlines() if l.strip()]
    utile = next((l for l in reversed(lignes) if "ERROR" in l), lignes[-1] if lignes else "échec du téléchargement")
    return utile.replace("ERROR: ", "")[:220]


# ── artiste / titre déduits du titre de la vidéo ─────────────────────
BRUIT = re.compile(
    r"\s*[\(\[][^\)\]]*\b(official|officiel|clip|audio|lyrics?|paroles|video|vidéo|visuali[sz]er|hd|hq|4k|"
    r"music video|lyric video|prod\.?)\b[^\)\]]*[\)\]]|\s*\|.*$|\s+-\s+(clip|audio)\s+officiel.*$",
    re.I,
)


def _sans_arobase(s):
    # « @TiakolaOfficiel » → « Tiakola »
    return re.sub(r"@([\w.]+?)(?:Officiel|Official|Music|TV)?\b", r"\1", s)


def principal(artiste):
    """Artiste principal, pour chercher les paroles (« Gazo x Tiakola » → « Gazo »)."""
    return re.split(r"\s+(?:x|&|feat\.?|ft\.?|featuring|avec)\s+|,", artiste or "", maxsplit=1, flags=re.I)[0].strip()


def deviner(titre, chaine):
    t = _sans_arobase(BRUIT.sub("", titre)).strip(" -–—") or titre
    m = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return chaine.removesuffix(" - Topic").strip(), t


def _genre(titre, chaine):
    bas = f"{titre} {chaine}".lower()
    if chaine.endswith(" - Topic") or any(k in bas for k in ("(audio)", "official audio", "audio officiel", "[audio]", "lyrics", "paroles", "lyric video")):
        return "audio"
    if " live" in bas or "(live" in bas or "[live" in bas or "en direct" in bas:
        return "live"
    if any(k in bas for k in ("clip", "video", "vidéo", "visualizer")):
        return "clip"
    return "autre"


# ── recherche ───────────────────────────────────────────────────────
def chercher(q):
    q = q.strip()
    if not q:
        return []
    cible = q if re.match(r"https?://", q) else f"ytsearch20:{q}"
    try:
        r = subprocess.run(_base() + ["--flat-playlist", "--dump-json", "--playlist-end", "60", cible],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp introuvable. Installe-le : pipx install yt-dlp")
    except subprocess.TimeoutExpired:
        raise RuntimeError("YouTube ne répond pas (délai dépassé)")
    res = []
    for ligne in r.stdout.splitlines():
        try:
            v = json.loads(ligne)
        except ValueError:
            continue
        if not v.get("id") or not v.get("title"):
            continue
        if v.get("_type") == "url" and v.get("ie_key") not in (None, "Youtube"):
            continue  # chaînes et playlists : on ne garde que les vidéos
        chaine = v.get("channel") or v.get("uploader") or ""
        artiste, titre = deviner(v["title"], chaine)
        url = next((u for u in (v.get("webpage_url"), v.get("url")) if u and u.startswith("http")), f"https://www.youtube.com/watch?v={v['id']}")
        res.append({
            "id": v["id"], "url": url, "titre_video": v["title"], "chaine": chaine.removesuffix(" - Topic"),
            "duree": v.get("duration") or 0, "vues": v.get("view_count") or 0,
            "verifiee": v.get("channel_is_verified") is True,
            "vignette": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg",
            "artiste": artiste, "titre": titre, "genre": _genre(v["title"], chaine),
        })
    if not res and r.returncode != 0:
        raise RuntimeError(_message(r.stderr))
    return res


# ── paroles disponibles (sondées pendant la recherche, réutilisées au téléchargement) ─
def _type_paroles(t):
    if not t:
        return "aucune"
    if t.get("instrumental"):
        return "instrumental"
    if t.get("syncedLyrics"):
        return "synchro"
    return "texte" if t.get("plainLyrics") else "aucune"


def _chercher_paroles(artiste, titre, album, duree):
    titre = re.sub(r"\s*[\(\[](?:feat|ft)\.?[^\)\]]*[\)\]]|\s+(?:feat|ft)\.?\s.*$", "", titre, flags=re.I).strip() or titre
    for a in dict.fromkeys(x for x in (artiste, principal(artiste)) if x):
        t = paroles._lrclib({"titre": titre, "artiste": a, "album": album, "duree": duree or None})
        if t:
            return t
    return None if artiste else paroles._lrclib({"titre": titre, "artiste": "Artiste inconnu", "album": "", "duree": duree or None})


def sonder(vid, artiste, titre, duree):
    cle = (vid, artiste, titre)
    if cle not in _sondes:
        _sondes[cle] = _chercher_paroles(artiste, titre, "", duree)
    return _type_paroles(_sondes[cle])


# ── tâches ──────────────────────────────────────────────────────────
def _maj(vid, **champs):
    with _verrou:
        for t in TACHES:
            if t["id"] == vid:
                t.update(champs)
                return t


def _annule(vid):
    return vid in _annules


def taches():
    with _verrou:
        return [dict(t) for t in TACHES]


def vider_terminees():
    with _verrou:
        TACHES[:] = [t for t in TACHES if t["etat"] not in ("fini", "erreur", "annule")]


def annuler(vid):
    _annules.add(vid)
    pid = _pids.get(vid)
    if pid:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    with _verrou:
        for t in TACHES:
            if t["id"] == vid and t["etat"] not in ("fini", "erreur"):
                t["etat"] = "annule"


def demarrer(r):
    vid = str(r.get("id") or "")
    if not re.fullmatch(r"[\w-]{6,20}", vid):
        raise ValueError("Identifiant de vidéo invalide")
    with _verrou:
        deja = next((t for t in TACHES if t["id"] == vid and t["etat"] not in ("erreur", "annule")), None)
        if deja:
            return dict(deja)
        TACHES[:] = [t for t in TACHES if t["id"] != vid]
        t = {"id": vid, "titre": r.get("titre") or r.get("titre_video") or vid, "artiste": r.get("artiste") or "",
             "vignette": r.get("vignette") or "", "etat": "attente", "pct": 0, "vitesse": "", "reste": "",
             "erreur": None, "paroles": None, "chemin": None}
        TACHES.insert(0, t)
    _annules.discard(vid)
    threading.Thread(target=_tache, args=(r,), daemon=True, name=f"dl-{vid}").start()
    return dict(t)


def _tache(r):
    vid = r["id"]
    with _places:  # file d'attente : MAX_PARALLELE à la fois
        try:
            if _annule(vid):
                raise InterruptedError
            _executer(r)
        except InterruptedError:
            _maj(vid, etat="annule")
        except Exception as e:  # noqa: BLE001 — affiché tel quel dans l'interface
            _maj(vid, etat="annule" if _annule(vid) else "erreur", erreur=str(e)[:300])
        finally:
            shutil.rmtree(TRAVAIL / vid, ignore_errors=True)


def _executer(r):
    vid = r["id"]
    tmp = TRAVAIL / vid
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    # 1. téléchargement (avec reprises)
    meta = _recuperer(r, tmp)
    audio = next((p for p in tmp.iterdir() if p.suffix.lower() in (".m4a", ".mp3", ".opus", ".ogg", ".webm", ".flac", ".aac", ".wav")), None)
    if not audio:
        raise RuntimeError("fichier audio introuvable après le téléchargement")

    # 2. tags : les métadonnées musicales de YouTube priment sur ce qu'on a déduit du titre
    _maj(vid, etat="tags", pct=100)
    artiste = _artistes(meta.get("artist")) or r.get("artiste") or ""
    titre = meta.get("track") or r.get("titre") or r.get("titre_video") or vid
    album = meta.get("album") or ""
    annee = meta.get("year") if len(meta.get("year", "")) == 4 else None
    import mutagen
    try:
        duree = mutagen.File(audio).info.length
    except Exception:
        duree = r.get("duree") or 0

    # 3. paroles (déjà sondées pendant la recherche si possible)
    _maj(vid, etat="paroles", artiste=artiste, titre=titre)
    cle = (vid, r.get("artiste"), r.get("titre"))
    trouve = _sondes.get(cle)
    # l'aperçu portait sur l'artiste/titre déduits : si YouTube en donne de meilleurs, on recherche à nouveau
    if cle not in _sondes or not ((trouve and trouve.get("syncedLyrics")) or (artiste, titre) == cle[1:]):
        trouve = _chercher_paroles(artiste, titre, album, duree)
    genre = _type_paroles(trouve)

    image = next((p for p in tmp.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")), None)
    pochette = _pochette_carree(image) if image else None
    _ecrire_tags(audio, titre, artiste, album or titre, annee, pochette, trouve)

    # 4. rangement dans la bibliothèque, .lrc à côté (lu en priorité par Onde)
    dossier = Path(config.lire_reglages()["dossiers"][0]).expanduser() / SOUS_DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    base = _nom(f"{artiste} - {titre}" if artiste else titre)
    dest = dossier / f"{base}{audio.suffix}"
    n = 2
    while dest.exists():
        dest = dossier / f"{base} ({n}){audio.suffix}"
        n += 1
    shutil.move(str(audio), dest)
    if trouve and trouve.get("syncedLyrics"):
        m, s = divmod(int(duree), 60)
        dest.with_suffix(".lrc").write_text(f"[ar:{artiste}]\n[ti:{titre}]\n[length:{m:02}:{s:02}]\n[re:Onde — lrclib]\n" + trouve["syncedLyrics"])
    _maj(vid, etat="fini", paroles=genre, chemin=str(dest), vitesse="", reste="")

    # 5. scan pour faire apparaître le titre (après un éventuel scan en cours)
    while not bib.scanner():
        time.sleep(0.3)


def _recuperer(r, tmp):
    attente, essai = 5, 0
    while True:
        essai += 1
        _maj(r["id"], etat="telechargement", erreur=None)
        ok, meta, stderr = _yt_dlp(r, tmp)
        if _annule(r["id"]):
            raise InterruptedError
        if ok:
            return meta
        bas = stderr.lower()
        limite = "429" in bas or "too many requests" in bas
        recuperable = limite or any(k in bas for k in ("timed out", "timeout", "connection", "temporary failure", "http error 5", "incompleteread", "unable to download", "network"))
        if not recuperable or essai >= MAX_ESSAIS:
            raise RuntimeError(_message(stderr))
        pause = max(attente, 20) if limite else attente
        _maj(r["id"], etat="reprise", erreur=f"{_message(stderr)} — nouvelle tentative dans {pause} s ({MAX_ESSAIS - essai} restante(s))")
        for _ in range(pause * 5):
            if _annule(r["id"]):
                raise InterruptedError
            time.sleep(0.2)
        attente = min(attente * 2, 60)


def _yt_dlp(r, tmp):
    """Un passage de yt-dlp : (succès, métadonnées, stderr)."""
    cmd = _base() + [
        "-f", "bestaudio[ext=m4a]/bestaudio/best",
        "-x", "--audio-format", "m4a", "--audio-quality", "0",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "--no-playlist", "--no-simulate", "--continue",
        "--progress", "--newline",
        "--progress-template", "download:ONDE_PROG:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "--print", "before_dl:ONDE_META:%(artist|)s\t%(track|)s\t%(album|)s\t%(release_year|)s",
        "--retries", "10", "--fragment-retries", "10", "--retry-sleep", "http:exp=2:60",
        "--file-access-retries", "5",
        "--concurrent-fragments", "4", "--http-chunk-size", "2M", "--throttled-rate", "100K",
        "-o", str(tmp / "%(id)s.%(ext)s"), r["url"],
    ]
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", bufsize=1)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp introuvable. Installe-le : pipx install yt-dlp")
    _pids[r["id"]] = p.pid
    meta, erreurs, dernier = {}, [], [0.0]

    def ligne(l):
        if "ONDE_PROG:" in l:
            pct, _, reste = l.split("ONDE_PROG:", 1)[1].partition("|")
            vitesse, _, eta = reste.partition("|")
            try:
                pct = max(0.0, min(100.0, float(pct.strip().rstrip("%"))))
            except ValueError:
                pct = 0.0
            if time.time() - dernier[0] >= 0.25 or pct >= 100:
                dernier[0] = time.time()
                propre = lambda s: "" if "Unknown" in s or s.strip() in ("NA", "") else s.strip()  # noqa: E731
                _maj(r["id"], pct=pct, vitesse=propre(vitesse), reste=propre(eta), **({"etat": "conversion"} if pct >= 100 else {}))
        elif "ONDE_META:" in l:
            champs = l.split("ONDE_META:", 1)[1].split("\t")
            for cle, v in zip(("artist", "track", "album", "year"), champs):
                v = v.strip()
                if v and v != "NA":
                    meta[cle] = v
        elif l.strip() and not l.startswith("[download]"):
            erreurs.append(l)

    def lire(flux):
        for brut in flux:
            for morceau in brut.split("\r"):
                ligne(morceau.rstrip())

    t = threading.Thread(target=lire, args=(p.stderr,), daemon=True)
    t.start()
    lire(p.stdout)
    t.join()
    code = p.wait()
    _pids.pop(r["id"], None)
    return code == 0, meta, "\n".join(erreurs)


def _artistes(a):
    """« Booba, Kalash » reste tel quel ; YouTube répète parfois l'artiste principal."""
    vus = []
    for x in (a or "").split(","):
        x = x.strip()
        if x and x.lower() not in (v.lower() for v in vus):
            vus.append(x)
    return ", ".join(vus)


def _nom(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")[:150] or "Titre"


def _pochette_carree(image):
    """Vignette 16:9 → pochette carrée (centre), JPEG ≤ 1200 px."""
    sortie = image.with_name("pochette-carree.jpg")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(image), "-vf",
                        "crop='min(iw,ih)':'min(iw,ih)',scale='min(1200,iw)':-2", "-q:v", "2", str(sortie)],
                       capture_output=True)
    return sortie.read_bytes() if r.returncode == 0 and sortie.exists() else image.read_bytes()


def _ecrire_tags(chemin, titre, artiste, album, annee, pochette, trouve):
    import mutagen
    from mutagen.mp4 import MP4, MP4Cover
    texte = ""
    if trouve and not trouve.get("instrumental"):
        texte = trouve.get("syncedLyrics") or trouve.get("plainLyrics") or ""
    if chemin.suffix.lower() == ".m4a":
        f = MP4(chemin)
        f["\xa9nam"] = titre
        if artiste:
            f["\xa9ART"] = artiste
        f["\xa9alb"] = album
        if annee:
            f["\xa9day"] = annee
        if pochette:
            f["covr"] = [MP4Cover(pochette, imageformat=MP4Cover.FORMAT_JPEG)]
        if texte:
            f["\xa9lyr"] = texte
        f.save()
        return
    f = mutagen.File(chemin, easy=True)
    if f is None:
        return
    f["title"], f["album"] = titre, album
    if artiste:
        f["artist"] = artiste
    if annee:
        f["date"] = annee
    f.save()
