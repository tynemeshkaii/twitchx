"""Phase 3 — favorite identity and sidebar behaviour guards.

P0-4   flat `favorites` list spawned phantom twitch:<login> duplicates
P1-10  removing the last favorite left dead rows in #channel-list
P2-16  every poll re-expanded the selected channel's section
P2-20  the new-live badge could not be dismissed
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).parent.parent / "ui" / "js"
CSS = Path(__file__).parent.parent / "ui" / "css"


def _read(name: str) -> str:
    return (JS / name).read_text(encoding="utf-8")


def _function_body(source: str, header: str) -> str:
    """Return the brace-balanced body of the function starting at `header`."""
    start = source.index(header)
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unbalanced braces after {header!r}")


def test_legacy_favorites_skip_logins_covered_by_meta() -> None:
    body = _function_body(_read("state.js"), "TwitchX.getFavoriteEntries = function()")
    assert "coveredLogins" in body
    # the guard must run before the twitch:<login> entry is built
    guard = body.index("if (coveredLogins[login]) return;")
    legacy_key = body.index("TwitchX.channelKey(login, 'twitch')", guard - 400)
    assert guard < legacy_key
    # matching is by login, never lower-cased (YouTube ids are case-sensitive)
    assert ".toLowerCase()" not in body


def test_render_sidebar_does_not_expand_sections() -> None:
    body = _function_body(_read("sidebar.js"), "function renderSidebar()")
    code = [line for line in body.splitlines() if not line.lstrip().startswith("//")]
    assert "expandSidebarSectionForLogin(" not in "\n".join(code)


def test_select_channel_still_expands_and_acknowledges() -> None:
    body = _function_body(
        _read("channel.js"), "function selectChannel(login, platform)"
    )
    assert "TwitchX.expandSidebarSectionForLogin(login, key)" in body
    assert "TwitchX.acknowledgeNotifBadge(key)" in body


def test_empty_favorites_clears_channel_list() -> None:
    body = _function_body(_read("sidebar.js"), "function renderSidebar()")
    match = re.search(
        r"if \(TwitchX\.getFavoriteEntries\(\)\.length === 0\) \{(.*?)\n  \}",
        body,
        re.DOTALL,
    )
    assert match is not None
    assert "list.replaceChildren();" in match.group(1)


def test_notif_badge_is_dismissable() -> None:
    sidebar = _read("sidebar.js")
    body = _function_body(sidebar, "function _updateNotifBadges()")
    assert "createElement('button')" in body
    assert "_clearNotifBadges();" in body
    assert "function acknowledgeNotifBadge(key)" in sidebar
    assert "TwitchX.acknowledgeNotifBadge = acknowledgeNotifBadge;" in sidebar
    css = (CSS / "components" / "sidebar.css").read_text(encoding="utf-8")
    badge_rule = css[css.index("#favorites-header .notif-badge {") :]
    badge_rule = badge_rule[: badge_rule.index("}")]
    assert "border: none" in badge_rule
    assert "cursor: pointer" in badge_rule


def test_notif_badges_accumulate_and_seed_baseline() -> None:
    callbacks = _read("callbacks.js")
    body = _function_body(callbacks, "window.onStreamsUpdate = function(data)")
    # first update seeds the baseline instead of flagging every live channel
    assert "if (!TwitchX._prevLiveSet) {\n    TwitchX._notifBadgeLogins = [];" in body
    # later updates keep unacknowledged keys that are still live
    assert "(TwitchX._notifBadgeLogins || []).filter(" in body
    assert "TwitchX._prevLiveSet = newLive;" in body
