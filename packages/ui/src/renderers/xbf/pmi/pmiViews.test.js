// A part's named view placed where the part stands (`pmiViews.js`): its camera and its section,
// served in the part's frame, turned and moved by the placement of its first occurrence shown; a
// section whose axis the placement turns off a world axis is not one the Clip can cut, and says so.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import test from "node:test";

import { pmiCallText, readXbfPmi } from "@text-to-cad/core/lib/xbf/xbfPmi.js";
import { english } from "../../../i18n/core.js";
import { PMI_SECTION_OFF, pmiViewAt, pmiViewFromHere, pmiViewPlacements, pmiViewShows, pmiViewShowsText } from "./pmiViews.js";

const FIXTURES = join(dirname(createRequire(import.meta.url).resolve("@text-to-cad/core/lib/xbf/xbfDocument.js")), "__fixtures__");
const V4 = JSON.parse(readFileSync(join(FIXTURES, "pmi_plate", "v4", "structure.json"), "utf8"));
const [SECTION, ISO] = readXbfPmi(V4).views;
const near = (actual, expected, what) => expected.forEach((value, axis) => assert.ok(Math.abs(actual[axis] - value) < 1e-9, `${what}[${axis}] ${actual[axis]} is not ${value}`));
// Column-major, as the structure's instances hold it.
const moved = (x, y, z) => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1];
const QUARTER_Z = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const EIGHTH_Z = [Math.SQRT1_2, Math.SQRT1_2, 0, 0, -Math.SQRT1_2, Math.SQRT1_2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const instances = (...matrices) => matrices.map(matrix => ({ prototype: 0, matrix }));

test("a view where its part stands: its camera and section moved with the part, at its first occurrence shown", () => {
  const at = pmiViewAt(SECTION, instances(moved(0, 30, 0)));
  assert.equal(at.instance, 0);
  near(at.direction, [0, -1, 0], "direction");
  near(at.up, [0, 0, 1], "up");
  assert.deepEqual(at.section, { axis: "y", at: 30, invert: true });
  assert.equal(at.sectionOff, false);
  // The first occurrence hidden, the next one's placement: turned a quarter about z, the part's y is the
  // scene's -x, so the cut is across x, keeping the other side.
  const turned = pmiViewAt(SECTION, instances(moved(0, 30, 0), QUARTER_Z), { hidden: ["i0"] });
  assert.equal(turned.instance, 1);
  near(turned.direction, [1, 0, 0], "direction");
  assert.deepEqual(turned.section, { axis: "x", at: 0, invert: false });
  // None shown: it stands nowhere.
  assert.equal(pmiViewAt(SECTION, instances(moved(0, 0, 0)), { hidden: ["i0"] }), null);
  // A view of no section has none to place.
  assert.deepEqual([pmiViewAt(ISO, instances(null)).section, pmiViewAt(ISO, instances(null)).sectionOff], [null, false]);
});

test("a section the placement turns off a world axis is not cut: the view says so, its camera still placed", () => {
  const at = pmiViewAt(SECTION, instances(EIGHTH_Z));
  assert.equal(at.section, null);
  assert.equal(at.sectionOff, true);
  near(at.direction, [Math.SQRT1_2, -Math.SQRT1_2, 0], "direction");
});

test("a view shows its part's ids, or every one of its part, at its own placements first", () => {
  const entry = (part, id) => ({ part, id });
  assert.deepEqual([entry(0, "hole-diameter"), entry(0, "mask"), entry(0, "thickness"), entry(1, "hole-diameter")].map(item => pmiViewShows(SECTION, item)),
    [true, true, false, false]);
  assert.deepEqual([entry(0, "thickness"), entry(1, "thickness")].map(item => pmiViewShows(ISO, item)), [true, false]);
  assert.deepEqual([...pmiViewPlacements(SECTION)], [["0:hole-diameter", { anchor: [5, 0, 0], offset: [15, 0, 10] }]]);
  assert.deepEqual([pmiViewShowsText(SECTION), pmiViewShowsText(ISO), pmiViewShowsText({ ...SECTION, shows: ["mask"] })], ["4 annotations", "All", "1 annotation"]);
});

// The camera and the Clip as the viewport has them now (the scene's frame), and the view they make.
const FRONT = { position: [0, -170, 0], target: [0, 30, 0], up: [0, 0, 1] };
const fromHere = (options) => pmiViewFromHere({ part: 0, name: "view", camera: FRONT, clip: null, instances: instances(moved(0, 30, 0)), shows: ["hole-diameter"], ...options });

test("the view from here is the camera and the Clip in its part's frame, through its first occurrence shown", () => {
  // The plate placed 30 along y, seen from the front, cut across y where it stands, keeping the far side.
  const { call } = fromHere({ clip: { axis: "y", at: 30, invert: true } });
  assert.deepEqual(call, { kind: "view", name: "view", camera: { direction: [0, -1, 0], up: [0, 0, 1] }, shows: ["hole-diameter"],
    section: { axis: "y", at: 0, invert: true } });
  assert.equal(pmiCallText(call), `view("view", camera=camera((0, -1, 0), (0, 0, 1)), shows=["hole-diameter"], section=section("y", 0, invert=True))`);
  // The Clip off: no section.
  assert.equal(pmiCallText(fromHere({}).call), `view("view", camera=camera((0, -1, 0), (0, 0, 1)), shows=["hole-diameter"])`);
  // Placed again where its part stands, it is the camera and the Clip it was made from.
  const turned = fromHere({ camera: { position: [80, -40, 90], target: [0, 0, 0], up: [0, 0, 1] }, clip: { axis: "x", at: 4, invert: false },
    instances: instances(moved(0, 0, 0), QUARTER_Z), shown: { hidden: ["i0"] } }).call;
  assert.equal(turned.section.axis, "y", "the scene's x is the turned part's -y");
  const back = pmiViewAt({ supported: true, part: 0, camera: turned.camera, section: turned.section }, instances(moved(0, 0, 0), QUARTER_Z), { hidden: ["i0"] });
  near(back.direction, [80, -40, 90].map(value => value / Math.hypot(80, -40, 90)), "direction");
  assert.deepEqual(back.section, { axis: "x", at: 4, invert: false });
  // Its up is the screen's: square to where it looks, whatever up the camera turns about.
  assert.ok(Math.abs(turned.camera.up.reduce((sum, value, axis) => sum + value * turned.camera.direction[axis], 0)) < 1e-9);
});

test("a view from here is refused where its part's placement turns the Clip off the part's axes, or its part is not shown", () => {
  assert.deepEqual(fromHere({ clip: { axis: "y", at: 0, invert: false }, instances: instances(EIGHTH_Z) }), { problem: english(PMI_SECTION_OFF) });
  assert.equal(english(PMI_SECTION_OFF), "Its section is not on this placement's axes");
  // Uncut, the same placement makes one.
  assert.ok(fromHere({ instances: instances(EIGHTH_Z) }).call);
  assert.deepEqual(fromHere({ shown: { hidden: ["i0"] } }), { problem: "Its part is not shown" });
  assert.deepEqual(fromHere({ camera: null }), { problem: "No camera to view from" });
  assert.deepEqual(fromHere({ camera: { position: [0, 0, 100], target: [0, 0, 0], up: [0, 0, 1] } }), { problem: "The camera's up is along its direction" });
});
