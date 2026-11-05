import { english } from "@cad/ui/i18n";
/**
 * A schematic's lists: its **Parts**, in blocks, the sheets they are placed on, and its **Nets**,
 * flat, as a board's (`../board/boardTree.js`: a part's pins and a net's are the picked one's detail,
 * `schematicDetail`, and the Parts' search reads each part with its pins, `partsSearch`) — and its
 * **Hierarchy**, the sheets as KiCad's Hierarchy Navigator lists them, the root and the sheets each
 * places, in page order. Nodes are what the kit's tree search reads (`id`, `label`, `children`,
 * `selectionId` and `searchAliases`: a part's value, footprint name, symbol and MPN, a pin's name),
 * plus what the row selects (`pick`, its reference; a block's `picks`, every part in it) and a muted `detail`.
 */
import { formatBoardRefSelector, parseBoardRefSelector } from "@cad/core/lib/boardRefs.js";
import { parseSchematicRefSelector } from "@cad/core/lib/schematicRefs.js";
import { describeSchematicReference } from "./schematicFacts.js";

// One collator for every comparison (natural order: C2 before C10).
const NATURAL = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const naturalCompare = (left, right) => NATURAL.compare(String(left), String(right));

function pinNode(pin, { underNet = false } = {}) {
  const name = pin.name && pin.name !== pin.number && pin.name !== "~" ? pin.name : "";
  const key = `${pin.part}.${pin.number}`;
  return {
    id: `${underNet ? "netpin" : "pin"}:${key}`, kind: "pin", pick: `#${key}`,
    // Under its part a pin is its number; under a net it is the part and the number.
    label: underNet ? key : pin.number,
    detail: underNet ? name : [name, pin.net].filter(Boolean).join(" · "),
    selectionId: key, searchAliases: name ? [name] : [], children: []
  };
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

// Each part's pins, in natural order.
function pinsByPart(index) {
  const pinsOf = new Map();
  for (const pin of index.pins.values()) {
    if (!pinsOf.has(pin.part)) pinsOf.set(pin.part, []);
    pinsOf.get(pin.part).push(pin);
  }
  for (const pins of pinsOf.values()) pins.sort((a, b) => naturalCompare(a.number, b.number));
  return pinsOf;
}

/**
 * @param {ReturnType<typeof import("@cad/core/lib/schematic2d/schematicIndex.js").createSchematicIndex>} index
 * @returns {{ parts: object, partsSearch: object[], nets: object }} each list as `{ roots, nodesById, parents }`
 */
export function buildSchematicTree(index, t = english) {
  const pinsOf = pinsByPart(index);
  const page = new Map(index.order.map((path, at) => [path, at]));
  const bySheet = new Map();
  for (const part of [...index.parts.values()].sort((a, b) => naturalCompare(a.ref, b.ref))) {
    // A part is in the block of the first sheet a unit of it is placed on.
    const sheet = (part.units || []).map((unit) => unit.sheet).sort((a, b) => (page.get(a) ?? 1e9) - (page.get(b) ?? 1e9))[0] || "";
    if (!bySheet.has(sheet)) bySheet.set(sheet, []);
    bySheet.get(sheet).push({
      id: `part:${part.ref}`, kind: "part", pick: `#${part.ref}`, label: part.ref, detail: part.value || "",
      selectionId: part.ref, children: [], pins: (pinsOf.get(part.ref) || []).map((pin) => pinNode(pin)),
      searchAliases: [part.value, String(part.footprint || "").split(":").pop(), String(part.lib_id || "").split(":").pop(), part.mpn || part.fields?.MPN]
        .filter(Boolean)
    });
  }
  const blocks = [...bySheet.keys()].sort((a, b) => (page.get(a) ?? 1e9) - (page.get(b) ?? 1e9)).map((sheet) => ({
    id: `sheet:${sheet}`, kind: "block", label: sheet ? index.sheetName(sheet) : t("board.text.other"), detail: String(bySheet.get(sheet).length),
    children: bySheet.get(sheet), picks: bySheet.get(sheet).map((node) => node.pick)
  }));
  const listed = [...index.nets.values()].sort((a, b) => naturalCompare(a.name, b.name));
  const netNode = (net) => ({
    id: `net:${net.name}`, kind: "net", pick: formatBoardRefSelector({ kind: "net", net: net.name }), label: net.name,
    detail: t(net.pins.length === 1 ? "schematic.text.count_pin" : "schematic.text.count_pins", { count: net.pins.length }),
    selectionId: `net:${net.name}`, searchAliases: [], children: []
  });
  // KiCad names a pin on nothing a net of its own, `unconnected-(R3-Pad2)`: those pins are kept together, under one shut group.
  const loose = listed.filter((net) => net.name.startsWith("unconnected-(")).map(netNode);
  const nets = listed.filter((net) => !net.name.startsWith("unconnected-(")).map(netNode);
  if (loose.length) nets.push({ id: "group:unconnected", kind: "group", label: t("board.text.unconnected_pins"), detail: String(loose.length), children: loose });
  // The Parts' search reads each part with its pins, so `#U3.9` or a pin's name finds the pin.
  const partsSearch = blocks.map((node) => ({ ...node, children: node.children.map((part) => ({ ...part, children: part.pins })) }));
  return { parts: indexTree(blocks), partsSearch, nets: indexTree(nets) };
}

/** The rows a selector is: a part's, a net's (a pin has none: it is its part's detail). */
export function schematicTreeNodeIds(selector) {
  const parsed = parseBoardRefSelector(selector);
  if (!parsed) return [];
  if (parsed.kind === "net") return [`net:${parsed.net}`];
  if (parsed.kind === "part") return [`part:${parsed.ref}`];
  return [];
}

/** The rows a selector is under, brought into view when it has none of its own: a pin's part, and its net. */
export function schematicRowOwners(index, selector) {
  const parsed = parseBoardRefSelector(selector);
  if (parsed?.kind !== "pad") return [];
  const net = index.pins.get(`${parsed.ref}.${parsed.pad}`)?.net;
  return [`part:${parsed.ref}`, ...(net ? [`net:${net}`] : [])];
}

/**
 * What a selector picks, in detail (`kit/inspector/CircuitDetail.jsx`): a part's pins, each its number,
 * name and net; a net's pins, each its part and number; a pin, its part's. Null for anything else.
 */
export function schematicDetail(index, selector, t = english) {
  const parsed = parseBoardRefSelector(selector);
  if (!parsed) return null;
  const count = (n) => t(n === 1 ? "schematic.text.count_pin" : "schematic.text.count_pins", { count: n });
  if (parsed.kind === "part" || parsed.kind === "pad") {
    const part = index.parts.get(parsed.ref);
    if (!part) return null;
    const rows = (pinsByPart(index).get(part.ref) || []).map((pin) => pinNode(pin));
    return {
      id: `part:${part.ref}`, kind: "part", pick: `#${part.ref}`, label: part.ref,
      detail: [part.value, String(part.footprint || "").split(":").pop()].filter(Boolean).join(" · "),
      count: count(rows.length), listLabel: t("schematic.text.pins_of", { name: part.ref }), rows
    };
  }
  if (parsed.kind === "net") {
    const net = index.nets.get(parsed.net);
    if (!net) return null;
    const rows = net.pins.slice().sort(naturalCompare).map((key) => index.pins.get(key)).filter(Boolean).map((pin) => pinNode(pin, { underNet: true }));
    return {
      id: `net:${net.name}`, kind: "net", pick: formatBoardRefSelector({ kind: "net", net: net.name }), label: net.name, detail: "",
      count: count(rows.length), listLabel: t("schematic.text.pins_on_net", { name: net.name }), rows
    };
  }
  return null;
}

/** The Hierarchy: the root, and under each sheet the sheets it places, in page order; each row its page number. */
export function buildSheetTree(index) {
  const node = (path) => ({
    id: `sheet:${path}`, kind: "sheet", path, label: index.sheetName(path), detail: String(index.sheets.get(path)?.page ?? ""),
    file: index.sheets.get(path)?.file || "", children: index.childrenOf(path).map(node)
  });
  const roots = index.order.filter((path) => !index.sheets.get(path)?.parent || !index.sheets.has(index.sheets.get(path).parent)).map(node);
  return indexTree(roots);
}

/** Whether a selector names a sheet (`#sheet:/Load/`): its path, else null. */
export function sheetOfSelector(selector) {
  const parsed = parseSchematicRefSelector(selector);
  return parsed?.kind === "sheet" ? parsed.sheet : null;
}

// A pick's glyph in the Selected pane, by what it is: a part's symbol, a pin, anything on a net its trace.
const glyphOf = (kind) => (kind === "part" ? "part" : kind === "pin" ? "pin" : "net");

/**
 * What is selected, for the Selected pane (`kit/inspector/CircuitDetail.jsx`): the last pick, as what it is
 * (its name, a line in words, its facts: `schematicFacts.js`'s, a Quick Edit chip card's) and what it is
 * connected to — a part its own pins, each with its net; a net its pins; a pin, a wire or a label the pins
 * on its net, the pin itself lit there. Several picks: how many, and each of them.
 */
export function schematicSelected(index, selected, t = english) {
  if (!selected.length) return null;
  if (selected.length > 1) {
    const rows = selected.map((id) => {
      const resolved = index.resolve(id), described = describeSchematicReference(resolved, index, t);
      return described ? { id, kind: glyphOf(resolved.kind), pick: id, label: described.name, detail: resolved.kind === "net" ? "" : String(resolved.net || "") } : null;
    }).filter(Boolean);
    return { id: `many:${selected.join(",")}`, kind: "net", pick: "", label: t("selection.count", { count: selected.length }), detail: "",
      facts: [], count: "", listLabel: t("selection.items"), rows };
  }
  const id = selected[0], resolved = index.resolve(id), described = describeSchematicReference(resolved, index, t);
  if (!described) return null;
  const part = resolved.kind === "pin" ? index.parts.get(resolved.ref) : null;
  const what = resolved.kind === "pin" ? [t("selection.pinOf", { part: resolved.ref }), part?.value].filter(Boolean).join(" · ")
    : "";
  const net = resolved.kind === "net" ? resolved.net : resolved.kind === "part" ? "" : String(resolved.net || "");
  const list = resolved.kind === "part" ? schematicDetail(index, `#${resolved.ref}`, t)
    : net ? schematicDetail(index, formatBoardRefSelector({ kind: "net", net }), t) : null;
  return {
    id: `selected:${id}`, kind: glyphOf(resolved.kind), pick: id, label: described.name, detail: what, facts: described.facts,
    count: list?.count || "", rows: list?.rows || [],
    listLabel: resolved.kind === "part" ? t("schematic.text.pins_of", { name: resolved.ref })
      : resolved.kind === "net" ? t("schematic.text.pins_on_net", { name: net }) : t("selection.connectedTo", { name: net })
  };
}
