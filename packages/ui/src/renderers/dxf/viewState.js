/**
 * What a DXF pane remembers about one file: the view, and only once the person
 * has moved it.
 *
 * A drawing that is still sitting where it opened has nothing worth storing —
 * the fit is recomputed from the pane's size anyway, and storing it would make
 * a pane that is reopened narrower come back framed for the old width. So the
 * record exists only after a pan or a zoom, and its absence means "fit me".
 *
 * A HARD CUTOVER from the 3D DXF viewer's record (`{ version: 1, camera,
 * display, inspectorTab, tool, renderer }`): that shape described a scene this
 * renderer does not have. Rather than migrate it into something it never meant,
 * the record is tagged `kind: "dxf-view"` and anything else — including every
 * record the old renderer wrote — reads as "nothing stored" and opens fitted.
 */

export const DXF_VIEW_STATE_KIND = "dxf-view";
export const DXF_VIEW_STATE_VERSION = 1;

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * The stored transform, or null.
 *
 * @param {unknown} raw
 * @returns {{ scale: number, offsetX: number, offsetY: number }|null}
 */
export function readDxfViewState(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  if (raw.kind !== DXF_VIEW_STATE_KIND || raw.version !== DXF_VIEW_STATE_VERSION) {
    return null;
  }
  const transform = raw.transform;
  if (!transform || typeof transform !== "object" || Array.isArray(transform)) {
    return null;
  }
  const { scale, offsetX, offsetY } = transform;
  if (!finite(scale) || scale <= 0 || !finite(offsetX) || !finite(offsetY)) {
    return null;
  }
  return { scale, offsetX, offsetY };
}

/**
 * The record to store for a moved view, or null when the view is untouched and
 * there is nothing to remember.
 *
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} transform
 * @param {boolean} moved
 */
export function dxfViewStateRecord(transform, moved) {
  if (!moved || !transform) {
    return null;
  }
  return {
    kind: DXF_VIEW_STATE_KIND,
    version: DXF_VIEW_STATE_VERSION,
    transform: { scale: transform.scale, offsetX: transform.offsetX, offsetY: transform.offsetY }
  };
}
