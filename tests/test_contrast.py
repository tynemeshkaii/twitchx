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
        q = (
            lightness * (1 + saturation)
            if lightness < 0.5
            else lightness + saturation - lightness * saturation
        )
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


# Must match ACCENT_PALETTE in ui/js/settings.js (checked below).
ACCENT_PALETTE = [
    ("Amber", "#FF9F0A"),
    ("Purple", "#BF5AF2"),
    ("Blue", "#0A84FF"),
    ("Teal", "#40C8E0"),
    ("Indigo", "#5E5CE6"),
    ("Graphite", "#8E8E93"),
]

ROOT = Path(__file__).parent.parent

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


def _on_accent(accent: Color) -> Color:
    """Black or white, whichever reads better — as settings.js picks it."""
    dark, light = parse_color("#0A0A0C"), parse_color("#FFFFFF")
    return (
        dark if contrast_ratio(dark, accent) >= contrast_ratio(light, accent) else light
    )


def _hue(c: Color) -> float:
    r, g, b = c.r / 255, c.g / 255, c.b / 255
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return -1.0  # grey: no hue to clash with
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


@pytest.mark.parametrize("accent_name,accent_value", ACCENT_PALETTE)
def test_accent_contrast(accent_name: str, accent_value: str) -> None:
    accent = parse_color(accent_value)
    # Text placed on top of accent-filled buttons must be readable.
    btn_ratio = contrast_ratio(_on_accent(accent), accent)
    assert btn_ratio >= 4.5, (
        f"{accent_name}: text on the {accent_name} accent is {btn_ratio:.2f}:1"
    )


# An accent must not read as a status colour: red is live, green is
# success/connected, yellow is a warning.
STATUS_TOKENS = ("live", "live-green", "warn-yellow")
# Amber (36°) vs systemYellow (50°) reads as orange vs yellow.
MIN_HUE_DISTANCE = 12


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("accent_name,accent_value", ACCENT_PALETTE)
def test_accent_is_not_a_status_colour(
    theme: str, accent_name: str, accent_value: str
) -> None:
    tokens = load_theme_tokens(ROOT / "ui" / "css" / "themes" / f"{theme}.css")
    accent_hue = _hue(parse_color(accent_value))
    if accent_hue < 0:
        return
    for token in STATUS_TOKENS:
        status_hue = _hue(resolve_color(tokens, token))
        distance = _hue_distance(accent_hue, status_hue)
        assert distance >= MIN_HUE_DISTANCE, (
            f"{theme} {accent_name} ({accent_value}) is {distance:.0f}° from --{token}"
        )


def test_accent_palette_matches_settings_js_and_schema() -> None:
    js = (ROOT / "ui" / "js" / "settings.js").read_text(encoding="utf-8")
    block = re.search(r"const ACCENT_PALETTE = \[(.*?)\];", js, re.S)
    assert block is not None
    js_palette = re.findall(
        r"value: '(#[0-9A-Fa-f]{6})', label: '(\w+)'", block.group(1)
    )
    assert [(label, value) for value, label in js_palette] == ACCENT_PALETTE

    from ui.api.settings_schema import _ACCENT_PALETTE

    assert {value for _, value in ACCENT_PALETTE} == _ACCENT_PALETTE
