"""API HTTP et interface d'Onde."""
import json
import re
import subprocess
import threading
import time
from pathlib import Path

import mutagen
from flask import Blueprint, Flask, Response, abort, jsonify, request, send_file

from . import VERSION, config, infos, outils, paroles, radios, volume
from . import bibliotheque as bib
from . import telechargement as tel

api = Blueprint("api", __name__, url_prefix="/api")
STATIQUE = config.RACINE / "static"
_mini_verrou = threading.Lock()
_mini_fenetre = None


def _hypr(*args):
    resultat = subprocess.run(["hyprctl", *args], capture_output=True,
                              text=True, timeout=2, check=True)
    if args[0] == "dispatch" and resultat.stdout.strip() != "ok":
        raise RuntimeError(resultat.stdout.strip() or "Hyprland n'a pas répondu")
    return resultat.stdout


@api.post("/mini/fenetre")
def mini_fenetre():
    """Masquer uniquement la fenêtre Chrome d'Onde, puis la remettre à sa place."""
    global _mini_fenetre
    corps = _corps()
    action = corps.get("action")
    if action not in ("masquer", "restaurer"):
        return _erreur("Action inconnue")
    with _mini_verrou:
        try:
            clients = json.loads(_hypr("-j", "clients"))
            if action == "masquer":
                if _mini_fenetre:
                    return jsonify({"masquee": True})
                candidats = []
                for client in clients:
                    classe = client.get("class", "")
                    if (classe != "Onde" and not classe.startswith("chrome-localhost__")):
                        continue
                    if client.get("title") != corps.get("titre"):
                        continue
                    candidats.append(client)
                if len(candidats) != 1:
                    return _erreur("La fenêtre principale d'Onde n'a pas été identifiée", 409)
                client = candidats[0]
                adresse = client["address"]
                if not re.fullmatch(r"0x[0-9a-fA-F]+", adresse):
                    return _erreur("Adresse de fenêtre invalide")
                _hypr("dispatch", "movetoworkspacesilent",
                      f"special:onde-mini,address:{adresse}")
                _mini_fenetre = {"adresse": adresse, "stable": client.get("stableId"),
                                 "workspace": client["workspace"]["name"]}
                return jsonify({"masquee": True})
            if _mini_fenetre:
                etat = _mini_fenetre
                client = next((c for c in clients if c["address"] == etat["adresse"]
                               and c.get("stableId") == etat["stable"]), None)
                if client:
                    _hypr("dispatch", "movetoworkspacesilent",
                          f"{etat['workspace']},address:{etat['adresse']}")
                    if corps.get("focus"):
                        _hypr("dispatch", "focuswindow", f"address:{etat['adresse']}")
                _mini_fenetre = None
            return jsonify({"masquee": False})
        except (OSError, ValueError, KeyError, subprocess.SubprocessError, RuntimeError) as e:
            return _erreur(f"Gestion de la fenêtre indisponible : {e}", 503)


def _corps():
    return request.get_json(silent=True) or {}


def _erreur(msg, code=400):
    return jsonify({"erreur": msg}), code


@api.get("/etat")
def etat():
    return jsonify({"version": VERSION, "scan": bib.ETAT_SCAN, "rev": bib.REV["n"], "reglages": config.lire_reglages()})


@api.get("/bibliotheque")
def bibliotheque():
    return jsonify(bib.instantane())


@api.post("/scan")
def scan():
    bib.scanner(complet=bool(_corps().get("complet")))
    return jsonify(bib.ETAT_SCAN)


@api.get("/scan")
def etat_scan():
    return jsonify({**bib.ETAT_SCAN, "rev": bib.REV["n"]})


@api.get("/audio/<int:pid>")
def audio(pid):
    chemin = bib.chemin_piste(pid)
    if not chemin or not Path(chemin).exists():
        abort(404)
    return send_file(chemin, conditional=True, max_age=0)


@api.get("/pochette/<nom>")
def pochette(nom):
    f = (config.POCHETTES / nom).resolve()
    if f.parent != config.POCHETTES.resolve() or not f.exists():
        abort(404)
    return send_file(f, max_age=31536000)


@api.post("/favoris/<int:pid>")
def favori(pid):
    return jsonify({"favori": bib.basculer_favori(pid)})


@api.post("/ecoute/<int:pid>")
def ecoute(pid):
    bib.noter_ecoute(pid)
    return jsonify({"ok": True})


@api.get("/stats")
def stats():
    return jsonify(bib.statistiques())


@api.get("/paroles/<int:pid>")
def lyrics(pid):
    r = paroles.paroles(pid, forcer=request.args.get("forcer") == "1")
    return jsonify(r or {"synchro": [], "texte": ""})


@api.get("/paroles/recherche")
def paroles_recherche():
    return jsonify({"resultats": paroles.rechercher_texte(request.args.get("q", "")), **paroles.couverture()})


@api.get("/paroles/tout")
def paroles_tout_etat():
    return jsonify({**paroles.ETAT_TOUT, **paroles.couverture()})


@api.post("/paroles/tout")
def paroles_tout():
    return jsonify(paroles.recuperer_tout())


@api.get("/paroles/<int:pid>/proposition")
def paroles_proposition(pid):
    return jsonify(paroles.proposition(pid) or {})


@api.get("/paroles/chercher")
def paroles_chercher():
    try:
        return jsonify({"resultats": paroles.chercher(request.args.get("q", ""), request.args.get("duree", type=float))})
    except RuntimeError as e:
        return _erreur(str(e), 502)


@api.post("/paroles/<int:pid>")
def paroles_choisir(pid):
    d = _corps()
    if not bib.piste(pid):
        abort(404)
    try:
        if d.get("lrclib"):
            return jsonify(paroles.choisir(pid, d["lrclib"]))
        if d.get("texte"):
            return jsonify(paroles.importer(pid, d["texte"]))
    except Exception as e:
        return _erreur(f"Impossible de récupérer ces paroles : {e}", 502)
    return _erreur("Rien à enregistrer")


@api.post("/paroles/<int:pid>/recaler")
def paroles_recaler(pid):
    if not bib.piste(pid):
        abort(404)
    try:
        return jsonify(paroles.recaler(pid))
    except (ValueError, RuntimeError, OSError) as e:
        return _erreur(f"Impossible de recaler ces paroles : {e}", 502)


@api.get("/volume/<int:pid>")
def volume_piste(pid):
    try:
        return jsonify(volume.niveau(pid))
    except (ValueError, OSError) as e:
        return _erreur(str(e))


@api.get("/proprietes/<int:pid>")
def proprietes(pid):
    r = outils.proprietes(pid)
    if not r:
        abort(404)
    return jsonify(r)


# ── sauvegarde / restauration ───────────────────────────────────────
@api.post("/sauvegarde")
def sauvegarde():
    s = outils.creer(_corps().get("client"))
    nom = time.strftime("onde-sauvegarde-%Y-%m-%d-%Hh%M.json")
    return Response(json.dumps(s, ensure_ascii=False, indent=1), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@api.post("/restauration")
def restauration():
    try:
        return jsonify(outils.restaurer(_corps().get("sauvegarde")))
    except (ValueError, TypeError, KeyError) as e:
        return _erreur(f"Restauration impossible : {e}")


# ── correction des métadonnées ─────────────────────────────────────
@api.get("/infos/chercher/<int:pid>")
def infos_chercher(pid):
    try:
        return jsonify({"resultats": infos.rechercher(pid, request.args.get("q", ""), request.args.get("album") == "1")})
    except ValueError as e:
        return _erreur(str(e))
    except RuntimeError as e:
        return _erreur(str(e), 502)


@api.post("/infos/album/<int:collection>")
def infos_album(collection):
    try:
        return jsonify({"resultats": infos.pistes_album(collection, [int(i) for i in _corps().get("ids", [])])})
    except (ValueError, TypeError) as e:
        return _erreur(str(e))
    except RuntimeError as e:
        return _erreur(str(e), 502)


@api.put("/infos/<int:pid>")
def infos_modifier(pid):
    try:
        return jsonify({"piste": infos.modifier(pid, _corps())})
    except (ValueError, TypeError, OSError, mutagen.MutagenError) as e:
        return _erreur(f"Tags non enregistrés : {e}")
    except RuntimeError as e:
        return _erreur(str(e), 502)


@api.get("/doublons")
def infos_doublons():
    return jsonify({"groupes": bib.doublons()})


@api.post("/doublons")
def infos_fusionner():
    try:
        d = _corps()
        return jsonify({"fusions": bib.fusionner(int(d["garder"]), [int(i) for i in d["ids"]])})
    except (ValueError, TypeError, KeyError) as e:
        return _erreur(str(e))


# ── playlists ───────────────────────────────────────────────────────
@api.post("/playlists")
def creer_playlist():
    d = _corps()
    pid = bib.creer_playlist(d.get("nom") or "Nouvelle playlist", [int(i) for i in d.get("pistes") or []])
    return jsonify({"id": pid, "playlists": bib.playlists()})


@api.put("/playlists/<int:pid>")
def modifier_playlist(pid):
    d = _corps()
    bib.modifier_playlist(pid, d.get("nom"), d.get("description"))
    if "pistes" in d:
        bib.ordonner_playlist(pid, [int(i) for i in d["pistes"]])
    return jsonify({"playlists": bib.playlists()})


@api.delete("/playlists/<int:pid>")
def supprimer_playlist(pid):
    bib.supprimer_playlist(pid)
    return jsonify({"playlists": bib.playlists()})


@api.post("/playlists/<int:pid>/pistes")
def ajouter_playlist(pid):
    n = bib.ajouter_a_playlist(pid, [int(i) for i in _corps().get("pistes") or []])
    return jsonify({"ajoutees": n, "playlists": bib.playlists()})


# ── radios ──────────────────────────────────────────────────────────
@api.get("/radios")
def mes_radios():
    return jsonify({"radios": bib.radios()})


@api.get("/radios/chercher")
def chercher_radios():
    a = request.args
    return jsonify({"radios": radios.chercher(a.get("q", ""), a.get("pays", ""), a.get("genre", ""))})


@api.post("/radios")
def ajouter_radio():
    bib.ajouter_radio(_corps())
    return jsonify({"radios": bib.radios()})


@api.delete("/radios")
def supprimer_radio():
    bib.supprimer_radio(request.args.get("url", ""))
    return jsonify({"radios": bib.radios()})


@api.get("/radio/flux")
def flux_radio():
    url = request.args.get("url", "")
    if not url.startswith(("http://", "https://")):
        abort(400)
    try:
        gen, type_ = radios.flux(url)
    except Exception as e:
        return _erreur(f"Radio injoignable : {e}", 502)
    return Response(gen, mimetype=type_, headers={"Cache-Control": "no-cache"})


# ── téléchargement YouTube (même système qu'Aura) ───────────────────
@api.get("/yt/chercher")
def yt_chercher():
    try:
        return jsonify({"resultats": tel.chercher(request.args.get("q", ""))})
    except Exception as e:
        return _erreur(f"Recherche impossible : {e}", 502)


@api.get("/yt/paroles")
def yt_paroles():
    a = request.args
    return jsonify({"paroles": tel.sonder(a.get("id", ""), a.get("artiste", ""), a.get("titre", ""), a.get("duree", 0, type=float))})


@api.post("/yt/telecharger")
def yt_telecharger():
    try:
        return jsonify(tel.demarrer(_corps()))
    except ValueError as e:
        return _erreur(str(e))


@api.get("/yt/taches")
def yt_taches():
    return jsonify({"taches": tel.taches()})


@api.post("/yt/annuler/<vid>")
def yt_annuler(vid):
    tel.annuler(vid)
    return jsonify({"taches": tel.taches()})


@api.delete("/yt/taches")
def yt_vider():
    tel.vider_terminees()
    return jsonify({"taches": tel.taches()})


# ── « Ouvrir avec Onde » : fichiers transmis par onde-app à la fenêtre ─
_cmd = {"n": 0, "liste": [], "acquittes": set()}
_cond = threading.Condition()


@api.post("/ouvrir-fichiers")
def ouvrir_fichiers():
    ids = bib.importer([str(c) for c in _corps().get("chemins") or []])
    if not ids:
        return _erreur("Aucun fichier audio lisible")
    with _cond:
        _cmd["n"] += 1
        n = _cmd["n"]
        _cmd["liste"] = [c for c in _cmd["liste"] if c["t"] > time.time() - 60] + [{"n": n, "ids": ids, "t": time.time()}]
        _cond.notify_all()
        # une fenêtre ouverte acquitte en moins d'une seconde ; sinon onde-app en ouvre une
        fenetre = _cond.wait_for(lambda: n in _cmd["acquittes"], timeout=2)
    return jsonify({"ids": ids, "fenetre": fenetre})


@api.get("/commande")
def attendre_commande():
    depuis = request.args.get("depuis", 0, type=int)
    with _cond:
        _cond.wait_for(lambda: any(c["n"] > depuis and c["n"] not in _cmd["acquittes"] for c in _cmd["liste"]), timeout=20)
        prets = [c for c in _cmd["liste"] if c["n"] > depuis and c["n"] not in _cmd["acquittes"]]
    return jsonify({"commandes": prets, "n": max([depuis] + [c["n"] for c in _cmd["liste"]])})


@api.post("/commande/<int:n>")
def acquitter_commande(n):
    with _cond:
        _cmd["acquittes"].add(n)
        _cmd["liste"] = [c for c in _cmd["liste"] if c["n"] != n]
        _cond.notify_all()
    return jsonify({"ok": True})


# ── réglages / système ──────────────────────────────────────────────
@api.post("/reglages")
def reglages():
    d = _corps()
    if "dossiers" in d:
        absents = [x for x in d["dossiers"] if not Path(x).expanduser().is_dir()]
        if absents:
            return _erreur(f"Dossier introuvable : {absents[0]}")
    r = config.ecrire_reglages(d)
    if "dossiers" in d or "titres_fichier" in d:
        bib.scanner(complet="titres_fichier" in d)
    return jsonify(r)


@api.post("/ouvrir/<int:pid>")
def ouvrir(pid):
    chemin = bib.chemin_piste(pid)
    if not chemin:
        abort(404)
    r = subprocess.run(["dbus-send", "--session", "--dest=org.freedesktop.FileManager1", "--type=method_call",
                        "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                        f"array:string:file://{chemin}", "string:"], capture_output=True)
    if r.returncode != 0:
        subprocess.Popen(["xdg-open", str(Path(chemin).parent)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify({"ok": True})


def creer_app():
    app = Flask(__name__, static_folder=str(STATIQUE), static_url_path="/static")
    app.json.ensure_ascii = False
    app.register_blueprint(api)

    @app.get("/")
    def accueil():
        return send_file(STATIQUE / "index.html", max_age=0)

    @app.get("/favicon.ico")
    def favicon():
        return send_file(STATIQUE / "icone.svg", mimetype="image/svg+xml")

    @app.before_request
    def meme_origine():
        # Serveur local : on refuse les requêtes envoyées par d'autres sites.
        if request.method in ("POST", "PUT", "DELETE"):
            o = request.headers.get("Origin")
            if o and o.split("://", 1)[-1] != request.host:
                abort(403)

    bib.completer_qualite()  # fréquence / résolution des titres indexés avant le badge qualité
    bib.scanner()  # mise à jour de la bibliothèque au démarrage (rapide si rien n'a changé)
    return app
