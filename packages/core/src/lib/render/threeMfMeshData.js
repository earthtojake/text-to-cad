import { displayGeometryWithNormals } from "./meshNormals.js";

const GENERATED_DEFAULT_MATERIAL_NAMES = new Set(["default"]);
const GENERATED_DEFAULT_MATERIAL_COLORS = new Set(["#fafafb", "#b6c4ce"]);
const WORKBENCH_DEFAULT_MATERIAL_COLOR = Object.freeze({
  rgb: [0.4677837961, 0.5520114015, 0.6172065624],
  hex: "#b6c4ce",
});

function buildBoundsFromVertices(vertices) {
  if (!vertices?.length) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0],
    };
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index + 2 < vertices.length; index += 3) {
    const x = Number(vertices[index]);
    const y = Number(vertices[index + 1]);
    const z = Number(vertices[index + 2]);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
      continue;
    }
    min[0] = Math.min(min[0], x);
    min[1] = Math.min(min[1], y);
    min[2] = Math.min(min[2], z);
    max[0] = Math.max(max[0], x);
    max[1] = Math.max(max[1], y);
    max[2] = Math.max(max[2], z);
  }
  if (!min.every(Number.isFinite) || !max.every(Number.isFinite)) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0],
    };
  }
  return { min, max };
}

function normalize3MfPackagePath(value = "", basePath = "") {
  const rawValue = String(value || "").trim().replace(/\\/g, "/");
  if (!rawValue) {
    return "";
  }
  if (rawValue.startsWith("/")) {
    return rawValue.replace(/^\/+/, "");
  }
  const baseParts = String(basePath || "").split("/");
  baseParts.pop();
  const parts = [...baseParts, ...rawValue.split("/")];
  const normalized = [];
  for (const part of parts) {
    if (!part || part === ".") {
      continue;
    }
    if (part === "..") {
      normalized.pop();
      continue;
    }
    normalized.push(part);
  }
  return normalized.join("/");
}

function elementChildren(node, localName) {
  return Array.from(node?.children || []).filter((child) => child.localName === localName);
}

function firstElementChild(node, localName) {
  return elementChildren(node, localName)[0] || null;
}

function attributeByLocalName(node, localName) {
  if (!node?.attributes) {
    return "";
  }
  const direct = node.getAttribute?.(localName);
  if (direct) {
    return direct;
  }
  for (const attribute of Array.from(node.attributes)) {
    if (attribute.localName === localName || String(attribute.name || "").split(":").pop() === localName) {
      return attribute.value || "";
    }
  }
  return "";
}

function parseNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function parseIndex(value) {
  const numericValue = Number(value);
  return Number.isInteger(numericValue) && numericValue >= 0 ? numericValue : -1;
}

function parse3MfXml(text, label) {
  if (typeof DOMParser !== "function") {
    throw new Error("3MF XML parsing is unavailable in this environment");
  }
  const document = new DOMParser().parseFromString(text, "application/xml");
  const parseError = document.querySelector?.("parsererror");
  if (parseError) {
    throw new Error(`Invalid 3MF XML: ${label}`);
  }
  return document;
}

function parse3MfTransform(THREE, value) {
  const transformValues = String(value || "")
    .trim()
    .split(/\s+/)
    .map((item) => Number(item));
  if (transformValues.length !== 12 || transformValues.some((item) => !Number.isFinite(item))) {
    return null;
  }
  const matrix = new THREE.Matrix4();
  matrix.set(
    transformValues[0], transformValues[3], transformValues[6], transformValues[9],
    transformValues[1], transformValues[4], transformValues[7], transformValues[10],
    transformValues[2], transformValues[5], transformValues[8], transformValues[11],
    0, 0, 0, 1
  );
  return matrix;
}

function parse3MfMeshNode(meshNode) {
  const vertices = [];
  const verticesNode = firstElementChild(meshNode, "vertices");
  for (const vertexNode of elementChildren(verticesNode, "vertex")) {
    vertices.push([
      parseNumber(vertexNode.getAttribute("x")),
      parseNumber(vertexNode.getAttribute("y")),
      parseNumber(vertexNode.getAttribute("z")),
    ]);
  }

  const triangles = [];
  const trianglesNode = firstElementChild(meshNode, "triangles");
  for (const triangleNode of elementChildren(trianglesNode, "triangle")) {
    const triangle = [
      parseIndex(triangleNode.getAttribute("v1")),
      parseIndex(triangleNode.getAttribute("v2")),
      parseIndex(triangleNode.getAttribute("v3")),
    ];
    if (triangle.every((index) => index >= 0)) {
      triangles.push(triangle);
    }
  }

  return { vertices, triangles };
}

function parse3MfModelPart(THREE, xmlText, modelPath) {
  const document = parse3MfXml(xmlText, modelPath);
  const modelNode = document.documentElement?.localName === "model"
    ? document.documentElement
    : document.querySelector?.("model");
  if (!modelNode) {
    throw new Error(`3MF model part is missing a model node: ${modelPath}`);
  }

  const resourcesNode = firstElementChild(modelNode, "resources");
  const objects = new Map();
  for (const objectNode of elementChildren(resourcesNode, "object")) {
    const id = String(objectNode.getAttribute("id") || "").trim();
    if (!id) {
      continue;
    }
    const name = String(objectNode.getAttribute("name") || objectNode.getAttribute("partnumber") || "").trim();
    const meshNode = firstElementChild(objectNode, "mesh");
    const componentsNode = firstElementChild(objectNode, "components");
    const components = [];
    for (const componentNode of elementChildren(componentsNode, "component")) {
      const objectId = String(componentNode.getAttribute("objectid") || "").trim();
      if (!objectId) {
        continue;
      }
      components.push({
        objectId,
        path: normalize3MfPackagePath(attributeByLocalName(componentNode, "path"), modelPath),
        transform: parse3MfTransform(THREE, componentNode.getAttribute("transform")),
      });
    }
    objects.set(id, {
      id,
      name,
      mesh: meshNode ? parse3MfMeshNode(meshNode) : null,
      components,
    });
  }

  const build = [];
  const buildNode = firstElementChild(modelNode, "build");
  for (const itemNode of elementChildren(buildNode, "item")) {
    const objectId = String(itemNode.getAttribute("objectid") || "").trim();
    if (!objectId) {
      continue;
    }
    build.push({
      objectId,
      transform: parse3MfTransform(THREE, itemNode.getAttribute("transform")),
    });
  }

  return {
    path: modelPath,
    objects,
    build,
  };
}

function parse3MfRelationships(xmlText, relsPath) {
  const document = parse3MfXml(xmlText, relsPath);
  return Array.from(document.querySelectorAll?.("Relationship") || [])
    .map((node) => ({
      target: normalize3MfPackagePath(node.getAttribute("Target")),
      type: String(node.getAttribute("Type") || "").trim(),
    }))
    .filter((relationship) => relationship.target);
}

function colorFromMaterial(material) {
  if (!material?.color) {
    return null;
  }
  const hex = `#${material.color.getHexString()}`.toLowerCase();
  const materialName = String(material.name || "").trim().toLowerCase();
  const generatedDefault = !material.isMeshStandardMaterial && GENERATED_DEFAULT_MATERIAL_NAMES.has(materialName) &&
    GENERATED_DEFAULT_MATERIAL_COLORS.has(hex);
  if (generatedDefault) {
    return {
      rgb: WORKBENCH_DEFAULT_MATERIAL_COLOR.rgb,
      hex: WORKBENCH_DEFAULT_MATERIAL_COLOR.hex,
      generatedDefault: true,
    };
  }
  return {
    rgb: [material.color.r, material.color.g, material.color.b],
    hex,
    generatedDefault: false,
  };
}

function materialForGroup(material, group) {
  if (Array.isArray(material)) {
    const materialIndex = Number.isInteger(group?.materialIndex) ? group.materialIndex : 0;
    return material[materialIndex] || material[0] || null;
  }
  return material || null;
}

function appendMeshPrimitive(THREE, accumulator, mesh, group, material, path) {
  const geometry = mesh?.geometry;
  const positions = geometry?.getAttribute?.("position");
  if (!positions || positions.itemSize !== 3 || positions.count <= 0) {
    return;
  }
  mesh.updateWorldMatrix?.(true, false);
  const matrixWorld = mesh.matrixWorld || null;
  const normalMatrix = matrixWorld ? new THREE.Matrix3().getNormalMatrix(matrixWorld) : null;
  const normals = geometry.getAttribute("normal");
  const indexAttribute = geometry.getIndex?.();
  const sourceStart = Math.max(0, Math.floor(Number(group?.start || 0)));
  const availableCount = indexAttribute?.count || positions.count;
  const rawCount = Math.floor(Number(group?.count || (availableCount - sourceStart)));
  const sourceCount = Math.max(0, Math.min(rawCount, availableCount - sourceStart));
  const triangleVertexCount = sourceCount - (sourceCount % 3);
  if (triangleVertexCount <= 0) {
    return;
  }
  const color = colorFromMaterial(material);
  const positionVector = new THREE.Vector3();
  const normalVector = new THREE.Vector3();
  const vertexOffset = Math.floor(accumulator.vertices.length / 3);
  const triangleOffset = Math.floor(accumulator.indices.length / 3);
  const partVertices = [];

  for (let localIndex = 0; localIndex < triangleVertexCount; localIndex += 1) {
    const sourceSlot = sourceStart + localIndex;
    const sourceIndex = indexAttribute ? indexAttribute.getX(sourceSlot) : sourceSlot;
    if (sourceIndex < 0 || sourceIndex >= positions.count) {
      continue;
    }
    const outputIndex = Math.floor(partVertices.length / 3);
    positionVector.set(
      positions.getX(sourceIndex),
      positions.getY(sourceIndex),
      positions.getZ(sourceIndex)
    );
    if (matrixWorld) {
      positionVector.applyMatrix4(matrixWorld);
    }
    accumulator.vertices.push(positionVector.x, positionVector.y, positionVector.z);
    partVertices.push(positionVector.x, positionVector.y, positionVector.z);
    if (normals?.itemSize === 3 && sourceIndex < normals.count) {
      normalVector.set(normals.getX(sourceIndex), normals.getY(sourceIndex), normals.getZ(sourceIndex));
      if (normalMatrix) {
        normalVector.applyMatrix3(normalMatrix).normalize();
      }
      accumulator.normals.push(normalVector.x, normalVector.y, normalVector.z);
    } else {
      accumulator.normals.push(0, 0, 0);
    }
    if (color) {
      accumulator.colors.push(color.rgb[0], color.rgb[1], color.rgb[2]);
    }
    accumulator.indices.push(vertexOffset + outputIndex);
  }

  const vertexCount = Math.floor(partVertices.length / 3);
  const triangleCount = Math.floor(vertexCount / 3);
  if (vertexCount <= 0 || triangleCount <= 0) {
    return;
  }
  const label = String(mesh?.name || mesh?.parent?.name || `3mf:${accumulator.parts.length}`).trim();
  const id = `3mf:${accumulator.parts.length}`;
  accumulator.parts.push({
    id,
    occurrenceId: id,
    name: label || id,
    label: label || id,
    nodeType: "part",
    path,
    color: color && !color.generatedDefault ? color.hex : "",
    opacity: Number.isFinite(material?.opacity) ? material.opacity : 1,
    ...(material?.isMeshStandardMaterial ? { finish: { metalness: material.metalness, roughness: material.roughness } } : {}),
    bounds: buildBoundsFromVertices(partVertices),
    vertexOffset,
    vertexCount,
    triangleOffset,
    triangleCount,
    edgeIndexOffset: 0,
    edgeIndexCount: 0,
  });
  if (color?.hex && !color.generatedDefault) {
    accumulator.colorSet.add(color.hex.toLowerCase());
  }
}

// Where a mesh's object stands in the build: three's loader adds one child per build item to its
// group, a component object one child per component, and an object's meshes (one per material)
// to the object's own group. So the object is the mesh's parent, and its place is each ancestor's
// place among its siblings, from the build item down, counted from 1.
function threeMfObjectPath(root, mesh) {
  const path = [];
  for (let object = mesh.parent; object && object !== root; object = object.parent) {
    path.unshift(object.parent ? object.parent.children.indexOf(object) + 1 : 1);
  }
  return path.length ? path : [1];
}

export function buildMeshDataFromThreeMfGroup(THREE, group, { toCreasedNormals = null } = {}) {
  const accumulator = {
    vertices: [],
    indices: [],
    normals: [],
    colors: [],
    parts: [],
    colorSet: new Set(),
  };
  group?.updateWorldMatrix?.(true, true);
  group?.traverse?.((object) => {
    if (object?.isMesh && object.geometry) {
      const path = threeMfObjectPath(group, object);
      // A 3MF mesh shares its vertices, so plain vertex normals round every hard edge.
      object.geometry = displayGeometryWithNormals(object.geometry, toCreasedNormals);
      const groups = Array.isArray(object.geometry.groups) && object.geometry.groups.length
        ? object.geometry.groups
        : [null];
      for (const geometryGroup of groups) {
        appendMeshPrimitive(THREE, accumulator, object, geometryGroup, materialForGroup(object.material, geometryGroup), path);
      }
    }
  });
  const vertices = new Float32Array(accumulator.vertices);
  const rawColors = accumulator.colors.length === accumulator.vertices.length
    ? new Float32Array(accumulator.colors)
    : new Float32Array(0);
  const hasSourceColors = rawColors.length === vertices.length && rawColors.length > 0 && accumulator.colorSet.size > 0;
  return {
    vertices,
    indices: new Uint32Array(accumulator.indices),
    normals: new Float32Array(accumulator.normals),
    colors: hasSourceColors ? rawColors : new Float32Array(0),
    edge_indices: new Uint32Array(0),
    bounds: buildBoundsFromVertices(vertices),
    parts: accumulator.parts,
    has_source_colors: hasSourceColors,
    sourceColor: accumulator.colorSet.size === 1 ? [...accumulator.colorSet][0] : "",
  };
}

function appendParsedMeshPart(THREE, accumulator, meshData, matrix, label, path) {
  if (!meshData?.vertices?.length || !meshData?.triangles?.length) {
    return;
  }

  const vertexOffset = Math.floor(accumulator.vertices.length / 3);
  const triangleOffset = Math.floor(accumulator.indices.length / 3);
  const positionVector = new THREE.Vector3();
  const transformedTriangle = [
    new THREE.Vector3(),
    new THREE.Vector3(),
    new THREE.Vector3(),
  ];
  const edgeA = new THREE.Vector3();
  const edgeB = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const partVertices = [];

  for (const triangle of meshData.triangles) {
    const sourceVertices = triangle.map((index) => meshData.vertices[index]);
    if (sourceVertices.some((vertex) => !vertex)) {
      continue;
    }
    for (let index = 0; index < 3; index += 1) {
      const vertex = sourceVertices[index];
      transformedTriangle[index].set(vertex[0], vertex[1], vertex[2]).applyMatrix4(matrix);
    }
    edgeA.subVectors(transformedTriangle[1], transformedTriangle[0]);
    edgeB.subVectors(transformedTriangle[2], transformedTriangle[0]);
    normal.crossVectors(edgeA, edgeB).normalize();
    if (!Number.isFinite(normal.x) || !Number.isFinite(normal.y) || !Number.isFinite(normal.z)) {
      normal.set(0, 0, 0);
    }
    for (const transformedVertex of transformedTriangle) {
      positionVector.copy(transformedVertex);
      const outputIndex = Math.floor(partVertices.length / 3);
      accumulator.vertices.push(positionVector.x, positionVector.y, positionVector.z);
      partVertices.push(positionVector.x, positionVector.y, positionVector.z);
      accumulator.normals.push(normal.x, normal.y, normal.z);
      accumulator.indices.push(vertexOffset + outputIndex);
    }
  }

  const vertexCount = Math.floor(partVertices.length / 3);
  const triangleCount = Math.floor(vertexCount / 3);
  if (vertexCount <= 0 || triangleCount <= 0) {
    return;
  }

  const id = `3mf:${accumulator.parts.length}`;
  const partLabel = String(label || id).trim() || id;
  accumulator.parts.push({
    id,
    occurrenceId: id,
    name: partLabel,
    label: partLabel,
    nodeType: "part",
    path,
    color: "",
    bounds: buildBoundsFromVertices(partVertices),
    vertexOffset,
    vertexCount,
    triangleOffset,
    triangleCount,
    edgeIndexOffset: 0,
    edgeIndexCount: 0,
  });
}

function findObjectInAnyModel(models, objectId) {
  for (const [modelPath, model] of models) {
    if (model.objects.has(objectId)) {
      return { modelPath, objectData: model.objects.get(objectId) };
    }
  }
  return null;
}

function appendParsed3MfObject(THREE, accumulator, models, modelPath, objectId, matrix, path, stack = []) {
  const stackKey = `${modelPath}#${objectId}`;
  if (stack.includes(stackKey)) {
    throw new Error(`3MF component cycle detected at ${stackKey}`);
  }

  const model = models.get(modelPath);
  let objectData = model?.objects?.get(objectId) || null;
  let resolvedModelPath = modelPath;
  if (!objectData) {
    const fallback = findObjectInAnyModel(models, objectId);
    objectData = fallback?.objectData || null;
    resolvedModelPath = fallback?.modelPath || modelPath;
  }
  if (!objectData) {
    throw new Error(`3MF object ${objectId} is missing from ${modelPath}`);
  }

  if (objectData.mesh) {
    appendParsedMeshPart(
      THREE,
      accumulator,
      objectData.mesh,
      matrix,
      objectData.name || `${resolvedModelPath}#${objectData.id}`,
      path
    );
    return;
  }

  for (const [index, component] of (objectData.components || []).entries()) {
    const componentPath = component.path || resolvedModelPath;
    const componentMatrix = matrix.clone();
    if (component.transform) {
      componentMatrix.multiply(component.transform);
    }
    appendParsed3MfObject(
      THREE,
      accumulator,
      models,
      componentPath,
      component.objectId,
      componentMatrix,
      [...path, index + 1],
      [...stack, stackKey]
    );
  }
}

function finalizeParsed3MfMesh(accumulator) {
  const vertices = new Float32Array(accumulator.vertices);
  return {
    vertices,
    indices: new Uint32Array(accumulator.indices),
    normals: new Float32Array(accumulator.normals),
    colors: new Float32Array(0),
    edge_indices: new Uint32Array(0),
    bounds: buildBoundsFromVertices(vertices),
    parts: accumulator.parts,
    has_source_colors: false,
    sourceColor: "",
  };
}

async function buildMeshDataFrom3MfPackageFallback(THREE, buffer) {
  const fflate = await import("three/examples/jsm/libs/fflate.module.js");
  const textDecoder = new TextDecoder();
  const zipEntries = fflate.unzipSync(new Uint8Array(buffer));
  const textEntry = (entryPath) => {
    const normalizedPath = normalize3MfPackagePath(entryPath);
    const payload = zipEntries[normalizedPath];
    return payload ? textDecoder.decode(payload) : "";
  };
  const modelPaths = Object.keys(zipEntries)
    .filter((entryPath) => /^3D\/.*\.model$/i.test(entryPath))
    .sort((left, right) => {
      const leftRoot = /\/3dmodel\.model$/i.test(left) ? 1 : 0;
      const rightRoot = /\/3dmodel\.model$/i.test(right) ? 1 : 0;
      return leftRoot - rightRoot || left.localeCompare(right);
    });
  if (!modelPaths.length) {
    throw new Error("3MF package does not contain any 3D model parts");
  }

  const models = new Map();
  for (const modelPath of modelPaths) {
    const xmlText = textEntry(modelPath);
    if (xmlText) {
      models.set(modelPath, parse3MfModelPart(THREE, xmlText, modelPath));
    }
  }

  const relationshipsText = textEntry("_rels/.rels");
  const rootModelPath = relationshipsText
    ? parse3MfRelationships(relationshipsText, "_rels/.rels")
      .find((relationship) => /\.model$/i.test(relationship.target))?.target
    : "";
  const buildModelPath = models.has(rootModelPath) ? rootModelPath : modelPaths.find((modelPath) => models.get(modelPath)?.build?.length) || modelPaths[0];
  const buildModel = models.get(buildModelPath);
  if (!buildModel) {
    throw new Error("3MF package does not contain a readable build model");
  }

  const identity = new THREE.Matrix4();
  const accumulator = {
    vertices: [],
    indices: [],
    normals: [],
    parts: [],
  };
  const buildItems = buildModel.build.length
    ? buildModel.build
    : Array.from(buildModel.objects.keys()).map((objectId) => ({ objectId, transform: null }));

  for (const [index, buildItem] of buildItems.entries()) {
    const matrix = buildItem.transform ? buildItem.transform.clone() : identity.clone();
    appendParsed3MfObject(THREE, accumulator, models, buildModelPath, buildItem.objectId, matrix, [index + 1]);
  }

  const meshData = finalizeParsed3MfMesh(accumulator);
  if (!meshData.indices.length) {
    throw new Error("3MF package did not produce any triangles");
  }
  return meshData;
}

const UNIT_READ_CHUNK = 1024;
/**
 * The unit the root model part declares (`<model unit="…">`, millimeter when absent): its
 * coordinates are in it, and nothing here scales them. Only the head of that part is inflated,
 * a kilobyte of the archive at a time, so reading it costs nothing beside the load itself.
 * @param {ArrayBuffer | Uint8Array} buffer  The 3MF package.
 * @returns {Promise<string>}  As the file writes it: "millimeter", "inch"…
 */
export async function declared3MfUnit(buffer) {
  const { Unzip, UnzipInflate } = await import("three/examples/jsm/libs/fflate.module.js");
  const bytes = new Uint8Array(buffer);
  let tag = null;
  let ended = false;
  const unzip = new Unzip((file) => {
    if (ended || !/^3D\/[^/]+\.model$/i.test(file.name)) return;
    const decoder = new TextDecoder();
    let head = "";
    file.ondata = (error, chunk, final) => {
      if (ended) return;
      head += error ? "" : decoder.decode(chunk, { stream: !final });
      tag = /<(?:[\w.-]+:)?model\b[^>]*>/.exec(head)?.[0] ?? null;
      if (tag || error || final || head.length > 1 << 16) { ended = true; file.terminate(); }
    };
    file.start();
  });
  unzip.register(UnzipInflate);
  for (let at = 0; at < bytes.length && !ended; at += UNIT_READ_CHUNK) {
    unzip.push(bytes.subarray(at, at + UNIT_READ_CHUNK), at + UNIT_READ_CHUNK >= bytes.length);
  }
  return /\sunit\s*=\s*["']([^"']*)["']/.exec(tag || "")?.[1] || "millimeter";
}

const xmlSpace = byte => byte === 32 || (byte >= 9 && byte <= 13);
function xmlMatches(bytes, at, text) {
  for (let i = 0; i < text.length; i++) if (bytes[at + i] !== text.charCodeAt(i)) return false;
  return true;
}
function xmlAfter(bytes, from, ending) {
  for (let at = bytes.indexOf(ending.charCodeAt(0), from); at >= 0; at = bytes.indexOf(ending.charCodeAt(0), at + 1)) {
    if (xmlMatches(bytes, at, ending)) return at + ending.length;
  }
  throw new Error('Invalid 3MF XML: unterminated markup');
}

// Read only XML markup. Comments, CDATA, processing instructions and quoted
// attributes cannot masquerade as a resource or an element's closing tag.
function xmlTag(bytes, from) {
  let at = bytes.indexOf(60, from);
  while (at >= 0) {
    let skip = null;
    if (xmlMatches(bytes, at, '<!--')) skip = xmlAfter(bytes, at + 4, '-->');
    else if (xmlMatches(bytes, at, '<![CDATA[')) skip = xmlAfter(bytes, at + 9, ']]>');
    else if (xmlMatches(bytes, at, '<?')) skip = xmlAfter(bytes, at + 2, '?>');
    if (skip !== null) { at = bytes.indexOf(60, skip); continue; }
    const declaration = bytes[at + 1] === 33;
    const closing = bytes[at + 1] === 47;
    const nameStart = at + (closing ? 2 : 1);
    let nameEnd = nameStart;
    while (nameEnd < bytes.length && !xmlSpace(bytes[nameEnd]) && ![47, 62].includes(bytes[nameEnd])) nameEnd++;
    let quote = 0, brackets = 0, end = nameEnd;
    for (; end < bytes.length; end++) {
      const byte = bytes[end];
      if (quote) { if (byte === quote) quote = 0; continue; }
      if (byte === 34 || byte === 39) quote = byte;
      else if (declaration && xmlMatches(bytes, end, '<!--')) end = xmlAfter(bytes, end + 4, '-->') - 1;
      else if (declaration && byte === 91) brackets++;
      else if (declaration && byte === 93) brackets--;
      else if (byte === 62 && brackets === 0) break;
    }
    if (end >= bytes.length) throw new Error('Invalid 3MF XML: unterminated tag');
    if (declaration) { at = bytes.indexOf(60, end + 1); continue; }
    const name = new TextDecoder().decode(bytes.subarray(nameStart, nameEnd));
    let tail = end - 1; while (xmlSpace(bytes[tail])) tail--;
    return { start: at, end: end + 1, name, localName: name.split(':').pop(), closing, selfClosing: bytes[tail] === 47 };
  }
  return null;
}

// Skip a whole object/mesh using byte searches, without constructing its DOM or
// decoding its geometry text. Only same-name tags and XML escape sections matter.
function xmlElementEnd(bytes, tag) {
  if (tag.selfClosing) return tag.end;
  let depth = 1, at = tag.end;
  const open = new TextEncoder().encode(`<${tag.name}`), close = new TextEncoder().encode(`</${tag.name}`);
  while ((at = bytes.indexOf(60, at)) >= 0) {
    if (xmlMatches(bytes, at, '<!--')) { at = xmlAfter(bytes, at + 4, '-->'); continue; }
    if (xmlMatches(bytes, at, '<![CDATA[')) { at = xmlAfter(bytes, at + 9, ']]>'); continue; }
    if (xmlMatches(bytes, at, '<?')) { at = xmlAfter(bytes, at + 2, '?>'); continue; }
    const marker = bytes[at + 1] === 47 ? close : open;
    if (!marker.every((value, index) => bytes[at + index] === value)
      || (!xmlSpace(bytes[at + marker.length]) && ![47, 62].includes(bytes[at + marker.length]))) { at++; continue; }
    const next = xmlTag(bytes, at);
    depth += next.closing ? -1 : next.selfClosing ? 0 : 1;
    if (!depth) return next.end;
    at = next.end;
  }
  throw new Error(`Invalid 3MF XML: missing closing ${tag.name}`);
}

// 3MF Materials 1.2.1 attaches display properties to a base-material GROUP;
// Three r186 reads an unqualified reference on each base. Bridge only those
// table bytes. Geometry is never part of the adapter DOM or XML serialization.
export function bridgeThreeMfMaterialModel(bytes, path = '3MF model') {
  const keyword = 'pbmetallicdisplayproperties';
  let candidate = bytes.indexOf(112);
  while (candidate >= 0 && !xmlMatches(bytes, candidate, keyword)) candidate = bytes.indexOf(112, candidate + 1);
  if (candidate < 0) return { bytes, adapted: false, materialBearing: false, unit: null };
  const model = xmlTag(bytes, 0), ranges = [];
  let resources = null;
  for (let child = xmlTag(bytes, model.end); child && !child.closing;) {
    const end = xmlElementEnd(bytes, child);
    if (child.localName === 'resources') {
      resources = child;
      for (let resource = xmlTag(bytes, child.end); resource && !resource.closing;) {
        const resourceEnd = xmlElementEnd(bytes, resource);
        if (['basematerials', 'pbmetallicdisplayproperties'].includes(resource.localName)) ranges.push({ start: resource.start, end: resourceEnd });
        resource = xmlTag(bytes, resourceEnd);
      }
      break;
    }
    child = xmlTag(bytes, end);
  }
  if (!ranges.length) return { bytes, adapted: false, materialBearing: false, unit: null };
  const decoder = new TextDecoder(), decode = (start, end) => decoder.decode(bytes.subarray(start, end));
  const document = parse3MfXml(decode(0, model.end) + decode(resources.start, resources.end)
    + ranges.map(range => decode(range.start, range.end)).join('') + `</${resources.name}></${model.name}>`, path);
  const ownResources = firstElementChild(document.documentElement, 'resources');
  const nodes = Array.from(ownResources?.children || []).filter(node => ['basematerials', 'pbmetallicdisplayproperties'].includes(node.localName));
  const metallic = new Map(elementChildren(ownResources, 'pbmetallicdisplayproperties').map(node => [node.getAttribute('id'), node]));
  const changed = new Set(), validated = new Set();
  let materialBearing = false;
  for (const group of elementChildren(ownResources, 'basematerials')) {
    const bases = elementChildren(group, 'base');
    const ids = bases.map(base => attributeByLocalName(base, 'displaypropertiesid') || attributeByLocalName(group, 'displaypropertiesid'));
    for (const id of new Set(ids)) {
      if (!id || !metallic.has(id)) continue;
      materialBearing = true;
      const values = elementChildren(metallic.get(id), 'pbmetallic');
      if (values.length !== bases.length) throw new Error(`Invalid 3MF metallic display properties: ${id}`);
      if (validated.has(id)) continue;
      for (const value of values) for (const [key, fallback] of [['metallicness', 0], ['roughness', 1]]) {
        const raw = value.getAttribute(key), number = raw === null ? fallback : Number(raw);
        if (raw?.trim() === '' || !Number.isFinite(number) || number < 0 || number > 1) throw new Error(`Invalid 3MF metallic display properties: ${id}`);
        if (raw === null) { value.setAttribute(key, String(fallback)); changed.add(metallic.get(id)); }
      }
      validated.add(id);
    }
    bases.forEach((base, index) => {
      if (metallic.has(ids[index]) && base.getAttribute('displaypropertiesid') !== ids[index]) {
        base.setAttribute('displaypropertiesid', ids[index]); changed.add(group);
      }
    });
  }
  const patches = nodes.flatMap((node, index) => changed.has(node)
    ? [{ ...ranges[index], bytes: new TextEncoder().encode(new XMLSerializer().serializeToString(node)) }] : []);
  if (!patches.length) return { bytes, adapted: false, materialBearing, unit: document.documentElement.getAttribute('unit') || 'millimeter' };
  const output = new Uint8Array(bytes.length + patches.reduce((sum, patch) => sum + patch.bytes.length - (patch.end - patch.start), 0));
  let read = 0, write = 0;
  for (const patch of patches) {
    output.set(bytes.subarray(read, patch.start), write); write += patch.start - read;
    output.set(patch.bytes, write); write += patch.bytes.length; read = patch.end;
  }
  output.set(bytes.subarray(read), write);
  return { bytes: output, adapted: true, materialBearing, unit: document.documentElement.getAttribute('unit') || 'millimeter' };
}

async function threeMfLoaderPackage(buffer) {
  const { unzipSync, zipSync } = await import('three/examples/jsm/libs/fflate.module.js');
  const entries = unzipSync(new Uint8Array(buffer));
  let adapted = false, materialBearing = false, unit = null;
  for (const [path, bytes] of Object.entries(entries)) {
    if (!/\.model$/i.test(path)) continue;
    const result = bridgeThreeMfMaterialModel(bytes, path);
    entries[path] = result.bytes; adapted ||= result.adapted; materialBearing ||= result.materialBearing;
    if (unit === null && /^3D\/[^/]+\.model$/i.test(path)) unit = result.unit;
  }
  // Store rather than recompress: this temporary package exists only for the loader.
  const bytes = adapted ? zipSync(entries, { level: 0 }) : null;
  return { buffer: bytes ? bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) : buffer,
    materialBearing, unit: unit || await declared3MfUnit(buffer) };
}

export async function buildMeshDataFrom3MfBuffer(buffer) {
  const [THREE, { ThreeMFLoader }, { toCreasedNormals }] = await Promise.all([
    import("three"),
    import("three/examples/jsm/loaders/3MFLoader.js"),
    import("three/examples/jsm/utils/BufferGeometryUtils.js"),
  ]);
  const loader = new ThreeMFLoader();
  const compatible = await threeMfLoaderPackage(buffer);
  const { unit } = compatible;
  try {
    return { ...buildMeshDataFromThreeMfGroup(THREE, loader.parse(compatible.buffer), { toCreasedNormals }), unit };
  } catch (error) {
    // The geometry-only package fallback cannot retain a metallic material table.
    // Keep its existing compatibility role for ordinary packages, never hide a
    // material-bearing loader failure behind a plausible generic surface.
    if (compatible.materialBearing) throw new Error(`3MF material-bearing package could not be decoded without losing its display properties: ${error.message}`, { cause: error });
    try {
      return { ...await buildMeshDataFrom3MfPackageFallback(THREE, buffer), unit };
    } catch {
      throw error;
    }
  }
}
