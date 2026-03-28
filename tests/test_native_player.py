from __future__ import annotations

import pytest

from ui.native_player import (
    DEFAULT_PLAYER_HEIGHT,
    MIN_PLAYER_HEIGHT,
    STATE_IDLE,
    NativePlayerController,
)


class TestNativePlayerController:
    def test_init_state(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        assert ctrl._current_channel is None
        assert ctrl._attached is False
        assert ctrl._player_visible is False
        assert ctrl._player_height == DEFAULT_PLAYER_HEIGHT

    def test_play_stream_without_attach_raises(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        with pytest.raises(RuntimeError, match="not attached"):
            ctrl.play_stream("https://example.com/stream.m3u8", "xqc", "Test")

    def test_set_player_height_clamps_to_min(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        ctrl.set_player_height(50.0)
        assert ctrl._player_height == MIN_PLAYER_HEIGHT

    def test_set_player_height_accepts_valid(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        ctrl.set_player_height(400.0)
        assert ctrl._player_height == 400.0

    def test_get_player_height_returns_stored(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        ctrl.set_player_height(500.0)
        assert ctrl.get_player_height() == 500.0

    def test_current_channel_initially_none(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        assert ctrl.current_channel is None

    def test_is_playing_false_without_player(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        assert ctrl.is_playing is False

    def test_cleanup_resets_player(self) -> None:
        ctrl = NativePlayerController(on_state_change=lambda s: None)
        ctrl.cleanup()
        assert ctrl._player is None
        assert ctrl._player_view is None

    def test_stop_without_attach_does_not_crash(self) -> None:
        states: list[dict] = []
        ctrl = NativePlayerController(on_state_change=states.append)
        ctrl.stop()
        assert any(s["state"] == STATE_IDLE for s in states)

    def test_notify_state_callback(self) -> None:
        states: list[dict] = []
        ctrl = NativePlayerController(on_state_change=states.append)
        ctrl._notify_state("loading")
        assert len(states) == 1
        assert states[0]["state"] == "loading"
        assert states[0]["channel"] is None  # _current_channel not set
