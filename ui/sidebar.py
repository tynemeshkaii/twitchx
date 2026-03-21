from __future__ import annotations

import tkinter as tk
import webbrowser
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from core.platforms import build_channel_url
from core.utils import bind_standard_text_shortcuts
from ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BG_BORDER,
    BG_ELEVATED,
    BG_OVERLAY,
    BG_SURFACE,
    FONT_SYSTEM,
    LIVE_GREEN,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

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
        bg = BG_OVERLAY if selected else "transparent"
        super().__init__(master, fg_color=bg, cursor="hand2")
        self._channel = channel
        self._on_click = on_click
        self._on_remove = on_remove
        self._is_live = is_live

        self.grid_columnconfigure(2, weight=1)

        # Selection accent bar (left edge)
        bar_color = ACCENT if selected else "transparent"
        self._accent_bar = ctk.CTkFrame(
            self, width=3, fg_color=bar_color, corner_radius=2
        )
        self._accent_bar.grid(row=0, column=0, sticky="ns", padx=(0, 2))

        # Live indicator dot
        dot_color = LIVE_GREEN if is_live else TEXT_MUTED
        self._dot = ctk.CTkLabel(
            self, text="\u25cf", text_color=dot_color, width=16, font=(FONT_SYSTEM, 10)
        )
        self._dot.grid(row=0, column=1, padx=(2, 2), pady=(3, 3))

        # Avatar
        self._avatar: ctk.CTkLabel | None = None
        col_name = 2
        if avatar_image:
            self._avatar = ctk.CTkLabel(
                self, image=avatar_image, text="", width=28, height=28
            )
            self._avatar.grid(row=0, column=2, padx=(2, 6), pady=(3, 3))
            col_name = 3
            self.grid_columnconfigure(3, weight=1)
        else:
            self.grid_columnconfigure(2, weight=1)

        # Channel name — bold only when selected
        self._name_label = ctk.CTkLabel(
            self,
            text=channel,
            anchor="w",
            font=(FONT_SYSTEM, 13, "bold") if selected else (FONT_SYSTEM, 13),
            text_color=TEXT_PRIMARY if is_live else (TEXT_SECONDARY if selected else TEXT_MUTED),
        )
        self._name_label.grid(row=0, column=col_name, sticky="w", padx=(2, 4), pady=(3, 3))

        # Bind click (all channels, not just live)
        if on_click:
            for widget in [self, self._dot, self._name_label]:
                widget.bind("<Button-1>", lambda e, ch=channel: on_click(ch))
            if self._avatar:
                self._avatar.bind("<Button-1>", lambda e, ch=channel: on_click(ch))

        # Hover effect
        for widget in [self, self._dot, self._name_label]:
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
        if self._avatar:
            self._avatar.bind("<Enter>", self._on_enter, add="+")
            self._avatar.bind("<Leave>", self._on_leave, add="+")
        self._selected = selected

        # Right-click context menu
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.configure(
            background=BG_ELEVATED,
            foreground=TEXT_PRIMARY,
            activebackground=ACCENT,
            activeforeground="white",
            borderwidth=0,
            font=(FONT_SYSTEM, 12),
        )
        self._menu.add_command(
            label="Open in Browser",
            command=lambda: webbrowser.open(build_channel_url(channel)),
        )
        self._menu.add_separator()
        self._menu.add_command(label="Remove from favorites", command=self._remove)
        for widget in [self, self._dot, self._name_label]:
            widget.bind("<Button-2>", self._show_menu)
            widget.bind("<Control-Button-1>", self._show_menu)

    def _on_enter(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._selected:
            self.configure(fg_color=BG_OVERLAY)

    def _on_leave(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._selected:
            self.configure(fg_color="transparent")

    def _show_menu(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._menu.post(event.x_root, event.y_root)

    def update_avatar(self, image: ctk.CTkImage) -> None:
        if self._avatar:
            self._avatar.configure(image=image)
            return

        self._avatar = ctk.CTkLabel(self, image=image, text="", width=28, height=28)
        self._avatar.grid(row=0, column=2, padx=(2, 6), pady=(3, 3))
        self._avatar.bind("<Enter>", self._on_enter, add="+")
        self._avatar.bind("<Leave>", self._on_leave, add="+")
        if self._on_click:
            self._avatar.bind(
                "<Button-1>", lambda e, ch=self._channel: self._on_click(ch)
            )
        self.grid_columnconfigure(3, weight=1)
        self._name_label.grid(row=0, column=3, sticky="w", padx=(2, 4), pady=(3, 3))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.configure(fg_color=BG_OVERLAY if selected else "transparent")
        self._accent_bar.configure(fg_color=ACCENT if selected else "transparent")
        self._name_label.configure(
            font=(FONT_SYSTEM, 13, "bold") if selected else (FONT_SYSTEM, 13),
            text_color=(
                TEXT_PRIMARY
                if self._is_live
                else (TEXT_SECONDARY if selected else TEXT_MUTED)
            ),
        )

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

        dot_color = LIVE_GREEN if is_live else TEXT_MUTED
        dot = ctk.CTkLabel(
            self, text="\u25cf", text_color=dot_color, width=14, font=(FONT_SYSTEM, 10)
        )
        dot.grid(row=0, column=0, padx=(4, 4), pady=2)

        name_label = ctk.CTkLabel(
            self,
            text=display_name,
            font=(FONT_SYSTEM, 12, "bold") if is_live else (FONT_SYSTEM, 12),
            text_color=TEXT_PRIMARY if is_live else TEXT_SECONDARY,
            anchor="w",
        )
        name_label.grid(row=0, column=1, sticky="w", padx=(0, 4), pady=2)

        if is_live and game_name:
            game_label = ctk.CTkLabel(
                self,
                text=game_name,
                font=(FONT_SYSTEM, 10),
                text_color=TEXT_MUTED,
                anchor="e",
            )
            game_label.grid(row=0, column=2, sticky="e", padx=(0, 6), pady=2)

        for w in [self, dot, name_label]:
            w.bind("<Button-1>", lambda e, lg=login: on_select(lg))

        # Hover
        for w in [self, dot, name_label]:
            w.bind("<Enter>", lambda e: self.configure(fg_color=BG_OVERLAY))
            w.bind("<Leave>", lambda e: self.configure(fg_color="transparent"))


class Sidebar(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        on_channel_click: Callable[[str], None] | None = None,
        on_add_channel: Callable[[str], None] | None = None,
        on_remove_channel: Callable[[str], None] | None = None,
        on_search_channels: Callable[[str], None] | None = None,
        on_login: Callable[[], None] | None = None,
        on_logout: Callable[[], None] | None = None,
        on_import_follows: Callable[[], None] | None = None,
        on_reorder_channel: Callable[[list[str]], None] | None = None,
    ) -> None:
        super().__init__(master, width=SIDEBAR_WIDTH, corner_radius=0, fg_color=BG_SURFACE)
        self._on_channel_click = on_channel_click
        self._on_add_channel = on_add_channel
        self._on_remove_channel = on_remove_channel
        self._on_search_channels = on_search_channels
        self._on_login = on_login
        self._on_logout = on_logout
        self._on_import_follows = on_import_follows
        self._on_reorder_channel = on_reorder_channel
        self._channel_items: list[ChannelItem] = []
        self._items_by_channel: dict[str, ChannelItem] = {}
        self._selected_channel: str | None = None
        self._current_channels: list[str] = []
        self._current_live_set: set[str] = set()
        self._search_debounce_job: str | None = None
        # Drag-to-reorder state
        self._drag_active = False
        self._drag_start_y: int = 0
        self._drag_channel: str | None = None
        self._drag_indicator: ctk.CTkFrame | None = None
        self._respect_manual_order = False

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)

        # ── User profile / login area (row 0) ──────────────────
        self._profile_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._profile_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(12, 6))
        self._profile_frame.grid_columnconfigure(0, weight=1)
        self._build_login_button()

        # Header (row 1) with live count badge
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 4))
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="FAVORITES",
            font=(FONT_SYSTEM, 11, "bold"),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w")

        self._live_badge = ctk.CTkLabel(
            header_frame,
            text="",
            font=(FONT_SYSTEM, 9, "bold"),
            text_color="white",
            fg_color="transparent",
            corner_radius=8,
            height=18,
            padx=6,
        )
        self._live_badge.grid(row=0, column=1, sticky="e")

        # Scrollable channel list
        self._scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            width=SIDEBAR_WIDTH - 20,
            scrollbar_button_color=BG_BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        self._scroll_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self._scroll_frame.grid_columnconfigure(0, weight=1)

        # Separator above add area
        sep = ctk.CTkFrame(self, height=1, fg_color=BG_BORDER, corner_radius=0)
        sep.grid(row=3, column=0, sticky="ew")

        # Add channel area (entry + button + search dropdown)
        self._add_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._add_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(6, 8))
        self._add_frame.grid_columnconfigure(0, weight=1)

        self._add_entry = ctk.CTkEntry(
            self._add_frame,
            placeholder_text="Search channels or paste URL...",
            height=30,
            fg_color=BG_ELEVATED,
            border_color=BG_BORDER,
            border_width=1,
            placeholder_text_color=TEXT_MUTED,
            corner_radius=RADIUS_SM,
        )
        self._add_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._add_entry.bind("<Return>", self._on_add_pressed)
        self._add_entry.bind("<KeyRelease>", self._on_search_key)
        self._add_entry.bind("<Escape>", lambda e: self._hide_search_dropdown())
        self._add_entry.bind("<FocusOut>", self._on_entry_focus_out)
        bind_standard_text_shortcuts(self._add_entry)

        self._add_btn = ctk.CTkButton(
            self._add_frame,
            text="+",
            width=30,
            height=30,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=RADIUS_SM,
        )
        self._add_btn.configure(command=self._on_add_pressed)
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
            font=(FONT_SYSTEM, 10),
            text_color=TEXT_MUTED,
        )
        self._search_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def show_search_results(self, results: list[dict[str, Any]]) -> None:
        self._hide_search_dropdown()
        if not results:
            self._search_label = ctk.CTkLabel(
                self._add_frame,
                text="No channels found",
                font=(FONT_SYSTEM, 10),
                text_color=TEXT_MUTED,
            )
            self._search_label.grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(2, 0)
            )
            return

        dropdown = ctk.CTkScrollableFrame(
            self._add_frame,
            fg_color=BG_ELEVATED,
            corner_radius=RADIUS_SM,
            height=min(len(results) * 32, 256),
            width=SIDEBAR_WIDTH - 40,
            border_width=1,
            border_color=BG_BORDER,
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
                is_selected = (
                    self._selected_channel is not None
                    and ch.lower() == self._selected_channel.lower()
                )
                if item:
                    item.set_selected(is_selected)
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

        # Sort: live first, preserve manual order within groups if enabled
        if self._respect_manual_order:
            order = {c.lower(): i for i, c in enumerate(channels)}
            sorted_channels = sorted(
                channels,
                key=lambda c: (c.lower() not in live_set, order.get(c.lower(), 0)),
            )
        else:
            sorted_channels = sorted(
                channels,
                key=lambda c: (c.lower() not in live_set, c.lower()),
            )

        live_count = sum(1 for c in channels if c.lower() in live_set)
        self._update_live_badge(live_count)

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

            # Drag-to-reorder bindings
            for w in [item, item._dot, item._name_label]:
                w.bind("<ButtonPress-1>", lambda e, c=ch: self._drag_start(e, c), add="+")
                w.bind("<B1-Motion>", self._drag_motion)
                w.bind("<ButtonRelease-1>", self._drag_end, add="+")

    def _update_live_badge(self, count: int) -> None:
        if count > 0:
            self._live_badge.configure(text=f"{count} live", fg_color=ACCENT)
        else:
            self._live_badge.configure(text="", fg_color="transparent")

    # ── Drag-to-reorder ───────────────────────────────────────

    def _drag_start(self, event: tk.Event, channel: str) -> None:  # type: ignore[type-arg]
        self._drag_start_y = event.y_root
        self._drag_channel = channel
        self._drag_active = False

    def _drag_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._drag_channel is None:
            return
        dy = abs(event.y_root - self._drag_start_y)
        if dy < 5:
            return
        self._drag_active = True
        # Show drag indicator
        self._hide_drag_indicator()
        target_idx = self._get_drop_index(event.y_root)
        if target_idx is not None and target_idx < len(self._channel_items):
            target_item = self._channel_items[target_idx]
            indicator = ctk.CTkFrame(
                self._scroll_frame, height=2, fg_color=ACCENT, corner_radius=0
            )
            indicator.pack(before=target_item, fill="x", pady=0)
            self._drag_indicator = indicator
        elif target_idx is not None:
            indicator = ctk.CTkFrame(
                self._scroll_frame, height=2, fg_color=ACCENT, corner_radius=0
            )
            indicator.pack(fill="x", pady=0)
            self._drag_indicator = indicator

    def _drag_end(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._hide_drag_indicator()
        if not self._drag_active or self._drag_channel is None:
            self._drag_channel = None
            self._drag_active = False
            return
        target_idx = self._get_drop_index(event.y_root)
        channel = self._drag_channel
        self._drag_channel = None
        self._drag_active = False
        if target_idx is None:
            return
        # Reorder the displayed list and map back to favorites order
        displayed = [item._channel for item in self._channel_items]
        if channel not in displayed:
            return
        old_idx = displayed.index(channel)
        if old_idx == target_idx:
            return
        displayed.pop(old_idx)
        if target_idx > old_idx:
            target_idx -= 1
        displayed.insert(target_idx, channel)
        self._respect_manual_order = True
        if self._on_reorder_channel:
            self._on_reorder_channel(displayed)

    def _get_drop_index(self, y_root: int) -> int | None:
        if not self._channel_items:
            return None
        for idx, item in enumerate(self._channel_items):
            try:
                iy = item.winfo_rooty()
                ih = item.winfo_height()
                if y_root < iy + ih // 2:
                    return idx
            except Exception:
                return None
        return len(self._channel_items)

    def _hide_drag_indicator(self) -> None:
        if self._drag_indicator:
            self._drag_indicator.destroy()
            self._drag_indicator = None

    # ── User profile ───────────────────────────────────────────

    def _build_login_button(self) -> None:
        for w in self._profile_frame.winfo_children():
            w.destroy()
        btn = ctk.CTkButton(
            self._profile_frame,
            text="Login with Twitch",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            height=34,
            font=(FONT_SYSTEM, 13, "bold"),
            corner_radius=RADIUS_MD,
            command=self._on_login,
        )
        btn.pack(fill="x")

    def _build_user_profile(
        self,
        display_name: str,
        avatar_image: ctk.CTkImage | None = None,
    ) -> None:
        for w in self._profile_frame.winfo_children():
            w.destroy()

        row = ctk.CTkFrame(self._profile_frame, fg_color="transparent")
        row.pack(fill="x")
        row.grid_columnconfigure(1, weight=1)

        col = 0
        if avatar_image:
            avatar_label = ctk.CTkLabel(
                row, image=avatar_image, text="", width=32, height=32
            )
            avatar_label.grid(row=0, column=0, padx=(0, 6), pady=2)
            col = 1

        name_label = ctk.CTkLabel(
            row,
            text=display_name,
            font=(FONT_SYSTEM, 13, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        name_label.grid(row=0, column=col, sticky="w", pady=2)

        logout_label = ctk.CTkLabel(
            row,
            text="Logout",
            font=(FONT_SYSTEM, 10),
            text_color=TEXT_MUTED,
            cursor="hand2",
        )
        logout_label.grid(row=0, column=col + 1, sticky="e", padx=(4, 0), pady=2)
        logout_label.bind("<Button-1>", lambda e: self._on_logout and self._on_logout())
        logout_label.bind("<Enter>", lambda e: logout_label.configure(text_color=TEXT_SECONDARY))
        logout_label.bind("<Leave>", lambda e: logout_label.configure(text_color=TEXT_MUTED))

        # Import follows button
        if self._on_import_follows:
            import_btn = ctk.CTkButton(
                self._profile_frame,
                text="\u2193 Import followed",
                fg_color=BG_ELEVATED,
                hover_color=BG_OVERLAY,
                height=26,
                font=(FONT_SYSTEM, 11),
                corner_radius=RADIUS_SM,
                command=self._on_import_follows,
            )
            import_btn.pack(fill="x", pady=(4, 0))

    def update_user_profile(
        self,
        user: dict[str, Any] | None,
        avatar_image: ctk.CTkImage | None = None,
    ) -> None:
        if user is None:
            self._build_login_button()
        else:
            self._build_user_profile(
                user.get("display_name", user.get("login", "")),
                avatar_image=avatar_image,
            )
