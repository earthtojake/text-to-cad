import { useEffect, useRef } from "react";
import { prefersCoarsePointer } from "../../viewport/dom.js";

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
 * A tap acts at once: there is no wait to tell it from a double-click. A renderer
 * that gives a second click its own meaning counts clicks in `onPick`.
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
 * @param {boolean} options.enabled  The renderer's selecting tool is active (never in fullscreen, never under Draw).
 * @param {(hit: object | null, modifiers: { multiSelect: boolean }) => void} options.onPick  A tap. Shift adds.
 * @param {(hit: object | null) => void} [options.onHover]  The pick under a resting fine pointer changed.
 * @param {(left: object | null, right: object | null) => boolean} [options.sameHit]  When two hover hits are
 *   the same thing to the renderer (default: equal `id`), so `onHover` fires on change only.
 */
export function usePointerPick({ viewport, scene, enabled, onPick, onHover = null, sameHit = null }) {
  const callbacks = useRef(null);
  callbacks.current = { onPick, onHover, sameHit };
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
    const same = (left, right) => callbacks.current.sameHit ? callbacks.current.sameHit(left, right) : (left?.id || "") === (right?.id || "");
    const setHover = (hit) => {
      if (same(hovered, hit)) return;
      hovered = hit;
      host.style.cursor = hit ? "pointer" : "";
      callbacks.current.onHover?.(hit);
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
      callbacks.current.onPick(pickAt(started.x, started.y), { multiSelect: Boolean(event.shiftKey) });
    };
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
        setHover(pickAt(hoverAt.x, hoverAt.y));
      });
    };
    const handlePointerLeave = () => { pendingHover = null; hoverAt = null; setHover(null); };
    const handlePointerCancel = event => { touches.delete(event.pointerId); press = null; };

    host.addEventListener("pointerdown", handlePointerDown);
    host.addEventListener("pointerup", handlePointerUp);
    host.addEventListener("pointercancel", handlePointerCancel);
    host.addEventListener("pointermove", handlePointerMove);
    host.addEventListener("pointerleave", handlePointerLeave);
    return () => {
      host.removeEventListener("pointerdown", handlePointerDown);
      host.removeEventListener("pointerup", handlePointerUp);
      host.removeEventListener("pointercancel", handlePointerCancel);
      host.removeEventListener("pointermove", handlePointerMove);
      host.removeEventListener("pointerleave", handlePointerLeave);
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
