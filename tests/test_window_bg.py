"""Native window background follows the theme setting (app.window_background)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import WINDOW_BG_DARK, WINDOW_BG_LIGHT, window_background

THEMES = Path(__file__).parent.parent / "ui" / "css" / "themes"


@pytest.mark.parametrize("system_is_dark", [True, False])
def test_explicit_modes_ignore_system(system_is_dark: bool) -> None:
    assert window_background("dark", system_is_dark) == "#0F1012"
    assert window_background("light", system_is_dark) == "#FFFFFF"


def test_auto_follows_system() -> None:
    assert window_background("auto", True) == "#0F1012"
    assert window_background("auto", False) == "#FFFFFF"


@pytest.mark.parametrize("mode", ["", "hacker", "Dark", "LIGHT"])
@pytest.mark.parametrize("system_is_dark", [True, False])
def test_unknown_mode_falls_back_to_dark(mode: str, system_is_dark: bool) -> None:
    assert window_background(mode, system_is_dark) == "#0F1012"


@pytest.mark.parametrize(
    ("theme_file", "expected"),
    [("dark.css", WINDOW_BG_DARK), ("light.css", WINDOW_BG_LIGHT)],
)
def test_constants_match_theme_bg_base(theme_file: str, expected: str) -> None:
    css = (THEMES / theme_file).read_text(encoding="utf-8")
    match = re.search(r"--bg-base:\s*(#[0-9A-Fa-f]{6})", css)
    assert match, f"--bg-base not found in {theme_file}"
    assert match.group(1).upper() == expected.upper()
