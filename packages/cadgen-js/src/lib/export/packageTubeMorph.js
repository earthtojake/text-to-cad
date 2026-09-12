// A clip's deforming tubes, baked into glTF MORPH TARGETS: the export half of
// tube deformation.
//
// The viewer DRIVES a deformation — every frame it recompiles the posed path and
// re-emits every vertex on it (common/tubeDeformation.js). A GLB carries no
// evaluator, so an exported deformation has to become data: a base mesh, a stack
// of per-vertex position deltas against it, and a weight schedule that blends
// between them. That is what this module produces, and everything here exists to
// keep the blend HONEST.
//
// The load-bearing fact, and it is not the obvious one:
//
//   Morph weights blend the RESULT of two poses. A clip blends its own control
//   numbers and rebuilds the path from them, and the path -> vertex map (arc-
//   length reparameterisation, parallel-transported frames, stretch) is not
//   linear. So a morph target at every solved keyframe of the clip is NOT
//   faithful — it is exact at the keyframes and wrong between them, worst
//   exactly where a tendon turns hardest. On a real tendon hand, targets at the
//   solve's own 4 Hz density leave 23 mm of error mid-interval on 1.5 mm cords,
//   in a file where every still frame taken AT a keyframe looks perfect.
//
// So the target times are not the clip's keyframes and not the export's frames:
// they are fitted, per occurrence, to a stated tolerance in millimetres, measured
// on a grid four times finer than the export's own frame rate. The fit is an
// upper BOUND rather than a sample, which is what makes the tolerance mean
// something — see boundsForFractions.
//
// This module is PURE (no filesystem) and it does not re-derive the deformation:
// it drives the same prepareTubeBake / poseTubeBake the viewer's display path
// calls, so an exported cord and a rendered one cannot disagree.

import {
  BufferAttribute,
  BufferGeometry,
  Float32BufferAttribute,
  Matrix3,
  Matrix4,
  Vector3,
} from "three";

import {
  compileDeformation,
  poseTubeBake,
  prepareTubeBake,
  sameTubeDeformation,
  sampleTubePath,
} from "../../common/tubeDeformation.js";
import {
  determinant3,
  identityTransform,
  normalMatrix3,
  occurrenceFaceRangeColors,
  occurrenceMaterial,
  transformPoint,
} from "./packageMeshExport.js";

// tubeDeformation takes its matrix classes as an argument rather than importing
// them, so this drives it with the same three the viewer does.
const TUBE_THREE = { BufferGeometry, Float32BufferAttribute, Matrix3, Vector3 };

/** The tolerance a morph bake fits to when the request names none, in millimetres.
 *
 * Two thirds of a typical tendon's diameter: visibly right, and on a 24 fps export
 * three times better than a target per frame would be, at a quarter of the targets. */
export const DEFAULT_MORPH_TOLERANCE_MM = 1.0;

/** The ceiling, and it is on PLAYBACK memory rather than on file size.
 *
 * three.js uploads morph data as a Float32 RGBA texture layer per target — 16 bytes
 * per vertex per target for positions, 32 with normals — and allocates the same
 * again as a JS array while it does. That, not the bytes on disk, is what decides
 * whether a deforming file opens: a 1.7 GB base GLB is merely large, while a 1.5 GB
 * morph texture is a browser tab that dies. Estimated before a single delta is
 * allocated, so the refusal costs seconds rather than the whole bake. */
export const MAX_MORPH_RUNTIME_BYTES = 512 * 1024 * 1024;

// One Float32 RGBA texel per vertex per target per attribute, in three's morph
// attribute texture (WebGLMorphtargets).
const RUNTIME_BYTES_PER_TEXEL = 16;

/** Below this the posed normals are close enough to the base ones to leave out.
 *
 * A deformed tube's normals turn with it, and shipping only positions lights a
 * bent cord as though it were still straight — worst on a tendon wrapping a
 * capstan, which is exactly where the bend is biggest. So normals are baked, and
 * the exemption is MEASURED per occurrence rather than assumed: a tube that barely
 * turns saves half its bytes and half its texture, and the summary says which ones
 * took it. glTF requires a mesh's primitives to agree on target attributes, so the
 * decision is per OCCURRENCE and never per primitive. */
export const MORPH_NORMAL_OMIT_DEGREES = 5;

// How long the fit's open interval may get before a key is forced. Purely a memory
// and time bound: the scan retains one posed corner set per open sample and
// re-checks every one of them as the interval grows, so an unbounded interval on a
// near-motionless tube would cost both without buying anything. A key every 128 grid
// samples is at most one extra target per 1.3 seconds, and a target whose delta is
// identically zero is dropped below anyway.
const MORPH_FIT_MAX_OPEN_SAMPLES = 128;

// How many of a primitive's vertices carry a posed reference into the file's own
// space for the reconstruction check (packageMeshExport.verifyMorphReconstruction).
// A basis or scale mistake is uniform across a primitive, so a strided sample finds
// it as surely as every vertex would, at a thousandth of the memory.
const MORPH_VERIFY_SAMPLE_LIMIT = 512;

const IDENTITY = new Matrix4();

function summarize(ids, limit = 6) {
  const sorted = [...ids].sort();
  if (sorted.length <= limit) {
    return sorted.join(", ");
  }
  return `${sorted.slice(0, limit).join(", ")} (and ${sorted.length - limit} more)`;
}

function formatBytes(bytes) {
  if (bytes >= 1024 ** 3) {
    return `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
  }
  return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
}

/** One occurrence's tessellation, placed, in world CAD millimetres.
 *
 * The deformation's paths are authored in assembly coordinates, so baking the
 * occurrence transform into the vertices here makes the preparation's `base` — and
 * therefore its inverse — the IDENTITY, and every posed vertex lands directly in the
 * space packageMeshExport bakes into. `triangleRange[t]` is the face range triangle
 * `t` came from, which is how a refined triangle finds its colour again.
 */
function occurrenceWorldGeometry(occurrence, tessellation) {
  const transform = Array.isArray(occurrence.transform) ? occurrence.transform : null;
  const identity = transform === null || identityTransform(transform);
  const mirrored = !identity && determinant3(transform) < 0;
  const nm = identity ? null : normalMatrix3(transform);
  const source = tessellation.positions;
  const sourceNormals = tessellation.normals;
  const vertexCount = Math.floor(source.length / 3);
  const positions = new Float32Array(source.length);
  const normals = new Float32Array(source.length);
  for (let v = 0; v < vertexCount; v += 1) {
    const i = v * 3;
    if (identity) {
      positions[i] = source[i];
      positions[i + 1] = source[i + 1];
      positions[i + 2] = source[i + 2];
    } else {
      transformPoint(transform, source[i], source[i + 1], source[i + 2], positions, i);
    }
    const nx = sourceNormals[i];
    const ny = sourceNormals[i + 1];
    const nz = sourceNormals[i + 2];
    let tx = nx;
    let ty = ny;
    let tz = nz;
    if (nm) {
      tx = nm[0] * nx + nm[1] * ny + nm[2] * nz;
      ty = nm[3] * nx + nm[4] * ny + nm[5] * nz;
      tz = nm[6] * nx + nm[7] * ny + nm[8] * nz;
    }
    const length = Math.hypot(tx, ty, tz) || 1;
    normals[i] = tx / length;
    normals[i + 1] = ty / length;
    normals[i + 2] = tz / length;
  }

  const ranges = tessellation.faceRanges || [];
  let triangles = 0;
  for (const range of ranges) {
    triangles += Math.floor((Number(range.indexCount) || 0) / 3);
  }
  const indices = new Uint32Array(triangles * 3);
  const triangleRange = new Uint32Array(triangles);
  // Mirroring flips winding so recomputed facet normals stay outward, exactly as
  // the soup path does it.
  const order = mirrored ? [0, 2, 1] : [0, 1, 2];
  let written = 0;
  ranges.forEach((range, rangeIndex) => {
    const start = Number(range.indexStart) || 0;
    const count = Number(range.indexCount) || 0;
    for (let k = start; k + 2 < start + count; k += 3) {
      indices[written * 3] = tessellation.indices[k + order[0]];
      indices[written * 3 + 1] = tessellation.indices[k + order[1]];
      indices[written * 3 + 2] = tessellation.indices[k + order[2]];
      triangleRange[written] = rangeIndex;
      written += 1;
    }
  });

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new BufferAttribute(normals, 3));
  geometry.setIndex(new BufferAttribute(indices, 1));
  return { geometry, triangleRange };
}

/** The BOX of (transverse u, transverse v, axial) at each distinct arc fraction.
 *
 * This is what turns the fit from a sample into a bound. At a fixed arc fraction a
 * posed vertex is AFFINE in (u, v, axial) — the frame's normal, binormal and tangent
 * scaled by them — so the difference between a true pose and a two-key blend is
 * affine there too, and the norm of an affine map over a box attains its maximum at
 * a corner. Probing the corners of each fraction's box therefore bounds every vertex
 * that shares that fraction, including ones between them, for about half the work
 * that visiting the vertices would cost.
 */
function boundsForFractions(mapping) {
  const values = mapping.values;
  const recordCount = Math.floor(values.length / 8);
  const byFraction = new Map();
  for (let record = 0; record < recordCount; record += 1) {
    const j = record * 8;
    const fraction = values[j];
    const box = byFraction.get(fraction);
    if (!box) {
      byFraction.set(fraction, [
        values[j + 1], values[j + 1],
        values[j + 2], values[j + 2],
        values[j + 3], values[j + 3],
      ]);
      continue;
    }
    for (let axis = 0; axis < 3; axis += 1) {
      const value = values[j + 1 + axis];
      if (value < box[axis * 2]) box[axis * 2] = value;
      if (value > box[axis * 2 + 1]) box[axis * 2 + 1] = value;
    }
  }
  const fractions = [...byFraction.keys()].sort((left, right) => left - right);
  const cornerOffset = new Uint32Array(fractions.length + 1);
  const uva = [];
  fractions.forEach((fraction, index) => {
    const box = byFraction.get(fraction);
    // A degenerate axis contributes ONE value, not two: a tube's vertices all sit at
    // essentially zero axial offset, so this is what keeps the probe at four corners
    // per ring instead of eight.
    const axes = [0, 1, 2].map((axis) => (
      box[axis * 2] === box[axis * 2 + 1] ? [box[axis * 2]] : [box[axis * 2], box[axis * 2 + 1]]
    ));
    for (const u of axes[0]) {
      for (const v of axes[1]) {
        for (const axial of axes[2]) {
          uva.push(u, v, axial);
        }
      }
    }
    cornerOffset[index + 1] = uva.length / 3;
  });
  return {
    fractions: Float64Array.from(fractions),
    cornerOffset,
    uva: Float64Array.from(uva),
  };
}

/** Where every probe corner lands under one pose. Positions only; see updateAttribute. */
function poseCorners(model, deformation, out) {
  const path = deformation.path;
  const twist = (deformation.twistDeg || 0) * Math.PI / 180;
  const cos = Math.cos(twist);
  const sin = Math.sin(twist);
  for (let index = 0; index < model.fractions.length; index += 1) {
    const frame = sampleTubePath(path, model.fractions[index] * path.length);
    const point = frame.point;
    const normal = frame.normal;
    const binormal = frame.binormal;
    const tangent = frame.tangent;
    for (let corner = model.cornerOffset[index]; corner < model.cornerOffset[index + 1]; corner += 1) {
      const j = corner * 3;
      const u0 = model.uva[j];
      const v0 = model.uva[j + 1];
      const axial = model.uva[j + 2];
      const u = cos * u0 - sin * v0;
      const v = sin * u0 + cos * v0;
      out[j] = point[0] + normal[0] * u + binormal[0] * v + tangent[0] * axial;
      out[j + 1] = point[1] + normal[1] * u + binormal[1] * v + tangent[1] * axial;
      out[j + 2] = point[2] + normal[2] * u + binormal[2] * v + tangent[2] * axial;
    }
  }
  return out;
}

/** How far the linear blend of `a` and `b` at `alpha` is from the true pose `m`. */
function blendDeviation(a, b, m, alpha) {
  let worst = 0;
  for (let i = 0; i < m.length; i += 3) {
    const dx = m[i] - (a[i] + (b[i] - a[i]) * alpha);
    const dy = m[i + 1] - (a[i + 1] + (b[i + 1] - a[i + 1]) * alpha);
    const dz = m[i + 2] - (a[i + 2] + (b[i + 2] - a[i + 2]) * alpha);
    const distance = dx * dx + dy * dy + dz * dz;
    if (distance > worst) {
      worst = distance;
    }
  }
  return Math.sqrt(worst);
}

/** Forward scan: the fewest grid samples whose blend stays inside `tolerance`.
 *
 * One pass, deterministic, and every interior sample of the open interval is
 * re-checked as it grows — a fit that only checked the newest sample would certify
 * an interval by the one moment that is exact by construction. */
function fitTargetTimes(poses, model, tolerance) {
  const total = poses.length;
  const keys = [0];
  if (total < 2) {
    return keys;
  }
  let anchor = 0;
  // ONE compiled path is live at a time. The pose is resolved here, its corners are
  // written into a Float64Array, and the arc-length tables that produced them fall
  // back to the LRU: what crosses a grid sample is the corners, never the tables.
  let anchorPose = poseCorners(model, compileDeformation(poses[0]), new Float64Array(model.uva.length));
  let previousPose = anchorPose;
  let open = [];
  let uniform = true;
  for (let index = 1; index < total; index += 1) {
    // A pose the clip did not change poses to the same corners bit for bit, so reuse
    // them rather than compiling the path again to recompute them.
    const pose = sameTubeDeformation(poses[index], poses[index - 1])
      ? previousPose
      : poseCorners(model, compileDeformation(poses[index]), new Float64Array(model.uva.length));
    previousPose = pose;
    open.push({ index, pose });
    // Every sample since the anchor is the SAME deformation, so every blend between
    // them is exact. A tube the clip holds still costs no comparisons at all.
    uniform = uniform && sameTubeDeformation(poses[index], poses[anchor]);
    let exceeded = false;
    if (!uniform) {
      const span = index - anchor;
      for (const entry of open) {
        if (entry.index === index) {
          continue;
        }
        const alpha = (entry.index - anchor) / span;
        if (blendDeviation(anchorPose, pose, entry.pose, alpha) > tolerance) {
          exceeded = true;
          break;
        }
      }
    }
    if (!exceeded && open.length < MORPH_FIT_MAX_OPEN_SAMPLES) {
      continue;
    }
    // The PREVIOUS sample is the last one that fit; the current one is what broke it.
    const cut = exceeded ? index - 1 : index;
    const cutEntry = open.find((entry) => entry.index === cut);
    keys.push(cut);
    anchor = cut;
    anchorPose = cutEntry.pose;
    open = open.filter((entry) => entry.index > cut);
    uniform = open.every((entry) => sameTubeDeformation(poses[entry.index], poses[anchor]));
  }
  if (keys[keys.length - 1] !== total - 1) {
    keys.push(total - 1);
  }
  return keys;
}

/** Refined triangles grouped by the export colour their source face range resolved to. */
function partitionByColor(prepared, triangleRange, rangeColors) {
  const index = prepared.geometry.index;
  const triangleCount = Math.floor(index.count / 3);
  const sourceTriangles = prepared.sourceTriangles;
  const byColor = new Map();
  for (let triangle = 0; triangle < triangleCount; triangle += 1) {
    // `sourceTriangles` is null when the rest mesh needed no refinement, and then a
    // refined triangle IS its source triangle.
    const source = sourceTriangles ? sourceTriangles[triangle] : triangle;
    const color = rangeColors[triangleRange[source]] || rangeColors[0];
    let bucket = byColor.get(color);
    if (!bucket) {
      byColor.set(color, (bucket = []));
    }
    bucket.push(triangle);
  }
  return [...byColor.entries()].map(([color, triangles]) => {
    const indices = new Uint32Array(triangles.length * 3);
    const mapped = new Map();
    let next = 0;
    triangles.forEach((triangle, ordinal) => {
      for (let corner = 0; corner < 3; corner += 1) {
        const vertex = index.getX(triangle * 3 + corner);
        let slot = mapped.get(vertex);
        if (slot === undefined) {
          slot = next;
          next += 1;
          mapped.set(vertex, slot);
        }
        indices[ordinal * 3 + corner] = slot;
      }
    });
    const vertexIds = new Uint32Array(next);
    for (const [vertex, slot] of mapped) {
      vertexIds[slot] = vertex;
    }
    return { color, indices, vertexIds, slotOf: mapped };
  });
}

/** One compaction, used for base positions, base normals and every delta alike.
 *
 * A partition duplicates the refined vertices its colour shares with another, so
 * every per-vertex array has to be re-ordered the same way. One function does all of
 * them, which is what makes a scrambled target impossible rather than merely
 * unlikely. */
function gather(source, vertexIds) {
  const out = new Float32Array(vertexIds.length * 3);
  for (let slot = 0; slot < vertexIds.length; slot += 1) {
    const from = vertexIds[slot] * 3;
    out[slot * 3] = source[from];
    out[slot * 3 + 1] = source[from + 1];
    out[slot * 3 + 2] = source[from + 2];
  }
  return out;
}

function verifySampleIds(count) {
  const limit = Math.max(1, Math.min(count, MORPH_VERIFY_SAMPLE_LIMIT));
  const ids = new Uint32Array(limit);
  for (let sample = 0; sample < limit; sample += 1) {
    ids[sample] = Math.floor((sample * count) / limit);
  }
  return ids;
}

function maxNormalDegrees(base, posed) {
  let worst = 0;
  for (let i = 0; i < base.length; i += 3) {
    const ax = base[i];
    const ay = base[i + 1];
    const az = base[i + 2];
    const bx = posed[i];
    const by = posed[i + 1];
    const bz = posed[i + 2];
    const denominator = Math.hypot(ax, ay, az) * Math.hypot(bx, by, bz);
    if (denominator < 1e-12) {
      continue;
    }
    const cosine = Math.min(1, Math.max(-1, (ax * bx + ay * by + az * bz) / denominator));
    const degrees = Math.acos(cosine) * 180 / Math.PI;
    if (degrees > worst) {
      worst = degrees;
    }
  }
  return worst;
}

/**
 * Bake every deforming tube of a sampled clip into morph targets.
 *
 * `deformations` is the sampler's own output — `Map<occurrenceId, { rest,
 * samples }>` over the fit grid — and `grid` is the schedule those samples fall on.
 * Returns:
 *
 *   overrides  Map<occurrenceId, primitive[]> for buildPackageMeshPrimitives: the
 *              REFINED, POSED base mesh with its `targets`, replacing what the soup
 *              path would have built from the rest tessellation.
 *   channels   one `{ node, times, weights, targetCount }` per occurrence that
 *              actually moves, for the glTF weights sampler.
 *   stats      what the summary reports, including the achieved deviation.
 *
 * Occurrences with no motion keep their override (the clip may hold a tube in a
 * shape that is not its rest shape, and shipping the rest shape would be the silent
 * freeze this door exists to prevent) and get no targets and no channel.
 */
export function buildTubeMorphTargets(descriptor, componentTessellations, deformations, options = {}) {
  const {
    toleranceMm = DEFAULT_MORPH_TOLERANCE_MM,
    grid,
    defaultColor = null,
    clipId = "clip",
    // The playback-memory ceiling this bake must fit under. A caller targeting a
    // tighter budget than a desktop browser's lowers it; nothing raises it.
    maxRuntimeBytes = MAX_MORPH_RUNTIME_BYTES,
  } = options;
  const tolerance = Number(toleranceMm);
  if (!(tolerance > 0)) {
    throw new Error(`morph deformTolerance must be a positive number of millimetres, got ${toleranceMm}`);
  }
  const warnings = [];
  const overrides = new Map();
  const channels = [];
  if (!deformations?.size) {
    return { overrides, channels, warnings, stats: null };
  }

  // Descriptor order, never Map order: the file's bytes must not depend on which
  // occurrence the clip happened to touch first.
  const jobs = [];
  const missing = [];
  for (const occurrence of descriptor.occurrences || []) {
    const cid = String(occurrence.component || "");
    const occurrenceId = String(occurrence.id || cid);
    const entry = deformations.get(occurrenceId);
    if (!entry) {
      continue;
    }
    const tessellation = componentTessellations.get(cid);
    if (!tessellation || !(tessellation.positions?.length)) {
      missing.push(occurrenceId);
      continue;
    }
    jobs.push({ occurrence, occurrenceId, tessellation, entry });
  }
  if (missing.length) {
    warnings.push(
      `${summarize(missing)} deforms in this clip but tessellated to nothing, so the file `
      + "carries no geometry to morph for it"
    );
  }
  if (!jobs.length) {
    return { overrides, channels, warnings, stats: null };
  }

  // PHASE A — prepare and fit every tube, allocating no deltas. The fit is the
  // expensive half in CPU and the cheap half in memory, and doing all of it first is
  // what lets the refusal below quote the real total rather than the part of it that
  // fit before the ceiling was hit.
  const prepared = [];
  let runtimeBytes = 0;
  for (const job of jobs) {
    const first = job.entry.samples[0].deformation;
    const { geometry, triangleRange } = occurrenceWorldGeometry(job.occurrence, job.tessellation);
    const bake = prepareTubeBake(TUBE_THREE, geometry, compileDeformation(first), IDENTITY);
    // A grid sample the clip did not deform is the tube at REST for that moment,
    // which is a pose like any other: posing the rest path against itself reproduces
    // the rest surface exactly, because that is what the mapping decomposed. A SPEC,
    // like every other pose here, so nothing in the grid holds a compiled path.
    const restPose = {
      restSpec: first.restSpec,
      pathSpec: first.restSpec,
      twistDeg: 0,
      maxSegmentLength: first.maxSegmentLength,
      braid: first.braid,
    };
    const poses = new Array(grid.count).fill(restPose);
    for (const sample of job.entry.samples) {
      poses[sample.index] = sample.deformation;
    }
    const model = boundsForFractions(bake.mapping);
    const keys = fitTargetTimes(poses, model, tolerance);
    const vertexCount = bake.vertexCount;
    prepared.push({ ...job, bake, model, poses, keys, triangleRange, vertexCount });
    // Conservative: normals may still be dropped below, and a ceiling that assumed
    // they would be would refuse nothing and then allocate twice what it promised.
    runtimeBytes += vertexCount * Math.max(0, keys.length - 1) * 2 * RUNTIME_BYTES_PER_TEXEL;
  }

  if (runtimeBytes > Math.min(maxRuntimeBytes, MAX_MORPH_RUNTIME_BYTES)) {
    const targets = prepared.reduce((sum, job) => sum + Math.max(0, job.keys.length - 1), 0);
    const vertices = prepared.reduce((sum, job) => sum + job.vertexCount, 0);
    throw new Error(
      `clip ${clipId} needs ${targets} morph targets over ${prepared.length} tubes `
      + `(${vertices} refined vertices) to hold ${tolerance}mm, which is `
      + `${formatBytes(runtimeBytes)} of morph texture at playback — past the `
      + `${formatBytes(Math.min(maxRuntimeBytes, MAX_MORPH_RUNTIME_BYTES))} ceiling, and it is the GPU number rather than `
      + "the file size that decides whether the file opens. Raise deformTolerance (the target "
      + "count falls as its square root), shorten seconds, coarsen --mesh-tolerance so the "
      + "tubes carry fewer vertices, or coarsen the clip's own maxSegmentLength"
    );
  }

  // PHASE B — pose the keys, subtract the base, partition and compact.
  const stats = {
    toleranceMm: tolerance,
    nodes: 0,
    targets: 0,
    bytes: 0,
    runtimeBytes: 0,
    refinedTriangles: 0,
    deviationMm: 0,
    normalsOmitted: [],
  };
  for (const job of prepared) {
    const { bake, poses, keys, vertexCount, occurrenceId } = job;
    const posed = new Float32BufferAttribute(new Float32Array(vertexCount * 3), 3);
    const posedNormals = new Float32BufferAttribute(new Float32Array(vertexCount * 3), 3);

    poseTubeBake(TUBE_THREE, bake, compileDeformation(poses[keys[0]]), IDENTITY, posed, posedNormals);
    const basePositions = Float32Array.from(posed.array);
    const baseNormals = Float32Array.from(posedNormals.array);

    // A strided handful of REFINED vertices, kept as the poser wrote them. Nothing
    // downstream derives these from the deltas, so carrying them into the file's own
    // space is an independent answer to "where should this vertex be" — the one thing
    // that catches a bake which is self-consistent and wrong.
    const referenceIds = verifySampleIds(vertexCount);

    // Uncompacted, over the whole refined mesh, and only for the life of this
    // occurrence: the verification below needs every key at once, and compaction
    // needs the partitions, which need the geometry rather than the poses.
    const deltaPositions = [];
    const deltaNormals = [];
    const referencePosed = [];
    let normalDegrees = 0;
    for (let key = 1; key < keys.length; key += 1) {
      poseTubeBake(TUBE_THREE, bake, compileDeformation(poses[keys[key]]), IDENTITY, posed, posedNormals);
      const dp = new Float32Array(vertexCount * 3);
      const dn = new Float32Array(vertexCount * 3);
      for (let i = 0; i < dp.length; i += 1) {
        dp[i] = posed.array[i] - basePositions[i];
        dn[i] = posedNormals.array[i] - baseNormals[i];
      }
      deltaPositions.push(dp);
      deltaNormals.push(dn);
      referencePosed.push(gather(posed.array, referenceIds));
      normalDegrees = Math.max(normalDegrees, maxNormalDegrees(baseNormals, posedNormals.array));
    }
    const bakeNormals = normalDegrees >= MORPH_NORMAL_OMIT_DEGREES;
    if (!bakeNormals && deltaPositions.length) {
      stats.normalsOmitted.push(occurrenceId);
    }

    // A target whose delta is identically zero is a full texture layer and a full
    // copy of the mesh that says nothing. Its KEY still exists — its weight row is
    // simply all zeros, which is the base shape, which is what that key's pose is.
    const targetOfKey = new Int32Array(keys.length).fill(-1);
    const emitted = [];
    for (let key = 1; key < keys.length; key += 1) {
      const dp = deltaPositions[key - 1];
      let moves = false;
      for (let i = 0; i < dp.length; i += 1) {
        if (dp[i] !== 0) {
          moves = true;
          break;
        }
      }
      if (!moves) {
        continue;
      }
      targetOfKey[key] = emitted.length;
      emitted.push(key - 1);
    }

    const deviation = verifyMorphFit(job, {
      basePositions,
      deltaPositions,
      grid,
      tolerance,
      posed,
      posedNormals,
    });
    stats.deviationMm = Math.max(stats.deviationMm, deviation);

    const rangeColors = occurrenceFaceRangeColors(
      descriptor, job.occurrence, job.tessellation, defaultColor || undefined,
    );
    const material = occurrenceMaterial(job.occurrence.material);
    const partitions = partitionByColor(bake, job.triangleRange, rangeColors);
    const primitives = partitions.map((partition) => {
      const vertexIds = partition.vertexIds;
      const targets = emitted.map((slot) => ({
        positionDeltas: gather(deltaPositions[slot], vertexIds),
        ...(bakeNormals ? { normalDeltas: gather(deltaNormals[slot], vertexIds) } : {}),
      }));
      // Whichever of the reference vertices this colour ended up owning, expressed in
      // the primitive's own compacted numbering — so the check below also fails if
      // compaction put a vertex somewhere else.
      const localSlots = [];
      const localSamples = [];
      referenceIds.forEach((refined, sample) => {
        const slot = partition.slotOf.get(refined);
        if (slot !== undefined) {
          localSlots.push(slot);
          localSamples.push(sample);
        }
      });
      return {
        color: partition.color,
        positions: gather(basePositions, vertexIds),
        normals: gather(baseNormals, vertexIds),
        indices: partition.indices,
        ...(material === null ? {} : { material }),
        ...(targets.length ? { targets } : {}),
        // The reconstruction reference, in CAD millimetres, straight out of the
        // poser. packageMeshExport carries it across the basis change with its own
        // literal and checks the file's own base + delta reproduces it; see
        // verifyMorphReconstruction.
        ...(targets.length && localSlots.length ? {
          verify: {
            vertexIds: Uint32Array.from(localSlots),
            posed: emitted.map((slot) => {
              const source = referencePosed[slot];
              const reference = new Float32Array(localSamples.length * 3);
              localSamples.forEach((sample, ordinal) => {
                reference[ordinal * 3] = source[sample * 3];
                reference[ordinal * 3 + 1] = source[sample * 3 + 1];
                reference[ordinal * 3 + 2] = source[sample * 3 + 2];
              });
              return reference;
            }),
          },
        } : {}),
      };
    });
    overrides.set(occurrenceId, primitives);

    stats.nodes += 1;
    stats.targets += emitted.length;
    stats.refinedTriangles += Math.floor(bake.geometry.index.count / 3);
    for (const primitive of primitives) {
      const vertices = primitive.positions.length / 3;
      stats.bytes += vertices * emitted.length * (bakeNormals ? 24 : 12);
      stats.runtimeBytes += vertices * emitted.length * (bakeNormals ? 2 : 1) * RUNTIME_BYTES_PER_TEXEL;
    }

    if (emitted.length) {
      const times = new Float32Array(keys.length);
      const weights = new Float32Array(keys.length * emitted.length);
      for (let key = 0; key < keys.length; key += 1) {
        times[key] = keys[key] / grid.hz;
        if (targetOfKey[key] >= 0) {
          // ONE-HOT, never cumulative: at most two targets have a nonzero influence
          // at any instant, so a loader with a fixed morph-slot budget that keeps the
          // largest influences renders this EXACTLY rather than approximately.
          weights[key * emitted.length + targetOfKey[key]] = 1;
        }
      }
      channels.push({ node: occurrenceId, times, weights, targetCount: emitted.length });
    }
  }

  if (stats.normalsOmitted.length) {
    warnings.push(
      `${summarize(stats.normalsOmitted)} turns by less than ${MORPH_NORMAL_OMIT_DEGREES}° over `
      + "this clip, so its morph targets carry positions only and its shading rides the base normals"
    );
  }
  return { overrides, channels, warnings, stats };
}

/** The fit's tolerance, re-checked against the EXACT poser over every vertex.
 *
 * Redundant by design. The corner bound in fitTargetTimes is the authority — it
 * bounds every vertex at every grid sample, including the ones between vertices —
 * and this is the independent second opinion: real poses, real vertices, the real
 * weight schedule, at the frames a player will actually land on. Reports the
 * achieved maximum either way, so the summary states what the file is worth rather
 * than what was asked for.
 */
function verifyMorphFit(job, { basePositions, deltaPositions, grid, tolerance, posed, posedNormals }) {
  const { bake, poses, keys, occurrenceId } = job;
  if (keys.length < 2) {
    return 0;
  }
  let worst = 0;
  let cursor = 0;
  for (let sample = 0; sample < poses.length; sample += grid.multiple) {
    while (cursor + 2 < keys.length && keys[cursor + 1] <= sample) {
      cursor += 1;
    }
    const low = keys[cursor];
    const high = keys[cursor + 1];
    const alpha = high === low ? 0 : (sample - low) / (high - low);
    poseTubeBake(TUBE_THREE, bake, compileDeformation(poses[sample]), IDENTITY, posed, posedNormals);
    // `deltaPositions[k]` belongs to key `k + 1`; key 0 is the base and has none. A
    // key whose target was dropped for being identically zero blends the same either
    // way, which is why it can be dropped at all.
    const lowDelta = cursor >= 1 ? deltaPositions[cursor - 1] : null;
    const highDelta = deltaPositions[cursor];
    for (let i = 0; i < basePositions.length; i += 3) {
      let distance = 0;
      for (let axis = 0; axis < 3; axis += 1) {
        const blended = basePositions[i + axis]
          + (lowDelta ? lowDelta[i + axis] * (1 - alpha) : 0)
          + (highDelta ? highDelta[i + axis] * alpha : 0);
        const difference = posed.array[i + axis] - blended;
        distance += difference * difference;
      }
      if (distance > worst) {
        worst = distance;
      }
    }
  }
  worst = Math.sqrt(worst);
  // A micron of slack for the float32 the file actually stores; the bound itself is
  // exact, so anything past this is a bug rather than rounding.
  if (worst > tolerance + 1e-3) {
    throw new Error(
      `morph fit for ${occurrenceId} leaves ${worst.toFixed(4)}mm between the baked targets and `
      + `the clip's own deformation, past the ${tolerance}mm it was fitted to`
    );
  }
  return worst;
}
