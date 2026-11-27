#!/usr/bin/env bash
# ============================================================================
#  Ano Shell — Add official binary Pacman repo & install ano-shell (EN / FR)
#  https://abdoul273.github.io/ano-shell/
#
#  Usage:
#    curl -fsSL https://abdoul273.github.io/ano-shell/add-repo.sh | bash
# ============================================================================

set -euo pipefail

raw_lang="${ANOSHELL_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}}"
UI_LANG="en"
[[ "${raw_lang,,}" == fr* ]] && UI_LANG="fr"
t() { [[ "$UI_LANG" == "fr" ]] && printf '%s' "$1" || printf '%s' "$2"; }

if [[ $EUID -eq 0 ]]; then
    echo "$(t "Ne lance pas ce script en root : utilise ton compte normal (sudo sera demandé)." "Do not run as root: run as your regular user (sudo will be prompted).")" >&2
    exit 1
fi

if ! command -v pacman >/dev/null 2>&1; then
    echo "$(t "Pacman introuvable : Ano Shell est conçu pour Arch Linux et dérivés." "pacman not found: Ano Shell is designed for Arch Linux and derivatives.")" >&2
    exit 1
fi

REPO_BLOCK=$'\n[ano-shell]\nSigLevel = Optional TrustAll\nServer = https://abdoul273.github.io/ano-shell/$arch\n'

if ! grep -q '^\[ano-shell\]' /etc/pacman.conf; then
    echo "==> $(t "Ajout du dépôt [ano-shell] dans /etc/pacman.conf" "Adding [ano-shell] repository to /etc/pacman.conf")"
    printf '%s' "$REPO_BLOCK" | sudo tee -a /etc/pacman.conf >/dev/null
else
    echo "==> $(t "Dépôt [ano-shell] déjà présent dans /etc/pacman.conf" "[ano-shell] repository already present in /etc/pacman.conf")"
fi

echo "==> $(t "Installation d'ano-shell depuis le dépôt binaire" "Installing ano-shell from binary repository")"
sudo pacman -Syu --needed --noconfirm ano-shell

echo "==> $(t "Déploiement des configurations utilisateur (ano-shell setup)" "Deploying user configurations (ano-shell setup)")"
if [[ ! -t 0 && -r /dev/tty ]]; then
    exec ano-shell setup "$@" </dev/tty
fi
exec ano-shell setup "$@"
