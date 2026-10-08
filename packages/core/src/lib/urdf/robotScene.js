import { resolveCadEdgeSettings } from "../../common/cadInk.js";
import { jointMotionMatrix, jointValues, normalizeControlValues } from "../../common/articulation.js";
import {
  PART_HOVER_EMISSIVE_INTENSITY, PART_HOVER_HIGHLIGHT_BLEND, PART_SELECTED_EMISSIVE_INTENSITY,
  PART_SELECTED_HIGHLIGHT_BLEND, partHighlightSurfaceColor, syncPartOcclusionGhost
} from "../viewer/partHighlight.js";
import { scheduleRuntimeRaycastBvh } from "../viewer/raycastBvh.js";
import { REFERENCE_HOVER_COLOR } from "../viewer/referenceGeometry.js";
import { createSurfaceLook } from "../viewer/surfaceLook.js";
import { shapeSourceColor } from "../viewer/surfaceMaterials.js";

// A robot as a SCENE GRAPH, played from the payload cadgen resolved (`cadgen.robot_payload`):
// the articulation (joints in rest space with affine rows over the controls, and which link
// each joint carries) and the visual list (each mesh at its rest placement). One node per
// joint, nested under its parent joint's, whose matrix is the joint's own motion in rest
// space; a link's meshes sit under the joint that carries the link, at their rest
// placements, and a link no joint carries sits under the root:
//
//   robot
//   ├ mesh (a root link's part)      matrix = the visual's rest placement
//   └ joint:<id>                     THE ONLY MATRIX A POSE WRITES: D(axis, q) in rest space
//      ├ mesh (a carried link's part) matrix = the visual's rest placement
//      └ joint:<child id>            the child joint, carried
//
// So posing is k matrix writes (the joints whose rows changed: a joint and its mimic
// followers), and three's own world-matrix pass carries them down the tree: a joint node's
// `matrixWorld` IS the joint's world delta (`articulation.jointDeltas`), which is what the
// Position handles hang on. No geometry, material or part list is touched by a pose. The
// scene decides nothing: the rows, the limits, the carries and the placements are the
// payload's, and a control vector is normalized against the articulation as every player
// normalizes one.
//
// No React and no DOM in here: the payload and the loaded part list in, a scene
// (`../viewer/sceneContract.js`) out, with the robot's own verbs beside the contract. The
// ONE builder of a robot's scene: the viewer's robot renderer and the snapshot CLI's
// headless stage both call it, and both pose it the one way it poses (`setControlValues`).

const HIGHLIGHT_RENDER_ORDER = 23;
const POSE_EPSILON = 1e-9;
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
const hex = value => (HEX_COLOR.test(String(value || "").trim()) ? String(value).trim() : "");
const numeric = (values, stride) => Boolean(values) && typeof values.length === "number" && values.length > 0 && values.length % stride === 0;

// Payload placements are ROW-major; three's `set` takes row-major arguments (`fromArray` does not).
function place(object, transform) {
  if (Array.isArray(transform) && transform.length === 16) object.matrix.set(...transform);
  object.matrixAutoUpdate = false;
  object.matrixWorldNeedsUpdate = true;
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
 * @param {{ robot: object, parts: object[] }} input  `robot`: the payload cadgen resolved (its `articulation`,
 *   `links` and `visuals`). `parts`: `buildRobotParts` — one per visual, or per named object of a visual's mesh.
 * @returns {import("../viewer/sceneContract.js").KitScene & object}  The contract, plus: `setControlValues(values)`
 *   (true when a matrix was written), `setHighlight({ hoveredLink, hoveredComponent, selectedLinks, selectedComponents })`,
 *   `jointRow(id)`, `motionFrame(jointId)`, `linkFrames()`, `linkCentre(name)`, `hasComponent(id)`,
 *   and `stats` (test seam: matrix writes per pose).
 */
export function createRobotScene(THREE, { robot, parts }) {
  const articulation = robot?.articulation || null;
  const root = new THREE.Group();
  root.name = "robot";
  place(root, null);

  // ---- the kinematic tree: one node per joint, parents first ----------------------------
  const nodes = new Map();
  const carrier = new Map();  // link name -> the joint node that carries it
  for (const joint of Array.isArray(articulation?.joints) ? articulation.joints : []) {
    if (!joint?.id || nodes.has(joint.id)) continue;
    const node = new THREE.Group();
    node.name = `joint:${joint.id}`;
    node.userData.jointId = joint.id;
    place(node, null);
    nodes.set(joint.id, { joint, object: node, parent: nodes.get(joint.parent) || null, turn: 0, travel: 0, meshes: [] });
    for (const link of Array.isArray(articulation?.carries?.[joint.id]) ? articulation.carries[joint.id] : []) {
      carrier.set(String(link), nodes.get(joint.id));
    }
  }
  const restPlacement = new Map((Array.isArray(robot?.links) ? robot.links : []).map(link => [String(link?.name || ""), link?.placement]));

  // ---- link meshes, attached once, at their rest placements ----------------------------
  const geometries = new Map();
  const materials = [];
  const meshes = [];
  const meshesByLink = new Map();
  const recordByComponent = new Map();
  for (const part of Array.isArray(parts) ? parts : []) {
    const linkName = String(part?.link || "");
    if (!linkName) continue;
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
    // The part's display name, where a GLB keeps a node's authored one (a snapshot lists it).
    mesh.userData.name = String(part.name || "");
    mesh.userData.linkName = linkName;
    if (part.componentName) mesh.userData.componentId = mesh.name;
    // Where "Color by part" deals this part its palette colour.
    if (Number.isInteger(part.fillIndex)) mesh.userData.cadFillIndex = part.fillIndex;
    place(mesh, part.placement);
    const owner = carrier.get(linkName);
    (owner?.object || root).add(mesh);
    const record = { mesh, sourceBounds: boxOf(part.sourceBounds || part.bounds), box: null, dirty: true, ghostRecord: null };
    meshes.push(record);
    if (part.componentName) recordByComponent.set(mesh.name, record);
    meshesByLink.set(linkName, [...(meshesByLink.get(linkName) || []), record]);
  }
  // A joint's node joins its parent AFTER that parent's own meshes, so the graph reads in tree
  // order, root first: a link, what it draws, then the links it carries. That is the order
  // `--mode list` lists a robot in.
  for (const node of nodes.values()) (node.parent?.object || root).add(node.object);
  // Every mesh a joint carries, down its subtree, so a pose marks exactly the boxes it moved.
  const recordByMesh = new Map(meshes.map(record => [record.mesh, record]));
  for (const node of nodes.values()) {
    node.object.traverse((object) => { const record = recordByMesh.get(object); if (record) node.meshes.push(record); });
  }

  // ---- bounds ----------------------------------------------------------------------
  const corner = new THREE.Vector3();
  const relative = new THREE.Matrix4();
  const rootInverse = new THREE.Matrix4();
  // A part's box where it is now, in the robot's own space: its source box's eight
  // corners through its world matrix.
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
  function setControlValues(values) {
    const rows = jointValues(articulation, normalizeControlValues(articulation, values));
    let written = 0;
    for (const [id, node] of nodes) {
      const row = rows[id] || { turn: 0, travel: 0 };
      if (Math.abs(row.turn - node.turn) <= POSE_EPSILON && Math.abs(row.travel - node.travel) <= POSE_EPSILON) continue;
      node.turn = row.turn;
      node.travel = row.travel;
      if (node.joint.kind === "fixed" || !Array.isArray(node.joint.axis)) continue;
      jointMotionMatrix(THREE, node.joint, row.turn, row.travel, node.object.matrix);
      node.object.matrixWorldNeedsUpdate = true;
      for (const record of node.meshes) record.dirty = true;
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
  // The rest placement is the robot as written (every row at zero), whatever pose the file
  // opens in: it is what the camera frames and what sizes the ground.
  root.updateMatrixWorld(true);
  const restBounds = merged(meshes) || { min: [0, 0, 0], max: [0, 0, 0] };
  boundsCache = restBounds;

  // ---- look and highlight ------------------------------------------------------------
  const look = createSurfaceLook(THREE, root);
  const gradedColor = new THREE.Color();
  let lastLook = null;
  let lastGrading = "";
  let highlight = { hoveredLink: "", hoveredComponent: "", selectedLinks: [], selectedComponents: [] };
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

  function recordsFor(linkNames, componentIds) {
    const records = [linkNames].flat().flatMap(linkName => (linkName ? meshesByLink.get(linkName) || [] : []));
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
    const selected = recordsFor(highlight.selectedLinks, highlight.selectedComponents);
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

  const rootInverseFrame = () => { root.updateMatrixWorld(); return new THREE.Matrix4().copy(root.matrixWorld).invert(); };
  let disposed = false;
  return {
    object3D: root,
    get bounds() { return (boundsCache ||= merged(meshes) || restBounds); },
    restBounds,
    stats,
    partCount: meshes.length,
    // A robot authors no finish: Render is the studio's surface over the same colours.
    setSurfaceLook(next) {
      if (disposed) return;
      lastLook = next ? { ...next, authored: false } : null;
      gradeVertexColors(next?.materialSettings);
      applyHighlight();
    },
    /** Pose the robot at a control vector (every control the vector does not name at its opening value). */
    setControlValues(values) { return disposed ? false : setControlValues(values); },
    /** The row a joint is posed at now: `{ turn, travel }`, or null for a joint the articulation does not have. */
    jointRow(id) { const node = nodes.get(id); return node ? { turn: node.turn, travel: node.travel } : null; },
    /** A joint's world delta now (its frame after its motion, and its parents'), relative to the robot: `THREE.Matrix4`, or null. */
    motionFrame(id) {
      const node = nodes.get(id);
      if (!node) return null;
      return rootInverseFrame().multiply(node.object.matrixWorld);
    },
    /** Every link's frame relative to the robot, row-major: its carrying joint's delta over its rest placement. */
    linkFrames() {
      const inverse = rootInverseFrame();
      return new Map([...restPlacement].map(([name, placement]) => {
        const frame = new THREE.Matrix4();
        if (Array.isArray(placement) && placement.length === 16) frame.set(...placement);
        const node = carrier.get(name);
        if (node) frame.premultiply(node.object.matrixWorld);
        return [name, frame.premultiply(inverse).transpose().toArray()];
      }));
    },
    /** The centre of a link's geometry in the ROBOT's rest space, or null for a frame-only link. */
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
      highlight = { hoveredLink: "", hoveredComponent: "", selectedLinks: [], selectedComponents: [], ...next };
      applyHighlight();
    },
    // The first surface under the ray: a named object is itself, anything else is its link.
    pick(ray) {
      if (disposed) return null;
      root.updateMatrixWorld();
      raycaster.ray.copy(ray);
      const hit = raycaster.intersectObjects(pickable, false).find(candidate => candidate.object.visible);
      if (!hit) return null;
      const componentId = hit.object.userData.componentId || "";
      const linkName = hit.object.userData.linkName || "";
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
