"""Premium widget kit for Timelapser — Figma/Linear/Arc quality.

Smooth rounded surfaces, subtle depth, refined interactions, and polished
controls tuned for a premium desktop application experience.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Iterable

import numpy as np

from .glass import Backdrop
from .theme import (
    Color,
    LightColor,
    Space,
    Type,
    ease_out_cubic,
    ease_out_expo,
    mix,
    tracked,
    with_alpha,
)

FRAME_MS = 16
_SETTLE = 0.003

_font_cache: dict[tuple, tkfont.Font] = {}


def measure(font: tuple, text: str) -> int:
    cached = _font_cache.get(font)
    if cached is None:
        cached = tkfont.Font(font=font)
        _font_cache[font] = cached
    return cached.measure(text)


def line_height(font: tuple) -> int:
    cached = _font_cache.get(font)
    if cached is None:
        cached = tkfont.Font(font=font)
        _font_cache[font] = cached
    return cached.metrics("linespace")


def _descendants(widget: tk.Misc) -> Iterable[tk.Misc]:
    for child in widget.winfo_children():
        yield child
        if getattr(child, "_modern_root", False):
            continue
        yield from _descendants(child)


# ---------------------------------------------------------------------------
# Page background
# ---------------------------------------------------------------------------
class Page:
    """Owns the solid background and surface compositor."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.backdrop = Backdrop()
        colors = get_colors()
        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, bg=colors.BASE)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._photo = None
        self._widgets: list = []
        self._size = (0, 0)
        self._resize_job = None

        self.backdrop.render(1400, 960)
        root.bind("<Configure>", self._on_configure, add="+")

    def register(self, widget) -> None:
        self._widgets.append(widget)

    def offset(self, widget: tk.Misc) -> tuple[int, int]:
        try:
            return (
                widget.winfo_rootx() - self.root.winfo_rootx(),
                widget.winfo_rooty() - self.root.winfo_rooty(),
            )
        except tk.TclError:
            return (0, 0)

    def invalidate(self, delay: int = 50) -> None:
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(delay, self._do_invalidate)

    def _do_invalidate(self) -> None:
        self._resize_job = None
        self.refresh_widgets()

    def refresh_widgets(self) -> None:
        for widget in list(self._widgets):
            self._refresh_one(widget)

    def _refresh_one(self, widget) -> None:
        try:
            widget.refresh_surface()
        except tk.TclError:
            try:
                self._widgets.remove(widget)
            except ValueError:
                pass
        except Exception:
            pass

    def _on_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        if (event.width, event.height) == self._size:
            return
        self._size = (event.width, event.height)
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(90, self.render)

    def render(self) -> None:
        self._resize_job = None
        width = max(64, self.root.winfo_width())
        height = max(64, self.root.winfo_height())
        self.backdrop.render(width, height)
        self._blit()
        self.refresh_widgets()

    def _blit(self) -> None:
        import numpy as np
        from PIL import Image, ImageTk

        colors = get_colors()
        w = max(64, self.root.winfo_width())
        h = max(64, self.root.winfo_height())
        arr = np.full((h, w, 3), [int(colors.BASE[i:i+2], 16) for i in (1, 3, 5)], dtype=np.uint8)
        if self._photo is not None and (
            self._photo.width() != w or self._photo.height() != h
        ):
            self._photo = None
        if self._photo is None:
            self._photo = ImageTk.PhotoImage(Image.fromarray(arr, "RGB"))
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self._photo, anchor="nw")


# ---------------------------------------------------------------------------
# Animator mixin
# ---------------------------------------------------------------------------
class _Animated:
    """Exponential-smoothing animator for interactive controls."""

    def _init_anim(self) -> None:
        self._values: dict[str, float] = {}
        self._targets: dict[str, float] = {}
        self._rates: dict[str, float] = {}
        self._anim_job = None

    def _define(self, name: str, value: float = 0.0, rate: float = 0.28) -> None:
        self._values[name] = value
        self._targets[name] = value
        self._rates[name] = rate

    def _v(self, name: str) -> float:
        return self._values.get(name, 0.0)

    def _to(self, name: str, target: float) -> None:
        self._targets[name] = target
        self._kick()

    def _kick(self) -> None:
        if self._anim_job is None:
            self._anim_job = self.after(FRAME_MS, self._step)

    def _step(self) -> None:
        self._anim_job = None
        moving = False
        for name, target in self._targets.items():
            current = self._values[name]
            delta = target - current
            if abs(delta) < _SETTLE:
                self._values[name] = target
                continue
            self._values[name] = current + delta * self._rates[name]
            moving = True
        try:
            self._paint()
        except tk.TclError:
            return
        if moving or self._keep_animating():
            self._anim_job = self.after(FRAME_MS, self._step)

    def _keep_animating(self) -> bool:
        return False

    def _paint(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Surface panel
# ---------------------------------------------------------------------------
class Panel(tk.Frame):
    """Flat rounded surface with subtle elevation."""

    def __init__(
        self,
        master,
        page: Page,
        *,
        radius: int = Space.RADIUS_LG,
        fill: str | None = None,
        pad: int = Space.LG,
        border: str | None = None,
        **kwargs,
    ) -> None:
        colors = get_colors()
        fill = fill or colors.SURFACE
        super().__init__(master, bg=fill, highlightthickness=0, bd=0, **kwargs)
        self._modern_root = True
        self._opaque = True
        self._page = page
        self._radius = radius
        self._fill = fill
        self._border = border
        self._pad = pad
        self._photo = None
        self._size = (0, 0)

        self._bg = tk.Canvas(self, highlightthickness=0, bd=0, bg=fill)
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg._opaque = True

        self.body = tk.Frame(self, bg=fill)
        self.body.pack(fill="both", expand=True, padx=pad, pady=pad)

        self.bind("<Configure>", self._on_configure)
        page.register(self)

    def _on_configure(self, event) -> None:
        if (event.width, event.height) == self._size:
            return
        self._size = (event.width, event.height)
        self.refresh_surface()

    def refresh_surface(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 6 or h < 6:
            return
        colors = get_colors()
        x, y = self._page.offset(self)
        arr = self._page.backdrop.compose(
            x, y, w, h,
            radius=self._radius,
            fill=self._fill or colors.SURFACE,
            border=self._border or colors.BORDER,
        )
        self._photo = Backdrop.to_photo(arr)
        self._bg.delete("all")
        self._bg.create_image(0, 0, image=self._photo, anchor="nw")
        self._apply_tint(self._fill or colors.SURFACE)

    def _apply_tint(self, color: str) -> None:
        try:
            self.configure(bg=color)
            self.body.configure(bg=color)
        except tk.TclError:
            return
        for widget in _descendants(self.body):
            if getattr(widget, "_opaque", False):
                continue
            if isinstance(widget, (tk.Frame, tk.Label, tk.Canvas)):
                try:
                    widget.configure(bg=color)
                except tk.TclError:
                    pass


# ---------------------------------------------------------------------------
# Preview well
# ---------------------------------------------------------------------------
class Well(tk.Canvas):
    """Deep preview area — sunken, dark, no border."""

    def __init__(
        self, master, page: Page, *, radius: int = Space.RADIUS_LG, **kwargs
    ) -> None:
        colors = get_colors()
        super().__init__(master, highlightthickness=0, bd=0, bg=colors.STAGE, **kwargs)
        self._opaque = True
        self._page = page
        self._radius = radius
        self._photo = None
        self._size = (0, 0)
        self.bind("<Configure>", self._on_configure)
        page.register(self)

    def _on_configure(self, event) -> None:
        if (event.width, event.height) == self._size:
            return
        self._size = (event.width, event.height)
        self.refresh_surface()

    def refresh_surface(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8 or h < 8:
            return
        colors = get_colors()
        x, y = self._page.offset(self)
        arr = self._page.backdrop.compose(
            x, y, w, h,
            radius=self._radius,
            fill=colors.STAGE,
        )
        self._photo = Backdrop.to_photo(arr)
        self.reset()

    def reset(self) -> None:
        self.delete("all")
        if self._photo is not None:
            self.create_image(0, 0, image=self._photo, anchor="nw")


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------
class Button(tk.Canvas, _Animated):
    """Modern pill or rounded button. Primary | Ghost variants."""

    def __init__(
        self,
        master,
        page: Page,
        text: str,
        command: Callable | None = None,
        *,
        variant: str = "primary",
        height: int = 44,
        icon: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            height=height,
            highlightthickness=0,
            bd=0,
            bg=get_colors().BASE,
            cursor="hand2",
            **kwargs,
        )
        self._opaque = True
        self._page = page
        self._text = text
        self._command = command
        self._icon = icon
        self._variant = variant
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._size = (200, height)
        self._cache: dict = {}
        self._spin = 0.0
        self._glow_radius = 0.0

        self._init_anim()
        self._define("level", 0.0, rate=0.26)
        self._define("inset", 0.0, rate=0.42)
        self._define("glow", 0.0, rate=0.18)

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_text(self, text: str) -> None:
        self._text = text
        self._paint()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self._cache.clear()
        self._paint()

    def set_icon(self, icon: str | None) -> None:
        self._icon = icon
        self._paint()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._cache.clear()
        self._paint()

    def set_loading(self, loading: bool) -> None:
        if hasattr(self, "_loading") and self._loading == loading:
            return
        self._loading = loading
        self._kick()
        self._paint()

    def refresh_surface(self) -> None:
        self._cache.clear()
        self._paint()

    def _on_configure(self, event) -> None:
        if (event.width, event.height) == self._size:
            return
        self._size = (event.width, event.height)
        self._cache.clear()
        self._paint()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        if self._enabled:
            self._to("level", 1.0)
            self._to("glow", 1.0)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._pressed = False
        self._to("level", 0.0)
        self._to("inset", 0.0)
        self._to("glow", 0.0)

    def _on_press(self, _event=None) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self._to("inset", 1.5)
        self._to("level", 1.25)
        self._to("glow", 0.5)

    def _on_release(self, event=None) -> None:
        fired = self._pressed
        self._pressed = False
        self._to("inset", 0.0)
        self._to("level", 1.0 if self._hover else 0.0)
        self._to("glow", 1.0 if self._hover else 0.0)
        if fired and self._enabled and self._command:
            self._command()

    def _keep_animating(self) -> bool:
        return getattr(self, "_loading", False) or self._v("glow") > 0.01

    def _paint(self) -> None:
        w, h = self._size
        if w < 20:
            return
        level = self._v("level")
        inset = int(round(self._v("inset")))
        key = (w, h, self._variant, round(level * 5), inset, self._enabled)
        cached = self._cache.get(key)

        if cached is None:
            x, y = self._page.offset(self)
            colors = get_colors()

            if self._variant == "primary":
                fill = mix(colors.ACCENT_DEEP, colors.ACCENT_HOVER, min(1.0, level))
                fg = "#FFFFFF"
                border = colors.ACCENT
            elif self._variant == "record":
                fill = mix(colors.REC, "#FF8A96", min(1.0, level))
                fg = "#FFFFFF"
                border = colors.REC
            elif self._variant == "stop":
                fill = mix(colors.SURFACE_ALT, colors.SURFACE_HOVER, min(1.0, level))
                fg = colors.TEXT
                border = colors.BORDER
            else:  # ghost
                fill = mix(colors.SURFACE_ALT, colors.SURFACE_HOVER, min(1.0, level))
                fg = mix(colors.TEXT_3, colors.TEXT, min(1.0, level))
                border = colors.BORDER_SUBTLE

            if not self._enabled:
                fill = colors.SURFACE_ALT
                fg = colors.TEXT_DISABLED
                border = None

            arr = self._page.backdrop.compose(
                x, y, w, h,
                radius=max(10, h // 2),
                fill=fill,
                border=border,
            )
            photo = Backdrop.to_photo(arr)
            self._cache[key] = photo
            self._avg = Backdrop.average(arr, inset=6)
        else:
            photo = cached
            fg = get_colors().TEXT

        self.delete("all")
        self.create_image(0, 0, image=photo, anchor="nw")

        cy = h / 2 + (1 if self._pressed else 0)

        text_x = w / 2 + (8 if self._icon else 0)
        self.create_text(text_x, cy, text=self._text, fill=fg, font=Type.BUTTON, anchor="center")

        if self._icon:
            self._draw_icon(text_x - measure(Type.BUTTON, self._text) / 2 - 12, cy, fg)

    def _draw_icon(self, cx: float, cy: float, fg: str) -> None:
        if self._icon == "dot":
            self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=fg, outline="")
        elif self._icon == "square":
            s = 4
            self.create_rectangle(cx - s, cy - s, cx + s, cy + s, fill=fg, outline="")
        elif self._icon == "folder":
            self.create_rectangle(cx - 5, cy - 3, cx + 5, cy + 4, outline=fg, width=1.2)
            self.create_line(cx - 5, cy - 3, cx - 2, cy - 6, cx + 1, cy - 3, fill=fg)
        elif self._icon == "refresh":
            self.create_arc(cx - 5, cy - 5, cx + 5, cy + 5, start=45, extent=270,
                            style="arc", outline=fg, width=1.4)


# ---------------------------------------------------------------------------
# Icon button
# ---------------------------------------------------------------------------
class IconButton(tk.Canvas, _Animated):
    """Small circular icon button — ghost style."""

    def __init__(
        self,
        master,
        page: Page,
        glyph: str,
        command: Callable,
        *,
        size: int = 36,
        tooltip: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master, width=size, height=size,
            highlightthickness=0, bd=0, bg=get_colors().BASE, cursor="hand2", **kwargs,
        )
        self._opaque = True
        self._page = page
        self._glyph = glyph
        self._command = command
        self._dim = size
        self._cache: dict = {}
        self._init_anim()
        self._define("level", 0.0, rate=0.28)
        self.bind("<Enter>", lambda _e: self._to("level", 1.0))
        self.bind("<Leave>", lambda _e: self._to("level", 0.0))
        self.bind("<Button-1>", lambda _e: command())
        self.bind("<Configure>", lambda _e: self._paint())
        if tooltip:
            Tooltip(self, tooltip)

    def refresh_surface(self) -> None:
        self._cache.clear()
        self._paint()

    def _paint(self) -> None:
        size = self._dim
        level = self._v("level")
        key = round(level * 5)
        cached = self._cache.get(key)
        if cached is None:
            colors = get_colors()
            x, y = self._page.offset(self)
            fill = mix(colors.SURFACE_ALT, colors.SURFACE_HOVER, min(1.0, level))
            arr = self._page.backdrop.compose(
                x, y, size, size,
                radius=size // 2,
                fill=fill,
                border=colors.BORDER,
            )
            cached = Backdrop.to_photo(arr)
            self._cache[key] = cached
        self.delete("all")
        self.create_image(0, 0, image=cached, anchor="nw")
        self.create_text(
            size / 2, size / 2,
            text=self._glyph,
            fill=mix(get_colors().TEXT_3, get_colors().TEXT, level),
            font=(Type.UI, 13),
        )


# ---------------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------------
class Tooltip:
    """Minimal tooltip."""

    def __init__(self, widget: tk.Misc, text: str, delay: int = 420) -> None:
        self._widget = widget
        self._text = text
        self._delay = delay
        self._job = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self._widget.after(self._delay, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self._widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self) -> None:
        if self._window is not None:
            return
        try:
            x = self._widget.winfo_rootx() + self._widget.winfo_width() // 2
            y = self._widget.winfo_rooty() - 32
        except tk.TclError:
            return
        colors = get_colors()
        win = tk.Toplevel(self._widget)
        win.overrideredirect(True)
        win.configure(bg=colors.SURFACE_ACTIVE)
        try:
            win.wm_attributes("-alpha", 0.96)
            win.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            win, text=self._text, bg=colors.SURFACE_ACTIVE,
            fg=colors.TEXT_2, font=Type.TINY, padx=10, pady=5,
        )
        label.pack()
        win.update_idletasks()
        win.geometry(f"+{x - win.winfo_width() // 2}+{y}")
        self._window = win

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


# ---------------------------------------------------------------------------
# Segmented control
# ---------------------------------------------------------------------------
class Segmented(tk.Canvas, _Animated):
    """Pill control whose indicator slides between options — modern style."""

    def __init__(
        self,
        master,
        page: Page,
        options: list[tuple[str, str]],
        variable: tk.StringVar,
        command: Callable | None = None,
        *,
        height: int = 38,
        **kwargs,
    ) -> None:
        super().__init__(
            master, height=height,
            highlightthickness=0, bd=0, bg=get_colors().BASE, cursor="hand2", **kwargs,
        )
        self._opaque = True
        self._page = page
        self._choices = options
        self._var = variable
        self._command = command
        self._height = height
        self._width = 0
        self._hover_index = -1
        self._photo = None

        self._init_anim()
        self._define("pos", float(self._index()), rate=0.28)

        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        variable.trace_add("write", lambda *_: self._sync())

    def _index(self) -> int:
        keys = [key for key, _ in self._choices]
        value = self._var.get()
        return keys.index(value) if value in keys else 0

    def _sync(self) -> None:
        self._to("pos", float(self._index()))

    def _on_configure(self, event) -> None:
        if event.width == self._width:
            return
        self._width = event.width
        self._paint()

    def _seg_width(self) -> float:
        return max(1.0, (self._width - 6) / max(1, len(self._choices)))

    def _hit(self, x: int) -> int:
        index = int((x - 3) // self._seg_width())
        return max(0, min(len(self._choices) - 1, index))

    def _on_motion(self, event) -> None:
        index = self._hit(event.x)
        if index != self._hover_index:
            self._hover_index = index
            self._paint()

    def _on_leave(self, _event=None) -> None:
        self._hover_index = -1
        self._paint()

    def _on_click(self, event) -> None:
        key = self._choices[self._hit(event.x)][0]
        if key != self._var.get():
            self._var.set(key)
            if self._command:
                self._command(key)

    def refresh_surface(self) -> None:
        self._paint()

    def _paint(self) -> None:
        w, h = self._width, self._height
        if w < 24:
            return
        colors = get_colors()
        x, y = self._page.offset(self)
        arr = self._page.backdrop.compose(
            x, y, w, h,
            radius=h // 2,
            fill=colors.SURFACE_ALT,
        )

        seg = self._seg_width()
        pos = self._v("pos")
        pad = 3
        ix = int(round(pad + pos * seg))
        iw = int(round(seg))
        indicator = self._page.backdrop.compose(
            0, 0, iw, h - 2 * pad,
            radius=(h - 2 * pad) // 2,
            fill=colors.ACCENT,
        )
        arr[pad : h - pad, ix : ix + iw] = indicator

        self._photo = Backdrop.to_photo(arr)
        self.delete("all")
        self.create_image(0, 0, image=self._photo, anchor="nw")

        active = self._index()
        for i, (_key, label) in enumerate(self._choices):
            cx = pad + seg * (i + 0.5)
            weight = max(0.0, 1.0 - abs(pos - i))
            if i == active:
                color = "#FFFFFF"
            elif i == self._hover_index:
                color = colors.TEXT_2
            else:
                color = colors.TEXT_4
            font = Type.BODY_MED if weight > 0.3 else Type.BODY
            self.create_text(cx, h / 2, text=label, fill=color, font=font)


# ---------------------------------------------------------------------------
# Toggle switch
# ---------------------------------------------------------------------------
class Toggle(tk.Canvas, _Animated):
    """Modern toggle switch — clean, minimal."""

    TRACK_W = 44
    TRACK_H = 24

    def __init__(
        self,
        master,
        page: Page,
        text: str,
        variable: tk.BooleanVar,
        command: Callable | None = None,
        **kwargs,
    ) -> None:
        self._text = text
        width = self.TRACK_W + 12 + measure(Type.BODY, text) + 2
        super().__init__(
            master,
            width=width,
            height=max(self.TRACK_H, line_height(Type.BODY)) + 6,
            highlightthickness=0, bd=0, bg=get_colors().BASE, cursor="hand2", **kwargs,
        )
        self._opaque = True
        self._page = page
        self._var = variable
        self._command = command
        self._width = width
        self._height = max(self.TRACK_H, line_height(Type.BODY)) + 6
        self._hover = False
        self._photo = None

        self._init_anim()
        self._define("on", 1.0 if variable.get() else 0.0, rate=0.24)
        self._define("hover", 0.0, rate=0.30)

        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _e: self._to("hover", 1.0))
        self.bind("<Leave>", lambda _e: self._to("hover", 0.0))
        self.bind("<Configure>", lambda _e: self._paint())
        variable.trace_add("write", lambda *_: self._to("on", 1.0 if variable.get() else 0.0))

    def _on_click(self, _event=None) -> None:
        self._var.set(not self._var.get())
        if self._command:
            self._command()

    def refresh_surface(self) -> None:
        self._paint()

    def _paint(self) -> None:
        w, h = self._width, self._height
        if w < 20:
            return
        on = self._v("on")
        hover = self._v("hover")
        colors = get_colors()
        x, y = self._page.offset(self)
        ty = (h - self.TRACK_H) // 2

        track_fill = mix(colors.SURFACE_ALT, colors.ACCENT, on * 0.7)
        track = self._page.backdrop.compose(
            x, y + ty, self.TRACK_W, self.TRACK_H,
            radius=self.TRACK_H // 2,
            fill=track_fill,
        )

        arr = self._page.backdrop.compose(
            x, y, self._width, self._height,
            radius=0, fill=colors.BASE,
        )
        arr[ty : ty + self.TRACK_H, 0 : self.TRACK_W] = track

        knob = self.TRACK_H - 8
        travel = self.TRACK_W - knob - 8
        kx = int(round(4 + travel * ease_out_cubic(on)))
        knob_fill = mix("#FFFFFF", colors.ACCENT_HOVER, on * 0.15)
        knob_surface = self._page.backdrop.compose(
            0, 0, knob, knob,
            radius=knob // 2,
            fill=knob_fill,
        )
        arr[ty + 4 : ty + 4 + knob, kx : kx + knob] = knob_surface

        self._photo = Backdrop.to_photo(arr)
        self.delete("all")
        self.create_image(0, 0, image=self._photo, anchor="nw")
        self.create_text(
            self.TRACK_W + 12, h / 2,
            text=self._text, anchor="w",
            fill=mix(colors.TEXT_3, colors.TEXT, max(on * 0.6, hover * 0.3)),
            font=Type.BODY,
        )


# ---------------------------------------------------------------------------
# Chip / Badge
# ---------------------------------------------------------------------------
_CHIP_TONES = {
    "live": (Color.SUCCESS, "#1A3A2E"),
    "rec": ("#FFFFFF", Color.REC),
    "info": (Color.ACCENT, "#1A2540"),
    "muted": (Color.TEXT_3, Color.SURFACE_ALT),
    "accent": (Color.ACCENT_GLOW, "#1A2555"),
}


class Chip(tk.Canvas):
    """Compact pill badge — minimal, with optional dot."""

    def __init__(
        self,
        master,
        page: Page,
        text: str,
        *,
        tone: str = "muted",
        dot: bool = False,
        height: int = 26,
        **kwargs,
    ) -> None:
        self._text = text
        self._tone = tone
        self._dot = dot
        self._height = height
        self._padx = 10
        width = self._needed_width()
        super().__init__(
            master, width=width, height=height,
            highlightthickness=0, bd=0, bg=get_colors().BASE, **kwargs,
        )
        self._opaque = True
        self._page = page
        self._width = width
        self._photo = None
        self._pulse = 0.0
        self._pulsing = False
        self._job = None
        self.bind("<Configure>", lambda _e: self._paint())

    def _needed_width(self) -> int:
        return self._padx * 2 + measure(Type.CHIP, self._text) + (12 if self._dot else 0)

    def set(self, text: str, tone: str | None = None, *, dot: bool | None = None) -> None:
        changed = text != self._text or (dot is not None and dot != self._dot)
        self._text = text
        if tone is not None:
            self._tone = tone
        if dot is not None:
            self._dot = dot
        if changed:
            self._width = self._needed_width()
            self.configure(width=self._width)
        self._paint()

    def set_pulsing(self, pulsing: bool) -> None:
        if self._pulsing == pulsing:
            return
        self._pulsing = pulsing
        if pulsing:
            self._animate()
        else:
            if self._job is not None:
                try:
                    self.after_cancel(self._job)
                except Exception:
                    pass
                self._job = None
            self._pulse = 0.0
            self._paint()

    def _animate(self) -> None:
        self._job = None
        if not self._pulsing:
            return
        self._pulse = (self._pulse + 0.09) % 1.0
        self._paint()
        self._job = self.after(40, self._animate)

    def refresh_surface(self) -> None:
        self._paint()

    def _paint(self) -> None:
        w, h = self._width, self._height
        if w < 8:
            return
        colors = get_colors()
        fg, bg = _CHIP_TONES.get(self._tone, _CHIP_TONES["muted"])
        x, y = self._page.offset(self)
        arr = self._page.backdrop.compose(
            x, y, w, h,
            radius=h // 2,
            fill=bg,
            border=colors.BORDER,
        )
        self._photo = Backdrop.to_photo(arr)
        self.delete("all")
        self.create_image(0, 0, image=self._photo, anchor="nw")

        text_x = self._padx + (12 if self._dot else 0)
        if self._dot:
            r = 3
            cx, cy = self._padx + 3, h / 2
            if self._pulsing:
                glow = r + 3 + (math.sin(self._pulse * math.tau) + 1) * 2
                self.create_oval(cx - glow, cy - glow, cx + glow, cy + glow,
                                 fill=mix(bg, fg, 0.3), outline="")
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fg, outline="")
        self.create_text(text_x, h / 2, text=self._text, anchor="w", fill=fg, font=Type.CHIP)


# ---------------------------------------------------------------------------
# Sunken field well (for entry)
# ---------------------------------------------------------------------------
class Field(tk.Frame):
    """Sunken input well with animated focus border."""

    def __init__(
        self,
        master,
        page: Page,
        *,
        radius: int = Space.RADIUS_SM,
        padx: int = 12,
        pady: int = 8,
        **kwargs,
    ) -> None:
        colors = get_colors()
        super().__init__(master, bg=colors.BASE, highlightthickness=0, bd=0, **kwargs)
        self._modern_root = True
        self._opaque = True
        self._page = page
        self._radius = radius
        self._focus = 0.0
        self._focus_target = 0.0
        self._focused = False
        self._job = None
        self._photo = None
        self._size = (0, 0)

        self._bg = tk.Canvas(self, highlightthickness=0, bd=0, bg=colors.BASE)
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg._opaque = True

        self.body = tk.Frame(self, bg=colors.BASE)
        self.body.pack(fill="both", expand=True, padx=padx, pady=pady)

        self.bind("<Configure>", self._on_configure)
        page.register(self)

    def _on_configure(self, event) -> None:
        if (event.width, event.height) == self._size:
            return
        self._size = (event.width, event.height)
        self.refresh_surface()

    def bind_focus(self, widget: tk.Misc) -> None:
        def focus_in(_event=None):
            self._focused = True
            self._set_focus(1.0)

        def focus_out(_event=None):
            self._focused = False
            self._set_focus(0.0)

        widget.bind("<FocusIn>", focus_in, add="+")
        widget.bind("<FocusOut>", focus_out, add="+")
        widget.bind(
            "<Enter>",
            lambda _e: self._set_focus(1.0 if self._focused else 0.4),
            add="+",
        )
        widget.bind(
            "<Leave>",
            lambda _e: self._set_focus(1.0 if self._focused else 0.0),
            add="+",
        )

    def _set_focus(self, value: float) -> None:
        self._focus_target = value
        if self._job is None:
            self._job = self.after(FRAME_MS, self._animate)

    def _animate(self) -> None:
        self._job = None
        delta = self._focus_target - self._focus
        if abs(delta) < 0.01:
            self._focus = self._focus_target
            self.refresh_surface()
            return
        self._focus += delta * 0.3
        self.refresh_surface()
        self._job = self.after(FRAME_MS, self._animate)

    def refresh_surface(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 6 or h < 6:
            return
        colors = get_colors()
        x, y = self._page.offset(self)
        fill = mix(colors.SURFACE_ALT, colors.SURFACE_HOVER, self._focus * 0.3)
        border = colors.BORDER_FOCUS if self._focus > 0.5 else None
        arr = self._page.backdrop.compose(
            x, y, w, h,
            radius=self._radius,
            fill=fill,
            border=border,
            border_width=1,
        )
        self._photo = Backdrop.to_photo(arr)
        self._bg.delete("all")
        self._bg.create_image(0, 0, image=self._photo, anchor="nw")

        color = Backdrop.average(arr, inset=6)
        try:
            self.configure(bg=color)
            self.body.configure(bg=color)
        except tk.TclError:
            return
        for widget in _descendants(self.body):
            if getattr(widget, "_opaque", False):
                continue
            if isinstance(widget, (tk.Frame, tk.Label, tk.Canvas)):
                try:
                    widget.configure(bg=color)
                except tk.TclError:
                    pass


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
class Entry(Field):
    """Field preconfigured with a borderless Entry inside."""

    def __init__(
        self,
        master,
        page: Page,
        textvariable: tk.StringVar,
        *,
        placeholder: str = "",
        font: tuple | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, page, **kwargs)
        colors = get_colors()
        self.entry = tk.Entry(
            self.body,
            textvariable=textvariable,
            bg=colors.BASE,
            fg=colors.TEXT,
            insertbackground=colors.ACCENT,
            insertwidth=2,
            relief="flat",
            font=font or Type.BODY,
            highlightthickness=0,
            bd=0,
        )
        self.entry.pack(fill="x")
        self.bind_focus(self.entry)
        self._placeholder = placeholder
        self._var = textvariable
        if placeholder:
            self._hint = tk.Label(
                self.body, text=placeholder, fg=colors.TEXT_4, font=font or Type.BODY
            )
            self._hint.bind("<Button-1>", lambda _e: self.entry.focus_set())
            self._sync_hint()
            textvariable.trace_add("write", lambda *_: self._sync_hint())

    def _sync_hint(self) -> None:
        if not self._placeholder:
            return
        if self._var.get():
            self._hint.place_forget()
        else:
            self._hint.place(x=0, y=0)


# ---------------------------------------------------------------------------
# Select
# ---------------------------------------------------------------------------
_KEY_COLOR = "#ff00ff"
_POPUP_TOP = "#1E2130"
_POPUP_BOTTOM = "#171A23"


def _popup_surface(width: int, height: int, radius: int):
    """Standalone flat panel for floating dropdowns."""
    import numpy as np
    from PIL import Image, ImageDraw

    top = np.asarray([int(_POPUP_TOP[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)
    bottom = np.asarray(
        [int(_POPUP_BOTTOM[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32
    )
    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    arr = top[None, None, :] * (1 - ramp) + bottom[None, None, :] * ramp
    arr = np.repeat(arr, width, axis=1)

    big = Image.new("L", (width * 4, height * 4), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, width * 4 - 1, height * 4 - 1), radius=radius * 4, fill=255
    )
    mask = np.asarray(big.resize((width, height), Image.LANCZOS), dtype=np.float32) / 255.0

    inner = Image.new("L", (width * 4, height * 4), 0)
    ImageDraw.Draw(inner).rounded_rectangle(
        (4, 4, width * 4 - 5, height * 4 - 5), radius=max(0, radius * 4 - 4), fill=255
    )
    inner_mask = (
        np.asarray(inner.resize((width, height), Image.LANCZOS), dtype=np.float32)
        / 255.0
    )
    ring = np.clip(mask - inner_mask, 0.0, 1.0)[..., None]
    vertical = np.linspace(0.25, 0.08, height, dtype=np.float32)[:, None, None]
    arr = arr * (1 - ring * vertical) + np.asarray([int(Color.BORDER[i:i+2], 16) for i in (1, 3, 5)]) * (ring * vertical)

    # Fully opaque surface — no transparency key
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


class Select(tk.Canvas, _Animated):
    """Dropdown with a flat popup list, hover tracking and keyboard nav."""

    ROW_H = 32
    MAX_H = 330

    def __init__(
        self,
        master,
        page: Page,
        variable: tk.StringVar,
        values: list[str] | None = None,
        *,
        height: int = 42,
        command: Callable | None = None,
        placeholder: str = "Nothing available",
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            height=height,
            highlightthickness=0,
            bd=0,
            bg=get_colors().BASE,
            cursor="hand2",
            **kwargs,
        )
        self._opaque = True
        self._page = page
        self._var = variable
        self._items = list(values or [])
        self._command = command
        self._placeholder = placeholder
        self._height = height
        self._width = 0
        self._photo = None
        self._popup: tk.Toplevel | None = None
        self._popup_canvas: tk.Canvas | None = None
        self._popup_photo = None
        self._scroll = 0
        self._hover_row = -1
        self._typed = ""

        self._init_anim()
        self._define("level", 0.0, rate=0.28)
        self._define("open", 0.0, rate=0.30)

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", lambda _e: self._to("level", 1.0))
        self.bind("<Leave>", lambda _e: self._to("level", 0.0))
        self.bind("<Button-1>", lambda _e: self.toggle())
        variable.trace_add("write", lambda *_: self._paint())

    def set_values(self, values: list[str]) -> None:
        self._items = list(values)
        if self._popup is not None:
            self._close()
        self._paint()

    def _on_configure(self, event) -> None:
        if event.width == self._width:
            return
        self._width = event.width
        self._paint()

    def refresh_surface(self) -> None:
        self._paint()

    def _paint(self) -> None:
        w, h = self._width, self._height
        if w < 24:
            return
        colors = get_colors()
        level = max(self._v("level"), self._v("open"))
        x, y = self._page.offset(self)
        arr = self._page.backdrop.compose(
            x, y, w, h,
            radius=Space.RADIUS_SM,
            fill=colors.SURFACE_ALT,
        )
        self._photo = Backdrop.to_photo(arr)
        self.delete("all")
        self.create_image(0, 0, image=self._photo, anchor="nw")

        value = self._var.get()
        text = value or self._placeholder
        color = colors.TEXT if value else colors.TEXT_4
        avail = w - 22 - 26
        self.create_text(
            13,
            h / 2,
            text=_truncate(text, Type.BODY, avail),
            anchor="w",
            fill=color,
            font=Type.BODY,
        )

        cx, cy = w - 18, h / 2
        spin = self._v("open") * 180
        chevron = mix(colors.TEXT_4, colors.ACCENT, level)
        self._draw_chevron(cx, cy, spin, chevron)

    def _draw_chevron(self, cx: float, cy: float, angle: float, color: str) -> None:
        rad = math.radians(angle)
        cos, sin = math.cos(rad), math.sin(rad)
        points = []
        for px, py in ((-4.5, -1.8), (0.0, 2.6), (4.5, -1.8)):
            points.append((cx + px * cos - py * sin, cy + px * sin + py * cos))
        self.create_line(
            points[0][0], points[0][1],
            points[1][0], points[1][1],
            points[2][0], points[2][1],
            fill=color, width=1.7, capstyle="round", joinstyle="round",
        )

    def toggle(self) -> None:
        if self._popup is not None:
            self._close()
        else:
            self._open()

    def _open(self) -> None:
        if not self._items:
            return
        rows = len(self._items)
        width = max(160, self._width)
        height = min(self.MAX_H, rows * self.ROW_H + 12)

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=_POPUP_BOTTOM)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass

        canvas = tk.Canvas(
            popup, width=width, height=height, highlightthickness=0, bd=0, bg=_POPUP_BOTTOM
        )
        canvas.pack()

        from PIL import ImageTk
        self._popup_photo = ImageTk.PhotoImage(_popup_surface(width, height, 10))
        self._popup = popup
        self._popup_canvas = canvas
        self._popup_size = (width, height)

        try:
            value = self._items.index(self._var.get())
        except ValueError:
            value = 0
        visible = max(1, (height - 12) // self.ROW_H)
        self._scroll = max(0, min(value - visible // 2, max(0, rows - visible)))
        self._hover_row = value

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self._height + 6
        screen_h = self.winfo_screenheight()
        if y + height > screen_h - 20:
            y = max(10, self.winfo_rooty() - height - 6)
        popup.geometry(f"{width}x{height}+{x}+{y}")

        canvas.bind("<Motion>", self._on_popup_motion)
        canvas.bind("<Leave>", lambda _e: self._set_hover(-1))
        canvas.bind("<Button-1>", self._on_popup_click)
        canvas.bind("<MouseWheel>", self._on_popup_wheel)
        popup.bind("<Escape>", lambda _e: self._close())
        popup.bind("<Up>", lambda _e: self._move_hover(-1))
        popup.bind("<Down>", lambda _e: self._move_hover(1))
        popup.bind("<Return>", lambda _e: self._commit(self._hover_row))
        popup.bind("<Key>", self._on_popup_key)
        popup.bind("<FocusOut>", lambda _e: self._close())
        popup.focus_force()

        self._to("open", 1.0)
        self._paint_popup()

    def _close(self) -> None:
        popup, self._popup = self._popup, None
        self._popup_canvas = None
        self._typed = ""
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
        self._to("open", 0.0)

    def _visible_rows(self) -> int:
        if self._popup is None:
            return 0
        return max(1, (self._popup_size[1] - 12) // self.ROW_H)

    def _set_hover(self, row: int) -> None:
        if row != self._hover_row:
            self._hover_row = row
            self._paint_popup()

    def _on_popup_motion(self, event) -> None:
        row = self._scroll + max(0, (event.y - 6) // self.ROW_H)
        self._set_hover(row if 0 <= row < len(self._items) else -1)

    def _on_popup_click(self, event) -> None:
        row = self._scroll + max(0, (event.y - 6) // self.ROW_H)
        self._commit(row)

    def _on_popup_wheel(self, event) -> None:
        step = -1 if event.delta > 0 else 1
        limit = max(0, len(self._items) - self._visible_rows())
        self._scroll = max(0, min(self._scroll + step * 2, limit))
        self._paint_popup()

    def _move_hover(self, delta: int) -> None:
        row = self._hover_row + delta
        row = max(0, min(len(self._items) - 1, row))
        self._hover_row = row
        visible = self._visible_rows()
        if row < self._scroll:
            self._scroll = row
        elif row >= self._scroll + visible:
            self._scroll = row - visible + 1
        self._paint_popup()

    def _on_popup_key(self, event) -> None:
        if not event.char or not event.char.isprintable():
            return
        self._typed += event.char.lower()
        for index, value in enumerate(self._items):
            if value.lower().startswith(self._typed):
                self._hover_row = index
                visible = self._visible_rows()
                self._scroll = max(0, min(index, max(0, len(self._items) - visible)))
                self._paint_popup()
                return
        self._typed = event.char.lower()

    def _commit(self, row: int) -> None:
        if 0 <= row < len(self._items):
            value = self._items[row]
            self._close()
            if value != self._var.get():
                self._var.set(value)
                if self._command:
                    self._command(value)
        else:
            self._close()

    def _paint_popup(self) -> None:
        canvas = self._popup_canvas
        if canvas is None or self._popup_photo is None:
            return
        width, height = self._popup_size
        canvas.delete("all")
        canvas.create_image(0, 0, image=self._popup_photo, anchor="nw")

        visible = self._visible_rows()
        selected = self._var.get()
        for slot in range(visible):
            index = self._scroll + slot
            if index >= len(self._items):
                break
            value = self._items[index]
            top = 6 + slot * self.ROW_H
            is_hover = index == self._hover_row
            is_selected = value == selected

            if is_hover:
                _rounded(canvas, 5, top + 1, width - 5, top + self.ROW_H - 1, 8, Color.SURFACE_HOVER)
            if is_selected:
                canvas.create_line(
                    8, top + 8, 8, top + self.ROW_H - 8,
                    fill=Color.ACCENT, width=2, capstyle="round",
                )

            color = Color.TEXT if (is_hover or is_selected) else Color.TEXT_2
            canvas.create_text(
                16, top + self.ROW_H / 2,
                text=_truncate(value, Type.BODY, width - 34),
                anchor="w", fill=color,
                font=Type.BODY_MED if is_selected else Type.BODY,
            )

        total = len(self._items)
        if total > visible:
            track_h = height - 16
            thumb_h = max(28, int(track_h * visible / total))
            span = track_h - thumb_h
            offset = int(span * self._scroll / max(1, total - visible))
            _rounded(
                canvas, width - 6, 8 + offset, width - 3, 8 + offset + thumb_h,
                2, Color.SURFACE_ACTIVE,
            )


def _rounded(canvas: tk.Canvas, x1, y1, x2, y2, r, fill) -> int:
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, fill=fill, outline="")


def _truncate(text: str, font: tuple, available: int) -> str:
    if available <= 8 or measure(font, text) <= available:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(font, text[:mid] + ellipsis) <= available:
            low = mid
        else:
            high = mid - 1
    return text[:low] + ellipsis if low else ellipsis


# ---------------------------------------------------------------------------
# Theme management
# ---------------------------------------------------------------------------
def get_colors():
    """Return the current color class."""
    return Color
