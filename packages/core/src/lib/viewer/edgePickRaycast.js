import { Matrix4, Ray } from "three";

// Culled raycasting for the merged edge-pick LineSegments.
//
// three.js tests every segment of a LineSegments against the ray (three-mesh-bvh
// only accelerates meshes), so an edge pick on a large assembly scanned millions
// of segments. This keeps the one merged buffer and adds a two-level table of
// bounding boxes over CONTIGUOUS runs of segments: a leaf box per
// EDGE_PICK_LEAF_SEGMENTS segments and a group box per EDGE_PICK_GROUP_LEAVES
// leaves. The proxy lays segments out edge by edge and occurrence by occurrence,
// so a contiguous run is spatially tight, and the table needs no reordering: it
// is O(segments) to build, a tenth of the index buffer in bytes, and grows by
// appending boxes when segments are appended.
//
// A ray is answered by three's own LineSegments.raycast, run only over the
// segments whose boxes — group, leaf, then the segment's own — the ray passes
// within the (threshold-inflated) pick distance of. Every segment three would
// report is among them, they are visited in ascending order, and three's code
// does the per-segment test, so the intersections — objects, distances,
// points, indices, order — are exactly the ones the full scan produces.
export const EDGE_PICK_LEAF_SEGMENTS = 32;
export const EDGE_PICK_GROUP_LEAVES = 32;

// three's Ray.distanceSqToSegment accumulates rounding of order eps * S^2 in
// the squared distance (S: the size of the problem, ray origin to the far side
// of the data), i.e. ~1e-7 * S in the distance itself even in its
// near-parallel branches. The culling boxes are widened by 1e-4 * S on top of
// the pick threshold, three orders of magnitude over that, so a segment three
// reports as hit is never culled. (For a model 1 m across seen from 10 m that
// is ~1 mm: nothing, for culling.)
const CULL_MARGIN_RELATIVE = 1e-4;

// Keyed by the position typed array: the pick geometry is rebuilt as a fresh
// BufferGeometry on every selector sync but wraps the proxy's arrays, which are
// never written in place (poses and composition allocate new ones).
const tables = new WeakMap();
const baseRaycasts = new WeakMap();

const inverseWorld = new Matrix4();
const localRay = new Ray();

function segmentCountOf(index) {
  return Math.floor((index?.count || 0) / 2);
}

function tableSource(geometry) {
  const position = geometry?.attributes?.position;
  const index = geometry?.index;
  if (!position || !index || position.isInterleavedBufferAttribute || index.isInterleavedBufferAttribute
    || position.itemSize !== 3 || index.itemSize !== 1 || position.normalized
    || !ArrayBuffer.isView(position.array) || !ArrayBuffer.isView(index.array)
    || geometry.morphAttributes?.position?.length) {
    return null;
  }
  return { position, index, positions: position.array, indices: index.array };
}

// Leaf boxes for segments [fromLeaf * LEAF, segmentCount). A segment three can
// only evaluate to NaN — a non-finite coordinate or an index past the position
// buffer — reads as a hit in three (NaN compares false against the threshold),
// so its leaf becomes the unbounded box that every ray crosses.
function fillLeafBounds(leafBounds, positions, indices, vertexCount, segmentCount, fromLeaf) {
  const leafCount = Math.ceil(segmentCount / EDGE_PICK_LEAF_SEGMENTS);
  const vertexEnd = segmentCount * 2;
  for (let leaf = fromLeaf; leaf < leafCount; leaf += 1) {
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    let unbounded = false;
    const end = Math.min(vertexEnd, (leaf + 1) * EDGE_PICK_LEAF_SEGMENTS * 2);
    // Both endpoints of every segment in the leaf, in index order.
    for (let i = leaf * EDGE_PICK_LEAF_SEGMENTS * 2; i < end; i += 1) {
      const vertex = indices[i];
      if (!(vertex < vertexCount)) {
        unbounded = true;
        continue;
      }
      const x = positions[vertex * 3];
      const y = positions[vertex * 3 + 1];
      const z = positions[vertex * 3 + 2];
      // x - x is 0 exactly when x is finite (NaN and +-Infinity give NaN).
      if (x - x !== 0 || y - y !== 0 || z - z !== 0) {
        unbounded = true;
        continue;
      }
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    }
    const offset = leaf * 6;
    if (unbounded) {
      leafBounds[offset] = leafBounds[offset + 1] = leafBounds[offset + 2] = -Infinity;
      leafBounds[offset + 3] = leafBounds[offset + 4] = leafBounds[offset + 5] = Infinity;
    } else {
      leafBounds[offset] = minX;
      leafBounds[offset + 1] = minY;
      leafBounds[offset + 2] = minZ;
      leafBounds[offset + 3] = maxX;
      leafBounds[offset + 4] = maxY;
      leafBounds[offset + 5] = maxZ;
    }
  }
}

function fillGroupBounds(groupBounds, leafBounds, leafCount, fromGroup) {
  const groupCount = Math.ceil(leafCount / EDGE_PICK_GROUP_LEAVES);
  for (let group = fromGroup; group < groupCount; group += 1) {
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    const leafEnd = Math.min(leafCount, (group + 1) * EDGE_PICK_GROUP_LEAVES);
    for (let leaf = group * EDGE_PICK_GROUP_LEAVES; leaf < leafEnd; leaf += 1) {
      const offset = leaf * 6;
      if (leafBounds[offset] < minX) minX = leafBounds[offset];
      if (leafBounds[offset + 1] < minY) minY = leafBounds[offset + 1];
      if (leafBounds[offset + 2] < minZ) minZ = leafBounds[offset + 2];
      if (leafBounds[offset + 3] > maxX) maxX = leafBounds[offset + 3];
      if (leafBounds[offset + 4] > maxY) maxY = leafBounds[offset + 4];
      if (leafBounds[offset + 5] > maxZ) maxZ = leafBounds[offset + 5];
    }
    const offset = group * 6;
    groupBounds[offset] = minX;
    groupBounds[offset + 1] = minY;
    groupBounds[offset + 2] = minZ;
    groupBounds[offset + 3] = maxX;
    groupBounds[offset + 4] = maxY;
    groupBounds[offset + 5] = maxZ;
  }
}

// The extent of the finite data (for the culling margin's scale). Groups are
// summed where they are finite; a group holding an unbounded leaf is summed
// leaf by leaf, since that leaf says nothing about where the finite data is.
function finiteExtent(groupBounds, groupCount, leafBounds, leafCount) {
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  const include = (bounds, offset) => {
    if (bounds[offset] < minX) minX = bounds[offset];
    if (bounds[offset + 1] < minY) minY = bounds[offset + 1];
    if (bounds[offset + 2] < minZ) minZ = bounds[offset + 2];
    if (bounds[offset + 3] > maxX) maxX = bounds[offset + 3];
    if (bounds[offset + 4] > maxY) maxY = bounds[offset + 4];
    if (bounds[offset + 5] > maxZ) maxZ = bounds[offset + 5];
  };
  for (let group = 0; group < groupCount; group += 1) {
    const offset = group * 6;
    if (groupBounds[offset] !== -Infinity) {
      include(groupBounds, offset);
      continue;
    }
    const leafEnd = Math.min(leafCount, (group + 1) * EDGE_PICK_GROUP_LEAVES);
    for (let leaf = group * EDGE_PICK_GROUP_LEAVES; leaf < leafEnd; leaf += 1) {
      if (leafBounds[leaf * 6] !== -Infinity) include(leafBounds, leaf * 6);
    }
  }
  if (!(minX <= maxX)) {
    return { centerX: 0, centerY: 0, centerZ: 0, radius: 0 };
  }
  return {
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
    centerZ: (minZ + maxZ) / 2,
    radius: Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) / 2,
  };
}

// Builds the box table for a geometry's segments. `prior` is a table whose
// source segments are a verified prefix of these: its complete leaves and
// groups are copied, and only the rest is computed.
function buildTable(source, prior = null) {
  const { position, index, positions, indices } = source;
  const segmentCount = segmentCountOf(index);
  const vertexCount = position.count;
  const leafCount = Math.ceil(segmentCount / EDGE_PICK_LEAF_SEGMENTS);
  const groupCount = Math.ceil(leafCount / EDGE_PICK_GROUP_LEAVES);
  const leafBounds = new Float32Array(leafCount * 6);
  const groupBounds = new Float32Array(groupCount * 6);
  let fromLeaf = 0;
  let fromGroup = 0;
  if (prior) {
    fromLeaf = Math.min(leafCount, Math.floor(prior.segmentCount / EDGE_PICK_LEAF_SEGMENTS));
    fromGroup = Math.floor(fromLeaf / EDGE_PICK_GROUP_LEAVES);
    leafBounds.set(prior.leafBounds.subarray(0, fromLeaf * 6));
    groupBounds.set(prior.groupBounds.subarray(0, fromGroup * 6));
  }
  fillLeafBounds(leafBounds, positions, indices, vertexCount, segmentCount, fromLeaf);
  fillGroupBounds(groupBounds, leafBounds, leafCount, fromGroup);
  return {
    positions,
    indices,
    position,
    positionVersion: position.version,
    index,
    indexVersion: index.version,
    vertexCount,
    segmentCount,
    leafCount,
    groupCount,
    leafBounds,
    groupBounds,
    ...finiteExtent(groupBounds, groupCount, leafBounds, leafCount),
    reusedSegments: fromLeaf * EDGE_PICK_LEAF_SEGMENTS,
  };
}

function tableMatches(table, source) {
  if (!table || table.indices !== source.indices || table.vertexCount !== source.position.count
    || table.segmentCount !== segmentCountOf(source.index)) {
    return false;
  }
  // The same attribute written through three's API bumps its version.
  if (table.position === source.position && table.positionVersion !== source.position.version) return false;
  if (table.index === source.index && table.indexVersion !== source.index.version) return false;
  return true;
}

function edgeTableForGeometry(geometry) {
  const source = tableSource(geometry);
  if (!source) return null;
  let table = tables.get(source.positions);
  if (!tableMatches(table, source)) {
    table = buildTable(source);
    tables.set(source.positions, table);
  }
  return table;
}

function bitwiseEqual(a, b, length) {
  if (length === 0) return true;
  if (a.BYTES_PER_ELEMENT !== b.BYTES_PER_ELEMENT) return false;
  const bytes = length * a.BYTES_PER_ELEMENT;
  // Compare raw words: exact for floats (no NaN/-0 folding), and a mismatch
  // only costs a rebuild.
  const wordSize = bytes % 4 === 0 && a.byteOffset % 4 === 0 && b.byteOffset % 4 === 0 ? 4 : 1;
  const View = wordSize === 4 ? Uint32Array : Uint8Array;
  const left = new View(a.buffer, a.byteOffset, bytes / wordSize);
  const right = new View(b.buffer, b.byteOffset, bytes / wordSize);
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

// Carries a built box table across a selector sync. When the new pick geometry
// wraps the same arrays, the table is simply shared. When its segments extend
// the previous geometry's (topology for more parts appended to the composed
// proxy: every earlier position and index unchanged), the previous boxes are
// kept and only the appended segments are boxed. Anything else — a pose moved
// the proxy, parts were removed — leaves the new geometry to build its table on
// its first edge ray. Nothing is carried when the previous geometry was never
// raycast, so this costs nothing unless edges are being picked.
export function adoptEdgePickTable(geometry, previousGeometry) {
  const source = tableSource(geometry);
  const previousSource = tableSource(previousGeometry);
  if (!source || !previousSource) return false;
  const previous = tables.get(previousSource.positions);
  if (!tableMatches(previous, previousSource)) return false;
  if (tableMatches(tables.get(source.positions), source)) return true;
  const segmentCount = segmentCountOf(source.index);
  if (segmentCount < previous.segmentCount || source.position.count < previous.vertexCount) return false;
  if (!bitwiseEqual(source.indices, previous.indices, previous.segmentCount * 2)) return false;
  if (!bitwiseEqual(source.positions, previous.positions, previous.vertexCount * 3)) return false;
  tables.set(source.positions, buildTable(source, previous));
  return true;
}

// For tests and benches: the table the next ray would use (built if needed).
export function edgePickTable(geometry) {
  return edgeTableForGeometry(geometry);
}

// The segment ranges [start, end) whose boxes pass within `margin` of the
// (local) ray, merged where adjacent: groups, then leaves, then each segment's
// own box (read straight from the buffers — far cheaper than three's segment
// test, which then runs only on these). Returns null when every segment is a
// candidate, so the caller runs one ordinary scan.
function candidateSegmentRanges(table, ray, margin) {
  const { origin, direction } = ray;
  const ox = origin.x, oy = origin.y, oz = origin.z;
  const dx = direction.x, dy = direction.y, dz = direction.z;
  const ix = 1 / dx, iy = 1 / dy, iz = 1 / dz;
  const { leafBounds, groupBounds, groupCount, leafCount, segmentCount, positions, indices, vertexCount } = table;

  // Slab test of the half-line t >= 0 against a box grown by `margin`. An axis
  // the ray does not move along constrains nothing but the origin's slab.
  const crosses = (minX, minY, minZ, maxX, maxY, maxZ) => {
    let tMin = 0;
    let tMax = Infinity;
    minX -= margin; minY -= margin; minZ -= margin;
    maxX += margin; maxY += margin; maxZ += margin;
    if (dx === 0) {
      if (ox < minX || ox > maxX) return false;
    } else {
      const t1 = (minX - ox) * ix, t2 = (maxX - ox) * ix;
      tMin = Math.max(tMin, Math.min(t1, t2));
      tMax = Math.min(tMax, Math.max(t1, t2));
    }
    if (dy === 0) {
      if (oy < minY || oy > maxY) return false;
    } else {
      const t1 = (minY - oy) * iy, t2 = (maxY - oy) * iy;
      tMin = Math.max(tMin, Math.min(t1, t2));
      tMax = Math.min(tMax, Math.max(t1, t2));
    }
    if (dz === 0) {
      if (oz < minZ || oz > maxZ) return false;
    } else {
      const t1 = (minZ - oz) * iz, t2 = (maxZ - oz) * iz;
      tMin = Math.max(tMin, Math.min(t1, t2));
      tMax = Math.min(tMax, Math.max(t1, t2));
    }
    // NaN (an unbounded box meeting a zero-width slab product) keeps the box.
    return !(tMax < tMin);
  };
  const crossesBox = (bounds, offset) => crosses(
    bounds[offset], bounds[offset + 1], bounds[offset + 2],
    bounds[offset + 3], bounds[offset + 4], bounds[offset + 5],
  );
  // A segment three can only evaluate to NaN is always a candidate.
  const crossesSegment = (segment) => {
    const a = indices[segment * 2];
    const b = indices[segment * 2 + 1];
    if (!(a < vertexCount && b < vertexCount)) return true;
    const ax = positions[a * 3], ay = positions[a * 3 + 1], az = positions[a * 3 + 2];
    const bx = positions[b * 3], by = positions[b * 3 + 1], bz = positions[b * 3 + 2];
    if (ax - ax !== 0 || ay - ay !== 0 || az - az !== 0 || bx - bx !== 0 || by - by !== 0 || bz - bz !== 0) return true;
    return crosses(
      ax < bx ? ax : bx, ay < by ? ay : by, az < bz ? az : bz,
      ax < bx ? bx : ax, ay < by ? by : ay, az < bz ? bz : az,
    );
  };

  const ranges = [];
  let runStart = -1;
  let runEnd = -1;
  for (let group = 0; group < groupCount; group += 1) {
    if (!crossesBox(groupBounds, group * 6)) continue;
    const leafEnd = Math.min(leafCount, (group + 1) * EDGE_PICK_GROUP_LEAVES);
    for (let leaf = group * EDGE_PICK_GROUP_LEAVES; leaf < leafEnd; leaf += 1) {
      if (!crossesBox(leafBounds, leaf * 6)) continue;
      const segmentEnd = Math.min(segmentCount, (leaf + 1) * EDGE_PICK_LEAF_SEGMENTS);
      for (let segment = leaf * EDGE_PICK_LEAF_SEGMENTS; segment < segmentEnd; segment += 1) {
        if (!crossesSegment(segment)) continue;
        if (segment === runEnd) {
          runEnd = segment + 1;
        } else {
          if (runStart >= 0) ranges.push(runStart, runEnd);
          runStart = segment;
          runEnd = segment + 1;
        }
      }
    }
  }
  if (runStart >= 0) ranges.push(runStart, runEnd);
  if (ranges.length === 2 && ranges[0] === 0 && ranges[1] === segmentCount) return null;
  return ranges;
}

function raycastEdgePickLines(raycaster, intersects) {
  const baseRaycast = baseRaycasts.get(this);
  const geometry = this.geometry;
  const table = edgeTableForGeometry(geometry);
  const drawRange = geometry?.drawRange;
  const threshold = raycaster?.params?.Line?.threshold;
  const scale = (this.scale.x + this.scale.y + this.scale.z) / 3;
  // The same local threshold three derives; its square is what three compares.
  const localThreshold = Math.abs(threshold / scale);
  if (!table || !table.segmentCount || !drawRange || drawRange.start !== 0
    || drawRange.count < geometry.index.count || !Number.isFinite(localThreshold)) {
    return baseRaycast.call(this, raycaster, intersects);
  }
  inverseWorld.copy(this.matrixWorld).invert();
  localRay.copy(raycaster.ray).applyMatrix4(inverseWorld);
  const { origin, direction } = localRay;
  if (![origin.x, origin.y, origin.z, direction.x, direction.y, direction.z].every(Number.isFinite)) {
    return baseRaycast.call(this, raycaster, intersects);
  }
  const reach = Math.hypot(origin.x - table.centerX, origin.y - table.centerY, origin.z - table.centerZ) + table.radius;
  const margin = localThreshold + CULL_MARGIN_RELATIVE * reach + Number.MIN_VALUE;
  const ranges = candidateSegmentRanges(table, localRay, margin);
  if (!ranges) {
    return baseRaycast.call(this, raycaster, intersects);
  }
  if (!ranges.length) return;
  const { start: drawStart, count: drawCount } = drawRange;
  try {
    for (let i = 0; i < ranges.length; i += 2) {
      drawRange.start = ranges[i] * 2;
      drawRange.count = (ranges[i + 1] - ranges[i]) * 2;
      baseRaycast.call(this, raycaster, intersects);
    }
  } finally {
    drawRange.start = drawStart;
    drawRange.count = drawCount;
  }
}

// Installs culled raycasting on an edge-pick LineSegments. Safe on anything:
// a geometry the table cannot describe falls back to three's full scan.
export function attachEdgePickRaycast(lines) {
  if (!lines?.isLineSegments || baseRaycasts.has(lines)) return lines;
  baseRaycasts.set(lines, lines.raycast);
  lines.raycast = raycastEdgePickLines;
  return lines;
}
