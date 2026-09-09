/**
 * The render-time transform for a DXF preview: thickness, then fold.
 *
 * The baked GLB is a prism at the reference thickness (previewGlb.js), lying flat in CAD
 * Z-up. Everything a drawing's settings do to it is this one vertex transform:
 *
 *   1. scale Z — thickness. Exact, because a flat pattern is a profile swept perpendicular:
 *      walls move, caps and holes are untouched in XY.
 *   2. accordion fold — each bend rotates every vertex on its MOVING side, accumulating
 *      through the chain of bends between that vertex and the sheet's anchored region, each
 *      bend by ITS OWN angle. Geometry past a bend is rigid; only its placement changes, so
 *      nothing is re-meshed and every angle can ride a slider.
 *   3. miter — vertices ON a crease belong to both strips at once. Left in place they
 *      stretch the wall from thin to thick around the bend (the "fan"); the sharp-bend
 *      geometry that keeps thickness constant is the miter, which moves a crease vertex
 *      onto the bend's bisector at offset z/cos(θ/2) — the intersection of the two cap
 *      planes.
 *
 * Bend lines are ARBITRARY 2D segments in the flat pattern — any orientation, as long as
 * they do not cross one another inside the sheet. Which side of a line moves is a fixed
 * convention (below), and the vertical-line special case reproduces the historical
 * "everything right of the axis folds" behavior exactly.
 *
 * ORDER is the correctness condition. Folding first and thickness-scaling after (as a group
 * scale) flattens every folded-up flange back into the sheet plane — at 0 mm the fold
 * becomes invisible, which is exactly the bug this module replaced.
 *
 * Pure functions over arrays, deliberately: they run identically in the viewer and in the
 * headless snapshot runtime, and they are testable in node without a scene.
 */

/**
 * The Z scale a zero-thickness drawing renders at. A true 0 collapses top and bottom caps
 * onto one plane (z-fighting) and degenerates normals; a hair keeps the solid valid while
 * reading as a flat face at any sane zoom.
 */
export const DXF_FLAT_THICKNESS_SCALE = 1e-3;

/**
 * How close to a bend line a vertex must sit (mm, flat frame) to count as ON the crease and
 * take the miter. The bake splits strips exactly at the lines and quantization moves
 * vertices by ~0.005 mm, so 0.05 mm is an order of magnitude of slack without capturing
 * real feature geometry near a bend.
 */
export const DXF_MITER_EPSILON_MM = 0.05;

/**
 * The miter factor 1/cos(θ/2) diverges as a bend approaches 180° (the cap planes go
 * parallel). Clamped at the 150° value: past that the sheet is folding onto itself and a
 * finite corner reads better than geometry racing to infinity.
 */
const MITER_FACTOR_MAX = 1 / Math.cos((150 / 2) * (Math.PI / 180));

const SIDE_EPSILON_MM = 1e-6;

// --- small 3D helpers (no three.js: this must run in bare node) -----------------------

/** Rodrigues rotation of vector v about UNIT axis a by the angle whose cos/sin are given. */
function rotateVector(v, a, cos, sin) {
  const cross = [
    a[1] * v[2] - a[2] * v[1],
    a[2] * v[0] - a[0] * v[2],
    a[0] * v[1] - a[1] * v[0]
  ];
  const dot = a[0] * v[0] + a[1] * v[1] + a[2] * v[2];
  const k = dot * (1 - cos);
  return [
    v[0] * cos + cross[0] * sin + a[0] * k,
    v[1] * cos + cross[1] * sin + a[1] * k,
    v[2] * cos + cross[2] * sin + a[2] * k
  ];
}

function rotateAroundLine(point, linePoint, axis, cos, sin) {
  const rotated = rotateVector(
    [point[0] - linePoint[0], point[1] - linePoint[1], point[2] - linePoint[2]],
    axis,
    cos,
    sin
  );
  return [rotated[0] + linePoint[0], rotated[1] + linePoint[1], rotated[2] + linePoint[2]];
}

// --- bend-line normalization ----------------------------------------------------------

/**
 * Which side of a bend line MOVES. The line's in-plane unit normal is oriented by a fixed
 * convention — pointing +X when it can, +Y when it is X-neutral — and the positive side is
 * the moving one. For a vertical bend line that makes the moving side "right of the axis",
 * which is the historical behavior every existing drawing was authored against; the fixed
 * (anchored) region is the one at the sheet's lower-left.
 */
function orientNormal(nx, ny) {
  if (nx < -SIDE_EPSILON_MM || (Math.abs(nx) <= SIDE_EPSILON_MM && ny < 0)) {
    return [-nx, -ny];
  }
  return [nx, ny];
}

function bendFromSegment(segment, angle) {
  const start = [Number(segment?.start?.[0]) || 0, Number(segment?.start?.[1]) || 0];
  const end = [Number(segment?.end?.[0]) || 0, Number(segment?.end?.[1]) || 0];
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const length = Math.hypot(dx, dy);
  if (!(length > SIDE_EPSILON_MM)) {
    return null;
  }
  const u = [dx / length, dy / length];
  const n = orientNormal(-u[1], u[0]);
  return {
    p: start,
    mid: [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
    n,
    seg: [start, end],
    angle: Number.isFinite(angle) ? angle : 0
  };
}

function bendFromAxisX(axisX, angle) {
  return {
    p: [axisX, 0],
    mid: [axisX, 0],
    n: [1, 0],
    seg: null,
    angle: Number.isFinite(angle) ? angle : 0
  };
}

function signedSide(bend, x, y) {
  return bend.n[0] * (x - bend.p[0]) + bend.n[1] * (y - bend.p[1]);
}

export function normalizeDxfFoldOptions({
  bendAxesX = null,
  bendLines = null,
  bendAnglesRad = null,
  thicknessScale = 1,
  miterEpsilon = DXF_MITER_EPSILON_MM
} = {}) {
  const angles = Array.isArray(bendAnglesRad) ? bendAnglesRad : [];
  let bends = [];
  if (Array.isArray(bendLines) && bendLines.length) {
    bends = bendLines
      .map((segment, index) => bendFromSegment(segment, angles[index]))
      .filter(Boolean);
  } else if (Array.isArray(bendAxesX)) {
    bends = bendAxesX
      .filter((axisX) => Number.isFinite(axisX))
      .map((axisX, index) => bendFromAxisX(axisX, angles[index]));
  }

  // Dependency order: a bend applies AFTER every bend between it and the anchored region —
  // i.e. after each bend whose moving side contains it. With non-crossing lines "how many
  // bends is it behind" is a well-defined depth, and for parallel vertical lines it
  // reproduces the historical left-to-right order (ties keep input order, so axis/angle
  // pairs never separate).
  const depths = bends.map((bend) => bends.reduce(
    (count, other) => (other !== bend && signedSide(other, bend.mid[0], bend.mid[1]) > SIDE_EPSILON_MM
      ? count + 1
      : count),
    0
  ));
  bends = bends
    .map((bend, index) => ({ bend, index, depth: depths[index] }))
    .sort((a, b) => (a.depth - b.depth) || (a.index - b.index))
    .map((entry) => entry.bend);

  const requestedScale = Number.isFinite(thicknessScale) ? thicknessScale : 1;
  const scale = Math.max(requestedScale, DXF_FLAT_THICKNESS_SCALE);
  const anyAngle = bends.some((bend) => bend.angle !== 0);
  const pivots = anyAngle ? computeFoldPivots(bends) : [];
  return { bends, scale, anyAngle, pivots, miterEpsilon };
}

/**
 * Each bend rotates about its axis's CURRENT position — the image of the flat line under
 * every earlier fold that carries it — not its flat one. Deciding membership by the folded
 * position instead (the obvious shortcut) under-folds a chain: after the first 90° fold the
 * second axis's strip has moved, so it never receives its second rotation and a U-channel
 * folds into an L. Pivots are precomputed once per option set.
 *
 * The rotation axis direction is n × ẑ (in the flat frame), which is what makes a POSITIVE
 * angle tilt the moving side toward +Z ("up") for every line orientation.
 */
function computeFoldPivots(bends) {
  const pivots = [];
  for (const bend of bends) {
    let p3 = [bend.p[0], bend.p[1], 0];
    let a3 = [bend.n[1], -bend.n[0], 0];
    for (const pivot of pivots) {
      if (signedSide(pivot.bend, bend.mid[0], bend.mid[1]) > SIDE_EPSILON_MM && pivot.rotates) {
        p3 = rotateAroundLine(p3, pivot.p3, pivot.a3, pivot.cos, pivot.sin);
        a3 = rotateVector(a3, pivot.a3, pivot.cos, pivot.sin);
      }
    }
    pivots.push({
      bend,
      p3,
      a3,
      angle: bend.angle,
      cos: Math.cos(bend.angle),
      sin: Math.sin(bend.angle),
      halfCos: Math.cos(bend.angle / 2),
      halfSin: Math.sin(bend.angle / 2),
      rotates: bend.angle !== 0
    });
  }
  return pivots;
}

/** True when the transform would change nothing — the caller's "is there work" gate. */
export function dxfFoldIsIdentity(options) {
  const { scale, anyAngle } = normalizeDxfFoldOptions(options);
  return scale === 1 && !anyAngle;
}

/**
 * The fold image of a FLAT-plane location (z = 0) plus the sheet normal there, through the
 * pivots strictly before `uptoIndex`. What the miter needs: where its crease foot ended up
 * and which way the approaching strip faces.
 */
function transformFlatFrame(x, y, uptoIndex, pivots) {
  let point = [x, y, 0];
  let normal = [0, 0, 1];
  for (let index = 0; index < uptoIndex; index += 1) {
    const pivot = pivots[index];
    if (!pivot.rotates) {
      continue;
    }
    if (signedSide(pivot.bend, x, y) > SIDE_EPSILON_MM) {
      point = rotateAroundLine(point, pivot.p3, pivot.a3, pivot.cos, pivot.sin);
      normal = rotateVector(normal, pivot.a3, pivot.cos, pivot.sin);
    }
  }
  return { point, normal };
}

/**
 * Transform one CAD-space point. Membership is decided in the FLAT frame — where the vertex
 * sits in the unfolded pattern — never by where earlier folds have moved it. Exported for
 * the overlays (guides, scores, text anchors), which must ride the SAME chain the sheet
 * folds through or they detach from their creases.
 */
export function foldDxfPoint(x, y, z, { scale, anyAngle, pivots, miterEpsilon }) {
  let position = [x, y, z * scale];
  if (!anyAngle) {
    return position;
  }
  for (let index = 0; index < pivots.length; index += 1) {
    const pivot = pivots[index];
    const side = signedSide(pivot.bend, x, y);
    if (side < -miterEpsilon) {
      continue;
    }
    if (side <= miterEpsilon) {
      // ON the crease: the vertex belongs to both strips, so it takes the miter — offset
      // along the bend's bisector, stretched by 1/cos(θ/2), which is where the two
      // constant-thickness cap planes intersect. Without this the wall fans from thin to
      // thick around every bend.
      const foot = [x - pivot.bend.n[0] * side, y - pivot.bend.n[1] * side];
      const frame = transformFlatFrame(foot[0], foot[1], index, pivots);
      const bisector = rotateVector(frame.normal, pivot.a3, pivot.halfCos, pivot.halfSin);
      const factor = Math.min(1 / Math.max(Math.abs(pivot.halfCos), 1e-6), MITER_FACTOR_MAX);
      const offset = z * scale * factor;
      return [
        frame.point[0] + bisector[0] * offset,
        frame.point[1] + bisector[1] * offset,
        frame.point[2] + bisector[2] * offset
      ];
    }
    if (pivot.rotates) {
      position = rotateAroundLine(position, pivot.p3, pivot.a3, pivot.cos, pivot.sin);
    }
  }
  return position;
}

/**
 * Rewrite `output` (a Float32Array-compatible position buffer, xyz-interleaved) from the
 * FLAT positions in `original`. Always transforms from flat, never from the current pose:
 * folding a folded sheet compounds.
 */
export function transformDxfPreviewPositions(original, output, options) {
  const resolved = normalizeDxfFoldOptions(options);
  for (let index = 0; index < original.length; index += 3) {
    const [px, py, pz] = foldDxfPoint(
      original[index],
      original[index + 1],
      original[index + 2],
      resolved
    );
    output[index] = px;
    output[index + 1] = py;
    output[index + 2] = pz;
  }
  return output;
}

/** The bounds facts the guide lines need, scanned once from the flat positions. */
export function dxfFlatPatternExtents(original) {
  let yMin = Infinity;
  let yMax = -Infinity;
  let zMax = 0;
  for (let index = 0; index < original.length; index += 3) {
    const y = original[index + 1];
    const z = Math.abs(original[index + 2]);
    if (y < yMin) yMin = y;
    if (y > yMax) yMax = y;
    if (z > zMax) zMax = z;
  }
  if (!Number.isFinite(yMin)) {
    yMin = 0;
    yMax = 0;
  }
  return { yMin, yMax, zMax };
}

/** How far above the folded top surface a guide line sits, in mm — enough to never
 *  z-fight the face it annotates, small enough to read as ON it. */
export const DXF_BEND_GUIDE_ELEVATION_MM = 0.3;

/**
 * Endpoints for the dotted bend-line overlay, as xyz-interleaved segment pairs, FOLDED
 * through the same chain as the sheet. A bend that arrived as a real segment keeps its own
 * endpoints; one that arrived as a bare axis X spans the sheet's Y extent. Guides sit just
 * above the top surface and ride the miter, so at any angle each lies on the outer corner
 * of its own crease.
 */
export function dxfBendGuideSegments(original, options) {
  const resolved = normalizeDxfFoldOptions(options);
  if (!resolved.bends.length) {
    return new Float32Array(0);
  }
  const { yMin, yMax, zMax } = dxfFlatPatternExtents(original);
  const zTop = zMax + DXF_BEND_GUIDE_ELEVATION_MM / Math.max(resolved.scale, 1e-6);
  const segments = new Float32Array(resolved.bends.length * 6);
  let cursor = 0;
  for (const bend of resolved.bends) {
    const endpoints = bend.seg || [[bend.p[0], yMin], [bend.p[0], yMax]];
    const [ax, ay, az] = foldDxfPoint(endpoints[0][0], endpoints[0][1], zTop, resolved);
    const [bx, by, bz] = foldDxfPoint(endpoints[1][0], endpoints[1][1], zTop, resolved);
    segments[cursor] = ax;
    segments[cursor + 1] = ay;
    segments[cursor + 2] = az;
    segments[cursor + 3] = bx;
    segments[cursor + 4] = by;
    segments[cursor + 5] = bz;
    cursor += 6;
  }
  return segments;
}
