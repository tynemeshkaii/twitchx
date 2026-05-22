#!/usr/bin/env bash
set -euo pipefail

echo "==> Cleaning previous build"
rm -rf build/ dist/

echo "==> Building TwitchX.app"
uv run pyinstaller TwitchX.spec

echo "==> Done: dist/TwitchX.app"
echo ""
echo "Prerequisites (not bundled):"
echo "  brew install streamlink"
echo "  IINA (optional, for external playback): https://iina.io"
