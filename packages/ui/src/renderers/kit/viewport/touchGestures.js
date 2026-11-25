import { useEffect } from "react";

// A finger's gestures on a view's picture, in ONE place for every 2D and 3D view (`ViewFrame.jsx` installs it on its
// root): what a mouse says with a button a finger says with time, and this says it back in the mouse's words, so the
// view's own handlers stay the only ones.
//
// - A double tap (two taps, each a press lifted within `TAP_MAX_MS` and moved no more than `TAP_SLOP_PX`, the second
//   within `DOUBLE_TAP_MS` of the first and `DOUBLE_TAP_SLOP_PX` of it) is a double-click: a `dblclick` at the second
//   tap's point on the canvas it landed on, so isolate, focus and fit do what a double-click does, with the same hit
//   test. A browser that sends its own `dblclick` for it (Android's Chrome) has that one dropped: one double-click.
// - A long press (one finger held `LONG_PRESS_MS` without moving more than `TAP_SLOP_PX`) is a right-click: a
//   `LONG_PRESS_EVENT` at the press's point on the canvas, which the viewport's menu opens on
//   (`ViewportContextMenu.jsx`), as a secondary press. The press is then the menu's: what it started on the canvas
//   (an orbit, a box) is cancelled (`pointercancel`), and its lift and click reach nothing.
// - A second finger, a move past the slop or the browser cancelling the touch makes it none of these (a pinch, a pan,
//   an orbit).
// A mouse and a pen are left alone: they have buttons. Only presses on a canvas count: a control drawn over the
// picture keeps its own.
//
// Importing this module has no environmental effects.

export const TAP_SLOP_PX = 10;
export const TAP_MAX_MS = 350;
export const DOUBLE_TAP_MS = 300;
/**
 * How long a mouse's click that would take the selection away waits for the click that would make it a double-click
 * (`usePointerPick`'s `takesAway`, an engine document's `clickActivation.js`): a double-click never shows the selection
 * going and coming back. A finger's wait is its double tap's, `DOUBLE_TAP_MS`.
 */
export const DOUBLE_CLICK_WAIT_MS = 220;
export const DOUBLE_TAP_SLOP_PX = 24;
export const LONG_PRESS_MS = 500;
/** The long press's event, on the canvas pressed: `{ detail: { clientX, clientY } }`, bubbling. */
export const LONG_PRESS_EVENT = "cad-long-press";
// How long after a double tap the browser's own `dblclick` for it is dropped.
const NATIVE_DOUBLE_CLICK_MS = 600;

const onCanvas = target => typeof HTMLCanvasElement !== "undefined" && target instanceof HTMLCanvasElement;

/**
 * Listens on `root` (capture) and says a finger's double taps and long presses on its canvases in the mouse's words.
 * @param {HTMLElement} root
 * @returns {() => void} Stops listening.
 */
export function listenTouchGestures(root) {
  const view = root.ownerDocument?.defaultView ?? window;
  const fingers = new Set();
  let press = null;          // the one finger down: { id, x, y, at, target, timer, moved, long }
  let lastTap = null;        // { x, y, at }
  let synthetic = -Infinity; // when this last sent a dblclick
  let swallowClick = false;
  const reset = () => { if (press) clearTimeout(press.timer); press = null; };
  const down = event => {
    if (event.pointerType !== "touch") return;
    fingers.add(event.pointerId);
    // A second finger: a pinch or a two-finger pan, never a tap or a long press.
    if (fingers.size > 1 || !onCanvas(event.target)) { reset(); lastTap = null; return; }
    const started = { id: event.pointerId, x: event.clientX, y: event.clientY, at: event.timeStamp, target: event.target, moved: false, long: false, timer: 0 };
    started.timer = setTimeout(() => {
      if (press !== started || started.moved) return;
      started.long = true;
      lastTap = null;
      // What the press started on the canvas (an orbit, a box being drawn) goes: the press is the menu's.
      started.target.dispatchEvent(new view.PointerEvent("pointercancel", { pointerId: started.id, pointerType: "touch", isPrimary: true, bubbles: true }));
      started.target.dispatchEvent(new view.CustomEvent(LONG_PRESS_EVENT, { bubbles: true, detail: { clientX: started.x, clientY: started.y } }));
    }, LONG_PRESS_MS);
    press = started;
  };
  const move = event => {
    if (!press || event.pointerId !== press.id || press.moved) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > TAP_SLOP_PX) { press.moved = true; clearTimeout(press.timer); }
  };
  const up = event => {
    if (event.pointerType !== "touch") return;
    fingers.delete(event.pointerId);
    const ended = press;
    if (!ended || event.pointerId !== ended.id) return;
    reset();
    if (ended.long) {
      // The lift of a long press, and its click, are the menu's: nothing under it sees them.
      event.stopPropagation();
      swallowClick = true;
      return;
    }
    if (ended.moved || event.timeStamp - ended.at > TAP_MAX_MS) { lastTap = null; return; }
    const tap = { x: event.clientX, y: event.clientY, at: event.timeStamp };
    if (lastTap && tap.at - lastTap.at <= DOUBLE_TAP_MS && Math.hypot(tap.x - lastTap.x, tap.y - lastTap.y) <= DOUBLE_TAP_SLOP_PX) {
      lastTap = null;
      synthetic = event.timeStamp;
      const target = ended.target;
      // After this lift's own handlers (and its click, a tap's select), as a mouse's dblclick comes after its second click.
      setTimeout(() => {
        if (!target.isConnected) return;
        target.dispatchEvent(new view.MouseEvent("dblclick", { bubbles: true, cancelable: true, composed: true, detail: 2, clientX: tap.x, clientY: tap.y, view }));
      });
      return;
    }
    lastTap = tap;
  };
  const cancel = event => {
    fingers.delete(event.pointerId);
    // Our own cancel of a long press is not the browser's.
    if (press && event.pointerId === press.id && !press.long) { reset(); lastTap = null; }
  };
  const click = event => {
    if (!swallowClick) return;
    swallowClick = false;
    event.stopPropagation();
    event.preventDefault();
  };
  const doubleClick = event => {
    // The browser's own double-click for a double tap this already said.
    if (event.isTrusted && event.timeStamp - synthetic < NATIVE_DOUBLE_CLICK_MS) { event.stopPropagation(); event.preventDefault(); }
  };
  root.addEventListener("pointerdown", down, true);
  root.addEventListener("pointermove", move, true);
  root.addEventListener("pointerup", up, true);
  root.addEventListener("pointercancel", cancel, true);
  root.addEventListener("click", click, true);
  root.addEventListener("dblclick", doubleClick, true);
  return () => {
    reset();
    root.removeEventListener("pointerdown", down, true);
    root.removeEventListener("pointermove", move, true);
    root.removeEventListener("pointerup", up, true);
    root.removeEventListener("pointercancel", cancel, true);
    root.removeEventListener("click", click, true);
    root.removeEventListener("dblclick", doubleClick, true);
  };
}

/** `listenTouchGestures` on `rootRef`'s element while it is mounted. */
export function useTouchGestures(rootRef) {
  useEffect(() => {
    const root = rootRef?.current;
    if (!root) return undefined;
    return listenTouchGestures(root);
  }, [rootRef]);
}
