/**
 * A board's index (`payload.board` of a KiCad board's plot), made ready to point at: what is under a
 * point of the picture, the board reference a person hands the agent for it, and back again from a
 * reference to what it names. Its graphics are what the plot draws of them (the sheet's items that
 * carry an `id`); everything else is the index's.
 *
 * Geometry arrives in SHEET coordinates (millimetres, y down, the plot sheet's corner) — every
 * point of it, a part's and a pad's place included — and is kept in PAGE coordinates (the sheet's
 * place in the laid-out plot added: `layoutPlot`), the frame the view's transform maps to the
 * screen. What a person or an agent reads is in KiCad's own coordinates (`toScript`): millimetres,
 * y down, from KiCad's page origin (`index.origin`: where that origin lies, in sheet coordinates),
 * the frame a script's `Vector2.from_xy_mm` takes, so a copied point pastes straight into one.
 *
 * Pure: no canvas, no DOM. The viewer picks with it on every pointer move, so what is near a point
 * is found through a grid of the board (`spatialGrid.js`): a board of tens of thousands of pads
 * and tracks answers a pick in a few cells' worth of tests.
 */
import { BOARD_ITEM_KINDS, formatBoardRefSelector, parseBoardRefSelector } from "../boardRefs.js";
import { bounds, nearestOnPolyline, point, pointInPolygon, polygonArea, polygonReach } from "./geometry.js";
import { boxOf, createSpatialGrid, nearBox } from "./spatialGrid.js";


/**
 * What a pick may take, by kind: `pads`, `tracks`, `vias`, `zones`, `texts`, `dimensions`, `shapes`
 * (graphics) and `parts`; `copper` is `tracks` and `vias` both. `nets` takes whole nets instead —
 * any copper under the pointer, a pad's or a pour's too, picks its net. Two flags say how far a kind
 * reaches: `footprintShapes`, a footprint's own graphics (without it they are their part's, as
 * KiCad picks them), and `zoneFill`, a zone anywhere inside its outline (without it, by its outline
 * alone: a press on bare board inside a ground pour, as most of a board is, takes nothing). The
 * named sets are the Select filter's modes.
 */
export const BOARD_PICK_KINDS = Object.freeze({
  all: Object.freeze({ pads: true, tracks: true, vias: true, zones: true, texts: true, dimensions: true, shapes: true, parts: true, nets: false }),
  parts: Object.freeze({ parts: true }),
  pads: Object.freeze({ pads: true }),
  nets: Object.freeze({ pads: true, tracks: true, vias: true, zones: true, zoneFill: true, nets: true }),
  tracks: Object.freeze({ tracks: true }),
  vias: Object.freeze({ vias: true }),
  zones: Object.freeze({ zones: true, zoneFill: true }),
  texts: Object.freeze({ texts: true }),
  dimensions: Object.freeze({ dimensions: true }),
  shapes: Object.freeze({ shapes: true, footprintShapes: true }),
});
export const BOARD_PICK_MODES = Object.freeze(Object.keys(BOARD_PICK_KINDS));

const EMPTY = Object.freeze([]);
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
// An item that names its part by reference (`#R1`, a footprint's text or graphic): the part's ref.
const partRef = (value) => (typeof value === "string" && value.startsWith("#") && !value.includes(".") ? value.slice(1) : "");
const pointList = (value) => (Array.isArray(value) ? value.map(point).filter(Boolean) : []);
// A closed line's points with the first again at its end, so a distance reaches its closing edge.
const closedLine = (points) => (points.length > 2 ? [...points, points[0]] : points);
/** The canonical layers a point or an area may name (`boardRefs.js`); the plot's own (vias, drills) are none. */
const NAMED_LAYER = /^(?:[FB]\.(?:Cu|Adhes|Paste|SilkS|Mask|CrtYd|Fab)|In[0-9]{1,2}\.Cu|(?:Dwgs|Cmts|Eco1|Eco2)\.User|Edge\.Cuts|Margin|User\.[0-9]{1,2})$/;
const COPPER_LAYER = /^(?:F|B|In\d+)\.Cu$/;

/**
 * @param {object} board  The payload's `board`.
 * @param {{ x?: number, y?: number, layers?: readonly object[] }} [sheet]  The board sheet's place in the
 *   plot layout (page mm), and its layers (`layoutPlot`'s), whose items with an `id` are the board's graphics.
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
  const toScript = ([x, y]) => [x - sheetX - origin[0], y - sheetY - origin[1]];
  const toPage = ([x, y]) => [x + origin[0] + sheetX, y + origin[1] + sheetY];

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
      fields: entry.fields && typeof entry.fields === "object" ? { ...entry.fields } : {},
      dnp: Boolean(entry.dnp), script: typeof entry.script === "string" ? entry.script : "",
      outline, area: outline.length > 2 ? polygonArea(outline) : Infinity, box: outline.length > 2 ? boxOf(outline) : null, pads: []
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

  const idOf = (entry) => (typeof entry?.id === "string" && entry.id ? entry.id.toLowerCase() : "");
  const tracks = (board?.tracks || EMPTY).map((entry) => {
    const width = Number(entry?.width) || 0;
    const points = pageList(entry?.points);
    return { kind: "track", id: idOf(entry), net: String(entry?.net ?? ""), layer: String(entry?.layer ?? ""), width, arc: entry?.arc === true,
      points, box: boxOf(points, width / 2) };
  }).filter((track) => track.points.length > 1);
  const vias = (board?.vias || EMPTY).map((entry) => {
    const at = page(entry?.at);
    const diameter = Number(entry?.diameter) || 0;
    const layers = Array.isArray(entry?.layers) ? entry.layers.map(String) : ["F.Cu", "B.Cu"];
    return { kind: "via", id: idOf(entry), net: String(entry?.net ?? ""), at, diameter, drill: Number(entry?.drill) || 0, layers,
      type: String(entry?.type || "through"), box: at ? boxOf([at], diameter / 2) : null };
  }).filter((via) => via.at);
  const zones = (board?.zones || EMPTY).map((entry) => {
    const outline = pageList(entry?.outline);
    return { kind: "zone", id: idOf(entry), net: String(entry?.net ?? ""), layer: String(entry?.layer ?? ""), name: String(entry?.name ?? ""),
      priority: Number(entry?.priority) || 0, filled: Number.isFinite(Number(entry?.filled)) && entry?.filled !== undefined ? Number(entry.filled) : null,
      outline, area: outline.length > 2 ? polygonArea(outline) : Infinity, box: boxOf(outline) };
  }).filter((zone) => zone.outline.length > 2);
  for (const track of tracks) netNamed(track.net)?.tracks.push(track);
  for (const via of vias) netNamed(via.net)?.vias.push(via);
  for (const zone of zones) netNamed(zone.net)?.zones.push(zone);
  // A zone on several layers is one zone: its layers, as each of its entries knows them.
  const zoneLayers = new Map();
  for (const zone of zones) if (zone.id) zoneLayers.set(zone.id, [...(zoneLayers.get(zone.id) || []), zone.layer]);
  for (const zone of zones) zone.layers = zone.id ? zoneLayers.get(zone.id) : [zone.layer];

  // What a person picks beside the copper: the texts, the dimensions and the graphics.
  const texts = (board?.texts || EMPTY).map((entry) => {
    const polygon = pageList(entry?.polygon);
    return { kind: "text", id: idOf(entry), text: String(entry?.text ?? ""), layer: String(entry?.layer ?? ""), at: page(entry?.at),
      angle: Number(entry?.angle) || 0, size: Number(entry?.size) || 0, part: String(entry?.part ?? ""), polygon,
      area: polygon.length > 2 ? polygonArea(polygon) : 0, box: boxOf(polygon) };
  }).filter((text) => text.id && text.polygon.length > 2);
  const dimensions = (board?.dimensions || EMPTY).map((entry) => {
    const lines = (Array.isArray(entry?.lines) ? entry.lines : EMPTY).map(pageList).filter((line) => line.length > 1);
    const polygon = pageList(entry?.polygon);
    return { kind: "dimension", id: idOf(entry), type: String(entry?.type || "aligned"), layer: String(entry?.layer ?? ""), value: String(entry?.value ?? ""),
      part: String(entry?.part ?? ""), lines, polygon, box: boxOf([...lines.flat(), ...polygon]) };
  }).filter((dimension) => dimension.id && dimension.box);
  // The graphics are what the plot draws of them, in sheet millimetres as the index is. A board's own
  // are read as the index is made; a footprint's — the most of a board's items, which a pick takes
  // only with Graphics alone (else they are their part's) — when something first asks for them.
  const placed = sheetX || sheetY;
  const shapeOf = (layer, item) => {
    // A laid-out item's points and box are the page's when the sheet is the page's corner, as a board's is.
    const points = placed ? pageList(item.pts) : Array.isArray(item.box) ? item.pts : pointList(item.pts);
    if (points.length < 2) return null;
    const width = Number(item.w) || 0;
    return { kind: "shape", id: item.id.toLowerCase(), shape: String(item.shape || "line"), layer: String(layer.id), width,
      closed: item.t === "poly" || item.closed === true, filled: item.t === "poly", part: partRef(item.ref), net: String(item.net ?? ""),
      points, box: !placed && Array.isArray(item.box) ? item.box : boxOf(points, width / 2) };
  };
  const graphics = (own) => {
    const found = [];
    for (const layer of sheet?.layers || EMPTY) {
      for (const item of layer?.items || EMPTY) {
        if (typeof item?.id !== "string" || !item.id || (item.t !== "path" && item.t !== "poly") || Boolean(partRef(item.ref)) !== own) continue;
        const shape = shapeOf(layer, item);
        if (shape) found.push(shape);
      }
    }
    return found;
  };
  const boardShapes = graphics(false);
  // Each kind by id: an item under its whole id, one named under its footprint's uuid also under its own.
  const byId = Object.fromEntries(BOARD_ITEM_KINDS.map((kind) => [kind, new Map()]));
  const file = (kind, list) => {
    for (const item of list) {
      if (!item.id) continue;
      for (const key of item.id.includes("/") ? [item.id, item.id.split("/")[1]] : [item.id]) {
        const found = byId[kind].get(key);
        if (found) found.push(item); else byId[kind].set(key, [item]);
      }
    }
  };
  for (const [kind, list] of [["track", tracks], ["via", vias], ["zone", zones], ["text", texts], ["dimension", dimensions], ["shape", boardShapes]]) file(kind, list);
  // A footprint's graphics, and their grid, made on first need.
  let footprintShapes = null;
  let footprintGrid = null;
  const ownShapes = () => {
    if (!footprintShapes) { footprintShapes = graphics(true); file("shape", footprintShapes); }
    return footprintShapes;
  };
  const ownGrid = () => (footprintGrid ??= createSpatialGrid(ownShapes().map((shape) => shape.box)));
  /** The `kind` an id names, or null for none, or for one that copies of a footprint share. */
  const itemNamed = (kind, id) => {
    if (kind === "shape") ownShapes();
    const found = byId[kind]?.get(String(id || "").toLowerCase()) || EMPTY;
    const whole = new Set(found.map((item) => item.id));
    return whole.size === 1 ? found[0] : null;
  };

  const holes = (board?.holes || EMPTY).map((entry) => ({ at: page(entry?.at), diameter: Number(entry?.diameter) || 0 })).filter((hole) => hole.at);
  const outline = (board?.outline || EMPTY).map(pageList).filter((line) => line.length > 1);

  // ---- what is near a point --------------------------------------------------
  const padGrid = createSpatialGrid(padShapes.map((shape) => (shape.polygon.length > 2 ? shape.box : null)));
  const viaGrid = createSpatialGrid(vias.map((via) => via.box));
  const trackGrid = createSpatialGrid(tracks.map((track) => track.box));
  const parted = [...parts.values()];
  const partGrid = createSpatialGrid(parted.map((part) => part.box));
  const zoneGrid = createSpatialGrid(zones.map((zone) => zone.box));
  const textGrid = createSpatialGrid(texts.map((text) => text.box));
  const dimensionGrid = createSpatialGrid(dimensions.map((dimension) => dimension.box));
  const shapeGrid = createSpatialGrid(boardShapes.map((shape) => shape.box));
  // How far a point is from what a dimension draws: its lines, and its value's box.
  const dimensionReach = (at, dimension) => {
    let distance = dimension.polygon.length > 2 ? polygonReach(at, dimension.polygon) : Infinity;
    for (const line of dimension.lines) distance = Math.min(distance, nearestOnPolyline(at, line)?.distance ?? Infinity);
    return distance;
  };
  // How far a point is from a graphic's ink: 0 in a filled one, else from its stroke's edge.
  const shapeReach = (at, shape) => {
    if (shape.filled && shape.points.length > 2 && pointInPolygon(at, shape.points)) return 0;
    const nearest = nearestOnPolyline(at, shape.closed ? closedLine(shape.points) : shape.points);
    return nearest ? Math.max(0, nearest.distance - shape.width / 2) : Infinity;
  };

  // ---- picking ---------------------------------------------------------------
  /**
   * What is under page point `at`, as a hit `{ kind, selector, ... }`, or null.
   * `kinds`: what may be taken (`BOARD_PICK_KINDS`), else `mode`'s set (its names). `view`: the side
   * looked at (top | bottom). `tolerance`: page millimetres a small thing may be missed by (a few
   * screen pixels at the view's scale). `layers`: the layer ids drawn (a Set), when the view draws
   * some alone: a track, a via, a zone, a text, a dimension or a graphic on a layer not drawn is
   * not taken.
   */
  function pick(at, { mode = "all", kinds = BOARD_PICK_KINDS[mode] || BOARD_PICK_KINDS.all, view = "top", tolerance = 0, layers = null } = {}) {
    if (!point(at)) return null;
    const reach = Math.max(0, Number(tolerance) || 0);
    const [x, y] = at;
    const candidates = [];
    const wholeNets = Boolean(kinds.nets);
    const wantPads = Boolean(kinds.pads);
    const wantVias = Boolean(kinds.vias || kinds.copper);
    const wantTracks = Boolean(kinds.tracks || kinds.copper);
    const wantParts = Boolean(kinds.parts);
    const drawn = (layer) => !layers || layers.has(layer);
    if (wantPads) {
      padGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const shape = padShapes[order];
        if (!nearBox(shape.box, at, reach)) return;
        const near = reach > 0 ? polygonReach(at, shape.polygon) : pointInPolygon(at, shape.polygon) ? 0 : Infinity;
        // Any pad of a pin picks the pin: its first pad names it.
        if (near <= reach) candidates.push({ rank: 0, side: facing(shape.side, view), size: shape.area, distance: near, order, hit: { kind: "pad", pad: pads.get(`${shape.ref}.${shape.number}`) } });
      });
    }
    if (wantVias && drawn("vias")) {
      viaGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const via = vias[order];
        const distance = Math.hypot(x - via.at[0], y - via.at[1]) - via.diameter / 2;
        if (distance <= reach) candidates.push({ rank: 1, side: 0, size: via.diameter, distance: Math.max(0, distance), order, hit: { kind: "via", via, at: via.at } });
      });
    }
    if (wantTracks) {
      trackGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const track = tracks[order];
        if (!drawn(track.layer) || !nearBox(track.box, at, reach)) return;
        const nearest = nearestOnPolyline(at, track.points);
        if (nearest && nearest.distance - track.width / 2 <= reach) {
          candidates.push({ rank: 2, side: facing(layerSide(track.layer), view), size: track.width, distance: Math.max(0, nearest.distance - track.width / 2), order, hit: { kind: "track", track, at: nearest.point } });
        }
      });
    }
    if (kinds.texts) {
      textGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const text = texts[order];
        if (!drawn(text.layer) || !nearBox(text.box, at, reach)) return;
        const distance = polygonReach(at, text.polygon);
        if (distance <= reach) candidates.push({ rank: 3, side: facing(layerSide(text.layer), view), size: text.area, distance, order, hit: { kind: "text", text } });
      });
    }
    if (kinds.dimensions) {
      dimensionGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const dimension = dimensions[order];
        if (!drawn(dimension.layer) || !nearBox(dimension.box, at, reach)) return;
        const distance = dimensionReach(at, dimension);
        if (distance <= reach) candidates.push({ rank: 4, side: facing(layerSide(dimension.layer), view), size: 0, distance, order, hit: { kind: "dimension", dimension } });
      });
    }
    if (kinds.shapes) {
      const take = (list, base) => (order) => {
        const shape = list[order];
        if (!drawn(shape.layer) || !nearBox(shape.box, at, reach)) return;
        const distance = shapeReach(at, shape);
        if (distance <= reach) candidates.push({ rank: 5, side: facing(layerSide(shape.layer), view), size: shape.width, distance, order: base + order, hit: { kind: "shape", shape } });
      };
      shapeGrid.visit(x - reach, y - reach, x + reach, y + reach, take(boardShapes, 0));
      // A footprint's own graphics are its part's, unless the filter takes graphics alone.
      if (kinds.footprintShapes) ownGrid().visit(x - reach, y - reach, x + reach, y + reach, take(ownShapes(), boardShapes.length));
    }
    // A pour is taken by its outline, or, for its net or with the zones alone, anywhere inside it:
    // under All, a press on bare board (inside a ground pour, as most of a board is) clears the
    // selection rather than taking the pour.
    if (kinds.zones) {
      const inside = Boolean(kinds.zoneFill || wholeNets);
      zoneGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
        const zone = zones[order];
        if (!drawn(zone.layer) || !nearBox(zone.box, at, reach)) return;
        const within = pointInPolygon(at, zone.outline);
        const edge = nearestOnPolyline(at, closedLine(zone.outline))?.distance ?? Infinity;
        if ((inside && within) || edge <= reach) {
          candidates.push({ rank: 6, side: facing(layerSide(zone.layer), view), size: zone.area, distance: inside && within ? 0 : edge, order, hit: { kind: "zone", zone, at } });
        }
      });
    }
    if (wantParts) {
      partGrid.visit(x, y, x, y, (order) => {
        const part = parted[order];
        if (nearBox(part.box, at, 0) && pointInPolygon(at, part.outline)) {
          candidates.push({ rank: 7, side: facing(part.side, view), size: part.area, distance: 0, order, hit: { kind: "part", part } });
        }
      });
    }
    // The facing side first, then the most specific kind, then the nearest, then the smallest; and
    // past one that names nothing (copper on no net) to the next.
    candidates.sort((a, b) => a.side - b.side || a.rank - b.rank || a.distance - b.distance || a.size - b.size || a.order - b.order);
    for (const candidate of candidates) {
      const found = describeHit(candidate.hit, wholeNets, at);
      if (found) return found;
    }
    return null;
  }

  function describeHit(hit, wholeNets, at) {
    if (wholeNets) {
      const name = hit.pad?.net ?? hit.via?.net ?? hit.track?.net ?? hit.zone?.net ?? "";
      const net = nets.get(name);
      return net ? { kind: "net", net, selector: formatBoardRefSelector({ kind: "net", net: net.name }) } : null;
    }
    if (hit.kind === "pad") return { kind: "pad", pad: hit.pad, selector: formatBoardRefSelector({ kind: "pad", ref: hit.pad.ref, pad: hit.pad.number }) };
    if (hit.kind === "part") return { kind: "part", part: hit.part, selector: formatBoardRefSelector({ kind: "part", ref: hit.part.ref }) };
    // An item by the uuid KiCad saved it with: what an edit keeps naming.
    const named = hit[hit.kind];
    if (named?.id) return { kind: hit.kind, item: named, selector: formatBoardRefSelector({ kind: hit.kind, id: named.id }) };
    const item = hit.via || hit.track || hit.zone;
    // A board that saved no uuids names its copper by its net where it was pressed; anything else, not at all.
    if (!item?.net) return null;
    // Copper is its net at a point: the via's centre, the track's centreline under the pointer,
    // the pour where it was pressed, to the hundredth of a millimetre.
    const [x, y] = toScript(hit.at || at);
    return { kind: "copper", net: nets.get(item.net) || netNamed(item.net), item, at: [round2(x), round2(y)],
      selector: formatBoardRefSelector({ kind: "copper", net: item.net, at: [round2(x), round2(y)] }) };
  }

  // ---- snapping: where Measure's ends land --------------------------------------
  const holeGrid = createSpatialGrid(holes.map((hole) => boxOf([hole.at], hole.diameter / 2)));
  const outlinePoints = outline.flat();
  const outlineGrid = createSpatialGrid(outlinePoints.map(([px, py]) => [px, py, px, py]));
  /**
   * The point a measurement's end takes near page point `at`: the nearest pad, via or hole centre
   * ("center"), or track end or outline vertex ("vertex"), within `tolerance` page millimetres, as
   * `{ point, kind, what }`; null when nothing is that near.
   */
  function snap(at, { tolerance = 0 } = {}) {
    if (!point(at)) return null;
    const reach = Math.max(0, Number(tolerance) || 0);
    const [x, y] = at;
    let best = null;
    const consider = (candidate, kind, what) => {
      if (!candidate) return;
      const distance = Math.hypot(candidate[0] - x, candidate[1] - y);
      if (distance <= reach && (!best || distance < best.distance)) best = { point: [candidate[0], candidate[1]], kind, what, distance };
    };
    padGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => consider(padShapes[order].at, "center", "pad"));
    viaGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => consider(vias[order].at, "center", "via"));
    holeGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => consider(holes[order].at, "center", "hole"));
    trackGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => {
      const line = tracks[order].points;
      consider(line[0], "vertex", "track");
      consider(line[line.length - 1], "vertex", "track");
    });
    outlineGrid.visit(x - reach, y - reach, x + reach, y + reach, (order) => consider(outlinePoints[order], "vertex", "outline"));
    return best ? { point: best.point, kind: best.kind, what: best.what } : null;
  }

  /**
   * The board reference of page point `at` (Select's Point or area, a press on bare board), to the
   * hundredth of a millimetre, on `layer` when one is given and the language can name it.
   */
  function pointSelector(at, layer = null) {
    const [x, y] = toScript(at);
    return formatBoardRefSelector({ kind: "point", at: [round2(x), round2(y)], ...(namedLayer(layer) ? { layer } : {}) });
  }

  /** The board reference of the box between page points `from` and `to` (Select's Point or area dragged). */
  function areaSelector(from, to, layer = null) {
    const [x0, y0] = toScript(from); const [x1, y1] = toScript(to);
    return formatBoardRefSelector({ kind: "area", at: [round2(x0), round2(y0)], to: [round2(x1), round2(y1)], ...(namedLayer(layer) ? { layer } : {}) });
  }
  const namedLayer = (layer) => typeof layer === "string" && NAMED_LAYER.test(layer);

  /**
   * Whether `item` is on `layer` (any, for none), as the board API's `at` and `area` say it: a
   * thing with a layer on its own; a pad on a copper layer it is on, or on its side's other layers; a
   * via on the copper it spans; a part on its side's layers (every part, on a layer of neither side).
   */
  const stack = () => {
    const copper = [...new Set([...tracks.map((track) => track.layer), ...zones.map((zone) => zone.layer), ...vias.flatMap((via) => via.layers),
      ...(sheet?.layers || EMPTY).map((layer) => layer.id)])].filter((name) => COPPER_LAYER.test(name));
    const rank = (name) => (name === "F.Cu" ? [0, 0] : name === "B.Cu" ? [2, 0] : [1, Number(name.replace(/\D/g, "")) || 0]);
    return copper.sort((a, b) => rank(a)[0] - rank(b)[0] || rank(a)[1] - rank(b)[1]);
  };
  let copperStack = null;
  function onLayer(item, layer) {
    if (!layer) return true;
    const side = layer.startsWith("F.") ? "top" : layer.startsWith("B.") ? "bottom" : null;
    const copper = COPPER_LAYER.test(layer);
    if (item.kind === "part") return !side || item.side === side;
    if (item.kind === "pad") return copper ? item.side === "both" || item.side === side : Boolean(side) && (item.side === side || item.side === "both");
    if (item.kind === "via") {
      if (!copper) return false;
      copperStack ??= stack();
      if (item.type === "through" || item.layers.length < 2) return true;
      const ends = item.layers.map((name) => copperStack.indexOf(name)).filter((index) => index >= 0).sort((a, b) => a - b);
      const at = copperStack.indexOf(layer);
      return ends.length ? at >= ends[0] && at <= ends[ends.length - 1] : true;
    }
    return item.layer === layer;
  }

  /**
   * What lies wholly inside the page box `[minX, minY, maxX, maxY]` (on `layer` alone, when one is
   * given), as the board API's `area` answers it: `{ parts, pads, tracks, vias, zones, texts,
   * dimensions, shapes, holes }`, each a list.
   */
  function within(box, layer = null) {
    const [x0, y0, x1, y1] = box;
    const held = (points, reach = 0) => points.length > 0 && points.every(([px, py]) => px - reach >= x0 && px + reach <= x1 && py - reach >= y0 && py + reach <= y1);
    const keep = (list, test) => list.filter((item) => onLayer(item, layer) && test(item));
    return {
      parts: keep(parted, (part) => held(part.outline)),
      pads: keep(padShapes, (pad) => held(pad.polygon)),
      tracks: keep(tracks, (track) => held(track.points)),
      vias: keep(vias, (via) => held([via.at], via.diameter / 2)),
      zones: keep(zones, (zone) => held(zone.outline)),
      texts: keep(texts, (text) => held(text.polygon)),
      dimensions: keep(dimensions, (dimension) => held([...dimension.lines.flat(), ...dimension.polygon])),
      shapes: keep([...boardShapes, ...ownShapes()], (shape) => held(shape.points)),
      holes: holes.filter((hole) => held([hole.at], hole.diameter / 2)),
    };
  }

  // ---- references -> what they name ------------------------------------------
  /**
   * What a board selector names on this board: `{ kind, selector, part | pad | net | item, at }`, or
   * null when it names nothing here (a part since renumbered, a net since renamed).
   */
  function resolve(selector) {
    const parsed = parseBoardRefSelector(selector);
    if (!parsed) return null;
    if (BOARD_ITEM_KINDS.includes(parsed.kind)) {
      const item = itemNamed(parsed.kind, parsed.id);
      return item ? { kind: parsed.kind, item, selector: parsed.canonical } : null;
    }
    if (parsed.kind === "area") {
      const from = toPage(parsed.at); const to = toPage(parsed.to);
      return { kind: "area", at: parsed.at, to: parsed.to, ...(parsed.layer ? { layer: parsed.layer } : {}),
        page: from, box: [Math.min(from[0], to[0]), Math.min(from[1], to[1]), Math.max(from[0], to[0]), Math.max(from[1], to[1])], selector: parsed.canonical };
    }
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
    if (parsed.kind === "point") return { kind: "point", at: parsed.at, ...(parsed.layer ? { layer: parsed.layer } : {}), page: at, selector: parsed.canonical };
    const net = nets.get(parsed.net);
    if (!net) return null;
    // The net's copper nearest the point: a track, a via or a pour holding it. Lenient on purpose: the nearest
    // however far off, where Python's copper() refuses copper past COPPER_TOLERANCE (0.1 mm).
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
    if (resolved.kind === "area") return [...resolved.box];
    if (BOARD_ITEM_KINDS.includes(resolved.kind) && resolved.item?.box) return [...resolved.item.box];
    const at = resolved.page || toPage(resolved.at);
    return [at[0], at[1], at[0], at[1]];
  }

  /** A pin's pads: the one that names it and any repeated under its number. */
  const shapesOf = (pad) => shapesByPin.get(`${pad.ref}.${pad.number}`) || [pad];
  return Object.freeze({
    document: "board", origin, parts, pads, padShapes, nets, tracks, vias, zones, holes, outline, texts, dimensions,
    /** Every graphic: the board's own, then the footprints' (read on first need). */
    get shapes() { return [...boardShapes, ...ownShapes()]; },
    toScript, toPage, pick, snap, pointSelector, areaSelector, within, onLayer, resolve, extent, shapesOf
  });
}
