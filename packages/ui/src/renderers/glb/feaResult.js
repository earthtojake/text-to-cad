/**
 * An FEA result inside a GLB, as `cadgen fea solve` writes it, and what the
 * viewer can do with it without a second file.
 *
 * The writer (cadgen `_internal/fea/outputs.py`) stores the raw fields as
 * custom vertex attributes beside the baked colour: `_VON_MISES` (float, MPa)
 * and `_DISPLACEMENT` (vec3, glTF units, i.e. metres, unscaled), and puts in
 * the mesh extras a `fields` list describing each one (`attribute`, `name`,
 * `units`, `min`, `max`, `attribute_scale`), `deformation_scale` (the
 * multiplier already baked into the positions) and the colour `ramp` it used.
 * GLTFLoader lower-cases custom attribute names and copies extras into
 * `userData`, which is what is read here.
 *
 * Everything is in-place on the loaded geometry: recolouring rewrites the
 * `color` bytes, re-scaling the deformation rewrites `position` from the
 * file's own positions and displacement vector. The originals are kept on
 * the mesh so any scale or field can be chosen in any order, and a request
 * for what is already shown does nothing.
 */
import { clamp } from "@hardcore/core/common/numbers.js";

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

/** The CSS gradient of the ramp, low at the bottom, for a vertical colour bar. */
export function feaRampGradient(stops = DEFAULT_RAMP) {
  const parts = stops.map(([t, [r, g, b]]) =>
    `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}) ${Math.round(t * 100)}%`);
  return `linear-gradient(to top, ${parts.join(", ")})`;
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
      fields,
      ramp: rampStops(extras.ramp),
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

/** A legend tick's text: enough figures to tell the values apart, no more. */
export function formatValue(value) {
  const v = Number(value) || 0;
  if (v === 0) return "0";
  const magnitude = Math.abs(v);
  if (magnitude >= 100) return v.toFixed(0);
  if (magnitude >= 10) return v.toFixed(1);
  if (magnitude >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}
