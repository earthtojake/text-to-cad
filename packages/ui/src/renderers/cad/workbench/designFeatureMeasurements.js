const validBox = box => box && ['min', 'max'].every(key => Array.isArray(box[key]) && box[key].length === 3 && box[key].every(Number.isFinite)) && box.min.every((value, axis) => value <= box.max[axis]);

// Read the linked final geometry, never infer construction dimensions or volume.
export function designFeatureMeasurements(selection, references, parts) {
  const faceIds = [...new Set(selection?.faceIds || [])];
  const partIds = [...new Set(selection?.partIds || [])];
  const faceMap = new Map(references.filter(ref => ref.selectorType === 'face').map(ref => [ref.id, ref.pickData]));
  const partMap = new Map(parts.map(part => [part.id, part]));
  const faces = faceIds.map(id => faceMap.get(id));
  const boxes = [...faces.map(face => face?.bbox), ...partIds.map(id => partMap.get(id)?.bounds)];
  const size = boxes.length && boxes.every(validBox) ? [0, 1, 2].map(axis => {
    let min = Infinity, max = -Infinity;
    for (const box of boxes) { min = Math.min(min, box.min[axis]); max = Math.max(max, box.max[axis]); }
    return max - min;
  }) : null;
  // Parts can overlap selected faces; do not present a partial or double-counted total.
  const area = !partIds.length && faces.length && faces.every(face => Number.isFinite(face?.area) && face.area >= 0) ? faces.reduce((sum, face) => sum + face.area, 0) : null;
  const radii = [...new Set(faces.flatMap(face => {
    const params = face?.params;
    return ['cylinder', 'sphere'].includes(face?.surfaceType || params?.kind) && Number.isFinite(params.radius) && params.radius > 0 ? [Number(params.radius.toPrecision(10))] : [];
  }))].sort((a, b) => a - b);
  return { size, area, radii };
}
