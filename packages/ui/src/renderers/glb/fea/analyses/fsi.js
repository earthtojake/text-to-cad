/**
 * Flow and bending (lite): steady two-way fluid-structure interaction, Tier 3. The flow pushes the
 * part, the part bends, the bend changes the flow, until the two agree. Its fields are on the part:
 * the von Mises stress (first), the wall pressure (Pa, signed), the wall shear and the displacement,
 * and it deforms by that displacement. Its verdict judges the stress, the displacement and the
 * pressure drop, none of which a load control moves (the flow's push is not proportional to the
 * flow's speed); its takeaway leads with the flow's regime ("Laminar · ", "Turbulent · ") and, where
 * the coupling did not settle, "not converged". What you see opens on the field and the deformation;
 * its setup says what bends it ("Water at 0.5 m/s bends the flap"), where the flow goes in and out,
 * where it is held and what it is made of; Details add the coupling's iterations. It plays no routine.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { flowRows, heldRows, madeOfRows, wholeRefs } from "../setup.js";
import { planned } from "./stub.js";

/** What the file says of its coupling (`extras.analysis.coupling`): iterations, converged, residual, tolerance, method. null for none. */
export function couplingOf(result) {
  const raw = result?.mesh?.userData?.analysis?.coupling;
  if (!raw || typeof raw !== "object" || !Number.isFinite(raw.iterations)) return null;
  return {
    iterations: Number(raw.iterations), converged: raw.converged !== false,
    residual: Number.isFinite(raw.residual) ? Number(raw.residual) : null,
    tolerance: Number.isFinite(raw.tolerance) ? Number(raw.tolerance) : null,
    method: raw.method === "fixed_point" ? "fixed_point" : "aitken",
  };
}

const capital = (text) => (text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}` : "");

/** The part's name as the file gives it ("flap" of "flap flow and bending"), else "the part". */
function partName(result) {
  const name = String(result?.name || "").replace(/ flow and bending$/, "").replace(/_/g, " ").trim();
  return name ? `the ${name}` : "the part";
}

/** Study's "Bent by the flow": "Water at 0.5 m/s bends the flap", chosen with the whole part. */
export function bentRows(result) {
  const flow = result.study.flow;
  if (!flow) return [];
  const speeds = flow.inlets.map((inlet) => inlet.speed).filter((speed) => speed !== null);
  const speed = speeds.length ? ` at ${plainNumber(Math.max(...speeds))} m/s` : "";
  const label = `${capital(flow.fluid) || "The flow"}${speed} bends ${partName(result)}`;
  const refs = wholeRefs(result);
  return [{ id: "bent", label: "Bent by the flow", detail: "", glyph: "flow", children: [{ id: "bent:flow", label, detail: "", wrap: true,
    ...(refs.length ? { refs, summary: `${label}, and the bend changes the flow (two-way)` } : {}) }] }];
}

/** Flow and bending's setup: what bends it, flow in/out, held at, made of. */
export const FSI_SETUP = Object.freeze([bentRows, flowRows, heldRows, madeOfRows]);

/** Details' coupling row: "Coupling: settled in 4 iterations", its hint the residual it reached. */
export function couplingRows(result, whole = () => ({})) {
  const coupling = couplingOf(result);
  if (!coupling) return [];
  const times = `${coupling.iterations} ${coupling.iterations === 1 ? "iteration" : "iterations"}`;
  const label = coupling.converged ? `Coupling: settled in ${times}` : `Coupling: did not settle in ${times}`;
  const hint = coupling.residual === null ? "" : coupling.converged
    ? `Last change ${coupling.residual.toExponential(1)} of itself`
    : `Still changing by ${coupling.residual.toExponential(1)}${coupling.tolerance === null ? "" : `, short of ${coupling.tolerance.toExponential(0)}`}: the last state, not an answer`;
  return [{ id: "coupling", label, detail: "", wrap: true, ...(hint ? { hint } : {}), ...whole(`${label}${hint ? ` (${hint})` : ""}`) }];
}

/** The takeaway's lead: the flow's regime, and "not converged" where the coupling did not settle. */
export const fsiLimitWord = (result) => {
  const regime = result?.analysis?.regime || result?.study?.flow?.regime;
  const word = regime === "turbulent" ? "Turbulent" : regime === "laminar" ? "Laminar" : "Flow and bending";
  return couplingOf(result)?.converged === false ? `${word} · not converged` : word;
};

export default planned({
  name: "fsi", tier: 3, word: "Flow and bending", noun: "this flow", limitWord: "Flow and bending", limitWordOf: fsiLimitWord,
  family: null, scalesWithLoad: false,
  checks: ["stress", "displacement", "pressure_drop"],
  defaultControls: fieldAndDeformation,
  setupGroups: FSI_SETUP,
  detailRows: couplingRows,
  routine: () => null,
  markers: ["inlet", "outlet", "fixture"], displayTitle: "Flow openings and fixtures",
});
