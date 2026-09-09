// Baking a clip's tube deformation into morph targets, tested where a bake can
// be self-consistent and wrong:
//
//   - the ANTI-FORK check. The whole design rests on the exporter driving the
//     viewer's own deformation rather than re-deriving it, so the first test
//     asserts `base + delta` reproduces what applyRecordTubeDeformation puts on
//     screen, vertex for vertex. If that ever fails, the two have forked.
//   - the FIT. Morph weights blend the RESULT of two poses while the clip blends
//     its inputs, so the tolerance is a claim about the motion BETWEEN targets,
//     which is exactly where a per-keyframe bake goes quietly wrong.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

import * as THREE from "three";

import { normalizeAnimationClips } from "../../common/animationRuntime.js";
import { resolveFramePlan } from "../../common/framePlan.js";
import { applyRecordTubeDeformation, normalizeTubeDeformation } from "../../common/tubeDeformation.js";
import { buildPackageMeshPrimitives } from "./packageMeshExport.js";
import { sampleClipAnimation } from "./packageAnimation.js";
import { MAX_MORPH_RUNTIME_BYTES, buildTubeMorphTargets } from "./packageTubeMorph.js";

const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const LENGTH = 40;
const RADIUS = 2;

const REST = {
  normal: [0, 0, 1],
  segments: [{ kind: "line", start: [0, 0, 0], end: [LENGTH, 0, 0] }],
};

/** A bent centerline: straight lead-in, then an arc of `sweepDeg`. */
function bent(sweepDeg) {
  if (Math.abs(sweepDeg) < 1e-9) return REST;
  const lead = LENGTH * 0.25;
  const radius = (LENGTH - lead) / (Math.abs(sweepDeg) * Math.PI / 180);
  const sign = Math.sign(sweepDeg);
  return {
    normal: [0, 0, 1],
    segments: [
      { kind: "line", start: [0, 0, 0], end: [lead, 0, 0] },
      { kind: "arc", center: [lead, sign * radius, 0], axis: [0, 0, 1], start: [lead, 0, 0], sweepDeg },
    ],
  };
}

/** A cylinder along +X as a component tessellation, split into two face ranges
 *  so the bake has to partition by colour the way a real body does. */
function tubeTessellation({ rings = 21, sides = 12 } = {}) {
  const positions = [];
  const normals = [];
  for (let ring = 0; ring < rings; ring += 1) {
    const x = (ring / (rings - 1)) * LENGTH;
    for (let side = 0; side < sides; side += 1) {
      const angle = (side / sides) * Math.PI * 2;
      positions.push(x, Math.cos(angle) * RADIUS, Math.sin(angle) * RADIUS);
      normals.push(0, Math.cos(angle), Math.sin(angle));
    }
  }
  const indices = [];
  for (let ring = 0; ring + 1 < rings; ring += 1) {
    for (let side = 0; side < sides; side += 1) {
      const a = ring * sides + side;
      const b = ring * sides + ((side + 1) % sides);
      indices.push(a, b, a + sides, b, b + sides, a + sides);
    }
  }
  const half = Math.floor(indices.length / 6) * 3;
  return {
    positions: Float32Array.from(positions),
    normals: Float32Array.from(normals),
    indices: Uint32Array.from(indices),
    faceRanges: [
      { indexStart: 0, indexCount: half, color: [0.8, 0.2, 0.1, 1] },
      { indexStart: half, indexCount: indices.length - half, color: [0.1, 0.2, 0.8, 1] },
    ],
    partColor: null,
  };
}

const DESCRIPTOR = {
  kind: "assembly-package",
  components: { c0: { surf: "components/c0.surf" } },
  occurrences: [
    { id: "o1.1", name: "block", component: "c1", transform: IDENTITY },
    { id: "o1.2", name: "tendon", component: "c0", transform: IDENTITY },
  ],
};

function tessellations(entry = tubeTessellation()) {
  return new Map([["c0", entry], ["c1", entry]]);
}

function bake(update, request = { fps: 12, seconds: 1 }, options = {}) {
  const clip = normalizeAnimationClips({ flex: { duration: 2, loop: true, update } }).flex;
  const plan = resolveFramePlan(request, clip, { label: "animation" });
  const sampled = sampleClipAnimation(DESCRIPTOR, clip, plan, { deform: "morph" });
  const maps = options.tessellations || tessellations();
  const morph = buildTubeMorphTargets(DESCRIPTOR, maps, sampled.deformations, {
    grid: sampled.grid,
    clipId: sampled.name,
    ...options,
  });
  return { clip, plan, sampled, morph, maps };
}

/** The viewer's own answer for the same occurrence at the same moment. */
function renderModulePositions(tessellation, deformation) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(Float32Array.from(tessellation.positions), 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(Float32Array.from(tessellation.normals), 3));
  geometry.setIndex(new THREE.BufferAttribute(Uint32Array.from(tessellation.indices), 1));
  const record = {
    mesh: { geometry, material: { userData: {} }, userData: {} },
    material: { userData: {} },
  };
  applyRecordTubeDeformation(THREE, record, deformation);
  const position = record.mesh.geometry.attributes.position;
  const out = new Float32Array(position.count * 3);
  for (let i = 0; i < position.count; i += 1) {
    out[i * 3] = position.getX(i);
    out[i * 3 + 1] = position.getY(i);
    out[i * 3 + 2] = position.getZ(i);
  }
  return out;
}

/** Nearest-neighbour distance from every point of `a` to the cloud `b`, in mm. */
function cloudDistance(a, b) {
  let worst = 0;
  for (let i = 0; i < a.length; i += 3) {
    let best = Infinity;
    for (let j = 0; j < b.length; j += 3) {
      const d = (a[i] - b[j]) ** 2 + (a[i + 1] - b[j + 1]) ** 2 + (a[i + 2] - b[j + 2]) ** 2;
      if (d < best) best = d;
    }
    if (best > worst) worst = best;
  }
  return Math.sqrt(worst);
}

const flex = (sweep) => (t, m) => m.get("tendon").deformTube({
  rest: REST,
  path: bent(sweep * Math.sin((t / 2) * Math.PI * 2)),
  maxSegmentLength: 2,
});

test("base + delta IS what the render module draws: the bake does not fork the deformation", () => {
  const { morph, sampled, maps } = bake(flex(60));
  const primitives = morph.overrides.get("o1.2");
  assert.ok(primitives?.length, "the deforming occurrence has prepared primitives");

  const entry = sampled.deformations.get("o1.2");
  // Every KEY the fit chose, checked against the viewer's own deformation at that
  // exact moment — the targets are supposed to be exact there, by construction.
  const times = morph.channels[0].times;
  for (let key = 1; key < times.length; key += 1) {
    const gridIndex = Math.round(times[key] * sampled.grid.hz);
    // The deformation the CLIP produced at that moment, pushed through the
    // viewer's own display entry point. Nothing here is reconstructed.
    const reference = renderModulePositions(maps.get("c0"), entry.samples[gridIndex].deformation);
    for (const primitive of primitives) {
      const rebuilt = new Float32Array(primitive.positions.length);
      const deltas = primitive.targets[key - 1].positionDeltas;
      for (let i = 0; i < rebuilt.length; i += 1) {
        rebuilt[i] = primitive.positions[i] + deltas[i];
      }
      assert.ok(
        cloudDistance(rebuilt, reference) < 1e-3,
        `key ${key}: rebuilt vertices are ${cloudDistance(rebuilt, reference)}mm off the render module's`,
      );
    }
  }
});

test("the fit tolerance is a claim about the motion BETWEEN targets, and a tighter one costs more", () => {
  const loose = bake(flex(60), { fps: 12, seconds: 1 }, { toleranceMm: 4 });
  const tight = bake(flex(60), { fps: 12, seconds: 1 }, { toleranceMm: 0.25 });
  assert.ok(loose.morph.stats.targets >= 1, "a moving tube gets targets");
  assert.ok(
    tight.morph.stats.targets > loose.morph.stats.targets,
    `0.25mm (${tight.morph.stats.targets}) must cost more targets than 4mm (${loose.morph.stats.targets})`,
  );
  assert.ok(loose.morph.stats.deviationMm <= 4 + 1e-3, `loose deviation ${loose.morph.stats.deviationMm}`);
  assert.ok(tight.morph.stats.deviationMm <= 0.25 + 1e-3, `tight deviation ${tight.morph.stats.deviationMm}`);
  // ...and the tolerance is not merely respected, it is APPROACHED: a fit that
  // emitted a target per grid sample would also pass the bound above.
  assert.ok(loose.morph.stats.deviationMm > 0.25, "the loose fit really is looser");
});

test("targets are one-hot: at most two influences at any instant", () => {
  const { morph } = bake(flex(60));
  const [channel] = morph.channels;
  assert.equal(channel.node, "o1.2");
  assert.equal(channel.weights.length, channel.times.length * channel.targetCount);
  for (let key = 0; key < channel.times.length; key += 1) {
    const row = channel.weights.subarray(key * channel.targetCount, (key + 1) * channel.targetCount);
    const nonzero = [...row].filter((value) => value !== 0);
    assert.ok(nonzero.length <= 1, `key ${key} has ${nonzero.length} nonzero weights`);
    if (nonzero.length) assert.equal(nonzero[0], 1);
  }
  // Key 0 is the BASE shape, never a target: emitting it would cost a full copy
  // of the mesh and a texture layer to say "no change".
  assert.deepEqual([...channel.weights.subarray(0, channel.targetCount)], new Array(channel.targetCount).fill(0));
  assert.equal(channel.times[0], 0);
});

test("a tube the clip holds still gets its posed shape and NO targets", () => {
  // Held at a constant bend: the file must still ship the bent tube (the rest
  // shape would be the silent freeze this mode exists to prevent) and must not
  // spend a single target saying it does not move.
  const { morph } = bake((t, m) => m.get("tendon").deformTube({
    rest: REST, path: bent(30), maxSegmentLength: 2,
  }));
  assert.equal(morph.channels.length, 0, "no weights channel for a tube that does not move");
  assert.equal(morph.stats.targets, 0);
  const primitives = morph.overrides.get("o1.2");
  // The base is the BENT tube, not the straight one it was tessellated as.
  const reference = renderModulePositions(
    tubeTessellation(), normalizeTubeDeformation({ rest: REST, path: bent(30), maxSegmentLength: 2 }),
  );
  let maxY = 0;
  for (const primitive of primitives) {
    assert.equal(primitive.targets, undefined);
    assert.ok(cloudDistance(primitive.positions, reference) < 1e-3);
    for (let i = 1; i < primitive.positions.length; i += 3) {
      maxY = Math.max(maxY, Math.abs(primitive.positions[i]));
    }
  }
  assert.ok(maxY > RADIUS * 2, `the shipped tube is bent, not straight (max |y| = ${maxY})`);
});

test("the deforming occurrence's colours survive as separate primitives", () => {
  const { morph } = bake(flex(60));
  const primitives = morph.overrides.get("o1.2");
  assert.equal(primitives.length, 2, "two face-range colours, two primitives");
  assert.deepEqual(primitives.map((primitive) => primitive.color).sort(), ["#597ce7", "#e77c59"]);
  for (const primitive of primitives) {
    assert.ok(primitive.indices instanceof Uint32Array, "overrides are indexed, never welded");
    assert.equal(primitive.positions.length, primitive.normals.length);
    for (const target of primitive.targets) {
      assert.equal(target.positionDeltas.length, primitive.positions.length);
      assert.equal(target.normalDeltas.length, primitive.positions.length);
      // Every index has to be inside the primitive's OWN compacted vertex table.
      for (const index of primitive.indices) {
        assert.ok(index < primitive.positions.length / 3, `index ${index} out of range`);
      }
    }
  }
});

test("a tube that barely turns ships positions only, and says which", () => {
  const { morph } = bake(flex(0.4));
  assert.deepEqual(morph.stats.normalsOmitted, ["o1.2"]);
  assert.match(morph.warnings.join("\n"), /turns by less than 5° over this clip/);
  for (const primitive of morph.overrides.get("o1.2")) {
    for (const target of primitive.targets || []) {
      assert.equal(target.normalDeltas, undefined);
    }
  }
});

test("the ceiling is on PLAYBACK memory, and the refusal names the levers", () => {
  assert.throws(
    () => bake(flex(60), { fps: 12, seconds: 1 }, { toleranceMm: 0.05, maxRuntimeBytes: 64 * 1024 }),
    (error) => {
      assert.match(error.message, /morph texture at playback/);
      assert.match(error.message, /Raise deformTolerance/);
      assert.match(error.message, /coarsen --mesh-tolerance/);
      return true;
    },
  );
  assert.equal(MAX_MORPH_RUNTIME_BYTES, 512 * 1024 * 1024);
});

test("the bake is deterministic and lands at the occurrence's own place in the file", () => {
  const first = bake(flex(60));
  const second = bake(flex(60));
  const serialize = (morph) => [...morph.overrides].map(([id, primitives]) => [
    id,
    primitives.map((primitive) => [
      primitive.color,
      [...primitive.indices].join(","),
      [...primitive.positions].join(","),
      (primitive.targets || []).map((target) => [...target.positionDeltas].join(",")).join("|"),
    ]),
  ]);
  assert.deepEqual(serialize(first.morph), serialize(second.morph));

  // Spliced at the occurrence's own ordinal: the block is occurrence 0 and the
  // tendon occurrence 1, so the file's node order does not depend on which of
  // them deformed.
  const mesh = buildPackageMeshPrimitives(DESCRIPTOR, first.maps, {
    perOccurrence: true,
    occurrenceOverrides: first.morph.overrides,
  });
  const nodes = mesh.primitives.map((primitive) => primitive.node);
  assert.equal(nodes[0], "o1.1");
  assert.deepEqual([...new Set(nodes)], ["o1.1", "o1.2"]);
  for (const primitive of mesh.primitives.filter((p) => p.node === "o1.2")) {
    assert.ok(primitive.targets?.length, "the override kept its targets through the primitive build");
    assert.equal(primitive.name, "tendon");
    assert.equal(primitive.occurrenceId, "o1.2");
  }
});

test("occurrenceOverrides without perOccurrence is refused rather than silently dropped", () => {
  assert.throws(
    () => buildPackageMeshPrimitives(DESCRIPTOR, tessellations(), {
      occurrenceOverrides: new Map([["o1.2", []]]),
    }),
    /occurrenceOverrides needs perOccurrence/,
  );
});

// A heap the probe clears with room to spare and a bake that retains its grid
// cannot fit in at all. Measured: the probe finishes under 48MB; the retention this
// test exists to prevent needs 312MiB for the same six tubes and still dies given
// 256MB. Nothing in between is close enough to either side to be a coin toss.
const MEMORY_PROBE_HEAP_MB = 160;

// One grid's whole retention, expressed in compiled paths of the shape being posed.
// Peak has to be set by the tube in hand — a few paths live at once — rather than by
// tubes x grid samples, which is two per sample and is what filled 4 GB.
const MEMORY_PROBE_MAX_PATHS_RETAINED = 32;

test("peak retention is set by the biggest tube, not by the tube count times the grid", () => {
  // Measured in a child, because the assertion is about a resource this process
  // cannot constrain for itself: the bake runs under a heap V8 enforces, and
  // finishing at all is half the claim. See morphMemoryProbe.mjs.
  const probe = fileURLToPath(new URL("./morphMemoryProbe.mjs", import.meta.url));
  const child = spawnSync(
    process.execPath,
    ["--expose-gc", `--max-old-space-size=${MEMORY_PROBE_HEAP_MB}`, probe],
    // NODE_OPTIONS out of the way: a developer who raised the heap for their own
    // work would otherwise be running a different test from CI, and this one is
    // ABOUT the heap.
    { encoding: "utf8", env: { ...process.env, NODE_OPTIONS: "" } },
  );
  assert.equal(
    child.status,
    0,
    `the bake did not survive a ${MEMORY_PROBE_HEAP_MB}MB heap:\n${child.stderr?.slice(-2000) || ""}`,
  );
  const report = JSON.parse(child.stdout.trim().split("\n").at(-1));

  // The probe has to be posing something worth measuring: a long grid, several
  // tubes, and paths whose compiled form is an arc-length table rather than a
  // handful of numbers.
  assert.ok(report.tubeSamples >= 1000, `only ${report.tubeSamples} tube-samples`);
  assert.ok(report.tableEntries >= 500, `only ${report.tableEntries} table entries per path`);
  assert.ok(report.targets > 0, "the probe's tubes actually moved");
  assert.ok(
    report.heapLimitBytes < MEMORY_PROBE_HEAP_MB * 3 * 1024 * 1024,
    `the cap did not apply: heap limit ${report.heapLimitBytes}`,
  );

  const paths = report.sampleRetainedBytes / report.onePathBytes;
  assert.ok(
    paths < MEMORY_PROBE_MAX_PATHS_RETAINED,
    `${report.tubeSamples} tube-samples retain ${(report.sampleRetainedBytes / 1024 ** 2).toFixed(1)}MiB, `
    + `which is ${paths.toFixed(0)} compiled paths of the shape they pose — a grid that holds its `
    + "compiled paths holds two per sample, and that is the export that ran out of memory",
  );
});
