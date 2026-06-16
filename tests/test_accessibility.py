"""Static accessibility smoke tests for the TwitchX UI shell.

These tests parse ui/index.html and verify basic a11y invariants that can be
checked without a running browser. Dynamic JS-generated controls are covered by
manual QA and runtime audits.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest


class ButtonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str | None]] = []
        self._current: dict[str, str | None] | None = None
        self._text_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "button":
            attr_dict = {k: v for k, v in attrs}
            self._current = {
                "tag": tag,
                "aria-label": attr_dict.get("aria-label"),
                "title": attr_dict.get("title"),
                "aria-hidden": attr_dict.get("aria-hidden"),
            }
            self._text_stack = []

    def handle_endtag(self, tag: str) -> None:
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
    """Buttons inside role=tablist must have role=tab and aria-selected."""
    text = html_path.read_text(encoding="utf-8")
    # Simple structural check: every platform-tab/platform-chip/browse-platform-tab
    # has the required ARIA attributes.
    for cls in ["platform-tab", "platform-chip", "browse-platform-tab"]:
        for line in text.splitlines():
            if f'class="{cls}' in line or f'class="btn {cls}' in line:
                assert 'role="tab"' in line, f"{cls} missing role=tab: {line.strip()}"
                assert "aria-selected" in line, (
                    f"{cls} missing aria-selected: {line.strip()}"
                )


def test_main_landmark_has_skip_link(html_path: Path) -> None:
    """The skip-to-content link is present and points to #content."""
    text = html_path.read_text(encoding="utf-8")
    assert '<a href="#content" class="skip-link">' in text
