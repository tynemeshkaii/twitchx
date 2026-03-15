from __future__ import annotations

import asyncio
import contextlib
import io
import re
import subprocess
import threading
import time
import webbrowser
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import customtkinter as ctk
import httpx
from PIL import Image

from core.launcher import launch_stream
from core.storage import (
    get_cached_avatar,
    load_config,
    save_avatar,
    save_config,
)
from core.twitch import TwitchClient
from ui.player_bar import PlayerBar
from ui.sidebar import Sidebar
from ui.stream_grid import SORT_OPTIONS, StreamGrid

ACCENT = "#9146FF"
MAX_CACHE = 50


class ImageCache:
    def __init__(self, max_size: int = MAX_CACHE) -> None:
        self._cache: OrderedDict[str, ctk.CTkImage] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> ctk.CTkImage | None:
        return self._cache.get(key)

    def put(self, key: str, image: ctk.CTkImage) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = image

    def as_dict(self) -> dict[str, ctk.CTkImage]:
        return dict(self._cache)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master: Any, config: dict[str, Any], on_save: Any) -> None:
        super().__init__(master)
        self.title("TwitchX Settings")
        self.geometry("420x440")
        self.resizable(False, False)
        self._config = dict(config)
        self._on_save = on_save

        self.bind("<Escape>", lambda e: self.destroy())
        self.after(100, self._make_modal)

        self.grid_columnconfigure(1, weight=1)
        row = 0

        fields = [
            ("Client ID", "client_id"),
            ("Client Secret", "client_secret"),
            ("Streamlink Path", "streamlink_path"),
            ("IINA Path", "iina_path"),
        ]
        self._entries: dict[str, ctk.CTkEntry] = {}
        for label, key in fields:
            ctk.CTkLabel(self, text=label, anchor="w").grid(
                row=row, column=0, padx=(16, 8), pady=8, sticky="w"
            )
            entry = ctk.CTkEntry(self, width=240)
            entry.insert(0, str(config.get(key, "")))
            if key == "client_secret":
                entry.configure(show="*")
            entry.grid(row=row, column=1, padx=(0, 16), pady=8, sticky="ew")
            self._entries[key] = entry
            row += 1

        # Refresh interval
        ctk.CTkLabel(self, text="Refresh interval", anchor="w").grid(
            row=row, column=0, padx=(16, 8), pady=8, sticky="w"
        )
        self._interval_var = ctk.StringVar(
            value=str(config.get("refresh_interval", 60))
        )
        interval_menu = ctk.CTkOptionMenu(
            self,
            variable=self._interval_var,
            values=["30", "60", "120"],
            width=100,
        )
        interval_menu.grid(row=row, column=1, padx=(0, 16), pady=8, sticky="w")
        row += 1

        # Inline feedback label
        self._feedback_label = ctk.CTkLabel(
            self, text="", font=("", 11), text_color="#888888"
        )
        self._feedback_label.grid(row=row, column=0, columnspan=2, padx=16, pady=(4, 0))
        row += 1

        # Button row
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=2, padx=16, pady=12)

        self._test_btn = ctk.CTkButton(
            btn_frame,
            text="Test Connection",
            width=130,
            fg_color="#2a2a3e",
            hover_color="#3a3a4e",
            command=self._test_connection,
        )
        self._test_btn.pack(side="left", padx=(0, 8))

        save_btn = ctk.CTkButton(
            btn_frame,
            text="Save",
            width=100,
            fg_color=ACCENT,
            hover_color="#7B38D8",
            command=self._save,
        )
        save_btn.pack(side="left")

    def _make_modal(self) -> None:
        self.grab_set()
        self.focus_force()

    def _set_feedback(self, text: str, color: str = "#888888") -> None:
        self._feedback_label.configure(text=text, text_color=color)

    _VALID_CRED = re.compile(r"^[A-Za-z0-9_-]+$")

    def _validate(self) -> bool:
        client_id = self._entries["client_id"].get().strip()
        client_secret = self._entries["client_secret"].get().strip()
        if not client_id or not client_secret:
            self._set_feedback("Client ID and Secret are required", "#FF6B6B")
            return False
        if not self._VALID_CRED.match(client_id):
            self._set_feedback("Client ID contains invalid characters", "#FF6B6B")
            return False
        if not self._VALID_CRED.match(client_secret):
            self._set_feedback("Client Secret contains invalid characters", "#FF6B6B")
            return False
        return True

    def _test_connection(self) -> None:
        if not self._validate():
            return
        self._set_feedback("Testing...", "#888888")
        self._test_btn.configure(state="disabled")
        client_id = self._entries["client_id"].get().strip()
        client_secret = self._entries["client_secret"].get().strip()

        def do_test() -> None:
            try:
                resp = httpx.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "client_credentials",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    self.after(
                        0, lambda: self._set_feedback("\u2713 Connected", "#00E676")
                    )
                else:
                    self.after(
                        0,
                        lambda: self._set_feedback(
                            "\u2717 Invalid credentials", "#FF6B6B"
                        ),
                    )
            except httpx.ConnectError:
                self.after(
                    0,
                    lambda: self._set_feedback(
                        "\u2717 No internet connection", "#FF6B6B"
                    ),
                )
            except Exception as exc:
                msg = str(exc)[:60]
                self.after(
                    0, lambda m=msg: self._set_feedback(f"\u2717 {m}", "#FF6B6B")
                )
            finally:
                self.after(0, lambda: self._test_btn.configure(state="normal"))

        threading.Thread(target=do_test, daemon=True).start()

    def _save(self) -> None:
        if not self._validate():
            return
        for key, entry in self._entries.items():
            self._config[key] = entry.get().strip()
        self._config["refresh_interval"] = int(self._interval_var.get())
        # Clear token if credentials changed
        orig = load_config()
        if (
            self._config["client_id"] != orig["client_id"]
            or self._config["client_secret"] != orig["client_secret"]
        ):
            self._config["access_token"] = ""
            self._config["token_expires_at"] = 0
        self._on_save(self._config)
        self.destroy()


class StreamDeckApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("TwitchX")
        self.geometry("900x600")
        self.minsize(700, 500)

        self._config = load_config()
        self._migrate_favorites()
        self._thumb_cache = ImageCache()
        self._avatar_cache = ImageCache()
        self._live_streams: list[dict[str, Any]] = []
        self._games: dict[str, str] = {}
        self._selected_channel: str | None = None
        self._refresh_job: str | None = None
        self._fetching = False
        self._shutdown = threading.Event()
        # Notification state
        self._prev_live_logins: set[str] = set()
        self._first_fetch_done = False
        # Watching state
        self._watching_channel: str | None = None
        # Launch progress timer
        self._launch_timer: threading.Timer | None = None
        self._launch_elapsed = 0
        self._launch_channel: str | None = None
        # Stale data tracking
        self._last_successful_fetch: float = 0

        self._build_ui()
        self._bind_shortcuts()
        self._player_bar.set_quality(self._config.get("quality", "best"))
        self._schedule_refresh()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Sidebar
        self._sidebar = Sidebar(
            self,
            on_channel_click=self._on_channel_click,
            on_add_channel=self._on_add_channel,
            on_remove_channel=self._on_remove_channel,
        )
        self._sidebar.grid(row=0, column=0, sticky="ns")

        # Main content area
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=0, column=1, sticky="nsew")
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # Sort/filter toolbar (row 0)
        toolbar = ctk.CTkFrame(
            main_frame, height=36, fg_color="#16162a", corner_radius=0
        )
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(1, weight=1)

        self._sort_var = ctk.StringVar(value=SORT_OPTIONS[0])
        sort_menu = ctk.CTkOptionMenu(
            toolbar,
            variable=self._sort_var,
            values=SORT_OPTIONS,
            width=140,
            height=26,
            fg_color="#2a2a3e",
            button_color=ACCENT,
            button_hover_color="#7B38D8",
            command=self._on_sort_changed,
        )
        sort_menu.grid(row=0, column=0, padx=(8, 6), pady=5)

        self._filter_entry = ctk.CTkEntry(
            toolbar,
            placeholder_text="Filter by game...",
            height=26,
            width=180,
        )
        self._filter_entry.grid(row=0, column=1, padx=(0, 8), pady=5, sticky="w")
        self._filter_entry.bind("<KeyRelease>", self._on_filter_changed)

        # Stream grid (row 1)
        self._stream_grid = StreamGrid(
            main_frame,
            on_stream_click=self._on_channel_click,
            on_stream_double_click=self._on_stream_double_click,
        )
        self._stream_grid.grid(row=1, column=0, sticky="nsew")

        # Player bar (bottom)
        self._player_bar = PlayerBar(
            self,
            on_watch=self._on_watch,
            on_open_browser=self._on_open_browser,
            on_settings=self._open_settings,
            on_refresh=self._manual_refresh,
        )
        self._player_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _on_sort_changed(self, value: str) -> None:
        self._stream_grid.set_sort_key(value)

    def _on_filter_changed(self, event: Any = None) -> None:
        self._stream_grid.set_filter_text(self._filter_entry.get())

    # ── Keyboard shortcuts ───────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        self.bind("<r>", self._shortcut_refresh)
        self.bind("<F5>", self._shortcut_refresh)
        self.bind("<space>", self._shortcut_watch)
        self.bind("<Return>", self._shortcut_watch)
        self.bind("<Command-comma>", self._shortcut_settings)
        self.bind("<Escape>", self._shortcut_deselect)

    def _entry_has_focus(self) -> bool:
        focused = self.focus_get()
        return isinstance(focused, ctk.CTkEntry)

    def _shortcut_refresh(self, event: Any = None) -> None:
        if self._entry_has_focus():
            return
        self._manual_refresh()

    def _shortcut_watch(self, event: Any = None) -> None:
        if self._entry_has_focus():
            return
        self._on_watch(self._player_bar.get_quality())

    def _shortcut_settings(self, event: Any = None) -> None:
        self._open_settings()

    def _shortcut_deselect(self, event: Any = None) -> None:
        if self._entry_has_focus():
            return
        self._selected_channel = None
        self._stream_grid.set_selected(None)
        self._sidebar.set_selected(None)
        live_logins = {s["user_login"].lower() for s in self._live_streams}
        favorites = self._config.get("favorites", [])
        self._sidebar.update_channels(
            favorites, live_logins, self._avatar_cache.as_dict()
        )
        self._player_bar.set_status("", "#888888")

    # ── Channel actions ──────────────────────────────────────────

    def _migrate_favorites(self) -> None:
        raw = self._config.get("favorites", [])
        cleaned = []
        seen: set[str] = set()
        for entry in raw:
            name = self._sanitize_username(entry)
            if name and name not in seen:
                cleaned.append(name)
                seen.add(name)
        if cleaned != raw:
            self._config["favorites"] = cleaned
            save_config(self._config)

    def _on_channel_click(self, channel: str) -> None:
        self._selected_channel = channel
        self._stream_grid.set_selected(channel)
        self._sidebar.set_selected(channel)
        live_logins = {s["user_login"].lower() for s in self._live_streams}
        favorites = self._config.get("favorites", [])
        self._sidebar.update_channels(
            favorites, live_logins, self._avatar_cache.as_dict()
        )
        self._player_bar.set_status(f"Selected: {channel}", "white")

    def _on_stream_double_click(self, login: str) -> None:
        self._selected_channel = login
        self._stream_grid.set_selected(login)
        self._on_watch(self._player_bar.get_quality())

    @staticmethod
    def _sanitize_username(raw: str) -> str:
        raw = raw.strip()
        match = re.search(r"(?:twitch\.tv/)([A-Za-z0-9_]+)", raw)
        if match:
            return match.group(1).lower()
        return re.sub(r"[^A-Za-z0-9_]", "", raw).lower()

    def _on_add_channel(self, username: str) -> None:
        username = self._sanitize_username(username)
        if not username:
            return
        favorites = self._config.get("favorites", [])
        if username not in [f.lower() for f in favorites]:
            favorites.append(username)
            self._config["favorites"] = favorites
            save_config(self._config)
            self._refresh_data()

    def _on_remove_channel(self, channel: str) -> None:
        favorites = self._config.get("favorites", [])
        self._config["favorites"] = [
            f for f in favorites if f.lower() != channel.lower()
        ]
        save_config(self._config)
        self._refresh_data()

    # ── Watch ────────────────────────────────────────────────────

    def _on_watch(self, quality: str) -> None:
        channel = self._selected_channel
        if not channel:
            self._player_bar.set_status("Select a channel first", "#FF6B6B")
            return
        live_logins = {s["user_login"].lower() for s in self._live_streams}
        if channel.lower() not in live_logins:
            self._player_bar.set_status(f"{channel} is offline", "#FF6B6B")
            return

        self._config["quality"] = quality
        save_config(self._config)
        self._player_bar.set_status(f"Launching {channel}...", "#FFC107")

        # Start launch progress timer
        self._launch_channel = channel
        self._launch_elapsed = 0
        self._start_launch_timer()

        def do_launch() -> None:
            result = launch_stream(
                channel,
                quality,
                self._config.get("streamlink_path", "streamlink"),
                self._config.get(
                    "iina_path", "/Applications/IINA.app/Contents/MacOS/iina-cli"
                ),
            )
            if not self._shutdown.is_set():
                self.after(0, lambda: self._on_launch_result(channel, result))

        threading.Thread(target=do_launch, daemon=True).start()

    def _start_launch_timer(self) -> None:
        self._cancel_launch_timer()
        self._launch_elapsed += 3

        def tick() -> None:
            if not self._shutdown.is_set() and self._launch_channel:
                ch = self._launch_channel
                elapsed = self._launch_elapsed
                self.after(
                    0,
                    lambda: self._player_bar.set_status(
                        f"Launching {ch}... ({elapsed}s)", "#FFC107"
                    ),
                )
                self._start_launch_timer()

        self._launch_timer = threading.Timer(3.0, tick)
        self._launch_timer.daemon = True
        self._launch_timer.start()

    def _cancel_launch_timer(self) -> None:
        if self._launch_timer:
            self._launch_timer.cancel()
            self._launch_timer = None

    def _on_launch_result(self, channel: str, result: Any) -> None:
        self._cancel_launch_timer()
        self._launch_channel = None
        if result.success:
            self._watching_channel = channel
            self._stream_grid.set_watching(channel)
            self._player_bar.set_status(result.message, "#00E676")
        else:
            self._player_bar.set_status("Error", "#FF6B6B")
            dialog = ctk.CTkToplevel(self)
            dialog.title("Error")
            dialog.geometry("400x200")
            dialog.resizable(False, False)
            ctk.CTkLabel(
                dialog, text=result.message, wraplength=360, justify="left"
            ).pack(padx=20, pady=20, expand=True)
            ctk.CTkButton(dialog, text="OK", command=dialog.destroy).pack(pady=(0, 20))

    def _on_open_browser(self) -> None:
        channel = self._selected_channel
        if not channel:
            self._player_bar.set_status("Select a channel first", "#FF6B6B")
            return
        webbrowser.open(f"https://twitch.tv/{channel}")

    # ── Data refresh ─────────────────────────────────────────────

    def _schedule_refresh(self) -> None:
        self._refresh_data()
        interval = self._config.get("refresh_interval", 60) * 1000
        # Check for stale data
        if self._last_successful_fetch > 0:
            stale = time.time() - self._last_successful_fetch > 2 * (interval / 1000)
            self._player_bar.set_stale(stale)
        self._refresh_job = self.after(interval, self._schedule_refresh)

    def _manual_refresh(self) -> None:
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        self._refresh_data()
        interval = self._config.get("refresh_interval", 60) * 1000
        self._refresh_job = self.after(interval, self._schedule_refresh)

    def _refresh_data(self) -> None:
        favorites = [
            self._sanitize_username(f) for f in self._config.get("favorites", [])
        ]
        favorites = [f for f in favorites if f]
        if not favorites:
            self._sidebar.update_channels([], set(), {})
            self._stream_grid.update_streams([], {}, {})
            self._player_bar.set_status("Add channels to get started", "#888888")
            self._player_bar.set_total_viewers(0)
            self.title("TwitchX")
            return

        if not self._config.get("client_id") or not self._config.get("client_secret"):
            self._sidebar.update_channels(favorites, set(), {})
            self._stream_grid.show_onboarding(self._open_settings)
            self._player_bar.set_status(
                "Set Twitch API credentials in Settings", "#FF6B6B"
            )
            return

        if self._fetching:
            return
        self._fetching = True
        self._player_bar.set_status("Refreshing...", "#888888")
        threading.Thread(
            target=self._fetch_data, args=(list(favorites),), daemon=True
        ).start()

    def _fetch_data(self, favorites: list[str]) -> None:
        retry_delays = [5, 15, 30]
        max_attempts = len(retry_delays) + 1

        try:
            for attempt in range(1, max_attempts + 1):
                if self._shutdown.is_set():
                    return
                loop = asyncio.new_event_loop()
                try:
                    streams, users = loop.run_until_complete(
                        self._async_fetch(favorites)
                    )
                    if not self._shutdown.is_set():
                        self.after(
                            0,
                            lambda s=streams, u=users: self._on_data_fetched(
                                favorites, s, u
                            ),
                        )
                    return
                except httpx.ConnectError:
                    if attempt < max_attempts:
                        delay = retry_delays[attempt - 1]
                        att = attempt + 1
                        if not self._shutdown.is_set():
                            self.after(
                                0,
                                lambda a=att, mx=max_attempts: (
                                    self._player_bar.set_status(
                                        f"Reconnecting... (attempt {a}/{mx})",
                                        "#FFC107",
                                    )
                                ),
                            )
                        time.sleep(delay)
                    else:
                        if not self._shutdown.is_set():
                            self.after(
                                0,
                                lambda: self._player_bar.set_status(
                                    "No internet connection", "#FF6B6B"
                                ),
                            )
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    if not self._shutdown.is_set():
                        if status_code in (401, 403):
                            self.after(
                                0,
                                lambda: self._player_bar.set_status(
                                    "Check your Twitch API credentials in Settings",
                                    "#FF6B6B",
                                ),
                            )
                        else:
                            self.after(
                                0,
                                lambda code=status_code: self._player_bar.set_status(
                                    f"API error: {code}", "#FF6B6B"
                                ),
                            )
                    return
                except ValueError:
                    if not self._shutdown.is_set():
                        self.after(
                            0,
                            lambda: self._player_bar.set_status(
                                "Set Twitch API credentials in Settings",
                                "#FF6B6B",
                            ),
                        )
                    return
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    msg = str(e)[:80] if str(e) else "Unknown error"
                    if not self._shutdown.is_set():
                        self.after(
                            0,
                            lambda m=msg: self._player_bar.set_status(
                                f"Error: {m}", "#FF6B6B"
                            ),
                        )
                    return
                finally:
                    loop.close()
        finally:
            if not self._shutdown.is_set():
                self.after(0, self._clear_fetching)

    def _clear_fetching(self) -> None:
        self._fetching = False

    async def _async_fetch(self, favorites: list[str]) -> tuple[list[dict], list[dict]]:
        client = TwitchClient()
        try:
            await client._ensure_token()
            streams, users = await asyncio.gather(
                client.get_live_streams(favorites),
                client.get_users(favorites),
            )
            game_ids = [s.get("game_id", "") for s in streams if s.get("game_id")]
            if game_ids:
                games = await client.get_games(game_ids)
                self._games.update(games)
            return streams, users
        finally:
            await client.close()

    def _on_data_fetched(
        self, favorites: list[str], streams: list[dict], users: list[dict]
    ) -> None:
        self._live_streams = streams
        self._last_successful_fetch = time.time()
        self._player_bar.set_stale(False)
        live_logins = {s["user_login"].lower() for s in streams}

        # ── Notifications ─────────────────────────────────────────
        if self._first_fetch_done:
            newly_live = live_logins - self._prev_live_logins
            if newly_live:
                stream_map = {s["user_login"].lower(): s for s in streams}
                for login in newly_live:
                    s = stream_map.get(login)
                    if s:
                        self._send_notification(
                            s.get("user_name", login),
                            s.get("title", ""),
                            s.get("game_name", ""),
                        )
        self._prev_live_logins = set(live_logins)
        self._first_fetch_done = True

        # Load avatars in background (with disk cache)
        user_avatars = {
            u["login"].lower(): u.get("profile_image_url", "") for u in users
        }
        threading.Thread(
            target=self._load_avatars, args=(user_avatars,), daemon=True
        ).start()

        # Load thumbnails in background
        thumb_urls = {}
        for s in streams:
            login = s["user_login"].lower()
            url = (
                s.get("thumbnail_url", "")
                .replace("{width}", "880")
                .replace("{height}", "496")
            )
            if url:
                thumb_urls[login] = url
        if thumb_urls:
            threading.Thread(
                target=self._load_thumbnails, args=(thumb_urls,), daemon=True
            ).start()

        # Update sidebar
        self._sidebar.update_channels(
            favorites, live_logins, self._avatar_cache.as_dict()
        )

        # Update grid
        self._stream_grid.update_streams(
            streams, self._thumb_cache.as_dict(), self._games
        )

        now = datetime.now().strftime("%H:%M:%S")
        self._player_bar.set_updated(f"Updated {now}")
        live_count = len(streams)
        self._player_bar.set_status(
            f"{live_count} channel{'s' if live_count != 1 else ''} live",
            "#00E676" if live_count else "#888888",
        )

        # Total viewers
        total = sum(s.get("viewer_count", 0) for s in streams)
        self._player_bar.set_total_viewers(total)

        # Window title
        if live_count:
            self.title(f"TwitchX \u2014 {live_count} live")
        else:
            self.title("TwitchX")

    # ── Notifications ─────────────────────────────────────────────

    def _send_notification(self, name: str, title: str, game: str) -> None:
        # Escape double quotes for AppleScript
        safe_name = name.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')[:80]
        safe_game = game.replace('"', '\\"')

        script = (
            f'display notification "{safe_name} is now live: {safe_title}" '
            f'with title "TwitchX" subtitle "{safe_game}"'
        )

        def do_notify() -> None:
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=5,
                )

        threading.Thread(target=do_notify, daemon=True).start()

    # ── Avatar loading (with disk cache) ──────────────────────────

    def _load_avatars(self, avatars: dict[str, str]) -> None:
        for login, url in avatars.items():
            if self._shutdown.is_set():
                return
            if self._avatar_cache.get(login) or not url:
                continue

            # Try disk cache first
            cached_bytes = get_cached_avatar(login)
            if cached_bytes:
                try:
                    img = Image.open(io.BytesIO(cached_bytes)).resize((28, 28))
                    ctk_img = ctk.CTkImage(
                        light_image=img, dark_image=img, size=(28, 28)
                    )
                    self._avatar_cache.put(login, ctk_img)
                    continue
                except Exception:
                    pass

            # Fetch from network
            try:
                resp = httpx.get(url, timeout=10)
                raw_bytes = resp.content
                img = Image.open(io.BytesIO(raw_bytes)).resize((28, 28))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(28, 28))
                self._avatar_cache.put(login, ctk_img)
                save_avatar(login, raw_bytes)
            except Exception:
                pass

        if not self._shutdown.is_set():
            self.after(0, self._update_sidebar_avatars)

    def _update_sidebar_avatars(self) -> None:
        favorites = self._config.get("favorites", [])
        live_logins = {s["user_login"].lower() for s in self._live_streams}
        self._sidebar.update_channels(
            favorites, live_logins, self._avatar_cache.as_dict()
        )

    def _load_thumbnails(self, thumb_urls: dict[str, str]) -> None:
        def fetch_one(login: str, url: str) -> tuple[str, bytes | None]:
            try:
                resp = httpx.get(url, timeout=10)
                return login, resp.content
            except Exception:
                return login, None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(fetch_one, login, url): login
                for login, url in thumb_urls.items()
            }
            for future in as_completed(futures):
                if self._shutdown.is_set():
                    return
                login, raw = future.result()
                if raw is None:
                    continue
                try:
                    img = Image.open(io.BytesIO(raw)).resize((220, 124))
                    ctk_img = ctk.CTkImage(
                        light_image=img, dark_image=img, size=(220, 124)
                    )
                    self._thumb_cache.put(login, ctk_img)
                    if not self._shutdown.is_set():
                        self.after(
                            0,
                            lambda lg=login, im=ctk_img: (
                                self._stream_grid.update_thumbnail(lg, im)
                            ),
                        )
                except Exception:
                    pass

    # ── Settings ─────────────────────────────────────────────────

    def _open_settings(self) -> None:
        SettingsDialog(self, self._config, self._on_settings_saved)

    def _on_settings_saved(self, new_config: dict[str, Any]) -> None:
        self._config = new_config
        save_config(self._config)
        self._manual_refresh()

    # ── Cleanup ──────────────────────────────────────────────────

    def destroy(self) -> None:
        self._shutdown.set()
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        super().destroy()
