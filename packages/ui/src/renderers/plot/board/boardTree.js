/**
 * A board's or a schematic's Select tree: its parts, by kind, each with its pads (a schematic's
 * pins), and its nets, each with the pads or pins on it. (What KiCad reported is the alert card's
 * and Select's Checks: `FindingsList.jsx`.) Nodes are what
 * the kit's tree search reads (`id`, `label`, `children`, `selectionId` — the reference a pasted
 * `#U3.9` finds — and `searchAliases`), plus the selector the row selects (`selector`) and a muted
 * `detail`.
 */
import { formatBoardRefSelector, parseBoardRefSelector } from "@text-to-cad/core/lib/boardRefs.js";

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
  const selector = `#${pad.ref}.${pad.number}`;
  return {
    id: `${underNet ? "netpad" : "pad"}:${pad.ref}.${pad.number}`, kind: "pad", selector,
    // Under its part a pad is its number; under a net it is the part and the number.
    label: underNet ? `${pad.ref}.${pad.number}` : pad.number,
    detail: underNet ? name : [name, pad.net].filter(Boolean).join(" · "),
    selectionId: `${pad.ref}.${pad.number}`, searchAliases: name ? [name] : [], children: [],
  };
}

/**
 * @param {ReturnType<typeof import("@text-to-cad/core/lib/board2d/boardIndex.js").createBoardIndex>
 *   | ReturnType<typeof import("@text-to-cad/core/lib/board2d/schematicIndex.js").createSchematicIndex>} index
 */
export function buildBoardTree(index) {
  const noun = index.document === "schematic" ? "pin" : "pad";
  const byKind = new Map();
  for (const part of [...index.parts.values()].sort((a, b) => naturalCompare(a.ref, b.ref))) {
    const kind = partKind(part.ref);
    if (!byKind.has(kind)) byKind.set(kind, []);
    // A pin's pads under one number are one row, as they are one pin.
    const seen = new Set();
    const pads = [...part.pads].filter((pad) => !seen.has(pad.number) && seen.add(pad.number)).sort((a, b) => naturalCompare(a.number, b.number));
    byKind.get(kind).push({
      id: `part:${part.ref}`, kind: "part", selector: `#${part.ref}`, label: part.ref, detail: part.value,
      selectionId: part.ref, searchAliases: [part.value, part.footprint.split(":").pop(), part.lib?.split(":").pop(), part.fields.MPN].filter(Boolean),
      children: pads.map((pad) => padNode(index.pads.get(`${pad.ref}.${pad.number}`) || pad)),
    });
  }
  const parts = KIND_ORDER.filter((kind) => byKind.has(kind)).map((kind) => ({
    id: `kind:${kind}`, kind: "group", label: kind, detail: String(byKind.get(kind).length), children: byKind.get(kind),
  }));
  const nets = [...index.nets.values()]
    .filter((net) => net.pads.length || net.tracks?.length || net.wires?.length)
    // KiCad's names for a pin on nothing are not nets anyone routes: they stay out of the list.
    .filter((net) => !net.name.startsWith("unconnected-("))
    .sort((a, b) => naturalCompare(a.name, b.name))
    .map((net) => ({
      id: `net:${net.name}`, kind: "net", selector: formatBoardRefSelector({ kind: "net", net: net.name }), label: net.name,
      detail: `${net.pads.length} ${noun}${net.pads.length === 1 ? "" : "s"}`, selectionId: `net:${net.name}`, searchAliases: [],
      children: net.pads.map((pad) => ({ pad, key: `${pad.ref}.${pad.number}` })).sort((a, b) => naturalCompare(a.key, b.key)).map(({ pad }) => padNode(pad, { underNet: true })),
    }));
  const roots = [
    { id: "group:parts", kind: "group", label: "Parts", detail: String(index.parts.size), children: parts },
    { id: "group:nets", kind: "group", label: "Nets", detail: String(nets.length), children: nets },
  ];
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

/** The tree rows a selector stands for (a pad or pin shows under its part and under its net). */
export function boardTreeNodeIds(selector) {
  const parsed = parseBoardRefSelector(selector);
  if (!parsed) return [];
  if (parsed.kind === "net" || parsed.kind === "copper") return [`net:${parsed.net}`];
  if (parsed.kind === "pad") return [`pad:${parsed.ref}.${parsed.pad}`, `netpad:${parsed.ref}.${parsed.pad}`];
  if (parsed.kind === "part") return [`part:${parsed.ref}`];
  return [];
}

/** The rows above a node, outermost first, to open so the node shows. */
export function boardTreeAncestors(tree, id) {
  const chain = [];
  for (let parent = tree.parents.get(id); parent; parent = tree.parents.get(parent)) chain.unshift(parent);
  return chain;
}
