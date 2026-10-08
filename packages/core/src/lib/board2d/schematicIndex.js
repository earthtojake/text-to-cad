/**
 * A schematic's index (`payload.schematic` of a KiCad schematic's plot), made ready to point at: the
 * symbol, pin or net under a point of the picture, the reference a person hands the agent for it,
 * and back again from a reference to what it names. The references are a board's (`#U3`, `#U3.9`,
 * `#net:VIN`): a pin is numbered as its pad is, so one reference names one connection in both
 * documents. A schematic has no points of its own to name: `#@x..y..` and copper are a board's.
 *
 * Geometry arrives in SHEET coordinates (millimetres, y down, from the corner of the sheet it is on:
 * KiCad's schematic frame, which its plot keeps) and is kept in PAGE coordinates (each sheet's place
 * in the laid-out plot added, `layoutPlot`). Where a symbol stands is KiCad's layout, not the design,
 * so nothing here reports a position.
 *
 * It wears a board index's face where the viewer reads both (`boardIndex.js`): `document`, `parts`
 * (each with its pins as `pads`), `pads` (a pin by `U3.9`), `nets` (each with its pins as `pads`),
 * `findings`, `pick`, `resolve` and `extent`. Pure, and found through a grid of the page
 * (`spatialGrid.js`), as the board's.
 */
import { formatBoardRefSelector, parseBoardRefSelector } from "../boardRefs.js";
import { nearestOnSegment, pointInPolygon, polygonArea } from "./boardIndex.js";
import { boxOf, createSpatialGrid, nearBox } from "./spatialGrid.js";

const EMPTY = Object.freeze([]);
// A pin and a wire are hairlines: how far off one a press still lands on it (page millimetres), and
// a junction's dot, before the view's own few pixels of slop.
const PIN_REACH = 0.5;
const WIRE_REACH = 0.35;
const JUNCTION_REACH = 0.6;

const point = (value) => (Array.isArray(value) && value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))
  ? [Number(value[0]), Number(value[1])] : null);

function bounds(points) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  }
  return Number.isFinite(minX) ? [minX, minY, maxX, maxY] : null;
}

function polygonDistance(at, polygon) {
  if (polygon.length < 3) return Infinity;
  if (pointInPolygon(at, polygon)) return 0;
  let distance = Infinity;
  for (let index = 0; index < polygon.length; index += 1) {
    distance = Math.min(distance, nearestOnSegment(at, polygon[index], polygon[(index + 1) % polygon.length]).distance);
  }
  return distance;
}

/**
 * @param {object} schematic  The payload's `schematic`.
 * @param {ReadonlyArray<{ name: string, x: number, y: number }>} [layoutSheets]  The plot's laid-out
 *   sheets (`layoutPlot(...).sheets`); an index sheet sits on the plot sheet of its name, else on the
 *   plot sheet of its place. One the plot did not draw holds nothing to point at.
 */
export function createSchematicIndex(schematic, layoutSheets = EMPTY) {
  const sheets = (schematic?.sheets || EMPTY).map((entry, at) => {
    const name = String(entry?.name ?? "");
    const placed = layoutSheets.find((candidate) => candidate.name === name) ?? layoutSheets[at] ?? null;
    return {
      name, path: String(entry?.path ?? ""), file: String(entry?.file ?? ""), title: String(entry?.title ?? ""),
      x: Number(placed?.x) || 0, y: Number(placed?.y) || 0, placed: Boolean(placed)
    };
  });
  const sheetAt = (value) => {
    const sheet = sheets[Number(value) || 0];
    return sheet?.placed ? sheet : null;
  };
  const page = (value, sheetIndex) => {
    const sheet = sheetAt(sheetIndex);
    const p = sheet && point(value);
    return p ? [p[0] + sheet.x, p[1] + sheet.y] : null;
  };
  const pageList = (values, sheetIndex) => (Array.isArray(values) ? values.map((value) => page(value, sheetIndex)).filter(Boolean) : []);

  // What KiCad's ERC reported (`schematic.findings`), as a board's are: each item where it is on the page.
  const findings = Object.freeze((schematic?.findings || EMPTY).map((entry, index) => ({
    kind: "finding", index, check: String(entry?.check ?? ""), severity: String(entry?.severity ?? ""), type: String(entry?.type ?? ""),
    description: String(entry?.description ?? ""), summary: String(entry?.summary || entry?.description || ""),
    items: (entry?.items || EMPTY).map((item) => ({
      text: String(item?.text ?? ""), ref: item?.ref ? String(item.ref) : "", at: item?.at && item?.sheet != null ? page(item.at, item.sheet) : null,
    })),
  })));

  const nets = new Map();
  const netNamed = (name) => {
    const key = String(name ?? "");
    if (!key) return null;
    let net = nets.get(key);
    if (!net) {
      net = { kind: "net", name: key, class: "", pads: [], wires: [], labels: [], junctions: [] };
      nets.set(key, net);
    }
    return net;
  };
  for (const entry of schematic?.nets || EMPTY) {
    const net = netNamed(entry?.name);
    if (net) net.class = String(entry?.class || "");
  }

  const parts = new Map();
  for (const entry of schematic?.parts || EMPTY) {
    const ref = String(entry?.ref || "");
    if (!ref) continue;
    const units = (entry.units || EMPTY).map((unit) => {
      const outline = pageList(unit?.outline, unit?.sheet);
      return {
        unit: Number(unit?.unit) || 1, sheet: Number(unit?.sheet) || 0, sheetName: sheets[Number(unit?.sheet) || 0]?.name ?? "",
        at: page(unit?.at, unit?.sheet), rotation: Number(unit?.rotation) || 0, mirror: unit?.mirror === "x" || unit?.mirror === "y" ? unit.mirror : null,
        outline, area: outline.length > 2 ? polygonArea(outline) : Infinity, box: outline.length > 2 ? boxOf(outline) : null
      };
    }).filter((unit) => unit.at || unit.outline.length);
    parts.set(ref, {
      kind: "part", ref, value: String(entry.value ?? ""), footprint: String(entry.footprint ?? ""), lib: String(entry.lib ?? ""),
      fields: entry.fields && typeof entry.fields === "object" ? { ...entry.fields } : {}, script: entry.script ? String(entry.script) : "",
      dnp: Boolean(entry.dnp), units, pads: []
    });
  }

  // A pin common to every unit (a package's power pins) is drawn by each placed unit: every drawing
  // picks it, the first names it.
  const pads = new Map();
  const pinShapes = [];
  // Each pin's drawings, by `U3.9`: a pin is highlighted as all of them.
  const shapesByPin = new Map();
  for (const entry of schematic?.pins || EMPTY) {
    const part = parts.get(String(entry?.part || ""));
    const number = String(entry?.number ?? "");
    const at = page(entry?.at, entry?.sheet);
    if (!part || !number || !at) continue;
    const end = page(entry.end, entry.sheet) || at;
    const pin = {
      kind: "pad", ref: part.ref, number, name: String(entry.name ?? ""), net: String(entry.net ?? ""), type: String(entry.type ?? ""),
      unit: Number(entry.unit) || 1, sheet: Number(entry.sheet) || 0, at, end, hidden: Boolean(entry.hidden), part, box: boxOf([at, end])
    };
    pinShapes.push(pin);
    part.pads.push(pin);
    const key = `${part.ref}.${number}`;
    if (pads.has(key)) { shapesByPin.get(key).push(pin); continue; }
    pads.set(key, pin);
    shapesByPin.set(key, [pin]);
    netNamed(pin.net)?.pads.push(pin);
  }

  const wires = (schematic?.wires || EMPTY).map((entry) => {
    const points = pageList(entry?.points, entry?.sheet);
    return { kind: "wire", net: String(entry?.net ?? ""), points, box: boxOf(points) };
  }).filter((wire) => wire.points.length > 1);
  const labels = (schematic?.labels || EMPTY).map((entry) => {
    const outline = pageList(entry?.outline, entry?.sheet);
    const at = page(entry?.at, entry?.sheet);
    return {
      kind: "label", net: String(entry?.net ?? ""), text: String(entry?.text ?? ""), type: String(entry?.kind ?? "local"),
      at, outline, area: outline.length > 2 ? polygonArea(outline) : Infinity, box: outline.length > 2 ? boxOf(outline) : at ? boxOf([at]) : null
    };
  }).filter((label) => label.at);
  const junctions = (schematic?.junctions || EMPTY).map((entry) => ({ kind: "junction", net: String(entry?.net ?? ""), at: page(entry?.at, entry?.sheet) }))
    .filter((junction) => junction.at);
  for (const wire of wires) netNamed(wire.net)?.wires.push(wire);
  for (const label of labels) netNamed(label.net)?.labels.push(label);
  for (const junction of junctions) netNamed(junction.net)?.junctions.push(junction);

  // ---- what is near a point --------------------------------------------------
  // Each kind in a grid of its own; `order` is a hit's place among them all (pins, labels, wires,
  // junctions, symbols' units), which decides between two hits that are otherwise alike.
  const pinGrid = createSpatialGrid(pinShapes.map((pin) => (pin.hidden ? null : pin.box)));
  const labelGrid = createSpatialGrid(labels.map((label) => label.box));
  const wireGrid = createSpatialGrid(wires.map((wire) => wire.box));
  const junctionGrid = createSpatialGrid(junctions.map((junction) => boxOf([junction.at])));
  const units = [...parts.values()].flatMap((part) => part.units.filter((unit) => unit.outline.length > 2).map((unit) => ({ part, unit })));
  const unitGrid = createSpatialGrid(units.map(({ unit }) => unit.box));
  const LABELS_FROM = pinShapes.length;
  const WIRES_FROM = LABELS_FROM + labels.length;
  const JUNCTIONS_FROM = WIRES_FROM + wires.length;
  const UNITS_FROM = JUNCTIONS_FROM + junctions.length;

  // ---- picking ---------------------------------------------------------------
  /**
   * What is under page point `at`, as a hit `{ kind, selector, part | pad | net }`, or null. `mode`:
   * all (the most specific: a pin, then a label, a wire or a junction for its net, then a symbol) |
   * parts (a symbol, its pins included) | pads (a pin) | nets (anything on a net). `tolerance`: page
   * millimetres a hairline may be missed by.
   */
  function pick(at, { mode = "all", tolerance = 0 } = {}) {
    if (!point(at)) return null;
    const reach = Math.max(0, Number(tolerance) || 0);
    const [x, y] = at;
    const candidates = [];
    const consider = (rank, distance, size, order, hit) => candidates.push({ rank, distance, size, order, hit });
    const near = (grid, slop, fn) => grid.visit(x - slop, y - slop, x + slop, y + slop, fn);
    near(pinGrid, PIN_REACH + reach, (order) => {
      const pin = pinShapes[order];
      if (!nearBox(pin.box, at, PIN_REACH + reach)) return;
      const distance = nearestOnSegment(at, pin.at, pin.end).distance;
      if (distance <= PIN_REACH + reach) consider(mode === "parts" ? 1 : 0, distance, 0, order, { kind: "pad", pad: pads.get(`${pin.ref}.${pin.number}`) || pin });
    });
    if (mode === "all" || mode === "nets") {
      near(labelGrid, reach, (order) => {
        const label = labels[order];
        if (!nearBox(label.box, at, reach)) return;
        const distance = label.outline.length > 2 ? polygonDistance(at, label.outline) : Math.hypot(x - label.at[0], y - label.at[1]);
        if (distance <= reach) consider(1, distance, label.area, LABELS_FROM + order, { kind: "label", item: label });
      });
      near(wireGrid, WIRE_REACH + reach, (order) => {
        const wire = wires[order];
        if (!nearBox(wire.box, at, WIRE_REACH + reach)) return;
        let distance = Infinity;
        for (let index = 1; index < wire.points.length; index += 1) distance = Math.min(distance, nearestOnSegment(at, wire.points[index - 1], wire.points[index]).distance);
        if (distance <= WIRE_REACH + reach) consider(2, distance, 0, WIRES_FROM + order, { kind: "wire", item: wire });
      });
      near(junctionGrid, JUNCTION_REACH + reach, (order) => {
        const junction = junctions[order];
        const distance = Math.hypot(x - junction.at[0], y - junction.at[1]);
        if (distance <= JUNCTION_REACH + reach) consider(2, distance, 0, JUNCTIONS_FROM + order, { kind: "junction", item: junction });
      });
    }
    if (mode === "all" || mode === "parts") {
      near(unitGrid, 0, (order) => {
        const { part, unit } = units[order];
        if (nearBox(unit.box, at, 0) && pointInPolygon(at, unit.outline)) consider(mode === "parts" ? 0 : 3, 0, unit.area, UNITS_FROM + order, { kind: "part", part });
      });
    }
    // A mode that does not take a kind's own pick still lets it lead to what the mode takes.
    candidates.sort((a, b) => a.rank - b.rank || a.distance - b.distance || a.size - b.size || a.order - b.order);
    for (const candidate of candidates) {
      const found = describeHit(candidate.hit, mode);
      if (found) return found;
    }
    return null;
  }

  function describeHit(hit, mode) {
    if (mode === "parts") {
      const part = hit.part || hit.pad?.part;
      return part ? { kind: "part", part, selector: formatBoardRefSelector({ kind: "part", ref: part.ref }) } : null;
    }
    if (hit.kind === "pad" && mode !== "nets") {
      return { kind: "pad", pad: hit.pad, selector: formatBoardRefSelector({ kind: "pad", ref: hit.pad.ref, pad: hit.pad.number }) };
    }
    if (hit.kind === "part") return mode === "all" ? { kind: "part", part: hit.part, selector: formatBoardRefSelector({ kind: "part", ref: hit.part.ref }) } : null;
    if (mode === "pads") return null;
    const net = nets.get(hit.pad?.net ?? hit.item?.net ?? "");
    return net ? { kind: "net", net, selector: formatBoardRefSelector({ kind: "net", net: net.name }) } : null;
  }

  // ---- references -> what they name ------------------------------------------
  /** What a reference names on this schematic: `{ kind, selector, part | pad | net }`, or null. */
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
    return null;
  }

  const pinPoints = (pin) => [pin.at, pin.end];
  /** A pin's drawings: the one that names it and any other unit's drawing of it. */
  const shapesOf = (pad) => shapesByPin.get(`${pad.ref}.${pad.number}`) || [pad];

  /** Where a resolved reference is on the page, as a box to frame: `[minX, minY, maxX, maxY]`. */
  function extent(resolved) {
    if (!resolved) return null;
    if (resolved.kind === "part") return bounds([...resolved.part.units.flatMap((unit) => unit.outline), ...resolved.part.pads.flatMap(pinPoints)]);
    if (resolved.kind === "pad") return bounds(shapesOf(resolved.pad).flatMap(pinPoints));
    if (resolved.kind === "net") {
      const net = resolved.net;
      return bounds([
        ...net.pads.flatMap((pad) => shapesOf(pad).flatMap(pinPoints)), ...net.wires.flatMap((wire) => wire.points),
        ...net.labels.flatMap((label) => (label.outline.length ? label.outline : [label.at])), ...net.junctions.map((junction) => junction.at)
      ]);
    }
    return null;
  }

  return Object.freeze({
    document: "schematic", sheets, parts, pads, pinShapes, nets, wires, labels, junctions, findings,
    pick, resolve, extent, shapesOf
  });
}
