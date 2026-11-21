import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { PaintBucket, Trash2 } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { ANNOTATION_STROKE_WIDTHS, AnnotationStylePickers, annotationColors } from "../../../../annotation/toolbar.jsx";
import { isHighlighterStroke, strokeSettingOf } from "../../../../annotation/geometry.js";
import { annotationsOnScreen, annotationWorldPoints, closedShape, fillAreasOf } from "./annotation3d.js";
import { useI18n } from "@cad/ui/i18n";

// How far the bar keeps from the ink it is about, and from the viewport's edges, in px.
const GAP = 10;
const EDGE = 8;

// The setting a stroke was drawn at: the pen's ink is heavier than a shape's at the same one, the highlighter's broad.
const strokeSetting = item => {
  const drawn = strokeSettingOf(item);
  return ANNOTATION_STROKE_WIDTHS.reduce((best, option) => (Math.abs(option.value - drawn) < Math.abs(best.value - drawn) ? option : best)).value;
};


/**
 * The ink Select has picked, its bar: a small floating toolbar just above it (below it where there
 * is no room above), following it as the camera moves — the tool strip's surface, a
 * size smaller. Colour, and for strokes their weight
 * (`AnnotationStylePickers`' dropdowns, each choice one step); Fill for a closed
 * shape (its interior, as it falls on the screen now, lying where the shape does — on its plane, or on the surface under it — one step; again
 * to take it away); and Delete, which deletes everything Select has picked (`onDelete`), a
 * measurement too.
 *
 * @param {{ annotation: import("../../../../annotation/session.js").AnnotationSession, runtimeRef: { current: object | null },
 *   viewerReadyTick?: number, onDelete(): void, disabled?: boolean }} props
 */
export default function AnnotationSelectionBar({ annotation, colorScheme = "light", runtimeRef, viewerReadyTick = 0, onDelete, disabled = false }) {
  const { t } = useI18n();
  const picked = new Set(annotation.selected);
  const items = annotation.items.filter(item => picked.has(item.id));
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const [box, setBox] = useState(/** @type {{ left: number, top: number, right: number, bottom: number, width: number, height: number } | null} */ (null));
  const key = items.map(item => item.id).join(",");
  // Each frame, where the picked ink falls on the screen, recomputed only when the camera has moved since.
  useEffect(() => {
    if (!key) { setBox(null); return undefined; }
    let frame = 0, last = null;
    const tick = () => {
      frame = globalThis.requestAnimationFrame(tick);
      const runtime = runtimeRef.current, canvas = runtime?.renderer?.domElement;
      if (!runtime?.camera || !canvas) return;
      runtime.camera.updateMatrixWorld();
      const signature = [canvas.clientWidth, canvas.clientHeight, ...runtime.camera.matrixWorld.elements, ...runtime.camera.projectionMatrix.elements];
      if (last && last.length === signature.length && last.every((value, index) => value === signature[index])) return;
      last = signature;
      const width = canvas.clientWidth, height = canvas.clientHeight;
      let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
      for (const item of itemsRef.current) {
        for (const point of annotationWorldPoints(runtime, item)) {
          const ndc = point.project(runtime.camera);
          if (ndc.z > 1) continue;
          const x = ((ndc.x + 1) / 2) * width, y = ((1 - ndc.y) / 2) * height;
          left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
        }
      }
      setBox(Number.isFinite(left) ? { left, top, right, bottom, width, height } : null);
    };
    tick();
    return () => globalThis.cancelAnimationFrame(frame);
  }, [key, runtimeRef, viewerReadyTick]);
  const bar = useRef(/** @type {HTMLDivElement | null} */ (null));
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const element = bar.current;
    if (element && (element.offsetWidth !== size.width || element.offsetHeight !== size.height)) setSize({ width: element.offsetWidth, height: element.offsetHeight });
  });
  if (!box || !items.length) return null;

  const strokes = items.filter(item => item.kind === "stroke");
  // The strokes a line style restyles: not the highlighter's band.
  const dashed = strokes.filter(item => !isHighlighterStroke(item));
  const closed = items.filter(closedShape);
  const filledGroups = new Set(annotation.items.filter(item => item.kind === "area" && item.group).map(item => item.group));
  const filled = closed.length > 0 && closed.every(item => item.group && filledGroups.has(item.group));
  const toggleFill = () => {
    if (filled) {
      const groups = new Set(closed.map(item => item.group));
      annotation.remove(annotation.items.filter(item => item.kind === "area" && groups.has(item.group)).map(item => item.id));
      return;
    }
    const runtime = runtimeRef.current, canvas = runtime?.renderer?.domElement;
    if (!runtime || !canvas) return;
    const view = { width: canvas.clientWidth, height: canvas.clientHeight };
    for (const shape of closed) {
      if (shape.group && filledGroups.has(shape.group)) continue;
      const [outline] = annotationsOnScreen(runtime, [shape], view);
      const areas = outline ? fillAreasOf(runtime, shape, outline, null, shape.color, view) : [];
      if (areas.length) annotation.fill(shape.id, areas);
    }
  };

  const centre = (box.left + box.right) / 2;
  const left = Math.max(EDGE, Math.min(box.width - EDGE - size.width, centre - size.width / 2));
  const above = box.top - GAP - size.height;
  const top = above >= EDGE ? above : Math.min(box.bottom + GAP, box.height - EDGE - size.height);
  return <div ref={bar} role="toolbar" aria-label={t("annotate.selected")}
    className={cn(FLOATING_CHROME_SURFACE_CLASS, "pointer-events-auto absolute z-20 rounded-md p-0.5", size.width ? null : "invisible")}
    style={{ left, top }} data-annotation-selection-bar="" onPointerDown={event => event.stopPropagation()}>
    <AnnotationStylePickers label={t("annotate.selectedStyle")} className="flex items-center gap-0.5" disabled={disabled} color={items[0].color} colors={annotationColors(colorScheme)}
      width={strokes.length ? strokeSetting(strokes[0]) : null}
      // The line style of the strokes picked that have one (none: the highlighter's alone, or no stroke picked).
      dash={dashed.length ? dashed[0].dash ?? 'solid' : null}
      onColor={color => annotation.restyle({ color })} onWidth={width => annotation.restyle({ width })} onDash={dash => annotation.restyle({ dash })}>
      {closed.length ? <ToolbarButton tooltip={false} label={t("annotate.fill")} disabled={disabled} active={filled} aria-pressed={filled} onClick={toggleFill}>
        <PaintBucket className="size-3" strokeWidth={2} aria-hidden="true" />
      </ToolbarButton> : null}
      <span role="separator" aria-orientation="vertical" className="mx-0.5 h-4 w-px bg-border" />
      <ToolbarButton tooltip={false} label={t("annotate.delete")} disabled={disabled} onClick={onDelete}>
        <Trash2 className="size-3" strokeWidth={2} aria-hidden="true" />
      </ToolbarButton>
    </AnnotationStylePickers>
  </div>;
}
