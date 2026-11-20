# Ano Shell

> **Standalone Liquid Glass desktop shell for Hyprland** — Quickshell + native Qt6 C++ plugins + integrated CLI, with **zero dependency on `caelestia-shell`, `caelestia-cli`, `caelestia-dots`, `libcava`, `sndio` or `aubio`**.

[Version française](README.fr.md)

## Why Ano Shell?

- **100% Standalone**: ships its own Qt6 C++ QML plugins (`AnoShell.*` + `AnoShell.Shapes`), its own Python CLI (`ano-shell`), its own theme engine (GTK4/3 Liquid Glass, GTK3 portal, Darkly Qt/KDE, Kitty, Hyprland) and dual-mode Hyprland configs (standalone turnkey or 1-line drop-in).
- **Immune to `libcava` / `sndio` breakage**: audio spectrum analysis uses a native PipeWire + `fftw3` engine (and pure C++ beat detection) directly inside `AnoShell.Services`.
- **Engineered for low-end laptops (2-core / Intel iGPU) & dedicated GPUs alike**:
  - Eliminated 60 FPS idle shader redraws (`windowMaskTex` event-driven, static crisp clock separator, native C++ `SystemWatch` replacing shell/`fuser` polling).
  - Lazy-loaded modal panels (`LazyPanel` unloads Control Center, Spotlight, Earbuds 3D, Settings, Clock, Annotate, etc. after 90 s idle).
  - On-demand voice assistant (`ano-siri` starts on first `Super+Shift+Space`, freeing ~350 MB RAM at boot; optional keep-alive toggle in `island.json`).
  - Automatic GPU & battery profile detection (`ano-shell glass --auto`).
- **Built-in Liquid Glass iOS 27 & macOS workflow**: Dynamic Island (music, synced lyrics, calls, transfers, AI agents, timers/alarms, battery, privacy), Control Center, Dock, Mission Control, Spotlight, Lock Screen, bilingual EN/FR interface (`I18n.qml`).

## Quick Install (Arch Linux / EndeavourOS)

### Option 1 — Single AUR-style package (`makepkg`)

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell/packaging/aur
# For local build from working tree, or after tagging v1.0.0:
makepkg -si
```

### Option 2 — Build & 1-click user setup

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell

# 1. Build & install native Qt6 C++ plugins (`AnoShell.*` + `AnoShell.Shapes`)
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_SYSCONFDIR=/etc
cmake --build build
sudo cmake --install build

# 2. Install CLI, QML shell, tools, Hyprland integration & optimal GPU profile
./install            # add --migrate-caelestia to import existing Caelestia prefs
                     # add --standalone-hypr on a fresh Arch + Hyprland install

# 3. Verify & launch
ano-shell doctor
setsid -f ano-shell shell -d
```

## CLI Overview (`ano-shell`)

| Command | Description |
| :--- | :--- |
| `ano-shell shell -d` / `-k` | Start or safely stop the shell (refuses to kill while screen is locked) |
| `ano-shell wallpaper -f <img>` | Set wallpaper and generate Material You dynamic palette |
| `ano-shell scheme set -m dark\|light` | Switch theme or color mode |
| `ano-shell glass --auto` | Detect GPU/battery and apply the best Liquid Glass profile |
| `ano-shell theme` | Regenerate GTK4/3 Liquid Glass, GTK3 portal, Qt/Darkly and Hyprland colors |
| `ano-shell screenshot` / `record` | Fullscreen/region screenshot and `gpu-screen-recorder` capture |
| `ano-shell doctor` | Check Quickshell Qt6 ABI alignment, plugin `ldd`, JSON configs and Hyprland |
| `ano-shell migrate` | Non-destructively copy settings from `~/.config/caelestia` |

## License & Attribution

Licensed under **GPL-3.0**. Derived from [caelestia-dots/shell](https://github.com/caelestia-dots/shell) (GPL-3.0) and [m3shapes](https://github.com/soramanew/m3shapes) (Apache-2.0); see [NOTICE](NOTICE).
