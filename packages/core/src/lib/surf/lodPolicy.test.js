// LOD policy math (design/unified-tessellation.md Phase 5): projected chord
// error picks levels, the enter/exit band prevents thrash, and work ranks
// worst-error-first.
import assert from "node:assert/strict";
import test from "node:test";

import {
  LOD_CHORD_LEVELS,
  LOD_DEFAULT_LEVEL,
  LOD_TESSELLATION_LEVELS,
  desiredLevel,
  lodTessellationForLevel,
  nextLevel,
  normalizeLodLevel,
  pixelsPerUnit,
  planLodWork,
  projectedChordErrorPx,
  settledLevel,
} from "./lodPolicy.js";

test("LOD tiers make coarse inputs explicit while preserving the default cache request", () => {
  assert.equal(LOD_DEFAULT_LEVEL, 1);
  assert.deepEqual(lodTessellationForLevel(0), { chordTolerance: 2e-3, angleTolerance: 1.4 });
  assert.equal(lodTessellationForLevel(LOD_DEFAULT_LEVEL), undefined);
  assert.deepEqual(lodTessellationForLevel(2), { chordTolerance: 5e-4, angleTolerance: 0.35 });
  assert.deepEqual(LOD_CHORD_LEVELS, LOD_TESSELLATION_LEVELS.map((level) => level.chordTolerance));
  assert.equal(normalizeLodLevel(undefined), LOD_DEFAULT_LEVEL);
  assert.equal(normalizeLodLevel(-10), 0);
  assert.equal(normalizeLodLevel(99), LOD_TESSELLATION_LEVELS.length - 1);
});

// A 100mm-diagonal part in a 1000px-tall, 45deg viewport.
function sample(cameraDistance) {
  return {
    diagonal: 100,
    cameraDistance,
    camera: { kind: "perspective", fovYDeg: 45 },
    viewportHeightPx: 1000,
  };
}

test("pixelsPerUnit: perspective shrinks with distance, ortho with visible height", () => {
  const cam = { kind: "perspective", fovYDeg: 45 };
  assert.ok(pixelsPerUnit(cam, 100, 1000) > pixelsPerUnit(cam, 200, 1000));
  const near = pixelsPerUnit(cam, 100, 1000);
  assert.ok(Math.abs(near - 1000 / (2 * 100 * Math.tan(Math.PI / 8))) < 1e-9);
  assert.equal(pixelsPerUnit({ kind: "orthographic", visibleWorldHeight: 500 }, 9, 1000), 2);
  assert.equal(pixelsPerUnit(cam, 100, 0), 0);
});

test("desiredLevel climbs as the camera approaches, capped at the finest rung", () => {
  assert.equal(desiredLevel(sample(2000)), 0, "far away: default is enough");
  const nearLevel = desiredLevel(sample(120));
  assert.ok(nearLevel >= 1, `near: expected finer than default, got L${nearLevel}`);
  assert.equal(desiredLevel(sample(50.0001)), LOD_CHORD_LEVELS.length - 1, "at the surface: finest");
});

test("camera at or inside the bounds demands the finest level, never NaN/Infinity", () => {
  for (const distance of [50, 10, 0]) {
    const errorPx = projectedChordErrorPx({
      ...sample(distance),
      chordRel: LOD_CHORD_LEVELS[0],
    });
    assert.ok(Number.isFinite(errorPx) && errorPx > 0, `d=${distance}: ${errorPx}`);
    assert.equal(desiredLevel(sample(distance)), LOD_CHORD_LEVELS.length - 1);
  }
});

test("hysteresis: the upgrade and downgrade boundaries do not meet", () => {
  // Find a distance where L0's error sits INSIDE the band (between downgrade
  // and upgrade thresholds when evaluated from L1): no move in either
  // direction — the no-thrash zone exists.
  let bandDistance = null;
  for (let d = 60; d < 3000; d += 1) {
    const l0Error = projectedChordErrorPx({ ...sample(d), chordRel: LOD_CHORD_LEVELS[0] });
    if (l0Error < 1.25 && l0Error > 0.6) {
      bandDistance = d;
      break;
    }
  }
  assert.ok(bandDistance !== null, "no band distance found — thresholds overlap");
  assert.equal(nextLevel(sample(bandDistance), 0), 0, "inside the band, L0 holds");
  assert.equal(nextLevel(sample(bandDistance), 1), 1, "inside the band, L1 holds");
});

test("nextLevel moves one rung at a time and re-evaluation converges", () => {
  const near = sample(52);
  let level = 0;
  const seen = [level];
  for (let step = 0; step < 10; step += 1) {
    const next = nextLevel(near, level);
    if (next === level) {
      break;
    }
    assert.equal(Math.abs(next - level), 1, "one rung per step");
    level = next;
    seen.push(level);
  }
  assert.equal(level, LOD_CHORD_LEVELS.length - 1, `climbed ${JSON.stringify(seen)}`);
  // And zooming back out walks it down again.
  const far = sample(5000);
  assert.equal(nextLevel(far, level), level - 1);
});

test("planLodWork ranks upgrades worst-error-first and drops settled components", () => {
  const entries = [
    { cid: "far", currentLevel: 0, sample: sample(2000) },
    { cid: "near", currentLevel: 0, sample: sample(60) },
    { cid: "mid", currentLevel: 0, sample: sample(150) },
  ];
  const plan = planLodWork(entries);
  assert.ok(plan.length >= 2, `expected near+mid to plan, got ${JSON.stringify(plan)}`);
  assert.equal(plan[0].cid, "near", "worst projected error first");
  assert.ok(!plan.some((item) => item.cid === "far"), "settled component plans no work");
  assert.ok(plan.every((item) => item.level !== undefined && item.errorPx > 0));
});

test("settledLevel skips intermediate rungs but preserves starting hysteresis and strict boundaries", () => {
  const ortho = (scale) => ({ diagonal: 1, cameraDistance: 10,
    camera: { kind: "orthographic", visibleWorldHeight: 1 }, viewportHeightPx: scale });
  assert.equal(settledLevel(ortho(3000), 0), 3);
  assert.equal(settledLevel(ortho(1000), 0), 2);
  assert.equal(settledLevel(ortho(250), 3), 0);
  assert.equal(desiredLevel(ortho(500)), 0);
  assert.deepEqual([0, 1, 2, 3].map(level => settledLevel(ortho(500), level)), [0, 1, 2, 2]);
  const levels = [1, .5, .125];
  assert.equal(settledLevel(ortho(1.25), 0, levels), 0);
  assert.equal(settledLevel(ortho(1.25 + Number.EPSILON), 0, levels), 1);
  assert.equal(settledLevel(ortho(.6), 1, levels), 1);
  assert.equal(settledLevel(ortho(.6 - Number.EPSILON), 1, levels), 0);
});

test("settledLevel matches repeated existing steps over perspective, orthographic and inside-bounds samples", () => {
  for (const camera of [{ kind: "perspective", fovYDeg: 45 }, { kind: "orthographic", visibleWorldHeight: 1 }]) {
    for (const diagonal of [.01, 1, 1000]) for (const cameraDistance of [0, .001, .5, 1, 10, 10000]) {
      for (const viewportHeightPx of [0, 300, 500, 625, 1000, 3000]) {
        for (const current of [-10, 0, 1, 2, 3, 20, undefined, NaN, Infinity]) {
          const input = { camera, diagonal, cameraDistance, viewportHeightPx };
          let expected = Math.max(0, Math.min(LOD_CHORD_LEVELS.length - 1, current | 0));
          const visited = new Set();
          while (true) {
            assert.ok(!visited.has(expected), "existing policy must not cycle");
            visited.add(expected);
            const next = nextLevel(input, expected);
            if (next === expected) break;
            expected = next;
          }
          assert.equal(settledLevel(input, current), expected);
          assert.equal(nextLevel(input, expected), expected);
        }
      }
    }
  }
  assert.equal(settledLevel(sample(52), 99, []), nextLevel(sample(52), 99, []));
  assert.equal(settledLevel(sample(52), 99, [1]), 0);
});
