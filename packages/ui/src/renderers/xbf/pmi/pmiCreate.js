import { pmiFreshId } from "@text-to-cad/core/lib/xbf/xbfPmi.js";
import { pmiDistanceAlong } from "@text-to-cad/core/lib/xbf/xbfPmiLayout.js";
import { english } from "../../../i18n/core.js";

// What a new annotation can be made of the faces Select has picked, as the supported subset has
// them: a datum on one flat or round face, a flatness on one flat face, a distance between two
// parallel flat faces, a basic (exact) distance between two of flat faces and holes, each hole by its
// axis, all parallel, a diameter or a position on one cylindrical face, a surface profile on any
// faces of one part; and what is of the part they are on (with none picked, the document's one
// part): a note (a flag note on the faces picked, a general one on none), its general profile while
// it has none, and a named view of it from where the viewport looks now. Each is the call it would
// be (`pmiCallText`'s input), its references the picked faces' canonical refs, of the part the first
// face is on, and its id and letter none of that part's annotations has (ids and letters are unique
// on a part; a view's name none of its views has); what a tolerance is, and a note's words, stay the
// person's to give -- nothing here fills one in. A distance's and a diameter's nominal here is the
// page's reading of the mesh, shown while the call is made: the engine measures the exact one when
// the model builds with it.

// ASME Y14.5 leaves I, O and Q out of datum letters: they read as 1, 0 and O.
const DATUM_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ".split("");
const PARALLEL = 1 - 1e-6;
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

/**
 * What two faces a basic dimension goes between measure, or null where they make none: two parallel
 * planes, a plane and an axis square to its normal (a hole's centre line), or two parallel axes
 * apart -- along what the layout draws it along (`pmiDistanceAlong`).
 */
function basicSeparation(a, b) {
  const planes = a.surface.type === "plane" && b.surface.type === "plane";
  const along = planes && Math.abs(dot(a.surface.normal, b.surface.normal)) < PARALLEL ? null : pmiDistanceAlong(a, b);
  return along ? Math.abs(dot(sub(b.surface.origin, a.surface.origin), along)) : null;
}

/** The letters of the datums of `part` (the structure's prototype) among `entries`, in their order. */
export function datumLetters(entries, part) {
  return entries.filter(entry => entry.kind === "datum" && entry.part === part && entry.datum?.letter).map(entry => entry.datum.letter);
}

/** The first datum letter none of `entries` (a part's) has, nor any new datum asked for on it (`pending` calls). */
export function nextDatumLetter(entries, pending = []) {
  const taken = new Set([...entries.filter(entry => entry.kind === "datum").map(entry => entry.datum?.letter),
    ...pending.filter(call => call.kind === "datum").map(call => call.letter)]);
  return DATUM_LETTERS.find(letter => !taken.has(letter)) || "";
}

/**
 * What a new annotation is called until it is built: its id; a datum, whose id is only its letter,
 * "datum B" (in the language of `t`); a view, its name.
 */
export const newPmiName = (call, t = english) => (call.kind === "datum" ? t("pmi.datumNamed", { letter: call.letter }) : call.kind === "view" ? call.name : call.id);

/**
 * The kinds a new annotation can be, in the order the menu lists them, each with whether the pick
 * makes one (`available`), what it needs when it does not (`need`), the part it is made on (`part`),
 * whether it stands on the faces picked (`onFaces`: what a face's menu offers) and the call it
 * starts as; a position or a profile with the datums it can refer to (`datums`, its part's). A
 * view's call is its name alone until it is seen from somewhere (`pmiViewFromHere`).
 *
 * @param {{ picked: Array<{ id: string, part: number | null, ref: string, surface: { type: string, normal?: number[], axis?: number[], origin?: number[], radius?: number } | null }>,
 *   entries: ReturnType<typeof import("@text-to-cad/core/lib/xbf/xbfPmi.js").readXbfPmi>["entries"], pending?: Array<{ part: number | null, call: object }>,
 *   parts?: readonly number[], views?: ReturnType<typeof import("@text-to-cad/core/lib/xbf/xbfPmi.js").readXbfPmi>["views"],
 *   moving?: boolean,
 *   t?: (key: string, values?: object) => string }} options
 *   `picked`: the faces Select has picked, each with its part (the structure's prototype), its
 *   canonical ref and its surface; anything else picked makes nothing. `pending`: the new
 *   annotations and views already asked for (each its part and its call), whose ids, letters and
 *   names are taken too. `parts`: the parts the document places, the one a pick of nothing is of
 *   where there is one. `views`: the document's (`readXbfPmi`'s). `moving`: the parts
 *   stand elsewhere than built (Explode, a pose), so no view of one is seen from here. Each `label` and
 *   `need` is said in the language of `t` (English unless the caller hands one over).
 */
export function pmiCreateOptions({ picked, entries, pending = [], parts = [], views = [], moving = false, t = english }) {
  const faces = picked.filter(item => item.surface && item.ref);
  const only = picked.length === faces.length;
  // What is of a part is of the faces' part, or, with nothing picked, of the document's one part.
  const part = faces[0]?.part ?? (!picked.length && parts.length === 1 ? parts[0] : null);
  const ofPart = only && part !== null && faces.every(face => face.part === part);
  const own = entries.filter(entry => entry.part === part);
  const asked = pending.filter(item => item.part === part).map(item => item.call);
  const ids = [...own.map(entry => entry.id), ...asked.filter(call => call.kind !== "view").map(call => call.id)];
  const refs = faces.map(face => face.ref);
  const named = ofPart ? [...views.filter(view => view.part === part).map(view => view.name), ...asked.filter(call => call.kind === "view").map(call => call.name)] : [];
  // One general profile a part: built, or asked for.
  const general = own.some(entry => entry.tolerance?.general === true) || asked.some(call => call.general === true);
  const needPart = faces.length ? t("pmi.need.partFaces") : t("pmi.need.partFace");
  const planes = only ? faces.filter(item => item.surface.type === "plane") : [];
  const cylinders = only ? faces.filter(item => item.surface.type === "cylinder") : [];
  const oneFlat = faces.length === 1 && planes.length === 1 ? planes[0] : null;
  const oneRound = faces.length === 1 && cylinders.length === 1 ? cylinders[0] : null;
  const pair = faces.length === 2 && planes.length === 2 ? planes : null;
  const ends = only && faces.length === 2 && planes.length + cylinders.length === 2 ? faces : null;
  const basic = ends ? basicSeparation(ends[0], ends[1]) : null;
  const parallel = pair && Math.abs(dot(pair[0].surface.normal, pair[1].surface.normal)) >= PARALLEL ? pair : null;
  const letter = nextDatumLetter(own, asked);
  const datums = datumLetters(own, part);
  // A datum feature is a plane or a cylinder (its axis), as the engine's datum takes one.
  const datumFace = oneFlat || oneRound;
  return [
    { kind: "datum", label: t("pmi.option.datum"), need: t("pmi.need.flatOrRound"), available: Boolean(datumFace && letter),
      call: datumFace ? { kind: "datum", id: letter, letter, ref: datumFace.ref } : null },
    { kind: "distance", label: t("pmi.option.distance"), need: t("pmi.need.parallelFlats"), available: Boolean(parallel),
      call: parallel ? { kind: "dimension", type: "distance", id: pmiFreshId("distance", ids), from: parallel[0].ref, to: parallel[1].ref, tolerance: null } : null,
      nominal: parallel ? Math.abs(dot(parallel[1].surface.origin.map((value, axis) => value - parallel[0].surface.origin[axis]), parallel[0].surface.normal)) : null },
    { kind: "basic", label: t("pmi.option.basic"), need: t("pmi.need.parallelFlatsOrHoles"), available: basic !== null,
      call: basic !== null ? { kind: "dimension", type: "distance", basic: true, id: pmiFreshId("basic", ids), from: ends[0].ref, to: ends[1].ref, tolerance: null } : null,
      nominal: basic },
    { kind: "diameter", label: t("pmi.option.diameter"), need: t("pmi.need.round"), available: Boolean(oneRound),
      call: oneRound ? { kind: "dimension", type: "diameter", id: pmiFreshId("diameter", ids), ref: oneRound.ref, tolerance: null } : null,
      nominal: oneRound ? 2 * oneRound.surface.radius : null },
    { kind: "flatness", label: t("pmi.option.flatness"), need: t("pmi.need.flat"), available: Boolean(oneFlat),
      call: oneFlat ? { kind: "geometric_tolerance", characteristic: "flatness", id: pmiFreshId("flatness", ids), ref: oneFlat.ref, value: null } : null },
    { kind: "position", label: t("pmi.option.position"), need: datums.length ? t("pmi.need.round") : t("pmi.need.roundAfterDatum"), available: Boolean(oneRound && datums.length),
      call: oneRound ? { kind: "geometric_tolerance", characteristic: "position", id: pmiFreshId("position", ids), ref: oneRound.ref, value: null,
        datums: datums.slice(0, 1), diameterZone: true } : null, datums },
    // A surface profile is on a face of any kind, or on several: one requirement on all of them.
    { kind: "profile", label: t("pmi.option.profile"), need: t("pmi.need.partFaces"), available: ofPart && faces.length > 0,
      call: ofPart && faces.length ? { kind: "geometric_tolerance", characteristic: "surface_profile", id: pmiFreshId("profile", ids), refs, value: null, datums: [] } : null,
      datums },
    // Of the part: a note on the faces picked or on none, its words the person's.
    { kind: "note", label: t("pmi.option.note"), need: needPart, available: ofPart, onFaces: ofPart && faces.length > 0,
      call: ofPart ? { kind: "note", id: pmiFreshId("note", ids), text: "", faces: refs } : null },
    { kind: "general_profile", label: t("pmi.option.general_profile"), need: ofPart && general ? t("pmi.need.hasGeneral") : needPart, available: ofPart && !general, onFaces: false,
      call: ofPart && !general ? { kind: "geometric_tolerance", characteristic: "surface_profile", general: true, id: pmiFreshId("general", ids), value: null, datums: [] } : null,
      datums },
    { kind: "view", label: t("pmi.option.view"), need: moving ? t("pmi.need.notMoving") : needPart, available: ofPart && !moving, onFaces: false,
      call: ofPart && !moving ? { kind: "view", name: pmiFreshId("view", named), camera: null, shows: null, section: null } : null, names: named },
  ].map(option => ({ onFaces: true, ...option, part }));
}

// Limits as a drawing writes them: two unsigned sizes, the least first, between an en dash, a
// hyphen or "to" ("10.00–10.05", the field's own text for them, `pmiToleranceText`). A hyphen
// spaced on one side alone is the second number's sign ("0.1 -0.05": deviations).
const UNSIGNED = String.raw`(\d+(?:\.\d*)?|\.\d+)`;
const LIMITS = new RegExp(String.raw`^${UNSIGNED}(?:\s*–\s*|-|\s+-\s+|\s+to\s+)${UNSIGNED}$`);

/**
 * A tolerance typed in: "±0.1", "0.1" (both ways), "+0.1/-0.05" or "+0.1 -0.05", deviations; or
 * limits, "10.00–10.05" (also "10.00-10.05" and "10.00 to 10.05"). "" is none, never a guess. An
 * `error` is said in the language of `t`.
 */
export function parseToleranceInput(text, t = english) {
  const value = String(text || "").trim().replaceAll("−", "-");
  if (!value) return { tolerance: null };
  const limits = value.match(LIMITS);
  if (limits) {
    const [lower, upper] = [Number(limits[1]), Number(limits[2])];
    // As `cadgen.ap242`'s `limits` holds them: a size above 0, then a greater one.
    if (!(lower > 0)) return { error: t("pmi.error.sizePositive") };
    return upper > lower ? { tolerance: { type: "limits", lower, upper } } : { error: t("pmi.error.limitsOrder") };
  }
  const numbers = value.replace(/^±/, "").split(/[\s/]+/).filter(Boolean).map(Number);
  if (!numbers.length || numbers.some(number => !Number.isFinite(number))) return { error: t("pmi.error.toleranceForm") };
  if (numbers.length === 1) return numbers[0] > 0 ? { tolerance: { type: "plus_minus", upper: numbers[0], lower: -numbers[0] } } : { error: t("pmi.error.tolerancePositive") };
  const [upper, lower] = numbers;
  if (numbers.length > 2 || upper <= lower) return { error: t("pmi.error.deviationOrder") };
  return { tolerance: { type: "plus_minus", upper, lower } };
}

// A feature control frame refers to a primary, a secondary and a tertiary datum, no more.
export const MAX_DATUMS = 3;

/**
 * A frame's datums with `letter` taken out, or put in last: in the order picked, primary first (the
 * order is what the frame means, never sorted), and never past three.
 */
export function toggleDatum(datums, letter) {
  if (datums.includes(letter)) return datums.filter(item => item !== letter);
  return datums.length >= MAX_DATUMS ? datums : [...datums, letter];
}
