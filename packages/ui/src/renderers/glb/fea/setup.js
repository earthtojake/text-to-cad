/**
 * Study's setup in plain words: the groups an analysis lists (`setupGroups`, ./analyses), each a
 * function of the result that gives its heading row, or none where the file records nothing for it,
 * and the words for faces and loads they and the Reference share. Pure: no three.js, no React.
 */
import { plainNumber } from "./numbers.js";

/** A face ref's own number ("#o1.1.f17": 17), or null for a ref that names no face. */
function faceNumber(ref) {
  const match = /\.f(\d+)$/.exec(String(ref || ""));
  return match ? Number(match[1]) : null;
}

/** A face as a person reads it: "Face 17"; the ref itself for one that names no face. */
export function faceLabel(ref) {
  const number = faceNumber(ref);
  return number === null ? String(ref || "") : `Face ${number}`;
}

/** A part's name as a person reads it, its underscores spaces so a long one wraps at words. */
export const spaced = (name) => String(name).replace(/_/g, " ");

/** Faces after a word: "face 17", "faces 17, 18". */
function facesWords(refs) {
  const names = refs.map((ref) => faceNumber(ref) ?? ref);
  return `${names.length === 1 ? "face" : "faces"} ${names.join(", ")}`;
}

const AXIS_NAMES = ["X", "Y", "Z"];

/**
 * Which way a force points, in words, in the part's CAD axes (Z up): "down", "up", "along +X"
 * for one along an axis, else "along (0.6, 0, −0.8)", its unit vector, with a true minus. "" for no force.
 */
export function forceDirection(force) {
  const length = Math.hypot(...force);
  if (!(length > 0)) return "";
  const unit = force.map((value) => value / length);
  const axis = unit.findIndex((value) => Math.abs(value) > 1 - 1e-6);
  if (axis === 2) return unit[2] < 0 ? "down" : "up";
  if (axis >= 0) return `along ${unit[axis] < 0 ? "−" : "+"}${AXIS_NAMES[axis]}`;
  return `along (${unit.map((value) => plainNumber(value).replace(/^-/, "−")).join(", ")})`;
}

/**
 * Which line something moves along, with no sign (a shake goes both ways): "Z", "X", else the unit
 * vector, "(0.6, 0, 0.8)". "" for none.
 */
export function axisWords(vector) {
  const size = Math.hypot(...vector);
  if (!(size > 0)) return "";
  const unit = vector.map((value) => value / size);
  const axis = unit.findIndex((value) => Math.abs(value) > 1 - 1e-6);
  if (axis >= 0) return AXIS_NAMES[axis];
  return `(${unit.map((value) => plainNumber(value).replace(/^-/, "−")).join(", ")})`;
}

/** A load as its row says it: what it is ("2500 N", "2 MPa pressure") and which way it points. */
export function loadWords(load) {
  if (load.vector) return { amount: `${plainNumber(Math.hypot(...load.vector))} N`, direction: forceDirection(load.vector), noun: "load" };
  if (load.pressure !== null) return { amount: `${plainNumber(load.pressure)} MPa pressure`, direction: "", noun: "" };
  return { amount: load.type || "load", direction: "", noun: "" };
}

/** What a load on these faces is called in a prompt: "2500 N load on face 22", "2 MPa pressure on faces 3, 4". */
function loadSummary(words, refs) {
  return `${[words.amount, words.noun].filter(Boolean).join(" ")} on ${facesWords(refs)}`;
}

const capitalised = (word) => word.charAt(0).toUpperCase() + word.slice(1);

/**
 * What a prompt calls one face, by everything the study does to it: "Fixed face 17", "2500 N load
 * on face 22", and for a face both fixed and loaded, "Fixed and loaded face 17". "" for a free face.
 */
export function faceSummary(study, ref) {
  const fixture = study.fixtures.find((entry) => entry.faces.includes(ref));
  const loads = study.loads.filter((entry) => entry.faces.includes(ref));
  if (fixture && loads.length) return `${capitalised(fixture.type)} and loaded ${facesWords([ref])}`;
  if (fixture) return `${capitalised(fixture.type)} ${facesWords([ref])}`;
  if (loads.length === 1) return loadSummary(loadWords(loads[0]), [ref]);
  return loads.length ? `Loaded ${facesWords([ref])}` : "";
}

/** The index into the result's `parts` of the part a face is on; -1 for a single part's face. */
export const facePartIndex = (result, ref) => result.parts.findIndex((entry) => entry.ref && String(ref).startsWith(`${entry.ref}.`));

/** A face's heading: "Face 17", and in an assembly "post · face 17", the part it is on (a long name's underscores spaced). */
export function faceTitle(result, ref) {
  const part = result.parts[facePartIndex(result, ref)];
  return part?.name ? `${spaced(part.name)} · ${faceLabel(ref).toLowerCase()}` : faceLabel(ref);
}

/** The whole result, for a prompt: its occurrence, else every part it holds. */
export const wholeRefs = (result) => (result.occurrence ? [result.occurrence] : result.parts.map((part) => part.ref).filter(Boolean));

/** Study's "Held at": one row per fixed face, its name alone ("Face 9", "base · face 9"), under the fixture glyph. */
export function heldRows(result) {
  const study = result.study;
  const fixed = study.fixtures.flatMap((fixture, index) => fixture.faces.map((ref) => ({
    id: `fixed:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], summary: faceSummary(study, ref), wrap: true,
  })));
  return fixed.length ? [{ id: "fixed", label: "Held at", detail: "", glyph: "fixture", children: fixed }] : [];
}

/**
 * Study's "Pushed": one row per load, how much and which way ("300 N along −X"), under the arrow
 * glyph, its faces under it by name alone, shut until opened (`collapsed`).
 */
export function pushedRows(result) {
  const study = result.study;
  const faceLoads = study.loads.filter((load) => load.faces.length).map((load, index) => {
    const words = loadWords(load);
    const label = [words.amount, words.direction].filter(Boolean).join(" ");
    return {
      id: `load:${index}`, label, detail: "", faces: load.faces,
      summary: loadSummary(words, load.faces), collapsed: true,
      children: load.faces.map((ref) => ({ id: `load:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], wrap: true,
        summary: study.fixtures.some((fixture) => fixture.faces.includes(ref)) ? faceSummary(study, ref) : loadSummary(words, [ref]) })),
    };
  });
  // A body load (gravity, an acceleration) acts on the whole part: chosen, it carries the whole result.
  const refs = wholeRefs(result);
  const bodyLoads = study.loads.filter((load) => !load.faces.length && load.g).map((load, index) => {
    const label = bodyLoadWords(load);
    const summary = load.type === "acceleration" ? `Accelerated ${label}` : `Its weight, ${label}`;
    return { id: `body:${index}`, label, detail: "", ...(load.type === "acceleration" ? { hint: "Accelerated: every part of it pushed the other way" } : {}),
      ...(refs.length ? { refs, summary } : {}) };
  });
  const loads = [...faceLoads, ...bodyLoads];
  return loads.length ? [{ id: "loads", label: "Pushed", detail: "", glyph: "load", children: loads }] : [];
}

/** A body load as its row says it: "1 g down", "5 g along +X". */
export const bodyLoadWords = (load) => `${plainNumber(Math.hypot(...load.g))} g ${forceDirection(load.g)}`.trim();

/**
 * A setup group of entries on faces, each a row with its faces under it, shut until opened, as
 * Pushed's loads are: `id` the group's, `label` its heading, `glyph` its marker, and for each entry
 * its row's `label`, its `summary` (what a prompt calls it on these faces) and an optional `hint`.
 */
function faceEntryGroup(result, { id, label, glyph, entries }) {
  const study = result.study;
  const rows = entries.map((entry, index) => ({ entry, index })).filter(({ entry }) => entry.faces.length).map(({ entry, index }) => {
    const words = entry.words;
    return {
      id: `${id}:${index}`, label: words.label, detail: "", faces: entry.faces, summary: words.summary(entry.faces), collapsed: true,
      ...(words.hint ? { hint: words.hint } : {}),
      children: entry.faces.map((ref) => ({ id: `${id}:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], wrap: true,
        summary: study.fixtures.some((fixture) => fixture.faces.includes(ref)) ? faceSummary(study, ref) : words.summary([ref]) })),
    };
  });
  return rows.length ? [{ id, label, detail: "", glyph, children: rows }] : [];
}

/** Study's "Kept at", under a thermometer: each fixed temperature ("25 °C"), its faces under it. */
export function keptAtRows(result) {
  return faceEntryGroup(result, { id: "temperature", label: "Kept at", glyph: "temperature", entries: (result.study.temperatures || []).map((entry) => {
    const degrees = entry.celsius === null ? "a fixed temperature" : `${plainNumber(entry.celsius)} °C`;
    return { faces: entry.faces, words: { label: degrees, summary: (refs) => `Kept at ${degrees} on ${facesWords(refs)}` } };
  }) });
}

/** Study's "Heated", under a flame: each heat input ("15 W", "2000 W/m²"), its faces under it. */
export function heatedRows(result) {
  return faceEntryGroup(result, { id: "heat", label: "Heated", glyph: "heat", entries: (result.study.heat || []).map((entry) => {
    const amount = entry.watts !== null ? `${plainNumber(entry.watts)} W` : entry.fluxWm2 !== null ? `${plainNumber(entry.fluxWm2)} W/m²` : "heat";
    return { faces: entry.faces, words: { label: amount, summary: (refs) => `${amount} of heat into ${facesWords(refs)}` } };
  }) });
}

/** Study's "Cooled by air", under the wind: each convection ("Air at 25 °C", how well it cools its hint), its faces under it. */
export function cooledRows(result) {
  return faceEntryGroup(result, { id: "convection", label: "Cooled by air", glyph: "convection", entries: (result.study.convection || []).map((entry) => {
    const air = entry.ambientC === null ? "Air" : `Air at ${plainNumber(entry.ambientC)} °C`;
    const how = entry.h === null ? "" : `${plainNumber(entry.h)} W/m²K`;
    return { faces: entry.faces, words: { label: air, hint: how ? `Heat transfer coefficient ${how}` : "",
      summary: (refs) => `Cooled by a${air.slice(1)}${how ? ` (${how})` : ""} on ${facesWords(refs)}` } };
  }) });
}

/** Study's "Shaken", under a wave: the shaker on the fixtures ("1 g along Z", "At random along Z"), chosen with every fixed face. */
export function shakenRows(result) {
  const study = result.study;
  const shake = study.excitation;
  if (!shake?.kind || shake.kind === "force") return [];
  const along = shake.direction ? ` along ${axisWords(shake.direction)}` : "";
  const label = shake.kind === "psd" ? `At random${along}` : shake.kind === "srs" ? `A shock${along}` : `${shake.amplitudeG === null ? "Shaken" : `${plainNumber(shake.amplitudeG)} g`}${along}`;
  const faces = study.fixtures.flatMap((fixture) => fixture.faces);
  const refs = faces.length ? { faces } : wholeRefs(result).length ? { refs: wholeRefs(result) } : null;
  return [{ id: "shaken", label: "Shaken", detail: "", glyph: "wave", children: [{ id: "shaken:0", label, detail: "", wrap: true,
    ...(refs ? { ...refs, summary: `Shaken where it is held: ${label.charAt(0).toLowerCase()}${label.slice(1)}` } : {}) }] }];
}

/** Study's "Dropped", under a drop: its height ("1 m drop"), how it stops its hint, the faces that land under it. */
export function droppedRows(result) {
  const drop = result.study.drop;
  if (!drop) return [];
  const height = drop.heightMm === null ? "Dropped" : drop.heightMm >= 1000 ? `${plainNumber(drop.heightMm / 1000)} m drop` : `${plainNumber(drop.heightMm)} mm drop`;
  const stop = drop.stopMm !== null ? `stopping in ${plainNumber(drop.stopMm)} mm` : drop.impactMs !== null ? `stopping in ${plainNumber(drop.impactMs)} ms` : "";
  const hint = [stop, drop.floor === "rigid" ? "onto a rigid floor" : ""].filter(Boolean).join(", ");
  const entry = { faces: drop.onto, words: { label: height, ...(hint ? { hint } : {}), summary: (refs) => `${height}${stop ? `, ${stop}` : ""}, landing on ${facesWords(refs)}` } };
  if (drop.onto.length) return faceEntryGroup(result, { id: "drop", label: "Dropped", glyph: "drop", entries: [entry] });
  const refs = wholeRefs(result);
  return [{ id: "drop", label: "Dropped", detail: "", glyph: "drop", children: [{ id: "drop:0", label: height, detail: "", ...(hint ? { hint } : {}),
    ...(refs.length ? { refs, summary: `${height}${stop ? `, ${stop}` : ""}` } : {}) }] }];
}

const SIDE_WORDS = Object.freeze({ min: "low", max: "high" });
/** An opening in words: "the low X side". */
const openingWords = (opening) => {
  const match = /^([xyz])_(min|max)$/.exec(String(opening || ""));
  return match ? `the ${SIDE_WORDS[match[2]]} ${match[1].toUpperCase()} side` : "";
};

/** Study's "Flow in/out", under the flow: each inlet ("In 0.5 m/s at the low X side") and outlet ("Out at 0 Pa"), chosen with the whole part. */
export function flowRows(result) {
  const flow = result.study.flow;
  if (!flow) return [];
  const refs = wholeRefs(result);
  const row = (id, label) => ({ id, label, detail: "", wrap: true, ...(refs.length ? { refs, summary: `Flow ${label.charAt(0).toLowerCase()}${label.slice(1)}` } : {}) });
  const rows = [
    ...flow.inlets.map((inlet, index) => {
      const speed = inlet.speed === null ? "" : ` ${plainNumber(inlet.speed)} m/s`;
      const where = inlet.opening ? ` at ${openingWords(inlet.opening) || inlet.opening}` : inlet.velocity ? ` ${forceDirection(inlet.velocity)}` : "";
      return row(`inlet:${index}`, `In${speed}${where}`);
    }),
    ...flow.outlets.map((outlet, index) => row(`outlet:${index}`,
      `Out${outlet.pressure === null ? "" : ` at ${plainNumber(outlet.pressure)} Pa`}${outlet.opening ? `, ${openingWords(outlet.opening) || outlet.opening}` : ""}`)),
  ];
  return rows.length ? [{ id: "flow", label: "Flow in/out", detail: "", glyph: "flow", children: rows }] : [];
}

/** Study's "Rigid floor", under a plane: each rigid plane, which way it faces, chosen with the whole part. */
export function rigidFloorRows(result) {
  const study = result.study;
  const refs = wholeRefs(result);
  const planes = [...(study.rigidPlanes || []).map((plane) => `Facing ${forceDirection(plane.normal)}`),
    ...(study.drop?.floor === "rigid" ? ["Under the drop"] : [])];
  if (!planes.length) return [];
  return [{ id: "rigid", label: "Rigid floor", detail: "", glyph: "plane", children: planes.map((label, index) => ({ id: `rigid:${index}`, label, detail: "",
    ...(refs.length ? { refs, summary: `A rigid floor, ${label.charAt(0).toLowerCase()}${label.slice(1)}` } : {}) })) }];
}

/** Every setup group an analysis can show, in Study's order: each is [] where the study records nothing for it. */
export const SETUP_GROUPS = Object.freeze([heldRows, keptAtRows, pushedRows, heatedRows, cooledRows, shakenRows, droppedRows, flowRows, rigidFloorRows, madeOfRows]);

/**
 * Study's "Made of", under a swatch: the material's name ("Aluminum 6061-T6"). In an assembly whose
 * parts differ, "Mostly Aluminum 6061-T6" where one material has most of the parts, else
 * "2 materials", each part's own in its hint (and in Parts and a picked face's Reference).
 */
export function madeOfRows(result) {
  const fallback = result.study.material?.name || "";
  const each = result.parts.map((part) => part.material || fallback).filter(Boolean);
  const counts = new Map();
  for (const name of each) counts.set(name, (counts.get(name) || 0) + 1);
  let label = fallback;
  let hint = "";
  if (counts.size === 1) label = each[0];
  else if (counts.size > 1) {
    const [top, count] = [...counts].sort((a, b) => b[1] - a[1])[0];
    label = count * 2 > each.length ? `Mostly ${top}` : `${counts.size} materials`;
    hint = [...counts].map(([name, n]) => `${name}: ${n} ${n === 1 ? "part" : "parts"}`).join(", ");
  }
  if (!label) return [];
  // Chosen, it carries the whole result into a prompt, each material with the parts made of it.
  const refs = result.parts.length ? result.parts.map((part) => part.ref).filter(Boolean) : wholeRefs(result);
  const yieldMPa = result.study.material?.yieldMPa;
  const byMaterial = new Map();
  for (const part of result.parts) {
    const name = part.material || fallback;
    if (name) byMaterial.set(name, [...(byMaterial.get(name) || []), spaced(part.name || part.ref)]);
  }
  const summary = byMaterial.size > 1
    ? `Made of ${[...byMaterial].map(([name, names]) => `${name} (${names.join(", ")})`).join(" and ")}`
    : `Made of ${counts.size === 1 ? each[0] : label}${counts.size <= 1 && yieldMPa !== null && yieldMPa !== undefined ? ` (yield ${plainNumber(yieldMPa)} MPa)` : ""}`;
  return [{ id: "material", label: "Made of", detail: "", glyph: "material", children: [{ id: "material:name", label, detail: "", wrap: true,
    ...(hint ? { hint } : {}), ...(refs.length ? { refs, summary } : {}) }] }];
}

/** Details, shut until opened: the mesh, "3.7 mm elements", how it got there its hint ("refined from 2.8 mm", "not refined"). */
export function detailRows(result) {
  const mesh = result.study.mesh;
  if (mesh?.sizeMm === null || mesh?.sizeMm === undefined) return [];
  const refined = mesh.refinedFromMm === null ? "not refined" : `refined from ${plainNumber(mesh.refinedFromMm)} mm`;
  // Chosen, it carries the whole result into a prompt with how fine the mesh is.
  const refs = wholeRefs(result);
  return [{ id: "details", label: "Details", detail: "", collapsed: true,
    children: [{ id: "mesh", label: "Mesh", detail: `${plainNumber(mesh.sizeMm)} mm elements`, hint: refined,
      ...(refs.length ? { refs, summary: `Mesh of ${plainNumber(mesh.sizeMm)} mm elements, ${refined}` } : {}) }] }];
}
