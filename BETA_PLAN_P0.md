# TwitchX — P0 Execution Plan (Closed Beta)

Status: **Active** | Created: 2026-06-26 | Supersedes the P0 section of `BETA_PLAN.md`

## Decisions locked

- **Distribution:** closed beta, ≤ small trusted tester group.
- **Secrets:** bundled into the `.app` (Twitch + Kick real, accepted as extractable; revocation fallback = users paste own creds in Settings).
- **YouTube:** **disabled for this beta** (bundled YouTube creds are placeholders). Gate the UI behind a feature flag; keep backend code intact for later re-enable.

## Already done (verified 2026-06-26)

- ✅ SQLite connection leak in `core/watch_stats.py` (423 → 0 ResourceWarnings)
- ✅ `.gitignore` hardening, `credentials.py` gitignored, `credentials.py.template` present
- ✅ No real secrets in git history (placeholders only)
- ✅ `ruff check .` clean, `pyright .` 0 errors
- ✅ `ui/api/auth.py` 98% cov, `ui/api/images.py` 100% cov
- ✅ 634 tests pass, 77% total coverage

---

## P0-2 — Fix the packaged `.app` (🔴 showstopper, do first)

**Problem:** packaged app loads but renders a blank, dead UI.
- `TwitchX.spec:15` `datas` bundles only `ui/index.html` — not `ui/css/` or `ui/js/`.
- `app.py:102` resolves resources via `Path(__file__).parent`, not the PyInstaller frozen path. Under a frozen bundle, `_inline_resources` (`app.py:64–77`) reads `base_dir / href`, every `.exists()` fails, all CSS/JS silently skipped.

**Tasks**
1. `TwitchX.spec` — add the UI tree to `datas`:
   ```python
   datas = [
       ("ui/index.html", "ui"),
       ("ui/css", "ui/css"),
       ("ui/js", "ui/js"),
   ]
   ```
   (Recurse the whole `ui/css` and `ui/js` dirs — every `.css`/`.js` `<link>`/`<script src>` in `index.html` must resolve.)
2. `app.py` — make the resource base dir frozen-aware:
   ```python
   import sys
   base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
   html_path = base / "ui" / "index.html"
   ```
   Apply the same base to `_inline_resources` `base_dir`.
3. Confirm `main.py` logging path (`RotatingFileHandler`) still resolves under a frozen bundle (writes to `~/.config/twitchx/` / user dir, not the read-only bundle).

**Acceptance**
- `bash build.sh` (or `make build`) produces `TwitchX.app`.
- Launch from **Finder** (right-click → Open for Gatekeeper) — full styled UI renders, sidebar + empty-state visible, no missing-resource breakage.
- No terminal required.

---

## P0-1 — Disable YouTube for beta (🔴 showstopper)

**Problem:** bundled YouTube creds are placeholders (`credentials.py:16–18`). New user hits "Connect YouTube" on the welcome screen → fails. YouTube login/browse/chat all non-functional.

**Approach:** feature flag, not deletion. Hide every YouTube *entry point*; leave platform/chat clients intact.

**Tasks**
1. Add flag source of truth:
   - `core/constants.py` → `YOUTUBE_ENABLED = False`.
   - Expose to JS: inject into `TwitchX.state.youtubeEnabled` at init (via an API method or the existing state-bootstrap path).
2. Gate the UI entry points (hide when `!youtubeEnabled`):
   - `ui/js/render.js:73` — remove the "Connect YouTube" `secondaryAction` on the welcome empty-state.
   - `ui/index.html:542` — hide `#yt-login-btn` ("Connect YouTube Account") in Settings.
   - `ui/js/init.js:700` — guard the `youtube_login(cid, cs)` Settings-credentials path.
   - `ui/js/browse.js` / `ui/js/sidebar.js` — drop YouTube from platform filters / browse tabs.
   - `ui/js/multistream.js` — remove YouTube from the slot platform picker.
   - `ui/js/settings.js` — hide the YouTube credential section.
   - `ui/js/context-menu.js` / `ui/js/channel.js` — no YouTube actions surface.
3. `CHANGELOG.md` — move YouTube to "Coming soon" / drop from the v0.1.0-beta feature list; note Twitch + Kick only.
4. Sanity: a logged-in user with existing YouTube favorites (edge case) shouldn't crash — flag-off path must tolerate `youtubeUser === null` (already the default).

**Acceptance**
- Fresh launch: no YouTube button anywhere in the UI.
- Browse / multistream / settings show only Twitch + Kick.
- `make check` green. No console errors referencing YouTube.
- Re-enable later = flip `YOUTUBE_ENABLED = True` + fill real creds.

---

## P0-5 — Closed-beta secret hygiene (🟡, cheap, lock after P0-1/2)

**Tasks**
1. **Build guard** — `build.sh` aborts before packaging if any bundled cred is still a placeholder *for an enabled platform*:
   - Check `core/credentials.py` for `REPLACE_WITH_` in `TWITCH_*` and `KICK_*` (YouTube exempt while `YOUTUBE_ENABLED = False`).
   - Fail loud: `ERROR: placeholder credential <NAME> — refusing to build`.
2. **Docs** — `README.md`: mark "Closed beta — do not redistribute the `.app`." State the revocation fallback (Settings → paste own Twitch/Kick app credentials).
3. Confirm `core/credentials.py` is bundled (it's an `import core.credentials`, collected as a module by PyInstaller Analysis — verify it's present in the built bundle, secrets included).

**Acceptance**
- `build.sh` refuses to build with a placeholder Twitch/Kick secret.
- README states closed-beta + fallback.

---

## P0-4 — Broad-exception logging audit (🟠, mechanical)

**Problem:** ~34 `except Exception` blocks, only ~8 log. Silent swallow hides beta failures.

**Tasks**
1. Enumerate: `grep -rn 'except Exception' core ui --include='*.py'`.
2. For each: ensure either a specific exception type OR `logger.exception(...)` / `logger.error(...)`. Never silent `pass`/bare `return` without a log.
3. Priority files (lowest current logging): `ui/api/chat.py` (6), `ui/api/auth.py` (6), `ui/api/favorites.py` (5), `ui/api/data.py` (5).

**Acceptance**
- Every broad catch logs or narrows. `make lint` green.

---

## P0-3 — New-user happy-path verification (🟠, largest)

Pytest can't drive the GUI; split into automated + manual.

### P0-3a — Integration tests for the watch core
`ui/api/streams.py` is 55% — the thinnest coverage on the most-used feature.
- `watch(channel, quality)` — live-grid happy path + channel-not-in-cache fallback.
- `watch_direct(channel, platform, quality)` — Browse path.
- `watch_media(url, ...)` — VOD/clip passes `url` (not `channel`) to `resolve_hls_url` (regression guard for the known VOD-launches-live bug).
- `add_multi_slot(slot_idx, channel, platform, quality)` — multistream slot.
- Use existing fixtures (`capture_eval_js`, `run_sync`, `mock_twitch_client`).
- **Target:** `streams.py` 55% → 75%+.

### P0-3b — Manual QA checklist (run against the built `.app`)
Twitch + Kick only (YouTube disabled):
1. Wipe `~/.config/twitchx/` → launch → Welcome empty-state, only Twitch login + manual-add.
2. Login Twitch (real OAuth round-trip) → favorites populate.
3. Login Kick → favorites populate.
4. Import follows (Twitch) → sidebar fills.
5. Add channel manually via search.
6. Click live channel → playback < N s, quality switch works.
7. Chat opens → messages flow, 7TV/BTTV/FFZ emotes render.
8. Multistream 2 → 4 slots, audio focus, per-slot chat.
9. VOD/clip via `watch_media` — does NOT launch live, no offline crash.
10. External IINA/mpv launch.
11. Record via streamlink (streamlink-missing → clear error, not silent).
12. Offline launch + mid-stream internet drop → reconnect + toast.

**Acceptance**
- P0-3a tests green, coverage target hit.
- P0-3b checklist run on the packaged `.app`, issues logged as follow-ups.

---

## Execution order

1. **P0-2** — build fix (nothing ships until `.app` runs).
2. **P0-1** — disable YouTube (user-facing).
3. **P0-5** — build guard + docs (locks 1 + 2).
4. **P0-4** — exception logging (mechanical).
5. **P0-3** — streams tests + manual QA (largest; de-risks the rest).

## Deferred to P1 (not blocking closed beta)

- macOS Keychain token storage (plaintext `~/.config` acceptable for trusted testers).
- Real YouTube credentials + flip `YOUTUBE_ENABLED`.
- Backend token-exchange proxy (only if going public).
- `streams.py`/`native_player.py` coverage beyond 75%.
