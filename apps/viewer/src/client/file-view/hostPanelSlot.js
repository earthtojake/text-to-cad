// Where the surface's right-hand panel is DRAWN (docs/file-view.md, "Where
// the panels are drawn").
//
// The surface has one right-hand panel with several contents — the theme
// editor and the file sheets — and standalone it draws the column that holds
// them: a width, a border, a resize handle. A host application usually has
// panels of its own beside them (the desktop app's file tree), and two
// columns of two different designs, each with its own width and its own
// header, is the thing a person notices first. So a host may hand over the
// box: `panelSlot` is an element, the open panel's content is portaled into
// it, and the surface draws no column at all — the host's frame is the only
// frame, and the viewport takes the width the column used to.
//
// Plain functions in a module with no `@/` imports, so `node --test` can load
// them without the bundler's aliases. The context they resolve into is read
// by `FileSheet`, which is the one frame every panel is drawn in.

/**
 * A host's panel slot, or null.
 *
 * Only an element node is a box a panel can be drawn in. Anything else —
 * null, a string selector, a ref that has not attached yet on the first
 * render — is nothing asked for, and nothing asked for is the standalone
 * behaviour rather than a panel portaled into `undefined`.
 */
export function normalizeHostPanelSlot(value) {
  return value && typeof value === "object" && value.nodeType === 1 ? value : null;
}

/**
 * Where the open panel goes, from whatever the host passed.
 *
 * One answer for both halves of the decision, because they are the same
 * decision: a panel portaled into a host's slot must not also reserve a
 * column, and a column drawn with no slot must not portal anywhere. Reading
 * the two out of one call is how they cannot disagree.
 */
export function resolveHostPanelPlacement(panelSlot) {
  const slot = normalizeHostPanelSlot(panelSlot);
  return { slot, drawsOwnColumn: slot === null };
}
