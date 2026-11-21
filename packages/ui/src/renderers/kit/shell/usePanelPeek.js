import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { hasOpenPopup } from "../../../lib/popups.js";

// The collapsed panel's peek (`ViewFrame.jsx`): a mouse resting on the navbar's panel toggle shows the panel over the
// view, as a sidebar that is not pinned shows itself in VS Code and Linear, so a glance at the file's tree never
// resizes the picture or moves its camera. It opens after the pointer has rested on the toggle `PANEL_PEEK_DELAY_MS`,
// never while a button is held (a drag passing over it), and only for a pointer that hovers (a mouse or a pen: a
// finger's press is a click, which opens the panel as it always has). It goes once the pointer has been outside both
// the toggle and the panel for the same delay, so the pointer can travel from the button down into the panel; it
// stays while the pointer is in either, and while a popup opened from it is up (a tab's dropdown, ⋯: the pointer is in
// that popup then), checked again after each delay. The keyboard in it does not hold it: what goes, goes, its focus
// handed to the toggle. Only the toggle pins it (a click, or its key ⌘\: the frame's toggle); nothing done inside it
// does (a pick, a tab, a search, a slider). Escape or a press on the model put it away (the frame's). Nothing of it is
// ever kept. It slides in as it opens and back out as it goes (`PanelSurface.jsx`), and is gone once it is out
// (`exited`, or `PANEL_PEEK_EXIT_FALLBACK_MS` should the animation's end never come); while it slides out, the pointer
// back on the toggle or the card brings it back at once. Pinned, it goes at once (the docked panel takes its place),
// and so it does where motion is not welcome.
//
// Importing this module has no environmental effects.

/** How long the pointer rests on the toggle before the panel peeks, and how long it is away before the peek goes. */
export const PANEL_PEEK_DELAY_MS = 500;
/** The longest a peek sliding out (150ms) stays mounted when its animation's end is never heard. */
export const PANEL_PEEK_EXIT_FALLBACK_MS = 250;

/** Whether the person asks for less motion: a peek then appears and goes without sliding. */
export const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

/** A pointer that can rest over a control without pressing it. */
const hovers = event => event.pointerType === "mouse" || event.pointerType === "pen";

/**
 * @param {{ enabled: boolean }} options  `enabled`: the panel is collapsed and could peek (a desktop's docked panel,
 *   not in Preview). Turned off, a peek goes at once.
 * @returns {{ peeking: boolean, shown: boolean, leaving: boolean, exited(): void, close(refocus?: boolean, instant?: boolean): void,
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
  // Out: off the screen, and off the tree.
  const exited = useCallback(() => { clearTimeout(exitTimer.current); exitTimer.current = null; setLeaving(false); }, []);
  const show = () => { exited(); setPeeking(true); };
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
      if (held()) { timer.current = setTimeout(fire, PANEL_PEEK_DELAY_MS); return; }
      hide();
    };
    timer.current = setTimeout(fire, PANEL_PEEK_DELAY_MS);
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
          if (enabledRef.current && inside.current.toggle) setPeeking(true);
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
  useEffect(() => () => { clear(); clearTimeout(exitTimer.current); }, []);
  return { peeking: peeking && enabled, shown: (peeking || leaving) && enabled, leaving: leaving && enabled, exited, close,
    toggleHandlers: handlers.toggle, panelHandlers: handlers.panel, panelRef };
}

/**
 * A card that comes and goes as the peek does (`PanelSurface.jsx`'s `peekSlideClass`): on screen while `open`, and
 * while it slides out after (`leaving`), until `exited` is called at the slide's end (or `PANEL_PEEK_EXIT_FALLBACK_MS`
 * should that end never come); gone at once where motion is not welcome.
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
