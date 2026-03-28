# Favorites Sidebar Sections

## Goal

Make the sidebar easier to scan by splitting favorites into `Online` and `Offline` groups with collapsible sections.

## Behavior

- Sidebar favorites are rendered as two sections in this order: `Online`, then `Offline`.
- `Online` contains channels from `state.liveSet`.
- `Offline` contains the remaining favorites.
- `Online` is the primary section in the sidebar and has priority in height allocation.
- `Online` is sorted by active viewers descending.
- If two live channels have the same viewer count, sort them alphabetically.
- `Offline` is sorted alphabetically.
- Drag-and-drop reordering is removed from the sidebar because ordering is fully automatic.
- Each section can be collapsed and expanded independently.
- Default state: `Online` expanded, `Offline` collapsed.
- Section collapsed state is persisted in `localStorage`.
- If the currently selected channel belongs to a collapsed section, that section auto-expands so the selection remains visible.
- `Online` adapts to the number of live channels and keeps a comfortable scrollable viewport when the list grows.
- `Online` height should hug its actual content for short live lists and be recalculated when the sidebar height changes.

## Visual Direction

- Keep the existing TwitchX dark glassy sidebar language.
- Add compact section cards with subtle depth and tinted headers.
- `Online` should feel slightly more vivid with a live-green accent and clearer information density.
- `Offline` should feel quieter and more muted.
- Rows keep the current avatar-first compact pattern, but gain a clearer information hierarchy.
- Live rows show a compact viewer count on the right to reinforce the automatic sort order.
- Section metadata should communicate list meaning at a glance, for example live count or combined viewers.

## Technical Notes

- Implement entirely in `ui/index.html`.
- Rebuild the sidebar DOM on refresh instead of preserving the old drag-and-drop structure.
- Continue using safe DOM creation APIs only.
