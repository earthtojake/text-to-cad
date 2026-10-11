/**
 * Fatigue life: how many cycles of its load the part lasts, from a static load case repeated. Its
 * fields are the life (log10 cycles, the colour bar in powers of ten) and the fatigue safety factor;
 * the displacement rides along at the load's peak. Its one check kind, `fatigue`, is judged at the
 * cycles needed and does not follow the load control (a Goodman factor is not linear in the load),
 * so it has no load control and no routine. Its setup is static's: where it is held, what pushes it
 * each cycle, what it is made of. Where the part outlasts the material's data everywhere, the life is
 * one capped number with nothing to show, so What you see opens on the fatigue margin instead.
 */
import { fieldAndDeformation } from "../controls.js";
import { heldRows, madeOfRows, pushedRows } from "../setup.js";
import { planned } from "./stub.js";

const FATIGUE_FACTOR = "_fatigue_factor";

/** Whether the life is the same everywhere: the part outlasts the material's data (the life is capped) on every face. */
export function lifeCapped(result) {
  const life = result.fields.find((entry) => entry.attribute === "_life");
  return Boolean(life) && !(life.max - life.min > 1e-6);
}

/** The field (life first, the fatigue margin where the life is capped everywhere) and the deformation. */
export function fatigueControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const margin = lifeCapped(result) && field.options.some((option) => option.value === FATIGUE_FACTOR);
  return [margin ? { ...field, defaultValue: FATIGUE_FACTOR } : field, deformation];
}

export default planned({
  name: "fatigue", tier: 1, word: "Fatigue life", noun: "this load", family: null, scalesWithLoad: false,
  checks: ["fatigue"],
  // The field (life first, then the fatigue factor and the displacement) and the deformation.
  defaultControls: fatigueControls,
  setupGroups: [heldRows, pushedRows, madeOfRows],
  routine: () => null,
  markers: ["load", "fixture", "body_load"],
});
