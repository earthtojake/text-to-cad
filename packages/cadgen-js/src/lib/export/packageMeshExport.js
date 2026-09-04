// Package -> colored triangle mesh -> STL/GLB/3MF bytes: the ONE mesh export
// path (design/unified-tessellation.md Phases 2-3). Consumes the same
// watertight tessellations the viewport renders, bakes the descriptor's
// ABSOLUTE occurrence transforms (mirroring-safe), resolves colors with the
// same priority the retiring native exporter used (face color > occurrence
// color > component color > part color > default), and serializes:
//
// - STL  — binary, colorless by format;
// - GLB  — one primitive per color through writeGlb's export preset;
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

// Authored sRGB already, not a linear colour: it goes into the same hex slot the
// encoded colours do, so it must NOT run through linearRgbToHex.
const DEFAULT_COLOR_HEX = "#d4d4d8";

// Row-major 3x4 (first 12 of the descriptor's 16-float row-major 4x4).
function transformPoint(m, x, y, z, out, offset) {
  out[offset] = m[0] * x + m[1] * y + m[2] * z + m[3];
  out[offset + 1] = m[4] * x + m[5] * y + m[6] * z + m[7];
  out[offset + 2] = m[8] * x + m[9] * y + m[10] * z + m[11];
}

function determinant3(m) {
  return (
    m[0] * (m[5] * m[10] - m[6] * m[9]) -
    m[1] * (m[4] * m[10] - m[6] * m[8]) +
    m[2] * (m[4] * m[9] - m[5] * m[8])
  );
}

// Normal matrix = inverse-transpose of the upper 3x3 (handles mirroring and
// any shear a descriptor could legally carry).
function normalMatrix3(m) {
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

function identityTransform(transform) {
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
 * Returns { primitives: [{ positions, normals, color }], triangleCount }.
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
  const jobs = [];
  const groupSizes = new Map(); // colorHex -> float count
  for (const occurrence of descriptor.occurrences || []) {
    const cid = String(occurrence.component || "");
    const tessellation = componentTessellations.get(cid);
    if (!tessellation) continue;
    const occurrenceColor = linearRgbToHex(occurrence.color);
    const componentColor = componentColors.get(cid) || null;
    const partColor = linearRgbToHex(tessellation.partColor) || null;
    const fallback = occurrenceColor || componentColor || partColor || defaultColor;

    const transform = Array.isArray(occurrence.transform) ? occurrence.transform : null;
    const identity = transform === null || identityTransform(transform);
    const mirrored = !identity && determinant3(transform) < 0;
    const nm = identity ? null : normalMatrix3(transform);

    for (const range of tessellation.faceRanges || []) {
      const indexCount = Number(range.indexCount) || 0;
      const triangles = Math.max(0, Math.ceil(indexCount / 3));
      if (!triangles) continue;
      const color = linearRgbToHex(range.color) || fallback;
      groupSizes.set(color, (groupSizes.get(color) || 0) + triangles * 9);
      jobs.push({ tessellation, range, color, transform: identity ? null : transform, mirrored, nm });
    }
  }

  const groups = new Map(); // colorHex -> { positions: Float32Array, normals: Float32Array, offset }
  for (const [color, floatCount] of groupSizes) {
    groups.set(color, {
      positions: new Float32Array(floatCount),
      normals: new Float32Array(floatCount),
      offset: 0,
    });
  }

  for (const job of jobs) {
    const { positions, normals, indices } = job.tessellation;
    const { range, transform, mirrored, nm } = job;
    const group = groups.get(job.color);
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
    .sort(([a], [b]) => (a < b ? -1 : 1)) // deterministic order
    .map(([color, group]) => ({
      color,
      positions: group.positions,
      normals: group.normals,
    }))
    .filter((primitive) => primitive.positions.length >= 9);
  const triangleCount = primitives.reduce((sum, p) => sum + p.positions.length / 9, 0);
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

function yUpPrimitives(primitives) {
  return primitives.map(({ color, positions, normals }) => {
    const rotate = (src, scale) => {
      const out = new Float32Array(src.length);
      for (let i = 0; i < src.length; i += 3) {
        out[i] = src[i] * scale;
        out[i + 1] = src[i + 2] * scale;
        out[i + 2] = -src[i + 1] * scale;
      }
      return out;
    };
    return {
      color,
      positions: rotate(positions, CAD_TO_GLB_SCALE),
      normals: rotate(normals, 1),
    };
  });
}

export function packageMeshToGlb({ primitives }, { name = "model" } = {}) {
  return writeGlb(
    { primitives: yUpPrimitives(primitives) },
    // upAxis: "y" states what yUpPrimitives just produced. It changes no geometry —
    // these bytes stay the spec-conformant Y-up metres they always were — it only stops
    // the CAD reader from having to guess, which it used to get wrong.
    { preset: "export", name, sourceKind: "step", units: "m", upAxis: "y" },
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
