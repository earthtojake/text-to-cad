/**
 * Heat over time: temperature against time from a start, the hottest moment. Its verdict judges the
 * hottest point over all time against a limit, and choosing that check jumps the scrubber to when
 * it happened (`at.frame`). What you see opens on the field and the time scrubber, on the hottest
 * frame (the series' default); Play runs the frames over three seconds. Its setup is the steady
 * analysis's: kept at, heated, cooled by air, made of.
 */
import { frameControl } from "../series.js";
import { routineOf } from "./stub.js";
import { HEAT_MARKERS, HEAT_SETUP, fieldOnly } from "./thermal.js";

/** Play: the frames one after another, interpolated (GlbRenderer plays it). */
export const PLAY = routineOf("Play", "play");

/** The field, then the time scrubber where the result has frames to scrub. */
export function fieldAndTime(result) {
  const time = frameControl(result, "frame");
  return [...fieldOnly(result), ...(time ? [time] : [])];
}

export default Object.freeze({
  name: "thermal_transient",
  tier: 1,
  word: "Heat over time",
  noun: "this heat",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["temperature"]),
  checkLabels: Object.freeze({}),
  defaultControls: fieldAndTime,
  setupGroups: HEAT_SETUP,
  routine: (result) => (result?.series ? PLAY : null),
  markers: HEAT_MARKERS,
  displayTitle: "Heat inputs and temperatures",
  limitWord: "",
});
