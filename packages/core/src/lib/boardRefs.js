// The board-reference language of KiCad boards (.kicad_pcb): what a person picks on a board and
// hands to the agent, which `cad.kicad_pcb.read_board(path).resolve(ref)` reads.
// Mirrors cad/engine/formats/kicad/refs.py; both assert boardRefs.parity.json.
//
//   #U3                   a part: a footprint, by reference designator (letters, digits, _ + -)
//   #U3.9                 its pad 9, numbered as KiCad numbers it: 9, A4, EP
//   #net:VIN              a net by name, JSON-quoted when it holds whitespace, a quote, a comma, '@' or '#'
//   #net:VIN@x40.1y21.6   a board's copper of that net at a point
//   #track:<uuid>         a track or an arc, by the uuid KiCad saved it with; #via:, #zone:, #text: (a
//                         board's or a footprint's), #dimension: and #shape: (a gr_* or fp_* graphic) alike
//   #@x40.1y21.6          a point on a board, in KiCad's millimetres (y down, from the page origin)
//   #F.Cu@x40.1y21.6      a point on one layer, by KiCad's name for it
//   #@x10y5..x20y15       an area, the box between two corners (#F.Cu@x10y5..x20y15 on one layer)
//
// A token is `<file>#<selectors>`, as a STEP token is: several selectors are comma-joined after one
// '#', split outside quotes, so a point is comma-free. An item's uuid is lower case in the canonical
// form; copies of a footprint that share their items' uuids name one under its footprint's uuid
// (`#text:<footprint uuid>/<uuid>`).

const REF_SOURCE = "[A-Za-z_][A-Za-z0-9_+-]*";
const PAD_SOURCE = "[A-Za-z0-9_+-]+";
const NUMBER_SOURCE = "-?\\d+(?:\\.\\d+)?";
const PART_RE = new RegExp(`^(${REF_SOURCE})$`);
const PAD_RE = new RegExp(`^(${REF_SOURCE})\\.(${PAD_SOURCE})$`);
const POINT_RE = new RegExp(`^x(${NUMBER_SOURCE})y(${NUMBER_SOURCE})$`);
const AREA_RE = new RegExp(`^x(${NUMBER_SOURCE})y(${NUMBER_SOURCE})\\.\\.x(${NUMBER_SOURCE})y(${NUMBER_SOURCE})$`);
const BARE_NET_RE = /^[^\s"@#,]+$/;
// KiCad's own layer names, as a board file writes them.
const LAYER_SOURCE = "(?:[FB]\\.(?:Cu|Adhes|Paste|SilkS|Mask|CrtYd|Fab)|In[0-9]{1,2}\\.Cu|(?:Dwgs|Cmts|Eco1|Eco2)\\.User|Edge\\.Cuts|Margin|User\\.[0-9]{1,2})";
const LAYER_RE = new RegExp(`^${LAYER_SOURCE}$`);
const HEX_SOURCE = "[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)*";
const ID_RE = new RegExp(`^${HEX_SOURCE}(?:/${HEX_SOURCE})?$`);
/** The kinds a board names by the uuid KiCad saved them with (`#track:<uuid>`). */
export const BOARD_ITEM_KINDS = Object.freeze(["track", "via", "zone", "text", "dimension", "shape"]);
const ITEM_RE = new RegExp(`^(${BOARD_ITEM_KINDS.join("|")}):(${HEX_SOURCE}(?:/${HEX_SOURCE})?)$`);
const SPOT_RE = new RegExp(`^(${LAYER_SOURCE})?@(.*)$`);
/** Whether a path names a KiCad board, whose selectors are board references. */
export function isBoardRefPath(path) {
  return String(path || "").toLowerCase().endsWith(".kicad_pcb");
}

/** A coordinate as a reference spells it: at most three decimals, no trailing zeros, no negative zero. */
export function formatBoardCoordinate(value) {
  const rounded = Number(Number(value).toFixed(3));
  if (!Number.isFinite(rounded)) throw new TypeError(`not a coordinate: ${value}`);
  return String(rounded === 0 ? 0 : rounded);
}

function formatNetName(name) {
  const text = String(name);
  return BARE_NET_RE.test(text) ? text : JSON.stringify(text);
}

function formatPoint([x, y]) {
  return `@x${formatBoardCoordinate(x)}y${formatBoardCoordinate(y)}`;
}

function formatLayer(layer) {
  if (layer === undefined || layer === null || layer === "") return "";
  if (!LAYER_RE.test(String(layer))) throw new TypeError(`not a KiCad layer: ${layer}`);
  return String(layer);
}

// An area's corners, low then high, as their canonical text rounds them: a box is the same either way round.
function formatArea(at, to) {
  const [x0, y0] = at.map((value) => Number(formatBoardCoordinate(value)));
  const [x1, y1] = to.map((value) => Number(formatBoardCoordinate(value)));
  return `${formatPoint([Math.min(x0, x1), Math.min(y0, y1)])}..${formatPoint([Math.max(x0, x1), Math.max(y0, y1)]).slice(1)}`;
}

/**
 * The canonical selector for a board entity: `{kind: "part", ref}`, `{kind: "pad", ref, pad}`,
 * `{kind: "net", net}`, `{kind: "copper", net, at}`, an item `{kind: "track" | "via" | "zone" | "text" |
 * "dimension" | "shape", id}` (its uuid), `{kind: "point", at, layer?}` or `{kind: "area", at, to, layer?}`
 * (`at`, `to` = [x, y], script mm; an area's two opposite corners).
 */
export function formatBoardRefSelector({ kind, ref, pad, net, at, to, layer, id } = {}) {
  if (kind === "part") return `#${ref}`;
  if (kind === "pad") return `#${ref}.${pad}`;
  if (kind === "net") return `#net:${formatNetName(net)}`;
  if (kind === "copper") return `#net:${formatNetName(net)}${formatPoint(at)}`;
  if (kind === "point") return `#${formatLayer(layer)}${formatPoint(at)}`;
  if (kind === "area") {
    if (!Array.isArray(at) || !Array.isArray(to)) throw new TypeError("an area is the box between two corners: give at and to");
    return `#${formatLayer(layer)}${formatArea(at, to)}`;
  }
  if (BOARD_ITEM_KINDS.includes(kind)) {
    if (!ID_RE.test(String(id ?? ""))) throw new TypeError(`a ${kind} is named by its uuid, not ${id}`);
    return `#${kind}:${String(id).toLowerCase()}`;
  }
  throw new TypeError(`unknown board reference kind: ${kind}`);
}

function parsePoint(text) {
  const match = POINT_RE.exec(text);
  if (!match) return null;
  const x = Number(match[1]);
  const y = Number(match[2]);
  return [x === 0 ? 0 : x, y === 0 ? 0 : y];
}

// `net:` then a bare name or a JSON string, then optionally `@x..y..`.
function parseNet(text) {
  let name;
  let rest;
  if (text.startsWith('"')) {
    let end = 1;
    while (end < text.length && text[end] !== '"') end += text[end] === "\\" ? 2 : 1;
    if (end >= text.length) return null;
    try {
      name = JSON.parse(text.slice(0, end + 1));
    } catch {
      return null;
    }
    rest = text.slice(end + 1);
  } else {
    const at = text.indexOf("@");
    name = at < 0 ? text : text.slice(0, at);
    rest = at < 0 ? "" : text.slice(at);
    if (!BARE_NET_RE.test(name)) return null;
  }
  if (!name) return null;
  if (!rest) return { kind: "net", net: name };
  if (!rest.startsWith("@")) return null;
  const at = parsePoint(rest.slice(1));
  return at ? { kind: "copper", net: name, at } : null;
}

/**
 * One board selector (with or without its leading '#') as `{kind, ref?, pad?, net?, at?, to?, layer?, id?,
 * canonical}`, or null when it is not one.
 */
export function parseBoardRefSelector(rawSelector) {
  const text = String(rawSelector ?? "").replace(/^#/, "");
  if (!text || text !== text.trim()) return null;
  let parsed = null;
  if (text.startsWith("net:")) {
    parsed = parseNet(text.slice(4));
  } else if (ITEM_RE.test(text)) {
    const [, kind, id] = ITEM_RE.exec(text);
    parsed = { kind, id: id.toLowerCase() };
  } else if (SPOT_RE.test(text)) {
    parsed = parseSpot(text);
  } else {
    const pad = PAD_RE.exec(text);
    if (pad) parsed = { kind: "pad", ref: pad[1], pad: pad[2] };
    else {
      const part = PART_RE.exec(text);
      if (part) parsed = { kind: "part", ref: part[1] };
    }
  }
  return parsed ? { ...parsed, canonical: formatBoardRefSelector(parsed) } : null;
}

// `[<layer>]@x..y..` a point, `[<layer>]@x..y....x..y..` an area (its corners low, then high).
function parseSpot(text) {
  const [, layer, rest] = SPOT_RE.exec(text);
  const where = layer ? { layer } : {};
  const at = parsePoint(rest);
  if (at) return { kind: "point", at, ...where };
  const area = AREA_RE.exec(rest);
  if (!area) return null;
  const [x0, y0, x1, y1] = area.slice(1).map((value) => (Number(value) === 0 ? 0 : Number(value)));
  return { kind: "area", at: [Math.min(x0, x1), Math.min(y0, y1)], to: [Math.max(x0, x1), Math.max(y0, y1)], ...where };
}

// Commas outside quotes separate selectors; a quoted net name keeps its own.
function splitSelectors(text) {
  const pieces = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      current += character;
      if (character === "\\" && index + 1 < text.length) {
        current += text[index + 1];
        index += 1;
      } else if (character === '"') quoted = false;
    } else if (character === '"') {
      quoted = true;
      current += character;
    } else if (character === ",") {
      pieces.push(current);
      current = "";
    } else current += character;
  }
  pieces.push(current);
  return pieces;
}

/**
 * A list of selectors as a host or a person writes one — comma-joined, each with or without its
 * '#', spaces around them ignored — split outside quotes, so `#net:"a,b"` stays one. Not parsed.
 */
export function splitBoardRefSelectors(text) {
  return splitSelectors(String(text ?? "")).map((piece) => piece.trim()).filter(Boolean);
}

/**
 * `<file>#<selectors>` as `{path, selectors}` (canonical selectors, in the order written), or null.
 * The file half is optional and JSON-quoted when it holds whitespace, '#', a quote or a backslash.
 */
export function parseBoardRefToken(token) {
  const text = String(token ?? "").trim();
  let path = "";
  let rest = text;
  if (text.startsWith('"')) {
    let end = 1;
    while (end < text.length && text[end] !== '"') end += text[end] === "\\" ? 2 : 1;
    try {
      path = JSON.parse(text.slice(0, end + 1));
    } catch {
      return null;
    }
    rest = text.slice(end + 1);
  } else {
    const hash = text.indexOf("#");
    if (hash < 0) return null;
    path = text.slice(0, hash);
    rest = text.slice(hash);
  }
  // Whitespace belongs only inside a quoted net name: every selector is checked whole below.
  if (!rest.startsWith("#")) return null;
  const selectors = [];
  for (const piece of splitSelectors(rest.slice(1))) {
    const parsed = parseBoardRefSelector(piece);
    if (!parsed) return null;
    selectors.push(parsed.canonical);
  }
  return { path, selectors };
}

/** `<file>#<selectors>`: the selectors comma-joined after one '#', in the order given. */
export function buildBoardRefToken({ path = "", selectors = [] } = {}) {
  const prefix = String(path || "").trim();
  const encoded = /[\s#"\\]/.test(prefix) ? JSON.stringify(prefix) : prefix;
  const bodies = selectors.map((selector) => {
    const parsed = parseBoardRefSelector(selector);
    if (!parsed) throw new TypeError(`not a board reference: ${selector}`);
    return parsed.canonical.slice(1);
  });
  return `${encoded}#${bodies.join(",")}`;
}
