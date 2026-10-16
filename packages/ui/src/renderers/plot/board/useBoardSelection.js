import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const EMPTY = Object.freeze([]);

/**
 * What is selected and hovered on a board (`useLinkSelection.js` is a robot's): any number of board
 * references (`#U3`, `#U3.9`, `#net:VIN`, `#net:VIN@x..y..` and points).
 * Read-only: nothing here changes the design.
 *
 * The selection is React state, because the tree and the Reference draw it; the hover is not,
 * because nothing but the canvas shows it and it changes as the pointer moves, over the canvas
 * (`hoverHit`) or down the tree (`hover`). Either repaints the canvas (`requestPaint`).
 *
 * The selection is Select's, a board's one tool, so it is never dropped for another tool.
 * A new revision keeps the selection where it still names something on it.
 *
 * @param {{ index: object | null, requestPaint: () => void }} options
 */
export function useBoardSelection({ index, requestPaint }) {
  const [selection, setSelection] = useState(EMPTY);
  const [selectMode, setSelectMode] = useState("all");
  const hoverRef = useRef(null);

  // ---- a new revision ----------------------------------------------------------
  useEffect(() => {
    if (!index) return;
    hoverRef.current = null;
    setSelection((current) => {
      const kept = current.filter((selector) => index.resolve(selector));
      return kept.length === current.length ? current : kept;
    });
  }, [index]);

  const resolved = useMemo(() => (index ? selection.map((selector) => index.resolve(selector)).filter(Boolean) : EMPTY), [index, selection]);
  // A net is easier to read with the rest of the board stepped back.
  const dim = resolved.some((item) => item.kind === "net");

  const clear = useCallback(() => { setSelection(EMPTY); }, []);

  /** Select what `selectors` name here (what names nothing is left out); `add` toggles each. */
  const select = useCallback((selectors, { add = false } = {}) => {
    const valid = (Array.isArray(selectors) ? selectors : [selectors]).map((selector) => index?.resolve(selector)?.selector).filter(Boolean);
    setSelection((current) => {
      if (!add) return valid.length ? [...new Set(valid)] : EMPTY;
      const next = new Set(current);
      for (const selector of valid) { if (next.has(selector)) next.delete(selector); else next.add(selector); }
      return [...next];
    });
  }, [index]);

  // ---- the hover -----------------------------------------------------------------
  /** What the pointer is over on the canvas (a pick, or null): repaints only when it changed. */
  const hoverHit = useCallback((hit) => {
    if ((hit?.selector || "") === (hoverRef.current?.selector || "")) return false;
    hoverRef.current = hit || null;
    requestPaint();
    return true;
  }, [requestPaint]);
  /** A tree row under the pointer lights what it names on the canvas; null puts it out. */
  const hover = useCallback((selector) => { hoverHit(selector && index ? index.resolve(selector) : null); }, [index, hoverHit]);
  /** Forget the hover, for a capture: a picture of the view shows what is selected, not where the pointer was. */
  const dropHover = useCallback(() => { hoverRef.current = null; }, []);

  return {
    selection, resolved, dim, active: Boolean(selection.length),
    select, clear, hover, hoverHit, hoverRef, dropHover, selectMode, setSelectMode,
  };
}
