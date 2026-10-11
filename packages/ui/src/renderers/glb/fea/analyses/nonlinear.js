/**
 * Permanent bend / Stretch (lite): metal past yield (J2 plasticity) or rubber stretched far
 * (Neo-Hookean), with the load applied in steps, Tier 3. Its series is the load steps as pseudo-time
 * ("60 % load"), opening on the last load the part carried. Its verdict judges the permanent strain,
 * the stress and the displacement there; none moves with a load control (the response is not
 * proportional to the load), and a part that collapses fails every check. Its takeaway leads with
 * "Lite · " and, for a collapse, says it ("Lite · Collapses at about 70 % of the load"); Details
 * lists its limits. What you see opens on the load-step scrubber, the field
 * (stress, displacement, plastic strain) and the deformation; Play runs the steps over three seconds.
 * Its setup is static's: held at, pushed, made of.
 */
import { seriesControls } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";
import { routineOf } from "./stub.js";

/** Play: the load steps one after another, interpolated (GlbRenderer plays it). */
export const PLAY = routineOf("Play", "play");

/**
 * The takeaway of a run that collapsed: the file's own sentence ("Collapses at about 70 % of the
 * load", in `analysis.warnings`), else one from the last load it carried; "" for a run that did not.
 */
export function collapseCaption(result) {
  if (!result?.collapsed) return "";
  const said = (result.analysis?.warnings || []).find((line) => /^Collapses\b/.test(line));
  if (said) return said;
  const percent = result.loadPercent;
  if (!Number.isFinite(percent)) return "Collapses before the full load";
  return percent < 1 ? "Collapses before 1 % of the load" : `Collapses at about ${Math.round(percent)} % of the load`;
}

/** Its setup: where it is held, what pushes it, what it is made of. */
export const NONLINEAR_SETUP = Object.freeze([heldRows, pushedRows, madeOfRows]);

export default Object.freeze({
  name: "nonlinear",
  tier: 3,
  word: "Permanent bend / Stretch",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  // Not linear in the load: every check is judged as solved, its takeaway its own sentence, never "OK up to 18× this load".
  scaling: "none",
  checks: Object.freeze(["plastic_strain", "stress", "displacement"]),
  checkLabels: Object.freeze({}),
  // The load-step scrubber, the field, the deformation (controls.seriesControls words a % series "Load step").
  defaultControls: seriesControls,
  setupGroups: NONLINEAR_SETUP,
  routine: (result) => (result?.series ? PLAY : null),
  markers: Object.freeze(["load", "fixture", "body_load"]),
  displayTitle: "Loads and fixtures",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway.
  limitWord: "Lite",
  // A collapse leads the takeaway, not the worst check's words.
  caption: collapseCaption,
});
