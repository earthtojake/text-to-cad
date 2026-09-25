export function isEditableTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  return !!target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], [role='textbox']");
}

/**
 * The page's primary pointer is coarse (a touch screen). The one place it is read; a gesture
 * asks when it starts, so a press of a fine pointer on such a page is still given touch slop.
 */
export function prefersCoarsePointer() {
  return typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
}
