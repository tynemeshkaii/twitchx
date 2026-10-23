"""Redesign phase 1 — component CSS stays on the token scales.

Type, spacing, radii and weights come from tokens.css; glass is reserved for
layers that float over content; the removed effects do not creep back.
Every failure names the file, the selector and the offending value.
"""

from __future__ import annotations

import re

import pytest

from tools.css_ownership import CSS_DIR, iter_rules

CHECKED = sorted((CSS_DIR / "components").glob("*.css")) + [CSS_DIR / "layout.css"]

SCALED_PROPS = re.compile(
    r"^(font-size|font-weight|border(-[a-z]+)*-radius|gap|row-gap|column-gap"
    r"|padding(-[a-z]+)?|margin(-[a-z]+)?)$"
)
SCALE_PREFIX = {
    "font-size": "font-",
    "font-weight": "weight-",
    "radius": "radius-",
    "space": "space-",
}
KEYWORDS = {"0", "1px", "50%", "auto", "inherit"}

# 2px is allowed only for indicator bars (radius) and segment/icon gaps.
TWO_PX_ALLOWED = {
    ("border-radius", 'input[type="range"]'),
    ("border-radius", "#volume-slider"),
    ("gap", "#sidebar-nav"),
    ("padding", ".segmented"),
    ("gap", ".segmented"),
    ("gap", ".emote-grid"),
    ("gap", ".drag-handle"),
    ("gap", ".watching-eq"),
    ("gap", ".player-volume"),
    ("margin-right", ".chat-msg .badge"),
    ("margin-right", ".badge-fallback"),
    ("padding", ".mod-select"),
}

# Glass only on layers floating over content (see phase 1, step 1.5.4).
BACKDROP_ALLOWED = {
    "#settings-overlay",
    "#settings-modal",
    ".modal-overlay",
    ".modal",
    "#onboarding-overlay",
    "#onboarding-modal",
    "#context-menu",
    "#group-context-menu",
    "#palette-overlay",
    "#palette-modal",
    ".toast",
    "#sidebar-tooltip",
    # chips and controls over video / thumbnails
    ".uptime-badge",
    ".watching-badge",
    ".ms-overlay",
    ".player-error-box",
    "#stats-overlay",
}

# Component-local layout lengths (a column width, not a spacing step).
LAYOUT_VARS = {"--settings-content-offset", "--traffic-lights-width"}

REMOVED_TOKENS = ("--shadow-glow-accent", "--app-noise", "--glass-content")


def _tokens() -> set[str]:
    text = (CSS_DIR / "tokens.css").read_text(encoding="utf-8")
    return set(re.findall(r"(--[\w-]+):", text))


TOKENS = _tokens()


def _decls(body: str):
    for m in re.finditer(r"(?<![\w-])([a-z-]+)\s*:\s*([^;]+);?", body):
        yield m.group(1), " ".join(m.group(2).split())


def _rules():
    for path in CHECKED:
        rel = path.relative_to(CSS_DIR)
        text = path.read_text(encoding="utf-8")
        for prelude, body, _layer in iter_rules(text, nested=True):
            prelude = " ".join(re.sub(r"/\*.*?\*/", "", prelude, flags=re.S).split())
            selectors = {s.strip() for s in prelude.split(",")}
            yield rel, prelude, selectors, re.sub(r"/\*.*?\*/", "", body, flags=re.S)


def _scale_for(prop: str) -> str:
    if prop in ("font-size", "font-weight"):
        return SCALE_PREFIX[prop]
    if prop.endswith("radius"):
        return SCALE_PREFIX["radius"]
    return SCALE_PREFIX["space"]


def _part_ok(part: str, prop: str, selectors: set[str]) -> bool:
    prefix = _scale_for(prop)
    if part in KEYWORDS:
        return True
    if part == "2px":
        base = re.sub(r"-(top|bottom|left|right)$", "", prop)
        if prop.endswith("radius"):
            base = "border-radius"
        return any((p, s) in TWO_PX_ALLOWED for p in (prop, base) for s in selectors)
    var = re.fullmatch(r"var\((--[\w-]+)\)", part)
    if var:
        name = var.group(1)
        if prefix == "space-" and name in LAYOUT_VARS:
            return True
        return name.startswith("--" + prefix) and name in TOKENS
    if part.startswith("calc("):
        names = re.findall(r"var\((--[\w-]+)\)", part)
        literals = re.findall(r"(\d+(?:\.\d+)?)px", part)
        return (
            bool(names)
            and all(n.startswith("--" + prefix) and n in TOKENS for n in names)
            and all(float(px) <= 2 for px in literals)
        )
    return False


def _split(value: str) -> list[str]:
    return re.findall(r"calc\((?:[^()]|\([^()]*\))*\)|var\([^)]*\)|\S+", value)


def test_scaled_properties_use_tokens() -> None:
    offenders = []
    for rel, prelude, selectors, body in _rules():
        for prop, value in _decls(body):
            if not SCALED_PROPS.match(prop):
                continue
            value = value.removesuffix("!important").strip()
            bad = [p for p in _split(value) if not _part_ok(p, prop, selectors)]
            if bad:
                offenders.append(f"{rel}: {prelude[:70]} → {prop}: {value}")
    assert offenders == [], (
        "Use the token scales (--font-*, --weight-*, --space-*, --radius-*):\n"
        + "\n".join(offenders)
    )


def test_backdrop_filter_only_on_floating_layers() -> None:
    offenders = []
    for rel, prelude, selectors, body in _rules():
        for prop, value in _decls(body):
            if prop not in ("backdrop-filter", "-webkit-backdrop-filter"):
                continue
            if value == "none":
                continue
            if not selectors <= BACKDROP_ALLOWED:
                offenders.append(f"{rel}: {prelude[:70]} → {prop}: {value}")
    assert offenders == [], (
        "backdrop-filter is only for layers over content (BACKDROP_ALLOWED):\n"
        + "\n".join(offenders)
    )


def test_app_shell_is_not_animated() -> None:
    offenders = [
        f"{rel}: {prelude} → {prop}: {value}"
        for rel, prelude, selectors, body in _rules()
        if "#app" in selectors
        for prop, value in _decls(body)
        if prop.startswith("animation")
    ]
    assert offenders == []


def test_at_most_four_font_weights() -> None:
    weights: dict[str, list[str]] = {}
    for rel, prelude, _selectors, body in _rules():
        for prop, value in _decls(body):
            if prop == "font-weight":
                weights.setdefault(value, []).append(f"{rel}: {prelude[:50]}")
    assert len(weights) <= 4, "\n".join(
        f"{w}: {where[0]}" for w, where in weights.items()
    )


@pytest.mark.parametrize("token", REMOVED_TOKENS)
def test_removed_effect_tokens_stay_gone(token: str) -> None:
    hits = [
        f"{path.relative_to(CSS_DIR)}:{n}: {line.strip()}"
        for path in sorted(CSS_DIR.rglob("*.css"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if token in line
    ]
    assert hits == []


def test_iter_rules_nested_reaches_media_blocks() -> None:
    sample = "@media (x) { .a { gap: 3px; } } @keyframes k { from { gap: 1px; } } .b {}"
    preludes = [p for p, _b, _l in iter_rules(sample, nested=True)]
    assert preludes == [".a", ".b"]
    assert [p for p, _b, _l in iter_rules(sample)] == [".b"]
