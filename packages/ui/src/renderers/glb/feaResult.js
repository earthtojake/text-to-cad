/**
 * An FEA result inside a GLB, as `cadgen fea solve` writes it, and what the
 * viewer can do with it without a second file.
 *
 * The writer (cadgen `_internal/fea/outputs.py`) stores the raw fields as
 * custom vertex attributes beside the baked colour: `_VON_MISES` (float, MPa)
 * and `_DISPLACEMENT` (vec3, glTF units, i.e. metres, unscaled), and puts in
 * the mesh extras a `fields` list describing each one (`attribute`, `name`,
 * `units`, `min`, `max`, `attribute_scale`), `deformation_scale` (the
 * multiplier already baked into the positions), the colour `ramp` it used and
 * the result's `safety_factor` (null when it has none). A result written since
 * the study was recorded also carries the `study` it was solved for (material,
 * fixtures, loads, mesh), `faces` (the occurrence's face refs) and `_FACE`, the
 * index into `faces` of the face each vertex lies on (-1 for none). A bonded
 * assembly also carries `parts` (name, material, peak stress, safety factor of
 * each part), `connections` (each detected pair: type, contact area, gap and the
 * interface faces of both sides), `_PART` (the index into `parts` of the part
 * each vertex belongs to) and the weakest part's name and peak; a single part has
 * none of these. A study that says what the viewer should offer carries its `view`
 * (`feaControls`): the controls of Study's What you see, each shown `when` the checks say, named
 * presets, Study's `sections` and whether the loads and fixtures are drawn. A result since the
 * study picked its checks carries `checks`, each judged (`feaVerdict`); an older one's verdict is
 * its safety factor's, the stress check derived from the fields it has.
 * GLTFLoader lower-cases custom attribute names and copies extras into
 * `userData`, which is what is read here.
 *
 * Everything is in-place on the loaded geometry: recolouring rewrites the
 * `color` bytes, re-scaling the deformation rewrites `position` from the
 * file's own positions and displacement vector. The originals are kept on
 * the mesh so any scale or field can be chosen in any order, and a request
 * for what is already shown does nothing.
 */
import { Raycaster } from "three";
import { clamp } from "@text-to-cad/core/common/numbers.js";

const GENERATOR = "cadgen fea";

// The ramp the writer uses when a file carries none: blue -> red.
export const DEFAULT_RAMP = Object.freeze([
  [0.0, [0.05, 0.10, 0.90]],
  [0.25, [0.05, 0.85, 0.95]],
  [0.5, [0.10, 0.85, 0.15]],
  [0.75, [0.98, 0.90, 0.10]],
  [1.0, [0.90, 0.08, 0.05]],
]);

/** RGB in [0, 1] for t in [0, 1], piecewise linear between the ramp stops. */
export function feaRamp(t, stops = DEFAULT_RAMP) {
  const x = clamp(Number(t) || 0, 0, 1);
  for (let i = 1; i < stops.length; i += 1) {
    const [t1, c1] = stops[i];
    if (x <= t1) {
      const [t0, c0] = stops[i - 1];
      const f = t1 === t0 ? 0 : (x - t0) / (t1 - t0);
      if (f >= 1) return [...c1];
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f];
    }
  }
  return [...stops[stops.length - 1][1]];
}

/** The CSS gradient of the ramp, low at the start, for a colour bar. */
export function feaRampGradient(stops = DEFAULT_RAMP, direction = "to right") {
  const parts = stops.map(([t, [r, g, b]]) =>
    `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}) ${Math.round(t * 100)}%`);
  return `linear-gradient(${direction}, ${parts.join(", ")})`;
}

/** 256 RGB byte triples of the ramp: one lookup per vertex instead of an interpolation. */
function rampTable(stops) {
  const table = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const [r, g, b] = feaRamp(i / 255, stops);
    table[i * 3] = Math.round(r * 255);
    table[i * 3 + 1] = Math.round(g * 255);
    table[i * 3 + 2] = Math.round(b * 255);
  }
  return table;
}

function rampStops(raw) {
  const valid = Array.isArray(raw) && raw.length >= 2 && raw.every((stop) =>
    Array.isArray(stop) && Number.isFinite(stop[0]) && Array.isArray(stop[1]) && stop[1].length === 3);
  return valid ? raw : DEFAULT_RAMP;
}

const vector = (value) => (Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? value.map(Number) : null);

/** The result's findings, kept for the agent (the viewer shows none), in the file's order, each with its position as `index`; malformed ones are left out. */
function readFindings(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((finding) => finding && (typeof finding.summary === "string" || typeof finding.description === "string"))
    .map((finding, index) => ({
      check: String(finding.check || "fea"),
      severity: finding.severity === "error" ? "error" : "warning",
      type: String(finding.type || ""),
      summary: String(finding.summary || ""),
      description: String(finding.description || ""),
      index,
      items: (Array.isArray(finding.items) ? finding.items : []).map((item) => ({
        text: String(item?.text || ""),
        ref: typeof item?.ref === "string" && item.ref ? item.ref : null,
        at: vector(item?.at),
      })),
    }));
}

const text = (value) => (typeof value === "string" ? value : "");
const faceRefs = (raw) => (Array.isArray(raw) ? raw.filter((ref) => typeof ref === "string" && ref) : []);
const finiteOrNull = (value) => (Number.isFinite(value) ? Number(value) : null);

/** An assembly's parts in `_PART` order (a malformed entry keeps its place, empty); [] for a single part. */
function readParts(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.map((part) => ({
    ref: text(part?.ref), name: text(part?.name), material: text(part?.material), yieldMPa: finiteOrNull(part?.yield_MPa),
    peakMPa: finiteOrNull(part?.peak_MPa), safetyFactor: finiteOrNull(part?.safety_factor), maxDisplacementMm: finiteOrNull(part?.max_displacement_mm),
  }));
}

/** An assembly's detected pairs: `between` the two part refs, `names` theirs, the interface `faces` of both sides (none for a free pair). */
function readConnections(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.filter((joint) => joint && Array.isArray(joint.between) && joint.between.length === 2).map((joint) => ({
    between: joint.between.map(text),
    names: [0, 1].map((side) => text(joint.names?.[side]) || text(joint.between[side])),
    type: text(joint.type) || "free",
    areaMm2: finiteOrNull(joint.area_mm2),
    gapMm: finiteOrNull(joint.gap_mm),
    faces: faceRefs(joint.faces),
  }));
}

/**
 * The study's `view`, as the file carries it: `controls` (null when it names none), `presets` and
 * `show`. null for a result with no view: the viewer's own defaults. Each control is checked where
 * it is used (`feaControls`), so one this viewer does not know is skipped rather than refused.
 */
function readView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  return {
    sections: Array.isArray(raw.sections) ? raw.sections.filter((name) => typeof name === "string") : null,
    controls: Array.isArray(raw.controls) ? raw.controls.filter((control) => control && typeof control === "object") : null,
    presets: Array.isArray(raw.presets) ? raw.presets.filter((preset) => preset && typeof preset.label === "string" && preset.label.trim()) : [],
    show: raw.show && typeof raw.show === "object" ? raw.show : {},
  };
}

/** The checks this viewer can judge; a kind from a newer cadgen is skipped. */
export const FEA_CHECK_KINDS = Object.freeze(["stress", "displacement"]);

/**
 * The checks the file judged (`kind`, `label`, `value`, `limit`, `unit`, `ratio`, `closeAt`, `status`, `where`),
 * in the study's order, those of a kind this viewer does not know or with numbers it cannot use left
 * out; null for a result written before checks were.
 */
function readChecks(raw) {
  if (!Array.isArray(raw)) return null;
  return raw.filter((check) => check && FEA_CHECK_KINDS.includes(check.kind) && Number.isFinite(check.value) && Number.isFinite(check.limit)
    && check.limit > 0 && Number.isFinite(check.ratio))
    .map((check) => ({
      kind: check.kind, label: text(check.label), value: Number(check.value), limit: Number(check.limit), unit: text(check.unit),
      ratio: Number(check.ratio), closeAt: Number.isFinite(check.close_at) ? Number(check.close_at) : 1,
      margin: Number.isFinite(check.margin) && check.margin >= 1 ? Number(check.margin) : null,
      status: ["fails", "close", "passes"].includes(check.status) ? check.status : null, part: text(check.part),
    }));
}

/** The study the result was solved for, as the file records it; null for a result written before it did. */
function readStudy(raw) {
  if (!raw || typeof raw !== "object") return null;
  const material = raw.material && typeof raw.material === "object"
    ? { name: text(raw.material.name), yieldMPa: finiteOrNull(raw.material.yield_MPa) } : null;
  const mesh = raw.mesh && typeof raw.mesh === "object"
    ? { sizeMm: finiteOrNull(raw.mesh.size_mm), refinedFromMm: finiteOrNull(raw.mesh.refined_from_mm) } : null;
  return {
    material,
    fixtures: (Array.isArray(raw.fixtures) ? raw.fixtures : []).filter(Boolean)
      .map((fixture) => ({ type: text(fixture.type) || "fixed", faces: faceRefs(fixture.faces) })),
    loads: (Array.isArray(raw.loads) ? raw.loads : []).filter(Boolean).map((load) => ({
      type: text(load.type), faces: faceRefs(load.faces), vector: vector(load.vector_N), pressure: finiteOrNull(load.pressure_MPa),
    })),
    mesh,
    margin: Number.isFinite(raw.margin) && raw.margin >= 1 ? Number(raw.margin) : null,
  };
}

/**
 * The absolute path of the STEP a result was solved from. The file records its name (`document`),
 * which is the GLB's own folder's; an absolute one is kept. "" when it names nothing.
 */
export function resultSourcePath(glbPath, document) {
  const named = String(document || "").trim();
  if (!named) return "";
  const absolute = /^(?:[A-Za-z]:)?[\\/]/.test(named);
  const parts = absolute ? named.split("/") : [...String(glbPath || "").split("/").slice(0, -1), ...named.split("/")];
  const out = [];
  for (const part of parts) {
    if (part === "..") out.pop();
    else if (part !== ".") out.push(part);
  }
  return out.join("/");
}

/** A finding's `ref` as a selector in the prompt grammar: the token's leading "#" is not part of it. */
export const findingSelector = (ref) => String(ref).replace(/^#/, "");

/**
 * The FEA result a loaded glTF scene root carries, or null for any other GLB.
 */
export function readFeaResult(root) {
  if (!root?.traverse) {
    return null;
  }
  let found = null;
  root.traverse((object) => {
    if (found || !object?.isMesh || !object.geometry) {
      return;
    }
    const extras = object.userData || {};
    if (extras.generator !== GENERATOR || !Array.isArray(extras.fields)) {
      return;
    }
    const fields = extras.fields
      .filter((field) => typeof field?.attribute === "string" && object.geometry.getAttribute(field.attribute.toLowerCase()))
      .map((field) => ({
        attribute: field.attribute.toLowerCase(),
        name: String(field.name || field.attribute),
        units: String(field.units || ""),
        min: Number(field.min) || 0,
        max: Number(field.max) || 0,
        attributeScale: Number(field.attribute_scale) || 1,
      }));
    if (fields.length === 0) {
      return;
    }
    found = {
      mesh: object,
      name: String(extras.name || ""),
      document: String(extras.document || ""),
      occurrence: String(extras.occurrence || ""),
      deformationScale: Number(extras.deformation_scale) || 1,
      safetyFactor: Number.isFinite(extras.safety_factor) ? extras.safety_factor : null,
      fields,
      ramp: rampStops(extras.ramp),
      findings: readFindings(extras.findings),
      study: readStudy(extras.study),
      faces: faceRefs(extras.faces),
      parts: readParts(extras.parts),
      connections: readConnections(extras.connections),
      weakestPart: text(extras.weakest_part),
      weakestPartPeakMPa: finiteOrNull(extras.weakest_part_peak_MPa),
      maxDisplacementMm: finiteOrNull(extras.max_displacement_mm),
      view: readView(extras.view),
      checks: readChecks(extras.checks),
    };
  });
  return found;
}

/** The file's own positions, each field's values once read, and what is currently shown, kept on the mesh. */
function shown(mesh) {
  let kept = mesh.userData.__fea;
  if (!kept) {
    kept = { position: Float32Array.from(mesh.geometry.getAttribute("position").array), values: {}, field: null, scale: null };
    mesh.userData.__fea = kept;
  }
  return kept;
}

/** The positions the file wrote (its own deformation scale baked in), whatever is drawn now. */
export const filePositions = (mesh) => shown(mesh).position;

/** A field's values, read from the geometry once: a ramp playing recolours every frame. */
function keptValues(mesh, field) {
  const kept = shown(mesh);
  if (!kept.values[field.attribute]) kept.values[field.attribute] = fieldValues(mesh, field);
  return kept.values[field.attribute];
}

/** The scalar value per vertex of a field: the attribute itself, or a vector's magnitude, in the field's units. */
export function fieldValues(mesh, field) {
  const attribute = mesh.geometry.getAttribute(field.attribute);
  if (!attribute) {
    return null;
  }
  const { count, itemSize: size, array } = attribute;
  const out = new Float32Array(count);
  const scale = field.attributeScale || 1;
  for (let i = 0; i < count; i += 1) {
    if (size === 1) {
      out[i] = array[i] * scale;
    } else {
      let sum = 0;
      for (let k = 0; k < size; k += 1) {
        const v = array[i * size + k];
        sum += v * v;
      }
      out[i] = Math.sqrt(sum) * scale;
    }
  }
  return out;
}

// What a chosen face is tinted toward: no colour of the ramp, two thirds of the way, so a chosen face
// reads at the ramp's blue end and its red end alike while its stress still shows through.
const HIGHLIGHT = Object.freeze([255, 64, 242]);
const HIGHLIGHT_BLEND = 0.68;
// A chosen joint also tints the two parts it joins, lightly: the interface faces sit hidden between them.
const SOFT_BLEND = 0.3;
// What a vertex under a threshold is drawn: a neutral grey, no colour of the ramp.
const BELOW_THRESHOLD = Object.freeze([150, 150, 150]);

/** The face each vertex lies on (`_FACE`), or null for a result that does not say. */
function vertexFaces(mesh) {
  const attribute = mesh.geometry.getAttribute("_face");
  return attribute?.itemSize === 1 ? attribute.array : null;
}

/** The part each vertex belongs to (`_PART`), or null for a single part's result. */
function vertexParts(mesh) {
  const attribute = mesh.geometry.getAttribute("_part");
  return attribute?.itemSize === 1 ? attribute.array : null;
}

/**
 * Rewrite the mesh's vertex colours from one field over `[field.min, field.max]`, with the
 * vertices of the faces in `highlight` (indices into the result's `faces`) and of the parts in
 * `parts` (indices into its `parts`) tinted, and the parts in `softParts` tinted lightly (a joint's
 * two parts; its interface faces keep the full tint).
 * `scaling`, for a load other than the solved one: the values are drawn at `valueScale` times
 * their own and the ramp spans `rangeScale` times the field's range (both the load scale; while a
 * load ramp plays the values climb toward the range). `threshold`: `{ field, value, scale }`, every
 * vertex whose value of that field (times `scale`) is under `value` drawn grey.
 * Returns true when the colours changed; false when that field and tint were already shown.
 */
export function recolorByField(mesh, field, ramp = DEFAULT_RAMP, highlight = null, parts = null, softParts = null,
  { valueScale = 1, rangeScale = 1, threshold = null } = {}) {
  const color = mesh.geometry.getAttribute("color");
  // The attribute's presence, not its values: a ramp playing recolours every frame, and keptValues
  // reads them once per field.
  const values = mesh.geometry.getAttribute(field.attribute) && keptValues(mesh, field);
  if (!color || !values) {
    return false;
  }
  const kept = shown(mesh);
  const under = threshold?.field ? keptValues(mesh, threshold.field) : null;
  const faces = vertexFaces(mesh);
  const tinted = faces && highlight?.length ? new Set(highlight) : null;
  const partOf = vertexParts(mesh);
  const tintedParts = partOf && parts?.length ? new Set(parts) : null;
  const lightParts = partOf && softParts?.length ? new Set(softParts) : null;
  const sorted = (set) => (set ? [...set].sort((a, b) => a - b).join(",") : "");
  const cut = under ? `${threshold.field.attribute}<${threshold.value}x${threshold.scale}` : "";
  const key = `${field.attribute}x${valueScale}/${rangeScale}|${cut}|${sorted(tinted)}|${sorted(tintedParts)}|${sorted(lightParts)}`;
  if (kept.field === key) {
    return false;
  }
  const table = rampTable(ramp);
  const low = field.min * rangeScale;
  const span = (field.max - field.min) * rangeScale;
  const stride = color.itemSize;
  const bytes = color.array;
  const cutScale = under ? threshold.scale ?? 1 : 1;
  for (let i = 0; i < values.length; i += 1) {
    const t = span > 0 ? clamp((values[i] * valueScale - low) / span, 0, 1) : 0;
    const entry = Math.round(t * 255) * 3;
    const grey = under !== null && under[i] * cutScale < threshold.value;
    const base = i * stride;
    const tint = (tinted !== null && tinted.has(Math.round(faces[i]))) || (tintedParts !== null && tintedParts.has(Math.round(partOf[i])));
    const blend = tint ? HIGHLIGHT_BLEND : lightParts !== null && lightParts.has(Math.round(partOf[i])) ? SOFT_BLEND : 0;
    for (let k = 0; k < 3; k += 1) {
      const own = grey ? BELOW_THRESHOLD[k] : table[entry + k];
      bytes[base + k] = blend ? Math.round(own + (HIGHLIGHT[k] - own) * blend) : own;
    }
    if (stride > 3) bytes[base + 3] = 255;
  }
  color.needsUpdate = true;
  kept.field = key;
  return true;
}

/**
 * Show the displacement at `scale` times its true size. The file's positions
 * already carry `baseScale` times the displacement, so the change is
 * `(scale - baseScale)` times the displacement vector. Returns true when the
 * positions changed; false when that scale was already shown.
 */
export function applyDeformation(mesh, scale, baseScale) {
  const geometry = mesh.geometry;
  const position = geometry.getAttribute("position");
  const displacement = geometry.getAttribute("_displacement");
  if (!position || !displacement || displacement.itemSize !== 3) {
    return false;
  }
  const kept = shown(mesh);
  const wanted = Number(scale) || 0;
  if (kept.scale === wanted || (kept.scale === null && wanted === (Number(baseScale) || 0))) {
    kept.scale = wanted;
    return false;
  }
  const delta = wanted - (Number(baseScale) || 0);
  const out = position.array;
  const base = kept.position;
  const d = displacement.array;
  for (let i = 0; i < out.length; i += 1) {
    out[i] = base[i] + delta * d[i];
  }
  position.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  kept.scale = wanted;
  return true;
}

/** Sensible slider bounds for the deformation scale, with no view to say: 0 to four times the file's own. */
export function deformationRange(baseScale) {
  const max = Math.max(1, (Number(baseScale) || 1) * 4);
  const step = max >= 100 ? 1 : max >= 10 ? 0.5 : 0.1;
  return { min: 0, max, step };
}

// The fields in plain words, short enough for the panel's one width; the file's own names (von
// Mises stress) are the colour bar's.
export const FIELD_WORDS = Object.freeze({ _von_mises: "Stress", _displacement: "Displacement" });

/** What a view's control can move, the closed set the viewer knows how to apply. */
export const FEA_DRIVES = Object.freeze(["field", "deformation", "load_scale", "threshold"]);
const DRIVE_TYPES = Object.freeze({ field: "enum", deformation: "number", load_scale: "number", threshold: "number" });
const DRIVE_LABELS = Object.freeze({ field: "Field", deformation: "Deformation", load_scale: "Load", threshold: "Show above" });

/** A view's field name ("von_mises") as the attribute the result carries ("_von_mises"). */
const fieldAttribute = (name) => `_${String(name || "").toLowerCase()}`;

/** A select's options over these fields, in this order, each that the result carries, in plain words. */
function fieldOptions(result, attributes) {
  return attributes.map((attribute) => result.fields.find((entry) => entry.attribute === attribute)).filter(Boolean)
    .map((entry) => ({ value: entry.attribute, label: FIELD_WORDS[entry.attribute] || entry.name }));
}

const finiteNumber = (value) => typeof value === "number" && Number.isFinite(value);

/**
 * Study's What you see controls, as generic parameters (`@text-to-cad/core/common/parameters.js`: `id`,
 * `type`, `label`, `min`, `max`, `defaultValue`, `unit`, `options`) with `drives`, what each moves:
 * `field` (which field the colours show; its options are attributes), `deformation` (how many times
 * the displacement is drawn), `load_scale` (the load as a multiple of the solved one) and
 * `threshold` (values of its `field` under it drawn grey). They are the study's `view.controls`, in
 * its order, with its labels and ranges; one whose `drives` or `type` this viewer does not know, or
 * whose range or fields it cannot use, is skipped. With no view, or none of its controls this viewer
 * can draw (an empty list, or all from a newer cadgen), the viewer's own: a field select
 * over every field, opening on the first (stress), and a deformation slider from 0 to four times the
 * file's own scale. The view's are labelled in the agent's words, often a sentence: their labels run
 * over the whole row (`wideLabel`), where the default two keep the one-column look they always had.
 */
export function feaControls(result) {
  const every = result.fields.map((entry) => entry.attribute);
  const chosen = result.view?.controls ? viewControls(result, every) : [];
  if (!chosen.length) {
    const range = deformationRange(result.deformationScale);
    return [
      { id: "field", drives: "field", type: "enum", label: "Field", ariaLabel: "Result field", hideLabel: true,
        options: fieldOptions(result, every), defaultValue: every[0] },
      { id: "deformation", drives: "deformation", type: "number", label: "Deformation", ariaLabel: "Deformation scale",
        labelTitle: "How much larger than life the displacement is drawn", min: range.min, max: range.max, step: range.step,
        defaultValue: clamp(result.deformationScale, range.min, range.max), unit: "×" },
    ];
  }
  return chosen;
}

/** The view's controls this viewer can draw, in its order; none when it names none it knows. */
function viewControls(result, every) {
  const controls = [];
  for (const raw of result.view.controls) {
    const drives = raw.drives;
    const type = DRIVE_TYPES[drives];
    if (!type || (raw.type ?? type) !== type || controls.some((control) => control.drives === drives)) continue;
    const label = typeof raw.label === "string" && raw.label.trim() ? raw.label.trim() : DRIVE_LABELS[drives];
    if (drives === "field") {
      const options = fieldOptions(result, Array.isArray(raw.options) ? raw.options.map(fieldAttribute) : every);
      if (!options.length) continue;
      const opening = options.find((option) => option.value === fieldAttribute(raw.default)) || options[0];
      controls.push({ id: drives, drives, type, label, options, defaultValue: opening.value, wideLabel: true, ...whenOf(raw) });
      continue;
    }
    const min = finiteNumber(raw.min) ? raw.min : 0;
    const max = raw.max;
    if (!finiteNumber(max) || !(min < max)) continue;
    const measured = drives === "threshold" ? result.fields.find((entry) => entry.attribute === fieldAttribute(raw.field)) : null;
    if (drives === "threshold" && !measured) continue;
    const fallback = drives === "load_scale" ? 1 : drives === "deformation" ? result.deformationScale : min;
    const unit = typeof raw.unit === "string" && raw.unit.trim() ? raw.unit.trim() : measured ? measured.units : "×";
    controls.push({
      id: drives, drives, type, label, min, max, defaultValue: clamp(finiteNumber(raw.default) ? raw.default : fallback, min, max), unit, wideLabel: true,
      ...(measured ? { field: measured.attribute } : {}), ...whenOf(raw),
    });
  }
  return controls;
}

/** When a control shows, as the view says: `failing` or `passing`; a control that says neither, or what this viewer does not know, always. */
const whenOf = (raw) => (raw.when === "failing" || raw.when === "passing" ? { when: raw.when } : {});

/** Whether a control with this `when` shows, with the checks failing (or close) or not; null, nothing judged, shows every one. */
const showsWhen = (when, failing) => failing === null || !when || (when === "failing" ? failing : !failing);

/**
 * The controls What you see shows, and what each control does, at the values chosen (`values`, by id):
 * a control shows `when` the checks say, judged at the load shown (`feaFailing`). The load control's
 * own `when` is judged at its default load, where it opens (the load as solved unless the view says),
 * so moving it never hides it, the very control a person drags to see what load would pass. A hidden
 * control acts as if at its default (`values` keeps what was chosen, for when it shows again).
 * `shown`: the controls, in order; `effective`: every control's value, by id; `loadScale`: the load shown.
 */
export function feaShownControls(result, controls, values) {
  const load = controls.find((control) => control.drives === "load_scale") || null;
  const loadShown = !load || showsWhen(load.when, feaFailing(result, load.defaultValue));
  const loadScale = load ? finiteNumber(values[load.id]) && loadShown ? values[load.id] : load.defaultValue : 1;
  const failing = feaFailing(result, loadScale);
  const shown = controls.filter((control) => (control === load ? loadShown : showsWhen(control.when, failing)));
  const effective = Object.fromEntries(controls.map((control) => [control.id, shown.includes(control) ? values[control.id] : control.defaultValue]));
  return { shown, effective, loadScale };
}

/** The parts of Study, in order: the view's `sections` this viewer knows, each once; with none, all four. */
export const FEA_SECTIONS = Object.freeze(["verdict", "setup", "controls", "details"]);
export function feaSections(result) {
  const named = (result.view?.sections || []).filter((name, index, all) => FEA_SECTIONS.includes(name) && all.indexOf(name) === index);
  return named.length ? named : FEA_SECTIONS;
}

/** Every control at its default, by id. */
export function feaDefaults(controls) {
  return Object.fromEntries(controls.map((control) => [control.id, control.defaultValue]));
}

/**
 * The study's named states over its controls, as a Preset select lists them: `value` (its place),
 * `label`, and `values`, every control at its default but what the preset sets (a full state, as a
 * kinematics pose is). What a preset names that no control drives is left out.
 */
export function feaPresets(result, controls) {
  const defaults = feaDefaults(controls);
  return (result.view?.presets || []).map((preset, index) => {
    const values = { ...defaults };
    for (const control of controls) {
      const value = preset[control.id];
      if (control.type === "enum" && control.options.some((option) => option.value === fieldAttribute(value))) values[control.id] = fieldAttribute(value);
      if (control.type === "number" && finiteNumber(value)) values[control.id] = clamp(value, control.min, control.max);
    }
    return { value: `preset:${index}`, label: preset.label.trim(), values };
  });
}

/**
 * Whether the loads and the fixtures are drawn on the model, as the study's `view.show` says: each
 * unless it is false. `on` is the Display switch's default, on while either is drawn; turned on by
 * the person when the view turned both off, it draws both.
 */
export function feaMarkerShow(result) {
  const show = result.view?.show || {};
  const loads = show.loads !== false;
  const fixtures = show.fixtures !== false;
  return { on: loads || fixtures, loads: loads || !fixtures, fixtures: fixtures || !loads };
}

/** An assembly's Parts panel shows from this many parts up; under it the picked face's Reference names its part. */
export const PARTS_PANEL_FROM = 6;

/**
 * Whether an assembly's Parts panel is shown: as the study's `view.show.parts` says, else only from
 * `PARTS_PANEL_FROM` parts up, since a few parts are told apart on the model, a picked face's
 * Reference naming its part, and the findings name the joints. Never for a single part.
 */
export function feaShowsParts(result) {
  if (!result.parts.length) return false;
  const chosen = result.view?.show?.parts;
  return typeof chosen === "boolean" ? chosen : result.parts.length >= PARTS_PANEL_FROM;
}

/** A figure for a sentence: whole numbers from 10 up, two significant figures below. */
function plainNumber(value) {
  const v = Number(value) || 0;
  return String(Math.abs(v) >= 10 ? Math.round(v) : Number(v.toPrecision(2)));
}

/** The safety factor as the findings say it: floored, one decimal under 10, whole from 10 up. */
function flooredFactor(value) {
  const v = Number(value) || 0;
  return String(v >= 10 ? Math.floor(v + 1e-9) : (Math.floor(v * 10 + 1e-9) / 10).toFixed(1));
}

/**
 * The one line under the colour bar, in plain words, from the numbers the file
 * carries: the peak stress and what it means for the part, and how far it moves.
 * At `loadScale` times the solved load (a linear study scales exactly), the stress
 * and the displacement are that many times larger, the safety factor that many
 * times smaller, and the line ends "at 1.5× the load".
 * "" for a field this does not know how to say.
 */
export function feaSummaryLine(result, field, loadScale = 1) {
  const k = Number(loadScale) >= 0 ? Number(loadScale) : 1;
  const at = k === 1 ? "" : `at ${plainNumber(k)}× the load`;
  const peak = (attribute) => result.fields.find((entry) => entry.attribute === attribute);
  const stress = peak("_von_mises");
  const displacement = peak("_displacement");
  const moves = displacement ? `${plainNumber(displacement.max * k)} ${displacement.units}`.trim() : "";
  if (field.attribute === "_displacement") {
    return moves ? [`Moves up to ${moves}`, at].filter(Boolean).join(" · ") : "";
  }
  if (field.attribute !== "_von_mises") {
    return "";
  }
  const factor = scaledFactor(result.safetyFactor, k);
  // Under 1 the part yields: "holds 0.4×" would read as a pass.
  const holds = factor === null ? "" : factor < 1 ? "yields under this load" : `holds ${flooredFactor(factor)}× this load`;
  // An assembly leads with its weakest part, whose peak (not the assembly's) and factor these are.
  const weakest = result.weakestPart && result.weakestPartPeakMPa !== null;
  return [
    weakest ? `Weakest: ${spaced(result.weakestPart)}` : "",
    `${weakest ? "peak stress" : "Peak stress"} ${plainNumber((weakest ? result.weakestPartPeakMPa : stress.max) * k)} ${stress.units}`.trim(),
    holds,
    moves ? `${weakest ? "the assembly moves" : "moves"} up to ${moves}` : "",
    at,
  ].filter(Boolean).join(" · ");
}

/**
 * A safety factor at `loadScale` times the solved load: yield over a stress that many times larger.
 * No load has no factor to say (null, so "holds" is left out rather than "holds Infinity×").
 */
const scaledFactor = (factor, loadScale) => {
  if (factor === null || !(loadScale > 0)) return null;
  const scaled = factor / loadScale;
  return Number.isFinite(scaled) ? scaled : null;
};

/** A colour bar end's text: enough figures to tell the values apart, no more. */
export function formatValue(value) {
  const v = Number(value) || 0;
  if (v === 0) return "0";
  const magnitude = Math.abs(v);
  if (magnitude >= 100) return v.toFixed(0);
  if (magnitude >= 10) return v.toFixed(1);
  if (magnitude >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}

/** A face ref's own number ("#o1.1.f17": 17), or null for a ref that names no face. */
function faceNumber(ref) {
  const match = /\.f(\d+)$/.exec(String(ref || ""));
  return match ? Number(match[1]) : null;
}

/** A face as a person reads it: "Face 17"; the ref itself for one that names no face. */
export function faceLabel(ref) {
  const number = faceNumber(ref);
  return number === null ? String(ref || "") : `Face ${number}`;
}

/** A part's name as a person reads it, its underscores spaces so a long one wraps at words. */
const spaced = (name) => String(name).replace(/_/g, " ");

/** Faces after a word: "face 17", "faces 17, 18". */
function facesWords(refs) {
  const names = refs.map((ref) => faceNumber(ref) ?? ref);
  return `${names.length === 1 ? "face" : "faces"} ${names.join(", ")}`;
}

const AXIS_NAMES = ["X", "Y", "Z"];

/**
 * Which way a force points, in words, in the part's CAD axes (Z up): "down", "up", "along +X"
 * for one along an axis, else "along (0.6, 0, −0.8)", its unit vector, with a true minus. "" for no force.
 */
export function forceDirection(force) {
  const length = Math.hypot(...force);
  if (!(length > 0)) return "";
  const unit = force.map((value) => value / length);
  const axis = unit.findIndex((value) => Math.abs(value) > 1 - 1e-6);
  if (axis === 2) return unit[2] < 0 ? "down" : "up";
  if (axis >= 0) return `along ${unit[axis] < 0 ? "\u2212" : "+"}${AXIS_NAMES[axis]}`;
  return `along (${unit.map((value) => plainNumber(value).replace(/^-/, "\u2212")).join(", ")})`;
}

/** A load as its row says it: what it is ("2500 N", "2 MPa pressure") and which way it points. */
function loadWords(load) {
  if (load.vector) return { amount: `${plainNumber(Math.hypot(...load.vector))} N`, direction: forceDirection(load.vector), noun: "load" };
  if (load.pressure !== null) return { amount: `${plainNumber(load.pressure)} MPa pressure`, direction: "", noun: "" };
  return { amount: load.type || "load", direction: "", noun: "" };
}

/** What a load on these faces is called in a prompt: "2500 N load on face 22", "2 MPa pressure on faces 3, 4". */
function loadSummary(words, refs) {
  return `${[words.amount, words.noun].filter(Boolean).join(" ")} on ${facesWords(refs)}`;
}

const capitalised = (word) => word.charAt(0).toUpperCase() + word.slice(1);

/**
 * What a prompt calls one face, by everything the study does to it: "Fixed face 17", "2500 N load
 * on face 22", and for a face both fixed and loaded, "Fixed and loaded face 17". "" for a free face.
 */
function faceSummary(study, ref) {
  const fixture = study.fixtures.find((entry) => entry.faces.includes(ref));
  const loads = study.loads.filter((entry) => entry.faces.includes(ref));
  if (fixture && loads.length) return `${capitalised(fixture.type)} and loaded ${facesWords([ref])}`;
  if (fixture) return `${capitalised(fixture.type)} ${facesWords([ref])}`;
  if (loads.length === 1) return loadSummary(loadWords(loads[0]), [ref]);
  return loads.length ? `Loaded ${facesWords([ref])}` : "";
}

/** A part's row detail: its material and what it holds ("yields" under a factor of 1, as the colour bar says), at `loadScale` times the load. */
function partDetail(part, loadScale) {
  const factor = scaledFactor(part.safetyFactor, loadScale);
  const holds = factor === null ? "" : factor < 1 ? "yields" : `holds ${flooredFactor(factor)}×`;
  return [part.material, holds].filter(Boolean).join(" · ");
}

/** A joint's row detail: bonded with its contact area and any gap closed, or not connected and how far apart. */
function jointDetail(joint) {
  const gap = joint.gapMm !== null && joint.gapMm > 0 ? `${plainNumber(joint.gapMm)} mm` : "";
  if (joint.type !== "bonded") return ["not connected", gap ? `${gap} apart` : ""].filter(Boolean).join(" · ");
  return ["bonded", joint.areaMm2 === null ? "" : `${plainNumber(joint.areaMm2)} mm²`, gap ? `${gap} gap closed` : ""].filter(Boolean).join(" · ");
}

/** What a prompt calls a joint: "Bonded joint between 'post' and 'base'". */
function jointSummary(joint) {
  const [first, second] = joint.names;
  return joint.type === "bonded" ? `Bonded joint between '${first}' and '${second}'` : `'${first}' and '${second}' aren't connected`;
}

/**
 * A joint as it is chosen: its interface `faces`, or for a free pair (no faces) both parts' refs
 * (`refs`), with both parts tinted lightly (`softParts`, indices into the result's `parts`) and
 * what a prompt calls it; `name` says both parts, for its button's name. One id per joint, so its
 * row under either part is the same choice.
 */
function jointChoice(result, joint, index) {
  return {
    id: `joint:${index}`, name: `${spaced(joint.names[0])} ↔ ${spaced(joint.names[1])}`, detail: jointDetail(joint), wrap: true,
    softParts: joint.between.map((ref) => result.parts.findIndex((part) => part.ref === ref)).filter((at) => at >= 0),
    ...(joint.faces.length ? { faces: joint.faces } : { refs: joint.between.filter(Boolean) }), summary: jointSummary(joint),
  };
}

/**
 * The Parts panel's rows, for an assembly (`parts` in the file); [] for a single part. One row per
 * part, chosen like a face's: its ref into Quick Edit (`refs`) and its triangles tinted (`parts`).
 * Under it, each joint it is in, named by the OTHER part ("↔ base") with how it is joined, so a
 * joint is under both its parts and either row is the same choice (`jointChoice`). Details wrap
 * (`wrap`) rather than truncate. What each part holds is at `loadScale` times the solved load.
 */
export function partRows(result, loadScale = 1) {
  const joints = result.connections.map((joint, index) => jointChoice(result, joint, index));
  return result.parts.map((part, index) => {
    const children = part.ref ? result.connections.flatMap((joint, at) => {
      const side = joint.between.indexOf(part.ref);
      return side < 0 ? [] : [{ ...joints[at], label: `↔ ${spaced(joint.names[1 - side])}` }];
    }) : [];
    return {
      id: `part:${index}`, label: spaced(part.name || part.ref), detail: partDetail(part, loadScale), wrap: true, refs: part.ref ? [part.ref] : [], parts: [index],
      summary: `Part '${part.name || part.ref}'`, ...(children.length ? { children } : {}),
    };
  });
}

/** The index of an assembly's weakest part: the one the file names, else the lowest safety factor; -1 for none. */
export function weakestPartIndex(result) {
  const named = result.weakestPart ? result.parts.findIndex((part) => part.name === result.weakestPart) : -1;
  if (named >= 0) return named;
  let weakest = -1;
  result.parts.forEach((part, index) => {
    if (part.safetyFactor !== null && (weakest < 0 || part.safetyFactor < result.parts[weakest].safetyFactor)) weakest = index;
  });
  return weakest;
}

/** The safety factor a study asks a part to keep, where it records none: cadgen's own default. */
export const DEFAULT_MARGIN = 2;

/**
 * The checks the verdict judges: the file's (`checks`), else, for a result written before them, the
 * stress check derived from what it has, today's verdict (the peak against the weakest part's yield,
 * its safety factor and the study's margin). [] where the file cannot say: no stress field, or a
 * stress with no safety factor (older than the factor).
 */
export function feaChecks(result) {
  if (result.checks) return result.checks;
  const stress = result.fields.find((entry) => entry.attribute === "_von_mises");
  const factor = result.safetyFactor;
  if (!stress || factor === null || !(factor > 0)) return [];
  const margin = result.study?.margin ?? DEFAULT_MARGIN;
  const weakest = result.parts[weakestPartIndex(result)] || null;
  const value = result.weakestPartPeakMPa ?? weakest?.peakMPa ?? stress.max;
  // The limit is the yield of the part these numbers are for; failing that, what the factor says it is.
  const limit = weakest?.yieldMPa ?? result.study?.material?.yieldMPa ?? value * factor;
  return [{ kind: "stress", label: "", value, limit, unit: stress.units || "MPa", ratio: 1 / factor, closeAt: 1 / margin, margin,
    status: factor < 1 ? "fails" : factor < margin ? "close" : "passes", part: "" }];
}

const STATUS_RANK = Object.freeze({ fails: 0, close: 1, passes: 2 });
// The verdict's tones: each status as the findings card's tones name it.
const TONE_OF = Object.freeze({ fails: "weak", close: "close", passes: "strong" });
const TITLES = Object.freeze({
  stress: Object.freeze({ fails: "Too weak", close: "Close to the limit", passes: "Strong enough" }),
  displacement: Object.freeze({ fails: "Moves too much", close: "Close to the limit", passes: "Stiff enough" }),
});
const DEFAULT_LABELS = Object.freeze({ stress: "Strength", displacement: "Displacement" });
const checkLabel = (check) => check.label || DEFAULT_LABELS[check.kind];
// Each half kept whole, so a narrow panel breaks the line at its comma.
const unbrokenHalves = (halves) => halves.map((half) => half.replace(/ /g, "\u00a0")).join(", ");

/**
 * One check at `loadScale` times the solved load (a linear study scales exactly): its value and its
 * share of its limit (`use`) k times the solved ones, `times` how many times this load it would take
 * to reach the limit, and its `status` at it. The stress check's is the result's safety factor over
 * k (its margin, not a share, makes it close), so it says exactly what the safety factor says; at
 * the solved load a check's status is the one cadgen judged.
 */
function checkAt(result, check, k) {
  const use = check.ratio * k;
  const times = check.kind === "stress" && result.safetyFactor !== null && result.safetyFactor > 0 ? result.safetyFactor / k : 1 / use;
  const margin = check.kind === "stress" ? check.margin ?? result.study?.margin ?? DEFAULT_MARGIN : null;
  const status = k === 1 && check.status ? check.status
    : times < 1 ? "fails" : (margin !== null ? times < margin : use > check.closeAt) ? "close" : "passes";
  return { ...check, use: check.kind === "stress" ? 1 / times : use, times, status, margin, shown: check.value * k };
}

/** A check's line, its value against its limit: "Peak 405 MPa, limit 276 MPa", "Moves 0.62 mm, limit 0.5 mm". */
function checkLine(check) {
  const unit = check.unit || (check.kind === "stress" ? "MPa" : "mm");
  // A displacement keeps three figures: its limit is often under a millimetre, and 1.04 is not 1.
  const figure = check.kind === "stress" ? plainNumber : (value) => String(Number(Number(value).toPrecision(3)));
  return unbrokenHalves([`${check.kind === "stress" ? "Peak" : "Moves"} ${figure(check.shown)} ${unit}`, `limit ${figure(check.limit)} ${unit}`]);
}

/** What a check says of the load: "Would hold 1.5× this load", "Holds only 0.6× this load"; a displacement's "OK up to 1.6× this load". */
function checkCaption(check) {
  const times = flooredFactor(check.times);
  if (check.kind === "stress") return check.times < 1 ? `Holds only ${times}× this load` : `Would hold ${times}× this load`;
  return check.times < 1 ? `OK only to ${times}× this load` : `OK up to ${times}× this load`;
}

/**
 * Whether some check fails or is close at `loadScale` times the solved load: what a control's `when`
 * reads. null where the file judges nothing (no checks, or no load), so every control shows.
 */
export function feaFailing(result, loadScale = 1) {
  const k = Number(loadScale) >= 0 ? Number(loadScale) : 1;
  const checks = feaChecks(result);
  if (!checks.length || !(k > 0)) return null;
  return checks.some((check) => checkAt(result, check, k).status !== "passes");
}

/**
 * The answer at a glance, at `loadScale` times the solved load, for the verdict at the top of Study:
 * the worst check (`feaChecks`; the first by status, failing before close before passing, then by
 * how much of its limit it uses) as the headline, and one compact row per further check (`rows`).
 * The headline: `status` (the tone: "weak" failing, "close", "strong" passing, "none" with no stress:
 * no load reaches the part, or the load is set to 0), its `title` in plain words ("Too weak", "Moves
 * too much"), `part` (an assembly's weakest part, whose numbers a stress check's are; "" else),
 * `label` (a check named in the person's words), `line` (the value against the limit: "Peak 405 MPa,
 * limit 276 MPa"), `use` (the share of the limit, 1 at it; past 1 it is over), the stress check's
 * `margin` (null for another) and the `caption` ("Holds only 0.6× this load"). null where the file
 * cannot say (no stress field, or a stress with no safety factor and no checks: a result older than both).
 */
export function feaVerdict(result, loadScale = 1) {
  const stress = result.fields.find((entry) => entry.attribute === "_von_mises");
  if (!stress) return null;
  const k = Number(loadScale) >= 0 ? Number(loadScale) : 1;
  const margin = result.study?.margin ?? DEFAULT_MARGIN;
  const weakest = result.parts[weakestPartIndex(result)] || null;
  const part = result.weakestPart ? spaced(result.weakestPart) : weakest?.name ? spaced(weakest.name) : "";
  const base = { part, margin, label: "", rows: [] };
  if (!(k > 0)) return { ...base, status: "none", title: "No load", line: "The load is set to 0", use: 0, caption: "" };
  const checks = feaChecks(result);
  const unloaded = checks.some((check) => check.kind === "stress" && !(check.value > 0));
  if (!checks.length || unloaded) {
    return stress.max > 0 && !unloaded ? null : { ...base, status: "none", title: "No stress", line: "Check the load reaches the part", use: 0, caption: "" };
  }
  const judged = checks.map((check, index) => ({ ...checkAt(result, check, k), index }));
  const [worst] = [...judged].sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.use - a.use || a.index - b.index);
  const named = (check) => check.label && check.label !== DEFAULT_LABELS[check.kind];
  return {
    ...base, part: worst.kind === "stress" ? part : "", margin: worst.margin, label: named(worst) ? checkLabel(worst) : "",
    status: TONE_OF[worst.status], title: TITLES[worst.kind][worst.status], use: worst.use, line: checkLine(worst), caption: checkCaption(worst),
    rows: judged.filter((check) => check !== worst).map((check) => ({
      id: `check:${check.index}`, kind: check.kind, status: TONE_OF[check.status], label: checkLabel(check), line: checkLine(check),
      use: check.use, margin: check.margin, caption: checkCaption(check),
    })),
  };
}

/** Study's "Held at": one row per fixed face, its name alone ("Face 9", "base · face 9"), under the fixture glyph. */
function heldRows(result) {
  const study = result.study;
  const fixed = study.fixtures.flatMap((fixture, index) => fixture.faces.map((ref) => ({
    id: `fixed:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], summary: faceSummary(study, ref), wrap: true,
  })));
  return fixed.length ? [{ id: "fixed", label: "Held at", detail: "", glyph: "fixture", children: fixed }] : [];
}

/**
 * Study's "Pushed": one row per load, how much and which way ("300 N along −X"), under the arrow
 * glyph, its faces under it by name alone, shut until opened (`collapsed`).
 */
function pushedRows(result) {
  const study = result.study;
  const loads = study.loads.filter((load) => load.faces.length).map((load, index) => {
    const words = loadWords(load);
    const label = [words.amount, words.direction].filter(Boolean).join(" ");
    return {
      id: `load:${index}`, label, detail: "", faces: load.faces,
      summary: loadSummary(words, load.faces), collapsed: true,
      children: load.faces.map((ref) => ({ id: `load:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], wrap: true,
        summary: study.fixtures.some((fixture) => fixture.faces.includes(ref)) ? faceSummary(study, ref) : loadSummary(words, [ref]) })),
    };
  });
  return loads.length ? [{ id: "loads", label: "Pushed", detail: "", glyph: "load", children: loads }] : [];
}

/**
 * Study's "Made of", under a swatch: the material's name ("Aluminum 6061-T6"). In an assembly whose
 * parts differ, "Mostly Aluminum 6061-T6" where one material has most of the parts, else
 * "2 materials", each part's own in its hint (and in Parts and a picked face's Reference).
 */
function madeOfRows(result) {
  const fallback = result.study.material?.name || "";
  const each = result.parts.map((part) => part.material || fallback).filter(Boolean);
  const counts = new Map();
  for (const name of each) counts.set(name, (counts.get(name) || 0) + 1);
  let label = fallback;
  let hint = "";
  if (counts.size === 1) label = each[0];
  else if (counts.size > 1) {
    const [top, count] = [...counts].sort((a, b) => b[1] - a[1])[0];
    label = count * 2 > each.length ? `Mostly ${top}` : `${counts.size} materials`;
    hint = [...counts].map(([name, n]) => `${name}: ${n} ${n === 1 ? "part" : "parts"}`).join(", ");
  }
  if (!label) return [];
  return [{ id: "material", label: "Made of", detail: "", glyph: "material", children: [{ id: "material:name", label, detail: "", wrap: true, ...(hint ? { hint } : {}) }] }];
}

/** Details, shut until opened: the mesh, "3.7 mm elements", how it got there its hint ("refined from 2.8 mm", "not refined"). */
function detailRows({ study }) {
  const mesh = study.mesh;
  if (mesh?.sizeMm === null || mesh?.sizeMm === undefined) return [];
  const refined = mesh.refinedFromMm === null ? "not refined" : `refined from ${plainNumber(mesh.refinedFromMm)} mm`;
  return [{ id: "details", label: "Details", detail: "", collapsed: true,
    children: [{ id: "mesh", label: "Mesh", detail: `${plainNumber(mesh.sizeMm)} mm elements`, hint: refined }] }];
}

// Study's setup, in order, each from what the file records and none when it records nothing for it:
// a result kind with more to say (a modal's modes, a thermal load) adds a group here. Details follow
// "What you see" (the panel's own), shut.
const STUDY_GROUPS = Object.freeze([heldRows, pushedRows, madeOfRows]);
const DETAIL_GROUPS = Object.freeze([detailRows]);

/**
 * Study's rows for a result's study, in order: where it is held (the fixed faces), what pushes it
 * (each load with its faces under it), what it is made of (`STUDY_GROUPS`), then Details (the mesh,
 * shut: `DETAIL_GROUPS`). An assembly's parts and joints are the Parts panel's (`partRows`). A row
 * that stands for faces carries them (`faces`, the file's refs) and what a prompt calls them
 * (`summary`); a group row (`children`) carries none, and one of the setup's names its `glyph`, the
 * marker it is drawn as on the model. A row that opens shut says so (`collapsed`), and a fact's
 * further words are its hint (`hint`). [] for a result written before the study was recorded.
 */
export function studyRows(result) {
  const { setup, details } = studySections(result);
  return [...setup, ...details];
}

/** Study's rows by section: `setup` (`STUDY_GROUPS`) and `details` (`DETAIL_GROUPS`), each [] where the file records nothing for it. */
export function studySections(result) {
  if (!result.study) return { setup: [], details: [] };
  return { setup: STUDY_GROUPS.flatMap((group) => group(result)), details: DETAIL_GROUPS.flatMap((group) => group(result)) };
}

/** The index into the result's `parts` of the part a face is on; -1 for a single part's face. */
const facePartIndex = (result, ref) => result.parts.findIndex((entry) => entry.ref && String(ref).startsWith(`${entry.ref}.`));

/**
 * What a picked face's Reference says of its part, in an assembly: its material and what it holds
 * at `loadScale` times the load ("6061-T6 · holds 1.4×", "yields"), as Parts' rows say it. "" for a
 * single part's face.
 */
export function facePartDetail(result, ref, loadScale = 1) {
  const index = facePartIndex(result, ref);
  return index < 0 ? "" : partDetail(result.parts[index], loadScale);
}

/** A face's heading: "Face 17", and in an assembly "post · face 17", the part it is on (a long name's underscores spaced). */
export function faceTitle(result, ref) {
  const part = result.parts[facePartIndex(result, ref)];
  return part?.name ? `${spaced(part.name)} · ${faceLabel(ref).toLowerCase()}` : faceLabel(ref);
}

/** What a prompt calls a face, by what the study does to it; "Face 17" for a face it does nothing to. */
export function facePromptSummary(result, ref) {
  return (result.study && faceSummary(result.study, ref)) || faceLabel(ref);
}

/** What the study does to a face, in words: "fixed", "2500 N load, down", "2 MPa pressure", or "free". */
export function faceRole(result, ref) {
  const study = result.study;
  if (!study) return "";
  const roles = [
    ...study.fixtures.filter((fixture) => fixture.faces.includes(ref)).map((fixture) => fixture.type),
    ...study.loads.filter((load) => load.faces.includes(ref)).map((load) => {
      const words = loadWords(load);
      return [[words.amount, words.noun].filter(Boolean).join(" "), words.direction].filter(Boolean).join(", ");
    }),
  ];
  return roles.length ? roles.join("; ") : "free";
}

/** The indices into the result's `faces` of these refs, for `recolorByField`'s tint. */
export function faceIndices(result, refs) {
  return refs.map((ref) => result.faces.indexOf(ref)).filter((index) => index >= 0);
}

const raycaster = new Raycaster();

/**
 * The source face of the result's triangle under a world-space ray: `{ id, ref, point }`, the
 * scene contract's pick (`kit/scene.js`), with `ref` the file's face ref. null over nothing, and
 * over a triangle the mesher matched to no face.
 */
export function pickFace(result, ray) {
  const faces = vertexFaces(result.mesh);
  if (!faces) return null;
  raycaster.ray.copy(ray);
  const hit = raycaster.intersectObject(result.mesh, false)[0];
  const ref = hit?.face ? result.faces[Math.round(faces[hit.face.a])] : null;
  return ref ? { id: ref, ref, point: hit.point } : null;
}
