from __future__ import annotations

import tkinter as tk
import webbrowser
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

ACCENT = "#9146FF"
SIDEBAR_WIDTH = 240


class ChannelItem(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        channel: str,
        is_live: bool = False,
        selected: bool = False,
        avatar_image: ctk.CTkImage | None = None,
        on_click: Callable[[str], None] | None = None,
        on_remove: Callable[[str], None] | None = None,
    ) -> None:
        bg = "#2a2a3e" if selected else "transparent"
        super().__init__(master, fg_color=bg, cursor="hand2")
        self._channel = channel
        self._on_click = on_click
        self._on_remove = on_remove
        self._is_live = is_live

        self.grid_columnconfigure(2, weight=1)

        # Selection accent bar (left edge)
        bar_color = ACCENT if selected else "transparent"
        self._accent_bar = ctk.CTkFrame(
            self, width=3, fg_color=bar_color, corner_radius=0
        )
        self._accent_bar.grid(row=0, column=0, sticky="ns", padx=(0, 2))

        # Live indicator dot
        dot_color = "#00E676" if is_live else "#555555"
        self._dot = ctk.CTkLabel(
            self, text="\u25cf", text_color=dot_color, width=16, font=("", 12)
        )
        self._dot.grid(row=0, column=1, padx=(2, 2), pady=4)

        # Avatar
        self._avatar: ctk.CTkLabel | None = None
        col_name = 2
        if avatar_image:
            self._avatar = ctk.CTkLabel(
                self, image=avatar_image, text="", width=28, height=28
            )
            self._avatar.grid(row=0, column=2, padx=(2, 6), pady=4)
            col_name = 3
            self.grid_columnconfigure(3, weight=1)
        else:
            self.grid_columnconfigure(2, weight=1)

        # Channel name
        is_bold = is_live or selected
        self._name_label = ctk.CTkLabel(
            self,
            text=channel,
            anchor="w",
            font=("", 13, "bold") if is_bold else ("", 13),
            text_color="white" if is_live else ("#cccccc" if selected else "#aaaaaa"),
        )
        self._name_label.grid(row=0, column=col_name, sticky="w", padx=(2, 4), pady=4)

        # Bind click (all channels, not just live)
        if on_click:
            for widget in [self, self._dot, self._name_label]:
                widget.bind("<Button-1>", lambda e, ch=channel: on_click(ch))
            if self._avatar:
                self._avatar.bind("<Button-1>", lambda e, ch=channel: on_click(ch))

        # Right-click context menu
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(
            label="Open in Browser",
            command=lambda: webbrowser.open(f"https://twitch.tv/{channel}"),
        )
        self._menu.add_separator()
        self._menu.add_command(label="Remove from favorites", command=self._remove)
        for widget in [self, self._dot, self._name_label]:
            widget.bind("<Button-2>", self._show_menu)
            widget.bind("<Control-Button-1>", self._show_menu)

    def _show_menu(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._menu.post(event.x_root, event.y_root)

    def update_avatar(self, image: ctk.CTkImage) -> None:
        if self._avatar:
            self._avatar.configure(image=image)

    def _remove(self) -> None:
        if self._on_remove:
            self._on_remove(self._channel)


class SearchResultRow(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        display_name: str,
        login: str,
        is_live: bool,
        game_name: str,
        on_select: Callable[[str], None],
    ) -> None:
        super().__init__(master, fg_color="transparent", cursor="hand2", height=32)
        self.grid_columnconfigure(1, weight=1)

        dot_color = "#00E676" if is_live else "#555555"
        dot = ctk.CTkLabel(
            self, text="\u25cf", text_color=dot_color, width=14, font=("", 10)
        )
        dot.grid(row=0, column=0, padx=(4, 4), pady=2)

        name_label = ctk.CTkLabel(
            self,
            text=display_name,
            font=("", 12, "bold") if is_live else ("", 12),
            text_color="white" if is_live else "#bbbbbb",
            anchor="w",
        )
        name_label.grid(row=0, column=1, sticky="w", padx=(0, 4), pady=2)

        if is_live and game_name:
            game_label = ctk.CTkLabel(
                self,
                text=game_name,
                font=("", 10),
                text_color="#888888",
                anchor="e",
            )
            game_label.grid(row=0, column=2, sticky="e", padx=(0, 6), pady=2)

        for w in [self, dot, name_label]:
            w.bind("<Button-1>", lambda e, lg=login: on_select(lg))

        # Hover
        for w in [self, dot, name_label]:
            w.bind("<Enter>", lambda e: self.configure(fg_color="#2a2a3e"))
            w.bind("<Leave>", lambda e: self.configure(fg_color="transparent"))


class Sidebar(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        on_channel_click: Callable[[str], None] | None = None,
        on_add_channel: Callable[[str], None] | None = None,
        on_remove_channel: Callable[[str], None] | None = None,
        on_search_channels: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master, width=SIDEBAR_WIDTH, corner_radius=0)
        self._on_channel_click = on_channel_click
        self._on_add_channel = on_add_channel
        self._on_remove_channel = on_remove_channel
        self._on_search_channels = on_search_channels
        self._channel_items: list[ChannelItem] = []
        self._items_by_channel: dict[str, ChannelItem] = {}
        self._selected_channel: str | None = None
        self._current_channels: list[str] = []
        self._current_live_set: set[str] = set()
        self._search_debounce_job: str | None = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)

        # Header
        header = ctk.CTkLabel(
            self, text="Favorites", font=("", 16, "bold"), text_color=ACCENT
        )
        header.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")

        # Scrollable channel list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", width=SIDEBAR_WIDTH - 20
        )
        self._scroll_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        # Add channel area (entry + button + search dropdown)
        self._add_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._add_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        self._add_frame.grid_columnconfigure(0, weight=1)

        self._add_entry = ctk.CTkEntry(
            self._add_frame, placeholder_text="Search channels...", height=30
        )
        self._add_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._add_entry.bind("<Return>", self._on_add_pressed)
        self._add_entry.bind("<KeyRelease>", self._on_search_key)
        self._add_entry.bind("<Escape>", lambda e: self._hide_search_dropdown())
        self._add_entry.bind("<FocusOut>", self._on_entry_focus_out)

        self._add_btn = ctk.CTkButton(
            self._add_frame,
            text="+",
            width=30,
            height=30,
            fg_color=ACCENT,
            hover_color="#7B38D8",
            command=self._on_add_pressed,
        )
        self._add_btn.grid(row=0, column=1)

        # Search dropdown (hidden by default)
        self._search_dropdown: ctk.CTkScrollableFrame | None = None
        self._search_label: ctk.CTkLabel | None = None

    # ── Search ────────────────────────────────────────────────

    def _on_search_key(self, event: tk.Event | None = None) -> None:
        query = self._add_entry.get().strip()
        if not query or len(query) < 2:
            self._hide_search_dropdown()
            return
        # Debounce: cancel previous timer, schedule new one
        if self._search_debounce_job:
            self.after_cancel(self._search_debounce_job)
        self._search_debounce_job = self.after(
            400, lambda q=query: self._trigger_search(q)  # type: ignore[misc]
        )

    def _trigger_search(self, query: str) -> None:
        self._search_debounce_job = None
        self._show_search_loading()
        if self._on_search_channels:
            self._on_search_channels(query)

    def _show_search_loading(self) -> None:
        self._hide_search_dropdown()
        self._search_label = ctk.CTkLabel(
            self._add_frame,
            text="Searching...",
            font=("", 10),
            text_color="#888888",
        )
        self._search_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def show_search_results(self, results: list[dict[str, Any]]) -> None:
        self._hide_search_dropdown()
        if not results:
            self._search_label = ctk.CTkLabel(
                self._add_frame,
                text="No channels found",
                font=("", 10),
                text_color="#888888",
            )
            self._search_label.grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(2, 0)
            )
            return

        dropdown = ctk.CTkScrollableFrame(
            self._add_frame,
            fg_color="#1a1a2e",
            corner_radius=6,
            height=min(len(results) * 32, 256),
            width=SIDEBAR_WIDTH - 40,
        )
        dropdown.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        dropdown.grid_columnconfigure(0, weight=1)
        self._search_dropdown = dropdown

        for r in results:
            login = r.get("broadcaster_login", "")
            display = r.get("display_name", login)
            is_live = r.get("is_live", False)
            game = r.get("game_name", "") if is_live else ""
            row = SearchResultRow(
                dropdown,
                display_name=display,
                login=login,
                is_live=is_live,
                game_name=game,
                on_select=self._on_search_select,
            )
            row.pack(fill="x", pady=1)

    def _on_search_select(self, login: str) -> None:
        self._hide_search_dropdown()
        self._add_entry.delete(0, "end")
        if self._on_add_channel:
            self._on_add_channel(login)

    def _hide_search_dropdown(self) -> None:
        if self._search_dropdown:
            self._search_dropdown.destroy()
            self._search_dropdown = None
        if self._search_label:
            self._search_label.destroy()
            self._search_label = None

    def _on_entry_focus_out(self, event: tk.Event | None = None) -> None:
        # Delay to allow click events on dropdown to fire first
        self.after(200, self._hide_search_dropdown)

    # ── Channel management ────────────────────────────────────

    def _on_add_pressed(self, event: tk.Event | None = None) -> None:
        username = self._add_entry.get().strip()
        if username and self._on_add_channel:
            self._on_add_channel(username)
            self._add_entry.delete(0, "end")
            self._hide_search_dropdown()

    def set_selected(self, channel: str | None) -> None:
        self._selected_channel = channel

    def update_channels(
        self,
        channels: list[str],
        live_set: set[str],
        avatars: dict[str, ctk.CTkImage],
    ) -> None:
        # Diff check: if channels and live status unchanged, just update avatars
        if (
            channels == self._current_channels
            and live_set == self._current_live_set
            and self._channel_items
        ):
            for ch in channels:
                item = self._items_by_channel.get(ch.lower())
                avatar = avatars.get(ch.lower())
                if item and avatar:
                    item.update_avatar(avatar)
            return

        self._current_channels = list(channels)
        self._current_live_set = set(live_set)

        # Full rebuild
        for item in self._channel_items:
            item.destroy()
        self._channel_items.clear()
        self._items_by_channel.clear()

        # Sort: live channels first, then alphabetical
        sorted_channels = sorted(
            channels, key=lambda c: (c.lower() not in live_set, c.lower())
        )

        for ch in sorted_channels:
            is_live = ch.lower() in live_set
            is_selected = (
                self._selected_channel is not None
                and ch.lower() == self._selected_channel.lower()
            )
            avatar = avatars.get(ch.lower())
            item = ChannelItem(
                self._scroll_frame,
                channel=ch,
                is_live=is_live,
                selected=is_selected,
                avatar_image=avatar,
                on_click=self._on_channel_click,
                on_remove=self._on_remove_channel,
            )
            item.pack(fill="x", pady=1)
            self._channel_items.append(item)
            self._items_by_channel[ch.lower()] = item
