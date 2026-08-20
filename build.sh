#!/usr/bin/env bash
set -euo pipefail

# ── Secret hygiene guard (closed beta) ──────────────────────────────
# Refuse to package if any bundled credential for an *enabled* platform is
# still a placeholder. YouTube is exempt while disabled (YOUTUBE_ENABLED=False).
echo "==> Checking bundled credentials"
CREDS="core/credentials.py"
if [[ ! -f "$CREDS" ]]; then
  echo "ERROR: $CREDS missing — copy core/credentials.py.template and fill real secrets." >&2
  exit 1
fi
for name in TWITCH_CLIENT_ID TWITCH_CLIENT_SECRET KICK_CLIENT_ID KICK_CLIENT_SECRET; do
  if grep -E "^${name}\b" "$CREDS" | grep -q "REPLACE_WITH_"; then
    echo "ERROR: placeholder credential ${name} — refusing to build." >&2
    exit 1
  fi
done
echo "    Twitch + Kick credentials present (YouTube exempt while disabled)"

echo "==> Cleaning previous build"
rm -rf build/ dist/

echo "==> Building TwitchX.app"
uv run pyinstaller TwitchX.spec

echo "==> Done: dist/TwitchX.app"
echo ""
echo "Prerequisites (not bundled):"
echo "  brew install streamlink"
echo "  IINA (optional, for external playback): https://iina.io"
