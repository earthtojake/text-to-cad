/**
 * Heat: the steady temperature from faces held at a temperature, heat put in and air carrying it
 * away. Its verdict judges the hottest point against a limit (a temperature, measured from the
 * coolest temperature the study sets), which no load control moves; nothing deforms. What you see
 * opens on the field alone (Temperature, Heat flow); its setup says where it is kept at a
 * temperature, where heat goes in, where air cools it, where it radiates ("Radiates to 25 °C,
 * emissivity 0.9") and what it is made of. It plays no routine.
 */
import { fieldAndDeformation } from "../controls.js";
import { cooledRows, heatedRows, keptAtRows, madeOfRows, radiatesRows } from "../setup.js";

/** The heat analyses' setup: kept at, heated, cooled by air, radiates, made of. */
export const HEAT_SETUP = Object.freeze([keptAtRows, heatedRows, cooledRows, radiatesRows, madeOfRows]);

/** The heat analyses' markers: a dot where a temperature is held, a wavy arrow where heat goes in, strokes where air cools it. */
export const HEAT_MARKERS = Object.freeze(["temperature", "heat", "convection"]);

/** The field select alone, over every field the result carries (temperature first): a temperature has no deformation. */
export const fieldOnly = (result) => [fieldAndDeformation(result)[0]];

export default Object.freeze({
  name: "thermal",
  tier: 1,
  word: "Heat",
  noun: "this heat",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["temperature"]),
  checkLabels: Object.freeze({}),
  defaultControls: fieldOnly,
  setupGroups: HEAT_SETUP,
  routine: () => null,
  markers: HEAT_MARKERS,
  displayTitle: "Heat inputs and temperatures",
  limitWord: "",
});
