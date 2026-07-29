"""Load the bundled Inter family into this process only.

Inter is what gives the glass surfaces their typography; shipping the .ttf files
and registering them with FR_PRIVATE means the app looks identical on a machine
where nothing was ever installed, and nothing is left behind on exit.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

FR_PRIVATE = 0x10

_loaded: list[Path] = []
_families: set[str] = set()


def assets_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def load_bundled_fonts() -> list[str]:
    """Register every .ttf in assets/fonts. Returns the file stems that loaded."""
    if _loaded:
        return [p.stem for p in _loaded]

    font_dir = assets_dir() / "fonts"
    if not font_dir.is_dir():
        return []

    try:
        gdi32 = ctypes.WinDLL("gdi32")
    except OSError:
        return []

    add = gdi32.AddFontResourceExW
    add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    add.restype = ctypes.c_int

    for path in sorted(font_dir.glob("*.ttf")):
        try:
            if add(str(path), FR_PRIVATE, None):
                _loaded.append(path)
        except Exception:
            continue
    return [p.stem for p in _loaded]


def register_available(families: set[str]) -> None:
    """Record which families Tk actually resolved, for `pick()` to consult."""
    _families.clear()
    _families.update(families)


def pick(*candidates: str, fallback: str = "Segoe UI") -> str:
    """First candidate Tk knows about, else `fallback`."""
    if not _families:
        return candidates[0] if candidates else fallback
    for name in candidates:
        if name in _families:
            return name
    return fallback
