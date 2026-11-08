import assert from "node:assert/strict";
import test from "node:test";

import { KICAD_PX_PER_MM, isTrack, shortNetName, trackNameDetail, trackNames } from "./trackNames.js";

// KiCad's rule for the names along a track (`renderNetNameForSegment`); the engine's `track_labels`
// is held to the same numbers by the Python suite.
const round = (value) => Math.round(value * 1000) / 1000;
const laid = (item, viewport = [30, 20]) => trackNames(item, viewport).map(({ text, at, size, angle, w }) => [text, at.map(round), size.map(round), round(angle), round(w)]);

test("a track's net name sits at its middle, along it, 0.55 of its width tall with a pen a twelfth of it", () => {
  assert.deepEqual(laid({ pts: [[0, 0], [10, 0]], w: 0.25, net: "/cpu/CLK" }), [["CLK", [5, 0], [0.138, 0.138], 0, 0.021]]);
  // Vertical it reads upwards; slanted it reads along the track, never upside down.
  assert.deepEqual(laid({ pts: [[0, 10], [0, 0]], w: 0.25, net: "CLK" }).map(([, , , angle]) => angle), [90]);
  assert.deepEqual(laid({ pts: [[0, 0], [4, 4]], w: 0.25, net: "CLK" }).map(([, , , angle]) => angle), [-45]);
  assert.deepEqual(laid({ pts: [[4, 0], [0, 4]], w: 0.25, net: "CLK" }).map(([, , , angle]) => angle), [45]);
  // A track shorter than its name (a square character a width wide) carries none.
  assert.deepEqual(laid({ pts: [[0, 0], [0.7, 0]], w: 0.25, net: "CLK" }), []);
});

test("a segment long against the view carries one name per view it spans; an arc one at its middle", () => {
  // 90 mm across a 30 mm wide view: three names, at its quarters.
  assert.deepEqual(laid({ pts: [[0, 0], [90, 0]], w: 0.25, net: "CLK" }).map(([, at]) => at), [[22.5, 0], [45, 0], [67.5, 0]]);
  // Vertical against the view's height, slanted against the diagonal of its shorter side.
  assert.equal(laid({ pts: [[0, 0], [0, 50]], w: 0.25, net: "CLK" }).length, 3);
  assert.equal(laid({ pts: [[0, 0], [40, 40]], w: 0.25, net: "CLK" }).length, 2);
  // An arc's polyline: its middle, along its tangent there.
  const arc = { pts: [[0, 0], [3, 1], [6, 0]], w: 0.25, net: "CLK" };
  assert.deepEqual(laid(arc), [["CLK", [3, 1], [0.138, 0.138], -18.435, 0.021]]);
});

test("a track is a copper path with a net and a width; its names show once the view is 4 mm over its width", () => {
  assert.ok(isTrack({ t: "path", pts: [[0, 0], [1, 0]], w: 0.25, net: "GND" }));
  assert.ok(!isTrack({ t: "path", pts: [[0, 0], [1, 0], [1, 1]], w: 0, closed: true, net: "GND" }), "a pour's outline");
  assert.ok(!isTrack({ t: "path", pts: [[0, 0], [1, 1]], w: 0.1, pairs: true, net: "GND" }), "a pour's hatch");
  assert.ok(!isTrack({ t: "path", pts: [[0, 0], [1, 0]], w: 0.25 }), "a line on copper with no net");
  assert.equal(round(trackNameDetail(0.25)), round(16 * KICAD_PX_PER_MM));
  assert.equal(trackNameDetail(0), Infinity);
  assert.deepEqual(["/cpu/CLK", "GND", "Net-(U8-BIN)"].map(shortNetName), ["CLK", "GND", "Net-(U8-BIN)"]);
});
