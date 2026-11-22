import assert from "node:assert/strict";
import test from "node:test";
import {
  changedParameters, formatParameterValue, parameterIsRanged, parameterStep, parameterValue, savedParametersNote, settledDrafts, unsavedParametersNote, xbfParameters
} from "./xbfParameters.js";

// A structure's `parameters` as the engine serves them: two of the model's own, one of another module.
const structure = { parameters: [
  { name: "wall", value: 2.0, kind: "float", min: 1, max: 5, step: null, unit: "mm", writable: true, reason: null, source: "bracket.py" },
  { name: "holes", value: 6, kind: "int", min: 3, max: 12, step: null, unit: null, writable: true, reason: null, source: "bracket.py" },
  { name: "pitch", value: 30.0, kind: "float", min: null, max: null, step: null, unit: "deg", writable: false, reason: "shared", source: "lib/spec.py" },
] };
const [wall, holes, pitch] = xbfParameters(structure);

test("a structure's parameters are read as the engine records them, and a structure without them has none", () => {
  assert.deepEqual(xbfParameters(structure).map(parameter => [parameter.name, parameter.value, parameter.kind, parameter.writable, parameter.reason, parameter.source]),
    [["wall", 2, "float", true, null, "bracket.py"], ["holes", 6, "int", true, null, "bracket.py"], ["pitch", 30, "float", false, "shared", "lib/spec.py"]]);
  assert.deepEqual([parameterIsRanged(wall), parameterIsRanged(holes), parameterIsRanged(pitch)], [true, true, false]);
  for (const none of [null, {}, { parameters: [] }, { parameters: "wall" }]) assert.deepEqual(xbfParameters(none), []);
  // What is no parameter is left out: no name, no number, a name twice. Only `true` is writable.
  assert.deepEqual(xbfParameters({ parameters: [{ value: 1 }, { name: "a", value: "1" }, { name: "b", value: 1, writable: "yes" }, { name: "b", value: 2 }] }),
    [{ name: "b", value: 1, kind: "float", min: null, max: null, step: null, unit: null, writable: false, reason: "", source: null }]);
});

test("every write crosses one boundary: inside the range, a whole number for an integer, six decimals for a float", () => {
  assert.deepEqual([parameterValue(wall, 9), parameterValue(wall, -1), parameterValue(wall, 2.3000000000000003), parameterValue(wall, "2.5")], [5, 1, 2.3, 2.5]);
  assert.deepEqual([parameterValue(holes, 7.6), parameterValue(holes, 99), parameterValue(holes, 0.2)], [8, 12, 3]);
  assert.equal(parameterValue(pitch, 1 / 3), 0.333333);
  for (const none of [null, undefined, "", "wide", NaN, Infinity]) assert.equal(parameterValue(wall, none), null);
  // An integer parameter steps by whole numbers whatever it declares; a float by its step, else a hundred to a thousand steps across its range.
  assert.deepEqual([parameterStep(holes), parameterStep({ ...holes, step: 2 }), parameterStep({ ...holes, step: 0.4 })], [1, 2, 1]);
  assert.deepEqual([parameterStep(wall), parameterStep({ ...wall, step: 0.25 }), parameterStep(pitch)], [0.01, 0.25, null]);
  assert.deepEqual([parameterStep({ ...wall, min: 0, max: 90 }), parameterStep({ ...wall, min: 0, max: 1000 }), parameterStep({ ...wall, min: 0, max: 0.004 })], [0.1, 10, 0.00001]);
});

test("a value is said with its unit, an integer whole and a float at its step's precision", () => {
  assert.deepEqual([formatParameterValue(wall, 2), formatParameterValue({ ...wall, step: 0.5 }, 2.5), formatParameterValue(holes, 6), formatParameterValue(pitch, 30)],
    ["2.00 mm", "2.5 mm", "6", "30°"]);
  // A value finer than its step is never rounded away.
  assert.equal(formatParameterValue({ ...wall, step: 0.5, unit: null }, 2.125), "2.125");
});

test("a save sends only the writable parameters whose drafts are other values than the document's", () => {
  const parameters = xbfParameters(structure);
  assert.deepEqual(changedParameters(parameters, {}), {});
  assert.deepEqual(changedParameters(parameters, { wall: 2.5, holes: 6, pitch: 45, gone: 1 }), { wall: 2.5 });
  assert.deepEqual(changedParameters(parameters, { wall: 2.0000001, holes: 7.4 }), { holes: 7 });
  // What was sent and is not yet answered by a rebuilt document is not sent again.
  assert.deepEqual(changedParameters(parameters, { wall: 2.5, holes: 8 }, { wall: 2.5 }), { holes: 8 });
  assert.deepEqual(changedParameters(parameters, { wall: 3 }, { wall: 2.5 }), { wall: 3 });
});

test("a new version of the document takes the drafts it now holds, and keeps the others", () => {
  const drafts = { wall: 2.5, holes: 8 };
  assert.equal(settledDrafts(xbfParameters(structure), drafts), drafts);
  const rebuilt = xbfParameters({ parameters: structure.parameters.map(parameter => (parameter.name === "wall" ? { ...parameter, value: 2.5 } : parameter)) });
  assert.deepEqual(settledDrafts(rebuilt, drafts), { holes: 8 });
  // A parameter gone from the document, or no longer writable, keeps no draft.
  const unheld = xbfParameters({ parameters: [{ ...structure.parameters[0], writable: false, reason: "no_worker" }] });
  assert.deepEqual(settledDrafts(unheld, drafts), {});
});

test("what was saved from the page is one line for the agent, a parameter's saves read as one change", () => {
  assert.equal(savedParametersNote([]), "");
  assert.equal(savedParametersNote([{ name: "wall", from: 2.0, to: 2.5, file: "/home/a/project/bracket.py" }]),
    "Saved from the viewer since your last edit: wall 2 -> 2.5 (bracket.py); the script holds these values and is built at them: read it again before you edit it, and keep them");
  assert.equal(savedParametersNote([
    { name: "wall", from: 2, to: 2.5, file: "C:\\parts\\bracket.py" }, { name: "holes", from: 6, to: 8, file: "C:\\parts\\bracket.py" },
    { name: "wall", from: 2.5, to: 3, file: "C:\\parts\\bracket.py" },
  ]), "Saved from the viewer since your last edit: wall 2 -> 3 (bracket.py), holes 6 -> 8 (bracket.py); the script holds these values and is built at them: read it again before you edit it, and keep them");
  // Saved back to where it began: nothing to say. A value the script changed in between: two changes.
  assert.equal(savedParametersNote([{ name: "wall", from: 2, to: 3, file: "a.py" }, { name: "wall", from: 3, to: 2, file: "a.py" }]), "");
  assert.equal(savedParametersNote([{ name: "wall", from: 2, to: 3, file: "a.py" }, { name: "wall", from: 4, to: 5 }]),
    "Saved from the viewer since your last edit: wall 2 -> 3 (a.py), wall 4 -> 5; the script holds these values and is built at them: read it again before you edit it, and keep them");
});

test("values on screen and not saved are one line for the agent, the script's value beside each", () => {
  const parameters = xbfParameters({ parameters: [
    { name: "wall", value: 2, kind: "float", writable: true, source: "bracket.py" },
    { name: "holes", value: 6, kind: "int", writable: true, source: "lib/spec.py" }] });
  assert.equal(unsavedParametersNote(parameters, {}), "");
  assert.equal(unsavedParametersNote(parameters, { wall: 3.5, holes: 8 }),
    "Shown in the viewer, not saved: wall 2 -> 3.5 (bracket.py), holes 6 -> 8 (spec.py); the script still holds the first values; write the new ones only if asked");
});
