/**
 * Magnetic / electric (lite), Tier 3: a static electric field, a steady (DC) current, a static
 * magnetic field or an AC one at a frequency (`ac_magnetic`: eddy currents, skin effect, induction
 * heating), by the study's `mode`. Its fields are on the parts' surface: the voltage (signed)
 * and the electric field, the voltage and the current density, or the magnetic field; with the Joule
 * heat handed to a thermal solve the temperature joins, and with the magnetic force handed to a static
 * solve the stress and displacement join and it deforms; an AC field carries the eddy current and the
 * magnetic field (amplitudes), and the temperature its loss makes. Its verdict judges the strongest electric
 * field against the gap's limit ("Arcs over"), the temperature, or the stress and displacement; no
 * load control moves them (a field grows with the voltage, a force with the current squared). Its
 * takeaway leads with "Static · ", or "AC · " for a field at a frequency. What you see opens on the Field select (and the deformation
 * when the force was mapped); its setup says where it is held at a voltage, where a current goes in,
 * which coils drive it (at what frequency: "Coil 2 A at 50 kHz", "Field 10 mT at 500 Hz"), where it is kept at a temperature or cooled, where it is held (mapped) and
 * what it is made of. It plays no routine.
 */
import { fieldAndDeformation } from "../controls.js";
import { plainNumber, threeFigures } from "../numbers.js";
import { cooledRows, faceTitle, heldRows, keptAtRows, madeOfRows, spaced } from "../setup.js";
import { planned } from "./stub.js";

/** The study as the file echoes it (the viewer's reader keeps only the keys every analysis shares). */
const echo = (result) => {
  const raw = result?.mesh?.userData?.study;
  return raw && typeof raw === "object" ? raw : {};
};

const list = (value) => (Array.isArray(value) ? value.filter((entry) => entry && typeof entry === "object") : []);
const refs = (value) => (Array.isArray(value) ? value.filter((ref) => typeof ref === "string" && ref) : []);
const number = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);

/** An AC study's frequency, null for a static or DC one. */
const frequencyOf = (result) => {
  const study = echo(result);
  return study.mode === "ac_magnetic" ? number(study.frequency_Hz) : null;
};

/** A frequency as a person says it: "50 Hz", "15.8 kHz", "2 MHz". */
export function hertz(value) {
  for (const [scale, unit] of [[1e6, "MHz"], [1e3, "kHz"]]) {
    if (value >= scale) return `${threeFigures(value / scale)} ${unit}`;
  }
  return `${threeFigures(value)} Hz`;
}

/** " at 50 kHz" for an AC study, "" otherwise. */
const atFrequency = (result) => {
  const hz = frequencyOf(result);
  return hz === null ? "" : ` at ${hertz(hz)}`;
};

/** Faces in a prompt's words: "face 3", "faces 3, 4". */
function facesWords(faces) {
  const names = faces.map((ref) => /\.f(\d+)$/.exec(ref)?.[1] ?? ref);
  return `${names.length === 1 ? "face" : "faces"} ${names.join(", ")}`;
}

/** One row per entry, its faces under it, shut until opened. */
function entryRows(result, id, entries) {
  return entries.map((entry, index) => ({
    id: `${id}:${index}`, label: entry.label, detail: "", faces: entry.faces, summary: entry.summary(entry.faces), collapsed: true,
    ...(entry.hint ? { hint: entry.hint } : {}),
    children: entry.faces.map((ref) => ({ id: `${id}:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], wrap: true,
      summary: entry.summary([ref]) })),
  }));
}

/** Study's "Electrodes": "Held at 1000 V" per held voltage, "2 A in" ("2 A in at 50 kHz") per current put in, each its faces under it. */
export function electrodeRows(result) {
  const study = echo(result);
  const at = atFrequency(result);
  const held = list(study.voltages).map((entry) => {
    const volts = number(entry.V);
    const label = volts === null ? "Held at a voltage" : `Held at ${plainNumber(volts)} V`;
    const named = typeof entry.name === "string" && entry.name && !/^-?[\d.e+]+ V$/.test(entry.name) ? entry.name : "";
    return { faces: refs(entry.faces), label, hint: named, summary: (faces) => `${label} on ${facesWords(faces)}` };
  });
  const fed = list(study.currents).map((entry) => {
    const amps = number(entry.A);
    const label = amps === null ? `A current in${at}` : `${plainNumber(amps)} A in${at}`;
    return { faces: refs(entry.faces), label, summary: (faces) => `${label} through ${facesWords(faces)}` };
  });
  const rows = entryRows(result, "electrode", [...held, ...fed].filter((entry) => entry.faces.length));
  return rows.length ? [{ id: "electrodes", label: "Electrodes", detail: "", glyph: "fixture", children: rows }] : [];
}

/**
 * Study's "Driven by": "Coil 2 A × 100 turns" per coil, the part it is wound on as its hint; at a frequency
 * "Coil 2 A at 50 kHz" (its turns in the hint), and a uniform field the air carries, "Field 10 mT at 500 Hz".
 */
export function coilRows(result) {
  const study = echo(result);
  const at = atFrequency(result);
  const rows = list(study.coils).map((coil, index) => {
    const amps = number(coil.A);
    const turns = number(coil.turns);
    const ampsWords = amps === null ? "" : ` ${plainNumber(amps)} A`;
    const turnsWords = turns === null ? "" : `${plainNumber(turns)} turns`;
    const whole = `Coil${ampsWords}${turnsWords ? ` × ${turnsWords}` : ""}${at}`;
    const label = at ? `Coil${ampsWords}${at}` : whole;
    const part = typeof coil.part === "string" && coil.part ? spaced(coil.part) : "";
    const wound = part ? `wound on ${part}` : "";
    // At a frequency the row has no room for the turns, so they lead the hint.
    const hint = at && turnsWords ? [turnsWords, wound].filter(Boolean).join(", ") : wound && `Wound on ${part}`;
    return { id: `coil:${index}`, label, detail: "", ...(hint ? { hint } : {}), summary: `${whole}${wound ? ` ${wound}` : ""}` };
  });
  const field = study.applied_field && typeof study.applied_field === "object" ? study.applied_field : null;
  if (field && at) {
    const mT = number(field.mT);
    const label = `Field${mT === null ? "" : ` ${plainNumber(mT)} mT`}${at}`;
    const axis = Array.isArray(field.direction) ? field.direction.map(Number) : [];
    const along = axis.length === 3 && axis.filter((c) => c !== 0).length === 1 ? ` along ${"xyz"[axis.findIndex((c) => c !== 0)]}` : "";
    rows.push({ id: "field", label, detail: "", summary: `A uniform${mT === null ? "" : ` ${plainNumber(mT)} mT`} field${along}${at}` });
  }
  return rows.length ? [{ id: "coils", label: "Driven by", detail: "", glyph: "wave", children: rows }] : [];
}

/** What leads the takeaway: "AC" for a field at a frequency, else the static word. */
export const electromagneticLimitWord = (result) => (frequencyOf(result) === null ? "Static" : "AC");

/** The Joule heat's way out (electro_thermal), as a thermal study's: kept at, cooled by air. */
function heatOutRows(result) {
  const block = echo(result).electro_thermal;
  if (!block || typeof block !== "object") return [];
  const study = {
    ...result.study,
    temperatures: list(block.temperatures).map((entry) => ({ faces: refs(entry.faces), celsius: number(entry.C) })),
    convection: list(block.convection).map((entry) => ({ faces: refs(entry.faces), h: number(entry.h_W_m2K), ambientC: number(entry.ambient_C) })),
  };
  const view = { ...result, study };
  return [...keptAtRows(view), ...cooledRows(view)];
}

export const ELECTROMAGNETIC_SETUP = Object.freeze([electrodeRows, coilRows, heatOutRows, heldRows, madeOfRows]);

/** The field select (every field it carries), and the deformation only when the force was mapped onto the structure. */
export function electromagneticControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  return result.fields.some((entry) => String(entry.attribute).toLowerCase() === "_displacement") ? [field, deformation] : [field];
}

export default planned({
  name: "electromagnetic", tier: 3, word: "Magnetic / electric", noun: "this voltage", limitWord: "Static", family: null,
  scalesWithLoad: false,
  checks: ["electric_field", "temperature", "stress", "displacement"],
  limitWordOf: electromagneticLimitWord,
  defaultControls: electromagneticControls,
  setupGroups: ELECTROMAGNETIC_SETUP,
  routine: () => null,
  markers: ["fixture"], displayTitle: "Electrodes and coils",
});
