/**
 * Sound (lite), Tier 3: linear acoustics in air or another fluid. Its result is the air's natural
 * frequencies (`solve: "modes"`, a series of modes: `Mode 2 · 903 Hz`, each its pressure shape,
 * signed, scaled to a largest of 1) or a driven response (a series of frequencies: the sound
 * pressure level in dB and the pressure amplitude in Pa per frame), on the part's surface: the air
 * the part is (`domain: "part"`), the air closed inside it, or the air around it out to an absorbing
 * box. Its verdict judges the sound level against a limit in dB ("Too loud"), or an acoustic mode's
 * frequency; no load control moves them. Its takeaway leads with "Linear · ". What you see opens on
 * the mode picker or the Frequency scrubber, then the field; its routine for modes is Ring (the
 * mode's pressure swinging through its cycle, its colours turning over). Its setup says where the
 * air is ("Air inside"), what makes the sound ("Speaker face 1 mm/s", a point source, or the part's
 * own vibration from a harmonic study, held and shaken as that one is), what soaks it up, which faces
 * are open, where it is listened to, and (driven by a vibration) what the part is made of.
 */
import { seriesControls } from "../controls.js";
import { plainNumber, threeFigures } from "../numbers.js";
import { faceTitle, heldRows, madeOfRows, wholeRefs } from "../setup.js";
import { shakenSweepRows } from "./harmonic.js";
import { planned, routineOf } from "./stub.js";

/** Ring: a one-second loop of the chosen mode's pressure, its colours swinging through the cycle (cos 2πt). */
export const RING = routineOf("Ring", "pulse");

/** The acoustic study as the viewer read it (`readStudy`), or {} for a file that records none. */
const acousticOf = (result) => result?.study?.acoustic || {};
const list = (value) => (Array.isArray(value) ? value : []);

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

/** A row about the whole part (no faces of its own), chosen with the whole part. */
function wholeRow(result, id, label, summary, hint = "") {
  const refs = wholeRefs(result);
  return { id, label, detail: "", wrap: true, ...(hint ? { hint } : {}), ...(refs.length ? { refs, summary } : {}) };
}

/** A fluid's name as a row starts with it: "Air", "Water", "Oil". */
const fluidWord = (fluid) => {
  const name = String(fluid?.name || "air");
  return name.charAt(0).toUpperCase() + name.slice(1);
};

/** Where the air is, in a row's words: "Air inside", "Air around it", "Air filling it". */
export function airWords(acoustic) {
  const fluid = fluidWord(acoustic.fluid);
  if (acoustic.domain === "inside") return `${fluid} inside`;
  if (acoustic.domain === "outside") return `${fluid} around it`;
  return `${fluid} filling it`;
}

/** Study's "Air": where the sound travels, its speed the hint (and, around the part, that open air ends at an absorbing box). */
export function airRows(result) {
  const acoustic = acousticOf(result);
  if (!acoustic.domain) return [];
  const label = airWords(acoustic);
  const speed = Number.isFinite(acoustic.fluid?.speedMS) ? `Sound at ${plainNumber(acoustic.fluid.speedMS)} m/s` : "";
  const open = acoustic.domain === "outside" ? "open air ends at an absorbing box" : "";
  const hint = [speed, open].filter(Boolean).join("; ");
  const summary = `${label}${acoustic.domain === "part" ? ": the part's solid is the air the sound travels in" : ""}`;
  return [{ id: "air", label: "Air", detail: "", glyph: "flow", children: [wholeRow(result, "air:0", label, summary, hint)] }];
}

/** A volume velocity in words: "1 cm³/s", "250 mm³/s". */
function volumeWords(m3s) {
  const cm3 = m3s * 1e6;
  return cm3 >= 1 ? `${threeFigures(cm3)} cm³/s` : `${threeFigures(m3s * 1e9)} mm³/s`;
}

/** Study's "Sound from": each speaker face ("Speaker face 1 mm/s"), point source, or the part's own vibration (from a harmonic study). */
export function sourceRows(result) {
  const acoustic = acousticOf(result);
  const faces = list(acoustic.sources).filter((source) => source.faces?.length).map((source) => {
    const speed = source.velocityMmS === null ? "" : ` ${plainNumber(source.velocityMmS)} mm/s`;
    const label = `Speaker face${speed}`;
    return { faces: source.faces, label, hint: "Moving in and out of the air at every frequency",
      summary: (refs) => `A speaker on ${facesWords(refs)}, moving${speed || " in and out"}` };
  });
  const rows = entryRows(result, "source", faces);
  list(acoustic.sources).filter((source) => source.point).forEach((source, index) => {
    const amount = Number.isFinite(source.volumeVelocity) ? ` ${volumeWords(source.volumeVelocity)}` : "";
    const at = `at (${source.point.map(plainNumber).join(", ")}) mm`;
    rows.push(wholeRow(result, `point:${index}`, `Point source${amount}`, `A point source${amount} ${at}`, at));
  });
  if (acoustic.from === "harmonic") {
    rows.push(wholeRow(result, "vibration", "Its own vibration", "The part's vibrating surface, from the harmonic shake",
      "The shake below moves the surface; the air does not push back"));
  }
  return rows.length ? [{ id: "sources", label: "Sound from", detail: "", glyph: "wave", children: rows }] : [];
}

/** Study's "Soaks up": each absorbing face ("Absorbs 30%", "Impedance 800 rayl"), and each open face ("Open"), its faces under it. */
export function absorberRows(result) {
  const acoustic = acousticOf(result);
  const absorbers = list(acoustic.absorbers).map((entry) => {
    const label = Number.isFinite(entry.absorption) ? `Absorbs ${plainNumber(entry.absorption * 100)}%`
      : Number.isFinite(entry.impedanceRayl) ? `Impedance ${plainNumber(entry.impedanceRayl)} rayl` : "Absorbs";
    return { faces: entry.faces, label, summary: (refs) => `${label} of the sound striking ${facesWords(refs)}` };
  });
  const open = list(acoustic.open).filter((faces) => faces.length).map((faces) => ({
    faces, label: "Open", hint: "Open to the air: no sound pressure there",
    summary: (refs) => `Open to the air at ${facesWords(refs)}`,
  }));
  const rows = entryRows(result, "absorber", [...absorbers, ...open]);
  return rows.length ? [{ id: "absorbers", label: "Soaks up", detail: "", glyph: "plane", children: rows }] : [];
}

/** Study's "Listening at": each probe by its label, where it is its hint. */
export function probeRows(result) {
  const probes = list(acousticOf(result).probes);
  if (!probes.length) return [];
  const rows = probes.map((probe, index) => {
    const at = `(${probe.at.map(plainNumber).join(", ")}) mm`;
    return wholeRow(result, `probe:${index}`, probe.label, `Listening at '${probe.label}', ${at}`, at);
  });
  return [{ id: "probes", label: "Listening at", detail: "", glyph: "wave", children: rows }];
}

/** A vibration-driven study is held, shaken and made of something as its harmonic is; a study of air alone is none of these. */
const fromVibration = (group) => (result) => (acousticOf(result).from === "harmonic" ? group(result) : []);

export const ACOUSTIC_SETUP = Object.freeze([
  airRows, sourceRows, absorberRows, probeRows, fromVibration(heldRows), fromVibration(shakenSweepRows), fromVibration(madeOfRows),
]);

export default planned({
  name: "acoustic", tier: 3, word: "Sound", noun: "this sound", limitWord: "Linear", family: null, scalesWithLoad: false,
  checks: ["sound_level", "frequency"],
  checkLabels: { frequency: "Resonance" },
  defaultControls: seriesControls,
  setupGroups: ACOUSTIC_SETUP,
  routine: (result) => (result?.series?.kind === "mode" ? RING : null),
  markers: ["fixture", "base_excitation", "speaker"], displayTitle: "Fixtures and speakers",
});
