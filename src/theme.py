"""Premium design tokens for Timelapser UI — Figma/Linear/Arc quality."""

from __future__ import annotations

from .fonts import pick

# ---------------------------------------------------------------------------
# Premium dark palette — inspired by Linear, Figma, Arc Browser
# Enhanced for maximum visual appeal
# ---------------------------------------------------------------------------
BASE_RGB = (13, 15, 20)


class Color:
    # Page backgrounds — layered depth with subtle warmth
    BASE = "#0D0F14"
    BASE_DEEP = "#080A0F"
    BASE_ELEVATED = "#12151D"

    # Surfaces — refined with better contrast
    SURFACE = "#181B24"
    SURFACE_ALT = "#1E222D"
    SURFACE_HOVER = "#252A37"
    SURFACE_ACTIVE = "#2C313F"
    SURFACE_OVERLAY = "#181B24"

    # Borders — more defined for better separation
    BORDER = "#323744"
    BORDER_SUBTLE = "#282C38"
    BORDER_FOCUS = "#7B9AFF"

    # Text — perfect contrast hierarchy
    TEXT = "#F5F5F7"
    TEXT_2 = "#C8C8CC"
    TEXT_3 = "#909098"
    TEXT_4 = "#64646C"
    TEXT_DISABLED = "#3E3E48"

    # Accent — vibrant but not harsh
    ACCENT = "#7B9AFF"
    ACCENT_HOVER = "#9BB0FF"
    ACCENT_DEEP = "#6A89EE"
    ACCENT_GLOW = "#1E2D4A"
    ACCENT_SUBTLE = "#1E2D4A"

    # Semantic colors — refined
    REC = "#FF6B7A"
    REC_GLOW = "#3A1E24"
    SUCCESS = "#5ADE8A"
    WARNING = "#FFCA3A"
    ERROR = "#FF6B7A"

    DISABLED_TEXT = "#64646C"

    # Preview stage — deep, focused with better contrast
    STAGE = "#0C0E13"
    STAGE_BORDER = "#1E212A"

    # Shadows — soft, layered (used as RGB tuples, not strings)
    SHADOW_SM = (0, 0, 0, 0.25)
    SHADOW_MD = (0, 0, 0, 0.35)
    SHADOW_LG = (0, 0, 0, 0.45)
    SHADOW_GLOW = (123, 154, 255, 0.15)


class LightColor:
    """Light mode color tokens — clean, bright, professional."""
    BASE = "#F8F9FA"
    BASE_DEEP = "#FFFFFF"
    BASE_ELEVATED = "#FFFFFF"

    SURFACE = "#FFFFFF"
    SURFACE_ALT = "#F5F5F7"
    SURFACE_HOVER = "#EAEAEC"
    SURFACE_ACTIVE = "#E0E0E2"
    SURFACE_OVERLAY = "#FFFFFF"

    BORDER = "#E5E5E7"
    BORDER_SUBTLE = "#F0F0F2"
    BORDER_FOCUS = "#007AFF"

    TEXT = "#1D1D1F"
    TEXT_2 = "#424245"
    TEXT_3 = "#6E6E73"
    TEXT_4 = "#9A9AA0"
    TEXT_DISABLED = "#C7C7CC"

    ACCENT = "#007AFF"
    ACCENT_HOVER = "#0051D5"
    ACCENT_DEEP = "#0047B3"
    ACCENT_GLOW = "#E8F0FF"
    ACCENT_SUBTLE = "#F5F9FF"

    REC = "#FF3B30"
    REC_GLOW = "#FFE8E8"
    SUCCESS = "#34C759"
    WARNING = "#FF9500"
    ERROR = "#FF3B30"

    DISABLED_TEXT = "#C7C7CC"

    STAGE = "#FFFFFF"
    STAGE_BORDER = "#E5E5E7"

    SHADOW_SM = (0, 0, 0, 0.04)
    SHADOW_MD = (0, 0, 0, 0.08)
    SHADOW_LG = (0, 0, 0, 0.12)
    SHADOW_GLOW = (0, 122, 255, 0.08)


class Space:
    # 8px grid system — refined for better spacing
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32
    XXXL = 48

    # Border radius — consistent, modern
    RADIUS_XS = 6
    RADIUS_SM = 8
    RADIUS = 12
    RADIUS_LG = 16
    RADIUS_XL = 20
    RADIUS_PILL = 999

    # Additional spacing for sections
    SECTION_GAP = 20
    DIVIDER = 1


class Shadow:
    """Elevation shadows — soft, layered depth."""
    NONE = (0, 0, 0, 0)
    SM = (0, 1, 2, 0.08)
    MD = (0, 2, 4, 0.12)
    LG = (0, 4, 8, 0.16)
    XL = (0, 8, 16, 0.20)
    GLOW = (0, 0, 8, 0.15)


class Type:
    """Premium typography system — Inter font family."""

    # Font families
    UI = "Inter"
    UI_MEDIUM = "Inter Medium"
    UI_SEMI = "Inter SemiBold"
    UI_BOLD = "Inter Bold"
    DISPLAY = "Inter Bold"
    MONO = "JetBrains Mono"

    # Font sizes — consistent scale with better hierarchy
    H1 = (DISPLAY, 24)
    H2 = (UI_BOLD, 15)
    H3 = (UI_SEMI, 13)
    LABEL = (UI_MEDIUM, 11)
    EYEBROW = (UI_SEMI, 10)
    BODY = (UI, 12)
    BODY_MED = (UI_MEDIUM, 12)
    SMALL = (UI, 11)
    TINY = (UI, 10)
    STAT = (DISPLAY, 20)
    CHIP = (UI_SEMI, 11)
    BUTTON = (UI_SEMI, 13)
    CODE = (MONO, 10)


def init_typography() -> None:
    """Bind the Type tokens to the best families Tk actually resolved."""
    import tkinter.font as tkfont

    from .fonts import register_available

    register_available(set(tkfont.families()))

    Type.UI = pick("Inter", "Segoe UI")
    Type.UI_MEDIUM = pick("Inter Medium", "Segoe UI")
    Type.UI_SEMI = pick("Inter SemiBold", "Segoe UI Semibold", "Segoe UI")
    Type.UI_BOLD = pick("Inter Bold", "Segoe UI Bold", "Segoe UI")
    Type.DISPLAY = pick("Inter Bold", "Segoe UI Bold", "Segoe UI")
    Type.MONO = pick("JetBrains Mono", "Cascadia Code", "Consolas", "Courier New")

    Type.H1 = (Type.DISPLAY, 24)
    Type.H2 = (Type.UI_BOLD, 15)
    Type.H3 = (Type.UI_SEMI, 13)
    Type.LABEL = (Type.UI_MEDIUM, 11)
    Type.EYEBROW = (Type.UI_SEMI, 10)
    Type.BODY = (Type.UI, 12)
    Type.BODY_MED = (Type.UI_MEDIUM, 12)
    Type.SMALL = (Type.UI, 11)
    Type.TINY = (Type.UI, 10)
    Type.STAT = (Type.DISPLAY, 20)
    Type.CHIP = (Type.UI_SEMI, 11)
    Type.BUTTON = (Type.UI_SEMI, 13)
    Type.CODE = (Type.MONO, 10)


_THIN = "\u2009"


def tracked(text: str, tight: bool = False) -> str:
    """Fake letter-spacing for micro-labels; Tk has no tracking control."""
    joiner = "" if tight else _THIN
    return joiner.join(text)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % (
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


def mix(c1: str, c2: str, t: float) -> str:
    """Blend two hex colors; `t` of 1.0 returns `c2`."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)


def with_alpha(hex_color: str, alpha: float) -> str:
    """Convert hex color to rgba with specified alpha."""
    r, g, b = hex_to_rgb(hex_color)
    return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha))})"


# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------
def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - pow(1 - t, 3)


def ease_out_expo(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 if t >= 1 else 1 - pow(2, -10 * t)


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2
