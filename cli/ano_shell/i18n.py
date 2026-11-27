"""Gestion bilingue FR/EN partagée pour la CLI `ano-shell`."""

from __future__ import annotations

import json
import os
from pathlib import Path

VALID_LANGS = ("auto", "en", "fr")


def _lang_file() -> Path:
    cfg = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    return cfg / "ano-shell" / "lang.json"


def get_lang_mode() -> str:
    """Retourne le mode enregistré dans lang.json ('auto', 'fr' ou 'en')."""
    try:
        data = json.loads(_lang_file().read_text(encoding="utf-8"))
        val = str(data.get("lang", "auto")).lower()
        if val in VALID_LANGS:
            return val
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return "auto"


def get_system_lang() -> str:
    """Détecte la langue du système ('fr' si locale fr_*, 'en' sinon)."""
    raw = os.getenv("LC_ALL") or os.getenv("LC_MESSAGES") or os.getenv("LANG") or "en"
    return "fr" if raw.lower().startswith("fr") else "en"


def get_lang() -> str:
    """Retourne la langue active effective ('fr' ou 'en')."""
    env = (os.getenv("ANOSHELL_LANG") or "").strip().lower()
    if env.startswith("fr"):
        return "fr"
    if env.startswith("en"):
        return "en"
    mode = get_lang_mode()
    if mode in ("fr", "en"):
        return mode
    return get_system_lang()


def is_fr() -> bool:
    return get_lang() == "fr"


def tr(fr: str, en: str) -> str:
    """Retourne `fr` si la langue active est le français, `en` sinon."""
    return fr if is_fr() else en


def set_lang(value: str) -> str:
    """Enregistre la langue ('auto', 'en' ou 'fr') dans ~/.config/ano-shell/lang.json."""
    val = value.strip().lower()
    if val not in VALID_LANGS:
        raise ValueError(
            tr(
                f"Langue invalide : {value} (attendu : auto | en | fr)",
                f"Invalid language: {value} (expected: auto | en | fr)",
            )
        )
    path = _lang_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lang": val}, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return val
