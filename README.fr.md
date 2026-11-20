# Ano Shell

> **Bureau Liquid Glass 100 % autonome pour Arch Linux + Hyprland** — s'installe depuis un Arch Linux vierge (**« no desktop »**) en **une seule commande**, sans aucune dépendance à `caelestia-shell`, `caelestia-cli`, `libcava`, `sndio` ni `aubio`.

[English version](README.md)

## Installation en 1 commande (Arch Linux vierge — « no desktop »)

Après une installation Arch Linux minimale (`archinstall` avec **Profil : Minimal / No desktop**), connecte-toi dans le TTY avec ton utilisateur normal et lance :

```bash
curl -fsSL https://raw.githubusercontent.com/Abdoul273/ano-shell/main/bootstrap.sh | bash
```

Puis redémarre (`sudo reboot`). Tout est installé et configuré automatiquement :
- **Socle bureau complet** : Hyprland, portails Wayland, PipeWire + WirePlumber, Bluetooth, NetworkManager, Power Profiles, **SDDM Liquid Glass** (écran de connexion en verre + curseur macOS).
- **Plugins C++ Qt6 natifs (`AnoShell.*` + `AnoShell.Shapes`)** : compilés automatiquement avec spectre audio FFT natif PipeWire + `fftw3` (immunisé contre les pannes `libcava`/`sndio`) et service C++ `SystemWatch` (zéro `fork/exec`).
- **Liquid Glass complet partout** : Dynamic Island iOS 27, Centre de contrôle, Mission Control, Spotlight, Écran de verrouillage, **Nautilus + Sushi** (GTK4/3 + Portail Ouvrir/Enregistrer en verre), **Qt/KDE Darkly**, **Kitty** (modulaire + `tab_bar.py` + terminal déroulant `Super+\``), **Fastfetch**, **Fish + Starship** (`eza`, `zoxide`).
- **Musique & Outils inclus** : **`onde-cli`** (lecteur musique interactif dans le terminal avec paroles synchronisées reliées à la Dynamic Island), presse-papiers, emojis, projection d'écran, horloge/minuteurs, assistant vocal (`ano-siri` à la demande), dictée, outils d'écriture, surveillances web, suivi d'agents IA.
- **Optimisé pour PC modestes (2 cœurs / iGPU Intel) et GPU dédiés** : profil matériel auto (`ano-shell glass --auto`), zéro redessin 60 FPS au repos, 16 panneaux chargés à la demande (`LazyPanel`).

---

## Installation sur un Hyprland déjà configuré

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell
./install                      # conserve ton hyprland.conf (ajoute 1 ligne `source` + sauvegarde)
# ou pour migrer depuis Caelestia Liquid Glass sans rien casser :
./install --migrate-caelestia
```

---

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
| `onde-cli` | Lance le lecteur musique terminal Rich synchronisé avec la Dynamic Island |

## Licence & Attribution

Licence **GPL-3.0**. Dérivé de [caelestia-dots/shell](https://github.com/caelestia-dots/shell) (GPL-3.0) et [m3shapes](https://github.com/soramanew/m3shapes) (Apache-2.0) ; voir [NOTICE](NOTICE).
