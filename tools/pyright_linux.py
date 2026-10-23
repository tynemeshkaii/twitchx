"""Run pyright on Linux, tolerating only the macOS-only imports.

On Linux the pyobjc frameworks cannot be installed, so pyright reports
``reportMissingImports`` for the modules listed in ``MACOS_ONLY_MODULES``.
Those errors are expected and filtered out; every other error fails the run.

Usage (see ``make check-linux``):
    python tools/pyright_linux.py [extra pyright args]

pyright must be installed in the same environment.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any

MACOS_ONLY_MODULES = (
    "AppKit",
    "Foundation",
    "PyObjCTools",
    "objc",
    "webview.platforms.cocoa",
)

_IMPORT_RE = re.compile(r'Import "([^"]+)" could not be resolved')


def is_allowed(diagnostic: dict[str, Any]) -> bool:
    """True for a missing-import error of a macOS-only module."""
    if diagnostic.get("rule") != "reportMissingImports":
        return False
    match = _IMPORT_RE.search(diagnostic.get("message", ""))
    if not match:
        return False
    module = match.group(1)
    return any(
        module == allowed or module.startswith(allowed + ".")
        for allowed in MACOS_ONLY_MODULES
    )


def blocking_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Errors from a ``pyright --outputjson`` report that are not allowed."""
    return [
        d
        for d in report.get("generalDiagnostics", [])
        if d.get("severity") == "error" and not is_allowed(d)
    ]


def _format(d: dict[str, Any]) -> str:
    start = d.get("range", {}).get("start", {})
    line = start.get("line", 0) + 1
    col = start.get("character", 0) + 1
    rule = f" ({d['rule']})" if d.get("rule") else ""
    return f"{d.get('file', '?')}:{line}:{col} - error: {d.get('message', '')}{rule}"


def main(argv: list[str]) -> int:
    proc = subprocess.run(
        ["pyright", "--outputjson", *argv], capture_output=True, text=True
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(proc.stdout + proc.stderr)
        return proc.returncode or 1

    diagnostics = report.get("generalDiagnostics", [])
    errors = blocking_errors(report)
    allowed = sum(
        1 for d in diagnostics if d.get("severity") == "error" and is_allowed(d)
    )
    for d in errors:
        print(_format(d))
    print(
        f"pyright: {len(errors)} blocking error(s), "
        f"{allowed} allowed macOS-only import error(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
