from __future__ import annotations

import tkinter as tk
import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import customtkinter as ctk

from core.utils import Tooltip, format_viewers
from ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BG_BASE,
    BG_BORDER,
    BG_ELEVATED,
    BG_OVERLAY,
    FONT_SYSTEM,
    LIVE_GREEN,
    LIVE_RED,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

CARD_WIDTH = 240
COLUMNS = 3

SORT_MOST_VIEWERS = "Most viewers"
SORT_RECENT = "Recently started"
SORT_ALPHA = "Alphabetical"
SORT_OPTIONS = [SORT_MOST_VIEWERS, SORT_RECENT, SORT_ALPHA]


def format_uptime(started_at: str) -> str:
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        delta = datetime.now(UTC) - start
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return ""
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except (ValueError, TypeError):
        return ""


class StreamCard(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        *,
        login: str,
        channel: str,
        title: str,
        game: str,
        viewers: int,
        started_at: str,
        thumbnail: ctk.CTkImage | None = None,
        on_click: Callable[[str], None] | None = None,
        on_double_click: Callable[[str], None] | None = None,
        on_add_favorite: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            fg_color=BG_ELEVATED,
            corner_radius=RADIUS_LG,
            border_width=1,
            border_color=BG_BORDER,
            cursor="hand2",
        )
        self._login = login
        self._channel = channel
        self._started_at = started_at
        self._selected = False

        self.grid_columnconfigure(0, weight=1)

        # Hover effect
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        # Thumbnail
        self._shimmer_job: str | None = None
        if thumbnail:
            self._thumb_label = ctk.CTkLabel(
                self, image=thumbnail, text="", corner_radius=RADIUS_MD
            )
        else:
            self._thumb_label = ctk.CTkLabel(
                self,
                text="",
                height=135,
                fg_color=BG_ELEVATED,
                corner_radius=RADIUS_MD,
            )
            self._start_shimmer()
        self._thumb_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))

        # Info area
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        info.grid_columnconfigure(0, weight=1)

        # LIVE badge + viewers + uptime row
        badge_row = ctk.CTkFrame(info, fg_color="transparent")
        badge_row.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        badge_row.grid_columnconfigure(2, weight=1)
        self._prev_viewers: int | None = None

        live_badge = ctk.CTkLabel(
            badge_row,
            text=" LIVE ",
            font=(FONT_SYSTEM, 9, "bold"),
            fg_color=LIVE_RED,
            corner_radius=RADIUS_SM,
            text_color="white",
            height=18,
            padx=5,
        )
        live_badge.grid(row=0, column=0, sticky="w", pady=1)

        uptime_text = format_uptime(started_at) if started_at else ""
        self._uptime_label = ctk.CTkLabel(
            badge_row,
            text=uptime_text,
            font=(FONT_SYSTEM, 10),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self._uptime_label.grid(row=0, column=1, sticky="w", padx=(6, 0))

        self._viewers_label = ctk.CTkLabel(
            badge_row,
            text=f"{format_viewers(viewers)} viewers",
            font=(FONT_SYSTEM, 11),
            text_color=TEXT_SECONDARY,
            anchor="e",
        )
        self._viewers_label.grid(row=0, column=2, sticky="e", padx=(6, 0))

        self._trend_label = ctk.CTkLabel(
            badge_row, text="", font=(FONT_SYSTEM, 9), width=14, text_color=TEXT_MUTED
        )
        self._trend_label.grid(row=0, column=3, sticky="e", padx=(2, 4))

        # Channel name
        name_label = ctk.CTkLabel(
            info,
            text=channel,
            font=(FONT_SYSTEM, 14, "bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        name_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Stream title (max 2 lines via wraplength)
        display_title = title[:120] if title else ""
        self._title_label = ctk.CTkLabel(
            info,
            text=display_title,
            font=(FONT_SYSTEM, 11),
            text_color=TEXT_SECONDARY,
            anchor="w",
            wraplength=200,
            justify="left",
        )
        self._title_label.grid(row=2, column=0, sticky="w", pady=(1, 0))

        # Tooltip for long titles
        self._title_tooltip: Tooltip | None = None
        if len(title) > 60:
            self._title_tooltip = Tooltip(self._title_label, title)

        # Game
        display_game = game or "Unknown"
        if len(display_game) > 28:
            display_game = display_game[:28] + "\u2026"
        self._game_label = ctk.CTkLabel(
            info,
            text=display_game,
            font=(FONT_SYSTEM, 11, "bold"),
            text_color=ACCENT,
            anchor="w",
        )
        self._game_label.grid(row=3, column=0, sticky="w")

        # "WATCHING" overlay (hidden by default)
        self._watching_label = ctk.CTkLabel(
            self._thumb_label,
            text=" \u25b6 WATCHING ",
            font=(FONT_SYSTEM, 9, "bold"),
            fg_color=LIVE_GREEN,
            corner_radius=4,
            text_color="white",
            height=16,
        )
        self._watching = False

        # Bind clicks on all children
        clickable = [
            self,
            self._thumb_label,
            info,
            badge_row,
            live_badge,
            self._viewers_label,
            name_label,
            self._title_label,
            self._game_label,
            self._uptime_label,
        ]
        for w in clickable:
            if on_click:
                w.bind("<Button-1>", lambda e, lg=login: on_click(lg))
            if on_double_click:
                w.bind("<Double-Button-1>", lambda e, lg=login: on_double_click(lg))

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
            label="\u25b6 Watch",
            command=lambda: on_double_click(login) if on_double_click else None,
        )
        self._menu.add_separator()
        self._menu.add_command(
            label="Open in Browser",
            command=lambda: webbrowser.open(f"https://twitch.tv/{login}"),
        )
        self._menu.add_command(
            label="Copy URL",
            command=lambda: self._copy_url(login),
        )
        if on_add_favorite:
            self._menu.add_separator()
            self._menu.add_command(
                label="\u2606 Add to favorites",
                command=lambda: on_add_favorite(login),
            )
        for w in clickable:
            w.bind("<Button-2>", self._show_menu)
            w.bind("<Control-Button-1>", self._show_menu)

    def _show_menu(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._menu.post(event.x_root, event.y_root)

    def _copy_url(self, login: str) -> None:
        url = f"https://twitch.tv/{login}"
        self.clipboard_clear()
        self.clipboard_append(url)

    # ── In-place update methods (no widget rebuild) ──────────────

    def update_viewers(self, count: int) -> None:
        self._viewers_label.configure(text=f"{format_viewers(count)} viewers")
        if self._prev_viewers is not None:
            if count > self._prev_viewers:
                self._trend_label.configure(text="\u25b2", text_color=LIVE_GREEN)
            elif count < self._prev_viewers:
                self._trend_label.configure(text="\u25bc", text_color="#FF6B6B")
            else:
                self._trend_label.configure(text="")
        self._prev_viewers = count

    def update_thumbnail(self, image: ctk.CTkImage) -> None:
        self._stop_shimmer()
        self._thumb_label.configure(image=image, text="", fg_color="transparent")

    def _start_shimmer(self) -> None:
        self._shimmer_bright = False
        self._shimmer_tick()

    def _shimmer_tick(self) -> None:
        self._shimmer_bright = not self._shimmer_bright
        color = BG_OVERLAY if self._shimmer_bright else BG_ELEVATED
        self._thumb_label.configure(fg_color=color)
        self._shimmer_job = self.after(600, self._shimmer_tick)

    def _stop_shimmer(self) -> None:
        if self._shimmer_job:
            self.after_cancel(self._shimmer_job)
            self._shimmer_job = None

    def update_game(self, name: str) -> None:
        display = name or "Unknown"
        if len(display) > 28:
            display = display[:28] + "\u2026"
        self._game_label.configure(text=display)

    def update_title(self, title: str) -> None:
        self._title_label.configure(text=(title[:120] if title else ""))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.configure(border_width=2, border_color=ACCENT)
        else:
            self.configure(border_width=1, border_color=BG_BORDER)

    def _on_enter(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._selected:
            self.configure(fg_color=BG_OVERLAY, border_color=ACCENT)

    def _on_leave(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._selected:
            self.configure(fg_color=BG_ELEVATED, border_color=BG_BORDER)

    def set_watching(self, active: bool) -> None:
        if active and not self._watching:
            self._watching_label.place(relx=1.0, x=-6, y=6, anchor="ne")
            self._watching = True
        elif not active and self._watching:
            self._watching_label.place_forget()
            self._watching = False

    def tick(self) -> None:
        if self._started_at:
            self._uptime_label.configure(text=format_uptime(self._started_at))


class StreamGrid(ctk.CTkScrollableFrame):
    def __init__(
        self,
        master: Any,
        on_stream_click: Callable[[str], None] | None = None,
        on_stream_double_click: Callable[[str], None] | None = None,
        on_add_favorite: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            fg_color=BG_BASE,
            scrollbar_button_color=BG_BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        self._on_stream_click = on_stream_click
        self._on_stream_double_click = on_stream_double_click
        self._on_add_favorite = on_add_favorite
        self._cards_by_login: dict[str, StreamCard] = {}
        self._selected_login: str | None = None
        self._empty_label: ctk.CTkLabel | None = None
        self._empty_subtitle: ctk.CTkLabel | None = None
        self._loading_label: ctk.CTkLabel | None = None
        self._onboarding_frame: ctk.CTkFrame | None = None
        self._no_results_label: ctk.CTkLabel | None = None
        self._tick_job: str | None = None

        # Sort/filter state + stored data for re-render
        self._sort_key: str = SORT_MOST_VIEWERS
        self._filter_text: str = ""
        self._last_streams: list[dict[str, Any]] = []
        self._last_thumbnails: dict[str, ctk.CTkImage] = {}
        self._last_games: dict[str, str] = {}

        self.grid_columnconfigure((0, 1, 2), weight=1)
        self._show_loading()
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        self._tick_all_cards()
        self._tick_job = self.after(60_000, self._schedule_tick)

    def _tick_all_cards(self) -> None:
        for card in self._cards_by_login.values():
            card.tick()

    def _clear(self) -> None:
        for card in self._cards_by_login.values():
            card.destroy()
        self._cards_by_login.clear()
        if self._empty_label:
            self._empty_label.destroy()
            self._empty_label = None
        if self._empty_subtitle:
            self._empty_subtitle.destroy()
            self._empty_subtitle = None
        if self._loading_label:
            self._loading_label.destroy()
            self._loading_label = None
        if self._onboarding_frame:
            self._onboarding_frame.destroy()
            self._onboarding_frame = None
        if self._no_results_label:
            self._no_results_label.destroy()
            self._no_results_label = None

    def _show_loading(self) -> None:
        self._clear()
        self._loading_label = ctk.CTkLabel(
            self,
            text="Loading streams...",
            font=(FONT_SYSTEM, 16),
            text_color=TEXT_MUTED,
        )
        self._loading_label.grid(row=0, column=0, columnspan=COLUMNS, pady=80)

    def _show_empty(self) -> None:
        self._clear()
        self._empty_label = ctk.CTkLabel(
            self,
            text="All quiet right now",
            font=(FONT_SYSTEM, 16),
            text_color=TEXT_SECONDARY,
        )
        self._empty_label.grid(row=0, column=0, columnspan=COLUMNS, pady=(80, 4))
        self._empty_subtitle = ctk.CTkLabel(
            self,
            text="None of your followed channels are live",
            font=(FONT_SYSTEM, 12),
            text_color=TEXT_MUTED,
        )
        self._empty_subtitle.grid(row=1, column=0, columnspan=COLUMNS, pady=(0, 40))

    def show_onboarding(
        self,
        on_open_settings: Callable[[], None],
        has_credentials: bool = False,
    ) -> None:
        self._clear()
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, columnspan=COLUMNS, pady=40)
        self._onboarding_frame = frame

        if has_credentials:
            # "No favorites" state
            ctk.CTkLabel(
                frame, text="\U0001f4fa", font=(FONT_SYSTEM, 40), text_color=ACCENT
            ).pack(pady=(0, 12))
            ctk.CTkLabel(
                frame,
                text="No favorites yet",
                font=(FONT_SYSTEM, 20, "bold"),
                text_color=TEXT_PRIMARY,
            ).pack(pady=(0, 8))
            ctk.CTkLabel(
                frame,
                text="Search for channels in the sidebar to add them here",
                font=(FONT_SYSTEM, 13),
                text_color=TEXT_MUTED,
            ).pack()
            return

        # Icon
        ctk.CTkLabel(
            frame, text="\u26a1", font=(FONT_SYSTEM, 40), text_color=ACCENT
        ).pack(pady=(0, 12))

        ctk.CTkLabel(
            frame,
            text="Welcome to TwitchX",
            font=(FONT_SYSTEM, 20, "bold"),
            text_color=TEXT_PRIMARY,
        ).pack(pady=(0, 20))

        steps = [
            ("1.", "Get your Twitch API credentials at dev.twitch.tv/console"),
            ("2.", "Create a new application \u2192 copy Client ID and Client Secret"),
            ("3.", "Paste them in Settings (\u2699 button below)"),
        ]
        for num, text in steps:
            row_f = ctk.CTkFrame(
                frame,
                fg_color=BG_ELEVATED,
                corner_radius=RADIUS_MD,
            )
            row_f.pack(anchor="w", padx=40, pady=4, fill="x")
            ctk.CTkLabel(
                row_f,
                text=num,
                font=(FONT_SYSTEM, 14, "bold"),
                text_color=ACCENT,
                width=24,
            ).pack(side="left", padx=(16, 8), pady=8)
            ctk.CTkLabel(
                row_f,
                text=text,
                font=(FONT_SYSTEM, 13),
                text_color=TEXT_SECONDARY,
                anchor="w",
            ).pack(side="left", padx=(0, 16), pady=8)

        ctk.CTkButton(
            frame,
            text="Open Settings",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=on_open_settings,
            width=140,
            height=36,
            corner_radius=RADIUS_MD,
            font=(FONT_SYSTEM, 13, "bold"),
        ).pack(pady=(24, 0))

    # ── Sort / Filter ────────────────────────────────────────────

    def set_sort_key(self, key: str) -> None:
        if key != self._sort_key:
            self._sort_key = key
            self._rerender()

    def set_filter_text(self, text: str) -> None:
        text = text.strip().lower()
        if text != self._filter_text:
            self._filter_text = text
            self._rerender()

    def _apply_sort_filter(self, streams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = streams
        if self._filter_text:
            filtered = [
                s
                for s in streams
                if self._filter_text in (s.get("game_name") or "").lower()
            ]
        if self._sort_key == SORT_MOST_VIEWERS:
            filtered.sort(key=lambda s: s.get("viewer_count", 0), reverse=True)
        elif self._sort_key == SORT_RECENT:
            filtered.sort(key=lambda s: s.get("started_at", ""), reverse=True)
        elif self._sort_key == SORT_ALPHA:
            filtered.sort(key=lambda s: (s.get("user_name") or "").lower())
        return filtered

    def _rerender(self) -> None:
        """Re-render using last stored data with current sort/filter."""
        if not self._last_streams:
            return
        visible = self._apply_sort_filter(self._last_streams)
        if not visible:
            self._clear()
            query = self._filter_text
            self._no_results_label = ctk.CTkLabel(
                self,
                text=f"No results for \u2018{query}\u2019",
                font=(FONT_SYSTEM, 16),
                text_color=TEXT_MUTED,
            )
            self._no_results_label.grid(row=0, column=0, columnspan=COLUMNS, pady=80)
            return
        self._full_rebuild(visible, self._last_thumbnails, self._last_games)
        if self._selected_login and self._selected_login in self._cards_by_login:
            self._cards_by_login[self._selected_login].set_selected(True)

    # ── Main update ──────────────────────────────────────────────

    def update_streams(
        self,
        streams: list[dict[str, Any]],
        thumbnails: dict[str, ctk.CTkImage],
        games: dict[str, str],
    ) -> None:
        # Store for re-render on sort/filter change
        self._last_streams = list(streams)
        self._last_thumbnails = thumbnails
        self._last_games = games

        if not streams:
            self._show_empty()
            return

        # Clear loading/empty/onboarding if present
        if self._loading_label:
            self._loading_label.destroy()
            self._loading_label = None
        if self._empty_label:
            self._empty_label.destroy()
            self._empty_label = None
        if self._empty_subtitle:
            self._empty_subtitle.destroy()
            self._empty_subtitle = None
        if self._onboarding_frame:
            self._onboarding_frame.destroy()
            self._onboarding_frame = None
        if self._no_results_label:
            self._no_results_label.destroy()
            self._no_results_label = None

        visible = self._apply_sort_filter(streams)
        if not visible:
            self._clear()
            query = self._filter_text
            self._no_results_label = ctk.CTkLabel(
                self,
                text=f"No results for \u2018{query}\u2019",
                font=(FONT_SYSTEM, 16),
                text_color=TEXT_MUTED,
            )
            self._no_results_label.grid(row=0, column=0, columnspan=COLUMNS, pady=80)
            return

        incoming_logins = {s.get("user_login", "").lower() for s in visible}
        existing_logins = set(self._cards_by_login)

        if incoming_logins == existing_logins and self._cards_by_login:
            # Same set of channels — update in-place (no flicker)
            for stream in visible:
                login = stream.get("user_login", "").lower()
                card = self._cards_by_login.get(login)
                if not card:
                    continue
                card.update_viewers(stream.get("viewer_count", 0))
                game_id = stream.get("game_id", "")
                game_name = stream.get("game_name", "") or games.get(game_id, "")
                card.update_game(game_name)
                card.update_title(stream.get("title", ""))
                thumb = thumbnails.get(login)
                if thumb:
                    card.update_thumbnail(thumb)
        else:
            # Channel set changed — full rebuild
            self._full_rebuild(visible, thumbnails, games)

        # Restore selection highlight
        if self._selected_login and self._selected_login in self._cards_by_login:
            self._cards_by_login[self._selected_login].set_selected(True)

    def _full_rebuild(
        self,
        streams: list[dict[str, Any]],
        thumbnails: dict[str, ctk.CTkImage],
        games: dict[str, str],
    ) -> None:
        self._clear()

        for idx, stream in enumerate(streams):
            login = stream.get("user_login", "").lower()
            display_name = stream.get("user_name", login)
            game_id = stream.get("game_id", "")
            game_name = stream.get("game_name", "") or games.get(game_id, "")
            viewers = stream.get("viewer_count", 0)
            title = stream.get("title", "")
            started_at = stream.get("started_at", "")
            thumb = thumbnails.get(login)

            card = StreamCard(
                self,
                login=login,
                channel=display_name,
                title=title,
                game=game_name,
                viewers=viewers,
                started_at=started_at,
                thumbnail=thumb,
                on_click=self._on_stream_click,
                on_double_click=self._on_stream_double_click,
                on_add_favorite=self._on_add_favorite,
            )
            row = idx // COLUMNS
            col = idx % COLUMNS
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            self._cards_by_login[login] = card

    def update_thumbnail(self, login: str, image: ctk.CTkImage) -> None:
        card = self._cards_by_login.get(login)
        if card:
            card.update_thumbnail(image)

    def set_selected(self, login: str | None) -> None:
        if self._selected_login and self._selected_login in self._cards_by_login:
            self._cards_by_login[self._selected_login].set_selected(False)
        self._selected_login = login
        if login and login in self._cards_by_login:
            self._cards_by_login[login].set_selected(True)

    def set_watching(self, login: str | None) -> None:
        for card_login, card in self._cards_by_login.items():
            card.set_watching(card_login == login)

    def destroy(self) -> None:
        if self._tick_job:
            self.after_cancel(self._tick_job)
        super().destroy()
