#!/usr/bin/env bash
# ============================================================================
#  Ano Shell — 1-command bootstrap for Arch Linux ("no desktop" or Hyprland)
#  https://github.com/Abdoul273/ano-shell
#
#  Usage from a fresh Arch Linux TTY:
#    curl -fsSL https://raw.githubusercontent.com/Abdoul273/ano-shell/main/bootstrap.sh | bash
#  Optional flags (passed to ./install):
#    curl -fsSL .../bootstrap.sh | bash -s -- --lang en --profile auto
# ============================================================================

set -euo pipefail

REPO_URL="https://github.com/Abdoul273/ano-shell.git"
DEST="$HOME/.local/src/ano-shell"

# Detect system language (English by default unless French locale is set)
detect_lang() {
    local raw="${ANOSHELL_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}}"
    case "${raw,,}" in
        fr*) echo "fr" ;;
        *)   echo "en" ;;
    esac
}

UI_LANG="$(detect_lang)"
EXPLICIT_LANG=0
EXPLICIT_YES=0
PASSTHROUGH_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --lang)
            shift
            val="${1:-}"
            if [[ "$val" =~ ^(fr|en|auto)$ ]]; then
                [[ "$val" != "auto" ]] && UI_LANG="$val"
                EXPLICIT_LANG=1
                PASSTHROUGH_ARGS+=(--lang "$val")
            else
                echo "Invalid language / Langue invalide : $val (expected: en | fr | auto)" >&2
                exit 1
            fi
            ;;
        --lang=*)
            val="${1#*=}"
            if [[ "$val" =~ ^(fr|en|auto)$ ]]; then
                [[ "$val" != "auto" ]] && UI_LANG="$val"
                EXPLICIT_LANG=1
                PASSTHROUGH_ARGS+=("--lang=$val")
            else
                echo "Invalid language / Langue invalide : $val (expected: en | fr | auto)" >&2
                exit 1
            fi
            ;;
        --yes|-y)
            EXPLICIT_YES=1
            PASSTHROUGH_ARGS+=("$1")
            ;;
        *)
            PASSTHROUGH_ARGS+=("$1")
            ;;
    esac
    shift
done

msg() {
    local fr="$1" en="$2"
    if [[ "$UI_LANG" == "fr" ]]; then
        printf '%s\n' "$fr"
    else
        printf '%s\n' "$en"
    fi
}

if [[ $EUID -eq 0 ]]; then
    msg \
        "Ne lance pas ce script en root : lance-le depuis ton utilisateur normal (sudo sera demandé)." \
        "Do not run this script as root: run it as your regular user (sudo will be prompted)." >&2
    exit 1
fi

if ! command -v pacman >/dev/null 2>&1; then
    msg \
        "Ano Shell est conçu pour Arch Linux et dérivés (EndeavourOS, CachyOS, Manjaro, Garuda — pacman introuvable)." \
        "Ano Shell is designed for Arch Linux and derivatives (EndeavourOS, CachyOS, Manjaro, Garuda — pacman not found)." >&2
    exit 1
fi

# Bilingual language prompt on interactive TTY (unless --lang or --yes was passed)
if (( ! EXPLICIT_LANG && ! EXPLICIT_YES )) && { [[ -t 0 ]] || [[ -r /dev/tty ]]; }; then
    default_choice=1
    [[ "$UI_LANG" == "fr" ]] && default_choice=2
    printf "\n  Ano Shell — Language / Langue :\n"
    printf "    1) English%s\n" "$([[ $default_choice -eq 1 ]] && echo ' (default)')"
    printf "    2) Français%s\n" "$([[ $default_choice -eq 2 ]] && echo ' (par défaut)')"
    reply=""
    if [[ -t 0 ]]; then
        read -r -p "  Choice / Choix [${default_choice}]: " reply || true
    else
        read -r -p "  Choice / Choix [${default_choice}]: " reply </dev/tty || true
    fi
    case "${reply:-$default_choice}" in
        2|fr|FR|f|F) UI_LANG="fr" ;;
        *)           UI_LANG="en" ;;
    esac
    PASSTHROUGH_ARGS+=(--lang "$UI_LANG")
fi

msg \
    "==> Préparation de l'installation complète d'Ano Shell (Arch Linux / dérivés)" \
    "==> Preparing full Ano Shell installation (Arch Linux / derivatives)"
sudo -v

# Avoid GPG keyring errors on older Arch ISOs
sudo pacman -Sy --needed --noconfirm archlinux-keyring 2>/dev/null || true

if ! command -v git >/dev/null 2>&1 || ! pacman -Q base-devel >/dev/null 2>&1; then
    msg \
        "==> Installation de git et base-devel" \
        "==> Installing git and base-devel"
    sudo pacman -Syu --needed --noconfirm git base-devel
fi

mkdir -p "$(dirname "$DEST")"
if [[ -d "$DEST/.git" ]]; then
    msg \
        "==> Mise à jour du dépôt existant ($DEST)" \
        "==> Updating existing repository ($DEST)"
    git -C "$DEST" pull --ff-only
else
    rm -rf "$DEST"
    msg \
        "==> Clonage d'Ano Shell dans $DEST" \
        "==> Cloning Ano Shell into $DEST"
    git clone --depth 1 "$REPO_URL" "$DEST"
fi

if [[ ! -t 0 && -r /dev/tty ]]; then
    exec "$DEST/install" --full --yes "${PASSTHROUGH_ARGS[@]}" </dev/tty
fi
exec "$DEST/install" --full --yes "${PASSTHROUGH_ARGS[@]}"
