"""Onde CLI — Studio musical interactif Liquid Glass 2.0 ultra-fluide dans le terminal.

Fonctionnalités phares :
    - Esthétique « Liquid Glass 2.0 » : 12 thèmes + Auto pochette, aurore 4-blobs tramée Bayer sans banding
    - Pochette d'album HD native Kitty (\x1b_G) + TrueColor arrondie à halo + platine vinyle articulée
    - 7 Visualiseurs FFT TrueColor 24-bit (Spectre, Horizon Symétrique, Onde Miroir, Braille, Aurore, Barres LED)
    - Vue Accueil Studio (reprise, récents, incontournables, ajouts, à redécouvrir & mixes par genre)
    - Scène karaoké mot-à-mot 2 lignes sans effet de rechargement + perspective profondeur + Studio Paroles
    - 10 Onglets (Titres, Favoris, Playlists, Artistes, Albums, Radios FM/Web, File, Récents, Dossiers, Genres)
    - Égaliseur 10 bandes avec profils persos + Effets DSP temps réel (Stéréo Large, Karaoké −Voix, Hall Reverb)
    - Radio intelligente du titre (Smart Mix), Export M3U8, Stats 24h, YouTube Direct, Tags iTunes/Pochette locale
    - Palette Spotlight ([F1]/[Ctrl+P]), Réglages & Sorties mpv ([Ctrl+G]), Doublons ([Ctrl+D]), IPC & MPRIS2
"""

import argparse
import atexit
import base64
import contextlib
import json
import math
import os
import random
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import termios
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from rich import box
from rich.align import Align
from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text

from . import (
    bibliotheque,
    config,
    infos,
    outils,
    paroles,
    radios,
    telechargement,
    volume,
)

CHARS_VUMETRE = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
CHARS_PROGRESSION = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
ROUES_VINYLE = ["◓", "◑", "◒", "◐"]
BARRES_LECTURE_ANIME = ["▁▄▆", "▄▆▂", "▆▂▄", "▂▆▄"]
FICHIER_ETAT_CLI = config.CONFIG / "cli.json"
SOCKET_CTRL_CLI = f"/tmp/onde_cli_ctrl_{os.getuid()}.sock"
EXTENSIONS_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
FREQS_EQ_10: list[tuple[int, str]] = [
    (31, "31Hz"),
    (62, "62Hz"),
    (125, "125Hz"),
    (250, "250Hz"),
    (500, "500Hz"),
    (1000, "1kHz"),
    (2000, "2kHz"),
    (4000, "4kHz"),
    (8000, "8kHz"),
    (16000, "16kHz"),
]
MODES_VISUALISEUR: list[tuple[str, str]] = [
    ("spectre", "Spectre Studio"),
    ("horizon", "Horizon Symétrique"),
    ("onde", "Onde Miroir"),
    ("braille", "Oscilloscope Braille"),
    ("galaxie", "Aurore Spectrale"),
    ("barres", "Barres Néon LED"),
    ("aucun", "Discret"),
]
TRIS_LISTE: list[tuple[str, str]] = [
    ("defaut", "Artiste A-Z"),
    ("titre", "Titre A-Z"),
    ("album", "Album"),
    ("ajouts", "Ajouts récents"),
    ("ecoutes", "Plus écoutés"),
    ("duree", "Durée"),
    ("annee", "Année"),
    ("qualite", "Qualité / Débit"),
]
EFFETS_DSP: list[tuple[str, str, str]] = [
    ("off", "Pur (Bit-Perfect)", ""),
    ("large", "Stéréo Large 🎧", "extrastereo=m=1.45"),
    ("karaoke", "Karaoké −Voix 🎙", "stereotools=mlev=0.08"),
    ("reverb", "Hall & Reverb ✨", "aecho=0.8:0.88:55:0.35"),
    ("nuit", "Nuit Douce 🌙", "dynaudnorm=f=150:g=15"),
]
RADIOS_DEFAUT: list[dict[str, Any]] = [
    {
        "nom": "FIP (Radio France)",
        "url": "https://icecast.radiofrance.fr/fip-hifi.aac",
        "pays": "FR",
        "tags": "eclectic, jazz, groove, world",
    },
    {
        "nom": "FIP Groove",
        "url": "https://icecast.radiofrance.fr/fipgroove-hifi.aac",
        "pays": "FR",
        "tags": "soul, funk, hip-hop, rnb",
    },
    {
        "nom": "FIP Electro",
        "url": "https://icecast.radiofrance.fr/fipelectro-hifi.aac",
        "pays": "FR",
        "tags": "electro, house, chill",
    },
    {
        "nom": "Mouv'",
        "url": "https://icecast.radiofrance.fr/mouv-hifi.aac",
        "pays": "FR",
        "tags": "rap, hip-hop, rnb, urbain",
    },
    {
        "nom": "Radio Nova",
        "url": "https://novazz.ice.infomaniak.ch/novazz-128.mp3",
        "pays": "FR",
        "tags": "eclectic, soul, world, indie",
    },
    {
        "nom": "Skyrock",
        "url": "https://icecast.skyrock.net/s/natio_aac_128k",
        "pays": "FR",
        "tags": "rap, rnb, hip-hop",
    },
    {
        "nom": "Lofi Girl — Beats to Relax/Study",
        "url": "https://play.streamafrica.net/lofiradio",
        "pays": "INT",
        "tags": "lofi, chillhop, study, relax",
    },
    {
        "nom": "SomaFM Groove Salad",
        "url": "https://ice2.somafm.com/groovesalad-128-mp3",
        "pays": "US",
        "tags": "ambient, downtempo, chillout",
    },
]

# ── Thèmes Visuels & Palettes « Liquid Glass » ───────────────────────────────

THEMES: dict[str, dict[str, str]] = {
    "auto": {
        "nom": "Auto (Pochette)",
        "primaire": "#c084fc",
        "secondaire": "#22d3ee",
        "accent": "#f472b6",
        "succes": "#34d399",
        "bordure": "#4c3575",
        "bordure_active": "#c084fc",
        "selection_bg": "#24193d",
        "badge_bg": "#6d28d9",
        "surface_bg": "#090814",
        "surface_2": "#131126",
        "texte_dim": "#b4b8d4",
        "texte_muet": "#6e7394",
        "aurora_1": "#db2777",
        "aurora_2": "#7c3aed",
        "aurora_3": "#0891b2",
    },
    "liquid": {
        "nom": "Onde Liquid Glass",
        "primaire": "#c084fc",
        "secondaire": "#22d3ee",
        "accent": "#f9a8d4",
        "succes": "#34d399",
        "bordure": "#5b3b8c",
        "bordure_active": "#c084fc",
        "selection_bg": "#251842",
        "badge_bg": "#7e22ce",
        "surface_bg": "#080713",
        "surface_2": "#121024",
        "texte_dim": "#b9bdd8",
        "texte_muet": "#6e7291",
        "aurora_1": "#db2777",
        "aurora_2": "#7c3aed",
        "aurora_3": "#0891b2",
    },
    "onde": {
        "nom": "Onde Cyan",
        "primaire": "#22d3ee",
        "secondaire": "#60a5fa",
        "accent": "#fde047",
        "succes": "#34d399",
        "bordure": "#0e7490",
        "bordure_active": "#22d3ee",
        "selection_bg": "#0c2d3d",
        "badge_bg": "#0369a1",
        "surface_bg": "#060d17",
        "surface_2": "#0d192a",
        "texte_dim": "#a5c4d4",
        "texte_muet": "#64748b",
        "aurora_1": "#0891b2",
        "aurora_2": "#2563eb",
        "aurora_3": "#0d9488",
    },
    "catppuccin": {
        "nom": "Catppuccin Mocha",
        "primaire": "#cba6f7",
        "secondaire": "#89b4fa",
        "accent": "#f9e2af",
        "succes": "#a6e3a1",
        "bordure": "#585b70",
        "bordure_active": "#cba6f7",
        "selection_bg": "#313244",
        "badge_bg": "#5b4880",
        "surface_bg": "#11111b",
        "surface_2": "#1e1e2e",
        "texte_dim": "#bac2de",
        "texte_muet": "#7f849c",
        "aurora_1": "#cba6f7",
        "aurora_2": "#89b4fa",
        "aurora_3": "#f38ba8",
    },
    "cyberpunk": {
        "nom": "Cyberpunk Néon",
        "primaire": "#00f0ff",
        "secondaire": "#ff2a85",
        "accent": "#fde047",
        "succes": "#00ff9f",
        "bordure": "#9d174d",
        "bordure_active": "#00f0ff",
        "selection_bg": "#2e084d",
        "badge_bg": "#be185d",
        "surface_bg": "#0a0414",
        "surface_2": "#160926",
        "texte_dim": "#cbd5e1",
        "texte_muet": "#70688a",
        "aurora_1": "#ff2a85",
        "aurora_2": "#7e22ce",
        "aurora_3": "#00f0ff",
    },
    "emeraude": {
        "nom": "Émeraude Studio",
        "primaire": "#34d399",
        "secondaire": "#2dd4bf",
        "accent": "#fbbf24",
        "succes": "#6ee7b7",
        "bordure": "#065f46",
        "bordure_active": "#34d399",
        "selection_bg": "#063b2d",
        "badge_bg": "#047857",
        "surface_bg": "#05110e",
        "surface_2": "#0b1f19",
        "texte_dim": "#a7f3d0",
        "texte_muet": "#608074",
        "aurora_1": "#10b981",
        "aurora_2": "#0d9488",
        "aurora_3": "#0284c7",
    },
    "ambre": {
        "nom": "Ambre Vinyle",
        "primaire": "#fbbf24",
        "secondaire": "#fb923c",
        "accent": "#fef08a",
        "succes": "#4ade80",
        "bordure": "#92400e",
        "bordure_active": "#fbbf24",
        "selection_bg": "#3b1806",
        "badge_bg": "#b45309",
        "surface_bg": "#110a05",
        "surface_2": "#1d1209",
        "texte_dim": "#fde68a",
        "texte_muet": "#8c7a6b",
        "aurora_1": "#d97706",
        "aurora_2": "#dc2626",
        "aurora_3": "#9333ea",
    },
    "nord": {
        "nom": "Nord Arctique",
        "primaire": "#88c0d0",
        "secondaire": "#81a1c1",
        "accent": "#ebcb8b",
        "succes": "#a3be8c",
        "bordure": "#434c5e",
        "bordure_active": "#88c0d0",
        "selection_bg": "#2e3440",
        "badge_bg": "#4c566a",
        "surface_bg": "#151922",
        "surface_2": "#202634",
        "texte_dim": "#d8dee9",
        "texte_muet": "#758096",
        "aurora_1": "#5e81ac",
        "aurora_2": "#88c0d0",
        "aurora_3": "#b48ead",
    },
    "velours": {
        "nom": "Velours Rose",
        "primaire": "#fb7185",
        "secondaire": "#f472b6",
        "accent": "#fde047",
        "succes": "#34d399",
        "bordure": "#881337",
        "bordure_active": "#fb7185",
        "selection_bg": "#3b0a1f",
        "badge_bg": "#be123c",
        "surface_bg": "#12060d",
        "surface_2": "#210c18",
        "texte_dim": "#fecdd3",
        "texte_muet": "#8f6678",
        "aurora_1": "#e11d48",
        "aurora_2": "#db2777",
        "aurora_3": "#7c3aed",
    },
    "tokyo": {
        "nom": "Tokyo Night Néon",
        "primaire": "#7dcfff",
        "secondaire": "#bb9af7",
        "accent": "#f7768e",
        "succes": "#9ece6a",
        "bordure": "#3b4261",
        "bordure_active": "#7dcfff",
        "selection_bg": "#24283b",
        "badge_bg": "#3d59a1",
        "surface_bg": "#0b0d17",
        "surface_2": "#16192a",
        "texte_dim": "#c0caf5",
        "texte_muet": "#646d91",
        "aurora_1": "#7aa2f7",
        "aurora_2": "#bb9af7",
        "aurora_3": "#f7768e",
    },
    "solaire": {
        "nom": "Sunset Synthwave",
        "primaire": "#ff7e5f",
        "secondaire": "#ff2e93",
        "accent": "#feb47b",
        "succes": "#38ef7d",
        "bordure": "#7a1f5c",
        "bordure_active": "#ff7e5f",
        "selection_bg": "#2d0c2e",
        "badge_bg": "#b91c63",
        "surface_bg": "#100617",
        "surface_2": "#1e0c29",
        "texte_dim": "#fed7aa",
        "texte_muet": "#8b6685",
        "aurora_1": "#ff2e93",
        "aurora_2": "#ff7e5f",
        "aurora_3": "#7c3aed",
    },
    "obsidienne": {
        "nom": "Obsidienne Or",
        "primaire": "#f5d08a",
        "secondaire": "#cbd5e1",
        "accent": "#fbbf24",
        "succes": "#4ade80",
        "bordure": "#3f3b32",
        "bordure_active": "#f5d08a",
        "selection_bg": "#211e18",
        "badge_bg": "#785a28",
        "surface_bg": "#08080a",
        "surface_2": "#141418",
        "texte_dim": "#e2e0d8",
        "texte_muet": "#78756c",
        "aurora_1": "#a16207",
        "aurora_2": "#475569",
        "aurora_3": "#ca8a04",
    },
}
ORDRE_THEMES = [
    "auto",
    "liquid",
    "tokyo",
    "solaire",
    "onde",
    "catppuccin",
    "cyberpunk",
    "emeraude",
    "ambre",
    "nord",
    "velours",
    "obsidienne",
]

# ── Préréglages Égaliseur MPV ────────────────────────────────────────────────

PROFILS_EQ: list[tuple[str, str]] = [
    ("Neutre", ""),
    ("Bass Boost 🔥", "lavfi=[bass=g=6:f=95:w=0.6]"),
    (
        "Voix & Karaoké 🎙️",
        "lavfi=[equalizer=f=2400:t=q:w=1.2:g=4.5,equalizer=f=110:t=q:w=1:g=-2]",
    ),
    ("Clarté Cristal ✨", "lavfi=[bass=g=3:f=90,treble=g=5:f=8500]"),
    ("Club / Électro ⚡", "lavfi=[bass=g=7.5:f=80,treble=g=4:f=10000]"),
    ("Nuit Douce 🌙", "lavfi=[dynaudnorm=f=150:g=15]"),
]
PROFILS_EQ_BANDES: list[list[float]] = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [6.0, 5.0, 3.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0],
    [-2.0, -2.0, -1.0, 1.0, 2.0, 3.0, 5.0, 4.0, 2.0, 1.0],
    [3.0, 2.0, 1.0, 0.0, 0.0, 1.0, 2.0, 4.0, 5.0, 5.0],
    [7.0, 6.0, 3.0, 0.0, -1.0, 0.0, 2.0, 3.0, 4.0, 4.0],
    [2.0, 1.0, 0.0, -1.0, -1.0, 0.0, 1.0, 1.0, -1.0, -2.0],
]

NIVEAUX_LUMINOSITE: list[tuple[str, float]] = [
    ("Discret (18%)", 0.18),
    ("Équilibré (28%)", 0.28),
    ("Lumineux (40%)", 0.40),
    ("Éclatant (55%)", 0.55),
]


# ── Utilitaires Couleurs, Formatage & Saisie ─────────────────────────────────


def _hex_vers_rgb(
    couleur: str | None, defaut: tuple[int, int, int] = (56, 189, 248)
) -> tuple[int, int, int]:
    if couleur and couleur.startswith("#") and len(couleur) == 7:
        with contextlib.suppress(ValueError):
            return (
                int(couleur[1:3], 16),
                int(couleur[3:5], 16),
                int(couleur[5:7], 16),
            )
    return defaut


def _rgb_vers_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"


def _melanger_rgb(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def formater_duree(secondes: float | None, radio: bool = False) -> str:
    if radio:
        return "LIVE"
    sec = max(0, int(secondes or 0))
    if sec >= 3600:
        return f"{sec // 3600}h{(sec % 3600) // 60:02d}"
    return f"{sec // 60:02d}:{sec % 60:02d}"


def badge_qualite_piste(
    piste: dict[str, Any] | None, complet: bool = False
) -> str:
    if not piste:
        return ""
    if piste.get("_type") == "radio":
        return "LIVE"
    fmt = (piste.get("format") or "").upper()
    debit = piste.get("debit")
    bits = piste.get("bits")
    freq = piste.get("frequence")
    if not complet:
        if bits and bits >= 24:
            return "HI-RES"
        if fmt in ("FLAC", "WAV", "ALAC"):
            return fmt
        if debit and debit > 0:
            kb = debit if debit < 20000 else debit // 1000
            return f"{fmt or 'AUD'} {kb}" if fmt else f"{kb}k"
        return fmt
    parties: list[str] = []
    if fmt:
        parties.append(fmt)
    if debit and debit > 0:
        parties.append(f"{debit} kbps" if debit < 20000 else f"{debit // 1000} kbps")
    if bits and freq:
        parties.append(f"{bits}-bit/{freq / 1000:.1f}kHz")
    elif freq:
        parties.append(f"{freq / 1000:.1f}kHz")
    return " • ".join(parties)


def barre_proportionnelle(
    ratio: float, largeur: int, style_plein: str, style_vide: str
) -> Text:
    """Barre haute précision au 1/8e de caractère."""
    txt = Text()
    w = max(2, largeur)
    r = max(0.0, min(1.0, ratio))
    total_huitièmes = round(r * w * 8)
    pleins = total_huitièmes // 8
    reste = total_huitièmes % 8
    vides = w - pleins - (1 if reste > 0 and pleins < w else 0)
    if pleins:
        txt.append("█" * pleins, style=style_plein)
    if reste > 0 and pleins < w:
        txt.append(CHARS_PROGRESSION[reste], style=style_plein)
    if vides > 0:
        txt.append("░" * vides, style=style_vide)
    return txt


def texte_degrade(
    texte: str,
    c_deb: str,
    c_fin: str,
    gras: bool = True,
    bg: str | None = None,
    c_milieu: str | None = None,
) -> Text:
    """Colore un texte avec un dégradé RGB TrueColor continu caractère par caractère."""
    out = Text(no_wrap=True)
    if not texte:
        return out
    rgb_a = _hex_vers_rgb(c_deb, (192, 132, 252))
    rgb_b = _hex_vers_rgb(c_fin, (34, 211, 238))
    rgb_m = _hex_vers_rgb(c_milieu, rgb_a) if c_milieu else None
    n = max(1, len(texte) - 1)
    prefixe = "bold " if gras else ""
    suffixe = f" on {bg}" if bg else ""
    for i, ch in enumerate(texte):
        t = i / n
        if rgb_m is not None:
            if t < 0.5:
                rgb = _melanger_rgb(rgb_a, rgb_m, t * 2.0)
            else:
                rgb = _melanger_rgb(rgb_m, rgb_b, (t - 0.5) * 2.0)
        else:
            rgb = _melanger_rgb(rgb_a, rgb_b, t)
        out.append(ch, style=f"{prefixe}{_rgb_vers_hex(*rgb)}{suffixe}")
    return out


def barre_degrade(
    ratio: float,
    largeur: int,
    c_deb: str,
    c_fin: str,
    style_vide: str,
    char_vide: str = "░",
) -> Text:
    """Barre proportionnelle au 1/8e avec dégradé RGB TrueColor."""
    txt = Text(no_wrap=True)
    w = max(2, largeur)
    r = max(0.0, min(1.0, ratio))
    total_h = round(r * w * 8)
    pleins = total_h // 8
    reste = total_h % 8
    rgb_a = _hex_vers_rgb(c_deb, (192, 132, 252))
    rgb_b = _hex_vers_rgb(c_fin, (34, 211, 238))
    for i in range(w):
        t = i / max(1, w - 1)
        c_hex = _rgb_vers_hex(*_melanger_rgb(rgb_a, rgb_b, t))
        if i < pleins:
            txt.append("█", style=c_hex)
        elif i == pleins and reste > 0:
            txt.append(CHARS_PROGRESSION[reste], style=c_hex)
        else:
            txt.append(char_vide, style=style_vide)
    return txt


def salutation_horaire() -> str:
    """Salutation contextuelle selon l'heure locale."""
    hr = time.localtime().tm_hour
    if hr < 5:
        return "Bonne nuit"
    if hr < 12:
        return "Bonjour"
    if hr < 18:
        return "Bon après-midi"
    return "Bonsoir"


def appliquer_touche_saisie(touche: str, tampon: str) -> str | None:
    """Applique une touche texte (caractère, retour, espace, collage) ou None si non gérée."""
    if touche == "RETOUR":
        return tampon[:-1]
    if touche == "ESPACE":
        return tampon + " "
    if touche.startswith("PASTE:"):
        propre = touche[6:].replace("\r", " ").replace("\n", " ").strip()
        return tampon + propre
    if len(touche) == 1 and ord(touche) >= 32:
        return tampon + touche
    return None


# ── Modèle de paroles synchronisées & Karaoké ─────────────────────────────────


@dataclass
class LigneParole:
    """Représente une ligne ou un passage de paroles avec repères temporels."""

    t: float
    fin: float
    texte: str
    pause: bool = False
    mots: list[tuple[float, str, float]] = field(default_factory=list)


def interpoler_mots_phrase(
    texte: str, t_deb: float, t_fin: float
) -> list[tuple[float, str, float]]:
    """Génère des repères mot-à-mot fluides et naturels proportionnels à leur longueur."""
    tokens = [m for m in texte.split(" ") if m]
    if not tokens:
        return []
    total_car = sum(max(1, len(m)) for m in tokens)
    duree_tot = max(0.5, t_fin - t_deb)
    duree_chant = duree_tot * 0.88
    res: list[tuple[float, str, float]] = []
    t_courant = t_deb
    for i, tok in enumerate(tokens):
        poids = max(1, len(tok)) / total_car
        duree_mot = duree_chant * poids
        fin_mot = t_courant + duree_mot
        espace = " " if i < len(tokens) - 1 else ""
        res.append((round(t_courant, 3), tok + espace, round(fin_mot, 3)))
        t_courant = fin_mot
    return res


def preparer_synchro_cli(
    synchro: list[list[Any]], mots_liste: list[list[Any]] | None = None
) -> list[LigneParole]:
    """Transforme les repères bruts en une séquence continue et fluide de lignes.

    Préserve la continuité sans effet de rechargement.
    """
    if not synchro:
        return []

    groupes: list[dict[str, Any]] = []
    for i, item in enumerate(synchro):
        if not item or len(item) < 2:
            continue
        t, l = float(item[0]), str(item[1] or "").strip()
        if groupes and abs(groupes[-1]["t"] - t) < 0.05:
            if l and l not in groupes[-1]["textes"]:
                groupes[-1]["textes"].append(l)
                groupes[-1]["mots"] = None
        else:
            m = mots_liste[i] if mots_liste and i < len(mots_liste) else None
            groupes.append({"t": t, "textes": [l], "mots": m})

    items: list[LigneParole] = []
    if groupes and groupes[0]["t"] > 2.0:
        items.append(
            LigneParole(
                t=0.0,
                fin=groupes[0]["t"],
                texte="♪  •  •  •  ♪",
                pause=True,
                mots=[],
            )
        )

    for i, grp in enumerate(groupes):
        t = grp["t"]
        suiv_t = groupes[i + 1]["t"] if i + 1 < len(groupes) else t + 7.0
        txt = " / ".join(filter(None, grp["textes"]))
        if not txt or all(c in "♪♫·. \t\n\r" for c in txt):
            if suiv_t > t:
                items.append(
                    LigneParole(
                        t=t, fin=suiv_t, texte="♪  •  •  •  ♪", pause=True, mots=[]
                    )
                )
            continue

        reperes = grp["mots"]
        fin_chant = suiv_t
        mots_prets: list[tuple[float, str, float]] = []
        if reperes and len(reperes) > 1:
            dernier = reperes[-1]
            if (
                len(dernier) >= 2
                and not str(dernier[1]).strip()
                and t < float(dernier[0]) < suiv_t
            ):
                fin_chant = float(dernier[0])
            for k in range(len(reperes) - 1):
                a = float(reperes[k][0])
                m = str(reperes[k][1])
                if not m:
                    continue
                proch = (
                    float(reperes[k + 1][0])
                    if k + 1 < len(reperes)
                    else fin_chant
                )
                mots_prets.append((a, m, proch))

        if not mots_prets and txt:
            mots_prets = interpoler_mots_phrase(txt, t, fin_chant)

        items.append(
            LigneParole(
                t=t,
                fin=fin_chant,
                texte=txt,
                pause=False,
                mots=mots_prets,
            )
        )
        if suiv_t - fin_chant >= 3.0:
            items.append(
                LigneParole(
                    t=fin_chant,
                    fin=suiv_t,
                    texte="♪  •  •  •  ♪",
                    pause=True,
                    mots=[],
                )
            )

    return items


def ligne_affichee(
    items: list[LigneParole], t: float
) -> tuple[int, LigneParole | None, bool, float]:
    """Détermine la ligne active avec lissage continu (sans sauts ni rechargement)."""
    if not items:
        return -1, None, False, 0.0

    idx = -1
    for k, item in enumerate(items):
        if item.t <= t:
            idx = k
        else:
            break

    if idx < 0:
        return 0, items[0], False, max(0.0, items[0].t - t)

    it = items[idx]
    if not it.pause:
        return idx, it, False, 0.0

    suiv_idx = next((k for k in range(idx + 1, len(items)) if not items[k].pause), -1)
    if suiv_idx >= 0 and items[suiv_idx].t - t <= 1.2:
        return suiv_idx, items[suiv_idx], False, 0.0

    prec_idx = idx - 1
    while prec_idx >= 0 and items[prec_idx].pause:
        prec_idx -= 1

    if prec_idx >= 0 and (it.fin - it.t < 2.5):
        return prec_idx, items[prec_idx], False, 0.0

    t_reprise = max(0.0, items[suiv_idx].t - t) if suiv_idx >= 0 else 0.0
    return idx, it, True, t_reprise


# ── Traitement d'image, Pochette ANSI & Fond Photo ───────────────────────────


def extraire_palette_image(chemin: str | Path) -> dict[str, str] | None:
    """Extrait une palette harmonieuse multi-tons Liquid Glass depuis une image."""
    try:
        with Image.open(chemin) as im:
            petit = im.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR)
            arr = np.asarray(petit, dtype=np.float32).reshape(-1, 3) / 255.0

        r, g, b = arr[:, 0], arr[:, 1], arr[:, 2]
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        delta = mx - mn
        sat = np.where(mx > 1e-4, delta / np.maximum(mx, 1e-4), 0.0)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

        # Calcul de la teinte (0..6) et regroupement en 12 secteurs chromatiques
        hue = np.zeros_like(r)
        mask_d = delta > 0.04
        m_r = mask_d & (mx == r)
        m_g = mask_d & (mx == g) & (~m_r)
        m_b = mask_d & (~m_r) & (~m_g)
        hue[m_r] = ((g[m_r] - b[m_r]) / delta[m_r]) % 6.0
        hue[m_g] = ((b[m_g] - r[m_g]) / delta[m_g]) + 2.0
        hue[m_b] = ((r[m_b] - g[m_b]) / delta[m_b]) + 4.0

        mask_valide = (lum > 0.12) & (lum < 0.92) & (sat > 0.14)
        poids = np.where(
            mask_valide,
            (sat ** 1.35) * np.maximum(0.15, 1.0 - np.abs(lum - 0.54) * 1.15),
            0.0,
        )

        groupes: list[tuple[float, int, tuple[int, int, int]]] = []
        bins = (hue * 2.0).astype(np.int32) % 12
        for bi in range(12):
            m_b_i = (bins == bi) & (poids > 0.0)
            if not np.any(m_b_i):
                continue
            w_b = float(np.sum(poids[m_b_i]))
            if w_b <= 0.01:
                continue
            c_m = np.average(arr[m_b_i], axis=0, weights=poids[m_b_i])
            rgb = (int(c_m[0] * 255), int(c_m[1] * 255), int(c_m[2] * 255))
            groupes.append((w_b, bi, rgb))

        groupes.sort(key=lambda item: item[0], reverse=True)

        def _assurer_lisibilite(
            rgb: tuple[int, int, int], lum_min: float = 0.56, lum_max: float = 0.86
        ) -> tuple[int, int, int]:
            c_r, c_g, c_b = rgb
            l_cur = (0.2126 * c_r + 0.7152 * c_g + 0.0722 * c_b) / 255.0
            if l_cur < lum_min:
                t = min(0.78, (lum_min - l_cur) / max(0.05, 1.0 - l_cur))
                return _melanger_rgb((c_r, c_g, c_b), (242, 246, 255), t)
            if l_cur > lum_max:
                t = min(0.55, (l_cur - lum_max) / max(0.05, l_cur))
                return _melanger_rgb((c_r, c_g, c_b), (20, 22, 38), t)
            return (c_r, c_g, c_b)

        if not groupes:
            # Image monochrome / très peu saturée : palette ardoise irisée propre
            c1 = (125, 211, 252)
            c2 = (167, 139, 250)
            c3 = (244, 114, 182)
        else:
            _, b1, raw1 = groupes[0]
            c1 = _assurer_lisibilite(raw1, 0.58, 0.86)
            c2 = None
            b2 = b1
            c3 = None
            for _, bi, raw in groupes[1:]:
                dist = min(abs(bi - b1), 12 - abs(bi - b1))
                if c2 is None and dist >= 2:
                    c2 = _assurer_lisibilite(raw, 0.52, 0.82)
                    b2 = bi
                elif c3 is None and dist >= 2 and min(abs(bi - b2), 12 - abs(bi - b2)) >= 2:
                    c3 = _assurer_lisibilite(raw, 0.62, 0.88)
                    break
            if c2 is None:
                c2 = _assurer_lisibilite(
                    (max(40, c1[2]), min(255, int(c1[0] * 0.8 + 45)), min(255, int(c1[1] * 0.8 + 70))),
                    0.52,
                    0.82,
                )
            if c3 is None:
                c3 = _assurer_lisibilite(
                    (min(255, 255 - c1[2] // 3), min(255, 235 - c1[0] // 4), max(90, c1[1] // 2 + 50)),
                    0.62,
                    0.88,
                )

        surf_bg = _melanger_rgb((7, 7, 16), c1, 0.06)
        surf_2 = _melanger_rgb((15, 16, 32), c1, 0.11)
        bord = _melanger_rgb((34, 38, 64), c1, 0.42)
        sel_bg = _melanger_rgb(surf_2, c1, 0.25)
        badge_bg = _melanger_rgb(surf_2, c1, 0.42)
        t_dim = _melanger_rgb((220, 228, 240), c1, 0.18)
        t_muet = _melanger_rgb((108, 120, 145), c1, 0.16)
        aur1 = _melanger_rgb((16, 14, 34), c1, 0.72)
        aur2 = _melanger_rgb((14, 16, 38), c2, 0.72)
        aur3 = _melanger_rgb((18, 14, 36), c3, 0.68)

        return {
            "nom": "Auto (Image)",
            "primaire": _rgb_vers_hex(*c1),
            "secondaire": _rgb_vers_hex(*c2),
            "accent": _rgb_vers_hex(*c3),
            "succes": "#34d399",
            "bordure": _rgb_vers_hex(*bord),
            "bordure_active": _rgb_vers_hex(*c1),
            "selection_bg": _rgb_vers_hex(*sel_bg),
            "badge_bg": _rgb_vers_hex(*badge_bg),
            "surface_bg": _rgb_vers_hex(*surf_bg),
            "surface_2": _rgb_vers_hex(*surf_2),
            "texte_dim": _rgb_vers_hex(*t_dim),
            "texte_muet": _rgb_vers_hex(*t_muet),
            "aurora_1": _rgb_vers_hex(*aur1),
            "aurora_2": _rgb_vers_hex(*aur2),
            "aurora_3": _rgb_vers_hex(*aur3),
        }
    except (OSError, ValueError, TypeError):
        return None


def rendre_pochette_ansi(
    chemin_image: str | Path | None,
    largeur_car: int = 12,
    hauteur_car: int = 6,
    phase_vinyle: int = 0,
    couleur_accent: str = "#38bdf8",
    fond_hex: str = "#090814",
    en_lecture: bool = True,
) -> Text:
    """Rend une pochette d'album arrondie TrueColor (▀) à halo verre ou une platine vinyle articulée."""
    w = max(6, largeur_car)
    h_px = max(6, hauteur_car * 2)
    fond_rgb = _hex_vers_rgb(fond_hex, (9, 8, 20))
    acc_rgb = _hex_vers_rgb(couleur_accent, (56, 189, 248))
    txt = Text()

    if chemin_image and os.path.exists(chemin_image):
        with (
            contextlib.suppress(OSError, ValueError, TypeError),
            Image.open(chemin_image) as im,
        ):
            im_rgb = ImageOps.fit(
                im.convert("RGB"), (w, h_px), Image.Resampling.LANCZOS
            )
            im_rgb = ImageEnhance.Contrast(im_rgb).enhance(1.10)
            im_rgb = ImageEnhance.Color(im_rgb).enhance(1.14)
            arr = np.asarray(im_rgb, dtype=np.float32)

            # Coins arrondis doux + subtil liseré lumineux interne façon Liquid Glass
            r_coin = max(1.6, min(w, h_px) * 0.16)
            xs = np.arange(w, dtype=np.float32) + 0.5
            ys = np.arange(h_px, dtype=np.float32) + 0.5
            dx = np.maximum(0.0, np.maximum(r_coin - xs, xs - (w - r_coin)))
            dy = np.maximum(0.0, np.maximum(r_coin - ys, ys - (h_px - r_coin)))
            dist_c = np.hypot(dx[None, :], dy[:, None]) - r_coin
            alpha = np.clip(0.5 - dist_c * 0.9, 0.0, 1.0)[..., None]

            rim = np.exp(-((dist_c + 0.45) ** 2) / 0.35)[..., None] * 0.24
            acc_arr = np.array(acc_rgb, dtype=np.float32)[None, None, :]
            arr_glow = arr * (1.0 - rim) + np.clip(acc_arr * 1.15, 0, 255) * rim

            fond_arr = np.array(fond_rgb, dtype=np.float32)[None, None, :]
            out = np.clip(arr_glow * alpha + fond_arr * (1.0 - alpha), 0, 255).astype(
                np.uint8
            )
            for y in range(0, h_px, 2):
                y2 = min(h_px - 1, y + 1)
                for x in range(w):
                    r1, g1, b1 = int(out[y, x, 0]), int(out[y, x, 1]), int(out[y, x, 2])
                    r2, g2, b2 = (
                        int(out[y2, x, 0]),
                        int(out[y2, x, 1]),
                        int(out[y2, x, 2]),
                    )
                    txt.append(
                        "▀",
                        style=f"#{r1:02x}{g1:02x}{b1:02x} on #{r2:02x}{g2:02x}{b2:02x}",
                    )
                if y + 2 < h_px:
                    txt.append("\n")
            return txt

    # Platine vinyle TrueColor anti-aliasée avec bras articulé (posé en lecture / relevé en pause)
    cx = (w - 1) / 2.0
    cy = (h_px - 1) / 2.0
    rayon_max = min(cx, cy) * 0.94
    angle_rot = phase_vinyle * 0.35
    ar, ag, ab = acc_rgb

    def _pixel_vinyle(x: int, y: int) -> tuple[int, int, int]:
        # Bras de lecture métallique articulé dans le coin supérieur droit
        if w >= 10:
            ax0, ay0 = w - 2.0, 1.2
            if en_lecture:
                ax1, ay1 = cx + rayon_max * 0.50, cy + rayon_max * 0.16
            else:
                ax1, ay1 = w - 1.4, cy + rayon_max * 0.45
            vx, vy = ax1 - ax0, ay1 - ay0
            seg_len2 = vx * vx + vy * vy
            if seg_len2 > 1e-4:
                t_b = max(0.0, min(1.0, ((x - ax0) * vx + (y - ay0) * vy) / seg_len2))
                px_b, py_b = ax0 + t_b * vx, ay0 + t_b * vy
                d_bras = math.hypot(x - px_b, y - py_b)
                if math.hypot(x - ax0, y - ay0) < 1.15:
                    return _melanger_rgb((205, 214, 232), acc_rgb, 0.30)
                if d_bras < 0.58:
                    return (240, 244, 250) if t_b > 0.85 else (172, 186, 210)

        dx = x - cx
        dy = y - cy
        dist = math.hypot(dx, dy)
        if dist > rayon_max + 0.8:
            return fond_rgb

        if dist < rayon_max * 0.13:
            coul = (238, 242, 248)
        elif dist < rayon_max * 0.38:
            anneau = 0.82 + 0.18 * math.sin(dist * 4.5 + angle_rot * 0.3)
            coul = (
                min(255, int(ar * anneau)),
                min(255, int(ag * anneau)),
                min(255, int(ab * anneau)),
            )
        else:
            ang = math.atan2(dy, dx) + angle_rot
            reflet = (math.sin(ang * 2.0 + 0.4) + 1.0) * 0.5
            reflet2 = (math.cos(ang * 4.0 - 0.7) + 1.0) * 0.25
            sillon = (math.sin(dist * 3.8) + 1.0) * 0.5
            base = int(18 + reflet * 38 + reflet2 * 16 + sillon * 15)
            bord_halo = 0.34 if abs(dist - rayon_max) < 0.80 else 0.0
            coul = (
                min(255, base + int(ar * (0.16 * reflet + bord_halo))),
                min(255, base + int(ag * (0.16 * reflet + bord_halo))),
                min(255, base + int(ab * (0.20 * reflet + bord_halo))),
            )

        if dist > rayon_max - 0.6:
            aa = max(0.0, min(1.0, (rayon_max + 0.6 - dist) / 1.2))
            return _melanger_rgb(fond_rgb, coul, aa)
        return coul

    for y in range(0, h_px, 2):
        y2 = min(h_px - 1, y + 1)
        for x in range(w):
            r1, g1, b1 = _pixel_vinyle(x, y)
            r2, g2, b2 = _pixel_vinyle(x, y2)
            txt.append(
                "▀",
                style=f"#{r1:02x}{g1:02x}{b1:02x} on #{r2:02x}{g2:02x}{b2:02x}",
            )
        if y + 2 < h_px:
            txt.append("\n")
    return txt


class GestionnairePochetteKittyHD:
    """Superpose la pochette d'album en vraie haute résolution via le protocole graphique Kitty (\\x1b_G)."""

    ID_IMAGE = 4242

    def __init__(self):
        self.supporte = bool(
            os.environ.get("KITTY_WINDOW_ID")
            or os.environ.get("KITTY_LISTEN_ON")
            or os.environ.get("TERM") == "xterm-kitty"
        )
        self._fichier_png = f"/tmp/onde_cover_hd_{os.getpid()}.png"
        self._cle_image: tuple[str, int, int] | None = None
        self._cle_placement: tuple[str, int, int, int, int] | None = None
        self._visible = False
        self._b64_chemin = base64.standard_b64encode(
            self._fichier_png.encode("utf-8")
        ).decode("ascii")

    def _ecrire_tty(self, seq: str):
        if not self.supporte:
            return
        with contextlib.suppress(OSError):
            sys.stdout.write(seq)
            sys.stdout.flush()

    def masquer(self):
        if not self.supporte or not self._visible:
            return
        self._visible = False
        self._cle_placement = None
        self._ecrire_tty(f"\x1b_Ga=d,d=i,i={self.ID_IMAGE},q=2\x1b\\")

    def afficher(
        self,
        chemin: str | None,
        col: int,
        row: int,
        cols: int,
        rows: int,
        forcer: bool = False,
    ) -> bool:
        """Affiche la pochette HD aux coordonnées 1-based `(col, row)` sur `(cols, rows)` cellules."""
        if not self.supporte or not chemin or not os.path.isfile(chemin):
            self.masquer()
            return False

        cols = max(4, cols)
        rows = max(2, rows)
        cle_pl = (chemin, col, row, cols, rows)
        try:
            taille_px = max(256, min(640, max(cols * 14, rows * 28)))
            cle_img = (chemin, taille_px, int(os.path.getmtime(chemin)))
            if cle_img != self._cle_image or not os.path.exists(self._fichier_png):
                with Image.open(chemin) as im:
                    im_rgba = ImageOps.fit(
                        im.convert("RGBA"),
                        (taille_px, taille_px),
                        Image.Resampling.LANCZOS,
                    )
                    masque = Image.new("L", (taille_px, taille_px), 0)
                    draw = ImageDraw.Draw(masque)
                    rayon = max(12, taille_px // 11)
                    draw.rounded_rectangle(
                        (0, 0, taille_px - 1, taille_px - 1),
                        radius=rayon,
                        fill=255,
                    )
                    im_rgba.putalpha(masque)
                    im_rgba.save(self._fichier_png, format="PNG")
                self._cle_image = cle_img
                seq = (
                    f"\x1b7\x1b[{row};{col}H"
                    f"\x1b_Ga=T,t=f,f=100,i={self.ID_IMAGE},p=1,c={cols},r={rows},C=1,z=10,q=2;{self._b64_chemin}\x1b\\"
                    f"\x1b8"
                )
                self._ecrire_tty(seq)
                self._cle_placement = cle_pl
                self._visible = True
                return True
        except (OSError, ValueError):
            return False

        if forcer or cle_pl != self._cle_placement or not self._visible:
            # Replacer à chaque frame (p=1 remplace le placement sans recharger le PNG)
            # car Rich Live efface l'écran lors de certains rafraîchissements.
            seq_place = (
                f"\x1b7\x1b[{row};{col}H"
                f"\x1b_Ga=p,i={self.ID_IMAGE},p=1,c={cols},r={rows},C=1,z=10,q=2\x1b\\"
                f"\x1b8"
            )
            self._ecrire_tty(seq_place)
            self._cle_placement = cle_pl
            self._visible = True
        return True

    def nettoyer(self):
        self.masquer()
        if os.path.exists(self._fichier_png):
            with contextlib.suppress(OSError):
                os.remove(self._fichier_png)


class GestionnaireFondPhoto:
    """Gère le fond d'écran photo dans le terminal (Kitty HD GPU + Canevas TrueColor 24-bit)."""

    def __init__(self):
        self.mode_fond = "pochette"  # "photo", "pochette", "aurore", "aucun"
        self.mode_rendu = (
            "kitty"
            if (os.environ.get("KITTY_LISTEN_ON") and shutil.which("kitten"))
            else "canevas"
        )
        self.chemin_photo_perso: str | None = None
        self.chemin_pochette_courante: str | None = None
        self.index_luminosite = 1  # 0.28 par défaut
        self.flou_rayon = 1.8

        # Cache du canevas TrueColor
        self._cle_cache_canevas: tuple[Any, ...] | None = None
        self._styles_bg: list[list[Style]] = []
        self._segments_hb: list[list[Segment]] = []

        # Cache Kitty HD
        self._fichier_png_kitty = f"/tmp/onde_bg_kitty_{os.getpid()}.png"
        self._cle_cache_kitty: tuple[Any, ...] | None = None
        self._kitty_actif = False
        self._verrou_kitty = threading.Lock()

    @property
    def luminosite(self) -> float:
        return NIVEAUX_LUMINOSITE[self.index_luminosite % len(NIVEAUX_LUMINOSITE)][1]

    @property
    def label_luminosite(self) -> str:
        return NIVEAUX_LUMINOSITE[self.index_luminosite % len(NIVEAUX_LUMINOSITE)][0]

    def chemin_image_active(self) -> str | None:
        if self.mode_fond == "photo":
            if self.chemin_photo_perso and os.path.isfile(self.chemin_photo_perso):
                return self.chemin_photo_perso
            return self.chemin_pochette_courante
        if self.mode_fond == "pochette":
            if self.chemin_pochette_courante and os.path.isfile(
                self.chemin_pochette_courante
            ):
                return self.chemin_pochette_courante
            if self.chemin_photo_perso and os.path.isfile(self.chemin_photo_perso):
                return self.chemin_photo_perso
        return None

    def synchroniser_kitty_hd(self):
        """Applique ou retire l'image de fond HD dans Kitty via `kitten @ set-background-image`."""
        if not os.environ.get("KITTY_LISTEN_ON") or not shutil.which("kitten"):
            return

        chemin = self.chemin_image_active()
        doit_activer = (
            self.mode_rendu == "kitty"
            and self.mode_fond in ("photo", "pochette")
            and chemin is not None
        )

        if not doit_activer:
            if self._kitty_actif:
                self._kitty_actif = False
                self._cle_cache_kitty = None
                threading.Thread(
                    target=self._executer_kitten_none, daemon=True
                ).start()
            return

        cle = (chemin, round(self.luminosite, 2))
        if cle == self._cle_cache_kitty and self._kitty_actif:
            return

        self._cle_cache_kitty = cle
        self._kitty_actif = True

        def _tache():
            with self._verrou_kitty:
                try:
                    with Image.open(chemin) as im:
                        im_rgb = ImageOps.fit(
                            im.convert("RGB"),
                            (1280, 720),
                            Image.Resampling.BILINEAR,
                        )
                        im_rgb = im_rgb.filter(ImageFilter.GaussianBlur(8.0))
                        im_rgb = ImageEnhance.Brightness(im_rgb).enhance(
                            self.luminosite
                        )
                        im_rgb.save(self._fichier_png_kitty, format="PNG")
                    r = subprocess.run(
                        [
                            "kitten",
                            "@",
                            "set-background-image",
                            "--no-response",
                            "--layout",
                            "cscaled",
                            self._fichier_png_kitty,
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1.5,
                        check=False,
                    )
                    if r.returncode != 0:
                        self.mode_rendu = "canevas"
                except (OSError, subprocess.SubprocessError, ValueError):
                    self.mode_rendu = "canevas"

        threading.Thread(target=_tache, daemon=True).start()

    def _executer_kitten_none(self):
        with self._verrou_kitty, contextlib.suppress(
            OSError, subprocess.SubprocessError
        ):
            subprocess.run(
                ["kitten", "@", "set-background-image", "--no-response", "none"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
                check=False,
            )

    def nettoyer(self):
        """Restaure le fond de Kitty et supprime le fichier temporaire à la fermeture."""
        if self._kitty_actif and os.environ.get("KITTY_LISTEN_ON"):
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["kitten", "@", "set-background-image", "--no-response", "none"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.6,
                    check=False,
                )
        if os.path.exists(self._fichier_png_kitty):
            with contextlib.suppress(OSError):
                os.remove(self._fichier_png_kitty)

    def _grille_depuis_array(
        self, arr_px: np.ndarray, w: int, h: int
    ) -> tuple[list[list[Style]], list[list[Segment]]]:
        """Convertit un tableau RGB `(h*2, w, 3)` uint8 en styles et demi-blocs cachés."""
        cache_bg: dict[str, Style] = {}
        cache_hb: dict[tuple[str, str], Segment] = {}
        styles_bg: list[list[Style]] = []
        segments_hb: list[list[Segment]] = []

        haut = arr_px[0 : h * 2 : 2]
        bas = arr_px[1 : h * 2 : 2]
        moy = ((haut.astype(np.uint16) + bas.astype(np.uint16)) >> 1).astype(np.uint8)

        for y in range(h):
            row_bg: list[Style] = []
            row_hb: list[Segment] = []
            h_row = haut[y]
            b_row = bas[y]
            m_row = moy[y]
            for x in range(w):
                hex_m = f"#{int(m_row[x, 0]):02x}{int(m_row[x, 1]):02x}{int(m_row[x, 2]):02x}"
                st = cache_bg.get(hex_m)
                if st is None:
                    st = Style(bgcolor=hex_m)
                    cache_bg[hex_m] = st
                row_bg.append(st)

                hex_1 = f"#{int(h_row[x, 0]):02x}{int(h_row[x, 1]):02x}{int(h_row[x, 2]):02x}"
                hex_2 = f"#{int(b_row[x, 0]):02x}{int(b_row[x, 1]):02x}{int(b_row[x, 2]):02x}"
                cle_hb = (hex_1, hex_2)
                seg = cache_hb.get(cle_hb)
                if seg is None:
                    seg = Segment("▀", Style(color=hex_1, bgcolor=hex_2))
                    cache_hb[cle_hb] = seg
                row_hb.append(seg)
            styles_bg.append(row_bg)
            segments_hb.append(row_hb)
        return styles_bg, segments_hb

    def obtenir_grille_canevas(
        self,
        largeur: int,
        hauteur: int,
        palette: dict[str, str] | str = "#38bdf8",
    ) -> tuple[list[list[Style]], list[list[Segment]]] | None:
        """Retourne les styles et segments TrueColor pré-calculés pour la taille du terminal."""
        if self.mode_fond == "aucun":
            return None
        chemin = self.chemin_image_active()
        if (
            self.mode_rendu == "kitty"
            and self.mode_fond in ("photo", "pochette")
            and chemin
            and os.environ.get("KITTY_LISTEN_ON")
        ):
            return None

        if self.mode_fond in ("photo", "pochette") and not chemin:
            mode_effectif = "aurore"
        else:
            mode_effectif = self.mode_fond

        if isinstance(palette, dict):
            c_prim = palette.get("primaire", "#38bdf8")
            c_surf = palette.get("surface_bg", "#070713")
            c_a1 = palette.get("aurora_1", palette.get("primaire", "#7c3aed"))
            c_a2 = palette.get("aurora_2", palette.get("secondaire", "#db2777"))
            c_a3 = palette.get("aurora_3", palette.get("accent", "#0891b2"))
        else:
            c_prim = palette
            c_surf = "#070713"
            c_a1 = palette
            c_a2 = "#db2777"
            c_a3 = "#0891b2"

        w = max(10, largeur)
        h = max(6, hauteur)
        cle = (
            mode_effectif,
            chemin,
            w,
            h,
            round(self.luminosite, 2),
            c_prim,
            c_surf,
            c_a1,
            c_a2,
            c_a3,
        )
        if cle == self._cle_cache_canevas and self._styles_bg:
            return self._styles_bg, self._segments_hb

        try:
            if mode_effectif in ("photo", "pochette") and chemin:
                with Image.open(chemin) as im:
                    im_rgb = ImageOps.fit(
                        im.convert("RGB"),
                        (w, h * 2),
                        Image.Resampling.BILINEAR,
                    )
                    im_rgb = im_rgb.filter(
                        ImageFilter.GaussianBlur(self.flou_rayon)
                    )
                    im_rgb = ImageEnhance.Brightness(im_rgb).enhance(
                        self.luminosite
                    )
                    arr_px = np.asarray(im_rgb, dtype=np.float32)
                    # Subtile teinte surface pour un contraste irréprochable
                    base = np.array(_hex_vers_rgb(c_surf, (7, 7, 19)), dtype=np.float32)
                    arr_px = np.clip(arr_px * 0.88 + base[None, None, :] * 0.12, 0, 255).astype(
                        np.uint8
                    )
                    styles_bg, segments_hb = self._grille_depuis_array(arr_px, w, h)
            else:
                # Aurore Liquid Glass 2.0 : mesh 4-blobs + reflet verre supérieur + tramage Bayer 2×2
                ny = np.linspace(0.0, 1.0, h * 2, dtype=np.float32)[:, None]
                nx = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]

                b1 = np.exp(-((nx - 0.14) ** 2 / 0.20 + (ny - 0.18) ** 2 / 0.22))
                b2 = np.exp(-((nx - 0.86) ** 2 / 0.24 + (ny - 0.26) ** 2 / 0.26))
                b3 = np.exp(-((nx - 0.50) ** 2 / 0.30 + (ny - 0.88) ** 2 / 0.24))
                b4 = np.exp(-((nx - 0.68) ** 2 / 0.20 + (ny - 0.52) ** 2 / 0.22))
                voile_haut = np.exp(-(ny**2) / 0.035) * 0.12
                onde_soie = 0.06 * np.sin(nx * 3.4 + ny * 2.4) + 0.06

                surf = np.array(_hex_vers_rgb(c_surf, (7, 7, 19)), dtype=np.float32)
                rgb1 = np.array(_hex_vers_rgb(c_a1, (124, 58, 237)), dtype=np.float32)
                rgb2 = np.array(_hex_vers_rgb(c_a2, (219, 39, 119)), dtype=np.float32)
                rgb3 = np.array(_hex_vers_rgb(c_a3, (8, 145, 178)), dtype=np.float32)
                rgb_p = np.array(_hex_vers_rgb(c_prim, (192, 132, 252)), dtype=np.float32)

                lum = max(0.18, min(0.78, self.luminosite * 1.48))
                champ = (
                    surf[None, None, :] * 0.88
                    + (
                        b1[..., None] * rgb1[None, None, :] * 0.34
                        + b2[..., None] * rgb2[None, None, :] * 0.30
                        + b3[..., None] * rgb3[None, None, :] * 0.28
                        + b4[..., None] * rgb_p[None, None, :] * 0.14
                        + onde_soie[..., None] * rgb1[None, None, :] * 0.08
                        + voile_haut[..., None] * rgb_p[None, None, :] * 0.35
                    )
                    * lum
                )
                # Tramage ordonné Bayer 2×2 pour supprimer 100 % du banding sur dégradés sombres
                bayer = np.array([[-0.375, 0.125], [0.375, -0.125]], dtype=np.float32)
                trame = np.tile(bayer, (h + 1, (w + 1) // 2 + 1))[: h * 2, :w]
                arr_px = np.clip(champ + trame[..., None], 0, 255).astype(np.uint8)
                styles_bg, segments_hb = self._grille_depuis_array(arr_px, w, h)

            self._cle_cache_canevas = cle
            self._styles_bg = styles_bg
            self._segments_hb = segments_hb
            return self._styles_bg, self._segments_hb
        except (OSError, ValueError, TypeError):
            return None


class ToileFondPhoto:
    """Compositeur Rich sans bande : applique le fond TrueColor cellule par cellule."""

    def __init__(
        self,
        layout: Layout,
        gestionnaire_fond: GestionnaireFondPhoto,
        palette: dict[str, str] | str,
    ):
        self.layout = layout
        self.gestionnaire_fond = gestionnaire_fond
        self.palette = palette

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        w = options.max_width
        h = options.height or console.size.height
        grille = self.gestionnaire_fond.obtenir_grille_canevas(
            w, h, self.palette
        )
        if grille is None:
            yield from console.render(self.layout, options)
            return

        styles_bg, segments_hb = grille
        lignes = console.render_lines(
            self.layout, options, pad=True, new_lines=False
        )
        nb_lignes = len(lignes)
        cache_fusion: dict[tuple[int, int], Style] = {}

        for y, ligne in enumerate(lignes):
            if y >= len(styles_bg):
                yield from ligne
                if y < nb_lignes - 1:
                    yield Segment.line()
                continue

            row_bg = styles_bg[y]
            row_hb = segments_hb[y]
            row_w = min(w, len(row_bg))
            x = 0
            out_ligne: list[Segment] = []
            for seg in ligne:
                txt, sty, ctrl = seg.text, seg.style, seg.control
                if ctrl or not txt:
                    out_ligne.append(seg)
                    continue
                if sty is not None and sty.bgcolor is not None:
                    out_ligne.append(seg)
                    x += cell_len(txt)
                    continue
                if txt.isspace():
                    n_sp = len(txt)
                    if x < row_w:
                        fin = min(row_w, x + n_sp)
                        out_ligne.extend(row_hb[x:fin])
                        reste = n_sp - (fin - x)
                        if reste > 0:
                            out_ligne.append(Segment(" " * reste, sty))
                    else:
                        out_ligne.append(seg)
                    x += n_sp
                    continue

                sty_id = id(sty) if sty is not None else 0
                for ch in txt:
                    cl = cell_len(ch)
                    bg_s = row_bg[min(max(0, x), row_w - 1)]
                    cle = (sty_id, id(bg_s))
                    fus = cache_fusion.get(cle)
                    if fus is None:
                        fus = (sty + bg_s) if sty is not None else bg_s
                        cache_fusion[cle] = fus
                    out_ligne.append(Segment(ch, fus))
                    x += cl
            yield from Segment.simplify(out_ligne)
            if y < nb_lignes - 1:
                yield Segment.line()


# ── Moteur audio MPV via IPC Socket ──────────────────────────────────────────


class LecteurMPV:
    """Contrôleur audio autonome utilisant mpv en arrière-plan via IPC UNIX."""

    def __init__(
        self,
        callback_fin: Callable[[], None] | None = None,
        callback_pause: Callable[[bool], None] | None = None,
        callback_seek: Callable[[float], None] | None = None,
        callback_duree: Callable[[float], None] | None = None,
    ):
        self.sock_path = f"/tmp/onde_mpv_{os.getpid()}_{random.randint(1000, 9999)}.sock"
        self.callback_fin = callback_fin
        self.callback_pause = callback_pause
        self.callback_seek = callback_seek
        self.callback_duree = callback_duree
        self._verrou = threading.Lock()
        self.en_cours = True
        self.position = 0.0
        self.duree = 0.0
        self.en_pause = False
        self.mute = False
        self.volume = 80.0
        self.gain_db = 0.0
        self.vitesse = 1.0
        self.audio_device = "auto"
        self.fichier_actuel: str | None = None
        self.icy_title: str = ""
        self._dernier_eof_ts = 0.0
        self._req_id = 100
        self._reponses_ipc: dict[int, list[Any]] = {}
        self._proc: subprocess.Popen | None = None
        self._sock: socket.socket | None = None
        self._demarrer_mpv()

    def _demarrer_mpv(self):
        if os.path.exists(self.sock_path):
            with contextlib.suppress(OSError):
                os.remove(self.sock_path)

        cmd = [
            "mpv",
            "--idle",
            "--no-video",
            "--no-terminal",
            f"--input-ipc-server={self.sock_path}",
            f"--volume={int(self.volume)}",
            "--audio-pitch-correction=yes",
            "--gapless-audio=yes",
        ]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        for _ in range(50):
            if os.path.exists(self.sock_path):
                break
            time.sleep(0.02)

        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(self.sock_path)
            self._sock.settimeout(0.1)
        except (OSError, TimeoutError):
            self._sock = None

        if self._sock:
            threading.Thread(target=self._boucle_ecoute, daemon=True).start()
            self._abonner_proprietes()
            if self.audio_device and self.audio_device != "auto":
                self.envoyer(["set_property", "audio-device", self.audio_device])

    def _abonner_proprietes(self):
        props = [
            "time-pos",
            "duration",
            "pause",
            "volume",
            "mute",
            "eof-reached",
            "media-title",
        ]
        for idx, p in enumerate(props, 1):
            self.envoyer(["observe_property", idx, p])

    def envoyer(self, commande: list[Any]):
        if not self._sock or not self.en_cours:
            return
        with contextlib.suppress(OSError, BrokenPipeError):
            msg = json.dumps({"command": commande}).encode("utf-8") + b"\n"
            with self._verrou:
                self._sock.sendall(msg)

    def obtenir_propriete(self, nom: str, timeout: float = 0.35) -> Any:
        if not self._sock or not self.en_cours:
            return None
        ev = threading.Event()
        with self._verrou:
            self._req_id += 1
            rid = self._req_id
            slot: list[Any] = [ev, None, None]
            self._reponses_ipc[rid] = slot
            try:
                msg = (
                    json.dumps({"command": ["get_property", nom], "request_id": rid}).encode(
                        "utf-8"
                    )
                    + b"\n"
                )
                self._sock.sendall(msg)
            except (OSError, BrokenPipeError):
                self._reponses_ipc.pop(rid, None)
                return None
        try:
            if ev.wait(timeout) and slot[2] == "success":
                return slot[1]
            return None
        finally:
            with self._verrou:
                self._reponses_ipc.pop(rid, None)

    def _declencher_fin(self):
        maintenant = time.monotonic()
        if maintenant - self._dernier_eof_ts >= 0.45 and self.callback_fin:
            self._dernier_eof_ts = maintenant
            self.callback_fin()

    def _boucle_ecoute(self):
        tampon = ""
        while self.en_cours and self._sock:
            try:
                morceau = self._sock.recv(4096).decode("utf-8", errors="replace")
                if not morceau:
                    break
                tampon += morceau
                while "\n" in tampon:
                    ligne, tampon = tampon.split("\n", 1)
                    if not ligne.strip():
                        continue
                    with contextlib.suppress(Exception):
                        msg = json.loads(ligne)
                        ev = msg.get("event")
                        if not ev and "request_id" in msg:
                            rid = msg["request_id"]
                            with self._verrou:
                                slot = self._reponses_ipc.get(rid)
                            if slot is not None:
                                slot[1] = msg.get("data")
                                slot[2] = msg.get("error")
                                slot[0].set()
                            continue
                        if ev == "property-change":
                            nom = msg.get("name")
                            val = msg.get("data")
                            if nom == "time-pos" and val is not None:
                                self.position = float(val)
                            elif nom == "duration" and val is not None:
                                self.duree = float(val)
                                if self.callback_duree:
                                    self.callback_duree(self.duree)
                            elif nom == "pause" and val is not None:
                                nouv_pause = bool(val)
                                self.en_pause = nouv_pause
                                if self.callback_pause:
                                    self.callback_pause(nouv_pause)
                            elif nom == "volume" and val is not None:
                                self.volume = float(val)
                            elif nom == "mute" and val is not None:
                                self.mute = bool(val)
                            elif nom == "media-title" and val is not None:
                                self.icy_title = str(val).strip()
                            elif nom == "eof-reached" and val is True:
                                self._declencher_fin()
                        elif ev in ("playback-restart", "seek"):
                            if self.callback_seek:
                                self.callback_seek(self.position)
                        elif ev == "end-file" and msg.get("reason") == "eof":
                            self._declencher_fin()
            except TimeoutError:
                continue
            except OSError:
                break

    def jouer(self, chemin: str, position_initiale: float = 0.0, duree_connue: float = 0.0):
        self.fichier_actuel = chemin
        self.position = position_initiale
        if duree_connue > 0:
            self.duree = duree_connue
        self.icy_title = ""
        self._dernier_eof_ts = time.monotonic()
        self.en_pause = False
        self.envoyer(["loadfile", chemin, "replace"])
        if position_initiale > 0.5:
            self.envoyer(["seek", position_initiale, "absolute"])
        self.envoyer(["set_property", "pause", False])

    def basculer_pause(self):
        self.en_pause = not self.en_pause
        self.envoyer(["set_property", "pause", self.en_pause])

    def basculer_muet(self) -> bool:
        self.mute = not self.mute
        self.envoyer(["set_property", "mute", self.mute])
        return self.mute

    def definir_muet(self, etat: bool) -> bool:
        self.mute = bool(etat)
        self.envoyer(["set_property", "mute", self.mute])
        return self.mute

    def aller_a(self, secondes: float):
        cible = max(0.0, secondes)
        self.position = cible
        self.envoyer(["seek", cible, "absolute"])

    def reculer(self, secondes: float = 5.0):
        self.position = max(0.0, self.position - secondes)
        self.envoyer(["seek", -secondes, "relative"])

    def avancer(self, secondes: float = 5.0):
        plafond = self.duree if self.duree > 0 else 1e9
        self.position = min(plafond, max(0.0, self.position + secondes))
        self.envoyer(["seek", secondes, "relative"])

    def ajuster_volume(self, delta: float):
        nouveau = max(0.0, min(100.0, self.volume + delta))
        self.volume = nouveau
        self.envoyer(["set_property", "volume", nouveau])

    def definir_volume(self, valeur: float):
        nouveau = max(0.0, min(100.0, valeur))
        self.volume = nouveau
        self.envoyer(["set_property", "volume", nouveau])

    def definir_gain_db(self, db: float):
        cible = max(-36.0, min(12.0, round(db, 2)))
        if abs(cible - self.gain_db) >= 0.05:
            self.gain_db = cible
            self.envoyer(["set_property", "volume-gain", cible])

    def definir_filtre_audio(self, filtre: str):
        self.envoyer(["set_property", "af", filtre])

    def definir_vitesse(self, vitesse: float):
        self.vitesse = max(0.5, min(2.0, round(vitesse, 2)))
        self.envoyer(["set_property", "speed", self.vitesse])

    def definir_peripherique_audio(self, dev: str):
        cible = (dev or "auto").strip() or "auto"
        self.audio_device = cible
        self.envoyer(["set_property", "audio-device", cible])

    def lister_peripheriques_audio(self) -> list[tuple[str, str]]:
        brut = self.obtenir_propriete("audio-device-list", timeout=0.45)
        res: list[tuple[str, str]] = []
        if isinstance(brut, list):
            for item in brut:
                if isinstance(item, dict):
                    nom = str(item.get("name") or "").strip()
                    desc = str(item.get("description") or nom).strip()
                    if nom:
                        res.append((nom, desc))
        if not res:
            res.append(("auto", "Automatique (Système)"))
        return res

    def arreter(self):
        self.envoyer(["stop"])
        self.position = 0.0

    def fermer(self):
        self.en_cours = False
        with contextlib.suppress(OSError):
            self.envoyer(["quit"])
        if self._sock:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=0.3)
            except (subprocess.SubprocessError, OSError):
                with contextlib.suppress(OSError):
                    self._proc.kill()
            self._proc = None
        if os.path.exists(self.sock_path):
            with contextlib.suppress(OSError):
                os.remove(self.sock_path)


# ── Analyseur de Spectre Audio FFT Temps Réel (PipeWire / PulseAudio) ────────


class AnalyseurSpectreTempsReel:
    """Capture légère du flux audio de sortie (parec) et calcul FFT temps réel (64 bandes)."""

    NB_BANDES = 64
    TAUX_ECHANTILLONNAGE = 16000
    TAILLE_BLOC = 512  # 512 échantillons stéréo = 32 ms (~31 FPS)

    def __init__(self):
        self.actif = True
        self.signal_temps_reel = False
        self.bandes = np.zeros(self.NB_BANDES, dtype=np.float32)
        self.niveau_gauche = 0.0
        self.niveau_droit = 0.0
        self.impact_basses = 0.0
        self._proc: subprocess.Popen | None = None
        self._verrou = threading.Lock()
        self._fenetre = np.hanning(self.TAILLE_BLOC).astype(np.float32)

        # Précalcul des limites des 64 bandes logarithmiques (de 35 Hz à 7600 Hz)
        freqs = np.fft.rfftfreq(self.TAILLE_BLOC, d=1.0 / self.TAUX_ECHANTILLONNAGE)
        bornes = np.geomspace(35.0, 7600.0, self.NB_BANDES + 1)
        self._tranches: list[tuple[int, int, float]] = []
        for i in range(self.NB_BANDES):
            idx = np.where((freqs >= bornes[i]) & (freqs < bornes[i + 1]))[0]
            if len(idx) == 0:
                cible = int(
                    np.argmin(np.abs(freqs - 0.5 * (bornes[i] + bornes[i + 1])))
                )
                deb, fin = cible, cible + 1
            else:
                deb, fin = int(idx[0]), int(idx[-1]) + 1
            # Compensation psychoacoustique (+3 dB/octave pour équilibrer aigus/basses)
            freq_centre = 0.5 * (bornes[i] + bornes[i + 1])
            gain_eq = float((freq_centre / 180.0) ** 0.34) * 3.8
            self._tranches.append((deb, fin, gain_eq))

        if shutil.which("parec"):
            threading.Thread(
                target=self._boucle_capture, daemon=True, name="onde-fft"
            ).start()

    def _boucle_capture(self):
        octets_bloc = self.TAILLE_BLOC * 2 * 2  # int16 stéréo
        while self.actif:
            try:
                self._proc = subprocess.Popen(
                    [
                        "parec",
                        f"--rate={self.TAUX_ECHANTILLONNAGE}",
                        "--channels=2",
                        "--format=s16le",
                        "--latency-msec=35",
                        "-d",
                        "@DEFAULT_MONITOR@",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                if not self._proc.stdout:
                    break
                silence_compteur = 0
                while self.actif and self._proc.poll() is None:
                    brut = self._proc.stdout.read(octets_bloc)
                    if not brut or len(brut) < octets_bloc:
                        break
                    pcm = (
                        np.frombuffer(brut, dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )
                    gauche = pcm[0::2]
                    droit = pcm[1::2]
                    rms_g = float(np.sqrt(np.mean(gauche * gauche)))
                    rms_d = float(np.sqrt(np.mean(droit * droit)))
                    energie = max(rms_g, rms_d)

                    if energie < 0.0008:
                        silence_compteur += 1
                        if silence_compteur > 12:
                            with self._verrou:
                                self.signal_temps_reel = False
                                self.bandes *= 0.75
                                self.niveau_gauche *= 0.75
                                self.niveau_droit *= 0.75
                                self.impact_basses *= 0.75
                        continue

                    silence_compteur = 0
                    mono = 0.5 * (gauche + droit) * self._fenetre
                    spectre = np.abs(np.fft.rfft(mono)) / (self.TAILLE_BLOC * 0.22)

                    nouv = np.empty(self.NB_BANDES, dtype=np.float32)
                    for i, (deb, fin, gain_eq) in enumerate(self._tranches):
                        val = float(np.mean(spectre[deb:fin])) * gain_eq
                        # Compression logarithmique douce pour un rendu visuel musical
                        nouv[i] = min(1.0, math.log1p(val * 4.2) / math.log1p(4.2))

                    with self._verrou:
                        self.signal_temps_reel = True
                        # Attaque rapide (0.68), relâchement fluide (0.34)
                        hausse = nouv > self.bandes
                        self.bandes = np.where(
                            hausse,
                            self.bandes * 0.32 + nouv * 0.68,
                            self.bandes * 0.66 + nouv * 0.34,
                        )
                        self.niveau_gauche = min(
                            1.0, self.niveau_gauche * 0.4 + rms_g * 2.6 * 0.6
                        )
                        self.niveau_droit = min(
                            1.0, self.niveau_droit * 0.4 + rms_d * 2.6 * 0.6
                        )
                        self.impact_basses = float(np.mean(self.bandes[:6]))
            except (OSError, ValueError):
                time.sleep(1.0)
            finally:
                self._arreter_proc()
            if self.actif:
                time.sleep(0.5)

    def echantillonner(self, largeur: int) -> tuple[list[float], bool, float, float]:
        """Retourne `largeur` bandes interpolées, (est_temps_reel, rms_g, rms_d)."""
        with self._verrou:
            if not self.signal_temps_reel or largeur <= 0:
                return [], False, self.niveau_gauche, self.niveau_droit
            x_src = np.linspace(0.0, 1.0, self.NB_BANDES)
            x_dst = np.linspace(0.0, 1.0, largeur)
            vals = np.interp(x_dst, x_src, self.bandes)
            return (
                [float(v) for v in vals],
                True,
                self.niveau_gauche,
                self.niveau_droit,
            )

    def _arreter_proc(self):
        if self._proc:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                self._proc.terminate()
                self._proc.wait(timeout=0.2)
            self._proc = None

    def fermer(self):
        self.actif = False
        self._arreter_proc()


# ── Service DBus MPRIS2 (Touches multimédias, playerctl & Île Caelestia) ─────

MPRIS_INTROSPECTION_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg direction="in" name="Offset" type="x"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri">
      <arg direction="in" name="Uri" type="s"/>
    </method>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""


class ServiceMPRIS2:
    """Expose Onde CLI sur DBus (org.mpris.MediaPlayer2.onde) pour Caelestia & playerctl."""

    CHEMIN_OBJET = "/org/mpris/MediaPlayer2"

    def __init__(self, app: "ApplicationOndeCLI"):
        self.app = app
        self._conn: Any = None
        self._loop: Any = None
        self._reg_ids: list[int] = []
        self._own_id: int = 0
        self._Gio: Any = None
        self._GLib: Any = None
        self._demarrer()

    def _demarrer(self):
        try:
            from gi.repository import Gio, GLib

            self._Gio = Gio
            self._GLib = GLib
            threading.Thread(
                target=self._boucle_dbus, daemon=True, name="onde-mpris"
            ).start()
        except ImportError:
            pass

    def _boucle_dbus(self):
        Gio, GLib = self._Gio, self._GLib
        try:
            self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node_info = Gio.DBusNodeInfo.new_for_xml(MPRIS_INTROSPECTION_XML)
            for iface in node_info.interfaces:
                reg_id = self._conn.register_object(
                    self.CHEMIN_OBJET,
                    iface,
                    self._sur_appel_methode,
                    self._sur_lecture_propriete,
                    self._sur_ecriture_propriete,
                )
                self._reg_ids.append(reg_id)

            nom_bus = "org.mpris.MediaPlayer2.onde"

            def _sur_nom_acquis(_conn: Any, _name: str):
                self.notifier_changement(["Metadata", "PlaybackStatus", "Volume", "Rate", "LoopStatus", "Shuffle"])
                self.emettre_seeked(self.app.lecteur.position)

            self._own_id = Gio.bus_own_name_on_connection(
                self._conn,
                nom_bus,
                Gio.BusNameOwnerFlags.REPLACE | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
                _sur_nom_acquis,
                None,
            )
            self._loop = GLib.MainLoop()
            self._loop.run()
        except Exception:  # noqa: BLE001
            self._conn = None

    def _construire_metadata(self) -> Any:
        GLib = self._GLib
        p = self.app.piste_courante
        if not p:
            return {
                "mpris:trackid": GLib.Variant(
                    "o", "/org/mpris/MediaPlayer2/TrackList/NoTrack"
                )
            }
        pid = p.get("id") or 0
        duree_s = float(self.app.lecteur.duree or p.get("duree") or 0.0)
        meta: dict[str, Any] = {
            "mpris:trackid": GLib.Variant(
                "o", f"/org/mpris/MediaPlayer2/Track/{pid}"
            ),
            "mpris:length": GLib.Variant("x", int(duree_s * 1_000_000)),
            "xesam:title": GLib.Variant("s", str(p.get("titre") or "Sans titre")),
            "xesam:artist": GLib.Variant(
                "as", [str(p.get("artiste") or "Artiste inconnu")]
            ),
            "xesam:album": GLib.Variant("s", str(p.get("album") or "")),
        }
        chemin = p.get("chemin")
        if chemin and os.path.exists(chemin):
            with contextlib.suppress(ValueError, OSError):
                meta["xesam:url"] = GLib.Variant(
                    "s", Path(chemin).resolve().as_uri()
                )
        pochette = self.app.chemin_pochette_piste(p)
        if pochette and os.path.exists(pochette):
            with contextlib.suppress(ValueError, OSError):
                meta["mpris:artUrl"] = GLib.Variant(
                    "s", Path(pochette).resolve().as_uri()
                )
        return meta

    def _statut_lecture(self) -> str:
        if not self.app.lecteur.fichier_actuel:
            return "Stopped"
        return "Paused" if self.app.lecteur.en_pause else "Playing"

    def _statut_boucle(self) -> str:
        return {"non": "None", "un": "Track", "tout": "Playlist"}.get(
            self.app.mode_repetition, "Playlist"
        )

    def _sur_lecture_propriete(
        self, _conn: Any, _sender: str, _path: str, iface: str, prop: str
    ) -> Any:
        GLib = self._GLib
        if iface == "org.mpris.MediaPlayer2":
            table_root = {
                "CanQuit": GLib.Variant("b", True),
                "CanRaise": GLib.Variant("b", False),
                "HasTrackList": GLib.Variant("b", False),
                "Identity": GLib.Variant("s", "Onde"),
                "DesktopEntry": GLib.Variant("s", "onde"),
                "SupportedUriSchemes": GLib.Variant("as", ["file"]),
                "SupportedMimeTypes": GLib.Variant(
                    "as", ["audio/mpeg", "audio/flac", "audio/ogg", "audio/mp4"]
                ),
            }
            return table_root.get(prop)

        if iface == "org.mpris.MediaPlayer2.Player":
            if prop == "PlaybackStatus":
                return GLib.Variant("s", self._statut_lecture())
            if prop == "LoopStatus":
                return GLib.Variant("s", self._statut_boucle())
            if prop == "Rate":
                return GLib.Variant("d", float(self.app.lecteur.vitesse))
            if prop == "Shuffle":
                return GLib.Variant("b", bool(self.app.mode_aleatoire))
            if prop == "Metadata":
                return GLib.Variant("a{sv}", self._construire_metadata())
            if prop == "Volume":
                return GLib.Variant("d", float(self.app.lecteur.volume) / 100.0)
            if prop == "Position":
                pos_eff = max(0.0, self.app.lecteur.position + self.app.decalage_paroles)
                return GLib.Variant(
                    "x", int(pos_eff * 1_000_000)
                )
            if prop in ("MinimumRate", "MaximumRate"):
                return GLib.Variant("d", 0.5 if prop == "MinimumRate" else 2.0)
            if prop in (
                "CanGoNext",
                "CanGoPrevious",
                "CanPlay",
                "CanPause",
                "CanSeek",
                "CanControl",
            ):
                return GLib.Variant("b", True)
        return None

    def _sur_ecriture_propriete(
        self,
        _conn: Any,
        _sender: str,
        _path: str,
        iface: str,
        prop: str,
        valeur: Any,
    ) -> bool:
        if iface != "org.mpris.MediaPlayer2.Player":
            return False
        if prop == "Volume":
            v = float(valeur.unpack()) * 100.0
            self.app.lecteur.definir_volume(v)
            self.notifier_changement(["Volume"])
            return True
        if prop == "Shuffle":
            self.app.mode_aleatoire = bool(valeur.unpack())
            self.notifier_changement(["Shuffle"])
            return True
        if prop == "LoopStatus":
            s = str(valeur.unpack())
            self.app.mode_repetition = {
                "None": "non",
                "Track": "un",
                "Playlist": "tout",
            }.get(s, "tout")
            self.notifier_changement(["LoopStatus"])
            return True
        if prop == "Rate":
            self.app.lecteur.definir_vitesse(float(valeur.unpack()))
            self.notifier_changement(["Rate"])
            return True
        return False

    def _sur_appel_methode(
        self,
        _conn: Any,
        _sender: str,
        _path: str,
        iface: str,
        methode: str,
        params: Any,
        invocation: Any,
    ):
        if iface == "org.mpris.MediaPlayer2":
            if methode == "Quit":
                self.app.lecteur.en_cours = False
            invocation.return_value(None)
            return

        if iface == "org.mpris.MediaPlayer2.Player":
            if methode == "PlayPause":
                if (
                    self.app.lecteur.fichier_actuel is None
                    and self.app.piste_courante
                ):
                    self.app.jouer_piste(self.app.piste_courante)
                else:
                    self.app.lecteur.basculer_pause()
                self.notifier_changement(["PlaybackStatus"])
            elif methode == "Play":
                if (
                    self.app.lecteur.fichier_actuel is None
                    and self.app.piste_courante
                ):
                    self.app.jouer_piste(self.app.piste_courante)
                elif self.app.lecteur.en_pause:
                    self.app.lecteur.basculer_pause()
                self.notifier_changement(["PlaybackStatus"])
            elif methode == "Pause":
                if not self.app.lecteur.en_pause:
                    self.app.lecteur.basculer_pause()
                self.notifier_changement(["PlaybackStatus"])
            elif methode == "Stop":
                self.app.lecteur.arreter()
                self.notifier_changement(["PlaybackStatus"])
            elif methode == "Next":
                self.app.piste_suivante()
            elif methode == "Previous":
                self.app.piste_precedente()
            elif methode == "Seek":
                (offset_us,) = params.unpack()
                nouv_pos = max(
                    0.0, self.app.lecteur.position + (offset_us / 1_000_000.0)
                )
                self.app.lecteur.aller_a(nouv_pos)
                self.emettre_seeked(nouv_pos)
            elif methode == "SetPosition":
                (_track_id, pos_us) = params.unpack()
                nouv_pos = max(0.0, pos_us / 1_000_000.0)
                self.app.lecteur.aller_a(nouv_pos)
                self.emettre_seeked(nouv_pos)
            elif methode == "OpenUri":
                (uri,) = params.unpack()
                if str(uri).startswith("file://"):
                    from urllib.parse import unquote

                    ch = unquote(str(uri)[7:])
                    p = chercher_piste(ch)
                    if p:
                        self.app.jouer_piste(p)
            invocation.return_value(None)

    def notifier_changement(self, proprietes: list[str]):
        """Émet org.freedesktop.DBus.Properties.PropertiesChanged."""
        if not self._conn or not self._GLib:
            return
        GLib = self._GLib
        changements: dict[str, Any] = {}
        for p in proprietes:
            val = self._sur_lecture_propriete(
                self._conn,
                "",
                self.CHEMIN_OBJET,
                "org.mpris.MediaPlayer2.Player",
                p,
            )
            if val is not None:
                changements[p] = val
        if not changements:
            return
        with contextlib.suppress(Exception):
            self._conn.emit_signal(
                None,
                self.CHEMIN_OBJET,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                GLib.Variant(
                    "(sa{sv}as)",
                    ("org.mpris.MediaPlayer2.Player", changements, []),
                ),
            )

    def emettre_seeked(self, secondes: float):
        if not self._conn or not self._GLib:
            return
        pos_eff = max(0.0, secondes + self.app.decalage_paroles)
        with contextlib.suppress(Exception):
            self._conn.emit_signal(
                None,
                self.CHEMIN_OBJET,
                "org.mpris.MediaPlayer2.Player",
                "Seeked",
                self._GLib.Variant("(x)", (int(pos_eff * 1_000_000),)),
            )

    def fermer(self):
        if self._Gio and self._own_id:
            with contextlib.suppress(Exception):
                self._Gio.bus_unown_name(self._own_id)
            self._own_id = 0
        if self._loop:
            with contextlib.suppress(Exception):
                self._loop.quit()
            self._loop = None


# ── Entrée Clavier non-bloquante ─────────────────────────────────────────────


class LecteurClavier:
    """Gestionnaire d'entrée brute non-bloquante avec support universel :
    - ANSI standard (\\x1b[A, \\x1b[B, F1-F10, Shift+Tab, Alt+Entrée)
    - Protocole Kitty (\\x1b[...u pour touches et modificateurs)
    - Collage encadré (Bracketed Paste \\x1b[200~...\\x1b[201~)
    - Souris SGR 1006 (molette et clic gauche) et UTF-8 complet.
    """

    def __init__(self):
        self.ancien_param = None
        self.fd = sys.stdin.fileno()

    def __enter__(self):
        if sys.stdin.isatty():
            self.ancien_param = termios.tcgetattr(self.fd)
            mode = termios.tcgetattr(self.fd)
            mode[0] = mode[0] & ~termios.IXON
            mode[3] = mode[3] & ~termios.ECHO & ~termios.ICANON
            mode[6][termios.VMIN] = 0
            mode[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, mode)
            with contextlib.suppress(Exception):
                sys.stdout.write("\x1b[?1000h\x1b[?1006h\x1b[?2004h")
                sys.stdout.flush()
        return self

    def __exit__(self, *args):
        if sys.stdin.isatty():
            with contextlib.suppress(Exception):
                sys.stdout.write("\x1b[?2004l\x1b[?1000l\x1b[?1006l")
                sys.stdout.flush()
        if self.ancien_param and sys.stdin.isatty():
            with contextlib.suppress(Exception):
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.ancien_param)

    def attendre(self, timeout: float = 0.04):
        """Attend jusqu'à `timeout` secondes ou se réveille instantanément dès qu'une touche arrive."""
        if not sys.stdin.isatty():
            time.sleep(timeout)
            return
        with contextlib.suppress(OSError, ValueError):
            select.select([self.fd], [], [], max(0.005, timeout))

    def lire_toutes(self) -> list[str]:
        if not sys.stdin.isatty():
            return []
        try:
            r, _, _ = select.select([self.fd], [], [], 0)
            if not r:
                return []
            tampon = os.read(self.fd, 1024)
            if b"\x1b[200~" in tampon and b"\x1b[201~" not in tampon:
                for _ in range(16):
                    r2, _, _ = select.select([self.fd], [], [], 0.04)
                    if not r2:
                        break
                    morceau = os.read(self.fd, 8192)
                    if not morceau:
                        break
                    tampon += morceau
                    if b"\x1b[201~" in tampon:
                        break
            elif tampon.endswith((b"\x1b", b"\x1b[")):
                r2, _, _ = select.select([self.fd], [], [], 0.025)
                if r2:
                    tampon += os.read(self.fd, 512)
        except (BlockingIOError, OSError):
            return []
        if not tampon:
            return []
        return self._decouper_touches(tampon)

    @staticmethod
    def _decouper_touches(tampon: bytes) -> list[str]:
        ctrl_ascii = {
            b"\x01": "CTRL_A",
            b"\x02": "CTRL_B",
            b"\x04": "CTRL_D",
            b"\x05": "CTRL_E",
            b"\x06": "CTRL_F",
            b"\x07": "CTRL_G",
            b"\x0b": "CTRL_K",
            b"\x0c": "CTRL_L",
            b"\x0e": "CTRL_N",
            b"\x0f": "CTRL_O",
            b"\x10": "CTRL_P",
            b"\x12": "CTRL_R",
            b"\x13": "CTRL_S",
            b"\x15": "CTRL_U",
            b"\x16": "CTRL_V",
            b"\x18": "CTRL_X",
        }
        ctrl_kitty = {
            97: "CTRL_A",
            98: "CTRL_B",
            100: "CTRL_D",
            101: "CTRL_E",
            102: "CTRL_F",
            103: "CTRL_G",
            107: "CTRL_K",
            108: "CTRL_L",
            110: "CTRL_N",
            111: "CTRL_O",
            112: "CTRL_P",
            114: "CTRL_R",
            115: "CTRL_S",
            117: "CTRL_U",
            118: "CTRL_V",
            120: "CTRL_X",
        }
        f_ss3 = {b"P": "F1", b"Q": "F2", b"R": "F3", b"S": "F4"}
        tilde_map = {
            b"1": "DEBUT",
            b"3": "SUPPR",
            b"4": "FIN",
            b"5": "PAGE_HAUT",
            b"6": "PAGE_BAS",
            b"7": "DEBUT",
            b"8": "FIN",
            b"11": "F1",
            b"12": "F2",
            b"13": "F3",
            b"14": "F4",
            b"15": "F5",
            b"17": "F6",
            b"18": "F7",
            b"19": "F8",
            b"20": "F9",
            b"21": "F10",
            b"23": "F11",
            b"24": "F12",
        }
        touches: list[str] = []
        i = 0
        n = len(tampon)
        while i < n:
            b = tampon[i : i + 1]
            if b == b"\x1b":
                reste = tampon[i:]

                # 0. Collage encadré (Bracketed paste) avant toute autre séquence ~
                m = re.match(rb"^\x1b\[200~(.*?)\x1b\[201~", reste, re.DOTALL)
                if m:
                    texte = m.group(1).decode("utf-8", errors="replace")
                    touches.append(f"PASTE:{texte}")
                    i += len(m.group(0))
                    continue

                # 1. Protocole clavier Kitty : \x1b[<codepoint>(:<alternate>)*(;<modifiers>(:<event_type>)*)*u
                m = re.match(
                    rb"^\x1b\[(\d+)(?::(\d+))*(?:;(\d+)(?::(\d+))*)?(?:;\d+)*u",
                    reste,
                )
                if m:
                    codepoint = int(m.group(1))
                    alt_cp = int(m.group(2)) if m.group(2) else 0
                    mods = int(m.group(3)) if m.group(3) else 1
                    event_type = int(m.group(4)) if m.group(4) else 1
                    i += len(m.group(0))
                    if event_type == 3:
                        continue
                    est_shift = bool((mods - 1) & 1)
                    est_alt = bool((mods - 1) & 2)
                    est_ctrl = bool((mods - 1) & 4)
                    cp_low = codepoint + 32 if 65 <= codepoint <= 90 else codepoint
                    if est_ctrl and cp_low in ctrl_kitty:
                        touches.append(ctrl_kitty[cp_low])
                        continue
                    if codepoint == 9 and est_shift:
                        touches.append("SHIFT_TAB")
                        continue
                    if codepoint == 13 and est_alt:
                        touches.append("ALT_ENTREE")
                        continue
                    if codepoint in (57358, 57398) and est_shift:
                        touches.append("SHIFT_HAUT")
                        continue
                    if codepoint in (57359, 57399) and est_shift:
                        touches.append("SHIFT_BAS")
                        continue
                    mapping_kitty = {
                        57358: "HAUT", 57398: "HAUT",
                        57359: "BAS", 57399: "BAS",
                        57360: "GAUCHE", 57400: "GAUCHE",
                        57361: "DROITE", 57401: "DROITE",
                        57362: "PAGE_HAUT", 57402: "PAGE_HAUT",
                        57363: "PAGE_BAS", 57403: "PAGE_BAS",
                        57364: "DEBUT", 57404: "DEBUT",
                        57365: "FIN", 57405: "FIN",
                        13: "ENTREE",
                        27: "ECHAP",
                        9: "TAB",
                        32: "ESPACE",
                        8: "RETOUR",
                        127: "RETOUR",
                    }
                    if codepoint in mapping_kitty:
                        touches.append(mapping_kitty[codepoint])
                    elif 32 <= codepoint < 57000:
                        if est_shift and alt_cp >= 32:
                            touches.append(chr(alt_cp))
                        elif est_shift and 97 <= codepoint <= 122:
                            touches.append(chr(codepoint).upper())
                        else:
                            touches.append(chr(codepoint))
                    continue

                # 2. Souris SGR (molette et clic gauche) : \x1b[<btn;x;y[Mm]
                m = re.match(rb"^\x1b\[<(\d+);(\d+);(\d+)([mM])", reste)
                if m:
                    btn = int(m.group(1))
                    x = int(m.group(2))
                    y = int(m.group(3))
                    est_presse = m.group(4) == b"M"
                    i += len(m.group(0))
                    if btn == 64:
                        touches.append("HAUT")
                    elif btn == 65:
                        touches.append("BAS")
                    elif btn == 0 and est_presse:
                        touches.append(f"CLIC:{x}:{y}")
                    continue

                # 3. Shift+Tab : \x1b[Z
                if reste.startswith(b"\x1b[Z"):
                    touches.append("SHIFT_TAB")
                    i += 3
                    continue

                # 4. Touches fonction F1-F4 SS3 ou CSI modifié
                m = re.match(rb"^\x1b(?:O|\[1;\d+)([PQRS])", reste)
                if m:
                    touches.append(f_ss3[m.group(1)])
                    i += len(m.group(0))
                    continue

                # 5. Flèches ANSI standard ou mode application : \x1b[A, \x1bOA
                m = re.match(rb"^\x1b(?:\[|O)([A-D])", reste)
                if m:
                    d = {b"A": "HAUT", b"B": "BAS", b"C": "DROITE", b"D": "GAUCHE"}
                    touches.append(d[m.group(1)])
                    i += len(m.group(0))
                    continue

                # 6. Flèches avec modificateurs : \x1b[1;2A (Shift+Haut), etc.
                m = re.match(rb"^\x1b\[1;(\d+)([A-D])", reste)
                if m:
                    mod = int(m.group(1))
                    d_ch = m.group(2)
                    if ((mod - 1) & 1) and d_ch in (b"A", b"B"):
                        touches.append("SHIFT_HAUT" if d_ch == b"A" else "SHIFT_BAS")
                    else:
                        d = {b"A": "HAUT", b"B": "BAS", b"C": "DROITE", b"D": "GAUCHE"}
                        touches.append(d[d_ch])
                    i += len(m.group(0))
                    continue

                # 7. Page Haut / Bas, Début, Fin, Suppr, F1-F10 : \x1b[5~
                m = re.match(rb"^\x1b\[(\d+)(?:;\d+)?~", reste)
                if m:
                    code = m.group(1)
                    if code in tilde_map:
                        touches.append(tilde_map[code])
                    i += len(m.group(0))
                    continue

                # 8. Alt+Entrée : \x1b\r ou \x1b\n
                if len(reste) >= 2 and reste[1:2] in (b"\r", b"\n"):
                    touches.append("ALT_ENTREE")
                    i += 2
                    continue

                touches.append("ECHAP")
                i += 1
            elif b in ctrl_ascii:
                touches.append(ctrl_ascii[b])
                i += 1
            elif b in (b"\r", b"\n"):
                touches.append("ENTREE")
                i += 1
            elif b == b"\t":
                touches.append("TAB")
                i += 1
            elif b == b" ":
                touches.append("ESPACE")
                i += 1
            elif b in (b"\x7f", b"\x08"):
                touches.append("RETOUR")
                i += 1
            else:
                try:
                    ch = b.decode("utf-8")
                    touches.append(ch)
                    i += 1
                except UnicodeDecodeError:
                    trouve = False
                    for l in (2, 3, 4):
                        if i + l <= n:
                            try:
                                ch = tampon[i : i + l].decode("utf-8")
                                touches.append(ch)
                                i += l
                                trouve = True
                                break
                            except UnicodeDecodeError:
                                pass
                    if not trouve:
                        i += 1
        return touches


# ── Application Principale Onde CLI ──────────────────────────────────────────


class ApplicationOndeCLI:
    """Interface interactive TUI Liquid Glass Studio : lecture audio, karaoké et outils pro."""

    def __init__(self):
        self.console = Console()
        self.mpris: ServiceMPRIS2 | None = None
        self.decalage_paroles = 0.0
        self.mode_aleatoire = False
        self.mode_repetition = "tout"  # "non", "tout", "un"
        self.piste_courante: dict[str, Any] | None = None
        self.lecteur = LecteurMPV(
            callback_fin=self.sur_fin_piste,
            callback_pause=self._sur_pause_mpv,
            callback_seek=self._sur_seek_mpv,
            callback_duree=self._sur_duree_mpv,
        )
        self.fond = GestionnaireFondPhoto()
        self.pochette_hd = GestionnairePochetteKittyHD()
        self.spectre = AnalyseurSpectreTempsReel()
        self.mpris = ServiceMPRIS2(self)
        atexit.register(self.fermer_proprement)

        # Base de données & Morceaux
        self.pistes: list[dict[str, Any]] = []
        self.pistes_filtrees: list[dict[str, Any]] = []
        self.playlists_liste: list[dict[str, Any]] = []
        self.favoris_set: set[int] = set()

        # État de lecture et sélection stable par vue
        self.index_selection = 0
        self.index_courant = -1
        self._vue_filtree: tuple | None = None
        self._terme_filtre = ""
        self._tri_filtre = "defaut"
        self._selection_par_vue: dict[tuple, tuple] = {}
        self._liste_debut = 0
        self.file_attente: list[dict[str, Any]] = []
        self.dernier_id_sauvegarde: int | None = None
        self.derniere_position = 0.0
        self.reprendre_position = True
        self.auto_dj = False

        # Sous-navigation Playlists, Artistes, Albums, Dossiers & Genres
        self.playlist_ouverte: dict[str, Any] | None = None
        self.artiste_ouvert: str | None = None
        self.album_ouvert: str | None = None
        self.dossier_ouvert: str | None = None
        self.genre_ouvert: str | None = None

        # Modes, Apparence & Tri
        self.mode_vue = "scinde"  # "accueil", "scinde", "scene", "paroles", "liste"
        self.mode_onglet = "titres"
        self.tri_mode = "defaut"
        self.visualiseur_mode = "spectre"
        self.effet_dsp = "off"
        self.afficher_timestamps_paroles = True
        self.recherche_active = False
        self.terme_recherche = ""
        self.decalages_paroles: dict[str, float] = {}
        self.index_animation = 0
        self.theme_code = "auto"
        self.palette_auto: dict[str, str] | None = None
        self.eq_index = 0
        self.aide_ouverte = False
        self.audio_device = "auto"
        self.peripheriques_audio: list[tuple[str, str]] = [
            ("auto", "Automatique (Système)")
        ]

        # Vue Accueil Studio ([F3])
        self.accueil_section = 0  # 0..3 étagères, 4 mixes genres
        self.accueil_index = 0
        self.accueil_graine = int(time.time())
        self._accueil_donnees: dict[str, Any] = {}
        self._accueil_zones: list[tuple[int, int, int, int, str, Any]] = []

        # Zones cliquables dynamiques (calculées à chaque rendu)
        self._zones_clic: dict[str, tuple[int, int, int, int]] = {}
        self._paroles_lignes_ecran: list[tuple[int, float]] = []
        self._dernier_clic: tuple[float, int, int] = (0.0, -1, -1)

        # Égaliseur graphique 10 bandes personnalisé ([Maj+E]) + profils persos
        self.eq_perso_ouvert = False
        self.eq_perso_actif = False
        self.eq_bandes: list[float] = [0.0] * 10
        self.eq_bande_selection = 0
        self.eq_profils_perso: list[dict[str, Any]] = []
        self.eq_saisie_nom = False
        self.eq_nom_tampon = ""

        # Boucle A-B de passage ([,] point A, [;] point B / effacer)
        self.boucle_a: float | None = None
        self.boucle_b: float | None = None

        # Recherche globale dans les paroles ([:] ou [Ctrl+K])
        self.paroles_recherche_ouverte = False
        self.paroles_recherche_saisie = False
        self.paroles_recherche_requete = ""
        self.paroles_recherche_resultats: list[dict[str, Any]] = []
        self.paroles_recherche_index = 0
        self.paroles_couverture: dict[str, int] = {"avec": 0, "total": 0}

        # Studio Paroles & Recalage ([Ctrl+L] / [F4])
        self.paroles_studio_ouvert = False
        self.paroles_studio_saisie = False
        self.paroles_studio_requete = ""
        self.paroles_studio_resultats: list[dict[str, Any]] = []
        self.paroles_studio_index = 0
        self.paroles_studio_en_cours = False
        self.paroles_studio_message = ""

        # Palette de commandes ([>] / [Ctrl+P] / [F1])
        self.palette_cmd_ouverte = False
        self.palette_cmd_requete = ""
        self.palette_cmd_index = 0

        # Réglages & Sortie audio ([Ctrl+G] / [F7] / [F10])
        self.reglages_ouvert = False
        self.reglages_section = 0
        self.reglages_index = 0
        self._statut_scan_cli = ""

        # Fusion de doublons ([Ctrl+D] / [F8])
        self.doublons_ouvert = False
        self.doublons_groupes: list[dict[str, Any]] = []
        self.doublons_groupe_index = 0
        self.doublons_copie_index = 0
        self.doublons_en_scan = False
        self.doublons_message = ""

        # Fiche Propriétés & Codec ([Maj+I])
        self.proprietes_ouvertes = False
        self.proprietes_donnees: dict[str, Any] | None = None

        # Éditeur de Tags & Lookup iTunes ([Maj+T])
        self.tags_ouvert = False
        self.tags_mode = "champs"  # "champs" | "itunes" | "saisie" | "pochette"
        self.tags_piste_id: int | None = None
        self.tags_champs: dict[str, str] = {}
        self.tags_champ_index = 0
        self.tags_saisie_Tampon = ""
        self.tags_itunes_resultats: list[dict[str, Any]] = []
        self.tags_itunes_index = 0
        self.tags_en_recherche = False
        self.tags_erreur = ""
        self.tags_itunes_choisi: int | None = None
        self.tags_pochette_locale: str | None = None
        self.tags_galerie_index = 0

        # Radios Web / FM ([6] Onglet Radios)
        self.radios_favorites: list[dict[str, Any]] = []
        self.radios_recherche_resultats: list[dict[str, Any]] = []
        self.radios_en_recherche = False

        # Serveur IPC UNIX de télécommande CLI
        self._sock_ctrl: socket.socket | None = None

        # Galerie de photos de fond
        self.galerie_ouverte = False
        self.photos_disponibles: list[tuple[str, str]] = []
        self.index_galerie = 0

        # Mode Mini-Barre ([I]) & Statistiques ([S])
        self.mini_mode = False
        self.stats_ouverte = False
        self.stats_donnees: dict[str, Any] = {}
        self.stats_index = 0
        self.stats_heures: list[int] = [0] * 24

        # Téléchargement YouTube intégré ([Y])
        self.yt_ouvert = False
        self.yt_saisie_active = False
        self.yt_requete = ""
        self.yt_en_recherche = False
        self.yt_resultats: list[dict[str, Any]] = []
        self.yt_index_selection = 0
        self.yt_erreur = ""
        self._yt_finis_connus: set[str] = set()

        # Gestion des Playlists au clavier ([N] créer, [P] ajouter, [F2] renommer)
        self.modal_playlist_mode: str | None = None  # "creer" | "ajouter" | "renommer" | None
        self.nom_nouvelle_playlist = ""
        self.index_playlist_cible = 0
        self.pistes_cibles_playlist: list[int] = []
        self.titre_cible_playlist = ""

        # Placement courant de la pochette HD Kitty (chemin, col, row, cols, rows)
        self._cible_pochette_hd: tuple[str, int, int, int, int] | None = None
        self._rev_bibliotheque = bibliotheque.REV.get("n", 0)

        # Minuterie de veille (Sleep Timer)
        self.veille_mode = 0  # 0=Off, -1=Fin du titre, >0=minutes
        self.veille_echeance = 0.0

        # Normalisation EBU R128 / ReplayGain & Fondu enchaîné (Crossfade)
        self.normalisation_active = True
        self.gain_piste_db = 0.0
        self.gain_source = ""
        self.gain_en_analyse = False
        self._dernier_poll_gain = 0.0
        self.fondu_duree = 0  # 0s, 2s, 4s, 6s
        self._debut_piste_ts = 0.0
        self._transition_fondu_en_cours = False

        # Cache de pochette ANSI & Crêtes du vumètre
        self._cache_pochette_cle: tuple[Any, ...] | None = None
        self._cache_pochette_rendu: Text | None = None
        self._cretes_vumetre: list[float] = []
        self._crete_rms_g = 0.0
        self._crete_rms_d = 0.0

        # Paroles
        self.paroles_items: list[LigneParole] = []
        self.paroles_source = ""
        self.paroles_en_chargement = False
        self.paroles_texte_libre: str | None = None
        self._verrou_paroles = threading.Lock()

        # Messages éphémères
        self.toast_message = ""
        self.toast_expiration = 0.0
        self.toast_duree = 2.6

        # Charger les préférences puis la bibliothèque
        self.charger_etat_cli()
        self.recharger_bibliotheque()
        self.scanner_photos_disponibles()
        if not self.fond.chemin_photo_perso and self.photos_disponibles:
            self.fond.chemin_photo_perso = self.photos_disponibles[0][1]
        self.actualiser_palette_et_fond()
        self._demarrer_serveur_ipc()

    @property
    def palette(self) -> dict[str, str]:
        if self.theme_code == "auto" and self.palette_auto:
            return self.palette_auto
        return THEMES.get(self.theme_code, THEMES["liquid"])

    def fermer_proprement(self):
        if self.piste_courante and not self.piste_courante.get("_type"):
            self.derniere_position = max(0.0, float(self.lecteur.position or 0.0))
        self.sauvegarder_etat_cli()
        self.pochette_hd.nettoyer()
        self.fond.nettoyer()
        self.spectre.fermer()
        if self.mpris:
            self.mpris.fermer()
        self.lecteur.fermer()
        if self._sock_ctrl:
            with contextlib.suppress(OSError):
                self._sock_ctrl.close()
            self._sock_ctrl = None
        if os.path.exists(SOCKET_CTRL_CLI):
            with contextlib.suppress(OSError):
                os.remove(SOCKET_CTRL_CLI)

    def _sur_pause_mpv(self, _en_pause: bool):
        if self.mpris:
            self.mpris.notifier_changement(["PlaybackStatus"])
            self.mpris.emettre_seeked(self.lecteur.position)

    def _sur_seek_mpv(self, pos: float):
        if self.mpris:
            self.mpris.notifier_changement(["PlaybackStatus", "Metadata"])
            self.mpris.emettre_seeked(pos)

    def _sur_duree_mpv(self, _dur: float):
        if self.mpris:
            self.mpris.notifier_changement(["Metadata"])

    def _demarrer_serveur_ipc(self):
        """Serveur UNIX permettant à `onde-cli play|pause|toggle|next|prev|mute|status|lyrics` de piloter l'instance."""
        if os.path.exists(SOCKET_CTRL_CLI):
            with contextlib.suppress(OSError):
                os.remove(SOCKET_CTRL_CLI)
        try:
            self._sock_ctrl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock_ctrl.bind(SOCKET_CTRL_CLI)
            self._sock_ctrl.listen(4)
            self._sock_ctrl.settimeout(0.5)
            threading.Thread(
                target=self._boucle_serveur_ipc, daemon=True, name="onde-cli-ipc"
            ).start()
        except OSError:
            self._sock_ctrl = None

    def _boucle_serveur_ipc(self):
        while self.lecteur.en_cours and self._sock_ctrl:
            try:
                conn, _ = self._sock_ctrl.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with conn, contextlib.suppress(OSError, ValueError):
                conn.settimeout(0.5)
                brut = conn.recv(2048).decode("utf-8").strip()
                if not brut:
                    continue
                rep = self._executer_commande_ipc(brut)
                conn.sendall((json.dumps(rep, ensure_ascii=False) + "\n").encode("utf-8"))

    def _trouver_piste_rapide(self, requete: str) -> dict[str, Any] | None:
        q = bibliotheque.sans_accents((requete or "").strip().lower())
        if not q:
            return None
        if q.isdigit():
            pid = int(q)
            for p in self.pistes:
                if p.get("id") == pid:
                    return p
        for p in self.pistes:
            chaine = bibliotheque.sans_accents(
                f"{p.get('titre') or ''} {p.get('artiste') or ''} {p.get('album') or ''}".lower()
            )
            if q in chaine:
                return p
        return None

    def _executer_commande_ipc(self, commande_brute: str) -> dict[str, Any]:
        cmd = ""
        arg = ""
        if commande_brute.startswith("{"):
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                obj = json.loads(commande_brute)
                if isinstance(obj, dict):
                    cmd = str(obj.get("action") or "").lower().strip()
                    arg = str(obj.get("arg") or "").strip()
        if not cmd:
            parts = commande_brute.split(maxsplit=1)
            cmd = parts[0].lower() if parts else "status"
            arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "lyrics":
            with self._verrou_paroles:
                items_l = list(self.paroles_items)
                en_chg = self.paroles_en_chargement
                src_l = self.paroles_source
            lignes_ipc: list[list[Any]] = []
            for idx_it, it_l in enumerate(items_l):
                if it_l.pause:
                    if idx_it > 0 and (it_l.fin - it_l.t < 2.5):
                        continue
                    lignes_ipc.append([round(it_l.t, 3), "♪"])
                else:
                    lignes_ipc.append([round(it_l.t, 3), it_l.texte])
            p_c = self.piste_courante or {}
            return {
                "ok": True,
                "id": p_c.get("id"),
                "titre": p_c.get("titre") or "",
                "artiste": p_c.get("artiste") or "",
                "en_chargement": en_chg,
                "source": src_l,
                "decalage": self.decalage_paroles,
                "lines": lignes_ipc,
            }

        if cmd == "toggle":
            if self.lecteur.fichier_actuel is None and self.piste_courante:
                self.jouer_piste(self.piste_courante)
            else:
                self.lecteur.basculer_pause()
                if self.mpris:
                    self.mpris.notifier_changement(["PlaybackStatus"])
                    self.mpris.emettre_seeked(self.lecteur.position)
        elif cmd == "play":
            if arg:
                cible = self._trouver_piste_rapide(arg)
                if cible:
                    self.jouer_piste(cible)
            elif self.lecteur.fichier_actuel is None and self.piste_courante:
                self.jouer_piste(self.piste_courante)
            elif self.lecteur.en_pause:
                self.lecteur.basculer_pause()
                if self.mpris:
                    self.mpris.notifier_changement(["PlaybackStatus"])
                    self.mpris.emettre_seeked(self.lecteur.position)
            elif self.mpris:
                self.mpris.notifier_changement(["PlaybackStatus"])
                self.mpris.emettre_seeked(self.lecteur.position)
        elif cmd == "pause":
            if not self.lecteur.en_pause:
                self.lecteur.basculer_pause()
            if self.mpris:
                self.mpris.notifier_changement(["PlaybackStatus"])
                self.mpris.emettre_seeked(self.lecteur.position)
        elif cmd == "mute":
            self.basculer_muet()
        elif cmd == "next":
            self.piste_suivante()
        elif cmd == "prev":
            self.piste_precedente()
        elif cmd == "seek" and arg:
            with contextlib.suppress(ValueError):
                if arg.startswith(("+", "-")):
                    nouv = max(0.0, self.lecteur.position + float(arg))
                else:
                    nouv = max(0.0, float(arg))
                self.lecteur.aller_a(nouv)
                if self.mpris:
                    self.mpris.emettre_seeked(nouv)
        elif cmd == "vol" and arg:
            with contextlib.suppress(ValueError):
                if arg.startswith(("+", "-")):
                    self.lecteur.ajuster_volume(float(arg))
                else:
                    self.lecteur.definir_volume(float(arg))
                if self.mpris:
                    self.mpris.notifier_changement(["Volume"])

        p = self.piste_courante or {}
        en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        t_pos = self.lecteur.position + self.decalage_paroles
        parole_active = ""
        with self._verrou_paroles:
            items = list(self.paroles_items)
        if items:
            _, it, est_p, _ = ligne_affichee(items, t_pos)
            if not est_p and it:
                parole_active = it.texte
        elif p.get("_type") == "radio" and self.lecteur.icy_title:
            parole_active = self.lecteur.icy_title

        return {
            "ok": True,
            "etat": "Playing" if en_lec else ("Paused" if self.lecteur.en_pause else "Stopped"),
            "id": p.get("id"),
            "titre": p.get("titre") or "Aucun morceau",
            "artiste": p.get("artiste") or "Onde",
            "album": p.get("album") or "",
            "position": round(self.lecteur.position, 2),
            "duree": round(float(self.lecteur.duree or p.get("duree") or 0.0), 2),
            "volume": round(self.lecteur.volume, 1),
            "mute": self.lecteur.mute,
            "mode_aleatoire": self.mode_aleatoire,
            "mode_repetition": self.mode_repetition,
            "theme": self.theme_code,
            "visualiseur": self.visualiseur_mode,
            "badge": badge_qualite_piste(p, True),
            "parole": parole_active,
            "radio": p.get("_type") == "radio",
        }

    def charger_etat_cli(self):
        with contextlib.suppress(OSError, ValueError, KeyError):
            if FICHIER_ETAT_CLI.exists():
                d = json.loads(FICHIER_ETAT_CLI.read_text(encoding="utf-8"))
                self.lecteur.definir_volume(float(d.get("volume", 80.0)))
                self.mode_aleatoire = bool(d.get("mode_aleatoire", False))
                if d.get("mode_repetition") in ("non", "tout", "un"):
                    self.mode_repetition = d["mode_repetition"]
                if d.get("mode_vue") in ("accueil", "scinde", "scene", "paroles", "liste"):
                    self.mode_vue = d["mode_vue"]
                if d.get("theme_code") in THEMES:
                    self.theme_code = d["theme_code"]
                if d.get("visualiseur_mode") in {k for k, _ in MODES_VISUALISEUR}:
                    self.visualiseur_mode = d["visualiseur_mode"]
                if d.get("effet_dsp") in {k for k, _, _ in EFFETS_DSP}:
                    self.effet_dsp = d["effet_dsp"]
                if d.get("tri_mode") in {k for k, _ in TRIS_LISTE}:
                    self.tri_mode = d["tri_mode"]
                if d.get("mode_fond") in ("photo", "pochette", "aurore", "aucun"):
                    self.fond.mode_fond = d["mode_fond"]
                if d.get("mode_rendu") in ("kitty", "canevas"):
                    self.fond.mode_rendu = d["mode_rendu"]
                if d.get("fond_photo") and os.path.isfile(str(d.get("fond_photo"))):
                    self.fond.chemin_photo_perso = str(d["fond_photo"])
                self.fond.index_luminosite = int(d.get("index_luminosite", 1)) % len(
                    NIVEAUX_LUMINOSITE
                )
                self.eq_index = int(d.get("eq_index", 0)) % len(PROFILS_EQ)
                bandes = d.get("eq_bandes")
                if isinstance(bandes, list) and len(bandes) == 10:
                    self.eq_bandes = [
                        max(-12.0, min(12.0, round(float(x), 1))) for x in bandes
                    ]
                profils_p = d.get("eq_profils_perso")
                if isinstance(profils_p, list):
                    self.eq_profils_perso = [
                        {
                            "nom": str(pr.get("nom") or "Perso")[:20],
                            "bandes": [
                                max(-12.0, min(12.0, round(float(x), 1)))
                                for x in pr["bandes"]
                            ],
                        }
                        for pr in profils_p[:3]
                        if isinstance(pr, dict)
                        and isinstance(pr.get("bandes"), list)
                        and len(pr["bandes"]) == 10
                    ]
                self.eq_perso_actif = bool(d.get("eq_perso_actif", False))
                self.afficher_timestamps_paroles = bool(
                    d.get("afficher_timestamps_paroles", True)
                )
                self.appliquer_egaliseur_courant()
                self.normalisation_active = bool(d.get("normalisation_active", True))
                if int(d.get("fondu_duree", 0)) in (0, 2, 4, 6):
                    self.fondu_duree = int(d["fondu_duree"])
                self.auto_dj = bool(d.get("auto_dj", False))
                self.reprendre_position = bool(d.get("reprendre_position", True))
                self.derniere_position = max(0.0, float(d.get("derniere_position", 0.0)))
                dev = str(d.get("audio_device") or "auto").strip() or "auto"
                self.audio_device = dev
                self.lecteur.definir_peripherique_audio(dev)
                decs = d.get("decalages_paroles")
                if isinstance(decs, dict):
                    self.decalages_paroles = {
                        str(k): max(-60.0, min(60.0, round(float(v), 2)))
                        for k, v in list(decs.items())[-300:]
                        if isinstance(v, (int, float))
                    }
                self.dernier_id_sauvegarde = d.get("dernier_id")

    def sauvegarder_etat_cli(self):
        with contextlib.suppress(OSError, ValueError):
            decs_brut = list(self.decalages_paroles.items())[-300:]
            donnees = {
                "volume": round(self.lecteur.volume, 1),
                "mode_aleatoire": self.mode_aleatoire,
                "mode_repetition": self.mode_repetition,
                "mode_vue": self.mode_vue,
                "theme_code": self.theme_code,
                "visualiseur_mode": self.visualiseur_mode,
                "effet_dsp": self.effet_dsp,
                "tri_mode": self.tri_mode,
                "mode_fond": self.fond.mode_fond,
                "mode_rendu": self.fond.mode_rendu,
                "fond_photo": self.fond.chemin_photo_perso,
                "index_luminosite": self.fond.index_luminosite,
                "eq_index": self.eq_index,
                "eq_bandes": self.eq_bandes,
                "eq_perso_actif": self.eq_perso_actif,
                "eq_profils_perso": self.eq_profils_perso,
                "afficher_timestamps_paroles": self.afficher_timestamps_paroles,
                "normalisation_active": self.normalisation_active,
                "fondu_duree": self.fondu_duree,
                "auto_dj": self.auto_dj,
                "reprendre_position": self.reprendre_position,
                "derniere_position": round(self.derniere_position, 1),
                "audio_device": self.audio_device,
                "decalages_paroles": dict(decs_brut),
                "dernier_id": (
                    self.piste_courante.get("id")
                    if self.piste_courante and not self.piste_courante.get("_type")
                    else self.dernier_id_sauvegarde
                ),
            }
            FICHIER_ETAT_CLI.write_text(
                json.dumps(donnees, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def construire_filtre_eq_10_bandes(self) -> str:
        """Construit la chaîne FFmpeg `lavfi=[equalizer=...]` pour les 10 bandes actives."""
        parties = [
            f"equalizer=f={freq}:t=q:w=1.4:g={gain:.1f}"
            for (freq, _), gain in zip(FREQS_EQ_10, self.eq_bandes, strict=False)
            if abs(gain) >= 0.1
        ]
        return f"lavfi=[{','.join(parties)}]" if parties else ""

    def construire_filtre_audio_complet(self) -> str:
        """Chaîne proprement l'égaliseur actif (10 bandes ou profil) et l'effet DSP Studio."""
        chaine: list[str] = []
        if self.eq_perso_actif:
            f_eq = self.construire_filtre_eq_10_bandes()
        else:
            f_eq = PROFILS_EQ[self.eq_index][1]
        if f_eq.startswith("lavfi=[") and f_eq.endswith("]"):
            interne = f_eq[7:-1].strip()
            if interne:
                chaine.append(interne)
        elif f_eq:
            chaine.append(f_eq)

        f_dsp = next((f for k, _, f in EFFETS_DSP if k == self.effet_dsp), "")
        if f_dsp:
            chaine.append(f_dsp)
        return f"lavfi=[{','.join(chaine)}]" if chaine else ""

    def appliquer_egaliseur_courant(self):
        self.lecteur.definir_filtre_audio(self.construire_filtre_audio_complet())

    def cycler_effet_dsp(self):
        codes = [k for k, _, _ in EFFETS_DSP]
        idx = (codes.index(self.effet_dsp) + 1) % len(codes) if self.effet_dsp in codes else 0
        self.effet_dsp = codes[idx]
        nom = next((n for k, n, _ in EFFETS_DSP if k == self.effet_dsp), "Pur")
        self.appliquer_egaliseur_courant()
        self.sauvegarder_etat_cli()
        self.notifier(f"✨ Effet DSP Studio : {nom}")

    def scanner_photos_disponibles(self):
        """Recherche les photos disponibles dans ~/Images/Wallpapers, ~/Images et les pochettes."""
        dossiers = [
            ("Fond d'écran", Path.home() / "Images" / "Wallpapers"),
            ("Images", Path.home() / "Images"),
            ("Pictures", Path.home() / "Pictures"),
            ("Pochette Onde", config.POCHETTES),
        ]
        vus: set[str] = set()
        liste: list[tuple[str, str]] = []
        if self.fond.chemin_photo_perso and os.path.isfile(
            self.fond.chemin_photo_perso
        ):
            p = Path(self.fond.chemin_photo_perso)
            vus.add(str(p.resolve()))
            liste.append((f"★ {p.name}", str(p)))

        for categorie, d in dossiers:
            if not d.exists() or not d.is_dir():
                continue
            with contextlib.suppress(OSError):
                fichiers = sorted(
                    (
                        f
                        for f in d.iterdir()
                        if f.is_file() and f.suffix.lower() in EXTENSIONS_IMAGES
                    ),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                for f in fichiers[:45]:
                    res = str(f.resolve())
                    if res not in vus:
                        vus.add(res)
                        liste.append((f"[{categorie}] {f.name}", str(f)))
        self.photos_disponibles = liste

    def chemin_pochette_piste(self, piste: dict[str, Any] | None) -> str | None:
        if not piste:
            return None
        nom = piste.get("pochette")
        if not nom:
            return None
        c = config.POCHETTES / nom
        return str(c) if c.is_file() else None

    def actualiser_palette_et_fond(self):
        """Met à jour la pochette active, la palette automatique et l'arrière-plan Kitty/Canevas."""
        self.fond.chemin_pochette_courante = self.chemin_pochette_piste(
            self.piste_courante
        )
        cible_palette = (
            self.fond.chemin_image_active() or self.fond.chemin_pochette_courante
        )
        if cible_palette and os.path.isfile(cible_palette):
            self.palette_auto = extraire_palette_image(cible_palette)
        else:
            self.palette_auto = None
        self.fond.synchroniser_kitty_hd()

    def notifier(self, msg: str, duree: float = 2.6):
        self.toast_message = msg
        self.toast_duree = max(0.5, float(duree))
        self.toast_expiration = time.time() + self.toast_duree

    def charger_pistes_recentes(self) -> list[dict[str, Any]]:
        """Charge les morceaux récemment écoutés depuis la base Onde."""
        try:
            lignes = bibliotheque.requete(
                "SELECT DISTINCT piste_id FROM ecoutes ORDER BY date DESC LIMIT 50"
            )
            pistes_map = {p["id"]: p for p in self.pistes if p.get("id")}
            res = []
            for r in lignes:
                pid = r["piste_id"]
                if pid in pistes_map:
                    res.append(pistes_map[pid])
            return res
        except (OSError, ValueError, KeyError):
            return []

    def construire_entrees_artistes(self) -> list[dict[str, Any]]:
        """Regroupe les morceaux par artiste."""
        compteur: dict[str, list[dict[str, Any]]] = {}
        for p in self.pistes:
            art = (p.get("artiste") or "Artiste inconnu").strip()
            compteur.setdefault(art, []).append(p)
        entrees: list[dict[str, Any]] = []
        for art in sorted(compteur.keys(), key=lambda s: s.lower()):
            ps = compteur[art]
            dur_tot = sum(float(x.get("duree") or 0.0) for x in ps)
            entrees.append(
                {
                    "_type": "artiste",
                    "id": f"art:{art}",
                    "titre": f"🎤 {art}",
                    "artiste": f"{len(ps)} titre{'s' if len(ps) > 1 else ''}",
                    "album": "",
                    "duree": dur_tot,
                    "_nom_artiste": art,
                    "_pistes": ps,
                }
            )
        return entrees

    def construire_entrees_playlists(self) -> list[dict[str, Any]]:
        """Construit les entrées de playlists depuis la base Onde."""
        pistes_map = {p["id"]: p for p in self.pistes if p.get("id")}
        entrees: list[dict[str, Any]] = []
        for pl in self.playlists_liste:
            ids = pl.get("pistes") or []
            ps = [pistes_map[i] for i in ids if i in pistes_map]
            dur_tot = sum(float(x.get("duree") or 0.0) for x in ps)
            entrees.append(
                {
                    "_type": "playlist",
                    "id": f"pl:{pl.get('id')}",
                    "titre": f"♪ {pl.get('nom') or 'Playlist'}",
                    "artiste": f"{len(ps)} titre{'s' if len(ps) > 1 else ''}",
                    "album": pl.get("description") or "",
                    "duree": dur_tot,
                    "_playlist": pl,
                    "_pistes": ps,
                }
            )
        return entrees

    def construire_entrees_albums(self) -> list[dict[str, Any]]:
        """Regroupe les morceaux par album."""
        compteur: dict[str, list[dict[str, Any]]] = {}
        artistes_alb: dict[str, str] = {}
        annees_alb: dict[str, str] = {}
        for p in self.pistes:
            alb = (p.get("album") or "").strip() or "Singles & Hors-album"
            compteur.setdefault(alb, []).append(p)
            if alb not in artistes_alb:
                artistes_alb[alb] = (
                    p.get("artiste_album") or p.get("artiste") or "Artiste inconnu"
                )
            if not annees_alb.get(alb) and p.get("annee"):
                annees_alb[alb] = str(p["annee"])
        entrees: list[dict[str, Any]] = []
        for alb in sorted(
            compteur.keys(), key=lambda s: ("~" if s == "Singles & Hors-album" else s.lower())
        ):
            ps = sorted(
                compteur[alb],
                key=lambda x: (int(x.get("numero") or 999), (x.get("titre") or "").lower()),
            )
            dur_tot = sum(float(x.get("duree") or 0.0) for x in ps)
            an = f" ({annees_alb[alb]})" if annees_alb.get(alb) else ""
            entrees.append(
                {
                    "_type": "album",
                    "id": f"alb:{alb}",
                    "titre": f"💿 {alb}{an}",
                    "artiste": f"{artistes_alb.get(alb, '')} • {len(ps)} titre{'s' if len(ps) > 1 else ''}",
                    "album": alb,
                    "duree": dur_tot,
                    "_nom_album": alb,
                    "_pistes": ps,
                }
            )
        return entrees

    def construire_entrees_radios(self) -> list[dict[str, Any]]:
        """Construit les entrées de stations radios (favorites + sélection par défaut + résultats web)."""
        entrees: list[dict[str, Any]] = []
        urls_vues: set[str] = set()
        sources = (
            self.radios_recherche_resultats
            if self.radios_recherche_resultats
            else [*self.radios_favorites, *RADIOS_DEFAUT]
        )
        fav_urls = {r.get("url") for r in self.radios_favorites if r.get("url")}
        for r in sources:
            url = r.get("url")
            if not url or url in urls_vues:
                continue
            urls_vues.add(url)
            nom = r.get("nom") or "Radio"
            pays = r.get("pays") or "WEB"
            tags = r.get("tags") or "Direct"
            est_fav_r = url in fav_urls
            badge_fav = "★ " if est_fav_r else ""
            entrees.append(
                {
                    "_type": "radio",
                    "id": None,
                    "titre": f"📻 {badge_fav}{nom}",
                    "artiste": f"[{pays}] {tags}",
                    "album": "Radio en direct",
                    "duree": 0.0,
                    "chemin": url,
                    "_radio": r,
                }
            )
        return entrees

    def lancer_recherche_radios(self, requete: str):
        q = requete.strip()
        if not q:
            self.radios_recherche_resultats = []
            self.filtrer_pistes()
            return
        self.radios_en_recherche = True
        self.notifier(f"📻 Recherche de radios « {q} » sur radio-browser.info...")

        def _tache():
            try:
                res = radios.chercher(nom=q)
                if not res:
                    res = radios.chercher(genre=q)
                self.radios_recherche_resultats = res
            except Exception:  # noqa: BLE001
                self.radios_recherche_resultats = []
            finally:
                self.radios_en_recherche = False
                self.filtrer_pistes()

        threading.Thread(target=_tache, daemon=True, name="onde-radio-search").start()

    def recharger_bibliotheque(self):
        try:
            insta = bibliotheque.instantane()
            self.pistes = insta.get("pistes", [])
            self.playlists_liste = insta.get("playlists", [])
            self.radios_favorites = bibliotheque.radios()
            chemins = {
                r["id"]: r["chemin"]
                for r in bibliotheque.requete("SELECT id, chemin FROM pistes")
            }
            for p in self.pistes:
                p["chemin"] = chemins.get(p.get("id"))
            self.favoris_set = set(insta.get("favoris", []))
            self.filtrer_pistes()
        except (OSError, ValueError) as e:
            self.pistes = []
            self.notifier(f"Erreur chargement bibliothèque : {e}")

    @staticmethod
    def _cle_entree(p: dict[str, Any]) -> tuple:
        t = p.get("_type")
        if t == "artiste":
            return ("artiste", p.get("_nom_artiste"))
        if t == "album":
            return ("album", p.get("_nom_album"))
        if t == "playlist":
            return ("playlist", (p.get("_playlist") or {}).get("id"))
        if t == "dossier":
            return ("dossier", p.get("_dossier"))
        if t == "genre":
            return ("genre", p.get("_genre"))
        if t == "radio":
            return ("radio", p.get("chemin"))
        return ("piste", p.get("id") or p.get("chemin"))

    def _cle_vue(self) -> tuple:
        return (
            self.mode_onglet,
            (self.playlist_ouverte or {}).get("id") if self.mode_onglet == "playlists" else None,
            self.artiste_ouvert if self.mode_onglet == "artistes" else None,
            self.album_ouvert if self.mode_onglet == "albums" else None,
            self.dossier_ouvert if self.mode_onglet == "dossiers" else None,
            self.genre_ouvert if self.mode_onglet == "genres" else None,
        )

    def _cle_selectionnee(self) -> tuple | None:
        if 0 <= self.index_selection < len(self.pistes_filtrees):
            return self._cle_entree(self.pistes_filtrees[self.index_selection])
        return None

    def _restaurer_selection(self, cle: tuple | None, defaut: int):
        """Replace le curseur sur l'élément `cle` (le plus proche de l'ancienne position)."""
        liste = self.pistes_filtrees
        if cle is not None and liste:
            if (
                0 <= self.index_selection < len(liste)
                and self._cle_entree(liste[self.index_selection]) == cle
            ):
                return
            positions = [i for i, p in enumerate(liste) if self._cle_entree(p) == cle]
            if positions:
                self.index_selection = min(
                    positions, key=lambda i: abs(i - self.index_selection)
                )
                return
        self.index_selection = max(0, min(defaut, len(liste) - 1))

    def construire_entrees_dossiers(self) -> list[dict[str, Any]]:
        """Regroupe les morceaux par dossier parent."""
        compteur: dict[str, list[dict[str, Any]]] = {}
        for p in self.pistes:
            dos = (p.get("dossier") or "").strip()
            if not dos and p.get("chemin"):
                dos = Path(str(p["chemin"])).parent.name or "Racine"
            dos = dos or "Racine"
            compteur.setdefault(dos, []).append(p)
        entrees: list[dict[str, Any]] = []
        for dos in sorted(compteur.keys(), key=lambda s: bibliotheque.sans_accents(s).lower()):
            ps = sorted(
                compteur[dos],
                key=lambda x: (int(x.get("numero") or 999), (x.get("titre") or "").lower()),
            )
            dur_tot = sum(float(x.get("duree") or 0.0) for x in ps)
            entrees.append(
                {
                    "_type": "dossier",
                    "id": f"dos:{dos}",
                    "titre": f"📁 {dos}",
                    "artiste": f"{len(ps)} titre{'s' if len(ps) > 1 else ''}",
                    "album": "",
                    "duree": dur_tot,
                    "_dossier": dos,
                    "_pistes": ps,
                }
            )
        return entrees

    def construire_entrees_genres(self) -> list[dict[str, Any]]:
        """Regroupe les morceaux par genre musical."""
        compteur: dict[str, list[dict[str, Any]]] = {}
        for p in self.pistes:
            g = (p.get("genre") or "").strip() or "Non classé"
            compteur.setdefault(g, []).append(p)
        entrees: list[dict[str, Any]] = []
        for g, ps in sorted(
            compteur.items(),
            key=lambda kv: (-len(kv[1]), bibliotheque.sans_accents(kv[0]).lower()),
        ):
            dur_tot = sum(float(x.get("duree") or 0.0) for x in ps)
            entrees.append(
                {
                    "_type": "genre",
                    "id": f"genre:{g}",
                    "titre": f"🏷 {g}",
                    "artiste": f"{len(ps)} titre{'s' if len(ps) > 1 else ''}",
                    "album": "",
                    "duree": dur_tot,
                    "_genre": g,
                    "_pistes": ps,
                }
            )
        return entrees

    def trier_entrees(self, entrees: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Applique le tri actif sur une liste de morceaux."""
        if (
            self.tri_mode == "defaut"
            or not entrees
            or self.mode_onglet in ("file", "recents", "radios")
            or any(
                p.get("_type") in ("artiste", "album", "playlist", "dossier", "genre")
                for p in entrees[:3]
            )
        ):
            return entrees

        def _annee(p: dict[str, Any]) -> int:
            an = str(p.get("annee") or "").strip()[:4]
            return int(an) if an.isdigit() else 0

        def _score_qualite(p: dict[str, Any]) -> tuple[int, int, int, int]:
            fmt = (p.get("format") or "").lower()
            bits = int(p.get("bits") or 0)
            freq = int(p.get("frequence") or 0)
            debit = int(p.get("debit") or 0)
            lossless = 1 if fmt in ("flac", "alac", "wav", "aiff", "dsf") else 0
            return (1 if bits >= 24 else 0, lossless, freq, debit)

        if self.tri_mode == "titre":
            return sorted(
                entrees,
                key=lambda p: bibliotheque.sans_accents(p.get("titre") or "").lower(),
            )
        if self.tri_mode == "artiste":
            return sorted(
                entrees,
                key=lambda p: (
                    bibliotheque.sans_accents(p.get("artiste") or "").lower(),
                    bibliotheque.sans_accents(p.get("album") or "").lower(),
                    int(p.get("numero") or 999),
                    bibliotheque.sans_accents(p.get("titre") or "").lower(),
                ),
            )
        if self.tri_mode == "album":
            return sorted(
                entrees,
                key=lambda p: (
                    bibliotheque.sans_accents(p.get("album") or "").lower(),
                    int(p.get("numero") or 999),
                    bibliotheque.sans_accents(p.get("titre") or "").lower(),
                ),
            )
        if self.tri_mode == "duree":
            return sorted(entrees, key=lambda p: -float(p.get("duree") or 0.0))
        if self.tri_mode == "annee":
            return sorted(
                entrees,
                key=lambda p: (
                    -_annee(p),
                    bibliotheque.sans_accents(p.get("album") or "").lower(),
                    int(p.get("numero") or 999),
                ),
            )
        if self.tri_mode in ("ajouts", "ajoute"):
            return sorted(
                entrees,
                key=lambda p: (-float(p.get("ajoute") or 0.0), -int(p.get("id") or 0)),
            )
        if self.tri_mode == "ecoutes":
            return sorted(
                entrees,
                key=lambda p: (
                    -int(p.get("ecoutes") or 0),
                    bibliotheque.sans_accents(p.get("titre") or "").lower(),
                ),
            )
        if self.tri_mode == "qualite":
            return sorted(entrees, key=_score_qualite, reverse=True)
        return entrees

    def filtrer_pistes(self):
        q = bibliotheque.sans_accents(self.terme_recherche.lower().strip())
        vue = self._cle_vue()
        vue_avant = self._vue_filtree
        cle_avant = self._cle_selectionnee()
        if vue_avant is not None and cle_avant is not None:
            self._selection_par_vue[vue_avant] = cle_avant
        base: list[dict[str, Any]] = self.pistes

        if self.mode_onglet == "favoris":
            base = [p for p in self.pistes if p.get("id") in self.favoris_set]
        elif self.mode_onglet == "file":
            base = list(self.file_attente)
        elif self.mode_onglet == "recents":
            base = self.charger_pistes_recentes()
        elif self.mode_onglet == "radios":
            base = self.construire_entrees_radios()
        elif self.mode_onglet == "playlists":
            if self.playlist_ouverte:
                pistes_map = {p["id"]: p for p in self.pistes if p.get("id")}
                ids = self.playlist_ouverte.get("pistes") or []
                base = [pistes_map[i] for i in ids if i in pistes_map]
            else:
                base = self.construire_entrees_playlists()
        elif self.mode_onglet == "artistes":
            if self.artiste_ouvert:
                base = [
                    p
                    for p in self.pistes
                    if (p.get("artiste") or "Artiste inconnu").strip()
                    == self.artiste_ouvert
                ]
            else:
                base = self.construire_entrees_artistes()
        elif self.mode_onglet == "albums":
            if self.album_ouvert:
                base = sorted(
                    [
                        p
                        for p in self.pistes
                        if ((p.get("album") or "").strip() or "Singles & Hors-album")
                        == self.album_ouvert
                    ],
                    key=lambda x: (int(x.get("numero") or 999), (x.get("titre") or "").lower()),
                )
            else:
                base = self.construire_entrees_albums()
        elif self.mode_onglet == "dossiers":
            if self.dossier_ouvert:
                base = sorted(
                    [
                        p
                        for p in self.pistes
                        if (
                            (p.get("dossier") or "").strip()
                            or (
                                Path(str(p["chemin"])).parent.name
                                if p.get("chemin")
                                else "Racine"
                            )
                        )
                        == self.dossier_ouvert
                    ],
                    key=lambda x: (int(x.get("numero") or 999), (x.get("titre") or "").lower()),
                )
            else:
                base = self.construire_entrees_dossiers()
        elif self.mode_onglet == "genres":
            if self.genre_ouvert:
                base = [
                    p
                    for p in self.pistes
                    if ((p.get("genre") or "").strip() or "Non classé") == self.genre_ouvert
                ]
            else:
                base = self.construire_entrees_genres()

        base = self.trier_entrees(base)

        if not q:
            self.pistes_filtrees = list(base)
        else:
            mots = q.split()
            res = []
            for p in base:
                titre = bibliotheque.sans_accents((p.get("titre") or "").lower())
                artiste = bibliotheque.sans_accents((p.get("artiste") or "").lower())
                album = bibliotheque.sans_accents((p.get("album") or "").lower())
                genre = bibliotheque.sans_accents((p.get("genre") or "").lower())
                texte_global = f"{titre} {artiste} {album} {genre}"
                score = 0
                if q == titre:
                    score += 100
                elif q in titre:
                    score += 60
                elif q in artiste:
                    score += 40
                elif all(m in texte_global for m in mots):
                    score += 30
                elif any(m in texte_global for m in mots):
                    score += 10
                if score > 0:
                    res.append((score, p))
            res.sort(key=lambda x: -x[0])
            self.pistes_filtrees = [p for _, p in res]

        if vue != vue_avant:
            self._restaurer_selection(self._selection_par_vue.get(vue), 0)
            self._liste_debut = 0
        elif q != self._terme_filtre and q:
            self.index_selection = 0
            self._liste_debut = 0
        else:
            self._restaurer_selection(cle_avant, self.index_selection)
        self._vue_filtree = vue
        self._terme_filtre = q
        self._tri_filtre = self.tri_mode

    def aller_a_piste_courante(self):
        """Place le curseur sur le titre en lecture (uniquement à la demande)."""
        if not self.piste_courante:
            self.notifier("Aucun titre en lecture")
            return
        cle = self._cle_entree(self.piste_courante)
        for i, p in enumerate(self.pistes_filtrees):
            if self._cle_entree(p) == cle:
                self.index_selection = i
                return
        self.notifier("Le titre en lecture n'est pas dans cette liste")

    def charger_paroles_async(self, pid: int, forcer: bool = False):
        with self._verrou_paroles:
            self.paroles_en_chargement = True
            self.paroles_items = []
            self.paroles_texte_libre = None
            self.paroles_source = "Recherche en cours..."

        def tache():
            try:
                donnees = paroles.paroles(pid, forcer=forcer)
                notifie = False
                with self._verrou_paroles:
                    if (
                        self.piste_courante
                        and self.piste_courante.get("id") == pid
                    ):
                        if donnees and donnees.get("synchro"):
                            self.paroles_items = preparer_synchro_cli(
                                donnees["synchro"], donnees.get("mots")
                            )
                            self.paroles_source = donnees.get("source", "synchro")
                            notifie = True
                        elif donnees and donnees.get("texte"):
                            self.paroles_texte_libre = donnees["texte"]
                            self.paroles_source = donnees.get("source", "texte")
                        else:
                            self.paroles_items = []
                            self.paroles_source = "Aucune parole trouvée"
                        self.paroles_en_chargement = False
                if notifie and self.mpris:
                    self.mpris.notifier_changement(["Metadata", "PlaybackStatus"])
                    self.mpris.emettre_seeked(self.lecteur.position)
            except (OSError, ValueError, RuntimeError) as ex:
                with self._verrou_paroles:
                    self.paroles_en_chargement = False
                    self.paroles_source = f"Erreur paroles : {ex}"

        threading.Thread(target=tache, daemon=True).start()

    def jouer_piste(self, piste: dict[str, Any], position_initiale: float = 0.0):
        # Si c'est un groupe (artiste, album, playlist ou dossier), entrer dedans
        if piste.get("_type") == "artiste":
            self.artiste_ouvert = piste.get("_nom_artiste")
            self.filtrer_pistes()
            return
        if piste.get("_type") == "album":
            self.album_ouvert = piste.get("_nom_album")
            self.filtrer_pistes()
            return
        if piste.get("_type") == "playlist":
            self.playlist_ouverte = piste.get("_playlist")
            self.filtrer_pistes()
            return
        if piste.get("_type") == "dossier":
            self.dossier_ouvert = piste.get("_dossier")
            self.filtrer_pistes()
            return
        if piste.get("_type") == "genre":
            self.genre_ouvert = piste.get("_genre")
            self.filtrer_pistes()
            return

        self.piste_courante = piste
        pid = piste.get("id")
        cle_dec = str(pid) if pid else str(piste.get("chemin") or "")
        self.decalage_paroles = float(self.decalages_paroles.get(cle_dec, 0.0))
        self.boucle_a = None
        self.boucle_b = None
        self._debut_piste_ts = time.time()
        self._transition_fondu_en_cours = False
        self.derniere_position = max(0.0, float(position_initiale))

        # Flux radio en direct (HTTP/HTTPS)
        if piste.get("_type") == "radio":
            url = str(piste.get("chemin") or "")
            if not url.startswith(("http://", "https://")):
                self.notifier("URL de flux radio invalide")
                return
            self.lecteur.jouer(url)
            self.actualiser_palette_et_fond()
            self.gain_piste_db = 0.0
            self.gain_source = "DIRECT"
            self.gain_en_analyse = False
            self.appliquer_gain_et_fondu(forcer=True)
            if self.mpris:
                self.mpris.notifier_changement(["Metadata", "PlaybackStatus"])
            with self._verrou_paroles:
                self.paroles_items = []
                self.paroles_texte_libre = None
                self.paroles_source = "Radio en direct"
                self.paroles_en_chargement = False
            self.notifier(f"📻 Connexion au direct : {piste.get('titre')}")
            return

        chemin = piste.get("chemin") or bibliotheque.chemin_piste(pid)
        piste["chemin"] = chemin
        if not chemin or not os.path.exists(chemin):
            self.notifier(f"Fichier audio introuvable : {piste.get('titre')}")
            return

        dur = float(piste.get("duree") or 0.0)
        pos_dep = position_initiale if 0.5 < position_initiale < max(0.0, dur - 3.0) else 0.0
        self.lecteur.jouer(chemin, position_initiale=pos_dep, duree_connue=dur)
        self.actualiser_palette_et_fond()
        self.actualiser_normalisation_piste()
        self.appliquer_gain_et_fondu(forcer=True)
        self.sauvegarder_etat_cli()
        if self.mpris:
            self.mpris.notifier_changement(["Metadata", "PlaybackStatus"])
            self.mpris.emettre_seeked(pos_dep)

        if pid:
            with contextlib.suppress(Exception):
                bibliotheque.noter_ecoute(pid)
            self.charger_paroles_async(pid)
        else:
            self.paroles_items = []
            self.paroles_source = ""

        try:
            self.index_courant = [
                p.get("id") for p in self.pistes_filtrees
            ].index(pid)
        except ValueError:
            self.index_courant = -1

    def jouer_collection(self, aleatoire: bool = False):
        """Lance la lecture de la collection sélectionnée ou de la liste visible."""
        cibles: list[dict[str, Any]] = []
        if self.pistes_filtrees and 0 <= self.index_selection < len(self.pistes_filtrees):
            sel = self.pistes_filtrees[self.index_selection]
            if sel.get("_type") in ("artiste", "album", "playlist", "dossier", "genre"):
                cibles = list(sel.get("_pistes") or [])
        if not cibles:
            cibles = [p for p in self.pistes_filtrees if not p.get("_type")]
        if not cibles:
            self.notifier("Aucun morceau à lancer dans cette sélection")
            return
        if aleatoire:
            random.shuffle(cibles)
        self.file_attente = list(cibles[1:])
        self.jouer_piste(cibles[0])
        self.notifier(f"▶ Collection lancée ({len(cibles)} titres)")

    def actualiser_normalisation_piste(self):
        """Récupère ou lance l'analyse ReplayGain / EBU R128 pour la piste courante."""
        pid = self.piste_courante.get("id") if self.piste_courante else None
        if not pid:
            self.gain_piste_db = 0.0
            self.gain_source = ""
            self.gain_en_analyse = False
            return
        try:
            res = volume.niveau(pid)
            etat = res.get("etat")
            if etat == "pret":
                self.gain_piste_db = float(res.get("gain_db") or 0.0)
                self.gain_source = str(res.get("source") or "EBU R128")
                self.gain_en_analyse = False
            elif etat in ("analyse", "en_attente"):
                self.gain_piste_db = 0.0
                self.gain_source = "Analyse..."
                self.gain_en_analyse = True
                self._dernier_poll_gain = time.time()
            else:
                self.gain_piste_db = 0.0
                self.gain_source = ""
                self.gain_en_analyse = False
        except (OSError, ValueError, RuntimeError):
            self.gain_piste_db = 0.0
            self.gain_source = ""
            self.gain_en_analyse = False

    def appliquer_gain_et_fondu(self, forcer: bool = False):
        """Calcule en temps réel le gain dB combiné (Normalisation EBU R128 + Fondu enchaîné)."""
        maintenant = time.time()
        if self.gain_en_analyse and maintenant - self._dernier_poll_gain >= 0.8:
            self._dernier_poll_gain = maintenant
            self.actualiser_normalisation_piste()
            forcer = True

        base_db = self.gain_piste_db if self.normalisation_active else 0.0
        fondu_db = 0.0

        en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        if self.fondu_duree > 0 and en_lec:
            pos = self.lecteur.position
            dur = self.lecteur.duree or (
                float(self.piste_courante.get("duree") or 0.0)
                if self.piste_courante
                else 0.0
            )
            f_dur = float(self.fondu_duree)
            ecoule_debut = min(pos if pos > 0 else (maintenant - self._debut_piste_ts), f_dur)
            if 0.0 <= ecoule_debut < f_dur:
                ratio_in = max(0.0, min(1.0, ecoule_debut / f_dur))
                fondu_db = -24.0 * ((1.0 - ratio_in) ** 1.6)
            elif dur > f_dur * 2.2 and pos > 0:
                restant = dur - pos
                if 0.15 < restant <= f_dur:
                    ratio_out = max(0.0, min(1.0, restant / f_dur))
                    fondu_db = -26.0 * ((1.0 - ratio_out) ** 1.6)
                elif restant <= 0.15 and not self._transition_fondu_en_cours:
                    self._transition_fondu_en_cours = True
                    self.sur_fin_piste()
                    return

        cible_db = round(base_db + fondu_db, 2)
        if forcer or abs(cible_db - self.lecteur.gain_db) >= 0.25:
            self.lecteur.definir_gain_db(cible_db)

    def basculer_normalisation(self):
        self.normalisation_active = not self.normalisation_active
        self.appliquer_gain_et_fondu(forcer=True)
        self.sauvegarder_etat_cli()
        if self.normalisation_active:
            detail = (
                f" ({self.gain_piste_db:+.1f} dB • {self.gain_source})"
                if self.gain_source
                else ""
            )
            self.notifier(f"⚖ Normalisation EBU R128 : Activée{detail}")
        else:
            self.notifier("⚖ Normalisation audio : Désactivée (0.0 dB)")

    def cycler_fondu(self):
        cycles = [0, 2, 4, 6]
        idx = (
            (cycles.index(self.fondu_duree) + 1) % len(cycles)
            if self.fondu_duree in cycles
            else 1
        )
        self.fondu_duree = cycles[idx]
        self.appliquer_gain_et_fondu(forcer=True)
        self.sauvegarder_etat_cli()
        if self.fondu_duree > 0:
            self.notifier(f"🎚 Fondu enchaîné (Crossfade) : {self.fondu_duree}s")
        else:
            self.notifier("🎚 Fondu enchaîné : Désactivé")

    def sur_fin_piste(self):
        if self.veille_mode == -1:
            self.veille_mode = 0
            if not self.lecteur.en_pause:
                self.lecteur.basculer_pause()
            self.notifier("🌙 Veille activée : arrêt en fin de titre")
            return
        self.piste_suivante()

    def _choisir_piste_autodj(self) -> dict[str, Any] | None:
        if len(self.pistes) < 2:
            return None
        pid_cur = self.piste_courante.get("id") if self.piste_courante else None
        genre_cur = (
            bibliotheque.sans_accents((self.piste_courante.get("genre") or "").lower())
            if self.piste_courante
            else ""
        )
        art_cur = (
            bibliotheque.sans_accents((self.piste_courante.get("artiste") or "").lower())
            if self.piste_courante
            else ""
        )
        candidats = [p for p in self.pistes if p.get("id") != pid_cur]
        if not candidats:
            return None
        similaires = [
            p
            for p in candidats
            if (genre_cur and genre_cur in bibliotheque.sans_accents((p.get("genre") or "").lower()))
            or (art_cur and art_cur == bibliotheque.sans_accents((p.get("artiste") or "").lower()))
        ]
        pool = similaires if similaires and random.random() < 0.72 else candidats
        return random.choice(pool)

    def piste_suivante(self):
        if self.file_attente:
            suiv = self.file_attente.pop(0)
            self.jouer_piste(suiv)
            if self.mode_onglet == "file":
                self.filtrer_pistes()
            return

        if self.mode_repetition == "un" and self.piste_courante:
            self.jouer_piste(self.piste_courante)
            return

        liste = [
            p for p in (self.pistes_filtrees or self.pistes) if not p.get("_type")
        ] or self.pistes
        if not liste:
            if self.auto_dj:
                dj = self._choisir_piste_autodj()
                if dj:
                    self.jouer_piste(dj)
                    self.notifier(f"🎧 Auto-DJ : {dj.get('titre')} — {dj.get('artiste')}")
            return

        if self.mode_aleatoire:
            if len(liste) > 1 and self.piste_courante:
                pid_cur = self.piste_courante.get("id")
                autres = [p for p in liste if p.get("id") != pid_cur]
                suiv = random.choice(autres or liste)
            else:
                suiv = random.choice(liste)
            self.jouer_piste(suiv)
            return

        pid_actuel = self.piste_courante.get("id") if self.piste_courante else None
        ids = [p.get("id") for p in liste]
        idx = ids.index(pid_actuel) if pid_actuel in ids else self.index_courant

        if idx >= 0 and idx + 1 < len(liste):
            self.jouer_piste(liste[idx + 1])
        elif self.auto_dj:
            dj = self._choisir_piste_autodj()
            if dj:
                self.jouer_piste(dj)
                self.notifier(f"🎧 Auto-DJ : {dj.get('titre')} — {dj.get('artiste')}")
        elif self.mode_repetition == "tout" and liste:
            self.jouer_piste(liste[0])

    def piste_precedente(self):
        if (
            self.lecteur.position > 3.0
            and self.piste_courante
            and self.piste_courante.get("_type") != "radio"
        ):
            self.lecteur.aller_a(0.0)
            if self.mpris:
                self.mpris.emettre_seeked(0.0)
            return

        liste = [
            p for p in (self.pistes_filtrees or self.pistes) if not p.get("_type")
        ] or self.pistes
        if not liste:
            return

        pid_actuel = self.piste_courante.get("id") if self.piste_courante else None
        ids = [p.get("id") for p in liste]
        idx = ids.index(pid_actuel) if pid_actuel in ids else self.index_courant

        if idx > 0:
            self.jouer_piste(liste[idx - 1])
        elif self.mode_repetition == "tout" and liste:
            self.jouer_piste(liste[-1])

    def basculer_favori_selection(self):
        if not self.pistes_filtrees:
            return
        p = self.pistes_filtrees[self.index_selection]
        if p.get("_type") == "radio":
            r = p.get("_radio") or {}
            url = r.get("url")
            if not url:
                return
            fav_urls = {x.get("url") for x in self.radios_favorites if x.get("url")}
            if url in fav_urls:
                bibliotheque.supprimer_radio(url)
                self.notifier(f"☆ Radio retirée des favoris : {r.get('nom')}")
            else:
                bibliotheque.ajouter_radio(r)
                self.notifier(f"★ Radio ajoutée aux favoris : {r.get('nom')}")
            self.radios_favorites = bibliotheque.radios()
            self.filtrer_pistes()
            return
        if p.get("_type"):
            return
        pid = p.get("id")
        if not pid:
            return
        try:
            est_fav = bibliotheque.basculer_favori(pid)
            if est_fav:
                self.favoris_set.add(pid)
                self.notifier(f"♥ Ajouté aux favoris : {p.get('titre')}")
            else:
                self.favoris_set.discard(pid)
                self.notifier(f"♡ Retiré des favoris : {p.get('titre')}")
            if self.mode_onglet == "favoris":
                self.filtrer_pistes()
        except (OSError, ValueError) as e:
            self.notifier(f"Erreur favori : {e}")

    def ajouter_selection_file(self):
        if not self.pistes_filtrees:
            return
        p = self.pistes_filtrees[self.index_selection]
        if p.get("_type") in ("artiste", "album", "playlist", "dossier"):
            sous = p.get("_pistes") or []
            self.file_attente.extend(sous)
            self.notifier(f"⏳ {len(sous)} titres ajoutés à la file")
            return
        self.file_attente.append(p)
        self.notifier(f"⏳ Ajouté à la file : {p.get('titre')}")

    def jouer_selection_ensuite(self):
        """Insère la sélection en tête de la file d'attente (Play Next)."""
        if not self.pistes_filtrees:
            return
        p = self.pistes_filtrees[self.index_selection]
        if p.get("_type") in ("artiste", "album", "playlist", "dossier"):
            sous = list(p.get("_pistes") or [])
            if sous:
                self.file_attente = sous + self.file_attente
                self.notifier(f"⏭ {len(sous)} titres joueront ensuite")
            return
        self.file_attente.insert(0, p)
        self.notifier(f"⏭ Jouera ensuite : {p.get('titre')}")

    def retirer_selection_file(self):
        if (
            self.mode_onglet == "file"
            and self.file_attente
            and 0 <= self.index_selection < len(self.file_attente)
        ):
            retire = self.file_attente.pop(self.index_selection)
            self.filtrer_pistes()
            self.notifier(f"Retiré de la file : {retire.get('titre')}")

    def retirer_selection_liste(self):
        """Retire l'élément sélectionné dans la file d'attente ou la playlist ouverte."""
        if self.mode_onglet == "file":
            self.retirer_selection_file()
            return
        if self.mode_onglet == "playlists" and self.playlist_ouverte:
            pl = self.playlist_ouverte
            ids = list(pl.get("pistes") or [])
            if 0 <= self.index_selection < len(self.pistes_filtrees):
                cible = self.pistes_filtrees[self.index_selection]
                cid = cible.get("id")
                nouveaux = [i for i in ids if i != cid]
                if len(nouveaux) != len(ids):
                    bibliotheque.ordonner_playlist(pl["id"], nouveaux)
                    self.recharger_bibliotheque()
                    for pl2 in self.playlists_liste:
                        if pl2.get("id") == pl["id"]:
                            self.playlist_ouverte = pl2
                            break
                    self.filtrer_pistes()
                    self.notifier(f"✕ Retiré de la playlist : {cible.get('titre')}")

    def deplacer_entree_liste(self, delta: int):
        """Déplace la ligne sélectionnée vers le haut (-1) ou le bas (+1) dans File / Playlist."""
        if self.terme_recherche:
            self.notifier("Efface le filtre avant de réordonner la liste")
            return
        if self.mode_onglet == "file" and self.file_attente:
            idx = self.index_selection
            cible = idx + delta
            if 0 <= idx < len(self.file_attente) and 0 <= cible < len(self.file_attente):
                self.file_attente[idx], self.file_attente[cible] = (
                    self.file_attente[cible],
                    self.file_attente[idx],
                )
                self.index_selection = cible
                self.filtrer_pistes()
            return
        if self.mode_onglet == "playlists" and self.playlist_ouverte:
            pl = self.playlist_ouverte
            ids = list(pl.get("pistes") or [])
            idx = self.index_selection
            cible = idx + delta
            if 0 <= idx < len(ids) and 0 <= cible < len(ids):
                ids[idx], ids[cible] = ids[cible], ids[idx]
                bibliotheque.ordonner_playlist(pl["id"], ids)
                self.recharger_bibliotheque()
                for pl2 in self.playlists_liste:
                    if pl2.get("id") == pl["id"]:
                        self.playlist_ouverte = pl2
                        break
                self.index_selection = cible
                self.filtrer_pistes()
                self.notifier("↕ Ordre de la playlist mis à jour")

    def renommer_playlist_selection(self):
        pl = None
        if self.mode_onglet == "playlists":
            if self.playlist_ouverte:
                pl = self.playlist_ouverte
            elif 0 <= self.index_selection < len(self.pistes_filtrees):
                ent = self.pistes_filtrees[self.index_selection]
                if ent.get("_type") == "playlist":
                    pl = ent.get("_playlist")
        if not pl:
            self.notifier("Ouvre ou sélectionne une playlist à renommer ([F2])")
            return
        self._fermer_toutes_modales()
        self.modal_playlist_mode = "renommer"
        self.nom_nouvelle_playlist = str(pl.get("nom") or "")
        self.pistes_cibles_playlist = [int(pl["id"])]
        self.titre_cible_playlist = str(pl.get("nom") or "")

    def cycler_mode_fond(self):
        modes = ["pochette", "photo", "aurore", "aucun"]
        noms = {
            "pochette": "🖼 Fond : Pochette Dynamique",
            "photo": "🖼 Fond : Photo Personnalisée",
            "aurore": "🌌 Fond : Aurore Liquid Glass",
            "aucun": "🪟 Fond : Verre Transparent",
        }
        idx = (modes.index(self.fond.mode_fond) + 1) % len(modes)
        self.fond.mode_fond = modes[idx]
        if self.fond.mode_fond == "photo" and not self.fond.chemin_photo_perso:
            self.scanner_photos_disponibles()
            if self.photos_disponibles:
                self.fond.chemin_photo_perso = self.photos_disponibles[0][1]
        self.actualiser_palette_et_fond()
        self.sauvegarder_etat_cli()
        self.notifier(noms[self.fond.mode_fond])

    def cycler_rendu_fond(self):
        self.fond.mode_rendu = (
            "canevas" if self.fond.mode_rendu == "kitty" else "kitty"
        )
        self.actualiser_palette_et_fond()
        self.sauvegarder_etat_cli()
        label = (
            "Kitty HD (GPU)"
            if self.fond.mode_rendu == "kitty"
            else "Canevas Pixel TrueColor (▀)"
        )
        self.notifier(f"🖥 Moteur de fond : {label}")

    def cycler_luminosite_fond(self):
        self.fond.index_luminosite = (self.fond.index_luminosite + 1) % len(
            NIVEAUX_LUMINOSITE
        )
        self.fond.synchroniser_kitty_hd()
        self.sauvegarder_etat_cli()
        self.notifier(f"☀ Luminosité du fond : {self.fond.label_luminosite}")

    def cycler_theme(self):
        idx = (ORDRE_THEMES.index(self.theme_code) + 1) % len(ORDRE_THEMES)
        self.theme_code = ORDRE_THEMES[idx]
        self.actualiser_palette_et_fond()
        self.sauvegarder_etat_cli()
        self.notifier(f"🎨 Thème : {THEMES[self.theme_code]['nom']}")

    def cycler_visualiseur(self):
        codes = [k for k, _ in MODES_VISUALISEUR]
        idx = (
            (codes.index(self.visualiseur_mode) + 1) % len(codes)
            if self.visualiseur_mode in codes
            else 0
        )
        self.visualiseur_mode = codes[idx]
        nom = dict(MODES_VISUALISEUR)[self.visualiseur_mode]
        self.sauvegarder_etat_cli()
        self.notifier(f"🌊 Visualiseur : {nom}")

    def cycler_tri(self):
        codes = [k for k, _ in TRIS_LISTE]
        idx = (
            (codes.index(self.tri_mode) + 1) % len(codes)
            if self.tri_mode in codes
            else 0
        )
        self.tri_mode = codes[idx]
        nom = dict(TRIS_LISTE)[self.tri_mode]
        self.filtrer_pistes()
        self.sauvegarder_etat_cli()
        self.notifier(f"⇅ Tri : {nom}")

    def basculer_muet(self):
        etat = self.lecteur.basculer_muet()
        self.notifier("🔇 Son coupé" if etat else f"🔊 Son rétabli ({int(self.lecteur.volume)}%)")

    def enregistrer_decalage_parole(self, delta_sec: float):
        nouv = max(-60.0, min(60.0, round(self.decalage_paroles + delta_sec, 2)))
        self.decalage_paroles = nouv
        if self.piste_courante:
            pid = self.piste_courante.get("id")
            cle = str(pid) if pid else str(self.piste_courante.get("chemin") or "")
            if abs(nouv) < 0.01:
                self.decalages_paroles.pop(cle, None)
            else:
                self.decalages_paroles[cle] = nouv
            self.sauvegarder_etat_cli()
        self.notifier(f"⏱ Calage paroles : {self.decalage_paroles:+.2f}s")

    def scanner_bibliotheque_cli(self, nettoyer: bool = False):
        if bibliotheque.ETAT_SCAN.get("en_cours"):
            self.notifier("↻ Scan déjà en cours en arrière-plan…")
            return
        self._statut_scan_cli = "Scan en cours…"
        self.notifier("↻ Scan de la bibliothèque lancé…")

        def _tache():
            try:
                bibliotheque.scanner(complet=False)
                if nettoyer:
                    bibliotheque.nettoyer_bibliotheque()
                self.recharger_bibliotheque()
                self._statut_scan_cli = f"À jour ({len(self.pistes)} titres)"
                self.notifier(f"✅ Bibliothèque à jour ({len(self.pistes)} titres)")
            except Exception as ex:  # noqa: BLE001
                self._statut_scan_cli = f"Erreur scan : {ex}"
                self.notifier(f"Erreur scan : {ex}")

        threading.Thread(target=_tache, daemon=True, name="onde-cli-scan").start()

    def exporter_sauvegarde_cli(self):
        try:
            donnees = outils.creer({"onde.decalages": self.decalages_paroles})
            cible = config.DONNEES / "sauvegarde-onde.json"
            cible.write_text(
                json.dumps(donnees, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.notifier(f"💾 Sauvegarde exportée : {cible.name}", duree=4.0)
        except Exception as ex:  # noqa: BLE001
            self.notifier(f"Erreur export : {ex}")

    def restaurer_sauvegarde_cli(self):
        cible = config.DONNEES / "sauvegarde-onde.json"
        if not cible.is_file():
            self.notifier(f"Aucune sauvegarde trouvée ({cible.name})")
            return
        try:
            donnees = json.loads(cible.read_text(encoding="utf-8"))
            bilan = outils.restaurer(donnees)
            decs = (bilan.get("client") or {}).get("onde.decalages")
            if isinstance(decs, dict):
                self.decalages_paroles.update(
                    {str(k): float(v) for k, v in decs.items()}
                )
            self.recharger_bibliotheque()
            self.notifier(
                f"✅ Restauré : {bilan.get('playlists', 0)} playlists, "
                f"{bilan.get('favoris', 0)} favoris, {bilan.get('radios', 0)} radios",
                duree=4.0,
            )
        except Exception as ex:  # noqa: BLE001
            self.notifier(f"Erreur restauration : {ex}")

    def cycler_egaliseur(self):
        self.eq_perso_actif = False
        self.eq_index = (self.eq_index + 1) % len(PROFILS_EQ)
        nom, _ = PROFILS_EQ[self.eq_index]
        if self.eq_index < len(PROFILS_EQ_BANDES):
            self.eq_bandes = list(PROFILS_EQ_BANDES[self.eq_index])
        self.appliquer_egaliseur_courant()
        self.sauvegarder_etat_cli()
        self.notifier(f"🎛 Égaliseur : {nom} ([Maj+E] pour l'Égaliseur 10 bandes)")

    def _fermer_toutes_modales(self):
        self.aide_ouverte = False
        self.galerie_ouverte = False
        self.stats_ouverte = False
        self.yt_ouvert = False
        self.modal_playlist_mode = None
        self.eq_perso_ouvert = False
        self.paroles_recherche_ouverte = False
        self.paroles_studio_ouvert = False
        self.palette_cmd_ouverte = False
        self.reglages_ouvert = False
        self.doublons_ouvert = False
        self.proprietes_ouvertes = False
        self.tags_ouvert = False

    def ouvrir_palette_commandes(self):
        est_ouv = not self.palette_cmd_ouverte
        self._fermer_toutes_modales()
        self.palette_cmd_ouverte = est_ouv
        if est_ouv:
            self.palette_cmd_requete = ""
            self.palette_cmd_index = 0

    def _piste_locale_cible(self) -> dict[str, Any] | None:
        if self.piste_courante and not self.piste_courante.get("_type") and self.piste_courante.get("id"):
            return self.piste_courante
        if self.pistes_filtrees and 0 <= self.index_selection < len(self.pistes_filtrees):
            sel = self.pistes_filtrees[self.index_selection]
            if not sel.get("_type") and sel.get("id"):
                return sel
        return None

    def ouvrir_studio_paroles(self):
        if self.paroles_studio_ouvert:
            self.paroles_studio_ouvert = False
            return
        cible = self._piste_locale_cible()
        if not cible or not cible.get("id"):
            self.notifier("Lance ou sélectionne un titre local pour le Studio Paroles")
            return
        self._fermer_toutes_modales()
        self.paroles_studio_ouvert = True
        self.paroles_studio_saisie = False
        self.paroles_studio_resultats = []
        self.paroles_studio_index = 0
        self.paroles_studio_message = ""
        prop = None
        with contextlib.suppress(Exception):
            prop = paroles.proposition(int(cible["id"]))
        q_init = (
            f"{prop.get('artiste', '')} {prop.get('titre', '')}".strip()
            if prop
            else f"{cible.get('artiste', '')} {cible.get('titre', '')}".strip()
        )
        self.paroles_studio_requete = q_init
        if q_init:
            self.chercher_studio_paroles(q_init, float(cible.get("duree") or 0.0))

    def chercher_studio_paroles(self, q: str, duree: float | None = None):
        q = q.strip()
        if not q:
            return
        self.paroles_studio_en_cours = True
        self.paroles_studio_message = ""

        def _tache():
            try:
                res = paroles.chercher(q, duree=duree)
                self.paroles_studio_resultats = res
                self.paroles_studio_index = 0
                if not res:
                    self.paroles_studio_message = "Aucun résultat LRCLIB / NetEase"
            except Exception as ex:  # noqa: BLE001
                self.paroles_studio_message = str(ex)
            finally:
                self.paroles_studio_en_cours = False

        threading.Thread(target=_tache, daemon=True, name="onde-lyrics-search").start()

    def choisir_studio_parole(self, identifiant: Any):
        cible = self._piste_locale_cible()
        if not cible or not cible.get("id"):
            return
        pid = int(cible["id"])
        self.paroles_studio_en_cours = True
        self.paroles_studio_message = "Enregistrement et alignement…"

        def _tache():
            try:
                paroles.choisir(pid, identifiant)
                if self.piste_courante and self.piste_courante.get("id") == pid:
                    self.charger_paroles_async(pid, forcer=False)
                self.paroles_studio_ouvert = False
                self.notifier("✅ Paroles enregistrées et synchronisées !")
            except Exception as ex:  # noqa: BLE001
                self.paroles_studio_message = str(ex)
            finally:
                self.paroles_studio_en_cours = False

        threading.Thread(target=_tache, daemon=True, name="onde-lyrics-pick").start()

    def recaler_parole_courante(self):
        cible = self._piste_locale_cible()
        if not cible or not cible.get("id"):
            return
        pid = int(cible["id"])
        self.paroles_studio_en_cours = True
        self.paroles_studio_message = "Analyse vocale & recalage en cours…"
        self.notifier("🎙 Analyse vocale en cours pour recaler les paroles…")

        def _tache():
            try:
                paroles.recaler(pid)
                if self.piste_courante and self.piste_courante.get("id") == pid:
                    self.charger_paroles_async(pid, forcer=False)
                self.paroles_studio_message = "Recalage vocal terminé"
                self.notifier("✅ Paroles recalées sur la voix !")
            except Exception as ex:  # noqa: BLE001
                self.paroles_studio_message = str(ex)
                self.notifier(f"Erreur recalage : {ex}")
            finally:
                self.paroles_studio_en_cours = False

        threading.Thread(target=_tache, daemon=True, name="onde-lyrics-recal").start()

    def ouvrir_reglages(self):
        est_ouv = not self.reglages_ouvert
        self._fermer_toutes_modales()
        self.reglages_ouvert = est_ouv
        if est_ouv:
            self.reglages_section = 0
            self.reglages_index = 0

            def _charger_devs():
                devs = self.lecteur.lister_peripheriques_audio()
                if devs:
                    self.peripheriques_audio = devs

            threading.Thread(target=_charger_devs, daemon=True).start()

    def ouvrir_doublons(self):
        est_ouv = not self.doublons_ouvert
        self._fermer_toutes_modales()
        self.doublons_ouvert = est_ouv
        if est_ouv:
            self.lancer_scan_doublons()

    def lancer_scan_doublons(self):
        self.doublons_en_scan = True
        self.doublons_message = ""

        def _tache():
            try:
                grps = bibliotheque.doublons()
                self.doublons_groupes = grps
                self.doublons_groupe_index = 0
                self.doublons_copie_index = 0
                if not grps:
                    self.doublons_message = "Aucun doublon détecté dans la bibliothèque ✨"
            except Exception as ex:  # noqa: BLE001
                self.doublons_message = str(ex)
            finally:
                self.doublons_en_scan = False

        threading.Thread(target=_tache, daemon=True, name="onde-dupes").start()

    def fusionner_doublon_courant(self):
        if not self.doublons_groupes or not (
            0 <= self.doublons_groupe_index < len(self.doublons_groupes)
        ):
            return
        grp = self.doublons_groupes[self.doublons_groupe_index]
        if not isinstance(grp, list) or len(grp) < 2:
            return
        idx_garder = max(0, min(self.doublons_copie_index, len(grp) - 1))
        garder = grp[idx_garder]["id"]
        ids = [p["id"] for p in grp]
        try:
            bibliotheque.fusionner(garder, ids)
            self.recharger_bibliotheque()
            self.doublons_groupes.pop(self.doublons_groupe_index)
            self.doublons_groupe_index = max(
                0, min(self.doublons_groupe_index, len(self.doublons_groupes) - 1)
            )
            self.doublons_copie_index = 0
            self.notifier("✅ Doublon fusionné (favoris, écoutes et playlists conservés)")
        except Exception as ex:  # noqa: BLE001
            self.doublons_message = str(ex)

    def ouvrir_eq_10_bandes(self):
        est_ouv = not self.eq_perso_ouvert
        self._fermer_toutes_modales()
        self.eq_perso_ouvert = est_ouv

    def ouvrir_recherche_paroles(self):
        est_ouv = not self.paroles_recherche_ouverte
        self._fermer_toutes_modales()
        self.paroles_recherche_ouverte = est_ouv
        if est_ouv:
            with contextlib.suppress(Exception):
                self.paroles_couverture = paroles.couverture()
            if not self.paroles_recherche_resultats:
                self.paroles_recherche_saisie = True

    def executer_recherche_paroles(self, q: str):
        q = q.strip()
        if len(q) < 2:
            self.paroles_recherche_resultats = []
            return
        with contextlib.suppress(Exception):
            self.paroles_recherche_resultats = paroles.rechercher_texte(q, limite=35)
            self.paroles_recherche_index = 0
            self.paroles_couverture = paroles.couverture()

    def ouvrir_proprietes_selection(self):
        if self.proprietes_ouvertes:
            self.proprietes_ouvertes = False
            return
        pid = None
        if self.pistes_filtrees and 0 <= self.index_selection < len(self.pistes_filtrees):
            sel = self.pistes_filtrees[self.index_selection]
            if not sel.get("_type"):
                pid = sel.get("id")
        if not pid and self.piste_courante and not self.piste_courante.get("_type"):
            pid = self.piste_courante.get("id")
        if not pid:
            self.notifier("Sélectionne un titre local pour inspecter ses propriétés")
            return
        with contextlib.suppress(Exception):
            self.proprietes_donnees = outils.proprietes(int(pid))
        if not self.proprietes_donnees:
            self.notifier("Propriétés indisponibles pour ce titre")
            return
        self._fermer_toutes_modales()
        self.proprietes_ouvertes = True

    def ouvrir_editeur_tags(self):
        if self.tags_ouvert:
            self.tags_ouvert = False
            return
        cible = None
        if self.pistes_filtrees and 0 <= self.index_selection < len(self.pistes_filtrees):
            sel = self.pistes_filtrees[self.index_selection]
            if not sel.get("_type") and sel.get("id"):
                cible = sel
        if not cible and self.piste_courante and not self.piste_courante.get("_type"):
            cible = self.piste_courante
        if not cible or not cible.get("id"):
            self.notifier("Sélectionne un fichier audio local pour modifier ses tags")
            return
        self._fermer_toutes_modales()
        self.tags_ouvert = True
        self.tags_mode = "champs"
        self.tags_piste_id = int(cible["id"])
        self.tags_champ_index = 0
        self.tags_erreur = ""
        self.tags_itunes_resultats = []
        self.tags_itunes_choisi = None
        self.tags_pochette_locale = None
        self.tags_galerie_index = 0
        self.tags_champs = {
            "titre": str(cible.get("titre") or ""),
            "artiste": str(cible.get("artiste") or ""),
            "album": str(cible.get("album") or ""),
            "artiste_album": str(cible.get("artiste_album") or ""),
            "annee": str(cible.get("annee") or ""),
            "genre": str(cible.get("genre") or ""),
            "numero": str(cible.get("numero") or ""),
        }

    def lancer_lookup_itunes_tags(self):
        if not self.tags_piste_id:
            return
        self.tags_en_recherche = True
        self.tags_erreur = ""
        q = f"{self.tags_champs.get('artiste', '')} {self.tags_champs.get('titre', '')}".strip()

        def _tache():
            try:
                res = infos.rechercher(self.tags_piste_id, q=q)
                self.tags_itunes_resultats = res
                self.tags_itunes_index = 0
                self.tags_mode = "itunes"
            except Exception as ex:  # noqa: BLE001
                self.tags_erreur = str(ex)
            finally:
                self.tags_en_recherche = False

        threading.Thread(target=_tache, daemon=True, name="onde-itunes").start()

    def sauvegarder_tags_piste(self):
        if not self.tags_piste_id:
            return
        charge: dict[str, Any] = dict(self.tags_champs)
        if self.tags_itunes_choisi:
            charge["itunes"] = self.tags_itunes_choisi
        elif self.tags_pochette_locale and os.path.isfile(self.tags_pochette_locale):
            try:
                import io as _io

                with Image.open(self.tags_pochette_locale) as im:
                    im_sq = ImageOps.fit(
                        im.convert("RGB"), (600, 600), Image.Resampling.LANCZOS
                    )
                    buf = _io.BytesIO()
                    im_sq.save(buf, format="JPEG", quality=90)
                    charge["pochette_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
            except (OSError, ValueError) as ex:
                self.tags_erreur = f"Pochette illisible : {ex}"
                return
        try:
            maj = infos.modifier(self.tags_piste_id, charge)
            self.recharger_bibliotheque()
            if self.piste_courante and self.piste_courante.get("id") == self.tags_piste_id and maj:
                maj["chemin"] = self.piste_courante.get("chemin") or bibliotheque.chemin_piste(self.tags_piste_id)
                self.piste_courante = maj
                self.actualiser_palette_et_fond()
                if self.mpris:
                    self.mpris.notifier_changement(["Metadata"])
            self.tags_ouvert = False
            self.tags_pochette_locale = None
            self.notifier("✅ Tags & pochette enregistrés dans le fichier audio !")
        except Exception as ex:  # noqa: BLE001
            self.tags_erreur = str(ex)

    def verifier_boucle_ab(self):
        """Si une boucle A-B est active et que la lecture dépasse B, revient instantanément à A."""
        if (
            self.boucle_a is not None
            and self.boucle_b is not None
            and self.lecteur.fichier_actuel
            and not self.lecteur.en_pause
            and self.lecteur.position >= self.boucle_b
        ):
            self.lecteur.aller_a(self.boucle_a)
            if self.mpris:
                self.mpris.emettre_seeked(self.boucle_a)

    def marquer_boucle_a(self):
        if not self.lecteur.fichier_actuel:
            return
        self.boucle_a = round(self.lecteur.position, 2)
        if self.boucle_b is not None and self.boucle_b <= self.boucle_a:
            self.boucle_b = None
        m, s = int(self.boucle_a) // 60, int(self.boucle_a) % 60
        self.notifier(f"🔁 Point A fixé à {m:02d}:{s:02d} (Appuie sur [;] pour fixer le point B)")

    def marquer_ou_effacer_boucle_b(self):
        if self.boucle_a is not None and self.boucle_b is None:
            pos = round(self.lecteur.position, 2)
            if pos > self.boucle_a + 0.5:
                self.boucle_b = pos
                ma, sa = int(self.boucle_a) // 60, int(self.boucle_a) % 60
                mb, sb = int(self.boucle_b) // 60, int(self.boucle_b) % 60
                self.notifier(f"🔁 Boucle A-B active : {ma:02d}:{sa:02d} ➔ {mb:02d}:{sb:02d} ([;] pour désactiver)")
                return
        self.boucle_a = None
        self.boucle_b = None
        self.notifier("🔁 Boucle A-B désactivée")

    def cycler_vitesse(self):
        vitesses = [0.85, 1.0, 1.1, 1.25]
        act = self.lecteur.vitesse
        proch = vitesses[0]
        for v in vitesses:
            if v > act + 0.02:
                proch = v
                break
        if abs(act - vitesses[-1]) < 0.03:
            proch = vitesses[0]
        self.lecteur.definir_vitesse(proch)
        self.notifier(f"⚡ Vitesse de lecture : {proch:.2f}x")

    def cycler_veille(self):
        cycles = [0, 15, 30, 45, 60, -1]
        idx = (cycles.index(self.veille_mode) + 1) % len(cycles) if self.veille_mode in cycles else 1
        self.veille_mode = cycles[idx]
        if self.veille_mode > 0:
            self.veille_echeance = time.time() + self.veille_mode * 60
            self.notifier(f"🌙 Veille programmée dans {self.veille_mode} min")
        elif self.veille_mode == -1:
            self.veille_echeance = 0.0
            self.notifier("🌙 Veille : arrêt à la fin du morceau")
        else:
            self.veille_echeance = 0.0
            self.notifier("🌙 Minuterie de veille désactivée")

    def verifier_veille(self):
        if self.veille_mode > 0 and self.veille_echeance > 0:
            restant = self.veille_echeance - time.time()
            if restant <= 0:
                self.veille_mode = 0
                self.veille_echeance = 0.0
                if not self.lecteur.en_pause:
                    self.lecteur.basculer_pause()
                self.notifier("🌙 Mise en pause automatique (Veille)")

    def verifier_mises_a_jour_arriere_plan(self):
        """Détecte la fin d'un scan ou d'un téléchargement YouTube pour rafraîchir la bibliothèque."""
        rev_act = bibliotheque.REV.get("n", 0)
        if rev_act != self._rev_bibliotheque:
            self._rev_bibliotheque = rev_act
            self.recharger_bibliotheque()

        taches = telechargement.taches()
        for t in taches:
            if t.get("etat") == "fini" and t.get("id") not in self._yt_finis_connus:
                self._yt_finis_connus.add(t["id"])
                chemin_dl = t.get("chemin")
                if chemin_dl and os.path.isfile(chemin_dl):
                    with contextlib.suppress(Exception):
                        bibliotheque.importer([chemin_dl])
                self.recharger_bibliotheque()
                self._rev_bibliotheque = bibliotheque.REV.get("n", 0)
                self.notifier(
                    f"✅ Téléchargé : {t.get('titre')} — {t.get('artiste')}",
                    duree=4.0,
                )

    def lancer_recherche_youtube(self, requete: str):
        q = requete.strip()
        if not q:
            return
        self.yt_en_recherche = True
        self.yt_erreur = ""
        self.yt_resultats = []
        self.yt_index_selection = 0

        def _tache():
            try:
                res = telechargement.chercher(q)
                self.yt_resultats = res
                self.yt_index_selection = 0
                self.yt_en_recherche = False
                if len(res) == 1 and re.match(r"https?://", q):
                    self.demarrer_telechargement_youtube(res[0])
            except Exception as ex:  # noqa: BLE001
                self.yt_erreur = str(ex)
                self.yt_en_recherche = False

        threading.Thread(target=_tache, daemon=True, name="onde-yt-search").start()

    def demarrer_telechargement_youtube(self, item: dict[str, Any]):
        try:
            t = telechargement.demarrer(item)
            self.notifier(
                f"⬇ Téléchargement lancé : {t.get('titre')} — {t.get('artiste')}"
            )
        except Exception as ex:  # noqa: BLE001
            self.notifier(f"Erreur téléchargement : {ex}")

    def ouvrir_statistiques(self):
        est_ouv = not self.stats_ouverte
        self._fermer_toutes_modales()
        self.stats_ouverte = est_ouv
        if est_ouv:
            self.stats_index = 0
            with contextlib.suppress(Exception):
                self.stats_donnees = bibliotheque.statistiques()
            heures = [0] * 24
            with contextlib.suppress(Exception):
                for r in bibliotheque.requete("SELECT date FROM ecoutes"):
                    ts = r["date"]
                    if ts:
                        hr = time.localtime(float(ts)).tm_hour
                        heures[hr % 24] += 1
            self.stats_heures = heures

    @staticmethod
    def _largeur_liste(largeur: int) -> int:
        """Largeur unifiée du panneau Bibliothèque en vue scindée (garantit l'alignement souris & Kitty HD)."""
        return max(36, min(52, int(largeur * 0.40)))

    def _prochaine_piste_apercu(self) -> dict[str, Any] | None:
        """Retourne un aperçu du prochain titre qui sera joué (file d'attente ou piste suivante)."""
        if self.file_attente:
            return self.file_attente[0]
        if self.mode_repetition == "un" and self.piste_courante:
            return self.piste_courante
        pistes_loc = [p for p in self.pistes_filtrees if not p.get("_type")]
        if not pistes_loc:
            pistes_loc = self.pistes
        if not pistes_loc:
            return None
        if self.piste_courante and not self.piste_courante.get("_type"):
            pid = self.piste_courante.get("id")
            for idx, p in enumerate(pistes_loc):
                if p.get("id") == pid:
                    if idx + 1 < len(pistes_loc):
                        return pistes_loc[idx + 1]
                    if self.mode_repetition == "tout":
                        return pistes_loc[0]
                    return None
        return pistes_loc[0]

    def lancer_radio_piste(self, piste_ref: dict[str, Any] | None = None):
        """Génère et lance un Smart Mix « Radio de ce titre » (25 morceaux proches par artiste/genre/année)."""
        ref = piste_ref or self._piste_locale_cible()
        if not ref or not self.pistes:
            self.notifier("Sélectionne ou écoute un morceau pour lancer sa Radio")
            return
        ref_id = ref.get("id")
        ref_art = bibliotheque.sans_accents((ref.get("artiste") or "").lower()).strip()
        ref_genre = bibliotheque.sans_accents((ref.get("genre") or "").lower()).strip()
        ref_an = int(str(ref.get("annee") or "0")[:4]) if str(ref.get("annee") or "")[:4].isdigit() else 0
        mots_art = {m for m in re.split(r"[\s,&featx\.]+", ref_art) if len(m) >= 3}

        candidats: list[tuple[float, dict[str, Any]]] = []
        for p in self.pistes:
            if p.get("id") == ref_id:
                continue
            sc = random.uniform(0.0, 2.5)
            art = bibliotheque.sans_accents((p.get("artiste") or "").lower()).strip()
            gen = bibliotheque.sans_accents((p.get("genre") or "").lower()).strip()
            an = int(str(p.get("annee") or "0")[:4]) if str(p.get("annee") or "")[:4].isdigit() else 0
            if ref_art and art == ref_art:
                sc += 10.0
            elif mots_art and any(m in art for m in mots_art):
                sc += 7.0
            if ref_genre and gen and (ref_genre == gen or ref_genre in gen or gen in ref_genre):
                sc += 6.0
            if ref_an and an and abs(ref_an - an) <= 3:
                sc += 3.0
            if p.get("id") in self.favoris_set:
                sc += 1.5
            candidats.append((sc, p))

        candidats.sort(key=lambda x: -x[0])
        selection = [p for _, p in candidats[:24]]
        self.file_attente = selection
        if self.piste_courante is None or self.piste_courante.get("id") != ref_id:
            self.jouer_piste(ref)
        self.notifier(
            f"📻 Radio « {ref.get('titre')} » : {len(selection)} titres préparés en file !",
            duree=3.5,
        )

    def exporter_playlist_m3u(self):
        """Exporte la playlist ouverte ou sélectionnée au format standard `.m3u8` dans ~/Musique."""
        pl = self.playlist_ouverte
        if not pl and self.mode_onglet == "playlists" and self.pistes_filtrees:
            sel = self.pistes_filtrees[max(0, min(self.index_selection, len(self.pistes_filtrees) - 1))]
            pl = sel.get("_playlist")
        if not pl and self.playlists_liste:
            pl = self.playlists_liste[0]
        if not pl:
            self.notifier("Aucune playlist à exporter en .m3u8")
            return
        pistes_map = {p["id"]: p for p in self.pistes if p.get("id")}
        ids = pl.get("pistes") or []
        lignes = ["#EXTM3U", f"#PLAYLIST:{pl.get('nom') or 'Onde'}"]
        nb_ok = 0
        for pid in ids:
            p = pistes_map.get(pid)
            if not p:
                continue
            ch = p.get("chemin") or bibliotheque.chemin_piste(pid)
            if not ch:
                continue
            dur = int(float(p.get("duree") or -1))
            lignes.append(f"#EXTINF:{dur},{p.get('artiste') or 'Onde'} - {p.get('titre') or ''}")
            lignes.append(str(ch))
            nb_ok += 1
        if not nb_ok:
            self.notifier("Playlist vide : rien à exporter")
            return
        slug = re.sub(r"[^\w\- ]+", "_", str(pl.get("nom") or "playlist")).strip() or "playlist"
        dossier_dest = Path.home() / "Musique"
        if not dossier_dest.is_dir():
            dossier_dest = config.DONNEES
        cible = dossier_dest / f"{slug}.m3u8"
        try:
            cible.write_text("\n".join(lignes) + "\n", encoding="utf-8")
            self.notifier(f"📤 Exporté ({nb_ok} titres) : {cible.name}", duree=3.8)
        except OSError as ex:
            self.notifier(f"Erreur export M3U8 : {ex}")

    def preparer_donnees_accueil(self) -> dict[str, Any]:
        """Construit les étagères éditoriales (récents, incontournables, ajouts, découvertes, mixes)."""
        recents = sorted(
            [p for p in self.pistes if p.get("derniere")],
            key=lambda p: -float(p.get("derniere") or 0.0),
        )[:8]
        if not recents:
            recents = self.charger_pistes_recentes()[:8]
        incontournables = sorted(
            [p for p in self.pistes if int(p.get("ecoutes") or 0) > 0],
            key=lambda p: (-int(p.get("ecoutes") or 0), (p.get("titre") or "").lower()),
        )[:8]
        ajouts = sorted(
            self.pistes,
            key=lambda p: (-float(p.get("ajoute") or 0.0), -int(p.get("id") or 0)),
        )[:8]
        peu_ecoutes = [p for p in self.pistes if int(p.get("ecoutes") or 0) == 0]
        if len(peu_ecoutes) < 6:
            peu_ecoutes = list(self.pistes)
        rng = random.Random(self.accueil_graine)
        decouverte = list(peu_ecoutes)
        rng.shuffle(decouverte)
        decouverte = decouverte[:8]

        # Mixes rapides : Favoris, Hi-Res/FLAC, + top genres détectés
        mixes: list[dict[str, Any]] = []
        favs = [p for p in self.pistes if p.get("id") in self.favoris_set]
        if favs:
            mixes.append({"nom": f"♥ Favoris ({len(favs)})", "pistes": favs})
        hires = [
            p
            for p in self.pistes
            if (p.get("format") or "").lower() in ("flac", "alac", "wav", "aiff")
            or int(p.get("bits") or 0) >= 24
        ]
        if hires:
            mixes.append({"nom": f"💎 Hi-Res / FLAC ({len(hires)})", "pistes": hires})
        par_genre: dict[str, list[dict[str, Any]]] = {}
        for p in self.pistes:
            g = (p.get("genre") or "").strip()
            if g:
                par_genre.setdefault(g, []).append(p)
        for g, ps in sorted(par_genre.items(), key=lambda kv: -len(kv[1]))[:5]:
            mixes.append({"nom": f"🏷 {g} ({len(ps)})", "pistes": ps})
        if not mixes and self.pistes:
            mixes.append({"nom": f"🔀 Mix Complet ({len(self.pistes)})", "pistes": list(self.pistes)})

        self._accueil_donnees = {
            "sections": [
                ("⏱ Écoutés récemment", recents),
                ("🔥 Tes incontournables", incontournables),
                ("✨ Ajoutés récemment", ajouts),
                ("🎲 À redécouvrir", decouverte),
            ],
            "mixes": mixes,
        }
        return self._accueil_donnees

    def ouvrir_creation_playlist(self):
        self._fermer_toutes_modales()
        self.modal_playlist_mode = "creer"
        self.nom_nouvelle_playlist = ""

    def ouvrir_ajout_playlist(self):
        """Prépare l'ajout de la sélection (ou du titre en cours) à une playlist."""
        cibles: list[int] = []
        label = ""
        if self.pistes_filtrees and 0 <= self.index_selection < len(self.pistes_filtrees):
            sel = self.pistes_filtrees[self.index_selection]
            if sel.get("_type") in ("artiste", "album", "playlist", "dossier", "genre"):
                cibles = [
                    int(x["id"])
                    for x in (sel.get("_pistes") or [])
                    if x.get("id")
                ]
                label = f"{sel.get('titre')} ({len(cibles)} titres)"
            elif sel.get("id"):
                cibles = [int(sel["id"])]
                label = f"{sel.get('titre')} — {sel.get('artiste')}"
        elif self.piste_courante and self.piste_courante.get("id"):
            cibles = [int(self.piste_courante["id"])]
            label = f"{self.piste_courante.get('titre')} — {self.piste_courante.get('artiste')}"

        if not cibles:
            self.notifier("Aucun morceau sélectionné à ajouter")
            return

        self._fermer_toutes_modales()
        self.pistes_cibles_playlist = cibles
        self.titre_cible_playlist = label
        self.playlists_liste = bibliotheque.playlists()
        if not self.playlists_liste:
            self.modal_playlist_mode = "creer"
            self.nom_nouvelle_playlist = ""
            self.notifier("Crée ta première playlist pour y ajouter ce titre")
            return
        self.index_playlist_cible = 0
        self.modal_playlist_mode = "ajouter"

    # ── Éléments d'Affichage Rich ────────────────────────────────────────────

    def _enregistrer_zone(self, nom: str, x0: int, y0: int, x1: int, y1: int):
        self._zones_clic[nom] = (x0, y0, max(x0, x1), max(y0, y1))

    def _texte_controles_transport(
        self, compact: bool = False
    ) -> tuple[Text, list[tuple[str, int, int]]]:
        """Construit la barre interactive de transport Liquid Glass et retourne `(Text, [(nom, deb, fin), ...])`."""
        pal = self.palette
        txt = Text(no_wrap=True)
        spans: list[tuple[str, int, int]] = []
        pos = 0

        def _btn(nom: str, label: str, style: str):
            nonlocal pos
            txt.append(label, style=style)
            w = cell_len(label)
            spans.append((nom, pos, pos + w - 1))
            pos += w

        def _sep(s: str = " "):
            nonlocal pos
            txt.append(s)
            pos += cell_len(s)

        en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        _btn("ctrl_prev", " ⏮ ", f"bold {pal['texte_dim']} on {pal['surface_2']}")
        _sep()
        _btn(
            "ctrl_play",
            " ⏸ PAUSE " if en_lec else " ▶ LIRE ",
            f"bold black on {pal['primaire']}",
        )
        _sep()
        _btn("ctrl_next", " ⏭ ", f"bold {pal['texte_dim']} on {pal['surface_2']}")
        _sep("  ")

        _btn(
            "ctrl_shuffle",
            " 🔀 Aléa " if not compact else " 🔀 ",
            f"bold black on {pal['accent']}"
            if self.mode_aleatoire
            else f"{pal['texte_muet']} on {pal['surface_2']}",
        )
        _sep()
        rep_txt = (
            f" 🔁 {self.mode_repetition.upper()} "
            if not compact
            else f" 🔁{self.mode_repetition[0].upper()} "
        )
        _btn(
            "ctrl_repeat",
            rep_txt,
            f"bold black on {pal['secondaire']}"
            if self.mode_repetition != "non"
            else f"{pal['texte_muet']} on {pal['surface_2']}",
        )
        _sep()
        _btn(
            "ctrl_dj",
            " 🎧DJ " if not compact else " DJ ",
            f"bold black on {pal['succes']}"
            if self.auto_dj
            else f"{pal['texte_muet']} on {pal['surface_2']}",
        )
        if compact:
            _sep()
            est_fav = bool(self.piste_courante and self.piste_courante.get("id") in self.favoris_set)
            _btn(
                "ctrl_fav",
                " ♥ " if est_fav else " ♡ ",
                f"bold {'bright_red' if est_fav else pal['texte_muet']} on {pal['surface_2']}",
            )
            _sep()
            vis_ic = {
                "spectre": "▄▆█",
                "horizon": "▄█▄",
                "onde": "▀▄▀",
                "braille": "⣿",
                "galaxie": "⣶⣷",
                "barres": "▮▮",
                "aucun": "─",
            }
            _btn(
                "ctrl_vis",
                f" {vis_ic.get(self.visualiseur_mode, '▄▆█')} ",
                f"bold {pal['secondaire']} on {pal['surface_2']}",
            )
            _sep()
            if self.lecteur.mute:
                _btn("ctrl_mute", " 🔇 ", f"bold bright_white on {pal['accent']}")
            else:
                _btn("ctrl_mute", f" 🔊{int(self.lecteur.volume)}% ", f"bold {pal['primaire']} on {pal['surface_2']}")
        else:
            _sep()
            est_fav = bool(self.piste_courante and self.piste_courante.get("id") in self.favoris_set)
            _btn(
                "ctrl_fav",
                " ♥ " if est_fav else " ♡ ",
                f"bold {'bright_red' if est_fav else pal['texte_muet']} on {pal['surface_2']}",
            )
            _sep()
            vis_ic = {
                "spectre": "▄▆█",
                "horizon": "▄█▄",
                "onde": "▀▄▀",
                "braille": "⣿",
                "galaxie": "⣶⣷",
                "barres": "▮▮",
                "aucun": "─",
            }
            _btn(
                "ctrl_vis",
                f" {vis_ic.get(self.visualiseur_mode, '▄▆█')} ",
                f"bold {pal['secondaire']} on {pal['surface_2']}",
            )
            if self.effet_dsp != "off":
                _sep()
                _btn("ctrl_dsp", " ✨DSP ", f"bold black on {pal['accent']}")
            _sep("  ")
            if self.lecteur.mute:
                _btn("ctrl_mute", " 🔇 MUET ", f"bold bright_white on {pal['accent']}")
            else:
                _btn("ctrl_mute", " 🔊", f"bold {pal['primaire']} on {pal['surface_2']}")
                vol_pct = max(0.0, min(1.0, float(self.lecteur.volume) / 100.0))
                w_vol = 6
                pos_v = min(w_vol - 1, round(vol_pct * (w_vol - 1)))
                deb_v = pos
                rgb_p = _hex_vers_rgb(pal["primaire"], (192, 132, 252))
                rgb_s = _hex_vers_rgb(pal["secondaire"], (34, 211, 238))
                for k in range(w_vol):
                    if k == pos_v:
                        txt.append("●", style=f"bold {pal['accent']} on {pal['surface_2']}")
                    elif k < pos_v:
                        c_v = _rgb_vers_hex(*_melanger_rgb(rgb_p, rgb_s, k / max(1, w_vol - 1)))
                        txt.append("━", style=f"bold {c_v} on {pal['surface_2']}")
                    else:
                        txt.append("─", style=f"{pal['texte_muet']} on {pal['surface_2']}")
                pos += w_vol
                spans.append(("ctrl_vol_barre", deb_v, pos - 1))
                _btn(
                    "ctrl_mute_pct",
                    f" {int(self.lecteur.volume):3d}% ",
                    f"bold {pal['primaire']} on {pal['surface_2']}",
                )
        return txt, spans

    def rendre_en_tete(self) -> Panel:
        """Barre Studio Deck 3 zones (Vues | En lecture | Télémétrie & Actions), sans débordement et 100% cliquable."""
        pal = self.palette
        w_tot = self.console.size.width
        w_in = max(20, w_tot - 4)  # bordures (2) + padding Panel (2), contenu commence à col 3 (1-based)

        # 1. Bloc gauche : Logo dégradé + sélecteur de vues cliquable
        gauche = Text(no_wrap=True)
        zones_g: list[tuple[str, int, int]] = []
        gx = 0

        logo_txt = " ◆ ONDE " if w_tot < 105 else " ◆ O N D E "
        gauche.append_text(
            texte_degrade(
                logo_txt,
                pal["primaire"],
                pal["secondaire"],
                gras=True,
                bg=pal["surface_2"],
                c_milieu=pal["accent"],
            )
        )
        gx += cell_len(logo_txt)
        gauche.append(" ")
        gx += 1

        if w_tot >= 86:
            if w_tot >= 148:
                vues_defs = [
                    ("accueil", "✦ Accueil"),
                    ("scinde", "◫ Scindé"),
                    ("scene", "💿 Scène"),
                    ("paroles", "🎙 Karaoké"),
                    ("liste", "☰ Liste"),
                ]
            elif w_tot >= 114:
                vues_defs = [
                    ("accueil", "✦ Acc"),
                    ("scinde", "◫ Split"),
                    ("scene", "💿 Scène"),
                    ("paroles", "🎙 Lyr"),
                    ("liste", "☰ List"),
                ]
            else:
                vues_defs = [
                    ("accueil", "✦"),
                    ("scinde", "◫"),
                    ("scene", "💿"),
                    ("paroles", "🎙"),
                    ("liste", "☰"),
                ]
            for v_code, v_lbl in vues_defs:
                pill = f" {v_lbl} "
                wp = cell_len(pill)
                actif_v = self.mode_vue == v_code
                gauche.append(
                    pill,
                    style=f"bold black on {pal['primaire']}"
                    if actif_v
                    else f"{pal['texte_dim']} on {pal['surface_2']}",
                )
                zones_g.append((f"vue:{v_code}", gx, gx + wp - 1))
                gx += wp
                gauche.append(" ")
                gx += 1

        # 2. Bloc droit : badges audio actifs, horloge & actions rapides cliquables
        droite = Text(no_wrap=True)
        zones_d: list[tuple[str, int, int]] = []
        dx = 0

        def _d_pill(nom: str | None, label: str, style: str, sep: bool = True):
            nonlocal dx
            if sep and dx > 0:
                droite.append(" ")
                dx += 1
            droite.append(label, style=style)
            w_l = cell_len(label)
            if nom:
                zones_d.append((nom, dx, dx + w_l - 1))
            dx += w_l

        if w_tot >= 100:
            if self.eq_perso_actif:
                _d_pill("hdr_eq", " 🎛10B ", f"bold bright_white on {pal['badge_bg']}")
            elif self.eq_index > 0:
                _d_pill("hdr_eq", " 🎛EQ ", f"bold bright_white on {pal['badge_bg']}")
            if self.effet_dsp != "off":
                _d_pill("hdr_dsp", " ✨DSP ", f"bold black on {pal['secondaire']}")
            if self.boucle_a is not None:
                ma, sa = int(self.boucle_a) // 60, int(self.boucle_a) % 60
                if self.boucle_b is not None:
                    mb, sb = int(self.boucle_b) // 60, int(self.boucle_b) % 60
                    _d_pill(None, f" 🔁{ma:02d}:{sa:02d}→{mb:02d}:{sb:02d} ", f"bold black on {pal['accent']}")
                else:
                    _d_pill(None, f" 🔁A:{ma:02d}:{sa:02d} ", f"bold black on {pal['accent']}")
            if abs(self.lecteur.vitesse - 1.0) > 0.02:
                _d_pill(None, f" ⚡{self.lecteur.vitesse:.2f}× ", f"bold black on {pal['accent']}")
            if self.veille_mode != 0:
                if self.veille_mode == -1:
                    _d_pill(None, " 🌙Fin ", f"bold black on {pal['accent']}")
                else:
                    r_min = max(1, int((self.veille_echeance - time.time()) / 60) + 1)
                    _d_pill(None, f" 🌙{r_min}m ", f"bold black on {pal['accent']}")
            if self.normalisation_active and (self.gain_source or self.gain_piste_db != 0.0):
                lbl_g = " ⚖… " if self.gain_en_analyse else f" ⚖{self.gain_piste_db:+.1f} "
                _d_pill(None, lbl_g, f"{pal['succes']} on {pal['surface_2']}")

        if w_tot >= 76:
            if self.lecteur.mute:
                _d_pill("hdr_mute", " 🔇 ", f"bold bright_white on {pal['accent']}")
            else:
                _d_pill("hdr_mute", f" 🔊{int(self.lecteur.volume)}% ", f"bold {pal['primaire']} on {pal['surface_2']}")
            if w_tot >= 94:
                _d_pill("hdr_theme", " 🎨 ", f"bold {pal['secondaire']} on {pal['surface_2']}")
                _d_pill("hdr_palette", " ⌘F1 ", f"bold {pal['accent']} on {pal['surface_2']}")
                _d_pill("hdr_reglages", " ⚙ ", f"bold {pal['texte_dim']} on {pal['surface_2']}")
            if w_tot >= 112:
                _d_pill(None, f" {time.strftime('%H:%M')} ", f"bold {pal['texte_dim']} on {pal['surface_2']}")

        # 3. Bloc central : statut + titre en cours, adapté exactement à l'espace restant
        budget_centre = max(8, w_in - gx - dx - 2)
        centre = Text(no_wrap=True)
        en_lecture = (
            self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        )
        if self.lecteur.en_pause:
            stat_s, stat_c = "⏸ ", f"bold {pal['accent']}"
        elif en_lecture:
            roue = ROUES_VINYLE[self.index_animation % len(ROUES_VINYLE)]
            stat_s, stat_c = f"{roue} ", f"bold {pal['succes']}"
        else:
            stat_s, stat_c = "■ ", pal["texte_muet"]

        p = self.piste_courante
        if p:
            titre_p = p.get("titre") or "Sans titre"
            art_p = p.get("artiste") or "Artiste inconnu"
            b_q = badge_qualite_piste(p, complet=False)
            b_len = (cell_len(b_q) + 3) if (b_q and budget_centre >= 28) else 0
            dispo_txt = max(6, budget_centre - cell_len(stat_s) - b_len)
            combo = f"{titre_p} — {art_p}"
            centre.append(stat_s, style=stat_c)
            if cell_len(combo) <= dispo_txt:
                centre.append(titre_p, style="bold bright_white")
                centre.append(" — ", style=pal["texte_muet"])
                centre.append(art_p, style=pal["texte_dim"])
            else:
                lim_t = max(4, int(dispo_txt * 0.62))
                t_cut = titre_p[: lim_t - 1] + "…" if len(titre_p) > lim_t else titre_p
                reste_a = dispo_txt - cell_len(t_cut) - 3
                centre.append(t_cut, style="bold bright_white")
                if reste_a >= 4:
                    a_cut = art_p[: reste_a - 1] + "…" if len(art_p) > reste_a else art_p
                    centre.append(" — ", style=pal["texte_muet"])
                    centre.append(a_cut, style=pal["texte_dim"])
            if b_len:
                st_b = (
                    f"bold black on {pal['accent']}"
                    if b_q in ("HI-RES", "FLAC", "ALAC", "WAV")
                    else (f"bold black on {pal['succes']}" if b_q == "LIVE" else f"{pal['texte_dim']} on {pal['surface_2']}")
                )
                centre.append(" ")
                centre.append(f" {b_q} ", style=st_b)
        else:
            centre.append(stat_s, style=stat_c)
            msg_idle = "Prêt — Choisis un titre"
            centre.append(msg_idle[: max(4, budget_centre - 2)], style=pal["texte_muet"])

        # Assemblage exact sur 1 ligne + enregistrement des zones cliquables sur y = 2
        wc = cell_len(centre.plain)
        espace_libre = max(0, w_in - gx - wc - dx)
        pad_g = espace_libre // 2
        pad_d = espace_libre - pad_g

        ligne = Text(no_wrap=True, overflow="crop")
        ligne.append_text(gauche)
        if pad_g:
            ligne.append(" " * pad_g)
        ligne.append_text(centre)
        if pad_d:
            ligne.append(" " * pad_d)
        ligne.append_text(droite)

        offset_x = 3  # col 1 bordure, col 2 espace padding Panel
        for nom_z, x0, x1 in zones_g:
            self._enregistrer_zone(nom_z, offset_x + x0, 2, offset_x + x1, 2)
        base_d = offset_x + gx + pad_g + wc + pad_d
        for nom_z, x0, x1 in zones_d:
            self._enregistrer_zone(nom_z, base_d + x0, 2, base_d + x1, 2)

        return Panel(
            ligne,
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
            height=3,
        )

    def rendre_panneau_liste(self, largeur: int, hauteur: int) -> Panel:
        pal = self.palette
        table = Table(
            box=None,
            expand=True,
            show_header=False,
            padding=(0, 1),
        )
        table.add_column("Curseur", width=4, justify="left", no_wrap=True)
        table.add_column("Titre & Artiste", ratio=4, no_wrap=True, overflow="ellipsis")
        afficher_badge_col = largeur >= 46
        if afficher_badge_col:
            table.add_column("Qualité", width=7, justify="right", no_wrap=True)
        table.add_column("Durée", width=6, justify="right", no_wrap=True)
        table.add_column("Défilement", width=1, no_wrap=True)

        # Barre d'onglets adaptative (tous les onglets visibles sans coupure quelle que soit la largeur)
        if largeur >= 84:
            onglets = [
                (f"1 Titres({len(self.pistes)})", "titres"),
                (f"2 ♥({len(self.favoris_set)})", "favoris"),
                (f"3 Pl({len(self.playlists_liste)})", "playlists"),
                ("4 Art", "artistes"),
                ("5 Alb", "albums"),
                ("6 📻", "radios"),
                (f"7 File({len(self.file_attente)})", "file"),
                ("8 Réc", "recents"),
                ("9 📁", "dossiers"),
                ("🏷", "genres"),
            ]
        elif largeur >= 48:
            onglets = [
                ("1", "titres"),
                ("2♥", "favoris"),
                ("3♪", "playlists"),
                ("4Art", "artistes"),
                ("5Alb", "albums"),
                ("6📻", "radios"),
                (f"7({len(self.file_attente)})", "file"),
                ("8Réc", "recents"),
                ("9📁", "dossiers"),
                ("🏷", "genres"),
            ]
        else:
            onglets = [
                ("1", "titres"),
                ("2♥", "favoris"),
                ("3♪", "playlists"),
                ("4A", "artistes"),
                ("5💿", "albums"),
                ("6📻", "radios"),
                ("7Q", "file"),
                ("8⏱", "recents"),
                ("9📁", "dossiers"),
                ("🏷", "genres"),
            ]

        onglets_texte = Text(no_wrap=True, overflow="crop")
        cur_x = 3  # 1-based : bordure gauche (col 1) + 1 espace padding Panel (col 2)
        compact_pad = largeur < 84
        for nom, code in onglets:
            pill = f" {nom} " if not compact_pad else nom
            w_pill = cell_len(pill)
            self._enregistrer_zone(f"tab:{code}", cur_x, 5, cur_x + w_pill - 1, 5)
            if self.mode_onglet == code:
                onglets_texte.append(
                    pill, style=f"bold black on {pal['primaire']}"
                )
            else:
                onglets_texte.append(
                    pill,
                    style=f"{pal['texte_dim']} on {pal['surface_2']}"
                    if not compact_pad
                    else pal["texte_muet"],
                )
            onglets_texte.append(" ")
            cur_x += w_pill + 1

        # Barre de contexte / filtre / sous-vue sur y = 6
        nom_tri = dict(TRIS_LISTE).get(self.tri_mode, "Défaut")
        recherche_texte = Text(no_wrap=True, overflow="ellipsis")
        self._enregistrer_zone("liste_barre", 3, 6, max(4, largeur - 2), 6)

        sous_vue_label = None
        if self.mode_onglet == "playlists" and self.playlist_ouverte:
            sous_vue_label = f"📂 {self.playlist_ouverte.get('nom')}"
        elif self.mode_onglet == "artistes" and self.artiste_ouvert:
            sous_vue_label = f"🎤 {self.artiste_ouvert}"
        elif self.mode_onglet == "albums" and self.album_ouvert:
            sous_vue_label = f"💿 {self.album_ouvert}"
        elif self.mode_onglet == "dossiers" and self.dossier_ouvert:
            sous_vue_label = f"📁 {self.dossier_ouvert}"
        elif self.mode_onglet == "genres" and self.genre_ouvert:
            sous_vue_label = f"🏷 {self.genre_ouvert}"

        if self.recherche_active:
            lbl_r = (
                " 🔎 Radio (Entrée -> web) : "
                if self.mode_onglet == "radios"
                else " 🔍 Filtrer : "
            )
            recherche_texte.append(
                f"{lbl_r}{self.terme_recherche}█",
                style=f"bold black on {pal['accent']}",
            )
        elif self.terme_recherche:
            recherche_texte.append(
                f" 🔍 « {self.terme_recherche} » ",
                style=f"bold black on {pal['primaire']}",
            )
            recherche_texte.append("  [Échap] effacer", style=pal["texte_muet"])
        elif sous_vue_label:
            cx_s = 3
            p_ret = " ← "
            recherche_texte.append(p_ret, style=f"bold black on {pal['accent']}")
            self._enregistrer_zone("sub_retour", cx_s, 6, cx_s + cell_len(p_ret) - 1, 6)
            cx_s += cell_len(p_ret) + 1
            recherche_texte.append(" ")
            dur_sub = sum(float(x.get("duree") or 0.0) for x in self.pistes_filtrees)
            p_tout = " ▶ Tout "
            p_alea = " 🔀 "
            budget_lbl = max(8, largeur - 4 - cell_len(p_ret) - cell_len(p_tout) - cell_len(p_alea) - 12)
            lbl_cut = sous_vue_label[: budget_lbl - 1] + "…" if len(sous_vue_label) > budget_lbl else sous_vue_label
            recherche_texte.append(lbl_cut, style="bold bright_white")
            cx_s += cell_len(lbl_cut)
            if largeur >= 50:
                meta_sub = f" ({formater_duree(dur_sub)}) "
                recherche_texte.append(meta_sub, style=pal["texte_muet"])
                cx_s += cell_len(meta_sub)
            else:
                recherche_texte.append(" ")
                cx_s += 1
            recherche_texte.append(p_tout, style=f"bold black on {pal['succes']}")
            self._enregistrer_zone("sub_tout", cx_s, 6, cx_s + cell_len(p_tout) - 1, 6)
            cx_s += cell_len(p_tout) + 1
            recherche_texte.append(" ")
            recherche_texte.append(p_alea, style=f"bold {pal['secondaire']} on {pal['surface_2']}")
            self._enregistrer_zone("sub_alea", cx_s, 6, cx_s + cell_len(p_alea) - 1, 6)
        elif self.mode_onglet == "radios":
            recherche_texte.append(
                " 📻 [Entrée] Direct • [/] Chercher web • [F] ★ Favori",
                style=pal["texte_dim"],
            )
        else:
            pill_tri = f" ⇅ {nom_tri} "
            self._enregistrer_zone("liste_tri", 3, 6, 3 + cell_len(pill_tri) - 1, 6)
            recherche_texte.append(pill_tri, style=f"bold {pal['secondaire']} on {pal['surface_2']}")
            recherche_texte.append(
                "  [/] Filtrer • [Ctrl+X] Radio",
                style=pal["texte_muet"],
            )

        lignes_dispos = max(4, hauteur - 6)
        self._enregistrer_zone(
            "liste_items", 2, 8, max(3, largeur - 1), 8 + lignes_dispos - 1
        )
        self._liste_y_debut = 8

        nb_pistes = len(self.pistes_filtrees)
        if nb_pistes:
            self.index_selection = max(0, min(self.index_selection, nb_pistes - 1))
        marge = min(3, (lignes_dispos - 1) // 2)
        debut = self._liste_debut
        if self.index_selection < debut + marge:
            debut = self.index_selection - marge
        elif self.index_selection > debut + lignes_dispos - 1 - marge:
            debut = self.index_selection - lignes_dispos + 1 + marge
        debut = max(0, min(debut, nb_pistes - lignes_dispos))
        self._liste_debut = debut
        fin = min(nb_pistes, debut + lignes_dispos)

        pouce_deb, pouce_fin = 0, 0
        if nb_pistes > lignes_dispos:
            taille_pouce = max(1, round(lignes_dispos * lignes_dispos / nb_pistes))
            pouce_deb = round(
                debut / max(1, nb_pistes - lignes_dispos) * (lignes_dispos - taille_pouce)
            )
            pouce_fin = pouce_deb + taille_pouce

        en_lec_global = (
            self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        )
        eq_anim = (
            BARRES_LECTURE_ANIME[(self.index_animation // 2) % len(BARRES_LECTURE_ANIME)]
            if en_lec_global
            else "▁▁▁"
        )

        for i in range(debut, fin):
            p = self.pistes_filtrees[i]
            est_selectionne = i == self.index_selection
            est_en_lecture = (
                self.piste_courante
                and not p.get("_type")
                and self.piste_courante.get("id") == p.get("id")
            )
            est_fav = not p.get("_type") and p.get("id") in self.favoris_set
            est_radio = p.get("_type") == "radio"

            if est_selectionne and est_en_lecture:
                cur = f"▎{eq_anim}"
                cur_style = f"bold {pal['succes']}"
            elif est_selectionne:
                cur = "▎❯ "
                cur_style = f"bold {pal['accent']}"
            elif est_en_lecture:
                cur = f" {eq_anim}"
                cur_style = f"bold {pal['succes']}"
            else:
                cur = f" {i + 1:02d}" if i < 99 and not p.get("_type") else "   "
                cur_style = pal["texte_muet"]

            dur_str = formater_duree(p.get("duree"), radio=est_radio)
            dur_style = (
                f"bold {pal['succes']}"
                if est_radio
                else (f"bold {pal['primaire']}" if est_selectionne else pal["texte_muet"])
            )

            col_info = Text()
            t_style = (
                "bold bright_white"
                if est_selectionne
                else (f"bold {pal['succes']}" if est_en_lecture else "#f1f5f9")
            )
            col_info.append(p.get("titre") or "Sans titre", style=t_style)
            if p.get("artiste"):
                col_info.append(" — ", style=pal["texte_muet"])
                col_info.append(
                    p.get("artiste") or "",
                    style=pal["primaire"] if est_selectionne else pal["texte_dim"],
                )
            if est_fav:
                col_info.append(" ♥", style="bold bright_red")

            style_ligne = f"on {pal['selection_bg']}" if est_selectionne else None
            if nb_pistes > lignes_dispos:
                dans_pouce = pouce_deb <= i - debut < pouce_fin
                barre = Text(
                    "┃" if dans_pouce else "┆",
                    style=pal["primaire"] if dans_pouce else pal["bordure"],
                )
            else:
                barre = Text(" ")

            cols_ligne: list[Any] = [Text(cur, style=cur_style), col_info]
            if afficher_badge_col:
                if self.tri_mode == "ecoutes" and not p.get("_type") and p.get("ecoutes"):
                    b_txt = f"{int(p['ecoutes'])}×"
                    b_st = f"bold {pal['accent']}"
                elif self.tri_mode == "annee" and not p.get("_type") and p.get("annee"):
                    b_txt = str(p["annee"])[:4]
                    b_st = f"bold {pal['secondaire']}"
                else:
                    b_txt = badge_qualite_piste(p, complet=False)[:7]
                    if b_txt == "HI-RES":
                        b_st = f"bold {pal['accent']}"
                    elif b_txt in ("FLAC", "ALAC", "WAV"):
                        b_st = f"bold {pal['secondaire']}"
                    elif b_txt == "LIVE":
                        b_st = f"bold {pal['succes']}"
                    else:
                        b_st = pal["texte_muet"]
                cols_ligne.append(Text(b_txt, style=b_st))
            cols_ligne.extend([Text(dur_str, style=dur_style), barre])
            table.add_row(*cols_ligne, style=style_ligne)

        corps = Layout()
        corps.split_column(
            Layout(onglets_texte, size=1),
            Layout(recherche_texte, size=1),
            Layout(Text("─" * max(10, largeur - 4), style=pal["bordure"]), size=1),
            Layout(table),
        )

        pos_str = f" • {self.index_selection + 1}/{nb_pistes}" if nb_pistes else ""
        tri_tag = f" • {nom_tri}" if self.tri_mode != "defaut" else ""
        titre = f" Bibliothèque ({nb_pistes}{pos_str}{tri_tag}) "
        dur_tot_liste = sum(float(x.get("duree") or 0.0) for x in self.pistes_filtrees if not x.get("_type"))
        sous_t = (
            f"[{pal['texte_muet']}] {formater_duree(dur_tot_liste)} [/]"
            if dur_tot_liste > 0
            else None
        )
        return Panel(
            corps,
            title=f"[bold {pal['primaire']}]{titre}[/bold {pal['primaire']}]",
            title_align="left",
            subtitle=sous_t,
            subtitle_align="right",
            box=box.ROUNDED,
            border_style=pal["bordure"] if not self.recherche_active else pal["accent"],
        )

    def rendre_visualiseur(self, largeur: int, hauteur: int = 2) -> Text:
        """Analyseur visuel temps réel TrueColor 24-bit multi-modes (7 styles + VU-mètre L/R mastering)."""
        pal = self.palette
        txt = Text()
        if largeur <= 4:
            return txt
        h_rows = max(1, min(3, hauteur))
        t = self.lecteur.position
        en_lec = (
            self.lecteur.fichier_actuel is not None
            and not self.lecteur.en_pause
            and self.piste_courante is not None
        )

        rgb_p = _hex_vers_rgb(pal["primaire"], (192, 132, 252))
        rgb_s = _hex_vers_rgb(pal["secondaire"], (34, 211, 238))
        rgb_a = _hex_vers_rgb(pal["accent"], (244, 114, 182))
        rgb_ok = _hex_vers_rgb(pal["succes"], (52, 211, 153))

        if self.visualiseur_mode == "aucun":
            sep = "─" * max(4, (largeur - 3) // 2)
            for r_idx in range(h_rows):
                if r_idx == h_rows // 2:
                    txt.append(sep, style=pal["bordure"])
                    txt.append(" ♪ " if en_lec else " · ", style=f"bold {pal['primaire']}")
                    txt.append(sep, style=pal["bordure"])
                else:
                    txt.append(" " * largeur)
                if r_idx < h_rows - 1:
                    txt.append("\n")
            return txt

        afficher_rms = h_rows >= 2 and largeur >= 42
        w_vis = largeur - 12 if afficher_rms else largeur

        if not en_lec:
            self._cretes_vumetre = [max(0.0, c - 0.08) for c in self._cretes_vumetre]
            self._crete_rms_g = max(0.0, self._crete_rms_g - 0.06)
            self._crete_rms_d = max(0.0, self._crete_rms_d - 0.06)
            if not any(c > 0.04 for c in self._cretes_vumetre):
                for r_idx in range(h_rows):
                    if r_idx == h_rows - 1:
                        txt.append("─" * largeur, style=pal["bordure"])
                    else:
                        txt.append(" " * largeur)
                    if r_idx < h_rows - 1:
                        txt.append("\n")
                return txt

        valeurs_fft, est_fft_reel, rms_g, rms_d = (
            self.spectre.echantillonner(w_vis)
            if en_lec
            else ([], False, 0.0, 0.0)
        )
        if not est_fft_reel and en_lec:
            rms_g = max(0.08, min(0.95, 0.48 + 0.34 * math.sin(t * 7.2)))
            rms_d = max(0.08, min(0.95, 0.48 + 0.34 * math.cos(t * 6.8)))

        self._crete_rms_g = max(rms_g, self._crete_rms_g - 0.025)
        self._crete_rms_d = max(rms_d, self._crete_rms_d - 0.025)

        if len(self._cretes_vumetre) != w_vis:
            self._cretes_vumetre = [0.0] * w_vis

        boost_basses = 1.25 if (self.eq_index in (1, 4) or self.eq_bandes[0] > 2.5) else 1.0
        niveaux: list[float] = []
        for i in range(w_vis):
            norm_i = i / max(1, w_vis - 1)
            if en_lec and est_fft_reel and i < len(valeurs_fft):
                val = max(
                    0.0,
                    min(1.0, valeurs_fft[i] * (boost_basses if norm_i < 0.25 else 1.0)),
                )
            elif en_lec:
                env = 0.85 * (1.0 - norm_i * 0.42)
                bas = math.sin(t * 8.5 + norm_i * 3.2) * 0.40 * boost_basses
                ryt = math.sin(t * 14.5) * math.cos(t * 5.2 + norm_i * 7.0) * 0.34
                aig = math.sin(t * 23.0 - norm_i * 12.0) * 0.24 * norm_i
                val = max(0.0, min(1.0, (env + bas + ryt + aig + 0.35) / 1.75))
            else:
                val = 0.0
            niveaux.append(val)
            if val >= self._cretes_vumetre[i]:
                self._cretes_vumetre[i] = val
            else:
                self._cretes_vumetre[i] = max(0.0, self._cretes_vumetre[i] - 0.042)

        def _coul_grad(norm_i: float, niveau: float = 0.5) -> str:
            """Dégradé RGB TrueColor continu primaire -> secondaire -> accent + éclat d'intensité."""
            if norm_i < 0.5:
                base = _melanger_rgb(rgb_p, rgb_s, norm_i * 2.0)
            else:
                base = _melanger_rgb(rgb_s, rgb_a, (norm_i - 0.5) * 2.0)
            if niveau > 0.72:
                base = _melanger_rgb(base, (255, 255, 255), (niveau - 0.72) * 0.55)
            return _rgb_vers_hex(*base)

        def _append_rms(row_idx: int):
            if not afficher_rms:
                return
            lbl, niv, cr, c_lbl = (
                (" L ", rms_g, self._crete_rms_g, pal["primaire"])
                if row_idx == 0
                else (" R ", rms_d, self._crete_rms_d, pal["secondaire"])
            )
            txt.append(lbl, style=f"bold {c_lbl}")
            pleins = round(max(0.0, min(1.0, niv)) * 9)
            idx_cr = min(8, round(max(0.0, min(1.0, cr)) * 8))
            for k in range(9):
                if k < pleins:
                    if k >= 8:
                        c_b = "#fb7185"
                    elif k >= 6:
                        c_b = _rgb_vers_hex(*_melanger_rgb(rgb_s, rgb_a, (k - 5) / 3.0))
                    else:
                        c_b = _rgb_vers_hex(*_melanger_rgb(rgb_ok, rgb_p, k / 6.0))
                    txt.append("▰", style=f"bold {c_b}")
                elif k == idx_cr and cr > 0.12:
                    txt.append("▪", style=f"bold {pal['accent']}")
                else:
                    txt.append("▱", style=pal["bordure"])

        # Mode 2 : Horizon Symétrique (basses au centre rayonnant vers les bords)
        if self.visualiseur_mode == "horizon":
            demi = max(1, w_vis // 2)
            sym: list[float] = []
            sym_cr: list[float] = []
            for i in range(w_vis):
                d_c = abs(i - demi) / max(1, demi)
                src_idx = min(w_vis - 1, int(d_c * (w_vis - 1)))
                sym.append(niveaux[src_idx])
                sym_cr.append(self._cretes_vumetre[src_idx])
            for r_idx in range(h_rows):
                for i in range(w_vis):
                    d_c = abs(i - demi) / max(1, demi)
                    amp = sym[i]
                    cr = sym_cr[i]
                    c_hex = _coul_grad(d_c, amp)
                    if h_rows >= 2 and r_idx == h_rows - 1:
                        # Reflet miroir adouci en ligne basse
                        k = min(len(CHARS_VUMETRE) - 1, int(amp * 5.2))
                        miroir = [" ", "▀", "▀", "▀", "█", "█"][min(5, k)]
                        c_ref = _rgb_vers_hex(*_melanger_rgb(_hex_vers_rgb(c_hex), _hex_vers_rgb(pal["surface_bg"]), 0.42))
                        txt.append(miroir, style=c_ref)
                    else:
                        idx_c = min(len(CHARS_VUMETRE) - 1, int(amp * (len(CHARS_VUMETRE) - 1)))
                        if cr > amp + 0.10 and idx_c <= 5:
                            txt.append("▫", style=f"bold {pal['accent']}")
                        else:
                            txt.append(CHARS_VUMETRE[idx_c], style=f"bold {c_hex}" if idx_c >= 5 else c_hex)
                _append_rms(r_idx)
                if r_idx < h_rows - 1:
                    txt.append("\n")
            return txt

        # Mode 3 : Onde Miroir TrueColor
        if self.visualiseur_mode == "onde" and h_rows >= 2:
            chars_haut = [" ", " ", "▁", "▄", "█"]
            chars_bas = [" ", "▀", "▀", "▀", "█"]
            for r_idx in range(h_rows):
                for i in range(w_vis):
                    norm_i = i / max(1, w_vis - 1)
                    amp = niveaux[i]
                    c_col = _coul_grad(norm_i, amp)
                    k = min(4, int(amp * 4.99))
                    if r_idx == 0:
                        txt.append(chars_haut[k], style=f"bold {c_col}" if k >= 3 else c_col)
                    elif r_idx == 1:
                        c_b = _rgb_vers_hex(*_melanger_rgb(_hex_vers_rgb(c_col), rgb_s, 0.35))
                        txt.append(chars_bas[k], style=c_b if k <= 2 else f"bold {c_col}")
                    else:
                        txt.append("─", style=pal["bordure"])
                _append_rms(r_idx)
                if r_idx < h_rows - 1:
                    txt.append("\n")
            return txt

        # Modes 4 & 5 : Oscilloscope Braille & Aurore Spectrale (remplissage haute densité 2×4)
        if self.visualiseur_mode in ("braille", "galaxie"):
            est_galaxie = self.visualiseur_mode == "galaxie"
            w_dots = w_vis * 2
            h_dots = h_rows * 4
            ys_dots = [0] * w_dots
            for dx_i in range(w_dots):
                idx_n = min(w_vis - 1, dx_i // 2)
                amp = niveaux[idx_n]
                if est_galaxie:
                    # Interpolation lissée entre colonnes voisines pour une courbe soyeuse
                    nxt = niveaux[min(w_vis - 1, idx_n + 1)]
                    amp_l = amp * 0.65 + nxt * 0.35 if dx_i % 2 else amp
                    ys_dots[dx_i] = max(0, min(h_dots - 1, round((1.0 - amp_l * 0.94) * (h_dots - 1))))
                else:
                    ph = t * 11.0 + dx_i * 0.24
                    y_f = 0.5 + math.sin(ph) * (amp * 0.44) + math.cos(ph * 0.5 - t * 4.0) * (amp * 0.14)
                    ys_dots[dx_i] = max(0, min(h_dots - 1, round((1.0 - y_f) * (h_dots - 1))))
            bits_g = (0x01, 0x02, 0x04, 0x40)
            bits_d = (0x08, 0x10, 0x20, 0x80)
            for r_idx in range(h_rows):
                y0 = r_idx * 4
                for i in range(w_vis):
                    norm_i = i / max(1, w_vis - 1)
                    mask = 0
                    yg = ys_dots[i * 2]
                    ydr = ys_dots[i * 2 + 1]
                    for sub_y in range(4):
                        yd = y0 + sub_y
                        if est_galaxie:
                            if yd >= yg:
                                mask |= bits_g[sub_y]
                            if yd >= ydr:
                                mask |= bits_d[sub_y]
                        else:
                            if yd == yg or (yd == h_dots // 2 and abs(yg - yd) <= 1 and niveaux[i] < 0.08):
                                mask |= bits_g[sub_y]
                            if yd == ydr or (yd == h_dots // 2 and abs(ydr - yd) <= 1 and niveaux[i] < 0.08):
                                mask |= bits_d[sub_y]
                    c_col = _coul_grad(norm_i, niveaux[i])
                    txt.append(chr(0x2800 + mask), style=f"bold {c_col}" if niveaux[i] > 0.45 else c_col)
                _append_rms(r_idx)
                if r_idx < h_rows - 1:
                    txt.append("\n")
            return txt

        # Modes 1 & 6 : Spectre Studio & Barres Néon LED sur 1 à 3 lignes empilées
        est_barres = self.visualiseur_mode == "barres"
        chars_bandes = [" ", "▎", "▌", "▊", "█"] if est_barres else CHARS_VUMETRE
        for r_idx in range(h_rows):
            seuil_bas = (h_rows - 1 - r_idx) / h_rows
            seuil_haut = (h_rows - r_idx) / h_rows
            tranche = 1.0 / h_rows
            for i in range(w_vis):
                norm_i = i / max(1, w_vis - 1)
                if est_barres and i % 3 == 2:
                    txt.append(" ")
                    continue
                val = niveaux[i]
                crete = self._cretes_vumetre[i]
                # Dégradé combinant position spectrale + élévation verticale
                c_col = _coul_grad(norm_i, max(val, 1.0 - r_idx / max(1, h_rows)))
                loc = max(0.0, min(1.0, (val - seuil_bas) / max(1e-4, tranche)))
                loc_crete = (crete - seuil_bas) / max(1e-4, tranche)
                if est_barres:
                    ch = "█" if loc >= 0.35 else ("▄" if loc >= 0.1 else ("▫" if 0.15 <= loc_crete <= 0.95 and crete > val + 0.08 else " "))
                    txt.append(ch, style=f"bold {pal['accent']}" if ch == "▫" else f"bold {c_col}")
                else:
                    idx_c = int(loc * (len(chars_bandes) - 1))
                    if r_idx == 0 and crete > val + 0.09 and seuil_bas <= crete <= seuil_haut and idx_c <= 5:
                        txt.append("▫", style=f"bold {pal['accent']}")
                    else:
                        txt.append(
                            chars_bandes[idx_c],
                            style=f"bold {c_col}" if idx_c >= 5 else c_col,
                        )
            _append_rms(r_idx)
            if r_idx < h_rows - 1:
                txt.append("\n")
        return txt

    def rendre_vumetre(self, largeur: int) -> Text:
        """Analyseur de spectre sur 1 ligne (compatibilité mini-lecteur et tests)."""
        return self.rendre_visualiseur(largeur, hauteur=1)

    def rendre_barre_progression(self, largeur: int) -> tuple[Text, int, int]:
        """Barre de progression Studio TrueColor en dégradé (1/8e de caractère) avec repères A-B et clic exact."""
        pal = self.palette
        txt = Text(no_wrap=True)
        est_radio = bool(self.piste_courante and self.piste_courante.get("_type") == "radio")
        pos = self.lecteur.position
        dur = self.lecteur.duree or (
            self.piste_courante.get("duree") if self.piste_courante else 0.0
        )
        dur = max(0.1, float(dur or 1.0))
        pct = max(0.0, min(1.0, pos / dur))

        pos_str = formater_duree(pos, radio=False)
        dur_str = "● LIVE" if est_radio else formater_duree(dur, radio=False)
        rest_sec = max(0, int(dur - pos))
        rest_str = "" if est_radio else f" (-{formater_duree(rest_sec)})"

        dispo = max(10, largeur - len(pos_str) - len(dur_str) - len(rest_str) - 4)
        offset_deb = len(pos_str) + 1
        offset_fin = offset_deb + dispo - 1

        txt.append(f"{pos_str} ", style="bold bright_white")

        rgb_p = _hex_vers_rgb(pal["primaire"], (192, 132, 252))
        rgb_s = _hex_vers_rgb(pal["secondaire"], (34, 211, 238))
        rgb_a = _hex_vers_rgb(pal["accent"], (244, 114, 182))

        if est_radio:
            pulse = int(time.time() * 6) % max(4, dispo)
            for k in range(dispo):
                d_p = abs(k - pulse)
                if d_p == 0:
                    txt.append("◉", style=f"bold {pal['accent']}")
                elif d_p <= 2:
                    txt.append("━", style=f"bold {pal['primaire']}")
                else:
                    txt.append("━", style=pal["succes"])
            txt.append(f" {dur_str}", style=f"bold {pal['succes']}")
            return txt, offset_deb, offset_fin

        pos_f = pct * dispo
        col_curseur = min(dispo - 1, int(pos_f))
        frac = round((pos_f - col_curseur) * 8)

        col_a = (
            max(0, min(dispo - 1, round((self.boucle_a / dur) * (dispo - 1))))
            if self.boucle_a is not None
            else None
        )
        col_b = (
            max(0, min(dispo - 1, round((self.boucle_b / dur) * (dispo - 1))))
            if self.boucle_b is not None
            else None
        )

        en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        curseur_ch = "◉" if en_lec else "◆"

        for k in range(dispo):
            t_k = k / max(1, dispo - 1)
            if k == col_a:
                txt.append("A", style=f"bold black on {pal['accent']}")
            elif k == col_b:
                txt.append("B", style=f"bold black on {pal['succes']}")
            elif k == col_curseur:
                txt.append(curseur_ch, style=f"bold {pal['accent']}")
            elif k < col_curseur:
                in_loop = col_a is not None and col_b is not None and col_a < k < col_b
                if in_loop:
                    c_seg = pal["accent"]
                else:
                    rgb_k = (
                        _melanger_rgb(rgb_p, rgb_s, t_k * 1.6)
                        if t_k < 0.62
                        else _melanger_rgb(rgb_s, rgb_a, (t_k - 0.62) / 0.38)
                    )
                    c_seg = _rgb_vers_hex(*rgb_k)
                txt.append("━", style=f"bold {c_seg}")
            elif k == col_curseur + 1 and frac > 4:
                txt.append(CHARS_PROGRESSION[frac - 4], style=pal["secondaire"])
            else:
                in_loop = col_a is not None and col_b is not None and col_a < k < col_b
                txt.append("─", style=pal["secondaire"] if in_loop else pal["bordure"])

        txt.append(f" {dur_str}", style="bold bright_white")
        if rest_str:
            txt.append(rest_str, style=pal["texte_muet"])
        return txt, offset_deb, offset_fin

    def rendre_banniere_karaoke(self, largeur: int) -> Panel:
        """Bannière karaoké téléprompteur 2 lignes : phrase active mot-à-mot + aperçu suivant / compte à rebours."""
        pal = self.palette
        t_pos = self.lecteur.position + self.decalage_paroles
        with self._verrou_paroles:
            items = list(self.paroles_items)
            source = self.paroles_source
            texte_libre = self.paroles_texte_libre
            en_chargement = self.paroles_en_chargement

        if en_chargement:
            corps = Text(
                "⠋ Synchronisation et calage des paroles...\n",
                style=f"italic {pal['primaire']}",
                justify="center",
            )
            return Panel(
                Align.center(corps, vertical="middle"),
                title=f"[bold {pal['primaire']}]🎙 Karaoké en direct[/bold {pal['primaire']}]",
                box=box.ROUNDED,
                border_style=pal["bordure"],
                height=4,
            )

        if not items and texte_libre:
            lignes = [l.strip() for l in texte_libre.splitlines() if l.strip()]
            corps = Text(justify="center", no_wrap=True, overflow="ellipsis")
            corps.append(f"♪ {lignes[0] if lignes else 'Paroles disponibles'}", style="bold #f1f5f9")
            if len(lignes) > 1:
                corps.append(f"\n↳ {lignes[1]}", style=f"italic {pal['texte_muet']}")
            return Panel(
                Align.center(corps),
                title=f"[bold {pal['primaire']}]🎙 Paroles ({source})[/bold {pal['primaire']}]",
                box=box.ROUNDED,
                border_style=pal["bordure"],
                height=4,
            )

        if not items:
            p = self.piste_courante
            if p and p.get("_type") == "radio":
                icy = self.lecteur.icy_title
                corps = Text(justify="center", no_wrap=True, overflow="ellipsis")
                corps.append(
                    f"📻 En direct : {icy}" if icy else f"📻 {p.get('titre')} — Flux direct",
                    style=f"bold {pal['accent']}",
                )
                corps.append(
                    f"\n{p.get('artiste') or 'Diffusion live'}",
                    style=pal["texte_dim"],
                )
                return Panel(
                    Align.center(corps),
                    title=f"[bold {pal['succes']}]📡 Radio Live Stream[/bold {pal['succes']}]",
                    box=box.ROUNDED,
                    border_style=pal["succes"],
                    height=4,
                )
            titre = p.get("titre") if p else "Aucun morceau sélectionné"
            corps = Text(justify="center", no_wrap=True, overflow="ellipsis")
            corps.append(f"♪ {titre}\n", style=f"italic {pal['texte_dim']}")
            corps.append(
                "[Ctrl+L] Studio Paroles  •  [Ctrl+V] Coller .lrc",
                style=pal["texte_muet"],
            )
            return Panel(
                Align.center(corps),
                title=f"[bold {pal['texte_muet']}]🎙 Karaoké[/bold {pal['texte_muet']}]",
                box=box.ROUNDED,
                border_style=pal["bordure"],
                height=4,
            )

        idx, item, est_pause, t_reprise = ligne_affichee(items, t_pos)
        prochaine = next(
            (it.texte for it in items[max(0, idx + 1) :] if not it.pause and it.texte.strip()),
            "",
        )
        max_w = max(18, largeur - 8)

        l1 = Text(no_wrap=True, overflow="ellipsis")
        l2 = Text(no_wrap=True, overflow="ellipsis")

        if est_pause or (item and item.pause):
            duree_p = max(0.8, (item.fin - item.t) if item else max(1.0, t_reprise))
            ratio_p = max(0.0, min(1.0, 1.0 - t_reprise / duree_p))
            w_p = min(22, max(8, max_w // 3))
            l1.append("♪  ", style=f"bold {pal['primaire']}")
            l1.append_text(barre_degrade(ratio_p, w_p, pal["primaire"], pal["accent"], pal["bordure"], "─"))
            l1.append("  ♪", style=f"bold {pal['secondaire']}")
            if t_reprise > 0.4:
                l1.append(f"  {t_reprise:.1f}s", style=f"italic {pal['texte_dim']}")
            if prochaine:
                ap_p = prochaine[: max_w - 4] + ("…" if len(prochaine) > max_w - 4 else "")
                l2.append(f"↳ {ap_p}", style=f"italic {pal['texte_dim']}")
            else:
                l2.append("Interlude musical", style=f"italic {pal['texte_muet']}")
        elif item:
            if item.mots:
                l1.append("▎ ", style=f"bold {pal['accent']}")
                for m_deb, mot, m_fin in item.mots:
                    if t_pos >= m_fin:
                        l1.append(mot, style=f"bold {pal['primaire']}")
                    elif m_deb <= t_pos < m_fin:
                        l1.append(
                            mot,
                            style=f"bold bright_white on {pal['badge_bg']}",
                        )
                    else:
                        l1.append(mot, style="bold #e2e8f0")
            else:
                l1.append(f"▎ {item.texte}", style="bold bright_white")

            if prochaine:
                ap_p = prochaine[: max_w - 4] + ("…" if len(prochaine) > max_w - 4 else "")
                l2.append(f"↳ {ap_p}", style=f"italic {pal['texte_muet']}")
            else:
                l2.append("♪  Fin des paroles", style=f"italic {pal['texte_muet']}")

        corps_lay = Layout()
        corps_lay.split_column(
            Layout(Align.center(l1), size=1),
            Layout(Align.center(l2), size=1),
        )

        calage_tag = (
            f" • {self.decalage_paroles:+.2f}s"
            if self.decalage_paroles != 0
            else ""
        )
        titre_banniere = (
            f"[bold {pal['accent']}]🎙 Karaoké en direct[/bold {pal['accent']}] "
            f"[bold {pal['secondaire']}]({source}{calage_tag})[/bold {pal['secondaire']}]"
        )
        return Panel(
            corps_lay,
            title=titre_banniere,
            box=box.ROUNDED,
            border_style=pal["bordure_active"] if not est_pause else pal["bordure"],
            height=4,
        )

    @staticmethod
    def _decouper_ligne_paroles(texte: str, max_car: int) -> list[str]:
        """Découpe une ligne longue sur les espaces sans dépasser `max_car`."""
        mots = texte.split(" ")
        lignes: list[str] = []
        courante = ""
        for mot in mots:
            if not courante:
                courante = mot
            elif len(courante) + 1 + len(mot) <= max_car:
                courante += " " + mot
            else:
                lignes.append(courante)
                courante = mot
        if courante or not lignes:
            lignes.append(courante)
        return lignes

    def rendre_zone_paroles(
        self, hauteur_disponible: int, largeur: int = 64, y_depart: int = 17
    ) -> Panel:
        """Vue paroles continue à colonne fixe et profondeur 4 niveaux : zéro saut, zéro rechargement, clic exact."""
        pal = self.palette
        self._paroles_lignes_ecran = []
        t_pos = self.lecteur.position + self.decalage_paroles
        with self._verrou_paroles:
            items = list(self.paroles_items)
            source = self.paroles_source
            texte_libre = self.paroles_texte_libre
            en_chargement = self.paroles_en_chargement

        if en_chargement:
            return Panel(
                Align.center(
                    Text(
                        "⠋ Recherche et alignement des paroles...",
                        style=f"italic {pal['primaire']}",
                    ),
                    vertical="middle",
                ),
                title=f"[bold {pal['primaire']}] Paroles synchronisées [/bold {pal['primaire']}]",
                box=box.ROUNDED,
                border_style=pal["bordure"],
            )

        if not items and texte_libre:
            lignes_tl = [l for l in texte_libre.splitlines() if l.strip()]
            w_col = min(66, max(24, largeur - 6))
            marge_l = " " * max(1, (largeur - 2 - w_col) // 2)
            t_corps = Text()
            for l in lignes_tl[: max(3, hauteur_disponible - 2)]:
                for sub in self._decouper_ligne_paroles(l, w_col):
                    t_corps.append(f"{marge_l}{sub}\n", style=pal["texte_dim"])
            return Panel(
                t_corps,
                title=f"[bold {pal['primaire']}] Paroles non synchronisées ({source}) • [Ctrl+L] Studio [/bold {pal['primaire']}]",
                box=box.ROUNDED,
                border_style=pal["bordure"],
            )

        if not items:
            p = self.piste_courante
            msg = Text(justify="center")
            msg.append("♪\n\n", style=f"bold {pal['primaire']}")
            msg.append(
                f"{p.get('titre') if p else 'Aucun morceau'}\n",
                style="bold bright_white",
            )
            if p and p.get("artiste"):
                msg.append(f"{p.get('artiste')}\n\n", style=pal["texte_dim"])
            else:
                msg.append("\n")
            msg.append(
                "Aucune parole synchronisée pour ce titre.\n\n",
                style=f"italic {pal['texte_muet']}",
            )
            if p and not p.get("_type"):
                msg.append(
                    " [Ctrl+L] Chercher (LRCLIB/NetEase) ",
                    style=f"bold black on {pal['primaire']}",
                )
                msg.append("  ")
                msg.append(
                    " [R] Recaler ",
                    style=f"bold bright_white on {pal['badge_bg']}",
                )
                msg.append("\n\n")
                msg.append(
                    "[Ctrl+V] Coller un fichier .lrc directement",
                    style=pal["texte_muet"],
                )
            return Panel(
                Align.center(msg, vertical="middle"),
                title=f"[bold {pal['texte_muet']}] Paroles [/bold {pal['texte_muet']}]",
                box=box.ROUNDED,
                border_style=pal["bordure"],
            )

        idx_actif, _, _, _ = ligne_affichee(items, t_pos)
        idx_actif = max(0, idx_actif)

        lignes_visibles = max(5, hauteur_disponible - 3)
        centre = lignes_visibles // 2
        debut = max(0, idx_actif - centre)
        fin = min(len(items), debut + lignes_visibles)
        if fin - debut < lignes_visibles:
            debut = max(0, fin - lignes_visibles)
        self._paroles_fenetre = (debut, fin)

        avec_ts = self.afficher_timestamps_paroles
        w_lecture = min(68, max(28, largeur - 6))
        marge_g = " " * max(1, (largeur - 2 - w_lecture) // 2)
        gutter = 11 if avec_ts else 3  # " ▎ [00:00] " (11) ou " ▎ " (3) -> colonne fixe garantie
        max_phrase = max(16, w_lecture - gutter)

        # Dégradé atmosphérique de profondeur (4 niveaux continus sans flash ni rechargement)
        rgb_dim = _hex_vers_rgb(pal["texte_dim"], (180, 190, 215))
        rgb_muet = _hex_vers_rgb(pal["texte_muet"], (110, 118, 148))
        rgb_surf = _hex_vers_rgb(pal["surface_bg"], (9, 8, 20))
        c_dist1 = _rgb_vers_hex(*_melanger_rgb((240, 244, 255), rgb_dim, 0.35))
        c_dist2 = pal["texte_dim"]
        c_dist3 = pal["texte_muet"]
        c_dist4 = _rgb_vers_hex(*_melanger_rgb(rgb_muet, rgb_surf, 0.36))

        zone_texte = Text()
        lignes_ecran_nb = 0
        for i in range(debut, fin):
            if lignes_ecran_nb >= lignes_visibles:
                break
            item = items[i]
            est_actif = i == idx_actif
            dist = abs(i - idx_actif)
            time_tag = f"[{int(item.t) // 60:02d}:{int(item.t) % 60:02d}] " if avec_ts else ""

            if item.pause:
                self._paroles_lignes_ecran.append((y_depart + lignes_ecran_nb, item.t))
                if est_actif:
                    zone_texte.append(f"{marge_g} ▎ ", style=f"bold {pal['accent']}")
                    if avec_ts:
                        zone_texte.append(time_tag, style=f"bold {pal['primaire']}")
                    zone_texte.append("♪  • • • ● • • •  ♪\n", style=f"bold {pal['primaire']}")
                else:
                    zone_texte.append(
                        f"{marge_g}   {time_tag}♪ • • • ♪\n",
                        style=c_dist4 if dist >= 3 else c_dist3,
                    )
                lignes_ecran_nb += 1
                continue

            if est_actif and item.mots:
                sous_lignes_mots: list[list[tuple[float, str, float]]] = [[]]
                cur_w = 0
                for seg_m in item.mots:
                    m_len = len(seg_m[1])
                    if cur_w > 0 and cur_w + m_len > max_phrase:
                        sous_lignes_mots.append([seg_m])
                        cur_w = m_len
                    else:
                        sous_lignes_mots[-1].append(seg_m)
                        cur_w += m_len
                for sl_idx, segs in enumerate(sous_lignes_mots):
                    if lignes_ecran_nb >= lignes_visibles:
                        break
                    self._paroles_lignes_ecran.append((y_depart + lignes_ecran_nb, item.t))
                    if sl_idx == 0:
                        zone_texte.append(f"{marge_g} ▎ ", style=f"bold {pal['accent']}")
                        if avec_ts:
                            zone_texte.append(time_tag, style=f"bold {pal['accent']}")
                    else:
                        zone_texte.append(f"{marge_g} ▎ ", style=pal["primaire"])
                        zone_texte.append(" " * (gutter - 3))
                    for m_deb, mot, m_fin in segs:
                        if t_pos >= m_fin:
                            zone_texte.append(mot, style=f"bold {pal['primaire']}")
                        elif m_deb <= t_pos < m_fin:
                            zone_texte.append(
                                mot,
                                style=f"bold bright_white on {pal['badge_bg']}",
                            )
                        else:
                            zone_texte.append(mot, style="bold #f8fafc")
                    zone_texte.append("\n")
                    lignes_ecran_nb += 1
            else:
                if est_actif:
                    style_t = f"bold {pal['accent']}"
                    style_l = "bold bright_white"
                    pref_rail = f"{marge_g} ▎ "
                else:
                    style_l = (
                        c_dist1
                        if dist == 1
                        else (c_dist2 if dist == 2 else (c_dist3 if dist == 3 else c_dist4))
                    )
                    style_t = c_dist3 if dist <= 2 else c_dist4
                    pref_rail = f"{marge_g}   "

                for sl_idx, sub in enumerate(self._decouper_ligne_paroles(item.texte, max_phrase)):
                    if lignes_ecran_nb >= lignes_visibles:
                        break
                    self._paroles_lignes_ecran.append((y_depart + lignes_ecran_nb, item.t))
                    if sl_idx == 0:
                        zone_texte.append(pref_rail, style=style_t)
                        if avec_ts:
                            zone_texte.append(time_tag, style=style_t)
                    else:
                        zone_texte.append(f"{marge_g}{' ' * gutter}")
                    zone_texte.append(f"{sub}\n", style=style_l)
                    lignes_ecran_nb += 1

        calage_tag = (
            f" • Calage: {self.decalage_paroles:+.2f}s"
            if self.decalage_paroles != 0
            else ""
        )
        titre = f" Paroles synchronisées ({source}{calage_tag}) • [Clic ligne] Aller au passage "
        return Panel(
            zone_texte,
            title=f"[bold {pal['primaire']}]{titre}[/bold {pal['primaire']}]",
            title_align="center",
            box=box.ROUNDED,
            border_style=pal["bordure"],
        )

    def obtenir_widget_pochette(self, w_car: int = 12, h_car: int = 6) -> Text:
        """Retourne la miniature TrueColor arrondie (avec cache) ou vinyle articulé."""
        pal = self.palette
        chemin = self.chemin_pochette_piste(self.piste_courante)
        en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        phase = self.index_animation if not chemin else 0
        fond_hex = pal.get("surface_bg", "#090814")
        cle = (chemin, w_car, h_car, phase, pal["primaire"], fond_hex, en_lec)
        if cle != self._cache_pochette_cle or self._cache_pochette_rendu is None:
            self._cache_pochette_cle = cle
            self._cache_pochette_rendu = rendre_pochette_ansi(
                chemin,
                w_car,
                h_car,
                phase,
                pal["primaire"],
                fond_hex=fond_hex,
                en_lecture=en_lec,
            )
        return self._cache_pochette_rendu

    def rendre_panneau_lecteur(self, largeur: int, hauteur: int) -> Layout:
        pal = self.palette
        p = self.piste_courante or {}
        titre_m = p.get("titre") or "Aucun morceau sélectionné"
        artiste_m = p.get("artiste") or "Onde"
        album_m = p.get("album") or ""
        sous_titre = f"{artiste_m} • {album_m}" if album_m else artiste_m

        badge_comp = badge_qualite_piste(p, complet=True)
        largeur_tot = self.console.size.width
        w_liste = self._largeur_liste(largeur_tot)

        afficher_pochette = largeur >= 52
        w_art, h_art = 12, 6  # Carré exact 1:1 (12 cols × 12 sous-pixels)
        w_pochette_col = 14 if afficher_pochette else 0
        w_infos = max(20, largeur - w_pochette_col - 6)

        entete_lecteur = Text(no_wrap=True, overflow="ellipsis")
        entete_lecteur.append(f"{titre_m} ", style="bold bright_white")
        if p.get("id") in self.favoris_set:
            entete_lecteur.append("♥ ", style="bold bright_red")
        if badge_comp:
            entete_lecteur.append(
                f" {badge_comp} ",
                style=f"bold bright_white on {pal['badge_bg']}",
            )
        if self.spectre.signal_temps_reel and not self.lecteur.en_pause:
            entete_lecteur.append(" ")
            entete_lecteur.append(" FFT ", style=f"bold black on {pal['succes']}")
        entete_lecteur.append(f"\n{sous_titre}", style=pal["texte_dim"])

        vumetre = self.rendre_visualiseur(w_infos, hauteur=2)
        barre_prog, off_deb, off_fin = self.rendre_barre_progression(w_infos)
        ctrl_txt, ctrl_spans = self._texte_controles_transport(compact=(w_infos < 62))

        # Coordonnées exactes des contrôles dans la Carte Hero (border gauche à w_liste + 1)
        x_droit_inner = w_liste + 1 + 1 + w_pochette_col + (1 if not afficher_pochette else 0)
        marge_prog = max(0, (w_infos - cell_len(barre_prog.plain)) // 2)
        self._enregistrer_zone(
            "barre_prog",
            x_droit_inner + marge_prog + off_deb,
            9,
            x_droit_inner + marge_prog + off_fin,
            9,
        )
        marge_ctrl = max(0, (w_infos - cell_len(ctrl_txt.plain)) // 2)
        for nom_c, deb_c, fin_c in ctrl_spans:
            self._enregistrer_zone(
                nom_c,
                x_droit_inner + marge_ctrl + deb_c,
                10,
                x_droit_inner + marge_ctrl + fin_c,
                10,
            )

        col_droite = Layout()
        col_droite.split_column(
            Layout(entete_lecteur, size=2),
            Layout(vumetre, size=2),
            Layout(Align.center(barre_prog), size=1),
            Layout(Align.center(ctrl_txt), size=1),
        )

        if afficher_pochette:
            chemin_cov = self.chemin_pochette_piste(self.piste_courante)
            if self.pochette_hd.supporte and chemin_cov:
                self._cible_pochette_hd = (chemin_cov, w_liste + 3, 5, w_art, h_art)
            widget_cov = self.obtenir_widget_pochette(w_art, h_art)
            corps_haut = Layout()
            corps_haut.split_row(
                Layout(Align.center(widget_cov), size=w_pochette_col),
                col_droite,
            )
        else:
            corps_haut = col_droite

        suiv = self._prochaine_piste_apercu()
        sous_t_lec = None
        if suiv:
            t_s = (suiv.get("titre") or "")[:28]
            a_s = (suiv.get("artiste") or "")[:18]
            q_cnt = f" (+{len(self.file_attente)} en file)" if self.file_attente else ""
            sous_t_lec = f"[{pal['texte_muet']}] ⏭ À suivre : [{pal['texte_dim']}]{t_s}[/] — {a_s}{q_cnt} [/]"

        vis_nom = dict(MODES_VISUALISEUR).get(self.visualiseur_mode, "Spectre")
        p_lecteur = Panel(
            corps_haut,
            title=f"[bold {pal['primaire']}]◆ Studio En Lecture[/bold {pal['primaire']}] [{pal['texte_muet']}]• {vis_nom}[/]",
            subtitle=sous_t_lec,
            subtitle_align="right",
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
            height=8,
        )

        banniere_st = self.rendre_banniere_karaoke(largeur)
        panneau_paroles = self.rendre_zone_paroles(hauteur - 12, largeur=largeur, y_depart=17)

        layout_droit = Layout()
        layout_droit.split_column(
            Layout(p_lecteur, size=8),
            Layout(banniere_st, size=4),
            Layout(panneau_paroles),
        )
        return layout_droit

    def rendre_vue_plein_ecran_paroles(self, largeur: int, hauteur: int) -> Layout:
        """Mode scène karaoké immersif plein écran."""
        pal = self.palette
        p = self.piste_courante or {}
        titre_m = p.get("titre") or "Aucun morceau sélectionné"
        artiste_m = p.get("artiste") or "Onde"
        album_m = p.get("album") or ""
        sous_titre = f"{artiste_m} • {album_m}" if album_m else artiste_m

        en_lecture = (
            self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        )
        roue = (
            ROUES_VINYLE[self.index_animation % len(ROUES_VINYLE)]
            if en_lecture
            else "⏸"
        )

        entete_plein = Text(no_wrap=True, overflow="ellipsis")
        entete_plein.append(f" {roue} ", style=f"bold {pal['accent']}")
        entete_plein.append(f"{titre_m} ", style="bold bright_white")
        entete_plein.append(f"— {sous_titre}  ", style=pal["texte_dim"])
        b_comp = badge_qualite_piste(p, complet=False)
        if b_comp:
            entete_plein.append(f" {b_comp} ", style=f"bold bright_white on {pal['badge_bg']}")

        w_in = max(20, largeur - 6)
        vumetre = self.rendre_visualiseur(w_in, hauteur=2)
        barre_prog, off_deb, off_fin = self.rendre_barre_progression(w_in)
        marge_p = max(0, (largeur - 2 - cell_len(barre_prog.plain)) // 2)
        self._enregistrer_zone("barre_prog", 2 + marge_p + off_deb, 8, 2 + marge_p + off_fin, 8)

        corps_haut = Layout()
        corps_haut.split_column(
            Layout(Align.center(entete_plein), size=1),
            Layout(Align.center(vumetre), size=2),
            Layout(Align.center(barre_prog), size=1),
        )

        p_lecteur_plein = Panel(
            corps_haut,
            title=f"[bold {pal['accent']}]🎙 Onde Live Karaoké[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
            height=6,
        )

        banniere = self.rendre_banniere_karaoke(largeur)
        defilement = self.rendre_zone_paroles(hauteur - 10, largeur=largeur, y_depart=15)

        stage = Layout()
        stage.split_column(
            Layout(p_lecteur_plein, size=6),
            Layout(banniere, size=4),
            Layout(defilement),
        )
        return stage

    def rendre_vue_scene_immersion(self, largeur: int, hauteur: int) -> Layout:
        """Mode Scène Plein Écran Cinéma : pochette HD 1:1, spectre TrueColor, À suivre & paroles."""
        pal = self.palette
        p = self.piste_courante or {}
        titre_m = p.get("titre") or "Aucun morceau sélectionné"
        artiste_m = p.get("artiste") or "Onde"
        album_m = p.get("album") or ""
        est_fav = p.get("id") in self.favoris_set
        badge_comp = badge_qualite_piste(p, complet=True)

        h_haut = max(10, hauteur - 4)
        w_gauche = max(34, min(58, int(largeur * 0.42)))
        w_droite = max(30, largeur - w_gauche)

        # Ratio visuel 1:1 exact : w_art = h_art * 2
        h_art_zone = max(6, h_haut - 10)
        h_art = max(5, min(14, h_art_zone))
        w_art = h_art * 2
        if w_art > w_gauche - 6:
            w_art = max(10, ((w_gauche - 6) // 2) * 2)
            h_art = max(5, w_art // 2)

        chemin_cov = self.chemin_pochette_piste(self.piste_courante)
        marge_haut_interne = max(0, (h_art_zone - h_art) // 2)
        col_hd = 1 + max(2, (w_gauche - w_art) // 2)
        row_hd = 5 + marge_haut_interne
        if self.pochette_hd.supporte and chemin_cov:
            self._cible_pochette_hd = (chemin_cov, col_hd, row_hd, w_art, h_art)
        widget_art = self.obtenir_widget_pochette(w_art, h_art)

        bloc_meta = Text(justify="center")
        bloc_meta.append(f"{titre_m}", style="bold bright_white")
        if est_fav:
            bloc_meta.append(" ♥", style="bold bright_red")
        bloc_meta.append(f"\n{artiste_m}", style=f"bold {pal['primaire']}")
        if album_m:
            bloc_meta.append(f" • {album_m}", style=pal["texte_dim"])
        bloc_meta.append("\n")
        if badge_comp:
            bloc_meta.append(
                f" 🎵 {badge_comp} ",
                style=f"bold bright_white on {pal['badge_bg']}",
            )
        if self.spectre.signal_temps_reel and not self.lecteur.en_pause:
            bloc_meta.append(" ")
            bloc_meta.append(" FFT LIVE ", style=f"bold black on {pal['succes']}")
        if self.effet_dsp != "off":
            nom_dsp = next((n for k, n, _ in EFFETS_DSP if k == self.effet_dsp), "DSP")
            bloc_meta.append(" ")
            bloc_meta.append(f" {nom_dsp} ", style=f"bold black on {pal['accent']}")

        vumetre_gauche = self.rendre_visualiseur(max(16, w_gauche - 8), hauteur=2)

        suiv = self._prochaine_piste_apercu()
        ligne_suiv = Text(justify="center", no_wrap=True, overflow="ellipsis")
        if suiv:
            ligne_suiv.append("⏭ À suivre : ", style=f"bold {pal['secondaire']}")
            ligne_suiv.append(f"{suiv.get('titre') or ''}", style="white")
            if suiv.get("artiste"):
                ligne_suiv.append(f" — {suiv.get('artiste')}", style=pal["texte_muet"])
        else:
            ligne_suiv.append("[Ctrl+X] Lancer Radio du titre", style=pal["texte_muet"])

        col_pochette = Layout()
        col_pochette.split_column(
            Layout(Align.center(widget_art, vertical="middle"), size=h_art_zone),
            Layout(Align.center(bloc_meta), size=3),
            Layout(Align.center(vumetre_gauche), size=2),
            Layout(Align.center(ligne_suiv), size=1),
        )

        panneau_gauche = Panel(
            col_pochette,
            title=f"[bold {pal['primaire']}]💿 Scène Immersion[/bold {pal['primaire']}]",
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
        )

        col_paroles = Layout()
        col_paroles.split_column(
            Layout(self.rendre_banniere_karaoke(w_droite), size=4),
            Layout(self.rendre_zone_paroles(h_haut - 4, largeur=w_droite, y_depart=9)),
        )

        zone_centrale = Layout()
        zone_centrale.split_row(
            Layout(panneau_gauche, size=w_gauche),
            Layout(col_paroles),
        )

        w_bar = max(24, largeur - 8)
        barre_bas, off_deb, off_fin = self.rendre_barre_progression(w_bar)
        y_bas_prog = 4 + h_haut + 1
        marge_b = max(0, (largeur - 2 - cell_len(barre_bas.plain)) // 2)
        self._enregistrer_zone("barre_prog", 2 + marge_b + off_deb, y_bas_prog, 2 + marge_b + off_fin, y_bas_prog)

        ctrl_bas, spans_bas = self._texte_controles_transport(compact=(largeur < 85))
        y_bas_ctrl = y_bas_prog + 1
        marge_c = max(0, (largeur - 2 - cell_len(ctrl_bas.plain)) // 2)
        for nom_c, deb_c, fin_c in spans_bas:
            self._enregistrer_zone(nom_c, 2 + marge_c + deb_c, y_bas_ctrl, 2 + marge_c + fin_c, y_bas_ctrl)

        lay_bas = Layout()
        lay_bas.split_column(
            Layout(Align.center(barre_bas), size=1),
            Layout(Align.center(ctrl_bas), size=1),
        )
        panneau_bas = Panel(
            lay_bas,
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
            height=4,
        )

        racine_scene = Layout()
        racine_scene.split_column(
            Layout(zone_centrale),
            Layout(panneau_bas, size=4),
        )
        return racine_scene

    def rendre_vue_accueil(self, largeur: int, hauteur: int) -> Layout:
        """Vue Accueil Studio ([F3]) : Salutation dégradée, Reprise Hero, 4 Étagères et Mixes rapides."""
        pal = self.palette
        self._accueil_zones = []
        donnees = self.preparer_donnees_accueil()
        sections: list[tuple[str, list[dict[str, Any]]]] = donnees["sections"]
        mixes: list[dict[str, Any]] = donnees["mixes"]

        self.accueil_section = max(0, min(4, self.accueil_section))
        if self.accueil_section < 4:
            nb_it = len(sections[self.accueil_section][1])
            self.accueil_index = max(0, min(self.accueil_index, nb_it - 1)) if nb_it else 0
        else:
            self.accueil_index = max(0, min(self.accueil_index, len(mixes) - 1)) if mixes else 0

        # 1. Bannière Hero : Salutation + Résumé bibliothèque + Carte « Reprendre l'écoute »
        nb_artistes = len({(p.get("artiste") or "").strip() for p in self.pistes if p.get("artiste")})
        duree_tot = sum(float(p.get("duree") or 0.0) for p in self.pistes)
        h_tot = int(duree_tot) // 3600
        m_tot = (int(duree_tot) % 3600) // 60
        dur_lbl = f"{h_tot}h {m_tot:02d}m" if h_tot else f"{m_tot} min"
        nb_hires = sum(
            1
            for p in self.pistes
            if (p.get("format") or "").lower() in ("flac", "alac", "wav", "aiff")
            or int(p.get("bits") or 0) >= 24
        )

        salut_t = Text(no_wrap=True, overflow="ellipsis")
        salut_t.append_text(
            texte_degrade(
                f"✦ {salutation_horaire()} !",
                pal["primaire"],
                pal["accent"],
                gras=True,
                c_milieu=pal["secondaire"],
            )
        )
        salut_t.append(
            f"\n{len(self.pistes)} titres • {nb_artistes} artistes • {dur_lbl} • "
            f"♥ {len(self.favoris_set)} favoris • 💎 {nb_hires} Hi-Res/FLAC\n\n",
            style=pal["texte_dim"],
        )
        salut_t.append(" Alt+Entrée ", style=f"bold black on {pal['primaire']}")
        salut_t.append(" Aléa  ", style=pal["texte_dim"])
        salut_t.append(" Ctrl+X ", style=f"bold black on {pal['secondaire']}")
        salut_t.append(" Radio  ", style=pal["texte_dim"])
        salut_t.append(" R ", style=f"bold black on {pal['accent']}")
        salut_t.append(" Découvrir", style=pal["texte_dim"])

        reprise = self.piste_courante or (sections[0][1][0] if sections[0][1] else (self.pistes[0] if self.pistes else None))
        rep_txt = Text(no_wrap=True, overflow="ellipsis")
        if reprise:
            en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
            rep_txt.append(
                "▶ EN LECTURE" if en_lec else "🔖 REPRENDRE L'ÉCOUTE",
                style=f"bold {pal['succes'] if en_lec else pal['accent']}",
            )
            rep_txt.append(f"\n{reprise.get('titre') or 'Sans titre'}", style="bold bright_white")
            rep_txt.append(f"\n{reprise.get('artiste') or 'Onde'}", style=pal["primaire"])
            b_q = badge_qualite_piste(reprise, complet=False)
            if b_q:
                rep_txt.append(f"  [{b_q}]", style=pal["texte_muet"])
            if reprise == self.piste_courante:
                dur_r = max(1.0, float(self.lecteur.duree or reprise.get("duree") or 1.0))
                pct_r = max(0.0, min(1.0, float(self.lecteur.position) / dur_r))
                rep_txt.append(f"\n{formater_duree(self.lecteur.position)} ", style="bold white")
                rep_txt.append_text(barre_degrade(pct_r, 18, pal["primaire"], pal["accent"], pal["bordure"], "─"))
                rep_txt.append(f" {formater_duree(dur_r)}", style=pal["texte_muet"])
        else:
            rep_txt.append("Ta bibliothèque est prête\n", style=f"bold {pal['primaire']}")
            rep_txt.append("Appuie sur [Y] pour télécharger depuis YouTube\nou [Ctrl+R] pour scanner ~/Musique", style=pal["texte_dim"])

        hero_row = Layout()
        if largeur >= 88 and reprise:
            mini_cov = self.obtenir_widget_pochette(8, 4) if reprise == self.piste_courante else rendre_pochette_ansi(
                self.chemin_pochette_piste(reprise), 8, 4, 0, pal["primaire"], fond_hex=pal["surface_bg"]
            )
            hero_row.split_row(
                Layout(salut_t, ratio=5),
                Layout(Align.center(mini_cov), size=10),
                Layout(rep_txt, ratio=4),
            )
        else:
            hero_row.split_row(Layout(salut_t, ratio=3), Layout(rep_txt, ratio=2))

        p_hero = Panel(
            hero_row,
            title=f"[bold {pal['primaire']}]✦ Onde Studio — Accueil & Découverte ([←/→] Section • [↑/↓] Titre • [Entrée] Lire)[/bold {pal['primaire']}]",
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
            height=6,
        )
        # Clic sur la partie droite du hero = reprendre / lire
        self._accueil_zones.append((largeur // 2, 4, largeur - 2, 9, "reprise", reprise))

        # 2. Grille 2×2 des 4 étagères éditoriales
        h_etag = max(7, (hauteur - 9) // 2)
        w_col = max(28, largeur // 2)
        lignes_par_carte = max(3, h_etag - 2)

        def _rendre_etagere(idx_sec: int, y_top: int, x_left: int, w_card: int) -> Panel:
            titre_s, items_s = sections[idx_sec]
            est_sec_act = self.accueil_section == idx_sec
            tbl = Table(box=None, expand=True, show_header=False, padding=(0, 1))
            tbl.add_column("Cur", width=4, no_wrap=True)
            tbl.add_column("Info", ratio=4, no_wrap=True, overflow="ellipsis")
            tbl.add_column("Meta", width=8, justify="right", no_wrap=True)

            if not items_s:
                return Panel(
                    Align.center(Text("Aucun morceau pour l'instant", style=pal["texte_muet"]), vertical="middle"),
                    title=f"[bold {pal['accent'] if est_sec_act else pal['primaire']}]{titre_s}[/]",
                    box=box.ROUNDED,
                    border_style=pal["accent"] if est_sec_act else pal["bordure"],
                )

            en_lec_acc = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
            eq_acc = BARRES_LECTURE_ANIME[(self.index_animation // 2) % len(BARRES_LECTURE_ANIME)] if en_lec_acc else "▁▁▁"
            max_ec = max((int(x.get("ecoutes") or 0) for x in items_s), default=1) or 1
            for j, it in enumerate(items_s[:lignes_par_carte]):
                sel = est_sec_act and j == self.accueil_index
                en_c = bool(self.piste_courante and self.piste_courante.get("id") == it.get("id"))
                cur = f"▎{eq_acc}" if (sel and en_c) else ("▎❯ " if sel else (f" {eq_acc}" if en_c else f" {j + 1:2d}"))
                c_st = f"bold {pal['succes']}" if en_c else (f"bold {pal['accent']}" if sel else pal["texte_muet"])
                inf = Text(no_wrap=True, overflow="ellipsis")
                inf.append(it.get("titre") or "Sans titre", style="bold bright_white" if sel else ("bold " + pal["succes"] if en_c else "#f1f5f9"))
                inf.append(" — ", style=pal["texte_muet"])
                inf.append(it.get("artiste") or "", style=pal["primaire"] if sel else pal["texte_dim"])
                if idx_sec == 1 and int(it.get("ecoutes") or 0) > 0:
                    meta_t = Text(f"{int(it['ecoutes'])}× ", style=f"bold {pal['accent']}")
                    meta_t.append_text(barre_degrade(int(it["ecoutes"]) / max_ec, 4, pal["primaire"], pal["accent"], pal["bordure"]))
                else:
                    meta_t = Text(formater_duree(it.get("duree")), style=pal["texte_muet"])
                tbl.add_row(
                    Text(cur, style=c_st),
                    inf,
                    meta_t,
                    style=f"on {pal['selection_bg']}" if sel else None,
                )
                self._accueil_zones.append(
                    (x_left + 1, y_top + 1 + j, x_left + w_card - 2, y_top + 1 + j, "piste", (idx_sec, j, it))
                )

            return Panel(
                tbl,
                title=f"[bold {pal['accent'] if est_sec_act else pal['primaire']}]{'◆ ' if est_sec_act else ''}{titre_s} ({len(items_s)})[/]",
                title_align="left",
                box=box.ROUNDED,
                border_style=pal["accent"] if est_sec_act else pal["bordure"],
            )

        y_row1 = 10
        y_row2 = 10 + h_etag
        ligne1 = Layout()
        ligne1.split_row(
            Layout(_rendre_etagere(0, y_row1, 1, w_col)),
            Layout(_rendre_etagere(1, y_row1, w_col + 1, largeur - w_col)),
        )
        ligne2 = Layout()
        ligne2.split_row(
            Layout(_rendre_etagere(2, y_row2, 1, w_col)),
            Layout(_rendre_etagere(3, y_row2, w_col + 1, largeur - w_col)),
        )

        # 3. Dock Mixes Rapides / Genres (section 4)
        est_mix_act = self.accueil_section == 4
        mix_txt = Text(no_wrap=True, overflow="crop")
        y_mix = 4 + hauteur - 2
        mx = 3
        for idx_m, mx_item in enumerate(mixes):
            sel_m = est_mix_act and idx_m == self.accueil_index
            pill = f" {mx_item['nom']} "
            wm = cell_len(pill)
            mix_txt.append(
                pill,
                style=f"bold black on {pal['accent']}"
                if sel_m
                else f"bold {pal['primaire']} on {pal['surface_2']}",
            )
            self._accueil_zones.append((mx, y_mix, mx + wm - 1, y_mix, "mix", (idx_m, mx_item)))
            mix_txt.append(" ")
            mx += wm + 1
        if not mixes:
            mix_txt.append("Scanne ta bibliothèque [Ctrl+R] pour générer des mixes automatiques", style=pal["texte_muet"])

        p_mixes = Panel(
            mix_txt,
            title=f"[bold {pal['accent'] if est_mix_act else pal['secondaire']}]🎧 Mixes Instantanés & Ambiances[/]",
            title_align="left",
            box=box.ROUNDED,
            border_style=pal["accent"] if est_mix_act else pal["bordure"],
            height=3,
        )

        racine = Layout()
        racine.split_column(
            Layout(p_hero, size=6),
            Layout(ligne1, size=h_etag),
            Layout(ligne2),
            Layout(p_mixes, size=3),
        )
        return racine

    def rendre_mini_lecteur(self, largeur: int, hauteur: int) -> Panel:
        """Mode Mini-Barre studio ultra-compact (5 lignes) avec commandes cliquables et dégradé."""
        pal = self.palette
        p = self.piste_courante or {}
        titre_m = p.get("titre") or "Aucun morceau"
        artiste_m = p.get("artiste") or "Onde"
        en_lec = self.lecteur.fichier_actuel is not None and not self.lecteur.en_pause
        roue = ROUES_VINYLE[self.index_animation % len(ROUES_VINYLE)] if en_lec else "⏸"

        l1 = Text(no_wrap=True, overflow="ellipsis")
        spans_m: list[tuple[str, int, int]] = []
        pos_m = 0

        def _mb(nom: str | None, lbl: str, st: str):
            nonlocal pos_m
            l1.append(lbl, style=st)
            w_b = cell_len(lbl)
            if nom:
                spans_m.append((nom, pos_m, pos_m + w_b - 1))
            pos_m += w_b

        _mb("ctrl_prev", " ⏮ ", f"{pal['texte_dim']} on {pal['surface_2']}")
        _mb(None, " ", "")
        _mb("ctrl_play", " ⏸ " if en_lec else " ▶ ", f"bold black on {pal['primaire']}")
        _mb(None, " ", "")
        _mb("ctrl_next", " ⏭ ", f"{pal['texte_dim']} on {pal['surface_2']}")
        _mb(None, f"  {roue} ", f"bold {pal['succes'] if en_lec else pal['accent']}")
        _mb(None, f"{titre_m}", "bold bright_white")
        _mb(None, f" — {artiste_m}  ", pal["texte_dim"])
        est_fav = p.get("id") in self.favoris_set
        _mb("ctrl_fav", " ♥ " if est_fav else " ♡ ", "bold bright_red" if est_fav else pal["texte_muet"])
        _mb(None, " ", "")
        _mb(
            "ctrl_mute",
            "🔇" if self.lecteur.mute else f"🔊{int(self.lecteur.volume)}%",
            f"bold {pal['primaire']}",
        )
        marge_l1 = max(0, (largeur - 2 - cell_len(l1.plain)) // 2)
        for nom_b, deb_b, fin_b in spans_m:
            self._enregistrer_zone(nom_b, 2 + marge_l1 + deb_b, 2, 2 + marge_l1 + fin_b, 2)

        t_pos = self.lecteur.position + self.decalage_paroles
        with self._verrou_paroles:
            items = list(self.paroles_items)
        l2 = Text(no_wrap=True, overflow="ellipsis")
        if items:
            _idx, item, est_pause, _ = ligne_affichee(items, t_pos)
            if not est_pause and item:
                if item.mots:
                    l2.append("🎙 ", style=f"bold {pal['accent']}")
                    for m_deb, mot, m_fin in item.mots:
                        if t_pos >= m_fin:
                            l2.append(mot, style=f"bold {pal['primaire']}")
                        elif m_deb <= t_pos < m_fin:
                            l2.append(mot, style=f"bold bright_white on {pal['badge_bg']}")
                        else:
                            l2.append(mot, style=pal["texte_dim"])
                else:
                    l2.append(f"🎙 {item.texte}", style="bold bright_white")
            else:
                l2 = self.rendre_vumetre(max(12, largeur - 6))
        else:
            l2 = self.rendre_vumetre(max(12, largeur - 6))

        l3, off_deb, off_fin = self.rendre_barre_progression(max(16, largeur - 6))
        marge_l3 = max(0, (largeur - 2 - cell_len(l3.plain)) // 2)
        self._enregistrer_zone("barre_prog", 2 + marge_l3 + off_deb, 4, 2 + marge_l3 + off_fin, 4)

        corps = Layout()
        corps.split_column(
            Layout(Align.center(l1), size=1),
            Layout(Align.center(l2), size=1),
            Layout(Align.center(l3), size=1),
        )
        return Panel(
            corps,
            title=f"[bold {pal['primaire']}]◆ ONDE MINI ([I] Agrandir • [Espace] Play/Pause • [</>] Piste)[/bold {pal['primaire']}]",
            box=box.ROUNDED,
            border_style=pal["bordure_active"],
        )

    def rendre_panneau_youtube(self, largeur: int, hauteur: int) -> Panel:
        """Panneau de recherche et téléchargement YouTube direct avec barres de progression."""
        pal = self.palette
        barre_saisie = Text()
        if self.yt_saisie_active:
            barre_saisie.append(
                f" 🔎 YouTube (titre, artiste ou URL) : {self.yt_requete}█ ",
                style=f"bold black on {pal['accent']}",
            )
            barre_saisie.append(
                "  ([Entrée] Chercher/Coller URL • [Ctrl+V] Coller • [Échap] Naviguer)",
                style=pal["texte_dim"],
            )
        else:
            barre_saisie.append(
                f" 🔎 Recherche : {self.yt_requete or '(Appuie sur / pour chercher ou coller une URL YouTube)'}",
                style=f"bold {pal['primaire']}",
            )
            barre_saisie.append(
                "  •  [Entrée] Télécharger/Lire  •  [/] Chercher  •  [X] Annuler  •  [C] Nettoyer  •  [Y/Échap] Fermer",
                style=pal["texte_dim"],
            )

        taches = telechargement.taches()
        bloc_taches = Table(box=None, expand=True, show_header=False, padding=(0, 1))
        bloc_taches.add_column("État", width=16)
        bloc_taches.add_column("Titre", ratio=3)
        bloc_taches.add_column("Progression", ratio=3)

        for t in taches[:5]:
            etat = t.get("etat") or "attente"
            pct = float(t.get("pct") or 0.0)
            vit = t.get("vitesse") or ""
            eta = t.get("reste") or ""
            badges_etat = {
                "attente": ("⏳ En attente", pal["texte_dim"]),
                "telechargement": ("⬇ Télécharg.", pal["primaire"]),
                "conversion": ("⚙ Audio m4a", pal["accent"]),
                "tags": ("🏷 Tags & Cover", pal["accent"]),
                "paroles": ("🎙 Paroles LRC", pal["secondaire"]),
                "reprise": ("🔄 Reprise...", pal["accent"]),
                "fini": ("✅ Terminé", pal["succes"]),
                "erreur": ("❌ Erreur", "bold bright_red"),
                "annule": ("⏹ Annulé", pal["texte_muet"]),
            }
            lbl_e, sty_e = badges_etat.get(etat, (etat, "white"))
            prog_txt = Text()
            if etat == "erreur":
                prog_txt.append(str(t.get("erreur") or "Échec")[:48], style="bright_red")
            elif etat == "fini":
                par_info = f" • Paroles : {t.get('paroles')}" if t.get("paroles") else ""
                prog_txt.append(f"100% Ajouté{par_info}", style=f"bold {pal['succes']}")
            elif etat == "annule":
                prog_txt.append("Téléchargement annulé", style=pal["texte_muet"])
            else:
                barre_t = barre_proportionnelle(
                    pct / 100.0, 18, pal["primaire"], pal["texte_muet"]
                )
                prog_txt.append_text(barre_t)
                prog_txt.append(f" {pct:4.0f}%", style="bold bright_white")
                if vit:
                    prog_txt.append(f" • {vit}", style=pal["texte_dim"])
                if eta:
                    prog_txt.append(f" (ETA {eta})", style=pal["texte_muet"])

            bloc_taches.add_row(
                Text(lbl_e, style=f"bold {sty_e}"),
                Text(f"{t.get('titre')} — {t.get('artiste')}", style="bold white"),
                prog_txt,
            )

        table_res = Table(box=None, expand=True, show_header=True, padding=(0, 1))
        table_res.add_column(" ", width=3)
        table_res.add_column("Titre déduit", ratio=3, style="bold white")
        table_res.add_column("Artiste / Chaîne", ratio=2, style=pal["texte_dim"])
        table_res.add_column("Type", width=8, justify="center")
        table_res.add_column("Durée", width=7, justify="right")

        ids_en_cours = {t.get("id"): t.get("etat") for t in taches}
        nb_res = len(self.yt_resultats)
        h_taches = min(6, len(taches) + 2) if taches else 0
        lignes_visibles = max(4, hauteur - 8 - h_taches)
        debut = max(0, self.yt_index_selection - lignes_visibles // 2)
        fin = min(nb_res, debut + lignes_visibles)

        for i in range(debut, fin):
            r = self.yt_resultats[i]
            sel = i == self.yt_index_selection
            vid = r.get("id")
            etat_dl = ids_en_cours.get(vid)
            if etat_dl == "fini":
                cur = "✅"
            elif etat_dl in ("attente", "telechargement", "conversion", "tags", "paroles", "reprise"):
                cur = "⬇ "
            elif sel:
                cur = "❯ "
            else:
                cur = "  "

            dur_s = formater_duree(float(r.get("duree") or 0.0)) or "—"
            genre = (r.get("genre") or "audio").upper()
            table_res.add_row(
                Text(cur, style=f"bold {pal['accent']}" if sel else pal["succes"]),
                Text(r.get("titre") or r.get("titre_video") or "", style="bold bright_white" if sel else "white"),
                Text(r.get("artiste") or r.get("chaine") or "", style=pal["primaire"] if sel else pal["texte_dim"]),
                Text(genre, style=f"bold {pal['secondaire']}"),
                Text(dur_s, style=pal["texte_muet"]),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        if self.yt_en_recherche:
            centre_res: Any = Align.center(
                Text("⠋ Recherche sur YouTube via yt-dlp en cours...", style=f"bold {pal['primaire']}"),
                vertical="middle",
            )
        elif self.yt_erreur:
            centre_res = Align.center(
                Text(f"⚠ {self.yt_erreur}", style="bold bright_red"),
                vertical="middle",
            )
        elif not nb_res:
            centre_res = Align.center(
                Text(
                    "Tape un titre, un artiste ou colle une URL YouTube puis appuie sur [Entrée].\n"
                    "Le morceau sera téléchargé en haute qualité avec pochette carrée et paroles .lrc synchronisées !",
                    justify="center",
                    style=pal["texte_muet"],
                ),
                vertical="middle",
            )
        else:
            centre_res = table_res

        corps = Layout()
        if taches:
            corps.split_column(
                Layout(barre_saisie, size=1),
                Layout(
                    Panel(
                        bloc_taches,
                        title=f"[bold {pal['succes']}]⬇ Téléchargements ({len(taches)}) • [X] Annuler • [C] Effacer finis[/bold {pal['succes']}]",
                        box=box.ROUNDED,
                        border_style=pal["succes"],
                        style=f"on {pal['surface_bg']}",
                    ),
                    size=min(7, len(taches) + 2),
                ),
                Layout(centre_res),
            )
        else:
            corps.split_column(
                Layout(barre_saisie, size=1),
                Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
                Layout(centre_res),
            )

        return Panel(
            corps,
            title=f"[bold {pal['accent']}]⬇ Studio YouTube Direct (Qualité Max + Pochette + Paroles LRC)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_statistiques(self, largeur: int, hauteur: int) -> Panel:
        """Tableau de bord analytique Studio (KPIs, activité 24h, formats audio, Top 10 jouable)."""
        pal = self.palette
        st = self.stats_donnees or {}
        ecoutes_tot = int(st.get("ecoutes") or 0)
        temps_tot = float(st.get("temps") or 0.0)
        ecoutes_mois = int(st.get("ecoutes_mois") or 0)
        temps_mois = float(st.get("temps_mois") or 0.0)

        def _fmt_temps(sec: float) -> str:
            h = int(sec) // 3600
            m = (int(sec) % 3600) // 60
            return f"{h}h {m:02d}m" if h > 0 else f"{m} min"

        duree_biblio = sum(float(p.get("duree") or 0.0) for p in self.pistes)
        nb_lossless = sum(
            1
            for p in self.pistes
            if (p.get("format") or "").lower() in ("flac", "alac", "wav", "aiff", "dsf")
        )
        couv = {}
        with contextlib.suppress(Exception):
            couv = paroles.couverture()

        resume = Text(justify="center")
        resume.append(" 📅 30 jours : ", style=pal["texte_dim"])
        resume.append(f"{ecoutes_mois} écoutes", style=f"bold {pal['primaire']}")
        resume.append(f" ({_fmt_temps(temps_mois)})", style=f"bold {pal['succes']}")
        resume.append("   •   🏆 Total : ", style=pal["texte_dim"])
        resume.append(f"{ecoutes_tot} écoutes", style=f"bold {pal['accent']}")
        resume.append(f" ({_fmt_temps(temps_tot)})\n", style=f"bold {pal['secondaire']}")
        resume.append(
            f" 📚 {len(self.pistes)} titres ({_fmt_temps(duree_biblio)})"
            f"  •  ♥ {len(self.favoris_set)} favoris"
            f"  •  📂 {len(self.playlists_liste)} playlists"
            f"  •  💎 {nb_lossless} Hi-Res/FLAC"
            f"  •  🎙 {couv.get('avec', 0)}/{couv.get('total', len(self.pistes))} paroles",
            style=pal["texte_dim"],
        )

        # Bandeau analytique : Activité par heure (24h) + Répartition des formats
        heures = self.stats_heures if len(self.stats_heures) == 24 else [0] * 24
        max_h = max(heures) if any(heures) else 1
        rgb_p = _hex_vers_rgb(pal["primaire"], (192, 132, 252))
        rgb_a = _hex_vers_rgb(pal["accent"], (244, 114, 182))
        bande_h = Text(justify="center")
        bande_h.append(" ⏰ Rythme 24h  00h ", style=pal["texte_dim"])
        for hr, cnt in enumerate(heures):
            idx_c = int((cnt / max_h) * (len(CHARS_VUMETRE) - 1)) if cnt else 1
            ch = CHARS_VUMETRE[max(1, idx_c)] if cnt else "▁"
            c_h = (
                _rgb_vers_hex(*_melanger_rgb(rgb_p, rgb_a, cnt / max_h))
                if cnt
                else pal["bordure"]
            )
            bande_h.append(ch, style=f"bold {c_h}" if cnt else c_h)
            if hr in (5, 11, 17):
                bande_h.append("·", style=pal["texte_muet"])
        bande_h.append(" 23h", style=pal["texte_dim"])

        # Formats dominants
        compt_fmt: dict[str, int] = {}
        for p in self.pistes:
            fm = (p.get("format") or "autre").upper()
            compt_fmt[fm] = compt_fmt.get(fm, 0) + 1
        top_fmts = sorted(compt_fmt.items(), key=lambda kv: -kv[1])[:4]
        if top_fmts:
            bande_h.append("    │    🎵 Formats : ", style=pal["texte_dim"])
            tot_p = max(1, len(self.pistes))
            for idx_f, (fm, nb_f) in enumerate(top_fmts):
                if idx_f:
                    bande_h.append("  ", style=pal["texte_muet"])
                pct_f = round(nb_f / tot_p * 100)
                c_f = pal["accent"] if fm in ("FLAC", "ALAC", "WAV") else pal["secondaire"]
                bande_h.append(f"{fm} ", style=f"bold {c_f}")
                bande_h.append(f"{pct_f}%", style=pal["texte_dim"])

        pistes_map = {p["id"]: p for p in self.pistes if p.get("id")}
        top_titres = st.get("top_titres") or []
        max_t = max((int(r.get("n") or 0) for r in top_titres), default=1) or 1
        if top_titres:
            self.stats_index = max(0, min(self.stats_index, min(10, len(top_titres)) - 1))

        t_titres = Table(
            title=f"[bold {pal['primaire']}]🔥 Top 10 Titres ([↑/↓] Choisir • [Entrée] Jouer)[/bold {pal['primaire']}]",
            box=box.SIMPLE,
            expand=True,
        )
        t_titres.add_column("#", width=4, justify="right", style=pal["accent"])
        t_titres.add_column("Titre", ratio=3, style="bold white", no_wrap=True, overflow="ellipsis")
        t_titres.add_column("Artiste", ratio=2, style=pal["texte_dim"], no_wrap=True, overflow="ellipsis")
        t_titres.add_column("Part", width=11)
        t_titres.add_column("Nb", width=6, justify="right", style=f"bold {pal['succes']}")

        for i, r in enumerate(top_titres[:10], 1):
            sel = (i - 1) == self.stats_index
            p_info = pistes_map.get(r.get("id"), {})
            nb_e = int(r.get("n") or 0)
            t_titres.add_row(
                f"❯{i}" if sel else str(i),
                p_info.get("titre") or f"Piste #{r.get('id')}",
                p_info.get("artiste") or "Inconnu",
                barre_degrade(nb_e / max_t, 10, pal["primaire"], pal["secondaire"], pal["bordure"]),
                f"{nb_e}×",
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        top_artistes = st.get("top_artistes") or []
        max_a = max((int(r.get("n") or 0) for r in top_artistes), default=1) or 1

        t_artistes = Table(
            title=f"[bold {pal['accent']}]🎤 Top 10 Artistes[/bold {pal['accent']}]",
            box=box.SIMPLE,
            expand=True,
        )
        t_artistes.add_column("#", width=3, justify="right", style=pal["primaire"])
        t_artistes.add_column("Artiste", ratio=3, style="bold white", no_wrap=True, overflow="ellipsis")
        t_artistes.add_column("Part", width=11)
        t_artistes.add_column("Nb", width=6, justify="right", style=f"bold {pal['accent']}")
        t_artistes.add_column("Temps", width=8, justify="right", style=pal["texte_dim"])

        for i, r in enumerate(top_artistes[:10], 1):
            nb_a = int(r.get("n") or 0)
            t_artistes.add_row(
                str(i),
                r.get("artiste") or "Artiste inconnu",
                barre_degrade(nb_a / max_a, 10, pal["secondaire"], pal["accent"], pal["bordure"]),
                f"{nb_a}×",
                _fmt_temps(float(r.get("s") or 0.0)),
            )

        colonnes = Layout()
        colonnes.split_row(Layout(t_titres), Layout(t_artistes))

        corps = Layout()
        corps.split_column(
            Layout(Align.center(resume), size=2),
            Layout(Align.center(bande_h), size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(colonnes),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]📊 Statistiques d'Écoute Onde Studio ([Maj+S] ou [Échap] pour fermer)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_modal_playlist(self, largeur: int, hauteur: int) -> Panel:
        """Fenêtre modale pour créer [N], renommer [F2] ou ajouter [P] à une playlist."""
        pal = self.palette
        if self.modal_playlist_mode in ("creer", "renommer"):
            est_ren = self.modal_playlist_mode == "renommer"
            txt = Text(justify="center")
            if est_ren:
                txt.append(
                    f"\n✏ Renommer la playlist « {self.titre_cible_playlist} »\n\n",
                    style=f"bold {pal['primaire']}",
                )
            else:
                txt.append(
                    "\n✨ Créer une nouvelle playlist dans Onde\n\n",
                    style=f"bold {pal['primaire']}",
                )
            txt.append(
                f"  Nom : {self.nom_nouvelle_playlist}█  \n\n",
                style=f"bold black on {pal['accent']}",
            )
            if not est_ren and self.pistes_cibles_playlist:
                txt.append(
                    f"({len(self.pistes_cibles_playlist)} titre(s) sélectionné(s) y seront ajoutés)\n\n",
                    style=pal["succes"],
                )
            txt.append(
                "[Entrée] Enregistrer   •   [Ctrl+V] Coller   •   [Échap] Annuler",
                style=pal["texte_dim"],
            )
            return Panel(
                Align.center(txt, vertical="middle"),
                title=f"[bold {pal['accent']}]{'✏ Renommer la Playlist' if est_ren else '➕ Nouvelle Playlist'}[/bold {pal['accent']}]",
                box=box.ROUNDED,
                border_style=pal["accent"],
                style=f"on {pal['surface_bg']}",
            )

        table = Table(box=None, expand=True, show_header=False, padding=(0, 1))
        table.add_column("Sel", width=3)
        table.add_column("Playlist", ratio=3)
        table.add_column("Titres", width=12, justify="right")

        for i, pl in enumerate(self.playlists_liste):
            sel = i == self.index_playlist_cible
            nb_t = len(pl.get("pistes") or [])
            table.add_row(
                Text("❯ " if sel else "  ", style=f"bold {pal['accent']}"),
                Text(f"♪ {pl.get('nom')}", style="bold bright_white" if sel else "white"),
                Text(f"{nb_t} titre{'s' if nb_t != 1 else ''}", style=pal["primaire"] if sel else pal["texte_muet"]),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        entete = Text()
        entete.append(f" Ajouter : {self.titre_cible_playlist}\n", style="bold bright_white")
        entete.append(
            " [↑/↓] Choisir  •  [Entrée] Ajouter  •  [N] Nouvelle playlist  •  [Échap] Annuler",
            style=pal["texte_dim"],
        )
        corps = Layout()
        corps.split_column(
            Layout(entete, size=2),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(table),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]📂 Ajouter à une Playlist ({len(self.playlists_liste)} playlists)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_galerie_photos(self, largeur: int, hauteur: int) -> Panel:
        """Sélecteur interactif de photos de fond avec prévisualisation en direct."""
        pal = self.palette
        table = Table(box=None, expand=True, show_header=False, padding=(0, 1))
        table.add_column("Sel", width=3)
        table.add_column("Photo", ratio=3)
        table.add_column("Chemin", ratio=4)

        nb = len(self.photos_disponibles)
        lignes_visibles = max(5, hauteur - 8)
        debut = max(0, self.index_galerie - lignes_visibles // 2)
        fin = min(nb, debut + lignes_visibles)

        for i in range(debut, fin):
            label, ch = self.photos_disponibles[i]
            sel = i == self.index_galerie
            act = ch == self.fond.chemin_photo_perso
            cur = "❯ " if sel else ("✓ " if act else "  ")
            table.add_row(
                Text(cur, style=f"bold {pal['accent']}" if sel else pal["succes"]),
                Text(label, style="bold bright_white" if sel else "white"),
                Text(ch, style=pal["texte_dim"] if sel else pal["texte_muet"]),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        info = Text()
        info.append(
            f" Fond : {self.fond.mode_fond.upper()} • Moteur : {self.fond.mode_rendu.upper()} • "
            f"Luminosité : {self.fond.label_luminosite} • Thème : {THEMES[self.theme_code]['nom']}\n",
            style=f"bold {pal['primaire']}",
        )
        info.append(
            " [↑/↓] Prévisualiser en direct  •  [Entrée] Appliquer  •  [B] Mode  •  [O] Luminosité  •  [M] Moteur  •  [T] Thème  •  [G/Échap] Fermer",
            style=pal["texte_dim"],
        )

        corps = Layout()
        corps.split_column(
            Layout(info, size=2),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(
                table
                if nb
                else Align.center(
                    Text(
                        "Aucune image trouvée dans ~/Images ou ~/.local/share/onde/pochettes",
                        style=pal["texte_muet"],
                    )
                )
            ),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]🖼 Galerie de Fonds d'Écran ({nb} photos disponibles)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_eq_10_bandes(self, largeur: int, hauteur: int) -> Panel:
        """Égaliseur graphique 10 bandes TrueColor (-12/+12 dB), profils persos [7-9] & Effets DSP [F]."""
        pal = self.palette
        nom_dsp = next((n for k, n, _ in EFFETS_DSP if k == self.effet_dsp), "Pur")
        info = Text(justify="center")
        if self.eq_saisie_nom:
            info.append(
                f" 💾 Nom du profil personnel : {self.eq_nom_tampon}█ ",
                style=f"bold black on {pal['accent']}",
            )
            info.append("  ([Entrée] Enregistrer • [Échap] Annuler)", style=pal["texte_dim"])
        else:
            statut = (
                "10 BANDES PERSO"
                if self.eq_perso_actif
                else PROFILS_EQ[self.eq_index][0]
            )
            info.append(" 🎛 ", style=pal["primaire"])
            info.append(statut, style=f"bold {pal['succes'] if self.eq_perso_actif else pal['primaire']}")
            info.append("  •  ✨ DSP : ", style=pal["texte_dim"])
            info.append(nom_dsp, style=f"bold {pal['accent'] if self.effet_dsp != 'off' else pal['texte_dim']}")
            info.append(
                "   •  [←/→] Bande  [↑/↓] ±1dB  [F] DSP  [S] Sauver  [0] Plat  [Échap] Fermer",
                style=pal["texte_dim"],
            )

        # Barre de préréglages usine [1..6] + persos [7..9] + bouton DSP cliquables sur y = 6
        bar_pre = Text(no_wrap=True, overflow="crop")
        cur_x = 3
        for idx_p, (nom_p, _) in enumerate(PROFILS_EQ):
            actif_p = not self.eq_perso_actif and self.eq_index == idx_p
            pill = f" [{idx_p + 1}] {nom_p.split(' ')[0]} "
            w_pill = cell_len(pill)
            self._enregistrer_zone(f"eq_preset:{idx_p}", cur_x, 6, cur_x + w_pill - 1, 6)
            bar_pre.append(
                pill,
                style=f"bold black on {pal['accent']}"
                if actif_p
                else f"{pal['texte_dim']} on {pal['surface_2']}",
            )
            bar_pre.append(" ")
            cur_x += w_pill + 1

        for idx_c, pr in enumerate(self.eq_profils_perso[:3]):
            touche_c = 7 + idx_c
            pill_c = f" [{touche_c}] ★{pr.get('nom', 'Perso')[:10]} "
            wc = cell_len(pill_c)
            self._enregistrer_zone(f"eq_custom:{idx_c}", cur_x, 6, cur_x + wc - 1, 6)
            bar_pre.append(
                pill_c,
                style=f"bold {pal['secondaire']} on {pal['surface_2']}",
            )
            bar_pre.append(" ")
            cur_x += wc + 1

        pill_dsp = f" [F] ✨{nom_dsp.split(' ')[0]} "
        wd = cell_len(pill_dsp)
        self._enregistrer_zone("eq_dsp", cur_x, 6, cur_x + wd - 1, 6)
        bar_pre.append(
            pill_dsp,
            style=f"bold black on {pal['secondaire']}"
            if self.effet_dsp != "off"
            else f"{pal['texte_muet']} on {pal['surface_2']}",
        )

        self._enregistrer_zone("eq_tableau", 2, 8, max(3, largeur - 1), max(9, hauteur - 5))

        table = Table(box=None, expand=True, show_header=False, padding=(0, 1))
        table.add_column("Échelle", width=8, justify="right", style=pal["texte_muet"])
        for _idx, (_, lbl) in enumerate(FREQS_EQ_10):
            table.add_column(lbl, justify="center", ratio=1)

        rgb_ok = _hex_vers_rgb(pal["succes"], (52, 211, 153))
        rgb_p = _hex_vers_rgb(pal["primaire"], (192, 132, 252))
        rgb_a = _hex_vers_rgb(pal["accent"], (244, 114, 182))
        rgb_s = _hex_vers_rgb(pal["secondaire"], (34, 211, 238))

        niveaux_db = [12, 9, 6, 3, 0, -3, -6, -9, -12]
        for db_ligne in niveaux_db:
            cells: list[Any] = [
                Text(
                    f"{db_ligne:+3d} dB",
                    style=pal["texte_muet"] if db_ligne != 0 else "bold bright_white",
                )
            ]
            for b_idx, gain in enumerate(self.eq_bandes):
                sel = b_idx == self.eq_bande_selection
                dist = abs(gain - db_ligne)
                if dist <= 1.5:
                    ch = "━━◉━━" if sel else "──●──"
                    st = f"bold {pal['accent']}" if sel else f"bold {pal['primaire']}"
                elif db_ligne > 0 and gain >= db_ligne:
                    ch = "  █  "
                    t_g = db_ligne / 12.0
                    c_g = _rgb_vers_hex(*_melanger_rgb(rgb_ok, rgb_a, t_g))
                    st = f"bold {c_g}" if sel else c_g
                elif db_ligne < 0 and gain <= db_ligne:
                    ch = "  █  "
                    t_g = abs(db_ligne) / 12.0
                    c_g = _rgb_vers_hex(*_melanger_rgb(rgb_s, rgb_p, t_g))
                    st = f"bold {c_g}" if sel else c_g
                elif db_ligne == 0:
                    ch = "─────"
                    st = pal["bordure"]
                else:
                    ch = "  ┆  "
                    st = pal["bordure"]
                cells.append(Text(ch, style=st))
            table.add_row(*cells)

        row_vals: list[Any] = [Text("Gain", style=pal["texte_dim"])]
        row_freqs: list[Any] = [Text("Bande", style=pal["texte_dim"])]
        for b_idx, ((_, lbl), gain) in enumerate(zip(FREQS_EQ_10, self.eq_bandes, strict=False)):
            sel = b_idx == self.eq_bande_selection
            row_vals.append(
                Text(
                    f"{gain:+.1f}dB",
                    style=f"bold black on {pal['accent']}" if sel else f"bold {pal['primaire']}",
                )
            )
            row_freqs.append(
                Text(
                    f"▲ {lbl}" if sel else lbl,
                    style=f"bold {pal['accent']}" if sel else pal["texte_dim"],
                )
            )
        table.add_row(*row_vals)
        table.add_row(*row_freqs)

        corps = Layout()
        corps.split_column(
            Layout(info, size=1),
            Layout(bar_pre, size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(Align.center(table, vertical="middle")),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]🎚 Égaliseur Studio 10 Bandes & DSP ([Maj+E] ou [Échap] pour fermer)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_recherche_paroles(self, largeur: int, hauteur: int) -> Panel:
        """Recherche plein-texte dans les paroles de toute la bibliothèque avec saut à la ligne exacte."""
        pal = self.palette
        avec = self.paroles_couverture.get("avec", 0)
        tot = self.paroles_couverture.get("total", len(self.pistes))

        barre = Text()
        if self.paroles_recherche_saisie:
            barre.append(
                f" 🎙 Chercher une phrase dans les paroles : {self.paroles_recherche_requete}█ ",
                style=f"bold black on {pal['accent']}",
            )
            barre.append("  ([Entrée] Valider • [Ctrl+V] Coller • [Échap] Naviguer)", style=pal["texte_dim"])
        else:
            barre.append(
                f" 🎙 Phrase : {self.paroles_recherche_requete or '(Appuie sur / pour taper des paroles)'}",
                style=f"bold {pal['primaire']}",
            )
            barre.append(
                "  •  [Entrée] Jouer au passage  •  [/] Chercher  •  [Maj+K] Indexer tout  •  [Échap] Fermer",
                style=pal["texte_dim"],
            )

        etat_tout = paroles.ETAT_TOUT
        info_couv = Text()
        info_couv.append(
            f" 📚 Couverture : {avec}/{tot} titres indexés avec paroles",
            style=pal["succes"] if avec > 0 else pal["texte_dim"],
        )
        if etat_tout.get("en_cours"):
            info_couv.append(
                f"   •   ⠋ Indexation : {etat_tout.get('fait', 0)}/{etat_tout.get('total', 0)} ({etat_tout.get('trouvees', 0)} trouvées)",
                style=f"bold {pal['accent']}",
            )

        table = Table(box=None, expand=True, show_header=True, padding=(0, 1))
        table.add_column(" ", width=3)
        table.add_column("Titre & Artiste", ratio=2)
        table.add_column("Passage trouvé dans les paroles", ratio=3)
        table.add_column("Repère", width=8, justify="right")

        pistes_map = {p["id"]: p for p in self.pistes if p.get("id")}
        nb_res = len(self.paroles_recherche_resultats)
        lignes_vis = max(4, hauteur - 8)
        debut = max(0, self.paroles_recherche_index - lignes_vis // 2)
        fin = min(nb_res, debut + lignes_vis)

        for i in range(debut, fin):
            r = self.paroles_recherche_resultats[i]
            sel = i == self.paroles_recherche_index
            p = pistes_map.get(r.get("id"), {})
            t_sec = r.get("t")
            t_str = (
                f"{int(t_sec)//60:02d}:{int(t_sec)%60:02d}"
                if t_sec is not None
                else "Texte"
            )
            table.add_row(
                Text("❯ " if sel else "  ", style=f"bold {pal['accent']}"),
                Text(
                    f"{p.get('titre', 'Inconnu')} — {p.get('artiste', '')}",
                    style="bold bright_white" if sel else "white",
                ),
                Text(f"« {r.get('ligne', '')} »", style=f"bold {pal['accent']}" if sel else pal["primaire"]),
                Text(t_str, style=pal["succes"] if t_sec is not None else pal["texte_muet"]),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        corps = Layout()
        corps.split_column(
            Layout(barre, size=1),
            Layout(info_couv, size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(
                table
                if nb_res
                else Align.center(
                    Text(
                        "Tape quelques mots d'un refrain ou d'un couplet (au moins 3 caractères).\n"
                        "Appuie sur [Entrée] sur un résultat pour lancer le titre directement au bon moment !",
                        justify="center",
                        style=pal["texte_muet"],
                    ),
                    vertical="middle",
                )
            ),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]🔎 Recherche Globale dans les Paroles ({nb_res} correspondances)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_proprietes(self, largeur: int, hauteur: int) -> Panel:
        """Fiche technique complète d'un morceau (codec, débit, résolution, EBU R128, historique, fichier)."""
        pal = self.palette
        pr = self.proprietes_donnees or {}
        table = Table(box=box.SIMPLE, expand=True, show_header=False, padding=(0, 2))
        table.add_column("Propriété", style=f"bold {pal['primaire']}", width=24)
        table.add_column("Valeur", style="bold white")

        duree = float(pr.get("duree") or 0.0)
        taille_mo = float(pr.get("taille") or 0) / (1024 * 1024)
        freq = pr.get("frequence")
        bits = pr.get("bits")
        canaux = pr.get("canaux")
        niv = pr.get("niveau")
        niv_str = (
            f"{float(niv['gain']):+.2f} dB (source : {niv.get('source', 'EBU R128')})"
            if isinstance(niv, dict) and niv.get("gain") is not None
            else "Non mesuré"
        )
        lignes_p = [
            ("🎵 Titre", str(pr.get("titre") or "—")),
            ("🎤 Artiste", str(pr.get("artiste") or "—")),
            ("💿 Album", f"{pr.get('album') or '—'} ({pr.get('annee') or 'Année inconnue'})"),
            ("🏷 Genre / Piste #", f"{pr.get('genre') or '—'}  •  N° {pr.get('numero') or '—'}"),
            ("⏱ Durée", f"{formater_duree(duree)} ({duree:.1f} secondes)"),
            ("🎛 Codec & Format", f"{pr.get('codec') or (pr.get('format') or '').upper()}  •  Encodeur : {pr.get('encodeur') or 'Standard'}"),
            ("📡 Débit binaire", f"{pr.get('debit') or '—'} kbps ({pr.get('mode_debit') or 'auto'})"),
            ("🔬 Résolution Audio", f"{f'{freq/1000:.1f} kHz' if freq else '—'}  •  {f'{bits}-bit' if bits else '—'}  •  {f'{canaux} canaux (Stéréo)' if canaux == 2 else (f'{canaux} ch' if canaux else '—')}"),
            ("⚖ Normalisation R128", niv_str),
            ("🎙 Paroles", f"{pr.get('paroles') or 'Aucune'} ({pr.get('paroles_source') or '—'})"),
            ("📊 Écoutes & Favori", f"{pr.get('ecoutes', 0)} écoute(s)  •  {'♥ Favori' if pr.get('favori') else 'Non favori'}"),
            ("📂 Playlists", ", ".join(pr.get("playlists") or []) or "Aucune playlist"),
            ("💾 Fichier Disque", f"{pr.get('chemin') or '—'} ({taille_mo:.2f} Mo)"),
        ]
        for k, v in lignes_p:
            table.add_row(k, v)

        return Panel(
            Align.center(table, vertical="middle"),
            title=f"[bold {pal['accent']}]🔬 Inspecteur Audio ([Maj+T] Tags • [Ctrl+L] Studio Paroles • [Échap] Fermer)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_editeur_tags(self, largeur: int, hauteur: int) -> Panel:
        """Éditeur de métadonnées ID3/MP4/FLAC/Opus et rapprochement automatique iTunes avec pochette HD."""
        pal = self.palette
        cles_labels = [
            ("titre", "🎵 Titre"),
            ("artiste", "🎤 Artiste"),
            ("album", "💿 Album"),
            ("artiste_album", "👥 Artiste de l'album"),
            ("annee", "📅 Année (4 chiffres)"),
            ("genre", "🏷 Genre"),
            ("numero", "🔢 Numéro de piste"),
        ]

        entete = Text()
        if self.tags_mode == "saisie":
            _cle_act, lbl_act = cles_labels[self.tags_champ_index]
            entete.append(
                f" ✏ Édition de {lbl_act} : {self.tags_saisie_Tampon}█ ",
                style=f"bold black on {pal['accent']}",
            )
            entete.append("  ([Entrée] Valider • [Ctrl+V] Coller • [Échap] Annuler)", style=pal["texte_dim"])
        elif self.tags_mode == "itunes":
            entete.append(
                " 🍎 Sélectionne la correspondance iTunes puis appuie sur [Entrée] (tags + pochette 600×600 HD)  •  [Échap] Retour",
                style=f"bold {pal['accent']}",
            )
        elif self.tags_mode == "pochette":
            entete.append(
                " 🖼 Choisis une image locale (recadrée 600×600 carré) puis [Entrée]  •  [Échap] Retour",
                style=f"bold {pal['accent']}",
            )
        else:
            entete.append(
                " [↑/↓] Champ • [Entrée] Éditer • [I] iTunes HD • [C] Pochette locale • [S] Enregistrer • [Échap] Fermer",
                style=pal["texte_dim"],
            )

        if self.tags_erreur:
            entete.append(f"\n ⚠ {self.tags_erreur}", style="bold bright_red")
        elif self.tags_en_recherche:
            entete.append("\n ⠋ Interrogation de l'API iTunes...", style=f"bold {pal['primaire']}")
        elif self.tags_itunes_choisi:
            entete.append(
                f"\n ✅ Correspondance iTunes #{self.tags_itunes_choisi} prête (tags + pochette HD) — appuie sur [S] pour écrire !",
                style=f"bold {pal['succes']}",
            )
        elif self.tags_pochette_locale:
            entete.append(
                f"\n 🖼 Pochette locale prête : {Path(self.tags_pochette_locale).name} — appuie sur [S] pour intégrer !",
                style=f"bold {pal['succes']}",
            )

        if self.tags_mode == "pochette":
            t_ph = Table(box=None, expand=True, show_header=True, padding=(0, 1))
            t_ph.add_column(" ", width=3)
            t_ph.add_column("Image locale", ratio=3)
            t_ph.add_column("Chemin", ratio=4)
            nb_ph = len(self.photos_disponibles)
            if nb_ph:
                self.tags_galerie_index = max(0, min(self.tags_galerie_index, nb_ph - 1))
                vis_p = max(5, hauteur - 8)
                deb_p = max(0, self.tags_galerie_index - vis_p // 2)
                fin_p = min(nb_ph, deb_p + vis_p)
                for idx_ph in range(deb_p, fin_p):
                    lbl_p, ch_p = self.photos_disponibles[idx_ph]
                    sel_p = idx_ph == self.tags_galerie_index
                    t_ph.add_row(
                        Text("❯ " if sel_p else "  ", style=f"bold {pal['accent']}"),
                        Text(lbl_p, style="bold bright_white" if sel_p else "white"),
                        Text(ch_p, style=pal["texte_dim"] if sel_p else pal["texte_muet"]),
                        style=f"on {pal['selection_bg']}" if sel_p else None,
                    )
                centre: Any = t_ph
            else:
                centre = Align.center(
                    Text("Aucune image trouvée dans ~/Images ou les pochettes Onde.", style=pal["texte_muet"]),
                    vertical="middle",
                )
        elif self.tags_mode == "itunes" and self.tags_itunes_resultats:
            t_it = Table(box=None, expand=True, show_header=True, padding=(0, 1))
            t_it.add_column(" ", width=3)
            t_it.add_column("Score", width=7, justify="right")
            t_it.add_column("Titre iTunes", ratio=3)
            t_it.add_column("Artiste", ratio=2)
            t_it.add_column("Album (Année)", ratio=3)
            t_it.add_column("Durée", width=7, justify="right")

            for idx, r in enumerate(self.tags_itunes_resultats[:12]):
                sel = idx == self.tags_itunes_index
                dur = float(r.get("duree") or 0)
                sc = r.get("score") or 0
                t_it.add_row(
                    Text("❯ " if sel else "  ", style=f"bold {pal['accent']}"),
                    Text(f"{sc}%", style=f"bold {pal['succes'] if sc >= 80 else pal['accent']}"),
                    Text(str(r.get("titre") or ""), style="bold bright_white" if sel else "white"),
                    Text(str(r.get("artiste") or ""), style=pal["primaire"] if sel else pal["texte_dim"]),
                    Text(f"{r.get('album') or ''} ({r.get('annee') or '—'})", style=pal["texte_dim"]),
                    Text(formater_duree(dur), style=pal["texte_muet"]),
                    style=f"on {pal['selection_bg']}" if sel else None,
                )
            centre: Any = t_it
        else:
            t_ch = Table(box=box.SIMPLE, expand=True, show_header=True, padding=(0, 2))
            t_ch.add_column(" ", width=3)
            t_ch.add_column("Champ ID3 / MP4 / FLAC", width=26, style=f"bold {pal['primaire']}")
            t_ch.add_column("Valeur actuelle", ratio=1)

            for idx, (cle, lbl) in enumerate(cles_labels):
                sel = idx == self.tags_champ_index and self.tags_mode != "itunes"
                val = self.tags_champs.get(cle, "")
                t_ch.add_row(
                    Text("❯ " if sel else "  ", style=f"bold {pal['accent']}"),
                    lbl,
                    Text(val or "—", style="bold bright_white" if sel else "white"),
                    style=f"on {pal['selection_bg']}" if sel else None,
                )
            centre = t_ch

        corps = Layout()
        corps.split_column(
            Layout(entete, size=2),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(centre),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]🏷 Éditeur de Tags Atomique & Lookup iTunes (Piste #{self.tags_piste_id})[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def _commandes_palette(self) -> list[tuple[str, str, str, Any]]:
        """Catalogue complet des commandes rapides filtrées pour la Palette [F1]/[Ctrl+P]."""
        toutes: list[tuple[str, str, str, Any]] = [
            ("F3", "✦ Vue Accueil & Découverte", "Tableau de bord éditorial, incontournables & mixes", lambda: (setattr(self, "mode_vue", "accueil"), self.sauvegarder_etat_cli())),
            ("Espace", "▶ Lecture / Pause", "Basculer lecture/pause", self.lecteur.basculer_pause),
            ("> / .", "⏭ Piste suivante", "Passer au titre suivant", self.piste_suivante),
            ("<", "⏮ Piste précédente", "Revenir au titre précédent", self.piste_precedente),
            ("Ctrl+X", "📻 Radio de ce titre (Smart Mix)", "Générer 25 morceaux similaires (artiste/genre/année)", self.lancer_radio_piste),
            ("Alt+Entrée", "📀 Tout lire (collection)", "Charger la liste courante en lecture", lambda: self.jouer_collection(False)),
            ("Ctrl+A", "⏭ Lire juste après", "Insérer la sélection en tête de file", self.jouer_selection_ensuite),
            ("A", "➕ Ajouter à la file", "Ajouter la sélection en queue de file", self.ajouter_selection_file),
            ("F", "♥ Basculer favori / radio", "Aimer le titre ou la station sélectionnée", self.basculer_favori_selection),
            ("# / F9", "🔇 Muet / Son", "Couper ou rétablir le son mpv", self.basculer_muet),
            ("!", "🎧 Auto-DJ intelligent", "Enchaîner par artiste et genre en fin de file", lambda: (setattr(self, "auto_dj", not self.auto_dj), self.sauvegarder_etat_cli(), self.notifier(f"🎧 Auto-DJ : {'Activé' if self.auto_dj else 'Désactivé'}"))),
            ("S", "🔀 Mode Aléatoire", "Activer ou couper le shuffle", lambda: (setattr(self, "mode_aleatoire", not self.mode_aleatoire), self.sauvegarder_etat_cli(), self.notifier(f"🔀 Aléatoire : {'Oui' if self.mode_aleatoire else 'Non'}"))),
            ("R", "🔁 Cycle Répétition", "Non → Tout → Un seul titre", lambda: (setattr(self, "mode_repetition", ["non", "tout", "un"][(["non", "tout", "un"].index(self.mode_repetition) + 1) % 3]), self.sauvegarder_etat_cli(), self.notifier(f"🔁 Répétition : {self.mode_repetition.upper()}"))),
            ("Ctrl+L / F4", "🎙 Studio Paroles & Recalage", "Chercher LRCLIB/NetEase ou recaler sur la voix", self.ouvrir_studio_paroles),
            (": / Ctrl+K", "🔎 Recherche plein-texte paroles", "Sauter à une phrase chantée de la bibliothèque", self.ouvrir_recherche_paroles),
            ("Shift+K", "🔄 Relancer paroles du titre", "Forcer la mise à jour des paroles actuelles", lambda: self.piste_courante and self.piste_courante.get("id") and self.charger_paroles_async(int(self.piste_courante["id"]), forcer=True)),
            ("—", "⏱ Horodatages dans les paroles", "Afficher ou masquer [00:00] pour un mode cinéma pur", lambda: (setattr(self, "afficher_timestamps_paroles", not self.afficher_timestamps_paroles), self.sauvegarder_etat_cli(), self.notifier(f"⏱ Horodatage paroles : {'Affiché' if self.afficher_timestamps_paroles else 'Masqué'}"))),
            ("Maj+E", "🎚 Égaliseur Studio 10 Bandes", "10 bandes (-12/+12 dB), profils persos & DSP", self.ouvrir_eq_10_bandes),
            ("E", "🎛 Préréglages Égaliseur", "Cycler les 6 profils sonores", self.cycler_egaliseur),
            ("F11", "✨ Effet DSP Studio", "Pur • Stéréo Large • Karaoké −Voix • Hall Reverb • Nuit", self.cycler_effet_dsp),
            ("F5", "🌊 Changer le Visualiseur (7)", "Spectre • Horizon • Onde • Braille • Aurore • Barres", self.cycler_visualiseur),
            ("T", "🎨 Changer le Thème (12)", "Auto, Liquid, Tokyo, Sunset, Obsidienne, Catppuccin…", self.cycler_theme),
            ("B / M / O", "🌌 Fond d'écran Liquid Glass", "Pochette / Photo / Aurore 4-blobs / Verre", self.cycler_mode_fond),
            ("G", "🖼 Galerie des Fonds d'écran", "Prévisualiser les photos locales en direct", lambda: (self.scanner_photos_disponibles(), setattr(self, "galerie_ouverte", True))),
            ("F6 / Ctrl+O", "⇅ Trier la liste courante", "Artiste • Titre • Album • Ajouts • Écoutes • Qualité", self.cycler_tri),
            ("—", "🏷 Explorer par Genres", "Ouvrir l'onglet Genres musicaux", lambda: (setattr(self, "mode_onglet", "genres"), setattr(self, "mode_vue", "scinde"), self.filtrer_pistes())),
            ("Ctrl+G / F7", "⚙ Réglages & Sortie Audio", "Périphérique audio, DSP, reprise, R128, scan, sauvegarde", self.ouvrir_reglages),
            ("Ctrl+D / F8", "👯 Fusionner les doublons", "Détecter et réunir favoris, écoutes et playlists", self.ouvrir_doublons),
            ("Y", "⬇ Téléchargement YouTube", "Chercher / coller une URL YouTube avec tags + LRC", lambda: (self._fermer_toutes_modales(), setattr(self, "yt_ouvert", True), setattr(self, "yt_saisie_active", not bool(self.yt_resultats)))),
            ("Maj+I", "🔬 Propriétés Audio & Codec", "Résolution, débit, encodeur, EBU R128, chemin", self.ouvrir_proprietes_selection),
            ("Maj+T", "🏷 Éditeur de Tags & Pochette HD", "Corriger métadonnées, iTunes HD ou pochette locale", self.ouvrir_editeur_tags),
            ("N / F2 / P", "📂 Créer / Renommer Playlist", "Créer une nouvelle playlist ou renommer l'actuelle", self.ouvrir_creation_playlist),
            ("Ctrl+U", "📤 Exporter Playlist en .m3u8", "Exporter la playlist sélectionnée dans ~/Musique", self.exporter_playlist_m3u),
            ("U / D", "⚖ Normalisation EBU R128 / Fondu", "Basculer R128 −18 LUFS ou cycler crossfade", self.basculer_normalisation),
            ("V / Z", "⚡ Vitesse / 🌙 Minuteur Veille", "Cycler la vitesse de lecture (0.85× à 1.25×)", self.cycler_vitesse),
            ("Maj+S", "📊 Statistiques & Rythme 24h", "Top 10 jouable, activité 24h et formats audio", self.ouvrir_statistiques),
            ("Ctrl+R", "↻ Scanner la bibliothèque", "Rechercher de nouveaux fichiers audio", lambda: self.scanner_bibliotheque_cli(False)),
            ("—", "✨ Scanner & Nettoyer tags/rips", "Purger mentions de sites et suffixes VEVO", lambda: self.scanner_bibliotheque_cli(True)),
            ("—", "📚 Indexer toutes les paroles", "Récupérer en fond les paroles manquantes", lambda: (paroles.recuperer_tout(), self.notifier("📚 Indexation globale des paroles lancée…"))),
            ("—", "💾 Exporter Sauvegarde JSON", "Sauvegarder playlists, favoris, stats et calages", self.exporter_sauvegarde_cli),
            ("—", "📥 Restaurer Sauvegarde JSON", "Recharger la sauvegarde JSON d'Onde", self.restaurer_sauvegarde_cli),
            ("W / Tab / i", "💿 Basculer Vue Scène / Mini-Barre", "Passer en immersion pochettes + paroles", lambda: (setattr(self, "mode_vue", "scinde" if self.mode_vue == "scene" else "scene"), self.sauvegarder_etat_cli())),
            ("?", "⌨ Aide complète des raccourcis", "Ouvrir la carte de tous les raccourcis", lambda: setattr(self, "aide_ouverte", True)),
        ]
        q = bibliotheque.sans_accents(self.palette_cmd_requete or "").strip()
        if not q:
            return toutes
        mots = q.split()
        return [
            cmd
            for cmd in toutes
            if all(
                m in bibliotheque.sans_accents(f"{cmd[0]} {cmd[1]} {cmd[2]}")
                for m in mots
            )
        ]

    def rendre_panneau_palette_commandes(self, largeur: int, hauteur: int) -> Panel:
        """Palette de commandes floue type Spotlight ([F1] / [Ctrl+P]), clavier & souris."""
        pal = self.palette
        cmds = self._commandes_palette()
        barre = Text()
        barre.append(" ⌘ Commande : ", style=f"bold black on {pal['accent']}")
        barre.append(f" {self.palette_cmd_requete}█", style=f"bold {pal['primaire']}")
        barre.append(
            f"   ({len(cmds)} action{'s' if len(cmds) != 1 else ''})   •   [↑/↓] Choisir  •  [Entrée/Clic] Exécuter  •  [Échap] Fermer",
            style=pal["texte_dim"],
        )

        table = Table(box=None, expand=True, show_header=False, padding=(0, 1))
        table.add_column("Sel", width=3)
        table.add_column("Action", ratio=3)
        table.add_column("Détail", ratio=4)
        table.add_column("Raccourci", width=16, justify="right")

        nb = len(cmds)
        if nb:
            self.palette_cmd_index = max(0, min(self.palette_cmd_index, nb - 1))
        else:
            self.palette_cmd_index = 0
        vis = max(5, hauteur - 7)
        deb = max(0, self.palette_cmd_index - vis // 2)
        fin = min(nb, deb + vis)
        deb = max(0, fin - vis)

        for row_k, i in enumerate(range(deb, fin)):
            rac, tit, desc, _fn = cmds[i]
            sel = i == self.palette_cmd_index
            self._enregistrer_zone(f"pal_row:{i}", 3, 7 + row_k, max(4, largeur - 2), 7 + row_k)
            table.add_row(
                Text("▎❯" if sel else "  ", style=f"bold {pal['accent']}"),
                Text(tit, style="bold bright_white" if sel else "white"),
                Text(desc, style=pal["primaire"] if sel else pal["texte_dim"]),
                Text(f" {rac} ", style=f"bold black on {pal['primaire']}" if sel else f"{pal['texte_dim']} on {pal['surface_2']}"),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        corps = Layout()
        corps.split_column(
            Layout(barre, size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(
                table
                if nb
                else Align.center(
                    Text("Aucune commande correspondante.", style=pal["texte_muet"]),
                    vertical="middle",
                )
            ),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]⌘ Palette de Commandes Onde Studio ([Ctrl+P] / [F1])[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_studio_paroles(self, largeur: int, hauteur: int) -> Panel:
        """Studio Paroles : recherche LRCLIB/NetEase, choix candidat, recalage vocal et collage .lrc."""
        pal = self.palette
        cible = self._piste_locale_cible() or {}
        barre = Text()
        if self.paroles_studio_saisie:
            barre.append(
                f" 🎙 Requête LRCLIB / NetEase : {self.paroles_studio_requete}█ ",
                style=f"bold black on {pal['accent']}",
            )
            barre.append("  ([Entrée] Chercher • [Échap] Liste)", style=pal["texte_dim"])
        else:
            barre.append(
                f" 🎵 {cible.get('titre') or '—'} — {cible.get('artiste') or '—'}",
                style="bold bright_white",
            )
            barre.append(
                f"  •  Source : {self.paroles_source or 'aucune'}  •  Calage : {self.decalage_paroles:+.2f}s\n",
                style=f"bold {pal['primaire']}",
            )
            barre.append(
                " [/] Modifier recherche • [Entrée] Appliquer • [R] Recaler sur la voix • [Ctrl+V] Coller .lrc • [Échap] Fermer",
                style=pal["texte_dim"],
            )

        etat_str = Text()
        if self.paroles_studio_en_cours:
            etat_str.append(" ⠋ Traitement audio / réseau en cours…", style=f"bold {pal['accent']}")
        elif self.paroles_studio_message:
            etat_str.append(f" ℹ {self.paroles_studio_message}", style=f"bold {pal['primaire']}")
        else:
            etat_str.append(
                f" Recherche : « {self.paroles_studio_requete} » ({len(self.paroles_studio_resultats)} résultat(s))",
                style=pal["texte_dim"],
            )

        table = Table(box=None, expand=True, show_header=True, padding=(0, 1))
        table.add_column(" ", width=3)
        table.add_column("Synchro", width=11)
        table.add_column("Titre & Artiste", ratio=3)
        table.add_column("Extrait", ratio=3)
        table.add_column("Durée", width=7, justify="right")

        nb = len(self.paroles_studio_resultats)
        vis = max(4, hauteur - 9)
        deb = max(0, self.paroles_studio_index - vis // 2)
        fin = min(nb, deb + vis)
        for i in range(deb, fin):
            r = self.paroles_studio_resultats[i]
            sel = i == self.paroles_studio_index
            if r.get("mot_a_mot"):
                badge_s = Text("⚡ Mot-à-mot", style=f"bold {pal['succes']}")
            elif r.get("synchro"):
                badge_s = Text("⏱ LRC Synchro", style=f"bold {pal['primaire']}")
            elif r.get("instrumental"):
                badge_s = Text("🎼 Instru", style=pal["secondaire"])
            else:
                badge_s = Text("📄 Texte", style=pal["texte_muet"])
            ext = str(r.get("extrait") or r.get("album") or "").replace("\n", " / ")[:48]
            table.add_row(
                Text("❯ " if sel else "  ", style=f"bold {pal['accent']}"),
                badge_s,
                Text(
                    f"{r.get('titre') or '—'} — {r.get('artiste') or '—'} ({r.get('source') or ''})",
                    style="bold bright_white" if sel else "white",
                ),
                Text(ext, style=pal["texte_dim"]),
                Text(formater_duree(float(r.get("duree") or 0.0)) or "—", style=pal["texte_muet"]),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        corps = Layout()
        corps.split_column(
            Layout(barre, size=2 if not self.paroles_studio_saisie else 1),
            Layout(etat_str, size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(
                table
                if nb
                else Align.center(
                    Text(
                        "Appuie sur [/] pour lancer une recherche manuelle sur LRCLIB / NetEase,\n"
                        "sur [R] pour recaler les paroles existantes sur la voix par FFT/VAD,\n"
                        "ou colle directement un texte .lrc avec [Ctrl+V] !",
                        justify="center",
                        style=pal["texte_muet"],
                    ),
                    vertical="middle",
                )
            ),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]🎙 Studio Paroles & Recalage Vocal ([Ctrl+L] / [F4])[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def _items_reglages(self) -> list[tuple[str, str, str, Any]]:
        """Liste interactive des réglages Studio, DSP, sorties audio mpv et maintenance."""
        nom_dsp = next((n for k, n, _ in EFFETS_DSP if k == self.effet_dsp), "Pur")
        items: list[tuple[str, str, str, Any]] = [
            ("Lecture", "Reprise automatique de la position", "Activée" if self.reprendre_position else "Désactivée", lambda: (setattr(self, "reprendre_position", not self.reprendre_position), self.sauvegarder_etat_cli(), self.notifier(f"🔖 Reprise : {'Oui' if self.reprendre_position else 'Non'}"))),
            ("Lecture", "Auto-DJ intelligent en fin de file", "Activé" if self.auto_dj else "Désactivé", lambda: (setattr(self, "auto_dj", not self.auto_dj), self.sauvegarder_etat_cli(), self.notifier(f"🎧 Auto-DJ : {'Activé' if self.auto_dj else 'Désactivé'}"))),
            ("Audio", "Effet DSP Studio temps réel ([F11])", nom_dsp, self.cycler_effet_dsp),
            ("Audio", "Normalisation EBU R128 (−18 LUFS)", "Activée" if self.normalisation_active else "Désactivée", self.basculer_normalisation),
            ("Audio", "Fondu enchaîné (Crossfade)", f"{self.fondu_duree} s" if self.fondu_duree else "Désactivé", self.cycler_fondu),
            ("Audio", "Vitesse de lecture (hauteur préservée)", f"{self.lecteur.vitesse:.2f}×", self.cycler_vitesse),
            ("Audio", "Son coupé (Mute)", "Oui (🔇)" if self.lecteur.mute else f"Non ({int(self.lecteur.volume)}%)", self.basculer_muet),
            ("Apparence", "Thème Liquid Glass (12 palettes)", THEMES[self.theme_code]["nom"], self.cycler_theme),
            ("Apparence", "Visualiseur audio TrueColor (7 styles)", dict(MODES_VISUALISEUR).get(self.visualiseur_mode, "Spectre"), self.cycler_visualiseur),
            ("Apparence", "Horodatages [00:00] dans les paroles", "Affichés" if self.afficher_timestamps_paroles else "Masqués (Cinéma)", lambda: (setattr(self, "afficher_timestamps_paroles", not self.afficher_timestamps_paroles), self.sauvegarder_etat_cli(), self.notifier(f"⏱ Horodatages : {'Affichés' if self.afficher_timestamps_paroles else 'Masqués'}"))),
            ("Apparence", "Fond d'écran dynamique", self.fond.mode_fond.upper(), self.cycler_mode_fond),
            ("Apparence", "Moteur de rendu pochette/fond", "Kitty HD (GPU)" if self.fond.mode_rendu == "kitty" else "Canevas Pixel (▀)", self.cycler_rendu_fond),
            ("Apparence", "Luminosité du fond d'écran", self.fond.label_luminosite, self.cycler_luminosite_fond),
            ("Bibliothèque", "Tri actif des listes", dict(TRIS_LISTE).get(self.tri_mode, "Défaut"), self.cycler_tri),
            ("Bibliothèque", "Scanner la bibliothèque musicale", self._statut_scan_cli or f"{len(self.pistes)} titres", lambda: self.scanner_bibliotheque_cli(False)),
            ("Bibliothèque", "Scanner + Nettoyer tags & suffixes VEVO", "Purge auto", lambda: self.scanner_bibliotheque_cli(True)),
            ("Bibliothèque", "Détecter et fusionner les doublons", "Ouvrir l'assistant", self.ouvrir_doublons),
            ("Paroles", "Indexer les paroles manquantes en fond", f"{paroles.ETAT_TOUT.get('trouvees', 0)} ajoutées" if paroles.ETAT_TOUT.get("en_cours") else "Lancer l'indexation", lambda: (paroles.recuperer_tout(), self.notifier("📚 Indexation globale des paroles démarrée"))),
            ("Données", "Exporter playlist courante en .m3u8", "Exporter M3U8", self.exporter_playlist_m3u),
            ("Données", "Exporter sauvegarde JSON (playlists, favoris, stats)", "sauvegarde-onde.json", self.exporter_sauvegarde_cli),
            ("Données", "Restaurer sauvegarde JSON", "Importer", self.restaurer_sauvegarde_cli),
        ]
        for dev_id, dev_nom in self.peripheriques_audio:
            actif_d = self.audio_device == dev_id
            items.append(
                (
                    "Sortie Audio",
                    f"🎧 {dev_nom}",
                    "✓ ACTIF" if actif_d else dev_id,
                    lambda d=dev_id, n=dev_nom: (
                        setattr(self, "audio_device", d),
                        self.lecteur.definir_peripherique_audio(d),
                        self.sauvegarder_etat_cli(),
                        self.notifier(f"🎧 Sortie audio : {n}"),
                    ),
                )
            )
        return items

    def rendre_panneau_reglages(self, largeur: int, hauteur: int) -> Panel:
        """Centre de Réglages & Sélecteur de Sortie Audio ([Ctrl+G] / [F7] / [F10]), clavier & souris."""
        pal = self.palette
        items = self._items_reglages()
        nb = len(items)
        if nb:
            self.reglages_index = max(0, min(self.reglages_index, nb - 1))

        barre = Text()
        barre.append(
            " [↑/↓] Naviguer  •  [Entrée / Espace / Clic] Modifier ou Activer  •  [Ctrl+D] Doublons  •  [Échap] Fermer",
            style=pal["texte_dim"],
        )

        table = Table(box=None, expand=True, show_header=True, padding=(0, 1))
        table.add_column(" ", width=3)
        table.add_column("Section", width=14)
        table.add_column("Paramètre ou Action", ratio=3)
        table.add_column("État / Valeur", ratio=2, justify="right")

        vis = max(6, hauteur - 7)
        deb = max(0, self.reglages_index - vis // 2)
        fin = min(nb, deb + vis)
        deb = max(0, fin - vis)

        for row_k, i in enumerate(range(deb, fin)):
            sec, label, val, _fn = items[i]
            sel = i == self.reglages_index
            self._enregistrer_zone(f"reg_row:{i}", 3, 8 + row_k, max(4, largeur - 2), 8 + row_k)
            est_actif = str(val).startswith("✓") or val in ("Activé", "Activée", "Affichés", "Oui (🔇)")
            table.add_row(
                Text("▎❯" if sel else "  ", style=f"bold {pal['accent']}"),
                Text(sec, style=f"bold {pal['secondaire']}"),
                Text(label, style="bold bright_white" if sel else "white"),
                Text(
                    val,
                    style=f"bold black on {pal['accent']}"
                    if sel
                    else (f"bold {pal['succes']}" if est_actif else pal["primaire"]),
                ),
                style=f"on {pal['selection_bg']}" if sel else None,
            )

        corps = Layout()
        corps.split_column(
            Layout(barre, size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(table),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]⚙ Réglages Studio & Sorties Audio mpv ([Ctrl+G] / [F7] / [F10])[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_doublons(self, largeur: int, hauteur: int) -> Panel:
        """Assistant interactif de détection et fusion des doublons ([Ctrl+D] / [F8])."""
        pal = self.palette
        grps = self.doublons_groupes
        nb_g = len(grps)
        if nb_g:
            self.doublons_groupe_index = max(0, min(self.doublons_groupe_index, nb_g - 1))

        entete = Text()
        entete.append(
            f" 👯 Groupes détectés : {nb_g}   •   [←/→] Groupe préc/suiv   •   [↑/↓] Copie à conserver   •   [Entrée] Fusionner   •   [R] Re-scanner   •   [Échap] Fermer",
            style=pal["texte_dim"],
        )

        if self.doublons_en_scan:
            centre: Any = Align.center(
                Text("⠋ Analyse des doublons dans la bibliothèque…", style=f"bold {pal['primaire']}"),
                vertical="middle",
            )
        elif not nb_g:
            centre = Align.center(
                Text(
                    self.doublons_message or "Aucun doublon détecté dans ta bibliothèque ✨",
                    style=f"bold {pal['succes']}",
                ),
                vertical="middle",
            )
        else:
            grp = grps[self.doublons_groupe_index]
            if grp:
                self.doublons_copie_index = max(0, min(self.doublons_copie_index, len(grp) - 1))
            t_copies = Table(
                title=f"[bold {pal['primaire']}]Groupe {self.doublons_groupe_index + 1}/{nb_g} — Choisis l'exemplaire à garder visible[/bold {pal['primaire']}]",
                box=box.SIMPLE,
                expand=True,
                padding=(0, 1),
            )
            t_copies.add_column("Choix", width=11)
            t_copies.add_column("Qualité", width=14)
            t_copies.add_column("Titre — Artiste", ratio=3)
            t_copies.add_column("Album", ratio=2)
            t_copies.add_column("Durée", width=7, justify="right")
            t_copies.add_column("Chemin disque", ratio=4)

            for idx, cp in enumerate(grp):
                sel = idx == self.doublons_copie_index
                t_copies.add_row(
                    Text("✓ GARDER" if sel else "  Fusion.", style=f"bold {pal['succes']}" if sel else pal["texte_muet"]),
                    Text(badge_qualite_piste(cp, complet=True), style=f"bold {pal['accent']}"),
                    Text(f"{cp.get('titre') or '—'} — {cp.get('artiste') or '—'}", style="bold bright_white" if sel else "white"),
                    Text(cp.get("album") or "—", style=pal["texte_dim"]),
                    Text(formater_duree(float(cp.get("duree") or 0.0)), style=pal["texte_muet"]),
                    Text(str(cp.get("chemin") or ""), style=pal["texte_dim"]),
                    style=f"on {pal['selection_bg']}" if sel else None,
                )
            centre = t_copies

        corps = Layout()
        corps.split_column(
            Layout(entete, size=1),
            Layout(Text("─" * max(10, largeur - 6), style=pal["bordure"]), size=1),
            Layout(centre),
        )
        return Panel(
            corps,
            title=f"[bold {pal['accent']}]👯 Fusion des Doublons (favoris, écoutes & playlists préservés) ([Ctrl+D] / [F8])[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_panneau_aide(self) -> Panel:
        """Carte complète des raccourcis clavier et contrôles souris Liquid Glass Studio 2.0."""
        pal = self.palette
        table = Table(box=box.SIMPLE, expand=True, show_header=True)
        table.add_column("Touche", style=f"bold {pal['primaire']}", width=20)
        table.add_column("Action", style="white")
        table.add_column("Touche", style=f"bold {pal['accent']}", width=20)
        table.add_column("Action", style="white")

        lignes = [
            ("Espace / Entrée", "Play/Pause • Jouer la sélection", "F3 / W / Tab / i", "Accueil • Scène • Cycle Vues • Mini-Barre"),
            ("← / →  •  + / -", "Seek ±5s  •  Volume ±5%", "1 à 9  •  Shift+Tab", "Onglets (9=Dossiers, 🏷=Genres) • Filtre /"),
            ("< / > ou .  •  #/F9", "Précédent / Suivant • Muet / Rétablir", "Ctrl+P ou F1", "Palette de commandes floue (Spotlight)"),
            ("F  •  A  •  Ctrl+A", "Favori ♥ / ★ Radio • File • Lire ensuite", "Ctrl+L / F4", "Studio Paroles (LRCLIB, recalage, coller .lrc)"),
            ("Ctrl+X  •  Alt+Entrée", "Radio du titre (Smart Mix) • Tout lire", ": ou Ctrl+K", "Recherche globale paroles (saut direct)"),
            ("N / F2 / P / Ctrl+U", "Créer / Renommer / Ajouter / Export M3U8", "Maj+E  •  F11", "EQ 10B (profils [S]/[7-9]) • Effet DSP Studio"),
            ("S  •  !  •  R", "Aléatoire • Auto-DJ intelligent • Répétition", "Maj+T  •  Maj+I", "Tags + iTunes HD + Cover [C] • Inspecteur"),
            ("U / D  •  V / Z", "Normalisation R128 / Fondu • Vitesse / Veille", "Ctrl+G / F7 / F10", "Réglages Studio, sorties audio & sauvegarde"),
            ("B / G / O / M / T", "Fond • Galerie • Luminosité • Kitty • 12 Thèmes", "Ctrl+D / F8  •  Y", "Fusion de doublons • Studio YouTube Direct"),
            ("F5  •  F6 / Ctrl+O", "Visualiseur (7 styles HD) • Tri (8 modes)", "Maj+S  •  K  •  C", "Stats 24h (jouable) • Relancer paroles • Courant"),
            ("[ / ] / 0  •  , / ;", "Calage paroles ±0.25s • Boucle A-B", "Souris & Double-clic", "En-tête, onglets, volume, barre, paroles, dock"),
        ]
        for g_t, g_a, d_t, d_a in lignes:
            table.add_row(g_t, g_a, d_t, d_a)

        return Panel(
            Align.center(table, vertical="middle"),
            title=f"[bold {pal['accent']}]⌨ Commandes & Raccourcis d'Onde Studio 2.0 ([?] ou [Échap] pour fermer)[/bold {pal['accent']}]",
            box=box.ROUNDED,
            border_style=pal["accent"],
            style=f"on {pal['surface_bg']}",
        )

    def rendre_pied_de_page(self) -> Panel:
        """Dock contextuel Liquid Glass avec capsules clavier cliquables et barre de décompte des toasts."""
        pal = self.palette
        w_tot = self.console.size.width
        h_tot = self.console.size.height
        y_foot = max(3, h_tot - 1)
        maintenant = time.time()

        if self.toast_message and maintenant < self.toast_expiration:
            reste_ratio = max(
                0.0,
                min(1.0, (self.toast_expiration - maintenant) / max(0.4, self.toast_duree)),
            )
            texte = Text(no_wrap=True, overflow="ellipsis")
            texte.append(f" ✨ {self.toast_message} ", style=f"bold black on {pal['accent']}")
            if w_tot >= 70:
                texte.append("  ")
                texte.append_text(
                    barre_degrade(reste_ratio, 10, pal["primaire"], pal["accent"], pal["bordure"], "─")
                )
            return Panel(
                Align.center(texte),
                box=box.ROUNDED,
                height=3,
                border_style=pal["accent"],
            )

        # Raccourcis dynamiques selon le contexte actif
        if self.mode_vue == "accueil":
            raccourcis: list[tuple[str | None, str, str]] = [
                (None, "←/→", "Section"),
                (None, "↑/↓", "Choisir"),
                (None, "Entrée", "Lire"),
                (None, "R", "Découvrir"),
                ("foot_radio", "Ctrl+X", "Radio"),
                ("foot_palette", "F1", "Palette"),
                ("foot_yt", "Y", "YouTube"),
                ("foot_eq", "Maj+E", "EQ"),
                ("foot_reglages", "Ctrl+G", "Réglages"),
                ("foot_aide", "?", "Aide"),
            ]
        elif self.mode_vue == "scene":
            raccourcis = [
                (None, "Espace", "Play"),
                ("foot_vis", "F5", "Visu(7)"),
                ("foot_theme", "T", "Thème(12)"),
                ("foot_dsp", "F11", "DSP"),
                ("foot_paroles", "Ctrl+L", "Paroles"),
                ("foot_radio", "Ctrl+X", "Radio"),
                ("foot_eq", "Maj+E", "EQ"),
                ("foot_palette", "F1", "Palette"),
                ("foot_aide", "?", "Aide"),
                (None, "W", "Scindé"),
            ]
        elif self.mode_onglet == "file":
            raccourcis = [
                (None, "Shift+↑↓", "Ordre"),
                (None, "X", "Retirer"),
                (None, "C", "Vider"),
                ("foot_radio", "Ctrl+X", "Radio"),
                ("foot_palette", "F1", "Palette"),
                ("foot_eq", "Maj+E", "EQ"),
                ("foot_yt", "Y", "YouTube"),
                ("foot_reglages", "Ctrl+G", "Réglages"),
                ("foot_aide", "?", "Aide"),
            ]
        elif self.mode_onglet == "playlists":
            raccourcis = [
                (None, "N", "Créer"),
                (None, "F2", "Renommer"),
                (None, "P", "Ajouter"),
                ("foot_m3u", "Ctrl+U", "M3U8"),
                (None, "X", "Suppr"),
                ("foot_palette", "F1", "Palette"),
                ("foot_yt", "Y", "YouTube"),
                ("foot_reglages", "Ctrl+G", "Réglages"),
                ("foot_aide", "?", "Aide"),
            ]
        else:
            raccourcis = [
                (None, "Espace", "Play"),
                ("foot_accueil", "F3", "Accueil"),
                ("foot_palette", "F1", "Palette"),
                ("foot_paroles", "Ctrl+L", "Paroles"),
                ("foot_vis", "F5", "Visu"),
                ("foot_dsp", "F11", "DSP"),
                ("foot_eq", "Maj+E", "EQ"),
                ("foot_yt", "Y", "YouTube"),
                ("foot_reglages", "Ctrl+G", "Réglages"),
                ("foot_aide", "?", "Aide"),
                (None, "Q", "Quitter"),
            ]

        texte = Text(no_wrap=True, overflow="crop")
        spans_f: list[tuple[str, int, int]] = []
        pos_f = 0
        for z_nom, touche, action in raccourcis:
            cap = f" {touche} "
            act_s = f" {action}  "
            w_item = cell_len(cap) + cell_len(act_s)
            if pos_f + w_item > max(20, w_tot - 4):
                break
            deb_i = pos_f
            texte.append(cap, style=f"bold {pal['primaire']} on {pal['surface_2']}")
            texte.append(act_s, style=pal["texte_dim"])
            if z_nom:
                spans_f.append((z_nom, deb_i, pos_f + w_item - 2))
            pos_f += w_item

        marge_f = max(0, (w_tot - 4 - pos_f) // 2)
        for z_nom, deb_i, fin_i in spans_f:
            self._enregistrer_zone(z_nom, 3 + marge_f + deb_i, y_foot, 3 + marge_f + fin_i, y_foot)

        return Panel(
            Align.center(texte),
            box=box.ROUNDED,
            height=3,
            border_style=pal["bordure"],
        )

    def generer_ecran(self) -> ToileFondPhoto:
        largeur = self.console.size.width
        hauteur = self.console.size.height
        self._cible_pochette_hd = None
        self._zones_clic = {}
        self._paroles_lignes_ecran = []
        self._accueil_zones = []

        # Mode Mini-Barre 5 lignes ([i] ou terminal très bas)
        if self.mini_mode or hauteur <= 10:
            racine_mini = Layout(self.rendre_mini_lecteur(largeur, hauteur))
            return ToileFondPhoto(racine_mini, self.fond, self.palette)

        racine = Layout()
        racine.split_column(
            Layout(self.rendre_en_tete(), size=3),
            Layout(name="corps"),
            Layout(self.rendre_pied_de_page(), size=3),
        )

        corps = racine["corps"]
        if self.aide_ouverte:
            corps.update(self.rendre_panneau_aide())
        elif self.palette_cmd_ouverte:
            corps.update(self.rendre_panneau_palette_commandes(largeur, hauteur - 6))
        elif self.reglages_ouvert:
            corps.update(self.rendre_panneau_reglages(largeur, hauteur - 6))
        elif self.doublons_ouvert:
            corps.update(self.rendre_panneau_doublons(largeur, hauteur - 6))
        elif self.paroles_studio_ouvert:
            corps.update(self.rendre_panneau_studio_paroles(largeur, hauteur - 6))
        elif self.eq_perso_ouvert:
            corps.update(self.rendre_panneau_eq_10_bandes(largeur, hauteur - 6))
        elif self.paroles_recherche_ouverte:
            corps.update(self.rendre_panneau_recherche_paroles(largeur, hauteur - 6))
        elif self.proprietes_ouvertes:
            corps.update(self.rendre_panneau_proprietes(largeur, hauteur - 6))
        elif self.tags_ouvert:
            corps.update(self.rendre_panneau_editeur_tags(largeur, hauteur - 6))
        elif self.modal_playlist_mode:
            corps.update(self.rendre_modal_playlist(largeur, hauteur - 6))
        elif self.yt_ouvert:
            corps.update(self.rendre_panneau_youtube(largeur, hauteur - 6))
        elif self.stats_ouverte:
            corps.update(self.rendre_panneau_statistiques(largeur, hauteur - 6))
        elif self.galerie_ouverte:
            corps.update(self.rendre_galerie_photos(largeur, hauteur - 6))
        elif self.mode_vue == "accueil":
            corps.update(self.rendre_vue_accueil(largeur, hauteur - 6))
        elif self.mode_vue == "scene" and largeur >= 76:
            corps.update(self.rendre_vue_scene_immersion(largeur, hauteur - 6))
        elif self.mode_vue == "paroles" or largeur < 76:
            corps.update(self.rendre_vue_plein_ecran_paroles(largeur, hauteur - 6))
        elif self.mode_vue == "liste":
            corps.update(self.rendre_panneau_liste(largeur, hauteur - 6))
        else:
            largeur_liste = self._largeur_liste(largeur)
            corps.split_row(
                Layout(
                    self.rendre_panneau_liste(largeur_liste, hauteur - 6),
                    size=largeur_liste,
                ),
                Layout(
                    self.rendre_panneau_lecteur(
                        largeur - largeur_liste, hauteur - 6
                    )
                ),
            )
        return ToileFondPhoto(racine, self.fond, self.palette)

    def synchroniser_pochette_hd(self):
        """Superpose ou masque l'image HD Kitty (\\x1b_G) après le rafraîchissement Rich."""
        if self._cible_pochette_hd:
            ch, col, row, cols, rows = self._cible_pochette_hd
            self.pochette_hd.afficher(ch, col, row, cols, rows)
        else:
            self.pochette_hd.masquer()

    # ── Boucle Interactive ───────────────────────────────────────────────────

    def traiter_touche(self, touche: str) -> bool:
        # 1. Fenêtre d'aide
        if self.aide_ouverte:
            if touche in ("?", "ECHAP", "ENTREE", "q", "Q"):
                self.aide_ouverte = False
            return False

        # 2. Palette de commandes Spotlight ([F1] / [Ctrl+P])
        if self.palette_cmd_ouverte:
            cmds = self._commandes_palette()
            nb_c = len(cmds)
            if touche.startswith("CLIC:"):
                with contextlib.suppress(ValueError):
                    _, sx, sy = touche.split(":")
                    cx, cy = int(sx), int(sy)
                    for nom_z, z in list(self._zones_clic.items()):
                        if nom_z.startswith("pal_row:") and z[0] <= cx <= z[2] and z[1] <= cy <= z[3]:
                            idx_p = int(nom_z.split(":", 1)[1])
                            if 0 <= idx_p < nb_c:
                                self.palette_cmd_index = idx_p
                                fn = cmds[idx_p][3]
                                self.palette_cmd_ouverte = False
                                fn()
                                return False
                return False
            if touche in ("ECHAP", "CTRL_P", "F1"):
                self.palette_cmd_ouverte = False
            elif touche == "HAUT" and nb_c:
                self.palette_cmd_index = (self.palette_cmd_index - 1) % nb_c
            elif touche == "BAS" and nb_c:
                self.palette_cmd_index = (self.palette_cmd_index + 1) % nb_c
            elif touche == "PAGE_HAUT" and nb_c:
                self.palette_cmd_index = max(0, self.palette_cmd_index - 8)
            elif touche == "PAGE_BAS" and nb_c:
                self.palette_cmd_index = min(nb_c - 1, self.palette_cmd_index + 8)
            elif touche == "ENTREE" and nb_c:
                fn = cmds[self.palette_cmd_index][3]
                self.palette_cmd_ouverte = False
                fn()
            else:
                nouv = appliquer_touche_saisie(touche, self.palette_cmd_requete)
                if nouv is not None:
                    self.palette_cmd_requete = nouv
                    self.palette_cmd_index = 0
            return False

        # 3. Centre de Réglages & Sortie Audio ([Ctrl+G] / [F7] / [F10])
        if self.reglages_ouvert:
            items = self._items_reglages()
            nb_reg = len(items)
            if touche.startswith("CLIC:"):
                with contextlib.suppress(ValueError):
                    _, sx, sy = touche.split(":")
                    cx, cy = int(sx), int(sy)
                    for nom_z, z in list(self._zones_clic.items()):
                        if nom_z.startswith("reg_row:") and z[0] <= cx <= z[2] and z[1] <= cy <= z[3]:
                            idx_r = int(nom_z.split(":", 1)[1])
                            if 0 <= idx_r < nb_reg:
                                self.reglages_index = idx_r
                                items[idx_r][3]()
                                return False
                return False
            if touche in ("ECHAP", "CTRL_G", "F7", "F10", "q", "Q"):
                self.reglages_ouvert = False
            elif touche in ("CTRL_D", "F8"):
                self.ouvrir_doublons()
            elif touche in ("HAUT", "k", "K") and nb_reg:
                self.reglages_index = (self.reglages_index - 1) % nb_reg
            elif touche in ("BAS", "j", "J") and nb_reg:
                self.reglages_index = (self.reglages_index + 1) % nb_reg
            elif touche == "PAGE_HAUT" and nb_reg:
                self.reglages_index = max(0, self.reglages_index - 6)
            elif touche == "PAGE_BAS" and nb_reg:
                self.reglages_index = min(nb_reg - 1, self.reglages_index + 6)
            elif touche in ("ENTREE", "ESPACE", "DROITE", "l") and nb_reg:
                items[self.reglages_index][3]()
            return False

        # 4. Fusion des Doublons ([Ctrl+D] / [F8])
        if self.doublons_ouvert:
            nb_g = len(self.doublons_groupes)
            if touche in ("ECHAP", "CTRL_D", "F8", "q", "Q"):
                self.doublons_ouvert = False
            elif touche in ("r", "R"):
                self.lancer_scan_doublons()
            elif touche in ("GAUCHE", "h") and nb_g:
                self.doublons_groupe_index = (self.doublons_groupe_index - 1) % nb_g
                self.doublons_copie_index = 0
            elif touche in ("DROITE", "l") and nb_g:
                self.doublons_groupe_index = (self.doublons_groupe_index + 1) % nb_g
                self.doublons_copie_index = 0
            elif touche in ("HAUT", "k") and nb_g:
                grp = self.doublons_groupes[self.doublons_groupe_index]
                if grp:
                    self.doublons_copie_index = (self.doublons_copie_index - 1) % len(grp)
            elif touche in ("BAS", "j") and nb_g:
                grp = self.doublons_groupes[self.doublons_groupe_index]
                if grp:
                    self.doublons_copie_index = (self.doublons_copie_index + 1) % len(grp)
            elif touche == "ENTREE" and nb_g:
                self.fusionner_doublon_courant()
            return False

        # 5. Studio Paroles & Recalage Vocal ([Ctrl+L] / [F4])
        if self.paroles_studio_ouvert:
            cible = self._piste_locale_cible()
            if self.paroles_studio_saisie:
                if touche == "ECHAP":
                    self.paroles_studio_saisie = False
                elif touche == "ENTREE":
                    self.paroles_studio_saisie = False
                    self.chercher_studio_paroles(
                        self.paroles_studio_requete,
                        float(cible.get("duree") or 0.0) if cible else None,
                    )
                else:
                    nouv = appliquer_touche_saisie(touche, self.paroles_studio_requete)
                    if nouv is not None:
                        self.paroles_studio_requete = nouv
                return False

            nb_ps = len(self.paroles_studio_resultats)
            if touche in ("ECHAP", "CTRL_L", "F4", "q", "Q"):
                self.paroles_studio_ouvert = False
            elif touche in ("/", "i"):
                self.paroles_studio_saisie = True
            elif touche in ("r", "R"):
                self.recaler_parole_courante()
            elif touche in ("HAUT", "k") and nb_ps:
                self.paroles_studio_index = (self.paroles_studio_index - 1) % nb_ps
            elif touche in ("BAS", "j") and nb_ps:
                self.paroles_studio_index = (self.paroles_studio_index + 1) % nb_ps
            elif touche == "ENTREE" and nb_ps:
                cand = self.paroles_studio_resultats[self.paroles_studio_index]
                if cand.get("id") is not None:
                    self.choisir_studio_parole(cand["id"])
            elif touche.startswith("PASTE:") and cible and cible.get("id"):
                txt_lrc = touche[6:].strip()
                if txt_lrc:
                    try:
                        paroles.importer(int(cible["id"]), txt_lrc)
                        if self.piste_courante and self.piste_courante.get("id") == cible["id"]:
                            self.charger_paroles_async(int(cible["id"]), forcer=False)
                        self.paroles_studio_ouvert = False
                        self.notifier("🎙 Paroles .lrc collées et enregistrées !")
                    except Exception as ex:  # noqa: BLE001
                        self.paroles_studio_message = str(ex)
            return False

        # 6. Modale Playlists (Créer [N] / Renommer [F2] / Ajouter [P])
        if self.modal_playlist_mode in ("creer", "renommer"):
            est_ren = self.modal_playlist_mode == "renommer"
            if touche == "ECHAP":
                self.modal_playlist_mode = None
            elif touche == "ENTREE":
                nom = self.nom_nouvelle_playlist.strip() or (
                    self.titre_cible_playlist if est_ren else "Ma Playlist"
                )
                try:
                    if est_ren:
                        pid_pl = self.pistes_cibles_playlist[0]
                        bibliotheque.modifier_playlist(pid_pl, nom)
                        self.recharger_bibliotheque()
                        self.pistes_cibles_playlist = []
                        self.modal_playlist_mode = None
                        self.notifier(f"✏ Playlist renommée : « {nom} »")
                    else:
                        pid_pl = bibliotheque.creer_playlist(
                            nom, self.pistes_cibles_playlist
                        )
                        self.recharger_bibliotheque()
                        nb_aj = len(self.pistes_cibles_playlist)
                        self.pistes_cibles_playlist = []
                        self.modal_playlist_mode = None
                        if nb_aj > 0:
                            self.notifier(
                                f"✨ Playlist « {nom} » créée avec {nb_aj} titre(s) !"
                            )
                        else:
                            self.notifier(f"✨ Playlist « {nom} » créée (id={pid_pl})")
                except Exception as ex:  # noqa: BLE001
                    self.notifier(f"Erreur playlist : {ex}")
                    self.modal_playlist_mode = None
            else:
                nouv = appliquer_touche_saisie(touche, self.nom_nouvelle_playlist)
                if nouv is not None:
                    self.nom_nouvelle_playlist = nouv
            return False

        if self.modal_playlist_mode == "ajouter":
            nb_pl = len(self.playlists_liste)
            if touche in ("ECHAP", "p", "P"):
                self.modal_playlist_mode = None
            elif touche in ("HAUT", "k", "K") and nb_pl:
                self.index_playlist_cible = (self.index_playlist_cible - 1) % nb_pl
            elif touche in ("BAS", "j", "J") and nb_pl:
                self.index_playlist_cible = (self.index_playlist_cible + 1) % nb_pl
            elif touche in ("n", "N"):
                self.modal_playlist_mode = "creer"
                self.nom_nouvelle_playlist = ""
            elif touche == "ENTREE" and nb_pl:
                pl = self.playlists_liste[self.index_playlist_cible]
                try:
                    aj = bibliotheque.ajouter_a_playlist(
                        pl["id"], self.pistes_cibles_playlist
                    )
                    self.recharger_bibliotheque()
                    self.modal_playlist_mode = None
                    self.notifier(
                        f"📂 +{aj} titre(s) ajouté(s) à « {pl.get('nom')} »"
                    )
                except Exception as ex:  # noqa: BLE001
                    self.notifier(f"Erreur ajout playlist : {ex}")
                    self.modal_playlist_mode = None
            return False

        # 7. Panneau Téléchargement YouTube ([Y])
        if self.yt_ouvert:
            if self.yt_saisie_active:
                if touche == "ECHAP":
                    self.yt_saisie_active = False
                elif touche == "ENTREE":
                    self.yt_saisie_active = False
                    self.lancer_recherche_youtube(self.yt_requete)
                else:
                    nouv = appliquer_touche_saisie(touche, self.yt_requete)
                    if nouv is not None:
                        self.yt_requete = nouv
                return False

            nb_yt = len(self.yt_resultats)
            if touche in ("ECHAP", "y", "Y", "q", "Q"):
                self.yt_ouvert = False
            elif touche in ("/", "i", "I"):
                self.yt_saisie_active = True
            elif touche.startswith("PASTE:"):
                self.yt_requete = touche[6:].strip()
                self.lancer_recherche_youtube(self.yt_requete)
            elif touche in ("HAUT", "k", "K") and nb_yt:
                self.yt_index_selection = (self.yt_index_selection - 1) % nb_yt
            elif touche in ("BAS", "j", "J") and nb_yt:
                self.yt_index_selection = (self.yt_index_selection + 1) % nb_yt
            elif touche == "ENTREE" and nb_yt:
                res_sel = self.yt_resultats[self.yt_index_selection]
                t_fini = next(
                    (
                        t
                        for t in telechargement.taches()
                        if t.get("id") == res_sel.get("id") and t.get("etat") == "fini"
                    ),
                    None,
                )
                p_fini = (
                    self._trouver_piste_rapide(
                        str(t_fini.get("titre") or res_sel.get("titre") or "")
                    )
                    if t_fini
                    else None
                )
                if p_fini:
                    self.yt_ouvert = False
                    self.jouer_piste(p_fini)
                else:
                    self.demarrer_telechargement_youtube(res_sel)
            elif touche in ("x", "X", "SUPPR"):
                actifs = [
                    t
                    for t in telechargement.taches()
                    if t.get("etat")
                    in ("attente", "telechargement", "conversion", "tags", "paroles", "reprise")
                ]
                if actifs:
                    cible_vid = (
                        self.yt_resultats[self.yt_index_selection].get("id")
                        if nb_yt
                        else None
                    )
                    vid_ann = next(
                        (t["id"] for t in actifs if t.get("id") == cible_vid),
                        actifs[0]["id"],
                    )
                    telechargement.annuler(vid_ann)
                    self.notifier("⏹ Téléchargement annulé")
            elif touche in ("c", "C"):
                telechargement.vider_terminees()
                self.notifier("🧹 Téléchargements terminés effacés")
            return False

        # 8. Panneau Statistiques ([Maj+S]) — Top 10 jouable au clavier
        if self.stats_ouverte:
            top_t = (self.stats_donnees or {}).get("top_titres") or []
            nb_t = min(10, len(top_t))
            if touche in ("ECHAP", "s", "S", "$", "*", "q", "Q"):
                self.stats_ouverte = False
            elif touche in ("HAUT", "k", "K") and nb_t:
                self.stats_index = (self.stats_index - 1) % nb_t
            elif touche in ("BAS", "j", "J") and nb_t:
                self.stats_index = (self.stats_index + 1) % nb_t
            elif touche == "ENTREE":
                if nb_t and 0 <= self.stats_index < nb_t:
                    pid = top_t[self.stats_index].get("id")
                    p_cib = next((p for p in self.pistes if p.get("id") == pid), None)
                    if p_cib:
                        self.stats_ouverte = False
                        self.jouer_piste(p_cib)
                        return False
                self.stats_ouverte = False
            return False

        # 9. Galerie de photos de fond ([G])
        if self.galerie_ouverte:
            nb_ph = len(self.photos_disponibles)
            if touche in ("ECHAP", "g", "G"):
                self.galerie_ouverte = False
                self.actualiser_palette_et_fond()
            elif touche in ("HAUT", "k", "K") and nb_ph:
                self.index_galerie = (self.index_galerie - 1) % nb_ph
                self.fond.mode_fond = "photo"
                self.fond.chemin_photo_perso = self.photos_disponibles[
                    self.index_galerie
                ][1]
                self.actualiser_palette_et_fond()
            elif touche in ("BAS", "j", "J") and nb_ph:
                self.index_galerie = (self.index_galerie + 1) % nb_ph
                self.fond.mode_fond = "photo"
                self.fond.chemin_photo_perso = self.photos_disponibles[
                    self.index_galerie
                ][1]
                self.actualiser_palette_et_fond()
            elif touche == "ENTREE" and nb_ph:
                nom, ch = self.photos_disponibles[self.index_galerie]
                self.fond.mode_fond = "photo"
                self.fond.chemin_photo_perso = ch
                self.galerie_ouverte = False
                self.actualiser_palette_et_fond()
                self.sauvegarder_etat_cli()
                self.notifier(f"🖼 Photo de fond appliquée : {nom}")
            elif touche in ("b", "B"):
                self.cycler_mode_fond()
            elif touche in ("o", "O"):
                self.cycler_luminosite_fond()
            elif touche in ("m", "M"):
                self.cycler_rendu_fond()
            elif touche in ("t", "T"):
                self.cycler_theme()
            return False

        # 10. Égaliseur Studio 10 bandes ([Maj+E]) + Profils Persos ([S]/[7-9]) & DSP ([F])
        if self.eq_perso_ouvert:
            if self.eq_saisie_nom:
                if touche == "ECHAP":
                    self.eq_saisie_nom = False
                elif touche == "ENTREE":
                    nom_p = self.eq_nom_tampon.strip()[:20] or f"Perso {len(self.eq_profils_perso) + 1}"
                    nouv_pr = {"nom": nom_p, "bandes": [round(float(x), 1) for x in self.eq_bandes]}
                    existant = next((i for i, pr in enumerate(self.eq_profils_perso) if pr.get("nom") == nom_p), None)
                    if existant is not None:
                        self.eq_profils_perso[existant] = nouv_pr
                    elif len(self.eq_profils_perso) < 3:
                        self.eq_profils_perso.append(nouv_pr)
                    else:
                        self.eq_profils_perso[-1] = nouv_pr
                    self.eq_saisie_nom = False
                    self.eq_perso_actif = True
                    self.sauvegarder_etat_cli()
                    self.notifier(f"💾 Profil EQ « {nom_p} » sauvegardé (touche [7-9])")
                else:
                    nouv = appliquer_touche_saisie(touche, self.eq_nom_tampon)
                    if nouv is not None:
                        self.eq_nom_tampon = nouv[:20]
                return False

            if touche in ("ECHAP", "E", "q", "Q", "ENTREE"):
                self.eq_perso_ouvert = False
                self.sauvegarder_etat_cli()
            elif touche in ("s", "S"):
                self.eq_saisie_nom = True
                self.eq_nom_tampon = ""
            elif touche in ("f", "F", "F11"):
                self.cycler_effet_dsp()
            elif touche in ("SUPPR", "x", "X") and self.eq_profils_perso:
                ret = self.eq_profils_perso.pop()
                self.sauvegarder_etat_cli()
                self.notifier(f"🗑 Profil EQ supprimé : {ret.get('nom')}")
            elif touche in ("GAUCHE", "h", "H"):
                self.eq_bande_selection = (self.eq_bande_selection - 1) % 10
            elif touche in ("DROITE", "l", "L"):
                self.eq_bande_selection = (self.eq_bande_selection + 1) % 10
            elif touche in ("HAUT", "k", "+", "="):
                self.eq_perso_actif = True
                b = self.eq_bande_selection
                self.eq_bandes[b] = round(min(12.0, self.eq_bandes[b] + 1.0), 1)
                self.appliquer_egaliseur_courant()
                self.sauvegarder_etat_cli()
            elif touche in ("BAS", "j", "-", "_"):
                self.eq_perso_actif = True
                b = self.eq_bande_selection
                self.eq_bandes[b] = round(max(-12.0, self.eq_bandes[b] - 1.0), 1)
                self.appliquer_egaliseur_courant()
                self.sauvegarder_etat_cli()
            elif touche == "0":
                self.eq_bandes = [0.0] * 10
                self.eq_perso_actif = False
                self.eq_index = 0
                self.appliquer_egaliseur_courant()
                self.sauvegarder_etat_cli()
                self.notifier("🎚 Égaliseur 10 bandes remis à plat (0 dB)")
            elif touche in ("1", "2", "3", "4", "5", "6"):
                idx_p = int(touche) - 1
                if 0 <= idx_p < len(PROFILS_EQ):
                    self.eq_index = idx_p
                    self.eq_perso_actif = False
                    if idx_p < len(PROFILS_EQ_BANDES):
                        self.eq_bandes = list(PROFILS_EQ_BANDES[idx_p])
                    self.appliquer_egaliseur_courant()
                    self.sauvegarder_etat_cli()
                    self.notifier(f"🎛 Profil EQ : {PROFILS_EQ[idx_p][0]}")
            elif touche in ("7", "8", "9"):
                idx_c = int(touche) - 7
                if 0 <= idx_c < len(self.eq_profils_perso):
                    pr = self.eq_profils_perso[idx_c]
                    self.eq_bandes = list(pr["bandes"])
                    self.eq_perso_actif = True
                    self.appliquer_egaliseur_courant()
                    self.sauvegarder_etat_cli()
                    self.notifier(f"★ Profil EQ perso : {pr.get('nom')}")
            elif touche == "e":
                self.cycler_egaliseur()
            elif touche.startswith("CLIC:"):
                with contextlib.suppress(ValueError):
                    _, s_x, s_y = touche.split(":")
                    cx, cy = int(s_x), int(s_y)
                    z_dsp = self._zones_clic.get("eq_dsp")
                    if z_dsp and z_dsp[0] <= cx <= z_dsp[2] and z_dsp[1] <= cy <= z_dsp[3]:
                        self.cycler_effet_dsp()
                        return False
                    for idx_p in range(len(PROFILS_EQ)):
                        z = self._zones_clic.get(f"eq_preset:{idx_p}")
                        if z and z[0] <= cx <= z[2] and z[1] <= cy <= z[3]:
                            self.eq_index = idx_p
                            self.eq_perso_actif = False
                            if idx_p < len(PROFILS_EQ_BANDES):
                                self.eq_bandes = list(PROFILS_EQ_BANDES[idx_p])
                            self.appliquer_egaliseur_courant()
                            self.sauvegarder_etat_cli()
                            self.notifier(f"🎛 Profil EQ : {PROFILS_EQ[idx_p][0]}")
                            return False
                    for idx_c in range(len(self.eq_profils_perso)):
                        zc = self._zones_clic.get(f"eq_custom:{idx_c}")
                        if zc and zc[0] <= cx <= zc[2] and zc[1] <= cy <= zc[3]:
                            pr = self.eq_profils_perso[idx_c]
                            self.eq_bandes = list(pr["bandes"])
                            self.eq_perso_actif = True
                            self.appliquer_egaliseur_courant()
                            self.sauvegarder_etat_cli()
                            self.notifier(f"★ Profil EQ perso : {pr.get('nom')}")
                            return False
                    z_tab = self._zones_clic.get("eq_tableau")
                    if z_tab and z_tab[0] <= cx <= z_tab[2] and z_tab[1] <= cy <= z_tab[3]:
                        col_debut = z_tab[0] + 10
                        w_cols = max(10, z_tab[2] - col_debut)
                        if cx >= col_debut:
                            b_cible = max(0, min(9, int((cx - col_debut) / w_cols * 10)))
                            self.eq_bande_selection = b_cible
                            ratio_y = (cy - z_tab[1]) / max(1, z_tab[3] - z_tab[1])
                            gain_cible = round(max(-12.0, min(12.0, (0.5 - ratio_y) * 28.0)))
                            self.eq_perso_actif = True
                            self.eq_bandes[b_cible] = float(gain_cible)
                            self.appliquer_egaliseur_courant()
                            self.sauvegarder_etat_cli()
            return False

        # 11. Recherche plein-texte dans les paroles ([:] / [Ctrl+K])
        if self.paroles_recherche_ouverte:
            if self.paroles_recherche_saisie:
                if touche == "ECHAP":
                    if self.paroles_recherche_resultats:
                        self.paroles_recherche_saisie = False
                    else:
                        self.paroles_recherche_ouverte = False
                elif touche == "ENTREE":
                    self.paroles_recherche_saisie = False
                    self.executer_recherche_paroles(self.paroles_recherche_requete)
                else:
                    nouv = appliquer_touche_saisie(touche, self.paroles_recherche_requete)
                    if nouv is not None:
                        self.paroles_recherche_requete = nouv
                        if len(self.paroles_recherche_requete.strip()) >= 3:
                            self.executer_recherche_paroles(self.paroles_recherche_requete)
                return False

            nb_pr = len(self.paroles_recherche_resultats)
            if touche in ("ECHAP", "q", "Q", ":", "CTRL_K"):
                self.paroles_recherche_ouverte = False
            elif touche in ("/", "i"):
                self.paroles_recherche_saisie = True
            elif touche in ("HAUT", "k") and nb_pr:
                self.paroles_recherche_index = (self.paroles_recherche_index - 1) % nb_pr
            elif touche in ("BAS", "j") and nb_pr:
                self.paroles_recherche_index = (self.paroles_recherche_index + 1) % nb_pr
            elif touche == "K":
                paroles.recuperer_tout()
                self.notifier("📚 Indexation des paroles de toute la bibliothèque lancée en arrière-plan...")
            elif touche == "ENTREE" and nb_pr:
                res = self.paroles_recherche_resultats[self.paroles_recherche_index]
                pid = res.get("id")
                t_cible = res.get("t")
                p_cible = next((p for p in self.pistes if p.get("id") == pid), None)
                if p_cible:
                    self.paroles_recherche_ouverte = False
                    self.jouer_piste(p_cible)
                    if t_cible is not None:
                        def _sauter_au_passage(t_dest: float):
                            time.sleep(0.18)
                            self.lecteur.aller_a(max(0.0, float(t_dest)))
                            self.mpris.emettre_seeked(self.lecteur.position)

                        threading.Thread(
                            target=_sauter_au_passage,
                            args=(float(t_cible),),
                            daemon=True,
                        ).start()
                        self.notifier(
                            f"🎙 Saut direct à {int(t_cible)//60:02d}:{int(t_cible)%60:02d} — « {res.get('ligne', '')[:42]} »"
                        )
            return False

        # 12. Inspecteur Propriétés & Codec ([Maj+I])
        if self.proprietes_ouvertes:
            if touche in ("ECHAP", "I", "ENTREE", "q", "Q"):
                self.proprietes_ouvertes = False
            elif touche in ("T", "t"):
                self.proprietes_ouvertes = False
                self.ouvrir_editeur_tags()
            elif touche in ("CTRL_L", "F4"):
                self.proprietes_ouvertes = False
                self.ouvrir_studio_paroles()
            return False

        # 13. Éditeur de Tags & Lookup iTunes ([Maj+T])
        if self.tags_ouvert:
            cles_tags = [
                "titre",
                "artiste",
                "album",
                "artiste_album",
                "annee",
                "genre",
                "numero",
            ]
            if self.tags_mode == "saisie":
                if touche == "ECHAP":
                    self.tags_mode = "champs"
                elif touche == "ENTREE":
                    cle_c = cles_tags[self.tags_champ_index]
                    self.tags_champs[cle_c] = self.tags_saisie_Tampon.strip()
                    self.tags_mode = "champs"
                else:
                    nouv = appliquer_touche_saisie(touche, self.tags_saisie_Tampon)
                    if nouv is not None:
                        self.tags_saisie_Tampon = nouv
                return False

            if self.tags_mode == "pochette":
                nb_ph = len(self.photos_disponibles)
                if touche == "ECHAP":
                    self.tags_mode = "champs"
                elif touche in ("HAUT", "k", "K") and nb_ph:
                    self.tags_galerie_index = (self.tags_galerie_index - 1) % nb_ph
                elif touche in ("BAS", "j", "J") and nb_ph:
                    self.tags_galerie_index = (self.tags_galerie_index + 1) % nb_ph
                elif touche == "ENTREE" and nb_ph:
                    nom_ph, ch_ph = self.photos_disponibles[self.tags_galerie_index]
                    self.tags_pochette_locale = ch_ph
                    self.tags_itunes_choisi = None
                    self.tags_mode = "champs"
                    self.notifier(f"🖼 Pochette choisie : {nom_ph} — appuie sur [S] pour enregistrer !")
                return False

            if self.tags_mode == "itunes":
                nb_it = min(12, len(self.tags_itunes_resultats))
                if touche == "ECHAP":
                    self.tags_mode = "champs"
                elif touche in ("HAUT", "k", "K") and nb_it:
                    self.tags_itunes_index = (self.tags_itunes_index - 1) % nb_it
                elif touche in ("BAS", "j", "J") and nb_it:
                    self.tags_itunes_index = (self.tags_itunes_index + 1) % nb_it
                elif touche == "ENTREE" and nb_it:
                    choisi = self.tags_itunes_resultats[self.tags_itunes_index]
                    for c in cles_tags:
                        if choisi.get(c) is not None and str(choisi.get(c)).strip():
                            self.tags_champs[c] = str(choisi[c]).strip()
                    self.tags_itunes_choisi = choisi.get("itunes") or choisi.get("itunes_id")
                    self.tags_pochette_locale = None
                    self.tags_mode = "champs"
                    self.notifier("🍎 Tags + pochette HD iTunes prêts — appuie sur [S] pour enregistrer !")
                return False

            if touche in ("ECHAP", "T", "q", "Q"):
                self.tags_ouvert = False
            elif touche in ("HAUT", "k") and cles_tags:
                self.tags_champ_index = (self.tags_champ_index - 1) % len(cles_tags)
            elif touche in ("BAS", "j") and cles_tags:
                self.tags_champ_index = (self.tags_champ_index + 1) % len(cles_tags)
            elif touche == "ENTREE":
                cle_c = cles_tags[self.tags_champ_index]
                self.tags_saisie_Tampon = self.tags_champs.get(cle_c, "")
                self.tags_mode = "saisie"
            elif touche in ("c", "C"):
                self.scanner_photos_disponibles()
                self.tags_galerie_index = 0
                self.tags_mode = "pochette"
            elif touche in ("i", "I"):
                self.lancer_lookup_itunes_tags()
            elif touche in ("s", "S"):
                self.sauvegarder_tags_piste()
            return False

        # 14. Clic souris (SGR 1006) via zones dynamiques exactes
        if touche.startswith("CLIC:"):
            try:
                _, s_x, s_y = touche.split(":")
                x, y = int(s_x), int(s_y)
                maintenant = time.time()
                est_double = (
                    (maintenant - self._dernier_clic[0]) < 0.45
                    and abs(self._dernier_clic[1] - x) <= 1
                    and abs(self._dernier_clic[2] - y) <= 1
                )
                self._dernier_clic = (maintenant, x, y)

                def _dans(nom: str) -> tuple[int, int, int, int] | None:
                    z = self._zones_clic.get(nom)
                    if z and z[0] <= x <= z[2] and z[1] <= y <= z[3]:
                        return z
                    return None

                # En-tête : sélecteur de vues & actions rapides cliquables
                for nom_z in list(self._zones_clic):
                    if nom_z.startswith("vue:") and _dans(nom_z):
                        self.mode_vue = nom_z.split(":", 1)[1]
                        self.sauvegarder_etat_cli()
                        return False
                if _dans("hdr_theme") or _dans("foot_theme"):
                    self.cycler_theme()
                    return False
                if _dans("hdr_palette") or _dans("foot_palette"):
                    self.ouvrir_palette_commandes()
                    return False
                if _dans("hdr_reglages") or _dans("foot_reglages"):
                    self.ouvrir_reglages()
                    return False
                if _dans("hdr_eq") or _dans("foot_eq"):
                    self.ouvrir_eq_10_bandes()
                    return False
                if _dans("hdr_dsp") or _dans("ctrl_dsp") or _dans("foot_dsp"):
                    self.cycler_effet_dsp()
                    return False
                if _dans("hdr_mute"):
                    self.basculer_muet()
                    return False
                if _dans("foot_accueil"):
                    self.mode_vue = "scinde" if self.mode_vue == "accueil" else "accueil"
                    self.sauvegarder_etat_cli()
                    return False
                if _dans("foot_paroles"):
                    self.ouvrir_studio_paroles()
                    return False
                if _dans("foot_vis"):
                    self.cycler_visualiseur()
                    return False
                if _dans("foot_yt"):
                    self._fermer_toutes_modales()
                    self.yt_ouvert = True
                    if not self.yt_resultats:
                        self.yt_saisie_active = True
                    return False
                if _dans("foot_radio"):
                    self.lancer_radio_piste()
                    return False
                if _dans("foot_m3u"):
                    self.exporter_playlist_m3u()
                    return False
                if _dans("foot_aide"):
                    self.aide_ouverte = True
                    return False

                # Jauge de volume cliquable intégrée au transport
                z_vol = _dans("ctrl_vol_barre")
                if z_vol:
                    w_v = max(1, z_vol[2] - z_vol[0])
                    pct_v = max(0.0, min(1.0, (x - z_vol[0]) / w_v))
                    nouv_v = round(pct_v * 100.0)
                    if self.lecteur.mute:
                        self.lecteur.definir_muet(False)
                    self.lecteur.definir_volume(nouv_v)
                    self.mpris.notifier_changement(["Volume"])
                    self.notifier(f"🔊 Volume : {nouv_v}%")
                    return False

                # Clics dans la Vue Accueil (reprise, étagères, mixes)
                if self.mode_vue == "accueil" and self._accueil_zones:
                    for x0, y0, x1, y1, kind, payload in self._accueil_zones:
                        if x0 <= x <= x1 and y0 <= y <= y1:
                            if kind == "reprise" and payload:
                                self.jouer_piste(payload)
                            elif kind == "piste":
                                idx_sec, idx_it, piste_c = payload
                                self.accueil_section = idx_sec
                                self.accueil_index = idx_it
                                self.jouer_piste(piste_c)
                            elif kind == "mix":
                                idx_m, mx_item = payload
                                self.accueil_section = 4
                                self.accueil_index = idx_m
                                ps = list(mx_item.get("pistes") or [])
                                if ps:
                                    random.shuffle(ps)
                                    self.file_attente = ps[1:]
                                    self.jouer_piste(ps[0])
                                    self.notifier(f"🎧 Mix « {mx_item.get('nom')} » lancé !")
                            return False

                # Contrôles de transport & barre rapide cliquables
                actions_ctrl = (
                    "ctrl_prev",
                    "ctrl_play",
                    "ctrl_next",
                    "ctrl_shuffle",
                    "ctrl_repeat",
                    "ctrl_dj",
                    "ctrl_fav",
                    "ctrl_vis",
                    "ctrl_mute",
                    "ctrl_mute_pct",
                )
                for c_nom in actions_ctrl:
                    if _dans(c_nom):
                        if c_nom == "ctrl_prev":
                            self.piste_precedente()
                        elif c_nom == "ctrl_play":
                            if self.lecteur.fichier_actuel is None and self.pistes_filtrees:
                                sel = self.pistes_filtrees[
                                    max(0, min(self.index_selection, len(self.pistes_filtrees) - 1))
                                ]
                                self.jouer_piste(sel)
                            elif self.lecteur.fichier_actuel is None and self.piste_courante:
                                self.jouer_piste(self.piste_courante)
                            else:
                                self.lecteur.basculer_pause()
                                self.mpris.notifier_changement(["PlaybackStatus"])
                        elif c_nom == "ctrl_next":
                            self.piste_suivante()
                        elif c_nom == "ctrl_shuffle":
                            self.mode_aleatoire = not self.mode_aleatoire
                            self.sauvegarder_etat_cli()
                            self.mpris.notifier_changement(["Shuffle"])
                            self.notifier(
                                f"🔀 Aléatoire : {'Activé' if self.mode_aleatoire else 'Désactivé'}"
                            )
                        elif c_nom == "ctrl_repeat":
                            cycles = ["non", "tout", "un"]
                            self.mode_repetition = cycles[
                                (cycles.index(self.mode_repetition) + 1) % len(cycles)
                            ]
                            self.sauvegarder_etat_cli()
                            self.mpris.notifier_changement(["LoopStatus"])
                            self.notifier(f"🔁 Répétition : {self.mode_repetition.upper()}")
                        elif c_nom == "ctrl_dj":
                            self.auto_dj = not self.auto_dj
                            self.sauvegarder_etat_cli()
                            self.notifier(
                                f"🎧 Auto-DJ : {'Activé' if self.auto_dj else 'Désactivé'}"
                            )
                        elif c_nom == "ctrl_fav":
                            if self.piste_courante and not self.piste_courante.get("_type"):
                                self.basculer_favori_selection() if (
                                    self.pistes_filtrees
                                    and 0 <= self.index_selection < len(self.pistes_filtrees)
                                    and self.pistes_filtrees[self.index_selection].get("id")
                                    == self.piste_courante.get("id")
                                ) else (
                                    bibliotheque.basculer_favori(self.piste_courante["id"]),
                                    self.recharger_bibliotheque(),
                                )
                        elif c_nom == "ctrl_vis":
                            self.cycler_visualiseur()
                        elif c_nom in ("ctrl_mute", "ctrl_mute_pct"):
                            self.basculer_muet()
                        return False

                # Onglets [1..9] + Genres
                for nom_z in list(self._zones_clic):
                    if nom_z.startswith("tab:") and _dans(nom_z):
                        self.mode_onglet = nom_z.split(":", 1)[1]
                        self.filtrer_pistes()
                        return False

                # Boutons de sous-vue (Retour / Tout lire / Aléatoire)
                if _dans("sub_retour"):
                    self.playlist_ouverte = None
                    self.artiste_ouvert = None
                    self.album_ouvert = None
                    self.dossier_ouvert = None
                    self.genre_ouvert = None
                    self.filtrer_pistes()
                    return False
                if _dans("sub_tout"):
                    self.jouer_collection(aleatoire=False)
                    return False
                if _dans("sub_alea"):
                    self.jouer_collection(aleatoire=True)
                    return False

                # Pilule tri ⇅
                if _dans("liste_tri"):
                    self.cycler_tri()
                    return False

                # Barre de contexte / filtre
                if _dans("liste_barre"):
                    dans_sous_vue = (
                        (self.mode_onglet == "playlists" and self.playlist_ouverte)
                        or (self.mode_onglet == "artistes" and self.artiste_ouvert)
                        or (self.mode_onglet == "albums" and self.album_ouvert)
                        or (self.mode_onglet == "dossiers" and self.dossier_ouvert)
                        or (self.mode_onglet == "genres" and self.genre_ouvert)
                    )
                    if dans_sous_vue and x <= 9:
                        self.playlist_ouverte = None
                        self.artiste_ouvert = None
                        self.album_ouvert = None
                        self.dossier_ouvert = None
                        self.genre_ouvert = None
                        self.filtrer_pistes()
                    else:
                        self.recherche_active = True
                    return False

                # Sélection / lecture dans la liste
                if _dans("liste_items"):
                    nb = len(self.pistes_filtrees)
                    idx = self._liste_debut + (y - self._liste_y_debut)
                    if 0 <= idx < nb:
                        if self.index_selection == idx or est_double:
                            self.index_selection = idx
                            self.jouer_piste(self.pistes_filtrees[idx])
                        else:
                            self.index_selection = idx
                    return False

                # Seek sur barre de progression
                z_prog = _dans("barre_prog")
                if z_prog:
                    w_b = max(1, z_prog[2] - z_prog[0])
                    pct = max(0.0, min(1.0, (x - z_prog[0]) / w_b))
                    est_rad = bool(
                        self.piste_courante
                        and self.piste_courante.get("_type") == "radio"
                    )
                    dur = self.lecteur.duree or (
                        float(self.piste_courante.get("duree") or 0.0)
                        if self.piste_courante
                        else 0.0
                    )
                    if dur > 0 and not est_rad:
                        self.lecteur.aller_a(pct * dur)
                        self.mpris.emettre_seeked(self.lecteur.position)
                    return False

                # Clic exact sur une ligne de paroles enroulée (_paroles_lignes_ecran)
                for y_par, t_par in self._paroles_lignes_ecran:
                    if y_par == y:
                        cible_t = max(0.0, t_par - self.decalage_paroles)
                        self.lecteur.aller_a(cible_t)
                        self.mpris.emettre_seeked(self.lecteur.position)
                        return False
                return False
            except (ValueError, IndexError):
                return False

        # 15. Barre de filtre actif ([/])
        if self.recherche_active:
            if touche == "ECHAP":
                self.recherche_active = False
            elif touche == "ENTREE":
                self.recherche_active = False
                if self.mode_onglet == "radios" and self.terme_recherche.strip():
                    self.lancer_recherche_radios(self.terme_recherche.strip())
            elif touche == "BAS":
                if self.pistes_filtrees:
                    self.index_selection = (
                        self.index_selection + 1
                    ) % len(self.pistes_filtrees)
            elif touche == "HAUT":
                if self.pistes_filtrees:
                    self.index_selection = (
                        self.index_selection - 1
                    ) % len(self.pistes_filtrees)
            else:
                nouv = appliquer_touche_saisie(touche, self.terme_recherche)
                if nouv is not None:
                    self.terme_recherche = nouv
                    self.filtrer_pistes()
            return False

        if touche in ("q", "Q"):
            return True

        # Collage direct de paroles .lrc quand aucune modale de saisie n'est ouverte
        if touche.startswith("PASTE:"):
            texte_colle = touche[6:].strip()
            cible = self._piste_locale_cible()
            if texte_colle and cible and cible.get("id"):
                try:
                    paroles.importer(int(cible["id"]), texte_colle)
                    if self.piste_courante and self.piste_courante.get("id") == cible["id"]:
                        self.charger_paroles_async(int(cible["id"]), forcer=False)
                    self.notifier(f"🎙 Paroles importées sur « {cible.get('titre')} »")
                except Exception as ex:  # noqa: BLE001
                    self.notifier(f"Erreur collage paroles : {ex}")
            return False

        # 16. Navigation dédiée dans la Vue Accueil ([F3])
        if self.mode_vue == "accueil" and touche in (
            "HAUT", "BAS", "GAUCHE", "DROITE", "k", "j", "h", "ENTREE", "ALT_ENTREE", "a", "A", "r", "R", "ECHAP"
        ):
            donnees_a = self._accueil_donnees or self.preparer_donnees_accueil()
            sections_a = donnees_a.get("sections") or []
            mixes_a = donnees_a.get("mixes") or []
            if touche == "ECHAP":
                self.mode_vue = "scinde"
                self.sauvegarder_etat_cli()
                return False
            if touche in ("r", "R"):
                self.accueil_graine = int(time.time() * 1000) % 1000000
                self.preparer_donnees_accueil()
                self.notifier("🎲 Étagère « À redécouvrir » rafraîchie !")
                return False
            if touche == "ALT_ENTREE":
                if self.pistes:
                    tous = list(self.pistes)
                    random.shuffle(tous)
                    self.file_attente = tous[1:]
                    self.jouer_piste(tous[0])
                    self.notifier(f"🔀 Lecture aléatoire lancée ({len(tous)} titres)")
                return False
            if touche in ("GAUCHE", "h"):
                self.accueil_section = (self.accueil_section - 1) % 5
                self.accueil_index = 0
                return False
            if touche == "DROITE":
                self.accueil_section = (self.accueil_section + 1) % 5
                self.accueil_index = 0
                return False
            if self.accueil_section < 4 and sections_a:
                items_s = sections_a[self.accueil_section][1]
                nb_s = len(items_s)
                if touche in ("HAUT", "k") and nb_s:
                    self.accueil_index = (self.accueil_index - 1) % nb_s
                elif touche in ("BAS", "j") and nb_s:
                    self.accueil_index = (self.accueil_index + 1) % nb_s
                elif touche == "ENTREE" and nb_s:
                    cible_a = items_s[max(0, min(self.accueil_index, nb_s - 1))]
                    self.jouer_piste(cible_a)
                elif touche in ("a", "A") and nb_s:
                    cible_a = items_s[max(0, min(self.accueil_index, nb_s - 1))]
                    self.file_attente.append(cible_a)
                    self.notifier(f"➕ Ajouté à la file : {cible_a.get('titre')}")
                return False
            if self.accueil_section == 4 and mixes_a:
                nb_m = len(mixes_a)
                if touche in ("HAUT", "k"):
                    self.accueil_index = (self.accueil_index - 1) % nb_m
                elif touche in ("BAS", "j"):
                    self.accueil_index = (self.accueil_index + 1) % nb_m
                elif touche == "ENTREE":
                    mx = mixes_a[max(0, min(self.accueil_index, nb_m - 1))]
                    ps = list(mx.get("pistes") or [])
                    if ps:
                        random.shuffle(ps)
                        self.file_attente = ps[1:]
                        self.jouer_piste(ps[0])
                        self.notifier(f"🎧 Mix « {mx.get('nom')} » lancé ({len(ps)} titres)")
                return False

        nb = len(self.pistes_filtrees)
        if touche in ("HAUT", "k"):
            if nb:
                self.index_selection = (self.index_selection - 1) % nb
        elif touche in ("BAS", "j", "J"):
            if nb:
                self.index_selection = (self.index_selection + 1) % nb
        elif touche == "PAGE_HAUT":
            if nb:
                self.index_selection = max(0, self.index_selection - 10)
        elif touche == "PAGE_BAS":
            if nb:
                self.index_selection = min(nb - 1, self.index_selection + 10)
        elif touche == "DEBUT":
            self.index_selection = 0
        elif touche == "FIN":
            if nb:
                self.index_selection = nb - 1
        elif touche == "ALT_ENTREE":
            self.jouer_collection(aleatoire=False)
        elif touche == "ENTREE":
            if nb and 0 <= self.index_selection < nb:
                self.jouer_piste(self.pistes_filtrees[self.index_selection])
        elif touche in ("RETOUR", "ECHAP"):
            if self.terme_recherche:
                self.terme_recherche = ""
                if self.mode_onglet == "radios":
                    self.radios_recherche_resultats = []
                self.filtrer_pistes()
            elif self.mode_onglet == "playlists" and self.playlist_ouverte:
                self.playlist_ouverte = None
                self.filtrer_pistes()
            elif self.mode_onglet == "artistes" and self.artiste_ouvert:
                self.artiste_ouvert = None
                self.filtrer_pistes()
            elif self.mode_onglet == "albums" and self.album_ouvert:
                self.album_ouvert = None
                self.filtrer_pistes()
            elif self.mode_onglet == "dossiers" and self.dossier_ouvert:
                self.dossier_ouvert = None
                self.filtrer_pistes()
            elif self.mode_onglet == "genres" and self.genre_ouvert:
                self.genre_ouvert = None
                self.filtrer_pistes()
            elif self.mode_onglet == "radios" and self.radios_recherche_resultats:
                self.radios_recherche_resultats = []
                self.filtrer_pistes()
        elif touche == "ESPACE":
            if self.lecteur.fichier_actuel is None and self.piste_courante:
                pos_rep = (
                    self.derniere_position
                    if (
                        self.reprendre_position
                        and self.derniere_position > 5.0
                        and self.piste_courante.get("id") == self.dernier_id_sauvegarde
                        and float(self.piste_courante.get("duree") or 0.0)
                        > self.derniere_position + 5.0
                    )
                    else 0.0
                )
                self.jouer_piste(self.piste_courante, position_initiale=pos_rep)
            elif self.lecteur.fichier_actuel is None and nb and 0 <= self.index_selection < nb:
                self.jouer_piste(self.pistes_filtrees[self.index_selection])
            else:
                self.lecteur.basculer_pause()
                self.mpris.notifier_changement(["PlaybackStatus"])
        elif touche in ("GAUCHE", "h", "H"):
            self.lecteur.reculer(5.0)
            self.mpris.emettre_seeked(self.lecteur.position)
        elif touche == "DROITE":
            self.lecteur.avancer(5.0)
            self.mpris.emettre_seeked(self.lecteur.position)
        elif touche in ("SHIFT_HAUT", "("):
            self.deplacer_entree_liste(-1)
        elif touche in ("SHIFT_BAS", ")"):
            self.deplacer_entree_liste(+1)
        elif touche in ("n", "N"):
            self.ouvrir_creation_playlist()
        elif touche == "F2":
            self.renommer_playlist_selection()
        elif touche in ("p", "P"):
            self.ouvrir_ajout_playlist()
        elif touche in (">", "."):
            self.piste_suivante()
        elif touche == "<":
            self.piste_precedente()
        elif touche == ",":
            self.marquer_boucle_a()
        elif touche == ";":
            self.marquer_ou_effacer_boucle_b()
        elif touche in (":", "CTRL_K"):
            self.ouvrir_recherche_paroles()
        elif touche == "F3":
            self.mode_vue = "scinde" if self.mode_vue == "accueil" else "accueil"
            self.sauvegarder_etat_cli()
            self.notifier(
                "✦ Vue Accueil & Découverte Studio"
                if self.mode_vue == "accueil"
                else "◫ Vue Scindée restaurée"
            )
        elif touche == "F11":
            self.cycler_effet_dsp()
        elif touche == "CTRL_X":
            self.lancer_radio_piste()
        elif touche == "CTRL_U":
            self.exporter_playlist_m3u()
        elif touche in ("CTRL_P", "F1"):
            self.ouvrir_palette_commandes()
        elif touche in ("CTRL_L", "F4"):
            self.ouvrir_studio_paroles()
        elif touche in ("CTRL_G", "F7", "F10"):
            self.ouvrir_reglages()
        elif touche in ("CTRL_D", "F8"):
            self.ouvrir_doublons()
        elif touche == "CTRL_R":
            self.scanner_bibliotheque_cli(False)
        elif touche in ("y", "Y"):
            self.yt_ouvert = not self.yt_ouvert
            if self.yt_ouvert:
                self._fermer_toutes_modales()
                self.yt_ouvert = True
                if not self.yt_resultats:
                    self.yt_saisie_active = True
        elif touche == "I":
            self.ouvrir_proprietes_selection()
        elif touche == "i":
            self.mini_mode = not self.mini_mode
            self.notifier(
                "🪟 Mode Mini-Barre activé ([i] pour agrandir)"
                if self.mini_mode
                else "🖥 Mode complet restauré"
            )
        elif touche in ("+", "="):
            self.lecteur.ajuster_volume(+5.0)
            self.mpris.notifier_changement(["Volume"])
            self.notifier(f"🔊 Volume : {int(self.lecteur.volume)}%")
        elif touche in ("-", "_"):
            self.lecteur.ajuster_volume(-5.0)
            self.mpris.notifier_changement(["Volume"])
            self.notifier(f"🔊 Volume : {int(self.lecteur.volume)}%")
        elif touche in ("#", "F9"):
            self.basculer_muet()
        elif touche == "CTRL_A":
            self.jouer_selection_ensuite()
        elif touche in ("a", "A"):
            self.ajouter_selection_file()
        elif touche in ("x", "X", "SUPPR"):
            if (
                self.mode_onglet == "playlists"
                and not self.playlist_ouverte
                and self.pistes_filtrees
            ):
                sel = self.pistes_filtrees[self.index_selection]
                pl = sel.get("_playlist")
                if pl and pl.get("id"):
                    bibliotheque.supprimer_playlist(pl["id"])
                    self.recharger_bibliotheque()
                    self.notifier(f"🗑 Playlist supprimée : {pl.get('nom')}")
            elif (self.mode_onglet == "playlists" and self.playlist_ouverte) or self.mode_onglet == "file":
                self.retirer_selection_liste()
            else:
                self.retirer_selection_file()
        elif touche in ("c", "C") and self.mode_onglet == "file":
            self.file_attente.clear()
            self.filtrer_pistes()
            self.notifier("⏳ File d'attente vidée")
        elif touche in ("c", "C"):
            self.aller_a_piste_courante()
        elif touche in ("f", "F"):
            self.basculer_favori_selection()
        elif touche == "S":
            self.ouvrir_statistiques()
        elif touche == "s":
            self.mode_aleatoire = not self.mode_aleatoire
            self.sauvegarder_etat_cli()
            self.mpris.notifier_changement(["Shuffle"])
            self.notifier(
                f"🔀 Aléatoire : {'Activé' if self.mode_aleatoire else 'Désactivé'} (Maj+S pour Statistiques)"
            )
        elif touche == "!":
            self.auto_dj = not self.auto_dj
            self.sauvegarder_etat_cli()
            self.notifier(
                f"🎧 Auto-DJ intelligent : {'Activé' if self.auto_dj else 'Désactivé'}"
            )
        elif touche in ("$", "*"):
            self.ouvrir_statistiques()
        elif touche in ("r", "R"):
            cycles = ["non", "tout", "un"]
            self.mode_repetition = cycles[
                (cycles.index(self.mode_repetition) + 1) % len(cycles)
            ]
            self.sauvegarder_etat_cli()
            self.mpris.notifier_changement(["LoopStatus"])
            self.notifier(f"🔁 Répétition : {self.mode_repetition.upper()}")
        elif touche in ("b", "B"):
            self.cycler_mode_fond()
        elif touche in ("g", "G"):
            self.scanner_photos_disponibles()
            self.galerie_ouverte = not self.galerie_ouverte
        elif touche in ("o", "O"):
            self.cycler_luminosite_fond()
        elif touche in ("CTRL_O", "F6"):
            self.cycler_tri()
        elif touche in ("m", "M"):
            self.cycler_rendu_fond()
        elif touche == "T":
            self.ouvrir_editeur_tags()
        elif touche == "t":
            self.cycler_theme()
        elif touche == "F5":
            self.cycler_visualiseur()
        elif touche == "E":
            self.ouvrir_eq_10_bandes()
        elif touche == "e":
            self.cycler_egaliseur()
        elif touche in ("u", "U"):
            self.basculer_normalisation()
        elif touche in ("d", "D"):
            self.cycler_fondu()
        elif touche in ("v", "V"):
            self.cycler_vitesse()
            self.mpris.notifier_changement(["Rate"])
        elif touche in ("z", "Z"):
            self.cycler_veille()
        elif touche == "?":
            self.aide_ouverte = not self.aide_ouverte
        elif touche == "SHIFT_TAB":
            onglets_codes = [
                "titres", "favoris", "playlists", "artistes",
                "albums", "radios", "file", "recents", "dossiers", "genres",
            ]
            idx_o = (
                onglets_codes.index(self.mode_onglet)
                if self.mode_onglet in onglets_codes
                else 0
            )
            self.mode_onglet = onglets_codes[(idx_o - 1) % len(onglets_codes)]
            self.filtrer_pistes()
        elif touche == "TAB":
            modes = ["scinde", "scene", "paroles", "liste", "accueil"]
            idx_m = modes.index(self.mode_vue) if self.mode_vue in modes else 0
            self.mode_vue = modes[(idx_m + 1) % len(modes)]
            self.sauvegarder_etat_cli()
            noms_v = {
                "accueil": "Vue Accueil & Découverte Studio",
                "scinde": "Vue Scindée (Bibliothèque + Lecteur)",
                "scene": "Mode Scène Plein Écran (Pochette HD + Paroles)",
                "paroles": "Karaoké Plein Écran",
                "liste": "Bibliothèque Plein Écran",
            }
            self.notifier(f"🖥 {noms_v[self.mode_vue]}")
        elif touche in ("w", "W"):
            self.mode_vue = "scinde" if self.mode_vue == "scene" else "scene"
            self.sauvegarder_etat_cli()
            self.notifier(
                "💿 Mode Scène Plein Écran (Pochette à gauche • Paroles à droite)"
                if self.mode_vue == "scene"
                else "🖥 Vue Scindée restaurée"
            )
        elif touche in ("l", "L"):
            self.mode_vue = (
                "scinde" if self.mode_vue == "paroles" else "paroles"
            )
            self.sauvegarder_etat_cli()
        elif touche == "K":
            if self.piste_courante and self.piste_courante.get("id"):
                self.charger_paroles_async(self.piste_courante["id"], forcer=True)
                self.notifier("🔄 Recherche des paroles relancée...")
        elif touche in ("/", "CTRL_F"):
            self.recherche_active = True
        elif touche == "1":
            self.mode_onglet = "titres"
            self.filtrer_pistes()
        elif touche == "2":
            self.mode_onglet = "favoris"
            self.filtrer_pistes()
        elif touche == "3":
            self.mode_onglet = "playlists"
            self.filtrer_pistes()
        elif touche == "4":
            self.mode_onglet = "artistes"
            self.filtrer_pistes()
        elif touche == "5":
            self.mode_onglet = "albums"
            self.filtrer_pistes()
        elif touche == "6":
            self.mode_onglet = "radios"
            self.filtrer_pistes()
        elif touche == "7":
            self.mode_onglet = "file"
            self.filtrer_pistes()
        elif touche == "8":
            self.mode_onglet = "recents"
            self.filtrer_pistes()
        elif touche == "9":
            self.mode_onglet = "dossiers"
            self.filtrer_pistes()
        elif touche in ("[", "{"):
            self.enregistrer_decalage_parole(-0.25)
            self.mpris.emettre_seeked(self.lecteur.position)
        elif touche in ("]", "}"):
            self.enregistrer_decalage_parole(+0.25)
            self.mpris.emettre_seeked(self.lecteur.position)
        elif touche == "0":
            self.enregistrer_decalage_parole(-self.decalage_paroles)
            self.mpris.emettre_seeked(self.lecteur.position)

        return False

    def executer(self, piste_demarrage: dict[str, Any] | None = None):
        if piste_demarrage:
            self.jouer_piste(piste_demarrage)
        elif self.pistes:
            p_init = self.pistes[0]
            if self.dernier_id_sauvegarde:
                for p in self.pistes:
                    if p.get("id") == self.dernier_id_sauvegarde:
                        p_init = p
                        break
            self.piste_courante = p_init
            # Restaurer le calage paroles mémorisé pour ce titre
            cle_dec = str(p_init.get("id") or p_init.get("chemin") or "")
            self.decalage_paroles = float(self.decalages_paroles.get(cle_dec, 0.0))
            self.actualiser_palette_et_fond()
            self.actualiser_normalisation_piste()
            self.mpris.notifier_changement(["Metadata"])
            if p_init.get("id"):
                self.charger_paroles_async(p_init["id"])

        dernier_save_pos = time.time()
        try:
            with LecteurClavier() as clavier, Live(
                self.generer_ecran(),
                console=self.console,
                auto_refresh=False,
                screen=True,
            ) as live:
                while self.lecteur.en_cours:
                    if self.lecteur.fichier_actuel and not self.lecteur.en_pause:
                        self.index_animation = (self.index_animation + 1) % 64
                        maintenant = time.time()
                        if maintenant - dernier_save_pos >= 15.0:
                            dernier_save_pos = maintenant
                            self.derniere_position = max(0.0, float(self.lecteur.position or 0.0))
                            self.sauvegarder_etat_cli()
                    self.verifier_veille()
                    self.verifier_boucle_ab()
                    self.verifier_mises_a_jour_arriere_plan()
                    self.appliquer_gain_et_fondu()

                    touches = clavier.lire_toutes()
                    doit_quitter = False
                    for t in touches:
                        if self.traiter_touche(t):
                            doit_quitter = True
                            break
                    if doit_quitter:
                        break

                    live.update(self.generer_ecran(), refresh=True)
                    self.synchroniser_pochette_hd()
                    en_lec_boucle = (
                        self.lecteur.fichier_actuel is not None
                        and not self.lecteur.en_pause
                    )
                    clavier.attendre(0.04 if en_lec_boucle else 0.085)
        finally:
            self.fermer_proprement()
            os._exit(0)


# ── Fonctions CLI auxiliaires (télécommande IPC, liste, paroles sans TUI) ────


def envoyer_commande_ipc(action: str, arg: str = "") -> dict[str, Any] | None:
    """Envoie une commande de contrôle ou de statut à l'instance Onde CLI en cours d'exécution."""
    if not os.path.exists(SOCKET_CTRL_CLI):
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.2)
            s.connect(SOCKET_CTRL_CLI)
            s.sendall(json.dumps({"action": action, "arg": arg}).encode("utf-8"))
            morceaux_b: list[bytes] = []
            while True:
                chunk = s.recv(8192)
                if not chunk:
                    break
                morceaux_b.append(chunk)
                if b"\n" in chunk:
                    break
            data = b"".join(morceaux_b)
            if data:
                return json.loads(data.decode("utf-8", errors="ignore"))
    except OSError:
        return None
    return None


def chercher_piste(terme: str) -> dict[str, Any] | None:
    """Cherche la meilleure correspondance (insensible aux accents) dans la bibliothèque Onde."""
    p_path = Path(terme).expanduser()
    if p_path.exists() and p_path.is_file():
        r = bibliotheque.requete(
            "SELECT id FROM pistes WHERE chemin=?", (str(p_path),), un=True
        )
        if r:
            return bibliotheque.piste(r["id"])
        ids = bibliotheque.importer([str(p_path)])
        if ids:
            return bibliotheque.piste(ids[0])
        return {
            "id": None,
            "titre": p_path.stem,
            "artiste": "Fichier local",
            "album": "",
            "duree": 0,
            "chemin": str(p_path),
        }

    pistes = bibliotheque.instantane().get("pistes", [])
    q = bibliotheque.sans_accents(terme).strip()
    mots = q.split()
    meilleur: tuple[int, dict[str, Any]] | None = None
    for p in pistes:
        titre = bibliotheque.sans_accents(p.get("titre") or "")
        artiste = bibliotheque.sans_accents(p.get("artiste") or "")
        album = bibliotheque.sans_accents(p.get("album") or "")
        texte = f"{titre} {artiste} {album}"
        score = 0
        if q == titre:
            score += 100
        elif q in titre:
            score += 60
        elif q in artiste:
            score += 40
        elif mots and all(m in texte for m in mots):
            score += 30
        elif mots and any(m in texte for m in mots):
            score += 10
        if score > 0 and (meilleur is None or score > meilleur[0]):
            meilleur = (score, p)

    return meilleur[1] if meilleur else None


def afficher_liste(filtre: str | None = None):
    """Affiche la liste des morceaux sous forme de beau tableau Rich avec badge qualité."""
    console = Console()
    pistes = bibliotheque.instantane().get("pistes", [])
    if filtre:
        q = bibliotheque.sans_accents(filtre).strip()
        pistes = [
            p
            for p in pistes
            if q in bibliotheque.sans_accents(p.get("titre") or "")
            or q in bibliotheque.sans_accents(p.get("artiste") or "")
            or q in bibliotheque.sans_accents(p.get("album") or "")
        ]

    table = Table(
        title=f"Bibliothèque Onde ({len(pistes)} morceaux)",
        box=box.ROUNDED,
        show_header=True,
        border_style="#38bdf8",
    )
    table.add_column("#", width=4, justify="right", style="#38bdf8")
    table.add_column("Titre", style="bold white", ratio=3)
    table.add_column("Artiste", style="#a5b4fc", ratio=2)
    table.add_column("Album", style="#94a3b8", ratio=2)
    table.add_column("Qualité", width=11, justify="center", style="#2dd4bf")
    table.add_column("Durée", width=7, justify="right", style="#94a3b8")

    for i, p in enumerate(pistes[:50], 1):
        dur_str = formater_duree(float(p.get("duree") or 0.0))
        table.add_row(
            str(i),
            p.get("titre") or "Sans titre",
            p.get("artiste") or "Inconnu",
            p.get("album") or "",
            badge_qualite_piste(p, complet=False),
            dur_str,
        )

    console.print(table)
    if len(pistes) > 50:
        console.print(
            f"[#94a3b8]... et {len(pistes) - 50} autres morceaux (précise ta recherche).[/#94a3b8]"
        )


def afficher_paroles_cli(terme: str):
    """Affiche les paroles d'un morceau dans le terminal."""
    console = Console()
    piste = chercher_piste(terme)
    if not piste:
        console.print(f"[bold red]Morceau non trouvé :[/bold red] {terme}")
        return

    pid = piste.get("id")
    if not pid:
        console.print("[yellow]Impossible de charger les paroles sans identifiant.[/yellow]")
        return

    console.print(
        f"[bold bright_cyan]Paroles pour :[/bold bright_cyan] {piste.get('titre')} — {piste.get('artiste')}\n"
    )
    donnees = paroles.paroles(pid)
    if not donnees:
        console.print("[#94a3b8]Aucune parole disponible.[/#94a3b8]")
        return

    synchro = donnees.get("synchro")
    if synchro:
        for item in synchro:
            t = float(item[0])
            txt = item[1]
            t_str = f"[{int(t)//60:02d}:{t%60:05.2f}]"
            console.print(f"[cyan]{t_str}[/cyan] [bold white]{txt}[/bold white]")
    elif donnees.get("texte"):
        console.print(donnees["texte"])
    else:
        console.print("[#94a3b8]Aucune parole trouvée.[/#94a3b8]")


# ── Point d'Entrée Principal ────────────────────────────────────────────────


def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    parser = argparse.ArgumentParser(
        prog="onde-cli",
        description=(
            "Onde Studio CLI — Lecteur de musique Liquid Glass dans le terminal (paroles mot-à-mot, "
            "FFT, égaliseur 10 bandes, radios live, éditeur de tags iTunes & télécommande IPC)"
        ),
    )
    parser.add_argument(
        "requete",
        nargs="?",
        default=None,
        help=(
            "Titre/artiste/fichier à jouer, ou commande télécommande : "
            "status, toggle, play, pause, next, prev, seek, vol, mute, info"
        ),
    )
    parser.add_argument(
        "valeur",
        nargs="?",
        default=None,
        help="Valeur pour les commandes télécommande (ex: onde-cli seek +10, onde-cli vol 80)",
    )
    parser.add_argument(
        "--waybar",
        action="store_true",
        help="Sortie JSON formatée pour Waybar / Polybar / Caelestia avec 'onde-cli status --waybar'",
    )
    parser.add_argument(
        "--bg",
        "--fond",
        dest="fond",
        default=None,
        help="Chemin d'une photo de fond, ou 'pochette', 'aurore', 'off'",
    )
    parser.add_argument(
        "--theme",
        choices=ORDRE_THEMES,
        default=None,
        help="Thème Liquid Glass de démarrage",
    )
    parser.add_argument(
        "--view",
        choices=["accueil", "scinde", "scene", "paroles", "liste"],
        default=None,
        help="Vue initiale (accueil, scinde, scene, paroles, liste)",
    )
    parser.add_argument(
        "--list",
        "-l",
        nargs="?",
        const="",
        help="Affiche la liste des morceaux dans le terminal",
    )
    parser.add_argument(
        "--lyrics",
        nargs="?",
        const="",
        help="Affiche les paroles d'un morceau",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scanne la bibliothèque audio puis affiche le total et quitte",
    )
    parser.add_argument(
        "--shuffle",
        "-s",
        action="store_true",
        help="Démarre en mode aléatoire",
    )
    parser.add_argument(
        "--fullscreen-lyrics",
        action="store_true",
        help="Démarre directement en mode plein écran paroles",
    )
    parser.add_argument(
        "--scene",
        action="store_true",
        help="Démarre directement en mode Scène Plein Écran (Pochette HD + Paroles)",
    )
    parser.add_argument(
        "--mini",
        action="store_true",
        help="Démarre en mode Mini-Barre 5 lignes compact",
    )

    args = parser.parse_args()

    # Télécommande IPC si l'utilisateur invoque une sous-commande de contrôle
    commandes_ipc = {
        "status", "info", "toggle", "play", "pause",
        "next", "prev", "seek", "vol", "mute",
    }
    if args.requete and args.requete.lower() in commandes_ipc:
        cmd = args.requete.lower()
        rep = envoyer_commande_ipc(cmd, args.valeur or "")
        if rep is None:
            if args.waybar:
                print(json.dumps({"text": "", "alt": "stopped", "class": "stopped"}))
            else:
                print("Aucune instance Onde CLI active.")
            return
        if cmd in ("status", "info"):
            if args.waybar:
                st = str(rep.get("etat") or "stopped").lower()
                ic = "▶" if st == "playing" else ("⏸" if st == "paused" else "⏹")
                t_m = rep.get("titre") or "Onde"
                a_m = rep.get("artiste") or ""
                par = rep.get("parole") or ""
                txt_wb = f"{ic} {t_m} — {a_m}" + (f"  ♪ {par}" if par else "")
                tooltip = (
                    f"{t_m} — {a_m}\nAlbum : {rep.get('album', '—')}\n"
                    f"Volume : {'Muet' if rep.get('mute') else str(rep.get('volume', 100)) + '%'}"
                    + (f"\n🎙 {par}" if par else "")
                )
                print(
                    json.dumps(
                        {
                            "text": txt_wb,
                            "tooltip": tooltip,
                            "alt": st,
                            "class": st,
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                print(json.dumps(rep, ensure_ascii=False, indent=2))
        return

    if args.scan:
        bibliotheque.scanner(complet=False)
        nb = len(bibliotheque.instantane().get("pistes", []))
        print(f"Bibliothèque scannée : {nb} morceau(x).")
        return

    if args.list is not None:
        afficher_liste(args.list or None)
        return

    if args.lyrics is not None:
        cible = args.lyrics or args.requete
        if not cible:
            print("Spécifie un titre ou un artiste : onde-cli --lyrics \"titre\"")
            return
        afficher_paroles_cli(cible)
        return

    app = ApplicationOndeCLI()
    if args.shuffle:
        app.mode_aleatoire = True
    if args.theme:
        app.theme_code = args.theme
        app.actualiser_palette_et_fond()
    if args.view:
        app.mode_vue = args.view
    if args.fullscreen_lyrics:
        app.mode_vue = "paroles"
    if args.scene:
        app.mode_vue = "scene"
    if args.mini:
        app.mini_mode = True
    if args.fond:
        val = args.fond.strip()
        if val.lower() in ("off", "none", "aucun", "verre"):
            app.fond.mode_fond = "aucun"
        elif val.lower() in ("pochette", "cover", "auto"):
            app.fond.mode_fond = "pochette"
        elif val.lower() in ("aurore", "aurora"):
            app.fond.mode_fond = "aurore"
        else:
            p_bg = Path(val).expanduser()
            if p_bg.is_file():
                app.fond.mode_fond = "photo"
                app.fond.chemin_photo_perso = str(p_bg.resolve())
            else:
                app.notifier(f"Image introuvable : {val}")
        app.actualiser_palette_et_fond()

    piste_cible = None
    if args.requete:
        piste_cible = chercher_piste(args.requete)
        if not piste_cible:
            app.notifier(f"Aucune correspondance pour : {args.requete}")

    app.executer(piste_cible)


if __name__ == "__main__":
    main()
