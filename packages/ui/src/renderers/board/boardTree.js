import { english } from "@cad/ui/i18n";
const GROUP_KEYS = {"ICs": "board.text.ics", "Transistors": "board.text.transistors", "Diodes": "board.text.diodes", "Resistors": "board.text.resistors", "Capacitors": "board.text.capacitors", "Inductors": "board.text.inductors", "Ferrite beads": "board.text.ferrite_beads", "Connectors": "board.text.connectors", "Jumpers": "board.text.jumpers", "Switches": "board.text.switches", "Crystals": "board.text.crystals", "Fuses": "board.text.fuses", "Relays": "board.text.relays", "Transformers": "board.text.transformers", "Batteries": "board.text.batteries", "Test points": "board.text.test_points", "Holes": "board.text.holes", "Fiducials": "board.text.fiducials", "Motors": "board.text.motors", "Buzzers": "board.text.buzzers", "Speakers": "board.text.speakers", "Other": "board.text.other"};
/**
 * A board's lists, two tabs of its panel, as Altium's PCB panel lists Components and Nets: its
 * **Parts**, in blocks — the schematic sheets their footprints record (`(sheetname ...)`, the
 * payload's `parts[].sheet`), else, on a board that records none, their kinds (ICs, Resistors, ...)
 * — and its **Nets**, flat, those of pins on nothing under one shut group. A part's pads and a net's
 * are not rows: they are the picked part's or net's detail (`boardDetail`), under the lists. The
 * search still finds a pad: the Parts' search reads each part with its pads (`partsSearch`).
 * Nodes are what the kit's tree search reads (`id`, `label`, `children`, `selectionId` — the
 * reference a pasted `#U3.9` finds — and `searchAliases`: a part's value, footprint name and MPN),
 * plus what the row selects (`pick`, its reference; a block's `picks`, every part in it) and a muted `detail`.
 */
import { formatBoardRefSelector, parseBoardRefSelector } from "@cad/core/lib/boardRefs.js";
import { describeBoardReference } from "./boardFacts.js";

// KiCad's reference prefixes, read as what the parts are. A prefix not here is "Other".
const KINDS = Object.freeze([
  ["U", "ICs"], ["IC", "ICs"], ["Q", "Transistors"], ["D", "Diodes"], ["LED", "Diodes"],
  ["R", "Resistors"], ["RN", "Resistors"], ["C", "Capacitors"], ["L", "Inductors"], ["FB", "Ferrite beads"],
  ["J", "Connectors"], ["P", "Connectors"], ["CN", "Connectors"], ["JP", "Jumpers"], ["SW", "Switches"],
  ["S", "Switches"], ["Y", "Crystals"], ["X", "Crystals"], ["F", "Fuses"], ["K", "Relays"], ["T", "Transformers"],
  ["BT", "Batteries"], ["TP", "Test points"], ["H", "Holes"], ["MH", "Holes"], ["FID", "Fiducials"],
  ["M", "Motors"], ["BZ", "Buzzers"], ["LS", "Speakers"],
]);
const KIND_BY_PREFIX = new Map(KINDS);
const KIND_ORDER = [...new Set(KINDS.map(([, kind]) => kind)), "Other"];

const prefixOf = (ref) => (/^[A-Za-z]+/.exec(ref)?.[0] || "").toUpperCase();
// One collator for every comparison: `localeCompare` with options builds a collator per call, which
// on a board of thousands of parts and pads is most of the tree's cost.
const NATURAL = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
/** Natural order: C2 before C10. */
export const naturalCompare = (left, right) => NATURAL.compare(String(left), String(right));

/** The kind a reference designator says a part is ("Capacitors" for C14). */
export function partKind(ref) {
  return KIND_BY_PREFIX.get(prefixOf(ref)) || "Other";
}

function padNode(pad, { underNet = false } = {}) {
  const name = pad.name && pad.name !== pad.number && pad.name !== "~" ? pad.name : "";
  return {
    id: `${underNet ? "netpad" : "pad"}:${pad.ref}.${pad.number}`, kind: "pad", pick: `#${pad.ref}.${pad.number}`,
    // Under its part a pad is its number; under a net it is the part and the number.
    label: underNet ? `${pad.ref}.${pad.number}` : pad.number,
    detail: underNet ? name : [name, pad.net].filter(Boolean).join(" · "),
    selectionId: `${pad.ref}.${pad.number}`, searchAliases: name ? [name] : [], children: [],
  };
}

// A part's pads, one a number (a pin's pads under one number are one pin), in natural order.
function partPads(index, part) {
  const seen = new Set();
  return [...part.pads].filter((pad) => !seen.has(pad.number) && seen.add(pad.number)).sort((a, b) => naturalCompare(a.number, b.number))
    .map((pad) => padNode(index.pads.get(`${pad.ref}.${pad.number}`) || pad));
}

function indexTree(roots) {
  const nodesById = new Map();
  const parents = new Map();
  const visit = (nodes, parent) => {
    for (const node of nodes) {
      nodesById.set(node.id, node);
      if (parent) parents.set(node.id, parent.id);
      visit(node.children, node);
    }
  };
  visit(roots, null);
  return { roots, nodesById, parents };
}

/**
 * @param {ReturnType<typeof import("@cad/core/lib/board2d/boardIndex.js").createBoardIndex>} index
 * @returns {{ parts: object, partsSearch: object[], nets: object }} each list as `{ roots, nodesById, parents }`
 */
export function buildBoardTree(index, t = english) {
  const sorted = [...index.parts.values()].sort((a, b) => naturalCompare(a.ref, b.ref));
  // The schematic's blocks when the footprints record them (a part that records none goes under Other), else the kinds.
  const bySheet = sorted.some((part) => part.sheet);
  const blockOf = (part) => (bySheet ? part.sheet || "" : partKind(part.ref));
  const byKind = new Map();
  for (const part of sorted) {
    const kind = blockOf(part);
    if (!byKind.has(kind)) byKind.set(kind, []);
    byKind.get(kind).push({
      id: `part:${part.ref}`, kind: "part", pick: `#${part.ref}`, label: part.ref, detail: part.value,
      selectionId: part.ref, searchAliases: [part.value, part.footprint.split(":").pop(), part.fields.MPN].filter(Boolean),
      children: [], pads: partPads(index, part),
    });
  }
  const block = (key, label) => ({
    id: `${bySheet ? "sheet" : "kind"}:${key}`, kind: "block", label, detail: String(byKind.get(key).length), children: byKind.get(key),
    picks: byKind.get(key).map((node) => node.pick),
  });
  const parts = bySheet
    ? [...byKind.keys()].filter(Boolean).sort(naturalCompare).map((sheet) => block(sheet, sheet))
      .concat(byKind.has("") ? [block("", t("board.text.other"))] : [])
    : KIND_ORDER.filter((kind) => byKind.has(kind)).map((kind) => block(kind, t(GROUP_KEYS[kind])));
  const listed = [...index.nets.values()]
    .filter((net) => net.pads.length || net.tracks.length)
    .sort((a, b) => naturalCompare(a.name, b.name));
  const netNode = (net) => ({
    id: `net:${net.name}`, kind: "net", pick: formatBoardRefSelector({ kind: "net", net: net.name }), label: net.name,
    detail: t(net.pads.length === 1 ? "board.text.count_pad" : "board.text.count_pads", { count: net.pads.length }), selectionId: `net:${net.name}`, searchAliases: [],
    children: [],
  });
  // KiCad names a pin on nothing a net of its own, `unconnected-(U3-Pad9)`, and counts it as KiCad's
  // Nets count does: the board's every net is listed, those pins' kept together, under one shut group.
  const loose = listed.filter((net) => net.name.startsWith("unconnected-(")).map(netNode);
  const nets = listed.filter((net) => !net.name.startsWith("unconnected-(")).map(netNode);
  if (loose.length) {
    nets.push({ id: "group:unconnected", kind: "group", label: t("board.text.unconnected_pins"), detail: String(loose.length), children: loose });
  }
  // The Parts' search reads each part with its pads, so `#U3.9` or a pin's name finds the pad.
  const partsSearch = parts.map((node) => ({ ...node, children: node.children.map((part) => ({ ...part, children: part.pads })) }));
  return { parts: indexTree(parts), partsSearch, nets: indexTree(nets) };
}

/** The rows a selector is: a part's, a net's (a pad has none: it is its part's detail). */
export function boardTreeNodeIds(selector) {
  const parsed = parseBoardRefSelector(selector);
  if (!parsed) return [];
  if (parsed.kind === "net" || parsed.kind === "copper") return [`net:${parsed.net}`];
  if (parsed.kind === "part") return [`part:${parsed.ref}`];
  return [];
}

/** The rows a selector is under, brought into view when it has none of its own: a pad's part, and its net. */
export function boardRowOwners(index, selector) {
  const parsed = parseBoardRefSelector(selector);
  if (parsed?.kind !== "pad") return [];
  const net = index.pads.get(`${parsed.ref}.${parsed.pad}`)?.net;
  return [`part:${parsed.ref}`, ...(net ? [`net:${net}`] : [])];
}

/** The rows above a node, outermost first, to open so the node shows. */
export function boardTreeAncestors(tree, id) {
  const chain = [];
  for (let parent = tree.parents.get(id); parent; parent = tree.parents.get(parent)) chain.unshift(parent);
  return chain;
}

/**
 * What a selector picks, in detail (`kit/inspector/CircuitDetail.jsx`): a part's pads, each its number,
 * its pin's name and its net; a net's pads, each its part and number; a pad, its part's. Null for
 * anything else (a track, a via, a block of parts).
 */
export function boardDetail(index, selector, t = english) {
  const parsed = parseBoardRefSelector(selector);
  if (!parsed) return null;
  const count = (n) => t(n === 1 ? "board.text.count_pad" : "board.text.count_pads", { count: n });
  if (parsed.kind === "part" || parsed.kind === "pad") {
    const part = index.parts.get(parsed.ref);
    if (!part) return null;
    const rows = partPads(index, part);
    return {
      id: `part:${part.ref}`, kind: "part", pick: `#${part.ref}`, label: part.ref,
      detail: [part.value, part.footprint.split(":").pop()].filter(Boolean).join(" · "),
      count: count(rows.length), listLabel: t("board.text.pads_of", { name: part.ref }), rows,
    };
  }
  if (parsed.kind === "net" || parsed.kind === "copper") {
    const net = index.nets.get(parsed.net);
    if (!net) return null;
    const rows = net.pads.map((pad) => ({ pad, key: `${pad.ref}.${pad.number}` })).sort((a, b) => naturalCompare(a.key, b.key))
      .map(({ pad }) => padNode(pad, { underNet: true }));
    return {
      id: `net:${net.name}`, kind: "net", pick: formatBoardRefSelector({ kind: "net", net: net.name }), label: net.name, detail: "",
      count: count(rows.length), listLabel: t("board.text.pads_on_net", { name: net.name }), rows,
    };
  }
  return null;
}

// A pick's glyph in the Selected pane, by what it is: a part's body, a pad's copper, anything on a net its trace.
const glyphOf = (kind) => (kind === "part" ? "part" : kind === "pad" ? "pad" : "net");
/** The net a pick is on, where it is on one: a pad's, a piece of copper's, a track's, a via's, a zone's. */
function netOf(resolved) {
  if (!resolved) return "";
  if (resolved.kind === "pad") return resolved.pad.net || "";
  if (resolved.kind === "copper") return resolved.net?.name || "";
  return resolved.item?.net || "";
}

/**
 * What is selected, for the Selected pane (`kit/inspector/CircuitDetail.jsx`): the last pick, as what it is
 * (its name, a line in words, its facts: `boardFacts.js`'s, a Quick Edit chip card's) and what it is
 * connected to — a part its own pads, each with its net; a net its pads; a pad, a track, a via, a pour
 * or a zone the pads on its net, the pad itself lit there. Several picks: how many, and each of them.
 */
export function boardSelected(index, selected, t = english) {
  if (!selected.length) return null;
  if (selected.length > 1) {
    const rows = selected.map((id) => {
      const resolved = index.resolve(id), described = describeBoardReference(resolved, index, t);
      return described ? { id, kind: glyphOf(resolved.kind), pick: id, label: described.name, detail: netOf(resolved) } : null;
    }).filter(Boolean);
    return { id: `many:${selected.join(",")}`, kind: "net", pick: "", label: t("selection.count", { count: selected.length }), detail: "",
      facts: [], count: "", listLabel: t("selection.items"), rows };
  }
  const id = selected[0], resolved = index.resolve(id), described = describeBoardReference(resolved, index, t);
  if (!described) return null;
  const part = resolved.kind === "pad" ? index.parts.get(resolved.pad.ref) : null;
  const what = resolved.kind === "pad" ? [t("selection.padOf", { part: resolved.pad.ref }), part?.value].filter(Boolean).join(" · ")
    : "";
  const net = resolved.kind === "net" ? resolved.net.name : netOf(resolved);
  const list = resolved.kind === "part" ? boardDetail(index, `#${resolved.part.ref}`, t)
    : net ? boardDetail(index, formatBoardRefSelector({ kind: "net", net }), t) : null;
  return {
    id: `selected:${id}`, kind: glyphOf(resolved.kind), pick: id, label: described.name, detail: what, facts: described.facts,
    count: list?.count || "", rows: list?.rows || [],
    listLabel: resolved.kind === "part" ? t("board.text.pads_of", { name: resolved.part.ref })
      : resolved.kind === "net" ? t("board.text.pads_on_net", { name: net }) : t("selection.connectedTo", { name: net })
  };
}
