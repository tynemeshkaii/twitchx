#!/usr/bin/env python3
"""Report CSS selectors that are defined in more than one stylesheet.

Every component-level selector must have exactly one owner file. Three
cross-cutting layers are exempt and must declare themselves with a
`/* css-layer: <name> */` comment:

    theme-tokens    :root in tokens.css + themes/*.css
    drag-regions    -webkit-app-region assignments in layout.css
    text-selection  the user-select allowlist in reset.css

At-rule blocks (@media / @supports) are exempt too: the accessibility
overrides in reset.css intentionally restate component selectors.

Usage:  uv run python tools/css_ownership.py [-v]
Exit code is the number of violations.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "ui" / "css"
INDEX = ROOT / "ui" / "index.html"
LAYER_RE = re.compile(r"/\*\s*css-layer:\s*([\w-]+)")


def stylesheet_order() -> list[str]:
    return re.findall(r'href="css/([^"]+)"', INDEX.read_text(encoding="utf-8"))


def iter_rules(text: str):
    """Yield (prelude, body, layer) for top-level rules; skip at-rule blocks."""
    i, n = 0, len(text)
    layer: str | None = None
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i)
            end = n if end == -1 else end + 2
            found = LAYER_RE.match(text[i:end])
            if found:
                layer = found.group(1)
            i = end
            continue
        brace = text.find("{", i)
        if brace == -1:
            return
        prelude = text[i:brace].strip()
        depth, k = 1, brace + 1
        while k < n and depth:
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
            k += 1
        if not prelude.startswith("@") and prelude:
            yield prelude, text[brace + 1 : k - 1], layer
            # A marker covers exactly the rule that follows it — otherwise the
            # exemption leaks to every remaining rule in the file.
            layer = None
        i = k


def collect() -> dict[str, set[tuple[str, str | None]]]:
    owners: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    for rel in stylesheet_order():
        path = CSS_DIR / rel
        if not path.exists():
            continue
        for prelude, _body, layer in iter_rules(path.read_text(encoding="utf-8")):
            for selector in prelude.split(","):
                selector = " ".join(selector.split())
                if selector:
                    owners[selector].add((rel, layer))
    return owners


def violations() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for selector, entries in collect().items():
        files = {rel for rel, _layer in entries}
        if len(files) < 2:
            continue
        # a selector may appear in several files only through a declared layer
        if any(layer for _rel, layer in entries):
            continue
        out[selector] = sorted(files)
    return out


def main() -> int:
    bad = violations()
    print(f"selectors without a single owner: {len(bad)}")
    if bad and "-q" not in sys.argv:
        for selector, files in sorted(bad.items()):
            print(f"  {selector:60} {files}")
    return len(bad)


if __name__ == "__main__":
    raise SystemExit(main())
