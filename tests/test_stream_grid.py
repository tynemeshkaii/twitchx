from __future__ import annotations

import sys
import types
from typing import Any


def _install_tkinter_stub() -> None:
    if "tkinter" in sys.modules:
        return

    module = types.ModuleType("tkinter")

    class Event:
        x_root = 0
        y_root = 0

    class Menu:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def configure(self, *args: Any, **kwargs: Any) -> None:
            pass

        def add_command(self, *args: Any, **kwargs: Any) -> None:
            pass

        def add_separator(self) -> None:
            pass

        def post(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Toplevel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def overrideredirect(self, *args: Any, **kwargs: Any) -> None:
            pass

        def geometry(self, *args: Any, **kwargs: Any) -> None:
            pass

        def configure(self, *args: Any, **kwargs: Any) -> None:
            pass

        def destroy(self) -> None:
            pass

    class Label:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def pack(self, *args: Any, **kwargs: Any) -> None:
            pass

    module.Event = Event
    module.Menu = Menu
    module.Toplevel = Toplevel
    module.Label = Label
    sys.modules["tkinter"] = module


def _install_customtkinter_stub() -> None:
    if "customtkinter" in sys.modules:
        return

    module = types.ModuleType("customtkinter")

    class _Widget:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def configure(self, *args: Any, **kwargs: Any) -> None:
            pass

        def bind(self, *args: Any, **kwargs: Any) -> None:
            pass

        def grid(self, *args: Any, **kwargs: Any) -> None:
            pass

        def pack(self, *args: Any, **kwargs: Any) -> None:
            pass

        def place(self, *args: Any, **kwargs: Any) -> None:
            pass

        def place_forget(self) -> None:
            pass

        def destroy(self) -> None:
            pass

        def after(self, *args: Any, **kwargs: Any) -> str:
            return "after-job"

        def after_cancel(self, *args: Any, **kwargs: Any) -> None:
            pass

        def grid_columnconfigure(self, *args: Any, **kwargs: Any) -> None:
            pass

        def grid_rowconfigure(self, *args: Any, **kwargs: Any) -> None:
            pass

    class CTkFrame(_Widget):
        pass

    class CTkScrollableFrame(_Widget):
        pass

    class CTkLabel(_Widget):
        pass

    class CTkButton(_Widget):
        pass

    class CTkImage:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    module.CTkFrame = CTkFrame
    module.CTkScrollableFrame = CTkScrollableFrame
    module.CTkLabel = CTkLabel
    module.CTkButton = CTkButton
    module.CTkImage = CTkImage
    sys.modules["customtkinter"] = module


_install_tkinter_stub()
_install_customtkinter_stub()

from ui.stream_grid import SORT_MOST_VIEWERS, StreamGrid  # noqa: E402


def _stream(login: str, viewers: int) -> dict[str, Any]:
    return {
        "channel_ref": login,
        "user_login": login,
        "user_name": login.capitalize(),
        "viewer_count": viewers,
        "title": f"{login} title",
        "game_name": "Just Chatting",
        "game_id": "509658",
        "started_at": "2026-03-16T10:00:00Z",
    }


class _FakeCard:
    def update_viewers(self, count: int) -> None:
        pass

    def update_game(self, name: str) -> None:
        pass

    def update_title(self, title: str) -> None:
        pass

    def update_thumbnail(self, image: Any) -> None:
        pass

    def set_selected(self, selected: bool) -> None:
        pass


class _FakeStreamGrid:
    def __init__(self) -> None:
        self._sort_key = SORT_MOST_VIEWERS
        self._filter_text = ""
        self._last_streams: list[dict[str, Any]] = []
        self._last_thumbnails: dict[str, Any] = {}
        self._last_games: dict[str, str] = {}
        self._cards_by_channel: dict[str, _FakeCard] = {}
        self._selected_channel: str | None = None
        self._empty_label = None
        self._empty_subtitle = None
        self._loading_label = None
        self._onboarding_frame = None
        self._no_results_label = None
        self.rendered_channels: list[str] = []

    def _apply_sort_filter(self, streams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return StreamGrid._apply_sort_filter(self, streams)

    def _show_empty(self) -> None:
        self.rendered_channels = []
        self._cards_by_channel = {}

    def _clear(self) -> None:
        self.rendered_channels = []
        self._cards_by_channel = {}

    def _full_rebuild(
        self,
        streams: list[dict[str, Any]],
        thumbnails: dict[str, Any],
        games: dict[str, str],
    ) -> None:
        self.rendered_channels = [stream["channel_ref"].lower() for stream in streams]
        self._cards_by_channel = {
            stream["channel_ref"].lower(): _FakeCard() for stream in streams
        }


def test_update_streams_rebuilds_when_sorted_order_changes() -> None:
    grid = _FakeStreamGrid()

    StreamGrid.update_streams(
        grid,
        [_stream("alpha", 200), _stream("beta", 100)],
        {},
        {},
    )
    assert grid.rendered_channels == ["alpha", "beta"]

    StreamGrid.update_streams(
        grid,
        [_stream("alpha", 100), _stream("beta", 300)],
        {},
        {},
    )

    assert grid.rendered_channels == ["beta", "alpha"]


def test_update_streams_keeps_same_login_from_different_platforms_distinct() -> None:
    grid = _FakeStreamGrid()

    StreamGrid.update_streams(
        grid,
        [
            {**_stream("alpha", 200), "channel_ref": "alpha"},
            {**_stream("alpha", 150), "channel_ref": "kick:alpha", "user_name": "Kick Alpha"},
        ],
        {},
        {},
    )

    assert grid.rendered_channels == ["alpha", "kick:alpha"]
