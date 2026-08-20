"""Phase 6 — player teardown and small-view regressions.

P1-9   the VOD seek bar survived hide/showPlayerView (interval kept ticking)
P2-12  empty img src rendered WebKit's broken-image glyph
P2-13  the sidebar tooltip stuck after a poll re-render
P2-14  toasts sat on the toolbar and ate clicks for 4s
P2-17  the grid diff never updated the pin badge
P2-18  a live channel showed an empty "Live Now" panel
P2-19  init.js re-implemented tab switching, leaving channelTabs.active stale
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).parent.parent / "ui"


def _read(rel: str) -> str:
    return (UI / rel).read_text(encoding="utf-8")


def _function_body(source: str, header: str) -> str:
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


def test_seek_bar_stops_with_the_player_view() -> None:
    player = _read("js/player.js")
    for header in (
        "function showPlayerView()",
        "function hidePlayerView(skipViewTransition)",
    ):
        body = _function_body(player, header)
        assert "TwitchX.stopVodSeekBar();" in body, header


def test_no_empty_image_src_anywhere() -> None:
    """An empty src is a failed load in WebKit, not a blank image."""
    assert 'src=""' not in _read("index.html")
    for path in sorted((UI / "js").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"\.src\s*=\s*(''|\"\")", source), path.name
        # …and no `|| ''` fallback feeding a src either
        assert not re.search(r"\.src\s*=\s*[^;\n]*\|\|\s*(''|\"\")", source), path.name


def test_pin_badge_is_synced_in_the_diff_branch() -> None:
    render = _read("js/render.js")
    assert "function _syncPinBadge(card, s)" in render
    body = _function_body(render, "function renderGrid()")
    assert "_syncPinBadge(card, s);" in body


def test_sidebar_tooltip_is_hidden_on_every_rerender() -> None:
    sidebar = _read("js/sidebar.js")
    assert "function hideSidebarTooltip()" in sidebar
    for header in ("function renderSidebar()", "function renderRail(groups)"):
        body = _function_body(sidebar, header)
        assert "hideSidebarTooltip();" in body, header


def test_toasts_clear_the_toolbar() -> None:
    css = _read("css/components/toast.css")
    container = css[css.index("#toast-container {") :]
    container = container[: container.index("}")]
    match = re.search(r"top:\s*(\d+)px", container)
    assert match is not None, container
    # toolbar is 46px tall
    assert int(match.group(1)) >= 46


def test_live_channel_renders_a_card() -> None:
    channel = _read("js/channel.js")
    assert "function renderChannelLivePanel(profile)" in channel
    body = _function_body(channel, "function renderChannelLivePanel(profile)")
    assert "channel-live-card" in body
    assert "watchChannelStream" in body
    callbacks = _read("js/callbacks.js")
    assert "TwitchX.renderChannelLivePanel(profile);" in callbacks
    # the old bare hide (which left the panel blank) must be gone
    assert "if (profile.is_live && profile.watch_supported) {" not in callbacks


def test_channel_tabs_go_through_switch_channel_tab() -> None:
    init = _read("js/init.js")
    bind = _function_body(init, "TwitchX._bindChannelEvents = function()")
    assert "TwitchX.switchChannelTab(btn, btn.dataset.tab);" in bind
    assert "channel-tab-panel" not in bind
    channel = _read("js/channel.js")
    assert "TwitchX.state.channelTabs.active = tab;" in _function_body(
        channel, "function switchChannelTab(btn, tab)"
    )
