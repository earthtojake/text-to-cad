/**
 * Study's setup in plain words: its groups (`SETUP_GROUPS`), each a function of the result that gives
 * its heading row, or none where the file records nothing for it, and the words for faces and loads
 * they and the Reference share. Pure: no three.js, no React.
 */
import { plainNumber } from "./numbers.js";
import { english } from "../../../i18n/core.js";

/** A face ref's own number ("bracket/face 17": 17), or null for a ref that names no face by its number. */
function faceNumber(ref) {
  const match = /(?:^|\/)face (\d+)$/.exec(String(ref || ""));
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
export function facesWords(refs) {
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

/** Whether a fixture is a roller: its face may slide in its own plane but not move off it. A fixed one holds it. */
export const isRoller = (fixture) => fixture.type === "roller";

/**
 * What a prompt calls one face, by everything the study does to it: "Fixed face 17", "Slides on
 * face 3", "2500 N load on face 22", and for a face both held and loaded, "Fixed and loaded face 17"
 * ("Sliding and loaded face 3"). "" for a free face.
 */
export function faceSummary(study, ref) {
  const fixture = study.fixtures.find((entry) => entry.faces.includes(ref));
  const loads = study.loads.filter((entry) => entry.faces.includes(ref));
  const roller = fixture && isRoller(fixture);
  if (fixture && loads.length) return `${roller ? "Sliding" : capitalised(fixture.type)} and loaded ${facesWords([ref])}`;
  if (fixture) return roller ? `Slides on ${facesWords([ref])}` : `${capitalised(fixture.type)} ${facesWords([ref])}`;
  if (loads.length === 1) return loadSummary(loadWords(loads[0]), [ref]);
  return loads.length ? `Loaded ${facesWords([ref])}` : "";
}

/** The index into the result's `parts` of the part a face is on; -1 for a single part's face. */
export const facePartIndex = (result, ref) => result.parts.findIndex((entry) => entry.ref && String(ref).startsWith(`${entry.ref}/`));

/** A face's heading: "Face 17", and in an assembly "post · face 17", the part it is on (a long name's underscores spaced). */
export function faceTitle(result, ref) {
  const part = result.parts[facePartIndex(result, ref)];
  return part?.name ? `${spaced(part.name)} · ${faceLabel(ref).toLowerCase()}` : faceLabel(ref);
}

/** The whole result, for a prompt: its occurrence, else every part it holds. */
export const wholeRefs = (result) => (result.occurrence ? [result.occurrence] : result.parts.map((part) => part.ref).filter(Boolean));

/** A setup group: its heading row over these rows, or none where there are no rows. */
export const group = (id, label, glyph, rows) => (rows.length ? [{ id, label, detail: "", glyph, children: rows }] : []);

/**
 * Study's "Held at": one row per fixed face, its name alone ("Face 9", "base · face 9"), under the
 * fixture glyph; then, right after it, "Slides on" (`slidesOnRows`).
 */
export function heldRows(result) {
  const study = result.study;
  const fixed = study.fixtures.flatMap((fixture, index) => (isRoller(fixture) ? [] : fixture.faces.map((ref) => ({
    id: `fixed:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], summary: faceSummary(study, ref), wrap: true,
  }))));
  return [...group("fixed", "Held at", "fixture", fixed), ...slidesOnRows(result)];
}

/**
 * Study's "Slides on", under the roller glyph: one row per face of a roller fixture (a frictionless
 * sliding support), its name alone, the hint saying what that means. Its rows number their fixture
 * as Held at's do (`roller:<fixture>:<ref>`), so a row chooses its own markers.
 */
export function slidesOnRows(result, t = english) {
  const study = result.study;
  const rows = study.fixtures.flatMap((fixture, index) => (isRoller(fixture) ? fixture.faces.map((ref) => ({
    id: `roller:${index}:${ref}`, label: faceTitle(result, ref), detail: "", faces: [ref], summary: faceSummary(study, ref), wrap: true,
    hint: t("fea.slideHint"),
  })) : []));
  return group("roller", "Slides on", "roller", rows);
}

/**
 * Study's "Pushed": one row per load, how much and which way ("300 N along −X"), under the arrow
 * glyph, its faces under it by name alone, shut until opened (`collapsed`).
 */
export function pushedRows(result, t = english) {
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
    return { id: `body:${index}`, label, detail: "", ...(load.type === "acceleration" ? { hint: t("fea.acceleratedHint") } : {}),
      ...(refs.length ? { refs, summary } : {}) };
  });
  return group("loads", "Pushed", "load", [...faceLoads, ...bodyLoads]);
}

/** A body load as its row says it: "1 g down", "5 g along +X". */
export const bodyLoadWords = (load) => `${plainNumber(Math.hypot(...load.g))} g ${forceDirection(load.g)}`.trim();

/** Study's setup groups, in its order: each is [] where the study records nothing for it. */
export const SETUP_GROUPS = Object.freeze([heldRows, pushedRows, madeOfRows]);

/**
 * Study's "Made of", under a swatch: the material's name ("Aluminum 6061-T6"). In an assembly whose
 * parts differ in two or three materials, each with its parts inline ("Copper C110 coil, Steel
 * plunger"; a material of three parts or more says how many: "Steel (4 parts)"); past three,
 * "Mostly Aluminum 6061-T6" where one material has most of the parts, else "5 materials", each
 * part's own in its hint (and in Parts and a picked face's Reference).
 */
/** The most materials Made of names inline, each with its parts; past it, a count and a hint. */
const INLINE_MATERIALS = 3;

export function madeOfRows(result, t = english) {
  const fallback = result.study.material?.name || "";
  const each = result.parts.map((part) => part.material || fallback).filter(Boolean);
  const counts = new Map();
  for (const name of each) counts.set(name, (counts.get(name) || 0) + 1);
  // Each material with the parts made of it, in the parts' order.
  const byMaterial = new Map();
  for (const part of result.parts) {
    const name = part.material || fallback;
    if (name) byMaterial.set(name, [...(byMaterial.get(name) || []), spaced(part.name || part.ref)]);
  }
  let label = fallback;
  let hint = "";
  if (counts.size === 1) label = each[0];
  else if (counts.size > 1 && counts.size <= INLINE_MATERIALS) {
    label = [...byMaterial].map(([name, names]) => (names.length < 3 ? `${name} ${names.join(" and ")}` : `${name} (${names.length} parts)`)).join(", ");
  } else if (counts.size > 1) {
    const [top, count] = [...counts].sort((a, b) => b[1] - a[1])[0];
    label = count * 2 > each.length ? `Mostly ${top}` : `${counts.size} materials`;
    hint = [...counts].map(([name, n]) => `${name}: ${n} ${n === 1 ? "part" : "parts"}`).join(", ");
  }
  if (!label) return [];
  // Chosen, it carries the whole result into a prompt, each material with the parts made of it.
  const refs = result.parts.length ? result.parts.map((part) => part.ref).filter(Boolean) : wholeRefs(result);
  const yieldMPa = result.study.material?.yieldMPa;
  const summary = byMaterial.size > 1
    ? `Made of ${[...byMaterial].map(([name, names]) => `${name} (${names.join(", ")})`).join(" and ")}`
    : `Made of ${counts.size === 1 ? each[0] : label}${counts.size <= 1 && yieldMPa !== null && yieldMPa !== undefined ? ` (yield ${plainNumber(yieldMPa)} MPa)` : ""}`;
  return [{ id: "material", label: t("fea.madeOf"), detail: "", glyph: "material", children: [{ id: "material:name", label, detail: "", wrap: true,
    ...(hint ? { hint } : {}), ...(refs.length ? { refs, summary } : {}) }] }];
}

/** Details, shut until opened: the mesh, "3.7 mm elements", how it got there its hint ("refined from 2.8 mm", "not refined"). */
export function detailRows(result, t = english) {
  const mesh = result.study.mesh;
  if (mesh?.sizeMm === null || mesh?.sizeMm === undefined) return [];
  const refined = mesh.refinedFromMm === null ? "not refined" : `refined from ${plainNumber(mesh.refinedFromMm)} mm`;
  // Chosen, it carries the whole result into a prompt with how fine the mesh is.
  const refs = wholeRefs(result);
  return [{ id: "details", label: t("fea.details"), detail: "", collapsed: true,
    children: [{ id: "mesh", label: t("fea.mesh"), detail: `${plainNumber(mesh.sizeMm)} mm elements`, hint: refined,
      ...(refs.length ? { refs, summary: t("fea.meshSummary", { size: plainNumber(mesh.sizeMm), refined }) } : {}) }] }];
}
