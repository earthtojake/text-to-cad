import assert from "node:assert/strict";
import test from "node:test";

import { FILE_VIEW_VERSION, fileViewsEqual, plainShellCamera, readFileView, scopeShellCamera, writeFileView } from "./fileView.js";

const camera = { position: [10, -20, 30], target: [0, 0, 0], up: [0, 0, 1], zoom: 1.5, projection: "orthographic" };

test("a missing, foreign or older record restores nothing and never throws", () => {
  for (const raw of [undefined, null, "x", [], { version: 1, camera, display: { mode: "render" }, tool: "draw" }, { version: FILE_VIEW_VERSION, renderer: "x" }]) {
    const view = readFileView(raw, { tree: "a" });
    assert.equal(view.version, FILE_VIEW_VERSION);
    assert.equal(view.camera, null);
    assert.equal(view.display.mode, "solid");
    assert.deepEqual(view.renderer, {});
  }
});

test("the camera and the display are always kept; a slice comes back only under the signature it was written against", () => {
  const display = readFileView({ version: FILE_VIEW_VERSION, display: { mode: "render", surfaces: { colorMode: "single", color: "#00c040" } } }).display;
  const written = writeFileView({ camera, display, renderer: { tree: { expanded: ["o1"] }, pose: { hinge: 30 }, plain: { note: 1 }, skipped: undefined },
    signatures: { tree: "geo:1", pose: "motion:1" } });
  assert.deepEqual(Object.keys(written.renderer), ["tree", "pose", "plain"], "an undefined slice is not written");
  assert.deepEqual(written.renderer.tree, { signature: "geo:1", value: { expanded: ["o1"] } });
  const copy = JSON.parse(JSON.stringify(written));
  const same = readFileView(copy, { tree: "geo:1", pose: "motion:1" });
  assert.deepEqual(same.camera, camera);
  assert.deepEqual([same.display.mode, same.display.surfaces.colorMode, same.display.surfaces.color], ["render", "single", "#00c040"]);
  assert.deepEqual(same.renderer, { tree: { expanded: ["o1"] }, pose: { hinge: 30 }, plain: { note: 1 } });
  // A rebuilt model: the geometry slice is dropped, the motion slice and everything else kept.
  const rebuilt = readFileView(copy, { tree: "geo:2", pose: "motion:1" });
  assert.deepEqual(rebuilt.camera, camera);
  assert.equal(rebuilt.display.mode, "render");
  assert.deepEqual(rebuilt.renderer, { pose: { hinge: 30 }, plain: { note: 1 } });
  // Reading is a copy: what comes back is nobody else's object.
  same.renderer.tree.expanded.push("o2");
  assert.deepEqual(readFileView(copy, { tree: "geo:1" }).renderer.tree, { expanded: ["o1"] });
  assert.equal(fileViewsEqual(written, writeFileView({ camera, display, renderer: { tree: { expanded: ["o1"] }, pose: { hinge: 30 }, plain: { note: 1 } }, signatures: { tree: "geo:1", pose: "motion:1" } })), true);
  assert.equal(fileViewsEqual(written, writeFileView({ camera, display })), false);
});

test("a view with no display or no camera writes null for them, playback at its defaults, and a drawing's camera is whatever the drawing says", () => {
  const drawing = writeFileView({ camera: { scale: 2, offsetX: 1, offsetY: 3 } });
  assert.deepEqual(drawing, { version: FILE_VIEW_VERSION, camera: { scale: 2, offsetX: 1, offsetY: 3 }, display: null,
    playback: { orbit: true, orbitSpeed: 1, autoplay: false }, renderer: {} });
  assert.deepEqual(readFileView(drawing).camera, { scale: 2, offsetX: 1, offsetY: 3 });
  assert.equal(writeFileView({ camera: "x" }).camera, null);
});

test("preview's playback settings are the view's: written whole, read back bounded, and the defaults for a view without them", () => {
  const written = writeFileView({ playback: { orbit: false, orbitSpeed: 2, autoplay: true, speed: 2, loop: false, junk: 1 } });
  assert.deepEqual(written.playback, { orbit: false, orbitSpeed: 2, autoplay: true, speed: 2, loop: false });
  assert.deepEqual(readFileView(JSON.parse(JSON.stringify(written))).playback, { orbit: false, orbitSpeed: 2, autoplay: true, speed: 2, loop: false });
  assert.deepEqual(readFileView({ version: FILE_VIEW_VERSION, playback: { orbitSpeed: 99, speed: "fast" } }).playback, { orbit: true, orbitSpeed: 5, autoplay: false });
  assert.deepEqual(readFileView(undefined).playback, { orbit: true, orbitSpeed: 1, autoplay: false });
});

test("a chosen floor finish is kept with the display, in the record either app writes", () => {
  const display = readFileView({ version: FILE_VIEW_VERSION, display: { mode: "render", floor: { finish: "glossy" } } }).display;
  assert.deepEqual(display.floor, { finish: "glossy" });
  const copy = JSON.parse(JSON.stringify(writeFileView({ camera, display })));
  assert.deepEqual(readFileView(copy).display.floor, { finish: "glossy" });
  assert.equal(readFileView({ version: FILE_VIEW_VERSION, display: { mode: "render", floor: { finish: "chrome" } } }).display.mode, "solid");
});

test("display settings this build cannot read are the defaults, and the stored record is not rewritten", () => {
  const raw = { version: FILE_VIEW_VERSION, display: { mode: "no-such-mode", surfaces: 7 } };
  const before = JSON.stringify(raw);
  assert.equal(readFileView(raw).display.mode, "solid");
  assert.equal(JSON.stringify(raw), before);
});

test("a stored camera is scoped to the model it frames on the way in, and stripped of its scope on the way out", () => {
  const scoped = scopeShellCamera(camera, "parts/plate.glb", "cad");
  assert.deepEqual([scoped.modelKey, scoped.sceneScaleMode, scoped.coordinateSystem], ["parts/plate.glb", "cad", "cad-z-up-v1"]);
  assert.equal(scopeShellCamera(null, "x", "cad"), null);
  assert.deepEqual(plainShellCamera(scoped), camera);
  assert.equal(plainShellCamera({ position: [1] }), null);
});
