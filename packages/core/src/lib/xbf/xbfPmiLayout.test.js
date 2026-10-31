// Where an engine document's PMI is drawn (`xbfPmiLayout.js`), on core's bracket
// (`__fixtures__/bracket`: a 40 x 20 x 4 plate on z = -2..2 with a Ø8 hole at the origin, and two
// pegs): from the plate's faces as the scene places them, its annotations stand where the code
// placed them, or out from their feature where it placed none, and a distance is drawn square
// between its two faces.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import * as THREE from "three";

import { parseEngineRef } from "../cadRefs.js";
import { loadXbfDocument } from "./xbfDocument.js";
import { pmiKey, readXbfPmi } from "./xbfPmi.js";
import { pmiConstruction, pmiConstructions, pmiDrawnOnPart, pmiFeaturePoint, pmiMovedPlacement, pmiPresentationToPart, pmiPresentationToScene } from "./xbfPmiLayout.js";
import { createXbfScene } from "./xbfScene.js";

const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), "__fixtures__");
const read = file => fs.readFileSync(path.join(FIXTURES, file));
const STRUCTURE = JSON.parse(read("bracket/structure.json"));
const ENVIRONMENT = new Uint8Array([...new TextEncoder().encode("#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n"), 255, 255, 255, 128]).buffer;

async function bracket() {
  const fetch = async (url) => {
    if (url.endsWith("/api/look")) return new Response(read("look.json"));
    if (url.endsWith("/api/look/environment")) return new Response(ENVIRONMENT);
    const part = /\/part\/([^/]+)$/.exec(url);
    return new Response(part ? read(`bracket/${part[1]}.xbm`) : JSON.stringify(STRUCTURE));
  };
  return createXbfScene(THREE, await loadXbfDocument("http://127.0.0.1:9/api/doc/bracket", { fetch }));
}

const TOP = "i0/face/2", BOTTOM = "i0/face/5", HOLE = "i0/face/11";
const BOUNDS = { min: [-20, -10, -2], max: [20, 10, 14] };
const near = (actual, expected, what = "") => assert.ok(Math.abs(actual - expected) < 1e-6, `${what} ${actual} is not ${expected}`);
const nearPoint = (actual, expected, what = "") => expected.forEach((value, axis) => near(actual[axis], value, `${what}[${axis}]`));
const entry = (item) => readXbfPmi({ pmi: [{ status: "ok", refs: [], presentation: null, ...item }] }).entries[0];
const flatness = (presentation = null) => entry({ id: "top-flat", kind: "geometric_tolerance", presentation,
  geometric_tolerance: { characteristic: "flatness", value: 0.05, unit: "mm", datums: [] } });

test("a leader starts on its feature: a flat face's own node, a hole's rim", async () => {
  const scene = await bracket();
  const top = scene.elementGeometry(TOP, { points: true });
  const start = pmiFeaturePoint(top, [0, 0, 6]);
  near(start[2], 2, "on the top");
  // Not in the hole the face's middle falls in.
  assert.ok(Math.hypot(start[0], start[1]) >= 4 - 1e-6, `${start} is in the hole`);
  const rim = pmiFeaturePoint(scene.elementGeometry(HOLE, { points: true }), [0, 0, 6]);
  near(Math.hypot(rim[0], rim[1]), 4, "on the hole's wall");
  near(Math.abs(rim[2]), 2, "at an end of it");
});

test("an annotation the code placed stands where it was placed; one it never placed stands out from its feature", async () => {
  const scene = await bracket();
  const geometry = { feature: scene.elementGeometry(TOP, { points: true }) };
  const placed = pmiConstruction(flatness({ anchor: [10, 5, 2], offset: [4, 0, 6] }), { geometry, bounds: BOUNDS });
  assert.equal(placed.placed, "given");
  nearPoint(placed.anchor, [10, 5, 2]);
  nearPoint(placed.label, [14, 5, 8]);
  const free = pmiConstruction(flatness(), { geometry, bounds: BOUNDS });
  assert.equal(free.placed, "default");
  near(free.anchor[2], 2, "its leader on the top");
  assert.ok(free.label[2] > 2 + 1, `${free.label} stands above the top`);
  // A second annotation of the same face is turned from the first.
  const second = pmiConstruction(flatness(), { geometry, bounds: BOUNDS, turn: 1 });
  assert.ok(Math.hypot(second.label[0] - free.label[0], second.label[1] - free.label[1]) > 1, "two on one face stand apart");
  // A drag not yet written draws it at the drag's place, as a placement.
  const dragged = pmiConstruction(flatness(), { geometry, bounds: BOUNDS, placement: { anchor: free.anchor, offset: [0, 0, 12] } });
  nearPoint(dragged.label, [free.anchor[0], free.anchor[1], 14]);
});

test("a distance is drawn square between its faces, through its label", async () => {
  const scene = await bracket();
  const thickness = entry({ id: "thickness", kind: "dimension", presentation: { anchor: [20, 0, -2], offset: [6, 0, 2] },
    dimension: { type: "distance", nominal: { value: 4, unit: "mm", source: "geometry" }, tolerance: null } });
  const drawn = pmiConstruction(thickness, { geometry: { from: scene.elementGeometry(BOTTOM, { points: true }), to: scene.elementGeometry(TOP, { points: true }) }, bounds: BOUNDS });
  nearPoint(drawn.label, [26, 0, 0]);
  nearPoint(drawn.dimension.from, [26, 0, -2], "on the bottom's plane");
  nearPoint(drawn.dimension.to, [26, 0, 2], "on the top's plane");
  nearPoint(drawn.dimension.extensions[0][0], [20, 0, -2], "from the anchor");
  nearPoint(drawn.dimension.extensions[1][0], [20, 0, 2], "from its foot on the top");
  // An anchor the code put off the face (on the side, mid-height) still extends from each face's plane.
  const mid = pmiConstruction({ ...thickness, presentation: { anchor: [20, 0, 0], offset: [6, 0, 1] } },
    { geometry: { from: scene.elementGeometry(BOTTOM, { points: true }), to: scene.elementGeometry(TOP, { points: true }) }, bounds: BOUNDS });
  nearPoint(mid.dimension.extensions[0][0], [20, 0, -2], "from the bottom's plane");
  nearPoint(mid.dimension.extensions[1][0], [20, 0, 2], "from the top's plane");
  nearPoint(mid.dimension.extensions[0][1], [26, 0, -2]);
  // Placed by no code, it stands halfway between them, out to the side.
  const free = pmiConstruction({ ...thickness, presentation: null }, { geometry: { from: scene.elementGeometry(BOTTOM, { points: true }), to: scene.elementGeometry(TOP, { points: true }) }, bounds: BOUNDS });
  near(free.label[2], 0, "halfway up");
  near(free.dimension.from[2], -2);
  near(free.dimension.to[2], 2);
});

test("a basic dimension to a hole is drawn to its centre line, and between two holes square to both", async () => {
  const scene = await bracket();
  // The plate's left side (x = -20), the hole's wall (its axis z through the origin), the first peg's
  // (r 3, its axis z through x = 12): a float32 mesh's fitted axis is within a few micrometres.
  const SIDE = "i0/face/1", PEG = "i1/face/1";
  const close = (actual, expected, what) => expected.forEach((value, axis) => assert.ok(Math.abs(actual[axis] - value) < 1e-4, `${what}[${axis}] ${actual[axis]} is not ${value}`));
  const basic = (id, presentation) => entry({ id, kind: "dimension", presentation,
    dimension: { type: "distance", basic: true, nominal: { value: 20, unit: "mm", source: "geometry" }, tolerance: null } });
  const geometry = (from, to) => ({ from: scene.elementGeometry(from, { points: true }), to: scene.elementGeometry(to, { points: true }) });
  const fromSide = pmiConstruction(basic("hole-from-side", { anchor: [-10, -10, 2], offset: [0, -6, 0] }), { geometry: geometry(SIDE, HOLE), bounds: BOUNDS });
  close(fromSide.dimension.from, [-20, -16, 2], "on the side's plane");
  close(fromSide.dimension.to, [0, -16, 2], "level with the hole's axis");
  close(fromSide.dimension.extensions[0][0], [-20, -10, 2], "from the anchor's foot on the side");
  close(fromSide.dimension.extensions[1][0], [0, 0, 2], "from the hole's centre line");
  // Two holes: measured square to both axes, each extension line from its own centre line.
  const between = pmiConstruction(basic("peg-from-hole", null), { geometry: geometry(HOLE, PEG), bounds: BOUNDS });
  close([between.anchor[0], between.anchor[1]], [0, 0], "anchored on the hole's axis");
  near(between.dimension.from[0], between.anchor[0], "from the hole's axis");
  assert.ok(Math.abs(between.dimension.to[0] - 12) < 1e-4, `to the peg's axis: ${between.dimension.to}`);
  near(between.label[0], (between.dimension.from[0] + between.dimension.to[0]) / 2, "halfway between them");
  close([between.dimension.extensions[1][0][0], between.dimension.extensions[1][0][1]], [12, 0], "from the peg's centre line");
  // An axis that crosses what is measured makes none: the hole's runs along the top's normal.
  assert.equal(pmiConstruction(basic("crossing", null), { geometry: geometry(TOP, HOLE), bounds: BOUNDS }), null);
  assert.equal(pmiConstruction(basic("crossing", { anchor: [0, 0, 2], offset: [0, 0, 6] }), { geometry: geometry(TOP, HOLE), bounds: BOUNDS }).broken, true);
});

test("a feature not on the page draws at its placement or not at all, and a move changes only the offset", () => {
  const broken = pmiConstruction(flatness({ anchor: [0, 0, 2], offset: [0, 0, 6] }), { geometry: { feature: null }, bounds: BOUNDS });
  assert.equal(broken.broken, true);
  nearPoint(broken.anchor, [0, 0, 2], "where the code anchored it");
  nearPoint(broken.label, [0, 0, 8]);
  assert.equal(pmiConstruction(flatness(), { geometry: { feature: null }, bounds: BOUNDS }), null);
  assert.deepEqual(pmiMovedPlacement({ anchor: [1, 2, 3], offset: [0, 0, 1] }, [4, 2, 9]), { anchor: [1, 2, 3], offset: [3, 0, 6] });
});

test("a flag note stands out from its first face as a frame does; a general note and the general profile are drawn as no callout", async () => {
  const scene = await bracket();
  const note = (item = {}) => entry({ id: "mask", kind: "note", refs: [{ role: "feature", ref: "plate/top", written: "plate/top", status: "ok" }],
    note: { number: 2, text: "Mask before coating", general: false, annotations: [] }, ...item });
  const geometry = { feature: scene.elementGeometry(TOP, { points: true }) };
  const flag = pmiConstruction(note(), { geometry, bounds: BOUNDS });
  assert.deepEqual(flag, pmiConstruction(flatness(), { geometry, bounds: BOUNDS }), "where a frame on the face stands");
  near(flag.anchor[2], 2, "its leader on the top");
  const placed = pmiConstruction(note({ presentation: { anchor: [10, 5, 2], offset: [0, 0, 6] } }), { geometry, bounds: BOUNDS });
  assert.equal(placed.placed, "given");
  nearPoint(placed.label, [10, 5, 8]);
  // A general note is said in the notes, as the general profile is: neither is drawn on the part, placed or not.
  const general = note({ presentation: { anchor: [10, 5, 2], offset: [0, 0, 6] }, note: { number: 2, text: "Deburr", general: true, annotations: [] } });
  assert.equal(pmiConstruction(general, { geometry, bounds: BOUNDS }), null);
  const profile = entry({ id: "general", kind: "geometric_tolerance", geometric_tolerance: { characteristic: "surface_profile", value: 0.5, unit: "mm", datums: [], general: true } });
  assert.equal(pmiConstruction(profile, { geometry, bounds: BOUNDS }), null);
  // On several faces it stands on the first, turned from what stood there before it; the general
  // profile on the same face, said in the notes, takes no turn of it.
  const ref = at => ({ role: "feature", ref: at, written: at, status: "ok" });
  const topFlat = entry({ id: "top-flat", kind: "geometric_tolerance", refs: [ref("plate/top")], geometric_tolerance: { characteristic: "flatness", value: 0.05, unit: "mm", datums: [] } });
  const onBoth = note({ refs: [ref("plate/top"), ref("plate/bottom")] });
  const drawn = pmiConstructions([{ entry: { ...profile, refs: [ref("plate/top")] }, elements: [TOP] }, { entry: topFlat, elements: [TOP] },
    { entry: onBoth, elements: [TOP, BOTTOM] }], { geometry: id => scene.elementGeometry(id, { points: true }), bounds: BOUNDS });
  assert.deepEqual([...drawn.keys()], [":top-flat", ":mask"]);
  assert.deepEqual(drawn.get(":mask"), pmiConstruction(note(), { geometry, bounds: BOUNDS, turn: 1 }));
  assert.deepEqual([topFlat, onBoth, note(), general, profile].map(pmiDrawnOnPart), [true, true, true, false, false]);
});

test("a flag note naming annotations alone has no face to stand on: listed, and drawn nowhere, placed or not", () => {
  const onAnnotations = entry({ id: "inspect", kind: "note", presentation: { anchor: [10, 5, 2], offset: [0, 0, 6] },
    note: { number: 2, text: "Inspect every part", general: false, annotations: ["thickness"] } });
  assert.equal(onAnnotations.supported, true);
  assert.equal(pmiDrawnOnPart(onAnnotations), false);
  // Not a broken one at the code's placement: it never named a face to break.
  assert.equal(pmiConstruction(onAnnotations, { geometry: {}, bounds: BOUNDS }), null);
  assert.equal(pmiConstructions([{ entry: onAnnotations, elements: [] }], { geometry: () => null, bounds: BOUNDS }).size, 0);
});

test("a placement is in its part's frame: drawn where the part stands, and written back in its frame", () => {
  // Turned a quarter about z and moved 10 along x: the second peg's kind of placement.
  const matrix = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 10, 0, 0, 1];
  const placed = { anchor: [1, 0, 2], offset: [0, 3, 0] };
  const scene = pmiPresentationToScene(placed, matrix);
  nearPoint(scene.anchor, [10, 1, 2]);
  nearPoint(scene.offset, [-3, 0, 0], "an offset turns and does not move");
  const back = pmiPresentationToPart(scene, matrix);
  nearPoint(back.anchor, placed.anchor);
  nearPoint(back.offset, placed.offset);
  assert.equal(pmiPresentationToScene(placed, null), placed, "no placement, one frame");
});

// The constructions cadgen's stills are held to (`__fixtures__/pmi_plate/constructions.json`, which
// `cadgen/engine/render/pmi.py` is held to through `tests/python/packages/cadgen/engine/test_render_pmi.py`):
// what the viewer's own loop (`pmiConstructions`, as `useXbfPmi` calls it) makes of the plate the
// engine served (`__fixtures__/pmi_plate`, which its `make_fixtures.py` builds and captures again),
// as its code placed its PMI (v1), with no placement at all (every default: a feature's point, a
// distance at the face's edge, each turned from the last), with each basic dimension's ends swapped
// and unplaced (a hole's axis first: anchored on its centre line), after the edit that left the
// hole's callouts invalid (v3: its name now a flat face's, where it named a round one), with every
// kind (v4: limits, a surface profile on the hole, the general profile and a general note drawn as no
// callout, a flag note on the hole), placed and unplaced (the general profile and the general note,
// said in the notes, take no turn of a face), and v4 as its view A-A places what it places
// (`placements`, by key: the view's own placements, in its part's frame). The file was made by this loop over these
// fixtures; a deliberate change to the layout or the fixtures changes it, and the port follows it.
test("the constructions cadgen's stills are held to are the ones this layout makes", async () => {
  const variants = { "v1": structure => structure, "v1-unplaced": structure => ({ ...structure, pmi: structure.pmi.map(item => ({ ...item, presentation: null })) }),
    "v1-reversed": structure => ({ ...structure, pmi: structure.pmi.map(item => (item.dimension?.basic
      ? { ...item, presentation: null, refs: item.refs.map(ref => ({ ...ref, role: ref.role === "from" ? "to" : "from" })).reverse() } : item)) }),
    "v3": structure => structure, "v4": structure => structure,
    "v4-unplaced": structure => ({ ...structure, pmi: structure.pmi.map(item => ({ ...item, presentation: null })) }), "v4-A-A": structure => structure };
  // A variant drawn as a view places its PMI: the view's placements by each annotation's key.
  const placedBy = { "v4-A-A": "A-A" };
  const made = {};
  for (const [name, change] of Object.entries(variants)) {
    const version = name.split("-")[0];
    const served = JSON.parse(read(`pmi_plate/${version}/structure.json`));
    const structure = change(served);
    const fetch = async (url) => {
      if (url.endsWith("/api/look")) return new Response(read("look.json"));
      if (url.endsWith("/api/look/environment")) return new Response(ENVIRONMENT);
      const part = /\/part\/([^/]+)$/.exec(url);
      return new Response(part ? read(`pmi_plate/${version}/${part[1]}.xbm`) : JSON.stringify(structure));
    };
    const scene = createXbfScene(THREE, await loadXbfDocument("http://127.0.0.1:9/api/doc/pmi_plate", { fetch }));
    // One part, one occurrence: a ref's element is its name among the part's faces, the part's
    // placement its frame (an annotation linked to no part's, the scene's).
    const ordinals = new Map(Object.entries(structure.prototypes[0].faceNames).map(([ordinal, faceName]) => [faceName, Number(ordinal)]));
    const idOf = (ref) => {
      const element = parseEngineRef(ref)?.selectors[0]?.element;
      const ordinal = typeof element === "string" ? ordinals.get(element) : element?.ordinal;
      return Number.isInteger(ordinal) ? `i0/face/${ordinal}` : null;
    };
    const pmi = readXbfPmi(structure);
    const drawn = pmi.entries.map(entry => ({ entry, elements: entry.refs.map(ref => (ref.status === "ok" ? idOf(ref.ref) : null)),
      frame: entry.part === null ? null : structure.instances[0].matrix }));
    const view = pmi.views.find(item => item.name === placedBy[name]);
    const placements = view ? new Map(Object.entries(view.place).map(([id, at]) => [pmiKey(view.part, id), at])) : null;
    const constructions = pmiConstructions(drawn, { geometry: id => scene.elementGeometry(id, { points: true }), bounds: scene.restBounds, placements });
    made[name] = drawn.filter(({ entry }) => constructions.has(entry.key)).map(({ entry }) => ({ id: entry.id, construction: constructions.get(entry.key) }));
  }
  assert.ok(placedBy["v4-A-A"] && made["v4-A-A"].length, "v4's view A-A is in the fixture");
  const golden = JSON.parse(read("pmi_plate/constructions.json"));
  const close = (actual, expected, where) => {
    if (Array.isArray(expected)) { assert.equal(actual.length, expected.length, where); expected.forEach((value, index) => close(actual[index], value, `${where}[${index}]`)); return; }
    if (expected && typeof expected === "object") { assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), where); for (const key of Object.keys(expected)) close(actual[key], expected[key], `${where}.${key}`); return; }
    if (typeof expected === "number") { assert.ok(Math.abs(actual - expected) < 1e-9, `${where}: ${actual} is not ${expected}`); return; }
    assert.equal(actual, expected, where);
  };
  close(JSON.parse(JSON.stringify(made)), golden, "constructions");
});
