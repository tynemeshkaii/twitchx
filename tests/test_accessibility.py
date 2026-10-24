"""Static accessibility smoke tests for the TwitchX UI shell.

These tests parse ui/index.html and verify basic a11y invariants that can be
checked without a running browser. Dynamic JS-generated controls are covered by
manual QA and runtime audits.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

VOID_TAGS = {"img", "input", "br", "hr", "meta", "link", "source", "wbr"}


class ButtonParser(HTMLParser):
    """Collects every <button> with its text and the role of its group
    (the nearest ancestor with role=tablist / radiogroup)."""

    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str | None]] = []
        self._current: dict[str, str | None] | None = None
        self._text_stack: list[str] = []
        self._groups: list[str | None] = []  # role of each open element

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: v for k, v in attrs}
        if tag == "button":
            group = next(
                (g for g in reversed(self._groups) if g in ("tablist", "radiogroup")),
                None,
            )
            self._current = {
                "tag": tag,
                "id": attr_dict.get("id"),
                "role": attr_dict.get("role"),
                "group": group,
                "aria-label": attr_dict.get("aria-label"),
                "aria-selected": attr_dict.get("aria-selected"),
                "aria-checked": attr_dict.get("aria-checked"),
                "title": attr_dict.get("title"),
                "aria-hidden": attr_dict.get("aria-hidden"),
            }
            self._text_stack = []
        if tag not in VOID_TAGS:
            self._groups.append(attr_dict.get("role"))

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID_TAGS and self._groups:
            self._groups.pop()
        if tag == "button" and self._current is not None:
            text = "".join(self._text_stack).strip()
            self._current["text"] = text
            self.buttons.append(self._current)
            self._current = None
            self._text_stack = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text_stack.append(data)


def _visible_text_content(html_path: Path) -> list[dict[str, str | None]]:
    parser = ButtonParser()
    parser.feed(html_path.read_text(encoding="utf-8"))
    return parser.buttons


@pytest.fixture
def html_path() -> Path:
    return Path(__file__).parent.parent / "ui" / "index.html"


def test_icon_only_buttons_have_accessible_name(html_path: Path) -> None:
    """Every visible button that contains no text must have aria-label or title."""
    buttons = _visible_text_content(html_path)
    missing: list[str] = []
    for btn in buttons:
        if btn.get("aria-hidden") == "true":
            continue
        text = (btn.get("text") or "").strip()
        if text:
            continue
        if not (btn.get("aria-label") or btn.get("title")):
            missing.append(str(btn))
    assert not missing, f"Icon-only buttons missing accessible name: {missing}"


def test_buttons_inside_tablists_have_aria_selected(html_path: Path) -> None:
    """Every button in a role=tablist (platform filter, Browse platforms,
    channel tabs, settings sections) is a tab with aria-selected; every button
    in a role=radiogroup (theme, multi-view presets) is a radio with
    aria-checked."""
    buttons = _visible_text_content(html_path)
    tabs = [b for b in buttons if b["group"] == "tablist"]
    radios = [b for b in buttons if b["group"] == "radiogroup"]
    assert len(tabs) >= 12, (
        "expected the toolbar, Browse, channel and settings tablists"
    )
    for b in tabs:
        assert b["role"] == "tab", f"button in a tablist without role=tab: {b}"
        assert b["aria-selected"] in ("true", "false"), (
            f"tab without aria-selected: {b}"
        )
    for b in radios:
        assert b["role"] == "radio", f"button in a radiogroup without role=radio: {b}"
        assert b["aria-checked"] in ("true", "false"), (
            f"radio without aria-checked: {b}"
        )


# Controls the redesign added that carry no visible text, or text that does
# not say what they do. Each needs an accessible name of its own.
NAMED_CONTROLS = {
    "account-chip": "Accounts",
    "player-more-btn": None,
    "chat-more-btn": None,
    "quality-menu-btn": None,
    "sort-menu-btn": None,
    "sidebar-collapse-btn": None,
    "toolbar-refresh-btn": None,
}


@pytest.mark.parametrize("button_id,expected", NAMED_CONTROLS.items())
def test_redesign_controls_have_accessible_name(
    html_path: Path, button_id: str, expected: str | None
) -> None:
    by_id = {b["id"]: b for b in _visible_text_content(html_path) if b["id"]}
    assert button_id in by_id, f"#{button_id} is gone from index.html"
    btn = by_id[button_id]
    name = btn["aria-label"] or btn["title"]
    assert name, f"#{button_id} has no aria-label or title"
    if expected:
        assert name == expected


def test_search_field_button_is_named_by_its_text(html_path: Path) -> None:
    """The toolbar search looks like a field but is a button: its label text
    is the name, and the shortcut is announced via aria-keyshortcuts."""
    by_id = {b["id"]: b for b in _visible_text_content(html_path) if b["id"]}
    btn = by_id["toolbar-search-btn"]
    assert "Search channels" in (btn["text"] or "")
    text = html_path.read_text(encoding="utf-8")
    assert 'id="toolbar-search-btn"' in text and 'aria-keyshortcuts="Meta+K"' in text


def test_main_landmark_has_skip_link(html_path: Path) -> None:
    """The skip-to-content link is present and points to #content."""
    text = html_path.read_text(encoding="utf-8")
    assert '<a href="#content" class="skip-link">' in text
