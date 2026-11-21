import { useCallback, useLayoutEffect, useRef, useState } from "react";

/**
 * Where a phone's sidebar sheet stands (`ViewFrame.jsx`): under the viewer's navbar, so the navbar (the panel's toggle,
 * the file's name, Display, Preview) stays in sight above it, its top the navbar's bottom edge, measured while the sheet
 * is open and again as the viewer or the navbar resizes (the page scrolled, the keyboard shown). With no navbar (a
 * host that shows the view alone) it stands from the window's top, as the stock Sheet does.
 * And where its focus goes back on close: the navbar's panel toggle, which opened it (Radix's Dialog returns focus
 * to its own Trigger, and the toggle is not one). A press on that toggle is not a press outside: the toggle shuts the
 * sheet itself (a dismissal first would have the toggle open it again); a press anywhere else outside closes it, and a
 * press on another navbar control (Display, Preview, the name) also does what that control does.
 * @param {{ current: HTMLElement | null } | null | undefined} viewerElement The viewer's element (`ViewerElementContext`).
 * @param {boolean} open
 * @returns {{ style: { top: string } | undefined, onCloseAutoFocus(event: Event): void, onPointerDownOutside(event: Event): void }}
 */
export function usePhoneSheetPlace(viewerElement, open) {
  const [top, setTop] = useState(null);
  useLayoutEffect(() => {
    const element = viewerElement?.current;
    if (!open || !element) return undefined;
    const measure = () => {
      const bar = element.querySelector("[data-viewer-navbar]");
      setTop(bar ? Math.round(bar.getBoundingClientRect().bottom) : null);
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
  return { style: top == null ? undefined : { top: `${top}px` }, onCloseAutoFocus, onPointerDownOutside };
}
