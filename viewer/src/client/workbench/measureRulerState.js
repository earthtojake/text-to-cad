import { isFinitePoint, measurementFromPicks } from "cadjs/lib/viewer/measurement.js";

export const MEASURE_RULER_MAX_MEASUREMENTS = 20;

let measureMeasurementCounter = 0;
let measureSeriesCounter = 0;

export function createMeasureMeasurementId() {
  measureMeasurementCounter += 1;
  return `measurement-${measureMeasurementCounter}`;
}

/**
 * Colours advance monotonically rather than being derived from the list length,
 * so deleting a row in the middle never hands its colour to a row that is still
 * on screen. Only the index is stored — the palette resolves it at render, so
 * changing the palette cannot leave stale colours behind in state.
 */
export function createMeasureSeriesIndex() {
  const index = measureSeriesCounter;
  measureSeriesCounter += 1;
  return index;
}

export function applyMeasureRulerPick(state, pick, {
  createId = createMeasureMeasurementId,
  createSeriesIndex = createMeasureSeriesIndex
} = {}) {
  if (!pick || !isFinitePoint(pick?.point)) {
    return state || null;
  }
  if (!state?.draft) {
    return {
      draft: { anchor: pick, hover: null },
      hover: pick,
      measurements: state?.measurements || []
    };
  }
  const measurement = measurementFromPicks(state.draft.anchor, pick);
  if (!measurement) {
    return {
      draft: { anchor: pick, hover: null },
      hover: pick,
      measurements: state.measurements || []
    };
  }
  const item = {
    id: createId(),
    colorIndex: createSeriesIndex(),
    pickA: state.draft.anchor,
    pickB: pick,
    measurement
  };
  let measurements = [...(state.measurements || []), item];
  if (measurements.length > MEASURE_RULER_MAX_MEASUREMENTS) {
    measurements = measurements.slice(measurements.length - MEASURE_RULER_MAX_MEASUREMENTS);
  }
  return {
    draft: null,
    hover: state?.hover || null,
    measurements
  };
}

/**
 * Hover is tracked whether or not a measurement is in flight: with a draft it
 * drives the rubber-band line, and without one it is what lets the panel read
 * out the size of the entity under the cursor before any click.
 *
 * With no draft the point itself is not needed, so the state object is only
 * replaced when the hovered entity changes — otherwise every mouse move would
 * re-render the workspace for a readout that did not move.
 */
export function applyMeasureRulerHover(state, hover) {
  const nextHover = hover && isFinitePoint(hover?.point) ? hover : null;
  if (!state?.draft) {
    const currentId = state?.hover?.referenceId || "";
    const nextId = nextHover?.referenceId || "";
    if (!state && !nextHover) {
      return state || null;
    }
    if (state && currentId === nextId && (state.hover?.snapKind || "") === (nextHover?.snapKind || "")) {
      return state;
    }
    return {
      draft: null,
      hover: nextHover,
      measurements: state?.measurements || []
    };
  }
  return {
    ...state,
    hover: nextHover,
    draft: {
      anchor: state.draft.anchor,
      hover: nextHover
    }
  };
}

export function applyMeasureRulerDelete(state, measurementId) {
  if (!state || !measurementId) {
    return state || null;
  }
  const measurements = (state.measurements || []).filter((item) => item.id !== measurementId);
  if (measurements.length === (state.measurements || []).length) {
    return state;
  }
  return {
    draft: state.draft || null,
    hover: state.hover || null,
    measurements
  };
}

export function measureRulerDraftMeasurement(state) {
  const draft = state?.draft;
  if (!draft?.anchor || !draft.hover) {
    return null;
  }
  return measurementFromPicks(draft.anchor, draft.hover);
}

/**
 * Committed measurements belong to the model, not to the tool. Leaving Measure
 * keeps them — the panel still lists them and the overlay still draws them, the
 * way a CAD measurement stays on screen once taken — and only abandons the
 * half-finished draft. Opening a different entry drops all of them, because the
 * points are world-space against the model that is going away.
 */
export function measureRulerStateForChange(state, { entryChanged = false, toolActive = true } = {}) {
  if (!state) {
    return null;
  }
  if (entryChanged) {
    return null;
  }
  if (!toolActive) {
    return state.draft ? { draft: null, hover: null, measurements: state.measurements || [] } : state;
  }
  return state;
}

/**
 * Abandon the half-finished measurement without touching the committed ones or
 * the tool itself — what Escape does in a CAD measure tool: cancel what you are
 * drawing, stay where you are.
 */
export function cancelMeasureRulerDraft(state) {
  if (!state?.draft) {
    return state || null;
  }
  return {
    draft: null,
    hover: state.hover || null,
    measurements: state.measurements || []
  };
}

export function clearMeasureRulerMeasurements(state) {
  if (!state) {
    return null;
  }
  return state.draft || state.hover
    ? { draft: state.draft || null, hover: state.hover || null, measurements: [] }
    : null;
}
