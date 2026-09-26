import { normalizeCadRefSelectors, parseCadRefSelector } from "@hardcore/core/lib/cadRefs.js";

// Annotations: notes a person pins to the geometry they selected, for prompting. Each one is the
// references that were selected when it was made (the portable `selector`, e.g. "o1.1.e3", and a
// display label), the note, and `anchor`: where its dot sits on the model. The chat box is where an
// annotation lives: making one puts it there, and the model shows a dot for each one it holds.
//
//   { id, references: [{ selector, label }], text, anchor: { point, normal } }
//
// `anchor.point` is in model space (the frame selector geometry is authored in, before the viewer
// re-centres the model); `anchor.normal` is the face's outward normal when the annotation was made
// on one face, so a dot on the far side can dim.

const text = value => String(value ?? "").trim();
const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);

const TOPOLOGY_NAMES = Object.freeze({ face: "Face", edge: "Edge", vertex: "Vertex" });

/**
 * A chip's label for one selector. A part keeps the name the tree gives it; a face, edge or vertex
 * is named by its type and number ("o1.1.e3" -> "Edge 3"); a group ("o1.1.f2,f5") is counted; no
 * selector at all is the whole model.
 */
export function annotationReferenceLabel(selector, label = "") {
  const given = text(label);
  if (given) return given;
  const value = text(selector);
  if (!value) return "Whole model";
  const selectors = normalizeCadRefSelectors(value);
  if (selectors.length > 1) {
    const types = new Set(selectors.map(item => parseCadRefSelector(item).selectorType));
    const [type] = types;
    return types.size === 1 && TOPOLOGY_NAMES[type] ? `${selectors.length} ${TOPOLOGY_NAMES[type].toLowerCase()}s` : `${selectors.length} references`;
  }
  const { selectorType, ordinal } = parseCadRefSelector(value);
  return TOPOLOGY_NAMES[selectorType] && ordinal ? `${TOPOLOGY_NAMES[selectorType]} ${ordinal}` : value;
}

// An empty selector is the whole file: what a selection of a single part's whole model copies as.
function readReference(value) {
  if (!plainObject(value)) return null;
  const selector = text(value.selector);
  return { selector, label: annotationReferenceLabel(selector, value.label) };
}

const point = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? [...value] : null;

function readAnchor(value) {
  if (!plainObject(value)) return null;
  const at = point(value.point);
  return at ? { point: at, normal: point(value.normal) } : null;
}

// An annotation is shown only as its dot, so one with nowhere to sit is not an annotation.
function readAnnotation(value) {
  if (!plainObject(value)) return null;
  const id = text(value.id);
  const references = Array.isArray(value.references) ? value.references.map(readReference).filter(Boolean) : [];
  const anchor = readAnchor(value.anchor);
  if (!id || !references.length || !anchor) return null;
  return { id, references, text: String(value.text ?? ""), anchor };
}

/** A stored list as it can be used: malformed entries dropped, ids unique. */
export function readAnnotations(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  return value.map(readAnnotation).filter(annotation => annotation && !seen.has(annotation.id) && seen.add(annotation.id));
}

const boxCenter = box => point(box?.min) && point(box?.max) ? box.min.map((min, axis) => (min + box.max[axis]) / 2) : null;

/**
 * Where a new annotation's dot goes: the middle of what it is about. A face or edge gives its own
 * centre (or its box's), a part its box's; several give the average of theirs. The normal is kept
 * only for a single face, the one case where "facing away" means something.
 *
 * @param {Array<{ center?: number[], bbox?: object, normal?: number[], selectorType?: string }>} geometry
 */
export function annotationAnchor(geometry) {
  const points = geometry.map(item => point(item?.center) || boxCenter(item?.bbox)).filter(Boolean);
  if (!points.length) return null;
  const at = [0, 1, 2].map(axis => points.reduce((sum, value) => sum + value[axis], 0) / points.length);
  const single = geometry.length === 1 && geometry[0]?.selectorType === "face" ? point(geometry[0].normal) : null;
  return { point: at, normal: single };
}

let counter = 0;
const nextId = () => `a${Date.now().toString(36)}${(counter++).toString(36)}`;

/** A new annotation on the given references at `anchor`, or null without either. */
export function createAnnotation(references, note, { id = nextId(), anchor = null } = {}) {
  return readAnnotation({ id, references, text: note, anchor });
}

/** Whether a delivery put the annotation where the person can send it. */
export function annotationDelivered(result) {
  return ["added", "copied", "partial"].includes(result?.status);
}
