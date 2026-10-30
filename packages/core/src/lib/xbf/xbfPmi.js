// An engine document's PMI -- its manufacturing annotations: dimensions with their tolerances,
// datum features, geometric tolerances and numbered notes, with each part's named views and
// coverage -- as the page reads them from the document the engine serves
// (`structure.pmi`, `pmi_views` and `pmi_coverage`, the document's XCAF GD&T,
// notes and views read by `cadgen.engine.pmi`), and as the viewer says them and asks for them.
//
// What is said comes from the document alone: a dimension's nominal is the engine's, measured on
// the geometry; a tolerance is what the model's code supplied (deviations from the nominal, or its
// limits: the least size and the greatest), and none where it supplied none -- the viewer never
// fills one in. A basic dimension (`dimensional_location(..., basic=True)`: theoretically exact, as a
// position tolerance's true position is located) is a distance that holds no tolerance at all, drawn boxed. A part's
// general profile ("unless otherwise noted, all surfaces") is its Note 1, then its notes in their
// numbers: a general note and the general profile are said in the notes, a flag note drawn on its
// faces. Where an annotation stands on screen (`presentation`) is no part of what it means: moving
// it changes how it is drawn, never what it says.
//
// An id is the author's and unique on its part (a datum's is its letter), so an annotation is known
// by its part and its id (`key`), and asked for by both; a view by its part and its name.
//
// The document is made from code (`annotate(body, datum("A", ...), ...)` in the model, each call
// `cadgen.ap242`'s, named after the AP242 entity it writes), so a change asked for in the viewer is
// the call it would write there (`pmiCallText`, `pmiPlaceText`): what Quick Edit hands the agent,
// which writes it into the model and builds.

/** The kinds the viewer reads and says; any other an entry names is told, not drawn. */
const PMI_KINDS = Object.freeze(["dimension", "datum", "geometric_tolerance", "note"]);
/** The dimension types the viewer draws. */
const PMI_DIMENSION_TYPES = Object.freeze(["distance", "diameter"]);
/** The geometric characteristics the viewer draws. */
const PMI_CHARACTERISTICS = Object.freeze(["flatness", "position", "surface_profile"]);
/** The axes a view's section (the Clip's plane) is across. */
const SECTION_AXES = Object.freeze(["x", "y", "z"]);
/**
 * What a reference's or an annotation's status may be, best first: it names one face it can
 * stand on; several; nothing; or a face it cannot stand on (a diameter on a plane, say).
 */
const PMI_STATUSES = Object.freeze(["ok", "ambiguous", "missing", "invalid"]);

const MINUS = "−";
const EN_DASH = "–";
const finite = value => (typeof value === "number" && Number.isFinite(value) ? value : null);
const text = value => (typeof value === "string" ? value : "");
const point3 = value => (Array.isArray(value) && value.length === 3 && value.every(item => finite(item) !== null) ? value.slice() : null);
const statusOf = value => (PMI_STATUSES.includes(value) ? value : "missing");
const partOf = value => (Number.isInteger(value) ? value : null);
const isRecord = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const words = value => (Array.isArray(value) ? value.map(text).filter(Boolean) : []);
// A presentation (`{ anchor, offset }`, as `place` writes it), or null.
const readPlacement = value => (value && point3(value.anchor) && point3(value.offset) ? { anchor: point3(value.anchor), offset: point3(value.offset) } : null);

function readRefs(refs) {
  return (Array.isArray(refs) ? refs : []).map((ref) => {
    const written = text(ref?.written) || text(ref?.ref);
    return { role: text(ref?.role) || "feature", ref: text(ref?.ref) || written, written, status: statusOf(ref?.status),
      candidates: Array.isArray(ref?.candidates) ? ref.candidates.map(text).filter(Boolean) : [] };
  });
}

// An unsupported entry's values, as far as they read as words: each number, word or list of them.
function readValues(values) {
  const plain = value => (typeof value === "number" && Number.isFinite(value)) || (typeof value === "string" && value);
  return Object.entries(values).flatMap(([key, value]) => (plain(value) ? [[key, String(value)]]
    : Array.isArray(value) && value.length && value.every(plain) ? [[key, value.join(", ")]] : []));
}

// A plus-minus tolerance (signed deviations from the nominal) or limits (the least size and the
// greatest, absolute), or null.
function readTolerance(value) {
  if (!value || (value.type !== "plus_minus" && value.type !== "limits")) return null;
  const upper = finite(value.upper), lower = finite(value.lower);
  return upper === null || lower === null ? null : { type: value.type, upper, lower };
}

// A note's number (the engine's: Note 1 is its part's general profile where it has one), its words,
// whether it is general (it names no face and no annotation) and the ids of the annotations it names.
function readNote(value) {
  if (!isRecord(value)) return null;
  return { number: Number.isInteger(value.number) && value.number > 0 ? value.number : null, text: text(value.text),
    general: value.general === true, annotations: words(value.annotations) };
}

/**
 * Why an entry the document holds is not one the viewer draws, or "" for one it draws: an unknown
 * kind, a dimension of a type it does not draw, a characteristic it does not draw, or the values
 * its kind needs missing. Where the engine says why (an `unsupported` entry's `reason`), its words
 * are said instead (`readXbfPmi`).
 */
function unsupportedReason(entry) {
  if (entry.kind === "unsupported") return entry.xcafType ? `${entry.xcafType} is not one the viewer draws` : "not one the viewer draws";
  if (!PMI_KINDS.includes(entry.kind)) return `${entry.kind || "an annotation"} is not one the viewer draws`;
  if (entry.kind === "dimension") {
    if (!PMI_DIMENSION_TYPES.includes(entry.dimension?.type)) return `a ${entry.dimension?.type || "dimension"} dimension is not one the viewer draws`;
    if (entry.dimension.basic && entry.dimension.type !== "distance") return `a basic ${entry.dimension.type} is not one the viewer draws`;
    // A broken reference leaves nothing to measure: no nominal, said as unknown. One that resolved
    // has one, but where its limits say its sizes, which need none (a file states limits alone).
    if (entry.dimension.nominal === null && entry.status === "ok" && entry.dimension.tolerance?.type !== "limits") return "it has no nominal";
  }
  if (entry.kind === "datum" && !entry.datum?.letter) return "it has no letter";
  if (entry.kind === "geometric_tolerance") {
    if (!PMI_CHARACTERISTICS.includes(entry.tolerance?.characteristic)) return `${entry.tolerance?.characteristic || "this characteristic"} is not one the viewer draws`;
    if (entry.tolerance.value === null) return "it has no tolerance value";
    if (entry.tolerance.general && entry.tolerance.characteristic !== "surface_profile") return `a general ${entry.tolerance.characteristic} is not one the viewer draws`;
  }
  if (entry.kind === "note") {
    if (!entry.note?.text.trim()) return "it has no text";
    if (entry.note.number === null) return "it has no number";
  }
  return "";
}

/** What an annotation is known by in its document: its part (`part`, the structure's prototype) and its id. */
export const pmiKey = (part, id) => `${part ?? ""}:${id}`;

// Each item of a served list keyed by its part and its name (`pmiKey`): one the document lacks a
// name for, or repeats on a part, is kept apart by its place.
function keyedByPart(list, nameOf, read) {
  const seen = new Set();
  return (Array.isArray(list) ? list : []).filter(isRecord).map((item, index) => {
    const part = partOf(item.part);
    const name = nameOf(item) || `#${index + 1}`;
    let key = pmiKey(part, name);
    if (seen.has(key)) key = `${key}#${index + 1}`;
    seen.add(key);
    return read(item, { key, part, name });
  });
}

function readEntry(item, { key, part, name: id }) {
  const dimension = isRecord(item.dimension) ? {
    type: text(item.dimension.type), basic: item.dimension.basic === true, nominal: finite(item.dimension.nominal?.value),
    unit: text(item.dimension.nominal?.unit) || "mm", source: text(item.dimension.nominal?.source),
    // A basic dimension is exact: a tolerance on one is not read as one.
    tolerance: item.dimension.basic === true ? null : readTolerance(item.dimension.tolerance)
  } : null;
  const gdt = isRecord(item.geometric_tolerance) ? {
    characteristic: text(item.geometric_tolerance.characteristic), value: finite(item.geometric_tolerance.value),
    unit: text(item.geometric_tolerance.unit) || "mm", zone: text(item.geometric_tolerance.zone) || null,
    modifier: text(item.geometric_tolerance.modifier) || null, datums: words(item.geometric_tolerance.datums),
    // The part's general profile: on the faces nothing else controls, which its refs are this build.
    general: item.geometric_tolerance.general === true
  } : null;
  const entry = {
    key, id, kind: text(item.kind), label: text(item.label), status: statusOf(item.status), problem: text(item.problem), part,
    refs: readRefs(item.refs), dimension, datum: item.datum && text(item.datum.letter) ? { letter: text(item.datum.letter) } : null,
    tolerance: gdt, note: readNote(item.note), presentation: readPlacement(item.presentation), xcafType: text(item.xcaf_type),
    // What the document holds of an annotation the viewer does not draw: its plain values, to read.
    values: isRecord(item.values) ? readValues(item.values) : null
  };
  // Whether it is drawn is the viewer's to say; why not, the engine's words where it gives them.
  const own = unsupportedReason(entry);
  const unsupported = own && (text(item.reason) || own);
  return { ...entry, supported: !unsupported, unsupported };
}

// A view's camera: the side from the target toward the eye (`direction`, as the stills' presets'),
// its up, the preset it is (null for the code's own) and its projection; null without both vectors.
function readCamera(value) {
  if (!isRecord(value) || !point3(value.direction) || !point3(value.up)) return null;
  return { preset: text(value.preset) || null, direction: point3(value.direction), up: point3(value.up), projection: text(value.projection) || null };
}

// A view's section, the Clip's shape: one plane across `axis` at `at`, keeping the lower side
// (`invert`: the upper); null for none, or for one that is not that.
function readSection(value) {
  if (!isRecord(value) || !SECTION_AXES.includes(value.axis) || finite(value.at) === null || typeof value.invert !== "boolean") return null;
  return { axis: value.axis, at: value.at, invert: value.invert };
}

function readView(item, { key, part, name }) {
  const camera = readCamera(item.camera);
  const section = readSection(item.section);
  const place = Object.fromEntries(Object.entries(isRecord(item.place) ? item.place : {})
    .flatMap(([id, at]) => (id && readPlacement(at) ? [[id, readPlacement(at)]] : [])));
  // One the viewer cannot apply says why: it is never seen down another camera, or uncut.
  const unsupported = !camera ? "it has no camera"
    : item.section != null && !section ? "its section is not one the viewer applies"
      : item.shows != null && !Array.isArray(item.shows) ? "what it shows is not a list of ids" : "";
  return { key, kind: "view", part, name, label: text(item.label), camera, section,
    shows: Array.isArray(item.shows) ? words(item.shows) : null, place, supported: !unsupported, unsupported };
}

// The note number an entry is said as, or null: its part's general profile is Note 1, each note its own.
const noteNumber = entry => (!entry.supported ? null : entry.kind === "note" ? entry.note.number : entry.tolerance?.general ? 1 : null);
const partRank = part => (part === null ? Number.MAX_SAFE_INTEGER : part);

/**
 * An annotation or a note as the viewer reads it, with every field its kind carries.
 *
 * @typedef {object} XbfPmiEntry
 * @property {string} key  Its part's and its id (`pmiKey`): what the viewer knows it by.
 * @property {string} id
 * @property {string} kind  `datum`, `dimension`, `geometric_tolerance`, `note`, or another the viewer tells and does not draw.
 * @property {string} label
 * @property {"ok" | "ambiguous" | "missing" | "invalid"} status
 * @property {string} problem
 * @property {number | null} part  The structure's prototype it is of (its presentation is in that part's frame), null where it is linked to nothing.
 * @property {Array<{ role: string, ref: string, written: string, status: string, candidates: string[] }>} refs  A general
 *   profile's: the faces it covers this build, none where it covers none.
 * @property {{ type: string, basic: boolean, nominal: number | null, unit: string, source: string,
 *   tolerance: { type: "plus_minus" | "limits", upper: number, lower: number } | null } | null} dimension  Its tolerance:
 *   deviations (`plus_minus`), or the least size and the greatest (`limits`, which need no nominal).
 * @property {{ letter: string } | null} datum
 * @property {{ characteristic: string, value: number | null, unit: string, zone: string | null, modifier: string | null,
 *   datums: string[], general: boolean } | null} tolerance  `general`: its part's general profile.
 * @property {{ number: number | null, text: string, general: boolean, annotations: string[] } | null} note  `general`: it
 *   names no face and no annotation; `annotations`: the ids it names.
 * @property {{ anchor: number[], offset: number[] } | null} presentation
 * @property {string} xcafType
 * @property {Array<[string, string]> | null} values  What an unsupported one holds, as words.
 * @property {boolean} supported  Whether the viewer draws it.
 * @property {string} unsupported  Why not, the engine's reason where it gives one.
 */

/**
 * A part's named view as the viewer reads it: seen down its camera, cut by its section, showing
 * its PMI at its own placements.
 *
 * @typedef {object} XbfPmiView
 * @property {string} key  Its part's and its name (`pmiKey`).
 * @property {"view"} kind
 * @property {number | null} part
 * @property {string} name
 * @property {string} label
 * @property {{ preset: string | null, direction: number[], up: number[], projection: string | null } | null} camera
 *   `direction`: the side from the target toward the eye (a preset's, as the stills' are); `preset` null for the code's own.
 * @property {{ axis: "x" | "y" | "z", at: number, invert: boolean } | null} section  The Clip's shape, in its part's frame.
 * @property {string[] | null} shows  The ids of its part's call it shows; null, every one.
 * @property {Record<string, { anchor: number[], offset: number[] }>} place  Its own placements of them, by id, in its part's frame.
 * @property {boolean} supported  Whether the viewer can apply it.
 * @property {string} unsupported  Why not.
 */

/**
 * The document's PMI as the viewer reads it (`structure.pmi`, and beside it `pmi_views` and
 * `pmi_coverage`, each served wherever `pmi` is; none where a key is absent),
 * read defensively: a field missing or of the wrong type is null, never guessed.
 *
 * - `entries`: each annotation and note.
 * - `notes`: the entries said as a part's numbered notes, each part's by its number: its general
 *   profile (Note 1, where it has one), then its notes. The same objects as in `entries`.
 * - `views`: each part's named views, in the code's order, keyed by part and name.
 * - `coverage`: of each part carrying PMI, the faces no requirement names, the requirements that
 *   cannot both hold, and what its requirements leave unsaid: each a question for the person who
 *   knows the part, the standard answer the engine suggests (the call that says it) and why.
 *
 * @param {object | null} structure  A served document's structure.
 * @returns {{ entries: XbfPmiEntry[], notes: XbfPmiEntry[], views: XbfPmiView[],
 *   coverage: Array<{ part: number | null, uncovered: string[], conflicts: Array<{ kind: string, ids: string[], problem: string }>,
 *     suggestions: Array<{ kind: string, faces: string[], question: string, answer: string, why: string }> }> }}
 */
export function readXbfPmi(structure) {
  const entries = keyedByPart(structure?.pmi, item => text(item.id), readEntry);
  const notes = entries.filter(entry => noteNumber(entry) !== null)
    .sort((a, b) => partRank(a.part) - partRank(b.part) || noteNumber(a) - noteNumber(b));
  const coverage = (Array.isArray(structure?.pmi_coverage) ? structure.pmi_coverage : []).filter(isRecord).map(item => ({
    part: partOf(item.part), uncovered: words(item.uncovered),
    conflicts: (Array.isArray(item.conflicts) ? item.conflicts : []).filter(isRecord)
      .map(conflict => ({ kind: text(conflict.kind), ids: words(conflict.ids), problem: text(conflict.problem) })),
    suggestions: (Array.isArray(item.suggestions) ? item.suggestions : []).filter(isRecord)
      .map(said => ({ kind: text(said.kind), faces: words(said.faces), question: text(said.question),
        answer: text(said.answer), why: text(said.why) }))
      .filter(said => said.question && said.answer) }));
  return { entries, notes, views: keyedByPart(structure?.pmi_views, item => text(item.name), readView), coverage };
}

// ---- saying it --------------------------------------------------------------------------------

// The places a number is given to: what its own value needs, up to four, trailing zeros dropped.
function decimalsOf(value) {
  const fixed = Math.abs(value).toFixed(4).replace(/0+$/, "");
  const dot = fixed.indexOf(".");
  return dot < 0 || dot === fixed.length - 1 ? 0 : fixed.length - dot - 1;
}

/** A number at `places` decimals, with a true minus sign. */
export function pmiNumber(value, places = decimalsOf(value)) {
  const fixed = Math.abs(value).toFixed(places);
  return Number(fixed) === 0 ? fixed : `${value < 0 ? MINUS : ""}${fixed}`;
}

/**
 * A tolerance as a drawing writes it, at one number of places (what the more exact of its two
 * numbers needs). A plus-minus one: `±0.2` where it is the same both ways, else its two
 * deviations, each signed (`+0.1`, `−0.05`) and a zero bare (`0`). Limits: the least size and the
 * greatest, `10.00–10.05` (an en dash between them), stacked upper over lower where drawn.
 */
export function pmiToleranceText(tolerance) {
  if (!tolerance) return null;
  const places = Math.max(decimalsOf(tolerance.upper), decimalsOf(tolerance.lower));
  if (tolerance.type === "limits") {
    const upper = pmiNumber(tolerance.upper, places), lower = pmiNumber(tolerance.lower, places);
    return { limits: true, upper, lower, text: `${lower}${EN_DASH}${upper}`, places };
  }
  if (tolerance.upper > 0 && Math.abs(tolerance.upper + tolerance.lower) < 1e-12) {
    return { symmetric: true, text: `±${pmiNumber(tolerance.upper, places)}`, upper: `+${pmiNumber(tolerance.upper, places)}`,
      lower: `${MINUS}${pmiNumber(tolerance.upper, places)}`, places };
  }
  const signed = value => (value === 0 ? "0" : value > 0 ? `+${pmiNumber(value, places)}` : pmiNumber(value, places));
  return { symmetric: false, text: `${signed(tolerance.upper)}/${signed(tolerance.lower)}`, upper: signed(tolerance.upper),
    lower: signed(tolerance.lower), places };
}

const CHARACTERISTIC_NAMES = Object.freeze({ flatness: "Flatness", position: "Position", surface_profile: "Surface profile" });
const DIMENSION_NAMES = Object.freeze({ distance: "Distance", diameter: "Diameter" });

/**
 * The places a dimension's numbers are written at: its tolerance's (none without one) or what its
 * nominal needs (up to four), whichever is more -- the nominal's on its callout, and both of its
 * current limits'. Limits given are its sizes, said in place of its nominal: at their own places.
 */
export function pmiDimensionPlaces(dimension) {
  const tolerance = pmiToleranceText(dimension.tolerance);
  if (tolerance?.limits) return tolerance.places;
  return Math.max(tolerance ? tolerance.places : 0, dimension.nominal === null ? 0 : decimalsOf(dimension.nominal));
}

/**
 * What a callout says, in pieces a label draws and in words: a dimension's nominal (at
 * `pmiDimensionPlaces`), its `⌀` for a diameter and its tolerance, `basic` for one that is exact (a
 * drawing boxes its number), and, given its limits, those in place of its nominal (`nominal` null);
 * a datum's letter;
 * a frame's cells -- its characteristic, its value (with `⌀` for a diameter zone) and each datum it
 * refers to; a note's number and words, `flag` for one on faces or annotations (a general note is
 * said in the notes, not drawn on the part). The general profile is its part's Note 1, said as a
 * drawing's notes say it, and drawn as no callout (`kind: "general_profile"`). `text` is the one
 * line a row, a hint or a copy carries.
 *
 * @param {XbfPmiEntry} entry
 */
export function pmiCallout(entry) {
  if (!entry?.supported) return { kind: "unsupported", title: entry?.label || entry?.id || "", text: entry?.xcafType || entry?.kind || "PMI" };
  if (entry.kind === "dimension") {
    const tolerance = pmiToleranceText(entry.dimension.tolerance);
    const diameter = entry.dimension.type === "diameter";
    const basic = entry.dimension.basic;
    const head = { kind: "dimension", type: entry.dimension.type, diameter, basic, tolerance, unit: entry.dimension.unit,
      title: basic ? "Basic distance" : DIMENSION_NAMES[entry.dimension.type] };
    if (tolerance?.limits) return { ...head, nominal: null, text: `${diameter ? "⌀" : ""}${tolerance.text}` };
    // No nominal where the reference broke: there is nothing to measure it on.
    const nominal = entry.dimension.nominal === null ? "?" : pmiNumber(entry.dimension.nominal, pmiDimensionPlaces(entry.dimension));
    return { ...head, nominal, text: `${diameter ? "⌀" : ""}${nominal}${tolerance ? ` ${tolerance.text}` : ""}${basic ? " basic" : ""}` };
  }
  if (entry.kind === "datum") return { kind: "datum", letter: entry.datum.letter, title: "Datum", text: `Datum ${entry.datum.letter}` };
  if (entry.kind === "note") {
    const { number, general } = entry.note;
    return { kind: "note", number, flag: !general, title: `Note ${number}`, text: entry.note.text };
  }
  const { characteristic, value, zone, datums, unit } = entry.tolerance;
  if (entry.tolerance.general) {
    return { kind: "general_profile", number: 1, title: "Note 1",
      text: `Unless otherwise noted, all surfaces profile ${pmiNumber(value)}${datums.length ? ` to ${datums.join("|")}` : ""}` };
  }
  const diameter = zone === "diameter";
  const shown = pmiNumber(value);
  return { kind: "frame", characteristic, diameter, value: shown, datums: [...datums], unit, title: CHARACTERISTIC_NAMES[characteristic],
    text: [`${CHARACTERISTIC_NAMES[characteristic]} ${diameter ? "⌀" : ""}${shown}`, ...datums].join(" | ") };
}

/** What the status of an entry or a reference is, in words, or "" for one that is fine. */
export function pmiStatusText(entry) {
  if (!entry || entry.status === "ok") return "";
  if (entry.problem) return entry.problem;
  const broken = entry.refs?.find(ref => ref.status !== "ok");
  if (entry.status === "ambiguous") return broken ? `${broken.written} names ${broken.candidates.length || "several"} elements` : "A reference names several elements";
  if (entry.status === "invalid") return broken ? `${broken.written} names a face this cannot stand on` : "A reference names a face this cannot stand on";
  return broken ? `${broken.written} names nothing in this version` : "A reference names nothing in this version";
}

// ---- asking for it: the code a change is ------------------------------------------------------

const PY_NUMBER_PLACES = 4;
/** A number as the model's code writes it: at most four places, no float noise, never `-0`. */
export function pyNumber(value) {
  const rounded = Number(Number(value).toFixed(PY_NUMBER_PLACES));
  return String(Object.is(rounded, -0) ? 0 : rounded);
}
// A string as Python reads it: JSON's quoting is Python's for every character a ref or an id holds.
const pyString = value => JSON.stringify(String(value));
const pyTuple = point => `(${point.map(pyNumber).join(", ")})`;
const pyList = items => `[${items.map(pyString).join(", ")}]`;

/** The `place(...)` an annotation's presentation is in code: where it is drawn, never what it means. */
export function pmiPlaceText(presentation) {
  return `place(anchor=${pyTuple(presentation.anchor)}, offset=${pyTuple(presentation.offset)})`;
}

/**
 * The tolerance a dimension's call gives it: `limits(lower, upper)`, or `plus_minus_tolerance(...)`,
 * its lower deviation left out where it is the upper's negative.
 */
function pmiToleranceCallText(tolerance) {
  if (tolerance.type === "limits") return `limits(${pyNumber(tolerance.lower)}, ${pyNumber(tolerance.upper)})`;
  const symmetric = Math.abs(tolerance.upper + tolerance.lower) < 1e-12;
  return symmetric ? `plus_minus_tolerance(${pyNumber(tolerance.upper)})`
    : `plus_minus_tolerance(${pyNumber(tolerance.upper)}, ${pyNumber(tolerance.lower)})`;
}

// A view's camera as its call gives it: a preset's name, or `camera(direction, up)`; null for neither.
function pmiCameraText(camera) {
  if (typeof camera === "string") return camera ? pyString(camera) : null;
  return camera && point3(camera.direction) && point3(camera.up) ? `camera(${pyTuple(camera.direction)}, ${pyTuple(camera.up)})` : null;
}

// `view(...)`: its name, its camera, then what it shows (every one where it names none), its
// section (`invert=` only where it keeps the upper side, the engine's default the lower), its own
// placements by id and its label, each where given.
function pmiViewText(call) {
  const camera = pmiCameraText(call.camera);
  const section = call.section;
  const placed = Object.entries(call.place || {});
  if (!text(call.name).trim() || !camera || (section && !(SECTION_AXES.includes(section.axis) && finite(section.at) !== null))
    || (Array.isArray(call.shows) && !call.shows.every(Boolean)) || !placed.every(([id, at]) => id && readPlacement(at))) return null;
  return `view(${[pyString(call.name), `camera=${camera}`, Array.isArray(call.shows) ? `shows=${pyList(call.shows)}` : null,
    section ? `section=section(${pyString(section.axis)}, ${pyNumber(section.at)}${section.invert ? ", invert=True" : ""})` : null,
    placed.length ? `place={${placed.map(([id, at]) => `${pyString(id)}: ${pmiPlaceText(at)}`).join(", ")}}` : null,
    call.label ? `label=${pyString(call.label)}` : null].filter(Boolean).join(", ")})`;
}

/**
 * The call that declares an annotation in the model's `annotate(body, ...)`, as `cadgen.ap242` takes
 * it, named after the AP242 entity it writes: its id first, then its references (each its canonical
 * ref, verbatim), then its values:
 *
 * - `{ kind: "datum", id, letter, ref }`: `datum("A", ref)` (a datum's id is its letter);
 * - `{ kind: "dimension", type: "distance", id, from, to, tolerance? }`:
 *   `dimensional_location(id, from, to, tolerance=...)`;
 * - `{ kind: "dimension", type: "distance", basic: true, id, from, to }`:
 *   `dimensional_location(id, from, to, basic=True)` (exact: a tolerance given it makes no call);
 * - `{ kind: "dimension", type: "diameter", id, ref, tolerance? }`: `dimensional_size(id, ref, tolerance=...)`;
 *   a dimension's tolerance `plus_minus_tolerance(...)`, or `limits(lower, upper)` for limits;
 * - `{ kind: "geometric_tolerance", characteristic: "flatness", id, ref, value }`: `flatness_tolerance(id, ref, value)`;
 * - `{ kind: "geometric_tolerance", characteristic: "position", id, ref, value, datums, diameterZone }`:
 *   `position_tolerance(id, ref, value, datums=[...], diameter_zone=True)`, its zone said either way
 *   (the engine's is a diameter's unless the call says it is not);
 * - `{ kind: "geometric_tolerance", characteristic: "surface_profile", id, refs, value, datums? }`:
 *   `surface_profile_tolerance(id, ref, value, datums=[...])`, its faces a list where it is on several;
 * - `{ kind: "geometric_tolerance", characteristic: "surface_profile", general: true, id, value, datums? }`:
 *   `general_profile(id, value, datums=[...])`, on no ref (its faces are each build's) and never
 *   placed (a presentation given it makes no call);
 * - `{ kind: "note", id, text, faces?, annotations? }`: `note(id, text, faces=[...], annotations=[...])`,
 *   a general note naming neither;
 * - `{ kind: "view", name, camera, shows?, section?, place? }`: `view(name, camera="front", shows=[...],
 *   section=section(axis, at, invert=True), place={id: place(...)})`, its camera a preset's
 *   name or `{ direction, up }` (`camera(direction, up)`), its shows null for every one.
 *
 * A tolerance is written only where one is given, a frame's datums where it names some. `label`,
 * where given, is its `label=`, and `presentation` its `place`. Null for a call that lacks what
 * its kind needs: nothing is filled in.
 */
export function pmiCallText(call) {
  if (call?.kind === "view") return pmiViewText(call);
  if (!call?.id) return null;
  const tail = [call.label ? `label=${pyString(call.label)}` : null, call.presentation ? `presentation=${pmiPlaceText(call.presentation)}` : null];
  const args = (...items) => [...items, ...tail].filter(item => item !== null && item !== undefined).join(", ");
  if (call.kind === "datum") {
    if (!call.ref || !call.letter) return null;
    return `datum(${args(pyString(call.letter), pyString(call.ref))})`;
  }
  if (call.kind === "dimension") {
    const tolerance = call.tolerance ? `tolerance=${pmiToleranceCallText(call.tolerance)}` : null;
    if (call.type === "distance") {
      if (!call.from || !call.to) return null;
      if (call.basic) return call.tolerance ? null : `dimensional_location(${args(pyString(call.id), pyString(call.from), pyString(call.to), "basic=True")})`;
      return `dimensional_location(${args(pyString(call.id), pyString(call.from), pyString(call.to), tolerance)})`;
    }
    if (call.type === "diameter") {
      if (!call.ref) return null;
      return `dimensional_size(${args(pyString(call.id), pyString(call.ref), tolerance)})`;
    }
    return null;
  }
  if (call.kind === "geometric_tolerance") {
    if (finite(call.value) === null || !(call.value > 0)) return null;
    const datums = (call.datums || []).filter(Boolean);
    const frame = datums.length ? `datums=${pyList(datums)}` : null;
    if (call.characteristic === "surface_profile") {
      if (call.general) return call.presentation ? null : `general_profile(${args(pyString(call.id), pyNumber(call.value), frame)})`;
      const refs = call.refs || [];
      if (!refs.length || !refs.every(Boolean)) return null;
      return `surface_profile_tolerance(${args(pyString(call.id), refs.length === 1 ? pyString(refs[0]) : pyList(refs), pyNumber(call.value), frame)})`;
    }
    if (!call.ref) return null;
    if (call.characteristic === "flatness") return `flatness_tolerance(${args(pyString(call.id), pyString(call.ref), pyNumber(call.value))})`;
    if (call.characteristic === "position") {
      return `position_tolerance(${args(pyString(call.id), pyString(call.ref), pyNumber(call.value), frame, `diameter_zone=${call.diameterZone ? "True" : "False"}`)})`;
    }
  }
  if (call.kind === "note") {
    const faces = call.faces || [], annotations = call.annotations || [];
    if (!text(call.text).trim() || !faces.every(Boolean) || !annotations.every(Boolean)) return null;
    return `note(${args(pyString(call.id), pyString(call.text), faces.length ? `faces=${pyList(faces)}` : null,
      annotations.length ? `annotations=${pyList(annotations)}` : null)})`;
  }
  return null;
}

/**
 * An entry the document holds as the call that declares it, with `changes` over its values
 * (`{ tolerance, value, letter, datums, diameterZone, presentation }`, each where given; a tolerance
 * of null takes it away) and its label as it is: what an edit in the viewer asks the code to become.
 * Its references are the canonical refs this build resolved them to (`ref`), which name the same
 * elements however the code wrote them (a variable holding a face, say); the code's own where none
 * resolved. A general profile names no face (its faces are each build's) and takes no placement. A
 * view (`readXbfPmi`'s `views`) is its `view` call, with changes over `{ camera, shows, section,
 * place }`.
 */
export function pmiEntryCall(entry, changes = {}) {
  const given = key => (Object.prototype.hasOwnProperty.call(changes, key) ? changes[key] : undefined);
  const over = (key, value) => (given(key) === undefined ? value : given(key));
  const named = ref => (ref?.status === "ok" ? ref.ref : ref?.written) || "";
  const refOf = role => named(entry.refs.find(ref => ref.role === role));
  const refsOf = role => entry.refs.filter(ref => ref.role === role).map(named);
  const label = entry.label || null;
  if (entry.kind === "view") {
    const camera = entry.camera ? entry.camera.preset || { direction: entry.camera.direction, up: entry.camera.up } : null;
    return { kind: "view", name: entry.name, camera: over("camera", camera), shows: over("shows", entry.shows), section: over("section", entry.section),
      place: over("place", entry.place), label };
  }
  const presentation = over("presentation", entry.presentation);
  if (entry.kind === "datum") return { kind: "datum", id: entry.id, letter: given("letter") ?? entry.datum.letter, ref: refOf("feature"), label, presentation };
  if (entry.kind === "note") {
    return { kind: "note", id: entry.id, text: entry.note.text, faces: refsOf("feature"), annotations: [...entry.note.annotations], label, presentation };
  }
  if (entry.kind === "dimension") {
    const tolerance = given("tolerance") === undefined ? entry.dimension.tolerance : given("tolerance");
    if (entry.dimension.basic) {
      return { kind: "dimension", type: "distance", basic: true, id: entry.id, from: refOf("from"), to: refOf("to"), tolerance: null, label, presentation };
    }
    return entry.dimension.type === "distance"
      ? { kind: "dimension", type: "distance", id: entry.id, from: refOf("from"), to: refOf("to"), tolerance, label, presentation }
      : { kind: "dimension", type: "diameter", id: entry.id, ref: refOf("feature"), tolerance, label, presentation };
  }
  const tolerance = entry.tolerance;
  const value = given("value") ?? tolerance.value, datums = given("datums") ?? tolerance.datums;
  if (tolerance.general) return { kind: "geometric_tolerance", characteristic: "surface_profile", general: true, id: entry.id, value, datums, label };
  if (tolerance.characteristic === "surface_profile") {
    return { kind: "geometric_tolerance", characteristic: "surface_profile", id: entry.id, refs: refsOf("feature"), value, datums, label, presentation };
  }
  return { kind: "geometric_tolerance", characteristic: tolerance.characteristic, id: entry.id, ref: refOf("feature"), value, datums,
    diameterZone: given("diameterZone") ?? tolerance.zone === "diameter", label, presentation };
}

/** An id for a new annotation that none of `taken` (its part's) has: `stem`, else `stem-2`, `stem-3`... */
export function pmiFreshId(stem, taken) {
  const held = new Set(taken);
  if (!held.has(stem)) return stem;
  for (let n = 2; ; n += 1) if (!held.has(`${stem}-${n}`)) return `${stem}-${n}`;
}

/**
 * What an edit sets, each as the call writes it: `tolerance=...` (or that it has none), its value,
 * `datums=[...]`, `presentation=...` (or that it is placed beside its feature).
 */
function pmiEditSettings(values) {
  const set = [];
  if (Object.prototype.hasOwnProperty.call(values, "tolerance")) set.push(values.tolerance ? `tolerance=${pmiToleranceCallText(values.tolerance)}` : "no tolerance (drop tolerance=)");
  if (Object.prototype.hasOwnProperty.call(values, "value")) set.push(`its tolerance value ${pyNumber(values.value)}`);
  if (Object.prototype.hasOwnProperty.call(values, "datums")) set.push(`datums=[${values.datums.map(pyString).join(", ")}]`);
  if (Object.prototype.hasOwnProperty.call(values, "presentation")) set.push(values.presentation ? `presentation=${pmiPlaceText(values.presentation)}` : "no placement (drop presentation=)");
  return set;
}

// The names a request's call and its `annotate` take from `cadgen.ap242`, in order: the import its
// request names. The call's strings (refs, ids, a note's words) are left out, so a name in one is none.
function pmiCallNames(call) {
  const code = call.replace(/"(?:[^"\\]|\\.)*"/g, '""');
  return [...new Set(["annotate", ...[...code.matchAll(/\b([a-z_]+)\(/g)].map(found => found[1])])].sort();
}

/**
 * A change asked for in the viewer as the request Quick Edit hands the agent: one paragraph of what
 * to do to the `annotate(...)` call of its part (`partName`, where the part has one), with the names
 * it and the call take from `cadgen.ap242`, then the call itself, exactly. `change`: a new annotation
 * (`{ kind: "add", part, partName, id, call }`) or an edit of one the document holds
 * (`{ kind: "edit", part, partName, id, values, call, placementOnly }`: what it sets, and the call it
 * makes), `id` the author's. "" for a call that lacks what its kind needs.
 */
export function pmiChangeRequest(change) {
  const call = pmiCallText(change.call);
  if (!call) return "";
  const annotate = change.partName ? `the annotate(...) call of the model's part ${pyString(change.partName)}` : "the model's annotate(...) call";
  const names = `(from cadgen.ap242 import ${pmiCallNames(call).join(", ")})`;
  if (change.kind === "add") return `Add this PMI to ${annotate} ${names}:\n${call}`;
  const what = change.placementOnly
    ? `Move the PMI "${change.id}" in ${annotate} ${names}, its placement only (what it says is unchanged)`
    : `Change the PMI "${change.id}" in ${annotate} ${names}`;
  return `${what}: ${pmiEditSettings(change.values).join("; ")}. Keep its references as the code writes them. `
    + `The whole call, its references as this build resolves them:\n${call}`;
}

/**
 * Whether the document now says what `change` asked for, so it has nothing left to ask: a new
 * annotation its part holds, an edit whose call -- its values, zone, label and placement -- is the
 * one the part's entry of that id makes now. A change to a view (its call `view`) is settled by
 * the part's view of that name in `views` (`readXbfPmi`'s), never by an annotation: a view and an
 * annotation may share a name. What the viewer drops once a build has it.
 */
export function pmiChangeSettled(change, entries, views = []) {
  const found = change.call?.kind === "view"
    ? views.find(view => view.part === change.part && view.name === change.call.name)
    : entries.find(item => item.part === change.part && item.id === change.id);
  if (change.kind === "add") return Boolean(found);
  return Boolean(found?.supported) && pmiCallText(pmiEntryCall(found)) === pmiCallText(change.call);
}
