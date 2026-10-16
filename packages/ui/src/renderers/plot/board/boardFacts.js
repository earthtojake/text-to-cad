import { formatBoardRefSelector } from "@text-to-cad/core/lib/boardRefs.js";

/**
 * What the Reference panel says about one board reference: its heading (what it is, as a person
 * names it — never the raw id, which is the ID row) and its rows, label and value, in KiCad's
 * millimetres (y down). Pure data; the Reference panel (`BoardPanels.jsx`) draws it.
 *
 * A row that names other things on the board carries them as a third element, `links`: each
 * `{ text, selector }` the panel draws as a button that selects it (a pad's net, a net's parts),
 * as a robot's Reference selects the links it names; a `text` without a selector reads as words.
 */

const mm = (value) => `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 })} mm`;
const position = ([x, y]) => `x ${Number(x).toLocaleString(undefined, { maximumFractionDigits: 3 })}, y ${Number(y).toLocaleString(undefined, { maximumFractionDigits: 3 })}`;
const plural = (count, noun) => `${count} ${noun}${count === 1 ? "" : "s"}`;
const titleCase = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text);
const FIELD_ROWS = ["MPN", "Manufacturer", "LCSC", "Description"];

function trackLength(track) {
  let length = 0;
  for (let index = 1; index < track.points.length; index += 1) {
    const [ax, ay] = track.points[index - 1];
    const [bx, by] = track.points[index];
    length += Math.hypot(bx - ax, by - ay);
  }
  return length;
}

const name = (pad) => (pad.name && pad.name !== pad.number && pad.name !== "~" ? pad.name : "");

const partSelector = (ref) => formatBoardRefSelector({ kind: "part", ref });
const netSelector = (net) => formatBoardRefSelector({ kind: "net", net });
/** A row whose value is one thing on the document, which its button selects. */
const linked = (label, text, selector) => [label, text, [{ text, selector }]];
/** A pad's net row: the net selects, "None" is words. */
const netRow = (net) => (net ? linked("Net", net, netSelector(net)) : ["Net", "None"]);
/** A part's row, named by its reference and value. */
const partRow = (part) => linked("Part", [part.ref, part.value].filter(Boolean).join(" · "), partSelector(part.ref));
/** What a list shown only to its first `shown` says of the rest: "and 3 more", or nothing. */
export const moreThan = (count, shown) => (count > shown ? `and ${count - shown} more` : "");
/** A net's Parts row: the first twelve select, the rest are counted. */
function partsRow(refs) {
  if (!refs.length) return ["Parts", "None"];
  const shown = refs.slice(0, 12);
  const more = moreThan(refs.length, 12);
  return ["Parts", [shown.join(", "), more].filter(Boolean).join(" "),
    [...shown.map((ref) => ({ text: ref, selector: partSelector(ref) })), ...(more ? [{ text: more }] : [])]];
}

/**
 * @param {object} resolved  `index.resolve(selector)` or a pick.
 * @param {{ toScript(point: number[]): number[] }} index
 * @returns {{ heading: string, rows: [string, string][] } | null}
 */
export function boardReferenceFacts(resolved, index) {
  if (!resolved) return null;
  const id = ["ID", resolved.selector];
  if (resolved.kind === "part") {
    const part = resolved.part;
    const fields = FIELD_ROWS.filter((key) => part.fields[key]).map((key) => [key, String(part.fields[key])]);
    const pins = new Set(part.pads.map((pad) => pad.number)).size;
    return {
      heading: [part.ref, part.value].filter(Boolean).join(" · "),
      rows: [
        ["Footprint", part.footprint.split(":").pop() || part.footprint],
        ["Side", titleCase(part.side)],
        ["Position", position(index.toScript(part.at))],
        ["Rotation", `${Number(part.rotation).toLocaleString(undefined, { maximumFractionDigits: 2 })}°`],
        ["Pads", String(pins)],
        ...fields,
        ...(part.dnp ? [["DNP", "Not assembled"]] : []),
        id,
      ],
    };
  }
  if (resolved.kind === "pad") {
    const pad = resolved.pad;
    return {
      heading: `${pad.ref} · pad ${pad.number}${name(pad) ? ` ${name(pad)}` : ""}`,
      rows: [
        netRow(pad.net),
        ...(name(pad) ? [["Pin", name(pad)]] : []),
        ...(pad.type ? [["Type", pad.type.replaceAll("_", " ")]] : []),
        ["Side", pad.side === "both" ? "Both (through-hole)" : titleCase(pad.side)],
        ["Position", position(index.toScript(pad.at))],
        partRow(pad.part),
        id,
      ],
    };
  }
  if (resolved.kind === "net") {
    const net = resolved.net;
    const refs = [...new Set(net.pads.map((pad) => pad.ref))];
    const length = net.tracks.reduce((sum, track) => sum + trackLength(track), 0);
    const pours = [...new Set(net.zones.map((zone) => zone.layer))];
    return {
      heading: `net ${net.name}`,
      rows: [
        ...(net.class ? [["Class", net.class]] : []),
        ["Pads", plural(net.pads.length, "pad")],
        partsRow(refs),
        ["Tracks", net.tracks.length ? `${net.tracks.length} · ${mm(length)}` : "None"],
        ["Vias", String(net.vias.length)],
        ...(pours.length ? [["Pours", pours.join(", ")]] : []),
        id,
      ],
    };
  }
  if (resolved.kind === "copper") {
    const item = resolved.item;
    const what = item?.kind === "via" ? "via" : item?.kind === "zone" ? "pour" : "track";
    const rows = [linked("Net", resolved.net.name, netSelector(resolved.net.name))];
    if (item?.kind === "track") rows.push(["Layer", item.layer], ["Width", mm(item.width)], ["Length", mm(trackLength(item))]);
    if (item?.kind === "via") rows.push(["Diameter", mm(item.diameter)], ["Drill", mm(item.drill)]);
    if (item?.kind === "zone") rows.push(["Layer", item.layer]);
    rows.push(["Position", position(resolved.at)], id);
    return { heading: `${resolved.net.name} · ${what}`, rows };
  }
  if (resolved.kind === "point") return { heading: "Point", rows: [["Position", position(resolved.at)], id] };
  return null;
}
