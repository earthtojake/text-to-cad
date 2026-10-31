// What a new annotation can be made of the faces Select has picked (`pmiCreate.js`): each kind of
// the supported subset offered only where the pick makes one, with what it needs where it does not,
// starting as its call with the picked faces' refs, a fresh id, and no tolerance filled in.
import assert from "node:assert/strict";
import test from "node:test";
import { pmiCallText, pmiToleranceText, readXbfPmi } from "@text-to-cad/core/lib/xbf/xbfPmi.js";
import { newPmiName, nextDatumLetter, parseToleranceInput, pmiCreateOptions, toggleDatum } from "./pmiCreate.js";

const TOP = { id: "i0/face/2", part: 0, ref: "plate/f:top", surface: { type: "plane", normal: [0, 0, 1], origin: [0, 0, 2] } };
const BOTTOM = { id: "i0/face/5", part: 0, ref: "plate/f:bottom", surface: { type: "plane", normal: [0, 0, -1], origin: [0, 0, -2] } };
const SIDE = { id: "i0/face/1", part: 0, ref: "plate/f:side", surface: { type: "plane", normal: [-1, 0, 0], origin: [-20, 0, 0] } };
const HOLE = { id: "i0/face/11", part: 0, ref: "plate/f:hole", surface: { type: "cylinder", axis: [0, 0, 1], origin: [0, 0, 0], radius: 4 } };
const PEG = { id: "i1/face/1", part: 1, ref: "peg/f:wall", surface: { type: "cylinder", axis: [0, 0, -1], origin: [12, 0, 8], radius: 3 } };
const PART = { id: "i0", part: 0, ref: "", surface: null };
const available = options => options.filter(option => option.available).map(option => option.kind);
// What any faces of one part carry, or are of: a surface profile, a note, its general profile, a view.
const ANY_FACES = ["profile", "note", "general_profile", "view"];
const of = (options, kind) => options.find(option => option.kind === kind);

test("one flat face makes a datum or a flatness; two parallel ones a distance; a round one a datum or a diameter", () => {
  assert.deepEqual(available(pmiCreateOptions({ picked: [TOP], entries: [] })), ["datum", "flatness", ...ANY_FACES]);
  const pair = pmiCreateOptions({ picked: [BOTTOM, TOP], entries: [] });
  assert.deepEqual(available(pair), ["distance", "basic", ...ANY_FACES]);
  assert.deepEqual(of(pair, "distance").call, { kind: "dimension", type: "distance", id: "distance", from: BOTTOM.ref, to: TOP.ref, tolerance: null });
  assert.equal(of(pair, "distance").nominal, 4);
  // A datum stands on a planar or a cylindrical face, as the engine's does.
  const round = pmiCreateOptions({ picked: [HOLE], entries: [] });
  assert.deepEqual(available(round), ["datum", "diameter", ...ANY_FACES]);
  assert.deepEqual(of(round, "datum").call, { kind: "datum", id: "A", letter: "A", ref: HOLE.ref });
  assert.equal(of(round, "diameter").nominal, 8);
  assert.equal(of(round, "position").need, "Pick one round face, after a datum");
});

test("a basic dimension goes between flat faces and holes, each hole by its axis, and takes no tolerance", () => {
  const fromSide = pmiCreateOptions({ picked: [SIDE, HOLE], entries: [] });
  assert.deepEqual(available(fromSide), ["basic", ...ANY_FACES]);
  assert.deepEqual(of(fromSide, "basic").call, { kind: "dimension", type: "distance", basic: true, id: "basic", from: SIDE.ref, to: HOLE.ref, tolerance: null });
  assert.equal(of(fromSide, "basic").nominal, 20, "to the hole's centre line");
  // Two holes: square to both axes, whichever way each runs.
  assert.equal(of(pmiCreateOptions({ picked: [HOLE, PEG], entries: [] }), "basic").nominal, 12);
  // A hole whose axis crosses the face makes no dimension.
  assert.deepEqual(available(pmiCreateOptions({ picked: [TOP, HOLE], entries: [] })), ANY_FACES);
});

test("a pick that makes nothing of a kind offers none of it, and says what each kind needs", () => {
  assert.deepEqual(available(pmiCreateOptions({ picked: [TOP, SIDE], entries: [] })), ANY_FACES, "two faces at an angle");
  assert.deepEqual(available(pmiCreateOptions({ picked: [TOP, PART], entries: [] })), [], "a face and a part");
  assert.deepEqual(available(pmiCreateOptions({ picked: [], entries: [] })), []);
  assert.equal(of(pmiCreateOptions({ picked: [], entries: [] }), "distance").need, "Pick two parallel flat faces");
});

test("a surface profile is on one face or several of one part, of any kind, its datums the part's and none given", () => {
  const profile = of(pmiCreateOptions({ picked: [TOP, HOLE], entries: [] }), "profile");
  assert.equal(profile.available, true);
  assert.deepEqual(profile.call, { kind: "geometric_tolerance", characteristic: "surface_profile", id: "profile", refs: [TOP.ref, HOLE.ref], value: null, datums: [] });
  assert.equal(pmiCallText({ ...profile.call, value: 0.1, datums: ["A"] }), `surface_profile_tolerance("profile", ["${TOP.ref}", "${HOLE.ref}"], 0.1, datums=["A"])`);
  assert.equal(pmiCallText({ ...of(pmiCreateOptions({ picked: [HOLE], entries: [] }), "profile").call, value: 0.2 }), `surface_profile_tolerance("profile", "${HOLE.ref}", 0.2)`);
  // Faces of two parts, or none: no profile.
  const across = of(pmiCreateOptions({ picked: [TOP, PEG], entries: [] }), "profile");
  assert.deepEqual([across.available, across.need], [false, "Pick faces of one part"]);
  assert.equal(of(pmiCreateOptions({ picked: [], entries: [], parts: [0] }), "profile").available, false);
});

test("the general profile takes no face, and is offered while its part has none", () => {
  // A document of one part, nothing picked: it is that part's.
  const lone = of(pmiCreateOptions({ picked: [], entries: [], parts: [0] }), "general_profile");
  assert.deepEqual([lone.available, lone.part], [true, 0]);
  assert.deepEqual(lone.call, { kind: "geometric_tolerance", characteristic: "surface_profile", general: true, id: "general", value: null, datums: [] });
  assert.equal(pmiCallText({ ...lone.call, value: 0.5, datums: ["A"] }), `general_profile("general", 0.5, datums=["A"])`);
  // Of several parts, a face picked says which.
  assert.deepEqual([of(pmiCreateOptions({ picked: [], entries: [], parts: [0, 1] }), "general_profile").need,
    of(pmiCreateOptions({ picked: [PEG], entries: [], parts: [0, 1] }), "general_profile").part], ["Pick a face of its part", 1]);
  // One per part: built, or asked for.
  const built = readXbfPmi({ pmi: [{ id: "general", kind: "geometric_tolerance", status: "ok", part: 0, refs: [],
    geometric_tolerance: { characteristic: "surface_profile", value: 0.5, datums: [], general: true } }] }).entries;
  const taken = of(pmiCreateOptions({ picked: [], entries: built, parts: [0] }), "general_profile");
  assert.deepEqual([taken.available, taken.need], [false, "Its part has one"]);
  const asked = [{ part: 0, call: lone.call }];
  assert.equal(of(pmiCreateOptions({ picked: [], entries: [], pending: asked, parts: [0] }), "general_profile").available, false);
  // The peg's is the peg's own.
  assert.equal(of(pmiCreateOptions({ picked: [PEG], entries: built, parts: [0, 1] }), "general_profile").available, true);
});

test("a note is general where no face is picked, a flag note on the faces picked; its words are given, typed", () => {
  const general = of(pmiCreateOptions({ picked: [], entries: [], parts: [0] }), "note");
  assert.deepEqual([general.available, general.call], [true, { kind: "note", id: "note", text: "", faces: [] }]);
  // No words given, no call: cadgen offers no starter text.
  assert.equal(pmiCallText(general.call), null);
  assert.equal(pmiCallText({ ...general.call, text: "Break all sharp edges 0.2 max" }), `note("note", "Break all sharp edges 0.2 max")`);
  const flag = of(pmiCreateOptions({ picked: [HOLE, TOP], entries: [] }), "note");
  assert.equal(pmiCallText({ ...flag.call, text: "Mask these" }), `note("note", "Mask these", faces=["${HOLE.ref}", "${TOP.ref}"])`);
  // Its id is one of the part's ids, with the rest.
  const noted = readXbfPmi({ pmi: [{ id: "note", kind: "note", status: "ok", part: 0, refs: [], note: { number: 1, text: "x", general: true, annotations: [] } }] }).entries;
  assert.equal(of(pmiCreateOptions({ picked: [TOP], entries: noted }), "note").call.id, "note-2");
  assert.equal(of(pmiCreateOptions({ picked: [TOP, PEG], entries: [] }), "note").available, false, "faces of two parts");
});

test("a view from here is of its part, a face's or the document's one, named afresh among its views, while the parts stand as made", () => {
  const views = readXbfPmi({ pmi_views: [{ part: 0, name: "view", camera: { direction: [0, -1, 0], up: [0, 0, 1] } }] }).views;
  const here = of(pmiCreateOptions({ picked: [], entries: [], parts: [0], views }), "view");
  assert.deepEqual([here.available, here.part, here.call.name], [true, 0, "view-2"]);
  // A view's name is its own, apart from the annotations' ids: a datum "view" takes nothing.
  const pending = [{ part: 0, call: { kind: "view", name: "view-2", camera: { direction: [1, 0, 0], up: [0, 0, 1] } } }];
  assert.equal(of(pmiCreateOptions({ picked: [], entries: [], parts: [0], views, pending }), "view").call.name, "view-3");
  assert.equal(of(pmiCreateOptions({ picked: [PEG], entries: [], parts: [0, 1], views }), "view").call.name, "view", "the peg has none");
  assert.equal(of(pmiCreateOptions({ picked: [], entries: [], parts: [0, 1] }), "view").need, "Pick a face of its part");
  const moved = of(pmiCreateOptions({ picked: [], entries: [], parts: [0], moving: true }), "view");
  assert.deepEqual([moved.available, moved.need], [false, "Not while the parts are moved"]);
});

test("a face's menu offers what stands on the faces picked; the general profile and a view are the part's", () => {
  const options = pmiCreateOptions({ picked: [TOP], entries: [], parts: [0] });
  assert.deepEqual(options.filter(option => option.available && option.onFaces).map(option => option.kind), ["datum", "flatness", "profile", "note"]);
  assert.equal(of(pmiCreateOptions({ picked: [], entries: [], parts: [0] }), "note").onFaces, false, "a general note is on none");
});

test("a new one's id and letter are ones the document does not have, and a position refers to its datums", () => {
  const entries = readXbfPmi({ pmi: [
    { id: "A", kind: "datum", status: "ok", part: 0, refs: [], datum: { letter: "A" } },
    { id: "flatness", kind: "geometric_tolerance", status: "ok", part: 0, refs: [], geometric_tolerance: { characteristic: "flatness", value: 0.05, datums: [] } },
  ] }).entries;
  assert.deepEqual(of(pmiCreateOptions({ picked: [TOP], entries }), "datum").call, { kind: "datum", id: "B", letter: "B", ref: TOP.ref });
  assert.equal(of(pmiCreateOptions({ picked: [TOP], entries }), "flatness").call.id, "flatness-2");
  const position = of(pmiCreateOptions({ picked: [HOLE], entries }), "position");
  assert.equal(position.available, true);
  assert.deepEqual([position.call.datums, position.call.value, position.call.diameterZone], [["A"], null, true]);
  // I, O and Q are never datum letters.
  assert.equal(nextDatumLetter(readXbfPmi({ pmi: "ABCDEFGH".split("").map(letter => ({ id: letter, kind: "datum", datum: { letter } })) }).entries), "J");
});

test("a tolerance typed in is read as a drawing writes one, and none is none", () => {
  assert.deepEqual(parseToleranceInput(""), { tolerance: null });
  assert.deepEqual(parseToleranceInput("±0.2"), { tolerance: { type: "plus_minus", upper: 0.2, lower: -0.2 } });
  assert.deepEqual(parseToleranceInput("0.2"), { tolerance: { type: "plus_minus", upper: 0.2, lower: -0.2 } });
  assert.deepEqual(parseToleranceInput("+0.1/−0.05"), { tolerance: { type: "plus_minus", upper: 0.1, lower: -0.05 } });
  assert.deepEqual(parseToleranceInput("+0.1 0"), { tolerance: { type: "plus_minus", upper: 0.1, lower: 0 } });
  assert.ok(parseToleranceInput("-0.1/+0.1").error, "the upper comes first");
  assert.ok(parseToleranceInput("+0.1/+0.1").error, "and is above the lower, as the engine's plus_minus has it");
  assert.ok(parseToleranceInput("loose").error);
  assert.ok(parseToleranceInput("0").error);
});

test("limits typed in are two sizes, the least first, as a drawing writes them; a signed or slashed pair stays deviations", () => {
  const limits = { tolerance: { type: "limits", lower: 10, upper: 10.05 } };
  for (const text of ["10.00–10.05", "10.00-10.05", "10.00 to 10.05", " 10 – 10.05 "]) assert.deepEqual(parseToleranceInput(text), limits, text);
  // What the section fills a limits dimension's field with reads back as those limits.
  const given = { type: "limits", lower: 9.8, upper: 10.2 };
  assert.equal(pmiToleranceText(given).text, "9.8–10.2");
  assert.deepEqual(parseToleranceInput(pmiToleranceText(given).text), { tolerance: given });
  assert.deepEqual(parseToleranceInput("+0.1/-0.05"), { tolerance: { type: "plus_minus", upper: 0.1, lower: -0.05 } });
  assert.deepEqual(parseToleranceInput("+0.1 -0.05"), { tolerance: { type: "plus_minus", upper: 0.1, lower: -0.05 } });
  assert.deepEqual(parseToleranceInput("0.1 -0.05"), { tolerance: { type: "plus_minus", upper: 0.1, lower: -0.05 } }, "a signed second is a deviation");
  assert.deepEqual(parseToleranceInput("10.00 - 10.05"), { tolerance: { type: "limits", lower: 10, upper: 10.05 } });
  assert.deepEqual(parseToleranceInput("0.1/0"), { tolerance: { type: "plus_minus", upper: 0.1, lower: 0 } });
  assert.ok(parseToleranceInput("10.05–10").error, "the least comes first");
  assert.ok(parseToleranceInput("0–10").error, "a size is above 0, as the engine's limits have it");
  assert.ok(parseToleranceInput("10–10.05–10.1").error);
});

test("a new one asked for but not yet built takes its id and letter, so a second never replaces it", () => {
  const pending = [{ part: 0, call: { kind: "geometric_tolerance", characteristic: "flatness", id: "flatness", ref: TOP.ref, value: 0.05 } },
    { part: 0, call: { kind: "datum", id: "A", letter: "A", ref: BOTTOM.ref } }];
  const options = pmiCreateOptions({ picked: [TOP], entries: [], pending });
  assert.equal(of(options, "flatness").call.id, "flatness-2");
  assert.equal(of(options, "datum").call.letter, "B");
});

test("ids and datum letters are a part's own: another part's never take them, nor are its datums offered", () => {
  const entries = readXbfPmi({ pmi: [
    { id: "A", kind: "datum", status: "ok", part: 0, refs: [], datum: { letter: "A" } },
    { id: "B", kind: "datum", status: "ok", part: 1, refs: [], datum: { letter: "B" } },
    { id: "diameter", kind: "dimension", status: "ok", part: 0, refs: [], dimension: { type: "diameter", nominal: { value: 8 }, tolerance: null } },
  ] }).entries;
  const onPeg = pmiCreateOptions({ picked: [PEG], entries, pending: [{ part: 0, call: { kind: "datum", id: "C", letter: "C", ref: TOP.ref } }] });
  assert.equal(onPeg.every(option => option.part === 1), true, "made on the peg");
  assert.deepEqual([of(onPeg, "datum").call.letter, of(onPeg, "diameter").call.id], ["A", "diameter"]);
  // A position on the peg refers to the peg's datums alone.
  assert.deepEqual([of(onPeg, "position").call.datums, of(onPeg, "position").datums], [["B"], ["B"]]);
  const onPlate = pmiCreateOptions({ picked: [HOLE], entries });
  assert.deepEqual([of(onPlate, "datum").call.letter, of(onPlate, "diameter").call.id, of(onPlate, "position").datums], ["B", "diameter-2", ["A"]]);
});

test("a new one is called by its id until it is built, and a datum by its letter", () => {
  assert.equal(newPmiName({ kind: "geometric_tolerance", characteristic: "flatness", id: "flatness" }), "flatness");
  assert.equal(newPmiName({ kind: "dimension", type: "distance", basic: true, id: "basic-2" }), "basic-2");
  assert.equal(newPmiName({ kind: "datum", id: "B", letter: "B" }), "datum B");
  assert.equal(newPmiName({ kind: "view", name: "view-2", camera: { direction: [0, -1, 0], up: [0, 0, 1] } }), "view-2");
});

test("a frame's datums keep the order they were picked in, primary first, and stop at three", () => {
  assert.deepEqual(toggleDatum(["B", "A"], "C"), ["B", "A", "C"]);
  assert.deepEqual(toggleDatum(["B", "A", "C"], "A"), ["B", "C"]);
  assert.deepEqual(toggleDatum(["B", "C"], "A"), ["B", "C", "A"]);
  assert.deepEqual(toggleDatum(["A", "B", "C"], "D"), ["A", "B", "C"]);
});
