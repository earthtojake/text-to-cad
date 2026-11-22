import { useEffect, useRef } from "react";
import { prefersCoarsePointer } from "../../viewport/dom.js";
import { DOUBLE_CLICK_WAIT_MS, DOUBLE_TAP_MS } from "../../viewport/touchGestures.js";

const HOVER_MIN_MOVE_PX = 2;
const FINE_TAP_SLOP_PX = 4;
const COARSE_TAP_SLOP_PX = 12;

/**
 * Picking for a scene that selects, through the scene contract's `pick(ray)`
 * (`kit/scene.js`). The hook owns the pointer side only: which press is a tap and
 * not the start of a camera drag, one hover pick per animation frame, the cursor.
 * What a hit MEANS is its renderer's, which gets `{ id, point, ... }` exactly as
 * its scene returned it (or null for a press or a pointer over nothing).
 *
 * A tap acts at once, but for one that would take the selection away (`takesAway`: the thing selected pressed
 * again, or a finger's tap on it): that one waits the double-click window (`DOUBLE_CLICK_WAIT_MS`, a finger's
 * `DOUBLE_TAP_MS`) and a double-click drops it, so a double-click never shows the selection going and coming back.
 * A tap on something else in the window lets the waiting one act first; a lone one acts once the window has passed.
 * A renderer that gives a second click its own meaning counts clicks in `onPick`.
 *
 * Nothing here is React state, and the camera keeps every gesture: listeners are
 * passive observers on the viewport's element, alive only while `enabled`.
 *
 * @param {object} options
 * @param {{ runtimeRef: { current: object | null }, hostRef: { current: HTMLElement | null },
 *   mountRef: { current: HTMLElement | null }, viewerReadyTick: number,
 *   commitScene: () => boolean }} options.viewport
 *   What `RendererShell`'s `viewportOverlay` render prop is given, all five keys. This hook
 *   reads the runtime, the element pointer events arrive on and the ready tick; the mount
 *   element and `commitScene()` belong to a renderer that draws its own layer into the
 *   viewport or publishes a scene that changed in place.
 * @param {import("../../scene.js").KitScene | null} options.scene
 * @param {boolean} options.enabled  The renderer's selecting tool is active (never in preview, never under Annotate).
 * @param {(hit: object | null, modifiers: { multiSelect: boolean }, pointer: Pointer) => void} options.onPick  A tap. Shift adds.
 * @param {(hit: object | null, pointer: Pointer | null) => void} [options.onHover]  The pick under a resting fine pointer changed.
 *   `Pointer`: where the pointer is, in CSS pixels from the viewport's top-left (`x`, `y`), and the
 *   viewport's size (`width`, `height`): what a tool that snaps to the screen (Measure) measures by.
 * @param {boolean} [options.touchAdds]  A selecting picker's: a finger's tap on something adds it to the selection, or
 *   takes it away where it is selected (a finger has no Shift); a finger's tap on nothing is a plain one (it clears).
 * @param {(left: object | null, right: object | null) => boolean} [options.sameHit]  When two hover hits are
 *   the same thing to the renderer (default: equal `id`), so `onHover` fires on change only.
 * @param {(hit: object | null, modifiers: { multiSelect: boolean }) => boolean} [options.takesAway]  Whether this tap
 *   would take something out of the selection: such a tap waits the double-click window (above).
 */
export function usePointerPick({ viewport, scene, enabled, onPick, onHover = null, sameHit = null, touchAdds = false, takesAway = null }) {
  const callbacks = useRef(null);
  callbacks.current = { onPick, onHover, sameHit, touchAdds, takesAway };
  const { runtimeRef, hostRef, viewerReadyTick } = viewport;

  useEffect(() => {
    const host = hostRef.current;
    const runtime = runtimeRef.current;
    if (!enabled || !host || !runtime?.THREE || typeof scene?.pick !== "function") return undefined;
    const raycaster = new runtime.THREE.Raycaster();
    const ndc = new runtime.THREE.Vector2();
    const coarseDefault = prefersCoarsePointer();
    const coarse = pointerType => pointerType === "touch" || pointerType === "pen" || coarseDefault;
    let press = null;
    const touches = new Set();
    let hovered = null;
    let hoverFrame = 0;
    let hoverAt = null;
    let pendingHover = null;
    // A tap that would take the selection away, waiting the double-click window: `{ hit, modifiers, pointer, timer }`.
    let held = null;
    const dropHeld = () => { if (held) window.clearTimeout(held.timer); held = null; };
    const commitHeld = () => {
      const waiting = held;
      dropHeld();
      if (waiting) callbacks.current.onPick(waiting.hit, waiting.modifiers, waiting.pointer);
    };

    // The scene's own canvas only: a control drawn over it keeps its presses.
    const onCanvas = event => event.target === runtimeRef.current?.renderer?.domElement;
    const pickAt = (clientX, clientY) => {
      const live = runtimeRef.current;
      if (!live?.camera) return null;
      const rect = host.getBoundingClientRect();
      if (!(rect.width > 0 && rect.height > 0)) return null;
      live.camera.updateMatrixWorld();
      raycaster.setFromCamera(ndc.set(((clientX - rect.left) / rect.width) * 2 - 1, 1 - ((clientY - rect.top) / rect.height) * 2), live.camera);
      return scene.pick(raycaster.ray) || null;
    };
    const pointerAt = (clientX, clientY) => {
      const rect = host.getBoundingClientRect();
      return { x: clientX - rect.left, y: clientY - rect.top, width: rect.width, height: rect.height };
    };
    const same = (left, right) => callbacks.current.sameHit ? callbacks.current.sameHit(left, right) : (left?.id || "") === (right?.id || "");
    const setHover = (hit, pointer = null) => {
      if (same(hovered, hit)) return;
      hovered = hit;
      host.style.cursor = hit ? "pointer" : "";
      callbacks.current.onHover?.(hit, pointer);
    };

    const handlePointerDown = (event) => {
      if (event.pointerType === "touch") {
        touches.add(event.pointerId);
        if (touches.size > 1) { press = null; return; }
      }
      press = event.button === 0 && onCanvas(event)
        ? { x: event.clientX, y: event.clientY, pointerId: event.pointerId, pointerType: event.pointerType || "" } : null;
    };
    const handlePointerUp = (event) => {
      touches.delete(event.pointerId);
      const started = press;
      press = null;
      if (!started || event.button !== 0 || event.pointerId !== started.pointerId) return;
      const slop = coarse(started.pointerType) ? COARSE_TAP_SLOP_PX : FINE_TAP_SLOP_PX;
      if (Math.hypot(event.clientX - started.x, event.clientY - started.y) > slop) return;
      const hit = pickAt(started.x, started.y);
      // Whether the tap found something: a hit, or (a scene that answers with a press and a rest) its press.
      const found = Boolean(hit && ("press" in hit ? hit.press : true));
      const touchAdds = callbacks.current.touchAdds && started.pointerType === "touch" && found;
      const modifiers = { multiSelect: Boolean(event.shiftKey) || touchAdds };
      const pointer = pointerAt(started.x, started.y);
      // A second tap on what is waiting is a double-click's second click: the first is dropped, and this one waits
      // in its place for the double-click that drops it. A tap on anything else lets the waiting one act first.
      if (held) { if (same(held.hit, hit)) dropHeld(); else commitHeld(); }
      if (callbacks.current.takesAway?.(hit, modifiers)) {
        held = { hit, modifiers, pointer, timer: window.setTimeout(commitHeld, started.pointerType === "touch" ? DOUBLE_TAP_MS : DOUBLE_CLICK_WAIT_MS) };
        return;
      }
      callbacks.current.onPick(hit, modifiers, pointer);
    };
    // The double-click (a finger's double tap says it too, `touchGestures.js`): the tap waiting for it is dropped.
    const handleDoubleClick = () => dropHeld();
    const handlePointerMove = (event) => {
      if (press?.pointerId === event.pointerId && Math.hypot(event.clientX - press.x, event.clientY - press.y) > (coarse(press.pointerType) ? COARSE_TAP_SLOP_PX : FINE_TAP_SLOP_PX)) press = null;
      // A camera gesture is under way, or the pointer cannot rest: no hover.
      if (event.buttons !== 0 || coarse(event.pointerType || "")) return;
      if (!onCanvas(event)) { pendingHover = null; setHover(null); return; }
      if (hoverAt && Math.hypot(event.clientX - hoverAt.x, event.clientY - hoverAt.y) < HOVER_MIN_MOVE_PX) return;
      pendingHover = { x: event.clientX, y: event.clientY };
      if (hoverFrame) return;
      hoverFrame = window.requestAnimationFrame(() => {
        hoverFrame = 0;
        if (!pendingHover) return;
        hoverAt = pendingHover;
        pendingHover = null;
        setHover(pickAt(hoverAt.x, hoverAt.y), pointerAt(hoverAt.x, hoverAt.y));
      });
    };
    const handlePointerLeave = () => { pendingHover = null; hoverAt = null; setHover(null); };
    const handlePointerCancel = event => { touches.delete(event.pointerId); press = null; };

    host.addEventListener("pointerdown", handlePointerDown);
    host.addEventListener("pointerup", handlePointerUp);
    host.addEventListener("pointercancel", handlePointerCancel);
    host.addEventListener("pointermove", handlePointerMove);
    host.addEventListener("pointerleave", handlePointerLeave);
    host.addEventListener("dblclick", handleDoubleClick);
    return () => {
      host.removeEventListener("pointerdown", handlePointerDown);
      host.removeEventListener("pointerup", handlePointerUp);
      host.removeEventListener("pointercancel", handlePointerCancel);
      host.removeEventListener("pointermove", handlePointerMove);
      host.removeEventListener("pointerleave", handlePointerLeave);
      host.removeEventListener("dblclick", handleDoubleClick);
      // A tap still waiting belongs to the tool it was made under.
      dropHeld();
      window.cancelAnimationFrame(hoverFrame);
      host.style.cursor = "";
      // Leaving the tool leaves nothing hovered.
      if (hovered) callbacks.current.onHover?.(null);
    };
  }, [runtimeRef, hostRef, viewerReadyTick, scene, enabled]);
}

/** `usePointerPick` as the element a `viewportOverlay` render prop returns: it draws nothing. */
export function PointerPick(props) {
  usePointerPick(props);
  return null;
}
