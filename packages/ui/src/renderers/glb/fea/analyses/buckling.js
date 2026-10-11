/**
 * Buckling: how many times this load the part takes before its shape gives way sideways. Its result
 * is a series of buckling shapes (`Mode 1 · 13.3×`), each scaled to a largest motion of 1 mm, plus the
 * prestress's stress, the same in every frame. Its verdict judges the first load factor against a
 * margin, which the load control moves inversely (at k times the load it buckles at λ/k). What you see
 * opens on the mode picker and the deformation; its setup is static's (held at, pushed, made of); its
 * routine is Buckle, the load ramp said its way.
 */
import { seriesControls } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";

/** Buckle: the load going on, from none to the load chosen, until the shape gives (GlbRenderer plays it as a load ramp). */
export const BUCKLE = Object.freeze({ id: "fea:buckle", label: "Buckle", kind: "load_ramp" });

export default Object.freeze({
  name: "buckling",
  tier: 1,
  word: "Buckling",
  noun: "this load",
  family: null,
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["buckling"]),
  checkLabels: Object.freeze({}),
  defaultControls: seriesControls,
  setupGroups: Object.freeze([heldRows, pushedRows, madeOfRows]),
  routine: () => BUCKLE,
  markers: Object.freeze(["load", "fixture", "body_load"]),
  displayTitle: "Loads and fixtures",
  limitWord: "",
});
