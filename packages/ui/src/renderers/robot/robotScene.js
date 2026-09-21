import { resolveCadEdgeSettings } from "@hardcore/core/common/cadInk.js";
import { jointMotionTransform, resolveUrdfJointValues } from "@hardcore/core/lib/urdf/kinematics.js";
import {
  PART_HOVER_EMISSIVE_INTENSITY, PART_HOVER_HIGHLIGHT_BLEND, PART_SELECTED_EMISSIVE_INTENSITY,
  PART_SELECTED_HIGHLIGHT_BLEND, partHighlightSurfaceColor, syncPartOcclusionGhost
} from "@hardcore/core/lib/viewer/partHighlight.js";
import { scheduleRuntimeRaycastBvh } from "@hardcore/core/lib/viewer/raycastBvh.js";
import { REFERENCE_HOVER_COLOR } from "@hardcore/core/lib/viewer/referenceGeometry.js";
import { createSurfaceLook } from "@hardcore/core/lib/viewer/surfaceLook.js";
import { shapeSourceColor } from "@hardcore/core/lib/viewer/surfaceMaterials.js";

// A robot as a SCENE GRAPH. One Group per link, a link's meshes attached to it once,
// and each joint as three nested frames of which a pose writes exactly one:
//
//   robot
//   └ link:<root>                 matrix = rootWorldTransform
//      ├ mesh (per part)          matrix = the visual's origin and mesh scale
//      └ joint:<name>             STATIC   parent link frame -> joint frame
//         └ motion:<name>         THE ONLY MATRIX A POSE WRITES
//            └ link:<child>       STATIC   an SDF joint's child offset, else identity
//
// So posing is k matrix writes (the joint and its mimic followers), and three's own
// world-matrix pass carries them down the tree. No geometry, material or part list is
// touched by a pose, and `motion:<name>.matrixWorld` IS the joint frame after its motion,
// which is what the Pose handles hang on.
//
// No React and no DOM in here: the description and the loaded part list in, a kit scene
// (`kit/scene.js`) out, with the robot's own verbs beside the contract.

const HIGHLIGHT_RENDER_ORDER = 23;
const POSE_EPSILON = 1e-9;
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
const hex = value => (HEX_COLOR.test(String(value || "").trim()) ? String(value).trim() : "");
const numeric = (values, stride) => Boolean(values) && typeof values.length === "number" && values.length > 0 && values.length % stride === 0;

// Core transforms are ROW-major; three's `set` takes row-major arguments (`fromArray` does not).
function place(object, transform) {
  if (Array.isArray(transform) && transform.length === 16) object.matrix.set(...transform);
  object.matrixAutoUpdate = false;
  object.matrixWorldNeedsUpdate = true;
}

function group(THREE, name, transform) {
  const object = new THREE.Group();
  object.name = name;
  place(object, transform);
  return object;
}

// One geometry per source mesh, shared by every visual that names it. The arrays are the
// loader's (or a named object's slice of them) and are wrapped, never copied; only a
// vertex-colour buffer is this scene's own, because the look grades it in place.
function partGeometry(THREE, part, wearsVertexColors) {
  const source = part.sourceMesh;
  if (!numeric(source?.vertices, 3) || !numeric(source?.indices, 3)) return null;
  const typed = (values, Type) => (values instanceof Type ? values : new Type(values));
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(typed(source.vertices, Float32Array), 3));
  geometry.setIndex(new THREE.BufferAttribute(typed(source.indices, Uint32Array), 1));
  if (numeric(source.normals, 3) && source.normals.length === source.vertices.length) {
    geometry.setAttribute("normal", new THREE.BufferAttribute(typed(source.normals, Float32Array), 3));
  } else geometry.computeVertexNormals();
  let sourceColors = null;
  if (wearsVertexColors && numeric(source.colors, 3) && source.colors.length === source.vertices.length) {
    sourceColors = typed(source.colors, Float32Array);
    geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(sourceColors), 3));
  }
  geometry.computeBoundingSphere();
  return { geometry, sourceColors };
}

function boxOf(bounds) {
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : [0, 0, 0];
  return [min, max];
}

/**
 * @param {typeof import("three")} THREE
 * @param {{ description: object, parts: object[] }} input  `description`: a parsed URDF or SDF (an SRDF's is its
 *   URDF's). `parts`: `buildRobotParts` — one per visual, or per named object of a visual's mesh.
 * @returns {import("../kit/scene.js").KitScene & object}  The contract, plus: `setJointValues(values)` (true when a
 *   matrix was written), `setHighlight({ hoveredLink, hoveredComponent, selectedLink, selectedComponents })`,
 *   `linkCentre(name)`, `motionFrame(jointName)`, `linkFrames()`, `hasComponent(id)`,
 *   and `stats` (test seam: matrix writes per pose).
 */
export function createRobotScene(THREE, { description, parts }) {
  const root = new THREE.Group();
  root.name = "robot";
  place(root, null);
  const joints = (Array.isArray(description?.joints) ? description.joints : []).filter(joint => String(joint?.name || ""));
  const links = new Map();
  const motions = new Map();
  const linkGroup = (name, transform) => {
    const object = group(THREE, `link:${name}`, transform);
    object.userData.linkName = name;
    links.set(name, object);
    return object;
  };

  // ---- the kinematic tree --------------------------------------------------------
  const jointsByParent = new Map();
  for (const joint of joints) {
    const parent = String(joint.parentLink || "");
    if (parent && String(joint.childLink || "")) jointsByParent.set(parent, [...(jointsByParent.get(parent) || []), joint]);
  }
  const rootLink = String(description?.rootLink || "");
  if (rootLink) {
    root.add(linkGroup(rootLink, description.rootWorldTransform));
    // Iterative, first claim wins: the parsers validate, and a description that still
    // holds a cycle or a second parent must never hang the builder.
    for (const queue = [rootLink]; queue.length;) {
      const parentName = queue.shift();
      for (const joint of jointsByParent.get(parentName) || []) {
        const childName = String(joint.childLink);
        if (links.has(childName)) continue;
        const frame = group(THREE, `joint:${joint.name}`, joint.preMotionTransform || joint.originTransform);
        const motion = group(THREE, `motion:${joint.name}`, null);
        motion.userData.jointName = joint.name;
        motions.set(joint.name, { joint, object: motion, value: null, meshes: [] });
        links.get(parentName).add(frame);
        frame.add(motion);
        motion.add(linkGroup(childName, joint.postMotionTransform || null));
        queue.push(childName);
      }
    }
  }

  // ---- link meshes, attached once ------------------------------------------------
  const geometries = new Map();
  const materials = [];
  const meshes = [];
  const meshesByLink = new Map();
  const recordByComponent = new Map();
  const recordByMesh = new Map();
  for (const part of Array.isArray(parts) ? parts : []) {
    const linkName = String(part?.linkName || "");
    if (!linkName) continue;
    // A link the tree never reached (no joint claims it) still shows, at the robot's origin.
    if (!links.has(linkName)) root.add(linkGroup(linkName, null));
    const owner = links.get(linkName);
    // Colour, in the order a robot description means it: the colour the description gives the
    // visual wins (as it does in the headless renderer); else the colours the mesh brought, per
    // vertex; else the named object's own; else the viewer's surface colour.
    const described = hex(part.descriptionColor);
    const wearsVertexColors = !described && Boolean(part.hasSourceColors);
    const key = `${String(part.sourceMeshKey || part.meshUrl || part.id)}:${wearsVertexColors ? "source-colors" : "flat"}`;
    if (!geometries.has(key)) geometries.set(key, partGeometry(THREE, part, wearsVertexColors));
    const entry = geometries.get(key);
    if (!entry) continue;
    const vertexColors = Boolean(entry.sourceColors);
    const authored = described || (vertexColors ? "" : hex(part.color));
    const material = new THREE.MeshPhysicalMaterial({ color: authored || 0xffffff, vertexColors, side: THREE.DoubleSide });
    material.userData.cadSourceColor = vertexColors || Boolean(authored);
    materials.push(material);
    const mesh = new THREE.Mesh(entry.geometry, material);
    mesh.name = String(part.id || "");
    mesh.castShadow = true;
    mesh.userData.partId = mesh.name;
    mesh.userData.linkName = String(part.linkName);
    if (part.componentName) mesh.userData.componentId = mesh.name;
    // Where "Color by part" deals this part its palette colour.
    if (Number.isInteger(part.fillIndex)) mesh.userData.cadFillIndex = part.fillIndex;
    place(mesh, part.localTransform);
    owner.add(mesh);
    const record = { mesh, sourceBounds: boxOf(part.sourceBounds || part.bounds), box: null, dirty: true, ghostRecord: null };
    meshes.push(record);
    recordByMesh.set(mesh, record);
    if (part.componentName) recordByComponent.set(mesh.name, record);
    meshesByLink.set(mesh.userData.linkName, [...(meshesByLink.get(mesh.userData.linkName) || []), record]);
  }
  // Every mesh a joint carries, so a pose marks exactly the boxes it moved.
  for (const motion of motions.values()) {
    motion.object.traverse((object) => { if (recordByMesh.has(object)) motion.meshes.push(recordByMesh.get(object)); });
  }

  // ---- bounds ----------------------------------------------------------------------
  const corner = new THREE.Vector3();
  const relative = new THREE.Matrix4();
  const rootInverse = new THREE.Matrix4();
  // A part's box where it is now, in the robot's own space: its source box's eight
  // corners through its world matrix (the method the description solver uses, so
  // framing numbers agree with it).
  function refreshBoxes(records) {
    let inverted = false;
    for (const record of records) {
      if (!record.dirty) continue;
      if (!inverted) { root.updateMatrixWorld(); rootInverse.copy(root.matrixWorld).invert(); inverted = true; }
      relative.multiplyMatrices(rootInverse, record.mesh.matrixWorld);
      const [low, high] = record.sourceBounds;
      const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      for (let index = 0; index < 8; index += 1) {
        corner.set(index & 4 ? high[0] : low[0], index & 2 ? high[1] : low[1], index & 1 ? high[2] : low[2]).applyMatrix4(relative);
        for (let axis = 0; axis < 3; axis += 1) {
          const value = corner.getComponent(axis);
          if (value < min[axis]) min[axis] = value;
          if (value > max[axis]) max[axis] = value;
        }
      }
      record.box = { min, max };
      record.dirty = false;
    }
  }
  function merged(records) {
    refreshBoxes(records);
    if (!records.length) return null;
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (const { box } of records) {
      for (let axis = 0; axis < 3; axis += 1) {
        if (box.min[axis] < min[axis]) min[axis] = box.min[axis];
        if (box.max[axis] > max[axis]) max[axis] = box.max[axis];
      }
    }
    return { min, max };
  }
  let boundsCache = null;

  // ---- pose ------------------------------------------------------------------------
  const stats = { poseWrites: 0, lastPoseWrites: 0 };
  function setJointValues(values) {
    const resolved = resolveUrdfJointValues(description, values || {});
    let written = 0;
    for (const [name, motion] of motions) {
      const value = resolved.get(name);
      if (motion.value !== null && Math.abs(value - motion.value) <= POSE_EPSILON) continue;
      motion.value = value;
      if (motion.joint.type === "fixed") continue;
      motion.object.matrix.set(...jointMotionTransform(motion.joint, value));
      motion.object.matrixWorldNeedsUpdate = true;
      for (const record of motion.meshes) record.dirty = true;
      written += 1;
    }
    stats.lastPoseWrites = written;
    stats.poseWrites += written;
    if (written) {
      boundsCache = null;
      root.updateMatrixWorld();
    }
    return written > 0;
  }
  // The rest placement is every joint at its declared default, whatever pose the file
  // opens in: it is what the camera frames and what sizes the ground.
  setJointValues({});
  root.updateMatrixWorld(true);
  const restBounds = merged(meshes) || { min: [0, 0, 0], max: [0, 0, 0] };
  boundsCache = restBounds;

  // ---- look and highlight ------------------------------------------------------------
  const look = createSurfaceLook(THREE, root);
  const gradedColor = new THREE.Color();
  let lastLook = null;
  let lastGrading = "";
  let highlight = { hoveredLink: "", hoveredComponent: "", selectedLink: "", selectedComponents: [] };
  const highlighted = new Set();
  // The viewer's highlight ink: a selection wears the colour a selected STEP part does.
  const hoverColor = new THREE.Color(REFERENCE_HOVER_COLOR);
  const selectedColor = new THREE.Color(resolveCadEdgeSettings().highlightColor);

  // Vertex colours take the same grading a material colour takes, so a link coloured
  // per vertex and one coloured by its description read as one robot.
  function gradeVertexColors(settings) {
    const grading = JSON.stringify([settings?.saturation, settings?.contrast, settings?.brightness, settings?.tintStrength, settings?.tintMode, settings?.defaultColor]);
    if (grading === lastGrading) return;
    lastGrading = grading;
    for (const entry of geometries.values()) {
      if (!entry?.sourceColors) continue;
      const attribute = entry.geometry.getAttribute("color");
      const source = entry.sourceColors;
      for (let index = 0; index + 2 < source.length; index += 3) {
        gradedColor.setRGB(Math.min(Math.max(source[index], 0), 1), Math.min(Math.max(source[index + 1], 0), 1), Math.min(Math.max(source[index + 2], 0), 1));
        const shaped = shapeSourceColor(THREE, gradedColor, settings || {});
        attribute.array[index] = shaped.r;
        attribute.array[index + 1] = shaped.g;
        attribute.array[index + 2] = shaped.b;
      }
      attribute.needsUpdate = true;
    }
  }

  function recordsFor(linkName, componentIds) {
    const records = linkName ? [...(meshesByLink.get(linkName) || [])] : [];
    for (const id of componentIds) if (recordByComponent.has(id)) records.push(recordByComponent.get(id));
    return records;
  }
  function paint(record, selected) {
    const material = record.mesh.material;
    const color = selected ? selectedColor : hoverColor;
    material.color.copy(partHighlightSurfaceColor(THREE, material.color, color, selected ? PART_SELECTED_HIGHLIGHT_BLEND : PART_HOVER_HIGHLIGHT_BLEND));
    if (material.emissive) {
      material.emissive.copy(color);
      material.emissiveIntensity = selected ? PART_SELECTED_EMISSIVE_INTENSITY : PART_HOVER_EMISSIVE_INTENSITY;
    }
    // A highlighted surface is drawn after its neighbours, opaque: the cue must not
    // depend on the surface opacity the Display tab set.
    if (!material.transparent) { material.transparent = true; material.needsUpdate = true; }
    material.opacity = 1;
    record.mesh.renderOrder = HIGHLIGHT_RENDER_ORDER;
    highlighted.add(record);
  }
  function applyHighlight() {
    // The look restores every base it owns; the rest of a highlight is undone here.
    for (const record of highlighted) {
      record.mesh.renderOrder = 0;
      syncPartOcclusionGhost(THREE, record.ghostRecord, { visible: false });
    }
    highlighted.clear();
    look.apply(lastLook);
    const selected = recordsFor(highlight.selectedLink, highlight.selectedComponents);
    // Selection outranks hover: hovering what is already picked must not weaken it.
    for (const record of recordsFor(highlight.hoveredLink, highlight.hoveredComponent ? [highlight.hoveredComponent] : [])) {
      if (!selected.includes(record)) paint(record, false);
    }
    for (const record of selected) {
      paint(record, true);
      // Only a SELECTED part shows through what hides it.
      record.ghostRecord ||= { mesh: record.mesh, geometry: record.mesh.geometry, partId: record.mesh.userData.partId, baseColor: selectedColor };
      syncPartOcclusionGhost(THREE, record.ghostRecord, { visible: true, color: selectedColor });
    }
  }

  // ---- pick --------------------------------------------------------------------------
  const raycaster = new THREE.Raycaster();
  const pickable = meshes.map(record => record.mesh);
  // A hover is a pick per frame, and a link mesh is tens of thousands of triangles: each
  // geometry gets its accelerator in idle time, the first time a ray reaches its bounds
  // (until then, and for a mesh too large for one, the ray is tested the plain way).
  scheduleRuntimeRaycastBvh({ displayRecords: meshes }, { deferUntilRaycast: true });

  let disposed = false;
  return {
    object3D: root,
    get bounds() { return (boundsCache ||= merged(meshes) || restBounds); },
    restBounds,
    links,
    stats,
    partCount: meshes.length,
    // A robot authors no finish: Render is the studio's surface over the same colours.
    setSurfaceLook(next) {
      if (disposed) return;
      lastLook = next ? { ...next, authored: false } : null;
      gradeVertexColors(next?.materialSettings);
      applyHighlight();
    },
    setJointValues(values) { return disposed ? false : setJointValues(values); },
    /** The value each joint is posed at now (mimic followers included). */
    jointValue(name) { return motions.get(name)?.value ?? null; },
    /** A joint's frame AFTER its motion, relative to the robot: `THREE.Matrix4`, or null for a joint off the tree. */
    motionFrame(name) {
      const motion = motions.get(name);
      if (!motion) return null;
      root.updateMatrixWorld();
      return new THREE.Matrix4().copy(root.matrixWorld).invert().multiply(motion.object.matrixWorld);
    },
    /** Every link's frame relative to the robot, row-major like the description solver's. */
    linkFrames() {
      root.updateMatrixWorld();
      const inverse = new THREE.Matrix4().copy(root.matrixWorld).invert();
      return new Map([...links].map(([name, object]) => [name, new THREE.Matrix4().multiplyMatrices(inverse, object.matrixWorld).transpose().toArray()]));
    },
    /** The centre of a link's geometry in the LINK's frame, or null for a frame-only link. */
    linkCentre(name) {
      const records = meshesByLink.get(name) || [];
      if (!records.length) return null;
      const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      for (const record of records) {
        const [low, high] = record.sourceBounds;
        for (let index = 0; index < 8; index += 1) {
          corner.set(index & 4 ? high[0] : low[0], index & 2 ? high[1] : low[1], index & 1 ? high[2] : low[2]).applyMatrix4(record.mesh.matrix);
          for (let axis = 0; axis < 3; axis += 1) {
            min[axis] = Math.min(min[axis], corner.getComponent(axis));
            max[axis] = Math.max(max[axis], corner.getComponent(axis));
          }
        }
      }
      return [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
    },
    hasComponent(id) { return recordByComponent.has(id); },
    setHighlight(next) {
      if (disposed) return;
      highlight = { hoveredLink: "", hoveredComponent: "", selectedLink: "", selectedComponents: [], ...next };
      applyHighlight();
    },
    // The first surface under the ray: a named object is itself, anything else is its
    // link, found by walking up the graph. No part table.
    pick(ray) {
      if (disposed) return null;
      root.updateMatrixWorld();
      raycaster.ray.copy(ray);
      const hit = raycaster.intersectObjects(pickable, false).find(candidate => candidate.object.visible);
      if (!hit) return null;
      const componentId = hit.object.userData.componentId || "";
      let owner = hit.object;
      while (owner && !(owner.isGroup && owner.userData.linkName)) owner = owner.parent;
      const linkName = owner?.userData.linkName || "";
      return { id: componentId || `link:${linkName}`, kind: componentId ? "component" : "link", linkName, componentId, point: hit.point };
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      for (const record of meshes) {
        record.ghostRecord?.ghostMesh?.removeFromParent();
        record.ghostRecord?.ghostMaterial?.dispose();
      }
      look.dispose();
      for (const material of materials) material.dispose();
      for (const entry of geometries.values()) entry?.geometry.dispose();
    }
  };
}
