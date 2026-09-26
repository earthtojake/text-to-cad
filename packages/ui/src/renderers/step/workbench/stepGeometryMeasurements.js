const validBox = box => box && ['min', 'max'].every(key => Array.isArray(box[key]) && box[key].length === 3 && box[key].every(Number.isFinite)) && box.min.every((value, axis) => value <= box.max[axis]);

// The overall size of what is selected, read from the linked final geometry: never inferred
// construction dimensions.
export function stepGeometryMeasurements(selection, references, parts) {
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
  return { size };
}
