"""Détection matérielle (GPU / batterie) et réglage du profil Liquid Glass d'Ano Shell."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from ano_shell.paths import atomic_dump, glass_config_path, load_json
from ano_shell.theme import GLASS_GTK_MODES, apply_glass_gtk_qt

SHELL_MODES = ("ios", "classic", "off")


def detect_hardware_profile() -> dict[str, Any]:
    """Détecte le GPU (iGPU Intel vs dédié AMD/NVIDIA) et la présence d'une batterie."""
    gpu_vendor = "unknown"
    is_dedicated = False
    drm = Path("/sys/class/drm")
    if drm.is_dir():
        for vendor_file in sorted(drm.glob("card*/device/vendor")):
            try:
                vid = vendor_file.read_text(encoding="utf-8").strip().lower()
            except OSError:
                continue
            if vid == "0x10de":
                gpu_vendor = "nvidia"
                is_dedicated = True
                break
            if vid == "0x1002":
                gpu_vendor = "amd"
                # Considérer dédié s'il existe plus d'un GPU ou PCI non-APU
                is_dedicated = True
            elif vid == "0x8086" and gpu_vendor == "unknown":
                gpu_vendor = "intel"

    has_battery = False
    ps = Path("/sys/class/power_supply")
    if ps.is_dir():
        for tfile in ps.glob("*/type"):
            try:
                if tfile.read_text(encoding="utf-8").strip() == "Battery":
                    has_battery = True
                    break
            except OSError:
                continue

    cpu_cores = os.cpu_count() or 2
    low_power = (not is_dedicated) and (cpu_cores <= 4 or has_battery)

    return {
        "gpu_vendor": gpu_vendor,
        "dedicated_gpu": is_dedicated,
        "has_battery": has_battery,
        "cpu_threads": cpu_cores,
        "profile": "igpu-eco" if low_power else "high",
        "recommended": {
            "shell": "ios",
            "gtk": "complet" if is_dedicated else "nautilus",
            "density": 0.62 if low_power else 0.55,
            "performance": "balanced" if low_power else "quality",
            "batteryAutoEco": has_battery,
        },
    }


def ensure_default_glass_config() -> dict[str, Any]:
    if glass_config_path.is_file():
        return load_json(glass_config_path)
    hw = detect_hardware_profile()
    cfg = dict(hw["recommended"])
    atomic_dump(glass_config_path, cfg)
    return cfg


def set_glass(
    shell_mode: str | None = None,
    gtk_mode: str | None = None,
    density: float | None = None,
    auto: bool = False,
) -> dict[str, Any]:
    conf = load_json(glass_config_path, detect_hardware_profile()["recommended"])
    if auto:
        conf.update(detect_hardware_profile()["recommended"])
    if shell_mode is not None:
        if shell_mode not in SHELL_MODES:
            raise ValueError(f"Mode shell invalide : {shell_mode} (valides : {SHELL_MODES})")
        conf["shell"] = shell_mode
    if gtk_mode is not None:
        if gtk_mode not in GLASS_GTK_MODES:
            raise ValueError(f"Mode GTK invalide : {gtk_mode} (valides : {GLASS_GTK_MODES})")
        conf["gtk"] = gtk_mode
    if density is not None:
        conf["density"] = round(max(0.0, min(1.0, float(density))), 3)

    atomic_dump(glass_config_path, conf)
    apply_glass_gtk_qt(mode=conf.get("gtk"), density=conf.get("density"), reload_desktop=True)

    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and gtk_mode is not None:
        subprocess.run(["hyprctl", "reload"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    return conf
