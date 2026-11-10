import { boxFromDrag } from "@cad/core/lib/viewer/boxSelect.js";
import { dimensionLayoutHit, dimensionLayoutTouchesBox, screenSpaceDimensionLayout } from "@cad/core/lib/viewer/measureDimension.js";
import { TOUCH_HIT_PX } from "../../viewport/dom.js";
import { boxedSelection } from "../select/boxTake.js";

/**
 * The measurement drawn under the pointer, the last drawn first, or null: what a press under Select
 * picks before any part, and what resting on one lights. A touch reaches one from further off
 * (`TOUCH_HIT_PX`) than a cursor does.
 *
 * @param {readonly { id: string, pickA: object, pickB: object, measurement: object }[]} measurements
 * @param {{ camera?: object, renderer?: { domElement?: Element } } | null} runtime  The viewport's runtime.
 * @param {{ clientX: number, clientY: number, pointerType?: string }} pointer
 */
export function measurementUnderPointer(measurements, runtime, { clientX, clientY, pointerType = "" }) {
  const drawn = drawnDimensions(measurements, runtime);
  if (!drawn) return null;
  const point = { x: clientX - drawn.rect.left, y: clientY - drawn.rect.top };
  return measurements.findLast(item => dimensionLayoutHit(drawn.layout(item), point, pointerType === "touch" ? TOUCH_HIT_PX : undefined))?.id ?? null;
}

/**
 * The measurements a box under Select takes: those whose drawn dimension it touches
 * (`dimensionLayoutTouchesBox`: its lines, an arrowhead or its label, even in part), in the order they
 * were taken, as a press takes one (`measurementUnderPointer`).
 *
 * @param {readonly { id: string, pickA: object, pickB: object, measurement: object }[]} measurements
 * @param {{ camera?: object, renderer?: { domElement?: Element } } | null} runtime  The viewport's runtime.
 * @param {{ left: number, top: number, right: number, bottom: number }} box  In client pixels.
 * @returns {string[]}
 */
export function measurementsInBox(measurements, runtime, box) {
  const drawn = drawnDimensions(measurements, runtime);
  if (!drawn || !box) return [];
  const { left, top } = drawn.rect;
  const local = boxFromDrag({ x: box.left - left, y: box.top - top }, { x: box.right - left, y: box.bottom - top });
  return measurements.filter(item => dimensionLayoutTouchesBox(drawn.layout(item), local)).map(item => item.id);
}

// Each measurement's dimension as the overlay draws it now (`screenSpaceDimensionLayout`), in the
// canvas's pixels, and the canvas's place on the page; null with no camera, canvas or measurement.
function drawnDimensions(measurements, runtime) {
  const element = runtime?.renderer?.domElement;
  if (!runtime?.camera || !element || !measurements.length) return null;
  const rect = element.getBoundingClientRect();
  const local = { left: 0, top: 0, width: rect.width, height: rect.height };
  return { rect, layout: item => screenSpaceDimensionLayout(item.pickA, item.pickB, item.measurement, runtime.camera, local) };
}

/**
 * Under Select, a press on a measurement picks it (Shift adds or takes away) before any part under
 * it; a press anywhere else lets go of the measurements, unless Shift keeps them. Picking one lets
 * go of the parts (`clearParts`), as picking a part lets go of the measurements. The pointer resting
 * on one lights it. What `RendererShell` takes as `onSelectPress` and `onSelectHover`. A box under
 * Select (`box`: a 3D view's Box select, a flat view's Select) takes every one it touches, and says which: Shift adds them, otherwise they replace the measurements picked, and it lets go of nothing
 * else (the box replaces the rest of the selection itself). `under`: the measurement a press lands
 * on, whatever the filter takes (a 3D Box select's drag from one turns the camera).
 *
 * @param {ReturnType<typeof import("./useMeasureSession.js").useMeasureSession>} measure
 * @param {() => object | null} runtime  The viewport's runtime now.
 * @param {() => void} clearParts
 * @param {{ picks?: boolean }} [options]  `picks`: Select's filter picks measurements (else a press only
 *   lets go of them).
 */
export function measureSelectHandlers(measure, runtime, clearParts, { picks = true } = {}) {
  const at = event => (picks ? measurementUnderPointer(measure.measurements, runtime(), event) : null);
  return {
    press(event) {
      const id = at(event);
      if (!id) {
        if (!event.shiftKey && measure.selected.length) measure.select([]);
        return false;
      }
      measure.select(event.shiftKey
        ? (measure.selected.includes(id) ? measure.selected.filter(other => other !== id) : [...measure.selected, id])
        : [id]);
      if (!event.shiftKey) clearParts();
      return true;
    },
    box(box) {
      const ids = picks ? measurementsInBox(measure.measurements, runtime(), box.client) : [];
      const next = boxedSelection(measure.selected, ids, box.additive);
      if (next !== measure.selected) measure.select(next);
      return ids;
    },
    under(event) {
      return measurementUnderPointer(measure.measurements, runtime(), event);
    },
    hover(event) {
      const id = event ? at(event) ?? "" : "";
      if (id !== measure.hovered) measure.hover(id);
      return Boolean(id);
    }
  };
}
