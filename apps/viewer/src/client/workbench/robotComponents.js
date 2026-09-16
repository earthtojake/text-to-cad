// Keep each source mesh object independently pickable through the shared mesh renderer.
// Split before posing so every object retains its visual's link and local transform.
function componentName(part) {
  const name = typeof part?.name === "string" ? part.name.trim() : "";
  return name && name !== part.id && !/^unnamed(?: component)?$/i.test(name) ? name : "";
}

// A loader that hands back a part whose ranges do not describe a slice of the mesh it
// came from is a bug in the loader, not in this robot — and it must not cost the user
// their render. Report it once per distinct part and let the caller fall back.
const reportedInvalidParts = new Set();

function reportInvalidPart(partId, reason) {
  const key = `${partId}:${reason}`;
  if (reportedInvalidParts.has(key)) {
    return;
  }
  reportedInvalidParts.add(key);
  console.warn(`Skipping robot mesh object components: ${reason} (${partId})`);
}

// Slice one named object out of its visual's mesh, or return null when the loader's
// ranges cannot describe a slice of it. Never throws: the caller keeps the whole
// visual instead, so the robot renders either way.
function sourceObjectMesh(mesh, part) {
  const { vertexOffset, vertexCount, triangleOffset, triangleCount } = part;
  const ranges = [vertexOffset, vertexCount, triangleOffset, triangleCount];
  if (!ranges.every((value) => Number.isSafeInteger(value) && value >= 0) ||
      vertexCount === 0 || triangleCount === 0 ||
      (vertexOffset + vertexCount) * 3 > (mesh.vertices?.length ?? 0) ||
      (triangleOffset + triangleCount) * 3 > (mesh.indices?.length ?? 0)) {
    reportInvalidPart(part.id, "invalid mesh object ranges");
    return null;
  }
  const indices = mesh.indices.slice(triangleOffset * 3, (triangleOffset + triangleCount) * 3);
  if (indices.some((index) => index < vertexOffset || index >= vertexOffset + vertexCount)) {
    reportInvalidPart(part.id, "mesh object indices exceed its vertices");
    return null;
  }
  const sliceAttribute = (values) => values?.slice(vertexOffset * 3, (vertexOffset + vertexCount) * 3);
  return {
    vertices: sliceAttribute(mesh.vertices),
    normals: sliceAttribute(mesh.normals),
    colors: sliceAttribute(mesh.colors),
    indices: indices.map((index) => index - vertexOffset),
    bounds: part.bounds,
    parts: []
  };
}

function splitVisual(visual) {
  const objects = visual.sourceMesh?.parts;
  if (!Array.isArray(objects) || !objects.some(componentName)) return [visual];
  const split = [];
  for (const [index, object] of objects.entries()) {
    const sourceMesh = sourceObjectMesh(visual.sourceMesh, object);
    // One unsliceable object forfeits the components for its VISUAL, not the visual's
    // geometry: dropping the object alone would silently delete triangles from the
    // render, so the visual stays whole and simply contributes no component rows.
    if (!sourceMesh) return [visual];
    split.push({
      ...visual,
      id: `${visual.id}/object/${index}`,
      name: componentName(object) || visual.name,
      componentName: componentName(object),
      visualId: visual.id,
      meshObjectId: String(object.id || index),
      meshObjectIndex: index,
      sourceBounds: object.bounds,
      bounds: object.bounds,
      sourceMesh,
      sourceMeshKey: `${visual.sourceMeshKey}/object/${index}`,
      vertexCount: object.vertexCount,
      triangleCount: object.triangleCount
    });
  }
  return split;
}

export function buildRobotComponentGeometry(meshData) {
  if (!meshData) return meshData;
  return { ...meshData, parts: (meshData.parts || []).flatMap(splitVisual) };
}

export function robotComponentReference(file, component) {
  // Explicit field names make the reference usable in prompts without STEP's topology grammar.
  const fields = [
    ["link", component.linkName],
    ["visual", component.visualId],
    ["object", component.meshObjectId],
    ["index", component.meshObjectIndex],
    ["name", component.componentName || component.name]
  ];
  const filePath = String(file).split("/").map(encodeURIComponent).join("/");
  return `${filePath}#${fields.map(([key, value]) => `${key}=${encodeURIComponent(value)}`).join("&")}`;
}

export function robotComponents(meshData, file) {
  return (meshData?.parts || []).filter((part) => part.componentName).map((part) => ({
    id: part.id,
    name: part.componentName,
    linkName: part.linkName,
    visualId: part.visualId,
    meshObjectId: part.meshObjectId,
    meshObjectIndex: part.meshObjectIndex,
    mesh: part.partFileRef || part.meshUrl,
    reference: robotComponentReference(file, part)
  }));
}
