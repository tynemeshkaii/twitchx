"""PATH augmentation for Finder-launched .app (homebrew CLI lookup)."""

from __future__ import annotations

import os

import pytest

import main


def test_augment_path_prepends_missing_homebrew_dirs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    main._augment_path()
    parts = os.environ["PATH"].split(os.pathsep)
    assert "/opt/homebrew/bin" in parts
    # Original entries preserved, homebrew dirs come first.
    assert parts.index("/opt/homebrew/bin") < parts.index("/usr/bin")


def test_augment_path_does_not_duplicate_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/opt/homebrew/bin:/usr/bin")
    main._augment_path()
    assert os.environ["PATH"].split(os.pathsep).count("/opt/homebrew/bin") == 1
