// A part's volume from the mesh it is drawn with: the signed volume of its closed
// triangle surface (the divergence theorem, one tetrahedron per triangle from the origin).
// Curved faces are tessellated, so on them this is a close approximation, not the exact
// B-rep volume. A part places its component's local mesh by its transform; a rigid
// placement keeps the volume, and |det| accounts for any scale.

const componentVolumeCache = new WeakMap();

export function meshVolume(vertices, indices, triangleOffset = 0, triangleCount = null) {
  if (!vertices?.length || !indices?.length) return null;
  const count = triangleCount ?? Math.floor(indices.length / 3) - triangleOffset;
  let sum = 0;
  for (let t = triangleOffset; t < triangleOffset + count; t += 1) {
    const a = indices[t * 3] * 3, b = indices[t * 3 + 1] * 3, c = indices[t * 3 + 2] * 3;
    const ax = vertices[a], ay = vertices[a + 1], az = vertices[a + 2];
    const bx = vertices[b], by = vertices[b + 1], bz = vertices[b + 2];
    const cx = vertices[c], cy = vertices[c + 1], cz = vertices[c + 2];
    sum += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
  }
  const volume = Math.abs(sum) / 6;
  return Number.isFinite(volume) && volume > 0 ? volume : null;
}

function determinant3(matrix) {
  if (!Array.isArray(matrix) && !ArrayBuffer.isView(matrix)) return 1;
  if (matrix.length !== 16) return 1;
  // Row-major or column-major: the upper-left 3x3 has the same determinant either way.
  const [a, b, c, , d, e, f, , g, h, i] = matrix;
  const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  return Number.isFinite(det) ? Math.abs(det) : 1;
}

export function partVolume(part, meshData = null) {
  if (!part) return null;
  const source = part.sourceMesh;
  if (source?.vertices && source?.indices) {
    let volume = componentVolumeCache.get(source);
    if (volume === undefined) {
      volume = meshVolume(source.vertices, source.indices);
      componentVolumeCache.set(source, volume);
    }
    return volume === null ? null : volume * determinant3(part.transform);
  }
  // A single-document mesh: the part is a triangle range of the shared buffers.
  const offset = Number(part.triangleOffset), count = Number(part.triangleCount);
  if (meshData?.vertices && meshData?.indices && Number.isInteger(offset) && Number.isInteger(count) && count > 0) {
    return meshVolume(meshData.vertices, meshData.indices, offset, count);
  }
  return null;
}

/** A tree node's volume: its own part, or the sum of its leaf parts. Null if any is unknown. */
export function nodeVolume(node, meshData) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  if (!node || !parts.length) return null;
  const ids = Array.isArray(node.leafPartIds) && node.leafPartIds.length
    ? node.leafPartIds
    : [node.occurrenceId || node.id].filter(Boolean);
  if (!ids.length) return null;
  const byId = new Map(parts.map((part) => [String(part.id || part.occurrenceId || ""), part]));
  let total = 0;
  for (const id of ids) {
    const volume = partVolume(byId.get(String(id)), meshData);
    if (volume === null) return null;
    total += volume;
  }
  return total;
}
