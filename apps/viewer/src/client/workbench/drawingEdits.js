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

// --- snapping: the sheet's own line work is what a dimension attaches to -----------

function distancePointToSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  const t = lengthSq > 0 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq)) : 0;
  const q = [a[0] + t * dx, a[1] + t * dy];
  return { distance: Math.hypot(p[0] - q[0], p[1] - q[1]), point: q, t };
}

/** Line work a dimension can attach to: a view's edges and holes, never its annotation.
 *  The sheet's existing dimensions are targets too, so one can be picked to tolerance
 *  or remove it. */
export function sheetSnapTargets(geometry, sheetDimensions = []) {
  const lines = (Array.isArray(geometry?.lines) ? geometry.lines : [])
    .filter((line) => line.view && line.dim === undefined && !/^(SHEET|TITLE|NOTES|DIM|CENTER)$/i.test(String(line.layer || "")));
  const circles = (Array.isArray(geometry?.circles) ? geometry.circles : [])
    .filter((circle) => circle.view && circle.dim === undefined);
  const allArcs = (Array.isArray(geometry?.arcs) ? geometry.arcs : []).filter((arc) => arc.view && arc.dim === undefined);
  const fullArcs = allArcs.filter((arc) => Math.abs(Number(arc.sweepAngleDeg)) >= 359);
  const partialArcs = allArcs.filter((arc) => Math.abs(Number(arc.sweepAngleDeg)) < 359);
  return {
    lines,
    circles: [...circles, ...fullArcs.map((arc) => ({ layer: arc.layer, view: arc.view, center: arc.center, radius: arc.radius }))],
    arcs: partialArcs,
    dimensions: (Array.isArray(sheetDimensions) ? sheetDimensions : [])
      .filter((dimension) => dimension?.view && dimension.index !== undefined && Array.isArray(dimension.position))
  };
}

/**
 * What the pointer is over, within `tolerance` sheet mm: a corner (line end), a
 * hole (circle, by its centre or its rim), or an edge (line). Corners win over
 * edges so a click near an end reads as the end. Null when nothing is close.
 */
/** The snap kinds a filter can name; all on unless the user narrows it. */
export const SNAP_KINDS = Object.freeze(["edge", "vertex", "midpoint", "circle", "dimension"]);

export function snapSheetPoint(targets, point, tolerance = 2, kinds = null) {
  if (!targets || !Array.isArray(point)) {
    return null;
  }
  const allowed = kinds ? new Set(kinds) : null;
  // Arcs ride with circles in the filter: both are "round features".
  const allow = (kind) => !allowed || allowed.has(kind === "arc" ? "circle" : kind);
  let best = null;
  const consider = (candidate) => {
    if (!allow(candidate.kind)) return;
    if (candidate.distance <= tolerance && (!best || candidate.rank < best.rank || (candidate.rank === best.rank && candidate.distance < best.distance))) {
      best = candidate;
    }
  };
  // An existing dimension is picked by its text; the text is a few mm wide, so it
  // gets a little more reach than a corner.
  for (const dimension of targets.dimensions || []) {
    const distance = Math.hypot(point[0] - dimension.position[0], point[1] - dimension.position[1]);
    if (distance <= tolerance * 1.6) {
      consider({ kind: "dimension", rank: -1, distance: Math.min(distance, tolerance), point: dimension.position, view: dimension.view, index: dimension.index, value: dimension.value });
    }
  }
  for (const circle of targets.circles || []) {
    const toCentre = Math.hypot(point[0] - circle.center[0], point[1] - circle.center[1]);
    const toRim = Math.abs(toCentre - circle.radius);
    consider({ kind: "circle", rank: 0, distance: Math.min(toCentre, toRim), point: circle.center, view: circle.view, circle });
  }
  for (const arc of targets.arcs || []) {
    // On the arc's curve, within its sweep: a radius target.
    const dx = point[0] - arc.center[0];
    const dy = point[1] - arc.center[1];
    const toCentre = Math.hypot(dx, dy);
    const angle = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360;
    const start = ((Number(arc.startAngleDeg) % 360) + 360) % 360;
    const sweep = Number(arc.sweepAngleDeg);
    const rel = sweep >= 0 ? (angle - start + 360) % 360 : (start - angle + 360) % 360;
    if (rel <= Math.abs(sweep)) {
      consider({ kind: "arc", rank: 0.5, distance: Math.abs(toCentre - arc.radius), point: [arc.center[0] + (dx / (toCentre || 1)) * arc.radius, arc.center[1] + (dy / (toCentre || 1)) * arc.radius], view: arc.view, arc });
    }
  }
  for (const line of targets.lines || []) {
    for (const end of [line.start, line.end]) {
      consider({ kind: "vertex", rank: 1, distance: Math.hypot(point[0] - end[0], point[1] - end[1]), point: end, view: line.view, line });
    }
    const mid = [(line.start[0] + line.end[0]) / 2, (line.start[1] + line.end[1]) / 2];
    consider({ kind: "midpoint", rank: 1.5, distance: Math.hypot(point[0] - mid[0], point[1] - mid[1]), point: mid, view: line.view, line });
    const along = distancePointToSegment(point, line.start, line.end);
    consider({ kind: "edge", rank: 2, distance: along.distance, point: along.point, view: line.view, line });
  }
  return best;
}

/** The staged dimension's sheet geometry. Without a placement the offset lands outside
 *  the nearer view edge; with one (the click that places it) the dimension line goes
 *  through that point. */
/** Standard dimension rows sit this far apart outside a view; placement snaps to them. */
export const DIMENSION_ROW_MM = 12;
const ROW_SNAP_MM = 3;

function snapToRow(value, edge, direction) {
  // direction +1: rows at edge + 12k above/right; -1: below/left.
  const distance = (value - edge) * direction;
  if (distance <= 0) return value;
  const k = Math.round(distance / DIMENSION_ROW_MM);
  if (k < 1) return value;
  const row = edge + direction * k * DIMENSION_ROW_MM;
  return Math.abs(row - value) <= ROW_SNAP_MM ? row : value;
}

export function draftDimensionFromPicks(view, a, b, placement = null, orientationHint = null) {
  const dx = Math.abs(b[0] - a[0]);
  const dy = Math.abs(b[1] - a[1]);
  let orientation = orientationHint || (dx >= dy ? "h" : "v");
  if (!orientationHint && placement && dx > 1e-6 && dy > 1e-6) {
    // A diagonal pair reads from where the pointer went: beyond the points above or
    // below means horizontal, beside them means vertical; inside, the longer span.
    const [x0, x1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
    const [y0, y1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
    const outsideX = placement[0] < x0 || placement[0] > x1;
    const outsideY = placement[1] < y0 || placement[1] > y1;
    if (outsideY && !outsideX) orientation = "h";
    else if (outsideX && !outsideY) orientation = "v";
    else if (outsideX && outsideY) orientation = Math.min(placement[0] - x0, x1 - placement[0]) < Math.min(placement[1] - y0, y1 - placement[1]) ? "v" : "h";
  }
  let offset = 12;
  if (placement) {
    if (orientation === "h") {
      const top = Math.max(a[1], b[1]);
      const bottom = Math.min(a[1], b[1]);
      let y = placement[1];
      if (view) y = y >= (top + bottom) / 2 ? snapToRow(y, view.maxY, 1) : snapToRow(y, view.minY, -1);
      offset = y >= (top + bottom) / 2 ? Math.max(y - top, 4) : -Math.max(bottom - y, 4);
    } else {
      const right = Math.max(a[0], b[0]);
      const left = Math.min(a[0], b[0]);
      let x = placement[0];
      if (view) x = x >= (right + left) / 2 ? snapToRow(x, view.maxX, 1) : snapToRow(x, view.minX, -1);
      offset = x >= (right + left) / 2 ? Math.max(x - right, 4) : -Math.max(left - x, 4);
    }
  } else if (view) {
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

function angleDegFrom(centre, point) {
  return Math.round((((Math.atan2(point[1] - centre[1], point[0] - centre[0]) * 180) / Math.PI + 360) % 360) * 10) / 10;
}

function lineDirection(line) {
  const dx = line.end[0] - line.start[0];
  const dy = line.end[1] - line.start[1];
  const length = Math.hypot(dx, dy) || 1;
  return [dx / length, dy / length];
}

function footOnLine(point, line) {
  const d = lineDirection(line);
  const t = (point[0] - line.start[0]) * d[0] + (point[1] - line.start[1]) * d[1];
  return [line.start[0] + t * d[0], line.start[1] + t * d[1]];
}

/** A snap as the point it stands for in a two-pick dimension: corners and midpoints
 *  are themselves, a circle or arc is its centre. Edges have no single point. */
function snapPoint(snap) {
  if (snap.kind === "circle") return snap.circle.center;
  if (snap.kind === "arc") return snap.arc.center;
  if (snap.kind === "vertex" || snap.kind === "midpoint") return snap.point;
  return null;
}

/**
 * What a set of smart picks means, the way SolidWorks reads them:
 *   edge -> its length; circle -> diameter; arc -> radius;
 *   point + point -> distance; point + edge -> perpendicular distance;
 *   parallel edges -> distance between; edges at an angle -> the angle;
 *   a circle or arc in a pair stands for its centre.
 * `placement` is where the user clicked to put the dimension; without it a sensible
 * default is chosen. Returns an edit body (without id) or null when the picks do not
 * yet make a dimension (a lone corner).
 */
export function smartDimensionFromSnaps(view, snaps, placement = null) {
  if (!Array.isArray(snaps) || !snaps.length) {
    return null;
  }
  const [first, second] = snaps;
  if (snaps.length === 1) {
    if (first.kind === "circle") {
      const c = first.circle.center;
      return { kind: "dia", view: first.view, cx: c[0], cy: c[1], r: first.circle.radius, angle: placement ? angleDegFrom(c, placement) : 45 };
    }
    if (first.kind === "arc") {
      const c = first.arc.center;
      return { kind: "rad", view: first.view, cx: c[0], cy: c[1], r: first.arc.radius, angle: placement ? angleDegFrom(c, placement) : 45 };
    }
    if (first.kind === "edge") {
      return { kind: "dim", view: first.view, ...draftDimensionFromPicks(view, first.line.start, first.line.end, placement) };
    }
    return null;
  }
  const pa = snapPoint(first);
  const pb = snapPoint(second);
  if (pa && pb) {
    return { kind: "dim", view: first.view, ...draftDimensionFromPicks(view, pa, pb, placement) };
  }
  const point = pa || pb;
  const edgeSnap = first.kind === "edge" ? first : second.kind === "edge" ? second : null;
  if (point && edgeSnap) {
    const foot = footOnLine(point, edgeSnap.line);
    const d = lineDirection(edgeSnap.line);
    const hint = Math.abs(d[1]) > Math.abs(d[0]) ? "h" : "v"; // a vertical edge: measure horizontally
    return { kind: "dim", view: first.view, ...draftDimensionFromPicks(view, point, foot, placement, hint) };
  }
  if (first.kind === "edge" && second.kind === "edge") {
    const da = lineDirection(first.line);
    const db = lineDirection(second.line);
    const cross = Math.abs(da[0] * db[1] - da[1] * db[0]);
    if (cross < 0.02) {
      const mid = [(first.line.start[0] + first.line.end[0]) / 2, (first.line.start[1] + first.line.end[1]) / 2];
      const foot = footOnLine(mid, second.line);
      const hint = Math.abs(da[1]) > Math.abs(da[0]) ? "h" : "v";
      return { kind: "dim", view: first.view, ...draftDimensionFromPicks(view, mid, foot, placement, hint) };
    }
    // Two lines at an angle: the angle at their intersection, measured between the
    // ends of each line that lie away from it.
    const [x1, y1] = first.line.start; const [x2, y2] = first.line.end;
    const [x3, y3] = second.line.start; const [x4, y4] = second.line.end;
    const den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
    if (Math.abs(den) < 1e-9) return null;
    const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den;
    const vertex = [x1 + t * (x2 - x1), y1 + t * (y2 - y1)];
    const far = (line) => (Math.hypot(line.start[0] - vertex[0], line.start[1] - vertex[1]) >= Math.hypot(line.end[0] - vertex[0], line.end[1] - vertex[1]) ? line.start : line.end);
    const a = far(first.line);
    const b = far(second.line);
    const r = placement ? Math.max(Math.hypot(placement[0] - vertex[0], placement[1] - vertex[1]), 6) : 14;
    return { kind: "ang", view: first.view, vx: vertex[0], vy: vertex[1], ax: a[0], ay: a[1], bx: b[0], by: b[1], r: round(r) };
  }
  return null;
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
  const circular = (kind) => (edits || []).filter((edit) => edit.kind === kind).map((edit) => {
    const shift = moves.find(([view]) => view === edit.view)?.[1] || [0, 0];
    return [edit.cx + shift[0], edit.cy + shift[1], edit.r, edit.angle ?? 45].map(fmt).join(",");
  }).join(";");
  const dia = circular("dia");
  if (dia) params.dia = dia;
  const rad = circular("rad");
  if (rad) params.rad = rad;
  const angles = (edits || []).filter((edit) => edit.kind === "ang");
  if (angles.length) {
    params.ang = angles.map((edit) => {
      const shift = moves.find(([view]) => view === edit.view)?.[1] || [0, 0];
      return [edit.vx + shift[0], edit.vy + shift[1], edit.ax + shift[0], edit.ay + shift[1], edit.bx + shift[0], edit.by + shift[1], edit.r].map(fmt).join(",");
    }).join(";");
  }
  const removals = (edits || []).filter((edit) => edit.kind === "del");
  if (removals.length) {
    params.del = removals.map((edit) => `${edit.view}:${edit.index}`).join(";");
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
  if (edit.kind === "ang") {
    const v = sheetToModel(view, [edit.vx, edit.vy]);
    const a = sheetToModel(view, [edit.ax, edit.ay]);
    const b = sheetToModel(view, [edit.bx, edit.by]);
    if (v && a && b) {
      const tuple = (p) => `(${fmt(p[0])}, ${fmt(p[1])}, ${fmt(p[2])})`;
      return `${edit.view}.angle(${tuple(v)}, ${tuple(a)}, ${tuple(b)}, offset=${fmt(edit.r)})  # model mm; the coordinate along the view's line of sight is 0`;
    }
    return `${edit.view}: add an angular dimension at sheet (${fmt(edit.vx)}, ${fmt(edit.vy)}) between the edges toward (${fmt(edit.ax)}, ${fmt(edit.ay)}) and (${fmt(edit.bx)}, ${fmt(edit.by)}).`;
  }
  if (edit.kind === "dia") {
    const centre = sheetToModel(view, [edit.cx, edit.cy]);
    if (centre) {
      const angle = edit.angle != null && edit.angle !== 45 ? `, angle=${fmt(edit.angle)}` : "";
      return `${edit.view}.hole((${fmt(centre[0])}, ${fmt(centre[1])}, ${fmt(centre[2])}), ${fmt(2 * edit.r)}, thru=True${angle})  # model mm; say depth=... instead of thru if it is blind`;
    }
    return `${edit.view}: add a diameter callout on the hole at sheet (${fmt(edit.cx)}, ${fmt(edit.cy)}), Ø${fmt(2 * edit.r)}.`;
  }
  if (edit.kind === "rad") {
    const centre = sheetToModel(view, [edit.cx, edit.cy]);
    if (centre) {
      const angle = edit.angle != null && edit.angle !== 45 ? `, angle=${fmt(edit.angle)}` : "";
      return `${edit.view}.radius((${fmt(centre[0])}, ${fmt(centre[1])}, ${fmt(centre[2])}), ${fmt(edit.r)}${angle})  # model mm; the coordinate along the view's line of sight is 0`;
    }
    return `${edit.view}: add a radius callout on the arc centred at sheet (${fmt(edit.cx)}, ${fmt(edit.cy)}), R${fmt(edit.r)}.`;
  }
  if (edit.kind === "del") {
    const dimension = dimensions.find((candidate) => candidate.view === edit.view && String(candidate.index) === String(edit.index)) || null;
    const reads = dimension?.value ? ` (reads ${dimension.value})` : "";
    if (/^overall/.test(String(edit.index))) {
      return `In the \`${edit.view}\` view, drop the overall ${edit.index === "overall-w" ? "width" : "height"}: replace overall() with an explicit dim() for the one that stays${reads}.`;
    }
    return `In the \`${edit.view}\` view, remove its ${ordinal(edit.index)} dim()/hole()/note() call${reads}.`;
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
