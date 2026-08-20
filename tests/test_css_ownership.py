"""Phase 7 / P2-21 — every CSS selector has exactly one owner file.

The legacy layout.css / views.css / player.css sheets loaded last and shadowed
the component files, so the same selector was styled in two places and the
cascade decided the winner by accident.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.css_ownership import CSS_DIR, iter_rules, stylesheet_order, violations

ROOT = Path(__file__).parent.parent


def test_no_selector_is_defined_in_two_files() -> None:
    offenders = violations()
    assert offenders == {}, offenders


def test_legacy_catch_all_sheets_are_gone() -> None:
    assert not (CSS_DIR / "views.css").exists()
    assert not (CSS_DIR / "player.css").exists()
    assert (CSS_DIR / "components" / "player-view.css").exists()


def test_every_linked_stylesheet_exists() -> None:
    missing = [rel for rel in stylesheet_order() if not (CSS_DIR / rel).exists()]
    assert missing == []


def test_layout_css_only_owns_the_app_frame() -> None:
    """Sidebar/search rules moved to their components; layout keeps the shell."""
    text = (CSS_DIR / "layout.css").read_text(encoding="utf-8")
    owned = set()
    for prelude, _body, layer in iter_rules(text):
        if layer == "drag-regions":
            continue
        for selector in prelude.split(","):
            owned.add(" ".join(selector.split()))
    strays = [
        s
        for s in owned
        if re.match(
            r"^#(sidebar|profile-area|kick-profile-area|platform-tabs|"
            r"favorites-header|channel-list|search-area|search-row)\b",
            s,
        )
    ]
    assert strays == []


def test_layer_marker_covers_only_the_next_rule() -> None:
    """A sticky marker would exempt every rule below it in the same file."""
    sample = (
        "/* css-layer: drag-regions */\n"
        ".a { -webkit-app-region: drag; }\n"
        ".b { color: red; }\n"
    )
    layers = [layer for _prelude, _body, layer in iter_rules(sample)]
    assert layers == ["drag-regions", None]


@pytest.mark.parametrize(
    "layer,rel",
    [
        ("theme-tokens", "tokens.css"),
        ("drag-regions", "layout.css"),
        ("text-selection", "reset.css"),
    ],
)
def test_cross_cutting_layers_declare_themselves(layer: str, rel: str) -> None:
    """The three exempt layers must stay explicitly marked, or the checker
    would silently start ignoring real duplicates."""
    assert f"css-layer: {layer}" in (CSS_DIR / rel).read_text(encoding="utf-8")
