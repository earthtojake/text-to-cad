/**
 * Shaking: the part's steady response to a sine sweep, shaken where it is held (a base shake) or
 * pushed by loads that swing. Its result is a series of frequencies (`490 Hz`): the response peaks
 * and log-spaced frequencies across the sweep, each frame's stress (its peak over a cycle) and
 * displacement (relative to where it is held) its own, with the displacement's imaginary part
 * (`displacement_im`) beside it. Its verdict judges stress, displacement and acceleration, all k
 * times larger at k times this shake; choosing a check jumps the scrubber to the frequency where it
 * peaks (`at.frame`). What you see opens on the Frequency scrubber, on the peak (the series'
 * default), and the deformation; Vibrate turns the chosen frame through its cycle (re·cos − im·sin).
 * Its setup says where it is held, how it is shaken (or which loads swing), the sweep and its damping
 * ("10 to 600 Hz sweep, 2% damping") and what it is made of.
 */
import { deforms, fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { frameControl } from "../series.js";
import { heldRows, madeOfRows, pushedRows, shakenRows } from "../setup.js";
import { routineOf } from "./stub.js";

/** Vibrate: a one-second loop of the chosen frequency's motion through its cycle, the real part then the imaginary. */
export const VIBRATE = routineOf("Vibrate", "vibrate");

/** The Frequency scrubber over the sweep's frames, then the deformation; the field select where there is nothing to scrub. */
export function frequencyAndDeformation(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const frequency = frameControl(result, "frame");
  if (!frequency) return deforms(result) ? [field, deformation] : [field];
  return deforms(result) ? [frequency, deformation] : [frequency, field];
}

/** The sweep in words: "10 to 600 Hz sweep, 2% damping"; either half alone where the file says only that; "" for neither. */
export function sweepWords(study) {
  const sweep = study?.sweepHz ? `${plainNumber(study.sweepHz[0])} to ${plainNumber(study.sweepHz[1])} Hz sweep` : "";
  const damping = Number.isFinite(study?.dampingRatio) ? `${plainNumber(study.dampingRatio * 100)}% damping` : "";
  return [sweep, damping].filter(Boolean).join(", ");
}

/** Study's "Shaken" for a base shake: its size and line, the sweep and damping its hint ("10 to 600 Hz sweep, 2% damping"). */
export function shakenSweepRows(result) {
  const hint = sweepWords(result.study);
  return shakenRows(result).map((group) => ({
    ...group,
    children: group.children.map((row) => ({ ...row, ...(hint ? { hint } : {}) })),
  }));
}

/** Study's "Pushed" for a force shake: each load row says it swings, back and forth at every frequency of the sweep. */
export function swingingRows(result) {
  if (result.study?.excitation?.kind !== "force") return [];
  return pushedRows(result).map((group) => ({
    ...group,
    children: group.children.map((row) => ({ ...row, hint: "Swinging back and forth across the sweep" })),
  }));
}

export default Object.freeze({
  name: "harmonic",
  tier: 1,
  word: "Shaking",
  noun: "this shake",
  family: null,
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["stress", "displacement", "acceleration"]),
  checkLabels: Object.freeze({}),
  defaultControls: frequencyAndDeformation,
  setupGroups: Object.freeze([heldRows, shakenSweepRows, swingingRows, madeOfRows]),
  routine: () => VIBRATE,
  markers: Object.freeze(["fixture", "base_excitation", "load"]),
  displayTitle: "Shaker and fixtures",
  limitWord: "",
});
