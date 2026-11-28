import { useCallback, useLayoutEffect, useRef, useState } from "react";

/** How much of the room under the navbar a phone's sidebar sheet takes, from the bottom: the model stays in sight above it. */
export const PHONE_SHEET_SHARE = 0.55;

/**
 * Where a phone's sidebar sheet stands (`ViewFrame.jsx`): a sheet from the bottom, its top `PHONE_SHEET_SHARE` of the
 * room under the viewer's navbar up from the view's foot (`sheetStyle`), so the navbar (the panel's toggle, the file's
 * name, Display, Preview) and the model above stay in sight: a part hidden or shown from the panel is seen going or
 * coming. Its overlay (`style`) starts at the navbar's bottom edge: a press on the model above closes the sheet. Both
 * are measured while the sheet is open and again as the viewer or the navbar resizes (the page scrolled, the keyboard shown).
 * And where its focus goes back on close: the navbar's panel toggle, which opened it (Radix's Dialog returns focus
 * to its own Trigger, and the toggle is not one). A press on that toggle is not a press outside: the toggle shuts the
 * sheet itself (a dismissal first would have the toggle open it again); a press anywhere else outside closes it, and a
 * press on another navbar control (Display, Preview, the name) also does what that control does.
 * @param {{ current: HTMLElement | null } | null | undefined} viewerElement The viewer's element (`ViewerElementContext`).
 * @param {boolean} open
 * `sheetTop`, the sheet's top in the window's px while it is open (else null): the frame lifts the canvas's foot to it.
 * @returns {{ style: { top: string } | undefined, sheetStyle: { top: string } | undefined, sheetTop: number | null, onCloseAutoFocus(event: Event): void,
 *   onPointerDownOutside(event: Event): void }}
 */
export function usePhoneSheetPlace(viewerElement, open) {
  const [top, setTop] = useState(null);
  const [sheetTop, setSheetTop] = useState(null);
  useLayoutEffect(() => {
    const element = viewerElement?.current;
    if (!open || !element) return undefined;
    const measure = () => {
      const bar = element.querySelector("[data-viewer-navbar]");
      const under = bar ? Math.round(bar.getBoundingClientRect().bottom) : null;
      setTop(under);
      // The sheet itself takes the lower part of the room under the navbar, the model in sight above it.
      const foot = Math.round(element.getBoundingClientRect().bottom || window.innerHeight);
      setSheetTop(under == null ? null : Math.round(under + (foot - under) * (1 - PHONE_SHEET_SHARE)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    const bar = element.querySelector("[data-viewer-navbar]");
    if (bar) observer.observe(bar);
    window.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); };
  }, [viewerElement, open]);
  // A press on another of the navbar's controls (Display, Preview, the name) closes the sheet and is that control's: focus
  // is left to it, or the menu it opens would close again as the toggle took the focus.
  const toNavbar = useRef(false);
  const onCloseAutoFocus = useCallback(event => {
    const toggle = viewerElement?.current?.querySelector('[data-navbar-panel="left"]');
    if (toNavbar.current) { toNavbar.current = false; event.preventDefault(); return; }
    if (!toggle) return;
    event.preventDefault();
    toggle.focus({ preventScroll: true });
  }, [viewerElement]);
  const onPointerDownOutside = useCallback(event => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest('[data-navbar-panel="left"]')) event.preventDefault();
    else toNavbar.current = Boolean(target?.closest("[data-viewer-navbar]"));
  }, []);
  return { style: top == null ? undefined : { top: `${top}px` }, sheetStyle: sheetTop == null ? undefined : { top: `${sheetTop}px` },
    sheetTop: open ? sheetTop : null, onCloseAutoFocus, onPointerDownOutside };
}
