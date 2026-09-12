import { invertRigidTransform, multiplyTransforms, poseTransformFromXyzRpy } from "./kinematics.js";

const IDENTITY_TRANSFORM = Object.freeze([
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 1, 0,
  0, 0, 0, 1
]);
const SDF_MODEL_FRAME = "__model__";
const SDF_WORLD_FRAME = "world";
const SDF_VIRTUAL_ROOT_LINK = "__sdf_model__";

function elementName(node) {
  return String(node?.localName || node?.tagName || "").split(":").pop();
}

function childElements(parent) {
  return Array.from(parent?.childNodes || []).filter((node) => node?.nodeType === 1);
}

function childElementsByTag(parent, tagName) {
  return childElements(parent).filter((node) => elementName(node) === tagName);
}

function descendantElementsByTag(parent, tagName, result = []) {
  for (const child of childElements(parent)) {
    if (elementName(child) === tagName) {
      result.push(child);
    }
    descendantElementsByTag(child, tagName, result);
  }
  return result;
}

function childText(parent, tagName) {
  return String(childElementsByTag(parent, tagName)[0]?.textContent || "").trim();
}

function pluginName(pluginElement) {
  return String(pluginElement?.getAttribute("name") || "").trim();
}

function pluginFilename(pluginElement) {
  return String(pluginElement?.getAttribute("filename") || "").trim();
}

function parseNumberList(value, count, fallback, context) {
  const text = String(value || "").trim();
  if (!text) {
    return [...fallback];
  }
  const parsed = text.split(/\s+/).map((entry) => Number(entry));
  if (parsed.length !== count || parsed.some((entry) => !Number.isFinite(entry))) {
    throw new Error(`${context} must contain ${count} numeric values`);
  }
  return parsed;
}

function translationTransform(x, y, z) {
  return [
    1, 0, 0, x,
    0, 1, 0, y,
    0, 0, 1, z,
    0, 0, 0, 1
  ];
}

function scaleTransform(x, y, z) {
  return [
    x, 0, 0, 0,
    0, y, 0, 0,
    0, 0, z, 0,
    0, 0, 0, 1
  ];
}

function rotationTransformFromRpy(roll, pitch, yaw) {
  const sr = Math.sin(roll);
  const cr = Math.cos(roll);
  const sp = Math.sin(pitch);
  const cp = Math.cos(pitch);
  const sy = Math.sin(yaw);
  const cy = Math.cos(yaw);
  return [
    cy * cp, (cy * sp * sr) - (sy * cr), (cy * sp * cr) + (sy * sr), 0,
    sy * cp, (sy * sp * sr) + (cy * cr), (sy * sp * cr) - (cy * sr), 0,
    -sp, cp * sr, cp * cr, 0,
    0, 0, 0, 1
  ];
}

function poseTransform(values) {
  return poseTransformFromXyzRpy(values);
}

function parseBooleanAttribute(value, fallback = false) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!normalized) {
    return fallback;
  }
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return fallback;
}

function parsePose(parentElement, context) {
  const poseElement = childElementsByTag(parentElement, "pose")[0] || null;
  if (!poseElement) {
    return {
      hasPose: false,
      rotationFormat: "euler_rpy",
      relativeTo: "",
      values: [0, 0, 0, 0, 0, 0],
      transform: [...IDENTITY_TRANSFORM]
    };
  }
  const rotationFormat = String(poseElement.getAttribute("rotation_format") || "euler_rpy").trim().toLowerCase();
  if (rotationFormat !== "euler_rpy") {
    throw new Error(`${context} pose uses unsupported rotation_format ${JSON.stringify(rotationFormat)}`);
  }
  const values = parseNumberList(
    poseElement.textContent,
    6,
    [0, 0, 0, 0, 0, 0],
    `${context} pose`
  );
  if (parseBooleanAttribute(poseElement.getAttribute("degrees"), false)) {
    values[3] *= Math.PI / 180;
    values[4] *= Math.PI / 180;
    values[5] *= Math.PI / 180;
  }
  return {
    hasPose: true,
    rotationFormat,
    relativeTo: String(poseElement.getAttribute("relative_to") || "").trim(),
    values,
    transform: poseTransform(values)
  };
}

function normalizeAbsoluteUrl(url) {
  if (url instanceof URL) {
    return url.toString();
  }
  return new URL(String(url || "/"), globalThis.window?.location?.href || "http://localhost/").toString();
}

function urlHasExplicitOrigin(value) {
  try {
    const url = new URL(String(value || ""));
    return Boolean(url.origin && url.origin !== "null");
  } catch {
    return false;
  }
}

function resolvedMeshUrlString(resolvedUrl, { sourceUrl }) {
  if (urlHasExplicitOrigin(sourceUrl)) {
    return resolvedUrl.toString();
  }
  return `${resolvedUrl.pathname}${resolvedUrl.search}`;
}

function resolveMeshUrl(uri, sourceUrl) {
  const rawUri = String(uri || "").trim();
  if (!rawUri) {
    throw new Error("SDF mesh URI is required");
  }
  const normalizedSourceUrl = normalizeAbsoluteUrl(sourceUrl);
  let resolvedUrl;
  if (rawUri.startsWith("package://")) {
    resolvedUrl = new URL(rawUri.slice("package://".length).replace(/^\/+/, ""), new URL("/", normalizedSourceUrl));
  } else if (/^[a-z][a-z0-9+.-]*:\/\//i.test(rawUri)) {
    throw new Error(`Unsupported SDF mesh URI scheme: ${rawUri}`);
  } else {
    resolvedUrl = new URL(rawUri, normalizedSourceUrl);
  }
  return resolvedMeshUrlString(resolvedUrl, { sourceUrl });
}

function labelForMeshUri(uri) {
  const parts = String(uri || "").split("/");
  return parts[parts.length - 1] || "mesh";
}

function rotateVectorByTransform(transform, vector) {
  const matrix = Array.isArray(transform) && transform.length === 16 ? transform : IDENTITY_TRANSFORM;
  const [x, y, z] = Array.isArray(vector) ? vector : [0, 0, 1];
  return [
    (matrix[0] * x) + (matrix[1] * y) + (matrix[2] * z),
    (matrix[4] * x) + (matrix[5] * y) + (matrix[6] * z),
    (matrix[8] * x) + (matrix[9] * y) + (matrix[10] * z)
  ];
}

function normalizeAxisVector(axis, fallback = [0, 0, 1]) {
  const vector = Array.isArray(axis) && axis.length >= 3 ? axis : fallback;
  const x = Number(vector[0]);
  const y = Number(vector[1]);
  const z = Number(vector[2]);
  const length = Math.hypot(x, y, z);
  if (!Number.isFinite(length) || length <= 1e-9) {
    return [...fallback];
  }
  return [x / length, y / length, z / length];
}

function transformDirectionBetweenFrames(vector, fromFrameWorldTransform, toFrameWorldTransform) {
  const worldVector = rotateVectorByTransform(fromFrameWorldTransform, vector);
  return rotateVectorByTransform(invertRigidTransform(toFrameWorldTransform), worldVector);
}

function parseRgbaColor(colorText, context) {
  const rawValues = String(colorText || "").trim().split(/\s+/).filter(Boolean);
  if (rawValues.length !== 3 && rawValues.length !== 4) {
    throw new Error(`${context} must contain 3 or 4 numeric color values`);
  }
  const values = rawValues.map((entry) => Number(entry));
  if (values.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
    throw new Error(`${context} must use color values between 0 and 1`);
  }
  return `#${values.slice(0, 3).map((value) => {
    const component = Math.round(value * 255);
    return component.toString(16).padStart(2, "0");
  }).join("")}`;
}

function materialColorFromElement(materialElement, context) {
  if (!materialElement) {
    return "";
  }
  const diffuseText = childText(materialElement, "diffuse");
  if (diffuseText) {
    return parseRgbaColor(diffuseText, `${context} diffuse material`);
  }
  const ambientText = childText(materialElement, "ambient");
  return ambientText ? parseRgbaColor(ambientText, `${context} ambient material`) : "";
}

function occurrenceIdFromSdfName(value) {
  const normalized = String(value || "").trim();
  const match = /(?:^|_)o(\d+(?:_\d+)+)(?:_|$)/i.exec(normalized);
  return match ? `o${match[1].replace(/_/g, ".")}` : "";
}

function parseMeshInstance(containerElement, { linkName, kind, index, sourceUrl }) {
  const labelKind = kind === "collision" ? "collision" : "visual";
  const instanceId = String(containerElement?.getAttribute("name") || "").trim();
  const pose = parsePose(containerElement, `SDF link ${linkName} ${labelKind} ${index}`);
  const geometryElement = childElementsByTag(containerElement, "geometry")[0] || null;
  const meshElement = geometryElement ? childElementsByTag(geometryElement, "mesh")[0] : null;
  if (!meshElement) {
    const geometryKind = geometryElement ? (elementName(childElements(geometryElement)[0]) || "unknown") : "missing";
    return {
      id: `${linkName}:${kind[0]}${index}`,
      label: `${geometryKind} ${labelKind}`,
      instanceId,
      occurrenceId: occurrenceIdFromSdfName(instanceId) || occurrenceIdFromSdfName(linkName),
      meshUrl: "",
      color: "",
      localTransform: pose.transform,
      pose,
      unsupportedGeometry: geometryKind
    };
  }
  const uri = childText(meshElement, "uri");
  if (!uri) {
    return {
      id: `${linkName}:${kind[0]}${index}`,
      label: `mesh ${labelKind}`,
      instanceId,
      occurrenceId: occurrenceIdFromSdfName(instanceId) || occurrenceIdFromSdfName(linkName),
      meshUrl: "",
      color: "",
      localTransform: pose.transform,
      pose,
      unsupportedGeometry: "mesh"
    };
  }
  const [scaleX, scaleY, scaleZ] = parseNumberList(
    childText(meshElement, "scale"),
    3,
    [1, 1, 1],
    `SDF link ${linkName} ${labelKind} ${index} mesh scale`
  );
  const meshScaleTransform = scaleTransform(scaleX, scaleY, scaleZ);
  return {
    id: `${linkName}:${kind[0]}${index}`,
    label: labelForMeshUri(uri),
    instanceId,
    occurrenceId: occurrenceIdFromSdfName(instanceId) || occurrenceIdFromSdfName(linkName),
    meshUrl: resolveMeshUrl(uri, sourceUrl || "/"),
    color: materialColorFromElement(
      childElementsByTag(containerElement, "material")[0] || null,
      `SDF link ${linkName} ${labelKind} ${index}`
    ),
    localTransform: multiplyTransforms(pose.transform, meshScaleTransform),
    pose,
    scaleTransform: meshScaleTransform
  };
}

function parseLink(linkElement, sourceUrl) {
  const name = String(linkElement.getAttribute("name") || "").trim();
  if (!name) {
    throw new Error("SDF link name is required");
  }
  const visuals = childElementsByTag(linkElement, "visual").map((visualElement, index) => (
    parseMeshInstance(visualElement, { linkName: name, kind: "visual", index: index + 1, sourceUrl })
  ));
  const collisions = childElementsByTag(linkElement, "collision").map((collisionElement, index) => (
    parseMeshInstance(collisionElement, { linkName: name, kind: "collision", index: index + 1, sourceUrl })
  ));
  return {
    name,
    visuals,
    collisions,
    pose: parsePose(linkElement, `SDF link ${name}`)
  };
}

function parseFrame(frameElement) {
  const name = String(frameElement.getAttribute("name") || "").trim();
  if (!name) {
    throw new Error("SDF frame name is required");
  }
  return {
    name,
    attachedTo: String(frameElement.getAttribute("attached_to") || "").trim(),
    pose: parsePose(frameElement, `SDF frame ${name}`)
  };
}

function parseJointLimit(axisElement, jointName, jointType) {
  if (jointType === "continuous") {
    return { minValueDeg: -180, maxValueDeg: 180 };
  }
  if (jointType !== "revolute" && jointType !== "prismatic") {
    return { minValueDeg: 0, maxValueDeg: 0 };
  }
  const limitElement = childElementsByTag(axisElement, "limit")[0] || null;
  const lower = Number(childText(limitElement, "lower"));
  const upper = Number(childText(limitElement, "upper"));
  if (!Number.isFinite(lower) || !Number.isFinite(upper)) {
    throw new Error(`SDF ${jointType} joint ${jointName} has invalid limits`);
  }
  if (jointType === "revolute") {
    return {
      minValueDeg: (lower * 180) / Math.PI,
      maxValueDeg: (upper * 180) / Math.PI
    };
  }
  return {
    minValueDeg: lower,
    maxValueDeg: upper
  };
}

function normalizeSdfFrameName(frameName, { modelName, defaultFrame = SDF_MODEL_FRAME } = {}) {
  const rawName = String(frameName || "").trim();
  if (!rawName) {
    return defaultFrame;
  }
  if (rawName === modelName || rawName === SDF_MODEL_FRAME) {
    return SDF_MODEL_FRAME;
  }
  if (rawName === SDF_WORLD_FRAME) {
    return SDF_WORLD_FRAME;
  }
  return rawName;
}

function parseJoint(jointElement, { modelName }) {
  const name = String(jointElement.getAttribute("name") || "").trim();
  if (!name) {
    throw new Error("SDF joint name is required");
  }
  const type = String(jointElement.getAttribute("type") || "").trim().toLowerCase();
  if (!["fixed", "continuous", "revolute", "prismatic"].includes(type)) {
    throw new Error(`Unsupported SDF joint type: ${type || "(missing)"}`);
  }
  const parentFrame = normalizeSdfFrameName(childText(jointElement, "parent"), { modelName, defaultFrame: "" });
  const childFrame = normalizeSdfFrameName(childText(jointElement, "child"), { modelName, defaultFrame: "" });
  if (!parentFrame || !childFrame) {
    throw new Error(`SDF joint ${name} must declare parent and child frames`);
  }
  if (childFrame === SDF_WORLD_FRAME) {
    throw new Error(`SDF joint ${name} cannot use world as the child frame`);
  }
  const axisElement = childElementsByTag(jointElement, "axis")[0] || null;
  const axisXyzElement = childElementsByTag(axisElement, "xyz")[0] || null;
  const axis = type === "fixed"
    ? [1, 0, 0]
    : normalizeAxisVector(parseNumberList(axisXyzElement?.textContent, 3, [0, 0, 1], `SDF joint ${name} axis`));
  const limits = parseJointLimit(axisElement, name, type);
  return {
    name,
    type,
    parentFrame,
    childFrame,
    pose: parsePose(jointElement, `SDF joint ${name}`),
    axis,
    axisExpressedIn: String(axisXyzElement?.getAttribute("expressed_in") || "").trim(),
    defaultValueDeg: 0,
    minValueDeg: limits.minValueDeg,
    maxValueDeg: limits.maxValueDeg,
    mimic: null
  };
}

function createFrameResolver({ modelName, modelWorldTransform, links, frames, joints }) {
  const descriptors = new Map([
    [SDF_WORLD_FRAME, { name: SDF_WORLD_FRAME, kind: "world", worldTransform: [...IDENTITY_TRANSFORM] }],
    [SDF_MODEL_FRAME, { name: SDF_MODEL_FRAME, kind: "model", worldTransform: modelWorldTransform }]
  ]);
  const linkNames = new Set();

  const addDescriptor = (name, descriptor) => {
    if (descriptors.has(name)) {
      throw new Error(`Duplicate SDF frame/link/joint name: ${name}`);
    }
    descriptors.set(name, descriptor);
  };

  for (const link of links) {
    linkNames.add(link.name);
    addDescriptor(link.name, {
      name: link.name,
      kind: "link",
      pose: link.pose,
      defaultRelativeTo: SDF_MODEL_FRAME
    });
  }

  for (const frame of frames) {
    const attachedTo = normalizeSdfFrameName(frame.attachedTo, { modelName, defaultFrame: SDF_MODEL_FRAME });
    addDescriptor(frame.name, {
      name: frame.name,
      kind: "frame",
      pose: frame.pose,
      attachedTo,
      defaultRelativeTo: attachedTo
    });
  }

  for (const joint of joints) {
    addDescriptor(joint.name, {
      name: joint.name,
      kind: "joint",
      pose: joint.pose,
      childFrame: joint.childFrame,
      defaultRelativeTo: joint.childFrame
    });
  }

  const resolveFrameWorld = (rawFrameName, defaultFrame = SDF_MODEL_FRAME, resolving = new Set()) => {
    const frameName = normalizeSdfFrameName(rawFrameName, { modelName, defaultFrame });
    const descriptor = descriptors.get(frameName);
    if (!descriptor) {
      throw new Error(`SDF references unknown frame ${JSON.stringify(frameName)}`);
    }
    if (descriptor.worldTransform) {
      return descriptor.worldTransform;
    }
    if (resolving.has(frameName)) {
      throw new Error(`SDF frame graph contains a cycle at ${frameName}`);
    }
    resolving.add(frameName);
    const pose = descriptor.pose || {
      relativeTo: "",
      transform: [...IDENTITY_TRANSFORM]
    };
    const relativeFrame = normalizeSdfFrameName(pose.relativeTo, {
      modelName,
      defaultFrame: descriptor.defaultRelativeTo || SDF_MODEL_FRAME
    });
    const relativeWorldTransform = resolveFrameWorld(relativeFrame, SDF_MODEL_FRAME, resolving);
    const worldTransform = multiplyTransforms(relativeWorldTransform, pose.transform || IDENTITY_TRANSFORM);
    descriptor.worldTransform = worldTransform;
    resolving.delete(frameName);
    return worldTransform;
  };

  const resolveAttachedLink = (rawFrameName, resolving = new Set()) => {
    const frameName = normalizeSdfFrameName(rawFrameName, { modelName, defaultFrame: SDF_MODEL_FRAME });
    if (linkNames.has(frameName)) {
      return frameName;
    }
    if (frameName === SDF_MODEL_FRAME || frameName === SDF_WORLD_FRAME) {
      return "";
    }
    const descriptor = descriptors.get(frameName);
    if (!descriptor) {
      throw new Error(`SDF references unknown frame ${JSON.stringify(frameName)}`);
    }
    if (resolving.has(frameName)) {
      throw new Error(`SDF attached_to graph contains a cycle at ${frameName}`);
    }
    resolving.add(frameName);
    if (descriptor.kind === "frame") {
      return resolveAttachedLink(descriptor.attachedTo || SDF_MODEL_FRAME, resolving);
    }
    if (descriptor.kind === "joint") {
      return resolveAttachedLink(descriptor.childFrame, resolving);
    }
    return "";
  };

  return {
    descriptors,
    linkNames,
    resolveFrameWorld,
    resolveAttachedLink
  };
}

function finalizeMeshInstance(instance, { linkName, resolver, modelName }) {
  const linkWorldTransform = resolver.resolveFrameWorld(linkName);
  const pose = instance.pose || {
    relativeTo: "",
    transform: [...IDENTITY_TRANSFORM]
  };
  const poseFrame = normalizeSdfFrameName(pose.relativeTo, { modelName, defaultFrame: linkName });
  const poseWorldTransform = multiplyTransforms(resolver.resolveFrameWorld(poseFrame), pose.transform);
  const localPoseTransform = multiplyTransforms(invertRigidTransform(linkWorldTransform), poseWorldTransform);
  const { pose: _pose, scaleTransform: meshScaleTransform, ...meshInstance } = instance;
  return {
    ...meshInstance,
    localTransform: multiplyTransforms(localPoseTransform, meshScaleTransform || IDENTITY_TRANSFORM)
  };
}

function finalizeLinks(links, resolver, modelName) {
  return links.map((link) => ({
    name: link.name,
    visuals: link.visuals.map((visual) => finalizeMeshInstance(visual, { linkName: link.name, resolver, modelName })),
    collisions: link.collisions.map((collision) => finalizeMeshInstance(collision, { linkName: link.name, resolver, modelName }))
  }));
}

function buildNativeJoint(rawJoint, resolver, modelName) {
  const parentLink = resolver.resolveAttachedLink(rawJoint.parentFrame) || SDF_VIRTUAL_ROOT_LINK;
  const childLink = resolver.resolveAttachedLink(rawJoint.childFrame);
  if (!childLink) {
    throw new Error(`SDF joint ${rawJoint.name} child frame ${JSON.stringify(rawJoint.childFrame)} is not attached to a link`);
  }
  if (parentLink === childLink) {
    throw new Error(`SDF joint ${rawJoint.name} resolves parent and child to the same link ${childLink}`);
  }
  const parentLinkWorldTransform = parentLink === SDF_VIRTUAL_ROOT_LINK
    ? [...IDENTITY_TRANSFORM]
    : resolver.resolveFrameWorld(parentLink);
  const jointWorldTransform = resolver.resolveFrameWorld(rawJoint.name);
  const childLinkWorldTransform = resolver.resolveFrameWorld(childLink);
  const preMotionTransform = multiplyTransforms(invertRigidTransform(parentLinkWorldTransform), jointWorldTransform);
  const postMotionTransform = multiplyTransforms(invertRigidTransform(jointWorldTransform), childLinkWorldTransform);
  const axisFrame = normalizeSdfFrameName(rawJoint.axisExpressedIn, { modelName, defaultFrame: rawJoint.name });
  const axis = rawJoint.type === "fixed"
    ? [1, 0, 0]
    : normalizeAxisVector(transformDirectionBetweenFrames(
      rawJoint.axis,
      resolver.resolveFrameWorld(axisFrame),
      jointWorldTransform
    ));
  return {
    name: rawJoint.name,
    type: rawJoint.type,
    parentLink,
    childLink,
    originTransform: multiplyTransforms(preMotionTransform, postMotionTransform),
    preMotionTransform,
    postMotionTransform,
    axis,
    axisInJointFrame: axis,
    defaultValueDeg: rawJoint.defaultValueDeg,
    minValueDeg: rawJoint.minValueDeg,
    maxValueDeg: rawJoint.maxValueDeg,
    mimic: null,
    sdf: {
      parentFrame: rawJoint.parentFrame,
      childFrame: rawJoint.childFrame,
      jointFrame: rawJoint.name,
      axisExpressedIn: axisFrame
    }
  };
}

function buildVirtualRootJoint(linkName, resolver, index) {
  const linkWorldTransform = resolver.resolveFrameWorld(linkName);
  return {
    name: `${SDF_VIRTUAL_ROOT_LINK}_to_${linkName}_${index}`,
    type: "fixed",
    parentLink: SDF_VIRTUAL_ROOT_LINK,
    childLink: linkName,
    originTransform: linkWorldTransform,
    preMotionTransform: linkWorldTransform,
    postMotionTransform: [...IDENTITY_TRANSFORM],
    axis: [1, 0, 0],
    axisInJointFrame: [1, 0, 0],
    defaultValueDeg: 0,
    minValueDeg: 0,
    maxValueDeg: 0,
    mimic: null,
    sdf: {
      parentFrame: SDF_MODEL_FRAME,
      childFrame: linkName,
      jointFrame: `${SDF_VIRTUAL_ROOT_LINK}_to_${linkName}_${index}`,
      synthetic: true
    }
  };
}

function buildRootedSdfTree(links, joints, resolver) {
  const linkNames = new Set(links.map((link) => link.name));
  const childLinks = new Set(joints.map((joint) => joint.childLink));
  const rootCandidates = [...linkNames].filter((linkName) => !childLinks.has(linkName));
  const needsVirtualRoot = rootCandidates.length !== 1 || joints.some((joint) => joint.parentLink === SDF_VIRTUAL_ROOT_LINK);
  if (!needsVirtualRoot) {
    const rootLink = rootCandidates[0];
    return {
      links,
      joints,
      rootLink,
      rootWorldTransform: resolver.resolveFrameWorld(rootLink),
      syntheticRoot: false
    };
  }
  const rootJoints = rootCandidates.map((linkName, index) => buildVirtualRootJoint(linkName, resolver, index + 1));
  return {
    links: [
      {
        name: SDF_VIRTUAL_ROOT_LINK,
        visuals: [],
        collisions: [],
        synthetic: true
      },
      ...links
    ],
    joints: [...rootJoints, ...joints],
    rootLink: SDF_VIRTUAL_ROOT_LINK,
    rootWorldTransform: [...IDENTITY_TRANSFORM],
    syntheticRoot: true
  };
}

function validateTree(links, joints) {
  const linkNames = new Set(links.map((link) => link.name));
  const children = new Set();
  const jointsByParent = new Map();
  const jointNames = new Set();
  for (const joint of joints) {
    if (jointNames.has(joint.name)) {
      throw new Error(`Duplicate SDF joint name: ${joint.name}`);
    }
    jointNames.add(joint.name);
    if (children.has(joint.childLink)) {
      throw new Error(`SDF link ${joint.childLink} has multiple parents`);
    }
    children.add(joint.childLink);
    const current = jointsByParent.get(joint.parentLink) || [];
    current.push(joint.childLink);
    jointsByParent.set(joint.parentLink, current);
  }
  const rootCandidates = [...linkNames].filter((linkName) => !children.has(linkName));
  if (rootCandidates.length !== 1) {
    throw new Error(`SDF must form a single rooted joint tree; found roots ${JSON.stringify(rootCandidates)}`);
  }
  const rootLink = rootCandidates[0];
  const visited = new Set();
  const visiting = new Set();
  const visit = (linkName) => {
    if (visited.has(linkName)) {
      return;
    }
    if (visiting.has(linkName)) {
      throw new Error("SDF joint graph contains a cycle");
    }
    visiting.add(linkName);
    for (const childLink of jointsByParent.get(linkName) || []) {
      visit(childLink);
    }
    visiting.delete(linkName);
    visited.add(linkName);
  };
  visit(rootLink);
  if (visited.size !== links.length) {
    const missing = links.map((link) => link.name).filter((linkName) => !visited.has(linkName));
    throw new Error(`SDF leaves links disconnected from the root: ${JSON.stringify(missing)}`);
  }
  return rootLink;
}

function elementAttributeObject(element, names) {
  return Object.fromEntries(
    names.map((name) => [name, String(element?.getAttribute(name) || "").trim()])
      .filter(([, value]) => value)
  );
}

function parseIncludeMetadata(includeElement, index) {
  return {
    id: `include:${index + 1}`,
    uri: childText(includeElement, "uri"),
    name: childText(includeElement, "name")
  };
}

function parsePluginMetadata(pluginElement, index) {
  const name = pluginName(pluginElement);
  const filename = pluginFilename(pluginElement);
  return {
    id: `plugin:${index + 1}`,
    name,
    filename,
    customAnimation: filename === "cad-viewer-input-motion" || name === "cad_viewer_input_motion"
  };
}

function parseSensorMetadata(sensorElement, index) {
  return {
    id: `sensor:${index + 1}`,
    ...elementAttributeObject(sensorElement, ["name", "type"])
  };
}

function parseLightMetadata(lightElement, index) {
  return {
    id: `light:${index + 1}`,
    ...elementAttributeObject(lightElement, ["name", "type"])
  };
}

function parsePhysicsMetadata(physicsElement, index) {
  return {
    id: `physics:${index + 1}`,
    ...elementAttributeObject(physicsElement, ["name", "type", "default"])
  };
}

function collectSdfStaticMetadata(root) {
  const includes = descendantElementsByTag(root, "include").map(parseIncludeMetadata);
  const plugins = descendantElementsByTag(root, "plugin").map(parsePluginMetadata);
  const sensors = descendantElementsByTag(root, "sensor").map(parseSensorMetadata);
  const lights = descendantElementsByTag(root, "light").map(parseLightMetadata);
  const physics = descendantElementsByTag(root, "physics").map(parsePhysicsMetadata);
  const nestedModelCount = descendantElementsByTag(root, "model")
    .filter((modelElement) => modelElement.parentNode && elementName(modelElement.parentNode) === "model")
    .length;
  const warnings = [];
  if (includes.length) {
    warnings.push("SDF includes are listed as static metadata; CAD Viewer does not resolve external models.");
  }
  if (plugins.length) {
    warnings.push("SDF plugins are listed as static metadata; CAD Viewer does not execute simulator plugins.");
  }
  if (plugins.some((plugin) => plugin.customAnimation)) {
    warnings.push("CAD Viewer input-motion plugins are ignored; SDF rendering is static unless joints are posed manually.");
  }
  if (sensors.length) {
    warnings.push("SDF sensors are listed as static metadata; CAD Viewer does not simulate sensor output.");
  }
  if (lights.length) {
    warnings.push("SDF lights are listed as static metadata; CAD Viewer does not execute simulator lighting behavior.");
  }
  if (physics.length) {
    warnings.push("SDF physics settings are listed as static metadata; CAD Viewer does not run simulation physics.");
  }
  if (nestedModelCount) {
    warnings.push("Nested SDF models are listed as static metadata; CAD Viewer renders the selected model's direct links.");
  }
  return {
    includes,
    plugins,
    sensors,
    lights,
    physics,
    nestedModelCount,
    warnings
  };
}

function selectSdfRenderModel(sdfRoot) {
  const directModels = childElementsByTag(sdfRoot, "model");
  if (directModels.length === 1) {
    return {
      documentKind: "model",
      worldName: "",
      model: directModels[0]
    };
  }
  if (directModels.length > 1) {
    throw new Error("SDF rendering currently requires one direct <model>; multiple top-level models are listed only as metadata");
  }
  const worlds = childElementsByTag(sdfRoot, "world");
  if (worlds.length !== 1) {
    throw new Error("SDF rendering requires one direct <model> or one <world> containing one direct <model>");
  }
  const world = worlds[0];
  const worldModels = childElementsByTag(world, "model");
  if (worldModels.length !== 1) {
    throw new Error("SDF world rendering currently requires exactly one direct <model>");
  }
  return {
    documentKind: "world",
    worldName: String(world.getAttribute("name") || "").trim(),
    model: worldModels[0]
  };
}

export function parseSdf(xmlText, { sourceUrl } = {}) {
  if (typeof DOMParser === "undefined") {
    throw new Error("DOMParser is unavailable in this environment");
  }
  const document = new DOMParser().parseFromString(String(xmlText || ""), "application/xml");
  const parseError = document.querySelector("parsererror");
  if (parseError) {
    throw new Error("Failed to parse SDF XML");
  }
  const sdfRoot = document.documentElement;
  if (!sdfRoot || elementName(sdfRoot) !== "sdf") {
    throw new Error("SDF root element must be <sdf>");
  }
  const version = String(sdfRoot.getAttribute("version") || "").trim();
  if (!version) {
    throw new Error("SDF root element must declare a version");
  }
  const staticMetadata = collectSdfStaticMetadata(sdfRoot);
  const { documentKind, worldName, model } = selectSdfRenderModel(sdfRoot);
  const robotName = String(model.getAttribute("name") || "").trim();
  if (!robotName) {
    throw new Error("SDF model name is required");
  }
  const modelPose = parsePose(model, `SDF model ${robotName}`);
  const modelPoseFrame = normalizeSdfFrameName(modelPose.relativeTo, { modelName: robotName, defaultFrame: SDF_WORLD_FRAME });
  if (modelPoseFrame !== SDF_WORLD_FRAME) {
    throw new Error(`SDF model ${robotName} uses unsupported pose frame ${JSON.stringify(modelPose.relativeTo)}`);
  }
  const modelWorldTransform = modelPose.transform;

  const links = childElementsByTag(model, "link").map((linkElement) => parseLink(linkElement, sourceUrl));
  if (!links.length) {
    throw new Error("SDF model must define at least one link");
  }
  const unsupportedVisualCount = links.flatMap((link) => link.visuals).filter((visual) => visual.unsupportedGeometry).length;
  const unsupportedCollisionCount = links.flatMap((link) => link.collisions).filter((collision) => collision.unsupportedGeometry).length;
  const linkNames = new Set();
  for (const link of links) {
    if (linkNames.has(link.name)) {
      throw new Error(`Duplicate SDF link name: ${link.name}`);
    }
    linkNames.add(link.name);
  }

  const frames = childElementsByTag(model, "frame").map(parseFrame);
  const rawJoints = childElementsByTag(model, "joint").map((jointElement) => parseJoint(jointElement, {
    modelName: robotName
  }));
  const rawJointNames = new Set();
  for (const joint of rawJoints) {
    if (rawJointNames.has(joint.name)) {
      throw new Error(`Duplicate SDF joint name: ${joint.name}`);
    }
    rawJointNames.add(joint.name);
  }
  const resolver = createFrameResolver({
    modelName: robotName,
    modelWorldTransform,
    links,
    frames,
    joints: rawJoints
  });
  const resolvedLinks = finalizeLinks(links, resolver, robotName);
  const resolvedJoints = rawJoints.map((joint) => buildNativeJoint(joint, resolver, robotName));
  const rootedTree = buildRootedSdfTree(resolvedLinks, resolvedJoints, resolver);
  const rootLink = validateTree(rootedTree.links, rootedTree.joints);

  return {
    robotName,
    rootLink,
    rootWorldTransform: rootedTree.rootWorldTransform,
    links: rootedTree.links,
    joints: rootedTree.joints,
    motion: null,
    sourceFormat: "sdf",
    sdf: {
      version,
      documentKind,
      worldName,
      modelName: robotName,
      nativeFrameSemantics: true,
      syntheticRoot: rootedTree.syntheticRoot,
      frameCount: frames.length,
      linkCount: links.length,
      jointCount: rawJoints.length,
      rootLink,
      unsupportedVisualCount,
      unsupportedCollisionCount,
      staticMetadata
    },
    srdf: null
  };
}
