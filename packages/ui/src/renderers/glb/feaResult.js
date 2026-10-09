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
 * the result's `safety_factor` (null when it has none).
 * GLTFLoader lower-cases custom attribute names and copies extras into
 * `userData`, which is what is read here.
 *
 * Everything is in-place on the loaded geometry: recolouring rewrites the
 * `color` bytes, re-scaling the deformation rewrites `position` from the
 * file's own positions and displacement vector. The originals are kept on
 * the mesh so any scale or field can be chosen in any order, and a request
 * for what is already shown does nothing.
 */
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

/**
 * Rewrite the mesh's vertex colours from one field over `[field.min, field.max]`.
 * Returns true when the colours changed; false when that field was already shown.
 */
export function recolorByField(mesh, field, ramp = DEFAULT_RAMP) {
  const color = mesh.geometry.getAttribute("color");
  const values = fieldValues(mesh, field);
  if (!color || !values) {
    return false;
  }
  const kept = shown(mesh);
  if (kept.field === field.attribute) {
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
    bytes[base] = table[entry];
    bytes[base + 1] = table[entry + 1];
    bytes[base + 2] = table[entry + 2];
    if (stride > 3) bytes[base + 3] = 255;
  }
  color.needsUpdate = true;
  kept.field = field.attribute;
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
  return [
    `Peak stress ${plainNumber(stress.max)} ${stress.units}`.trim(),
    holds,
    moves ? `moves up to ${moves}` : "",
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
