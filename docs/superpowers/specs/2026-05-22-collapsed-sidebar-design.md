# Collapsed Sidebar — Icon Rail Design

**Date:** 2026-05-22  
**Status:** Approved

---

## Problem

The current `collapsed-sidebar` mode (56px) has no visual treatment for channel items — they are simply clipped at the container width. The result is an accidental layout: the 2px accent-bar, 7px live-dot, and 26px avatar are visible, but only because the sidebar is 56px wide, not by design. Section headers (Online/Offline) are also completely unadapted for this width.

---

## Decision

Replace the current broken collapsed state with a proper **icon rail** — a 52px sidebar that shows only channel avatars with live/offline indicators and a thin section divider.

---

## Design Spec

### Dimensions

| Property | Value |
|---|---|
| Collapsed width | `52px` |
| Expanded width | `240px` (unchanged) |
| Transition | `width 200ms ease` (already set via `var(--duration-normal)`) |

### Avatar

| Property | Value |
|---|---|
| Size | `32×32px` |
| Border-radius | `50%` |
| Centering | `margin: 0 auto` within the rail |

### Live channel indicators

| Property | Value |
|---|---|
| Ring | `2px solid #30d158`, `inset: -2px` (absolute positioned) |
| Dot | `9px×9px`, `border-radius: 50%`, `background: #30d158`, `border: 2px solid #1c1c1e`, positioned `bottom: 0; right: 0` |
| Avatar filter | none (full color) |

### Offline channel

| Property | Value |
|---|---|
| Avatar filter | `grayscale(0.7) opacity(0.5)` |
| No ring, no dot | — |

### Section divider

A single `1px` horizontal rule between the last live avatar and the first offline avatar:

```css
width: 24px;
height: 1px;
background: rgba(255, 255, 255, 0.1);
margin: 3px auto;
```

Only rendered if both groups are non-empty.

### Toggle button

Positioned at the top of the rail, centered:

```
28×28px
border-radius: 6px
background: rgba(255,255,255,0.06)
chevron icon pointing right (→) — indicates "expand"
```

When expanded, the same button sits in `#favorites-header` with chevron pointing left (←), as today.

### Elements hidden in collapsed mode

These are hidden via `display: none` when `#sidebar.collapsed-sidebar` is active:

- `.sidebar-section` header elements: `.section-toggle` (the full button), replaced by avatar-only list
- `.channel-copy` (name + meta text)
- `.metric` / `.status-badge`
- `.accent-bar`
- The sidebar-internal `.live-dot` (the 7px dot inside `channel-item` — replaced by the new 9px dot on the avatar)
- `#profile-area`, `#kick-profile-area`, `#platform-tabs`, `#search-area`, `#browse-nav-wrapper` (already hidden today)
- `#favorites-header` (replaced by the toggle button rendered directly in the rail)

### Hover tooltip

The existing `_setupSidebarTooltip` mechanism works as-is — shows name, game, thumbnail, viewers on 400ms hover delay. No changes needed.

---

## Rendering approach

The icon rail does **not** reuse `.channel-item` DOM nodes styled down. Instead, `renderSidebar()` detects the collapsed state and renders a completely different DOM structure inside `#channel-list`:

```
#channel-list (collapsed)
  .rail-toggle-btn        ← expand chevron
  .rail-avatar[data-login] (live, in order)
    .av-ring
    .av-dot
  .rail-divider           ← only if both groups non-empty
  .rail-avatar[data-login] (offline, in order)
```

This avoids complex CSS overrides on `.channel-item` and makes the two modes independently maintainable. The `data-login` attribute is preserved so tooltip and click handlers attach the same way.

### Update path

`renderSidebar()` already diffs the DOM. The collapsed/expanded check becomes a branch at the top:

```js
if (document.getElementById('sidebar').classList.contains('collapsed-sidebar')) {
  renderRail(groups);
} else {
  renderFullSidebar(groups);  // existing logic
}
```

`renderRail` is a new function that builds the rail DOM. It runs the same diff logic (detect login membership changes, do in-place updates vs full rebuild).

---

## CSS changes

### `layout.css`

No changes needed. The `#sidebar` width is already controlled by the `.collapsed-sidebar` class.

### `components.css`

1. Change `#sidebar.collapsed-sidebar { width: 56px }` → `width: 52px`
2. Add `.rail-toggle-btn` styles
3. Add `.rail-avatar` styles (ring, dot, offline filter)
4. Add `.rail-divider` style
5. Remove the existing (currently unused) collapsed-sidebar channel-item overrides

---

## What does NOT change

- Expanded sidebar: no changes
- Tooltip on hover: works as-is
- Click/dblclick/contextmenu handlers: attached to `.rail-avatar` with same `data-login`
- `collapsed-sidebar` class toggling logic in `init.js` / keyboard shortcut
- Transition duration

---

## Out of scope

- "Fully hidden" sidebar mode (B from brainstorm)
- Live count badge on toggle button (B from approaches)
- Drag-to-multistream from icon rail (can be added later)
