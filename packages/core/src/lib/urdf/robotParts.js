import { paletteIndices } from "../render/meshObjects.js";

// The once-per-load part list a robot scene is built from: one part per visual of the
// payload cadgen resolved (`cadgen.robot_payload`), or per NAMED object of a visual's mesh,
// each with its link, its rest placement, the mesh it draws in that mesh's own units and
// frame (a loaded link mesh, or the primitive cadgen meshed into the store), the colour the
// description gives it, and the place "Color by part" deals it. Posing never touches this
// list: a pose is the scene graph's joint matrices (`robotScene.js`).

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const IDENTITY_PLACEMENT = Object.freeze([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

function srgbToLinear(value) {
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function parseHexColorToLinearRgb(value) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) return null;
  const expanded = normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`
    : normalized;
  return [
    srgbToLinear(Number.parseInt(expanded.slice(1, 3), 16) / 255),
    srgbToLinear(Number.parseInt(expanded.slice(3, 5), 16) / 255),
    srgbToLinear(Number.parseInt(expanded.slice(5, 7), 16) / 255)
  ];
}

// A link mesh may carry its colour PER PART rather than per vertex: a GLB with one material
// per primitive produces `has_source_colors` with an empty `colors` buffer and the colour on
// `parts[].color`. A robot visual is ONE renderable part, so that detail had nowhere to go and
// the whole link fell back to default grey — an authored two-colour hand rendered as a grey
// stub, with no warning, purely because the colour was a material rather than an attribute.
// Expand it into the per-vertex buffer the scene already reads.
function withPerVertexPartColors(partMesh) {
  const vertices = partMesh?.vertices;
  if (!partMesh?.has_source_colors || !vertices?.length || partMesh.colors?.length) return partMesh;
  const objects = Array.isArray(partMesh.parts) ? partMesh.parts : [];
  if (!objects.length) return partMesh;
  const colors = new Float32Array(vertices.length);
  let painted = false;
  for (const object of objects) {
    const rgb = parseHexColorToLinearRgb(String(object?.color || "").trim());
    const offset = Number(object?.vertexOffset);
    const count = Number(object?.vertexCount);
    if (!rgb || !Number.isFinite(offset) || !Number.isFinite(count) || count <= 0) continue;
    const end = Math.min(offset + count, Math.floor(vertices.length / 3));
    for (let index = Math.max(offset, 0); index < end; index += 1) {
      colors[index * 3] = rgb[0];
      colors[index * 3 + 1] = rgb[1];
      colors[index * 3 + 2] = rgb[2];
    }
    painted = true;
  }
  // A part the loader left uncoloured keeps white, which multiplies to the theme fill.
  return painted ? { ...partMesh, colors } : partMesh;
}

function meshHasSourceColors(partMesh) {
  return !!partMesh?.has_source_colors && partMesh.colors?.length > 0 && partMesh.colors.length === partMesh.vertices?.length;
}

function placementOf(visual) {
  const placement = Array.isArray(visual?.placement) ? visual.placement.map(Number) : [];
  return placement.length === 16 && placement.every(Number.isFinite) ? placement : [...IDENTITY_PLACEMENT];
}

/**
 * One part per visual of the payload whose mesh is loaded: its link, its rest placement (the
 * payload's: the link frame, the visual's origin and the mesh's scale composed), the mesh it
 * draws, the colour the description gives it, and whether it has a colour of its own at all.
 * A visual whose mesh is not in `meshesByUrl` has no part: the loader fails a robot with a
 * missing link mesh before it gets here.
 *
 * @param {object} robot  The payload (`cadgen.robot_payload`).
 * @param {Map<string, object> | Record<string, object>} meshesByUrl  Every mesh the visuals name, loaded, by URL.
 */
export function robotVisualParts(robot, meshesByUrl) {
  const lookup = url => (meshesByUrl instanceof Map ? meshesByUrl.get(url) : meshesByUrl?.[url]) || null;
  const parts = [];
  for (const visual of Array.isArray(robot?.visuals) ? robot.visuals : []) {
    const url = String(visual?.mesh?.url || "").trim();
    const loaded = lookup(url);
    if (!loaded) continue;
    const partMesh = withPerVertexPartColors(loaded);
    const color = String(visual?.color || "").trim();
    const label = String(visual?.label || visual?.id || url).trim();
    parts.push({
      id: String(visual?.id || `${visual?.link}:${url}`),
      name: label,
      label,
      color,
      meshUrl: url,
      link: String(visual?.link || ""),
      placement: placementOf(visual),
      sourceBounds: partMesh.bounds,
      bounds: partMesh.bounds,
      hasSourceColors: !!parseHexColorToLinearRgb(color) || meshHasSourceColors(partMesh),
      sourceMesh: partMesh,
      sourceMeshKey: url || String(visual?.id || ""),
      vertexCount: Math.floor((partMesh.vertices?.length || 0) / 3),
      triangleCount: Math.floor((partMesh.indices?.length || 0) / 3)
    });
  }
  return parts;
}

// Keep each source mesh object independently pickable through the shared mesh renderer.
// Split before posing so every object retains its visual's link and placement.
// A loader that finds no name for an object names it anyway: `glb:3`, `3mf:0`, three's
// GLTFLoader's `mesh_0` (the primitives cadgen meshes carry no name), or the CAD
// occurrence id the node carries (`o1.2`). Those are identity, not something a person
// wrote, and an inventory of them is noise -- so they are what this rejects.
//
// It is NOT "the name equals the id". cadgen's own GLB writer stamps each node's
// cadOccurrenceId extra with the node's authored name, so every part of every GLB this
// repo writes arrives with name === id === occurrenceId (`elbow_pitch_link:color0`).
// Reading that as "unnamed" left a robot built from cadgen meshes with no components at
// all, which is every robot in the corpus.
const SYNTHETIC_OBJECT_NAME = /^(?:[a-z0-9]+:\d+|o\d+(?:\.\d+)*|(?:mesh|node)_\d+(?:_\d+)*)$/i;

function componentName(part) {
  const name = typeof part?.name === "string" ? part.name.trim() : "";
  if (!name || /^unnamed(?: component)?$/i.test(name) || SYNTHETIC_OBJECT_NAME.test(name)) {
    return "";
  }
  return name;
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
      color: String(object.color || ""),
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

// A link mesh is in the units and frame of its own FILE: the `<mesh scale>` and the
// visual origin live in the placement, and a robot is metres. So an object's size on
// the robot is its mesh-space box scaled by that placement, reported in millimetres
// because that is the size robot parts are quoted in.
//
// The basis norms are the scale whichever way the 16 numbers are laid out, which is
// what makes this safe to read without knowing the producer's convention. A rotation
// leaves lengths alone; a NON-uniform scale under a rotation would need the box
// rebuilt rather than measured, and no URDF in the corpus writes one.
function transformScale(transform) {
  if (!Array.isArray(transform) || transform.length !== 16) {
    return [1, 1, 1];
  }
  return [0, 4, 8].map((offset) => {
    const length = Math.hypot(transform[offset], transform[offset + 1], transform[offset + 2]);
    return Number.isFinite(length) && length > 0 ? length : 1;
  });
}

function componentSizeMillimetres(part) {
  const min = part?.bounds?.min;
  const max = part?.bounds?.max;
  if (!Array.isArray(min) || !Array.isArray(max) || min.length < 3 || max.length < 3) {
    return null;
  }
  const scale = transformScale(part.placement);
  const extents = [0, 1, 2].map((axis) => Math.abs(Number(max[axis]) - Number(min[axis])) * scale[axis] * 1000);
  return extents.every((extent) => Number.isFinite(extent)) ? extents : null;
}

export function robotComponents(meshData) {
  return (meshData?.parts || []).filter((part) => part.componentName).map((part) => ({
    id: part.id,
    name: part.componentName,
    link: part.link,
    visualId: part.visualId,
    meshObjectId: part.meshObjectId,
    meshObjectIndex: part.meshObjectIndex,
    color: part.color || "",
    triangleCount: Number(part.triangleCount) || 0,
    vertexCount: Number(part.vertexCount) || 0,
    sizeMillimetres: componentSizeMillimetres(part)
  }));
}

/**
 * The once-per-load part list a robot scene is built from: one part per visual, or per
 * named object of a visual's mesh, each with its link, its rest placement, its source
 * mesh, the colour its description gives it (`descriptionColor`) and the place "Color by
 * part" deals it. Posing never touches this list.
 *
 * @param {object} robot  The payload cadgen resolved.
 * @param {Map<string, object>} meshesByUrl  Every mesh the payload's visuals name, loaded, by URL.
 * @returns {{ parts: object[], components: ReturnType<typeof robotComponents> }}
 */
export function buildRobotParts(robot, meshesByUrl) {
  // What the DESCRIPTION says a visual's colour is (a URDF <material>, an SDF <diffuse>), kept
  // apart from the colour a named object of its mesh brings: the description's wins over both.
  const visuals = { parts: robotVisualParts(robot, meshesByUrl).map(part => ({ ...part, descriptionColor: String(part.color || "").trim() })) };
  let geometry = visuals;
  // The split is an enhancement: a failure in it costs the named objects, never the robot.
  try { geometry = buildRobotComponentGeometry(visuals); }
  catch (error) { console.warn("Failed to split robot mesh objects into components", error); }
  const places = paletteIndices(geometry.parts);
  const parts = geometry.parts.map((part, index) => ({ ...part, fillIndex: places[index] }));
  return { parts, components: robotComponents({ parts }) };
}
