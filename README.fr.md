# Ano Shell

> **Shell de bureau Liquid Glass 100 % autonome pour Hyprland** — Quickshell + plugins C++ Qt6 natifs + CLI intégrée, **sans aucune dépendance à `caelestia-shell`, `caelestia-cli`, `caelestia-dots`, `libcava`, `sndio` ni `aubio`**.

[English version](README.md)

## Pourquoi Ano Shell ?

- **100 % indépendant** : embarque ses propres plugins C++ Qt6 (`AnoShell.*` + `AnoShell.Shapes`), sa propre CLI Python (`ano-shell`), son moteur de thèmes Liquid Glass (GTK4/3, portail GTK3, Darkly Qt/KDE, Kitty, Hyprland) et une config Hyprland double mode (autonome clé en main ou greffe d'une ligne `source = ...`).
- **Immunisé contre les casses `libcava` / `sndio`** : le spectre audio utilise un moteur FFT natif PipeWire + `fftw3` (et détection de tempo pure C++) directement dans `AnoShell.Services`.
- **Optimisé pour les PC modestes (2 cœurs / iGPU Intel) comme pour les GPU dédiés** :
  - Suppression des redessins 60 FPS inutiles au repos (`windowMaskTex` événementiel, séparateur d'horloge fixe, service C++ `SystemWatch` remplaçant les `fork/exec` shell/`fuser`).
  - Chargement paresseux (`LazyPanel`) de 16 panneaux modaux (Centre de contrôle, Spotlight, Écouteurs 3D, Paramètres, Horloge, Annotation, Dock…) avec libération mémoire après 90 s d'inactivité.
  - Assistant vocal `ano-siri` démarré à la demande (0 Mo au boot, option `siriKeepAlive` disponible dans `island.json`).
  - Profil matériel automatique (`ano-shell glass --auto`).
- **Toute la richesse Liquid Glass iOS 27 & macOS** : Dynamic Island (musique, paroles Onde, appels, transferts, agents IA, minuteur/alarmes, batterie, confidentialité), Centre de contrôle, Dock, Mission Control, Spotlight, Écran de verrouillage, interface bilingue FR/EN.

## Installation rapide (Arch Linux / EndeavourOS)

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell

# 1. Compiler et installer les plugins C++ Qt6 natifs (`AnoShell.*` + `AnoShell.Shapes`)
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_SYSCONFDIR=/etc
cmake --build build
sudo cmake --install build

# 2. Installer la CLI, le shell QML, les outils, la config Hyprland et le profil GPU optimal
./install --migrate-caelestia   # importe vos réglages Caelestia sans y toucher
                                # (utilisez --standalone-hypr sur un Arch/Hyprland vierge)

# 3. Vérifier et lancer (côte à côte sans supprimer Caelestia)
ano-shell doctor
qs -c caelestia kill; sleep 2; setsid -f ano-shell shell -d
```

## Commandes principales (`ano-shell`)

| Commande | Rôle |
| :--- | :--- |
| `ano-shell shell -d` / `-k` | Démarre ou arrête le shell (bloque l'arrêt si l'écran est verrouillé) |
| `ano-shell wallpaper -f <img>` | Change le fond d'écran et génère la palette dynamique Material You |
| `ano-shell scheme set -m dark\|light` | Change le thème ou bascule clair/sombre |
| `ano-shell glass --auto` | Détecte GPU/batterie et applique le profil Liquid Glass optimal |
| `ano-shell theme` | Régénère GTK4/3 Liquid Glass, portail GTK3, Qt/Darkly et Hyprland |
| `ano-shell screenshot` / `record` | Capture d'écran et enregistrement vidéo `gpu-screen-recorder` |
| `ano-shell doctor` | Vérifie l'ABI Qt6 de Quickshell, `ldd` des plugins, JSON et Hyprland |
| `ano-shell migrate` | Copie les réglages depuis `~/.config/caelestia` sans rien modifier là-bas |

## Licence & Attribution

Licence **GPL-3.0**. Dérivé de [caelestia-dots/shell](https://github.com/caelestia-dots/shell) (GPL-3.0) et [m3shapes](https://github.com/soramanew/m3shapes) (Apache-2.0) ; voir [NOTICE](NOTICE).
