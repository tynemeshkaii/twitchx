"""Phase 2 — static guards for the critical UI states.

Covers the three regressions that made whole views unusable:
    P0-2  #empty-state stayed at opacity: 0 (invisible Welcome screen)
    P0-3  opening the multistream add-form hid every slot
    P1-5  the context menu shipped a duplicated action block
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

UI = Path(__file__).parent.parent / "ui"


class ContextMenuParser(HTMLParser):
    """Collect data-action values per context menu id."""

    def __init__(self) -> None:
        super().__init__()
        self.menus: dict[str, list[str]] = {}
        self._menu_id: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v for k, v in attrs}
        if tag != "div":
            return
        if self._menu_id is None:
            el_id = attr.get("id") or ""
            if el_id.endswith("context-menu"):
                self._menu_id = el_id
                self.menus[el_id] = []
                self._depth = 1
            return
        self._depth += 1
        action = attr.get("data-action")
        if action and "ctx-item" in (attr.get("class") or ""):
            self.menus[self._menu_id].append(action)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self._menu_id is None:
            return
        self._depth -= 1
        if self._depth == 0:
            self._menu_id = None


def _parse_menus() -> dict[str, list[str]]:
    parser = ContextMenuParser()
    parser.feed((UI / "index.html").read_text(encoding="utf-8"))
    return parser.menus


def test_context_menu_actions_are_unique() -> None:
    """Duplicated items made disabled actions clickable through the copy."""
    for menu_id, actions in _parse_menus().items():
        assert len(actions) == len(set(actions)), f"{menu_id} has duplicates: {actions}"


def test_context_menu_keeps_all_channel_actions() -> None:
    actions = _parse_menus()["context-menu"]
    assert actions == [
        "watch",
        "multistream",
        "watch-external",
        "favorite",
        "pin",
        "create-group",
        "move-to-group",
        "remove",
    ]


def test_empty_state_is_revealed_by_view_active() -> None:
    """#empty-state lives in #view-stack, so .view-active must clear opacity: 0."""
    css = (UI / "css" / "components" / "empty-state.css").read_text(encoding="utf-8")
    reveal = re.search(
        r"([^}]*)\{[^}]*opacity:\s*1[^}]*\}",
        css[css.index("#empty-state") :],
    )
    assert reveal is not None
    selectors = reveal.group(1)
    assert "#empty-state.view-active" in selectors
    assert "#empty-state.visible" in selectors


def test_render_empty_state_marks_target_visible() -> None:
    render_js = (UI / "js" / "render.js").read_text(encoding="utf-8")
    assert "target.classList.add('empty-state', 'view-active', 'visible')" in render_js
    # …and there is a single symmetric hide path, exported for other modules.
    assert "function hideEmptyState(target)" in render_js
    assert "TwitchX.hideEmptyState = hideEmptyState;" in render_js


def test_empty_state_hidden_only_through_helper() -> None:
    """No module may drop #empty-state by adding .hidden alone — .visible would
    survive and the next reveal would fight the stale class."""
    offenders = []
    for path in sorted((UI / "js").glob("*.js")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if re.search(r"\bempty\w*\.classList\.add\('hidden'\)", line):
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == []


def test_multistream_add_form_slot_stays_visible() -> None:
    """The collapse rule for empty slots must exempt the open add-form."""
    css = (UI / "css" / "components" / "multistream.css").read_text(encoding="utf-8")
    assert (
        "#multistream-grid:not(.ms-grid-empty) "
        ".ms-slot.ms-state-empty:not(.ms-add-form-open)" in css.replace("\n", " ")
    )
    assert not re.search(
        r"#multistream-grid:not\(\.ms-grid-empty\) \.ms-slot\.ms-state-empty\s*\{",
        css,
    )


def test_add_form_close_goes_through_single_helper() -> None:
    multistream_js = (UI / "js" / "multistream.js").read_text(encoding="utf-8")
    init_js = (UI / "js" / "init.js").read_text(encoding="utf-8")
    assert "function closeMultiAddForm(idx, opts)" in multistream_js
    assert "TwitchX.closeMultiAddForm = closeMultiAddForm;" in multistream_js
    # init.js must not hand-roll the teardown any more
    assert "classList.remove('ms-add-form-open')" not in init_js
    assert init_js.count("TwitchX.closeMultiAddForm(") == 4
