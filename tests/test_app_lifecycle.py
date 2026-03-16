from __future__ import annotations

import importlib
import sys
import threading
import types
from typing import Any

import pytest


def _install_tkinter_stub() -> None:
    module = sys.modules.get("tkinter") or types.ModuleType("tkinter")

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

    module.Event = getattr(module, "Event", Event)
    module.Menu = getattr(module, "Menu", Menu)
    module.Toplevel = getattr(module, "Toplevel", Toplevel)
    module.Label = getattr(module, "Label", Label)
    sys.modules["tkinter"] = module


def _install_customtkinter_stub() -> None:
    module = sys.modules.get("customtkinter") or types.ModuleType("customtkinter")

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

        def grid_propagate(self, *args: Any, **kwargs: Any) -> None:
            pass

        def winfo_children(self) -> list[Any]:
            return []

    class CTk(_Widget):
        pass

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

    class CTkOptionMenu(_Widget):
        pass

    class CTkToplevel(_Widget):
        pass

    class CTkImage:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class StringVar:
        def __init__(self, value: str = "") -> None:
            self._value = value

        def get(self) -> str:
            return self._value

        def set(self, value: str) -> None:
            self._value = value

    module.CTk = getattr(module, "CTk", CTk)
    module.CTkFrame = getattr(module, "CTkFrame", CTkFrame)
    module.CTkScrollableFrame = getattr(module, "CTkScrollableFrame", CTkScrollableFrame)
    module.CTkLabel = getattr(module, "CTkLabel", CTkLabel)
    module.CTkButton = getattr(module, "CTkButton", CTkButton)
    module.CTkEntry = getattr(module, "CTkEntry", CTkEntry)
    module.CTkOptionMenu = getattr(module, "CTkOptionMenu", CTkOptionMenu)
    module.CTkToplevel = getattr(module, "CTkToplevel", CTkToplevel)
    module.CTkImage = getattr(module, "CTkImage", CTkImage)
    module.StringVar = getattr(module, "StringVar", StringVar)
    module.set_appearance_mode = getattr(
        module,
        "set_appearance_mode",
        lambda *args, **kwargs: None,
    )
    module.set_default_color_theme = getattr(
        module,
        "set_default_color_theme",
        lambda *args, **kwargs: None,
    )
    sys.modules["customtkinter"] = module


def _install_httpx_stub() -> None:
    module = sys.modules.get("httpx") or types.ModuleType("httpx")

    class AsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

    class ConnectError(Exception):
        pass

    class HTTPStatusError(Exception):
        def __init__(self, response: Any) -> None:
            self.response = response

    module.AsyncClient = getattr(module, "AsyncClient", AsyncClient)
    module.ConnectError = getattr(module, "ConnectError", ConnectError)
    module.HTTPStatusError = getattr(module, "HTTPStatusError", HTTPStatusError)
    module.get = getattr(module, "get", lambda *args, **kwargs: None)
    module.post = getattr(module, "post", lambda *args, **kwargs: None)
    sys.modules["httpx"] = module


def _install_pil_stub() -> None:
    pil_module = sys.modules.get("PIL") or types.ModuleType("PIL")
    image_module = sys.modules.get("PIL.Image") or types.ModuleType("PIL.Image")

    class _Resampling:
        LANCZOS = "LANCZOS"

    image_module.Resampling = getattr(image_module, "Resampling", _Resampling)
    image_module.open = getattr(image_module, "open", lambda *args, **kwargs: None)
    pil_module.Image = image_module

    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module


_install_tkinter_stub()
_install_customtkinter_stub()
_install_httpx_stub()
_install_pil_stub()

app = importlib.import_module("app")


class _ImmediateThread:
    def __init__(
        self,
        target: Any,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        daemon: bool | None = None,
    ) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)


class _FakeSidebar:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] | None = None
        self.profile_updates: list[Any] = []

    def show_search_results(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def update_user_profile(
        self,
        user: dict[str, Any] | None,
        avatar_image: Any | None = None,
    ) -> None:
        self.profile_updates.append((user, avatar_image))


class _FakeTwitch:
    def __init__(self) -> None:
        self.reset_calls = 0

    async def search_channels(self, query: str) -> list[dict[str, Any]]:
        return [{"login": query}]

    async def rebind_client(self) -> None:
        self.reset_calls += 1

    def reset_client(self) -> None:
        self.reset_calls += 1


class _FakePlayerBar:
    def __init__(self) -> None:
        self.status_calls: list[tuple[str, Any]] = []

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        self.status_calls.append((args[0], args[1] if len(args) > 1 else None))


class _FakeCache:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, Any]] = []

    def get(self, key: str) -> None:
        return None

    def put(self, key: str, value: Any) -> None:
        self.put_calls.append((key, value))


class _FakeStreamGridUpdates:
    def __init__(self) -> None:
        self.thumbnail_updates: list[tuple[str, Any]] = []

    def update_thumbnail(self, login: str, image: Any) -> None:
        self.thumbnail_updates.append((login, image))


class _FakeFetchApp:
    def __init__(self) -> None:
        self._shutdown = threading.Event()
        self._twitch = _FakeTwitch()
        self._player_bar = _FakePlayerBar()
        self.fetch_result: tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]] | None = None
        self.clear_calls = 0
        self._fetching = True

    async def _async_fetch(self, favorites: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return ([{"user_login": favorites[0]}], [{"login": favorites[0]}])

    def _on_data_fetched(
        self,
        favorites: list[str],
        streams: list[dict[str, Any]],
        users: list[dict[str, Any]],
    ) -> None:
        self.fetch_result = (favorites, streams, users)

    def _clear_fetching(self) -> None:
        self.clear_calls += 1
        self._fetching = False

    def after(self, delay: int, callback: Any) -> None:
        callback()


class _FakeDialogButton:
    def __init__(self) -> None:
        self.configure_calls: list[dict[str, Any]] = []

    def configure(self, **kwargs: Any) -> None:
        self.configure_calls.append(kwargs)


class _FakeDialogEntry:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


class _FakeTimer:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


def test_search_channels_resets_client_after_temp_loop(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(app.threading, "Thread", _ImmediateThread)

    fake_app = types.SimpleNamespace(
        _config={"client_id": "id", "client_secret": "secret"},
        _twitch=_FakeTwitch(),
        _shutdown=threading.Event(),
        _sidebar=_FakeSidebar(),
        after=lambda delay, callback: callback(),
    )

    app.TwitchXApp._search_channels(fake_app, "alpha")

    assert fake_app._sidebar.results == [{"login": "alpha"}]
    assert fake_app._twitch.reset_calls == 1


def test_run_twitch_temp_loop_returns_result_and_resets_client() -> None:
    fake_app = types.SimpleNamespace(_twitch=_FakeTwitch())

    async def action() -> str:
        return "ok"

    result = app.TwitchXApp._run_twitch_temp_loop(fake_app, action)

    assert result == "ok"
    assert fake_app._twitch.reset_calls == 1


def test_run_twitch_temp_loop_resets_client_on_exception() -> None:
    fake_app = types.SimpleNamespace(_twitch=_FakeTwitch())

    async def action() -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        app.TwitchXApp._run_twitch_temp_loop(fake_app, action)

    assert fake_app._twitch.reset_calls == 1


def test_run_twitch_temp_loop_rebinds_client_before_loop_close() -> None:
    state: dict[str, bool] = {}

    class FakeTwitch:
        async def rebind_client(self) -> None:
            loop = __import__("asyncio").get_running_loop()
            state["running"] = loop.is_running()
            state["closed"] = loop.is_closed()

    fake_app = types.SimpleNamespace(_twitch=FakeTwitch())

    async def action() -> str:
        return "ok"

    result = app.TwitchXApp._run_twitch_temp_loop(fake_app, action)

    assert result == "ok"
    assert state == {"running": True, "closed": False}


def test_fetch_data_resets_client_after_temp_loop() -> None:
    fake_app = _FakeFetchApp()

    app.TwitchXApp._fetch_data(fake_app, ["alpha"])

    assert fake_app.fetch_result == (
        ["alpha"],
        [{"user_login": "alpha"}],
        [{"login": "alpha"}],
    )
    assert fake_app._twitch.reset_calls == 1
    assert fake_app.clear_calls == 1


def test_fetch_image_bytes_returns_none_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        content = b"valid-image-bytes"

        def raise_for_status(self) -> None:
            raise app.httpx.HTTPStatusError(self)

    monkeypatch.setattr(app.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = app.TwitchXApp._fetch_image_bytes(types.SimpleNamespace(), "https://img")

    assert result is None


def test_load_avatars_skips_failed_http_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: list[tuple[str, bytes]] = []
    updated = {"count": 0}

    fake_app = types.SimpleNamespace(
        _shutdown=threading.Event(),
        _avatar_cache=_FakeCache(),
        _fetch_image_bytes=lambda url: None,
        after=lambda delay, callback: callback(),
        _update_sidebar_avatars=lambda: updated.__setitem__("count", updated["count"] + 1),
    )

    monkeypatch.setattr(app, "get_cached_avatar", lambda login: None)
    monkeypatch.setattr(app, "save_avatar", lambda login, data: saved.append((login, data)))

    app.TwitchXApp._load_avatars(fake_app, {"alpha": "https://avatar"})

    assert fake_app._avatar_cache.put_calls == []
    assert saved == []
    assert updated["count"] == 1


def test_load_thumbnails_skips_failed_http_response() -> None:
    fake_app = types.SimpleNamespace(
        _shutdown=threading.Event(),
        _thumb_cache=_FakeCache(),
        _stream_grid=_FakeStreamGridUpdates(),
        _fetch_image_bytes=lambda url: None,
        after=lambda delay, callback: callback(),
    )

    app.TwitchXApp._load_thumbnails(fake_app, {"alpha": "https://thumb"})

    assert fake_app._thumb_cache.put_calls == []
    assert fake_app._stream_grid.thumbnail_updates == []


def test_format_error_message_uses_fallback_for_blank_exception() -> None:
    assert (
        app._format_error_message(RuntimeError("   "), "Login failed", limit=80)
        == "Login failed"
    )


def test_queue_error_status_prefixes_and_truncates_message() -> None:
    fake_app = types.SimpleNamespace(
        _shutdown=threading.Event(),
        _player_bar=_FakePlayerBar(),
        after=lambda delay, callback: callback(),
    )

    app.TwitchXApp._queue_error_status(
        fake_app,
        "Login error",
        RuntimeError("x" * 120),
        "Login failed",
    )

    assert fake_app._player_bar.status_calls == [
        (f"Login error: {'x' * 80}", app.ERROR_RED)
    ]


def test_schedule_refresh_noops_after_shutdown() -> None:
    refresh_calls: list[str] = []
    after_calls: list[tuple[int, Any]] = []
    stale_calls: list[bool] = []
    shutdown = threading.Event()
    shutdown.set()

    fake_app = types.SimpleNamespace(
        _shutdown=shutdown,
        _refresh_data=lambda: refresh_calls.append("refresh"),
        _config={"refresh_interval": 60},
        _last_successful_fetch=123.0,
        _player_bar=types.SimpleNamespace(set_stale=lambda stale: stale_calls.append(stale)),
        after=lambda delay, callback: after_calls.append((delay, callback)),
    )

    app.TwitchXApp._schedule_refresh(fake_app)

    assert refresh_calls == []
    assert stale_calls == []
    assert after_calls == []


def test_manual_refresh_noops_after_shutdown() -> None:
    refresh_calls: list[str] = []
    after_cancel_calls: list[str] = []
    after_calls: list[tuple[int, Any]] = []
    shutdown = threading.Event()
    shutdown.set()

    fake_app = types.SimpleNamespace(
        _shutdown=shutdown,
        _refresh_job="after-job",
        _refresh_data=lambda: refresh_calls.append("refresh"),
        _config={"refresh_interval": 60},
        after_cancel=lambda job: after_cancel_calls.append(job),
        after=lambda delay, callback: after_calls.append((delay, callback)),
    )

    app.TwitchXApp._manual_refresh(fake_app)

    assert after_cancel_calls == []
    assert refresh_calls == []
    assert after_calls == []


def test_destroy_cancels_launch_timer_before_closing_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    super_destroy_calls: list[str] = []
    monkeypatch.setattr(app.ctk.CTk, "destroy", lambda self: super_destroy_calls.append("destroyed"))

    fake_timer = _FakeTimer()
    cancelled_refresh_jobs: list[str] = []
    close_calls: list[str] = []

    async def close_client() -> None:
        close_calls.append("closed")

    fake_app = app.TwitchXApp.__new__(app.TwitchXApp)
    fake_app._shutdown = threading.Event()
    fake_app._refresh_job = "after-job"
    fake_app._launch_timer = fake_timer
    fake_app._twitch = types.SimpleNamespace(close=close_client)
    fake_app.after_cancel = lambda job: cancelled_refresh_jobs.append(job)

    app.TwitchXApp.destroy(fake_app)

    assert fake_timer.cancel_calls == 1
    assert fake_app._launch_timer is None
    assert cancelled_refresh_jobs == ["after-job"]
    assert close_calls == ["closed"]
    assert super_destroy_calls == ["destroyed"]


def test_destroy_suppresses_after_cancel_and_close_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    super_destroy_calls: list[str] = []
    monkeypatch.setattr(app.ctk.CTk, "destroy", lambda self: super_destroy_calls.append("destroyed"))

    fake_timer = _FakeTimer()
    after_cancel_calls: list[str] = []
    close_calls: list[str] = []

    async def close_client() -> None:
        close_calls.append("closed")
        raise RuntimeError("close failed")

    fake_app = app.TwitchXApp.__new__(app.TwitchXApp)
    fake_app._shutdown = threading.Event()
    fake_app._refresh_job = "after-job"
    fake_app._launch_timer = fake_timer
    fake_app._twitch = types.SimpleNamespace(close=close_client)

    def after_cancel(job: str) -> None:
        after_cancel_calls.append(job)
        raise RuntimeError("after_cancel failed")

    fake_app.after_cancel = after_cancel

    app.TwitchXApp.destroy(fake_app)

    assert fake_timer.cancel_calls == 1
    assert after_cancel_calls == ["after-job"]
    assert close_calls == ["closed"]
    assert super_destroy_calls == ["destroyed"]


def test_destroy_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    super_destroy_calls: list[str] = []
    monkeypatch.setattr(app.ctk.CTk, "destroy", lambda self: super_destroy_calls.append("destroyed"))

    fake_timer = _FakeTimer()
    after_cancel_calls: list[str] = []
    close_calls: list[str] = []

    async def close_client() -> None:
        close_calls.append("closed")

    fake_app = app.TwitchXApp.__new__(app.TwitchXApp)
    fake_app._shutdown = threading.Event()
    fake_app._refresh_job = "after-job"
    fake_app._launch_timer = fake_timer
    fake_app._twitch = types.SimpleNamespace(close=close_client)
    fake_app.after_cancel = lambda job: after_cancel_calls.append(job)

    app.TwitchXApp.destroy(fake_app)
    app.TwitchXApp.destroy(fake_app)

    assert fake_timer.cancel_calls == 1
    assert after_cancel_calls == ["after-job"]
    assert close_calls == ["closed"]
    assert super_destroy_calls == ["destroyed"]


def test_manual_refresh_suppresses_after_cancel_error() -> None:
    refresh_calls: list[str] = []
    after_calls: list[tuple[int, Any]] = []
    after_cancel_calls: list[str] = []

    fake_app = types.SimpleNamespace(
        _shutdown=threading.Event(),
        _refresh_job="after-job",
        _refresh_data=lambda: refresh_calls.append("refresh"),
        _config={"refresh_interval": 60},
        after=lambda delay, callback: after_calls.append((delay, callback)) or "next-job",
        after_cancel=lambda job: (after_cancel_calls.append(job), (_ for _ in ()).throw(RuntimeError("after_cancel failed")))[1],
    )

    app.TwitchXApp._manual_refresh(fake_app)

    assert after_cancel_calls == ["after-job"]
    assert refresh_calls == ["refresh"]
    assert after_calls and after_calls[0][0] == 60000
    assert fake_app._refresh_job == "next-job"


def test_schedule_refresh_suppresses_after_error() -> None:
    refresh_calls: list[str] = []
    stale_calls: list[bool] = []

    fake_app = types.SimpleNamespace(
        _shutdown=threading.Event(),
        _refresh_data=lambda: refresh_calls.append("refresh"),
        _config={"refresh_interval": 60},
        _last_successful_fetch=0.0,
        _player_bar=types.SimpleNamespace(set_stale=lambda stale: stale_calls.append(stale)),
        _refresh_job="existing-job",
        after=lambda delay, callback: (_ for _ in ()).throw(RuntimeError("after failed")),
    )

    app.TwitchXApp._schedule_refresh(fake_app)

    assert refresh_calls == ["refresh"]
    assert stale_calls == []
    assert fake_app._refresh_job is None


def test_schedule_followed_sync_noops_without_logged_in_user() -> None:
    after_calls: list[tuple[int, Any]] = []

    fake_app = types.SimpleNamespace(
        _shutdown=threading.Event(),
        _current_user=None,
        _config={},
        after=lambda delay, callback: after_calls.append((delay, callback)),
    )

    app.TwitchXApp._schedule_followed_sync(fake_app)

    assert after_calls == []


def test_logout_cancels_followed_sync_job() -> None:
    after_cancel_calls: list[str] = []
    status_calls: list[tuple[str, Any]] = []
    sidebar = _FakeSidebar()

    fake_app = types.SimpleNamespace(
        _config={
            "user_id": "user-1",
            "user_login": "alpha",
            "user_display_name": "Alpha",
            "refresh_token": "refresh",
            "access_token": "token",
            "token_expires_at": 1,
            "token_type": "user",
        },
        _current_user={"id": "user-1"},
        _sidebar=sidebar,
        _player_bar=types.SimpleNamespace(
            set_status=lambda text, color: status_calls.append((text, color))
        ),
        _followed_sync_job="followed-job",
        after_cancel=lambda job: after_cancel_calls.append(job),
    )

    app.TwitchXApp._on_logout(fake_app)

    assert after_cancel_calls == ["followed-job"]
    assert fake_app._followed_sync_job is None
    assert fake_app._current_user is None
    assert sidebar.profile_updates == [(None, None)]
    assert status_calls == [("Logged out", app.TEXT_MUTED)]


def test_merge_follows_skips_refresh_when_nothing_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, Any] = {}
    refresh_calls: list[str] = []
    status_calls: list[tuple[str, Any]] = []

    monkeypatch.setattr(app, "save_config", lambda config: saved.update(config))

    fake_app = types.SimpleNamespace(
        _config={"favorites": ["alpha"]},
        _player_bar=types.SimpleNamespace(
            set_status=lambda text, color: status_calls.append((text, color))
        ),
        _refresh_data=lambda: refresh_calls.append("refresh"),
    )

    app.TwitchXApp._merge_follows(fake_app, ["alpha"], show_status=False)

    assert saved["favorites"] == ["alpha"]
    assert refresh_calls == []
    assert status_calls == []


def test_fetch_data_clears_fetching_when_after_raises() -> None:
    fake_app = _FakeFetchApp()
    fake_app.after = lambda delay, callback: (_ for _ in ()).throw(RuntimeError("widget destroyed"))

    app.TwitchXApp._fetch_data(fake_app, ["alpha"])

    assert fake_app.clear_calls == 1
    assert fake_app._fetching is False


def test_settings_test_connection_ignores_after_errors_when_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.threading, "Thread", _ImmediateThread)

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(app.httpx, "post", lambda *args, **kwargs: FakeResponse())

    feedback_calls: list[tuple[str, Any]] = []
    button = _FakeDialogButton()
    fake_dialog = types.SimpleNamespace(
        _validate=lambda: True,
        _set_feedback=lambda text, color=None: feedback_calls.append((text, color)),
        _test_btn=button,
        _entries={
            "client_id": _FakeDialogEntry("client"),
            "client_secret": _FakeDialogEntry("secret"),
        },
        after=lambda delay, callback: (_ for _ in ()).throw(RuntimeError("window destroyed")),
    )

    app.SettingsDialog._test_connection(fake_dialog)

    assert feedback_calls == [("Testing...", app.TEXT_MUTED)]
    assert button.configure_calls == [{"state": "disabled"}]


def test_import_follows_reports_progress_while_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.threading, "Thread", _ImmediateThread)

    merged: list[list[str]] = []

    class FakeTwitch:
        async def get_followed_channels(
            self,
            user_id: str,
            on_progress: Any | None = None,
        ) -> list[str]:
            assert user_id == "user-1"
            if on_progress:
                on_progress(100)
                on_progress(135)
            return ["alpha", "beta"]

        async def rebind_client(self) -> None:
            pass

    fake_app = types.SimpleNamespace(
        _current_user={"id": "user-1"},
        _config={},
        _player_bar=_FakePlayerBar(),
        _shutdown=threading.Event(),
        _twitch=FakeTwitch(),
        _merge_follows=lambda follows, show_status=True: merged.append(follows),
        _followed_sync_job=None,
        _importing_follows=False,
        after=lambda delay, callback: callback() if delay == 0 else "followed-job",
    )

    app.TwitchXApp._on_import_follows(fake_app)

    assert merged == [["alpha", "beta"]]
    assert fake_app._player_bar.status_calls == [
        ("Importing followed channels...", app.WARN_YELLOW),
        ("Importing followed channels... (100 loaded)", app.WARN_YELLOW),
        ("Importing followed channels... (135 loaded)", app.WARN_YELLOW),
    ]


def test_import_follows_reschedules_periodic_sync_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.threading, "Thread", _ImmediateThread)

    merged: list[tuple[list[str], bool]] = []
    after_calls: list[int] = []

    class FakeTwitch:
        async def get_followed_channels(
            self,
            user_id: str,
            on_progress: Any | None = None,
        ) -> list[str]:
            return ["alpha"]

        async def rebind_client(self) -> None:
            pass

    fake_app = types.SimpleNamespace(
        _current_user={"id": "user-1"},
        _config={},
        _player_bar=_FakePlayerBar(),
        _shutdown=threading.Event(),
        _twitch=FakeTwitch(),
        _merge_follows=lambda follows, show_status=True: merged.append((follows, show_status)),
        _followed_sync_job=None,
        _importing_follows=False,
        after=lambda delay, callback: (
            callback() if delay == 0 else None,
            after_calls.append(delay),
            "followed-job",
        )[-1],
    )

    app.TwitchXApp._on_import_follows(fake_app, show_status=False)

    assert merged == [(["alpha"], False)]
    assert after_calls.count(app.FOLLOWED_SYNC_INTERVAL_MS) == 1
    assert fake_app._followed_sync_job == "followed-job"
    assert fake_app._importing_follows is False


def test_login_complete_auto_imports_follows_without_empty_refresh() -> None:
    sidebar = _FakeSidebar()
    status_calls: list[tuple[str, Any]] = []
    import_calls: list[str] = []
    refresh_calls: list[str] = []

    fake_app = types.SimpleNamespace(
        _current_user=None,
        _sidebar=sidebar,
        _player_bar=types.SimpleNamespace(
            set_status=lambda text, color: status_calls.append((text, color))
        ),
        _config={"favorites": []},
        _sanitize_username=lambda value: value,
        _on_import_follows=lambda: import_calls.append("import"),
        _refresh_data=lambda: refresh_calls.append("refresh"),
    )

    user = {"id": "1", "login": "alpha", "display_name": "Alpha"}

    app.TwitchXApp._on_login_complete(fake_app, user)

    assert fake_app._current_user == user
    assert sidebar.profile_updates == [(user, None)]
    assert status_calls == [("Logged in as Alpha", app.LIVE_GREEN)]
    assert import_calls == ["import"]
    assert refresh_calls == []


def test_login_complete_refreshes_existing_favorites_before_auto_import() -> None:
    sidebar = _FakeSidebar()
    import_calls: list[str] = []
    refresh_calls: list[str] = []

    fake_app = types.SimpleNamespace(
        _current_user=None,
        _sidebar=sidebar,
        _player_bar=types.SimpleNamespace(set_status=lambda text, color: None),
        _config={"favorites": ["existing"]},
        _sanitize_username=lambda value: value,
        _on_import_follows=lambda: import_calls.append("import"),
        _refresh_data=lambda: refresh_calls.append("refresh"),
    )

    user = {"id": "1", "login": "alpha", "display_name": "Alpha"}

    app.TwitchXApp._on_login_complete(fake_app, user)

    assert refresh_calls == ["refresh"]
    assert import_calls == ["import"]
