from __future__ import annotations

import contextlib
import tkinter as tk
from typing import Any

from ui.theme import ACCENT, BG_ELEVATED, FONT_SYSTEM, TEXT_PRIMARY

_TEXT_INPUT_CLASSES = {"Entry", "TEntry", "Text", "CTkEntry", "CTkTextbox"}


def format_viewers(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(count)


def is_text_input_widget(widget: Any) -> bool:
    if widget is None:
        return False
    winfo_class = getattr(widget, "winfo_class", None)
    if callable(winfo_class):
        try:
            if str(winfo_class()) in _TEXT_INPUT_CLASSES:
                return True
        except Exception:
            pass
    if type(widget).__name__ in _TEXT_INPUT_CLASSES:
        return True
    return callable(getattr(widget, "insert", None)) and callable(
        getattr(widget, "get", None)
    )


def _clipboard_text(widget: Any) -> str:
    getters = [getattr(widget, "clipboard_get", None)]
    winfo_toplevel = getattr(widget, "winfo_toplevel", None)
    if callable(winfo_toplevel):
        with_top = winfo_toplevel()
        getters.append(getattr(with_top, "clipboard_get", None))
    for getter in getters:
        if not callable(getter):
            continue
        try:
            return str(getter())
        except (tk.TclError, Exception):
            continue
    return ""


def paste_text_input(widget: Any) -> str:
    text = _clipboard_text(widget)
    if not text:
        return "break"
    delete = getattr(widget, "delete", None)
    index = getattr(widget, "index", None)
    selection_present = getattr(widget, "selection_present", None)
    if (
        callable(delete)
        and callable(index)
        and callable(selection_present)
        and selection_present()
    ):
        with contextlib.suppress(Exception):
            delete(index("sel.first"), index("sel.last"))
    insert = getattr(widget, "insert", None)
    if not callable(insert):
        return "break"
    insert_at: Any = "end"
    if callable(index):
        with contextlib.suppress(Exception):
            insert_at = index("insert")
    try:
        insert(insert_at, text)
    except Exception:
        with contextlib.suppress(Exception):
            insert("end", text)
    return "break"


def select_all_text_input(widget: Any) -> str:
    focus_set = getattr(widget, "focus_set", None)
    if callable(focus_set):
        with contextlib.suppress(Exception):
            focus_set()
    select_range = getattr(widget, "select_range", None)
    if callable(select_range):
        with contextlib.suppress(Exception):
            select_range(0, "end")
    event_generate = getattr(widget, "event_generate", None)
    if callable(event_generate):
        with contextlib.suppress(Exception):
            event_generate("<<SelectAll>>")
    icursor = getattr(widget, "icursor", None)
    if callable(icursor):
        with contextlib.suppress(Exception):
            icursor("end")
    return "break"


def bind_standard_text_shortcuts(widget: Any) -> None:
    bind = getattr(widget, "bind", None)
    if not callable(bind):
        return
    for sequence in ("<Command-v>", "<Control-v>", "<<Paste>>"):
        bind(
            sequence,
            lambda event, target=widget: paste_text_input(target),
            add="+",
        )
    for sequence in ("<Command-a>", "<Control-a>"):
        bind(
            sequence,
            lambda event, target=widget: select_all_text_input(target),
            add="+",
        )


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
