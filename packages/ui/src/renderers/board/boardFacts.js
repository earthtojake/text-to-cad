import { english } from "@text-to-cad/ui/i18n";
const FACT_KEYS = {"Value": "board.text.value", "Footprint": "board.text.footprint", "Side": "board.text.side", "Position": "position.title", "Rotation": "render.rotation", "Net": "board.text.net", "Number": "board.text.number", "Pin": "board.text.pin", "Type": "robot.type", "Class": "board.text.class", "Pads": "board.text.pads", "Layer": "drawing.layer", "Width": "board.text.width", "Length": "measure.length", "Diameter": "board.text.diameter", "Drill": "board.text.drill"};
/**
 * What the viewer says of one board reference: its name, as a chip names it (`R1`, `R1.2`,
 * `net VBUS`, `VBUS · track`, a point) — never the raw selector, which its card shows as its ID —
 * the pick glyph its chip leads with, and its card's rows, in KiCad's millimetres (y down, from
 * KiCad's page origin: what a script's `Vector2.from_xy_mm` takes). Pure data.
 *
 * A part's card is its value, footprint, side, position and rotation (and its fields, DNP and the
 * script line that placed it, when the index has them); a pad's its net, number, pin name, type and position; a net's its class and how many
 * pads are on it; a piece of copper its net, what it is (a track's layer, width and length; a via's
 * diameter and drill) and where it was picked; a point its position.
 */

const mm = (value) => `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 3 })} mm`;
const coordinate = (value) => Number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
const position = ([x, y]) => `x ${coordinate(x)}, y ${coordinate(y)}`;
const FIELD_ROWS = ["MPN", "Manufacturer", "LCSC", "Description"];
const pinName = (pad) => (pad.name && pad.name !== pad.number && pad.name !== "~" ? pad.name : "");

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
 * @param {{ toScript(point: number[]): number[] }} index
 * @returns {{ name: string, glyph: string, facts: { label: string, value: string }[] } | null}
 */
export function describeBoardReference(resolved, index, t = english) {
  if (!resolved) return null;
  const row = (label, value) => ({ label: FACT_KEYS[label] ? t(FACT_KEYS[label]) : label, value: String(value) });
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
  if (resolved.kind === "point") {
    return { name: t("board.text.point_x_y", { x: coordinate(resolved.at[0]), y: coordinate(resolved.at[1]) }), glyph: "vertex", facts: [row("Position", position(resolved.at))] };
  }
  return null;
}
