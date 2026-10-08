/**
 * A board's index (`payload.board` of a KiCad board's plot), made ready to point at: what is under a
 * point of the picture, the board reference a person hands the agent for it, and back again from a
 * reference to what it names.
 *
 * Geometry arrives in SHEET coordinates (millimetres, y down, the plot sheet's corner) — every
 * point of it, a part's and a pad's place included — and is kept in PAGE coordinates (the sheet's
 * place in the laid-out plot added: `layoutPlot`), the frame the view's transform maps to the
 * screen. What a person or an agent reads is in SCRIPT coordinates (`toScript`): millimetres, y
 * up, from the board's drill/place origin (`index.origin`, in sheet coordinates), the frame
 * `board.place` and the build's checks speak.
 *
 * Pure: no canvas, no DOM. The viewer picks with it on every pointer move, so what is near a point
 * is found through a grid of the board (`spatialGrid.js`): a board of tens of thousands of pads
 * and tracks answers a pick in a few cells' worth of tests.
 */
import { formatBoardRefSelector, parseBoardRefSelector } from "../boardRefs.js";
import { boxOf, createSpatialGrid, nearBox } from "./spatialGrid.js";

/** How a pick is filtered: the Select tool's modes. */
export const BOARD_PICK_MODES = Object.freeze(["all", "parts", "pads", "nets"]);

const EMPTY = Object.freeze([]);
const point = (value) => (Array.isArray(value) && value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))
  ? [Number(value[0]), Number(value[1])] : null);

/** Whether `[x, y]` lies inside a closed polygon (even-odd). */
export function pointInPolygon([x, y], polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The nearest point of segment ab to p, and its distance. */
export function nearestOnSegment([px, py], [ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const length = dx * dx + dy * dy;
  const t = length > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length)) : 0;
  const nearest = [ax + t * dx, ay + t * dy];
  return { point: nearest, distance: Math.hypot(px - nearest[0], py - nearest[1]) };
}

function nearestOnPolyline(p, points) {
  let best = null;
  for (let index = 1; index < points.length; index += 1) {
    const candidate = nearestOnSegment(p, points[index - 1], points[index]);
    if (!best || candidate.distance < best.distance) best = candidate;
  }
  return best || (points[0] ? { point: points[0], distance: Math.hypot(p[0] - points[0][0], p[1] - points[0][1]) } : null);
}

/** How far `at` is from a closed polygon's edge (0 inside it). */
function polygonReach(at, polygon) {
  if (pointInPolygon(at, polygon)) return 0;
  let distance = Infinity;
  for (let i = 0; i < polygon.length; i += 1) {
    distance = Math.min(distance, nearestOnSegment(at, polygon[i], polygon[(i + 1) % polygon.length]).distance);
  }
  return distance;
}

/** A polygon's area (shoelace), for preferring the smallest of overlapping shapes. */
export function polygonArea(polygon) {
  let sum = 0;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) sum += polygon[j][0] * polygon[i][1] - polygon[i][0] * polygon[j][1];
  return Math.abs(sum) / 2;
}

function bounds(points) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  }
  return [minX, minY, maxX, maxY];
}

function centre(polygon) {
  if (!polygon.length) return null;
  const [minX, minY, maxX, maxY] = bounds(polygon);
  return [(minX + maxX) / 2, (minY + maxY) / 2];
}

// Copper on the side a view looks at comes first: a top view picks the top's pad over the bottom's.
function layerSide(layer) {
  if (typeof layer !== "string") return "both";
  if (layer.startsWith("F.")) return "front";
  if (layer.startsWith("B.")) return "back";
  return "inner";
}
function facing(side, view) {
  if (side === "both" || side === "top-bottom") return 0;
  const front = side === "front" || side === "top";
  const back = side === "back" || side === "bottom";
  if (view === "bottom") return back ? 0 : front ? 2 : 1;
  return front ? 0 : back ? 2 : 1;
}

const round2 = (value) => Math.round(value * 100) / 100;

/**
 * @param {object} board  The payload's `board`.
 * @param {{ x?: number, y?: number }} [sheet]  The board sheet's place in the plot layout (page mm).
 */
export function createBoardIndex(board, sheet = {}) {
  const sheetX = Number(sheet.x) || 0;
  const sheetY = Number(sheet.y) || 0;
  const page = (value) => {
    const p = point(value);
    return p ? [p[0] + sheetX, p[1] + sheetY] : null;
  };
  const pageList = (values) => (Array.isArray(values) ? values.map(page).filter(Boolean) : []);
  const origin = point(board?.origin) || [0, 0];
  const toScript = ([x, y]) => [x - sheetX - origin[0], origin[1] + sheetY - y];
  const toPage = ([x, y]) => [x + origin[0] + sheetX, origin[1] + sheetY - y];

  const nets = new Map();
  const netNamed = (name) => {
    const key = String(name ?? "");
    if (!key) return null;
    let net = nets.get(key);
    if (!net) {
      net = { kind: "net", name: key, class: "", pads: [], tracks: [], vias: [], zones: [] };
      nets.set(key, net);
    }
    return net;
  };
  for (const entry of board?.nets || EMPTY) {
    const net = netNamed(entry?.name);
    if (net) net.class = String(entry?.class || "");
  }

  const parts = new Map();
  for (const entry of board?.parts || EMPTY) {
    const ref = String(entry?.ref || "");
    if (!ref) continue;
    const outline = pageList(entry.outline);
    parts.set(ref, {
      kind: "part", ref, value: String(entry.value ?? ""), footprint: String(entry.footprint ?? ""),
      side: entry.side === "bottom" ? "bottom" : "top", at: page(entry.at) || [sheetX, sheetY], rotation: Number(entry.rotation) || 0,
      fields: entry.fields && typeof entry.fields === "object" ? { ...entry.fields } : {}, script: entry.script ? String(entry.script) : "",
      dnp: Boolean(entry.dnp), outline, area: outline.length > 2 ? polygonArea(outline) : Infinity, box: outline.length > 2 ? boxOf(outline) : null, pads: []
    });
  }

  const pads = new Map();
  const padShapes = [];
  // Each pin's pads, by `U3.9`: a pin is drawn and picked as all of them.
  const shapesByPin = new Map();
  for (const entry of board?.pads || EMPTY) {
    const part = parts.get(String(entry?.part || ""));
    const number = String(entry?.number ?? "");
    if (!part || !number) continue;
    const polygon = pageList(entry.polygon);
    const pad = {
      kind: "pad", ref: part.ref, number, name: String(entry.name ?? ""), net: String(entry.net ?? ""), type: String(entry.type ?? ""), drill: Number(entry.drill) || 0,
      side: entry.side === "both" ? "both" : entry.side === "bottom" ? "bottom" : "top", at: page(entry.at) || centre(polygon) || part.at, polygon,
      area: polygon.length > 2 ? polygonArea(polygon) : 0, box: polygon.length > 2 ? boxOf(polygon) : null, part
    };
    // A pad repeated under one number (a tab, a USB-C's stacked pads) is one pin: its first pad names it.
    const key = `${part.ref}.${number}`;
    padShapes.push(pad);
    part.pads.push(pad);
    if (pads.has(key)) { shapesByPin.get(key).push(pad); continue; }
    pads.set(key, pad);
    shapesByPin.set(key, [pad]);
    netNamed(pad.net)?.pads.push(pad);
  }

  const tracks = (board?.tracks || EMPTY).map((entry) => {
    const width = Number(entry?.width) || 0;
    const points = pageList(entry?.points);
    return { kind: "track", net: String(entry?.net ?? ""), layer: String(entry?.layer ?? ""), width, points, box: boxOf(points, width / 2) };
  }).filter((track) => track.points.length > 1);
  const vias = (board?.vias || EMPTY).map((entry) => {
    const at = page(entry?.at);
    const diameter = Number(entry?.diameter) || 0;
    return { kind: "via", net: String(entry?.net ?? ""), at, diameter, drill: Number(entry?.drill) || 0, box: at ? boxOf([at], diameter / 2) : null };
  }).filter((via) => via.at);
  const zones = (board?.zones || EMPTY).map((entry) => {
    const outline = pageList(entry?.outline);
    return { kind: "zone", net: String(entry?.net ?? ""), layer: String(entry?.layer ?? ""), outline, area: outline.length > 2 ? polygonArea(outline) : Infinity,
      box: boxOf(outline) };
  }).filter((zone) => zone.outline.length > 2);
  for (const track of tracks) netNamed(track.net)?.tracks.push(track);
  for (const via of vias) netNamed(via.net)?.vias.push(via);
  for (const zone of zones) netNamed(zone.net)?.zones.push(zone);

  const holes = (board?.holes || EMPTY).map((entry) => ({ at: page(entry?.at), diameter: Number(entry?.diameter) || 0 })).filter((hole) => hole.at);
  const outline = (board?.outline || EMPTY).map(pageList).filter((line) => line.length > 1);
  const findings = (board?.findings || EMPTY).map((entry, index) => ({
    kind: "finding", index, check: String(entry?.check ?? ""), severity: String(entry?.severity ?? ""), type: String(entry?.type ?? ""),
    description: String(entry?.description ?? ""), summary: String(entry?.summary || entry?.description || ""),
    items: (entry?.items || EMPTY).map((item) => ({ text: String(item?.text ?? ""), ref: item?.ref ? String(item.ref) : "", at: page(item?.at) }))
  }));

  // ---- what is near a point --------------------------------------------------
  const padGrid = createSpatialGrid(padShapes.map((shape) => (shape.polygon.length > 2 ? shape.box : null)));
  const viaGrid = createSpatialGrid(vias.map((via) => via.box));
  const trackGrid = createSpatialGrid(tracks.map((track) => track.box));
  const parted = [...parts.values()];
  const partGrid = createSpatialGrid(parted.map((part) => part.box));
  const zoneGrid = createSpatialGrid(zones.map((zone) => zone.box));
  // What a measurement snaps to, in the order it prefers them when two are as near: pad centres
  // (a pin's first pad), via centres, track ends, holes, then the outline's corners.
  const snapTargets = [];
  for (const pad of pads.values()) snapTargets.push({ at: pad.at, kind: "pad", group: "pads", item: pad });
  for (const via of vias) snapTargets.push({ at: via.at, kind: "via", group: "copper", item: via });
  for (const track of tracks) {
    snapTargets.push({ at: track.points[0], kind: "track", group: "copper", item: track });
    snapTargets.push({ at: track.points[track.points.length - 1], kind: "track", group: "copper", item: track });
  }
  for (const hole of holes) snapTargets.push({ at: hole.at, kind: "hole", group: "outline", item: hole });
  for (const line of outline) for (const corner of line) snapTargets.push({ at: corner, kind: "outline", group: "outline", item: null });
  const snapGrid = createSpatialGrid(snapTargets.map((target) => [target.at[0], target.at[1], target.at[0], target.at[1]]));

  // ---- picking ---------------------------------------------------------------
  /**
   * What is under page point `at`, as a hit `{ kind, selector, ... }`, or null.
   * `mode`: all | parts | pads | nets. `view`: the side looked at (top | bottom). `tolerance`: page
   * millimetres a small thing may be missed by (a few screen pixels at the view's scale).
   */
  function pick(at, { mode = "all", view = "top", tolerance = 0 } = {}) {
    if (!point(at)) return null;
    const reach = Math.max(0, Number(tolerance) || 0);
    const [x, y] = at;
    const candidates = [];
    const wantPads = mode === "all" || mode === "pads" || mode === "nets";
    const wantCopper = mode === "all" || mode === "nets";
    const wantParts = mode === "all" || mode === "parts";
    if (wantPads) {
      padGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const shape = padShapes[order];
        if (!nearBox(shape.box, at, reach)) return;
        const near = reach > 0 ? polygonReach(at, shape.polygon) : pointInPolygon(at, shape.polygon) ? 0 : Infinity;
        // Any pad of a pin picks the pin: its first pad names it.
        if (near <= reach) candidates.push({ rank: 0, side: facing(shape.side, view), size: shape.area, distance: near, order, hit: { kind: "pad", pad: pads.get(`${shape.ref}.${shape.number}`) } });
      });
    }
    if (wantCopper) {
      viaGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const via = vias[order];
        const distance = Math.hypot(x - via.at[0], y - via.at[1]) - via.diameter / 2;
        if (distance <= reach) candidates.push({ rank: 1, side: 0, size: via.diameter, distance: Math.max(0, distance), order, hit: { kind: "via", via, at: via.at } });
      });
      trackGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const track = tracks[order];
        if (!nearBox(track.box, at, reach)) return;
        const nearest = nearestOnPolyline(at, track.points);
        if (nearest && nearest.distance - track.width / 2 <= reach) {
          candidates.push({ rank: 2, side: facing(layerSide(track.layer), view), size: track.width, distance: Math.max(0, nearest.distance - track.width / 2), order, hit: { kind: "track", track, at: nearest.point } });
        }
      });
    }
    if (wantParts) {
      partGrid.visit(x, y, x, y, (order) => {
        const part = parted[order];
        if (nearBox(part.box, at, 0) && pointInPolygon(at, part.outline)) {
          candidates.push({ rank: mode === "parts" ? 0 : 3, side: facing(part.side, view), size: part.area, distance: 0, order, hit: { kind: "part", part } });
        }
      });
    }
    // A pour is picked only for its net: under All, a press on bare board (inside a ground pour,
    // as most of a board is) clears the selection rather than taking the pour.
    if (mode === "nets") {
      zoneGrid.visit(x, y, x, y, (order) => {
        const zone = zones[order];
        if (nearBox(zone.box, at, 0) && pointInPolygon(at, zone.outline)) candidates.push({ rank: 4, side: facing(layerSide(zone.layer), view), size: zone.area, distance: 0, order, hit: { kind: "zone", zone, at } });
      });
    }
    // The facing side first, then the most specific kind, then the nearest, then the smallest; and
    // past one that names nothing (copper on no net) to the next.
    candidates.sort((a, b) => a.side - b.side || a.rank - b.rank || a.distance - b.distance || a.size - b.size || a.order - b.order);
    for (const candidate of candidates) {
      const found = describeHit(candidate.hit, mode, at);
      if (found) return found;
    }
    return null;
  }

  function describeHit(hit, mode, at) {
    if (mode === "nets") {
      const name = hit.pad?.net ?? hit.via?.net ?? hit.track?.net ?? hit.zone?.net ?? "";
      const net = nets.get(name);
      return net ? { kind: "net", net, selector: formatBoardRefSelector({ kind: "net", net: net.name }) } : null;
    }
    if (hit.kind === "pad") return { kind: "pad", pad: hit.pad, selector: formatBoardRefSelector({ kind: "pad", ref: hit.pad.ref, pad: hit.pad.number }) };
    if (hit.kind === "part") return { kind: "part", part: hit.part, selector: formatBoardRefSelector({ kind: "part", ref: hit.part.ref }) };
    const item = hit.via || hit.track || hit.zone;
    if (!item.net) return null;
    // Copper is its net at a point: the via's centre, the track's centreline under the pointer,
    // the pour where it was pressed, to the hundredth of a millimetre.
    const [x, y] = toScript(hit.at || at);
    return { kind: "copper", net: nets.get(item.net) || netNamed(item.net), item, at: [round2(x), round2(y)],
      selector: formatBoardRefSelector({ kind: "copper", net: item.net, at: [round2(x), round2(y)] }) };
  }

  /** The board reference of a point (a press on bare board), to the hundredth of a millimetre. */
  function pointSelector(at) {
    const [x, y] = toScript(at);
    return formatBoardRefSelector({ kind: "point", at: [round2(x), round2(y)] });
  }

  // ---- references -> what they name ------------------------------------------
  /**
   * What a board selector names on this board: `{ kind, selector, part | pad | net | item, at }`, or
   * null when it names nothing here (a part since renumbered, a net since renamed).
   */
  function resolve(selector) {
    const parsed = parseBoardRefSelector(selector);
    if (!parsed) return null;
    if (parsed.kind === "part") {
      const part = parts.get(parsed.ref);
      return part ? { kind: "part", part, selector: parsed.canonical } : null;
    }
    if (parsed.kind === "pad") {
      const pad = pads.get(`${parsed.ref}.${parsed.pad}`);
      return pad ? { kind: "pad", pad, selector: parsed.canonical } : null;
    }
    if (parsed.kind === "net") {
      const net = nets.get(parsed.net);
      return net ? { kind: "net", net, selector: parsed.canonical } : null;
    }
    const at = toPage(parsed.at);
    if (parsed.kind === "point") return { kind: "point", at: parsed.at, page: at, selector: parsed.canonical };
    const net = nets.get(parsed.net);
    if (!net) return null;
    // The net's copper nearest the point: a track, a via or a pour holding it.
    let best = null;
    for (const via of net.vias) {
      const distance = Math.max(0, Math.hypot(at[0] - via.at[0], at[1] - via.at[1]) - via.diameter / 2);
      if (!best || distance < best.distance) best = { item: via, distance };
    }
    for (const track of net.tracks) {
      const nearest = nearestOnPolyline(at, track.points);
      const distance = nearest ? Math.max(0, nearest.distance - track.width / 2) : Infinity;
      if (!best || distance < best.distance) best = { item: track, distance };
    }
    for (const zone of net.zones) if (pointInPolygon(at, zone.outline) && (!best || best.distance > 0)) best = { item: zone, distance: 0 };
    return { kind: "copper", net, item: best?.item || null, at: parsed.at, page: at, selector: parsed.canonical };
  }

  /** Where a resolved reference is on the page, as a box to frame: `[minX, minY, maxX, maxY]`. */
  function extent(resolved) {
    if (!resolved) return null;
    if (resolved.kind === "part") return bounds([...resolved.part.outline, ...resolved.part.pads.flatMap((pad) => pad.polygon)]);
    if (resolved.kind === "pad") return bounds(resolved.pad.polygon.length ? resolved.pad.polygon : [resolved.pad.at]);
    if (resolved.kind === "net") {
      const net = resolved.net;
      const points = [...net.pads.flatMap((pad) => pad.polygon), ...net.tracks.flatMap((track) => track.points), ...net.vias.map((via) => via.at)];
      return points.length ? bounds(points) : null;
    }
    const at = resolved.page || toPage(resolved.at);
    return [at[0], at[1], at[0], at[1]];
  }

  const SNAP_LABELS = {
    pad: (target) => `${target.item.ref}.${target.item.number}`,
    via: (target) => `via ${target.item.net}`,
    track: (target) => `track ${target.item.net}`,
    hole: () => "hole",
    outline: () => "board edge",
  };
  /** Things a measurement snaps to near page point `at`: pad and via centres, track ends, holes, outline corners. */
  function snap(at, { tolerance = 0, kinds = null } = {}) {
    if (!point(at)) return null;
    const reach = Math.max(0, Number(tolerance) || 0);
    let best = null;
    let bestOrder = Infinity;
    snapGrid.visit(at[0] - reach, at[1] - reach, at[0] + reach, at[1] + reach, (order) => {
      const target = snapTargets[order];
      if (kinds && !kinds.includes(target.group)) return;
      const distance = Math.hypot(at[0] - target.at[0], at[1] - target.at[1]);
      if (distance > reach) return;
      if (!best || distance < best.distance || (distance === best.distance && order < bestOrder)) { best = { target, distance }; bestOrder = order; }
    });
    if (!best) return null;
    const { target, distance } = best;
    const selector = target.kind === "pad" ? formatBoardRefSelector({ kind: "pad", ref: target.item.ref, pad: target.item.number }) : "";
    return { at: target.at, distance, kind: target.kind, label: SNAP_LABELS[target.kind](target), selector };
  }

  /** A pin's pads: the one that names it and any repeated under its number. */
  const shapesOf = (pad) => shapesByPin.get(`${pad.ref}.${pad.number}`) || [pad];
  return Object.freeze({
    document: "board", origin, parts, pads, padShapes, nets, tracks, vias, zones, holes, outline, findings,
    toScript, toPage, pick, pointSelector, resolve, extent, snap, shapesOf
  });
}
