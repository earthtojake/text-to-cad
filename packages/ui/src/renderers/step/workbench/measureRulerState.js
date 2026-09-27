import { isFinitePoint, measurementFromPicks } from "@hardcore/core/lib/viewer/measurement.js";

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

const sameSnapTarget = (left, right) => (left?.referenceId || "") === (right?.referenceId || "") &&
  (left?.snapKind || "") === (right?.snapKind || "");

/**
 * Hover is tracked whether or not a measurement is in flight: with a draft it
 * decides whether there is a rubber band at all, and without one it is what lets
 * the panel read out the size of the entity under the cursor before any click.
 *
 * Either way the state object is only replaced when what the pointer SNAPS TO
 * changes (or a hover comes or goes) — otherwise every mouse move would re-render
 * the workspace. The point itself moves every frame, and the overlay draws it from
 * the live hover it is handed (`useStepMeasureOverlay`), not from here.
 */
export function applyMeasureRulerHover(state, hover) {
  const nextHover = hover && isFinitePoint(hover?.point) ? hover : null;
  if (!state?.draft) {
    if (!state && !nextHover) {
      return state || null;
    }
    if (state && sameSnapTarget(state.hover, nextHover)) {
      return state;
    }
    return {
      draft: null,
      hover: nextHover,
      measurements: state?.measurements || []
    };
  }
  if (Boolean(state.draft.hover) === Boolean(nextHover) && sameSnapTarget(state.draft.hover, nextHover)) {
    return state;
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
 * Completed measurements outlive the picking tool. Changing tools cancels only
 * the draft; changing files clears results because their coordinates belong to that model.
 */
export function measureRulerStateForChange(state, { entryChanged = false, toolActive = true } = {}) {
  if (!state) {
    return null;
  }
  if (entryChanged) {
    return null;
  }
  if (!toolActive) {
    return cancelMeasureRulerDraft(state);
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

/** Whether Measure's snapping filter lets a pick (or a hover) of this snap kind through. */
export function measureFilterAccepts(filter, snapKind) {
  return (filter !== "edges" || snapKind === "edge") && (filter !== "faces" || snapKind === "face");
}

/** What Measure's snapping filter offers to snap to: the faces, the edges, both, or neither (free points). */
export function measureFilterSnaps(filter) {
  return { faces: filter === "all" || filter === "faces", edges: filter === "all" || filter === "edges" };
}
