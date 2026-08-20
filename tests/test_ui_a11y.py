"""Phase 4 — keyboard and accessibility guards.

P1-6   Enter/Space were hijacked globally, breaking Tab navigation
P1-7   .logout-link buttons rendered as unstyled UA chrome (invisible in light)
P2-15  the skip-link peeked out at the top of every screen
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).parent.parent / "ui"


def _css_rule(path: Path, selector: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(selector + " {")
    return text[start : text.index("}", start)]


def test_activation_keys_are_left_to_the_focused_control() -> None:
    js = (UI / "js" / "keyboard.js").read_text(encoding="utf-8")
    assert "function focusOwnsActivationKeys()" in js
    guard = js.index(
        "if ((e.key === 'Enter' || e.key === ' ') && focusOwnsActivationKeys()) return;"
    )
    watch = js.index("if (e.key === sc.watch || e.key === 'Enter')")
    # the guard must run before the global watch shortcut
    assert guard < watch


def test_activation_guard_covers_real_controls() -> None:
    js = (UI / "js" / "keyboard.js").read_text(encoding="utf-8")
    selector = re.search(r"ACTIVATION_TARGET_SELECTOR =\s*\n?\s*'([^']+)'", js)
    assert selector is not None
    for needed in ("button", "a[href]", '[role="button"]', '[role="tab"]'):
        assert needed in selector.group(1)


def test_channel_targets_still_watch_on_activation() -> None:
    """Grid cards / sidebar rows keep the select-then-watch behaviour."""
    js = (UI / "js" / "keyboard.js").read_text(encoding="utf-8")
    channel = re.search(r"CHANNEL_TARGET_SELECTOR = '([^']+)'", js)
    assert channel is not None
    assert ".stream-card" in channel.group(1)
    assert ".channel-item" in channel.group(1)
    assert ".rail-avatar" in channel.group(1)
    assert "if (el.closest(CHANNEL_TARGET_SELECTOR)) return false;" in js


def test_logout_link_resets_ua_button_chrome() -> None:
    rule = _css_rule(UI / "css" / "components" / "settings.css", ".logout-link")
    assert "background: none" in rule
    assert "border: none" in rule
    assert "padding: 0" in rule
    assert "font: inherit" in rule
    css = (UI / "css" / "components" / "settings.css").read_text(encoding="utf-8")
    assert ".logout-link:focus-visible" in css
    assert ".logout-link:hover" in css


def test_skip_link_is_parked_off_screen() -> None:
    reset = UI / "css" / "reset.css"
    rule = _css_rule(reset, ".skip-link")
    assert "top: -100px" in rule
    # no transform trickery that can leave a sliver on screen
    assert "transform:" not in rule
    focus_rule = _css_rule(reset, ".skip-link:focus")
    assert "top: var(--space-8)" in focus_rule
