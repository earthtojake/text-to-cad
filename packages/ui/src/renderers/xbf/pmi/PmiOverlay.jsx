import { useEffect, useRef } from "react";
import { ANNOTATION_HIDDEN_OPACITY } from "@text-to-cad/core/common/annotation.js";
import { cn } from "@text-to-cad/ui/utils";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
import PmiLabel, { PMI_STATUS_TOKENS } from "./PmiLabel.jsx";
import { separateLabels } from "./separateLabels.js";

// An engine document's PMI over the viewport: each annotation's label, a few words at the UI's
// size whatever the zoom, standing where its construction puts it (`xbfPmiLayout.js`) -- set apart
// on screen from one it would cover, where the code did not place it (`separateLabels.js`) -- and on a
// canvas under the labels what ties each to its feature -- a leader with an arrow (a datum's ends on
// its triangle), and a distance's dimension and extension lines with their arrows. Laid out again
// on every frame the camera or the view's size moved, as the joint handles are
// (`kit/tools/pose/useJointHandles.js`), and on nothing else.
//
// Under Select a label is a control: a click picks its annotation, a double-click looks at its
// feature, and a drag of the picked one moves it -- on the plane facing the view through where it
// stood -- which is where it is drawn, never what it says. Under any other tool the labels take no
// pointer: ink, a measurement or a pick goes through to the model.

// The canvas's inks: what Select has picked, as the annotations and the measurements are, in the one
// selection blue (the labels' too, `--pmi-selected`); and a reference the engine could not stand the
// annotation on, in its status's colour, read from the token its label's box is drawn in
// (`PMI_STATUS_TOKENS`): it names nothing, or a face it cannot stand on (failed), or several (a warning).
const SELECTED_COLOR = "#2979ff";
const ARROW_PX = 7, ARROW_HALF_PX = 2.6, DATUM_PX = 6;
const FINE_SLOP_PX = 4, COARSE_SLOP_PX = 12;
// How far a distance's words stand off its dimension line.
const LABEL_CLEAR_PX = 6;

const projectWith = (THREE, camera, width, height) => {
  const scratch = new THREE.Vector3();
  return (point) => {
    if (!point) return null;
    scratch.set(point[0], point[1], point[2]).project(camera);
    if (!Number.isFinite(scratch.x) || !Number.isFinite(scratch.y) || scratch.z > 1 || scratch.z < -1) return null;
    return { x: ((scratch.x + 1) * width) / 2, y: ((1 - scratch.y) * height) / 2, z: scratch.z };
  };
};

// Where a leader from `from` meets the box `box` ({ x, y, w, h } centred on x, y): its edge on the way in.
function boxEdge(from, box) {
  const dx = from.x - box.x, dy = from.y - box.y;
  if (!dx && !dy) return { x: box.x, y: box.y };
  const sx = box.w / 2 / Math.abs(dx || 1e-9), sy = box.h / 2 / Math.abs(dy || 1e-9);
  const s = Math.min(sx, sy, 1);
  return { x: box.x + dx * s, y: box.y + dy * s };
}

function arrowHead(context, tip, from, hollow = false) {
  const angle = Math.atan2(tip.y - from.y, tip.x - from.x);
  context.beginPath();
  context.moveTo(tip.x, tip.y);
  context.lineTo(tip.x - ARROW_PX * Math.cos(angle) + ARROW_HALF_PX * Math.sin(angle), tip.y - ARROW_PX * Math.sin(angle) - ARROW_HALF_PX * Math.cos(angle));
  context.lineTo(tip.x - ARROW_PX * Math.cos(angle) - ARROW_HALF_PX * Math.sin(angle), tip.y - ARROW_PX * Math.sin(angle) + ARROW_HALF_PX * Math.cos(angle));
  context.closePath();
  if (hollow) context.stroke(); else context.fill();
}

// A datum's feature symbol: the filled triangle its leader stands on, its base on the feature.
function datumTriangle(context, base, from, hollow = false) {
  const angle = Math.atan2(from.y - base.y, from.x - base.x);
  const along = [Math.cos(angle), Math.sin(angle)], side = [-along[1], along[0]];
  context.beginPath();
  context.moveTo(base.x + side[0] * DATUM_PX, base.y + side[1] * DATUM_PX);
  context.lineTo(base.x - side[0] * DATUM_PX, base.y - side[1] * DATUM_PX);
  context.lineTo(base.x + along[0] * DATUM_PX * 1.4, base.y + along[1] * DATUM_PX * 1.4);
  context.closePath();
  if (hollow) context.stroke(); else context.fill();
}

function drawItem(context, item, at, inks) {
  const color = item.status !== "ok" ? inks[item.status] || inks.ok : item.selected ? SELECTED_COLOR : inks.ok;
  context.strokeStyle = color;
  context.fillStyle = color;
  const alpha = item.hovered || item.selected ? 1 : 0.85;
  context.globalAlpha = alpha;
  context.lineWidth = item.selected ? 1.5 : 1;
  context.setLineDash(item.status !== "ok" ? [4, 3] : []);
  const line = (a, b) => { if (!a || !b) return; context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke(); };
  if (at.dimension) {
    const { from, to } = at.dimension;
    // An extension line from a face the model hides is drawn faint, as hidden ink is.
    at.dimension.extensions.forEach(([a, b], index) => {
      context.globalAlpha = at.dimension.behind?.[index] ? alpha * ANNOTATION_HIDDEN_OPACITY : alpha;
      line(a, b);
    });
    context.globalAlpha = alpha;
    line(from, to);
    context.setLineDash([]);
    if (!from || !to) return;
    // Arrows inside, out to the extension lines; where the line is too short to hold them, outside
    // pointing in, on short tails, as a drawing does (Measure's `screenSpaceDimensionLayout`).
    const length = Math.hypot(to.x - from.x, to.y - from.y);
    if (length >= ARROW_PX * 2.5) {
      arrowHead(context, from, to);
      arrowHead(context, to, from);
    } else {
      const along = length > 1e-6 ? { x: (to.x - from.x) / length, y: (to.y - from.y) / length } : { x: 0, y: 1 };
      const tail = point => ({ x: point.x + along.x * ARROW_PX * 2, y: point.y + along.y * ARROW_PX * 2 });
      const before = { x: from.x - along.x * ARROW_PX * 2, y: from.y - along.y * ARROW_PX * 2 };
      line(before, from); line(to, tail(to));
      arrowHead(context, from, before);
      arrowHead(context, to, tail(to));
    }
    return;
  }
  if (!at.anchor || !at.box) return;
  const end = boxEdge(at.anchor, at.box);
  // A leader to a face the model hides from this side: faint, as hidden ink is, its marker hollow, so it reads as behind.
  if (at.behind) context.globalAlpha = alpha * ANNOTATION_HIDDEN_OPACITY;
  line(at.anchor, end);
  context.setLineDash([]);
  // A feature not on the page: an open ring where the code anchored it, nothing pointing at a face.
  if (at.broken) {
    context.beginPath();
    context.arc(at.anchor.x, at.anchor.y, ARROW_HALF_PX + 1, 0, Math.PI * 2);
    context.stroke();
  } else if (item.kind === "datum") datumTriangle(context, at.anchor, end, at.behind); else arrowHead(context, at.anchor, end, at.behind);
  context.globalAlpha = alpha;
}

/**
 * @param {{ viewport: { runtimeRef: object, hostRef: object, viewerReadyTick: number },
 *   items: ReadonlyArray<{ key: string, id: string, kind: string, callout: object, status: string, construction: object,
 *     selected: boolean, hovered: boolean, moved: boolean, problem: string }>,
 *   interactive: boolean, onSelect: (key: string) => void, onHover: (key: string) => void,
 *   onMove: (key: string, label: number[]) => void, onLookAt: (key: string) => void,
 *   hiddenAt?: ((point: number[]) => boolean) | null }} props
 *   `key`: an annotation's, what every callback is given (`id`, its author's, what its label says it
 *   is); `construction`: each annotation's points in the scene's coordinates (`pmiConstruction`); `onMove`:
 *   where a dragged label was let go, in the scene's coordinates; `hiddenAt`: whether the model hides
 *   a point from the camera as it stands (a leader's start, an extension line's), which is drawn faint.
 */
export default function PmiOverlay({ viewport, items, interactive, onSelect, onHover, onMove, onLookAt, hiddenAt = null }) {
  const { runtimeRef, hostRef, viewerReadyTick } = viewport;
  const canvasRef = useRef(null);
  const rootRef = useRef(null);
  const labels = useRef(new Map());
  const itemsRef = useRef(items);
  itemsRef.current = items;
  // A label being dragged: its annotation's key and where it is now, in the scene's coordinates.
  const dragRef = useRef(null);
  const repaintRef = useRef(() => {});
  const callbacks = useRef(null);
  callbacks.current = { onSelect, onHover, onMove, onLookAt };
  const hiddenAtRef = useRef(hiddenAt);
  hiddenAtRef.current = hiddenAt;

  useEffect(() => {
    const host = hostRef.current, canvas = canvasRef.current, root = rootRef.current;
    if (!host || !canvas || !root) return undefined;
    let frame = 0, painted = "", paintedItems = null, paintedDrag = null;
    // One drawing as the camera stands now; skipped when nothing it depends on moved, unless `force`.
    const draw = (force = false) => {
      const runtime = runtimeRef.current;
      const camera = runtime?.camera;
      if (!camera || !runtime?.THREE) return;
      const width = host.clientWidth || 1, height = host.clientHeight || 1;
      const dpr = window.devicePixelRatio || 1;
      camera.updateMatrixWorld();
      const key = [width, height, dpr, camera.zoom, camera.matrixWorld.elements.join(), camera.projectionMatrix.elements.join()].join("|");
      const drag = dragRef.current;
      if (!force && key === painted && paintedItems === itemsRef.current && paintedDrag === drag?.label) return;
      painted = key;
      paintedItems = itemsRef.current;
      paintedDrag = drag?.label;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      // The theme's inks as they are now: the labels' foreground, and each status's token.
      const style = getComputedStyle(root);
      const inks = { ok: style.color || "#888" };
      for (const [status, token] of Object.entries(PMI_STATUS_TOKENS)) inks[status] = style.getPropertyValue(token).trim() || inks.ok;
      const project = projectWith(runtime.THREE, camera, width, height);
      // Where each label falls, then set apart where two would cover one another (a dimension's
      // stays on its line, and a dragged one where the pointer has it).
      const drawn = itemsRef.current.map((item) => {
        const element = labels.current.get(item.key);
        const dragged = drag?.key === item.key;
        const label = project(dragged ? drag.label : item.construction?.label);
        return element && label ? { item, element, label, box: { x: label.x, y: label.y, w: element.offsetWidth, h: element.offsetHeight,
          movable: !dragged && item.construction.placed === "default" && !item.construction.dimension } } : { item, element, label: null };
      });
      // A distance's words stand beside its dimension line, out from the part (the side its
      // extension lines run to), clear of the line and its arrows.
      for (const entry of drawn) {
        const dimension = entry.label && drag?.key !== entry.item.key ? entry.item.construction?.dimension : null;
        if (!dimension) continue;
        const from = project(dimension.from), to = project(dimension.to), anchor = project(entry.item.construction.anchor);
        if (!from || !to) continue;
        const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
        // Out from the part, square to the line on screen: the way the extension lines run.
        const span = Math.hypot(to.x - from.x, to.y - from.y);
        const along = span > 1e-6 ? { x: (to.x - from.x) / span, y: (to.y - from.y) / span } : { x: 0, y: 0 };
        let out = anchor ? { x: mid.x - anchor.x, y: mid.y - anchor.y } : { x: 0, y: 0 };
        const share = out.x * along.x + out.y * along.y;
        out = { x: out.x - along.x * share, y: out.y - along.y * share };
        let size = Math.hypot(out.x, out.y);
        if (size < 1) { out = { x: -(to.y - from.y), y: to.x - from.x }; size = Math.hypot(out.x, out.y) || 1; }
        out = { x: out.x / size, y: out.y / size };
        const reach = Math.abs(out.x) * entry.box.w / 2 + Math.abs(out.y) * entry.box.h / 2 + LABEL_CLEAR_PX;
        Object.assign(entry.box, { x: mid.x + out.x * reach, y: mid.y + out.y * reach });
      }
      const shown = drawn.filter(entry => entry.label);
      separateLabels(shown.map(entry => entry.box)).forEach((at, index) => Object.assign(shown[index].box, at));
      for (const { item, element, label, box } of drawn) {
        if (!element) continue;
        if (!label) { element.style.visibility = "hidden"; continue; }
        element.style.visibility = "";
        element.style.transform = `translate(${Math.round(box.x)}px, ${Math.round(box.y)}px) translate(-50%, -50%)`;
        const construction = item.construction;
        const behind = point => Boolean(point && hiddenAtRef.current?.(point));
        const dimension = construction?.dimension && drag?.key !== item.key ? {
          from: project(construction.dimension.from), to: project(construction.dimension.to),
          extensions: construction.dimension.extensions.map(([a, b]) => [project(a), project(b)]),
          behind: construction.dimension.extensions.map(([a]) => behind(a))
        } : null;
        drawItem(context, item, { anchor: project(construction?.anchor), box, dimension, broken: Boolean(construction?.broken),
          behind: !construction?.broken && !construction?.dimension && behind(construction?.anchor) }, inks);
      }
      context.globalAlpha = 1;
      context.setLineDash([]);
    };
    // The one loop: it alone schedules itself; a repaint asked for draws once, in place.
    const loop = () => { frame = window.requestAnimationFrame(loop); draw(); };
    repaintRef.current = () => draw(true);
    frame = window.requestAnimationFrame(loop);
    return () => {
      window.cancelAnimationFrame(frame);
      repaintRef.current = () => {};
      canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [runtimeRef, hostRef, viewerReadyTick]);
  // A label's size changes with what it says: lay out again once the new labels are in.
  useEffect(() => { repaintRef.current(); }, [items]);

  // A press on a label: a click picks it; a drag of the picked one moves it, square to the view.
  const press = (event, item) => {
    if (!interactive || event.button !== 0) return;
    event.stopPropagation();
    const element = event.currentTarget;
    const runtime = runtimeRef.current;
    const host = hostRef.current;
    if (!runtime?.camera || !host) return;
    capturePointer(element, event.pointerId);
    const slop = event.pointerType === "touch" || event.pointerType === "pen" ? COARSE_SLOP_PX : FINE_SLOP_PX;
    const start = { x: event.clientX, y: event.clientY };
    const rect = host.getBoundingClientRect();
    const from = item.construction?.label;
    const depth = from ? new runtime.THREE.Vector3(...from).project(runtime.camera).z : null;
    let moved = false;
    const at = (clientX, clientY) => new runtime.THREE.Vector3(((clientX - rect.left) / rect.width) * 2 - 1,
      1 - ((clientY - rect.top) / rect.height) * 2, depth).unproject(runtime.camera).toArray();
    const move = (next) => {
      if (!moved && Math.hypot(next.clientX - start.x, next.clientY - start.y) <= slop) return;
      // Only the picked annotation moves: a drag of another is nothing, so a stray press never re-places it.
      if (!item.selected || depth === null) return;
      moved = true;
      dragRef.current = { key: item.key, label: at(next.clientX, next.clientY) };
    };
    const end = (last) => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", end);
      element.removeEventListener("pointercancel", cancel);
      releasePointer(element, event.pointerId);
      const drag = dragRef.current;
      dragRef.current = null;
      if (moved && drag) callbacks.current.onMove(item.key, at(last.clientX, last.clientY));
      else if (Math.hypot(last.clientX - start.x, last.clientY - start.y) <= slop) callbacks.current.onSelect(item.key);
    };
    const cancel = () => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", end);
      element.removeEventListener("pointercancel", cancel);
      dragRef.current = null;
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", end);
    element.addEventListener("pointercancel", cancel);
  };

  return <div ref={rootRef} className="pointer-events-none absolute inset-0 z-10 overflow-hidden text-foreground" style={{ "--pmi-selected": SELECTED_COLOR }} data-cad-pmi="">
    <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden="true" />
    {items.map(item => <button key={item.key} type="button" ref={node => { if (node) labels.current.set(item.key, node); else labels.current.delete(item.key); }}
      tabIndex={interactive ? 0 : -1} aria-label={`${item.callout.text}${item.problem ? `: ${item.problem}` : ""}`} aria-pressed={item.selected}
      data-pmi-label={item.id} data-pmi-status={item.status} data-selected={item.selected ? "" : undefined}
      className={cn("absolute left-0 top-0 select-none whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
        interactive ? "pointer-events-auto touch-none" : "pointer-events-none", item.selected && interactive && "cursor-move")}
      style={{ visibility: "hidden" }}
      onPointerDown={event => press(event, item)}
      onPointerEnter={() => { if (interactive) callbacks.current.onHover(item.key); }}
      onPointerLeave={() => { if (interactive) callbacks.current.onHover(""); }}
      onDoubleClick={(event) => { if (!interactive) return; event.stopPropagation(); callbacks.current.onLookAt(item.key); }}
      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); callbacks.current.onSelect(item.key); } }}>
      <PmiLabel callout={item.callout} status={item.status} selected={item.selected} hovered={item.hovered} moved={item.moved} />
    </button>)}
  </div>;
}
