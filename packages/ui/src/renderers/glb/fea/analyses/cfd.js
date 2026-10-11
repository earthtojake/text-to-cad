/**
 * Flow (lite): steady laminar incompressible flow through or around the part, Tier 3. Its fields are
 * on the part's wetted surface: the wall pressure (Pa, signed) and the wall shear; mapped onto the
 * structure (one-way), the part's stress and displacement join them and it deforms. Its verdict
 * judges the pressure drop and the fastest flow (and the stress and displacement when mapped), none
 * of which a load control moves, and its takeaway leads with "Laminar · " (past the laminar range,
 * "Laminar · unreliable above Re 2000 · "). What you see opens on the field (Pressure first) and,
 * mapped, the deformation; its setup says where the flow goes in and out, where it is held (mapped)
 * and what it is made of. It plays no routine.
 */
import { fieldAndDeformation } from "../controls.js";
import { flowRows, heldRows, madeOfRows } from "../setup.js";
import { planned } from "./stub.js";

/** Flow's setup: flow in/out, then (mapped onto the structure) held and made of. */
export const FLOW_SETUP = Object.freeze([flowRows, heldRows, madeOfRows]);

/**
 * The field select (pressure first), and the deformation only when the flow was mapped onto the
 * structure (its displacement is among the fields): an unmapped flow moves nothing.
 */
export function flowControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  return result.fields.some((entry) => String(entry.attribute).toLowerCase() === "_displacement") ? [field, deformation] : [field];
}

export default planned({
  name: "cfd", tier: 3, word: "Flow", noun: "this flow", limitWord: "Laminar", family: null, scalesWithLoad: false,
  checks: ["pressure_drop", "velocity", "stress", "displacement"],
  defaultControls: flowControls,
  setupGroups: FLOW_SETUP,
  routine: () => null,
  markers: ["inlet", "outlet", "fixture"], displayTitle: "Flow openings",
});
