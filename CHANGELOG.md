# Changelog

## 1.0.0 — 2026-11-23

- **100% standalone desktop environment for Arch Linux & Hyprland** — installs from a fresh `no desktop` TTY in one command (`bootstrap.sh`), with zero dependency on `caelestia-shell`, `caelestia-cli`, `caelestia-dots`, `libcava`, `sndio`, or `aubio`.
- **Native Qt6 C++ plugins** (`AnoShell.*` + `AnoShell.Shapes`): native PipeWire + `fftw3` audio spectrum, pure C++ beat tracker, and `/sys`-based `SystemWatch` without `fork/exec`.
- **Liquid Glass iOS 27 / macOS 27 UI**: redesigned balanced Dynamic Island (rolling clock, workspaces, weather, info/perf/media/timer/transfers/AI agents/calls), Control Center, auto-hiding Dock, 14 refractive glass popups, 3D Earbuds HUD, Mission Control, SDDM Liquid Glass, Kitty, Nautilus GTK4, Qt/KDE Darkly, and `onde-cli`.
- **Hardware-aware Performance Profiles (`ultra` / `eco` / `auto`)**: selectable interactively during `./install`, via `ano-shell glass --performance`, or live in Settings (`Super + I`), combining `liquidios-fast.frag`, `LazyPanel` lazy loading on 16 panels, event-driven `windowMaskTex`, and on-demand daemons.
- **Standalone Python CLI (`ano-shell`)**: `shell` (lock-safe), `wallpaper`, `scheme`, `theme`, `glass`, `screenshot`, `record`, `doctor`, and `migrate`.
- **Dual-mode Hyprland config & packaging**: non-destructive 1-line graft (`config/hypr/shell.conf`), standalone turnkey config, AUR `PKGBUILD`, pacman Qt6 rebuild hook, and full `./uninstall`.
