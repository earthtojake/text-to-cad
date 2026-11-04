import { useEffect, useRef } from "react";
import { boxFromDrag } from "@cad/core/lib/viewer/boxSelect.js";
import { prefersCoarsePointer } from "../../viewport/dom.js";
import { capturePointer, releasePointer } from "../../../../lib/pointerCapture.js";

const FINE_DRAG_SLOP_PX = 4;
const COARSE_DRAG_SLOP_PX = 12;
// The box, in the selection's blue.
const BOX_STYLE = Object.freeze({ border: "1px solid #2979ff", background: "rgba(41, 121, 255, 0.12)" });

/**
 * The gesture of Select's Box select tool: a drag over the canvas draws a box instead of turning the
 * camera, and its release hands the box to the renderer (`onBox`). A press that does not move past
 * the tap slop is left exactly as it was — the renderer's own picking takes it as a click — so a
 * click still picks and a double-click still isolates.
 *
 * The press is seen before OrbitControls sees it (capture phase, above the WebGL canvas), and the
 * controls are switched off for that one press: a left drag draws the box, Shift + drag adds to the
 * selection rather than panning, and every other camera gesture is the camera's (the wheel, a right
 * or middle drag, Ctrl or Cmd + drag). A second finger ends the box, and the camera stays still
 * until every finger has lifted. Escape drops a box being drawn.
 *
 * Nothing here is React state: the box is one element drawn straight into the viewport's host.
 *
 * @param {{ runtimeRef: { current: object | null }, hostRef: { current: HTMLElement | null },
 *   viewerReadyTick: number }} viewport  What `RendererShell`'s `viewportOverlay` render prop is given.
 * @param {boolean} enabled  Box select is the tool in hand.
 * @param {(box: ReturnType<typeof boxFromDrag> & { additive: boolean }) => void} onBox  The box drawn,
 *   in the viewport's CSS pixels (its top-left (0, 0)); `additive` when Shift was held at the press
 *   or the release.
 */
export function useBoxSelectGesture({ runtimeRef, hostRef, viewerReadyTick }, enabled, onBox) {
  const onBoxRef = useRef(onBox);
  onBoxRef.current = onBox;

  useEffect(() => {
    const host = hostRef.current;
    if (!enabled || !host || !runtimeRef.current) return undefined;
    const coarseDefault = prefersCoarsePointer();
    const touches = new Set();
    // { pointerId, pointerType, start, end, dragging, shiftKey }, in the viewport's pixels.
    let press = null;
    // A gesture this hook has taken the camera from, for as long as any finger is still down.
    let held = null;
    let element = null;

    const onCanvas = event => event.target === runtimeRef.current?.renderer?.domElement;
    const slop = pointerType => (pointerType === "touch" || pointerType === "pen" || coarseDefault ? COARSE_DRAG_SLOP_PX : FINE_DRAG_SLOP_PX);
    const local = (event) => {
      const rect = host.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };

    const draw = () => {
      if (!press?.dragging) return;
      const box = boxFromDrag(press.start, press.end);
      if (!element) {
        element = document.createElement("div");
        element.setAttribute("data-box-select", "");
        element.setAttribute("aria-hidden", "true");
        Object.assign(element.style, BOX_STYLE, { position: "absolute", pointerEvents: "none", zIndex: "30", boxSizing: "border-box" });
        host.appendChild(element);
      }
      Object.assign(element.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
    };
    const erase = () => {
      element?.remove();
      element = null;
    };
    const giveBackCamera = () => {
      if (!held) return;
      const controls = runtimeRef.current?.controls;
      if (controls) controls.enabled = held.controlsWereEnabled;
      held = null;
    };
    const end = () => {
      if (press) releasePointer(host, press.pointerId);
      press = null;
      erase();
      host.style.cursor = "";
      if (!touches.size) giveBackCamera();
    };

    const handlePointerDown = (event) => {
      if (event.pointerType === "touch") {
        touches.add(event.pointerId);
        // A second finger: no box, and no camera either until the fingers lift.
        if (touches.size > 1) { end(); return; }
      }
      if (press || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || !onCanvas(event)) return;
      const controls = runtimeRef.current?.controls;
      held = { controlsWereEnabled: controls?.enabled !== false };
      if (controls) controls.enabled = false;
      const at = local(event);
      press = { pointerId: event.pointerId, pointerType: event.pointerType || "", start: at, end: at, dragging: false, shiftKey: Boolean(event.shiftKey) };
    };
    const handlePointerMove = (event) => {
      if (!press || event.pointerId !== press.pointerId) return;
      press.end = local(event);
      if (!press.dragging) {
        if (Math.hypot(press.end.x - press.start.x, press.end.y - press.start.y) <= slop(press.pointerType)) return;
        press.dragging = true;
        capturePointer(host, press.pointerId);
        host.style.cursor = "crosshair";
      }
      event.preventDefault();
      draw();
    };
    const handlePointerUp = (event) => {
      if (event.pointerType === "touch") touches.delete(event.pointerId);
      if (!press || event.pointerId !== press.pointerId) {
        if (!press && !touches.size) giveBackCamera();
        return;
      }
      const drawn = press.dragging ? { ...boxFromDrag(press.start, local(event)), additive: press.shiftKey || Boolean(event.shiftKey) } : null;
      end();
      if (drawn && drawn.width > 0 && drawn.height > 0) onBoxRef.current?.(drawn);
    };
    const handlePointerCancel = (event) => {
      touches.delete(event.pointerId);
      if (press && event.pointerId === press.pointerId) end();
      else if (!press && !touches.size) giveBackCamera();
    };
    const handleKeyDown = (event) => {
      if (event.key !== "Escape" || !press?.dragging) return;
      event.preventDefault();
      event.stopPropagation();
      end();
    };

    host.addEventListener("pointerdown", handlePointerDown, true);
    host.addEventListener("pointermove", handlePointerMove, true);
    host.addEventListener("pointerup", handlePointerUp, true);
    host.addEventListener("pointercancel", handlePointerCancel, true);
    host.addEventListener("lostpointercapture", handlePointerCancel, true);
    window.addEventListener("keydown", handleKeyDown, true);
    return () => {
      host.removeEventListener("pointerdown", handlePointerDown, true);
      host.removeEventListener("pointermove", handlePointerMove, true);
      host.removeEventListener("pointerup", handlePointerUp, true);
      host.removeEventListener("pointercancel", handlePointerCancel, true);
      host.removeEventListener("lostpointercapture", handlePointerCancel, true);
      window.removeEventListener("keydown", handleKeyDown, true);
      // Leaving the tool mid-drag hands the camera back.
      touches.clear();
      end();
    };
  }, [runtimeRef, hostRef, viewerReadyTick, enabled]);
}

/** `useBoxSelectGesture` as the element a `viewportOverlay` render prop returns: it draws nothing of its own. */
export function BoxSelectGesture({ viewport, enabled, onBox }) {
  useBoxSelectGesture(viewport, enabled, onBox);
  return null;
}
