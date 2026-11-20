"""Annuaire de radios (radio-browser.info) et relais du flux (pour l'égaliseur)."""
import json
import urllib.parse
import urllib.request

from . import VERSION

UA = {"User-Agent": f"Onde/{VERSION}"}
SERVEURS = ["https://de1.api.radio-browser.info", "https://fi1.api.radio-browser.info", "https://de2.api.radio-browser.info"]


def _get(chemin, params):
    q = urllib.parse.urlencode({**params, "hidebroken": "true", "limit": params.get("limit", 40)})
    for s in SERVEURS:
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{s}{chemin}?{q}", headers=UA), timeout=8) as r:
                return json.load(r)
        except Exception:
            continue
    return []


def chercher(nom="", pays="", genre=""):
    params = {"order": "clickcount", "reverse": "true"}
    if nom:
        params["name"] = nom
    if pays:
        params["countrycode"] = pays
    if genre:
        params["tag"] = genre
    res = _get("/json/stations/search", params)
    vus, sortie = set(), []
    for r in res:
        url = r.get("url_resolved") or r.get("url")
        if not url or url in vus:
            continue
        vus.add(url)
        sortie.append({"nom": (r.get("name") or "").strip(), "url": url, "logo": r.get("favicon") or None,
                       "pays": r.get("countrycode"), "tags": ", ".join((r.get("tags") or "").split(",")[:3]),
                       "debit": r.get("bitrate"), "format": r.get("codec")})
    return sortie


def flux(url):
    """Relais du flux radio (même origine → l'égaliseur et le visualiseur fonctionnent)."""
    req = urllib.request.Request(url, headers={**UA, "Icy-MetaData": "0"})
    r = urllib.request.urlopen(req, timeout=12)
    type_ = r.headers.get("Content-Type", "audio/mpeg")

    def generer():
        try:
            while True:
                bloc = r.read(16384)
                if not bloc:
                    break
                yield bloc
        finally:
            r.close()

    return generer(), type_
