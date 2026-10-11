/**
 * Strength: a linear static study, today's result. Its verdict judges stress and displacement, both
 * k times larger at k times the load; its setup says where it is held, what pushes it and what it is
 * made of; its one routine is the Load ramp.
 */
import { fieldAndDeformation } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";

/** The Load ramp: the load going on, from none to the load chosen (GlbRenderer plays it). */
export const LOAD_RAMP = Object.freeze({ id: "fea:load-ramp", label: "Load ramp", kind: "load_ramp" });

export default Object.freeze({
  name: "static",
  tier: 1,
  word: "Strength",
  noun: "this load",
  // The static family: a result whose verdict needs a stress field, and says "No stress" without one.
  family: "static",
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["stress", "displacement"]),
  checkLabels: Object.freeze({}),
  defaultControls: fieldAndDeformation,
  setupGroups: Object.freeze([heldRows, pushedRows, madeOfRows]),
  routine: () => LOAD_RAMP,
  markers: Object.freeze(["load", "fixture", "body_load"]),
  displayTitle: "Loads and fixtures",
});
