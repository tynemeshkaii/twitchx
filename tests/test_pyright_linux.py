"""Filter rules of tools/pyright_linux.py (used by `make check-linux`)."""

from __future__ import annotations

import pytest

from tools.pyright_linux import blocking_errors, is_allowed


def _missing(module: str, rule: str = "reportMissingImports") -> dict:
    return {
        "severity": "error",
        "rule": rule,
        "message": f'Import "{module}" could not be resolved',
    }


@pytest.mark.parametrize(
    "module",
    [
        "AppKit",
        "Foundation",
        "PyObjCTools",
        "PyObjCTools.AppHelper",
        "objc",
        "webview.platforms.cocoa",
    ],
)
def test_macos_only_imports_are_allowed(module: str) -> None:
    assert is_allowed(_missing(module))


@pytest.mark.parametrize(
    "module", ["httpx", "AVKit", "AppKitty", "webview", "webview.platforms"]
)
def test_other_missing_imports_block(module: str) -> None:
    assert not is_allowed(_missing(module))


def test_other_rules_block_even_for_macos_modules() -> None:
    assert not is_allowed(_missing("AppKit", rule="reportAttributeAccessIssue"))


def test_blocking_errors_ignores_warnings_and_allowed() -> None:
    report = {
        "generalDiagnostics": [
            _missing("AppKit"),
            {**_missing("httpx"), "severity": "warning"},
            {"severity": "error", "rule": "reportArgumentType", "message": "bad arg"},
        ]
    }
    errors = blocking_errors(report)
    assert [e["rule"] for e in errors] == ["reportArgumentType"]
