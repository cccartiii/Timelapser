"""Pixel-art sprite loader for the flat UI sprite set.

Loads individual .png sprites from assets/Sprites/ and provides
a simple API to render them onto Tk Canvas widgets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from PIL import Image, ImageTk


def _assets_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


SPRITE_DIR = _assets_dir() / "Sprites"
SPRITESHEET_DIR = _assets_dir() / "Spritesheets"

_cache: dict[str, ImageTk.PhotoImage] = {}


def _resource_path(*parts: str) -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = Path(__file__).resolve().parent.parent
    return os.path.join(base, *parts)


def load(name: str, scale: int = 1) -> ImageTk.PhotoImage | None:
    """Load a sprite by filename (e.g. 'UI_Flat_Frame01a.png') and cache it."""
    key = f"{name}_{scale}"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    path = os.path.join(SPRITE_DIR, name)
    if not os.path.isfile(path):
        return None

    try:
        img = Image.open(path)
        if scale > 1:
            w, h = img.size
            img = img.resize((w * scale, h * scale), Image.NEAREST)
        photo = ImageTk.PhotoImage(img)
        _cache[key] = photo
        return photo
    except Exception:
        return None


def load_sheet(name: str) -> Image.Image | None:
    """Load a spritesheet as a PIL Image for manual slicing."""
    path = os.path.join(SPRITESHEET_DIR, name)
    if not os.path.isfile(path):
        return None
    try:
        return Image.open(path)
    except Exception:
        return None


def sprite_size(name: str) -> tuple[int, int]:
    """Return the (width, height) of a sprite without loading it into cache."""
    path = os.path.join(SPRITE_DIR, name)
    if not os.path.isfile(path):
        return (0, 0)
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def clear_cache() -> None:
    _cache.clear()