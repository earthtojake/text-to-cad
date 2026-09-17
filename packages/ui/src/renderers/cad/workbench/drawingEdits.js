/**
 * Drawing EDITS the viewer stages against a cadgen sheet.
 *
 * The sheet is a generated file and its script is the source, so the viewer
 * never writes the DXF. It stages edits (move a view, add a dimension, put a
 * tolerance on one), previews them through the server's SVG route, and hands
 * the agent the exact script change. Everything here is pure: sheet millimetres
 * in, query parameters and prompt text out.
 *
 * A view's `map` is the affine model->sheet map its label carries
 * (b, a0, a1, a2: eight numbers), so a sheet point can be turned back into the
 * two model coordinates the view shows; the third, along the line of sight, is
 * not on the sheet and is stated as 0, which projects to the same place.
 */

let nextEditId = 1;

export function createDrawingEditId() {
  nextEditId += 1;
  return `edit-${nextEditId}`;
}

function round(value, places = 2) {
  const factor = 10 ** places;
  return Math.round((Number(value) || 0) * factor) / factor;
}

function fmt(value) {
  const text = round(value).toFixed(2).replace(/\.?0+$/, "");
  return text === "-0" ? "0" : text || "0";
}

/** The model point a view shows at a sheet point: solve the two model axes whose
 *  sheet images span the view; the third is 0. Null without a map. */
export function sheetToModel(view, point) {
  const map = Array.isArray(view?.map) && view.map.length === 8 ? view.map : null;
  if (!map || !Array.isArray(point)) {
    return null;
  }
  const [bx, by] = map;
  const axes = [
    { index: 0, x: map[2], y: map[3] },
    { index: 1, x: map[4], y: map[5] },
    { index: 2, x: map[6], y: map[7] }
  ];
  const [u, v] = [...axes].sort((a, b) => Math.hypot(b.x, b.y) - Math.hypot(a.x, a.y));
  const det = u.x * v.y - u.y * v.x;
  if (!Number.isFinite(det) || Math.abs(det) < 1e-9) {
    return null;
  }
  const rx = point[0] - bx;
  const ry = point[1] - by;
  const s = (rx * v.y - ry * v.x) / det;
  const t = (u.x * ry - u.y * rx) / det;
  const model = [0, 0, 0];
  model[u.index] = s;
  model[v.index] = t;
  return model;
}

/** Which view a sheet point falls in, with a small margin for dimension lines. */
export function viewAtSheetPoint(views, point, margin = 4) {
  if (!Array.isArray(views) || !Array.isArray(point)) {
    return null;
  }
  return views.find((view) => (
    point[0] >= view.minX - margin && point[0] <= view.maxX + margin
    && point[1] >= view.minY - margin && point[1] <= view.maxY + margin
  )) || null;
}

/** The view nearest a sheet point (the one under it when there is one). */
export function nearestView(views, point) {
  const inside = viewAtSheetPoint(views, point);
  if (inside || !Array.isArray(views) || !views.length || !Array.isArray(point)) {
    return inside;
  }
  const distance = (view) => Math.hypot(
    Math.max(view.minX - point[0], 0, point[0] - view.maxX),
    Math.max(view.minY - point[1], 0, point[1] - view.maxY)
  );
  return [...views].sort((a, b) => distance(a) - distance(b))[0];
}

/** The staged dimension's sheet geometry, offset placed away from the nearer view edge. */
export function draftDimensionFromPicks(view, a, b) {
  const dx = Math.abs(b[0] - a[0]);
  const dy = Math.abs(b[1] - a[1]);
  const orientation = dx >= dy ? "h" : "v";
  let offset = 12;
  if (view) {
    if (orientation === "h") {
      const top = view.maxY - Math.max(a[1], b[1]);
      const bottom = Math.min(a[1], b[1]) - view.minY;
      offset = top <= bottom ? 12 + top : -(12 + bottom);
    } else {
      const right = view.maxX - Math.max(a[0], b[0]);
      const left = Math.min(a[0], b[0]) - view.minX;
      offset = right <= left ? 12 + right : -(12 + left);
    }
  }
  return { x1: a[0], y1: a[1], x2: b[0], y2: b[1], offset: round(offset), orientation };
}

/** Net move per view, in sheet mm, from the staged edits. */
export function netViewMoves(edits) {
  const moves = new Map();
  for (const edit of Array.isArray(edits) ? edits : []) {
    if (edit.kind !== "move") continue;
    const current = moves.get(edit.view) || [0, 0];
    moves.set(edit.view, [current[0] + edit.dx, current[1] + edit.dy]);
  }
  return moves;
}

/** The /__cad/drawing query parameters that preview the staged edits and the highlight. */
export function drawingEditParams(edits, { highlight = "" } = {}) {
  const params = {};
  const moves = [...netViewMoves(edits).entries()].filter(([, [dx, dy]]) => dx || dy);
  if (moves.length) {
    params.move = moves.map(([view, [dx, dy]]) => `${view}:${fmt(dx)},${fmt(dy)}`).join(";");
  }
  const drafts = (edits || []).filter((edit) => edit.kind === "dim");
  if (drafts.length) {
    params.dim = drafts.map((edit) => {
      const shift = moves.find(([view]) => view === edit.view)?.[1] || [0, 0];
      return [edit.x1 + shift[0], edit.y1 + shift[1], edit.x2 + shift[0], edit.y2 + shift[1], edit.offset].map(fmt)
        .concat(edit.orientation || "").join(",");
    }).join(";");
  }
  const tolerances = (edits || []).filter((edit) => edit.kind === "tol" && edit.spec);
  if (tolerances.length) {
    params.tol = tolerances.map((edit) => `${edit.view}:${edit.index}=${edit.spec}`).join(";");
  }
  if (highlight) {
    params.hl = highlight;
  }
  return params;
}

function ordinal(index) {
  const n = Number(index) + 1;
  if (!Number.isFinite(n)) return String(index);
  const suffix = n % 10 === 1 && n % 100 !== 11 ? "st" : n % 10 === 2 && n % 100 !== 12 ? "nd" : n % 10 === 3 && n % 100 !== 13 ? "rd" : "th";
  return `${n}${suffix}`;
}

/** The script line an edit asks for, in the drawing API's own words. */
export function drawingEditSnippet(edit, { views = [], dimensions = [] } = {}) {
  const view = views.find((candidate) => candidate.name === edit.view) || null;
  if (edit.kind === "move") {
    const at = view?.at ? [view.at[0] + edit.dx, view.at[1] + edit.dy] : null;
    return at
      ? `Move the \`${edit.view}\` view to at=(${fmt(at[0])}, ${fmt(at[1])}) (sheet mm; it was at (${fmt(view.at[0])}, ${fmt(view.at[1])})). If it came from three_views(), place it with sheet.view(part, "${edit.view}", at=(${fmt(at[0])}, ${fmt(at[1])})) instead.`
      : `Move the \`${edit.view}\` view by (${fmt(edit.dx)}, ${fmt(edit.dy)}) sheet mm.`;
  }
  if (edit.kind === "dim") {
    const p1 = sheetToModel(view, [edit.x1, edit.y1]);
    const p2 = sheetToModel(view, [edit.x2, edit.y2]);
    const orientation = edit.orientation ? `, orientation="${edit.orientation}"` : "";
    if (p1 && p2) {
      const tuple = (p) => `(${fmt(p[0])}, ${fmt(p[1])}, ${fmt(p[2])})`;
      return `${edit.view}.dim(${tuple(p1)}, ${tuple(p2)}, offset=${fmt(edit.offset)}${orientation})  # model mm; the coordinate along the view's line of sight is 0`;
    }
    return `${edit.view}: add a linear dimension between sheet points (${fmt(edit.x1)}, ${fmt(edit.y1)}) and (${fmt(edit.x2)}, ${fmt(edit.y2)}), offset=${fmt(edit.offset)}${orientation}.`;
  }
  if (edit.kind === "tol") {
    const dimension = dimensions.find((candidate) => candidate.view === edit.view && String(candidate.index) === String(edit.index)) || null;
    const which = /^overall/.test(String(edit.index))
      ? `the overall ${edit.index === "overall-w" ? "width" : "height"} from overall()`
      : `its ${ordinal(edit.index)} dim()/hole() call`;
    const reads = dimension?.value ? ` (reads ${dimension.value})` : "";
    const spec = String(edit.spec || "").trim();
    const arg = /^[+-]?\d*\.?\d+\/[+-]?\d*\.?\d+$/.test(spec)
      ? `tol=(${spec.split("/").map((v) => fmt(Math.abs(Number(v)))).join(", ")})`
      : /^±?\d*\.?\d+$/.test(spec) ? `tol=${fmt(Math.abs(Number(spec.replace("±", ""))))}` : `fit="${spec}"`;
    return `In the \`${edit.view}\` view, ${which}${reads}: add ${arg}.`;
  }
  return "";
}

/** The message that hands the staged edits to the agent. */
export function drawingEditsPromptText({ drawingPath = "", edits = [], views = [], dimensions = [] } = {}) {
  const staged = (edits || []).filter((edit) => drawingEditSnippet(edit, { views, dimensions }));
  if (!staged.length) {
    return "";
  }
  const lines = staged.map((edit) => `- ${drawingEditSnippet(edit, { views, dimensions })}`);
  const target = drawingPath ? `the script that writes ${drawingPath}` : "the drawing script";
  return [
    `Please make these changes to ${target} (the @drawing function) and rerun it so the DXF and PDF update:`,
    ...lines
  ].join("\n");
}
