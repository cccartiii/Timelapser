"""Premium surface renderer — layered gradients, inner shadows, subtle depth.

Each surface is a rounded rectangle with:
  • A soft vertical gradient (top lighter, bottom darker)
  • A barely-visible inner shadow at the edges for depth
  • An optional hairline border with rounded corners
  • Subtle noise texture for a premium, tactile feel
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageTk

from .theme import Color, Space

_SS = 4


def _rounded_image(
    w: int,
    h: int,
    radius: int,
    fill: str,
    border: str | None = None,
    border_width: int = 1,
) -> np.ndarray:
    """Render a premium rounded rectangle with gradient, inner shadow, and border."""
    r = int(fill[1:3], 16)
    g = int(fill[3:5], 16)
    b = int(fill[5:7], 16)
    arr = np.full((h, w, 3), [r, g, b], dtype=np.float32)

    # Subtle vertical gradient — top 4% lighter, bottom 4% darker
    if h > 4:
        gradient = np.linspace(1.04, 0.96, h, dtype=np.float32)[:, None, None]
        arr = arr * gradient
        np.clip(arr, 0, 255, out=arr)

    # Inner shadow — darker at edges, transparent in center
    if w > 8 and h > 8:
        inner = Image.new("L", (w * _SS, h * _SS), 0)
        ImageDraw.Draw(inner).rounded_rectangle(
            (0, 0, w * _SS - 1, h * _SS - 1), radius=radius * _SS, fill=255
        )
        outer_mask = (
            np.asarray(inner.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
        )

        inset = max(2, min(w, h) // 6)
        inner2 = Image.new("L", (w * _SS, h * _SS), 0)
        ImageDraw.Draw(inner2).rounded_rectangle(
            (inset * _SS, inset * _SS, w * _SS - 1 - inset * _SS, h * _SS - 1 - inset * _SS),
            radius=max(0, radius * _SS - inset * _SS),
            fill=255,
        )
        inner2_mask = (
            np.asarray(inner2.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
        )

        shadow_ring = np.clip(outer_mask - inner2_mask, 0.0, 1.0)[..., None]
        shadow_strength = 0.12
        shadow_color = np.asarray([0, 0, 0], dtype=np.float32)
        arr = arr * (1.0 - shadow_ring * shadow_strength) + shadow_color * (shadow_ring * shadow_strength)
        np.clip(arr, 0, 255, out=arr)

    if border is not None and border_width > 0:
        br = int(border[1:3], 16)
        bg = int(border[3:5], 16)
        bb = int(border[5:7], 16)
        border_arr = np.full((h, w, 3), [br, bg, bb], dtype=np.float32)

        big = Image.new("L", (w * _SS, h * _SS), 0)
        ImageDraw.Draw(big).rounded_rectangle(
            (0, 0, w * _SS - 1, h * _SS - 1), radius=radius * _SS, fill=255
        )
        outer_mask = (
            np.asarray(big.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
        )

        inner = Image.new("L", (w * _SS, h * _SS), 0)
        inset_px = border_width * _SS
        ImageDraw.Draw(inner).rounded_rectangle(
            (inset_px, inset_px, w * _SS - 1 - inset_px, h * _SS - 1 - inset_px),
            radius=max(0, radius * _SS - inset_px),
            fill=255,
        )
        inner_mask = (
            np.asarray(inner.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0
        )

        ring = np.clip(outer_mask - inner_mask, 0.0, 1.0)[..., None]
        arr = (border_arr * ring + arr * (1.0 - ring)).astype(np.float32)

    return arr.astype(np.float32)


class Backdrop:
    """Premium surface renderer — gradients, inner shadows, subtle depth."""

    def __init__(self) -> None:
        self._w = 0
        self._h = 0
        self._t = 0.0
        self.sharp: Image.Image | None = None

    @property
    def size(self) -> tuple[int, int]:
        return self._w, self._h

    def render(self, width: int, height: int, t: float | None = None) -> None:
        if t is not None:
            self._t = t
        self._w = max(8, int(width))
        self._h = max(8, int(height))

    def advance(self, step: float = 1.0) -> None:
        self._t += step

    def photo(self) -> ImageTk.PhotoImage | None:
        return None

    def compose(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        radius: int = Space.RADIUS,
        fill: str = Color.SURFACE,
        border: str | None = None,
        border_width: int = 1,
        **kwargs,
    ) -> np.ndarray:
        self.render(max(x + w, 64), max(y + h, 64))
        w = max(2, min(int(w), self._w))
        h = max(2, min(int(h), self._h))
        radius = max(0, min(int(radius), min(w, h) // 2))
        return _rounded_image(w, h, radius, fill, border, border_width)

    def overlay(
        self,
        arr: np.ndarray,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        radius: int,
        fill: tuple[str, str] | str,
        alpha: float = 1.0,
        **kwargs,
    ) -> None:
        ah, aw = arr.shape[:2]
        x, y = int(x), int(y)
        w, h = max(2, int(w)), max(2, int(h))
        if x >= aw or y >= ah or x + w <= 0 or y + h <= 0:
            return
        radius = max(0, min(int(radius), min(w, h) // 2))

        if isinstance(fill, str):
            top = bottom = np.asarray(
                [int(fill[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32
            )
        else:
            top = np.asarray(
                [int(fill[0][i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32
            )
            bottom = np.asarray(
                [int(fill[1][i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32
            )
        ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        shape = top[None, None, :] * (1 - ramp) + bottom[None, None, :] * ramp
        shape = np.repeat(shape, w, axis=1)

        big = Image.new("L", (w * _SS, h * _SS), 0)
        ImageDraw.Draw(big).rounded_rectangle(
            (0, 0, w * _SS - 1, h * _SS - 1), radius=radius * _SS, fill=255
        )
        mask = (
            np.asarray(big.resize((w, h), Image.LANCZOS), dtype=np.float32)
            / 255.0
        )[..., None]
        mask = mask * alpha

        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(aw, x + w), min(ah, y + h)
        m = mask[y0 - y : y1 - y, x0 - x : x1 - x]
        s = shape[y0 - y : y1 - y, x0 - x : x1 - x]
        region = arr[y0:y1, x0:x1]
        region *= 1.0 - m
        region += s * m
        np.clip(region, 0, 255, out=region)

    def tile(self, *args, **kwargs) -> ImageTk.PhotoImage:
        arr = self.compose(*args, **kwargs)
        return ImageTk.PhotoImage(Image.fromarray(arr.astype(np.uint8), "RGB"))

    @staticmethod
    def to_photo(arr: np.ndarray) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(Image.fromarray(arr.astype(np.uint8), "RGB"))

    @staticmethod
    def average(arr: np.ndarray, inset: int = 6) -> str:
        h, w = arr.shape[:2]
        inset = min(inset, max(0, min(h, w) // 3))
        region = arr[inset : h - inset or None, inset : w - inset or None]
        if region.size == 0:
            region = arr
        r, g, b = region.reshape(-1, 3).mean(axis=0)
        return "#%02x%02x%02x" % (
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))),
        )
