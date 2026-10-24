import { spellEngineRefs } from "@text-to-cad/core/lib/cadRefs.js";
import { xbfElementId } from "@text-to-cad/core/lib/xbf/xbfScene.js";

// An engine document's tree as a STEP's model tree presented an assembly: its
// assemblies over their children and each placed part a leaf, its faces and edges never rows
// (they are the viewport's to pick). The tree is the engine's (`structure.tree`): an assembly is
// `{ name, children }`, a placed part `{ name, prototype, instance }`.
//
// A node selects by its `selectionId`: a part by its instance (`i3`, the id the scene picks, lights
// and hides it by), an assembly by its place in the tree (`n0.2`). `leafPartIds` are the instances
// at and under it: what its eye hides and its selection lights. The document's own wrapper is not
// a row (its children are the tree's first rows), and sibling parts of one prototype that share a
// name's stem fold into one row carrying the count, as a STEP's repeated components do.
//
// Each node, and each element of a part, is also a ref into the document as the engine spells it
// (`spellEngineRefs`, `cadgen.engine.refs`): `refOf` and `elementRefOf`, over the engine's tree
// itself, never the rows a fold made.

/**
 * @typedef {object} XbfTreeNode
 * @property {string} id  Its row's id (`model:<selectionId>`, or a folded group's).
 * @property {string} [selectionId]  What it selects; a folded group has none.
 * @property {string[]} leafPartIds
 * @property {string[]} [memberSelectionIds]  A folded group's members.
 * @property {"assembly" | "part" | "group"} kind
 * @property {string} label
 * @property {string | null} component  A part's prototype key: what folds repeated parts.
 * @property {XbfTreeNode[]} children
 */

/** An assembly's selection id: its place in the engine's tree (`n0.2`). */
export const xbfAssemblyId = path => `n${path}`;
export const isXbfAssemblyId = id => /^n\d+(\.\d+)*$/.test(String(id || ""));

// The name a folded row can honestly carry: the stem its members share, backed up past the digits
// the common prefix splits. Empty means there is no such name, and that is a reason not to fold.
function repeatedLabelStem(labels) {
  let stem = labels[0] || "";
  for (const label of labels.slice(1)) {
    let at = 0;
    while (at < stem.length && at < label.length && stem[at] === label[at]) at += 1;
    stem = stem.slice(0, at);
  }
  return stem.replace(/[\s._-]*\d*$/, "");
}

// Sibling parts that share a prototype AND a name's stem fold into one row carrying the count,
// every instance still under it; an assembly never folds.
function foldRepeatedParts(nodes, ownerId) {
  const repeats = new Map();
  for (const node of nodes) {
    if (node.kind !== "part" || !node.component) continue;
    repeats.set(node.component, (repeats.get(node.component) || 0) + 1);
  }
  const folded = [], seen = new Set();
  for (const node of nodes) {
    const component = node.kind === "part" ? node.component : null;
    if (!component || repeats.get(component) < 2) { folded.push(node); continue; }
    if (seen.has(component)) continue;
    seen.add(component);
    const members = nodes.filter(other => other.kind === "part" && other.component === component);
    const stem = repeatedLabelStem(members.map(member => member.label));
    if (!stem) { for (const member of members) folded.push(member); continue; }
    folded.push({
      id: `${ownerId}:repeat:${component}`, kind: "group", label: `${stem} (${members.length})`,
      leafPartIds: [...new Set(members.flatMap(member => member.leafPartIds))],
      memberSelectionIds: members.map(member => member.selectionId), component: null, children: members
    });
  }
  return folded;
}

/**
 * The tree's rows, and what the host reads of it: every node by its selection id, each one's
 * owners (outermost first), and each instance's own node.
 * @param {object | null} structure  The engine's structure.
 * @returns {{ roots: XbfTreeNode[], wrapper: XbfTreeNode | null, nodes: Map<string, XbfTreeNode>,
 *   owners: Map<string, string[]>, refOf: (id: string) => string,
 *   elementRefOf: (partId: string, kind: string, ordinal: number, name?: string) => string }}
 *   `refOf`: a node's canonical ref by its selection id (`palm`, `hand/finger.2`); `elementRefOf`: an
 *   element's of the part `partId` (`hand/finger.2/face 7`, by its name where it has one). "" for an
 *   id the tree does not hold.
 */
export function presentXbfTree(structure) {
  const nodes = new Map();
  const owners = new Map();
  const entries = new Map();
  const prototypes = structure?.prototypes || [];
  const visit = (source, path, chain) => {
    const children = Array.isArray(source?.children) ? source.children : null;
    const placed = Number.isInteger(source?.instance);
    if (!children && !placed) return null;
    const selectionId = children ? xbfAssemblyId(path) : xbfElementId(source.instance);
    const label = String(source?.name || (placed ? prototypes[source.prototype]?.name : "") || "(unnamed)");
    const node = { id: `model:${selectionId}`, selectionId, kind: children ? "assembly" : "part", label,
      component: placed ? String(prototypes[source.prototype]?.key ?? source.prototype) : null, leafPartIds: [], children: [] };
    nodes.set(selectionId, node);
    owners.set(selectionId, chain);
    entries.set(selectionId, source);
    if (children) {
      const kids = children.map((child, at) => visit(child, `${path}.${at}`, [...chain, selectionId])).filter(Boolean);
      node.leafPartIds = [...new Set(kids.flatMap(child => child.leafPartIds))];
      node.children = foldRepeatedParts(kids, node.id);
      // An assembly that holds no part is a part of the tree no pick reaches: a leaf, as a STEP's.
      if (!kids.length) node.kind = "part";
    } else {
      node.leafPartIds = [selectionId];
    }
    return node;
  };
  const top = structure?.tree ? visit(structure.tree, "0", []) : null;
  // The document's wrapper is a STEP's assembly root: its children are the tree's rows.
  const wrapper = top?.kind === "assembly" ? top : null;
  const spelled = spellEngineRefs(structure?.tree || null);
  return {
    roots: wrapper ? wrapper.children : top ? [top] : [], wrapper, nodes, owners,
    refOf: id => spelled.occurrence(entries.get(id)),
    elementRefOf: (partId, kind, ordinal, name = "") => spelled.element(entries.get(partId), kind, ordinal, name)
  };
}

/**
 * The structural wrappers that add no choice when there is only one: kept in the logical tree
 * (and open in the host), their children shown. Never a folded group.
 */
export function implicitXbfRoots(roots) {
  const found = [];
  let nodes = roots;
  while (nodes.length === 1 && nodes[0].kind === "assembly" && nodes[0].children?.length) {
    found.push(nodes[0]);
    nodes = nodes[0].children;
  }
  return found;
}

/** Every assembly's selection id: what Parts, Faces and Edges hold open. */
export function xbfAssemblyIds(tree) {
  return [...tree.nodes.values()].filter(node => node.kind === "assembly").map(node => node.selectionId);
}

/**
 * The fewest nodes that name the parts `partIds` (instances, `i3`), in the tree's order: an assembly
 * every part of which is among them by its own id, else each of its parts -- so a hidden assembly is
 * said once, not part by part. A folded group is no node: its parts are said.
 */
export function xbfCoveringIds(tree, partIds) {
  const wanted = new Set(partIds);
  const found = [];
  const visit = (node) => {
    if (node.selectionId && node.leafPartIds.length && node.leafPartIds.every(id => wanted.has(id))) found.push(node.selectionId);
    else for (const child of node.children || []) visit(child);
  };
  if (wanted.size) for (const root of tree.roots) visit(root);
  return found;
}

/**
 * The node a viewport press on instance `partId` reaches: the outermost owner the host has
 * shut (a collapsed assembly is picked as a unit), else the part. The wrapper is always open.
 */
export function xbfPickFrontier(tree, partId, expanded) {
  for (const owner of tree.owners.get(partId) || []) {
    if (owner === tree.wrapper?.selectionId) continue;
    if (!expanded.has(owner)) return owner;
  }
  return partId;
}

/**
 * The tree paths the selection reveals: a selected part or assembly at its own row, a picked
 * face or edge at the row of the part it belongs to.
 */
export function xbfSelectionPaths(roots, selectedIds) {
  const paths = [];
  const visit = (nodes, parents = []) => {
    for (const node of nodes) {
      const path = [...parents, node];
      paths.push(path);
      visit(node.children || [], path);
    }
  };
  visit(roots);
  const found = [];
  for (const id of selectedIds) {
    const part = String(id).split("/")[0];
    const path = paths.find(p => p.at(-1).selectionId === part);
    if (path) found.push(path);
  }
  return [...new Map(found.map(path => [path.at(-1).id, path])).values()];
}
