/**
 * The page's primary pointer is coarse (a touch screen). The one place it is read (the kit's `viewport/dom.js` hands
 * it on); a gesture asks when it starts, so a press of a fine pointer on such a page is still given touch slop, and a
 * menu asks as it draws, leaving out the key hints a touch screen has no keys for.
 */
export function prefersCoarsePointer() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
}
