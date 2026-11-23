# Contributing to Ano Shell

Thank you for your interest in contributing to **Ano Shell**! Bug reports, performance profiles, translations, and pull requests are very welcome.

## High-Impact Areas

- **Additional languages (i18n)**: English & French are built in (`shell/services/I18n.qml` & `shell/services/I18nEn.js`). Translations for new locales are warmly welcomed.
- **Hardware & GPU testing**: reports and fixes for NVIDIA GPUs, AMD iGPUs/dGPUs, multi-monitor setups, HiDPI scaling, and Arch derivatives (EndeavourOS, CachyOS, Manjaro, Garuda).
- **GLSL shader & performance optimizations**: improvements to `liquidios.frag`, `liquidios-fast.frag`, or memory footprint.
- **Documentation & packaging**: AUR `PKGBUILD` refinements and beginner guides.

## Local Verification Before Opening a PR

Run these fast checks from the repository root:

```bash
# Python CLI lint & unit tests
ruff check cli/ tests/
pytest -q tests/

# Shell script syntax checks
bash -n bootstrap.sh install uninstall

# C++ syntax check (if touching plugin/src/)
cmake -B build && cmake --build build -j
```

## Reporting Bugs

Please open a [Bug Report](https://github.com/Abdoul273/ano-shell/issues/new/choose) and attach the output of:

```bash
ano-shell doctor
```

along with your Arch derivative, GPU model, Hyprland version, and active Liquid Glass performance profile (`ultra` / `eco` / `auto`).

## Code Style & License

- Keep changes minimal, focused, and consistent with surrounding code.
- All contributions are licensed under **GPL-3.0** (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).
