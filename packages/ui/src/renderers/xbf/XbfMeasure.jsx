import { useEffect, useMemo, useRef } from "react";
import { fetchXbfElementFacts } from "@text-to-cad/core/lib/xbf/xbfDocument.js";
import { usePointerPick } from "../kit/tools/select/usePointerPick.js";
import { useMeasureOverlay } from "../kit/tools/measure/useMeasureOverlay.js";
import { prefersCoarsePointer } from "../kit/viewport/dom.js";
import { xbfMeasurePick } from "./xbfMeasurePick.js";

// An engine document's Measure, as a STEP's: a press takes a vertex, an edge or a face whole, as
// its menu chooses (`xbfMeasurePick.js`), and a pair reads what the two make
// (`@text-to-cad/core/lib/viewer/measureEntities.js`): parallel faces square across, holes by their
// centres, faces or edges at an angle by the angle. The entity under the resting pointer is lit, a
// vertex by its marker alone, with what it is worth on its own beside it; an edge's length along a
// curve and a face's area are the engine's facts of it (`fetchXbfElementFacts`), read when the
// pointer first rests on it and shown once they are in. In millimetres, the rulers drawn and
// listed as a STEP's are (`useMeasureOverlay.js`, `measurementChips.jsx`). The session is the
// renderer's (`useMeasureSession`), since Quick Edit reads it before the shell is made.

/**
 * The engine's facts of the elements Measure rests on, each asked for once by its part's geometry
 * key (a part an edit did not touch keeps its key, and so its facts): `read(id)`, the facts once
 * they are in (null until then); `want(id)` asks for them; `heard` is told of each answer.
 */
function useMeasureFacts({ scene, source, fetch }) {
  const held = useRef(new Map());
  const heard = useRef(() => {});
  return useMemo(() => {
    const keyOf = (id) => {
      const element = scene?.describeElement(id);
      return element ? { key: `${element.key}/${element.kind}/${element.ordinal}`, element } : null;
    };
    return {
      heard,
      read(id) {
        const found = keyOf(id);
        const facts = found && held.current.get(found.key);
        return facts && typeof facts === "object" ? facts : null;
      },
      want(id) {
        const found = keyOf(id);
        if (!found || !source || held.current.has(found.key)) return;
        held.current.set(found.key, "asked");
        fetchXbfElementFacts(source, found.element.key, found.element.kind, found.element.ordinal, { fetch })
          .then((facts) => { held.current.set(found.key, facts); heard.current(id); }, () => {});
      }
    };
  }, [scene, source, fetch]);
}

/**
 * Measure's layer over the viewport: the measurements drawn, and while the tool is in hand
 * (`picking`) a pick per tap and the marker under the resting pointer, with the entity there lit
 * (`onHoverElement`: a face's or an edge's id, or ""); a double-click names the face or edge a
 * press there takes, or "" for none (`onDoublePick`), as a STEP's Measure did.
 *
 * @param {{ viewport: object, scene: object | null, measure: object, picking: boolean, preview?: boolean,
 *   filter: readonly string[], source?: string, fetch?: typeof fetch, onHoverElement?: (id: string) => void,
 *   onDoublePick?: (id: string) => void }} props
 */
export default function XbfMeasureOverlay({ viewport, scene, measure, picking, preview = false, filter, source = "", fetch, onHoverElement,
  onDoublePick }) {
  const canvasRef = useRef(null);
  const hoverRef = useRef(null);
  const anchorRef = useRef(null);
  // Where the pointer last rested, so the facts that land for what is under it are read in at once.
  const restingRef = useRef(null);
  const active = picking && !preview;
  const facts = useMeasureFacts({ scene, source, fetch });
  useEffect(() => { if (!picking) { hoverRef.current = null; anchorRef.current = null; restingRef.current = null; } }, [picking]);
  useEffect(() => { if (!measure.state?.draft?.anchor) anchorRef.current = null; }, [measure.state]);
  // The ray a press or a resting pointer casts: what it takes is read with the pointer's place (`take`).
  const caster = useMemo(() => (scene ? { pick: ray => ({ id: "", ray: ray.clone() }) } : null), [scene]);
  const take = (found, pointer, { free = false } = {}) => {
    const camera = viewport.runtimeRef.current?.camera;
    const rect = viewport.hostRef.current?.getBoundingClientRect?.();
    if (!found?.ray || !pointer || !camera || !rect?.width) return null;
    return xbfMeasurePick({ scene, ray: found.ray, view: { camera, width: rect.width, height: rect.height }, pointer, filter, free,
      facts: hit => facts.read(hit.id) });
  };
  const rest = (pick) => {
    hoverRef.current = pick || anchorRef.current;
    measure.onHoverPoint(pick);
    // A vertex lights as its marker alone.
    onHoverElement?.(pick && pick.snapKind !== "vertex" ? pick.referenceId : "");
  };
  facts.heard.current = (id) => {
    const resting = restingRef.current;
    if (!active || !resting || hoverRef.current?.referenceId !== id) return;
    rest(take(resting.found, resting.pointer));
  };
  usePointerPick({
    viewport, scene: caster, enabled: active,
    // Every pointer move takes its point anew: where on the entity the reading is drawn from.
    sameHit: () => false,
    onPick(found, modifiers, pointer) {
      // Shift takes the point on the model as it is; a press on nothing lets go of what is held.
      const pick = take(found, pointer, { free: Boolean(modifiers?.multiSelect) });
      if (pick && !anchorRef.current) { anchorRef.current = pick; hoverRef.current = pick; } else anchorRef.current = null;
      measure.onPick(pick);
    },
    onHover(found, pointer) {
      restingRef.current = found && pointer ? { found, pointer } : null;
      const pick = take(found, pointer);
      if (pick?.referenceId && pick.snapKind !== "vertex") facts.want(pick.referenceId);
      rest(pick);
    }
  });
  // Measuring keeps one cursor throughout: what a press takes is lit, not told by the cursor.
  useEffect(() => {
    const canvas = viewport.runtimeRef.current?.renderer?.domElement;
    if (!active || !canvas) return undefined;
    const before = canvas.style.cursor;
    canvas.style.cursor = "crosshair";
    return () => { canvas.style.cursor = before; };
  }, [active, viewport.runtimeRef, viewport.viewerReadyTick]);
  // A double-click (a fine pointer's): the face or edge a press there takes, after the presses of the gesture took theirs.
  const doubleRef = useRef(null);
  doubleRef.current = (event) => {
    const runtime = viewport.runtimeRef.current;
    const rect = viewport.hostRef.current?.getBoundingClientRect?.();
    if (event.target !== runtime?.renderer?.domElement || !runtime?.THREE || !rect?.width) return;
    const raycaster = new runtime.THREE.Raycaster();
    runtime.camera.updateMatrixWorld();
    raycaster.setFromCamera(new runtime.THREE.Vector2(((event.clientX - rect.left) / rect.width) * 2 - 1, 1 - ((event.clientY - rect.top) / rect.height) * 2), runtime.camera);
    const pick = take({ ray: raycaster.ray }, { x: event.clientX - rect.left, y: event.clientY - rect.top });
    onDoublePick?.(pick?.referenceId || "");
  };
  useEffect(() => {
    const host = viewport.hostRef.current;
    if (!active || !host || prefersCoarsePointer()) return undefined;
    const listener = event => doubleRef.current(event);
    host.addEventListener("dblclick", listener);
    return () => host.removeEventListener("dblclick", listener);
  }, [active, viewport.hostRef, viewport.viewerReadyTick]);
  const faceAreas = useMemo(() => ({
    read: (reference) => {
      const area = Number(facts.read(reference?.id || "")?.area);
      return Number.isFinite(area) ? { state: "ready", area } : null;
    }
  }), [facts]);
  useMeasureOverlay({
    measureCanvasRef: canvasRef, measureState: measure.state, activeMeasurementId: measure.activeId,
    selectedMeasurementIds: measure.selected, hoveredMeasurementId: measure.hovered, measureHoverRef: hoverRef,
    measureModeActive: picking, runtimeRef: viewport.runtimeRef, mountRef: viewport.mountRef, preview,
    viewerReadyTick: viewport.viewerReadyTick, faceAreas
  });
  return <canvas ref={canvasRef} className="absolute inset-0 z-10 h-full w-full touch-none" style={{ pointerEvents: "none" }} aria-hidden="true" data-scene-measure="" />;
}
