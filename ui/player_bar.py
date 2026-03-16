from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from core.launcher import QUALITIES
from core.utils import format_viewers
from ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BG_BORDER,
    BG_ELEVATED,
    BG_OVERLAY,
    BG_SURFACE,
    FONT_SYSTEM,
    LIVE_RED,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_SECONDARY,
)


class PlayerBar(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        on_watch: Callable[[str], None] | None = None,
        on_open_browser: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_refresh: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, height=48, corner_radius=0, fg_color=BG_SURFACE)
        self._on_watch = on_watch
        self.grid_columnconfigure(4, weight=1)
        self.grid_propagate(False)
        self._pulse_job: str | None = None
        self._pulse_bright = False

        # Quality selector
        self._quality_var = ctk.StringVar(value="best")
        self._quality_menu = ctk.CTkOptionMenu(
            self,
            variable=self._quality_var,
            values=QUALITIES,
            width=130,
            height=32,
            fg_color=BG_ELEVATED,
            button_color=BG_BORDER,
            button_hover_color=ACCENT,
            corner_radius=RADIUS_MD,
        )
        self._quality_menu.grid(row=0, column=0, padx=(12, 6), pady=8)

        # Watch button
        self._watch_btn = ctk.CTkButton(
            self,
            text="\u25b6  Watch",
            width=90,
            height=32,
            fg_color=BG_ELEVATED,
            hover_color=BG_OVERLAY,
            text_color=TEXT_MUTED,
            font=(FONT_SYSTEM, 13, "bold"),
            corner_radius=RADIUS_MD,
            command=self._on_watch_pressed,
        )
        self._watch_btn.grid(row=0, column=1, padx=4, pady=8)

        # Open in Browser button
        self._browser_btn = ctk.CTkButton(
            self,
            text="\U0001f310",
            width=32,
            height=32,
            fg_color=BG_ELEVATED,
            hover_color=BG_OVERLAY,
            border_width=1,
            border_color=BG_BORDER,
            corner_radius=RADIUS_SM,
            command=on_open_browser,
        )
        self._browser_btn.grid(row=0, column=2, padx=(0, 4), pady=8)

        # Live pulse dot (hidden by default)
        self._live_dot = ctk.CTkLabel(
            self, text="\u25cf", font=(FONT_SYSTEM, 12), text_color=BG_SURFACE, width=14
        )
        self._live_dot.grid(row=0, column=3, padx=(0, 2), pady=8)

        # Status label (spacer)
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=(FONT_SYSTEM, 12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self._status_label.grid(row=0, column=4, sticky="ew", padx=12, pady=8)

        # Total viewers
        self._total_label = ctk.CTkLabel(
            self,
            text="",
            font=(FONT_SYSTEM, 10),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self._total_label.grid(row=0, column=5, padx=(4, 4), pady=8)

        # Last updated
        self._updated_label = ctk.CTkLabel(
            self,
            text="",
            font=(FONT_SYSTEM, 10),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self._updated_label.grid(row=0, column=6, padx=(4, 4), pady=8)

        # Refresh button
        self._refresh_btn = ctk.CTkButton(
            self,
            text="\u21bb",
            width=32,
            height=32,
            fg_color=BG_ELEVATED,
            hover_color=BG_OVERLAY,
            border_width=1,
            border_color=BG_BORDER,
            corner_radius=RADIUS_SM,
            command=on_refresh,
        )
        self._refresh_btn.grid(row=0, column=7, padx=(0, 4), pady=8)

        # Settings button
        self._settings_btn = ctk.CTkButton(
            self,
            text="\u2699",
            width=32,
            height=32,
            fg_color=BG_ELEVATED,
            hover_color=BG_OVERLAY,
            border_width=1,
            border_color=BG_BORDER,
            corner_radius=RADIUS_SM,
            command=on_settings,
        )
        self._settings_btn.grid(row=0, column=8, padx=(0, 12), pady=8)

    def _on_watch_pressed(self) -> None:
        if self._on_watch:
            self._on_watch(self._quality_var.get())

    def set_quality(self, quality: str) -> None:
        self._quality_var.set(quality)

    def get_quality(self) -> str:
        return self._quality_var.get()

    def set_status(self, text: str, color: str = TEXT_SECONDARY) -> None:
        self._status_label.configure(text=text, text_color=color)

    def set_updated(self, text: str) -> None:
        self._updated_label.configure(text=text)

    def set_stale(self, stale: bool) -> None:
        self._updated_label.configure(text_color="#FF6B6B" if stale else TEXT_MUTED)

    def set_total_viewers(self, count: int) -> None:
        if count > 0:
            self._total_label.configure(
                text=f"\U0001f465 {format_viewers(count)} total"
            )
        else:
            self._total_label.configure(text="")

    def set_watching(self, active: bool) -> None:
        if active:
            self._pulse_bright = False
            self._pulse_tick()
        else:
            if self._pulse_job:
                self.after_cancel(self._pulse_job)
                self._pulse_job = None
            self._live_dot.configure(text_color=BG_SURFACE)

    def _pulse_tick(self) -> None:
        self._pulse_bright = not self._pulse_bright
        color = "#FF6B6B" if self._pulse_bright else LIVE_RED
        self._live_dot.configure(text_color=color)
        self._pulse_job = self.after(800, self._pulse_tick)

    def set_channel_selected(self, selected: bool) -> None:
        if selected:
            self._watch_btn.configure(
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                text_color="white",
            )
        else:
            self._watch_btn.configure(
                fg_color=BG_ELEVATED,
                hover_color=BG_OVERLAY,
                text_color=TEXT_MUTED,
            )
