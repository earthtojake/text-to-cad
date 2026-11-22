// A model's declared parameters as a page reads and edits them: the `parameters` of the engine's
// structure JSON (`xbfDocument.js`), each a named number its script declares -- its value as the
// document was built, its kind (a whole number or a float), its range and step where declared, its
// unit, and whether the engine can write it back (`writable`, else `reason`). A page holds new
// values as drafts, shows the model at them as they move (`client.previewModelParameters`: the engine
// builds it for that page alone and writes nothing), and saves the changed ones in one request
// (`client.setModelParameters`): the engine rewrites the numbers in the script and builds the model
// again, and the page reads the rebuilt document as it reads any new version. Nothing here draws or
// fetches.

/** Why a parameter cannot be written, the engine's closed set (any other reads as read-only, unexplained). */
export const PARAMETER_REASONS = Object.freeze(["file", "no_worker", "shared", "expression"]);
/** Why a save was refused, the engine's closed set of `code`s. */
export const PARAMETER_REFUSALS = Object.freeze([
  "no_worker", "unknown_parameter", "not_writable", "not_a_number", "out_of_range", "script_changed", "busy", "build_failed"
]);
// A float is written with at most this many decimals (the engine's own rounding of what it writes).
const FLOAT_DECIMALS = 6;
const NONE = Object.freeze([]);

const finite = value => (typeof value === "number" && Number.isFinite(value) ? value : null);
const rounded = value => Number(Number(value).toFixed(FLOAT_DECIMALS));

/**
 * @typedef {object} XbfParameter
 * @property {string} name
 * @property {number} value  The value the document was built with.
 * @property {"int" | "float"} kind
 * @property {number | null} min
 * @property {number | null} max
 * @property {number | null} step
 * @property {string | null} unit  `"mm"`, `"deg"` or none: how the value is read, never converted.
 * @property {boolean} writable
 * @property {string | null} reason  Why it is not writable (`PARAMETER_REASONS`); null when it is.
 * @property {string | null} source  The file that declares it, where the engine knows.
 */

/**
 * The parameters a structure records, in its order; none for a structure without the key (an
 * engine before parameters) or a record that is no parameter (no name, no finite value).
 * @param {{ parameters?: unknown } | null | undefined} structure
 * @returns {readonly XbfParameter[]}
 */
export function xbfParameters(structure) {
  const listed = structure?.parameters;
  if (!Array.isArray(listed) || !listed.length) return NONE;
  const seen = new Set();
  const parameters = [];
  for (const record of listed) {
    const name = typeof record?.name === "string" ? record.name : "";
    const value = finite(record?.value);
    if (!name || value === null || seen.has(name)) continue;
    seen.add(name);
    const step = finite(record.step);
    const writable = record.writable === true;
    parameters.push(Object.freeze({
      name, value, kind: record.kind === "int" ? "int" : "float",
      min: finite(record.min), max: finite(record.max), step: step !== null && step > 0 ? step : null,
      unit: typeof record.unit === "string" && record.unit.trim() ? record.unit.trim() : null,
      writable, reason: writable ? null : typeof record.reason === "string" && record.reason ? record.reason : "",
      source: typeof record.source === "string" && record.source ? record.source : null
    }));
  }
  return parameters.length ? Object.freeze(parameters) : NONE;
}

/** Whether a parameter has both ends of a range: what a slider needs. */
export const parameterIsRanged = parameter => parameter.min !== null && parameter.max !== null && parameter.max > parameter.min;

/**
 * The value `parameter` takes from `value`, the one boundary every write crosses (a slider, a typed
 * number, the request): inside its range where one is declared, a whole number for an integer
 * parameter, a float of at most six decimals otherwise. Null for no number.
 * @param {XbfParameter} parameter @param {unknown} value @returns {number | null}
 */
export function parameterValue(parameter, value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const min = parameter.min ?? -Infinity, max = parameter.max ?? Infinity;
  if (parameter.kind === "int") {
    // The whole numbers inside the range: a bound that is no whole number is not one of them.
    const low = Math.ceil(min), high = Math.floor(max);
    return low > high ? null : Math.min(Math.max(Math.round(number), low), high) + 0;
  }
  return rounded(Math.min(Math.max(number, min), max)) + 0;
}

/** Whether two values of a parameter are the same value as the engine would write them. */
export function sameParameterValue(parameter, left, right) {
  if (left === null || left === undefined || right === null || right === undefined) return false;
  return parameter.kind === "int" ? Math.round(left) === Math.round(right) : rounded(left) === rounded(right);
}

// The decimals a number is written with ("0.25": 2), at most six.
function decimalsOf(number) {
  const text = String(number);
  const exponent = text.match(/e-(\d+)$/);
  return Math.min(FLOAT_DECIMALS, exponent ? Number(exponent[1]) + (text.split("e")[0].split(".")[1] || "").length : (text.split(".")[1] || "").length);
}

/**
 * The step a parameter's control moves by: whole numbers for an integer parameter (its declared
 * step, where that is one), the declared step for a float, else a power of ten that crosses its range
 * in a hundred to a thousand steps; none for a float with neither.
 * @param {XbfParameter} parameter @returns {number | null}
 */
export function parameterStep(parameter) {
  if (parameter.kind === "int") return Math.max(1, Math.round(parameter.step ?? 1));
  if (parameter.step !== null) return parameter.step;
  if (!parameterIsRanged(parameter)) return null;
  const range = parameter.max - parameter.min;
  return Number(Math.max(10 ** Math.floor(Math.log10(range / 100)), 10 ** -FLOAT_DECIMALS).toPrecision(12));
}

/** A unit as a value's text carries it: degrees as the sign, any other after a space. */
export function parameterUnitSuffix(unit) {
  const text = String(unit || "").trim();
  return !text ? "" : /^(deg|degrees?|°)$/i.test(text) ? "°" : ` ${text}`;
}

/**
 * A parameter's value as text, with its unit: a whole number for an integer parameter; a float at
 * its step's precision where it has a step (so a dragged slider's text keeps its width), else as
 * few decimals as say it, at most six.
 * @param {XbfParameter} parameter @param {number} value @returns {string}
 */
export function formatParameterValue(parameter, value) {
  const number = Number(value);
  const suffix = parameterUnitSuffix(parameter.unit);
  if (!Number.isFinite(number)) return `0${suffix}`;
  if (parameter.kind === "int") return `${Math.round(number)}${suffix}`;
  const step = parameterStep(parameter);
  // A value finer than the step (a declared 2.125 on a step of 0.1) is said whole, never rounded away.
  const decimals = step === null ? 0 : Math.max(decimalsOf(step), decimalsOf(rounded(number)));
  return `${step === null ? String(rounded(number)) : number.toFixed(Math.min(FLOAT_DECIMALS, decimals))}${suffix}`;
}

/**
 * What a save sends: each writable parameter whose draft is another value than the document's, by
 * name, as the number the engine takes (`parameterValue`); never a value the document already
 * holds, nor one already sent and not yet answered by a rebuilt document (`sent`).
 * @param {readonly XbfParameter[]} parameters @param {Record<string, number>} drafts
 * @param {Record<string, number> | null} [sent]
 * @returns {Record<string, number>}
 */
export function changedParameters(parameters, drafts, sent = null) {
  const changed = {};
  for (const parameter of parameters) {
    if (!parameter.writable || !Object.hasOwn(drafts || {}, parameter.name)) continue;
    const value = parameterValue(parameter, drafts[parameter.name]);
    if (value === null || sameParameterValue(parameter, value, parameter.value)) continue;
    if (sent && Object.hasOwn(sent, parameter.name) && sameParameterValue(parameter, value, sent[parameter.name])) continue;
    changed[parameter.name] = value;
  }
  return changed;
}

/**
 * The drafts a new version of the document leaves standing: a draft whose parameter now holds its
 * value, is gone or can no longer be written is dropped. The same object when none is.
 * @param {readonly XbfParameter[]} parameters @param {Record<string, number>} drafts
 * @returns {Record<string, number>}
 */
export function settledDrafts(parameters, drafts) {
  const byName = new Map(parameters.map(parameter => [parameter.name, parameter]));
  const kept = Object.entries(drafts || {}).filter(([name, value]) => {
    const parameter = byName.get(name);
    return Boolean(parameter?.writable) && !sameParameterValue(parameter, value, parameter.value);
  });
  return kept.length === Object.keys(drafts || {}).length ? drafts : Object.fromEntries(kept);
}

const baseName = file => String(file || "").replace(/\\/g, "/").split("/").pop() || "";

/**
 * What a page tells an agent of the values a person saved from it, as one line of plain text for the
 * next message: each parameter's value before and after, the script it is in by its name, and what the
 * agent does with them ("Saved from the viewer since your last edit: wall 2 -> 2.5 (bracket.py); the
 * script holds these values and is built at them: read it again before you edit it, and keep them"),
 * so the line alone says what it means. Saves of one parameter that follow on from each other read as
 * one change, and a value saved back to where it began is left out. "" for nothing to say.
 * @param {readonly { name: string, from: number, to: number, file?: string }[]} saved  In the order saved.
 * @returns {string}
 */
export function savedParametersNote(saved) {
  const changes = [];
  for (const entry of saved || []) {
    if (typeof entry?.name !== "string" || !entry.name) continue;
    const file = baseName(entry.file);
    const before = changes.findLast(change => change.name === entry.name && change.file === file);
    if (before && before.to === entry.from) before.to = entry.to;
    else changes.push({ name: entry.name, from: entry.from, to: entry.to, file });
  }
  const said = changes.filter(change => change.from !== change.to)
    .map(change => `${change.name} ${change.from} -> ${change.to}${change.file ? ` (${change.file})` : ""}`);
  return said.length ? `Saved from the viewer since your last edit: ${said.join(", ")}; the script holds these values and is built at them: read it again before you edit it, and keep them` : "";
}

/**
 * What a page tells an agent of the values on screen that are not saved (a preview: the model drawn at
 * values the script does not hold), as one line of plain text for a message sent while they are: each
 * parameter's value in the code and on screen, and the file that declares it ("Shown in the viewer, not
 * saved: wall 2 -> 3.5 (bracket.py); the script still holds the first values; write the new ones only if
 * asked"), so the line alone tells an agent what to do with them. Said with every message while it is so:
 * it is the view's state, not a change. "" for none.
 * @param {readonly XbfParameter[]} parameters @param {Record<string, number>} changed  `changedParameters`'s.
 * @returns {string}
 */
export function unsavedParametersNote(parameters, changed) {
  const said = (parameters || []).filter(parameter => Object.hasOwn(changed || {}, parameter.name))
    .map(parameter => `${parameter.name} ${parameter.value} -> ${changed[parameter.name]}${parameter.source ? ` (${baseName(parameter.source)})` : ""}`);
  return said.length ? `Shown in the viewer, not saved: ${said.join(", ")}; the script still holds the first values; write the new ones only if asked` : "";
}
