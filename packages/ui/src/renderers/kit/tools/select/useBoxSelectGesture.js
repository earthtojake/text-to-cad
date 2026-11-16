import { useEffect, useRef } from "react";
import { boxFromDrag } from "@cad/core/lib/viewer/boxSelect.js";
import { prefersCoarsePointer } from "../../viewport/dom.js";
import { capturePointer, releasePointer } from "../../../../lib/pointerCapture.js";

const FINE_DRAG_SLOP_PX = 4;
const COARSE_DRAG_SLOP_PX = 12;
// The box's one look, the same in every viewer and whichever way it is drawn: a solid outline in the
// selection's blue over a light fill of it.
const BOX_STYLE = Object.freeze({ border: "1px solid #2979ff", background: "rgba(41, 121, 255, 0.12)" });

/**
 * Box selection's one gesture, in every viewer that has it: a left drag over the canvas draws a box
 * (one element, straight into the viewport's host) instead of moving the view, and its release hands
 * the box on (`onBox`). The box takes whatever it touches, even in part, whichever way it is drawn,
 * and it always looks the same: a solid blue outline (`BOX_STYLE`). Where it may start is the viewer's to say
 * (`mayStart(event)`, asked at the press): a flat view's Select draws a box from anywhere a plain
 * left drag starts, a 3D view's Box select only from empty space (a drag on the model, its ink or a
 * measurement turns the camera, as Select's does). A press that does not move past the tap slop is
 * left exactly as it was -- the viewer's own picking takes it as a click -- so a click still picks
 * and a double-click still does what it does.
 *
 * `RendererShell` mounts it for a 3D renderer that hands it `boxSelect` (the shell takes the
 * annotation's ink in the box, then hands the box on for the model and its measurements); a flat
 * view mounts it through `useFlatBoxSelect` (`flatBoxSelect.js`), over its canvas and its pan.
 *
 * The press is seen before anything else in the page sees it (the window's capture phase), and the
 * camera is switched off for that one press (the viewport runtime's `controls`: OrbitControls, or a
 * flat view's pan, `useFlatCanvasView`'s): a left drag draws the box, and every other camera
 * gesture stays the camera's (the wheel, a right or middle drag, Ctrl, Cmd or Alt + drag, and
 * whatever `mayStart` refuses). The pointer is captured by the canvas the press landed on, so the
 * view under it keeps hearing the press it began. A second finger ends the box, and a 3D camera
 * stays still until every finger has lifted (a flat view's pinch is its own). Escape drops a box
 * being drawn.
 *
 * Nothing here is React state: the box is one element drawn straight into the viewport's host.
 *
 * @param {{ runtimeRef: { current: { renderer?: { domElement?: Element }, controls?: { enabled: boolean } } | null },
 *   hostRef: { current: HTMLElement | null }, viewerReadyTick: number }} viewport  What `RendererShell`'s
 *   `viewportOverlay` render prop is given, or a flat view's stand-in (`useFlatBoxSelect`).
 * @param {{ enabled: boolean, onBox: (box: ReturnType<typeof boxFromDrag> & { client: ReturnType<typeof boxFromDrag>, additive: boolean }) => void,
 *   mayStart?: ((event: PointerEvent) => boolean) | null }} options
 *   `enabled`: a box may be drawn now (the tool in hand). `onBox`: the box drawn, in the viewport's CSS
 *   pixels (its top-left (0, 0)), and the same box in the page's (`client`, as a pointer event's
 *   `clientX`/`clientY`: what the ink and the measurements drawn over the canvas are judged in);
 *   `additive` when Shift was held at the press or the release. `mayStart`: whether a left press with
 *   no Ctrl, Cmd or Alt may start a box; without it, every one may.
 */
export function useBoxSelectGesture({ runtimeRef, hostRef, viewerReadyTick }, { enabled, onBox, mayStart = null }) {
  const onBoxRef = useRef(onBox);
  onBoxRef.current = onBox;
  const mayStartRef = useRef(mayStart);
  mayStartRef.current = mayStart;

  useEffect(() => {
    const host = hostRef.current;
    if (!enabled || !host || !runtimeRef.current) return undefined;
    const coarseDefault = prefersCoarsePointer();
    const touches = new Set();
    // { pointerId, pointerType, start, end, dragging, shiftKey, canvas }, in the viewport's pixels; `clientStart`, the page's.
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
        element.setAttribute("aria-hidden", "true");
        element.setAttribute("data-box-select", "");
        Object.assign(element.style, { position: "absolute", pointerEvents: "none", zIndex: "30", boxSizing: "border-box" }, BOX_STYLE);
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
      if (press) releasePointer(press.canvas, press.pointerId);
      press = null;
      erase();
      host.style.cursor = "";
      if (!touches.size) giveBackCamera();
    };

    const handlePointerDown = (event) => {
      // Heard at the window: only a press on this viewport is its business.
      if (!(event.target instanceof Node) || !host.contains(event.target)) return;
      if (event.pointerType === "touch") {
        touches.add(event.pointerId);
        // A second finger: no box, and no camera either until the fingers lift.
        if (touches.size > 1) { end(); return; }
      }
      if (press || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || !onCanvas(event)) return;
      if (mayStartRef.current && !mayStartRef.current(event)) return;
      const controls = runtimeRef.current?.controls;
      held = { controlsWereEnabled: controls?.enabled !== false };
      if (controls) controls.enabled = false;
      const at = local(event);
      press = { pointerId: event.pointerId, pointerType: event.pointerType || "", start: at, end: at, dragging: false, shiftKey: Boolean(event.shiftKey),
        clientStart: { x: event.clientX, y: event.clientY }, canvas: event.target };
    };
    const handlePointerMove = (event) => {
      if (!press || event.pointerId !== press.pointerId) return;
      press.end = local(event);
      if (!press.dragging) {
        if (Math.hypot(press.end.x - press.start.x, press.end.y - press.start.y) <= slop(press.pointerType)) return;
        press.dragging = true;
        capturePointer(press.canvas, press.pointerId);
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
      const last = local(event);
      const drawn = press.dragging ? { ...boxFromDrag(press.start, last), client: boxFromDrag(press.clientStart, { x: event.clientX, y: event.clientY }),
        additive: press.shiftKey || Boolean(event.shiftKey) } : null;
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

    const view = host.ownerDocument?.defaultView || window;
    view.addEventListener("pointerdown", handlePointerDown, true);
    host.addEventListener("pointermove", handlePointerMove, true);
    host.addEventListener("pointerup", handlePointerUp, true);
    host.addEventListener("pointercancel", handlePointerCancel, true);
    host.addEventListener("lostpointercapture", handlePointerCancel, true);
    window.addEventListener("keydown", handleKeyDown, true);
    return () => {
      view.removeEventListener("pointerdown", handlePointerDown, true);
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

/** `useBoxSelectGesture` as an element of the viewport's overlay (`RendererShell`'s): it draws nothing of its own. */
export function BoxSelectGesture({ viewport, enabled, onBox, mayStart = null }) {
  useBoxSelectGesture(viewport, { enabled, onBox, mayStart });
  return null;
}

// A flat view's Shift drag pans, as its Ctrl and Cmd drags do: Shift adds only at a box's release.
const flatMayStart = event => !event.shiftKey;

/**
 * The same gesture over a flat view (a board's, a schematic's, a drawing's canvas: `useFlatCanvasView`),
 * under its Select: a plain left drag draws the box wherever it starts, on what a click would pick too,
 * and the view's other drags (right, middle, Ctrl, Cmd or Shift) still pan it. The box handed on carries
 * `local` as well: the box in the canvas's pixels, where the flat view's transform, its ink on the
 * screen and its picks are.
 *
 * @param {{ containerRef: { current: HTMLElement | null }, canvasRef: { current: HTMLCanvasElement | null },
 *   controls: { enabled: boolean } }} view  The flat view (`useFlatCanvasView`'s, or a plot's or a drawing's over it).
 * @param {{ enabled: boolean, onBox: (box: ReturnType<typeof boxFromDrag> & { client: object, local: object, additive: boolean }) => void }} options
 */
export function useFlatBoxSelect(view, { enabled, onBox }) {
  const canvasRef = view.canvasRef;
  // The viewport runtime the gesture reads (a 3D view's `renderer.domElement` and `controls`): the canvas and its pan.
  const runtimeRef = useRef(null);
  runtimeRef.current ??= { renderer: { get domElement() { return canvasRef.current; } }, controls: null };
  runtimeRef.current.controls = view.controls;
  const handleBox = (box) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const local = boxFromDrag({ x: box.client.left - rect.left, y: box.client.top - rect.top }, { x: box.client.right - rect.left, y: box.client.bottom - rect.top });
    onBox({ ...box, local });
  };
  useBoxSelectGesture({ runtimeRef, hostRef: view.containerRef, viewerReadyTick: 0 }, { enabled, onBox: handleBox, mayStart: flatMayStart });
}
