# Ano Shell

> **Bureau Liquid Glass 100 % autonome pour Arch Linux + Hyprland** — s'installe en **une seule commande** depuis un Arch Linux vierge (**« no desktop »**), sans aucune dépendance à `caelestia-shell`, `caelestia-cli`, `libcava`, `sndio` ni `aubio`.

[English version](README.md)

---

## Guide complet pour débutant (depuis zéro sur Arch Linux)

Tu viens d'installer Arch Linux (ou tu veux l'installer) et tu n'as jamais configuré Hyprland ? Suis simplement ces **4 étapes** :

### Étape 1 — Installer Arch Linux minimal (`archinstall`)
1. Démarre sur la clé USB Arch Linux et lance `archinstall`.
2. Choisis :
   - **Profile** → **`Minimal`** (ou **`No desktop`**)
   - **Audio** → **`PipeWire`**
   - **Network configuration** → **`Use NetworkManager`**
   - **User account** → crée ton compte utilisateur avec **`Superuser (sudo) = Yes`**
3. Lance l'installation puis redémarre et retire la clé USB.

### Étape 2 — Te connecter sur l'écran noir (TTY)
1. Tape ton **nom d'utilisateur** puis ton **mot de passe** (rien ne s'affiche quand tu tapes le mot de passe, c'est normal).
2. Si tu es en **Wi-Fi**, connecte-toi facilement avec :
   ```bash
   nmtui
   ```
   *(Choisis « Activate a connection », sélectionne ton Wi-Fi, tape le mot de passe, puis Quitter.)*
   *(En câble Ethernet, internet fonctionne déjà tout seul.)*

### Étape 3 — Lancer l'installation automatique en 1 commande
Tape cette unique commande puis appuie sur **Entrée** :

```bash
curl -fsSL https://raw.githubusercontent.com/Abdoul273/ano-shell/main/bootstrap.sh | bash
```

Entre ton mot de passe `sudo` quand demandé, puis laisse faire (~5 à 15 min selon ton PC et ta connexion).

**Tout est installé et configuré tout seul :**
- Hyprland, Wayland, audio PipeWire, Bluetooth, Wi-Fi, gestion d'énergie et **écran de connexion SDDM Liquid Glass** + curseur macOS.
- Plugins C++ Qt6 natifs (`AnoShell.*` + `AnoShell.Shapes`) compilés automatiquement (avec spectre audio FFT natif `fftw3` + PipeWire, sans `libcava`/`sndio`).
- **Tout le Liquid Glass iOS 27 / macOS** : Dynamic Island, Centre de contrôle, 14 popups gouttes de verre, Mission Control, Écran de verrouillage, **Nautilus + Sushi** (GTK4/3 + portail Ouvrir/Enregistrer en verre), **Qt/KDE Darkly**, **Kitty** (modulaire + terminal déroulant), **Fastfetch**, **Fish + Starship** (`eza`, `zoxide`).
- **`onde-cli`** : lecteur musique interactif dans le terminal avec paroles synchronisées dans la Dynamic Island.
- **Profil GPU/batterie automatique** (`ano-shell glass --auto`) : fluide même sur PC modeste 2 cœurs / Intel HD.

### Étape 4 — Redémarrer et profiter
Une fois terminé, tape simplement :

```bash
sudo reboot
```

Tu arrives directement sur ton **écran de connexion Liquid Glass**, puis sur ton bureau Hyprland + Ano Shell prêt à l'emploi.

---

## Raccourcis essentiels (tous préconfigurés)

Appuie sur **`Super + H`** à tout moment pour ouvrir l'aide interactive des raccourcis.

| Raccourci | Action |
| :--- | :--- |
| **`Super + Espace`** | Recherche Spotlight (goutte de verre) |
| **`Super + A`** | Centre de contrôle Liquid Glass (ou coin haut-droit) |
| **`Super + N`** | Centre de notifications dans l'île |
| **`Super + I`** | Paramètres (Liquid Glass, thèmes, alimentation, langue FR/EN) |
| **`Super + T`** ou **`Super + Entrée`** | Terminal Kitty Liquid Glass |
| **`Super + \``** | Terminal Kitty déroulant depuis le haut |
| **`Super + E`** | Fichiers Nautilus (Liquid Glass + aperçu rapide `Espace`) |
| **`Super + W`** | Navigateur web |
| **`Super + M`** | Lecteur musique **`onde-cli`** (paroles synchronisées dans l'île) |
| **`Super + V`** / **`Super + .`** / **`Super + O`** | Presse-papiers / Emojis / Calculatrice (gouttes de verre) |
| **`Super + P`** | Projection d'écran (PC seul, Dupliquer, Étendre, Sans fil) |
| **`Super + Maj + N`** / **`Super + Maj + T`** | Notes rapides / Tâches rapides |
| **`Super + Maj + O`** | Horloge (minuteur, chrono, pomodoro, alarmes) |
| **`Super + Maj + B`** | Écouteurs 3D façon AirPods |
| **`Super + Maj + Espace`** | Assistant vocal (`ano-siri`, chargé à la demande) |
| **`Super + Maj + D`** / **`W`** / **`Super + Alt + T`** | Dictée vocale / Outils d'écriture / Traduction |
| **`Super + Tab`** (ou 3 doigts ↑) | Mission Control |
| **`Impr. écran`** / **`Super + Impr. écran`** | Capture plein écran / Capture zone + annotation |
| **`Super + L`** / **`Ctrl + Alt + Suppr`** | Verrouiller l'écran / Menu de session |
| **`Super + Q`** / **`Super + Maj + Q`** | Fermer la fenêtre / Quitter complètement l'appli |
| **`Super + Maj + R`** | Recharger Hyprland + Ano Shell |

---

## Installation sur un Hyprland déjà configuré

Si tu as déjà un Arch + Hyprland configuré, l'installeur **ne casse rien** (sauvegarde horodatée + 1 seule ligne `source` ajoutée) :

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell
./install                      # mode greffe sur ton hyprland.conf existant
# ou pour migrer depuis Caelestia Liquid Glass sans rien modifier là-bas :
./install --migrate-caelestia
```

Désinstallation réversible à tout moment : `./uninstall`.

---

## Commandes CLI (`ano-shell`)

| Commande | Rôle |
| :--- | :--- |
| `ano-shell shell -d` / `-k` | Démarre ou arrête le shell (bloque l'arrêt si l'écran est verrouillé) |
| `ano-shell wallpaper -f <img>` | Change le fond d'écran et génère la palette dynamique Material You |
| `ano-shell scheme set -m dark\|light` | Change le thème ou bascule clair/sombre |
| `ano-shell glass --auto` | Détecte GPU/batterie et applique le profil Liquid Glass optimal |
| `ano-shell theme` | Régénère GTK4/3 Liquid Glass, portail GTK3, Qt/Darkly et Hyprland |
| `ano-shell screenshot` / `record` | Capture d'écran et enregistrement vidéo `gpu-screen-recorder` |
| `ano-shell doctor` | Vérifie l'ABI Qt6 de Quickshell, `ldd` des plugins, JSON et Hyprland |
| `ano-shell migrate` | Copie les réglages depuis `~/.config/caelestia` sans y toucher |
| `onde-cli` | Lance le lecteur musique terminal synchronisé avec la Dynamic Island |

## Licence & Attribution

Licence **GPL-3.0**. Dérivé de [caelestia-dots/shell](https://github.com/caelestia-dots/shell) (GPL-3.0) et [m3shapes](https://github.com/soramanew/m3shapes) (Apache-2.0) ; voir [NOTICE](NOTICE).
