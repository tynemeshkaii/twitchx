"""Phase 5 — contrast on surfaces that stay dark in both themes.

    P1-8      .uptime-badge / .ms-audio-state / #seek-tooltip used --text-*
              tokens on fixed-dark backgrounds (≈2.4:1 in the light theme)
    P3-toast  toasts were a 5-14% tint over whatever content was behind them

Composite math assumes the worst case backdrop for each surface (pure white
video frame / thumbnail), since the app cannot control what is behind.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_contrast import (
    Color,
    contrast_ratio,
    load_theme_tokens,
    parse_color,
)

CSS = Path(__file__).parent.parent / "ui" / "css"
THEMES = ("dark", "light")

WHITE = Color(255, 255, 255)
BLACK = Color(0, 0, 0)


def _alpha(value: str) -> float:
    m = re.search(r"rgba?\([^)]*?,\s*([\d.]+)\s*\)", value)
    if m:
        return float(m.group(1))
    m = re.search(r"/\s*([\d.]+)\s*\)", value)
    return float(m.group(1)) if m else 1.0


def composite(fg: str, backdrop: Color) -> Color:
    """Flatten a possibly translucent CSS color over an opaque backdrop."""
    color = parse_color(fg)
    a = _alpha(fg)
    return Color(
        r=color.r * a + backdrop.r * (1 - a),
        g=color.g * a + backdrop.g * (1 - a),
        b=color.b * a + backdrop.b * (1 - a),
    )


def _rule_body(path: Path, selector: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(selector + " {")
    return text[start : text.index("}", start)]


def _decl(body: str, prop: str) -> str:
    m = re.search(rf"(?<![-\w]){prop}:\s*([^;]+);", body)
    assert m is not None, f"{prop} not found in {body!r}"
    return m.group(1).strip()


def _token(theme: str, name: str) -> str:
    return load_theme_tokens(CSS / "themes" / f"{theme}.css")[name]


# (file, selector) pairs whose background stays dark regardless of theme
FIXED_DARK_SURFACES = [
    ("components/stream-card.css", ".uptime-badge"),
    ("components/multistream.css", ".ms-audio-state"),
    ("components/player-view.css", "#seek-tooltip"),
]


@pytest.mark.parametrize("rel_path,selector", FIXED_DARK_SURFACES)
def test_fixed_dark_surfaces_do_not_use_theme_text(
    rel_path: str, selector: str
) -> None:
    """--text-primary/secondary/muted flip with the theme; these surfaces do not."""
    body = _rule_body(CSS / rel_path, selector)
    color = _decl(body, "color")
    assert not re.search(r"var\(--text-(primary|secondary|muted)", color), color


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("backdrop", [WHITE, BLACK], ids=["on-white", "on-black"])
@pytest.mark.parametrize("rel_path,selector", FIXED_DARK_SURFACES)
def test_fixed_dark_surface_contrast(
    theme: str, backdrop: Color, rel_path: str, selector: str
) -> None:
    body = _rule_body(CSS / rel_path, selector)
    bg_decl = _decl(body, "background")
    if bg_decl.startswith("var("):
        bg_decl = _token(theme, bg_decl[6:-1])
    color_decl = _decl(body, "color")
    if color_decl.startswith("var("):
        color_decl = _token(theme, color_decl[6:-1])

    surface = composite(bg_decl, backdrop)
    text = composite(color_decl, surface)
    ratio = contrast_ratio(text, surface)
    assert ratio >= 4.5, f"{theme}: {selector} over {backdrop} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("backdrop", [WHITE, BLACK], ids=["on-white", "on-black"])
@pytest.mark.parametrize("kind", ["success", "error", "info", "warn"])
def test_toast_text_contrast(theme: str, backdrop: Color, kind: str) -> None:
    tokens = load_theme_tokens(CSS / "themes" / f"{theme}.css")
    surface = composite(tokens["toast-surface"], backdrop)
    tinted = composite(tokens[f"toast-bg-{kind}"], surface)

    body_text = parse_color(tokens["text-primary"])
    assert contrast_ratio(body_text, tinted) >= 4.5, f"{theme}/{kind}: toast text"

    icon = tokens[f"toast-text-{kind}"]
    if icon.startswith("var("):
        icon = tokens[icon[6:-1]]
    assert contrast_ratio(parse_color(icon), tinted) >= 4.5, f"{theme}/{kind}: icon"


def test_toast_paints_an_opaque_surface() -> None:
    css = (CSS / "components" / "toast.css").read_text(encoding="utf-8")
    assert "background: var(--toast-surface);" in css
    for kind in ("success", "error", "info", "warn"):
        assert (
            f"linear-gradient(var(--toast-bg-{kind}), var(--toast-bg-{kind})),\n"
            "    var(--toast-surface);" in css
        )


FIXED_DARK_BACKGROUND = re.compile(
    r"rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*(0?\.[5-9]\d*|1(\.0+)?)\s*\)"
    r"|var\(--bg-dark-\d+\)"
    r"|var\(--bg-tooltip-dark\)"
)
THEME_TEXT_TOKEN = re.compile(r"color:\s*var\(--text-(primary|secondary|muted)")


def test_no_theme_text_on_fixed_dark_backgrounds() -> None:
    """Sweep every rule, not just the three the audit happened to spot."""
    offenders = []
    for path in sorted(CSS.rglob("*.css")):
        if path.parent.name == "themes":
            continue
        for match in re.finditer(
            r"([^{}]+)\{([^{}]*)\}", path.read_text(encoding="utf-8")
        ):
            selector = " ".join(match.group(1).split())
            body = match.group(2)
            background = re.search(r"background(-color)?:\s*([^;]+);", body)
            if not background or not FIXED_DARK_BACKGROUND.search(background.group(2)):
                continue
            if THEME_TEXT_TOKEN.search(body):
                offenders.append(f"{path.relative_to(CSS)}: {selector[:60]}")
    assert offenders == []
