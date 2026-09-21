import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  ANIMATION_MODULE_EXPORTS,
  compileAnimationModule,
  compileAnimationSource,
  importAnimationModule,
  loadSourceAnimation,
  validateAnimationClips
} from "./renderModule.js";

const GOOD = `
export const clips = {
  demo: { label: "Demo", duration: 4, update(t, m) { m.get("arm").rotate([0, 0, 1], 10 * t); } },
  still: { duration: 1, loop: false, update() {} },
};
`;

const MESH_DATA = { parts: [{ id: "o1.1", label: "base" }, { id: "o1.2", label: "arm" }] };

test("embedded source compiles to normalized clips without fetching", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("animation source must not fetch"); };
  try {
    const compiled = await loadSourceAnimation({
      animation: { language: "javascript", source: GOOD }
    }, { name: "arm animation" });
    assert.deepEqual(Object.keys(compiled.clips), ["demo", "still"]);
    assert.equal(compiled.clips.demo.label, "Demo");
    assert.equal(compiled.clips.demo.duration, 4);
    assert.equal(compiled.clips.demo.loop, true);
    assert.equal(compiled.clips.still.loop, false);
    assert.equal(await loadSourceAnimation({}), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("the embedded module vocabulary is closed", async () => {
  const namespace = await importAnimationModule("export const animations = {}; export const clips = {};", {
    name: "arm animation"
  });
  assert.throws(
    () => compileAnimationModule(namespace, { name: "arm animation" }),
    new RegExp(`unknown export animations — the renderer understands: ${ANIMATION_MODULE_EXPORTS.join(", ")}`)
  );
  const withDefault = await importAnimationModule("export default { demo: { update() {} } };", {
    name: "arm animation"
  });
  assert.throws(
    () => compileAnimationModule(withDefault, { name: "arm animation" }),
    /default export is not an animation-module export/
  );
});

test("syntax errors carry the embedded animation name", async () => {
  await assert.rejects(
    () => compileAnimationSource("export const clips = {", { name: "arm animation" }),
    /^Error: arm animation: /
  );
});

test("clips are validated against the tree at load", async () => {
  const { clips } = await compileAnimationSource(GOOD);
  assert.deepEqual(validateAnimationClips(THREE, MESH_DATA, clips), []);
  const bad = await compileAnimationSource(
    'export const clips = { typo: { duration: 1, update(t, m) { m.get("forearm").translate([0, 0, 1]); } } };'
  );
  const problems = validateAnimationClips(THREE, MESH_DATA, bad.clips);
  assert.equal(problems.length, 1);
  assert.equal(problems[0].clip, "typo");
  assert.match(problems[0].error, /forearm/);
});
