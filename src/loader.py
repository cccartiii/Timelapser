"""Premium pulsing circle loader, drawn on a Tk Canvas.

Five dots cascade in a wave, each scaling and fading with a smooth
ease-in-out.  The dots use the accent colour with a subtle glow ring
that expands and fades, giving a premium, polished feel.
"""

from __future__ import annotations

import math
import tkinter as tk


class PulseLoader(tk.Canvas):
    """Five-dot loader with cascading wave animation.

    circle: scale 1 -> 1.5 -> 1, opacity 1 -> 0.5 -> 1
    dot:    scale 1 -> 0 -> 1
    outline: expands from 0 with a fading ring
    Each circle is staggered by 0.3s across a 2s loop.
    """

    PERIOD_MS = 2000
    STAGGER_MS = 300
    TICK_MS = 16
    COUNT = 5

    def __init__(
        self,
        master,
        *,
        color: str = "#dedede",
        accent: str | None = None,
        bg: str = "#0c0e12",
        diameter: int = 18,
        gap: int = 18,
        **kwargs,
    ) -> None:
        width = self.COUNT * diameter + (self.COUNT - 1) * gap + diameter * 3
        height = int(diameter * 3.2)
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._color = color
        self._accent = accent or color
        self._diameter = diameter
        self._gap = gap
        self._running = False
        self._t0 = 0.0
        self._after_id = None
        self._items: list[dict] = []
        self._build()

    def _build(self) -> None:
        self.delete("all")
        self._items.clear()
        d = self._diameter
        total = self.COUNT * d + (self.COUNT - 1) * self._gap
        start_x = (int(self["width"]) - total) / 2 + d / 2
        cy = int(self["height"]) / 2

        for i in range(self.COUNT):
            cx = start_x + i * (d + self._gap)
            outline = self.create_oval(0, 0, 0, 0, outline="", width=0)
            ring = self.create_oval(0, 0, 0, 0, outline=self._color, width=2, fill="")
            dot = self.create_oval(0, 0, 0, 0, outline="", fill=self._color)
            self._items.append(
                {"cx": cx, "cy": cy, "ring": ring, "dot": dot, "outline": outline, "i": i}
            )

    @staticmethod
    def _ease_in_out(t: float) -> float:
        # Approximate CSS ease-in-out with a smoothstep cubic.
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def _phase(self, elapsed_ms: float, delay_ms: float) -> float:
        t = ((elapsed_ms - delay_ms) % self.PERIOD_MS) / self.PERIOD_MS
        if t < 0:
            t += 1.0
        return t

    def _lerp_color(self, a: str, b: str, t: float) -> str:
        def parse(c: str) -> tuple[int, int, int]:
            c = c.lstrip("#")
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

        ar, ag, ab = parse(a)
        br, bg, bb = parse(b)
        r = int(ar + (br - ar) * t)
        g = int(ag + (bg - ag) * t)
        bl = int(ab + (bb - ab) * t)
        return f"#{r:02x}{g:02x}{bl:02x}"

    def _tick(self) -> None:
        if not self._running:
            return
        import time

        elapsed = (time.perf_counter() - self._t0) * 1000.0
        d = self._diameter

        for item in self._items:
            i = item["i"]
            # CSS: circle delay i*0.3s; outline delay i*0.3s + 0.9s
            circle_t = self._phase(elapsed, i * self.STAGGER_MS)
            outline_t = self._phase(elapsed, i * self.STAGGER_MS + 900)

            # circle-keys: 0->0.5 scale 1->1.5 opacity 1->0.5, then reverse
            if circle_t < 0.5:
                u = self._ease_in_out(circle_t * 2)
            else:
                u = self._ease_in_out((1 - circle_t) * 2)
            circle_scale = 1.0 + 0.5 * u
            circle_opacity = 1.0 - 0.5 * u

            # dot-keys: scale 1 -> 0 -> 1
            if circle_t < 0.5:
                du = self._ease_in_out(circle_t * 2)
                dot_scale = 1.0 - du
            else:
                du = self._ease_in_out((circle_t - 0.5) * 2)
                dot_scale = du

            # outline-keys: scale 0->1, outline 20px -> 0, opacity 1->0
            ou = self._ease_in_out(outline_t)
            outline_scale = ou
            outline_width = max(0.0, 10 * (1 - ou))
            outline_opacity = 1.0 - ou

            cx, cy = item["cx"], item["cy"]

            # ring (border circle)
            rs = (d / 2) * circle_scale
            ring_color = self._fade(self._color, circle_opacity)
            self.coords(item["ring"], cx - rs, cy - rs, cx + rs, cy + rs)
            self.itemconfigure(item["ring"], outline=ring_color, width=2)

            # inner dot
            ds = (d * 0.4) * max(0.01, dot_scale)
            self.coords(item["dot"], cx - ds, cy - ds, cx + ds, cy + ds)
            self.itemconfigure(item["dot"], fill=self._fade(self._accent, circle_opacity))

            # expanding outline ring
            os_ = (d / 2) * (0.2 + 1.4 * outline_scale)
            oc = self._fade(self._color, outline_opacity * 0.7)
            self.coords(item["outline"], cx - os_, cy - os_, cx + os_, cy + os_)
            self.itemconfigure(
                item["outline"],
                outline=oc,
                width=max(1, outline_width),
            )

        self._schedule()

    def _schedule(self) -> None:
        self._after_id = self.after(self.TICK_MS, self._tick)

    def _fade(self, color: str, opacity: float) -> str:
        """Blend color toward canvas bg to fake opacity (Tk has no alpha)."""
        bg = str(self["bg"])
        if not bg.startswith("#") or len(bg) != 7:
            bg = "#0c0e12"
        opacity = max(0.0, min(1.0, opacity))
        return self._lerp_color(bg, color, opacity)

    def start(self) -> None:
        if self._running:
            return
        import time

        self._running = True
        self._t0 = time.perf_counter()
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def set_color(self, color: str, accent: str | None = None) -> None:
        self._color = color
        self._accent = accent or color
