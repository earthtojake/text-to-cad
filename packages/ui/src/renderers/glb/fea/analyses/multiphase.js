/**
 * Two fluids (lite): a liquid and a gas inside the part over time (sloshing in a shaken tank, filling or
 * draining, a rising bubble), Tier 3. Its fields are on the part's wetted walls, one per time frame: the
 * water fraction (1 where the liquid touches the wall, 0 where the gas does) and the wall pressure (Pa,
 * signed); mapped onto the structure (one-way), the part's stress and displacement join them and it
 * deforms. Its verdict judges the highest the liquid rises (against the brim or a limit: "Spills over",
 * "Close to the brim", "Stays in") and the hardest it presses on the walls, none of which a load control
 * moves, and choosing a check jumps the scrubber to when it peaked. Its takeaway leads with "Laminar · ".
 * What you see opens on the Time scrubber (on the moment the liquid rises highest) and the field, water
 * fraction first; Play runs the frames over three seconds. Its setup says how full it starts and how it
 * is shaken ("Half full of water, shaken 0.3 g along X"), where fluid goes in and out, and, mapped, where
 * it is held and what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { frameControl } from "../series.js";
import { axisWords, heldRows, madeOfRows, wholeRefs } from "../setup.js";
import { planned } from "./stub.js";
import { PLAY, historyWords } from "./transient.js";

const record = (raw) => (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : null);

/** What the file says of the two fluids: the study's `multiphase` (as the viewer read it) and its analysis's `fill`. */
function twoFluids(result) {
  const extras = result?.mesh?.userData || {};
  return { study: record(result?.study?.multiphase), fill: record(extras.analysis?.fill) };
}

/** How full it starts, in words: "Half full of water", "A quarter full of oil", "40 % full of water". */
export function fillWords(fraction, liquid = "water") {
  const name = liquid || "liquid";
  if (!Number.isFinite(fraction)) return `Partly ${name}`;
  const named = [[0.25, "A quarter full"], [0.5, "Half full"], [0.75, "Three quarters full"], [1, "Full"]];
  const near = named.find(([share]) => Math.abs(fraction - share) < 0.02);
  return near ? `${near[1]} of ${name}` : `${Math.round(100 * fraction)} % full of ${name}`;
}

/** How it is shaken, in words: "shaken 0.3 g along X". "" for a part held still. */
export function shakeWords(acceleration) {
  const shake = record(acceleration);
  if (!shake || !Number.isFinite(shake.amplitude_g) || !Array.isArray(shake.direction)) return "";
  const along = axisWords(shake.direction);
  return `shaken ${plainNumber(Math.abs(shake.amplitude_g))} g${along ? ` along ${along}` : ""}`;
}

const SINGLE_FLUID = /^Completely full: solved as single-fluid flow/;

/**
 * Study's "Filled": how full it starts and how it is shaken, its hint how the shake changes over time; a
 * completely full inside's hint says it was solved as the liquid's flow alone ("Completely full: solved as
 * single-fluid flow, no free surface").
 */
export function filledRows(result) {
  const { study, fill } = twoFluids(result);
  if (!study && !fill) return [];
  const words = fillWords(fill?.fraction, fill?.liquid || study?.liquid?.name);
  const shake = shakeWords(study?.acceleration);
  const label = shake ? `${words}, ${shake}` : words;
  const history = study?.acceleration ? historyWords(study.acceleration.history) : "";
  // A completely full inside has no free surface: cadgen solves the liquid's flow alone and says so.
  const single = (result.analysis?.warnings || []).find((line) => SINGLE_FLUID.test(line)) || "";
  const hint = [single, history ? `Over time: ${history}` : ""].filter(Boolean).join(". ");
  const refs = wholeRefs(result);
  return [{ id: "filled", label: "Filled", detail: "", glyph: "flow", children: [{ id: "filled:0", label, detail: "", wrap: true,
    ...(hint ? { hint } : {}),
    ...(refs.length ? { refs, summary: `Filled: ${label.charAt(0).toLowerCase()}${label.slice(1)}${history ? `, ${history}` : ""}` } : {}) }] }];
}

const sideWords = (opening) => {
  const [axis, end] = String(opening || "").split("_");
  return axis && end ? `the ${end === "min" ? "low" : "high"} ${axis.toUpperCase()} side` : "";
};

/** Study's "Flow in/out": each inlet's speed, side and fluid, each outlet's pressure and side. */
export function openingRows(result) {
  const { study } = twoFluids(result);
  if (!study) return [];
  const refs = wholeRefs(result);
  const row = (id, label) => ({ id, label, detail: "", wrap: true, ...(refs.length ? { refs, summary: label } : {}) });
  const fluidOf = (kind) => (kind === "gas" ? study.gas?.name : study.liquid?.name) || kind;
  const rows = [
    ...(Array.isArray(study.inlets) ? study.inlets : []).map((inlet, index) => row(`inlet:${index}`,
      `${fluidOf(inlet.fluid)} in${Number.isFinite(inlet.velocity_m_s) ? ` at ${plainNumber(inlet.velocity_m_s)} m/s` : ""}, ${sideWords(inlet.opening)}`)),
    ...(Array.isArray(study.outlets) ? study.outlets : []).map((outlet, index) => row(`outlet:${index}`,
      `Out${Number.isFinite(outlet.pressure_Pa) ? ` at ${plainNumber(outlet.pressure_Pa)} Pa` : ""}, ${sideWords(outlet.opening)}`)),
  ].map((entry) => ({ ...entry, label: entry.label.charAt(0).toUpperCase() + entry.label.slice(1) }));
  return rows.length ? [{ id: "flow", label: "Flow in/out", detail: "", glyph: "flow", children: rows }] : [];
}

/** Two fluids' setup: filled (and shaken), flow in/out, then (mapped onto the structure) held and made of. */
export const TWO_FLUIDS_SETUP = Object.freeze([filledRows, openingRows, heldRows, madeOfRows]);

/**
 * The Time scrubber over its frames (opening on the series' default, the highest rise), the field (water
 * fraction first), and the deformation only when the fluids' push was mapped onto the structure.
 */
export function twoFluidControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const time = frameControl(result, "frame");
  const mapped = result.fields.some((entry) => String(entry.attribute).toLowerCase() === "_displacement");
  return [...(time ? [time] : []), field, ...(mapped ? [deformation] : [])];
}

export default planned({
  name: "multiphase", tier: 3, word: "Two fluids", noun: "this shake", limitWord: "Laminar", family: null, scalesWithLoad: false,
  checks: ["fill_level", "wall_pressure", "stress", "displacement"],
  defaultControls: twoFluidControls,
  setupGroups: TWO_FLUIDS_SETUP,
  routine: (result) => (result?.series ? PLAY : null),
  markers: ["inlet", "outlet", "fixture"], displayTitle: "Flow openings",
});
