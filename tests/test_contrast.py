"""Contrast ratio smoke tests for TwitchX themes.

Parses the dark/light theme CSS files and checks that critical foreground/
background pairs meet WCAG AA (4.5:1 for normal text).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest


class Color(NamedTuple):
    r: float
    g: float
    b: float

    @property
    def luminance(self) -> float:
        def _channel(c: float) -> float:
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return (
            0.2126 * _channel(self.r)
            + 0.7152 * _channel(self.g)
            + 0.0722 * _channel(self.b)
        )


def _parse_hex(value: str) -> Color:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return Color(
        r=int(value[0:2], 16),
        g=int(value[2:4], 16),
        b=int(value[4:6], 16),
    )


def _parse_rgb(value: str) -> Color:
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value)
    if not m:
        raise ValueError(f"Cannot parse rgb value: {value}")
    return Color(r=int(m.group(1)), g=int(m.group(2)), b=int(m.group(3)))


def _parse_hsl(value: str) -> Color:
    m = re.match(
        r"hsla?\(\s*(\d+(?:\.\d+)?)\s+([\d.]+)%\s+([\d.]+)%",
        value,
    ) or re.match(
        r"hsla?\(\s*(\d+(?:\.\d+)?)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%",
        value,
    )
    if not m:
        raise ValueError(f"Cannot parse hsl value: {value}")
    hue = float(m.group(1)) / 360.0
    saturation = float(m.group(2)) / 100.0
    lightness = float(m.group(3)) / 100.0

    def _hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    if saturation == 0:
        r = g = b = lightness
    else:
        q = lightness * (1 + saturation) if lightness < 0.5 else lightness + saturation - lightness * saturation
        p = 2 * lightness - q
        r = _hue_to_rgb(p, q, hue + 1 / 3)
        g = _hue_to_rgb(p, q, hue)
        b = _hue_to_rgb(p, q, hue - 1 / 3)

    return Color(r=round(r * 255), g=round(g * 255), b=round(b * 255))


def parse_color(value: str) -> Color:
    value = value.strip()
    if value.startswith("#"):
        return _parse_hex(value)
    if value.startswith("rgb"):
        return _parse_rgb(value)
    if value.startswith("hsl"):
        return _parse_hsl(value)
    raise ValueError(f"Unsupported color format: {value!r}")


def contrast_ratio(c1: Color, c2: Color) -> float:
    l1, l2 = c1.luminance, c2.luminance
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def load_theme_tokens(theme_path: Path) -> dict[str, str]:
    text = theme_path.read_text(encoding="utf-8")
    tokens: dict[str, str] = {}
    for match in re.finditer(r"--([\w-]+):\s*([^;]+);", text):
        tokens[match.group(1)] = match.group(2).strip()
    return tokens


def resolve_color(
    tokens: dict[str, str], name: str, accent_override: str | None = None
) -> Color:
    raw = tokens[name]
    if raw.startswith("var("):
        ref = raw[4:-1].strip().removeprefix("--")
        raw = tokens.get(ref, raw)
    if name == "accent" and accent_override:
        raw = accent_override
    return parse_color(raw)


ACCENT_PALETTE = [
    ("Amber", "#FF9F0A"),
    ("Purple", "#BF5AF2"),
    ("Blue", "#0A84FF"),
    ("Green", "#30D158"),
    ("Red", "#FF453A"),
    ("Pink", "#FF2D55"),
]

# Critical text/background pairs that must meet WCAG AA normal text (4.5:1).
TEXT_PAIRS = [
    ("text-primary", "bg-base"),
    ("text-secondary", "bg-base"),
    ("text-secondary", "bg-elevated"),
    ("text-muted", "bg-base"),
    ("text-muted", "bg-elevated"),
]

# Status colors used as foreground text on surfaces.
STATUS_PAIRS = [
    ("live-green", "bg-base"),
    ("error-red", "bg-base"),
    ("warn-yellow", "bg-base"),
]


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("fg_name,bg_name", TEXT_PAIRS + STATUS_PAIRS)
def test_theme_text_contrast(theme: str, fg_name: str, bg_name: str) -> None:
    theme_path = Path(__file__).parent.parent / "ui" / "css" / "themes" / f"{theme}.css"
    tokens = load_theme_tokens(theme_path)
    fg = resolve_color(tokens, fg_name)
    bg = resolve_color(tokens, bg_name)
    ratio = contrast_ratio(fg, bg)
    assert ratio >= 4.5, f"{theme}: {fg_name} on {bg_name} contrast is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("accent_name,accent_value", ACCENT_PALETTE)
def test_accent_contrast(theme: str, accent_name: str, accent_value: str) -> None:
    theme_path = Path(__file__).parent.parent / "ui" / "css" / "themes" / f"{theme}.css"
    tokens = load_theme_tokens(theme_path)
    accent = parse_color(accent_value)
    on_accent = resolve_color(tokens, "text-on-accent")

    # Text placed on top of accent-filled buttons must be readable.
    btn_ratio = contrast_ratio(on_accent, accent)
    assert btn_ratio >= 4.5, (
        f"{theme} {accent_name}: text-on-accent on {accent_name} contrast is {btn_ratio:.2f}:1"
    )
