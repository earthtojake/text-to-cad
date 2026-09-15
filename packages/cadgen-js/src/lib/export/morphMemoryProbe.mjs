// The morph bake, run under a heap V8 will not let it exceed.
//
// A retention regression here is not a slow test, it is a dead export: the bake
// that motivated this probe reached 4.08 GB and died before it wrote a byte,
// because the fit grid held every sample's COMPILED path (arc-length tables,
// transported frames, hundreds of KB each) instead of the numbers that describe
// it. Peak retention has to be set by the ONE tube being posed, not by the tube
// count times the grid length — so this poses one big tube and five small ones over
// a long grid, under a `--max-old-space-size` the caller sets well below what a
// retained grid needs and well above what the big tube does. Surviving IS the
// assertion; the numbers printed at the end let the caller state the margin.
//
// Run by packageTubeMorph.test.js, never imported. Requires --expose-gc.

import v8 from "node:v8";

import { normalizeAnimationClips } from "../../common/animationRuntime.js";
import { resolveFramePlan } from "../../common/framePlan.js";
import { compileTubePath } from "../../common/tubeDeformation.js";
import { sampleClipAnimation } from "./packageAnimation.js";
import { buildTubeMorphTargets } from "./packageTubeMorph.js";

// Fixed, not configurable: the caller's heap cap is chosen against THESE numbers,
// so an environment that could change them would change what the test means.
const TUBES = 6;
const BIG_RINGS = 900;
const SMALL_RINGS = 60;
const SIDES = 12;
const RADIUS = 0.6;
const SECONDS = 2;
const FPS = 12;

/** Retained bytes, after V8 has been given every chance to disagree. */
function settled() {
  for (let i = 0; i < 4; i += 1) {
    global.gc();
  }
  return v8.getHeapStatistics().used_heap_size;
}

const LEAD = 10;
const SPAN = 12;
const BENDS = 6;
const LENGTH = LEAD + BENDS * SPAN * 2;

/** A cord: a lead-in line, then `BENDS` tangent-continuous cubics alternating by
 *  `bend` degrees. Beziers are the point — a line or an arc compiles to a handful
 *  of numbers, while a Bezier compiles to the arc-length table this is about. */
function cord(bend) {
  const segments = [{ kind: "line", start: [0, 0, 0], end: [LEAD, 0, 0] }];
  let point = [LEAD, 0, 0];
  let tangent = [1, 0, 0];
  for (let index = 0; index < BENDS; index += 1) {
    const turn = (bend * (index % 2 ? -1 : 1) * Math.PI) / 180;
    const next = [
      Math.cos(turn) * tangent[0] - Math.sin(turn) * tangent[1],
      Math.sin(turn) * tangent[0] + Math.cos(turn) * tangent[1],
      0,
    ];
    const mid = point.map((value, axis) => value + tangent[axis] * SPAN);
    const end = mid.map((value, axis) => value + next[axis] * SPAN);
    segments.push({
      kind: "bezier",
      points: [
        point,
        point.map((value, axis) => value + tangent[axis] * SPAN * 0.5),
        end.map((value, axis) => value - next[axis] * SPAN * 0.5),
        end,
      ],
    });
    point = end;
    tangent = next;
  }
  return { normal: [0, 0, 1], segments };
}

const REST = { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [LENGTH, 0, 0] }] };

/** A straight cylinder along +X, as a component tessellation. */
function tube(rings) {
  const positions = new Float32Array(rings * SIDES * 3);
  const normals = new Float32Array(rings * SIDES * 3);
  for (let ring = 0; ring < rings; ring += 1) {
    const x = (ring / (rings - 1)) * LENGTH;
    for (let side = 0; side < SIDES; side += 1) {
      const angle = (side / SIDES) * Math.PI * 2;
      const i = (ring * SIDES + side) * 3;
      positions[i] = x;
      positions[i + 1] = Math.cos(angle) * RADIUS;
      positions[i + 2] = Math.sin(angle) * RADIUS;
      normals[i + 1] = Math.cos(angle);
      normals[i + 2] = Math.sin(angle);
    }
  }
  const indices = new Uint32Array((rings - 1) * SIDES * 6);
  let write = 0;
  for (let ring = 0; ring + 1 < rings; ring += 1) {
    for (let side = 0; side < SIDES; side += 1) {
      const a = ring * SIDES + side;
      const b = ring * SIDES + ((side + 1) % SIDES);
      indices[write++] = a;
      indices[write++] = b;
      indices[write++] = a + SIDES;
      indices[write++] = b;
      indices[write++] = b + SIDES;
      indices[write++] = a + SIDES;
    }
  }
  return {
    positions,
    normals,
    indices,
    faceRanges: [{ indexStart: 0, indexCount: indices.length, color: [0.35, 0.32, 0.3, 1] }],
    partColor: null,
  };
}

const ids = Array.from({ length: TUBES }, (unused, index) => `o1.${index + 1}`);
const descriptor = {
  kind: "assembly-package",
  components: Object.fromEntries(ids.map((id) => [`c_${id}`, {}])),
  occurrences: ids.map((id) => ({ id, name: id, component: `c_${id}` })),
};
const tessellations = new Map(ids.map((id, index) => [`c_${id}`, tube(index ? SMALL_RINGS : BIG_RINGS)]));

const clip = normalizeAnimationClips({
  flex: {
    duration: SECONDS,
    loop: true,
    // Every tube bends on its own schedule, so no two share a pose and nothing in
    // here is deduplicated by accident.
    update: (t, m) => {
      ids.forEach((id, index) => {
        m.get(id).deformTube({
          rest: REST,
          path: cord(6 * Math.sin(((t / SECONDS) + index / TUBES) * Math.PI * 2)),
          maxSegmentLength: 1000,
        });
      });
    },
  },
}).flex;

const plan = resolveFramePlan({ clip: "flex", fps: FPS, seconds: SECONDS }, clip, { label: "animation" });

// One compiled path for the shape every tube is posed onto: the unit this probe
// measures peak retention in.
const floor = settled();
const compiled = compileTubePath(cord(6));
const onePathBytes = settled() - floor;
const tableEntries = compiled.segments.reduce((sum, segment) => sum + (segment.table?.length || 0), 0);

const beforeSample = settled();
const sampled = sampleClipAnimation(descriptor, clip, plan, { deform: "morph" });
const afterSample = settled();

const tubeSamples = [...sampled.deformations.values()].reduce((sum, entry) => sum + entry.samples.length, 0);
const morph = buildTubeMorphTargets(descriptor, tessellations, sampled.deformations, {
  grid: sampled.grid,
  clipId: sampled.name,
  toleranceMm: 1,
});

process.stdout.write(`${JSON.stringify({
  tubes: TUBES,
  gridCount: sampled.grid.count,
  tubeSamples,
  tableEntries,
  onePathBytes,
  sampleRetainedBytes: afterSample - beforeSample,
  heapLimitBytes: v8.getHeapStatistics().heap_size_limit,
  targets: morph.stats.targets,
  nodes: morph.stats.nodes,
})}\n`);
