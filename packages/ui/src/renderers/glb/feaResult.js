/**
 * An FEA result inside a GLB, as `cadgen fea solve` writes it, and what the
 * viewer can do with it without a second file.
 *
 * The writer (cadgen `_internal/fea/outputs.py`) stores the raw fields as
 * custom vertex attributes beside the baked colour: `_VON_MISES` (float, MPa)
 * and `_DISPLACEMENT` (vec3, glTF units, i.e. metres, unscaled), and puts in
 * the mesh extras a `fields` list describing each one (`attribute`, `name`,
 * `units`, `min`, `max`, `attribute_scale`), `deformation_scale` (the
 * multiplier already baked into the positions), the colour `ramp` it used, the
 * result's `safety_factor` (null when it has none), the `checks` cadgen judged
 * (`feaVerdict`), the `study` it was solved for (material, fixtures, loads, mesh,
 * margin), `faces` (the occurrence's face refs) and `_FACE`, the index into
 * `faces` of the face each vertex lies on (-1 for none). A bonded assembly also
 * carries `parts` (name, material, peak stress, safety factor of each part),
 * `connections` (each detected pair: type, contact area, gap and the interface
 * faces of both sides), `_PART` (the index into `parts` of the part each vertex
 * belongs to) and the weakest part's name and peak; a single part has none of
 * these. A file without anything cadgen always writes, or with a field, check, study, part or joint not as
 * cadgen writes it, does not read (`readFeaResult` throws): nothing here stands in for what the file should hold. The words the viewer says are in `fea/`: `checkKinds.js` (each check kind's),
 * `fields.js` (each field's), `setup.js` (Study's setup) and `controls.js` (What you see's controls).
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
import { FEA_CHECK_KINDS, checkLabel, checkLine, checkTitle, loadCaption } from "./fea/checkKinds.js";
import { flooredFactor, plainNumber } from "./fea/numbers.js";
import { SETUP_GROUPS, detailRows, faceLabel, facePartIndex, faceSummary, isRoller, loadWords, spaced, wholeRefs } from "./fea/setup.js";

export { FEA_CHECK_KINDS } from "./fea/checkKinds.js";
export { deformationRange, feaControls } from "./fea/controls.js";
import { english } from "../../i18n/core.js";
export { FIELD_WORDS } from "./fea/fields.js";
export { faceLabel, faceTitle, forceDirection } from "./fea/setup.js";

const GENERATOR = "cadgen fea";

/** The deformation's own attribute: the displacement the file baked into its positions. */
export const DISPLACEMENT = "_displacement";

/** RGB in [0, 1] for t in [0, 1], piecewise linear between the ramp's stops (the file's `ramp`). */
export function feaRamp(t, stops) {
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
export function feaRampGradient(stops, direction = "to right") {
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

/** The colour ramp the writer coloured the file with: two stops or more, each a position and an RGB triple. */
function readRamp(raw) {
  const valid = Array.isArray(raw) && raw.length >= 2 && raw.every((stop) =>
    Array.isArray(stop) && Number.isFinite(stop[0]) && Array.isArray(stop[1]) && stop[1].length === 3 && stop[1].every(Number.isFinite));
  if (!valid) throw new Error("The FEA result has no colour ramp in its extras.");
  return raw;
}

const isVector = (value) => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
const finiteOrNull = (value) => (Number.isFinite(value) ? Number(value) : null);

const named = (value) => typeof value === "string" && value !== "";

/** Face refs as cadgen writes them, a list of refs; anything else does not read. */
function faceRefs(raw, what) {
  if (!(Array.isArray(raw) && raw.every(named))) throw new Error(`The FEA result's ${what} are not a list of face refs.`);
  return [...raw];
}

/** An assembly's parts in `_PART` order, each its ref, name, material and safety factor; [] for a single part, which has none. */
function readParts(raw) {
  if (raw === undefined) return [];
  if (!Array.isArray(raw)) throw new Error("The FEA result's parts are not a list.");
  return raw.map((part, index) => {
    if (!(named(part?.ref) && named(part.name) && typeof part.material === "string")) {
      throw new Error(`The FEA result's part ${index} has no ref, name or material.`);
    }
    return { ref: part.ref, name: part.name, material: part.material, safetyFactor: finiteOrNull(part.safety_factor) };
  });
}

/** The joints cadgen writes: a touching pair bonded, or left free. */
const JOINT_TYPES = ["bonded", "free"];

/** An assembly's detected pairs: `between` the two part refs, `names` theirs, the interface `faces` of both sides (none for a free pair). */
function readConnections(raw) {
  if (raw === undefined) return [];
  if (!Array.isArray(raw)) throw new Error("The FEA result's connections are not a list.");
  return raw.map((joint, index) => {
    const pair = (value) => Array.isArray(value) && value.length === 2 && value.every(named);
    if (!(pair(joint?.between) && pair(joint.names) && JOINT_TYPES.includes(joint.type))) {
      throw new Error(`The FEA result's connection ${index} is not a pair of parts, their names and ${JOINT_TYPES.join(" or ")}.`);
    }
    if (!(Number.isFinite(joint.area_mm2) && Number.isFinite(joint.gap_mm))) {
      throw new Error(`The FEA result's connection ${index} has no contact area or gap.`);
    }
    return { between: [...joint.between], names: [...joint.names], type: joint.type, areaMm2: joint.area_mm2,
      gapMm: joint.gap_mm, faces: faceRefs(joint.faces, `connection ${index}'s faces`) };
  });
}

const CHECK_STATUSES = ["fails", "close", "passes"];

/** Whether a check is as cadgen judges one: its numbers, its status and where it peaks (a stress check also its margin, and a stress). */
const judged = (check) => named(check.label) && Number.isFinite(check.value) && check.value >= 0 && Number.isFinite(check.limit)
  && check.limit > 0 && typeof check.unit === "string" && Number.isFinite(check.ratio) && Number.isFinite(check.close_at)
  && CHECK_STATUSES.includes(check.status) && check.where && (check.where.ref === null || named(check.where.ref))
  && (check.part === undefined || named(check.part))
  && (check.kind !== "stress" || (check.value > 0 && Number.isFinite(check.margin) && check.margin >= 1));

/**
 * The checks the file judged (`kind`, `label`, `value`, `limit`, `unit`, `ratio`, `closeAt`, `margin`, `status`,
 * `part`, `faces`, `where`), in the study's order. A check of a kind this viewer does not know, or not as cadgen
 * judges one, does not read: the verdict never says what it could not judge. A stress check always has a stress:
 * cadgen refuses a study no load reaches.
 */
function readChecks(raw) {
  if (!Array.isArray(raw) || !raw.length) throw new Error("The FEA result has no checks in its extras.");
  return raw.map((check, index) => {
    if (!FEA_CHECK_KINDS.includes(check?.kind)) throw new Error(`The FEA result's check ${index} is of a kind this viewer does not know.`);
    if (!judged(check)) throw new Error(`The FEA result's check ${index} is not a ${check.kind} check as cadgen judges one.`);
    return {
      kind: check.kind, label: check.label, value: check.value, limit: check.limit, unit: check.unit, ratio: check.ratio,
      closeAt: check.close_at, margin: check.kind === "stress" ? check.margin : null, status: check.status, part: check.part ?? "",
      faces: check.faces === undefined ? [] : faceRefs(check.faces, `check ${index}'s faces`), where: check.where.ref ?? "",
    };
  });
}

const FIXTURE_TYPES = ["fixed", "roller"];
const BODY_LOADS = ["gravity", "acceleration"];

/** One load of the study as cadgen echoes it: a force or a pressure on faces, or a body load's `g` vector. */
function readLoad(load, index) {
  const where = `The FEA result's load ${index}`;
  if (BODY_LOADS.includes(load?.type)) {
    if (!isVector(load.vector_g)) throw new Error(`${where} has no g vector.`);
    return { type: load.type, faces: [], vector: null, pressure: null, g: [...load.vector_g] };
  }
  if (!["force", "pressure"].includes(load?.type)) throw new Error(`${where} is not a force, a pressure, gravity or an acceleration.`);
  const faces = faceRefs(load.faces, `load ${index}'s faces`);
  if (load.type === "force") {
    if (!isVector(load.vector_N)) throw new Error(`${where} has no force vector.`);
    return { type: "force", faces, vector: [...load.vector_N], pressure: null };
  }
  if (!Number.isFinite(load.pressure_MPa)) throw new Error(`${where} has no pressure.`);
  return { type: "pressure", faces, vector: null, pressure: load.pressure_MPa };
}

/**
 * The study the result was solved for, as the file records it: the material (null for an assembly whose parts
 * each have their own), fixtures, loads (a body load, gravity or an acceleration, has no faces and its `g`
 * vector), mesh and margin. A fixture's `type` is "fixed" or "roller" (it may slide in the face's plane, not
 * off it). The viewer reads its study from here, never the raw echo.
 */
function readStudy(raw) {
  if (!raw || typeof raw !== "object") throw new Error("The FEA result has no study in its extras.");
  const { material, mesh } = raw;
  if (!(material === null || (named(material?.name) && Number.isFinite(material.yield_MPa)))) {
    throw new Error("The FEA result's study material has no name or yield.");
  }
  if (!(Number.isFinite(mesh?.size_mm) && (mesh.refined_from_mm === null || Number.isFinite(mesh.refined_from_mm)))) {
    throw new Error("The FEA result's study has no mesh size.");
  }
  if (!(Number.isFinite(raw.margin) && raw.margin >= 1)) throw new Error("The FEA result's study has no margin.");
  if (!(Array.isArray(raw.fixtures) && Array.isArray(raw.loads))) throw new Error("The FEA result's study has no fixtures or loads.");
  return {
    material: material === null ? null : { name: material.name, yieldMPa: material.yield_MPa },
    fixtures: raw.fixtures.map((fixture, index) => {
      if (!FIXTURE_TYPES.includes(fixture?.type)) throw new Error(`The FEA result's fixture ${index} is not fixed or a roller.`);
      return { type: fixture.type, faces: faceRefs(fixture.faces, `fixture ${index}'s faces`) };
    }),
    loads: raw.loads.map(readLoad),
    mesh: { sizeMm: mesh.size_mm, refinedFromMm: mesh.refined_from_mm },
    margin: raw.margin,
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
 * The FEA result a loaded glTF scene root carries (a mesh `cadgen fea` generated), or null for any other GLB.
 * Throws for a result without anything cadgen always writes: the viewer says so rather than show less than the
 * file should hold.
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
    if (extras.generator !== GENERATOR) {
      return;
    }
    if (!(Array.isArray(extras.fields) && extras.fields.length)) throw new Error("The FEA result has no fields in its extras.");
    const fields = extras.fields.map((field) => {
      if (!(named(field?.attribute) && named(field.name) && typeof field.units === "string" && Number.isFinite(field.min)
        && Number.isFinite(field.max) && Number.isFinite(field.attribute_scale) && field.attribute_scale > 0)) {
        throw new Error(`The FEA result's field ${field?.attribute} has no name, units, range or scale.`);
      }
      if (!object.geometry.getAttribute(field.attribute.toLowerCase())) {
        throw new Error(`The FEA result's field ${field.attribute} is not on its geometry.`);
      }
      return { attribute: field.attribute.toLowerCase(), name: field.name, units: field.units, min: field.min, max: field.max,
        attributeScale: field.attribute_scale };
    });
    if (!(fields.some((field) => field.attribute === "_von_mises") && fields.some((field) => field.attribute === DISPLACEMENT))) {
      throw new Error("The FEA result has no von Mises or displacement field.");
    }
    // What cadgen writes on every vertex: the colours the ramp rewrites, the displacement the view scales,
    // the face each vertex lies on (`_face`); and, for an assembly, the part it belongs to (`_part`).
    const attribute = (name, sizes) => sizes.includes(object.geometry.getAttribute(name)?.itemSize);
    if (!attribute("color", [3, 4])) throw new Error("The FEA result has no vertex colours.");
    if (!attribute(DISPLACEMENT, [3])) throw new Error("The FEA result's displacement is not a vector per vertex.");
    if (!attribute("_face", [1])) throw new Error("The FEA result has no face per vertex.");
    if (!(Number.isFinite(extras.deformation_scale) && extras.deformation_scale > 0)) {
      throw new Error("The FEA result has no deformation scale in its extras.");
    }
    if (!(named(extras.name) && named(extras.document) && named(extras.occurrence))) {
      throw new Error("The FEA result has no name, document or occurrence in its extras.");
    }
    // A study no load reaches is refused by cadgen, so every result has a safety factor.
    if (!(Number.isFinite(extras.safety_factor) && extras.safety_factor > 0)) throw new Error("The FEA result has no safety factor in its extras.");
    const parts = readParts(extras.parts);
    if (parts.length && !named(extras.weakest_part)) throw new Error("The FEA result's assembly names no weakest part.");
    if (parts.length && !attribute("_part", [1])) throw new Error("The FEA result's assembly has no part per vertex.");
    found = {
      mesh: object,
      name: extras.name,
      document: extras.document,
      occurrence: extras.occurrence,
      deformationScale: extras.deformation_scale,
      safetyFactor: extras.safety_factor,
      fields,
      ramp: readRamp(extras.ramp),
      study: readStudy(extras.study),
      faces: faceRefs(extras.faces, "faces"),
      parts,
      connections: readConnections(extras.connections),
      weakestPart: parts.length ? extras.weakest_part : "",
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
  const { count, itemSize: size, array } = mesh.geometry.getAttribute(field.attribute);
  const out = new Float32Array(count);
  const scale = field.attributeScale;
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

/** A per-vertex index the file writes: the face each vertex lies on (`_face`), the part it belongs to (`_part`, an
 * assembly's alone: null for one part). `readFeaResult` refuses a result without the ones it has. */
function vertexIndex(mesh, name) {
  return mesh.geometry.getAttribute(name)?.array ?? null;
}

/**
 * Rewrite the mesh's vertex colours from one field over `[field.min, field.max]`, with the
 * vertices of the faces in `highlight` (indices into the result's `faces`) and of the parts in
 * `parts` (indices into its `parts`) tinted, and the parts in `softParts` tinted lightly (a joint's
 * two parts; its interface faces keep the full tint). `scaling`, for a load other than the solved
 * one: the values are drawn at `valueScale` times their own and the ramp spans `rangeScale` times the
 * field's range (both the load scale; while a load ramp plays the values climb toward the range).
 * Returns true when the colours changed; false when that field and tint were already shown.
 */
export function recolorByField(mesh, field, ramp, highlight = null, parts = null, softParts = null,
  { valueScale = 1, rangeScale = 1 } = {}) {
  const color = mesh.geometry.getAttribute("color");
  const values = keptValues(mesh, field);
  const kept = shown(mesh);
  const faces = vertexIndex(mesh, "_face");
  const tinted = highlight?.length ? new Set(highlight) : null;
  const partOf = vertexIndex(mesh, "_part");
  const tintedParts = partOf && parts?.length ? new Set(parts) : null;
  const lightParts = partOf && softParts?.length ? new Set(softParts) : null;
  const sorted = (set) => (set ? [...set].sort((a, b) => a - b).join(",") : "");
  const key = `${field.attribute}x${valueScale}/${rangeScale}|${sorted(tinted)}|${sorted(tintedParts)}|${sorted(lightParts)}`;
  if (kept.field === key) {
    return false;
  }
  const table = rampTable(ramp);
  const low = field.min * rangeScale;
  const span = (field.max - field.min) * rangeScale;
  const stride = color.itemSize;
  const bytes = color.array;
  for (let i = 0; i < values.length; i += 1) {
    const t = span > 0 ? clamp((values[i] * valueScale - low) / span, 0, 1) : 0;
    const entry = Math.round(t * 255) * 3;
    const base = i * stride;
    const tint = (tinted !== null && tinted.has(Math.round(faces[i]))) || (tintedParts !== null && tintedParts.has(Math.round(partOf[i])));
    const blend = tint ? HIGHLIGHT_BLEND : lightParts !== null && lightParts.has(Math.round(partOf[i])) ? SOFT_BLEND : 0;
    for (let k = 0; k < 3; k += 1) {
      const own = table[entry + k];
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
  const displacement = geometry.getAttribute(DISPLACEMENT);
  const kept = shown(mesh);
  const wanted = Number(scale) || 0;
  if (kept.scale === wanted || (kept.scale === null && wanted === (Number(baseScale) || 0))) {
    kept.scale = wanted;
    return false;
  }
  const out = position.array;
  const base = kept.position;
  const delta = wanted - (Number(baseScale) || 0);
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

/** An assembly's Parts panel shows from this many parts up; under it the picked face's Reference names its part. */
export const PARTS_PANEL_FROM = 6;

/**
 * Whether an assembly's Parts panel is shown: only from `PARTS_PANEL_FROM` parts up, since a few
 * parts are told apart on the model, a picked face's Reference naming its part, and the findings
 * name the joints. Never for a single part.
 */
export const feaShowsParts = (result) => result.parts.length >= PARTS_PANEL_FROM;

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

/** A part's row detail: its material and what it holds ("yields" under a factor of 1), at `loadScale` times the load. */
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
export function partRows(result, loadScale = 1, t = english) {
  const joints = result.connections.map((joint, index) => jointChoice(result, joint, index));
  return result.parts.map((part, index) => {
    const children = part.ref ? result.connections.flatMap((joint, at) => {
      const side = joint.between.indexOf(part.ref);
      return side < 0 ? [] : [{ ...joints[at], label: `↔ ${spaced(joint.names[1 - side])}` }];
    }) : [];
    return {
      id: `part:${index}`, label: spaced(part.name || part.ref), detail: partDetail(part, loadScale), wrap: true, refs: part.ref ? [part.ref] : [], parts: [index],
      summary: t("fea.partSummary", { name: part.name || part.ref }), ...(children.length ? { children } : {}),
    };
  });
}

/** The index of an assembly's weakest part, the one the file names; -1 for a single part. */
export function weakestPartIndex(result) {
  return result.weakestPart ? result.parts.findIndex((part) => part.name === result.weakestPart) : -1;
}

const STATUS_RANK = Object.freeze({ fails: 0, close: 1, passes: 2 });
// The verdict's tones: each status as the findings card's tones name it.
const TONE_OF = Object.freeze({ fails: "weak", close: "close", passes: "strong" });

/**
 * One check at `k` times the solved load (a linear study scales exactly): its value and its share of
 * its limit (`use`) k times the solved ones, `times`, how many times this load it would take to reach
 * the limit, and its `status` at it. The stress check's is the result's safety factor over k (its
 * margin, not a share, makes it close), so it says exactly what the safety factor says; at the solved
 * load a check's status is the one cadgen judged.
 */
function checkAt(result, check, k) {
  const use = check.ratio * k;
  const times = check.kind === "stress" ? result.safetyFactor / k : 1 / use;
  // A stress check is held to its margin; a displacement, judged by a share of its limit, has none.
  const margin = check.kind === "stress" ? check.margin : null;
  const status = k === 1 ? check.status
    : times < 1 ? "fails" : (margin !== null ? times < margin : use > check.closeAt) ? "close" : "passes";
  return { ...check, use: check.kind === "stress" ? 1 / times : use, times, status, margin, shown: check.value * k };
}

const STATUS_WORDS = Object.freeze({ fails: "fails", close: "is close to its limit", passes: "passes" });

/**
 * What a check chosen in the verdict carries into a prompt: the faces it is over, else the face it
 * peaks on, else the whole result; and what it says, in one sentence ("Tip sag fails: moves 0.62 mm,
 * limit 0.5 mm (OK only to 0.8× this load)"). `part`: whose numbers a stress check's are, in an assembly.
 */
function checkChoice(result, check, part, label) {
  const faces = check.faces?.length ? check.faces : check.where ? [check.where] : [];
  const line = checkLine(check).replace(/ /g, " ");
  const where = check.kind === "stress" && part ? ` in ${part}` : "";
  const summary = `${label} ${STATUS_WORDS[check.status]}${where}: ${line[0].toLowerCase()}${line.slice(1)} (${loadCaption(check.times)})`;
  return { id: `check:${check.index}`, ...(faces.length ? { faces } : { refs: wholeRefs(result) }), summary };
}

// The headline over several checks: how many fail, else whether any is close.
const failedTitle = (failing, total) => (failing === total ? (total === 2 ? "Fails both checks" : `Fails all ${total} checks`)
  : `Fails ${failing} of ${total} checks`);

/**
 * The answer at a glance, at `loadScale` times the solved load, for the verdict at the top of Study:
 * a headline, one line of what it means for the load, then every check the same way. `status` is
 * the worst check's tone ("weak" failing, "close", "strong" passing; "none" with the load set to 0).
 * `title`: one check's own words ("Too weak", "Moves too much", "Stiff enough", its kind's,
 * `checkKinds.js`), or over several, how many fail ("Fails both checks"), else "Close to the limit"
 * or "Passes all checks". `caption`: how much of this load the weakest check takes ("OK only to 0.4×
 * this load"; with the load at 0, what to do). `rows`: each check,
 * worst first (failing before close before passing, then the most of its limit used), with its
 * `label` in the person's words, the `part` a stress check's numbers are for in an assembly, its
 * `line` (the value against the limit, the label saying what it is: "405 MPa, limit 276 MPa"), `use`
 * (the share of the limit, 1 at it), the `margin` a stress check is held to (null for a displacement)
 * and its `choice` for Quick Edit.
 */
export function feaVerdict(result, loadScale = 1, t = english) {
  const k = Number(loadScale) >= 0 ? Number(loadScale) : 1;
  if (!(k > 0)) return { status: "none", title: t("fea.noLoad"), caption: t("fea.loadIsZero"), rows: [] };
  const judged = result.checks.map((check, index) => ({ ...checkAt(result, check, k), index }))
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.use - a.use || a.index - b.index);
  const [worst] = judged;
  const failing = judged.filter((check) => check.status === "fails").length;
  const total = judged.length;
  const title = total === 1 ? checkTitle(worst, worst.status)
    : failing ? failedTitle(failing, total) : worst.status === "close" ? "Close to the limit" : "Passes all checks";
  return {
    status: TONE_OF[worst.status], title,
    // The load the weakest check takes.
    caption: loadCaption(Math.min(...judged.map((check) => check.times))),
    rows: judged.map((check) => {
      const part = check.kind === "stress" ? spaced(check.part) : "";
      const label = checkLabel(check);
      return { id: `check:${check.index}`, kind: check.kind, status: TONE_OF[check.status], label, part, line: checkLine(check, { bare: true }),
        use: check.use, margin: check.margin, choice: checkChoice(result, check, part, label) };
    }),
  };
}

/**
 * Study's rows by section: `setup` (`SETUP_GROUPS`: where it is held, the fixed faces; what pushes it,
 * each load with its faces under it; what it is made of) and `details` (the mesh, shut), each [] where
 * the file records nothing for it. An assembly's parts and joints are the Parts panel's (`partRows`). A
 * row that stands for faces carries them (`faces`, the file's refs) and what a prompt calls them
 * (`summary`); a group row (`children`) carries none, and one of the setup's names its `glyph`, the
 * marker it is drawn as on the model. A row that opens shut says so (`collapsed`), and a fact's further
 * words are its hint (`hint`).
 */
export function studySections(result, t = english) {
  return { setup: SETUP_GROUPS.flatMap((group) => group(result, t)), details: detailRows(result, t) };
}

/**
 * What a picked face's Reference says of its part, in an assembly: its material and what it holds
 * at `loadScale` times the load ("6061-T6 · holds 1.4×", "yields"), as Parts' rows say it. "" for a
 * single part's face.
 */
export function facePartDetail(result, ref, loadScale = 1) {
  const index = facePartIndex(result, ref);
  return index < 0 ? "" : partDetail(result.parts[index], loadScale);
}

/** What a prompt calls a face, by what the study does to it; "Face 17" for a face it does nothing to. */
export function facePromptSummary(result, ref) {
  return faceSummary(result.study, ref) || faceLabel(ref);
}

/** What the study does to a face, in words: "fixed", "slides along it" (a roller), "2500 N load, down", "2 MPa pressure", or "free". */
export function faceRole(result, ref) {
  const study = result.study;
  const roles = [
    ...study.fixtures.filter((fixture) => fixture.faces.includes(ref)).map((fixture) => (isRoller(fixture) ? "slides along it" : fixture.type)),
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
 * over a triangle the mesher matched to no face. `clip`: a world-space plane the view cuts the result
 * with (the view's Clip, `runtime.activeClipPlanes`): what lies past it is not there to pick, so the ray goes on to what the cut shows.
 */
export function pickFace(result, ray, clip = null) {
  const faces = vertexIndex(result.mesh, "_face");
  raycaster.ray.copy(ray);
  const hit = raycaster.intersectObject(result.mesh, false).find((entry) => !clip || clip.distanceToPoint(entry.point) >= -1e-6);
  const ref = hit?.face ? result.faces[Math.round(faces[hit.face.a])] : null;
  return ref ? { id: ref, ref, point: hit.point } : null;
}
