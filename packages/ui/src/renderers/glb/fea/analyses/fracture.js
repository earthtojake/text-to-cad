/**
 * Cracks (lite): a crack the study describes, cut into the part and opened, judged by linear-elastic
 * fracture mechanics, Tier 3. Its verdict judges the crack's largest stress intensity K against the
 * material's toughness ("K 18 MPa√m at the deepest point, toughness 29 MPa√m"), which grows with the
 * load, so it has the load control and the Load ramp; with crack growth, the cycles until the crack
 * grows to its critical size against the cycles needed. Its takeaway leads with "Lite · ", and
 * Details lists its limits (LEFM only, small-scale yielding, no ductile tearing). What you see is
 * static's: the field (stress, displacement, which shows the crack opening) and the deformation. Its
 * setup is static's held at and pushed, then the crack in plain words ("2 mm edge crack on face 4",
 * its K the hint, chosen with the face it opens from tinted), then the material. It draws dots along
 * the crack's front.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { faceLabel, heldRows, madeOfRows, pushedRows, wholeRefs } from "../setup.js";
import { LOAD_RAMP } from "./static.js";

const KINDS = Object.freeze(["edge", "through", "surface", "embedded"]);
const finite = (value) => (Number.isFinite(Number(value)) && value !== null && value !== "" ? Number(value) : null);
const mm = (value) => `${plainNumber(value)} mm`;

/**
 * The crack as the file records it: the study's echo (`study.crack`: `kind`, `face`, `size_mm`,
 * `length_mm`) and what was solved (`extras.crack`: `K_max_MPa_sqrt_m`, `K_point`, `front_mm`, the
 * front's stations). null for a result with none.
 */
export function crackOf(result) {
  const extras = result?.mesh?.userData || {};
  const echo = extras.study?.crack && typeof extras.study.crack === "object" ? extras.study.crack : null;
  const solved = extras.crack && typeof extras.crack === "object" ? extras.crack : {};
  const kind = echo?.kind ?? solved.kind;
  const size = finite(echo?.size_mm ?? solved.size_mm);
  if (!KINDS.includes(kind) || size === null || !(size > 0)) return null;
  const front = Array.isArray(solved.front_mm)
    ? solved.front_mm.filter((point) => Array.isArray(point) && point.length === 3 && point.every((c) => Number.isFinite(c))) : [];
  return {
    kind, sizeMm: size, lengthMm: finite(echo?.length_mm), face: typeof (echo?.face ?? solved.face) === "string" ? (echo?.face ?? solved.face) : "",
    kMax: finite(solved.K_max_MPa_sqrt_m), point: typeof solved.K_point === "string" ? solved.K_point : "",
    toughness: finite(solved.toughness_MPa_sqrt_m), front,
  };
}

/**
 * The crack in a sentence, as its row says it: "2 mm edge crack on face 4", "1.5 mm deep surface
 * crack, 6 mm long, on face 4", "10 mm through crack across face 6", "2 mm embedded crack".
 */
export function crackWords(crack) {
  if (!crack) return "";
  const face = crack.face ? faceLabel(crack.face).toLowerCase() : "";
  if (crack.kind === "edge") return `${mm(crack.sizeMm)} edge crack${face ? ` on ${face}` : ""}`;
  if (crack.kind === "surface") {
    return `${mm(crack.sizeMm)} deep surface crack, ${mm(crack.lengthMm ?? 2 * crack.sizeMm)} long${face ? `, on ${face}` : ""}`;
  }
  if (crack.kind === "through") return `${mm(2 * crack.sizeMm)} through crack${face ? ` across ${face}` : ""}`;
  const across = crack.lengthMm !== null && Math.abs(crack.lengthMm - 2 * crack.sizeMm) > 1e-9 ? ` by ${mm(crack.lengthMm)}` : "";
  return `${mm(2 * crack.sizeMm)} embedded crack${across}`;
}

/** Its K in a hint: "K 18 MPa√m at the deepest point"; "" where the file does not say. */
export function crackHint(crack) {
  if (!crack || crack.kMax === null) return "";
  return `K ${plainNumber(crack.kMax)} MPa√m${crack.point ? ` at ${crack.point}` : ""}`;
}

/**
 * Study's "Crack": one row, the crack in plain words ("2 mm edge crack on face 4"), its K its hint,
 * chosen with the face it opens from (else the whole result). [] for a result with no crack.
 */
export function crackRows(result) {
  const crack = crackOf(result);
  if (!crack) return [];
  const label = crackWords(crack);
  const hint = crackHint(crack);
  const faces = crack.face ? [crack.face] : [];
  return [{ id: "crack", label: "Crack", detail: "", glyph: "plane", children: [{
    id: "crack:0", label, detail: "", wrap: true, ...(hint ? { hint } : {}),
    ...(faces.length ? { faces } : { refs: wholeRefs(result) }), summary: `Crack: ${label}${hint ? ` (${hint})` : ""}`,
  }] }];
}

/** Its setup: where it is held, what pushes it, the crack, what it is made of. */
export const FRACTURE_SETUP = Object.freeze([heldRows, pushedRows, crackRows, madeOfRows]);

export default Object.freeze({
  name: "fracture",
  tier: 3,
  word: "Cracks",
  noun: "this load",
  family: null,
  estimate: false,
  // K is linear in the load: the load control moves the fracture check (a crack life does not move).
  scalesWithLoad: true,
  checks: Object.freeze(["fracture", "crack_life", "stress", "displacement"]),
  checkLabels: Object.freeze({}),
  defaultControls: fieldAndDeformation,
  setupGroups: FRACTURE_SETUP,
  routine: () => LOAD_RAMP,
  markers: Object.freeze(["load", "fixture", "body_load", "crack_front"]),
  displayTitle: "Loads, fixtures and the crack",
  // A Tier 3 analysis's short limit word, which leads its verdict's takeaway.
  limitWord: "Lite",
});
