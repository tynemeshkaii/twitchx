"""The JS modules are flat scripts merged into ONE inline <script> block.

Every top-level name is therefore global across all modules: a duplicate
``const``/``function`` in two files is a SyntaxError (or a silent override)
that breaks the whole UI, and no Python test would otherwise notice.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from app import TwitchXApp

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
JS_DIR = UI_DIR / "js"

_TOP_LEVEL_DECL = re.compile(
    r"^(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"
    r"|^(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def _bundle_js() -> str:
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    inlined = TwitchXApp._inline_resources(html, UI_DIR)
    end = inlined.rfind("\n</script>\n</body>")
    assert end != -1, "merged <script> block not found before </body>"
    start = inlined.rfind("<script>\n", 0, end) + len("<script>\n")
    return inlined[start:end]


def test_index_loads_every_js_module() -> None:
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    referenced = set(re.findall(r'<script src="js/([^"]+)"></script>', html))
    on_disk = {p.name for p in JS_DIR.glob("*.js")}
    assert referenced == on_disk


def test_bundle_passes_node_syntax_check(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    bundle = tmp_path / "bundle.js"
    bundle.write_text(_bundle_js(), encoding="utf-8")
    result = subprocess.run(
        [node, "--check", str(bundle)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_no_duplicate_top_level_names_across_modules() -> None:
    owners: dict[str, set[str]] = defaultdict(set)
    for path in sorted(JS_DIR.glob("*.js")):
        for match in _TOP_LEVEL_DECL.finditer(path.read_text(encoding="utf-8")):
            name = match.group(1) or match.group(2)
            if name != "TwitchX":
                owners[name].add(path.name)
    duplicates = {n: sorted(f) for n, f in owners.items() if len(f) > 1}
    assert not duplicates, f"top-level names declared in several modules: {duplicates}"
