# Review Fixes and Roadmap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize the current Twitch-only desktop client after review findings, reduce architectural risk, and prepare the codebase for multi-platform streaming support and opt-in ad-protection capabilities.

**Architecture:** Fix correctness and security issues first with focused regression tests. Then extract a provider-agnostic domain layer so Twitch becomes one adapter instead of the whole application contract. Add future platform and ad-protection features behind explicit capability flags and isolated services to avoid spreading provider-specific logic through UI code.

**Tech Stack:** Python 3.11+, CustomTkinter, httpx, pytest, threading + asyncio event loops, streamlink, IINA.

---

## Scope

1. Close the currently known correctness/security gaps from review.
2. Reduce coupling between `app.py`, Twitch-specific API logic, and UI diff logic.
3. Prepare a normalized provider model for Kick, W.TV, and similar platforms.
4. Prepare a normalized emote ecosystem layer for BTTV, 7TV, FrankerFaceZ, and similar providers.
5. Define a controlled implementation path for ad protection with explicit legal and technical boundaries.

## Constraints and Assumptions

- The app remains macOS-first and keeps `streamlink + IINA` as the default launch path.
- New work should preserve the existing CustomTkinter single-window architecture.
- Platform-specific capabilities will differ; the UI must support partial feature availability.
- External emote providers must be integrated through a separate service layer, not hardcoded into platform adapters or UI widgets.
- Ad-protection work must be opt-in, isolated, and reviewed against platform ToS before shipping by default.

### Task 1: Add Russian-only communication policy to repository guidance

**Files:**
- Modify: `AGENTS.md`

**Step 1: Add a dedicated communication section**

Document that all user-facing agent communication must be in Russian.

**Step 2: Preserve technical terms as-is**

Keep commands, code, identifiers, API names, and product names in original form.

**Step 3: Add tone constraints**

State that responses must stay concise, direct, and engineering-focused.

**Step 4: Review for conflicts**

Check that the new section does not contradict existing repository workflow instructions.

**Step 5: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add russian communication rules for agents"
```

### Task 2: Fix stream-grid ordering regression for in-place updates

**Files:**
- Modify: `ui/stream_grid.py`
- Create: `tests/test_stream_grid.py`

**Step 1: Write the failing test**

```python
def test_update_streams_rebuilds_when_sorted_order_changes():
    grid = make_grid(sort_key=SORT_MOST_VIEWERS)
    grid.update_streams(
        [stream("a", 200), stream("b", 100)],
        {},
        {},
    )
    grid.update_streams(
        [stream("a", 100), stream("b", 300)],
        {},
        {},
    )
    assert visible_logins(grid) == ["b", "a"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stream_grid.py::test_update_streams_rebuilds_when_sorted_order_changes -v`

**Step 3: Implement minimal fix**

Compare the ordered visible login list, not just the visible login set. Rebuild the grid when ordering changes under the current sort/filter mode.

**Step 4: Run focused tests**

Run: `uv run pytest tests/test_stream_grid.py -v`

**Step 5: Commit**

```bash
git add ui/stream_grid.py tests/test_stream_grid.py
git commit -m "fix: preserve sorted order in stream grid updates"
```

### Task 3: Fix sidebar diff-update state drift

**Files:**
- Modify: `ui/sidebar.py`
- Create: `tests/test_sidebar.py`

**Step 1: Write failing tests**

```python
def test_update_channels_refreshes_selected_state_without_full_rebuild():
    sidebar = make_sidebar()
    sidebar.update_channels(["a", "b"], {"a"}, {})
    sidebar.set_selected("b")
    sidebar.update_channels(["a", "b"], {"a"}, {})
    assert item_is_selected(sidebar, "b")

def test_update_channels_can_attach_avatar_after_initial_render():
    sidebar = make_sidebar()
    sidebar.update_channels(["a"], set(), {})
    sidebar.update_channels(["a"], set(), {"a": fake_avatar()})
    assert item_has_avatar(sidebar, "a")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sidebar.py -v`

**Step 3: Implement minimal fix**

Update `ChannelItem` so it can create the avatar widget lazily, and refresh selection styling during incremental updates.

**Step 4: Run focused tests**

Run: `uv run pytest tests/test_sidebar.py -v`

**Step 5: Commit**

```bash
git add ui/sidebar.py tests/test_sidebar.py
git commit -m "fix: refresh sidebar selection and avatar state"
```

### Task 4: Close OAuth and local secret-handling risks

**Files:**
- Modify: `core/twitch.py`
- Modify: `core/oauth_server.py`
- Modify: `core/storage.py`
- Modify: `app.py`
- Create: `tests/test_oauth_flow.py`

**Step 1: Write failing tests**

```python
def test_auth_url_contains_state():
    client = TwitchClient()
    url = client.get_auth_url()
    assert "state=" in url

def test_callback_rejects_mismatched_state():
    assert validate_state("expected", "received") is False

def test_save_config_uses_private_permissions(tmp_path):
    save_config({"client_id": "x", "client_secret": "y"})
    assert oct(CONFIG_FILE.stat().st_mode & 0o777) == "0o600"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_oauth_flow.py tests/test_storage.py -v`

**Step 3: Implement minimal fix**

- Generate and persist a per-login `state` token.
- Validate `state` in the localhost callback path before exchanging the code.
- Write config atomically with mode `0600`.
- Surface a clear UI error when port `3457` cannot be bound.

**Step 4: Run focused tests**

Run: `uv run pytest tests/test_oauth_flow.py tests/test_storage.py -v`

**Step 5: Commit**

```bash
git add core/twitch.py core/oauth_server.py core/storage.py app.py tests/test_oauth_flow.py tests/test_storage.py
git commit -m "fix: harden oauth flow and config secret storage"
```

### Task 5: Fix async client lifecycle and stale-loop failures

**Files:**
- Modify: `app.py`
- Modify: `core/twitch.py`
- Modify: `tests/test_twitch.py`

**Step 1: Write failing tests**

```python
def test_refresh_path_does_not_reuse_closed_loop_client():
    client = TwitchClient()
    run_fetch_on_temp_loop(client)
    run_fetch_on_temp_loop(client)
    assert no_runtime_error_occurred()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_twitch.py -v`

**Step 3: Implement minimal fix**

Choose one of two approaches and document the decision:
- create one worker event loop and keep `TwitchClient` bound to it, or
- recreate/close the `httpx.AsyncClient` after each temp-loop fetch/search/import path.

Recommendation: move all Twitch I/O onto one dedicated background event loop service instead of per-call loop creation.

**Step 4: Run focused tests**

Run: `uv run pytest tests/test_twitch.py -v`

**Step 5: Commit**

```bash
git add app.py core/twitch.py tests/test_twitch.py
git commit -m "fix: stabilize twitch client event loop lifecycle"
```

### Task 6: Refactor application into provider-agnostic layers

**Files:**
- Create: `core/models.py`
- Create: `core/providers/__init__.py`
- Create: `core/providers/base.py`
- Create: `core/providers/registry.py`
- Modify: `core/twitch.py`
- Modify: `app.py`
- Modify: `ui/sidebar.py`
- Modify: `ui/stream_grid.py`

**Step 1: Define normalized domain models**

Create dataclasses such as:

```python
@dataclass
class StreamSummary:
    platform: str
    channel_id: str
    login: str
    display_name: str
    title: str
    game_name: str
    viewer_count: int
    started_at: str
    thumbnail_url: str
    is_live: bool
```

**Step 2: Define provider contract**

Create an abstract interface for:
- auth status
- search
- favorites import
- live stream fetch
- user fetch
- launch URL resolution
- capability flags

**Step 3: Wrap Twitch behind the new contract**

Adapt existing Twitch responses into normalized models without changing UI behavior yet.

**Step 4: Move UI off raw Twitch payloads**

Update `app.py`, `ui/sidebar.py`, and `ui/stream_grid.py` to consume normalized models instead of Twitch-specific field names.

**Step 5: Run regression suite**

Run: `uv run pytest tests/ -v`

**Step 6: Commit**

```bash
git add core/models.py core/providers app.py ui/sidebar.py ui/stream_grid.py tests
git commit -m "refactor: introduce provider-agnostic streaming models"
```

### Task 7: Add platform capability matrix and settings model

**Files:**
- Modify: `core/storage.py`
- Modify: `app.py`
- Modify: `ui/sidebar.py`
- Create: `tests/test_platform_config.py`

**Step 1: Extend config schema**

Store enabled platforms, per-platform credentials, default platform order, and per-platform feature flags.

**Step 2: Add provider registry wiring**

Resolve enabled providers from config and aggregate streams/search results through one application service.

**Step 3: Add settings UI placeholders**

Expose provider enable/disable and credential fields without implementing all providers yet.

**Step 4: Test config compatibility**

Run: `uv run pytest tests/test_platform_config.py tests/test_storage.py -v`

**Step 5: Commit**

```bash
git add core/storage.py app.py ui/sidebar.py tests/test_platform_config.py
git commit -m "feat: add provider registry and multi-platform config"
```

### Task 8: Add Kick as the second provider

**Files:**
- Create: `core/providers/kick.py`
- Modify: `core/providers/registry.py`
- Modify: `app.py`
- Create: `tests/test_kick_provider.py`

**Step 1: Define Kick adapter scope**

Support:
- channel search
- live status fetch
- normalized stream mapping
- open/watch launch path

**Step 2: Implement provider adapter**

Map Kick data into `StreamSummary` and user/channel models.

**Step 3: Add capability guards**

Disable follows import or OAuth-specific features if Kick does not support them in the same way as Twitch.

**Step 4: Test adapter behavior**

Run: `uv run pytest tests/test_kick_provider.py -v`

**Step 5: Commit**

```bash
git add core/providers/kick.py core/providers/registry.py app.py tests/test_kick_provider.py
git commit -m "feat: add kick platform provider"
```

### Task 9: Add W.TV and future-provider onboarding path

**Files:**
- Create: `core/providers/wtv.py`
- Modify: `core/providers/base.py`
- Modify: `docs/plans/2026-03-16-review-fixes-and-roadmap.md`
- Create: `tests/test_wtv_provider.py`

**Step 1: Implement W.TV adapter only through the shared contract**

Do not add W.TV-specific branching to UI code.

**Step 2: Document provider checklist**

Every new platform must define:
- auth model
- search support
- live fetch support
- thumbnail format
- viewer metric semantics
- playback URL strategy
- supported ad-protection modes

**Step 3: Test adapter behavior**

Run: `uv run pytest tests/test_wtv_provider.py -v`

**Step 4: Commit**

```bash
git add core/providers/wtv.py core/providers/base.py docs/plans/2026-03-16-review-fixes-and-roadmap.md tests/test_wtv_provider.py
git commit -m "feat: add wtv provider and provider checklist"
```

### Task 10: Add opt-in ad-protection architecture

**Files:**
- Create: `core/adguard.py`
- Create: `core/launch_policies.py`
- Modify: `core/launcher.py`
- Modify: `core/storage.py`
- Modify: `app.py`
- Create: `tests/test_launch_policies.py`

**Step 1: Define explicit modes**

Add launch policy enum:

```python
class AdProtectionMode(StrEnum):
    OFF = "off"
    DETECT_ONLY = "detect_only"
    OPT_IN = "opt_in"
```

**Step 2: Separate detection from bypass strategy**

`core/adguard.py` should only decide whether the current provider/playback path is ad-protected, ad-prone, or unsupported. Do not bury this logic inside UI callbacks.

**Step 3: Add provider capability mapping**

Each provider declares supported ad-protection strategies:
- unsupported
- player-side only
- alternate playback resolver
- explicit warning only

**Step 4: Add settings toggle and safe defaults**

Default to `OFF`. Surface a warning in UI when the selected provider does not support the chosen mode.

**Step 5: Add tests**

Run: `uv run pytest tests/test_launch_policies.py -v`

**Step 6: Commit**

```bash
git add core/adguard.py core/launch_policies.py core/launcher.py core/storage.py app.py tests/test_launch_policies.py
git commit -m "feat: add opt-in ad protection policy layer"
```

### Task 11: Add third-party emote ecosystem support

**Files:**
- Create: `core/emotes.py`
- Create: `core/emote_providers/__init__.py`
- Create: `core/emote_providers/base.py`
- Create: `core/emote_providers/bttv.py`
- Create: `core/emote_providers/seventv.py`
- Create: `core/emote_providers/ffz.py`
- Modify: `core/models.py`
- Modify: `core/storage.py`
- Modify: `app.py`
- Modify: `ui/sidebar.py`
- Modify: `ui/stream_grid.py`
- Create: `tests/test_emotes.py`

**Step 1: Define normalized emote models**

Create dataclasses such as:

```python
@dataclass
class EmoteDescriptor:
    provider: str
    code: str
    image_url: str
    scope: str
    channel_login: str | None = None
```

**Step 2: Define emote provider contract**

Each provider adapter must expose:
- global emotes
- channel emotes
- cache TTL
- fallback behavior
- image format and size variants

**Step 3: Implement BTTV, 7TV, and FrankerFaceZ adapters**

Keep them independent from Twitch/Kick/W.TV transport adapters. Emote providers are a parallel integration layer, not stream providers.

**Step 4: Add emote aggregation service**

`core/emotes.py` should merge multiple emote catalogs into one lookup table with deterministic precedence rules and local caching.

**Step 5: Add UI usage points**

Initial integration scope:
- render emote-aware text in any future chat/search/metadata surfaces;
- expose provider badges or availability in settings;
- keep stream list rendering safe when emote providers are unavailable.

Do not block stream loading on emote API failures.

**Step 6: Add config and feature flags**

Store enabled emote providers and precedence order in config, for example:
- `["7tv", "bttv", "ffz"]`

**Step 7: Add tests**

Run: `uv run pytest tests/test_emotes.py -v`

**Step 8: Commit**

```bash
git add core/emotes.py core/emote_providers core/models.py core/storage.py app.py ui/sidebar.py ui/stream_grid.py tests/test_emotes.py
git commit -m "feat: add third-party emote provider support"
```

## Delivery Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8
9. Task 9
10. Task 10
11. Task 11

## Verification Matrix

- `uv run pytest tests/test_stream_grid.py -v`
- `uv run pytest tests/test_sidebar.py -v`
- `uv run pytest tests/test_oauth_flow.py tests/test_storage.py -v`
- `uv run pytest tests/test_twitch.py -v`
- `uv run pytest tests/test_platform_config.py tests/test_kick_provider.py tests/test_wtv_provider.py tests/test_launch_policies.py -v`
- `uv run pytest tests/test_platform_config.py tests/test_kick_provider.py tests/test_wtv_provider.py tests/test_launch_policies.py tests/test_emotes.py -v`
- `uv run pytest tests/ -v`
- `uv run ruff check .`
- `uv run pyright .`

## Risks to Track

- Cross-loop `httpx.AsyncClient` reuse remains the main reliability risk until Task 5 is finished.
- Provider normalization can balloon if platform-specific quirks leak into UI types.
- Emote-provider integration can create API fan-out and rate-limit pressure; cache aggressively and fail open.
- Ad-protection work has product and legal risk; keep it behind capability checks and default-off behavior.
- Multi-platform support will change search, favorites, and launch semantics; add platform labels to every normalized entity early.
