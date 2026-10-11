/**
 * Vibration: the part's natural frequencies and the shape it rings in at each. Its result is a series
 * of modes (`Mode 2 · 118 Hz`), each mode's shape scaled to a largest motion of 1 mm, mode 1's also
 * the displacement baked into the file. Its verdict judges frequencies (a mode that must stay above a
 * minimum, a band no mode may sit in), which no load control moves. What you see opens on the mode
 * picker and the deformation; its setup says where it is held, or that nothing holds it (free in
 * space, its rigid-body motions left out), and what it is made of; its routine is Vibrate.
 */
import { seriesControls } from "../controls.js";
import { heldRows, madeOfRows, wholeRefs } from "../setup.js";
import { routineOf } from "./stub.js";

/** Vibrate: a one-second loop of the chosen mode's shape, out one way, through rest and back the other. */
export const VIBRATE = routineOf("Vibrate", "vibrate");

/** Study's "Held at" for a part nothing holds: one row, free in space, chosen with the whole part. */
export function freeRows(result) {
  if (result.study.fixtures.length) return [];
  const refs = wholeRefs(result);
  return [{ id: "free", label: "Held at", detail: "", glyph: "fixture", children: [{
    id: "free:0", label: "Nothing: free in space", detail: "", hint: "Its six rigid-body motions are left out", wrap: true,
    ...(refs.length ? { refs, summary: "Free in space, held by nothing" } : {}),
  }] }];
}

export default Object.freeze({
  name: "modal",
  tier: 1,
  word: "Vibration",
  noun: "this shake",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["frequency"]),
  checkLabels: Object.freeze({}),
  defaultControls: seriesControls,
  setupGroups: Object.freeze([heldRows, freeRows, madeOfRows]),
  routine: () => VIBRATE,
  markers: Object.freeze(["fixture"]),
  displayTitle: "Fixtures",
  limitWord: "",
});
