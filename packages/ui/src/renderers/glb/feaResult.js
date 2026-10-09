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
 * none of these.
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

/** The result's findings as the card lists them, in the file's order, each with its position as `index`; malformed ones are left out. */
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
 * Where a finding's `at` points are in the mesh's own space (glTF metres, Y up), with the
 * displacement there. `at` is the part's CAD millimetres, undeformed: (x, y, z) is (x, z, -y) in
 * metres (the writer's own convention). The displacement is the nearest vertex's, found once
 * against the undeformed positions (the file's, less the scale already baked in), so a ring can
 * follow the part as the deformation slider moves.
 */
export function ringTargets(result, points) {
  const geometry = result.mesh.geometry;
  const position = shown(result.mesh).position;
  const displacement = geometry.getAttribute("_displacement");
  const usable = displacement?.itemSize === 3 && displacement.count * 3 === position.length;
  return points.map(([x, y, z]) => {
    const base = [x / 1000, z / 1000, 0 - y / 1000];
    let nearest = -1;
    let best = Infinity;
    if (usable) {
      for (let i = 0; i < displacement.count; i += 1) {
        let sum = 0;
        for (let k = 0; k < 3; k += 1) {
          const d = position[i * 3 + k] - result.deformationScale * displacement.array[i * 3 + k] - base[k];
          sum += d * d;
        }
        if (sum < best) { best = sum; nearest = i; }
      }
    }
    const move = nearest < 0 ? [0, 0, 0] : [0, 1, 2].map((k) => displacement.array[nearest * 3 + k]);
    return { base, move };
  });
}

/** A ring target in the mesh's space at the deformation `scale` (times the true displacement). */
export const ringPoint = ({ base, move }, scale) => base.map((value, k) => value + scale * move[k]);

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
    };
  });
  return found;
}

/** The file's own positions and what is currently shown, kept on the mesh. */
function shown(mesh) {
  let kept = mesh.userData.__fea;
  if (!kept) {
    kept = { position: Float32Array.from(mesh.geometry.getAttribute("position").array), field: null, scale: null };
    mesh.userData.__fea = kept;
  }
  return kept;
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
 * Returns true when the colours changed; false when that field and tint were already shown.
 */
export function recolorByField(mesh, field, ramp = DEFAULT_RAMP, highlight = null, parts = null, softParts = null) {
  const color = mesh.geometry.getAttribute("color");
  const values = fieldValues(mesh, field);
  if (!color || !values) {
    return false;
  }
  const kept = shown(mesh);
  const faces = vertexFaces(mesh);
  const tinted = faces && highlight?.length ? new Set(highlight) : null;
  const partOf = vertexParts(mesh);
  const tintedParts = partOf && parts?.length ? new Set(parts) : null;
  const lightParts = partOf && softParts?.length ? new Set(softParts) : null;
  const sorted = (set) => (set ? [...set].sort((a, b) => a - b).join(",") : "");
  const key = `${field.attribute}|${sorted(tinted)}|${sorted(tintedParts)}|${sorted(lightParts)}`;
  if (kept.field === key) {
    return false;
  }
  const table = rampTable(ramp);
  const span = field.max - field.min;
  const stride = color.itemSize;
  const bytes = color.array;
  for (let i = 0; i < values.length; i += 1) {
    const t = span > 0 ? clamp((values[i] - field.min) / span, 0, 1) : 0;
    const entry = Math.round(t * 255) * 3;
    const base = i * stride;
    const tint = (tinted !== null && tinted.has(Math.round(faces[i]))) || (tintedParts !== null && tintedParts.has(Math.round(partOf[i])));
    const blend = tint ? HIGHLIGHT_BLEND : lightParts !== null && lightParts.has(Math.round(partOf[i])) ? SOFT_BLEND : 0;
    for (let k = 0; k < 3; k += 1) {
      bytes[base + k] = blend ? Math.round(table[entry + k] + (HIGHLIGHT[k] - table[entry + k]) * blend) : table[entry + k];
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

/** Sensible slider bounds for the deformation scale: 0 to four times the file's own. */
export function deformationRange(baseScale) {
  const max = Math.max(1, (Number(baseScale) || 1) * 4);
  const step = max >= 100 ? 1 : max >= 10 ? 0.5 : 0.1;
  return { min: 0, max, step };
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
 * "" for a field this does not know how to say.
 */
export function feaSummaryLine(result, field) {
  const peak = (attribute) => result.fields.find((entry) => entry.attribute === attribute);
  const stress = peak("_von_mises");
  const displacement = peak("_displacement");
  const moves = displacement ? `${plainNumber(displacement.max)} ${displacement.units}`.trim() : "";
  if (field.attribute === "_displacement") {
    return moves ? `Moves up to ${moves}` : "";
  }
  if (field.attribute !== "_von_mises") {
    return "";
  }
  const factor = result.safetyFactor;
  // Under 1 the part yields: "holds 0.4×" would read as a pass.
  const holds = factor === null ? "" : factor < 1 ? "yields under this load" : `holds ${flooredFactor(factor)}× this load`;
  // An assembly leads with its weakest part, whose peak (not the assembly's) and factor these are.
  const weakest = result.weakestPart && result.weakestPartPeakMPa !== null;
  return [
    weakest ? `Weakest: ${spaced(result.weakestPart)}` : "",
    `${weakest ? "peak stress" : "Peak stress"} ${plainNumber(weakest ? result.weakestPartPeakMPa : stress.max)} ${stress.units}`.trim(),
    holds,
    moves ? `${weakest ? "the assembly moves" : "moves"} up to ${moves}` : "",
  ].filter(Boolean).join(" · ");
}

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
 * for one along an axis, else "along (0.6, 0, -0.8)", its unit vector. "" for no force.
 */
export function forceDirection(force) {
  const length = Math.hypot(...force);
  if (!(length > 0)) return "";
  const unit = force.map((value) => value / length);
  const axis = unit.findIndex((value) => Math.abs(value) > 1 - 1e-6);
  if (axis === 2) return unit[2] < 0 ? "down" : "up";
  if (axis >= 0) return `along ${unit[axis] < 0 ? "-" : "+"}${AXIS_NAMES[axis]}`;
  return `along (${unit.map((value) => plainNumber(value)).join(", ")})`;
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

/** A part's row detail: its material and what it holds ("yields" under a factor of 1, as the colour bar says). */
function partDetail(part) {
  const factor = part.safetyFactor;
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
 * An assembly's Parts and Connections groups. A row for a part or a joint is chosen like a face's
 * and carries into Quick Edit and tints: a part its ref (`refs`) and its triangles (`parts`, indices
 * into the result's `parts`); a joint its interface `faces`, or for a free pair (no faces) both
 * parts' refs. Their details wrap (`wrap`) rather than truncate.
 */
function assemblyRows(result) {
  const rows = [];
  const parts = result.parts.map((part, index) => ({
    id: `part:${index}`, label: spaced(part.name || part.ref), detail: partDetail(part), wrap: true, refs: part.ref ? [part.ref] : [], parts: [index],
    summary: `Part '${part.name || part.ref}'`,
  }));
  if (parts.length) rows.push({ id: "parts", label: "Parts", detail: "", children: parts });
  const joints = result.connections.map((joint, index) => ({
    id: `joint:${index}`, label: `${spaced(joint.names[0])} ↔ ${spaced(joint.names[1])}`, detail: jointDetail(joint), wrap: true,
    softParts: joint.between.map((ref) => result.parts.findIndex((part) => part.ref === ref)).filter((at) => at >= 0),
    ...(joint.faces.length ? { faces: joint.faces } : { refs: joint.between.filter(Boolean) }), summary: jointSummary(joint),
  }));
  if (joints.length) rows.push({ id: "connections", label: "Connections", detail: "", children: joints });
  return rows;
}

/**
 * Study's rows for a result's study, in order: for an assembly its parts and connections, the material, the fixed faces, the loads (each
 * with its faces under it) and the mesh. A row that stands for faces carries them (`faces`, the
 * file's refs) and what a prompt calls them (`summary`); a group row (`children`) carries none.
 * [] for a result written before the study was recorded.
 */
export function studyRows(result) {
  const study = result.study;
  if (!study) return [];
  const rows = assemblyRows(result);
  const material = study.material;
  if (material?.name) {
    const yieldText = material.yieldMPa === null ? "" : `yield ${plainNumber(material.yieldMPa)} MPa`;
    rows.push({ id: "material", label: "Material", detail: [material.name, yieldText].filter(Boolean).join(" · ") });
  }
  const fixed = study.fixtures.flatMap((fixture, index) => fixture.faces.map((ref) => ({
    id: `fixed:${index}:${ref}`, label: faceTitle(result, ref), detail: fixture.type, faces: [ref], summary: faceSummary(study, ref),
  })));
  if (fixed.length) rows.push({ id: "fixed", label: "Fixed", detail: "", children: fixed });
  const loads = study.loads.filter((load) => load.faces.length).map((load, index) => {
    const words = loadWords(load);
    return {
      id: `load:${index}`, label: words.amount, detail: words.direction, faces: load.faces, summary: loadSummary(words, load.faces),
      children: load.faces.map((ref) => ({ id: `load:${index}:${ref}`, label: faceTitle(result, ref), detail: "loaded", faces: [ref],
        summary: study.fixtures.some((fixture) => fixture.faces.includes(ref)) ? faceSummary(study, ref) : loadSummary(words, [ref]) })),
    };
  });
  if (loads.length) rows.push({ id: "loads", label: "Loads", detail: "", children: loads });
  const mesh = study.mesh;
  if (mesh?.sizeMm !== null && mesh?.sizeMm !== undefined) {
    const refined = mesh.refinedFromMm === null ? "not refined" : `refined from ${plainNumber(mesh.refinedFromMm)} mm`;
    rows.push({ id: "mesh", label: "Mesh", detail: `${plainNumber(mesh.sizeMm)} mm elements · ${refined}` });
  }
  return rows;
}

/** A face's heading: "Face 17", and in an assembly "post · face 17", the part it is on (a long name's underscores spaced). */
export function faceTitle(result, ref) {
  const part = result.parts.find((entry) => entry.ref && String(ref).startsWith(`${entry.ref}.`));
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
