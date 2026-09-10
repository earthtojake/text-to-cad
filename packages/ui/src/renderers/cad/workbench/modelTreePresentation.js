import { buildSelectionCopyPayload, canonicalCadRefCopyText, withFileRefPrefix } from './referenceSelection.js';

const surfaceLabels = { plane: 'Planar', cylinder: 'Cylindrical', sphere: 'Spherical', cone: 'Conical', torus: 'Toroidal' };
export const MODEL_GROUP_PREFIX = 'model-group:';

// Presentation folders retain the original entity nodes and reference IDs.
export function modelTreePresentation(root, references = [], groupFaces = false) {
  const byId = new Map(references.map(ref => [ref.id, ref]));
  const folder = (owner, kind, label, children) => ({
    id: `${MODEL_GROUP_PREFIX}${owner.id}:${kind}`, nodeType: 'topology-folder',
    displayName: `${label} (${children.length})`, partId: owner.partId || owner.id,
    groupReferenceIds: children.filter(node => ['topology-face', 'topology-edge'].includes(node.nodeType)).map(node => node.topologyReferenceId).filter(Boolean), children,
  });
  const visit = node => {
    if (!node) return node;
    let children = node.children || [];
    // The standalone part already names the model; omit its duplicate topology wrapper.
    if (node.nodeType === 'part' && children.length === 1 && children[0].nodeType === 'topology-folder' && children[0].id?.endsWith(':folder:faces-edges')) children = children[0].children || [];
    const faces = [], edges = [], bodies = [], other = [];
    for (const child of children) {
      if (child.nodeType === 'topology-face') faces.push(child);
      else if (child.nodeType === 'topology-edge') edges.push(child);
      else if (child.nodeType === 'topology-shape') bodies.push(child);
      else other.push(visit(child));
    }
    const result = [...other];
    if (faces.length) {
      const faceFolder = folder(node, 'faces', 'Faces', faces);
      if (groupFaces) {
        const groups = new Map();
        for (const face of faces) {
          const ref = byId.get(face.topologyReferenceId);
          const type = ref?.pickData?.surfaceType || ref?.pickData?.params?.kind || 'other';
          if (!groups.has(type)) groups.set(type, []);
          groups.get(type).push(face);
        }
        faceFolder.children = [...groups].map(([type, nodes]) => folder(node, `surface:${type}`, surfaceLabels[type] || 'Other', nodes));
      }
      result.push(faceFolder);
    }
    if (edges.length) result.push(folder(node, 'edges', 'Edges', edges));
    if (bodies.length) result.push(folder(node, 'bodies', 'Bodies', bodies));
    return {...node, children: result};
  };
  return visit(root);
}

export function modelTreeReferenceAncestors(root, referenceId) {
  if (!root || !referenceId) return [];
  for (const node of root.children || []) {
    if (node.topologyReferenceId === referenceId) return [root.id];
    const path = modelTreeReferenceAncestors(node, referenceId);
    if (path.length) return [root.id, ...path];
  }
  return [];
}

export function modelTreeGroupCopyText(ids, referenceMap, entry) {
  const references = ids.map(id => referenceMap.get(id));
  if (!entry || !references.length || references.some(ref => !['face', 'edge'].includes(ref?.selectorType) || !canonicalCadRefCopyText(ref.copyText))) return '';
  return buildSelectionCopyPayload({references, parts: [], entry}).lines.map(line => withFileRefPrefix(canonicalCadRefCopyText(line), entry.fileRefPrefix)).join('\n');
}
