// Sampling a clip into glTF node tracks, tested where the translation between
// the two systems can go quietly wrong:
//
//   - the CHANGE OF BASIS. Vertices leave a package rotated into Y-up metres;
//     a clip's matrix is authored in the Z-up millimetres they left. A rotation
//     about a pivot is the case that fails loudest if the conjugation is wrong
//     and silently if only the translation half is — hence a non-origin pivot,
//     checked on BOTH halves.
//   - what glTF cannot carry. Every refusal here is a file that would otherwise
//     have looked finished and moved wrong.

import assert from "node:assert/strict";
import test from "node:test";

import { normalizeAnimationClips } from "../../common/animationRuntime.js";
import { resolveFramePlan } from "../../common/framePlan.js";
import { restrictAnimationToNodes, sampleClipAnimation } from "./packageAnimation.js";

const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

const DESCRIPTOR = {
  kind: "assembly-package",
  components: { c0: { surf: "components/c0.surf" } },
  occurrences: [
    { id: "o1.1", name: "base", component: "c0", transform: IDENTITY },
    { id: "o1.2", name: "spinner", component: "c0", transform: IDENTITY },
    { id: "o1.3", name: "lid", component: "c0", transform: IDENTITY },
  ],
};

function clipsFor(update, { duration = 4, loop = true } = {}) {
  return normalizeAnimationClips({ showcase: { duration, loop, update } }).showcase;
}

function sample(update, request = { fps: 10, seconds: 2 }, options = {}, clipOptions = {}) {
  const clip = clipsFor(update, clipOptions);
  const plan = resolveFramePlan(request, clip, { label: "animation" });
  return { plan, ...sampleClipAnimation(DESCRIPTOR, clip, plan, options) };
}

function channelFor(result, node) {
  return result.channels.find((channel) => channel.node === node) || null;
}

test("a rotation about a non-origin pivot lands as quaternion AND translation", () => {
  // 90 degrees about CAD +Z over 4s, taken about (40, 0, 0) mm. The plan's last
  // sample is t = 1.9s, so 42.75 degrees.
  const result = sample((t, m) => {
    m.get("spinner").rotate([0, 0, 1], 90 * (t / 4), [40, 0, 0]);
  });
  const channel = channelFor(result, "o1.2");
  assert.ok(channel, "the moving occurrence has a channel");

  const half = (42.75 / 2) * (Math.PI / 180);
  // CAD +Z is glTF +Y after the (x, y, z) -> (x, z, -y) change of basis, so the
  // quaternion turns about Y, not Z. Getting this wrong swings the part around
  // the wrong axis while every other assertion still passes.
  const last = channel.rotation.slice(-4);
  assert.ok(Math.abs(last[0] - 0) < 1e-6, `qx ${last[0]}`);
  assert.ok(Math.abs(last[1] - Math.sin(half)) < 1e-6, `qy ${last[1]}`);
  assert.ok(Math.abs(last[2] - 0) < 1e-6, `qz ${last[2]}`);
  assert.ok(Math.abs(last[3] - Math.cos(half)) < 1e-6, `qw ${last[3]}`);

  // The pivot is carried by the TRANSLATION half: p - R p, in metres.
  const angle = 42.75 * (Math.PI / 180);
  const pivot = 40 * 0.001;
  const expected = [pivot - (pivot * Math.cos(angle)), 0, pivot * Math.sin(angle)];
  const translation = channel.translation.slice(-3);
  for (let axis = 0; axis < 3; axis += 1) {
    assert.ok(
      Math.abs(translation[axis] - expected[axis]) < 1e-6,
      `translation[${axis}] ${translation[axis]} != ${expected[axis]}`
    );
  }
  // Rigid motion: nothing scales, so no scale channel is written at all.
  assert.equal(channel.scale, undefined);
});

test("an occurrence the clip never moves emits no channel", () => {
  const result = sample((t, m) => {
    m.get("spinner").translate([t, 0, 0]);
  });
  assert.deepEqual(result.channels.map((channel) => channel.node), ["o1.2"]);
  assert.equal(channelFor(result, "o1.1"), null);
  assert.equal(channelFor(result, "o1.3"), null);
  // ...and nothing is written on its node either, so the file's rest pose IS the
  // geometry as baked.
  assert.equal(result.rest.has("o1.1"), false);
});

test("a constant offset rides the node's own transform, not a channel of identical keys", () => {
  const result = sample((_t, m) => {
    m.get("lid").translate([0, 0, 10]);
  });
  assert.deepEqual(result.channels, []);
  const rest = result.rest.get("o1.3");
  // CAD +Z (10 mm) is glTF +Y, at 0.01 m.
  assert.deepEqual(rest.translation.map((value) => Number(value.toFixed(6))), [0, 0.01, 0]);
  assert.equal(rest.scale, null);
});

test("the time accessor IS the schedule, re-based to zero", () => {
  const result = sample(
    (t, m) => m.get("spinner").translate([t, 0, 0]),
    { fps: 12, seconds: 1.5, start: 2 }
  );
  assert.equal(result.plan.frameCount, 18);
  assert.equal(result.times.length, 18);
  // `start` picks where in the CLIP the span begins; the exported animation runs
  // from 0, so a file does not open with two seconds of nothing.
  assert.equal(result.times[0], 0);
  for (let index = 0; index < result.times.length; index += 1) {
    assert.ok(Math.abs(result.times[index] - (index / 12)) < 1e-6, `times[${index}]`);
  }
  const channel = channelFor(result, "o1.2");
  assert.equal(channel.translation.length, 18 * 3);
  // The span really started at t = 2: the first sample is the pose at 2s, not 0s.
  assert.ok(Math.abs(channel.translation[0] - (2 * 0.001)) < 1e-6);
});

test("opacity is refused by name, and dropping it bakes the value at start", () => {
  const fade = (t, m) => m.get("lid").opacity(t < 1 ? 1 : 0.25);
  assert.throws(() => sample(fade), /animates \.opacity\(\) on o1\.3/);
  assert.throws(() => sample(fade), /drop: \["opacity"\]/);

  const dropped = sample(fade, { fps: 10, seconds: 2 }, { drop: ["opacity"] });
  assert.equal(dropped.statics.opacity.get("o1.3"), 1);
  assert.equal(dropped.warnings.length, 1);
  assert.match(dropped.warnings[0], /\.opacity\(\) is not an animated glTF channel/);
});

test("visibility is refused by name, and dropping it omits what is hidden at start", () => {
  const blink = (t, m) => m.get("lid").visible(t > 1);
  assert.throws(() => sample(blink), /animates \.visible\(\) on o1\.3/);

  const dropped = sample(blink, { fps: 10, seconds: 2 }, { drop: ["visible"] });
  assert.deepEqual([...dropped.statics.hidden], ["o1.3"]);
  assert.match(dropped.warnings[0], /\.visible\(\) is not an animated glTF channel/);
});

test("a dropped effect this export cannot bake is refused rather than ignored", () => {
  assert.throws(
    () => sample((t, m) => m.get("spinner").translate([t, 0, 0]), { fps: 10, seconds: 1 },
      { drop: ["deformTube"] }),
    /droppable effects: opacity, visible/
  );
});

test("tube deformation: refused by default, collected under morph, explicit about rest", () => {
  const tendon = (t, m) => m.get("spinner").deformTube({
    rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, 0, 0] }] },
    path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, t, 0] }] },
  });
  assert.throws(() => sample(tendon), /deforms tube geometry on o1\.2/);
  assert.throws(() => sample(tendon), /deform: "morph"/);
  assert.throws(() => sample(tendon), /deform: "rest"/);

  const rest = sample(tendon, { fps: 10, seconds: 1 }, { deform: "rest" });
  assert.equal(rest.channels.length, 0);
  assert.equal(rest.deformations.size, 0, "rest mode collects nothing to bake");
  assert.match(rest.warnings[0], /ships o1\.2 at rest shape/);

  assert.throws(
    () => sample(tendon, { fps: 10, seconds: 1 }, { deform: "freeze" }),
    /deform must be one of refuse, morph, rest/
  );
});

test("morph collects the deformation on the FIT grid, not the export's frames", () => {
  const tendon = (t, m) => m.get("spinner").deformTube({
    rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, 0, 0] }] },
    path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, t, 0] }] },
  });
  const morph = sample(tendon, { fps: 24, seconds: 1 }, { deform: "morph" });
  // 24 fps x 4 = 96 Hz, the floor; 24 export frames span 23 intervals, so the
  // grid is 23 * 4 + 1 samples and every export frame is one of them.
  assert.equal(morph.grid.hz, 96);
  assert.equal(morph.grid.multiple, 4);
  assert.equal(morph.grid.count, 93);
  assert.equal(morph.times.length, 24, "the TRS schedule is still the export's own");

  const entry = morph.deformations.get("o1.2");
  assert.ok(entry, "the deforming occurrence is collected by id");
  assert.equal(entry.samples.length, 93);
  assert.equal(entry.samples[0].timeSec, 0);
  assert.ok(Math.abs(entry.samples.at(-1).timeSec - 23 / 24) < 1e-9);
  // Sampling four times finer must not move where the export's own frames fall.
  for (let frame = 0; frame < morph.times.length; frame += 1) {
    assert.ok(
      Math.abs(entry.samples[frame * 4].timeSec - morph.times[frame]) < 1e-7,
      `grid sample ${frame * 4} is export frame ${frame}`,
    );
  }
  // A low fps still measures at the 96 Hz floor rather than certifying itself.
  assert.equal(sample(tendon, { fps: 8, seconds: 1 }, { deform: "morph" }).grid.hz, 96);
});

test("a clip that re-routes a tube's REST path mid-span has no base mesh, and says so", () => {
  const reroute = (t, m) => m.get("spinner").deformTube({
    // The rest path itself moves with t: there is no one shape the targets could
    // be deltas against, and blending toward one that was never this pose's rest
    // would bend the tube through whatever it runs inside.
    rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10 + t, 0, 0] }] },
    path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10 + t, t, 0] }] },
  });
  assert.throws(
    () => sample(reroute, { fps: 10, seconds: 1 }, { deform: "morph" }),
    /changes the REST path of o1\.2/,
  );
  // Only morph needs one base mesh; "rest" ships the rest shape either way.
  assert.doesNotThrow(() => sample(reroute, { fps: 10, seconds: 1 }, { deform: "rest" }));
});

test("a braided cord under morph warns that the weave is a shader, not geometry", () => {
  const braided = (t, m) => m.get("spinner").deformTube({
    rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, 0, 0] }] },
    path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [10, t, 0] }] },
    braid: { pitch: 0.8, depth: 0.02, strands: 8 },
  });
  const morph = sample(braided, { fps: 10, seconds: 1 }, { deform: "morph" });
  assert.match(morph.warnings.join("\n"), /o1\.2 carries a braid/);
  assert.match(morph.warnings.join("\n"), /cadgen's own CAD Viewer/);
});

test("a label the tree does not carry fails here, not at playback", () => {
  assert.throws(
    () => sample((t, m) => m.get("flywheel").rotate([0, 0, 1], t)),
    /no occurrence labeled "flywheel"/
  );
});

test("quaternion samples stay in one hemisphere so a keyframe never takes the long way", () => {
  // Two and a half turns: the naive per-sample quaternion flips sign every half
  // turn, and glTF interpolates the numbers, not the rotation.
  const result = sample(
    (t, m) => m.get("spinner").rotate([0, 0, 1], 900 * (t / 4)),
    { fps: 30, seconds: 4 }
  );
  const rotation = channelFor(result, "o1.2").rotation;
  for (let index = 1; index < result.times.length; index += 1) {
    const previous = index * 4 - 4;
    const current = index * 4;
    const dot = rotation[previous] * rotation[current]
      + rotation[previous + 1] * rotation[current + 1]
      + rotation[previous + 2] * rotation[current + 2]
      + rotation[previous + 3] * rotation[current + 3];
    assert.ok(dot >= 0, `sample ${index} flipped hemisphere (dot ${dot})`);
  }
});

test("an occurrence hidden at start loses its motion too, and is told so", () => {
  // The reveal idiom, and the one shape `drop: ["visible"]` used to break on:
  // hidden at t = 0 and moving throughout. Dropping the visibility omits the
  // occurrence from the file entirely, so a channel for it would target a node
  // no primitive declared — a throw out of the glTF writer, reached by
  // following the visibility refusal's own advice.
  const reveal = (t, m) => {
    const cover = m.get("lid");
    cover.visible(t > 1);
    cover.translate([10 * t, 0, 0]);
  };
  const result = sample(reveal, { fps: 10, seconds: 2 }, { drop: ["visible"] });

  assert.deepEqual([...result.statics.hidden], ["o1.3"]);
  assert.equal(channelFor(result, "o1.3"), null, "a hidden occurrence has no channel");
  assert.equal(result.rest.has("o1.3"), false, "nor a rest pose on a node it does not have");
  assert.match(result.warnings.join("\n"), /o1\.3 moves in this clip and is hidden at start/);

  // An occurrence that is hidden and STILL is unaffected: nothing was lost, so
  // nothing is said about it beyond the effect being frozen.
  const still = sample((t, m) => m.get("lid").visible(t > 1), { fps: 10, seconds: 2 },
    { drop: ["visible"] });
  assert.equal(still.warnings.length, 1);
});

test("a channel the export has no geometry for is dropped by name, not thrown at by the writer", () => {
  const result = sample((t, m) => m.get("spinner").translate([10 * t, 0, 0]));
  assert.ok(channelFor(result, "o1.2"), "the occurrence moves");

  // What the mesh build actually produced: o1.2 tessellated to nothing, so the
  // file has no node for it.
  const narrowed = restrictAnimationToNodes(result, new Set(["o1.1", "o1.3"]));
  assert.equal(narrowed.channels.length, 0);
  assert.equal(narrowed.rest.has("o1.2"), false);
  assert.match(narrowed.warnings.at(-1), /o1\.2 moves in this clip but has no geometry/);

  // A no-op when everything a channel targets is in the file: same object back.
  assert.equal(restrictAnimationToNodes(result, new Set(["o1.1", "o1.2", "o1.3"])), result);
});

test("a track that returns to rest after passing 180 degrees stays in one hemisphere", () => {
  // 270 degrees over the first half of the clip, then untouched: the frames
  // after it stop are REST samples, and a rest sample pushed as a bare identity
  // is the one pair the hemisphere alignment used to skip.
  const result = sample(
    (t, m) => { if (t < 2) m.get("spinner").rotate([0, 0, 1], 270 * (t / 2)); },
    { fps: 5, seconds: 4 }
  );
  const rotation = channelFor(result, "o1.2").rotation;
  for (let index = 1; index < result.times.length; index += 1) {
    const previous = index * 4 - 4;
    const current = index * 4;
    const dot = rotation[previous] * rotation[current]
      + rotation[previous + 1] * rotation[current + 1]
      + rotation[previous + 2] * rotation[current + 2]
      + rotation[previous + 3] * rotation[current + 3];
    assert.ok(dot >= 0, `sample ${index} flipped hemisphere (dot ${dot})`);
  }
});

// A cord shaped like a real tendon: a lead-in line and a tangent-continuous cubic.
// Beziers are what make retention visible — a line or an arc compiles to a handful
// of numbers, a Bezier to the adaptive arc-length table this is about.
const CORD_REST = {
  normal: [0, 0, 1],
  segments: [
    { kind: "line", start: [0, 0, 0], end: [10, 0, 0] },
    { kind: "bezier", points: [[10, 0, 0], [20, 0, 0], [30, 0, 0], [40, 0, 0]] },
  ],
};

const cordAt = (lift) => ({
  normal: [0, 0, 1],
  segments: [
    { kind: "line", start: [0, 0, 0], end: [10, 0, 0] },
    { kind: "bezier", points: [[10, 0, 0], [20, 0, 0], [30, lift, 0], [40, lift, 0]] },
  ],
});

test("the fit grid retains a deformation's NUMBERS, never the paths they compile to", () => {
  // The defect this guards: one 6-second clip over 48 tubes is 27,504 samples, and
  // a sample that holds its two COMPILED paths holds two adaptive arc-length tables
  // — hundreds of KB each. The grid stopped being a schedule and became the model,
  // 48 times over, and the export died at the heap limit before writing a byte.
  const result = sample(
    (t, m) => m.get("spinner").deformTube({ rest: CORD_REST, path: cordAt(3 * Math.sin(t)) }),
    { fps: 12, seconds: 1 },
    { deform: "morph" },
  );
  const entry = result.deformations.get("o1.2");
  assert.ok(result.grid.hz >= 96 && result.grid.count > 80, `grid ${JSON.stringify(result.grid)}`);
  assert.equal(entry.samples.length, result.grid.count, "every grid sample deforms this tube");
  for (const sample of entry.samples) {
    const deformation = sample.deformation;
    assert.equal(deformation.rest, undefined, "a sample must not hold a compiled rest path");
    assert.equal(deformation.path, undefined, "a sample must not hold a compiled posed path");
    assert.equal(deformation.key, undefined, "a sample must not hold a key string per grid sample");
    for (const segment of deformation.pathSpec.segments) {
      assert.equal(segment.table, undefined, "a spec segment must not carry an arc-length table");
    }
    // One rest spec for the tube, shared by every sample: the refusal above is what
    // makes the rest constant, so storing it per sample is storing it 97 times.
    assert.equal(deformation.restSpec, entry.rest.restSpec);
  }
});

test("a sampled deformation OWNS its numbers: a reused control array cannot change what was sampled", () => {
  // Authors may build one array and mutate it every frame; the old code survived
  // that only because it stringified the spec on the spot. Now that a spec is
  // retained for the whole bake, the copy is what keeps 27,504 samples from all
  // aliasing the one array that is about to change under them.
  const reused = [40, 0, 0];
  const result = sample(
    (t, m) => {
      reused[1] = t;
      m.get("spinner").deformTube({
        rest: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: [40, 0, 0] }] },
        path: { normal: [0, 0, 1], segments: [{ kind: "line", start: [0, 0, 0], end: reused }] },
      });
    },
    { fps: 12, seconds: 1 },
    { deform: "morph" },
  );
  const entry = result.deformations.get("o1.2");
  const sampled = entry.samples.map((sample) => sample.deformation.pathSpec.segments[0].end[1]);
  assert.ok(new Set(sampled).size > 1, "the clip really did move the endpoint");
  reused[1] = 999;
  assert.deepEqual(
    entry.samples.map((sample) => sample.deformation.pathSpec.segments[0].end[1]),
    sampled,
    "mutating the author's array after sampling changed what had already been sampled",
  );
});
