import { createContext, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { hasOpenPopup } from "../lib/popups.js";

// The collapsed panel's peek (`ViewFrame.jsx`): a mouse resting on the navbar's panel toggle shows the panel over the
// view, as a sidebar that is not pinned shows itself in VS Code and Linear, so a glance at the file's tree never
// resizes the picture or moves its camera. It opens after the pointer has rested on the toggle `PANEL_PEEK_DELAY_MS`,
// never while a button is held (a drag passing over it), and only for a pointer that hovers (a mouse or a pen: a
// finger's press is a click, which opens the panel as it always has). It goes once the pointer has been outside both
// the toggle and the panel for `PANEL_PEEK_LEAVE_MS`, so the pointer can travel from the button down into the panel; it
// stays while the pointer is in either, and while a popup opened from it is up (a tab's dropdown, ⋯: the pointer is in
// that popup then), checked again after each delay. The keyboard in it does not hold it: what goes, goes, its focus
// handed to the toggle. Only the toggle pins it (a click, or its key ⌘\: the frame's toggle); nothing done inside it
// does (a pick, a tab, a search, a slider). Escape or a press on the model put it away (the frame's). Nothing of it is
// ever kept. It slides in as it opens and back out as it goes (`PanelSurface.jsx`, and the file viewer's stand-in before the
// view is up), and is gone once it is out (`exited`, or `PANEL_PEEK_EXIT_FALLBACK_MS` should the animation's end never come); while it slides out, the pointer
// back on the toggle or the card brings it back at once. Pinned, it goes at once (the docked panel takes its place),
// and so it does where motion is not welcome.
//

//
// ONE peek for the page: the file viewer (`FileViewer.tsx`) holds it from the page's first frame, the navbar's stand-in
// toggle and panel using it while the file loads, and hands it to the view's frame (`PanelPeekContext`), which takes the
// card over where it stands: a peek up as the view arrives stays up, with no flicker and no second slide. A frame drawn
// outside a file viewer holds its own. Here, in the file viewer, so both may import it (as `panelToggles.js` is).
//
// Its look and motion are here too, the ONE source for every card that slides in as it does (the view's panel,
// the stand-in, and any card mirroring it): the durations, the easing and the classes that carry them.
//
// Importing this module has no environmental effects.

/** How long the pointer rests on the toggle before the panel peeks: long enough that passing over it opens nothing. */
export const PANEL_PEEK_DELAY_MS = 250;
/** How long the pointer is away from the toggle and the panel before the peek goes: room to cross the gap between them. */
export const PANEL_PEEK_LEAVE_MS = 150;
/** The slide in: quick, eased out (it arrives fast and settles). */
export const PANEL_PEEK_IN_MS = 100;
/** The slide out: quicker, eased in (it gathers speed as it goes). */
export const PANEL_PEEK_OUT_MS = 80;
/** The longest a peek sliding out stays mounted when its animation's end is never heard. */
export const PANEL_PEEK_EXIT_FALLBACK_MS = PANEL_PEEK_OUT_MS + 100;
/**
 * The slides, as classes (tw-animate's, a transform: nothing is laid out again): their durations are the constants
 * above, written out so the stylesheet has them (`panelPeek.test.js` holds the two the same). Where motion is not
 * welcome a peek appears and goes (`motion-reduce`). A card that mirrors the panel's peek takes these, with
 * `slide-in-from-right`/`slide-out-to-right` added for the other side.
 */
export const PANEL_PEEK_IN_CLASS = "animate-in duration-100 ease-out motion-reduce:animate-none";
export const PANEL_PEEK_OUT_CLASS = "animate-out fill-mode-forwards duration-80 ease-in motion-reduce:animate-none";
/** The panel's, from the left. */
export const PANEL_PEEK_IN_LEFT_CLASS = `${PANEL_PEEK_IN_CLASS} slide-in-from-left`;
export const PANEL_PEEK_OUT_LEFT_CLASS = `${PANEL_PEEK_OUT_CLASS} slide-out-to-left`;
/** A card docked at the view's right edge, the peek's mirror (`kit/view-settings/SettingsCard.jsx`), from the right. */
export const PANEL_PEEK_IN_RIGHT_CLASS = `${PANEL_PEEK_IN_CLASS} slide-in-from-right`;
export const PANEL_PEEK_OUT_RIGHT_CLASS = `${PANEL_PEEK_OUT_CLASS} slide-out-to-right`;
/** The same slide for a sheet that opens and closes by its `data-state` (a phone's sidebar, from the left): written out
 * whole so the stylesheet sees it; `panelPeek.test.js` holds its durations to the peek's. */
export const PANEL_SHEET_LEFT_CLASS = "data-[state=open]:animate-in data-[state=open]:slide-in-from-left data-[state=open]:duration-100 "
  + "data-[state=open]:ease-out data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left data-[state=closed]:duration-80 "
  + "data-[state=closed]:ease-in data-[state=closed]:fill-mode-forwards motion-reduce:animate-none";

/** A peeking panel's elevation over the view: the floating chrome's shadow (`lib/floatingSurface.js`'s `shadow-md`). */
export const PANEL_PEEK_ELEVATION_CLASS = "shadow-md";
/**
 * A peeking panel is a card floating over the view (as other apps' unpinned sidebars are), so it reads as
 * hovering: its surface stands this far in from the window's left edge, the navbar's bottom and the view's bottom, its
 * right edge this far short of the docked panel's, with the floating chrome's rounded corners (the strip's 10px), border
 * and shadow, on the chrome's colour. Its content does not move: the panel's box is the docked one, and the card is drawn
 * behind it, its content clipped to the card's inside, so every tab, row and control stands where it does docked. 4px
 * leaves a row's fill (8px out from the content line) 3px of the card's inside at the left and 4px at the right.
 */
export const PANEL_PEEK_GAP_PX = 4;
export const PANEL_PEEK_RADIUS_PX = 10;
/** The card, in the panel's padding box (its right 1px is the docked panel's rule, kept transparent so the content's width holds). */
export const PANEL_PEEK_CARD_STYLE = Object.freeze({ inset: `${PANEL_PEEK_GAP_PX}px ${PANEL_PEEK_GAP_PX - 1}px ${PANEL_PEEK_GAP_PX}px ${PANEL_PEEK_GAP_PX}px`,
  borderRadius: PANEL_PEEK_RADIUS_PX });
/** The content, clipped to the card's inside (within its 1px border). */
export const PANEL_PEEK_CONTENT_STYLE = Object.freeze({ clipPath: `inset(${PANEL_PEEK_GAP_PX + 1}px ${PANEL_PEEK_GAP_PX}px ${PANEL_PEEK_GAP_PX + 1}px ${PANEL_PEEK_GAP_PX + 1}px round ${PANEL_PEEK_RADIUS_PX - 1}px)` });
/** The card's own classes (behind the content). */
export const PANEL_PEEK_CARD_CLASS = `pointer-events-none absolute border border-border bg-sidebar ${PANEL_PEEK_ELEVATION_CLASS}`;
/** A peek's aside: over the view at the docked panel's place, taking no room. */
export const PANEL_PEEK_ASIDE_CLASS = "absolute inset-y-0 left-0 z-40 border-r border-transparent";
/**
 * A peek's motion class now: sliding out while it goes, sliding in until it has arrived (`entered`), and none once it
 * stands, so a surface that takes over a card already standing (the view's, from the stand-in) does not slide again.
 */
export const panelPeekMotionClass = ({ leaving, entered }) => (leaving ? PANEL_PEEK_OUT_LEFT_CLASS : entered ? "" : PANEL_PEEK_IN_LEFT_CLASS);

/**
 * The page's one peek, where a file viewer holds it (`FileViewer.tsx`): a view's frame inside it uses this one, not its
 * own. Its enabled state is the toggle's (`PanelToggle`'s `peekable`), said by whoever draws the toggle now.
 * @type {import("react").Context<ReturnType<typeof usePanelPeek> | null>}
 */
export const PanelPeekContext = createContext(/** @type {any} */ (null));

/** Whether the person asks for less motion: a peek then appears and goes without sliding. */
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

/** A pointer that can rest over a control without pressing it. */
const hovers = event => event.pointerType === "mouse" || event.pointerType === "pen";

/**
 * @param {{ enabled: boolean }} options  `enabled`: the panel is collapsed and could peek (a desktop's docked panel,
 *   not in Preview). Turned off, a peek goes at once.
 * @returns {{ peeking: boolean, shown: boolean, leaving: boolean, entered: boolean, exited(): void, close(refocus?: boolean, instant?: boolean): void,
 *   toggleHandlers: object, panelHandlers: object, panelRef: { current: HTMLElement | null } }}
 *   `peeking`: up (not going); `shown`: on screen, sliding out included (`leaving`), until `exited` is called (the
 *   slide's end). `toggleHandlers` go on the navbar's toggle, `panelHandlers` and `panelRef` on the panel's surface.
 */
export function usePanelPeek({ enabled }) {
  const [peeking, setPeeking] = useState(false);
  const peekingRef = useRef(false);
  peekingRef.current = peeking;
  const [leaving, setLeaving] = useState(false);
  const leavingRef = useRef(false);
  leavingRef.current = leaving;
  const exitTimer = useRef(null);
  // Arrived: its slide in has played (`PANEL_PEEK_IN_MS` after it came up), so a surface taking it over stands still.
  const [entered, setEntered] = useState(false);
  const enterTimer = useRef(null);
  const arrive = () => {
    clearTimeout(enterTimer.current);
    setEntered(false);
    enterTimer.current = setTimeout(() => { enterTimer.current = null; setEntered(true); }, PANEL_PEEK_IN_MS);
  };
  // Out: off the screen, and off the tree.
  const exited = useCallback(() => {
    clearTimeout(exitTimer.current); exitTimer.current = null; setLeaving(false);
    if (!peekingRef.current) { clearTimeout(enterTimer.current); enterTimer.current = null; setEntered(false); }
  }, []);
  const show = () => { exited(); setPeeking(true); arrive(); };
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const timer = useRef(null);
  // Where the pointer is: on the toggle, in the panel.
  const inside = useRef({ toggle: false, panel: false });
  const panelRef = useRef(null);
  // The toggle, where the keyboard goes when the peek goes from under it.
  const toggleRef = useRef(null);
  const clear = () => { clearTimeout(timer.current); timer.current = null; };
  // Going, a peek hands the keyboard, if it was in it, to the toggle, so it is never left on a panel that is gone. It
  // slides out, unless `instant` (a pin: the docked panel takes its place) or motion is not welcome.
  const hide = (refocus = true, instant = false) => {
    const panel = panelRef.current, focused = typeof document === "undefined" ? null : document.activeElement;
    if (refocus && panel && focused && panel.contains(focused)) toggleRef.current?.focus({ preventScroll: true });
    setPeeking(false);
    if (instant || reducedMotion()) { exited(); return; }
    setLeaving(true);
    clearTimeout(exitTimer.current);
    exitTimer.current = setTimeout(exited, PANEL_PEEK_EXIT_FALLBACK_MS);
  };
  // Put away (Escape, a press on the model, a pin): the panel it leaves is gone from under the pointer. `refocus`
  // false where the keyboard goes elsewhere anyway (a pin keeps the panel; a press on the model takes it); `instant`
  // for a pin, which leaves the panel where it is, docked.
  const close = useCallback((refocus = true, instant = false) => {
    clear();
    inside.current.panel = false;
    if (peekingRef.current) hide(refocus, instant); else if (instant) exited();
  }, []);
  // The one thing that holds it up: a popup opened from it (the pointer is in that popup).
  const held = () => hasOpenPopup(panelRef.current);
  const armClose = () => {
    clear();
    const fire = () => {
      timer.current = null;
      if (inside.current.toggle || inside.current.panel) return;
      if (held()) { timer.current = setTimeout(fire, PANEL_PEEK_LEAVE_MS); return; }
      hide();
    };
    timer.current = setTimeout(fire, PANEL_PEEK_LEAVE_MS);
  };
  const handlers = useMemo(() => ({
    toggle: {
      onPointerEnter(event) {
        if (!hovers(event)) return;
        toggleRef.current = event.currentTarget;
        inside.current.toggle = true;
        if (peekingRef.current) { clear(); return; }
        // Back on the toggle while it slides out: it comes back at once.
        if (leavingRef.current && enabledRef.current) { clear(); show(); return; }
        if (!enabledRef.current || event.buttons) return;
        clear();
        timer.current = setTimeout(() => {
          timer.current = null;
          if (enabledRef.current && inside.current.toggle) { setPeeking(true); arrive(); }
        }, PANEL_PEEK_DELAY_MS);
      },
      onPointerLeave() {
        inside.current.toggle = false;
        if (peekingRef.current) armClose(); else clear();
      },
      // A press on the toggle is its click's (it opens or pins the panel): a rest under way gives way to it.
      onPointerDown() { if (!peekingRef.current) clear(); }
    },
    panel: {
      onPointerEnter() {
        inside.current.panel = true;
        if (peekingRef.current) clear();
        else if (leavingRef.current && enabledRef.current) show();
      },
      onPointerLeave() {
        inside.current.panel = false;
        if (peekingRef.current && !inside.current.toggle) armClose();
      }
    }
  }), []);
  // Pinned (or gone to a phone, or Preview): the peek goes, the panel, if pinned, keeping the keyboard where it is.
  useEffect(() => { if (!enabled) close(false, true); }, [enabled, close]);
  useEffect(() => () => { clear(); clearTimeout(exitTimer.current); clearTimeout(enterTimer.current); }, []);
  return { peeking: peeking && enabled, shown: (peeking || leaving) && enabled, leaving: leaving && enabled, entered, exited, close,
    toggleHandlers: handlers.toggle, panelHandlers: handlers.panel, panelRef };
}

/**
 * A card that comes and goes as the peek does (`PANEL_PEEK_IN_RIGHT_CLASS`, `PANEL_PEEK_OUT_RIGHT_CLASS`): on screen
 * while `open`, and while it slides out after (`leaving`), until `exited` is called at the slide's end (or
 * `PANEL_PEEK_EXIT_FALLBACK_MS` should that end never come); gone at once where motion is not welcome.
 * @param {boolean} open
 * @returns {{ shown: boolean, leaving: boolean, exited(): void }}
 */
export function useSlidingCard(open) {
  const [state, setState] = useState({ open, leaving: false });
  if (state.open !== open) setState({ open, leaving: !open && !reducedMotion() });
  const exited = useCallback(() => setState(now => (now.leaving ? { ...now, leaving: false } : now)), []);
  const leaving = !open && state.leaving;
  useEffect(() => {
    if (!leaving) return undefined;
    const timer = setTimeout(exited, PANEL_PEEK_EXIT_FALLBACK_MS);
    return () => clearTimeout(timer);
  }, [leaving, exited]);
  return { shown: open || leaving, leaving, exited };
}
