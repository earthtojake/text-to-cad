/**
 * Creep (lite): the slow, permanent stretch of a part under a load held for a long time, usually
 * hot, by Norton's power law, Tier 3. Its series is the hold in hours ("0 h" the instant the load
 * goes on, "10,000 h" at the end), opening on the end. Its verdict judges the creep strain at the
 * end ("0.8 % creep after 10,000 h, limit 1 %"), the largest stress over the hold and the
 * displacement at the end; none moves with a load control (creep goes as the stress to a power),
 * and a run whose creep ran away fails every check. Its takeaway leads with "Steady creep · " (its
 * limit: secondary creep only) and, for a runaway, says it; Details lists its limits. What you see
 * opens on the time scrubber, the field (stress, displacement, creep strain) and the deformation;
 * Play runs the hold over three seconds, the stress relaxing where the creep sheds it. Its setup is
 * static's: held at, pushed, made of.
 */
import { seriesControls } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";
import { routineOf } from "./stub.js";

/** Play: the time frames one after another, interpolated (GlbRenderer plays it). */
export const PLAY = routineOf("Play", "play");

/** The takeaway of a run whose creep ran away: the file's own sentence (in `analysis.warnings`); "" otherwise. */
export function runawayCaption(result) {
  return (result?.analysis?.warnings || []).find((line) => /^Creep runs away\b/.test(line)) || "";
}

/** Its setup: where it is held, what pushes it, what it is made of. */
export const CREEP_SETUP = Object.freeze([heldRows, pushedRows, madeOfRows]);

export default Object.freeze({
  name: "creep",
  tier: 3,
  word: "Creep",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["creep_strain", "stress", "displacement"]),
  checkLabels: Object.freeze({}),
  // The time scrubber (controls.seriesControls words an hours series "Time"), the field, the deformation.
  defaultControls: seriesControls,
  setupGroups: CREEP_SETUP,
  routine: (result) => (result?.series ? PLAY : null),
  markers: Object.freeze(["load", "fixture", "body_load"]),
  displayTitle: "Loads and fixtures",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway: secondary (steady) creep only.
  limitWord: "Steady creep",
  // A runaway leads the takeaway, not the worst check's words.
  caption: runawayCaption,
});
