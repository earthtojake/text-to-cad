/**
 * A CAM job's result as `cadgen cam plan` writes it into `<stem>.cam.glb`: the scene's extras carry
 * `generator: "cadgen cam"` and `cam` (schema 1), which this reads into the one shape the viewer
 * draws (`detect.js` says whether a scene is one). Reading is forgiving: a missing or malformed
 * value takes a plain default, an operation with no index takes its place in the job, a verdict
 * with no status takes it from its errors, so a file written by a newer cadgen still opens.
 * Pure: no three.js, no React.
 */

import { camExtras, carriesCamJob } from "./detect.js";

export { carriesCamJob };

const NONE = Object.freeze([]);

const plainObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const list = (value) => (Array.isArray(value) ? value : NONE);
const number = (value, fallback = null) => (typeof value === "number" && Number.isFinite(value) ? value
  : typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value)) ? Number(value) : fallback);
const text = (value, fallback = "") => (typeof value === "string" ? value.trim() || fallback
  : typeof value === "number" && Number.isFinite(value) ? String(value) : fallback);

/** A duration in plain words: "35 s", "42 min", "1 h 5 min". */
export function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value === 0) return "0 s";
  if (value < 59.5) return `${Math.max(1, Math.round(value))} s`;
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

/** A face token as the prompt grammar writes a selector: its leading "#" is not part of it. */
export const faceSelector = (ref) => String(ref).replace(/^#/, "");

/**
 * The part the job was planned from, the file a row's references name: `document` as the extras
 * write it (relative to the GLB, or absolute), resolved against the GLB's own path. Empty when the
 * extras do not say.
 */
export function camSourcePath(glbPath, document) {
  const named = String(document || "").trim();
  if (!named) return "";
  const absolute = /^(?:[A-Za-z]:)?[\\/]/.test(named);
  const parts = absolute ? named.split("/") : [...String(glbPath || "").split("/").slice(0, -1), ...named.split("/")];
  const out = [];
  for (const part of parts) {
    if (part === "..") out.pop();
    else if (part !== ".") out.push(part);
  }
  return out.join("/");
}

/** The tool's diameter in mm: the operation's, the job's tool list's, else the leading "6 mm" of its plain name. */
function toolDiameter(op, tools) {
  const own = number(op.tool_diameter_mm);
  if (own !== null && own > 0) return own;
  const listed = number(tools[text(op.tool)]?.diameter_mm);
  if (listed !== null && listed > 0) return listed;
  const named = /^\s*(\d+(?:\.\d+)?)\s*mm\b/i.exec(text(op.tool_plain));
  return named ? Number(named[1]) : null;
}

/** A beam's kerf (mm): the operation's tool's, from the job's tool list; null for any other tool. */
function kerf(op, tools) {
  const value = number(tools[text(op.tool)]?.kerf_mm);
  return value !== null && value > 0 ? value : null;
}

/**
 * A setup's frame in part (CAD) coordinates: `axis`, the direction its tool comes from (WCS +Z), and `across`,
 * its WCS +X (a lathe's radial direction), from the extras' `matrix` (part -> WCS, rows WCS X, Y, Z). Without a
 * usable matrix, the axis its `orientation` names ("+Z", "-X", ...), else +Z.
 */
const ORIENTATION_AXES = Object.freeze({ "+Z": [0, 0, 1], "-Z": [0, 0, -1], "+X": [1, 0, 0], "-X": [-1, 0, 0], "+Y": [0, 1, 0], "-Y": [0, -1, 0] });
function unitRow(matrix, row) {
  const values = list(list(matrix)[row]).slice(0, 3).map((value) => number(value));
  if (values.length !== 3 || values.some((value) => value === null)) return null;
  const length = Math.hypot(...values);
  return length > 1e-9 ? values.map((value) => value / length) : null;
}
function setupFrame(rawSetup) {
  const named = typeof rawSetup.orientation === "string" ? ORIENTATION_AXES[rawSetup.orientation.trim().toUpperCase()] : null;
  return { axis: unitRow(rawSetup.matrix, 2) || named || ORIENTATION_AXES["+Z"], across: unitRow(rawSetup.matrix, 0) || [1, 0, 0] };
}

/** A setup's orientation in words: "+Z", or a 3+2 tilt's angles ("A 30° C 90°"). */
function orientationWords(value) {
  if (typeof value === "string") return value.trim();
  if (!plainObject(value)) return "";
  return Object.entries(value).map(([key, angle]) => [/^([abc])_deg$/i.exec(key)?.[1], number(angle)])
    .filter(([axis, angle]) => axis && angle !== null && angle !== 0).map(([axis, angle]) => `${axis.toUpperCase()} ${angle}°`).join(" ") || "+Z";
}

function toolType(op, tools) {
  const own = text(op.tool_type) || text(tools[text(op.tool)]?.type);
  if (own) return own;
  return /\bball\b/i.test(text(op.tool_plain)) ? "ball" : "";
}

/**
 * A setup's fixture keep-out boxes, as cadgen writes them: `{ name, min_mm, max_mm }` in part coordinates (mm,
 * Z up), read as `{ name, min, max }` with each corner's coordinates in order. A box with a corner missing is left out.
 */
function readFixtures(value) {
  return list(value).filter(plainObject).map((entry, index) => {
    const min = point(entry.min_mm);
    const max = point(entry.max_mm);
    if (!min || !max) return null;
    return { name: text(entry.name, `Fixture ${index + 1}`), min: min.map((at, axis) => Math.min(at, max[axis])), max: max.map((at, axis) => Math.max(at, min[axis])) };
  }).filter(Boolean);
}

const point = (value) => {
  const at = list(value).map((entry) => number(entry)).filter((entry) => entry !== null);
  return at.length === 3 ? at : null;
};
const opIndex = (value) => (Number.isInteger(number(value)) ? number(value) : null);

/**
 * A finding as the viewer shows it. cadgen writes `severity`, `summary` and the places it is about as `items`
 * (`[{ setup, operation, at, ... }]`); a flat `level`, `message`, `operation` and `at` are read too. `operation`
 * is the first operation it names, `operations` every one, `at` the first place.
 */
function readFinding(raw) {
  if (!plainObject(raw)) return null;
  const level = text(raw.level) || text(raw.severity) || "warning";
  const message = text(raw.message) || text(raw.summary) || text(raw.description) || text(raw.check);
  if (!message) return null;
  const items = list(raw.items).filter(plainObject);
  const operations = [...new Set([opIndex(raw.operation), ...items.map((item) => opIndex(item.operation))].filter((index) => index !== null))];
  return {
    check: text(raw.check), level: level === "error" ? "error" : level === "warning" ? "warning" : level, message,
    operation: operations.length ? operations[0] : null, operations,
    at: point(raw.at) || items.map((item) => point(item.at)).find(Boolean) || null,
  };
}

/**
 * The job a CAM result carries, or null for any other GLB.
 *
 * @returns {null | { schema: number, verdict: { status: "ready" | "fix", headline: string, errors: number, warnings: number, gcode: string },
 *   setups: { id: string, plain: string, timeS: number, orientation: string, axis: number[], across: number[], operations: object[] }[],
 *   operations: object[], findings: object[], adapted: object[], posts: object[], durationS: number, machine: string, post: string,
 *   tools: object[], toolChanges: { count: number, order: string[] }, warnings: string[], assumed: { key: string, value: string, why: string }[],
 *   stock: { kind: string, thicknessMm: number | null }, document: string, material: string }}
 *   A setup's `fixtures` are its keep-out boxes, `{ name, min, max }` in part coordinates (mm); `tools` are `readTools`'s.
 *   A setup's `axis` is the direction its tool comes from and `across` its WCS +X, both in part coordinates (`setupFrame`);
 *   `orientation` is in words. Each operation: `{ index, op, plain, name, tool, toolPlain, toolDiameterMm, toolType, kerfMm,
 *   rpm, feedMmMin, timeS, t0, t1, summary, faces, limits, setup }`, `index` the one `_CAM_OP` and a finding's `operation` name.
 */
export function readCamJob(root) {
  if (!carriesCamJob(root)) return null;
  let cam = null;
  root.traverse((object) => { if (!cam) cam = camExtras(object); });
  const tools = Object.fromEntries(list(cam.tools).filter(plainObject).map((tool) => [text(tool.id), tool]));
  const operations = [];
  const setups = [];
  let clock = 0;
  for (const [setupIndex, rawSetup] of list(cam.setups).entries()) {
    if (!plainObject(rawSetup)) continue;
    const id = text(rawSetup.id, `setup-${setupIndex + 1}`);
    const plain = text(rawSetup.plain, id);
    const own = [];
    for (const rawOp of list(rawSetup.operations)) {
      if (!plainObject(rawOp)) continue;
      const index = Number.isInteger(number(rawOp.index)) ? number(rawOp.index) : operations.length;
      const timeS = Math.max(0, number(rawOp.time_s, 0));
      const t0 = number(rawOp.t0, clock);
      const t1 = Math.max(t0, number(rawOp.t1, t0 + timeS));
      clock = Math.max(clock, t1);
      const plainWord = text(rawOp.plain) || text(rawOp.op, "Operation");
      const toolPlain = text(rawOp.tool_plain) || text(rawOp.tool);
      const op = {
        index, op: text(rawOp.op), plain: plainWord, name: text(rawOp.name), tool: text(rawOp.tool), toolPlain,
        toolDiameterMm: toolDiameter(rawOp, tools), toolType: toolType(rawOp, tools), kerfMm: kerf(rawOp, tools),
        rpm: number(rawOp.rpm), feedMmMin: number(rawOp.feed_mm_min), timeS: timeS || t1 - t0, t0, t1,
        summary: text(rawOp.summary) || [plainWord, toolPlain && `with ${toolPlain}`].filter(Boolean).join(" "),
        faces: list(rawOp.faces).map((face) => text(face)).filter(Boolean),
        limits: list(rawOp.limits).map((limit) => text(limit)).filter(Boolean),
        setup: id,
      };
      own.push(op);
      operations.push(op);
    }
    const timeS = number(rawSetup.time_s, own.reduce((sum, op) => sum + op.timeS, 0));
    setups.push({ id, plain, timeS, orientation: orientationWords(rawSetup.orientation), ...setupFrame(rawSetup), operations: own,
      fixtures: readFixtures(rawSetup.fixtures) });
  }
  const findings = list(cam.findings).map(readFinding).filter(Boolean)
    .sort((a, b) => (a.level === "error" ? 0 : 1) - (b.level === "error" ? 0 : 1));
  const rawVerdict = plainObject(cam.verdict) ? cam.verdict : {};
  const errors = number(rawVerdict.errors, findings.filter((finding) => finding.level === "error").length);
  const warnings = number(rawVerdict.warnings, findings.filter((finding) => finding.level === "warning").length);
  const status = rawVerdict.status === "ready" || rawVerdict.status === "fix" ? rawVerdict.status : errors > 0 ? "fix" : "ready";
  const durationS = number(cam.duration_s, operations.reduce((end, op) => Math.max(end, op.t1), 0));
  const toolCount = new Set(operations.map((op) => op.tool).filter(Boolean)).size;
  const headline = text(rawVerdict.headline) || (status === "fix" ? `${errors} to fix`
    : ["Ready to cut", formatDuration(durationS), toolCount ? `${toolCount} tool${toolCount === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · "));
  const posts = list(cam.posts).filter(plainObject).map((entry) => ({ setup: text(entry.setup), file: text(entry.file), post: text(entry.post), tool: text(entry.tool) }));
  return {
    schema: number(cam.schema, 1),
    // A plan with errors writes no G-code; its verdict says so ("G-code not written: fix 2 errors first").
    verdict: { status, headline, errors, warnings, gcode: text(rawVerdict.gcode) },
    setups, operations, findings,
    adapted: list(cam.adapted).filter(plainObject).map((entry) => ({ step: text(entry.step), note: text(entry.note) || text(entry.words) })),
    // A setup may post several files (one per tool on a controller without tool changes), each naming its `tool`.
    posts,
    durationS,
    machine: text(cam.machine?.kind) || text(cam.machine),
    // The controller the G-code is written for: the machine's post, else the first file's.
    post: text(cam.machine?.post) || posts.find((entry) => entry.post)?.post || "",
    tools: readTools(cam.tools, operations),
    toolChanges: readToolChanges(cam.tool_changes, operations),
    // The run's own warnings in plain words ("G-code not written: fix 2 errors first"), for the agent as the findings are.
    warnings: list(cam.warnings).map((entry) => text(entry)).filter(Boolean),
    // What the plan took that nobody stated (a generic post, a spindle limit, a tool's catalogue flute length).
    assumed: readAssumed(cam.assumed),
    stock: { kind: text(cam.stock?.kind), thicknessMm: number(cam.stock?.thickness_mm) },
    document: text(cam.document),
    material: typeof cam.material === "string" ? cam.material : text(cam.material?.name),
  };
}

/** An assumed value in words: "fanuc", "8000", "false", "300, 200, 80". */
function valueWords(value) {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (Array.isArray(value)) return value.map(valueWords).filter(Boolean).join(", ");
  return text(value);
}

/**
 * What the plan assumed, as cadgen writes it (`[{ key, value, why }]`): `{ key, value, why }` with the value in
 * words. An entry with no key is left out.
 */
function readAssumed(value) {
  return list(value).filter(plainObject).map((entry) => ({ key: text(entry.key), value: valueWords(entry.value), why: text(entry.why) }))
    .filter((entry) => entry.key);
}

/** An assumption in one line: "machine.post fanuc". */
export const assumedWords = (entry) => [entry.key, entry.value].filter(Boolean).join(" ");

/** The operations in program order: by when each starts, the job's order where two start together. */
const programOrder = (operations) => operations.map((op, order) => ({ op, order })).sort((a, b) => a.op.t0 - b.op.t0 || a.order - b.order).map(({ op }) => op);

/** The smallest and largest of some values (finite only), or null for none. */
function span(values) {
  const finite = values.filter((value) => value !== null && Number.isFinite(value));
  return finite.length ? [Math.min(...finite), Math.max(...finite)] : null;
}

/**
 * The job's tools, each once, in the order the program first uses them (then any the job lists but no operation
 * uses): `{ id, label, plain, type, diameterMm, operations, rpm, feedMmMin }`. `label` is how the machine names it
 * ("T1"); `plain` what it is ("6 mm flat"); `rpm` and `feedMmMin` the range (`[min, max]`) the operations that use
 * it run it at, or null where none says.
 */
function readTools(rawTools, operations) {
  // A listed tool with no id goes by its number, as the machine names it ("T7").
  const toolId = (tool) => text(tool.id) || (number(tool.number) !== null ? `T${number(tool.number)}` : "");
  const listed = list(rawTools).filter(plainObject);
  const byId = new Map(listed.map((tool) => [toolId(tool), tool]));
  const ids = [...new Set([...programOrder(operations).map((op) => op.tool), ...listed.map(toolId)].filter(Boolean))];
  return ids.map((id) => {
    const raw = byId.get(id) || {};
    const uses = operations.filter((op) => op.tool === id);
    const diameterMm = number(raw.diameter_mm) ?? uses.find((op) => op.toolDiameterMm)?.toolDiameterMm ?? null;
    const type = text(raw.type) || uses.find((op) => op.toolType)?.toolType || "";
    const sized = [diameterMm !== null ? `${diameterMm} mm` : "", type.replace(/_/g, " ")].filter(Boolean).join(" ");
    return {
      id, label: id, plain: text(raw.plain) || uses.find((op) => op.toolPlain && op.toolPlain !== id)?.toolPlain || sized,
      type, diameterMm, operations: uses.map((op) => op.index),
      rpm: span(uses.map((op) => op.rpm)), feedMmMin: span(uses.map((op) => op.feedMmMin)),
    };
  });
}

/**
 * The tool changes in the program: `{ count, order }`, `order` the tools in the order they are loaded. cadgen's
 * `tool_changes` where it writes them; else counted from the operations in program order, a change wherever one
 * runs another tool than the one before it (loading the first is not one).
 */
function readToolChanges(raw, operations) {
  const order = [];
  for (const op of programOrder(operations)) if (op.tool && order[order.length - 1] !== op.tool) order.push(op.tool);
  const written = plainObject(raw) ? raw : {};
  const count = number(written.count);
  return {
    count: count !== null && count >= 0 ? Math.round(count) : Math.max(order.length - 1, 0),
    order: Array.isArray(written.order) ? list(written.order).map((entry) => text(entry)).filter(Boolean) : order,
  };
}

const grouped = (value) => Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 });
const ranged = (range, unit) => (range ? `${range[0] === range[1] ? grouped(range[0]) : `${grouped(range[0])}–${grouped(range[1])}`} ${unit}` : "");

/** A tool's speed and feed as the operations that use it run it ("12,000 rpm · 1,440 mm/min"), a range where they differ. */
export const toolSpeeds = (tool) => [ranged(tool.rpm, "rpm"), ranged(tool.feedMmMin, "mm/min")].filter(Boolean).join(" · ");

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The job's tool changes in words: "No tool changes", "1 tool change", "3 tool changes". */
export const toolChangeWords = (count) => (count > 0 ? plural(count, "tool change") : "No tool changes");

/** What the job takes, under its verdict: its tool changes and the controller its G-code is for ("1 tool change · grbl controller"). */
export function jobSummary(job) {
  if (!job.operations.length) return "";
  return [toolChangeWords(job.toolChanges.count), job.post ? `${job.post} controller` : ""].filter(Boolean).join(" · ");
}

/** An operation of the job by its index, or null. */
export const camOperation = (job, index) => job?.operations.find((op) => op.index === index) || null;

/** An operation row's detail: its tool and its time ("6 mm flat · 5 min"). */
export const operationDetail = (op) => [op.toolPlain, formatDuration(op.timeS)].filter(Boolean).join(" · ");
