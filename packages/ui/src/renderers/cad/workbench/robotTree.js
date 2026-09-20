/**
 * The Components tab's tree: a robot description's kinematic tree, as plain data.
 *
 * Links are the nodes. A child link sits under its parent link through the joint
 * that connects them, and carries that joint (the row's secondary text). Named
 * mesh objects (`robotComponents`) are leaves under the link whose meshes hold
 * them. Nodes use the Model tree's `{ id, kind, label, children }` shape so the
 * shared tree search reads them unchanged.
 *
 * The parsers reject malformed descriptions, but this is a view of whatever model
 * it is handed: a cycle, a missing parent or a second parent must neither hang
 * nor lose a link, so every link appears exactly once and orphans become roots.
 */

const text = value => String(value ?? "").trim();

export const robotLinkNodeId = linkName => `link:${linkName}`;
export const robotComponentNodeId = componentId => `component:${componentId}`;

/** `shoulder_pan · revolute`: the joint a link hangs from, as its row says it. */
export function robotJointSummary(joint) {
  if (!joint) return "";
  return [text(joint.name), text(joint.type)].filter(Boolean).join(" · ");
}

/**
 * @param {{ rootLink?: string, links?: object[], joints?: object[] } | null} description A parsed URDF/SDF model.
 * @param {{ components?: object[], parts?: { id: string, linkName: string }[] }} [geometry]
 *   `components` are `robotComponents(meshData)`; `parts` are the mesh parts, which map a link to its viewport geometry.
 * @returns {{ roots: object[], nodesById: Map<string, object>, parentById: Map<string, string> }}
 */
export function buildRobotTree(description, { components = [], parts = [] } = {}) {
  const links = Array.isArray(description?.links) ? description.links : [];
  const joints = Array.isArray(description?.joints) ? description.joints : [];
  const linkByName = new Map();
  for (const link of links) {
    const name = text(link?.name);
    if (name && !linkByName.has(name)) linkByName.set(name, link);
  }
  // A joint may name a link the description never declares. It is still a link of this robot.
  for (const joint of joints) {
    for (const name of [text(joint?.parentLink), text(joint?.childLink)]) {
      if (name && !linkByName.has(name)) linkByName.set(name, { name, undeclared: true });
    }
  }

  // The first joint to claim a child is its parent joint; a later claim would give the link two rows.
  const parentJointByChild = new Map();
  const childJointsByParent = new Map();
  for (const joint of joints) {
    const parent = text(joint?.parentLink), child = text(joint?.childLink);
    if (!parent || !child || parent === child || parentJointByChild.has(child)) continue;
    parentJointByChild.set(child, joint);
    childJointsByParent.set(parent, [...(childJointsByParent.get(parent) || []), joint]);
  }

  const componentsByLink = new Map();
  for (const component of components) {
    const linkName = text(component?.linkName);
    if (!linkName || !linkByName.has(linkName)) continue;
    componentsByLink.set(linkName, [...(componentsByLink.get(linkName) || []), component]);
  }
  const partIdsByLink = new Map();
  for (const part of parts) {
    const linkName = text(part?.linkName), id = text(part?.id);
    if (!linkName || !id) continue;
    partIdsByLink.set(linkName, [...(partIdsByLink.get(linkName) || []), id]);
  }

  const nodesById = new Map();
  const parentById = new Map();
  const placed = new Set();
  const linkNode = (linkName, joint) => {
    const node = {
      id: robotLinkNodeId(linkName), kind: "link", label: linkName, linkName,
      joint: joint || null, detail: robotJointSummary(joint),
      // The tree filter also finds a link by the joint it hangs from.
      searchAliases: joint && text(joint.name) ? [text(joint.name)] : [],
      partIds: partIdsByLink.get(linkName) || [],
      componentIds: (componentsByLink.get(linkName) || []).map(component => component.id),
      children: [],
    };
    nodesById.set(node.id, node);
    return node;
  };
  // Iterative: a long serial chain must not depend on the call stack.
  const place = (rootName, rootJoint) => {
    const root = linkNode(rootName, rootJoint);
    placed.add(rootName);
    const pending = [root];
    while (pending.length) {
      const node = pending.pop();
      const childLinks = [];
      for (const joint of childJointsByParent.get(node.linkName) || []) {
        const childName = text(joint.childLink);
        if (placed.has(childName)) continue;
        placed.add(childName);
        const child = linkNode(childName, joint);
        parentById.set(child.id, node.id);
        childLinks.push(child);
      }
      // Child links first: a link holding dozens of mesh objects must not bury the chain below it.
      node.children = [...childLinks, ...(componentsByLink.get(node.linkName) || []).map(component => {
        const leaf = {
          id: robotComponentNodeId(component.id), kind: "component", label: text(component.name) || text(component.id),
          linkName: node.linkName, component, partIds: [component.id], children: [],
        };
        nodesById.set(leaf.id, leaf);
        parentById.set(leaf.id, node.id);
        return leaf;
      })];
      for (let index = childLinks.length - 1; index >= 0; index -= 1) pending.push(childLinks[index]);
    }
    return root;
  };

  const declaredRoot = text(description?.rootLink);
  const names = [...linkByName.keys()];
  const roots = [];
  const rootNames = names.filter(name => !parentJointByChild.has(name));
  if (declaredRoot && rootNames.includes(declaredRoot)) {
    rootNames.splice(rootNames.indexOf(declaredRoot), 1);
    rootNames.unshift(declaredRoot);
  }
  for (const name of rootNames) if (!placed.has(name)) roots.push(place(name, null));
  // Whatever is left hangs only from itself (a cycle). Cut it at its first declared
  // link, which keeps the joint it arrived by so nothing the description says is lost.
  for (const name of names) if (!placed.has(name)) roots.push(place(name, parentJointByChild.get(name) || null));
  return { roots, nodesById, parentById };
}

/** Ancestor node ids of `nodeId`, outermost first; the node itself is not included. */
export function robotTreeAncestorIds(tree, nodeId) {
  const ancestors = [];
  const seen = new Set([nodeId]);
  for (let cursor = tree?.parentById?.get(nodeId); cursor && !seen.has(cursor); cursor = tree.parentById.get(cursor)) {
    seen.add(cursor);
    ancestors.unshift(cursor);
  }
  return ancestors;
}

const numbers = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? value : null;

/**
 * What the description says about one link, for the details pane. Only facts the
 * parsed model carries are returned: an SDF model, for one, records no mass.
 */
export function robotLinkFacts(description, linkName, { groupNamesByLink = null } = {}) {
  const name = text(linkName);
  const link = (Array.isArray(description?.links) ? description.links : []).find(candidate => text(candidate?.name) === name) || null;
  const joints = Array.isArray(description?.joints) ? description.joints : [];
  const parentJoint = joints.find(joint => text(joint?.childLink) === name) || null;
  const geometry = entries => (Array.isArray(entries) ? entries : []).map(entry => ({
    type: text(entry?.type) || (entry?.primitive ? text(entry.primitive.type) : entry?.meshUrl ? "mesh" : "unknown"),
    filename: text(entry?.filename) || (entry?.meshUrl ? text(entry.label) : ""),
  }));
  const endEffectors = (Array.isArray(description?.srdf?.endEffectors) ? description.srdf.endEffectors : [])
    .filter(endEffector => text(endEffector?.parentLink) === name || text(endEffector?.link) === name)
    .map(endEffector => text(endEffector.name)).filter(Boolean);
  return {
    name,
    isRoot: !parentJoint,
    parentJoint: parentJoint ? {
      name: text(parentJoint.name), type: text(parentJoint.type), parentLink: text(parentJoint.parentLink),
      // A fixed joint has no axis; the parser's placeholder is not something the description says.
      axis: text(parentJoint.type) === "fixed" ? null : numbers(parentJoint.axis),
      limit: parentJoint.limit && Object.keys(parentJoint.limit).length ? parentJoint.limit : null,
      origin: parentJoint.origin && numbers(parentJoint.origin.xyz) && numbers(parentJoint.origin.rpy) ? parentJoint.origin : null,
      mimic: parentJoint.mimic || null,
    } : null,
    childJoints: joints.filter(joint => text(joint?.parentLink) === name)
      .map(joint => ({ name: text(joint.name), type: text(joint.type), childLink: text(joint.childLink) })),
    mass: Number.isFinite(link?.inertial?.mass) ? link.inertial.mass : null,
    visuals: geometry(link?.visuals),
    // `null` when the model does not record collisions at all, `[]` when the link declares none.
    collisions: Array.isArray(link?.collisions) ? geometry(link.collisions) : null,
    groups: groupNamesByLink?.get?.(name) || [],
    endEffectors,
  };
}
