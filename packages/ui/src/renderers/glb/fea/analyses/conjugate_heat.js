/**
 * Cooled by flow (lite): heat carried by a flowing fluid into and out of the part (conjugate heat transfer),
 * Tier 3. Its fields are on the part's surface: the part's temperature (signed), the fluid's temperature next
 * to each wetted wall, the heat into the flow (W/m², signed) and the heat transfer coefficient, and the wall
 * pressure. Its verdict judges the hottest point of the part against a limit (measured from the coolest
 * temperature the study sets) and the flow's pressure drop and fastest speed, none of which a load control
 * moves; nothing deforms. Its takeaway leads with the flow model the file solved ("Laminar · ", "Turbulent · ").
 * What you see opens on the field alone, temperature first, with the fluid temperature among its options; its
 * setup says where the flow goes in and out, the coolant and its temperature, where heat goes in, where it is
 * kept at a temperature or cooled by air, and what it is made of. It plays no routine.
 */
import { fieldOnly } from "./thermal.js";
import { coolantRows, cooledRows, flowRows, heatedRows, keptAtRows, madeOfRows } from "../setup.js";
import { planned } from "./stub.js";

/** Cooled by flow's setup: flow in/out, the coolant, heated, kept at, cooled by air, made of. */
export const COOLED_SETUP = Object.freeze([flowRows, coolantRows, heatedRows, keptAtRows, cooledRows, madeOfRows]);

/** The takeaway's lead word: the flow model the file says it solved, else "Flow". */
export const cooledLimitWord = (result) => {
  const regime = result?.analysis?.regime || result?.study?.flow?.regime;
  return regime === "turbulent" ? "Turbulent" : regime === "laminar" ? "Laminar" : "Flow";
};

export default planned({
  name: "conjugate_heat", tier: 3, word: "Cooled by flow", noun: "this heat", limitWord: "Flow", limitWordOf: cooledLimitWord,
  family: null, scalesWithLoad: false,
  checks: ["temperature", "pressure_drop", "velocity"],
  defaultControls: fieldOnly,
  setupGroups: COOLED_SETUP,
  routine: () => null,
  markers: ["inlet", "outlet", "heat", "temperature", "convection"], displayTitle: "Flow openings and heat",
});
