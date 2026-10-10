/**
 * Heat stress: the stress and movement a temperature field puts in a part, with any mechanical
 * loads on top. It is of the static family (its verdict needs a stress field), its stress and
 * displacement checks follow the load control, which scales the temperature change and the loads
 * together ("this heat"), and it plays the Load ramp. What you see opens on today's field and
 * deformation, the field over stress, displacement and temperature; its setup says where it is held,
 * what pushes it, where it is kept at a temperature, heated and cooled, and what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { cooledRows, heatedRows, heldRows, keptAtRows, madeOfRows, pushedRows } from "../setup.js";
import { LOAD_RAMP } from "./static.js";

export default Object.freeze({
  name: "thermal_stress",
  tier: 1,
  word: "Heat stress",
  noun: "this heat",
  family: "static",
  estimate: false,
  scalesWithLoad: true,
  checks: Object.freeze(["stress", "displacement"]),
  checkLabels: Object.freeze({}),
  defaultControls: fieldAndDeformation,
  setupGroups: Object.freeze([heldRows, pushedRows, keptAtRows, heatedRows, cooledRows, madeOfRows]),
  routine: () => LOAD_RAMP,
  markers: Object.freeze(["load", "fixture", "body_load", "temperature", "heat", "convection"]),
  displayTitle: "Loads, fixtures and heat",
  limitWord: "",
});
