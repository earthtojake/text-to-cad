// A popup — a Select, a menu, a popover, a context menu — may portal anywhere (the page
// body, say), so what belongs to an owner is its TRIGGER, and the trigger says whether its
// popup is up. A closing popup's trigger says so at once, even while its content animates out.
const OPEN_POPUP_TRIGGER = '[aria-haspopup][aria-expanded="true"], [role="combobox"][aria-expanded="true"], [data-slot="context-menu-trigger"][data-state="open"]';

/**
 * A popup opened from inside `element` is up. Its owner leaves the gesture that dismisses it
 * (Escape, an outside press) to the popup: the innermost layer closes first.
 * @param {Element | null | undefined} element
 */
export function hasOpenPopup(element) {
  return Boolean(element?.querySelector(OPEN_POPUP_TRIGGER));
}
