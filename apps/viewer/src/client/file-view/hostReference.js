// What a host gets from the surface, and what it can ask of it, about
// references (docs/file-view.md, "References and captures").
//
// Standalone, a copied reference goes to the clipboard and nowhere else.
// Embedded, the host wants it too — the desktop app puts it in its composer —
// so every copy site hands the copied text to `onReference` as well, in the
// shape below. The other direction is `selectReference`: a host that has a
// reference from elsewhere (a link in a transcript) asks the surface to
// select it, and the resolver here maps a selector back onto the ids the
// surface's own selection machinery uses. Both halves are pure so a test can
// read them without a viewer.
import { createContext, useContext } from "react";

import { isNativeCadSelector, parseCadRefToken } from "cadgen-js/lib/cadRefs.js";
import { STEP_TREE_TOPOLOGY_NODE_PREFIX, stepTreeNodeChildren } from "cadgen-js/lib/step/stepTree.js";

// The same two spellings stepTreeSelection.js uses, repeated here rather than
// imported: that module reaches for `@/workbench/...`, and this one is read
// by `node --test`, which knows no aliases.
function stepTreeNodeIdForWorkspace(node) {
  return String(node?.id || node?.occurrenceId || "").trim();
}

function selectorFromStepTreeInternalId(value) {
  const normalized = String(value || "").trim();
  if (!normalized.startsWith(STEP_TREE_TOPOLOGY_NODE_PREFIX)) {
    return "";
  }
  const candidate = String(normalized.split(":").pop() || "").trim();
  return isNativeCadSelector(candidate) ? candidate : "";
}

/**
 * A copied line as the host sees it: the file it belongs to (served-root
 * relative, as `cadFileParamForEntry` gives it), the selector half without its
 * `#` (`""` for a whole file), and the text exactly as copied. The prefix on
 * the copied line is the viewer's shortest-unique suffix, which is right for a
 * prompt and wrong for a host that wants to open the file, so `file` is
 * always the full path.
 */
export function referenceFromCopyText(text, file) {
  const copied = String(text || "").trim();
  const parsed = parseCadRefToken(copied);
  const selector = parsed ? parsed.selectors.join(",") : "";
  return { file: String(file || "").trim(), selector, text: copied };
}

/** Every copied line, one reference each; blank lines are nothing. */
export function referencesFromCopyText(text, file) {
  return String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => referenceFromCopyText(line, file));
}

/**
 * `{ deliverReference(text) }` when a host is listening, else null. The
 * sheet's own copy buttons (StepReferenceSection) read it, so a reference
 * copied from anywhere in the surface reaches the host.
 */
export const HostReferenceContext = createContext(null);

export function useHostReference() {
  return useContext(HostReferenceContext);
}

const ENTITY_RE = /^([sfev])(\d+)$/;

/**
 * The tree node a selector names, walking the display tree the way the copy
 * map is built (buildStepTreeCopyReferenceMap): every spelling a node is
 * copyable by is a spelling it can be selected by.
 */
export function findStepTreeNodeForSelector(root, selector) {
  const wanted = String(selector || "").trim();
  if (!root || !wanted) {
    return null;
  }
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    const nodeId = stepTreeNodeIdForWorkspace(node);
    const spellings = [
      nodeId,
      node?.id,
      node?.topologyReferenceId,
      node?.displaySelector,
      node?.occurrenceId,
      node?.name,
      node?.label,
      node?.displayName,
      selectorFromStepTreeInternalId(node?.id)
    ].map((value) => String(value || "").trim());
    if (spellings.includes(wanted)) {
      return node;
    }
    const children = stepTreeNodeChildren(node);
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return null;
}

/**
 * A selector as the surface's selection machinery wants it.
 *
 *   { kind: "reference", id }   a topology entity — `toggleReferenceSelection(id)`
 *   { kind: "part", id }        an occurrence or subassembly — `togglePartSelection(id)`
 *   null                        nothing known by that name yet (the maps fill as
 *                               the model and its topology load; ask again)
 *
 * Tried in order: the reference map, which knows every loaded entity by its
 * canonical, display and copy spellings; the tree, which knows parts and
 * subassemblies by occurrence id, name and label; and a label-qualified
 * entity (`bracket.f45`) resolved through the labelled node's occurrence.
 * A list selects its first member.
 */
export function resolveSelectorSelection(selector, { referenceMap, treeRoot } = {}) {
  const first = String(selector || "").trim().split(",")[0]?.trim();
  if (!first) {
    return null;
  }
  const reference = referenceMap?.get?.(first);
  if (reference?.id) {
    return { kind: "reference", id: String(reference.id) };
  }
  const node = findStepTreeNodeForSelector(treeRoot, first);
  if (node) {
    const nodeType = String(node.nodeType || "");
    if (nodeType.startsWith("topology-")) {
      return { kind: "reference", id: String(node.topologyReferenceId || stepTreeNodeIdForWorkspace(node)) };
    }
    return { kind: "part", id: stepTreeNodeIdForWorkspace(node) };
  }
  // `label.f45` / `o1.2.f45`: the entity of an occurrence, by the occurrence's spelling.
  const dot = first.lastIndexOf(".");
  if (dot > 0) {
    const owner = first.slice(0, dot);
    const entity = first.slice(dot + 1);
    if (ENTITY_RE.test(entity)) {
      const ownerNode = findStepTreeNodeForSelector(treeRoot, owner);
      const occurrenceId = String(ownerNode?.occurrenceId || "").trim();
      if (occurrenceId) {
        const qualified = referenceMap?.get?.(`${occurrenceId}.${entity}`);
        if (qualified?.id) {
          return { kind: "reference", id: String(qualified.id) };
        }
      }
    }
  }
  return null;
}
