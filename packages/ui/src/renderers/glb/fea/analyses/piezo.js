/**
 * Piezo (lite), Tier 3: coupled electro-mechanical parts, actuators, sensors and buzzers, by the
 * study's `solve`. Static: the voltage on its electrodes moves it (or a force makes a voltage on an
 * open electrode); its fields are the stress, the voltage (signed), the electric field and the
 * displacement. Resonance: a series of modes, each frame its shape, stress and voltage; the mode
 * picker chooses one and Vibrate plays it. Harmonic: a series of frequencies across the sweep, each
 * its displacement, stress and voltage amplitude; the Frequency scrubber chooses one. Its verdict
 * judges stress, displacement, an open electrode's signal (`voltage`: "0.82 V, needs at least 0.5 V")
 * or a frequency; no load control moves them. Its takeaway leads with "Linear · " (small signal, no
 * depolarisation). Its setup says each electrode ("1 V on the top electrode", "The out electrode, open"),
 * how each part is poled ("Poled along Z"), where it is held and pushed, and what it is made of.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber } from "../numbers.js";
import { frameControl } from "../series.js";
import { axisWords, faceTitle, heldRows, madeOfRows, pushedRows, spaced } from "../setup.js";
import { VIBRATE as HARMONIC_VIBRATE } from "./harmonic.js";
import { VIBRATE } from "./modal.js";
import { planned } from "./stub.js";

/** The piezo study as the viewer read it (`readStudy`'s `piezo`): its solve, electrodes and poling; null for none. */
const piezoOf = (result) => result?.study?.piezo || null;

/** Faces in a prompt's words: "face 3", "faces 3, 4". */
function facesWords(faces) {
  const names = faces.map((ref) => /\.f(\d+)$/.exec(ref)?.[1] ?? ref);
  return `${names.length === 1 ? "face" : "faces"} ${names.join(", ")}`;
}

/** The poling in words: "along Z", "along −Z", "along (0.6, 0, 0.8)". */
export function polingWords(direction) {
  const line = axisWords(direction);
  if (!line) return "";
  const axis = direction.findIndex((value) => Math.abs(value) > 1e-6);
  const single = direction.filter((value) => Math.abs(value) > 1e-6).length === 1;
  return single && direction[axis] < 0 ? `along −${line}` : `along ${line}`;
}

/** How the study's piezo parts are poled, as one phrase when they share a direction: "poled along Z"; "" for none. */
function poledPhrase(result) {
  const poling = piezoOf(result)?.poling || [];
  const words = [...new Set(poling.map((entry) => polingWords(entry.direction)).filter(Boolean))];
  return words.length === 1 ? `poled ${words[0]}` : "";
}

/** An electrode's row label: "1 V on the top electrode", "0 V on the ground electrode", "The out electrode, open". */
export function electrodeLabel(entry) {
  const name = entry.name ? `the ${spaced(entry.name)} electrode` : "the electrode";
  if (entry.open || entry.volts === null) return `${name.charAt(0).toUpperCase()}${name.slice(1)}, open`;
  return `${plainNumber(entry.volts)} V on ${name}`;
}

/**
 * Study's "Electrodes": one row per electrode, its voltage or "open" ("1 V on the top electrode"), its faces under it,
 * the poling in its prompt ("1 V on the top electrode (face 6), poled along Z").
 */
export function piezoElectrodeRows(result) {
  const piezo = piezoOf(result);
  if (!piezo) return [];
  const poled = poledPhrase(result);
  const rows = piezo.electrodes.filter((entry) => entry.faces.length).map((entry, index) => {
    const label = electrodeLabel(entry);
    const summary = (faces) => `${label} (${facesWords(faces)})${poled ? `, ${poled}` : ""}`;
    return {
      id: `electrode:${index}`, label, detail: "", faces: entry.faces, summary: summary(entry.faces), collapsed: true,
      ...(entry.open ? { hint: "Floats: one voltage, no net charge (a sensor's output)" } : {}),
      children: entry.faces.map((ref) => ({ id: `electrode:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref],
        wrap: true, summary: summary([ref]) })),
    };
  });
  return rows.length ? [{ id: "electrodes", label: "Electrodes", detail: "", glyph: "fixture", children: rows }] : [];
}

/** Study's "Poled": one row per piezo part, "Along Z", the part and its ceramic its hint. */
export function poledRows(result) {
  const poling = piezoOf(result)?.poling || [];
  const rows = poling.map((entry, index) => {
    const words = polingWords(entry.direction);
    const label = `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
    const hint = [entry.part ? spaced(entry.part) : "", entry.material].filter(Boolean).join(", ");
    return { id: `poled:${index}`, label, detail: "", ...(hint ? { hint } : {}),
      summary: `${entry.part ? `${spaced(entry.part)} ` : ""}poled ${words}`.replace(/^./, (c) => c.toUpperCase()) };
  });
  return rows.length ? [{ id: "poled", label: "Poled", detail: "", glyph: "wave", children: rows }] : [];
}

export const PIEZO_SETUP = Object.freeze([piezoElectrodeRows, poledRows, heldRows, pushedRows, madeOfRows]);

/**
 * What you see: a resonance opens on the mode picker, the field and the deformation; a sweep on the Frequency scrubber,
 * the field and the deformation; a static result on the field (stress, voltage, field, displacement) and the deformation.
 */
export function piezoControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const series = result.series ? frameControl(result, result.series.kind === "mode" ? "mode" : "frame") : null;
  return series ? [series, field, deformation] : [field, deformation];
}

/** Its routine: Vibrate through a mode or a frequency's cycle; none for a static result. */
export function piezoRoutine(result) {
  if (result?.series?.kind === "mode") return VIBRATE;
  if (result?.series?.kind === "frequency") return HARMONIC_VIBRATE;
  return null;
}

export default planned({
  name: "piezo", tier: 3, word: "Piezo", noun: "this voltage", limitWord: "Linear", family: null,
  scalesWithLoad: false,
  checks: ["stress", "displacement", "voltage", "frequency"],
  defaultControls: piezoControls,
  setupGroups: PIEZO_SETUP,
  routine: piezoRoutine,
  markers: ["fixture", "load", "electrode"], displayTitle: "Electrodes and fixtures",
});
