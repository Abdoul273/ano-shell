# Ano Shell

> **Standalone Liquid Glass desktop environment for Arch Linux + Hyprland** — installs from a fresh Arch Linux (`no desktop`) TTY in **one command**, with zero dependency on `caelestia-shell`, `caelestia-cli`, `libcava`, `sndio` or `aubio`.

[Version française (guide pas-à-pas)](README.fr.md)

---

## Step-by-Step Beginner Guide (From a Fresh Arch Linux Install)

Never configured Hyprland before? Follow these **4 simple steps**:

### Step 1 — Install minimal Arch Linux (`archinstall`)
1. Boot the Arch Linux ISO and run `archinstall`.
2. Pick:
   - **Profile** → **`Minimal`** (or **`No desktop`**)
   - **Audio** → **`PipeWire`**
   - **Network configuration** → **`Use NetworkManager`**
   - **User account** → create a normal user with **`Superuser (sudo) = Yes`**
3. Finish installation and reboot without the USB stick.

### Step 2 — Log in at the black screen (TTY)
1. Type your username and password.
2. If on Wi-Fi, connect with `nmtui` (*Activate a connection* → pick your network → Quit). Ethernet works automatically.

### Step 3 — Run the 1-command automatic installer

```bash
curl -fsSL https://raw.githubusercontent.com/Abdoul273/ano-shell/main/bootstrap.sh | bash
```

Enter your `sudo` password once and wait ~5–15 minutes while everything installs and builds automatically:
- **Full Wayland/Hyprland stack**: Hyprland, portals, PipeWire, Bluetooth, NetworkManager, Power Profiles, **SDDM Liquid Glass login screen** + macOS cursor.
- **Native Qt6 C++ plugins (`AnoShell.*` + `AnoShell.Shapes`)**: built automatically with native PipeWire + `fftw3` audio spectrum (immune to `libcava`/`sndio` breakage) and C++ `SystemWatch`.
- **Full Liquid Glass theme everywhere**: Dynamic Island iOS 27, Control Center, 14 glass drop popups, Mission Control, Lock Screen, **Nautilus + Sushi** (GTK4/3 + File Chooser Portal Liquid Glass), **Qt/KDE Darkly**, **Kitty** (modular + `tab_bar.py` + `Super+\`` dropdown), **Fastfetch**, **Fish + Starship** (`eza`, `zoxide`), **Firefox**.
- **`onde-cli`**: interactive Rich terminal music player with word-synced lyrics in the Dynamic Island.
- **Optimized for 2-core Intel laptops & dedicated GPUs alike**: automatic hardware profile (`ano-shell glass --auto`), zero 60 FPS idle shader redraws, lazy-loaded modal panels (`LazyPanel`), on-demand daemons.

### Step 4 — Reboot & Enjoy

```bash
sudo reboot
```

Press **`Super + H`** anytime on the desktop to open the interactive shortcuts search.

---

## Essential Shortcuts (Pre-configured)

| Shortcut | Action |
| :--- | :--- |
| **`Super + Space`** | Spotlight search (glass popup) |
| **`Super + A`** | Liquid Glass Control Center (or top-right hot corner) |
| **`Super + N`** | Notification Center inside the Island |
| **`Super + I`** | Settings (Liquid Glass, themes, power, EN/FR language) |
| **`Super + T`** / **`Super + Enter`** | Kitty Liquid Glass terminal |
| **`Super + \``** | Quake-style dropdown Kitty terminal |
| **`Super + E`** | Nautilus file manager (Liquid Glass + `Space` Quick Look) |
| **`Super + W`** | Web browser |
| **`Super + M`** | **`onde-cli`** terminal music player (synced with Island) |
| **`Super + V`** / **`Super + .`** / **`Super + O`** | Clipboard / Emoji / Calculator glass popups |
| **`Super + P`** | Display projection (Single, Duplicate, Extend, Wireless) |
| **`Super + Shift + N`** / **`T`** | Quick Notes / Quick Tasks |
| **`Super + Shift + O`** / **`B`** | Clock (timer/pomodoro/alarms) / 3D Earbuds popup |
| **`Super + Shift + Space`** | Voice assistant (`ano-siri`, on-demand) |
| **`Super + Shift + D`** / **`W`** / **`Super + Alt + T`** | Dictation / Writing tools / Translate |
| **`Super + Tab`** (or 3-finger swipe ↑) | Mission Control |
| **`Print`** / **`Super + Print`** | Fullscreen / Region + Annotate screenshot |
| **`Super + L`** / **`Ctrl + Alt + Del`** | Lock screen / Session menu |
| **`Super + Q`** / **`Super + Shift + Q`** | Close window / Fully quit app |
| **`Super + Shift + R`** | Reload Hyprland + Ano Shell |

---

## Install on an Existing Hyprland Setup

Non-destructive (creates a timestamped backup and adds 1 `source` line):

```fish
git clone https://github.com/Abdoul273/ano-shell.git
cd ano-shell
./install
# or to migrate settings from Caelestia Liquid Glass:
./install --migrate-caelestia
```

Reversible anytime via `./uninstall`.

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
