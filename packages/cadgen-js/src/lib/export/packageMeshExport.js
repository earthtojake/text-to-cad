// Package -> colored triangle mesh -> STL/GLB/3MF bytes: the ONE mesh export
// path (design/unified-tessellation.md Phases 2-3). Consumes the same
// watertight tessellations the viewport renders, bakes the descriptor's
// ABSOLUTE occurrence transforms (mirroring-safe), resolves colors with the
// same priority the retiring native exporter used (face color > occurrence
// color > component color > part color > default), and serializes:
//
// - STL  — binary, colorless by format;
// - GLB  — one primitive per color through writeGlb's export preset, or, with
//          `perOccurrence`, one NODE per occurrence so a sampled clip has
//          something to animate (lib/export/packageAnimation.js). An occurrence
//          named in `occurrenceOverrides` brings its own prepared, indexed
//          primitives instead — that is how a morph bake replaces a deforming
//          tube's tessellation with the refined, posed mesh its targets are
//          deltas against (lib/export/packageTubeMorph.js);
// - 3MF  — a basematerials group with per-triangle material references.
//
// This module is PURE (no filesystem): callers supply per-component
// tessellations (bin/mesh-export.mjs adds the disk cache; a browser caller
// could feed worker results). Determinism: same tessellations + descriptor in,
// identical bytes out.
import { meshToBinaryStl, xmlEscape, zipStore } from "./meshFormats.js";
import { writeGlb } from "../glb/writeGlb.js";
// Every colour this module reads out of a package -- face, occurrence,
// component, part -- is LINEAR, and every colour it hands downstream is an sRGB
// hex string (writeGlb decodes it back to a linear baseColorFactor; 3MF's
// displaycolor is specified sRGB). linearRgbToHex is that boundary.
import { linearRgbToHex } from "../color.js";

export const PACKAGE_MESH_EXPORT_FORMATS = ["stl", "glb", "3mf"];

// Largest primitive this module emits. Both the GLB writer's vertex weld and
// the 3MF writer's vertex table key every corner of ONE primitive in a JS Map,
// and V8 caps a Map at 2^24 entries ("Map maximum size exceeded"). A 19M-
// triangle single-colour assembly has 58M corners, so a colour group is cut
// into runs of at most this many triangles (2^22 -> 12.6M corners, under the
// cap even with zero welding). Below the cap the output is unchanged; above it
// a colour simply spans several same-material primitives, split at face-range
// boundaries in occurrence order, so bytes stay deterministic.
export const MAX_PRIMITIVE_TRIANGLES = 4_194_304;

// Authored sRGB already, not a linear colour: it goes into the same hex slot the
// encoded colours do, so it must NOT run through linearRgbToHex.
const DEFAULT_COLOR_HEX = "#d4d4d8";

// The per-occurrence PBR FINISH the descriptor may carry (written by cadgen's
// component_package._occurrence_material from a shape's `cad_material`), in the fixed
// order the group key below serializes. It is the same five channels the viewer
// overrides its theme material with, so an export and the viewport agree about a
// brushed, polished or clearcoated part instead of the export flattening every one of
// them to the writer's plastic default.
const MATERIAL_CHANNELS = ["roughness", "metalness", "clearcoat", "clearcoatRoughness", "opacity"];

// Canonicalize so the key is a stable string and the writer gets numbers in [0, 1]
// whatever a hand-built descriptor carried. Returns null when nothing is authored, which
// is what keeps a materialless source's group key -- and therefore its bytes -- exactly
// what it was before finishes existed here.
export function occurrenceMaterial(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const finish = {};
  for (const channel of MATERIAL_CHANNELS) {
    const number = Number(value[channel]);
    if (!Number.isFinite(number)) continue;
    finish[channel] = Math.min(1, Math.max(0, number));
  }
  return Object.keys(finish).length ? finish : null;
}

// The finish's contribution to the grouping key. Colour alone would merge a brushed and
// a polished body that happen to share a colour into ONE material, and the file would
// then show one finish for both. Empty for an unauthored finish.
export function materialKey(finish) {
  if (!finish) return "";
  return `|${MATERIAL_CHANNELS.map((channel) => (channel in finish ? finish[channel] : "")).join(",")}`;
}

/** Every face range of one occurrence resolved to its export colour.
 *
 * The priority is the export's own (face > occurrence > component > part >
 * default) and lives here alone: the morph bake (lib/export/packageTubeMorph.js)
 * replaces a deforming occurrence's primitives wholesale, and a second copy of
 * this chain would let a tendon export in one colour and its neighbours in
 * another for no reason a reader could find.
 */
export function occurrenceFaceRangeColors(descriptor, occurrence, tessellation, defaultColor = DEFAULT_COLOR_HEX) {
  const cid = String(occurrence?.component || "");
  const occurrenceColor = linearRgbToHex(occurrence?.color);
  const componentColor = linearRgbToHex(descriptor?.components?.[cid]?.color) || null;
  const partColor = linearRgbToHex(tessellation?.partColor) || null;
  const fallback = occurrenceColor || componentColor || partColor || defaultColor;
  return (tessellation?.faceRanges || []).map((range) => linearRgbToHex(range.color) || fallback);
}

// Row-major 3x4 (first 12 of the descriptor's 16-float row-major 4x4).
export function transformPoint(m, x, y, z, out, offset) {
  out[offset] = m[0] * x + m[1] * y + m[2] * z + m[3];
  out[offset + 1] = m[4] * x + m[5] * y + m[6] * z + m[7];
  out[offset + 2] = m[8] * x + m[9] * y + m[10] * z + m[11];
}

export function determinant3(m) {
  return (
    m[0] * (m[5] * m[10] - m[6] * m[9]) -
    m[1] * (m[4] * m[10] - m[6] * m[8]) +
    m[2] * (m[4] * m[9] - m[5] * m[8])
  );
}

// Normal matrix = inverse-transpose of the upper 3x3 (handles mirroring and
// any shear a descriptor could legally carry).
export function normalMatrix3(m) {
  const a = m[0], b = m[1], c = m[2];
  const d = m[4], e = m[5], f = m[6];
  const g = m[8], h = m[9], i = m[10];
  const A = e * i - f * h;
  const B = f * g - d * i;
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (!Number.isFinite(det) || Math.abs(det) < 1e-30) return null;
  const inv = 1 / det;
  // inverse (row-major), then transpose -> columns of the inverse.
  return [
    A * inv, B * inv, C * inv,
    (c * h - b * i) * inv, (a * i - c * g) * inv, (b * g - a * h) * inv,
    (b * f - c * e) * inv, (c * d - a * f) * inv, (a * e - b * d) * inv,
  ];
}

export function identityTransform(transform) {
  if (!Array.isArray(transform) || transform.length < 12) return true;
  const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0];
  return IDENTITY.every((value, index) => transform[index] === value);
}

/**
 * Bake a package into color-grouped triangle soup.
 *
 * descriptor              — the package's assembly.json object
 * componentTessellations  — Map<cid, { positions, normals, indices, faceRanges, partColor }>
 *                           (tessellateComponent output + the surf's partColor)
 *
 * Returns { primitives: [{ positions, normals, color, material? }], triangleCount }.
 */
export function buildPackageMeshPrimitives(descriptor, componentTessellations, options = {}) {
  const defaultColor = options.defaultColor || DEFAULT_COLOR_HEX;
  const componentColors = new Map(
    Object.entries(descriptor.components || {}).map(([cid, entry]) => [
      cid,
      linearRgbToHex(entry?.color),
    ]),
  );

  // Pass 1 — resolve every (occurrence x face range) into a placement job and
  // count the floats each colour group needs. Pass 2 then writes into
  // preallocated Float32Arrays: growing plain JS arrays here used to hit V8's
  // fast-elements backing-store cap (~2^27 elements, "invalid array length")
  // on large single-colour assemblies. Rounding is unchanged — every value was
  // already converted to float32 at primitive build, and nothing reads a value
  // back after writing it.
  const maxPrimitiveTriangles = Math.max(1, Math.floor(Number(options.maxPrimitiveTriangles) || MAX_PRIMITIVE_TRIANGLES));
  // Per-occurrence output: one glTF node per occurrence, which is what an animation
  // channel has to target. It costs welding across occurrences (a colour that spanned
  // the assembly becomes one primitive per occurrence of it), so it is opt-in and the
  // default stays the flat, colour-grouped soup every static export has always been.
  const perOccurrence = options.perOccurrence === true;
  const hidden = options.hiddenOccurrenceIds instanceof Set ? options.hiddenOccurrenceIds : null;
  const opacityByOccurrence = options.occurrenceOpacity instanceof Map ? options.occurrenceOpacity : null;
  // Occurrences whose geometry somebody else already built: the morph bake replaces
  // a deforming tube's tessellation with the REFINED, POSED one its targets are
  // deltas against, and hands those primitives (indexed, with `targets`) in here.
  // They take the same group keys the soup path would have taken, so they sort into
  // the same place and the file's node order does not depend on which occurrences
  // deformed.
  const overrides = options.occurrenceOverrides instanceof Map ? options.occurrenceOverrides : null;
  if (overrides && !perOccurrence) {
    throw new Error(
      "buildPackageMeshPrimitives: occurrenceOverrides needs perOccurrence — an override is "
      + "keyed by occurrence, and the flat soup has no occurrence to key it to"
    );
  }
  const jobs = [];
  // group key -> { color, material, node, name, occurrenceId, opacity, chunks: [{ triangles, floatCount, positions, normals, offset }] }
  // The key is the COLOUR alone in the flat case, so the grouping and the sort below are
  // exactly what they were; per occurrence it is a zero-padded occurrence ordinal plus
  // the colour, so sorting the same strings sorts by occurrence and then by colour. An
  // authored FINISH appends itself to whichever of those two the caller asked for -- so a
  // source with no material keys, sorts and serializes byte for byte as it always did,
  // and two same-colour different-finish bodies stay two groups.
  const groups = new Map();
  let occurrenceIndex = -1;
  for (const occurrence of descriptor.occurrences || []) {
    occurrenceIndex += 1;
    const cid = String(occurrence.component || "");
    const tessellation = componentTessellations.get(cid);
    if (!tessellation) continue;
    const occurrenceId = String(occurrence.id || cid);
    if (hidden?.has(occurrenceId)) continue;
    const occurrenceColor = linearRgbToHex(occurrence.color);
    const componentColor = componentColors.get(cid) || null;
    const partColor = linearRgbToHex(tessellation.partColor) || null;
    const fallback = occurrenceColor || componentColor || partColor || defaultColor;
    const opacity = opacityByOccurrence?.has(occurrenceId)
      ? opacityByOccurrence.get(occurrenceId)
      : null;
    // The occurrence's authored finish rides every face range it owns. `opacity` above is
    // a CALLER's override (an animation clip's faded occurrence) and stays separate: the
    // writer resolves the two, preferring the override.
    const material = occurrenceMaterial(occurrence.material);
    const finishKey = materialKey(material);

    const override = overrides?.get(occurrenceId);
    if (override) {
      // Prepared geometry, spliced in at this occurrence's own ordinal so the group
      // ordering below is what it would have been. No chunking: an override is
      // already indexed and already one primitive per colour.
      override.forEach((primitive, ordinal) => {
        const key = `${String(occurrenceIndex).padStart(8, "0")}|${primitive.color}`
          + `${materialKey(primitive.material || null)}|${String(ordinal).padStart(4, "0")}`;
        groups.set(key, {
          override: {
            ...primitive,
            node: occurrenceId,
            name: String(occurrence.name || occurrenceId),
            occurrenceId,
            ...(opacity === null || opacity === undefined ? {} : { opacity }),
          },
        });
      });
      continue;
    }

    const transform = Array.isArray(occurrence.transform) ? occurrence.transform : null;
    const identity = transform === null || identityTransform(transform);
    const mirrored = !identity && determinant3(transform) < 0;
    const nm = identity ? null : normalMatrix3(transform);

    for (const range of tessellation.faceRanges || []) {
      const indexCount = Number(range.indexCount) || 0;
      const triangles = Math.max(0, Math.ceil(indexCount / 3));
      if (!triangles) continue;
      const color = linearRgbToHex(range.color) || fallback;
      const key = (perOccurrence
        ? `${String(occurrenceIndex).padStart(8, "0")}|${color}`
        : color) + finishKey;
      let group = groups.get(key);
      if (!group) {
        groups.set(key, (group = {
          color,
          material,
          chunks: [],
          node: perOccurrence ? occurrenceId : null,
          name: perOccurrence ? String(occurrence.name || occurrenceId) : null,
          occurrenceId: perOccurrence ? occurrenceId : null,
          opacity,
        }));
      }
      let chunk = group.chunks[group.chunks.length - 1];
      // A face range never splits: one range larger than the cap becomes its
      // own oversized chunk (and would still hit the Map cap downstream).
      if (!chunk || chunk.triangles + triangles > maxPrimitiveTriangles) {
        chunk = { triangles: 0, floatCount: 0, positions: null, normals: null, offset: 0 };
        group.chunks.push(chunk);
      }
      chunk.triangles += triangles;
      chunk.floatCount += triangles * 9;
      jobs.push({ tessellation, range, color, chunk, transform: identity ? null : transform, mirrored, nm });
    }
  }

  for (const group of groups.values()) {
    for (const chunk of group.chunks || []) {
      chunk.positions = new Float32Array(chunk.floatCount);
      chunk.normals = new Float32Array(chunk.floatCount);
    }
  }

  for (const job of jobs) {
    const { positions, normals, indices } = job.tessellation;
    const { range, transform, mirrored, nm } = job;
    const group = job.chunk;
    const out = group.positions;
    const outNormals = group.normals;
    let base = group.offset;
    // Mirroring flips winding so recomputed facet normals stay outward.
    const order = mirrored ? [0, 2, 1] : [0, 1, 2];
    for (let k = range.indexStart; k < range.indexStart + range.indexCount; k += 3) {
      for (const corner of order) {
        const v = indices[k + corner];
        const x = positions[v * 3];
        const y = positions[v * 3 + 1];
        const z = positions[v * 3 + 2];
        if (transform === null) {
          out[base] = x;
          out[base + 1] = y;
          out[base + 2] = z;
        } else {
          transformPoint(transform, x, y, z, out, base);
        }
        const nx = normals[v * 3];
        const ny = normals[v * 3 + 1];
        const nz = normals[v * 3 + 2];
        let tx = nx;
        let ty = ny;
        let tz = nz;
        // The TRUE inverse-transpose (det-divided, not the adjugate) maps
        // reflected surfaces' outward normals correctly with no extra
        // mirrored-case negation; only the winding needs the flip above.
        if (nm) {
          tx = nm[0] * nx + nm[1] * ny + nm[2] * nz;
          ty = nm[3] * nx + nm[4] * ny + nm[5] * nz;
          tz = nm[6] * nx + nm[7] * ny + nm[8] * nz;
        }
        const length = Math.hypot(tx, ty, tz) || 1;
        outNormals[base] = tx / length;
        outNormals[base + 1] = ty / length;
        outNormals[base + 2] = tz / length;
        base += 3;
      }
    }
    group.offset = base;
  }

  const primitives = [...groups.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1)) // deterministic order: group key, then run order
    .flatMap(([, group]) => (group.override ? [group.override] : group.chunks.map((chunk) => ({
      color: group.color,
      positions: chunk.positions,
      normals: chunk.normals,
      ...(group.node === null ? {} : {
        node: group.node,
        name: group.name,
        occurrenceId: group.occurrenceId,
      }),
      ...(group.opacity === null || group.opacity === undefined ? {} : { opacity: group.opacity }),
      ...(group.material === null ? {} : { material: group.material }),
    }))))
    .filter((primitive) => (primitive.indices ? primitive.indices.length >= 3 : primitive.positions.length >= 9));
  // An INDEXED primitive (a morph override) counts its triangles from its index
  // buffer; the soup path's are three vertices each, which is where 9 floats comes
  // from. One count for both, so a summary's triangleCount means one thing.
  const triangleCount = primitives.reduce(
    (sum, p) => sum + (p.indices ? p.indices.length / 3 : p.positions.length / 9),
    0,
  );
  return { primitives, triangleCount };
}

export function packageMeshToStl({ primitives }, { name = "model" } = {}) {
  let total = 0;
  for (const p of primitives) total += p.positions.length;
  const positions = new Float32Array(total);
  let offset = 0;
  for (const p of primitives) {
    positions.set(p.positions, offset);
    offset += p.positions.length;
  }
  return meshToBinaryStl({ positions }, { name });
}

// glTF is Y-up and meter-scaled; packages are Z-up CAD millimetres:
// (x, y, z) -> (x, z, -y) (a proper rotation — winding and outwardness
// untouched) and mm -> m on positions only.
const CAD_TO_GLB_SCALE = 0.001;

function rotateToYUp(src, scale) {
  const out = new Float32Array(src.length);
  for (let i = 0; i < src.length; i += 3) {
    out[i] = src[i] * scale;
    out[i + 1] = src[i + 2] * scale;
    out[i + 2] = -src[i + 1] * scale;
  }
  return out;
}

// A morph target's POSITION delta is a VECTOR, not a point: the same rotation and
// the same mm -> m scale apply, with no translation to worry about, and a NORMAL
// delta takes the rotation at scale 1 exactly as a normal does. Getting this wrong
// is the whole reason verifyMorphReconstruction below exists -- a file whose base
// was rotated and whose deltas were not opens, animates, and is wrong.
function yUpTargets(targets) {
  return targets.map((target) => ({
    positionDeltas: rotateToYUp(target.positionDeltas, CAD_TO_GLB_SCALE),
    ...(target.normalDeltas ? { normalDeltas: rotateToYUp(target.normalDeltas, 1) } : {}),
  }));
}

/** `base + delta_k` against a posed reference carried across INDEPENDENTLY.
 *
 * True by construction, which is exactly why it is worth asserting: the bugs it
 * catches are the ones that produce a plausible file. The morph bake hands a small
 * strided sample of each primitive's vertices posed in CAD millimetres; this rotates
 * THAT with its own literal and checks the file's own numbers reproduce it. A basis
 * change applied to the base and not the deltas, a scale applied twice, a normal
 * delta that went through the position path -- each is a file that opens and moves
 * and is wrong, and each fails here.
 */
function verifyMorphReconstruction(primitive) {
  const verify = primitive.verify;
  if (!verify) {
    return;
  }
  const { vertexIds, posed } = verify;
  for (let k = 0; k < posed.length; k += 1) {
    const deltas = primitive.targets[k].positionDeltas;
    for (let s = 0; s < vertexIds.length; s += 1) {
      const v = vertexIds[s] * 3;
      const reference = [
        posed[k][s * 3] * CAD_TO_GLB_SCALE,
        posed[k][s * 3 + 2] * CAD_TO_GLB_SCALE,
        -posed[k][s * 3 + 1] * CAD_TO_GLB_SCALE,
      ];
      for (let axis = 0; axis < 3; axis += 1) {
        const rebuilt = primitive.positions[v + axis] + deltas[v + axis];
        if (Math.abs(rebuilt - reference[axis]) > MORPH_RECONSTRUCTION_TOLERANCE_M) {
          throw new Error(
            `packageMeshExport: morph target ${k} of ${primitive.occurrenceId || primitive.node} `
            + `rebuilds vertex ${vertexIds[s]} as ${rebuilt} where the posed tube is `
            + `${reference[axis]} (axis ${axis}) — base and deltas are not in the same space`
          );
        }
      }
    }
  }
}

// 1e-6 m is a thousandth of a millimetre: far tighter than anything a bake could be
// wrong by and about forty times the float32 rounding of a half-metre coordinate,
// which is what `base + delta` costs when both are stored as the file stores them.
const MORPH_RECONSTRUCTION_TOLERANCE_M = 1e-6;

function yUpPrimitives(primitives) {
  return primitives.map((primitive) => {
    // Spread first: everything that is not geometry -- the node key, the name, the
    // occurrence id, a dropped opacity -- travels to the writer untouched, and only
    // positions, normals and morph deltas change space.
    const out = {
      ...primitive,
      positions: rotateToYUp(primitive.positions, CAD_TO_GLB_SCALE),
      normals: rotateToYUp(primitive.normals, 1),
      ...(primitive.targets ? { targets: yUpTargets(primitive.targets) } : {}),
    };
    if (out.targets) {
      verifyMorphReconstruction(out);
      delete out.verify;
    }
    return out;
  });
}

export function packageMeshToGlb({ primitives }, { name = "model", animation = null } = {}) {
  return writeGlb(
    { primitives: yUpPrimitives(primitives) },
    // upAxis: "y" states what yUpPrimitives just produced. It changes no geometry —
    // these bytes stay the spec-conformant Y-up metres they always were — it only stops
    // the CAD reader from having to guess, which it used to get wrong.
    {
      preset: "export",
      name,
      sourceKind: "step",
      units: "m",
      upAxis: "y",
      // A sampled clip (lib/export/packageAnimation.js): its channels target the node
      // keys the per-occurrence primitives above declared, and its `rest` is what the
      // file shows when nothing plays it.
      ...(animation
        ? { animations: [animation], nodeTransforms: animation.rest || null }
        : {}),
    },
  );
}

export function packageMeshTo3mf({ primitives }, { name = "model" } = {}) {
  // One basematerials group; per-object pid/pindex reference its material.
  const materials = primitives
    .map(
      (p, index) =>
        `      <base name="material-${index}" displaycolor="${xmlEscape(p.color.toUpperCase())}FF"/>`,
    )
    .join("\n");
  const objects = [];
  const buildItems = [];
  primitives.forEach((primitive, index) => {
    const vertices = [];
    const triangles = [];
    const seen = new Map();
    const positions = primitive.positions;
    const vertexId = (x, y, z) => {
      const key = `${x}:${y}:${z}`;
      let id = seen.get(key);
      if (id === undefined) {
        id = seen.size;
        seen.set(key, id);
        vertices.push(`        <vertex x="${x}" y="${y}" z="${z}"/>`);
      }
      return id;
    };
    for (let k = 0; k < positions.length; k += 9) {
      const a = vertexId(positions[k], positions[k + 1], positions[k + 2]);
      const b = vertexId(positions[k + 3], positions[k + 4], positions[k + 5]);
      const c = vertexId(positions[k + 6], positions[k + 7], positions[k + 8]);
      if (a !== b && b !== c && c !== a) {
        triangles.push(`        <triangle v1="${a}" v2="${b}" v3="${c}"/>`);
      }
    }
    const objectId = index + 2; // id 1 is the materials group
    objects.push(
      `    <object id="${objectId}" type="model" pid="1" pindex="${index}">\n` +
        `      <mesh>\n` +
        `        <vertices>\n${vertices.join("\n")}\n        </vertices>\n` +
        `        <triangles>\n${triangles.join("\n")}\n        </triangles>\n` +
        `      </mesh>\n` +
        `    </object>`,
    );
    buildItems.push(`    <item objectid="${objectId}"/>`);
  });
  const model =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" ` +
    `xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">\n` +
    `  <metadata name="Title">${xmlEscape(name)}</metadata>\n` +
    `  <resources>\n` +
    `    <basematerials id="1">\n${materials}\n    </basematerials>\n${objects.join("\n")}\n` +
    `  </resources>\n` +
    `  <build>\n${buildItems.join("\n")}\n  </build>\n` +
    `</model>\n`;
  const contentTypes =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n` +
    `  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n` +
    `  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n` +
    `</Types>\n`;
  const rels =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n` +
    `  <Relationship Target="/3D/3dmodel.model" Id="rel-1" ` +
    `Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n` +
    `</Relationships>\n`;
  return zipStore([
    { name: "[Content_Types].xml", body: contentTypes },
    { name: "_rels/.rels", body: rels },
    { name: "3D/3dmodel.model", body: model },
  ]);
}

export function packageMeshToFormat(mesh, format, options = {}) {
  const normalized = String(format || "").toLowerCase();
  if (options.animation && normalized !== "glb") {
    // STL is triangles and 3MF is a static build plate: neither format has anywhere to
    // put a clip. Dropping it would write a file that looks like the one asked for.
    throw new Error(
      `${normalized || "(no format)"} carries no animation: only glb does — `
      + "export the clip as .glb, or drop the animation for a static mesh"
    );
  }
  if (normalized === "stl") {
    return { body: packageMeshToStl(mesh, options), contentType: "model/stl", extension: ".stl" };
  }
  if (normalized === "glb") {
    return {
      body: packageMeshToGlb(mesh, options),
      contentType: "model/gltf-binary",
      extension: ".glb",
    };
  }
  if (normalized === "3mf") {
    return {
      body: packageMeshTo3mf(mesh, options),
      contentType: "model/3mf",
      extension: ".3mf",
    };
  }
  throw new Error(`Unsupported package mesh export format: ${format}`);
}
