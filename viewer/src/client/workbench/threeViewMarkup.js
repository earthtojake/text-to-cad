export const THREE_VIEW_MARKUP_SCHEMA = "cad-viewer-three-view-markup";
export const THREE_VIEW_MARKUP_VERSION = 1;

export const THREE_VIEW_MARKUP_VIEWS = Object.freeze([
  Object.freeze({
    id: "front",
    label: "Front",
    plane: "XZ",
    cameraPreset: "yNeg",
    lookingAlong: "+Y",
    screenAxes: Object.freeze({ right: "+X", up: "+Z" })
  }),
  Object.freeze({
    id: "back",
    label: "Back",
    plane: "XZ",
    cameraPreset: "y",
    lookingAlong: "-Y",
    screenAxes: Object.freeze({ right: "-X", up: "+Z" })
  }),
  Object.freeze({
    id: "top",
    label: "Top",
    plane: "XY",
    cameraPreset: "z",
    lookingAlong: "-Z",
    screenAxes: Object.freeze({ right: "+X", up: "+Y" })
  }),
  Object.freeze({
    id: "bottom",
    label: "Bottom",
    plane: "XY",
    cameraPreset: "zNeg",
    lookingAlong: "+Z",
    screenAxes: Object.freeze({ right: "-X", up: "+Y" })
  }),
  Object.freeze({
    id: "right",
    label: "Right",
    plane: "YZ",
    cameraPreset: "x",
    lookingAlong: "-X",
    screenAxes: Object.freeze({ right: "+Y", up: "+Z" })
  }),
  Object.freeze({
    id: "left",
    label: "Left",
    plane: "YZ",
    cameraPreset: "xNeg",
    lookingAlong: "+X",
    screenAxes: Object.freeze({ right: "-Y", up: "+Z" })
  })
]);

export const THREE_VIEW_MARKUP_INTENTS = Object.freeze([
  Object.freeze({
    id: "remove",
    label: "Remove / cut",
    color: "#ef4444",
    fillColor: "rgba(239, 68, 68, 0.22)"
  }),
  Object.freeze({
    id: "add",
    label: "Add material",
    color: "#22c55e",
    fillColor: "rgba(34, 197, 94, 0.22)"
  }),
  Object.freeze({
    id: "move",
    label: "Move / rotate",
    color: "#3b82f6",
    fillColor: "rgba(59, 130, 246, 0.22)"
  }),
  Object.freeze({
    id: "hardware",
    label: "Servo / hardware",
    color: "#a855f7",
    fillColor: "rgba(168, 85, 247, 0.22)"
  }),
  Object.freeze({
    id: "note",
    label: "General note",
    color: "#f59e0b",
    fillColor: "rgba(245, 158, 11, 0.22)"
  })
]);

const INTENT_IDS = new Set(THREE_VIEW_MARKUP_INTENTS.map((intent) => intent.id));
const VIEW_BY_ID = new Map(THREE_VIEW_MARKUP_VIEWS.map((view) => [view.id, view]));

function cleanText(value) {
  return String(value || "").trim();
}

function finiteUnitCoordinate(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return null;
  }
  return Math.min(Math.max(number, 0), 1);
}

function sanitizePoint(point) {
  const x = finiteUnitCoordinate(point?.x);
  const y = finiteUnitCoordinate(point?.y);
  return x === null || y === null ? null : { x, y };
}

function sanitizePoints(points) {
  return (Array.isArray(points) ? points : [])
    .map(sanitizePoint)
    .filter(Boolean);
}

function sanitizeStroke(stroke, index) {
  const points = sanitizePoints(stroke?.points);
  const fillPoints = sanitizePoints(stroke?.fillPoints);
  if (!points.length && !fillPoints.length) {
    return null;
  }
  const intent = INTENT_IDS.has(stroke?.intent) ? stroke.intent : "note";
  const intentStyle = THREE_VIEW_MARKUP_INTENTS.find((candidate) => candidate.id === intent);
  return {
    id: cleanText(stroke?.id) || `stroke-${index + 1}`,
    tool: cleanText(stroke?.tool) || "freehand",
    intent,
    color: cleanText(stroke?.color) || intentStyle.color,
    fillColor: cleanText(stroke?.fillColor) || intentStyle.fillColor,
    haloColor: cleanText(stroke?.haloColor) || "rgba(255, 255, 255, 0.94)",
    points,
    ...(fillPoints.length ? { fillPoints } : {}),
    ...(stroke?.guessed === true ? { guessed: true } : {})
  };
}

function sanitizeView(view, definition) {
  return {
    id: definition.id,
    label: definition.label,
    plane: definition.plane,
    cameraPreset: definition.cameraPreset,
    lookingAlong: definition.lookingAlong,
    screenAxes: definition.screenAxes,
    note: cleanText(view?.note),
    strokes: (Array.isArray(view?.strokes) ? view.strokes : [])
      .map(sanitizeStroke)
      .filter(Boolean)
  };
}

export function emptyThreeViewMarkupState() {
  return Object.fromEntries(
    THREE_VIEW_MARKUP_VIEWS.map((view) => [
      view.id,
      {
        note: "",
        strokes: []
      }
    ])
  );
}

export function normalizeThreeViewMarkupDocument(value) {
  if (!value || typeof value !== "object") {
    throw new Error("Markup file must contain a JSON object.");
  }
  if (value.schema !== THREE_VIEW_MARKUP_SCHEMA) {
    throw new Error(`Unsupported markup schema: ${cleanText(value.schema) || "missing"}.`);
  }
  if (Number(value.version) !== THREE_VIEW_MARKUP_VERSION) {
    throw new Error(`Unsupported markup version: ${value.version ?? "missing"}.`);
  }

  const incomingViews = new Map(
    (Array.isArray(value.views) ? value.views : [])
      .filter((view) => VIEW_BY_ID.has(view?.id))
      .map((view) => [view.id, view])
  );

  return {
    schema: THREE_VIEW_MARKUP_SCHEMA,
    version: THREE_VIEW_MARKUP_VERSION,
    createdAt: cleanText(value.createdAt) || new Date().toISOString(),
    coordinateSystem: "cad-z-up-v1",
    source: {
      file: cleanText(value.source?.file),
      modelKey: cleanText(value.source?.modelKey),
      renderFormat: cleanText(value.source?.renderFormat)
    },
    overallNote: cleanText(value.overallNote),
    views: THREE_VIEW_MARKUP_VIEWS.map((definition) => (
      sanitizeView(incomingViews.get(definition.id), definition)
    ))
  };
}

export function buildThreeViewMarkupDocument({
  sourceFile = "",
  modelKey = "",
  renderFormat = "step",
  overallNote = "",
  viewState = {},
  includeEmptyViews = true
} = {}) {
  const document = normalizeThreeViewMarkupDocument({
    schema: THREE_VIEW_MARKUP_SCHEMA,
    version: THREE_VIEW_MARKUP_VERSION,
    createdAt: new Date().toISOString(),
    coordinateSystem: "cad-z-up-v1",
    source: {
      file: sourceFile,
      modelKey,
      renderFormat
    },
    overallNote,
    views: THREE_VIEW_MARKUP_VIEWS.map((view) => ({
      ...view,
      note: viewState?.[view.id]?.note || "",
      strokes: viewState?.[view.id]?.strokes || []
    }))
  });
  if (!includeEmptyViews) {
    document.views = document.views.filter((view) => (
      Boolean(view.note) || view.strokes.length > 0
    ));
  }
  return document;
}

export function parseThreeViewMarkupDocument(text) {
  let parsed;
  try {
    parsed = JSON.parse(String(text || ""));
  } catch {
    throw new Error("The selected file is not valid JSON.");
  }
  return normalizeThreeViewMarkupDocument(parsed);
}

export function viewStateFromThreeViewMarkupDocument(document) {
  const normalized = normalizeThreeViewMarkupDocument(document);
  return Object.fromEntries(
    normalized.views.map((view) => [
      view.id,
      {
        note: view.note,
        strokes: view.strokes
      }
    ])
  );
}

export function markupFilenameStem(sourceFile) {
  const filename = cleanText(sourceFile).split(/[\\/]/u).pop() || "cad-part";
  const stem = filename.replace(/\.[^.]+$/u, "") || "cad-part";
  return stem.replace(/[^a-z0-9_-]+/giu, "_").replace(/^_+|_+$/gu, "") || "cad-part";
}
