/**
 * Bolted joint (lite): bolts with a preload clamping parts that touch through frictional contact,
 * Tier 3. Its series opens on the preload ("Preload", 0 %) and follows the load steps ("60 % load"),
 * on the last load solved. Its verdict judges each bolt's force after loading, whether the clamped
 * faces open, and whether they slip (friction against the sideways force); none moves with a load
 * control (the preload is there before any load, so nothing is proportional to it). Its takeaway leads
 * with "Lite · ", and Details lists its limits. What you see opens on the load-step scrubber, the
 * field (stress, displacement, contact pressure) and the deformation; Play runs the steps. Its setup is
 * static's held at and pushed, then one row per bolt in plain words ("M6 bolt, 5 kN preload, clamps
 * plate and bracket", its force after loading its hint), any other contact pair, the rigid floor and
 * the material.
 */
import { forceWords } from "../checkKinds.js";
import { seriesControls } from "../controls.js";
import { heldRows, madeOfRows, pushedRows, rigidFloorRows, spaced } from "../setup.js";
import { contactRows } from "./contact.js";
import { routineOf } from "./stub.js";

/** Play: the preload, then the load steps one after another, interpolated (GlbRenderer plays it). */
export const PLAY = routineOf("Play", "play");

const list = (value) => (Array.isArray(value) ? value.filter((entry) => entry && typeof entry === "object") : []);

/** A bolt as its row says it: "M6 bolt, 5 kN preload, clamps plate and bracket". */
export function boltWords(bolt) {
  const between = Array.isArray(bolt.between) && bolt.between.length === 2 ? bolt.between : null;
  const preload = Number(bolt.preload_N);
  if (!bolt.size || !between || !Number.isFinite(preload)) return typeof bolt.words === "string" ? bolt.words : "";
  return `${bolt.size} bolt, ${forceWords(preload)} preload, clamps ${spaced(between[0])} and ${spaced(between[1])}`;
}

/** What a bolt came to under the load, for its row's hint: "6.1 kN after loading", "goes slack". */
function outcomeWords(outcome) {
  if (!outcome) return "";
  if (outcome.slack === true) return "goes slack";
  const force = Number(outcome.force_N);
  return Number.isFinite(force) ? `${forceWords(force)} after loading` : "";
}

/**
 * Study's "Bolted": one row per bolt as cadgen solved it ("M6 bolt, 5 kN preload, clamps plate and
 * bracket"), its force after loading its hint, chosen with the two parts it clamps. [] for none.
 */
export function boltRows(result) {
  const extras = result?.mesh?.userData || {};
  const outcomes = list(extras.bolts);
  const rows = list(extras.study?.bolts).map((bolt, index) => {
    const label = boltWords(bolt);
    if (!label) return null;
    const outcome = outcomes[index];
    const refs = Array.isArray(outcome?.refs) ? outcome.refs.filter((ref) => typeof ref === "string" && ref) : [];
    const hint = outcomeWords(outcome);
    return { id: `bolt:${index}`, label, detail: "", wrap: true, ...(hint ? { hint } : {}),
      ...(refs.length ? { refs, summary: `Bolt: ${label}` } : {}) };
  }).filter(Boolean);
  return rows.length ? [{ id: "bolts", label: "Bolted", detail: "", glyph: "load", children: rows }] : [];
}

/** Its setup: where it is held, what pushes it, its bolts, any other contact, the rigid floor, what it is made of. */
export const BOLT_SETUP = Object.freeze([heldRows, pushedRows, boltRows, contactRows, rigidFloorRows, madeOfRows]);

export default Object.freeze({
  name: "bolt",
  tier: 3,
  word: "Bolted joint",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["bolt_load", "joint_separation", "joint_slip", "stress", "displacement", "contact_pressure"]),
  checkLabels: Object.freeze({}),
  // The load-step scrubber (from the preload), the field, the deformation.
  defaultControls: seriesControls,
  setupGroups: BOLT_SETUP,
  routine: (result) => (result?.series ? PLAY : null),
  markers: Object.freeze(["load", "fixture", "rigid_plane"]),
  displayTitle: "Loads and fixtures",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway.
  limitWord: "Lite",
});
