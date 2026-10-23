"""Every icon name used by the UI must exist in ICONS (ui/js/icons.js).

renderIcon() falls back to a placeholder circle for unknown names, so a
missing icon never fails loudly: it just draws a dot in a menu.

Only string literals are checked. Names that reach the helpers through
variables are skipped; at the time of writing those are:
  - palette.js   setIconOnly(iconEl, icon, …)       — `icon:` fields of the command list
  - render.js    EMPTY_STATE_ICONS[config.illustration] (the `|| 'info'` fallback is checked)
  - init.js      iconMap[saved], DENSITY_ICONS[next] — density toggle maps
  - icons.js     renderIcon(name, size) inside mountIcons / TwitchX.icon
  - utils.js     makeIcon(name, …) inside setIconText / setIconOnly
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).parent.parent / "ui"

# One argument: anything up to a top-level comma or closing paren, allowing one
# level of nested parentheses (e.g. `document.getElementById('x')`).
_ARG = r"(?:[^,()]|\([^()]*\))*"
_LITERAL = re.compile(r"""'([^']*)'|"([^"]*)\"""")


def _icon_names() -> set[str]:
    source = (UI / "js" / "icons.js").read_text(encoding="utf-8")
    body = re.search(r"\bICONS\s*=\s*\{(.*?)\n\};", source, re.S)
    assert body, "ICONS object not found in icons.js"
    keys = re.findall(
        r"""^\s*(?:'([\w-]+)'|"([\w-]+)"|([A-Za-z_$][\w$]*))\s*:""",
        body.group(1),
        re.M,
    )
    return {next(k for k in groups if k) for groups in keys}


def _literals(expr: str) -> set[str]:
    return {a or b for a, b in _LITERAL.findall(expr)}


def _used_names() -> dict[str, set[str]]:
    """icon name → set of places that use it."""
    used: dict[str, set[str]] = {}

    def add(name: str, where: str) -> None:
        used.setdefault(name, set()).add(where)

    html = (UI / "index.html").read_text(encoding="utf-8")
    for name in re.findall(r'data-icon="([^"]*)"', html):
        add(name, "index.html data-icon")

    second_arg = re.compile(rf"\b(setIconOnly|setIconText)\(\s*{_ARG},\s*({_ARG})")
    first_arg = re.compile(rf"\brenderIcon\(\s*({_ARG})")
    for path in sorted((UI / "js").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for fn, arg in second_arg.findall(source):
            for name in _literals(arg):
                add(name, f"{path.name} {fn}")
        for arg in first_arg.findall(source):
            for name in _literals(arg):
                add(name, f"{path.name} renderIcon")
    return used


def test_parsers_find_icons_and_usages() -> None:
    # Guards against a regex silently matching nothing.
    assert len(_icon_names()) > 40
    used = _used_names()
    assert "close" in used and "pin" in used and "check" in used


def test_every_used_icon_exists() -> None:
    icons = _icon_names()
    missing = {
        name: sorted(where)
        for name, where in _used_names().items()
        if name not in icons
    }
    assert not missing, "icons used but not defined in ui/js/icons.js:\n" + "\n".join(
        f"  {name}: {', '.join(where)}" for name, where in sorted(missing.items())
    )
