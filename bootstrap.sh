#!/usr/bin/env bash
# ============================================================================
#  Ano Shell — Bootstrap 1 commande pour Arch Linux (« no desktop » ou Hyprland)
#  https://github.com/Abdoul273/ano-shell
#
#  Usage depuis un TTY Arch Linux vierge :
#    curl -fsSL https://raw.githubusercontent.com/Abdoul273/ano-shell/main/bootstrap.sh | bash
# ============================================================================

set -euo pipefail

REPO_URL="https://github.com/Abdoul273/ano-shell.git"
DEST="$HOME/.local/src/ano-shell"

if [[ $EUID -eq 0 ]]; then
    echo "Ne lance pas ce script en root : lance-le depuis ton utilisateur normal (sudo sera demandé)." >&2
    exit 1
fi

if ! command -v pacman >/dev/null 2>&1; then
    echo "Ano Shell est conçu pour Arch Linux et dérivés (EndeavourOS, CachyOS, Manjaro, Garuda — pacman introuvable)." >&2
    exit 1
fi

echo "==> Préparation de l'installation complète d'Ano Shell (Arch Linux / dérivés)"
sudo -v

# Éviter les erreurs de clés GPG sur une ISO Arch ancienne
sudo pacman -Sy --needed --noconfirm archlinux-keyring 2>/dev/null || true

if ! command -v git >/dev/null 2>&1 || ! pacman -Q base-devel >/dev/null 2>&1; then
    echo "==> Installation de git et base-devel"
    sudo pacman -Syu --needed --noconfirm git base-devel
fi

mkdir -p "$(dirname "$DEST")"
if [[ -d "$DEST/.git" ]]; then
    echo "==> Mise à jour du dépôt existant ($DEST)"
    git -C "$DEST" pull --ff-only
else
    rm -rf "$DEST"
    echo "==> Clonage d'Ano Shell dans $DEST"
    git clone --depth 1 "$REPO_URL" "$DEST"
fi

if [[ ! -t 0 && -r /dev/tty ]]; then
    exec "$DEST/install" --full --yes "$@" </dev/tty
fi
exec "$DEST/install" --full --yes "$@"
