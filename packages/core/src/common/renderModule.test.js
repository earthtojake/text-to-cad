import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  RENDER_MODULE_EXPORTS,
  compileRenderModule,
  fetchRenderModuleSource,
  importRenderModule,
  loadRenderModule,
  renderModuleName,
  renderModuleUrlForDocument,
  validateRenderModuleClips
} from "./renderModule.js";

const GOOD = `
export const clips = {
  demo: { label: "Demo", duration: 4, update(t, m) { m.get("arm").rotate([0, 0, 1], 10 * t); } },
  still: { duration: 1, loop: false, update() {} },
};
`;

const MESH_DATA = {
  parts: [
    { id: "o1.1", label: "base" },
    { id: "o1.2", label: "arm" }
  ]
};

function stubFetch(t, routes) {
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const entry = routes[String(url)];
    if (entry === undefined) {
      return { ok: false, status: 404, text: async () => "" };
    }
    if (typeof entry === "number") {
      return { ok: false, status: entry, text: async () => "" };
    }
    return { ok: true, status: 200, text: async () => entry };
  };
  t.after(() => {
    globalThis.fetch = original;
  });
}

test("the module is the document's whole name plus .js, in every URL form clients hold", () => {
  assert.equal(renderModuleUrlForDocument("STEP/arm.step"), "STEP/arm.step.js");
  assert.equal(renderModuleUrlForDocument("/hero/arm.STP"), "/hero/arm.STP.js");
  assert.equal(renderModuleUrlForDocument("/models/arm.step?v=3"), "/models/arm.step.js?v=3");
  assert.equal(
    renderModuleUrlForDocument("/__cad/asset?file=STEP%2Farm.step"),
    "/__cad/asset?file=STEP%2Farm.step.js"
  );
  assert.equal(
    renderModuleUrlForDocument("/__cad/asset?file=STEP%2Farm.step&v=7"),
    "/__cad/asset?file=STEP%2Farm.step.js&v=7"
  );
  assert.equal(renderModuleUrlForDocument(""), "");
});

test("the module's name is read out of a plain URL or the viewer's asset route", () => {
  assert.equal(renderModuleName("/models/STEP/arm.step.js"), "arm.step.js");
  assert.equal(renderModuleName("/__cad/asset?file=STEP%2Farm.step.js"), "arm.step.js");
});

test("a good module compiles to normalized clips", async () => {
  const namespace = await importRenderModule(GOOD, { name: "arm.step.js" });
  const compiled = compileRenderModule(namespace, { name: "arm.step.js" });
  assert.deepEqual(Object.keys(compiled), ["clips"]);
  assert.deepEqual(Object.keys(compiled.clips), ["demo", "still"]);
  assert.equal(compiled.clips.demo.label, "Demo");
  assert.equal(compiled.clips.demo.duration, 4);
  assert.equal(compiled.clips.demo.loop, true);
  assert.equal(compiled.clips.still.loop, false);
});

test("an unknown export is an error naming it and the vocabulary", async () => {
  const namespace = await importRenderModule("export const animations = {}; export const clips = {};", {
    name: "arm.step.js"
  });
  assert.throws(
    () => compileRenderModule(namespace, { name: "arm.step.js" }),
    new RegExp(`arm\\.step\\.js: unknown export animations — the renderer understands: ${RENDER_MODULE_EXPORTS.join(", ")}`)
  );
});

test("a default export is refused: the contract is named exports", async () => {
  const namespace = await importRenderModule("export default { demo: { update() {} } };", {
    name: "arm.step.js"
  });
  assert.throws(() => compileRenderModule(namespace, { name: "arm.step.js" }), /default export is not a render-module export/);
});

test("a syntax error carries the module's name", async () => {
  await assert.rejects(
    () => importRenderModule("export const clips = {", { name: "arm.step.js" }),
    /^Error: arm\.step\.js: /
  );
});

test("a missing module is null, not an error; any other HTTP failure throws", async (t) => {
  stubFetch(t, { "/m/arm.step.js": GOOD, "/m/broken.step.js": 500 });
  assert.equal(await fetchRenderModuleSource("/m/none.step.js"), null);
  assert.equal(await loadRenderModule("/m/none.step.js"), null);
  assert.equal(await loadRenderModule(""), null);
  await assert.rejects(() => fetchRenderModuleSource("/m/broken.step.js"), /broken\.step\.js: HTTP 500/);
  const loaded = await loadRenderModule("/m/arm.step.js");
  assert.deepEqual(Object.keys(loaded.clips), ["demo", "still"]);
});

test("clips are validated against the tree at load: an unresolved target is reported per clip", async () => {
  const namespace = await importRenderModule(
    `${GOOD}
     export const clips2 = undefined;`.replace("export const clips2 = undefined;", ""),
    { name: "arm.step.js" }
  );
  const { clips } = compileRenderModule(namespace, { name: "arm.step.js" });
  assert.deepEqual(validateRenderModuleClips(THREE, MESH_DATA, clips), []);

  const bad = compileRenderModule(
    await importRenderModule(
      'export const clips = { typo: { duration: 1, update(t, m) { m.get("forearm").translate([0, 0, 1]); } } };',
      { name: "arm.step.js" }
    ),
    { name: "arm.step.js" }
  );
  const problems = validateRenderModuleClips(THREE, MESH_DATA, bad.clips);
  assert.equal(problems.length, 1);
  assert.equal(problems[0].clip, "typo");
  assert.match(problems[0].error, /forearm/);
});
