/**
 * An FEA result inside a GLB, as `cadgen fea solve` writes it, and what the
 * viewer can do with it without a second file.
 *
 * The writer (cadgen `_internal/fea/outputs.py`) stores the raw fields as
 * custom vertex attributes beside the baked colour: `_VON_MISES` (float, MPa)
 * and `_DISPLACEMENT` (vec3, glTF units, i.e. metres, unscaled), and puts a
 * `fields` list in the mesh extras describing each one (`attribute`, `name`,
 * `units`, `min`, `max`, `attribute_scale`), plus `deformation_scale`, the
 * multiplier already baked into the positions. GLTFLoader lower-cases custom
 * attribute names and copies extras into `userData`, which is what is read
 * here.
 *
 * Everything is in-place on the loaded geometry: recolouring rewrites the
 * `color` bytes, re-scaling the deformation rewrites `position` from the
 * file's own positions and displacement vector. The originals are kept on
 * the mesh so any scale or field can be chosen in any order.
 */

const GENERATOR = "cadgen fea";

// The writer's ramp (outputs.py `_RAMP`), so the viewer's recolouring
// reproduces the file's baked colours bit for bit at the same range.
export const FEA_RAMP = Object.freeze([
  [0.0, [0.05, 0.10, 0.90]],
  [0.25, [0.05, 0.85, 0.95]],
  [0.5, [0.10, 0.85, 0.15]],
  [0.75, [0.98, 0.90, 0.10]],
  [1.0, [0.90, 0.08, 0.05]],
]);

/** RGB in [0, 1] for t in [0, 1], piecewise linear between the ramp stops. */
export function feaRamp(t) {
  const x = Math.min(Math.max(Number(t) || 0, 0), 1);
  for (let i = 1; i < FEA_RAMP.length; i += 1) {
    const [t1, c1] = FEA_RAMP[i];
    if (x <= t1) {
      const [t0, c0] = FEA_RAMP[i - 1];
      const f = t1 === t0 ? 0 : (x - t0) / (t1 - t0);
      if (f >= 1) return [...c1];
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f];
    }
  }
  return [...FEA_RAMP[FEA_RAMP.length - 1][1]];
}

/** The CSS gradient of the ramp, low at the bottom, for a vertical colour bar. */
export function feaRampGradient() {
  const stops = FEA_RAMP.map(([t, [r, g, b]]) =>
    `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}) ${Math.round(t * 100)}%`);
  return `linear-gradient(to top, ${stops.join(", ")})`;
}

function attributeName(name) {
  return String(name || "").toLowerCase();
}

/**
 * The FEA result a loaded GLB scene carries, or null for any other GLB.
 * `scene` is what `useGlbScene` returns (`scene.document.scene` is the glTF
 * root); a plain three `Object3D` is accepted too.
 */
export function readFeaResult(scene) {
  const root = scene?.document?.scene || scene?.object3D || scene;
  if (!root?.traverse) {
    return null;
  }
  let found = null;
  root.traverse((object) => {
    if (found || !object?.isMesh || !object.geometry) {
      return;
    }
    const extras = object.userData || {};
    const fields = Array.isArray(extras.fields) ? extras.fields : null;
    if (extras.generator !== GENERATOR || !fields) {
      return;
    }
    const usable = fields
      .filter((field) => field && typeof field.attribute === "string" && object.geometry.getAttribute(attributeName(field.attribute)))
      .map((field) => ({
        attribute: attributeName(field.attribute),
        name: String(field.name || field.attribute),
        units: String(field.units || ""),
        min: Number(field.min) || 0,
        max: Number(field.max) || 0,
        attributeScale: Number(field.attribute_scale) || 1,
      }));
    if (usable.length === 0) {
      return;
    }
    found = {
      mesh: object,
      name: String(extras.name || ""),
      document: String(extras.document || ""),
      occurrence: String(extras.occurrence || ""),
      deformationScale: Number(extras.deformation_scale) || 1,
      fields: usable,
    };
  });
  return found;
}

function originals(mesh) {
  const geometry = mesh.geometry;
  let kept = mesh.userData.__fea;
  if (!kept) {
    kept = {
      position: Float32Array.from(geometry.getAttribute("position").array),
      color: geometry.getAttribute("color") ? Uint8Array.from(geometry.getAttribute("color").array) : null,
    };
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
  const count = attribute.count;
  const size = attribute.itemSize;
  const out = new Float32Array(count);
  const scale = field.attributeScale || 1;
  for (let i = 0; i < count; i += 1) {
    if (size === 1) {
      out[i] = attribute.array[i] * scale;
    } else {
      let sum = 0;
      for (let k = 0; k < size; k += 1) {
        const v = attribute.array[i * size + k];
        sum += v * v;
      }
      out[i] = Math.sqrt(sum) * scale;
    }
  }
  return out;
}

/**
 * Rewrite the mesh's vertex colours from one field over `[field.min, field.max]`.
 * Returns true when something changed (the caller requests a render).
 */
export function recolorByField(mesh, field) {
  const color = mesh.geometry.getAttribute("color");
  const values = fieldValues(mesh, field);
  if (!color || !values) {
    return false;
  }
  originals(mesh);
  const span = field.max - field.min;
  const stride = color.itemSize;
  const bytes = color.array;
  const isByte = bytes instanceof Uint8Array || bytes instanceof Uint8ClampedArray;
  for (let i = 0; i < values.length; i += 1) {
    const t = span > 0 ? (values[i] - field.min) / span : 0;
    const [r, g, b] = feaRamp(t);
    const base = i * stride;
    if (isByte) {
      bytes[base] = Math.round(r * 255);
      bytes[base + 1] = Math.round(g * 255);
      bytes[base + 2] = Math.round(b * 255);
      if (stride > 3) bytes[base + 3] = 255;
    } else {
      bytes[base] = r;
      bytes[base + 1] = g;
      bytes[base + 2] = b;
      if (stride > 3) bytes[base + 3] = 1;
    }
  }
  color.needsUpdate = true;
  return true;
}

/**
 * Show the displacement at `scale` times its true size. The file's positions
 * already carry `baseScale` times the displacement, so the change is
 * `(scale - baseScale)` times the displacement vector. Returns true when the
 * positions changed.
 */
export function applyDeformation(mesh, scale, baseScale) {
  const geometry = mesh.geometry;
  const position = geometry.getAttribute("position");
  const displacement = geometry.getAttribute("_displacement");
  if (!position || !displacement || displacement.itemSize !== 3) {
    return false;
  }
  const kept = originals(mesh);
  const delta = (Number(scale) || 0) - (Number(baseScale) || 0);
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
