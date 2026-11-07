/**
 * The one rule for how a tree opens, every file's sidebar tree alike — "open until there is a
 * choice": its roots open, and a node with exactly one child opens too, and so on down, since
 * there is nothing to decide; a node with two or more children stays shut. A pick on the model
 * then opens the owners of what was picked, and once the person opens or shuts a row the shape is
 * theirs for the session. Nothing else shapes a tree.
 *
 * The whole tree is walked, so a chain of single children under a shut node is already open when
 * the person opens it. Pure: no React, no DOM.
 */

/**
 * The ids of the nodes a tree opens on.
 *
 * @template T
 * @param {readonly T[]} roots
 * @param {(node: T) => readonly T[] | null | undefined} childrenOf  A leaf answers none.
 * @param {(node: T) => string} [idOf]
 * @returns {Set<string>}
 */
export function openUntilChoice(roots, childrenOf, idOf = node => node.id) {
  const open = new Set();
  const visit = (node, root) => {
    const children = childrenOf(node) || [];
    if (!children.length) return;
    if (root || children.length === 1) open.add(idOf(node));
    for (const child of children) visit(child, false);
  };
  for (const root of roots || []) visit(root, true);
  return open;
}
