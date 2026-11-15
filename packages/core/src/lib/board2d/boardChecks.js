/**
 * KiCad's design rule check of a board (`GET <board>/drc`, `client.boardDrc`: the `CheckResult`
 * `cad kicad_pcb drc --json` prints, `docs/plot-payload.md`), as the board's view reads it: whether the
 * board passes, the counts behind that, and every finding with where it is and what it is between, in the
 * board index's own terms (`boardIndex.js`): its place in PAGE millimetres (the payload's is KiCad's
 * frame, which `index.toPage` maps, the inverse of the `toScript` a copied point is written in), and its
 * items as the selectors the index resolves, so a finding is picked as anything else on the board is.
 *
 * A board fails on an error, a missing connection or a difference from its schematic, the last two
 * whatever severity KiCad gave them (`cad.kicad._check.fails`'s rule); a warning does not, nor does an
 * exclusion the board's project records (`excluded: true`, or an older KiCad's `exclusion` severity),
 * which is listed apart. A check that judged nothing — no KiCad, a board KiCad refused — is
 * `notChecked` with the reason: no verdict, and never a pass.
 *
 * Pure: no canvas, no DOM.
 */

const EMPTY = Object.freeze([]);
/** The groups a finding is listed in, in their order: what fails the board, what does not, what was excluded. */
export const BOARD_CHECK_GROUPS = Object.freeze(["error", "warning", "excluded"]);
// What a finding with a place frames: this far round it (millimetres), with the items it is between that
// are no larger than `ITEM_MM` (a track's end, a via, a pad, a small part: a pour or a long track would
// frame the whole board instead of the fault).
const WINDOW_MM = 3;
const ITEM_MM = 12;

const text = (value) => (typeof value === "string" ? value : "");
const xy = (value) => (Array.isArray(value) && value.length >= 2 && Number.isFinite(value[0]) && Number.isFinite(value[1]) ? [value[0], value[1]] : null);
const united = (boxes) => (boxes.length ? [Math.min(...boxes.map((box) => box[0])), Math.min(...boxes.map((box) => box[1])),
  Math.max(...boxes.map((box) => box[2])), Math.max(...boxes.map((box) => box[3]))] : null);

function groupOf(entry) {
  if (entry.excluded === true || entry.severity === "exclusion") return "excluded";
  if (entry.severity === "error" || entry.check === "unconnected" || entry.check === "parity") return "error";
  return entry.severity === "warning" ? "warning" : "note";
}

function findingOf(entry, order, index) {
  const items = (Array.isArray(entry.items) ? entry.items : EMPTY).filter((item) => item && typeof item === "object").map((item) => ({
    description: text(item.description), selector: (text(item.ref) && index?.resolve(item.ref)?.selector) || "", pos: xy(item.pos),
  }));
  // Where it is, in KiCad's frame: its own place, else its first item's.
  const script = xy(entry.at) || items.find((item) => item.pos)?.pos || null;
  const at = script && index ? index.toPage(script) : null;
  const selectors = [...new Set(items.map((item) => item.selector).filter(Boolean))];
  // What a press on it selects: its items; a finding with a place and no item the board names (a copper
  // sliver), the place itself, as a point reference.
  const picks = selectors.length ? selectors : at ? [index.pointSelector(at)] : EMPTY;
  const boxes = index ? picks.map((selector) => index.extent(index.resolve(selector))).filter(Boolean) : EMPTY;
  const near = boxes.filter((box) => box[2] - box[0] <= ITEM_MM && box[3] - box[1] <= ITEM_MM);
  const box = at ? united([[at[0] - WINDOW_MM, at[1] - WINDOW_MM, at[0] + WINDOW_MM, at[1] + WINDOW_MM], ...near]) : united(boxes);
  return {
    id: `check:${order}`, group: groupOf(entry), check: text(entry.check) || "violation", severity: text(entry.severity), type: text(entry.type),
    description: text(entry.description) || text(entry.type), comment: text(entry.comment), at, script, box,
    items: items.map(({ description, selector }) => ({ description, selector })), picks,
  };
}

const NOT_CHECKED = Object.freeze({ errors: 0, unconnected: 0, warnings: 0, excluded: 0 });
const notChecked = (reason) => ({ state: "notChecked", verdict: null, reason, counts: NOT_CHECKED, failing: 0, findings: EMPTY, notes: EMPTY });

/**
 * @param {object | null} payload  The route's answer (`CadBoardDrc`).
 * @param {ReturnType<typeof import("./boardIndex.js").createBoardIndex> | null} index
 * @returns {{ state: "checked" | "notChecked", verdict: "pass" | "fail" | null, reason: string,
 *   counts: { errors: number, unconnected: number, warnings: number, excluded: number }, failing: number,
 *   findings: { id: string, group: "error" | "warning" | "excluded", check: string, severity: string, type: string,
 *     description: string, comment: string, at: [number, number] | null, script: [number, number] | null,
 *     box: [number, number, number, number] | null, items: { description: string, selector: string }[], picks: readonly string[] }[],
 *   notes: { code: string, message: string }[] }}
 *   `at`: page millimetres (null: KiCad gave no place); `script`: the same place in KiCad's frame; `box`: the
 *   page box a zoom to it frames (null: nothing to frame); `picks`: what a press on it selects; `notes`: what
 *   the check said beside its findings (no project beside the board, no schematic to compare with).
 */
export function boardChecks(payload, index = null) {
  if (!payload || typeof payload !== "object") return notChecked("");
  const said = Array.isArray(payload.findings) ? payload.findings.filter((finding) => finding && typeof finding === "object") : EMPTY;
  const entries = payload.measurements?.drc;
  if (payload.status === "not_checked" || !Array.isArray(entries)) {
    return notChecked(text(said.find((finding) => finding.severity === "error")?.message) || text(said[0]?.message) || text(payload.reason) || text(payload.summary));
  }
  const listed = entries.filter((entry) => entry && typeof entry === "object").map((entry, order) => findingOf(entry, order, index));
  // What the check said that is no entry of KiCad's report: an error fails the board as any other, the rest are notes.
  const types = new Set(listed.map((finding) => finding.type));
  const beside = said.filter((finding) => !types.has(text(finding.code)));
  const extra = beside.filter((finding) => finding.severity === "error").map((finding, order) => findingOf(
    { check: "violation", severity: "error", type: text(finding.code), description: text(finding.message) }, listed.length + order, index));
  const all = [...listed, ...extra];
  const notes = [...beside.filter((finding) => finding.severity !== "error").map((finding) => ({ code: text(finding.code), message: text(finding.message) })),
    ...all.filter((finding) => finding.group === "note").map((finding) => ({ code: finding.type, message: finding.description }))].filter((note) => note.message);
  const findings = BOARD_CHECK_GROUPS.flatMap((group) => all.filter((finding) => finding.group === group));
  const failed = findings.filter((finding) => finding.group === "error");
  const counts = {
    errors: failed.filter((finding) => finding.check !== "unconnected").length,
    unconnected: failed.filter((finding) => finding.check === "unconnected").length,
    warnings: findings.filter((finding) => finding.group === "warning").length,
    excluded: findings.filter((finding) => finding.group === "excluded").length,
  };
  // The verdict is the check's own (`ok`), which the counts agree with: its rule is the grouping's.
  const verdict = (typeof payload.ok === "boolean" ? !payload.ok : failed.length > 0) ? "fail" : "pass";
  // A board the check fails with nothing of its own listed says why in its summary.
  return { state: "checked", verdict, reason: verdict === "fail" && !failed.length ? text(payload.summary) : "", counts, failing: failed.length, findings, notes };
}

/** Where a failing board's failing findings are, once each: the page points its view marks (`boardCheckMarks.js`). */
export function boardCheckMarks(checks) {
  const seen = new Set();
  return (checks?.verdict === "fail" ? checks.findings : EMPTY).filter((finding) => finding.group === "error" && finding.at)
    .filter((finding) => { const key = finding.at.join(","); return !seen.has(key) && seen.add(key); }).map((finding) => finding.at);
}

/** A finding's description without the figures KiCad ends it with: `Clearance violation`, for a chip's few words. */
export function boardCheckTitle(finding) {
  return finding.description.replace(/\s*\([^()]*\)\s*$/, "") || finding.description;
}

const number = (value) => String(Number(value.toFixed(4)));

/**
 * A finding as one line an agent reads beside its items' references: `cad kicad_pcb drc`'s own line for it
 * (`CheckFinding.human_line` over `cad.kicad._check.issues`: the check's severity — `error` for one that
 * fails the board, `info` for an excluded one — KiCad's rule name, its place in KiCad's millimetres, its
 * description, then its items in KiCad's words), led by `DRC`.
 */
export function boardCheckText(finding) {
  const severity = finding.group === "excluded" ? "info" : finding.group === "error" ? "error" : finding.severity || finding.group;
  const place = finding.script ? ` at (${number(finding.script[0])}, ${number(finding.script[1])}) mm` : "";
  const items = finding.items.map((item) => item.description).filter(Boolean).join("; ");
  const excluded = finding.group === "excluded" ? ` (excluded in the project${finding.comment ? `: ${finding.comment}` : ""})` : "";
  return `DRC ${severity}: ${finding.type}${place}: ${finding.description}${items ? `: ${items}` : ""}${excluded}`;
}
