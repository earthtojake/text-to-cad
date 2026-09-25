// Annotations: notes a person pins to the geometry they selected, for prompting. Each one is
// the references that were selected when it was made (the portable `selector`, e.g.
// "o1.1.e3", and a display label) and the note. Nothing is sent anywhere by making one: the
// person adds an annotation to the chat box and presses Send themselves.
//
// They live in the STEP's own slice of the tab's record (`stepSessionRecord.js`), and unlike
// the tree they are NOT dropped when the model is rebuilt: a note about an edge is still the
// person's note after the agent changes the part. Its chips simply stop resolving if the edge
// is gone.
//
//   { id, references: [{ selector, label }], text, sent, anchor }
//
// `anchor` is where the annotation's dot sits on the model: a point in model space (the
// frame selector geometry is authored in, before the viewer re-centres the model), and the
// face's outward normal when it was made on one face, so a dot on the far side can dim.

const text = value => String(value ?? "").trim();
const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** The most a tab keeps; the oldest go first. Annotations are a scratchpad, not a store. */
export const MAX_ANNOTATIONS = 50;

const TOPOLOGY_NAMES = Object.freeze({ f: "Face", e: "Edge", v: "Vertex" });

/**
 * A chip's label for one selector. A part keeps the name the tree gives it; a face, edge or
 * vertex is named by its type and number ("o1.1.e3" -> "Edge 3"); a merged group of faces
 * ("o1.1.f2,o1.1.f5") is counted.
 */
export function annotationReferenceLabel(selector, label = "") {
  const value = text(selector);
  const given = text(label);
  if (given) return given;
  const parts = value.split(",").map(text).filter(Boolean);
  if (parts.length > 1) {
    const kinds = new Set(parts.map(part => part.match(/\.([fev])\d+$/)?.[1] || ""));
    const [kind] = kinds;
    return kinds.size === 1 && TOPOLOGY_NAMES[kind] ? `${parts.length} ${TOPOLOGY_NAMES[kind].toLowerCase()}s` : `${parts.length} references`;
  }
  const topology = value.match(/\.([fev])(\d+)$/);
  if (topology) return `${TOPOLOGY_NAMES[topology[1]]} ${topology[2]}`;
  return value || "Model";
}

function readReference(value) {
  if (!plainObject(value)) return null;
  const selector = text(value.selector);
  if (!selector) return null;
  return { selector, label: annotationReferenceLabel(selector, value.label) };
}

const point = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? [...value] : null;

function readAnchor(value) {
  if (!plainObject(value)) return null;
  const at = point(value.point);
  return at ? { point: at, normal: point(value.normal) } : null;
}

function readAnnotation(value) {
  if (!plainObject(value)) return null;
  const id = text(value.id);
  const references = Array.isArray(value.references) ? value.references.map(readReference).filter(Boolean) : [];
  if (!id || !references.length) return null;
  return { id, references, text: String(value.text ?? ""), sent: value.sent === true, anchor: readAnchor(value.anchor) };
}

const boxCenter = box => point(box?.min) && point(box?.max) ? box.min.map((min, axis) => (min + box.max[axis]) / 2) : null;

/**
 * Where a new annotation's dot goes: the middle of what it is about. A face or edge gives its
 * own centre (or its box's), a part its box's; several give the average of theirs. The normal
 * is kept only for a single face, the one case where "facing away" means something.
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

/** A stored list as it can be used: malformed entries dropped, ids unique, the newest kept. */
export function readAnnotations(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const list = [];
  for (const item of value) {
    const annotation = readAnnotation(item);
    if (!annotation || seen.has(annotation.id)) continue;
    seen.add(annotation.id);
    list.push(annotation);
  }
  return list.slice(-MAX_ANNOTATIONS);
}

let counter = 0;
const nextId = () => `a${Date.now().toString(36)}${(counter++).toString(36)}`;

/** A new annotation on the given references, or null when there is nothing to pin it to. */
export function createAnnotation(references, note, { id = nextId(), anchor = null } = {}) {
  return readAnnotation({ id, references, text: note, sent: false, anchor });
}

export function addAnnotation(list, annotation) {
  return annotation ? readAnnotations([...list, annotation]) : list;
}

/** A changed note is a new request: it has not been sent in this form. */
export function editAnnotation(list, id, note) {
  return list.map(annotation => annotation.id === id && annotation.text !== note
    ? { ...annotation, text: note, sent: false } : annotation);
}

export function removeAnnotation(list, id) {
  return list.filter(annotation => annotation.id !== id);
}

export function markAnnotationSent(list, id) {
  return list.map(annotation => annotation.id === id ? { ...annotation, sent: true } : annotation);
}

/** Whether a delivery put the annotation where the person can send it. */
export function annotationDelivered(result) {
  return ["added", "copied", "partial"].includes(result?.status);
}
