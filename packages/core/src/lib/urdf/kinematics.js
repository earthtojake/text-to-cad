const IDENTITY_TRANSFORM = Object.freeze([
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  0, 0, 0, 1
]);
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const CYLINDER_SEGMENTS = 32;
const SPHERE_WIDTH_SEGMENTS = 24;
const SPHERE_HEIGHT_SEGMENTS = 12;
function srgbToLinear(value) {
  return value <= 0.04045
    ? value / 12.92
    : ((value + 0.055) / 1.055) ** 2.4;
}

function parseHexColorToLinearRgb(value) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return null;
  }
  const expanded = normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`
    : normalized;
  return [
    srgbToLinear(Number.parseInt(expanded.slice(1, 3), 16) / 255),
    srgbToLinear(Number.parseInt(expanded.slice(3, 5), 16) / 255),
    srgbToLinear(Number.parseInt(expanded.slice(5, 7), 16) / 255)
  ];
}

function toTransformArray(value, fallback = IDENTITY_TRANSFORM) {
  if (!Array.isArray(value) || value.length !== 16) {
    return [...fallback];
  }
  return value.map((component, index) => Number.isFinite(Number(component)) ? Number(component) : fallback[index]);
}

function toVector3(value, fallback = [0, 0, 1]) {
  if (!Array.isArray(value) || value.length < 3) {
    return [...fallback];
  }
  return [
    Number.isFinite(Number(value[0])) ? Number(value[0]) : fallback[0],
    Number.isFinite(Number(value[1])) ? Number(value[1]) : fallback[1],
    Number.isFinite(Number(value[2])) ? Number(value[2]) : fallback[2]
  ];
}

function normalizeVector(vector) {
  const [x, y, z] = toVector3(vector, [0, 0, 1]);
  const length = Math.hypot(x, y, z);
  if (length <= 1e-9) {
    return [0, 0, 1];
  }
  return [x / length, y / length, z / length];
}

export function multiplyTransforms(left, right) {
  const a = toTransformArray(left);
  const b = toTransformArray(right);
  const product = new Array(16).fill(0);
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      let total = 0;
      for (let offset = 0; offset < 4; offset += 1) {
        total += a[(row * 4) + offset] * b[(offset * 4) + column];
      }
      product[(row * 4) + column] = total;
    }
  }
  return product;
}

export function translationTransform(x, y, z) {
  return [
    1, 0, 0, Number.isFinite(Number(x)) ? Number(x) : 0,
    0, 1, 0, Number.isFinite(Number(y)) ? Number(y) : 0,
    0, 0, 1, Number.isFinite(Number(z)) ? Number(z) : 0,
    0, 0, 0, 1
  ];
}

export function rotationTransformFromRpy(roll, pitch, yaw) {
  const safeRoll = Number.isFinite(Number(roll)) ? Number(roll) : 0;
  const safePitch = Number.isFinite(Number(pitch)) ? Number(pitch) : 0;
  const safeYaw = Number.isFinite(Number(yaw)) ? Number(yaw) : 0;
  const sr = Math.sin(safeRoll);
  const cr = Math.cos(safeRoll);
  const sp = Math.sin(safePitch);
  const cp = Math.cos(safePitch);
  const sy = Math.sin(safeYaw);
  const cy = Math.cos(safeYaw);
  return [
    cy * cp, (cy * sp * sr) - (sy * cr), (cy * sp * cr) + (sy * sr), 0,
    sy * cp, (sy * sp * sr) + (cy * cr), (sy * sp * cr) - (cy * sr), 0,
    -sp, cp * sr, cp * cr, 0,
    0, 0, 0, 1
  ];
}

export function poseTransformFromXyzRpy(values) {
  const poseValues = Array.isArray(values) ? values : [];
  return multiplyTransforms(
    translationTransform(poseValues[0], poseValues[1], poseValues[2]),
    rotationTransformFromRpy(poseValues[3], poseValues[4], poseValues[5])
  );
}

export function axisAngleTransform(axis, angleRad) {
  const [x, y, z] = normalizeVector(axis);
  const cosine = Math.cos(angleRad);
  const sine = Math.sin(angleRad);
  const oneMinusCosine = 1 - cosine;
  return [
    cosine + (x * x * oneMinusCosine), (x * y * oneMinusCosine) - (z * sine), (x * z * oneMinusCosine) + (y * sine), 0,
    (y * x * oneMinusCosine) + (z * sine), cosine + (y * y * oneMinusCosine), (y * z * oneMinusCosine) - (x * sine), 0,
    (z * x * oneMinusCosine) - (y * sine), (z * y * oneMinusCosine) + (x * sine), cosine + (z * z * oneMinusCosine), 0,
    0, 0, 0, 1
  ];
}

export function transformPoint(transform, point) {
  const matrix = toTransformArray(transform);
  const [x, y, z] = toVector3(point, [0, 0, 0]);
  return [
    (matrix[0] * x) + (matrix[1] * y) + (matrix[2] * z) + matrix[3],
    (matrix[4] * x) + (matrix[5] * y) + (matrix[6] * z) + matrix[7],
    (matrix[8] * x) + (matrix[9] * y) + (matrix[10] * z) + matrix[11]
  ];
}

export function invertRigidTransform(transform) {
  const matrix = toTransformArray(transform);
  return [
    matrix[0], matrix[4], matrix[8], -((matrix[0] * matrix[3]) + (matrix[4] * matrix[7]) + (matrix[8] * matrix[11])),
    matrix[1], matrix[5], matrix[9], -((matrix[1] * matrix[3]) + (matrix[5] * matrix[7]) + (matrix[9] * matrix[11])),
    matrix[2], matrix[6], matrix[10], -((matrix[2] * matrix[3]) + (matrix[6] * matrix[7]) + (matrix[10] * matrix[11])),
    0, 0, 0, 1
  ];
}

export function transformBounds(bounds, transform) {
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : [0, 0, 0];
  const corners = [
    [min[0], min[1], min[2]],
    [min[0], min[1], max[2]],
    [min[0], max[1], min[2]],
    [min[0], max[1], max[2]],
    [max[0], min[1], min[2]],
    [max[0], min[1], max[2]],
    [max[0], max[1], min[2]],
    [max[0], max[1], max[2]]
  ];
  const transformed = corners.map((corner) => transformPoint(transform, corner));
  const xs = transformed.map((point) => point[0]);
  const ys = transformed.map((point) => point[1]);
  const zs = transformed.map((point) => point[2]);
  return {
    min: [Math.min(...xs), Math.min(...ys), Math.min(...zs)],
    max: [Math.max(...xs), Math.max(...ys), Math.max(...zs)]
  };
}

export function mergeBounds(boundsList) {
  const normalized = (Array.isArray(boundsList) ? boundsList : []).filter(Boolean);
  if (!normalized.length) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0]
    };
  }
  const xs = normalized.flatMap((bounds) => [bounds.min[0], bounds.max[0]]);
  const ys = normalized.flatMap((bounds) => [bounds.min[1], bounds.max[1]]);
  const zs = normalized.flatMap((bounds) => [bounds.min[2], bounds.max[2]]);
  return {
    min: [Math.min(...xs), Math.min(...ys), Math.min(...zs)],
    max: [Math.max(...xs), Math.max(...ys), Math.max(...zs)]
  };
}

export function buildDefaultUrdfJointValues(urdfData) {
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  return Object.fromEntries(
    joints
      .filter((joint) => String(joint?.type || "") !== "fixed" && !joint?.mimic)
      .map((joint) => [String(joint?.name || ""), Number(joint?.defaultValueDeg) || 0])
      .filter(([name]) => name)
  );
}

export function clampJointValueDeg(joint, valueDeg) {
  const defaultValue = Number(joint?.defaultValueDeg) || 0;
  const jointType = String(joint?.type || "");
  if (jointType === "fixed") {
    return defaultValue;
  }
  const numericValue = Number.isFinite(Number(valueDeg)) ? Number(valueDeg) : defaultValue;
  if (jointType === "continuous") {
    return numericValue;
  }
  const minValue = Number.isFinite(Number(joint?.minValueDeg)) ? Number(joint.minValueDeg) : numericValue;
  const maxValue = Number.isFinite(Number(joint?.maxValueDeg)) ? Number(joint.maxValueDeg) : numericValue;
  return Math.min(Math.max(numericValue, minValue), Math.max(minValue, maxValue));
}

function isAngularJoint(joint) {
  const jointType = String(joint?.type || "fixed");
  return jointType === "continuous" || jointType === "revolute";
}

function jointValueToNative(joint, value) {
  const clampedValue = clampJointValueDeg(joint, value);
  return isAngularJoint(joint) ? (clampedValue * Math.PI) / 180 : clampedValue;
}

function nativeToJointValue(joint, value) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : 0;
  return isAngularJoint(joint) ? (numericValue * 180) / Math.PI : numericValue;
}

function translationAlongAxisTransform(axis, distance) {
  const [x, y, z] = normalizeVector(axis);
  const safeDistance = Number.isFinite(Number(distance)) ? Number(distance) : 0;
  return [
    1, 0, 0, x * safeDistance,
    0, 1, 0, y * safeDistance,
    0, 0, 1, z * safeDistance,
    0, 0, 0, 1
  ];
}

/**
 * A joint's motion alone, in its own frame: the turn about its axis or the slide
 * along it at `valueDeg` (degrees, or metres for a prismatic joint), clamped as the
 * solver clamps it. A fixed joint does not move. This is the one factor of a joint's
 * local transform a pose changes, so a scene graph writes it and nothing else.
 */
export function jointMotionTransform(joint, valueDeg) {
  const jointType = String(joint?.type || "fixed");
  if (jointType === "fixed") {
    return [...IDENTITY_TRANSFORM];
  }
  const axis = toVector3(joint?.axis ?? joint?.axisInJointFrame ?? joint?.axisInParentFrame, [0, 0, 1]);
  if (jointType === "prismatic") {
    return translationAlongAxisTransform(axis, clampJointValueDeg(joint, valueDeg));
  }
  // URDF axes are defined in the joint frame; SDF axes are converted into the
  // joint frame at parse time. In both cases the static parent-to-joint transform
  // applies before the animated axis motion.
  return axisAngleTransform(axis, (clampJointValueDeg(joint, valueDeg) * Math.PI) / 180);
}

export function posedJointLocalTransform(joint, valueDeg) {
  const originTransform = toTransformArray(joint?.originTransform);
  const preMotionTransform = toTransformArray(joint?.preMotionTransform, originTransform);
  const postMotionTransform = toTransformArray(joint?.postMotionTransform);
  if (String(joint?.type || "fixed") === "fixed") {
    return multiplyTransforms(preMotionTransform, postMotionTransform);
  }
  return multiplyTransforms(multiplyTransforms(preMotionTransform, jointMotionTransform(joint, valueDeg)), postMotionTransform);
}

function resolveJointValue(joint, jointByName, jointValuesByName, resolving = new Set()) {
  const jointName = String(joint?.name || "");
  if (!joint?.mimic) {
    return clampJointValueDeg(joint, jointValuesByName?.[jointName]);
  }
  if (resolving.has(jointName)) {
    return clampJointValueDeg(joint, joint?.defaultValueDeg);
  }
  resolving.add(jointName);
  const mimic = joint.mimic;
  const masterJoint = jointByName.get(String(mimic.joint || ""));
  const masterValue = masterJoint
    ? resolveJointValue(masterJoint, jointByName, jointValuesByName, resolving)
    : Number(jointValuesByName?.[mimic.joint]) || 0;
  resolving.delete(jointName);

  const masterNativeValue = masterJoint ? jointValueToNative(masterJoint, masterValue) : masterValue;
  const multiplier = Number.isFinite(Number(mimic.multiplier)) ? Number(mimic.multiplier) : 1;
  const offset = Number.isFinite(Number(mimic.offset)) ? Number(mimic.offset) : 0;
  return clampJointValueDeg(joint, nativeToJointValue(joint, (multiplier * masterNativeValue) + offset));
}

/**
 * The value every joint is posed at for `jointValuesByName`: driven joints clamped to
 * their limits, mimic followers solved from their master. One entry per named joint.
 *
 * @returns {Map<string, number>}  Degrees, or metres for a prismatic joint.
 */
export function resolveUrdfJointValues(urdfData, jointValuesByName = {}) {
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  return new Map([...jointByName].map(([name, joint]) => [name, resolveJointValue(joint, jointByName, jointValuesByName)]));
}

export function solveUrdfLinkWorldTransforms(urdfData, jointValuesByName = {}) {
  const rootLink = String(urdfData?.rootLink || "");
  const rootWorldTransform = toTransformArray(urdfData?.rootWorldTransform);
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  const linkTransforms = new Map();
  if (!rootLink) {
    return linkTransforms;
  }
  const jointsByParent = new Map();
  for (const joint of joints) {
    const parentLink = String(joint?.parentLink || "");
    if (!parentLink) {
      continue;
    }
    const current = jointsByParent.get(parentLink) || [];
    current.push(joint);
    jointsByParent.set(parentLink, current);
  }

  const visit = (linkName, worldTransform) => {
    linkTransforms.set(linkName, worldTransform);
    const childJoints = jointsByParent.get(linkName) || [];
    for (const joint of childJoints) {
      const childLink = String(joint?.childLink || "");
      if (!childLink) {
        continue;
      }
      const jointValueDeg = resolveJointValue(joint, jointByName, jointValuesByName);
      const childWorldTransform = multiplyTransforms(worldTransform, posedJointLocalTransform(joint, jointValueDeg));
      visit(childLink, childWorldTransform);
    }
  };

  visit(rootLink, rootWorldTransform);
  return linkTransforms;
}

export function linkOriginInFrame(urdfData, jointValuesByName, linkName, frameLinkName) {
  const normalizedLinkName = String(linkName || "").trim();
  const normalizedFrameLinkName = String(frameLinkName || "").trim();
  if (!normalizedLinkName || !normalizedFrameLinkName) {
    return null;
  }
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(urdfData, jointValuesByName);
  const linkWorldTransform = linkWorldTransforms.get(normalizedLinkName);
  const frameWorldTransform = linkWorldTransforms.get(normalizedFrameLinkName);
  if (!linkWorldTransform || !frameWorldTransform) {
    return null;
  }
  return transformPoint(
    invertRigidTransform(frameWorldTransform),
    transformPoint(linkWorldTransform, [0, 0, 0])
  );
}

function resolveVisualMesh(meshesByUrl, meshUrl, partFileRef) {
  const lookupKey = meshUrl || partFileRef;
  if (!lookupKey) {
    return null;
  }
  if (meshesByUrl instanceof Map) {
    return meshesByUrl.get(lookupKey) || null;
  }
  if (meshesByUrl && typeof meshesByUrl === "object") {
    return meshesByUrl[lookupKey] || null;
  }
  return null;
}

function primitiveBounds(min, max) {
  return {
    min,
    max
  };
}

function primitiveMesh(vertices, normals, indices, bounds) {
  return {
    vertices: new Float32Array(vertices),
    normals: new Float32Array(normals),
    indices: new Uint32Array(indices),
    colors: new Float32Array(0),
    edge_indices: new Uint32Array(0),
    bounds,
    has_source_colors: false
  };
}

function buildBoxPrimitiveMesh(size) {
  const [sx, sy, sz] = toVector3(size, [1, 1, 1]);
  const hx = sx / 2;
  const hy = sy / 2;
  const hz = sz / 2;
  const vertices = [];
  const normals = [];
  const indices = [];
  const faces = [
    [[1, 0, 0], [[hx, -hy, -hz], [hx, hy, -hz], [hx, hy, hz], [hx, -hy, hz]]],
    [[-1, 0, 0], [[-hx, hy, -hz], [-hx, -hy, -hz], [-hx, -hy, hz], [-hx, hy, hz]]],
    [[0, 1, 0], [[-hx, hy, -hz], [hx, hy, -hz], [hx, hy, hz], [-hx, hy, hz]]],
    [[0, -1, 0], [[hx, -hy, -hz], [-hx, -hy, -hz], [-hx, -hy, hz], [hx, -hy, hz]]],
    [[0, 0, 1], [[-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz]]],
    [[0, 0, -1], [[-hx, hy, -hz], [hx, hy, -hz], [hx, -hy, -hz], [-hx, -hy, -hz]]]
  ];

  for (const [normal, corners] of faces) {
    const offset = vertices.length / 3;
    for (const corner of corners) {
      vertices.push(...corner);
      normals.push(...normal);
    }
    indices.push(offset, offset + 1, offset + 2, offset, offset + 2, offset + 3);
  }

  return primitiveMesh(vertices, normals, indices, primitiveBounds([-hx, -hy, -hz], [hx, hy, hz]));
}

function buildCylinderPrimitiveMesh(radius, length) {
  const r = Number.isFinite(Number(radius)) ? Number(radius) : 0.5;
  const halfLength = (Number.isFinite(Number(length)) ? Number(length) : 1) / 2;
  const vertices = [];
  const normals = [];
  const indices = [];

  for (let index = 0; index < CYLINDER_SEGMENTS; index += 1) {
    const nextIndex = (index + 1) % CYLINDER_SEGMENTS;
    const angle = (index / CYLINDER_SEGMENTS) * Math.PI * 2;
    const nextAngle = (nextIndex / CYLINDER_SEGMENTS) * Math.PI * 2;
    const x0 = Math.cos(angle) * r;
    const y0 = Math.sin(angle) * r;
    const x1 = Math.cos(nextAngle) * r;
    const y1 = Math.sin(nextAngle) * r;
    const base = vertices.length / 3;
    vertices.push(x0, y0, -halfLength, x1, y1, -halfLength, x1, y1, halfLength, x0, y0, halfLength);
    normals.push(Math.cos(angle), Math.sin(angle), 0, Math.cos(nextAngle), Math.sin(nextAngle), 0, Math.cos(nextAngle), Math.sin(nextAngle), 0, Math.cos(angle), Math.sin(angle), 0);
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3);

    const topBase = vertices.length / 3;
    vertices.push(0, 0, halfLength, x0, y0, halfLength, x1, y1, halfLength);
    normals.push(0, 0, 1, 0, 0, 1, 0, 0, 1);
    indices.push(topBase, topBase + 1, topBase + 2);

    const bottomBase = vertices.length / 3;
    vertices.push(0, 0, -halfLength, x1, y1, -halfLength, x0, y0, -halfLength);
    normals.push(0, 0, -1, 0, 0, -1, 0, 0, -1);
    indices.push(bottomBase, bottomBase + 1, bottomBase + 2);
  }

  return primitiveMesh(vertices, normals, indices, primitiveBounds([-r, -r, -halfLength], [r, r, halfLength]));
}

function buildSpherePrimitiveMesh(radius) {
  const r = Number.isFinite(Number(radius)) ? Number(radius) : 0.5;
  const vertices = [];
  const normals = [];
  const indices = [];

  for (let lat = 0; lat <= SPHERE_HEIGHT_SEGMENTS; lat += 1) {
    const theta = (lat / SPHERE_HEIGHT_SEGMENTS) * Math.PI;
    const sinTheta = Math.sin(theta);
    const cosTheta = Math.cos(theta);
    for (let lon = 0; lon <= SPHERE_WIDTH_SEGMENTS; lon += 1) {
      const phi = (lon / SPHERE_WIDTH_SEGMENTS) * Math.PI * 2;
      const x = Math.cos(phi) * sinTheta;
      const y = Math.sin(phi) * sinTheta;
      const z = cosTheta;
      vertices.push(x * r, y * r, z * r);
      normals.push(x, y, z);
    }
  }

  const rowWidth = SPHERE_WIDTH_SEGMENTS + 1;
  for (let lat = 0; lat < SPHERE_HEIGHT_SEGMENTS; lat += 1) {
    for (let lon = 0; lon < SPHERE_WIDTH_SEGMENTS; lon += 1) {
      const first = (lat * rowWidth) + lon;
      const second = first + rowWidth;
      indices.push(first, second, first + 1, second, second + 1, first + 1);
    }
  }

  return primitiveMesh(vertices, normals, indices, primitiveBounds([-r, -r, -r], [r, r, r]));
}

function buildUrdfPrimitiveMesh(primitive) {
  const type = String(primitive?.type || "").trim().toLowerCase();
  if (type === "box") {
    return buildBoxPrimitiveMesh(primitive?.size);
  }
  if (type === "cylinder") {
    return buildCylinderPrimitiveMesh(primitive?.radius, primitive?.length);
  }
  if (type === "sphere") {
    return buildSpherePrimitiveMesh(primitive?.radius);
  }
  return null;
}

// A link mesh may carry its colour PER PART rather than per vertex: a GLB with one material
// per primitive produces `has_source_colors` with an empty `colors` buffer and the colour on
// `parts[].color`. A URDF link is ONE renderable part, so that detail had nowhere to go and
// the whole link fell back to default grey — an authored two-colour hand rendered as a grey
// stub, with no warning, purely because the colour was a material rather than an attribute.
// Expand it into the per-vertex buffer the composer already reads, which is exactly what the
// composer does for a `<material>` the URDF itself declares.
function withPerVertexPartColors(partMesh) {
  const vertices = partMesh?.vertices;
  if (!partMesh?.has_source_colors || !vertices?.length || partMesh.colors?.length) {
    return partMesh;
  }
  const parts = Array.isArray(partMesh.parts) ? partMesh.parts : [];
  if (!parts.length) {
    return partMesh;
  }
  const colors = new Float32Array(vertices.length);
  let painted = false;
  for (const part of parts) {
    const rgb = parseHexColorToLinearRgb(String(part?.color || "").trim());
    const offset = Number(part?.vertexOffset);
    const count = Number(part?.vertexCount);
    if (!rgb || !Number.isFinite(offset) || !Number.isFinite(count) || count <= 0) {
      continue;
    }
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

function resolveUrdfVisuals(urdfData, meshesByUrl) {
  const links = Array.isArray(urdfData?.links) ? urdfData.links : [];
  const resolvedVisuals = [];
  for (const link of links) {
    const linkName = String(link?.name || "");
    const visuals = Array.isArray(link?.visuals) ? link.visuals : [];
    for (const visual of visuals) {
      const meshUrl = String(visual?.meshUrl || "");
      const partFileRef = String(visual?.partFileRef || "");
      const loadedMesh = visual?.primitive
        ? buildUrdfPrimitiveMesh(visual.primitive)
        : resolveVisualMesh(meshesByUrl, meshUrl, partFileRef);
      if (!loadedMesh) {
        continue;
      }
      const partMesh = withPerVertexPartColors(loadedMesh);
      resolvedVisuals.push({
        linkName,
        meshUrl,
        partFileRef,
        visual,
        partMesh
      });
    }
  }
  return resolvedVisuals;
}

/**
 * One part per resolved visual of a description: its link, its local transform (the visual
 * origin and `<mesh scale>`), the mesh it draws in that mesh's own units and frame (a loaded
 * link mesh, or a primitive built here), the colour the description gives it, and whether it
 * has a colour of its own at all. What a robot's scene is built from (`robotParts.js`, then
 * `robotScene.js`, in the viewer and in a snapshot alike); a pose never touches it, because a
 * pose is the scene graph's joint matrices. A visual whose mesh is not in `meshesByUrl` has no
 * part: the loader fails a robot with a missing link mesh before it gets here.
 *
 * @param {object} urdfData  A parsed URDF or SDF (an SRDF's is its URDF's).
 * @param {Map<string, object> | Record<string, object>} meshesByUrl  Every link mesh, loaded.
 */
export function buildUrdfVisualParts(urdfData, meshesByUrl) {
  return resolveUrdfVisuals(urdfData, meshesByUrl).map(({ linkName, meshUrl, partFileRef, partMesh, visual }, visualIndex) => {
    const visualColor = String(visual?.color || "").trim();
    const partLabel = String(visual?.label || visual?.instanceId || visual?.id || meshUrl || partFileRef).trim();
    return {
      id: String(visual?.id || `${linkName}:${meshUrl || partFileRef}`),
      name: partLabel,
      label: partLabel,
      occurrenceId: String(visual?.occurrenceId || "").trim(),
      instanceId: String(visual?.instanceId || "").trim(),
      color: visualColor,
      meshUrl,
      partFileRef,
      linkName,
      localTransform: toTransformArray(visual?.localTransform),
      sourceBounds: partMesh.bounds,
      bounds: partMesh.bounds,
      hasSourceColors: !!parseHexColorToLinearRgb(visualColor) || urdfMeshHasSourceColors(partMesh),
      sourceMesh: partMesh,
      sourceMeshKey: String(meshUrl || partFileRef || visual?.id || `visual:${visualIndex + 1}`),
      vertexCount: Math.floor((partMesh.vertices?.length || 0) / 3),
      triangleCount: Math.floor((partMesh.indices?.length || 0) / 3)
    };
  });
}

function urdfMeshHasSourceColors(partMesh) {
  return !!partMesh?.has_source_colors &&
    partMesh.colors?.length > 0 &&
    partMesh.colors.length === partMesh.vertices?.length;
}
