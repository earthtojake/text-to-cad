import { english } from "@cad/ui/i18n";
/**
 * A schematic's trees: its **Circuit** — its parts in blocks, the sheets they are placed on, each part
 * with its pins, then its nets, each with the pins on it, as a board's (`../board/boardTree.js`) — and
 * its **Hierarchy**, the sheets as KiCad's Hierarchy Navigator lists them, the root and the sheets each
 * places, in page order. Nodes are what the kit's tree search reads (`id`, `label`, `children`,
 * `selectionId` and `searchAliases`: a part's value, footprint name, symbol and MPN, a pin's name),
 * plus what the row selects (`pick`, its reference; a block's `picks`, every part in it) and a muted `detail`.
 */
import { formatBoardRefSelector, parseBoardRefSelector } from "@cad/core/lib/boardRefs.js";
import { parseSchematicRefSelector } from "@cad/core/lib/schematicRefs.js";

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

/** @param {ReturnType<typeof import("@cad/core/lib/schematic2d/schematicIndex.js").createSchematicIndex>} index */
export function buildSchematicTree(index, t = english) {
  const pinsOf = new Map();
  for (const pin of index.pins.values()) {
    if (!pinsOf.has(pin.part)) pinsOf.set(pin.part, []);
    pinsOf.get(pin.part).push(pin);
  }
  const page = new Map(index.order.map((path, at) => [path, at]));
  const bySheet = new Map();
  for (const part of [...index.parts.values()].sort((a, b) => naturalCompare(a.ref, b.ref))) {
    // A part is in the block of the first sheet a unit of it is placed on.
    const sheet = (part.units || []).map((unit) => unit.sheet).sort((a, b) => (page.get(a) ?? 1e9) - (page.get(b) ?? 1e9))[0] || "";
    if (!bySheet.has(sheet)) bySheet.set(sheet, []);
    const pins = (pinsOf.get(part.ref) || []).slice().sort((a, b) => naturalCompare(a.number, b.number));
    bySheet.get(sheet).push({
      id: `part:${part.ref}`, kind: "part", pick: `#${part.ref}`, label: part.ref, detail: part.value || "",
      selectionId: part.ref, children: pins.map((pin) => pinNode(pin)),
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
    selectionId: `net:${net.name}`, searchAliases: [],
    children: net.pins.slice().sort(naturalCompare).map((key) => index.pins.get(key)).filter(Boolean).map((pin) => pinNode(pin, { underNet: true }))
  });
  // KiCad names a pin on nothing a net of its own, `unconnected-(R3-Pad2)`: those pins are kept together, under one shut group.
  const loose = listed.filter((net) => net.name.startsWith("unconnected-(")).map(netNode);
  const nets = listed.filter((net) => !net.name.startsWith("unconnected-(")).map(netNode);
  if (loose.length) nets.push({ id: "group:unconnected", kind: "group", label: t("board.text.unconnected_pins"), detail: String(loose.length), children: loose });
  return indexTree([...blocks, { id: "group:nets", kind: "group", label: t("board.text.nets"), detail: String(listed.length), children: nets }]);
}

/** The Circuit rows a selector stands for (a pin shows under its part and under its net). */
export function schematicTreeNodeIds(selector) {
  const parsed = parseBoardRefSelector(selector);
  if (!parsed) return [];
  if (parsed.kind === "net") return [`net:${parsed.net}`];
  if (parsed.kind === "pad") return [`pin:${parsed.ref}.${parsed.pad}`, `netpin:${parsed.ref}.${parsed.pad}`];
  if (parsed.kind === "part") return [`part:${parsed.ref}`];
  return [];
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
