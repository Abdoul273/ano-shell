# Changelog

## 1.0.0 — 2026-11-20

- Première version 100 % autonome d'**Ano Shell** (aucune dépendance à `caelestia-shell`, `caelestia-cli`, `caelestia-dots`, `libcava`, `sndio` ni `aubio`).
- Plugins C++ Qt6 natifs `AnoShell.*` + `AnoShell.Shapes`, avec analyseur de spectre FFT PipeWire + `fftw3`, détecteur de tempo C++ pur et service `SystemWatch` sans `fork/exec`.
- CLI autonome `ano-shell` (`shell`, `wallpaper`, `scheme`, `theme`, `glass`, `screenshot`, `record`, `doctor`, `migrate`) avec garde-fou anti-verrouillage et moteur Liquid Glass GTK/Qt/Darkly intégré.
- Optimisations majeures CPU/RAM/GPU au repos : suppression de l'animation 60 FPS du séparateur d'horloge, `windowMaskTex` événementiel, `LazyPanel` sur 16 panneaux modaux/secondaires, `ano-siri` à la demande et allègement d'`ano-agents` / `ano-transfers`.
- Configuration Hyprland dual-mode (`config/hypr/shell.conf` en greffe 1 ligne + `config/hypr/standalone/hyprland.conf` clé en main), `PKGBUILD` AUR, hook pacman Qt6 et installeur 1-clic.
