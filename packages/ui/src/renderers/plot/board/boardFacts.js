import { formatBoardRefSelector } from "@text-to-cad/core/lib/boardRefs.js";

/**
 * What the Reference panel says about one board reference: its heading (what it is, as a person
 * names it — never the raw id, which is the ID row) and its rows, label and value, in script
 * millimetres. Pure data; the Reference panel (`BoardPanels.jsx`) draws it.
 *
 * A row that names other things on the document carries them as a third element, `links`: each
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
/** A pad's or a pin's net row: the net selects, "None" is words. */
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
        // The line that made it leads what the library says of it: it is where an edit goes.
        ...(part.script ? [["Script", part.script]] : []),
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

/**
 * What the Reference panel says about one schematic reference. A schematic has no positions worth
 * reading (where a symbol stands is KiCad's layout, not the design), so it says what a thing is
 * and what it connects to: a symbol's library entry, footprint and sheet; a pin's net; a net's pins.
 */
export function schematicReferenceFacts(resolved, index) {
  if (!resolved) return null;
  const id = ["ID", resolved.selector];
  const several = (index?.sheets?.filter((sheet) => sheet.placed).length || 0) > 1;
  if (resolved.kind === "part") {
    const part = resolved.part;
    const fields = FIELD_ROWS.filter((key) => part.fields[key]).map((key) => [key, String(part.fields[key])]);
    const pins = new Set(part.pads.map((pad) => pad.number)).size;
    const sheets = [...new Set(part.units.map((unit) => unit.sheetName).filter(Boolean))];
    return {
      heading: [part.ref, part.value].filter(Boolean).join(" · "),
      rows: [
        ["Symbol", part.lib || "None"],
        ["Footprint", part.footprint.split(":").pop() || "None"],
        ...(part.units.length > 1 ? [["Units", String(part.units.length)]] : []),
        ...(several && sheets.length ? [["Sheet", sheets.join(", ")]] : []),
        ["Pins", String(pins)],
        ...(part.script ? [["Script", part.script]] : []),
        ...fields,
        ...(part.dnp ? [["DNP", "Not assembled"]] : []),
        id,
      ],
    };
  }
  if (resolved.kind === "pad") {
    const pin = resolved.pad;
    return {
      heading: `${pin.ref} · pin ${pin.number}${name(pin) ? ` ${name(pin)}` : ""}`,
      rows: [
        netRow(pin.net),
        ...(name(pin) ? [["Name", name(pin)]] : []),
        ...(pin.type ? [["Type", pin.type.replaceAll("_", " ")]] : []),
        partRow(pin.part),
        id,
      ],
    };
  }
  if (resolved.kind === "net") {
    const net = resolved.net;
    const refs = [...new Set(net.pads.map((pad) => pad.ref))];
    const labels = [...new Set(net.labels.filter((label) => label.type !== "power").map((label) => label.text))];
    return {
      heading: `net ${net.name}`,
      rows: [
        ...(net.class ? [["Class", net.class]] : []),
        ["Pins", plural(net.pads.length, "pin")],
        partsRow(refs),
        ...(labels.length ? [["Labels", labels.join(", ")]] : []),
        id,
      ],
    };
  }
  return null;
}

/** The Reference's facts for whichever document `index` is. */
export function referenceFacts(resolved, index) {
  return index?.document === "schematic" ? schematicReferenceFacts(resolved, index) : boardReferenceFacts(resolved, index);
}

/**
 * A finding KiCad (or the review) reported, for the Reference panel when it is chosen in the alert
 * card: headed by its sentence, which its first row gives in full, then KiCad's own words.
 */
export function boardFindingFacts(finding, index) {
  // A schematic has no script frame: an item it cannot name reads as KiCad wrote it.
  const located = (item) => (item.at && index?.toScript ? position(index.toScript(item.at)) : item.text);
  const items = finding.items.map((item) => item.ref || located(item)).filter(Boolean);
  // What it names by reference selects; what it can only place reads as words.
  const links = finding.items.some((item) => item.ref)
    ? finding.items.map((item) => (item.ref ? { text: item.ref, selector: item.ref } : { text: located(item) })).filter((link) => link.text) : null;
  return {
    heading: finding.summary || finding.description || finding.type.replaceAll("_", " "),
    rows: [
      // The sentence in full (the heading may be cut short), where it says more than KiCad's message.
      ...(finding.summary && finding.summary !== finding.description ? [["Finding", finding.summary]] : []),
      ["Check", finding.check.toUpperCase()],
      ["Severity", titleCase(finding.severity)],
      ["Message", finding.description],
      ...(items.length ? [links ? ["Items", items.join(", "), links] : ["Items", items.join(", ")]] : []),
    ],
  };
}

/** What copying a chosen check gives: its sentence, then the references it names. */
export function findingCopyText(finding, token) {
  return token && finding?.summary ? `${finding.summary} · ${token}` : token;
}
