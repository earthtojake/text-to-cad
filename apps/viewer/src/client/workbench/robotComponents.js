// Keep each source mesh object independently pickable through the shared mesh renderer.
// Split before posing so every object retains its visual's link and local transform.
function componentName(part) {
  const name = typeof part?.name === "string" ? part.name.trim() : "";
  return name && name !== part.id && !/^unnamed(?: component)?$/i.test(name) ? name : "";
}

function sourceObjectMesh(mesh, part) {
  const { vertexOffset, vertexCount, triangleOffset, triangleCount } = part;
  const ranges = [vertexOffset, vertexCount, triangleOffset, triangleCount];
  if (!ranges.every((value) => Number.isSafeInteger(value) && value >= 0) ||
      vertexCount === 0 || triangleCount === 0 ||
      (vertexOffset + vertexCount) * 3 > mesh.vertices.length ||
      (triangleOffset + triangleCount) * 3 > mesh.indices.length) {
    throw new Error(`Invalid robot mesh object ranges: ${part.id}`);
  }
  const indices = mesh.indices.slice(triangleOffset * 3, (triangleOffset + triangleCount) * 3);
  if (indices.some((index) => index < vertexOffset || index >= vertexOffset + vertexCount)) {
    throw new Error(`Robot mesh object indices exceed its vertices: ${part.id}`);
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
  return objects.map((object, index) => ({
    ...visual,
    id: `${visual.id}/object/${index}`,
    name: componentName(object) || visual.name,
    componentName: componentName(object),
    visualId: visual.id,
    meshObjectId: String(object.id || index),
    meshObjectIndex: index,
    sourceBounds: object.bounds,
    bounds: object.bounds,
    sourceMesh: sourceObjectMesh(visual.sourceMesh, object),
    sourceMeshKey: `${visual.sourceMeshKey}/object/${index}`,
    vertexCount: object.vertexCount,
    triangleCount: object.triangleCount
  }));
}

export function buildRobotComponentGeometry(meshData) {
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
