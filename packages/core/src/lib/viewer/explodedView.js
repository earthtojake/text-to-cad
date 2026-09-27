// Exploded view: hierarchical radial layout + evaluator.
//
// One methodology, no knobs — the standard automatic explode used by
// mainstream CAD viewers (SolidWorks auto-explode, Autodesk's hierarchy
// explode), driven by a single 0..1 slider:
//
//   - the occurrence tree is walked top-down, level by level;
//   - at each level every child group moves RADIALLY away from its parent
//     group's center — direction = (child center − parent center) in full 3D,
//     so parts spread into the space they already occupy relative to each
//     other: left parts go left, top parts go up, a bolt circle blooms as a
//     ring. Nothing is serialized onto a single world axis;
//   - distance is the child's assembled offset scaled up plus a size-aware
//     clearance, so the explode reads as an inflated copy of the assembly —
//     neighbors stay neighbors and every gap opens in proportion;
//   - concentric children (center on the parent center: a shaft in a housing)
//     have no radial direction; the largest anchors as the core and the rest
//     telescope out along their own longest axis, fanned when tied;
//   - levels cascade over the 0..1 scrub with overlapping windows, so the
//     slider walks the disassembly: subassemblies separate first, then bloom
//     internally.
//
// The layout is computed from display records ({partId, partBounds, mesh})
// and evaluated to a per-record `record.explodedViewMatrix` — the single
// hand-off contract the renderer, topology edges, snapshot export, and
// zoom-to-part read. THREE is dependency-injected for the matrix writes; the
// layout math itself is pure arrays.

export const EPSILON = 1e-6;
export const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

// How many hierarchy levels explode. Deeper nesting still moves rigidly with
// its level-3 ancestor; more levels than this reads as scatter, not structure.
export const MAX_EXPLODED_VIEW_LEVELS = 3;

// Radial distance = assembled offset × SPREAD + child radius × CLEARANCE.
// SPREAD inflates the arrangement (1.5 ≈ gaps comparable to the parts
// themselves); CLEARANCE gives near-center parts a size-proportional push so
// tight clusters still separate visibly.
const RADIAL_SPREAD = 1.5;
const RADIAL_CLEARANCE = 0.45;
// Deeper levels move proportionally less, keeping subassembly clusters
// visually grouped after they bloom.
const LEVEL_FALLOFF = 0.8;
// A child whose center sits within this fraction of the parent radius from
// the parent center is treated as concentric (no meaningful radial direction).
const CONCENTRIC_THRESHOLD = 0.05;
// Cascade scheduling: fraction of a level's window shared with the next level.
const WINDOW_OVERLAP = 0.5;
// Clearance kept between exploded siblings (fraction of the parent radius),
// and the cap on separation sweeps per node.
const SEPARATION_MARGIN = 0.05;
const MAX_SEPARATION_PASSES = 10;

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function toNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function isFiniteVectorArray(value) {
  return (Array.isArray(value) || ArrayBuffer.isView(value)) && value.length >= 3;
}

// -- occurrence path helpers ------------------------------------------------
// Occurrence ids look like "o1.2.3": the first segment is o<number>, the rest
// are numeric. Non-occurrence part ids (e.g. "part:3") are opaque leaves.

export function occurrenceSegments(partId) {
  const text = String(partId || "").trim();
  const match = text.match(/^o\d+(?:\.\d+)*/i);
  return match ? match[0].split(".").filter(Boolean) : [];
}

// -- bounds helpers ---------------------------------------------------------

export function boundsCenterArray(bounds, fallback = [0, 0, 0]) {
  const min = isFiniteVectorArray(bounds?.min) ? bounds.min : null;
  const max = isFiniteVectorArray(bounds?.max) ? bounds.max : null;
  if (!min || !max) {
    return [...fallback];
  }
  return [
    (toNumber(min[0]) + toNumber(max[0])) / 2,
    (toNumber(min[1]) + toNumber(max[1])) / 2,
    (toNumber(min[2]) + toNumber(max[2])) / 2
  ];
}

export function boundsSize(bounds, axis) {
  const min = isFiniteVectorArray(bounds?.min) ? bounds.min : null;
  const max = isFiniteVectorArray(bounds?.max) ? bounds.max : null;
  if (!min || !max) {
    return 0;
  }
  return Math.max(toNumber(max[axis]) - toNumber(min[axis]), 0);
}

export function boundsRadius(bounds) {
  const x = boundsSize(bounds, 0);
  const y = boundsSize(bounds, 1);
  const z = boundsSize(bounds, 2);
  return Math.sqrt(x * x + y * y + z * z) / 2;
}

export function mergeBounds(boundsList) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let count = 0;
  for (const bounds of Array.isArray(boundsList) ? boundsList : []) {
    if (!isFiniteVectorArray(bounds?.min) || !isFiniteVectorArray(bounds?.max)) {
      continue;
    }
    count += 1;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], toNumber(bounds.min[axis]));
      max[axis] = Math.max(max[axis], toNumber(bounds.max[axis]));
    }
  }
  return count > 0 && min.every(Number.isFinite) && max.every(Number.isFinite)
    ? { min, max }
    : null;
}

export function recordBounds(record) {
  const bounds = record?.partBounds;
  return isFiniteVectorArray(bounds?.min) && isFiniteVectorArray(bounds?.max) ? bounds : null;
}

export function recordCanExplode(record) {
  const partId = String(record?.partId || "").trim();
  return Boolean(record?.mesh && partId && partId !== "__model__");
}

// -- hierarchy --------------------------------------------------------------

// Longest occurrence-path prefix shared by every record, clamped so at least
// one segment is left to distinguish records (an assembly of "o1.1", "o1.2"
// has prefix ["o1"], not ["o1", "1"]).
function commonPrefixLength(segmentLists) {
  const paths = segmentLists.filter((segments) => segments.length > 0);
  if (!paths.length) {
    return 0;
  }
  const shortest = Math.min(...paths.map((segments) => segments.length));
  let length = 0;
  while (length < shortest && paths.every((segments) => segments[length] === paths[0][length])) {
    length += 1;
  }
  return Math.min(length, shortest - 1);
}

// Group node entries by the next occurrence segment. Entries whose path is
// exhausted (the record sits at this node's own path, or has a non-occurrence
// id) become singleton leaf groups keyed by their part id.
function childGroups(entries, depth) {
  const groups = new Map();
  for (const entry of entries) {
    const key = entry.segments.length > depth
      ? entry.segments.slice(0, depth + 1).join(".")
      : entry.partId;
    const group = groups.get(key) || { key, entries: [], depth: entry.segments.length > depth ? depth + 1 : depth };
    group.entries.push(entry);
    groups.set(key, group);
  }
  return [...groups.values()];
}

function buildNode(key, entries, depth, levelsLeft) {
  const bounds = mergeBounds(entries.map((entry) => entry.bounds));
  const node = {
    key,
    entries,
    bounds,
    center: boundsCenterArray(bounds, [0, 0, 0]),
    radius: boundsRadius(bounds),
    order: Math.min(...entries.map((entry) => entry.index)),
    children: []
  };
  if (levelsLeft <= 0 || entries.length < 2) {
    return node;
  }
  // Collapse single-child chains (every record continues through the same
  // segment) so a wrapper occurrence does not burn an explode level.
  let groups = childGroups(entries, depth);
  let nextDepth = depth;
  while (groups.length === 1 && groups[0].depth > nextDepth) {
    nextDepth = groups[0].depth;
    groups = childGroups(entries, nextDepth);
  }
  if (groups.length < 2) {
    return node;
  }
  node.children = groups
    .map((group) => buildNode(group.key, group.entries, group.depth, levelsLeft - 1))
    .sort((left, right) => left.order - right.order);
  return node;
}

// -- layout -----------------------------------------------------------------

function scaleVec(vec, scalar) {
  return [vec[0] * scalar, vec[1] * scalar, vec[2] * scalar];
}

function addVec(a, b) {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function vecLength(vec) {
  return Math.hypot(vec[0], vec[1], vec[2]);
}

// In-plane fan for tied concentric children: golden-angle directions in the
// plane perpendicular to the child's long axis sibling rank.
function fanDirection(axisIndex, rank) {
  const angle = rank * GOLDEN_ANGLE;
  const direction = [0, 0, 0];
  const [a, b] = [0, 1, 2].filter((axis) => axis !== axisIndex);
  direction[a] = Math.cos(angle);
  direction[b] = Math.sin(angle);
  return direction;
}

// Radial displacement for one child about its parent center, or null for the
// anchored core.
function radialVector(node, child, level, concentricRank) {
  const falloff = LEVEL_FALLOFF ** (level - 1);
  const relative = [
    child.center[0] - node.center[0],
    child.center[1] - node.center[1],
    child.center[2] - node.center[2]
  ];
  const distance = Math.hypot(relative[0], relative[1], relative[2]);
  const concentric = distance <= Math.max(node.radius * CONCENTRIC_THRESHOLD, EPSILON);
  if (!concentric) {
    const direction = scaleVec(relative, 1 / distance);
    const magnitude = (distance * RADIAL_SPREAD + child.radius * RADIAL_CLEARANCE) * falloff;
    return scaleVec(direction, magnitude);
  }
  if (concentricRank.count === 0) {
    concentricRank.count += 1;
    return null; // largest concentric child anchors as the core
  }
  const rank = concentricRank.count;
  concentricRank.count += 1;
  // Telescope along the child's own longest axis; alternate sides and stagger
  // distances so successive concentric parts clear each other and the core.
  const extents = [boundsSize(child.bounds, 0), boundsSize(child.bounds, 1), boundsSize(child.bounds, 2)];
  const axisIndex = extents.indexOf(Math.max(...extents));
  const nodeExtent = boundsSize(node.bounds, axisIndex);
  const sign = rank % 2 === 1 ? 1 : -1;
  const step = Math.ceil(rank / 2);
  const magnitude = (nodeExtent + extents[axisIndex]) * 0.55 * step * (LEVEL_FALLOFF ** (level - 1));
  if (magnitude <= EPSILON) {
    return scaleVec(fanDirection(axisIndex, rank), Math.max(child.radius, EPSILON));
  }
  const direction = [0, 0, 0];
  direction[axisIndex] = sign;
  return scaleVec(direction, magnitude);
}

function shiftedBoundsByVector(bounds, vector) {
  if (!vector) {
    return bounds;
  }
  return {
    min: [
      toNumber(bounds.min[0]) + vector[0],
      toNumber(bounds.min[1]) + vector[1],
      toNumber(bounds.min[2]) + vector[2]
    ],
    max: [
      toNumber(bounds.max[0]) + vector[0],
      toNumber(bounds.max[1]) + vector[1],
      toNumber(bounds.max[2]) + vector[2]
    ]
  };
}

// Per-axis positive overlap extents between two AABBs, or null when disjoint.
function overlapExtents(a, b) {
  const extents = [];
  for (let axis = 0; axis < 3; axis += 1) {
    const overlap = Math.min(toNumber(a.max[axis]), toNumber(b.max[axis]))
      - Math.max(toNumber(a.min[axis]), toNumber(b.min[axis]));
    if (overlap <= 0) {
      return null;
    }
    extents.push(overlap);
  }
  return extents;
}

// Collision relief: proportional radial distances alone cannot guarantee
// clearance (two large parts with nearby centers barely separate), so sweep
// the siblings and push any still-intersecting mover further OUT along its own
// explode direction until every pair clears with a margin — the interval
// stacking CAD auto-explode performs. An anchored core never moves; pushes
// stay on the mover's ray, so the layout remains radial.
function relaxSiblingOverlaps(node, vectorByChild) {
  const children = node.children;
  if (children.length < 2) {
    return;
  }
  const gap = Math.max(node.radius * SEPARATION_MARGIN, EPSILON);
  for (let pass = 0; pass < MAX_SEPARATION_PASSES; pass += 1) {
    let pushed = false;
    for (let i = 0; i < children.length; i += 1) {
      for (let j = i + 1; j < children.length; j += 1) {
        const a = children[i];
        const b = children[j];
        const va = vectorByChild.get(a) || null;
        const vb = vectorByChild.get(b) || null;
        if (!va && !vb) {
          continue;
        }
        const overlap = overlapExtents(
          shiftedBoundsByVector(a.bounds, va),
          shiftedBoundsByVector(b.bounds, vb)
        );
        if (!overlap) {
          continue;
        }
        // Push the outer mover (the core, when involved, always stays).
        const target = !va ? b : (!vb ? a : (vecLength(va) >= vecLength(vb) ? a : b));
        const vector = vectorByChild.get(target);
        const length = vecLength(vector);
        if (length <= EPSILON) {
          continue;
        }
        const unit = scaleVec(vector, 1 / length);
        // Travel needed to clear the overlap along the mover's own ray: the
        // cheapest axis whose direction component is significant.
        let travel = Infinity;
        for (let axis = 0; axis < 3; axis += 1) {
          if (Math.abs(unit[axis]) > 0.25) {
            travel = Math.min(travel, (overlap[axis] + gap) / Math.abs(unit[axis]));
          }
        }
        if (!Number.isFinite(travel)) {
          continue;
        }
        vectorByChild.set(target, addVec(vector, scaleVec(unit, travel)));
        pushed = true;
      }
    }
    if (!pushed) {
      return;
    }
  }
}

// Overlapping cascade windows: level i of L animates over its own slice of the
// 0..1 scrub, sharing WINDOW_OVERLAP of it with the next level. One level
// spans the whole scrub.
function levelWindows(levelCount) {
  if (levelCount <= 1) {
    return [[0, 1]];
  }
  const span = 1 / (1 + (levelCount - 1) * (1 - WINDOW_OVERLAP));
  return Array.from({ length: levelCount }, (_, index) => {
    const start = index * span * (1 - WINDOW_OVERLAP);
    return [start, Math.min(start + span, 1)];
  });
}

// Compute the exploded-view layout for a set of display records.
// Returns { entries, records, levelCount }:
//   - entries: per moved record, the contribution list [{ vector, window }]
//     scheduled by level windows;
//   - records: every explodable record (moved or not), for clearing.
export function computeExplodedViewLayout(records = [], modelBounds = null) {
  const explodable = (Array.isArray(records) ? records : []).filter(recordCanExplode);
  const empty = { entries: [], records: explodable, levelCount: 0 };
  if (explodable.length < 2) {
    return empty;
  }
  const nodeEntries = explodable
    .map((record, index) => ({
      record,
      index,
      partId: String(record.partId || "").trim(),
      segments: occurrenceSegments(record.partId),
      bounds: recordBounds(record)
    }))
    .filter((entry) => entry.bounds);
  if (nodeEntries.length < 2) {
    return empty;
  }

  const prefixLength = commonPrefixLength(nodeEntries.map((entry) => entry.segments));
  const root = buildNode("", nodeEntries, prefixLength, MAX_EXPLODED_VIEW_LEVELS);
  if (!root.children.length) {
    return empty;
  }
  if (modelBounds && isFiniteVectorArray(modelBounds.min) && isFiniteVectorArray(modelBounds.max)) {
    // Prefer the true model bounds for the root so the top-level bloom radiates
    // from the same center the viewer frames.
    root.bounds = modelBounds;
    root.center = boundsCenterArray(modelBounds, root.center);
    root.radius = boundsRadius(modelBounds);
  }

  // Walk the tree breadth-first, collecting one radial contribution per moved
  // child group per level.
  const contributionsByRecord = new Map();
  let levelCount = 0;
  const queue = [{ node: root, level: 1 }];
  while (queue.length) {
    const { node, level } = queue.shift();
    const concentricRank = { count: 0 };
    // Rank concentric children by size so the largest anchors as the core.
    const children = [...node.children].sort((left, right) => right.radius - left.radius);
    const vectorByChild = new Map();
    for (const child of children) {
      vectorByChild.set(child, radialVector(node, child, level, concentricRank));
    }
    relaxSiblingOverlaps(node, vectorByChild);
    for (const child of node.children) {
      const vector = vectorByChild.get(child);
      if (vector) {
        levelCount = Math.max(levelCount, level);
        for (const entry of child.entries) {
          const list = contributionsByRecord.get(entry.record) || [];
          list.push({ vector, level });
          contributionsByRecord.set(entry.record, list);
        }
      }
      if (child.children.length) {
        queue.push({ node: child, level: level + 1 });
      }
    }
  }

  if (!levelCount) {
    return empty;
  }
  const windows = levelWindows(levelCount);
  const windowForLevel = (level) => windows[Math.min(level, levelCount) - 1];
  const entries = [];
  for (const [record, contributions] of contributionsByRecord) {
    entries.push({
      record,
      partId: String(record.partId || "").trim(),
      contributions: contributions.map((contribution) => ({
        vector: contribution.vector,
        window: windowForLevel(contribution.level)
      }))
    });
  }
  return { entries, records: explodable, levelCount };
}

// -- evaluation -------------------------------------------------------------

// Local progress of one contribution at a global 0..1 scrub position:
// linear ramp inside the contribution's window, smoothstepped so each cascade
// stage starts and lands softly.
function contributionProgress(window, progress) {
  const t0 = window?.[0] ?? 0;
  const t1 = window?.[1] ?? 1;
  const t = clamp((clamp(toNumber(progress), 0, 1) - t0) / Math.max(t1 - t0, EPSILON), 0, 1);
  return t * t * (3 - 2 * t);
}

function entryOffset(entry, progress) {
  const offset = [0, 0, 0];
  for (const contribution of entry?.contributions || []) {
    const local = contributionProgress(contribution.window, progress);
    if (local <= EPSILON) {
      continue;
    }
    offset[0] += contribution.vector[0] * local;
    offset[1] += contribution.vector[1] * local;
    offset[2] += contribution.vector[2] * local;
  }
  return offset;
}

// Write record.explodedViewMatrix for every explodable record at `progress`.
// Records with no active offset are explicitly cleared to null so stale
// offsets never persist (the matrix is the sole downstream contract).
export function applyExplodedViewProgress(THREE, layout, progress = 1) {
  if (!THREE?.Matrix4 || !layout) {
    return;
  }
  const moved = new Set();
  for (const entry of layout.entries || []) {
    const record = entry?.record;
    if (!record) {
      continue;
    }
    const offset = entryOffset(entry, progress);
    record.explodedViewMatrix = Math.hypot(offset[0], offset[1], offset[2]) > EPSILON
      ? new THREE.Matrix4().makeTranslation(offset[0], offset[1], offset[2])
      : null;
    moved.add(record);
  }
  for (const record of layout.records || []) {
    if (record && !moved.has(record)) {
      record.explodedViewMatrix = null;
    }
  }
}

export function clearExplodedViewRecords(records = []) {
  for (const record of Array.isArray(records) ? records : []) {
    if (record) {
      record.explodedViewMatrix = null;
    }
  }
}

// Bounds of the assembly at a given scrub progress, for auto-framing. Offsets
// are pure translations, so each moved record's bounds just shift.
export function explodedViewBounds(layout, fallbackBounds = null, progress = 1) {
  if (!layout?.records?.length) {
    return fallbackBounds;
  }
  const offsetByRecord = new Map();
  for (const entry of layout.entries || []) {
    offsetByRecord.set(entry.record, entryOffset(entry, progress));
  }
  const boundsList = [];
  for (const record of layout.records) {
    const bounds = recordBounds(record);
    if (!bounds) {
      continue;
    }
    const offset = offsetByRecord.get(record) || [0, 0, 0];
    boundsList.push({
      min: [
        toNumber(bounds.min[0]) + offset[0],
        toNumber(bounds.min[1]) + offset[1],
        toNumber(bounds.min[2]) + offset[2]
      ],
      max: [
        toNumber(bounds.max[0]) + offset[0],
        toNumber(bounds.max[1]) + offset[1],
        toNumber(bounds.max[2]) + offset[2]
      ]
    });
  }
  return mergeBounds(boundsList) || fallbackBounds;
}

export function easeExplodedViewProgress(value) {
  const amount = clamp(toNumber(value), 0, 1);
  return 1 - (1 - amount) ** 3;
}
