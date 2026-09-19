/** Folding a flat pattern along fold lines of ANY orientation.
 *
 * The older decomposition sliced the blank into vertical X-slabs, one per bend, and folded
 * each slab about the previous bend. That only describes a part whose bends are all parallel
 * to the Y axis: a bend at any other angle became a phantom vertical line, and a bend that did
 * not cross the whole blank rotated material it does not separate. This module replaces the
 * slab model with the thing a brake actually does:
 *
 *   1. every fold line cuts the blank in two, so N fold lines cut it into REGIONS;
 *   2. regions that a fold separates are hinged to each other, giving a TREE;
 *   3. one region stays put (the root) and every other region's placement is the product of
 *      the hinges on its path back to the root.
 *
 * The geometry lives in the flat pattern's own 2D coordinates (DXF x/y). The mesher maps them
 * to the XZ plane with Y as thickness, so a fold rotates about an in-plane axis and lifts
 * material out of the plane -- see foldHingeMatrix.
 */

import { Matrix4, Vector3 } from "three";

const EPSILON_MM = 1e-6;
/** How far a point may sit past a fold's band edge and still count as on the band. */
const BAND_TOLERANCE_MM = 1e-4;
/** Regions smaller than this are clipping slivers, not faces of the part. */
const MIN_REGION_AREA_MM2 = 1e-4;

function polygonArea(loop) {
  let area = 0;
  for (let index = 0; index < loop.length; index += 1) {
    const [x1, y1] = loop[index];
    const [x2, y2] = loop[(index + 1) % loop.length];
    area += (x1 * y2) - (x2 * y1);
  }
  return area / 2;
}

export function polygonAbsArea(loop) {
  return Math.abs(polygonArea(loop));
}

function loopCentroid(loop) {
  const area = polygonArea(loop);
  if (Math.abs(area) <= EPSILON_MM) {
    const sum = loop.reduce((acc, [x, y]) => [acc[0] + x, acc[1] + y], [0, 0]);
    return [sum[0] / loop.length, sum[1] / loop.length];
  }
  let cx = 0;
  let cy = 0;
  for (let index = 0; index < loop.length; index += 1) {
    const [x1, y1] = loop[index];
    const [x2, y2] = loop[(index + 1) % loop.length];
    const cross = (x1 * y2) - (x2 * y1);
    cx += (x1 + x2) * cross;
    cy += (y1 + y2) * cross;
  }
  return [cx / (6 * area), cy / (6 * area)];
}

/** Signed distance from the fold line, positive on the fold's normal side. */
export function foldSignedDistance(foldLine, point) {
  return ((point[0] - foldLine.origin[0]) * foldLine.normal[0])
    + ((point[1] - foldLine.origin[1]) * foldLine.normal[1]);
}

/** The part of ``loop`` on one side of a fold's band, as a closed loop (possibly empty).
 *
 * Sutherland-Hodgman against the half-plane ``signedDistance >= limit`` (or <=, mirrored by
 * ``keepPositiveSide``). Convex clipping of a possibly-concave polygon against a HALF-PLANE is
 * exact -- the classic Sutherland-Hodgman caveat is convex CLIP REGIONS with several edges,
 * where concave subjects can gain degenerate bridges. One half-plane cannot do that.
 */
export function foldAlongCoordinate(foldLine, point) {
  return ((point[0] - foldLine.origin[0]) * foldLine.direction[0])
    + ((point[1] - foldLine.origin[1]) * foldLine.direction[1]);
}

/** The part of ``loop`` on one side of a fold's band, cut ONLY along the fold's own span.
 *
 * The window is what makes a local fold local. A bend line separates the material it actually
 * crosses; the same infinite line, continued, runs through the rest of the part, and cutting
 * there invents a division no brake makes. tom's link_bracket is the case that showed it: its
 * wrap bend sits in the top 27mm of a 154mm bracket, and clipping by the infinite line sliced
 * the whole height in two -- after which the foot bend straddled both halves and could not be
 * folded at all.
 *
 * So a point outside the window is always kept, and a crossing is only cut where it falls
 * inside the window. Where the window covers the whole face this is the plain half-plane clip
 * it started as.
 */
export function clipLoopByHalfPlane(loop, foldLine, limit, keepPositiveSide, window = null) {
  const withinWindow = (point) => {
    if (!window) {
      return true;
    }
    const along = foldAlongCoordinate(foldLine, point);
    return along >= window.min - BAND_TOLERANCE_MM && along <= window.max + BAND_TOLERANCE_MM;
  };
  const inside = (point) => {
    if (!withinWindow(point)) {
      return true;
    }
    const distance = foldSignedDistance(foldLine, point);
    return keepPositiveSide ? distance >= limit - BAND_TOLERANCE_MM : distance <= limit + BAND_TOLERANCE_MM;
  };
  const clipped = [];
  for (let index = 0; index < loop.length; index += 1) {
    const current = loop[index];
    const next = loop[(index + 1) % loop.length];
    const currentInside = inside(current);
    const nextInside = inside(next);
    if (currentInside) {
      clipped.push(current);
    }
    if (currentInside === nextInside) {
      continue;
    }
    const currentDistance = foldSignedDistance(foldLine, current) - limit;
    const nextDistance = foldSignedDistance(foldLine, next) - limit;
    const denominator = currentDistance - nextDistance;
    if (Math.abs(denominator) <= EPSILON_MM) {
      continue;
    }
    const t = currentDistance / denominator;
    const crossing = [
      current[0] + (t * (next[0] - current[0])),
      current[1] + (t * (next[1] - current[1]))
    ];
    // A crossing outside the fold's own span is not this fold's business: the edge simply
    // continues, and inserting a vertex there would cut the part where no bend runs.
    if (!withinWindow(crossing)) {
      continue;
    }
    clipped.push(crossing);
  }
  return dropRepeatedPoints(clipped);
}

function dropRepeatedPoints(loop) {
  const out = [];
  for (const point of loop) {
    const last = out[out.length - 1];
    if (!last || Math.hypot(point[0] - last[0], point[1] - last[1]) > BAND_TOLERANCE_MM) {
      out.push(point);
    }
  }
  while (out.length > 1) {
    const first = out[0];
    const last = out[out.length - 1];
    if (Math.hypot(first[0] - last[0], first[1] - last[1]) <= BAND_TOLERANCE_MM) {
      out.pop();
      continue;
    }
    break;
  }
  return out;
}

/** Do two segments properly cross (not merely touch at an end)? */
export function segmentsCross(first, second) {
  const cross = (ax, ay, bx, by) => (ax * by) - (ay * bx);
  const [p1, p2] = [first.start, first.end];
  const [p3, p4] = [second.start, second.end];
  const d1 = cross(p4[0] - p3[0], p4[1] - p3[1], p1[0] - p3[0], p1[1] - p3[1]);
  const d2 = cross(p4[0] - p3[0], p4[1] - p3[1], p2[0] - p3[0], p2[1] - p3[1]);
  const d3 = cross(p2[0] - p1[0], p2[1] - p1[1], p3[0] - p1[0], p3[1] - p1[1]);
  const d4 = cross(p2[0] - p1[0], p2[1] - p1[1], p4[0] - p1[0], p4[1] - p1[1]);
  return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0));
}

function pointToSegmentDistance(point, start, end) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthSq = (dx * dx) + (dy * dy);
  if (lengthSq <= EPSILON_MM) {
    return Math.hypot(point[0] - start[0], point[1] - start[1]);
  }
  const t = Math.max(0, Math.min(1, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / lengthSq));
  return Math.hypot(point[0] - (start[0] + (t * dx)), point[1] - (start[1] + (t * dy)));
}

function distanceToLoopBoundary(point, loop) {
  let best = Infinity;
  for (let index = 0; index < loop.length; index += 1) {
    best = Math.min(best, pointToSegmentDistance(point, loop[index], loop[(index + 1) % loop.length]));
  }
  return best;
}

/** Does this fold's SEGMENT cut the region clean in two?
 *
 * Both ends have to reach the region's boundary and the line between them has to stay inside
 * it. This is what makes the fold a hinge rather than a slit: a segment stopping in the middle
 * of a face leaves the two halves joined by the material past its end, which no brake can bend.
 * Reported with the shortfall so the answer is actionable -- the fix is to extend the line, or
 * to add the relief cuts that make the material end where the line does.
 */
export function foldSegmentCrossesRegion(foldLine, region, tolerance = 0.05) {
  const start = foldLine.bendLine.start;
  const end = foldLine.bendLine.end;
  const startGap = distanceToLoopBoundary(start, region.outerLoop);
  const endGap = distanceToLoopBoundary(end, region.outerLoop);
  const samples = 9;
  let interiorSamples = 0;
  for (let index = 1; index < samples; index += 1) {
    const t = index / samples;
    const point = [start[0] + (t * (end[0] - start[0])), start[1] + (t * (end[1] - start[1]))];
    if (pointInsideLoop(point, region.outerLoop)) {
      interiorSamples += 1;
    }
  }
  return {
    crosses: startGap <= tolerance && endGap <= tolerance && interiorSamples === samples - 1,
    startGap,
    endGap,
    interiorFraction: interiorSamples / (samples - 1)
  };
}


/** Where on a loop's boundary a point sits: which edge, and how far along it. */
function projectPointOntoLoop(loop, point) {
  let best = null;
  for (let index = 0; index < loop.length; index += 1) {
    const start = loop[index];
    const end = loop[(index + 1) % loop.length];
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const lengthSq = (dx * dx) + (dy * dy);
    if (lengthSq <= EPSILON_MM) {
      continue;
    }
    const t = Math.max(0, Math.min(1, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / lengthSq));
    const projected = [start[0] + (t * dx), start[1] + (t * dy)];
    const distance = Math.hypot(point[0] - projected[0], point[1] - projected[1]);
    if (!best || distance < best.distance) {
      best = { edgeIndex: index, t, point: projected, distance };
    }
  }
  return best;
}

/** Cut a face in two along the bend's own segment.
 *
 * The chord is the BEND LINE, not a band edge and not the fold's infinite line. Cutting by an
 * infinite line divides faces the fold never touches; cutting by a band edge only works when
 * that edge happens to cross the boundary twice, which it does not when the boundary runs ALONG
 * the fold -- a tab folded about the panel's own bottom edge, where both chord ends are existing
 * vertices sitting exactly on the line. Projecting the bend's two endpoints onto the boundary
 * sidesteps every one of those degeneracies: the gate has already checked they reach it.
 */
function splitLoopAtSegment(loop, start, end) {
  const from = projectPointOntoLoop(loop, start);
  const to = projectPointOntoLoop(loop, end);
  if (!from || !to) {
    return null;
  }
  const [first, second] = (from.edgeIndex + from.t) <= (to.edgeIndex + to.t) ? [from, to] : [to, from];
  if (first.edgeIndex === second.edgeIndex && Math.abs(first.t - second.t) <= EPSILON_MM) {
    return null;
  }
  const between = [first.point];
  for (let index = first.edgeIndex + 1; index <= second.edgeIndex; index += 1) {
    between.push(loop[index % loop.length]);
  }
  between.push(second.point);
  const rest = [second.point];
  for (let index = second.edgeIndex + 1; index <= first.edgeIndex + loop.length; index += 1) {
    rest.push(loop[index % loop.length]);
  }
  rest.push(first.point);
  return [dropRepeatedPoints(between), dropRepeatedPoints(rest)];
}

/** Take this fold's half-band off one of the two faces it cut.
 *
 * ``path`` runs from one chord end, round the face, to the other, so the band only ever has to
 * come off its two ends. Walking out from a chord end, the boundary does one of two things:
 *
 *  - it RISES clear of the band, and the face starts where it crosses the band edge -- the
 *    ordinary case, and the same answer the plain half-plane clip gives;
 *  - it leaves the fold's SPAN first, running on along the fold, as a panel's bottom edge does
 *    under a folded tab. Then the corner stays and the face gains a jog: straight out to the
 *    band edge at the span's end. Trimming to the band edge anyway would take the panel's whole
 *    bottom edge with the tab.
 */
function trimBandFromFace(path, foldLine, side, window) {
  const limit = side * foldLine.halfWidth;
  const clearOfBand = (point) => (
    side * foldSignedDistance(foldLine, point) >= foldLine.halfWidth - BAND_TOLERANCE_MM
  );
  const withinSpan = (point) => {
    const along = foldAlongCoordinate(foldLine, point);
    return along >= window.min - BAND_TOLERANCE_MM && along <= window.max + BAND_TOLERANCE_MM;
  };
  const bandEdgePoint = (along) => [
    foldLine.origin[0] + (along * foldLine.direction[0]) + (limit * foldLine.normal[0]),
    foldLine.origin[1] + (along * foldLine.direction[1]) + (limit * foldLine.normal[1])
  ];
  const crossingToBandEdge = (inside, outside) => {
    const insideDistance = (side * foldSignedDistance(foldLine, inside)) - foldLine.halfWidth;
    const outsideDistance = (side * foldSignedDistance(foldLine, outside)) - foldLine.halfWidth;
    const denominator = outsideDistance - insideDistance;
    if (Math.abs(denominator) <= EPSILON_MM) {
      return null;
    }
    const t = -insideDistance / denominator;
    return [inside[0] + (t * (outside[0] - inside[0])), inside[1] + (t * (outside[1] - inside[1]))];
  };
  // Where a boundary edge leaves the fold's span, which is where the band's end sits.
  const crossingAtAlong = (from, to, along) => {
    const fromAlong = foldAlongCoordinate(foldLine, from);
    const toAlong = foldAlongCoordinate(foldLine, to);
    const denominator = toAlong - fromAlong;
    if (Math.abs(denominator) <= EPSILON_MM) {
      return null;
    }
    const t = (along - fromAlong) / denominator;
    if (t < -BAND_TOLERANCE_MM || t > 1 + BAND_TOLERANCE_MM) {
      return null;
    }
    return [from[0] + (t * (to[0] - from[0])), from[1] + (t * (to[1] - from[1]))];
  };
  // How far in from each end the band reaches, and what replaces the material taken off.
  const lead = (indices) => {
    let cursor = 0;
    while (cursor < indices.length) {
      const point = path[indices[cursor]];
      if (clearOfBand(point) || !withinSpan(point)) {
        break;
      }
      cursor += 1;
    }
    if (cursor >= indices.length) {
      return null;
    }
    const stop = path[indices[cursor]];
    if (clearOfBand(stop)) {
      const previous = cursor > 0 ? path[indices[cursor - 1]] : null;
      const crossing = previous ? crossingToBandEdge(previous, stop) : null;
      return { drop: cursor, insert: crossing ? [crossing] : [] };
    }
    // Left the span still inside the band. The face keeps the corner where its boundary leaves
    // the fold's span, and reaches it from the band edge: out along the span's end, then on.
    const along = foldAlongCoordinate(foldLine, stop);
    const spanEnd = along > window.max ? window.max : window.min;
    const previous = cursor > 0 ? path[indices[cursor - 1]] : null;
    const exit = previous ? crossingAtAlong(previous, stop, spanEnd) : null;
    return { drop: cursor, insert: exit ? [bandEdgePoint(spanEnd), exit] : [bandEdgePoint(spanEnd)] };
  };
  const forward = path.map((_, index) => index);
  const head = lead(forward);
  const tail = lead([...forward].reverse());
  if (!head || !tail) {
    return [];
  }
  const kept = path.slice(head.drop, path.length - tail.drop);
  return dropRepeatedPoints([...head.insert, ...kept, ...[...tail.insert].reverse()]);
}

/** The two faces a fold leaves behind, each with its half of the bend band removed. */
function splitFaceAtFold(loop, foldLine, window) {
  const split = splitLoopAtSegment(loop, foldLine.bendLine.start, foldLine.bendLine.end);
  if (!split) {
    return null;
  }
  const sides = split.map((candidate) => (
    candidate.length >= 3 && foldSignedDistance(foldLine, loopCentroid(candidate)) >= 0 ? 1 : -1
  ));
  if (sides[0] === sides[1]) {
    return null;
  }
  const positiveIndex = sides[0] === 1 ? 0 : 1;
  return {
    positive: trimBandFromFace(split[positiveIndex], foldLine, 1, window),
    negative: trimBandFromFace(split[1 - positiveIndex], foldLine, -1, window)
  };
}

/** Cut the blank into the faces the folds leave behind.
 *
 * Each fold splits ONE face into two, along its own segment, and removes its band -- the
 * material that becomes the curved bend. Splitting per face rather than by each fold's infinite
 * line is what lets folds of different orientations coexist: a fold only ever cuts the face it
 * actually crosses, so a bend on one arm of an L does not slice through the other arm. It also
 * makes the hinge graph a TREE by construction. Splitting by infinite lines instead put two
 * crossing folds in a cycle, where a face's placement depended on which way round the graph you
 * reached it -- an over-constrained blank that no brake can fold, reported as geometry.
 */
export function decomposeFoldRegions(outerLoop, foldLines, { tolerance = 0.05 } = {}) {
  let regions = [{ loop: outerLoop, sides: [] }];
  const splits = [];
  for (let foldIndex = 0; foldIndex < foldLines.length; foldIndex += 1) {
    const foldLine = foldLines[foldIndex];
    let target = -1;
    let bestReport = null;
    for (let index = 0; index < regions.length; index += 1) {
      const report = foldSegmentCrossesRegion(foldLine, { outerLoop: regions[index].loop }, tolerance);
      if (report.crosses) {
        target = index;
        break;
      }
      if (!bestReport || report.interiorFraction > bestReport.interiorFraction) {
        bestReport = report;
      }
    }
    if (target < 0) {
      // Two different failures wear the same symptom -- no single face holds this fold -- and
      // saying "it stops N mm short" about a fold that actually CROSSES another one sends the
      // reader off to lengthen a line that is already too long.
      const crossed = regions.filter(
        (region) => foldSegmentCrossesRegion(foldLine, { outerLoop: region.loop }, tolerance)
          .interiorFraction > 0
      ).length;
      if (crossed > 1) {
        const crossing = foldLines
          .slice(0, foldIndex)
          .map((other, otherIndex) => ({ other, otherIndex }))
          .filter(({ other }) => segmentsCross(foldLine.bendLine, other.bendLine))
          .map(({ otherIndex }) => `bend ${otherIndex + 1}`);
        throw new Error(
          `DXF 3D bend preview cannot fold crossing bend lines: bend ${foldIndex + 1} crosses `
          + `${crossing.length ? crossing.join(" and ") : "another bend"} inside the material. `
          + "One blank cannot be folded along both -- a brake needs each fold to separate two "
          + "faces, and at the crossing all four quarters would have to move at once. Add a "
          + "relief cut at the crossing, or shorten one line so the folds meet end to end."
        );
      }
      const shortBy = Math.max(bestReport?.startGap || 0, bestReport?.endGap || 0);
      throw new Error(
        `DXF 3D bend preview requires a fold line that runs edge to edge: bend ${foldIndex + 1}, `
        + `from (${foldLine.bendLine.start[0].toFixed(3)}, ${foldLine.bendLine.start[1].toFixed(3)}) `
        + `to (${foldLine.bendLine.end[0].toFixed(3)}, ${foldLine.bendLine.end[1].toFixed(3)}), `
        + `does not cut any face of the blank in two (its ends stop ${shortBy.toFixed(3)} mm short `
        + "of the material's edge). Extend the bend line, or add relief cuts at its ends so the "
        + "fold really does separate the two faces."
      );
    }
    const region = regions[target];
    // The fold cuts along ITS OWN segment, not along its infinite line -- see splitFaceAtFold.
    const span = foldLineSpan(foldLine);
    const window = { min: span.min, max: span.max };
    const split = splitFaceAtFold(region.loop, foldLine, window);
    const negative = split?.negative || [];
    const positive = split?.positive || [];
    if (negative.length < 3 || positive.length < 3) {
      throw new Error(
        `DXF 3D bend preview could not split the blank at bend ${foldIndex + 1}: its bend radius `
        + "band covers the whole face."
      );
    }
    const negativeRegion = { loop: negative, sides: [...region.sides, { foldIndex, side: -1 }] };
    const positiveRegion = { loop: positive, sides: [...region.sides, { foldIndex, side: 1 }] };
    regions = [
      ...regions.slice(0, target),
      negativeRegion,
      positiveRegion,
      ...regions.slice(target + 1)
    ];
    splits.push({ foldIndex, negative: negativeRegion, positive: positiveRegion });
  }
  const built = regions.map((region, index) => ({
    id: `region-${index}`,
    index,
    outerLoop: region.loop,
    holeLoops: [],
    // Which side of EVERY fold this face lies on, measured from its own centroid rather than
    // from the order the splits happened in. Split history cannot answer it: a later fold
    // re-splits a face, so "the negative child of fold 1" stops naming one face.
    sides: foldLines.map((foldLine, foldIndex) => ({
      foldIndex,
      side: foldSignedDistance(foldLine, loopCentroid(region.loop)) >= 0 ? 1 : -1
    })),
    area: polygonAbsArea(region.loop),
    centroid: loopCentroid(region.loop)
  }));
  // Two faces are hinged by a fold when they sit on opposite sides of it AND meet along it.
  // Segment-limited splitting is what keeps this a tree: a fold only ever cut one face, so no
  // face can be reached by two different paths.
  const adjacency = buildFoldAdjacency(built, foldLines);
  return { regions: built, adjacency };
}

function sideOf(region, foldIndex) {
  return region.sides.find((entry) => entry.foldIndex === foldIndex)?.side || 0;
}

/** Which two faces each fold hinges: the pair that meets along the most of it.
 *
 * ONE edge per fold, which is what makes the graph a tree: each fold cut exactly one face in
 * two, so N folds over N+1 faces need N hinges, no more.
 *
 * The pair is chosen by CONTACT along the fold, not by comparing which side of every fold each
 * face lies on. That comparison reads a fold's infinite line as dividing the whole blank, so two
 * faces a fold genuinely hinges lose their hinge whenever they also happen to straddle an
 * unrelated fold's line somewhere else on the part. tom's link_bracket is exactly that: its foot
 * sits right of the wrap bend's line and the body's centroid sits left of it, so the foot came
 * out hinged to nothing -- a second root, folded flat, with its bend band already taken out.
 */
export function buildFoldAdjacency(regions, foldLines) {
  const edges = [];
  foldLines.forEach((foldLine, foldIndex) => {
    let best = null;
    for (let a = 0; a < regions.length; a += 1) {
      for (let b = a + 1; b < regions.length; b += 1) {
        // Opposite sides of THIS fold, and meeting along it. Two faces on the same side of a
        // fold are not hinged by it, and faces that merely line up across it -- an L blank whose
        // arms are cut apart -- never touch its band.
        if (sideOf(regions[a], foldIndex) === sideOf(regions[b], foldIndex)) {
          continue;
        }
        const overlap = foldContactLength(regions[a], regions[b], foldLine);
        if (overlap <= BAND_TOLERANCE_MM) {
          continue;
        }
        if (!best || overlap > best.contactLength) {
          best = { foldIndex, regions: [a, b], contactLength: overlap };
        }
      }
    }
    if (best) {
      edges.push(best);
    }
  });
  return edges;
}

/** How much of the fold line the two faces share, measured along the line. */
export function foldContactLength(regionA, regionB, foldLine) {
  const spanA = foldLineSpanForRegion(regionA, foldLine);
  const spanB = foldLineSpanForRegion(regionB, foldLine);
  if (!spanA || !spanB) {
    return 0;
  }
  return Math.max(0, Math.min(spanA.max, spanB.max) - Math.max(spanA.min, spanB.min));
}

/** The region's extent ALONG the fold line, over the points that touch the fold's band. */
export function foldLineSpanForRegion(region, foldLine) {
  let min = Infinity;
  let max = -Infinity;
  for (const point of region.outerLoop) {
    const distance = Math.abs(foldSignedDistance(foldLine, point));
    if (Math.abs(distance - foldLine.halfWidth) > 1e-3) {
      continue;
    }
    const along = ((point[0] - foldLine.origin[0]) * foldLine.direction[0])
      + ((point[1] - foldLine.origin[1]) * foldLine.direction[1]);
    min = Math.min(min, along);
    max = Math.max(max, along);
  }
  return Number.isFinite(min) && max > min ? { min, max } : null;
}

/** The hinge that carries the child face across one fold, in the parent's frame.
 *
 * Built in the fold's own frame -- u across the line, v along it, y out of the sheet -- so the
 * arc formula is the flat one, and then conjugated into the mesher's XZ plane. The child face
 * starts at the band's far edge, which after folding sits at the arc's exit: advanced
 * ``R sin|a|`` across and lifted ``R (1 - cos|a|)`` out of the plane, measured from the band's
 * near edge. Composing hinge after hinge is what gives a chain of bends its shape.
 *
 * ``side`` is +1 when the child is on the fold's normal side. Folding "up" always lifts the
 * child towards +Y whichever side it is on, so the rotation sign follows the side.
 */
export function foldHingeMatrix(foldLine, side) {
  const magnitude = Math.abs(foldLine.angleRadians);
  if (magnitude <= 1e-9 || foldLine.halfWidth <= EPSILON_MM) {
    return new Matrix4().identity();
  }
  const sign = foldLine.angleRadians < 0 ? -1 : 1;
  const halfWidth = foldLine.halfWidth;
  const radius = foldLine.neutralRadius;

  // Local frame: u ACROSS the fold, increasing towards the child; y out of the sheet; v ALONG
  // the fold. In it the parent's edge of the band is at u = -halfWidth and the child's entry
  // edge at u = +halfWidth, whichever side of the line the child is on -- which is why `across`
  // carries the side.
  const across = new Vector3(foldLine.normal[0], 0, foldLine.normal[1]).multiplyScalar(side >= 0 ? 1 : -1);
  const along = new Vector3(foldLine.direction[0], 0, foldLine.direction[1]);
  const basis = new Matrix4().makeBasis(across, new Vector3(0, 1, 0), along);
  const originTranslate = new Matrix4().makeTranslation(foldLine.origin[0], 0, foldLine.origin[1]);

  // Hinge at the parent's tangent point, then unroll: a rigid rotation would swing the child's
  // entry edge along the chord, but the band becomes an ARC of the same length, so the entry
  // edge belongs at the arc's exit instead. The difference between the two is the correction.
  const rotation = new Matrix4()
    .makeTranslation(-halfWidth, 0, 0)
    .multiply(new Matrix4().makeRotationAxis(new Vector3(0, 0, 1), sign * magnitude))
    .multiply(new Matrix4().makeTranslation(halfWidth, 0, 0));
  const rotatedEntry = new Vector3(halfWidth, 0, 0).applyMatrix4(rotation);
  const arcExit = new Vector3(
    -halfWidth + (radius * Math.sin(magnitude)),
    sign * radius * (1 - Math.cos(magnitude)),
    0
  );
  const local = new Matrix4()
    .makeTranslation(arcExit.x - rotatedEntry.x, arcExit.y - rotatedEntry.y, 0)
    .multiply(rotation);

  return originTranslate
    .clone()
    .multiply(basis)
    .multiply(local)
    .multiply(basis.clone().invert())
    .multiply(originTranslate.clone().invert());
}

/** Place every region: root stays put, each child is its parent's placement times a hinge.
 *
 * The root is the largest face by area, which is the one a person would hold. Any face the
 * folds do not connect to it keeps the identity -- it is a separate island in the blank, not
 * something a bend can move.
 */
export function buildRegionPlacements(regions, foldLines, adjacency) {
  const placements = regions.map(() => new Matrix4().identity());
  if (!regions.length) {
    return { placements, rootIndex: -1, parents: [] };
  }
  // Which face stays still. The MOST HINGED face, area breaking ties -- not simply the
  // largest, which is what made identical bend settings produce different shapes on different
  // blanks: on a U channel whose flanges are wider than its web, the largest face is a flange,
  // so anchoring it made "both bends up" fold a Z (flange, then web, then the far flange
  // carrying on in the same rotational sense) instead of a U. The web has two hinges and every
  // flange has one, so counting hinges anchors the part on the face a person would hold, and
  // "up" then means up relative to it.
  const hingeCounts = regions.map(() => 0);
  for (const edge of adjacency) {
    hingeCounts[edge.regions[0]] += 1;
    hingeCounts[edge.regions[1]] += 1;
  }
  const rootIndex = regions.reduce((best, region, index) => {
    if (hingeCounts[index] !== hingeCounts[best]) {
      return hingeCounts[index] > hingeCounts[best] ? index : best;
    }
    return region.area > regions[best].area ? index : best;
  }, 0);
  const neighbours = regions.map(() => []);
  for (const edge of adjacency) {
    const [a, b] = edge.regions;
    neighbours[a].push({ region: b, foldIndex: edge.foldIndex });
    neighbours[b].push({ region: a, foldIndex: edge.foldIndex });
  }
  const parents = regions.map(() => null);
  const visited = regions.map(() => false);
  visited[rootIndex] = true;
  const queue = [rootIndex];
  while (queue.length) {
    const current = queue.shift();
    for (const link of neighbours[current]) {
      if (visited[link.region]) {
        continue;
      }
      visited[link.region] = true;
      parents[link.region] = { region: current, foldIndex: link.foldIndex };
      const foldLine = foldLines[link.foldIndex];
      const side = sideOf(regions[link.region], link.foldIndex);
      placements[link.region] = placements[current]
        .clone()
        .multiply(foldHingeMatrix(foldLine, side));
      queue.push(link.region);
    }
  }
  return { placements, rootIndex, parents, visited };
}


/** A fold line the decomposition can work with, from a DXF bend line and its setting.
 *
 * Any orientation: the direction comes from the line's own endpoints, the normal is that turned
 * 90 degrees, and the band is centred on the line with the same width the flat pattern loses to
 * the arc (2 * halfWidth = neutralRadius * angle, so the band's flat length IS the arc length).
 */
export function buildFoldLine({
  bendLine,
  angleRadians,
  insideRadiusMm = 0,
  kFactor = 0.5,
  halfThicknessMm = 1,
}) {
  const dx = bendLine.end[0] - bendLine.start[0];
  const dy = bendLine.end[1] - bendLine.start[1];
  const length = Math.hypot(dx, dy);
  if (!(length > EPSILON_MM)) {
    return null;
  }
  const direction = [dx / length, dy / length];
  // Left-hand normal, so "positive side" is a consistent hand for a given line direction.
  const normal = [-direction[1], direction[0]];
  const insideRadius = insideRadiusMm > 0
    ? insideRadiusMm
    : Math.max(halfThicknessMm * 2 * 0.6, EPSILON_MM);
  const neutralRadius = insideRadius + (kFactor * halfThicknessMm * 2);
  const magnitude = Math.abs(angleRadians);
  return {
    bendLine,
    origin: [bendLine.start[0], bendLine.start[1]],
    direction,
    normal,
    angleRadians,
    neutralRadius,
    insideRadius,
    halfWidth: magnitude > 1e-9 ? (neutralRadius * magnitude) / 2 : 0,
    length,
  };
}

/** Where the fold's infinite line crosses the outer contour, as distances along the line.
 *
 * The generalisation of "the material's Y span at the bend's X" to a line of any angle: the
 * crossings bound the material the line passes through, so a fold line has to cover them to
 * separate the part in two.
 */
export function outerMaterialSpanAlongFold(outerLoop, foldLine) {
  const crossings = [];
  for (let index = 0; index < outerLoop.length; index += 1) {
    const start = outerLoop[index];
    const end = outerLoop[(index + 1) % outerLoop.length];
    const startDistance = foldSignedDistance(foldLine, start);
    const endDistance = foldSignedDistance(foldLine, end);
    if (startDistance * endDistance > 0) {
      continue;
    }
    const denominator = startDistance - endDistance;
    const points = [];
    if (Math.abs(denominator) <= EPSILON_MM) {
      // The edge lies ON the line: both endpoints bound the crossing.
      points.push(start, end);
    } else {
      const t = startDistance / denominator;
      points.push([
        start[0] + (t * (end[0] - start[0])),
        start[1] + (t * (end[1] - start[1]))
      ]);
    }
    for (const point of points) {
      crossings.push(
        ((point[0] - foldLine.origin[0]) * foldLine.direction[0])
        + ((point[1] - foldLine.origin[1]) * foldLine.direction[1])
      );
    }
  }
  if (!crossings.length) {
    return null;
  }
  return { min: Math.min(...crossings), max: Math.max(...crossings) };
}

/** The fold line's own extent, as distances along itself. Its endpoints, in the same units as
 *  outerMaterialSpanAlongFold, so the two are directly comparable. */
export function foldLineSpan(foldLine) {
  const at = (point) => ((point[0] - foldLine.origin[0]) * foldLine.direction[0])
    + ((point[1] - foldLine.origin[1]) * foldLine.direction[1]);
  const a = at(foldLine.bendLine.start);
  const b = at(foldLine.bendLine.end);
  return { min: Math.min(a, b), max: Math.max(a, b) };
}

function pointInsideLoop(point, loop) {
  let inside = false;
  for (let index = 0, previous = loop.length - 1; index < loop.length; previous = index, index += 1) {
    const [xi, yi] = loop[index];
    const [xj, yj] = loop[previous];
    const intersects = ((yi > point[1]) !== (yj > point[1]))
      && (point[0] < (((xj - xi) * (point[1] - yi)) / ((yj - yi) || EPSILON_MM)) + xi);
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

/** Give every hole to the region that contains it.
 *
 * A hole that straddles a fold's band cannot be folded -- material inside the bend radius has
 * nowhere to go -- and a hole that lands in no region at all means the decomposition and the
 * hole disagree, so both are reported rather than dropped.
 */
export function assignHolesToRegions(regions, holeLoops, foldLines) {
  for (const holeLoop of holeLoops) {
    for (let foldIndex = 0; foldIndex < foldLines.length; foldIndex += 1) {
      const foldLine = foldLines[foldIndex];
      if (foldLine.halfWidth <= EPSILON_MM) {
        continue;
      }
      // Only where the bend actually RUNS. Measured against the infinite line, a cutout tens of
      // millimetres away from a short bend counted as crossing it -- which is how tom's
      // link_bracket came to be rejected for a web cutout 30mm below its wrap bend.
      const span = foldLineSpan(foldLine);
      const alongs = holeLoop.map((point) => foldAlongCoordinate(foldLine, point));
      const beside = Math.min(...alongs) > span.max + foldLine.halfWidth
        || Math.max(...alongs) < span.min - foldLine.halfWidth;
      if (beside) {
        continue;
      }
      const distances = holeLoop.map((point) => foldSignedDistance(foldLine, point));
      const insideBand = distances.some((distance) => Math.abs(distance) < foldLine.halfWidth - BAND_TOLERANCE_MM);
      const bothSides = distances.some((distance) => distance > 0) && distances.some((distance) => distance < 0);
      if (insideBand || bothSides) {
        throw new Error(
          `DXF 3D bend preview does not support holes crossing bend radius bands: a cutout `
          + `crosses bend ${foldIndex + 1}`
        );
      }
    }
    const centroid = loopCentroid(holeLoop);
    const owner = regions.find((region) => pointInsideLoop(centroid, region.outerLoop))
      || regions.find((region) => holeLoop.every((point) => pointInsideLoop(point, region.outerLoop)));
    if (!owner) {
      continue;
    }
    owner.holeLoops.push(holeLoop);
  }
  return regions;
}


/** The fold's own frame in mesh coordinates: u across (towards the child), y out, v along. */
function foldBasis(foldLine, side) {
  const across = new Vector3(foldLine.normal[0], 0, foldLine.normal[1]).multiplyScalar(side >= 0 ? 1 : -1);
  const along = new Vector3(foldLine.direction[0], 0, foldLine.direction[1]);
  const basis = new Matrix4().makeBasis(across, new Vector3(0, 1, 0), along);
  return new Matrix4()
    .makeTranslation(foldLine.origin[0], 0, foldLine.origin[1])
    .multiply(basis);
}

/** The curved band that joins two folded faces, as world-space triangles and edge segments.
 *
 * Swept in the fold's own frame -- an arc across, straight along -- and then placed by the
 * PARENT's matrix, because the band belongs to the parent's frame just as the hinge is expressed
 * in it. Both faces of the sheet get an arc (inner and outer radius), and the two ends of the
 * sweep are capped so the band is a closed solid rather than a surface.
 */
export function buildFoldBridgeGeometry({
  foldLine,
  side,
  span,
  halfThickness,
  parentMatrix = new Matrix4().identity(),
  segments = 0,
}) {
  const magnitude = Math.abs(foldLine.angleRadians);
  if (magnitude <= 1e-9 || !span || span.max - span.min <= EPSILON_MM) {
    return { triangles: [], edges: [] };
  }
  const sign = foldLine.angleRadians < 0 ? -1 : 1;
  const radius = foldLine.neutralRadius;
  const sampleCount = Math.max(segments || Math.ceil((magnitude / (Math.PI / 18)) + 1), 2);
  const place = parentMatrix.clone().multiply(foldBasis(foldLine, side));
  const toWorld = (u, y, v) => new Vector3(u, y, v).applyMatrix4(place).toArray();

  // The neutral arc starts at the parent's tangent point (u = -halfWidth) and turns towards the
  // child. Its centre sits `radius` away on the side the sheet folds towards.
  const centre = { u: -foldLine.halfWidth, y: sign * radius };
  const rings = [];
  for (let index = 0; index <= sampleCount; index += 1) {
    const t = (index / sampleCount) * magnitude;
    // Angle measured from the start of the arc, sweeping towards the child.
    const u = centre.u + (radius * Math.sin(t));
    const y = centre.y - (sign * radius * Math.cos(t));
    // Outward normal of the sheet at this station, in the (u, y) plane.
    const normalU = Math.sin(t) * sign;
    const normalY = -Math.cos(t);
    rings.push({
      u,
      y,
      outer: [u + (normalU * halfThickness * sign), y + (normalY * halfThickness * sign)],
      inner: [u - (normalU * halfThickness * sign), y - (normalY * halfThickness * sign)],
    });
  }

  const triangles = [];
  const edges = [];
  const quad = (a, b, c, d) => {
    triangles.push([a, b, c], [a, c, d]);
  };
  for (let index = 0; index < rings.length - 1; index += 1) {
    const current = rings[index];
    const next = rings[index + 1];
    for (const face of ["outer", "inner"]) {
      const flip = face === "inner";
      const a = toWorld(current[face][0], current[face][1], span.min);
      const b = toWorld(next[face][0], next[face][1], span.min);
      const c = toWorld(next[face][0], next[face][1], span.max);
      const d = toWorld(current[face][0], current[face][1], span.max);
      if (flip) {
        quad(a, d, c, b);
      } else {
        quad(a, b, c, d);
      }
    }
    // The two cut ends of the band, so it reads as a solid from the side.
    for (const [v, flip] of [[span.min, false], [span.max, true]]) {
      const a = toWorld(current.outer[0], current.outer[1], v);
      const b = toWorld(next.outer[0], next.outer[1], v);
      const c = toWorld(next.inner[0], next.inner[1], v);
      const d = toWorld(current.inner[0], current.inner[1], v);
      if (flip) {
        quad(a, d, c, b);
      } else {
        quad(a, b, c, d);
      }
    }
  }
  // Edge lines: the four silhouette curves of the band, which is what reads as a bend.
  for (const face of ["outer", "inner"]) {
    for (const v of [span.min, span.max]) {
      for (let index = 0; index < rings.length - 1; index += 1) {
        edges.push([
          toWorld(rings[index][face][0], rings[index][face][1], v),
          toWorld(rings[index + 1][face][0], rings[index + 1][face][1], v)
        ]);
      }
    }
  }
  return { triangles, edges };
}
