#!/usr/bin/env python3
"""Patche le CMakeLists.txt de m3shapes pour enregistrer le module QML AnoShell.Shapes."""

from __future__ import annotations

import sys
from pathlib import Path


def patch_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text.replace("URI M3Shapes", "URI AnoShell.Shapes").replace(
        "/M3Shapes", "/AnoShell/Shapes"
    )
    if "URI AnoShell.Shapes" not in updated or "/AnoShell/Shapes" not in updated:
        raise RuntimeError(f"Patch AnoShell.Shapes incomplet sur {path}")
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("CMakeLists.txt")
    patch_file(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
