import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@cad/ui/i18n";
import { Sheet, SheetContent, SheetTitle } from "@cad/ui/primitives/sheet";
import { cn } from "@cad/ui/utils";
import { ViewerElementContext, ViewerHostContext } from "../host/context.js";
import { hasOpenPopup } from "../lib/popups.js";
import { PANEL_SHEET_LEFT_CLASS, PanelPeekContext, usePanelPeek } from "./panelPeek.js";
import { panelShortcut, sidebarLayout, toggleSidebar, usePanelToggles } from "./panelToggles.js";
import { usePhoneSheetPlace } from "./usePhoneSheetPlace.js";

// The panel's frame: how ONE panel at a page's left shares the page, whatever it holds. A document's panel
// (`renderers/kit/shell/ViewFrame.jsx`: the file's structure and settings, beside its picture) and the home's sidebar
// (`library/LibrarySidebar.jsx`: its places, beside the place on screen) are both this, so they open, collapse, peek
// and turn into a phone's sheet the same way, from the same toggle in the navbar:
//
// - Pinned, it pushes what is beside it; collapsed, it leaves nothing (`panelToggles.js`'s `sidebarLayout`).
// - Until the person opens or closes it, the frame's width decides, again at every resize; their choice then holds at
//   any width (`choice`, which `onChoice` hands back to whoever keeps it: a file's record, the home's).
// - Collapsed, a mouse resting on the toggle peeks it over the page (`panelPeek.js`: the page's one peek where a file
//   viewer holds it, else the frame's own), never kept; Escape puts it away, and only the toggle pins it.
// - On a phone it is a sheet from the left under the navbar (`PanelSheet`), closed until its toggle opens it, kept nowhere.
// - Its toggle is the navbar's (`usePanelToggles`), with its key (`panelShortcut`); whoever has the keyboard calls
//   `toggle` for that key.
//
// The surface the panel is drawn on is `PanelSurface.jsx`; what is in it is its owner's.

/**
 * @param {{ has: boolean, mobile: boolean, hidden?: boolean, frameWidth: number, choice?: boolean,
 *   onChoice(open: boolean): void, early?: boolean }} options
 *   `has`: there is a panel to show. `hidden`: out of sight for now (a view's Preview): no toggle, no peek, no sheet.
 *   `frameWidth`: the frame's measured width (0 until measured). `choice`: the person's (open, closed, or none yet).
 *   `onChoice`: they chose, by the toggle; a stable function. `early`: the toggle is said before the first paint
 *   (`usePanelToggles`).
 * @returns {{ mode: "push" | "closed", peek: ReturnType<typeof usePanelPeek>, toggle(): void, closePeek(refocus?: boolean, instant?: boolean): void,
 *   state: { current: { has: boolean, mobile: boolean } & object },
 *   sheet: { open: boolean, onOpenChange(open: boolean): void, close(): void, place: ReturnType<typeof usePhoneSheetPlace> } }}
 *   `mode`: where a desktop's panel is. `peek`: the peek, for the surface (`shown`, `leaving`, `entered`, `exited`,
 *   `panelRef`, `panelHandlers`). `state`: the frame's state now, for a handler that outlives a render. `sheet`: a
 *   phone's, for `PanelSheet`.
 */
export function usePanelFrame({ has, mobile, hidden = false, frameWidth, choice, onChoice, early = false }) {
  const { t } = useI18n();
  // A phone's sheet: closed until its toggle opens it, and kept nowhere.
  const [sheetOpen, setSheetOpen] = useState(false);
  const viewerElement = useContext(ViewerElementContext);
  const sidebarState = { frameWidth, choice, has: has && !mobile, mobile, phoneHas: has };
  const { mode } = sidebarLayout(sidebarState);
  const stateRef = useRef(sidebarState);
  stateRef.current = sidebarState;
  // A peek (`panelPeek.js`): the collapsed panel over the page while a mouse rests on its toggle; never kept. Inside a
  // file viewer it is the page's one peek (`PanelPeekContext`), up from the first frame, its enabled state what this
  // frame says with its toggle (`peekable`); outside one, the frame's own.
  const peekable = has && !mobile && !hidden && mode === "closed";
  const pagePeek = useContext(PanelPeekContext);
  const ownPeek = usePanelPeek({ enabled: !pagePeek && peekable });
  const peek = pagePeek ?? ownPeek;
  const closePeek = peek.close;
  const toggle = useCallback(() => {
    const current = stateRef.current;
    if (current.mobile) { if (current.phoneHas) setSheetOpen(open => !open); return; }
    if (!current.has) return;
    // A click (or ⌘\) while it peeks pins it: the panel opens as a click on a collapsed one always has, where the peek
    // is (no slide: the card becomes the docked panel in place), and that is the person's choice, kept. A peek on its
    // own is none.
    closePeek(false, true);
    onChoice(toggleSidebar(current).open);
  }, [onChoice, closePeek]);
  // Escape puts a peek away, before anything else of the page's (a view's tool in hand, its selection: the view's ladder
  // leaves it to the peek, `lib/popups.js`), after a popup or the search box in it has spent its own.
  useEffect(() => {
    if (!peek.peeking) return undefined;
    const onKeyDown = event => {
      if (event.key !== "Escape" || event.defaultPrevented || hasOpenPopup(peek.panelRef.current)) return;
      event.preventDefault();
      closePeek();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [peek.peeking, peek.panelRef, closePeek]);
  // A phone's: under the navbar, with no scrim (`usePhoneSheetPlace`).
  const closeSheet = useCallback(() => setSheetOpen(false), []);
  const sheetPlace = usePhoneSheetPlace(viewerElement, has && mobile && sheetOpen && !hidden);
  // The toggle, the navbar's (`panelToggles.js`), after its logo. A collapsed panel leaves nothing over the page.
  const platform = useContext(ViewerHostContext)?.environment?.platform;
  const panelOpen = mobile ? sheetOpen : mode === "push";
  const showToggle = has && !hidden;
  const toggles = useMemo(() => (!showToggle ? null : {
    left: { open: panelOpen, label: t(panelOpen ? "flatPanel.hide" : "flatPanel.show"), shortcut: panelShortcut(platform), toggle,
      // Whether it may peek, once the frame has measured its width (before, its mode is not yet known: not said).
      hover: mobile ? null : peek.toggleHandlers, peeking: peek.peeking, peekable: frameWidth > 0 ? peekable : undefined }
  }), [showToggle, panelOpen, platform, toggle, t, mobile, peek.toggleHandlers, peek.peeking, peekable, frameWidth > 0]);
  // Leaving a phone's width (or hidden) puts its sheet away.
  useLayoutEffect(() => { if (!mobile || hidden) setSheetOpen(false); }, [mobile, hidden]);
  usePanelToggles(toggles, { early });
  return { mode, peek, toggle, closePeek, state: stateRef,
    sheet: { open: sheetOpen && !hidden, onOpenChange: setSheetOpen, close: closeSheet, place: sheetPlace } };
}

/**
 * A phone's panel: a sheet from the left (shadcn's Sheet) in the viewer's element, under the navbar and over the page
 * with no scrim, 85% of the width and at most 20rem, sliding in and out as the peek does (100ms in, 80ms out:
 * `PANEL_SHEET_LEFT_CLASS`). A tap outside it, a swipe back to the left or Escape put it away; the focus goes back to
 * the navbar's toggle (`usePhoneSheetPlace.js`). `children`: the panel's surface, as a page (`PanelSurface`'s "page").
 * @param {{ sheet: ReturnType<typeof usePanelFrame>["sheet"], label: string, children: import("react").ReactNode }} props
 */
export function PanelSheet({ sheet, label, children }) {
  const viewerElement = useContext(ViewerElementContext);
  return <Sheet open={sheet.open} onOpenChange={sheet.onOpenChange}>
    <SheetContent side="left" showCloseButton={false} onSwipeClose={sheet.close} container={viewerElement?.current ?? undefined}
      scrim={false} animated={false} style={sheet.place.style} overlayStyle={sheet.place.style} onCloseAutoFocus={sheet.place.onCloseAutoFocus}
      onPointerDownOutside={sheet.place.onPointerDownOutside}
      aria-describedby={undefined} className={cn("h-auto w-[85%] max-w-[20rem] gap-0 overflow-hidden border-border p-0", PANEL_SHEET_LEFT_CLASS)} data-panel-sheet="">
      <SheetTitle className="sr-only">{label}</SheetTitle>
      {children}
    </SheetContent>
  </Sheet>;
}
