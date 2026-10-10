/**
 * Fatigue life: how many cycles of its load the part lasts, from a static load case repeated. Its
 * fields are the life (log10 cycles, the colour bar in powers of ten) and the fatigue safety factor;
 * the displacement rides along at the load's peak. Its one check kind, `fatigue`, is judged at the
 * cycles needed and does not follow the load control (a Goodman factor is not linear in the load),
 * so it has no load control and no routine. Its setup is static's: where it is held, what pushes it
 * each cycle, what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";
import { planned } from "./stub.js";

export default planned({
  name: "fatigue", tier: 1, word: "Fatigue life", noun: "this load", family: null, scalesWithLoad: false,
  checks: ["fatigue"],
  // The field (life first, then the fatigue factor and the displacement) and the deformation.
  defaultControls: fieldAndDeformation,
  setupGroups: [heldRows, pushedRows, madeOfRows],
  routine: () => null,
  markers: ["load", "fixture", "body_load"],
});
