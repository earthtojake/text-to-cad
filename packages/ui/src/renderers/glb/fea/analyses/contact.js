/**
 * Contact (lite): parts that press on each other or slide instead of being glued, and parts resting on
 * a rigid plane, Tier 3. Its series is the load steps as pseudo-time ("60 % load"), opening on the
 * last load solved. Its verdict judges the stress, the displacement and the contact pressure there;
 * none moves with a load control (contact opens, closes and slides, so the response is not
 * proportional to the load). Its takeaway leads with "Lite · ", and Details lists its limits. What
 * you see opens on the load-step scrubber, the field (stress, displacement, contact pressure) and the
 * deformation; Play runs the steps over three seconds. Its setup is static's held at and pushed, then
 * one row per contact pair in plain words ("pin presses on plate, friction 0.2", what it did under the
 * load its hint), the rigid floor and the material.
 */
import { seriesControls } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { heldRows, madeOfRows, pushedRows, rigidFloorRows, spaced } from "../setup.js";
import { routineOf } from "./stub.js";

/** Play: the load steps one after another, interpolated (GlbRenderer plays it). */
export const PLAY = routineOf("Play", "play");

const list = (value) => (Array.isArray(value) ? value.filter((entry) => entry && typeof entry === "object") : []);

/** How a contact came out under the load, for its row's hint: "1000 N, peak 10 MPa", "no longer touching". */
function outcomeWords(outcome) {
  if (!outcome) return "";
  if (outcome.touching === false) return "no longer touching";
  const force = Number(outcome.force_N);
  const peak = Number(outcome.peak_MPa);
  return [Number.isFinite(force) ? `${plainNumber(force)} N` : "", Number.isFinite(peak) ? `peak ${plainNumber(peak)} MPa` : ""]
    .filter(Boolean).join(", ");
}

/**
 * Study's "Pressed together": one row per contact pair as cadgen solved it ("pin presses on plate,
 * friction 0.2"), what it did under the load its hint, chosen with both parts. [] for none.
 */
export function contactRows(result) {
  const extras = result?.mesh?.userData || {};
  const pairs = list(extras.study?.contact_pairs);
  const outcomes = list(extras.contacts).filter((entry) => entry.kind === "pair");
  const rows = pairs.map((pair, index) => {
    const outcome = outcomes[index];
    const between = Array.isArray(outcome?.between) && outcome.between.length === 2 ? outcome.between : pair.between;
    if (!Array.isArray(between) || between.length !== 2) return null;
    const friction = Number(pair.friction) || 0;
    const label = `${spaced(between[0])} presses on ${spaced(between[1])}, ${friction ? `friction ${plainNumber(friction)}` : "no friction"}`;
    const refs = Array.isArray(outcome?.refs) ? outcome.refs.filter((ref) => typeof ref === "string" && ref) : [];
    const hint = outcomeWords(outcome);
    return { id: `contact:${index}`, label, detail: "", wrap: true, ...(hint ? { hint } : {}),
      ...(refs.length ? { refs, summary: `Contact: ${label}` } : {}) };
  }).filter(Boolean);
  return rows.length ? [{ id: "contacts", label: "Pressed together", detail: "", glyph: "load", children: rows }] : [];
}

/** Its setup: where it is held, what pushes it, which parts press on which, the rigid floor, what it is made of. */
export const CONTACT_SETUP = Object.freeze([heldRows, pushedRows, contactRows, rigidFloorRows, madeOfRows]);

export default Object.freeze({
  name: "contact",
  tier: 3,
  word: "Contact",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["stress", "displacement", "contact_pressure"]),
  checkLabels: Object.freeze({}),
  // The load-step scrubber, the field, the deformation (controls.seriesControls words a % series "Load step").
  defaultControls: seriesControls,
  setupGroups: CONTACT_SETUP,
  routine: (result) => (result?.series ? PLAY : null),
  markers: Object.freeze(["load", "fixture", "rigid_plane"]),
  displayTitle: "Loads and fixtures",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway.
  limitWord: "Lite",
});
