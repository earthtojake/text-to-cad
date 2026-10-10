/** Heat stress: stress and movement from a temperature field (planned viewer file; static's defaults until its track fills it). */
import { LOAD_RAMP } from "./static.js";
import { planned } from "./stub.js";

export default planned({
  name: "thermal_stress", tier: 1, word: "Heat stress", noun: "this heat", family: "static", scalesWithLoad: true,
  checks: ["stress", "displacement"], routine: () => LOAD_RAMP,
  markers: ["load", "fixture", "temperature", "heat", "convection"],
});
