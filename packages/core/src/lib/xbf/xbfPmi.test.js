// An engine document's PMI as the viewer reads, says and asks for it (`xbfPmi.js`): the entries
// `structure.pmi` carries, read defensively; the callout each says; and the `cadgen.ap242` call
// a change in the viewer is, which Quick Edit hands the agent to write into the model.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { pmiCallText, pmiCallout, pmiChangeRequest, pmiChangeSettled, pmiDimensionPlaces, pmiEntryCall, pmiFreshId, pmiNumber, pmiPlaceText, pmiStatusText, pmiToleranceText, pyNumber, readXbfPmi } from "./xbfPmi.js";
import { pmiConstruction } from "./xbfPmiLayout.js";

// The annotations of a document as the viewer reads them (`readXbfPmi`'s `entries`).
const entriesOf = structure => readXbfPmi(structure).entries;
// The engine's own, as it served a plate built with `cadgen.ap242`'s calls (`__fixtures__/pmi_plate`,
// which its `make_fixtures.py` builds and captures again).
const served = version => JSON.parse(readFileSync(new URL(`./__fixtures__/pmi_plate/${version}/structure.json`, import.meta.url), "utf8"));

const TOP = "plate/f:bracket.fillet1~d3f70920d846";
const BOTTOM = "plate/f:bracket.fillet1~908aee34f872";
const HOLE = "plate/f:bracket.make_cylinder1.1;M:bracket.cut1";
const ref = (role, at, extra = {}) => ({ role, ref: at, written: at, status: "ok", candidates: null, ...extra });

// The supported subset, as `cadgen.engine.pmi` serves it.
const PMI = [
  { id: "A", kind: "datum", label: null, status: "ok", problem: null, refs: [ref("feature", BOTTOM)], datum: { letter: "A" }, presentation: null, xcaf_type: null },
  { id: "thickness", kind: "dimension", label: null, status: "ok", problem: null, refs: [ref("from", BOTTOM), ref("to", TOP)],
    dimension: { type: "distance", nominal: { value: 4.000000001, unit: "mm", source: "geometry" }, tolerance: { type: "plus_minus", upper: 0.2, lower: -0.2 } },
    presentation: { anchor: [20, 0, -2], offset: [6, 0, 2] }, xcaf_type: null },
  { id: "hole-dia", kind: "dimension", label: null, status: "ok", problem: null, refs: [ref("feature", HOLE)],
    dimension: { type: "diameter", nominal: { value: 8, unit: "mm", source: "geometry" }, tolerance: { type: "plus_minus", upper: 0.1, lower: 0 } },
    presentation: null, xcaf_type: null },
  { id: "top-flat", kind: "geometric_tolerance", label: null, status: "ok", problem: null, refs: [ref("feature", TOP)],
    geometric_tolerance: { characteristic: "flatness", value: 0.05, unit: "mm", zone: null, modifier: null, datums: [] }, presentation: null, xcaf_type: null },
  { id: "hole-pos", kind: "geometric_tolerance", label: null, status: "ok", problem: null, refs: [ref("feature", HOLE)],
    geometric_tolerance: { characteristic: "position", value: 0.1, unit: "mm", zone: "diameter", modifier: null, datums: ["A"] }, presentation: null, xcaf_type: null },
];

test("the document's PMI is read as it is served, and a document without any has none", () => {
  assert.deepEqual(readXbfPmi({ name: "bracket" }), { entries: [], views: [], notes: [], coverage: [] });
  const read = entriesOf({ pmi: PMI });
  assert.deepEqual(read.map(entry => [entry.id, entry.kind, entry.supported]), [
    ["A", "datum", true], ["thickness", "dimension", true], ["hole-dia", "dimension", true], ["top-flat", "geometric_tolerance", true], ["hole-pos", "geometric_tolerance", true]]);
  const thickness = read[1];
  assert.deepEqual(thickness.dimension, { type: "distance", basic: false, nominal: 4.000000001, unit: "mm", source: "geometry", tolerance: { type: "plus_minus", upper: 0.2, lower: -0.2 } });
  assert.deepEqual(thickness.refs.map(item => [item.role, item.ref, item.status]), [["from", BOTTOM, "ok"], ["to", TOP, "ok"]]);
  assert.deepEqual(thickness.presentation, { anchor: [20, 0, -2], offset: [6, 0, 2] });
  assert.deepEqual(read[4].tolerance, { characteristic: "position", value: 0.1, unit: "mm", zone: "diameter", modifier: null, datums: ["A"], general: false });
});

test("a basic dimension is an exact distance: boxed, with no tolerance, made by dimensional_location(basic=True)", () => {
  const SIDE = "plate/f:bracket.make_box1.1;M:bracket.fillet1";
  const [basic] = entriesOf({ pmi: [{ id: "hole-from-side", kind: "dimension", status: "ok", refs: [ref("from", SIDE), ref("to", HOLE)],
    // A tolerance a document puts on one is not read: it is exact.
    dimension: { type: "distance", basic: true, nominal: { value: 20, unit: "mm", source: "geometry" }, tolerance: { type: "plus_minus", upper: 0.1, lower: -0.1 } },
    presentation: { anchor: [-10, -10, 2], offset: [0, -6, 0] } }] });
  assert.equal(basic.supported, true);
  assert.deepEqual([basic.dimension.basic, basic.dimension.tolerance], [true, null]);
  const said = pmiCallout(basic);
  assert.deepEqual([said.basic, said.nominal, said.tolerance, said.title, said.text], [true, "20", null, "Basic distance", "20 basic"]);
  assert.equal(pmiCallText(pmiEntryCall(basic, { presentation: null })), `dimensional_location("hole-from-side", "${SIDE}", "${HOLE}", basic=True)`);
  assert.equal(pmiCallText(pmiEntryCall(basic)),
    `dimensional_location("hole-from-side", "${SIDE}", "${HOLE}", basic=True, presentation=place(anchor=(-10, -10, 2), offset=(0, -6, 0)))`);
  // Exact: a tolerance given one makes no call, rather than one the engine refuses.
  assert.equal(pmiCallText({ kind: "dimension", type: "distance", basic: true, id: "b", from: SIDE, to: HOLE, tolerance: { type: "plus_minus", upper: 0.1, lower: -0.1 } }), null);
  // A basic of another type is told, not drawn.
  const [diameter] = entriesOf({ pmi: [{ id: "d", kind: "dimension", status: "ok", refs: [], dimension: { type: "diameter", basic: true, nominal: { value: 8 }, tolerance: null } }] });
  assert.match(diameter.unsupported, /basic diameter/);
});

test("an entry the viewer does not draw is kept and says why, never dropped or guessed", () => {
  const read = entriesOf({ pmi: [
    { id: "profile", kind: "unsupported", status: "ok", refs: [], presentation: null, xcaf_type: "XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface" },
    { id: "angle", kind: "dimension", status: "ok", refs: [], dimension: { type: "angle", nominal: { value: 90, unit: "deg" }, tolerance: null } },
    { id: "runout", kind: "geometric_tolerance", status: "ok", refs: [], geometric_tolerance: { characteristic: "total_runout", value: 0.1, datums: [] } },
    { id: "bad", kind: "dimension", status: "ok", refs: [], dimension: { type: "distance", nominal: { value: "4" }, tolerance: null } },
  ] });
  assert.deepEqual(read.map(entry => [entry.id, entry.supported]), [["profile", false], ["angle", false], ["runout", false], ["bad", false]]);
  assert.match(read[0].unsupported, /ProfileOfSurface is not one the viewer draws/);
  assert.match(read[1].unsupported, /angle dimension/);
  assert.match(read[2].unsupported, /total_runout/);
  // A nominal that is not a number is no nominal: the viewer never reads one into it.
  assert.equal(read[3].dimension.nominal, null);
  assert.match(read[3].unsupported, /no nominal/);
});

test("one the viewer does not draw says the engine's reason where it gives one, the viewer's own where not", () => {
  const read = entriesOf({ pmi: [
    { id: "profile", kind: "unsupported", status: "ok", refs: [], xcaf_type: "XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface",
      reason: "profile of surface is not a characteristic this holds; it has modifiers" },
    { id: "edge", kind: "unsupported", status: "ok", refs: [], xcaf_type: "XCAFDimTolObjects_DatumObject", reason: null },
    // What is drawn is the viewer's to say: a reason given beside one it draws makes it no less drawn.
    { id: "A", kind: "datum", status: "ok", refs: [], datum: { letter: "A" }, reason: "linked to an edge" },
  ] });
  assert.deepEqual(read.map(entry => [entry.id, entry.supported, entry.unsupported]), [
    ["profile", false, "profile of surface is not a characteristic this holds; it has modifiers"],
    ["edge", false, "XCAFDimTolObjects_DatumObject is not one the viewer draws"],
    ["A", true, ""]]);
});

test("a dimension whose reference broke has no nominal, and is said as unknown, not unsupported", () => {
  const [broken] = entriesOf({ pmi: [{ id: "thickness", kind: "dimension", status: "missing", problem: null,
    refs: [{ role: "from", ref: BOTTOM, written: BOTTOM, status: "ok" }, { role: "to", ref: "plate/f:gone", written: "plate/f:gone", status: "missing", candidates: null }],
    dimension: { type: "distance", nominal: null, tolerance: { type: "plus_minus", upper: 0.2, lower: -0.2 } }, presentation: { anchor: [0, 0, -2], offset: [8, 0, 2] } }] });
  assert.equal(broken.supported, true);
  assert.equal(pmiCallout(broken).text, "? ±0.2");
  // The engine's foreign entries name no written ref: theirs is read as nothing, never "null".
  const [foreign] = entriesOf({ pmi: [{ id: "datum", kind: "datum", status: "ok", refs: [{ role: "feature", ref: TOP, written: null, status: "ok", candidates: null }], datum: { letter: "B" } }] });
  assert.deepEqual([foreign.refs[0].ref, foreign.refs[0].written], [TOP, TOP]);
});

test("a tolerance the code did not supply is none, and a malformed one is none too", () => {
  const read = entriesOf({ pmi: [
    { id: "a", kind: "dimension", status: "ok", refs: [], dimension: { type: "distance", nominal: { value: 4, unit: "mm" }, tolerance: null } },
    { id: "b", kind: "dimension", status: "ok", refs: [], dimension: { type: "distance", nominal: { value: 4, unit: "mm" }, tolerance: { type: "plus_minus", upper: 0.1 } } },
  ] });
  assert.equal(read[0].dimension.tolerance, null);
  assert.equal(read[1].dimension.tolerance, null);
  assert.equal(pmiCallout(read[0]).text, "4");
});

test("a callout says the nominal at the tolerance's places, and each kind as a drawing writes it", () => {
  const [datum, thickness, diameter, flatness, position] = entriesOf({ pmi: PMI }).map(pmiCallout);
  assert.deepEqual([datum.kind, datum.letter, datum.text], ["datum", "A", "Datum A"]);
  assert.equal(thickness.text, "4.0 ±0.2");
  assert.deepEqual([thickness.tolerance.upper, thickness.tolerance.lower], ["+0.2", "−0.2"]);
  assert.equal(diameter.text, "⌀8.0 +0.1/0");
  assert.equal(diameter.diameter, true);
  assert.deepEqual([flatness.kind, flatness.characteristic, flatness.value, flatness.datums], ["frame", "flatness", "0.05", []]);
  assert.equal(flatness.text, "Flatness 0.05");
  assert.equal(position.text, "Position ⌀0.1 | A");
});

test("a nominal is written at its tolerance's places or at what it needs, whichever is more", () => {
  const said = (type, value, tolerance, basic = false) => pmiCallout(entriesOf({ pmi: [{ id: "d", kind: "dimension", status: "ok", refs: [],
    dimension: { type, basic, nominal: { value, unit: "mm", source: "geometry" }, tolerance } }] })[0]).text;
  const plusMinus = value => ({ type: "plus_minus", upper: value, lower: -value });
  assert.equal(said("diameter", 6.35, plusMinus(0.1)), "⌀6.35 ±0.1");
  assert.equal(said("distance", 25.4, plusMinus(0.05)), "25.40 ±0.05");
  // With no tolerance, and exact: what the value needs, up to four places.
  assert.equal(said("distance", 3.175, null, true), "3.175 basic");
  assert.equal(said("distance", 12.345678, null), "12.3457");
});

test("tolerances and numbers are written with true minus signs and one count of places", () => {
  assert.deepEqual(pmiToleranceText({ upper: 0.05, lower: -0.1 }), { symmetric: false, text: "+0.05/−0.10", upper: "+0.05", lower: "−0.10", places: 2 });
  assert.equal(pmiToleranceText({ upper: 0, lower: -0.1 }).text, "0/−0.1");
  assert.equal(pmiToleranceText(null), null);
  assert.equal(pmiNumber(-0.0000001, 2), "0.00");
  assert.equal(pmiNumber(12.5), "12.5");
});

test("a reference that names nothing, or several things, is said in words", () => {
  const [missing, ambiguous] = entriesOf({ pmi: [
    { id: "top-flat", kind: "geometric_tolerance", status: "missing", problem: null, refs: [{ role: "feature", ref: "plate/f:gone", written: "plate/f:gone", status: "missing", candidates: null }],
      geometric_tolerance: { characteristic: "flatness", value: 0.05, unit: "mm", datums: [] }, presentation: { anchor: [0, 0, 2], offset: [0, 0, 6] } },
    { id: "A", kind: "datum", status: "ambiguous", problem: null, refs: [{ role: "feature", ref: "face 3", written: "face 3", status: "ambiguous", candidates: [TOP, BOTTOM] }],
      datum: { letter: "A" } },
  ] });
  assert.equal(missing.status, "missing");
  assert.equal(pmiStatusText(missing), "plate/f:gone names nothing in this version");
  assert.deepEqual(missing.presentation, { anchor: [0, 0, 2], offset: [0, 0, 6] });
  assert.equal(pmiStatusText(ambiguous), "face 3 names 2 elements");
  assert.deepEqual(ambiguous.refs[0].candidates, [TOP, BOTTOM]);
  // The engine's own words win where it gives them.
  assert.equal(pmiStatusText({ status: "missing", problem: "plate.body.6 is now f:plate.body.6", refs: [] }), "plate.body.6 is now f:plate.body.6");
  assert.equal(pmiStatusText({ status: "ok", refs: [] }), "");
});

test("a new annotation is the cadgen.ap242 call that declares it, its refs verbatim", () => {
  assert.equal(pmiCallText({ kind: "datum", id: "B", letter: "B", ref: TOP }), `datum("B", "${TOP}")`);
  assert.equal(pmiCallText({ kind: "dimension", type: "distance", id: "thickness", from: BOTTOM, to: TOP, tolerance: { upper: 0.2, lower: -0.2 } }),
    `dimensional_location("thickness", "${BOTTOM}", "${TOP}", tolerance=plus_minus_tolerance(0.2))`);
  assert.equal(pmiCallText({ kind: "dimension", type: "diameter", id: "hole-dia", ref: HOLE, tolerance: { upper: 0.1, lower: 0 } }),
    `dimensional_size("hole-dia", "${HOLE}", tolerance=plus_minus_tolerance(0.1, 0))`);
  // No tolerance given, none written: a dimension is not toleranced by the viewer.
  assert.equal(pmiCallText({ kind: "dimension", type: "diameter", id: "hole-dia", ref: HOLE, tolerance: null }), `dimensional_size("hole-dia", "${HOLE}")`);
  assert.equal(pmiCallText({ kind: "geometric_tolerance", characteristic: "flatness", id: "top-flat", ref: TOP, value: 0.05 }), `flatness_tolerance("top-flat", "${TOP}", 0.05)`);
  assert.equal(pmiCallText({ kind: "geometric_tolerance", characteristic: "position", id: "hole-pos", ref: HOLE, value: 0.1, datums: ["A"], diameterZone: true }),
    `position_tolerance("hole-pos", "${HOLE}", 0.1, datums=["A"], diameter_zone=True)`);
  // What a kind needs and lacks is never filled in.
  assert.equal(pmiCallText({ kind: "geometric_tolerance", characteristic: "flatness", id: "top-flat", ref: TOP, value: null }), null);
  assert.equal(pmiCallText({ kind: "dimension", type: "distance", id: "x", from: BOTTOM, to: "" }), null);
  assert.equal(pmiCallText({ kind: "datum", id: "", letter: "A", ref: TOP }), null);
});

test("an edit names its references as this build resolves them and changes only what was changed", () => {
  const [, thickness, , flatness] = entriesOf({ pmi: PMI });
  assert.equal(pmiCallText(pmiEntryCall(thickness, { tolerance: { upper: 0.1, lower: -0.05 } })),
    `dimensional_location("thickness", "${BOTTOM}", "${TOP}", tolerance=plus_minus_tolerance(0.1, -0.05), presentation=place(anchor=(20, 0, -2), offset=(6, 0, 2)))`);
  assert.equal(pmiCallText(pmiEntryCall(thickness, { tolerance: null, presentation: null })), `dimensional_location("thickness", "${BOTTOM}", "${TOP}")`);
  assert.equal(pmiCallText(pmiEntryCall(flatness, { value: 0.02 })), `flatness_tolerance("top-flat", "${TOP}", 0.02)`);
  // A placement is where it is drawn: the call says the same, placed.
  assert.equal(pmiCallText(pmiEntryCall(flatness, { presentation: { anchor: [1.23456, 0, 2], offset: [0, -0.00001, 8] } })),
    `flatness_tolerance("top-flat", "${TOP}", 0.05, presentation=place(anchor=(1.2346, 0, 2), offset=(0, 0, 8)))`);
});

test("numbers are written without float noise, and fresh ids never collide", () => {
  assert.equal(pyNumber(0.1 + 0.2), "0.3");
  assert.equal(pyNumber(-0.00001), "0");
  assert.equal(pmiPlaceText({ anchor: [1, 2, 3], offset: [0.5, 0, -1] }), "place(anchor=(1, 2, 3), offset=(0.5, 0, -1))");
  assert.equal(pmiFreshId("flatness", ["top-flat"]), "flatness");
  assert.equal(pmiFreshId("flatness", ["flatness", "flatness-2"]), "flatness-3");
});

test("a reference the code wrote as a face of the body is called by its canonical ref, which names the same face", () => {
  const [entry] = entriesOf({ pmi: [{ id: "top-flat", kind: "geometric_tolerance", status: "ok", refs: [{ role: "feature", ref: TOP, written: "face 2", status: "ok" }],
    geometric_tolerance: { characteristic: "flatness", value: 0.05, unit: "mm", datums: [] } }] });
  assert.equal(pmiCallText(pmiEntryCall(entry, { value: 0.02 })), `flatness_tolerance("top-flat", "${TOP}", 0.02)`);
  // One that names nothing now is called as the code wrote it: there is nothing else to call it.
  const [broken] = entriesOf({ pmi: [{ id: "top-flat", kind: "geometric_tolerance", status: "missing", refs: [{ role: "feature", ref: "plate/f:gone", written: "plate/f:gone", status: "missing" }],
    geometric_tolerance: { characteristic: "flatness", value: 0.05, unit: "mm", datums: [] } }] });
  assert.equal(pmiCallText(pmiEntryCall(broken)), `flatness_tolerance("top-flat", "plate/f:gone", 0.05)`);
});

test("a change goes to the agent as what to do to the model's annotate call, its cadgen.ap242 names, then the call exactly", () => {
  const [, thickness] = entriesOf({ pmi: PMI });
  const add = { kind: "geometric_tolerance", characteristic: "flatness", id: "flatness", ref: BOTTOM, value: 0.02 };
  assert.equal(pmiChangeRequest({ kind: "add", call: add }),
    `Add this PMI to the model's annotate(...) call (from cadgen.ap242 import annotate, flatness_tolerance):\nflatness_tolerance("flatness", "${BOTTOM}", 0.02)`);
  const values = { tolerance: { upper: 0.1, lower: -0.05 } };
  assert.equal(pmiChangeRequest({ kind: "edit", id: "thickness", values, call: pmiEntryCall(thickness, values), placementOnly: false }),
    `Change the PMI "thickness" in the model's annotate(...) call (from cadgen.ap242 import annotate, dimensional_location, place, plus_minus_tolerance): `
    + `tolerance=plus_minus_tolerance(0.1, -0.05). Keep its references as the code writes them. `
    + `The whole call, its references as this build resolves them:\ndimensional_location("thickness", "${BOTTOM}", "${TOP}", tolerance=plus_minus_tolerance(0.1, -0.05), presentation=place(anchor=(20, 0, -2), offset=(6, 0, 2)))`);
  const moved = { presentation: { anchor: [20, 0, -2], offset: [10, 0, 2] } };
  assert.match(pmiChangeRequest({ kind: "edit", id: "thickness", values: moved, call: pmiEntryCall(thickness, moved), placementOnly: true }),
    /^Move the PMI "thickness" in the model's annotate\(\.\.\.\) call \(from cadgen\.ap242 import annotate, dimensional_location, place, plus_minus_tolerance\), its placement only \(what it says is unchanged\): presentation=place\(anchor=\(20, 0, -2\), offset=\(10, 0, 2\)\)\./);
  assert.equal(pmiChangeRequest({ kind: "add", call: { ...add, value: null } }), "");
});

test("a change the document now says is settled, and one it does not yet say is not", () => {
  const read = entriesOf({ pmi: PMI });
  const thickness = read[1];
  const values = { tolerance: { type: "plus_minus", upper: 0.1, lower: -0.05 } };
  const change = { kind: "edit", part: null, id: "thickness", values, call: pmiEntryCall(thickness, values) };
  assert.equal(pmiChangeSettled(change, read), false);
  const built = entriesOf({ pmi: PMI.map(item => (item.id === "thickness" ? { ...item, dimension: { ...item.dimension, tolerance: values.tolerance } } : item)) });
  assert.equal(pmiChangeSettled(change, built), true);
  assert.equal(pmiChangeSettled({ kind: "add", part: null, id: "flatness", call: {} }, read), false);
  assert.equal(pmiChangeSettled({ kind: "add", part: null, id: "top-flat", call: {} }, read), true);
  // An edit of an annotation the document no longer holds is not settled: it is the person's to drop.
  assert.equal(pmiChangeSettled({ ...change, id: "gone" }, read), false);
});

test("a change to a view is settled by the document's views, never by an annotation of its name", () => {
  const { entries, views } = readXbfPmi(served("v4"));
  const [section] = views;
  const add = { kind: "add", part: 0, id: "A-A", call: pmiEntryCall(section) };
  assert.equal(pmiChangeSettled(add, entries, views), true);
  assert.equal(pmiChangeSettled({ ...add, id: "B-B", call: { ...add.call, name: "B-B" } }, entries, views), false);
  // A view "A" asked for is not the datum A the part holds.
  assert.equal(pmiChangeSettled({ ...add, id: "A", call: { ...add.call, name: "A" } }, entries, views), false);
  const values = { section: { axis: "y", at: 2, invert: true } };
  const edit = { kind: "edit", part: 0, id: "A-A", values, call: pmiEntryCall(section, values) };
  assert.equal(pmiChangeSettled(edit, entries, views), false);
  assert.equal(pmiChangeSettled(edit, entries, [{ ...section, section: values.section }]), true);
  // Served without views, none is settled.
  assert.equal(pmiChangeSettled(add, entries), false);
});

test("an edit keeps what the code said beside its values: a position's zone, round or not, and its label", () => {
  const position = (item = {}) => entriesOf({ pmi: [{ id: "hole-pos", kind: "geometric_tolerance", label: "Hole location", status: "ok",
    refs: [ref("feature", HOLE)], geometric_tolerance: { characteristic: "position", value: 0.1, unit: "mm", zone: null, modifier: null, datums: ["A"] }, ...item }] });
  const values = { value: 0.2 };
  const call = pmiEntryCall(position()[0], values);
  // A zone that is not a diameter's says so: the engine's position takes a diameter's unless told.
  assert.equal(pmiCallText(call), `position_tolerance("hole-pos", "${HOLE}", 0.2, datums=["A"], diameter_zone=False, label="Hole location")`);
  const change = { kind: "edit", part: null, id: "hole-pos", values, call };
  const built = gdt => position({ geometric_tolerance: { characteristic: "position", value: 0.2, unit: "mm", zone: null, datums: ["A"], ...gdt } });
  assert.equal(pmiChangeSettled(change, built({})), true);
  // A build that made the zone round, or dropped the label, has not done what was asked.
  assert.equal(pmiChangeSettled(change, built({ zone: "diameter" })), false);
  assert.equal(pmiChangeSettled(change, built({}).map(entry => ({ ...entry, label: "" }))), false);
});

test("an id is unique on its part only: two parts' datum A are two entries, each asked for by its part and its own id", () => {
  const PEG_END = "bracket/peg/f:bracket.make_cylinder1.2";
  const datum = (part, at) => ({ id: "A", kind: "datum", status: "ok", part, refs: [ref("feature", at)], datum: { letter: "A" } });
  const raw = [datum(0, BOTTOM), datum(1, PEG_END)];
  const read = entriesOf({ pmi: raw });
  assert.deepEqual(read.map(entry => [entry.key, entry.id, entry.part]), [["0:A", "A", 0], ["1:A", "A", 1]]);
  // One the document repeats on a part is kept apart by its place.
  assert.deepEqual(entriesOf({ pmi: [...raw, datum(1, PEG_END)] }).map(entry => entry.key), ["0:A", "1:A", "1:A#3"]);
  // The peg's moved: asked for by its own id, in its part's call, and settled by the peg's alone.
  const presentation = { anchor: [0, 0, 8], offset: [0, 0, 6] };
  const values = { presentation };
  const change = { kind: "edit", part: 1, partName: "peg", id: "A", values, call: pmiEntryCall(read[1], values), placementOnly: true };
  assert.match(pmiChangeRequest(change), /^Move the PMI "A" in the annotate\(\.\.\.\) call of the model's part "peg" \(from cadgen\.ap242 import annotate, datum, place\), its placement only/);
  const placed = part => entriesOf({ pmi: raw.map(item => (item.part === part ? { ...item, presentation } : item)) });
  assert.equal(pmiChangeSettled(change, placed(1)), true);
  assert.equal(pmiChangeSettled(change, placed(0)), false, "the plate's A placed there is not the peg's");
  // A new one is its part's: the plate's A is not the peg's B, nor the peg's A the plate's.
  assert.equal(pmiChangeSettled({ kind: "add", part: 0, id: "A", call: {} }, entriesOf({ pmi: [datum(1, PEG_END)] })), false);
  assert.match(pmiChangeRequest({ kind: "add", part: 0, partName: "plate", id: "B", call: { kind: "datum", id: "B", letter: "B", ref: TOP } }),
    /^Add this PMI to the annotate\(\.\.\.\) call of the model's part "plate" \(from cadgen\.ap242 import annotate, datum\):\ndatum\("B"/);
});

// The engine's plate as made (v1), and after an edit put a square cut where the hole was (v3): the
// hole's name now on a flat face, which a diameter, a position and a distance from a face square to
// it cannot stand on, and a distance from a parallel face measures to as it now is.
test("the PMI the engine serves reads whole, and a reference an edit left on the wrong kind of face is invalid", () => {
  const made = entriesOf(served("v1"));
  assert.deepEqual(made.map(entry => [entry.id, entry.supported, entry.status, entry.part]), [
    ["A", true, "ok", 0], ["thickness", true, "ok", 0], ["hole-diameter", true, "ok", 0], ["hole-from-front", true, "ok", 0],
    ["hole-from-left", true, "ok", 0], ["top-flatness", true, "ok", 0], ["hole-position", true, "ok", 0]]);
  assert.deepEqual(made.map(entry => pmiCallout(entry).text), ["Datum A", "10.0 ±0.2", "⌀10.0 +0.1/0", "30 basic", "50 basic", "Flatness 0.05", "Position ⌀0.1 | A"]);
  const cut = entriesOf(served("v3"));
  // What broke is still its part's: linked to no geometry, known by the same key.
  assert.deepEqual(cut.map(entry => [entry.key, entry.status]), [
    ["0:A", "ok"], ["0:thickness", "ok"], ["0:hole-diameter", "invalid"], ["0:hole-from-front", "invalid"],
    ["0:hole-from-left", "ok"], ["0:top-flatness", "ok"], ["0:hole-position", "invalid"]]);
  const hole = cut.find(entry => entry.id === "hole-diameter");
  assert.deepEqual([hole.supported, hole.dimension.nominal], [true, null]);
  assert.match(pmiStatusText(hole), /is a plane face; a diameter is on a cylinder face/);
  assert.match(pmiStatusText(cut.find(entry => entry.id === "hole-position")), /is a plane face; a position is on a cylinder face/);
  const fromFront = cut.find(entry => entry.id === "hole-from-front");
  assert.deepEqual([fromFront.dimension.basic, pmiCallout(fromFront).text], [true, "? basic"]);
  assert.match(pmiStatusText(fromFront), /are not parallel planes/);
  // One that can stand on the cut's flat face is measured to it.
  const fromLeft = cut.find(entry => entry.id === "hole-from-left");
  assert.deepEqual([fromLeft.dimension.nominal, pmiCallout(fromLeft).text, pmiStatusText(fromLeft)], [44, "44 basic", ""]);
});

// The same plate as a model-based definition (v4): the thickness given limits, a surface profile on
// the hole, a general profile 0.5 to A (Note 1), a general note and a flag note on the hole and its
// diameter, and two views (a section A-A through the hole, and an iso).
const V4_BOTTOM = "plate/f:edit_plate.body_make_box1.5;M:edit_plate.body";
const V4_TOP = "plate/f:edit_plate.body_make_box1.6;M:edit_plate.body";
const V4_HOLE = "plate/f:edit_plate.cut.1;M:edit_plate.body";
const V4_SIDES = [1, 3, 4, 2].map(n => `plate/f:edit_plate.body_make_box1.${n}`);

test("limits are written stacked at one places count and need no nominal", () => {
  assert.deepEqual(pmiToleranceText({ type: "limits", lower: 10, upper: 10.05 }), { limits: true, upper: "10.05", lower: "10.00", text: "10.00–10.05", places: 2 });
  // The code's: its nominal measured, and not said; its limits at their own places, not its nominal's.
  const thickness = entriesOf(served("v4")).find(entry => entry.id === "thickness");
  assert.deepEqual([thickness.supported, thickness.dimension.nominal, thickness.dimension.tolerance], [true, 10, { type: "limits", lower: 9.8, upper: 10.2 }]);
  const said = pmiCallout(thickness);
  assert.deepEqual([said.nominal, said.tolerance.limits, said.tolerance.upper, said.tolerance.lower, said.text], [null, true, "10.2", "9.8", "9.8–10.2"]);
  assert.equal(pmiDimensionPlaces({ ...thickness.dimension, nominal: 10.025 }), 1);
  // Another system's: the file states its limits and no nominal, and it is drawn all the same, a diameter's ⌀ before them.
  const file = (tolerance) => entriesOf({ pmi: [{ id: "bore", kind: "dimension", status: "ok", refs: [ref("feature", HOLE)],
    dimension: { type: "diameter", basic: false, nominal: null, tolerance } }] })[0];
  const bore = file({ type: "limits", lower: 10, upper: 10.05 });
  assert.deepEqual([bore.supported, bore.dimension.nominal, pmiCallout(bore).diameter, pmiCallout(bore).text], [true, null, true, "⌀10.00–10.05"]);
  // Deviations are from a nominal, so one with none is not drawn; limits malformed are none, never guessed.
  assert.match(file({ type: "plus_minus", upper: 0.1, lower: -0.1 }).unsupported, /no nominal/);
  assert.deepEqual([file({ type: "limits", lower: 10 }).dimension.tolerance, file({ type: "limits", lower: 10 }).supported], [null, false]);
});

test("a surface profile names its faces and its datums", () => {
  const profile = entriesOf(served("v4")).find(entry => entry.id === "hole-profile");
  assert.equal(profile.supported, true);
  assert.deepEqual(profile.tolerance, { characteristic: "surface_profile", value: 0.2, unit: "mm", zone: null, modifier: null, datums: ["A"], general: false });
  assert.deepEqual(profile.refs.map(item => [item.role, item.ref]), [["feature", V4_HOLE]]);
  const said = pmiCallout(profile);
  assert.deepEqual([said.kind, said.characteristic, said.title, said.text], ["frame", "surface_profile", "Surface profile", "Surface profile 0.2 | A"]);
  // One requirement on several faces, of any kind, to no datum.
  const [both] = entriesOf({ pmi: [{ id: "both", kind: "geometric_tolerance", status: "ok", refs: [ref("feature", TOP), ref("feature", HOLE)],
    geometric_tolerance: { characteristic: "surface_profile", value: 0.1, unit: "mm", zone: null, datums: [], general: false } }] });
  assert.deepEqual([both.supported, both.refs.map(item => item.ref), pmiCallout(both).text], [true, [TOP, HOLE], "Surface profile 0.1"]);
});

test("the general profile is Note 1 and draws no callout", () => {
  const read = readXbfPmi(served("v4"));
  const general = read.entries.find(entry => entry.id === "general");
  assert.deepEqual([general.supported, general.status, general.tolerance.general], [true, "ok", true]);
  // Its refs are the faces it covers this build, the code's own none: each known by its canonical ref.
  assert.deepEqual(general.refs.map(item => [item.ref, item.written]), V4_SIDES.map(side => [side, side]));
  assert.deepEqual(pmiCallout(general), { kind: "general_profile", number: 1, title: "Note 1", text: "Unless otherwise noted, all surfaces profile 0.5 to A" });
  assert.equal(read.notes[0], general);
  // A frame would stand on its first face; the general profile is said in the notes, never drawn on the part.
  const plane = { feature: { surface: { type: "plane", origin: [0, 0, 0], normal: [0, 0, 1] }, points: [[0, 0, 0], [1, 0, 0]] } };
  assert.equal(pmiConstruction(general, { geometry: plane }), null);
  // Its value at its own places, its datums joined, or none; one every face of which is controlled otherwise is ok with no ref at all.
  const said = (value, datums) => {
    const [entry] = entriesOf({ pmi: [{ id: "g", kind: "geometric_tolerance", status: "ok", refs: [],
      geometric_tolerance: { characteristic: "surface_profile", value, unit: "mm", zone: null, datums, general: true } }] });
    assert.equal(entry.supported, true);
    return pmiCallout(entry).text;
  };
  assert.equal(said(0.25, ["A", "B", "C"]), "Unless otherwise noted, all surfaces profile 0.25 to A|B|C");
  assert.equal(said(1, []), "Unless otherwise noted, all surfaces profile 1");
});

test("notes come numbered, flag notes with their faces", () => {
  const read = readXbfPmi(served("v4"));
  assert.deepEqual(read.notes.map((entry) => { const said = pmiCallout(entry); return [entry.key, said.kind, said.number, said.flag, said.text]; }), [
    ["0:general", "general_profile", 1, undefined, "Unless otherwise noted, all surfaces profile 0.5 to A"],
    ["0:edges", "note", 2, false, "Break all sharp edges 0.2 max"],
    ["0:mask", "note", 3, true, "Mask these features before coating with primer"]]);
  const [, edges, mask] = read.notes;
  assert.deepEqual([edges.supported, edges.refs, edges.note], [true, [], { number: 2, text: "Break all sharp edges 0.2 max", general: true, annotations: [] }]);
  assert.deepEqual(pmiCallout(mask), { kind: "note", number: 3, flag: true, title: "Note 3", text: "Mask these features before coating with primer" });
  assert.deepEqual([mask.refs.map(item => [item.role, item.ref]), mask.note.annotations], [[["feature", V4_HOLE]], ["hole-diameter"]]);
  // Each part's by its number.
  const note = (part, id, number) => ({ id, kind: "note", status: "ok", part, refs: [], note: { number, text: id, general: true, annotations: [] } });
  assert.deepEqual(readXbfPmi({ pmi: [note(1, "b", 2), note(0, "d", 3), note(0, "c", 2)] }).notes.map(entry => entry.key), ["0:c", "0:d", "1:b"]);
  // One whose face an edit removed keeps its number and its text, and says what broke.
  const [gone] = entriesOf({ pmi: [{ id: "mask", kind: "note", status: "missing", part: 0, refs: [{ role: "feature", ref: "plate/f:gone", written: "plate/f:gone", status: "missing" }],
    note: { number: 2, text: "Mask before coating", general: false, annotations: [] } }] });
  assert.deepEqual([gone.supported, pmiCallout(gone).number, pmiCallout(gone).flag, pmiStatusText(gone)], [true, 2, true, "plate/f:gone names nothing in this version"]);
  // A note with no words or no number is told, never drawn as one.
  assert.match(entriesOf({ pmi: [{ ...note(0, "e", 2), note: { number: 2, text: "", general: true, annotations: [] } }] })[0].unsupported, /no text/);
  assert.match(entriesOf({ pmi: [{ ...note(0, "e", 2), note: { text: "Deburr", general: true, annotations: [] } }] })[0].unsupported, /no number/);
});

test("views carry their camera, section, shows and placements, keyed by part", () => {
  const read = readXbfPmi(served("v4"));
  const [section, iso] = read.views;
  assert.deepEqual(section, { key: "0:A-A", kind: "view", part: 0, name: "A-A", label: "",
    camera: { preset: "front", direction: [0, -1, 0], up: [0, 0, 1], projection: "orthographic" },
    section: { axis: "y", at: 0, invert: true }, shows: ["hole-diameter", "hole-position", "hole-profile", "mask"],
    place: { "hole-diameter": { anchor: [5, 0, 0], offset: [15, 0, 10] } }, supported: true, unsupported: "" });
  assert.deepEqual([iso.key, iso.camera.preset, iso.section, iso.shows, iso.place], ["0:iso", "iso", null, null, {}]);
  // What coverage found, its part's.
  // Every face covered; its material is still to be said, asked as the engine words it.
  assert.deepEqual(read.coverage.map(item => [item.part, item.uncovered, item.conflicts, item.suggestions.map(said => said.kind)]),
    [[0, [], [], ["material"]]]);
  assert.equal(read.coverage[0].suggestions[0].question, "What is the part made of?");
  const conflict = { kind: "unused_datum", ids: ["B"], problem: "datum B is named by no tolerance" };
  const said = { kind: "hole", faces: [V4_TOP], question: "What is the 9 mm hole for?", answer: "dimensional_size(...)", why: "ISO 273" };
  assert.deepEqual(readXbfPmi({ pmi: [], pmi_coverage: [{ part: 1, uncovered: [V4_TOP, 4], conflicts: [conflict, "x"],
    suggestions: [said, { ...said, answer: "" }, 7] }] }).coverage,
  [{ part: 1, uncovered: [V4_TOP], conflicts: [conflict], suggestions: [said] }]);
  // A document served before suggestions were: none.
  assert.deepEqual(readXbfPmi({ pmi: [], pmi_coverage: [{ part: 0, uncovered: [], conflicts: [] }] }).coverage[0].suggestions, []);
  // Two parts' views of one name are two, each its part's.
  const view = (part, name, camera = { preset: "front", direction: [0, -1, 0], up: [0, 0, 1], projection: "orthographic" }, extra = {}) => ({ part, name, label: null, camera, section: null, shows: null, place: {}, ...extra });
  assert.deepEqual(readXbfPmi({ pmi: [], pmi_views: [view(0, "front"), view(1, "front")] }).views.map(item => item.key), ["0:front", "1:front"]);
  // One the viewer cannot apply says why, never taken for a view seen otherwise or uncut.
  const [blind, cut] = readXbfPmi({ pmi: [], pmi_views: [view(0, "blind", { preset: null, direction: [0, -1] }), view(0, "cut", undefined, { section: { axis: "w", at: 0, invert: false } })] }).views;
  assert.deepEqual([blind.supported, blind.camera, blind.unsupported], [false, null, "it has no camera"]);
  assert.deepEqual([cut.supported, cut.section, cut.unsupported], [false, null, "its section is not one the viewer applies"]);
});

test("each new kind's call is the engine's call exactly", () => {
  const read = readXbfPmi(served("v4"));
  const call = (id, changes) => pmiCallText(pmiEntryCall(read.entries.find(entry => entry.id === id), changes));
  assert.equal(call("thickness"), `dimensional_location("thickness", "${V4_BOTTOM}", "${V4_TOP}", tolerance=limits(9.8, 10.2), presentation=place(anchor=(50, 30, 0), offset=(15, 0, 0)))`);
  assert.equal(call("hole-profile"), `surface_profile_tolerance("hole-profile", "${V4_HOLE}", 0.2, datums=["A"], presentation=place(anchor=(0, 5, 5), offset=(0, 15, 15)))`);
  assert.equal(call("general"), `general_profile("general", 0.5, datums=["A"])`);
  assert.equal(call("edges"), `note("edges", "Break all sharp edges 0.2 max")`);
  assert.equal(call("mask"), `note("mask", "Mask these features before coating with primer", faces=["${V4_HOLE}"], annotations=["hole-diameter"], `
    + "presentation=place(anchor=(0, -5, 5), offset=(0, -15, 15)))");
  const [section, iso] = read.views;
  assert.equal(pmiCallText(pmiEntryCall(section)), `view("A-A", camera="front", shows=["hole-diameter", "hole-position", "hole-profile", "mask"], `
    + `section=section("y", 0, invert=True), place={"hole-diameter": place(anchor=(5, 0, 0), offset=(15, 0, 10))})`);
  assert.equal(pmiCallText(pmiEntryCall(iso)), `view("iso", camera="iso")`);
  // A camera of the code's own, a section keeping the lower side, a view showing nothing; a profile on several faces lists them.
  assert.equal(pmiCallText({ kind: "view", name: "side", camera: { direction: [1, 0, 0], up: [0, 0, 1] }, shows: [], section: { axis: "x", at: 12.5, invert: false }, place: {}, label: "Side" }),
    `view("side", camera=camera((1, 0, 0), (0, 0, 1)), shows=[], section=section("x", 12.5), label="Side")`);
  assert.equal(pmiCallText(pmiEntryCall({ ...iso, camera: { ...iso.camera, preset: null } })), `view("iso", camera=camera((0.6155, -0.6155, 0.4924), (0, 0, 1)))`);
  assert.equal(pmiCallText({ kind: "geometric_tolerance", characteristic: "surface_profile", id: "both", refs: [TOP, HOLE], value: 0.1, datums: [] }), `surface_profile_tolerance("both", ["${TOP}", "${HOLE}"], 0.1)`);
  // Limits edited to deviations and back, as a change asks for them.
  assert.equal(call("thickness", { tolerance: { type: "plus_minus", upper: 0.2, lower: -0.2 }, presentation: null }), `dimensional_location("thickness", "${V4_BOTTOM}", "${V4_TOP}", tolerance=plus_minus_tolerance(0.2))`);
  const values = { tolerance: { type: "limits", lower: 9.9, upper: 10.1 } };
  const thickness = read.entries.find(entry => entry.id === "thickness");
  assert.match(pmiChangeRequest({ kind: "edit", id: "thickness", values, call: pmiEntryCall(thickness, values), placementOnly: false }),
    /^Change the PMI "thickness" in the model's annotate\(\.\.\.\) call \(from cadgen\.ap242 import annotate, dimensional_location, limits, place\): tolerance=limits\(9\.9, 10\.1\)\. .*tolerance=limits\(9\.9, 10\.1\), presentation=/s);
  // What a kind needs and lacks makes no call: a note with no words, a profile on no face, a view seen down nothing, a general profile placed (it takes no placement).
  assert.equal(pmiCallText({ kind: "note", id: "n", text: " " }), null);
  assert.equal(pmiCallText({ kind: "geometric_tolerance", characteristic: "surface_profile", id: "p", refs: [], value: 0.1 }), null);
  assert.equal(pmiCallText({ kind: "view", name: "v", camera: null }), null);
  assert.equal(pmiCallText({ kind: "view", name: "v", camera: "front", place: { "hole-diameter": { anchor: [0, 0] } } }), null);
  assert.equal(pmiCallText({ kind: "geometric_tolerance", characteristic: "surface_profile", general: true, id: "g", value: 0.5, presentation: { anchor: [0, 0, 0], offset: [0, 0, 1] } }), null);
});

test("a new note asks for its call, its words as typed", () => {
  const call = { kind: "note", id: "edges", text: "Break all sharp edges 0.2 max", faces: [] };
  assert.equal(pmiChangeRequest({ kind: "add", part: 0, partName: "plate", id: "edges", call }),
    `Add this PMI to the annotate(...) call of the model's part "plate" (from cadgen.ap242 import annotate, note):\nnote("edges", "Break all sharp edges 0.2 max")`);
});
