/**
 * Spinning (lite): a shaft and its discs spinning on bearings, Tier 3. Its result is a series of whirl
 * shapes, one per critical speed ("Critical · 12,400 rpm · forward"; with none in the sweep, the whirls
 * at the top speed), each an orbit: its real part the deformation, its imaginary part beside it
 * (`displacement_im`), which the Whirl routine turns through so every section of the shaft walks its
 * orbit. The part is coloured by its spinning stress at the top speed. Its verdict judges the critical
 * speeds against the operating speeds ("Critical at 12,400 rpm, 14% above the 10,800 rpm top speed"),
 * the whirl's damping (log decrement) and the spinning stress, none of which a load control moves. Its
 * takeaway leads with "Lite · ", and Details lists its limits (linear bearings, bending whirl only). What
 * you see opens on the whirl picker, the field (stress, whirl) and the deformation. Its setup says how it
 * spins ("Spins 0 to 12,000 rpm about Z"), where its bearings are ("Bearings at face 3 and face 9"), the
 * discs and unbalances the study adds, and what it is made of; it reads them from the study the file
 * records (`extras.study`: `spin`, `bearings`, `discs`, `unbalance`).
 */
import { rpmWords } from "../checkKinds.js";
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { frameControl } from "../series.js";
import { faceLabel, madeOfRows, wholeRefs } from "../setup.js";
import { routineOf } from "./stub.js";

/** Whirl: a one-second loop of the chosen whirl shape walking its orbit (re·cos − im·sin), every section at once. */
export const WHIRL = routineOf("Whirl", "vibrate");

export { rpmWords };

const finite = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);
const AXES = Object.freeze(["X", "Y", "Z"]);

/** The spin axis in words: "Z", else its direction "(0.6, 0, 0.8)". */
function axisName(axis) {
  if (typeof axis === "string" && axis) return axis;
  if (!Array.isArray(axis) || axis.length !== 3) return "";
  const size = Math.hypot(...axis);
  if (!(size > 0)) return "";
  const unit = axis.map((value) => value / size);
  const along = unit.findIndex((value) => Math.abs(value) > 1 - 1e-9);
  return along >= 0 ? AXES[along] : `(${unit.map((value) => plainNumber(value).replace(/^-/, "−")).join(", ")})`;
}

/** The study's spin, bearings, discs and unbalances as the file records them (`extras.study`), or null for none. */
export function rotorOf(result) {
  const study = result?.mesh?.userData?.study;
  const spin = study?.spin;
  if (!spin || typeof spin !== "object") return null;
  const rpm = Array.isArray(spin.rpm) && spin.rpm.length === 2 && spin.rpm.every((v) => finite(v) !== null) ? spin.rpm.map(Number) : null;
  const list = (raw) => (Array.isArray(raw) ? raw.filter((entry) => entry && typeof entry === "object") : []);
  const refs = (raw) => (Array.isArray(raw) ? raw.filter((ref) => typeof ref === "string" && ref) : []);
  return {
    axis: axisName(spin.axis),
    rpm,
    bearings: list(study.bearings).map((entry) => ({
      faces: refs(entry.faces), atMm: finite(entry.at_mm), rigid: entry.rigid === true, clamped: entry.clamped === true,
      k: finite(entry.kxx), c: finite(entry.cxx), varies: Array.isArray(entry.kxx) || Array.isArray(entry.cxx),
    })),
    discs: list(study.discs).map((entry) => ({ atMm: finite(entry.at_mm), massKg: finite(entry.mass_kg) })),
    unbalance: list(study.unbalance).map((entry) => ({ faces: refs(entry.faces), atMm: finite(entry.at_mm), gMm: finite(entry.g_mm) })),
  };
}

/** How it spins in words: "Spins 0 to 12,000 rpm about Z", "Spins at 3,000 rpm about X". "" for no spin. */
export function spinWords(rotor) {
  if (!rotor?.rpm) return "";
  const [low, high] = rotor.rpm;
  const about = rotor.axis ? ` about ${rotor.axis}` : "";
  if (low === high) return `Spins at ${rpmWords(high)}${about}`;
  const from = low >= 1000 ? rpmWords(low).replace(/ rpm$/, "") : plainNumber(low);
  return `Spins ${from} to ${rpmWords(high)}${about}`;
}

/** Where something sits on the rotor: "face 3", "faces 3, 4", "250 mm along Z". */
function placeWords(entry, axis) {
  if (entry.faces.length) return entry.faces.map((ref) => faceLabel(ref).toLowerCase()).join(" and ");
  return entry.atMm === null ? "" : `${plainNumber(entry.atMm)} mm along ${axis || "the axis"}`;
}

/** A bearing's springs in words: "Rigid", "Clamped", "20,000 N/mm, 5 N·s/mm", "Changes with speed". */
export function bearingWords(bearing) {
  if (bearing.clamped) return "Clamped: holds the shaft and its tilt";
  if (bearing.rigid) return "Rigid";
  if (bearing.varies) return "Stiffness changes with speed";
  const k = bearing.k === null ? "" : `${Number(plainNumber(bearing.k)).toLocaleString("en-US")} N/mm`;
  const c = bearing.c ? `${plainNumber(bearing.c)} N·s/mm` : "";
  return [k, c].filter(Boolean).join(", ");
}

/** Study's "Spins": one row, how fast and about which axis, chosen with the whole part. */
export function spinRows(result) {
  const rotor = rotorOf(result);
  const label = spinWords(rotor);
  if (!label) return [];
  const refs = wholeRefs(result);
  return [{ id: "spin", label: "Spins", detail: "", glyph: "wave", children: [{
    id: "spin:0", label, detail: "", wrap: true, ...(refs.length ? { refs, summary: label } : {}),
  }] }];
}

/** Study's "Bearings": one row naming them all ("Bearings at face 3 and face 9"), chosen with their faces; each bearing's springs its hint. */
export function bearingRows(result) {
  const rotor = rotorOf(result);
  if (!rotor?.bearings.length) return [];
  const places = rotor.bearings.map((bearing) => placeWords(bearing, rotor.axis)).filter(Boolean);
  const label = `Bearings at ${places.join(" and ")}`;
  const kinds = [...new Set(rotor.bearings.map(bearingWords).filter(Boolean))];
  const faces = rotor.bearings.flatMap((bearing) => bearing.faces);
  return [{ id: "bearings", label: "Bearings", detail: "", glyph: "fixture", children: [{
    id: "bearings:0", label, detail: "", wrap: true, ...(kinds.length ? { hint: kinds.join("; ") } : {}),
    ...(faces.length ? { faces } : { refs: wholeRefs(result) }), summary: label,
  }] }];
}

/** Study's "Unbalance": one row per unbalance ("50 g·mm at face 5"), chosen with its faces. */
export function unbalanceRows(result) {
  const rotor = rotorOf(result);
  const rows = (rotor?.unbalance || []).filter((entry) => entry.gMm !== null).map((entry, index) => {
    const place = placeWords(entry, rotor.axis);
    const label = `${plainNumber(entry.gMm)} g·mm${place ? ` at ${place}` : ""}`;
    return { id: `unbalance:${index}`, label, detail: "", wrap: true, summary: `Unbalance ${label}`,
      ...(entry.faces.length ? { faces: entry.faces } : { refs: wholeRefs(result) }) };
  });
  return rows.length ? [{ id: "unbalance", label: "Unbalance", detail: "", glyph: "load", children: rows }] : [];
}

/** Study's "Discs added": each disc the study adds to the CAD's ("2.5 kg disc at 150 mm along Z"). */
export function discRows(result) {
  const rotor = rotorOf(result);
  const rows = (rotor?.discs || []).filter((disc) => disc.massKg !== null).map((disc, index) => {
    const label = `${plainNumber(disc.massKg)} kg disc${disc.atMm === null ? "" : ` at ${plainNumber(disc.atMm)} mm along ${rotor.axis || "the axis"}`}`;
    const refs = wholeRefs(result);
    return { id: `disc:${index}`, label, detail: "", wrap: true, ...(refs.length ? { refs, summary: `Added ${label}` } : {}) };
  });
  return rows.length ? [{ id: "discs", label: "Discs added", detail: "", glyph: "plane", children: rows }] : [];
}

/** Its setup: how it spins, its bearings, the discs and unbalances the study adds, what it is made of. */
export const ROTOR_SETUP = Object.freeze([spinRows, bearingRows, discRows, unbalanceRows, madeOfRows]);

/** What you see: the whirl picker (one shape per critical speed), the field, and the deformation. */
export function whirlControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const whirl = frameControl(result, "mode", { label: "Whirl" });
  return [...(whirl ? [whirl] : []), field, deformation];
}

export default Object.freeze({
  name: "rotordynamics",
  tier: 3,
  word: "Spinning",
  noun: "this spin",
  family: null,
  estimate: false,
  // A critical speed, a log decrement and the stress at the top speed: no load control moves them.
  scalesWithLoad: false,
  checks: Object.freeze(["critical_speed", "stability", "stress"]),
  checkLabels: Object.freeze({ stress: "Spin stress" }),
  defaultControls: whirlControls,
  setupGroups: ROTOR_SETUP,
  routine: (result) => (result?.series ? WHIRL : null),
  markers: Object.freeze([]),
  displayTitle: "Bearings",
  limitWord: "Lite",
});
