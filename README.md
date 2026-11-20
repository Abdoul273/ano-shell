# Ano Shell

> **Standalone Liquid Glass desktop environment for Arch Linux + Hyprland** — installs from a fresh Arch Linux (`no desktop`) TTY in **one command**, with zero dependency on `caelestia-shell`, `caelestia-cli`, `libcava`, `sndio` or `aubio`.

[Version française](README.fr.md)

## One-Command Install (Fresh Arch Linux — `no desktop`)

On a brand-new Arch Linux installation (from `archinstall` with **Profile: Minimal / No desktop**), log into the TTY as your normal user and run:

```bash
curl -fsSL https://raw.githubusercontent.com/Abdoul273/ano-shell/main/bootstrap.sh | bash
```

Then reboot (`sudo reboot`). Everything is configured automatically:
- **Desktop stack**: Hyprland, Wayland portals, PipeWire + WirePlumber, Bluetooth, NetworkManager, Power Profiles, SDDM (**Liquid Glass login screen** + macOS cursor).
- **Native Qt6 C++ plugins (`AnoShell.*` + `AnoShell.Shapes`)**: built automatically with native PipeWire + `fftw3` audio spectrum (no `libcava`/`sndio` breakage) and C++ `SystemWatch` (no shell/`fuser` polling).
- **Full Liquid Glass theme everywhere**: Dynamic Island iOS 27, Control Center, Mission Control, Spotlight, Lock Screen, **Nautilus + Sushi** (GTK4/3 + File Chooser Portal Liquid Glass), **Qt/KDE Darkly**, **Kitty** (modular + `tab_bar.py` + `Super+\`` dropdown), **Fastfetch**, **Fish + Starship** (`eza`, `zoxide`).
- **Music & Tools included**: **`onde-cli`** (Rich terminal music player with word-synced lyrics connected to the Dynamic Island), clipboard, emoji, display projection, clock/timers, voice assistant (`ano-siri`, on-demand), dictation, writing tools, web watchers, AI agents monitor.
- **Tuned for low-end laptops & dedicated GPUs alike**: automatic hardware profile (`ano-shell glass --auto`), zero 60 FPS idle shader redraws, lazy-loaded modal panels (`LazyPanel`), on-demand daemons.

---

## Install on an Existing Hyprland Setup

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell
./install                      # keeps your hyprland.conf (adds 1 `source` line + timestamped backup)
# or if migrating from Caelestia Liquid Glass:
./install --migrate-caelestia
```

---

## CLI Overview (`ano-shell`)

| Command | Description |
| :--- | :--- |
| `ano-shell shell -d` / `-k` | Start or safely stop the shell (blocks kill while screen is locked) |
| `ano-shell wallpaper -f <img>` | Set wallpaper and generate Material You dynamic palette |
| `ano-shell scheme set -m dark\|light` | Switch theme or color mode |
| `ano-shell glass --auto` | Detect GPU/battery and apply the best Liquid Glass profile |
| `ano-shell theme` | Regenerate GTK4/3 Liquid Glass, GTK3 portal, Qt/Darkly and Hyprland colors |
| `ano-shell screenshot` / `record` | Fullscreen/region screenshot and `gpu-screen-recorder` capture |
| `ano-shell doctor` | Check Quickshell Qt6 ABI alignment, plugin `ldd`, JSON configs and Hyprland |
| `ano-shell migrate` | Non-destructively copy settings from `~/.config/caelestia` |
| `onde-cli` | Launch interactive terminal music player synced with the Dynamic Island |

## License & Attribution

Licensed under **GPL-3.0**. Derived from [caelestia-dots/shell](https://github.com/caelestia-dots/shell) (GPL-3.0) and [m3shapes](https://github.com/soramanew/m3shapes) (Apache-2.0); see [NOTICE](NOTICE).
