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

    module.Event = Event
    module.Menu = Menu
    sys.modules["tkinter"] = module


def _install_customtkinter_stub() -> None:
    if "customtkinter" in sys.modules:
        return

    module = types.ModuleType("customtkinter")

    class _Widget:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.configured: dict[str, Any] = {}

        def configure(self, **kwargs: Any) -> None:
            self.configured.update(kwargs)

        def bind(self, *args: Any, **kwargs: Any) -> None:
            pass

        def grid(self, *args: Any, **kwargs: Any) -> None:
            pass

        def pack(self, *args: Any, **kwargs: Any) -> None:
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

        def grid_propagate(self, *args: Any, **kwargs: Any) -> None:
            pass

        def winfo_children(self) -> list[Any]:
            return []

    class CTkFrame(_Widget):
        pass

    class CTkScrollableFrame(_Widget):
        pass

    class CTkLabel(_Widget):
        pass

    class CTkButton(_Widget):
        pass

    class CTkEntry(_Widget):
        pass

    class CTkImage:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    module.CTkFrame = CTkFrame
    module.CTkScrollableFrame = CTkScrollableFrame
    module.CTkLabel = CTkLabel
    module.CTkButton = CTkButton
    module.CTkEntry = CTkEntry
    module.CTkImage = CTkImage
    sys.modules["customtkinter"] = module


_install_tkinter_stub()
_install_customtkinter_stub()

from ui.sidebar import ChannelItem, Sidebar


class _FakeItem:
    def __init__(self) -> None:
        self.selected_calls: list[bool] = []
        self.avatar_updates = 0

    def set_selected(self, selected: bool) -> None:
        self.selected_calls.append(selected)

    def update_avatar(self, image: Any) -> None:
        self.avatar_updates += 1


class _FakeSidebar:
    def __init__(self) -> None:
        self._current_channels = ["alpha", "beta"]
        self._current_live_set = {"alpha"}
        self._selected_channel = "beta"
        self._channel_items = [_FakeItem(), _FakeItem()]
        self._items_by_channel = {
            "alpha": self._channel_items[0],
            "beta": self._channel_items[1],
        }


class _FakeChannelItem:
    def __init__(self) -> None:
        self._avatar = None
        self._on_click = None
        self._channel = "alpha"
        self._name_label = types.SimpleNamespace(grid=lambda *args, **kwargs: None)

    def grid_columnconfigure(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _on_enter(self, *args: Any, **kwargs: Any) -> None:
        pass

    def _on_leave(self, *args: Any, **kwargs: Any) -> None:
        pass


def test_update_channels_refreshes_selected_state_without_full_rebuild() -> None:
    sidebar = _FakeSidebar()

    Sidebar.update_channels(sidebar, ["alpha", "beta"], {"alpha"}, {})

    assert sidebar._items_by_channel["alpha"].selected_calls == [False]
    assert sidebar._items_by_channel["beta"].selected_calls == [True]


def test_channel_item_update_avatar_creates_avatar_when_missing() -> None:
    item = _FakeChannelItem()

    ChannelItem.update_avatar(item, object())

    assert item._avatar is not None
