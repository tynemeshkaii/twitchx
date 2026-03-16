from __future__ import annotations

import tkinter as tk
from typing import Any

from ui.theme import ACCENT, BG_ELEVATED, FONT_SYSTEM, TEXT_PRIMARY


def format_viewers(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


class Tooltip:
    """Lightweight hover tooltip using an undecorated Toplevel."""

    def __init__(
        self,
        widget: Any,
        text: str,
        delay: int = 600,
        wraplength: int = 320,
    ) -> None:
        self._widget = widget
        self._text = text
        self._delay = delay
        self._wraplength = wraplength
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._after_id = self._widget.after(self._delay, self._show)

    def _on_leave(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self) -> None:
        self._after_id = None
        self._hide()
        x = self._widget.winfo_rootx() + 10
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        tip = tk.Toplevel(self._widget)
        tip.overrideredirect(True)
        tip.geometry(f"+{x}+{y}")
        tip.configure(bg=ACCENT)
        label = tk.Label(
            tip,
            text=self._text,
            bg=BG_ELEVATED,
            fg=TEXT_PRIMARY,
            font=(FONT_SYSTEM, 11),
            wraplength=self._wraplength,
            justify="left",
            padx=6,
            pady=6,
        )
        label.pack(padx=1, pady=1)
        self._tip = tip

    def _hide(self) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None
