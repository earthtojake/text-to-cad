// A face's tangent group is cadgen's to decide (the selector table's `tangentGroup`: faces joined
// across the tangent-class edges of one solid, from the exact BREP's continuity). Faces of one
// placed component with the same group id are one group; a group never crosses a part, an
// occurrence or a solid.
export function buildTangentFaceGraph(references) {
  const faces = [...new Map(references.filter(ref => ref.selectorType === 'face').map(ref => [ref.id, ref])).values()];
  const graph = new Map(faces.map(face => [face.id, new Set()]));
  const groups = new Map();
  for (const face of faces) {
    const group = face.pickData?.tangentGroup;
    if (!Number.isInteger(group)) continue;
    const key = JSON.stringify([face.partId || '', face.occurrenceId || '', face.shapeId || '', group]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(face);
  }
  for (const members of groups.values()) {
    for (let index = 1; index < members.length; index += 1) {
      graph.get(members[0].id).add(members[index].id);
      graph.get(members[index].id).add(members[0].id);
    }
  }
  return graph;
}
