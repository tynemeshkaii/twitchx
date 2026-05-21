# TwitchX Beta Release Plan

Status: **Draft** | Created: 2026-05-21

---

## P0 — Blockers

### 1. Credentials security
- [ ] Add `core/credentials.py` to `.gitignore`
- [ ] Create `core/credentials.py.template` with placeholder values
- [ ] Verify real credentials are never committed (check git history, scrub if needed)
- [ ] Consider moving to macOS Keychain for production

### 2. .gitignore hardening
- [ ] Add standard Python ignores: `__pycache__/`, `*.pyc`, `*.egg-info/`, `dist/`, `build/`
- [ ] Add env/secrets: `.env*`, `.venv*/`, `.venv_test/`
- [ ] Add macOS: `.DS_Store`
- [ ] Add project-specific: `.coverage`, `htmlcov/`, `.superpowers/`

### 3. Pyright errors (12)
- [ ] Fix 8 test mock signature mismatches (`_eval_js` parameter name `code` vs `s`)
- [ ] Fix 2 `run_until_complete` on possibly-None loop in `ui/api/data.py:466,471`
- [ ] Fix remaining 2 errors
- [ ] Target: 0 errors on `make lint`

### 4. Test coverage: auth.py (22% → 70%+)
- [ ] OAuth login initiation (Twitch, Kick, YouTube)
- [ ] Token exchange (success, failure, timeout)
- [ ] Token refresh (success, expired refresh token, network error)
- [ ] Logout / token cleanup
- [ ] PKCE flow verification

### 5. Test coverage: images.py (17% → 70%+)
- [ ] Avatar resize + base64 encode
- [ ] Thumbnail resize + base64 encode
- [ ] Corrupt/missing image handling
- [ ] Disk cache hit/miss/expiry

### 6. Audit broad exception handlers
- [ ] Grep all 43 `except Exception` blocks
- [ ] For each: add specific exception types where possible
- [ ] For unavoidable broad catches: add `logger.exception()` so errors are visible
- [ ] Never silently swallow — at minimum log

---

## P1 — High Priority

### 7. Structured logging
- [ ] Add `logger = logging.getLogger(__name__)` to every module in `core/` and `ui/`
- [ ] Log levels: DEBUG for API requests/responses, INFO for state changes, WARNING for fallbacks, ERROR for failures
- [ ] Key log points:
  - OAuth flow start/success/failure
  - API request errors and retries
  - Stream resolution attempts and fallbacks
  - Chat connect/disconnect/reconnect
  - Config load/save
- [ ] Default level: WARNING (quiet). `TWITCHX_DEBUG=1` → DEBUG

### 8. Error UX (toast notifications)
- [ ] `toast.js` already exists — wire it to all failure paths
- [ ] API fetch failure → toast with retry option
- [ ] Stream resolution failure → toast with error detail
- [ ] OAuth failure → toast with "try again" action
- [ ] Chat disconnect → toast (auto-dismiss on reconnect)
- [ ] Network offline → persistent toast until recovery

### 9. Null event loop guard
- [ ] `ui/api/data.py:466` — guard `loop.run_until_complete()` with `if loop is not None`
- [ ] `ui/api/data.py:471` — same
- [ ] Add test for the None-loop path

### 10. Connection status indicators
- [ ] Chat panel: show connected/disconnected/reconnecting state
- [ ] Stream player: show buffering/error/reconnecting state
- [ ] Sidebar: visual indicator when polling fails (stale data)

### 11. YouTube quota persistence
- [ ] Verify quota counter survives app restart (check `config.json` or separate state)
- [ ] Verify quota resets daily (YouTube resets at midnight Pacific)
- [ ] Test toast triggers at 80% and 95%

### 12. Platform client test coverage
- [ ] `twitch.py` (56%): rate limit retry, 401 refresh, malformed JSON, empty response, pagination edge cases
- [ ] `kick.py` (64%): auth flow, channel not found, API shape changes
- [ ] Target: 75%+ for both

---

## P2 — Beta Quality

### 13. macOS .app bundle
- [ ] Evaluate: py2app vs PyInstaller vs Nuitka
- [ ] Create build script (`make build` or `build.sh`)
- [ ] Bundle streamlink as dependency or document as prerequisite
- [ ] Test: launch from Finder, no terminal needed
- [ ] Code-sign (optional for beta, required for public release)

### 14. First-run / onboarding testing
- [ ] Test: fresh `~/.config/twitchx/` (no config file)
- [ ] Test: no OAuth login — app shows onboarding buttons
- [ ] Test: add first channel manually
- [ ] Test: import follows from Twitch
- [ ] Test: settings modal on first open

### 15. Dependency audit
- [ ] Verify `curl-cffi` usage (likely Kick anti-bot) — remove if unused
- [ ] Pin all dependency versions in `pyproject.toml` (use `>=X,<Y` ranges)
- [ ] Run `uv pip audit` or equivalent for known vulnerabilities

### 16. Offline / network resilience
- [ ] Test: app launch with no internet
- [ ] Test: internet drops during stream playback
- [ ] Test: internet drops during browse/search
- [ ] Test: internet recovers — auto-reconnect behavior
- [ ] Test: DNS failure vs timeout vs connection refused (different UX?)

### 17. Memory / resource leaks
- [ ] Profile a 2-hour session: RSS memory, thread count, open file descriptors
- [ ] Verify `threading.Timer` cancellation on shutdown
- [ ] Verify `httpx.AsyncClient` cleanup after temporary event loops
- [ ] Verify avatar disk cache size stays bounded
- [ ] Verify `_seen_msg_ids` in KickChat doesn't grow past cap

### 18. Config robustness
- [ ] Test: malformed JSON in `config.json` → graceful fallback to defaults
- [ ] Test: missing fields → merge with `DEFAULT_CONFIG` works
- [ ] Test: unexpected types (string where int expected)
- [ ] Test: config file permissions (read-only, missing directory)

---

## P3 — Nice to Have

### 19. Lint cleanup
- [ ] Fix 3 ruff import-order issues in test files
- [ ] `make lint` should pass with 0 warnings

### 20. CI/CD (GitHub Actions)
- [ ] Workflow: `make check` (lint + type-check + tests) on push/PR
- [ ] Matrix: Python 3.11, 3.12, 3.13
- [ ] Coverage report as PR comment (optional)

### 21. Version display in UI
- [ ] Read version from `pyproject.toml` or bake into build
- [ ] Show `v0.1.0-beta` in settings footer or about section

### 22. CHANGELOG.md
- [ ] Document features available in beta
- [ ] Document known limitations
- [ ] Document required prerequisites (streamlink, IINA optional)

### 23. Crash reporting (optional)
- [ ] Evaluate: Sentry (free tier) or local crash log file
- [ ] Opt-in only, with clear privacy disclosure
- [ ] At minimum: write unhandled exceptions to `~/.config/twitchx/crash.log`

### 24. Accessibility audit
- [ ] Keyboard navigation: can every feature be reached without mouse?
- [ ] Screen reader: verify ARIA labels on interactive elements
- [ ] Focus management: modal/overlay traps focus correctly?
- [ ] Color contrast: check against WCAG AA
