// The reference language of KiCad schematics (.kicad_sch): what a person picks on a schematic and hands
// to the agent, which `cad.kicad_sch.read(path).resolve(ref)` reads. Mirrors
// cad/engine/formats/kicad/schematic_refs.py. Where a schematic and a board hold the same thing it is
// named the same (`boardRefs.js`), so one reference cross-probes the two:
//
//   #U3                 a part: every unit of it placed, on any sheet
//   #U3.7               its pin 7 (the board's pad 7)
//   #net:VBUS           a net, by KiCad's name (`/Power/VBUS` for a local one)
//   #sheet:/Power/      a sheet, by its path (`/` the root)
//   #wire:<uuid>        a wire, by the uuid KiCad saved it with; so too #bus:, #label:, #junction:,
//                       #no_connect:, #bus_entry: and #symbol: (one unit's placement)
//
// A sheet path holding a comma, whitespace, a quote, '@' or '#' is JSON-quoted (`#sheet:"/Power Stage/"`).
// The canonical form begins and ends a sheet's path with '/'.
import { parseBoardRefSelector, splitBoardRefSelectors } from "./boardRefs.js";

/** The kinds a schematic names by the uuid KiCad saved them with. */
export const SCHEMATIC_ITEM_KINDS = Object.freeze(["wire", "bus", "label", "junction", "no_connect", "bus_entry", "symbol"]);
const HEX_SOURCE = "[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)*";
const ITEM_RE = new RegExp(`^(${SCHEMATIC_ITEM_KINDS.join("|")}):(${HEX_SOURCE})$`);
const SHEET_RE = /^sheet:("(?:[^"\\]|\\.)*"|[^\s"@#,]+)$/s;
const NEEDS_QUOTES = /[\s"@#,]/;

/** Whether a path names a KiCad schematic, whose selectors are schematic references. */
export function isSchematicRefPath(path) {
  return String(path || "").toLowerCase().endsWith(".kicad_sch");
}

/** A sheet's path in its canonical form: `/` the root, `/Power/` a child. */
export function canonicalSheetPath(text) {
  const parts = String(text ?? "").split("/").filter(Boolean);
  return `/${parts.map((part) => `${part}/`).join("")}`;
}

/** The canonical selector of the sheet at `path`: `#sheet:/Power/`. */
export function formatSheetSelector(path) {
  const canonical = canonicalSheetPath(path);
  return `#sheet:${NEEDS_QUOTES.test(canonical) ? JSON.stringify(canonical) : canonical}`;
}

/**
 * One schematic selector (with or without its leading '#') as `{kind, ref?, pad?, net?, sheet?, id?,
 * canonical}`, or null when it is not one. A pin is the board's `pad` kind: the two name one thing.
 */
export function parseSchematicRefSelector(rawSelector) {
  const text = String(rawSelector ?? "").replace(/^#/, "");
  if (!text || text !== text.trim()) return null;
  const sheet = SHEET_RE.exec(text);
  if (sheet) {
    let raw = sheet[1];
    if (raw.startsWith('"')) {
      try { raw = JSON.parse(raw); } catch { return null; }
      if (typeof raw !== "string") return null;
    }
    return { kind: "sheet", sheet: canonicalSheetPath(raw), canonical: formatSheetSelector(raw) };
  }
  const item = ITEM_RE.exec(text);
  if (item) {
    const id = item[2].toLowerCase();
    return { kind: item[1], id, canonical: `#${item[1]}:${id}` };
  }
  const board = parseBoardRefSelector(text);
  if (board && (board.kind === "part" || board.kind === "pad" || board.kind === "net")) {
    return { kind: board.kind, ...(board.ref ? { ref: board.ref } : {}), ...(board.pad ? { pad: board.pad } : {}),
      ...(board.net ? { net: board.net } : {}), canonical: board.canonical };
  }
  return null;
}

/** A list of selectors as a host or a person writes one, split outside quotes (`boardRefs.js`'s). Not parsed. */
export const splitSchematicRefSelectors = splitBoardRefSelectors;

/** `<file>#<selectors>`: the canonical selectors comma-joined after one '#', in the order given. */
export function buildSchematicRefToken({ path = "", selectors = [] } = {}) {
  const prefix = String(path || "").trim();
  const encoded = /[\s#"\\]/.test(prefix) ? JSON.stringify(prefix) : prefix;
  const bodies = selectors.map((selector) => {
    const parsed = parseSchematicRefSelector(selector);
    if (!parsed) throw new TypeError(`not a schematic reference: ${selector}`);
    return parsed.canonical.slice(1);
  });
  return `${encoded}#${bodies.join(",")}`;
}

/**
 * `<file>#<selectors>` as `{path, selectors}` (canonical selectors, in the order written), or null: the
 * board's token (`boardRefs.js`), its selectors a schematic's. The file half is optional and JSON-quoted
 * when it holds whitespace, '#', a quote or a backslash.
 */
export function parseSchematicRefToken(token) {
  const text = String(token ?? "").trim();
  let path = "";
  let rest = text;
  if (text.startsWith('"')) {
    let end = 1;
    while (end < text.length && text[end] !== '"') end += text[end] === "\\" ? 2 : 1;
    try { path = JSON.parse(text.slice(0, end + 1)); } catch { return null; }
    rest = text.slice(end + 1);
  } else {
    const hash = text.indexOf("#");
    if (hash < 0) return null;
    path = text.slice(0, hash);
    rest = text.slice(hash);
  }
  if (!rest.startsWith("#")) return null;
  const selectors = [];
  for (const piece of splitBoardRefSelectors(rest.slice(1))) {
    const parsed = parseSchematicRefSelector(piece);
    if (!parsed) return null;
    selectors.push(parsed.canonical);
  }
  return selectors.length ? { path, selectors } : null;
}
