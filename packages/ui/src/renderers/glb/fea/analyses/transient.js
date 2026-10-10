/**
 * Over time: a held part's response to loads that change in time, a hammer blow or a sudden push.
 * Its result is a series of times (`1.02 ms`): evenly spaced from the start plus the moments of the
 * peak stress and the peak displacement, each frame's stress and displacement its own, with the
 * envelopes over all time beside them. Its verdict judges stress and displacement at their peaks,
 * both k times larger at k times this load, and choosing a check jumps the scrubber to when it
 * peaked (`at.frame`). What you see opens on the Time scrubber, on the peak (the series' default),
 * the field and the deformation; Play runs the frames over three seconds. Its setup says where it is
 * held, what pushes it and how that changes over time ("50 N half-sine, 2 ms"), how its fixtures are
 * shaken, and what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { threeFigures } from "../numbers.js";
import { frameControl } from "../series.js";
import { heldRows, loadWords, madeOfRows, pushedRows, shakenRows } from "../setup.js";
import { routineOf } from "./stub.js";

/** Play: the frames one after another, interpolated (GlbRenderer plays it). */
export const PLAY = routineOf("Play", "play");

/** A time as the scrubber says it: "0 s", "2 ms", "1.5 s", "5 min". */
export function timeWords(seconds) {
  const s = Number(seconds) || 0;
  if (s === 0) return "0 s";
  if (s < 1) return `${threeFigures(s * 1000)} ms`;
  if (s < 120) return `${threeFigures(s)} s`;
  return `${threeFigures(s / 60)} min`;
}

/**
 * A load's history as the file echoes it, in words: "step", "ramp over 2 ms", "half-sine, 2 ms",
 * "table of 4 points to 10 ms". "" for none.
 */
export function historyWords(history) {
  if (Array.isArray(history)) {
    const points = history.filter((point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite));
    if (!points.length) return "";
    return `table of ${points.length} point${points.length === 1 ? "" : "s"} to ${timeWords(points[points.length - 1][0])}`;
  }
  if (!history || typeof history !== "object") return "";
  if (history.shape === "step") return "step";
  if (!(history.duration_s > 0)) return "";
  if (history.shape === "ramp") return `ramp over ${timeWords(history.duration_s)}`;
  if (history.shape === "half_sine") return `half-sine, ${timeWords(history.duration_s)}`;
  return "";
}

/** The study echo as the file wrote it: the histories ride on its loads and excitation, which `readStudy` keeps no copy of. */
const rawStudy = (result) => result?.mesh?.userData?.study || {};

/** The Time scrubber over the run's frames, the field and the deformation; the field and the deformation with no frames. */
export function timeFieldAndDeformation(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const time = frameControl(result, "frame");
  return [...(time ? [time] : []), field, deformation];
}

/**
 * Study's "Pushed" over time: each face load says how much and how it changes ("50 N half-sine,
 * 2 ms"), which way it points its hint, and a prompt carries the history too.
 */
export function pushedOverTimeRows(result) {
  const raw = (rawStudy(result).loads || []).filter((load) => load && Array.isArray(load.faces) && load.faces.length);
  const loads = result.study.loads.filter((load) => load.faces.length);
  return pushedRows(result).map((group) => ({
    ...group,
    children: group.children.map((row, index) => {
      const history = historyWords(raw[index]?.history);
      if (!history || !loads[index]) return row;
      const words = loadWords(loads[index]);
      return {
        ...row,
        label: `${words.amount} ${history}`,
        ...(words.direction ? { hint: `Pointing ${words.direction}` } : {}),
        ...(row.summary ? { summary: `${row.summary}, ${history}` } : {}),
      };
    }),
  }));
}

/** Study's "Shaken" over time: the shake's size and line, how it changes over time its hint ("half-sine, 2 ms"). */
export function shakenOverTimeRows(result) {
  const history = historyWords(rawStudy(result).excitation?.history);
  return shakenRows(result).map((group) => ({
    ...group,
    children: group.children.map((row) => ({
      ...row,
      ...(history ? { hint: `Over time: ${history}` } : {}),
      ...(row.summary && history ? { summary: `${row.summary}, ${history}` } : {}),
    })),
  }));
}

export default Object.freeze({
  name: "transient",
  tier: 1,
  word: "Over time",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["stress", "displacement"]),
  checkLabels: Object.freeze({}),
  defaultControls: timeFieldAndDeformation,
  setupGroups: Object.freeze([heldRows, pushedOverTimeRows, shakenOverTimeRows, madeOfRows]),
  routine: (result) => (result?.series ? PLAY : null),
  markers: Object.freeze(["load", "fixture", "base_excitation"]),
  displayTitle: "Loads and fixtures",
  limitWord: "",
});
