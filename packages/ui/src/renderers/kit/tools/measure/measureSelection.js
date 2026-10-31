import { dimensionLayoutHit, screenSpaceDimensionLayout } from "@text-to-cad/core/lib/viewer/measureDimension.js";
import { TOUCH_HIT_PX } from "../../viewport/dom.js";

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
  const element = runtime?.renderer?.domElement;
  if (!runtime?.camera || !element || !measurements.length) return null;
  const rect = element.getBoundingClientRect();
  const local = { left: 0, top: 0, width: rect.width, height: rect.height };
  const point = { x: clientX - rect.left, y: clientY - rect.top };
  return measurements.findLast(item =>
    dimensionLayoutHit(screenSpaceDimensionLayout(item.pickA, item.pickB, item.measurement, runtime.camera, local), point,
      pointerType === "touch" ? TOUCH_HIT_PX : undefined))?.id ?? null;
}

/**
 * Under Select, a press on a measurement picks it (Shift adds or takes away) before any part under
 * it; a press anywhere else lets go of the measurements, unless Shift keeps them. Picking one lets
 * go of the parts (`clearParts`), as picking a part lets go of the measurements. The pointer resting
 * on one lights it. What `RendererShell` takes as `onSelectPress` and `onSelectHover`.
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
    hover(event) {
      const id = event ? at(event) ?? "" : "";
      if (id !== measure.hovered) measure.hover(id);
      return Boolean(id);
    }
  };
}
