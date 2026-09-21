function createMap() {
  return new Map();
}

export function buildAssemblyPartMap(assemblyParts) {
  const map = createMap();
  for (const part of Array.isArray(assemblyParts) ? assemblyParts : []) {
    map.set(part.id, part);
  }
  return map;
}

export function buildReferenceMap(references) {
  const map = createMap();
  for (const reference of Array.isArray(references) ? references : []) {
    map.set(reference.id, reference);
  }
  return map;
}
