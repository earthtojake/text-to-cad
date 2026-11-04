/**
 * A KiCad schematic's index on the client: what its references name, and, on a sheet drawn, what a
 * pointer is over. The server reads the files (`cad.engine.formats.kicad.schematic`); its plot payload
 * carries the hierarchy's index (`payload.schematic`, `SchematicIndex.as_json`) beside the sheet on
 * screen, whose drawn items carry `ref` (`#R1`, `#R1.2`, `#sheet:/Load/`), `net` and `id` (the uuid
 * KiCad saved them with). Nothing here parses KiCad's files.
 *
 * `createSchematicIndex(schematic)` is the hierarchy: its sheets (a tree by `parent`), parts, pins,
 * nets and the items KiCad names by uuid, and `resolve(selector)` for a schematic reference
 * (`schematicRefs.js`): what it names and the sheets it is on. `createSchematicPage(index, sheet)` is one
 * drawn sheet (a laid-out plot's `sheets[0]`, `plot2d/plot.js`): the drawn items of what a reference
 * names (`itemsOf`, `extent`), the most specific thing under a point (`pick`), the things inside a box
 * (`within`), the sheet symbol under a point (`sheetAt`) and Measure's snap (`snap`). Page millimetres,
 * y down, as the payload's.
 *
 * Importing this module has no environmental effects.
 */
import { canonicalSheetPath, formatSheetSelector, parseSchematicRefSelector } from "../schematicRefs.js";

const EMPTY = Object.freeze([]);
const NATURAL = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const natural = (left, right) => NATURAL.compare(String(left), String(right));

/**
 * The kinds Select's filter ticks, KiCad's Selection Filter's: Symbols (a part, by its body, its fields
 * or a power symbol), Pins, Wires (wires, buses and bus entries), Labels, Sheets (a sheet symbol, by its
 * box; a sheet pin is its net) and Other items (junctions, no-connects).
 */
export const SCHEMATIC_PICK_KINDS = Object.freeze(["symbols", "pins", "wires", "labels", "sheets", "other"]);

/** @param {object} schematic The payload's `schematic`. */
export function createSchematicIndex(schematic) {
  const sheets = new Map();
  for (const sheet of schematic?.sheets || []) sheets.set(sheet.path, { ...sheet, children: [] });
  for (const sheet of sheets.values()) if (sheet.parent && sheets.has(sheet.parent)) sheets.get(sheet.parent).children.push(sheet.path);
  const parts = new Map((schematic?.parts || []).map((part) => [part.ref, part]));
  const pins = new Map();
  for (const pin of schematic?.pins || []) pins.set(`${pin.part}.${pin.number}`, pin);
  const nets = new Map((schematic?.nets || []).map((net) => [net.name, net]));
  // What KiCad names by uuid, each with its kind and its sheet.
  const items = new Map();
  for (const wire of schematic?.wires || []) if (wire.id) items.set(wire.id, { kind: wire.kind === "bus" ? "bus" : "wire", ...wire });
  for (const label of schematic?.labels || []) if (label.id) items.set(label.id, { ...label, kind: "label", label: label.kind });
  for (const item of schematic?.junctions || []) if (item.id) items.set(item.id, { kind: "junction", ...item });
  for (const item of schematic?.no_connects || []) if (item.id) items.set(item.id, { kind: "no_connect", ...item });
  for (const item of schematic?.bus_entries || []) if (item.id) items.set(item.id, { kind: "bus_entry", ...item });
  for (const part of parts.values()) {
    for (const unit of part.units || []) if (unit.id) items.set(unit.id, { kind: "symbol", ref: part.ref, ...unit });
  }
  const order = [...sheets.values()].sort((a, b) => natural(a.page, b.page) || natural(a.path, b.path));
  const root = order.find((sheet) => !sheet.parent) || order[0] || null;
  const rootName = String(schematic?.root || "").replace(/\.kicad_sch$/i, "") || "/";

  /** A sheet's name as a person reads it: the root by its file, a child by its sheet name. */
  const sheetName = (path) => (path === root?.path ? rootName : sheets.get(path)?.name || path);

  /**
   * What `selector` names, or null: `{ kind, selector, label, sheets, ... }` — `sheets` the paths of the
   * sheets it is drawn on, in page order (a sheet's own symbol is on its parent).
   */
  function resolve(selector) {
    const parsed = parseSchematicRefSelector(selector);
    if (!parsed) return null;
    const onSheets = (list) => order.map((sheet) => sheet.path).filter((path) => list.includes(path));
    if (parsed.kind === "part") {
      const part = parts.get(parsed.ref);
      return part ? { kind: "part", selector: parsed.canonical, ref: part.ref, label: part.ref, part,
        sheets: onSheets((part.units || []).map((unit) => unit.sheet)) } : null;
    }
    if (parsed.kind === "pad") {
      const pin = pins.get(`${parsed.ref}.${parsed.pad}`);
      return pin ? { kind: "pin", selector: parsed.canonical, ref: pin.part, pad: pin.number, label: `${pin.part}.${pin.number}`, pin,
        net: pin.net || null, sheets: onSheets([pin.sheet]) } : null;
    }
    if (parsed.kind === "net") {
      const net = nets.get(parsed.net);
      return net ? { kind: "net", selector: parsed.canonical, net: net.name, label: net.name, netInfo: net, sheets: onSheets(net.sheets || []) } : null;
    }
    if (parsed.kind === "sheet") {
      const sheet = sheets.get(parsed.sheet);
      return sheet ? { kind: "sheet", selector: parsed.canonical, path: sheet.path, label: sheetName(sheet.path), sheet,
        sheets: sheet.parent ? [sheet.parent] : [] } : null;
    }
    const item = items.get(parsed.id);
    if (!item || item.kind !== parsed.kind) return null;
    const label = item.kind === "label" ? item.text : item.kind === "symbol" ? item.ref : item.net || item.kind;
    return { kind: item.kind, selector: parsed.canonical, id: parsed.id, label, item, net: item.net || null, sheets: onSheets([item.sheet]) };
  }

  /** The path a sheet's children are entered by: its own children, in page order. */
  const childrenOf = (path) => (sheets.get(path)?.children || EMPTY).slice().sort((a, b) => natural(sheets.get(a).page, sheets.get(b).page));
  /** The sheets from the root down to `path`, the root first. */
  function trail(path) {
    const chain = [];
    for (let at = sheets.get(canonicalSheetPath(path)); at; at = at.parent ? sheets.get(at.parent) : null) chain.unshift(at.path);
    return chain;
  }
  return { root: root?.path || "/", rootName, sheets, order: order.map((sheet) => sheet.path), parts, pins, nets, items,
    sheetName, childrenOf, trail, resolve };
}

// ---- one drawn sheet -------------------------------------------------------------

const unionBox = (boxes) => {
  if (!boxes.length) return null;
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  for (const b of boxes) {
    if (b[0] < box[0]) box[0] = b[0]; if (b[1] < box[1]) box[1] = b[1];
    if (b[2] > box[2]) box[2] = b[2]; if (b[3] > box[3]) box[3] = b[3];
  }
  return box;
};
const inBox = (box, [x, y], reach = 0) => x >= box[0] - reach && x <= box[2] + reach && y >= box[1] - reach && y <= box[3] + reach;
const insideBox = (inner, outer) => inner[0] >= outer[0] && inner[1] >= outer[1] && inner[2] <= outer[2] && inner[3] <= outer[3];
function segmentDistance([px, py], [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay;
  const length = dx * dx + dy * dy;
  const t = length > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function insidePolygon([x, y], pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
/**
 * How far a point is from an item's ink, page millimetres: 0 inside a filled shape, a text's box or a
 * small closed outline (a label's flag, a sheet pin's); a sheet's or a symbol's outline is its edge alone.
 */
function inkDistance(item, point) {
  if (item.t === "text") return inBox(item.box, point) ? 0 : Infinity;
  if (item.t === "circle") {
    const d = Math.hypot(point[0] - item.at[0], point[1] - item.at[1]);
    return item.w === 0 ? Math.max(0, d - item.r) : Math.abs(d - item.r);
  }
  const pts = item.pts;
  if (item.t === "poly" && insidePolygon(point, pts)) return 0;
  if (item.closed && (item.label || item.role === "pin") && insidePolygon(point, pts)) return 0;
  let best = Infinity;
  const step = item.pairs ? 2 : 1;
  for (let index = 0; index + 1 < pts.length; index += step) best = Math.min(best, segmentDistance(point, pts[index], pts[index + 1]));
  if (item.closed && !item.pairs && pts.length > 2) best = Math.min(best, segmentDistance(point, pts[pts.length - 1], pts[0]));
  return Math.max(0, best - (item.w || 0) / 2);
}

/**
 * One drawn sheet of a schematic (`index`), its plot sheet laid out (`plot2d`'s `layoutPlot(...).sheets[0]`).
 * @param {ReturnType<typeof createSchematicIndex>} index
 * @param {{ path?: string, layers: readonly { id: string, kind: string, items: readonly object[] }[] }} sheet
 */
export function createSchematicPage(index, sheet) {
  const path = canonicalSheetPath(sheet.path || "/");
  /** Every drawn item with its layer's kind, the page's edge left out. */
  const drawn = [];
  for (const layer of sheet.layers) if (layer.kind !== "sheet") for (const item of layer.items) drawn.push({ item, kind: layer.kind });
  const byRef = new Map(), byNet = new Map(), byId = new Map();
  const add = (map, key, entry) => { if (!key) return; if (!map.has(key)) map.set(key, []); map.get(key).push(entry); };
  for (const entry of drawn) {
    add(byRef, entry.item.ref, entry);
    add(byNet, entry.item.net, entry);
    add(byId, entry.item.id, entry);
  }
  // A part's own items are its body's and its fields' (by `#R1`) and its pins' (`#R1.<n>`).
  const partItems = new Map();
  for (const [ref, list] of byRef) {
    const parsed = ref.startsWith("#sheet:") ? null : parseSchematicRefSelector(ref);
    if (!parsed?.ref) continue;
    if (!partItems.has(parsed.ref)) partItems.set(parsed.ref, []);
    partItems.get(parsed.ref).push(...list);
  }
  // Each placed symbol's body, by its uuid: what a press inside it picks.
  const bodies = [];
  for (const [id, list] of byId) {
    const symbol = list.filter((entry) => entry.kind === "symbol");
    if (!symbol.length) continue;
    const found = index.items.get(id);
    const selector = found?.kind === "symbol" ? `#${found.ref}` : found?.kind === "label" ? `#label:${id}` : null;
    if (selector) bodies.push({ selector, box: unionBox(symbol.map((entry) => entry.item.box)), kind: "symbols" });
  }
  const sheetBoxes = [];
  for (const child of index.childrenOf(path)) {
    const info = index.sheets.get(child);
    if (!info?.at || !info?.size) continue;
    sheetBoxes.push({ path: child, selector: formatSheetSelector(child), box: [info.at[0], info.at[1], info.at[0] + info.size[0], info.at[1] + info.size[1]], kind: "sheets" });
  }

  /** The drawn items of what `resolved` names on this sheet. */
  function itemsOf(resolved) {
    if (!resolved) return EMPTY;
    if (resolved.kind === "part") return partItems.get(resolved.ref) || EMPTY;
    if (resolved.kind === "pin") return byRef.get(resolved.selector) || EMPTY;
    if (resolved.kind === "net") return byNet.get(resolved.net) || EMPTY;
    if (resolved.kind === "sheet") return byRef.get(resolved.selector) || EMPTY;
    if (resolved.kind === "symbol") return (byId.get(resolved.id) || EMPTY).concat((partItems.get(resolved.item.ref) || EMPTY).filter((entry) => entry.kind === "field"));
    return byId.get(resolved.id) || EMPTY;
  }
  /** The page box of what `resolved` names on this sheet, or null when it is not drawn here. */
  const extent = (resolved) => unionBox(itemsOf(resolved).map((entry) => entry.item.box));

  // What a drawn item picks, and under which box of the filter: the most specific first.
  function pickOf(entry) {
    const { item, kind } = entry;
    if ((kind === "pin" || kind === "pin_number" || kind === "pin_name") && item.ref) return { selector: item.ref, filter: "pins", rank: 0 };
    if (kind === "junction" && item.id) return { selector: `#junction:${item.id}`, filter: "other", rank: 1 };
    if (kind === "no_connect" && item.id) return { selector: `#no_connect:${item.id}`, filter: "other", rank: 1 };
    if (kind === "label" && item.id) return { selector: `#label:${item.id}`, filter: "labels", rank: 2 };
    if (kind === "sheet_box" && item.role === "pin" && item.net) return { selector: `#net:${item.net}`, filter: "sheets", rank: 2 };
    if ((kind === "wire" || kind === "bus") && item.id) {
      const found = index.items.get(item.id);
      const named = found && (found.kind === "wire" || found.kind === "bus" || found.kind === "bus_entry") ? found.kind : kind;
      return { selector: `#${named}:${item.id}`, filter: "wires", rank: 3 };
    }
    if (kind === "field" && item.ref) return { selector: item.ref, filter: "symbols", rank: 4 };
    if (kind === "symbol") {
      const found = item.id ? index.items.get(item.id) : null;
      const selector = found?.kind === "symbol" ? `#${found.ref}` : found?.kind === "label" ? `#label:${item.id}` : null;
      return selector ? { selector, filter: "symbols", rank: 5 } : null;
    }
    if (kind === "sheet_box" && item.ref) return { selector: item.ref, filter: "sheets", rank: 6 };
    return null;
  }
  const quote = (selector) => {
    // A net's name may need quoting in its canonical form.
    const parsed = parseSchematicRefSelector(selector);
    if (parsed) return parsed.canonical;
    if (selector.startsWith("#net:")) return `#net:${JSON.stringify(selector.slice(5))}`;
    return selector;
  };

  /**
   * What is under `point` that `kinds` (Select's filter, the `SCHEMATIC_PICK_KINDS` ticked) takes, within
   * `tolerance` millimetres: the nearest ink — a pin, a junction or a no-connect, a label (a sheet pin, its
   * net), a wire, a field (its part), a symbol's outline (its part; a power symbol, its label), a sheet
   * symbol's outline — or the symbol body or sheet symbol the point is inside; of those about as near (half
   * the reach), the most specific, in that order. `{ selector, kind }`, or null.
   */
  function pick(point, { kinds = SCHEMATIC_PICK_KINDS, tolerance = 0.5 } = {}) {
    const wanted = new Set(kinds);
    const hits = [];
    for (const entry of drawn) {
      if (!inBox(entry.item.box, point, tolerance)) continue;
      const pickEntry = pickOf(entry);
      if (!pickEntry || !wanted.has(pickEntry.filter)) continue;
      const distance = inkDistance(entry.item, point);
      if (distance <= tolerance) hits.push({ ...pickEntry, distance, area: 0 });
    }
    // Inside a body or a sheet's box is as near as its ink, and the least specific: the smallest box first.
    for (const area of [...(wanted.has("symbols") ? bodies : EMPTY), ...(wanted.has("sheets") ? sheetBoxes : EMPTY)]) {
      if (area.box && inBox(area.box, point)) {
        hits.push({ selector: area.selector, filter: area.kind, rank: 7, distance: 0, area: (area.box[2] - area.box[0]) * (area.box[3] - area.box[1]) });
      }
    }
    if (!hits.length) return null;
    const nearest = Math.min(...hits.map((hit) => hit.distance));
    const near = hits.filter((hit) => hit.distance <= nearest + tolerance / 2);
    near.sort((a, b) => a.rank - b.rank || a.area - b.area || a.distance - b.distance);
    return { selector: quote(near[0].selector), kind: near[0].filter };
  }

  /** Everything `kinds` takes whose ink lies wholly inside `box` (KiCad's window selection), once each. */
  function within(box, { kinds = SCHEMATIC_PICK_KINDS } = {}) {
    const wanted = new Set(kinds);
    const found = new Map();
    for (const entry of drawn) {
      const pickEntry = pickOf(entry);
      if (!pickEntry || !wanted.has(pickEntry.filter) || found.has(pickEntry.selector)) continue;
      // A part is inside when its body is, a sheet when its box is: each is judged by its whole below.
      if (pickEntry.filter === "symbols" || (pickEntry.filter === "sheets" && entry.item.role !== "pin")) continue;
      if (insideBox(entry.item.box, box)) found.set(pickEntry.selector, quote(pickEntry.selector));
    }
    if (wanted.has("symbols")) for (const body of bodies) if (body.box && insideBox(body.box, box)) found.set(body.selector, body.selector);
    if (wanted.has("sheets")) for (const area of sheetBoxes) if (insideBox(area.box, box)) found.set(area.selector, area.selector);
    return [...found.values()];
  }

  /** The child sheet whose symbol is under `point` (its box, `tolerance` round it): its path, or null. */
  function sheetAt(point, tolerance = 0) {
    const hit = sheetBoxes.find((area) => inBox(area.box, point, tolerance));
    return hit ? hit.path : null;
  }

  // Measure's ends: pin tips, wire ends, junctions, label anchors, sheet pins.
  const snaps = [];
  for (const pin of index.pins.values()) if (pin.sheet === path && !pin.hidden) snaps.push({ point: pin.at, kind: "pin" });
  for (const item of index.items.values()) {
    if (item.sheet !== path) continue;
    if (item.kind === "junction") snaps.push({ point: item.at, kind: "junction" });
    else if (item.kind === "label") snaps.push({ point: item.at, kind: "label" });
    else if ((item.kind === "wire" || item.kind === "bus" || item.kind === "bus_entry") && item.points?.length) {
      snaps.push({ point: item.points[0], kind: "end" }, { point: item.points[item.points.length - 1], kind: "end" });
    }
  }
  for (const child of index.childrenOf(path)) for (const pin of index.sheets.get(child)?.pins || EMPTY) snaps.push({ point: pin.at, kind: "pin" });
  /** The nearest end within `tolerance` of `point`: `{ point, kind }`, or null. */
  function snap(point, { tolerance = 0.5 } = {}) {
    // Nearest first; of ends that meet, the pin's (they are listed first).
    let best = null, bestDistance = Infinity;
    for (const candidate of snaps) {
      const distance = Math.hypot(candidate.point[0] - point[0], candidate.point[1] - point[1]);
      if (distance <= tolerance && distance < bestDistance - 1e-9) { best = candidate; bestDistance = distance; }
    }
    return best;
  }

  return { path, drawn, itemsOf, extent, pick, within, sheetAt, snap };
}
