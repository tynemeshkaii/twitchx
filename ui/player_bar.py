from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from core.launcher import QUALITIES
from core.utils import format_viewers

ACCENT = "#9146FF"


class PlayerBar(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        on_watch: Callable[[str], None] | None = None,
        on_open_browser: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_refresh: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, height=44, corner_radius=0, fg_color="#16162a")
        self._on_watch = on_watch
        self.grid_columnconfigure(3, weight=1)
        self.grid_propagate(False)

        # Quality selector
        self._quality_var = ctk.StringVar(value="best")
        self._quality_menu = ctk.CTkOptionMenu(
            self,
            variable=self._quality_var,
            values=QUALITIES,
            width=130,
            height=30,
            fg_color="#2a2a3e",
            button_color=ACCENT,
            button_hover_color="#7B38D8",
        )
        self._quality_menu.grid(row=0, column=0, padx=(12, 6), pady=7)

        # Watch button
        self._watch_btn = ctk.CTkButton(
            self,
            text="\u25b6  Watch",
            width=90,
            height=30,
            fg_color=ACCENT,
            hover_color="#7B38D8",
            command=self._on_watch_pressed,
        )
        self._watch_btn.grid(row=0, column=1, padx=4, pady=7)

        # Open in Browser button
        self._browser_btn = ctk.CTkButton(
            self,
            text="\U0001f310",
            width=30,
            height=30,
            fg_color="#2a2a3e",
            hover_color="#3a3a4e",
            command=on_open_browser,
        )
        self._browser_btn.grid(row=0, column=2, padx=(0, 4), pady=7)

        # Status label (spacer)
        self._status_label = ctk.CTkLabel(
            self,
            text="",
            font=("", 11),
            text_color="#888888",
            anchor="w",
        )
        self._status_label.grid(row=0, column=3, sticky="ew", padx=12, pady=7)

        # Total viewers
        self._total_label = ctk.CTkLabel(
            self,
            text="",
            font=("", 10),
            text_color="#777777",
            anchor="e",
        )
        self._total_label.grid(row=0, column=4, padx=(4, 4), pady=7)

        # Last updated
        self._updated_label = ctk.CTkLabel(
            self,
            text="",
            font=("", 10),
            text_color="#555555",
            anchor="e",
        )
        self._updated_label.grid(row=0, column=5, padx=(4, 4), pady=7)

        # Refresh button
        self._refresh_btn = ctk.CTkButton(
            self,
            text="\u21bb",
            width=30,
            height=30,
            fg_color="#2a2a3e",
            hover_color="#3a3a4e",
            command=on_refresh,
        )
        self._refresh_btn.grid(row=0, column=6, padx=(0, 4), pady=7)

        # Settings button
        self._settings_btn = ctk.CTkButton(
            self,
            text="\u2699",
            width=30,
            height=30,
            fg_color="#2a2a3e",
            hover_color="#3a3a4e",
            command=on_settings,
        )
        self._settings_btn.grid(row=0, column=7, padx=(0, 12), pady=7)

    def _on_watch_pressed(self) -> None:
        if self._on_watch:
            self._on_watch(self._quality_var.get())

    def set_quality(self, quality: str) -> None:
        self._quality_var.set(quality)

    def get_quality(self) -> str:
        return self._quality_var.get()

    def set_status(self, text: str, color: str = "#888888") -> None:
        self._status_label.configure(text=text, text_color=color)

    def set_updated(self, text: str) -> None:
        self._updated_label.configure(text=text)

    def set_stale(self, stale: bool) -> None:
        self._updated_label.configure(text_color="#FF6B6B" if stale else "#555555")

    def set_total_viewers(self, count: int) -> None:
        if count > 0:
            self._total_label.configure(
                text=f"\U0001f465 {format_viewers(count)} total"
            )
        else:
            self._total_label.configure(text="")
