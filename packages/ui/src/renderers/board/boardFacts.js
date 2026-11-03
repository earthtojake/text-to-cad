import { english } from "@cad/ui/i18n";
const FACT_KEYS = {
  "Value": "board.text.value", "Footprint": "board.text.footprint", "Side": "board.text.side", "Position": "position.title", "Rotation": "render.rotation",
  "Net": "board.text.net", "Number": "board.text.number", "Pin": "board.text.pin", "Type": "robot.type", "Class": "board.text.class", "Pads": "board.text.pads",
  "Layer": "drawing.layer", "Layers": "board.text.layers", "Width": "board.text.width", "Length": "measure.length", "Diameter": "board.text.diameter",
  "Drill": "board.text.drill", "Size": "board.text.size", "Priority": "board.text.priority", "Filled": "board.text.filled_area", "Text": "board.text.text",
  "Part": "board.text.part", "Shape": "board.text.shape", "Box": "board.text.box", "Contains": "board.text.contains", "Holds": "board.text.holds"
};
const SHAPE_KEYS = { line: "board.text.shape_line", rect: "board.text.shape_rect", circle: "board.text.shape_circle", arc: "board.text.shape_arc",
  poly: "board.text.shape_poly", curve: "board.text.shape_curve" };
const VIA_KEYS = { through: "board.text.via_through", blind: "board.text.via_blind", buried: "board.text.via_buried", micro: "board.text.via_micro" };
// What an area holds, counted on its card, each by its Select kind's name.
const HELD_KEYS = [["pads", "board.text.pads"], ["tracks", "board.text.tracks"], ["vias", "board.text.vias"], ["zones", "board.text.zones"],
  ["texts", "board.text.texts"], ["dimensions", "board.text.dimensions"], ["shapes", "board.text.graphics"]];
/**
 * What the viewer says of one board reference: its name, as a chip names it (`R1`, `R1.2`,
 * `net VBUS`, `VBUS · track`, `“blinky”`, a point, an area) — never the raw selector, which its card
 * shows as its ID — the pick glyph its chip leads with (`glyph`, a pick glyph's kind, and `icon`, the
 * board's own glyph for it), and its card's rows, in KiCad's millimetres (y down, from KiCad's page
 * origin: what a script's `Vector2.from_xy_mm` takes). Pure data.
 *
 * A part's card is its value, footprint, side, position and rotation (and its fields, DNP and the
 * script line that placed it, when the index has them); a pad's its net, number, pin name, type and
 * position; a net's its class and how many pads are on it; a piece of copper its net, what it is
 * and where it was picked; a track its net, layer, width and length; a via its net, size, drill, the
 * layers it joins and its type; a zone its net, layers, priority and the copper it was filled with (a
 * rule area its layers); a text its words, layer, size (and part); a dimension its value and layer; a graphic its shape, layer
 * and width (and part); a point its position and layer; an area its box, size, layer, the parts that
 * lie inside it and how much else does.
 */

const mm = (value) => `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 3 })} mm`;
const coordinate = (value) => Number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
const position = ([x, y]) => `x ${coordinate(x)}, y ${coordinate(y)}`;
const FIELD_ROWS = ["MPN", "Manufacturer", "LCSC", "Description"];
const pinName = (pad) => (pad.name && pad.name !== pad.number && pad.name !== "~" ? pad.name : "");
// A chip's name is a few words: a long text is cut, its card holding more of it.
const clipped = (text, most) => (text.length > most ? `${text.slice(0, most - 1)}…` : text);
// At most this many parts name themselves on an area's card; the rest are counted.
const PARTS_NAMED = 6;

function trackLength(track) {
  let length = 0;
  for (let index = 1; index < track.points.length; index += 1) {
    const [ax, ay] = track.points[index - 1];
    const [bx, by] = track.points[index];
    length += Math.hypot(bx - ax, by - ay);
  }
  return length;
}

/** The selector as its card's ID reads it: the reference after its file, without the `#`. */
export const boardReferenceId = (selector) => String(selector || "").replace(/^#/, "");

/**
 * @param {object} resolved  `index.resolve(selector)`.
 * @param {{ toScript(point: number[]): number[], within?(box: number[], layer?: string | null): object }} index
 * @returns {{ name: string, glyph: string, icon?: string, facts: { label: string, value: string }[] } | null}
 */
export function describeBoardReference(resolved, index, t = english) {
  if (!resolved) return null;
  const row = (label, value) => ({ label: FACT_KEYS[label] ? t(FACT_KEYS[label]) : label, value: String(value) });
  const netName = (name) => name || t("robot.none");
  if (resolved.kind === "part") {
    const part = resolved.part;
    return {
      name: part.ref, glyph: "solid",
      facts: [
        ...(part.value ? [row("Value", part.value)] : []),
        row("Footprint", part.footprint.split(":").pop() || part.footprint),
        row("Side", t(part.side === "bottom" ? "viewCube.face.bottom" : "viewCube.face.top")),
        row("Position", position(index.toScript(part.at))),
        row("Rotation", `${Number(part.rotation).toLocaleString("en-US", { maximumFractionDigits: 2 })}°`),
        ...FIELD_ROWS.filter((key) => part.fields[key]).map((key) => row(key, part.fields[key])),
        ...(part.dnp ? [row("DNP", t("board.text.not_assembled"))] : []),
        // The line of the board's script that placed it, where the index carries one.
        ...(part.script ? [row("Script", part.script)] : [])
      ]
    };
  }
  if (resolved.kind === "pad") {
    const pad = resolved.pad;
    return {
      name: `${pad.ref}.${pad.number}`, glyph: "face",
      facts: [
        row("Net", pad.net || t("robot.none")),
        row("Number", pad.number),
        ...(pinName(pad) ? [row("Pin", pinName(pad))] : []),
        ...(pad.type ? [row("Type", pad.type.replaceAll("_", " "))] : []),
        row("Position", position(index.toScript(pad.at)))
      ]
    };
  }
  if (resolved.kind === "net") {
    const net = resolved.net;
    return {
      name: t("board.text.net_name", { name: net.name }), glyph: "edge",
      facts: [...(net.class ? [row("Class", net.class)] : []), row("Pads", String(net.pads.length))]
    };
  }
  if (resolved.kind === "copper") {
    const item = resolved.item;
    const what = item?.kind === "via" ? t("board.text.via") : item?.kind === "zone" ? t("board.text.pour") : t("board.text.track");
    const facts = [row("Net", resolved.net.name)];
    if (item?.kind === "track") facts.push(row("Layer", item.layer), row("Width", mm(item.width)), row("Length", mm(trackLength(item))));
    if (item?.kind === "via") facts.push(row("Diameter", mm(item.diameter)), row("Drill", mm(item.drill)));
    if (item?.kind === "zone") facts.push(row("Layer", item.layer));
    facts.push(row("Position", position(resolved.at)));
    return { name: `${resolved.net.name} · ${what}`, glyph: "edge", facts };
  }
  const item = resolved.item;
  if (resolved.kind === "track") {
    const what = item.arc ? t("board.text.arc") : t("board.text.track");
    return {
      name: `${netName(item.net)} · ${what}`, glyph: "edge", icon: "track",
      facts: [row("Net", netName(item.net)), row("Layer", item.layer), row("Width", mm(item.width)), row("Length", mm(trackLength(item)))]
    };
  }
  if (resolved.kind === "via") {
    const ends = item.layers.length > 1 ? `${item.layers[0]} – ${item.layers[item.layers.length - 1]}` : item.layers.join("");
    return {
      name: `${netName(item.net)} · ${t("board.text.via")}`, glyph: "edge", icon: "via",
      facts: [row("Net", netName(item.net)), row("Diameter", mm(item.diameter)), row("Drill", mm(item.drill)), row("Layers", ends),
        row("Type", VIA_KEYS[item.type] ? t(VIA_KEYS[item.type]) : item.type)]
    };
  }
  if (resolved.kind === "zone" && item.rule) {
    return {
      name: item.name || t("board.text.rule_area"), glyph: "edge", icon: "ruleArea",
      facts: [row("Layers", (item.layers || [item.layer]).join(", "))]
    };
  }
  if (resolved.kind === "zone") {
    return {
      name: item.name || `${netName(item.net)} · ${t("board.text.zone")}`, glyph: "edge", icon: "zone",
      facts: [row("Net", netName(item.net)), row("Layers", (item.layers || [item.layer]).join(", ")),
        row("Priority", String(item.priority || 0)),
        row("Filled", item.filled === null || item.filled === undefined ? t("board.text.not_filled") : `${Number(item.filled).toLocaleString("en-US", { maximumFractionDigits: 1 })} mm²`)]
    };
  }
  if (resolved.kind === "text") {
    return {
      name: t("board.text.text_name", { text: clipped(item.text.replace(/\s+/g, " "), 24) }), glyph: "face", icon: "text",
      facts: [row("Text", clipped(item.text, 80)), row("Layer", item.layer), row("Size", mm(item.size)), ...(item.part ? [row("Part", item.part)] : [])]
    };
  }
  if (resolved.kind === "dimension") {
    return {
      name: t("board.text.dimension_name", { value: item.value }), glyph: "edge", icon: "dimension",
      facts: [row("Value", item.value), row("Layer", item.layer)]
    };
  }
  if (resolved.kind === "shape") {
    const shape = SHAPE_KEYS[item.shape] ? t(SHAPE_KEYS[item.shape]) : item.shape;
    return {
      name: t("board.text.shape_on_layer", { shape, layer: item.layer }), glyph: "edge", icon: "shape",
      facts: [row("Shape", shape), row("Layer", item.layer), row("Width", mm(item.width)), ...(item.part ? [row("Part", item.part)] : [])]
    };
  }
  if (resolved.kind === "point") {
    return {
      name: t("board.text.point_x_y", { x: coordinate(resolved.at[0]), y: coordinate(resolved.at[1]) }), glyph: "vertex",
      facts: [row("Position", position(resolved.at)), ...(resolved.layer ? [row("Layer", resolved.layer)] : [])]
    };
  }
  if (resolved.kind === "area") {
    const [x0, y0] = resolved.at;
    const [x1, y1] = resolved.to;
    const held = index.within ? index.within(resolved.box, resolved.layer || null) : null;
    const refs = held ? held.parts.map((part) => part.ref) : [];
    const named = refs.slice(0, PARTS_NAMED).join(", ");
    const counts = held ? HELD_KEYS.filter(([key]) => held[key].length).map(([key, label]) => `${t(label)} ${held[key].length}`) : [];
    return {
      name: t("board.text.area_w_h", { width: coordinate(x1 - x0), height: coordinate(y1 - y0) }), glyph: "vertex", icon: "area",
      facts: [
        row("Box", `x ${coordinate(x0)}–${coordinate(x1)}, y ${coordinate(y0)}–${coordinate(y1)}`),
        ...(resolved.layer ? [row("Layer", resolved.layer)] : []),
        ...(held ? [row("Contains", refs.length > PARTS_NAMED ? t("board.text.count_more", { list: named, count: refs.length - PARTS_NAMED })
          : named || t("board.text.nothing"))] : []),
        ...(counts.length ? [row("Holds", counts.join(" · "))] : [])
      ]
    };
  }
  return null;
}
