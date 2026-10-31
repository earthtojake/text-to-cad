import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";
import { scheduleRuntimeRaycastBvh } from "../viewer/raycastBvh.js";
import { createSceneExplode } from "../viewer/sceneExplode.js";
import { createSceneHighlight } from "../viewer/sceneHighlight.js";
import { GLB_SCENE_UNITS } from "../viewer/sceneUnits.js";
import { createSurfaceLook } from "../viewer/surfaceLook.js";
import { disposeGlbDocument } from "./glbMeshData.js";
import { releaseGeometry, shareGeometry } from "./sharedGeometry.js";

// Every mesh's materials as the file authored them, before any look touches them: what a sibling
// starts from (`createSibling`).
function materialList(object) {
  return Array.isArray(object.material) ? object.material : [object.material];
}
function copyMaterial(material) {
  // Material.copy deep-copies userData through JSON; glTF extras survive that, a viewer's own may not.
  const userData = material.userData;
  material.userData = {};
  try {
    const copy = material.clone();
    copy.userData = { ...userData };
    return copy;
  } finally {
    material.userData = userData;
  }
}

// The glTF node an object belongs to: itself, else the nearest of its parents that is one
// (`glbMeshData.js` marks them). A mesh of several primitives is its node's.
function owningNode(object) {
  for (let current = object; current; current = current.parent) {
    if (Number.isInteger(current.userData?.gltfNode)) return current;
  }
  return null;
}

// Drawn where its geometry says: a skin or morph targets move the vertices away from it.
const deformed = mesh => Boolean(mesh.isSkinnedMesh || mesh.morphTargetInfluences?.length);

/** A node as Quick Edit names it: its authored name (GLTFLoader keeps it in `userData.name`), else its index. */
export function glbNodeName(object) {
  return String(object?.userData?.name || object?.name || "").trim() || `Node ${object?.userData?.gltfNode}`;
}

function boundsOf(THREE, root) {
  root.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(root, true);
  if (box.isEmpty()) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min: box.min.toArray(), max: box.max.toArray() };
}

/**
 * A GLB's scene (`../viewer/sceneContract.js`): the file's NATIVE glTF hierarchy,
 * always. Nodes, skins, morph targets and authored materials are the file's own;
 * the scene places them in CAD space, wears the look its host resolves, and owns
 * the document from here on (`dispose()` releases its geometry, materials and
 * textures). The ONE builder of a GLB's scene: the viewer's GLB renderer and the
 * parity page's headless stage both call it, so neither can draw a GLB the other
 * does not.
 *
 * @param {typeof import("three")} THREE
 * @param {{ scene: import("three").Object3D, clips: object[], cadRootMatrix: number[],
 *   animatedBounds: object | null, restBounds: object | null }} document  `buildGlbDocumentFromBuffer`.
 * @returns {import("../viewer/sceneContract.js").KitScene & { document: object, meshCount: number }}
 */
export function createGlbScene(THREE, document, { sibling = false } = {}) {
  const root = new THREE.Group();
  root.name = "glb-document";
  root.matrix.fromArray(document.cadRootMatrix);
  root.matrixAutoUpdate = false;
  root.matrixWorldNeedsUpdate = true;
  root.add(document.scene);
  document.scene.traverse((object) => {
    // The viewer owns one lighting rig in both Inspect and Render. Keep the authored
    // hierarchy, but never let embedded punctual lights build a second, file-specific one.
    if (object.isLight) { object.visible = false; return; }
    if (!object.isMesh) return;
    object.castShadow = true;
    // Three caches local culling bounds. Bone deformation and morph displacement
    // leave the rest-pose box while the hierarchy and the framing box stay correct.
    if (object.isSkinnedMesh || object.morphTargetInfluences?.length) object.frustumCulled = false;
  });
  // A sibling opens at the file's authored pose, even while this scene holds a routine's
  // frame or an explosion. Keep values for every node (bones included), before either can
  // write them; clip time zero need not be the authored pose.
  const authoredPose = new Map();
  document.scene.traverse(object => authoredPose.set(object, {
    position: object.position.toArray(), quaternion: object.quaternion.toArray(), scale: object.scale.toArray(),
    matrix: object.matrix.toArray(), matrixAutoUpdate: object.matrixAutoUpdate,
    morphs: object.morphTargetInfluences?.slice() || null, visible: object.visible, renderOrder: object.renderOrder
  }));
  // The authored materials, kept apart from the ones this scene's look will dress, for a sibling.
  const authored = new Map();
  document.scene.traverse((object) => {
    if (object.isMesh) authored.set(object, materialList(object).map(material => material && copyMaterial(material)));
  });
  const look = createSurfaceLook(THREE, document.scene);
  const ink = createSceneHighlight(THREE, look);
  // One box for framing, lighting and the floor: a routine poses the model inside
  // the box sampled over every clip at load, so playing one never re-frames it.
  const bounds = document.animatedBounds || document.restBounds || boundsOf(THREE, root);

  // ---- its nodes: what Select picks, Quick Edit names and Explode moves ------------------
  // A node here is one that draws: the node a mesh belongs to. Its meshes are its own, not those of
  // the nodes under it.
  const meshes = [];
  const nodes = new Map();
  document.scene.traverse((object) => {
    if (!object.isMesh) return;
    const node = owningNode(object);
    meshes.push({ mesh: object, node });
    if (!node) return;
    const index = node.userData.gltfNode;
    // What Annotate hangs a mark on, here and in a snapshot (`annotation.js`): the node that draws it.
    object.userData.partId = `n${index}`;
    if (!nodes.has(index)) nodes.set(index, { index, object: node, meshes: [] });
    nodes.get(index).meshes.push(object);
  });
  const recordsOf = new Map(meshes.map(record => [record.mesh, record]));
  // A name several nodes share (an exporter's habit) is told apart by the node's id.
  const nameCounts = new Map();
  for (const node of nodes.values()) nameCounts.set(glbNodeName(node.object), (nameCounts.get(glbNodeName(node.object)) || 0) + 1);
  const nodeName = node => { const name = glbNodeName(node.object); return nameCounts.get(name) > 1 ? `${name} (n${node.index})` : name; };
  // A node and what is under it: selecting a node lights all it draws.
  const drawnUnder = (index) => {
    const node = nodes.get(index);
    const records = [];
    node?.object.traverse((object) => { if (object.isMesh && recordsOf.has(object)) records.push(recordsOf.get(object)); });
    return records;
  };
  const pickable = meshes.filter(record => record.node).map(record => record.mesh);
  // A hover is a pick per frame: each rigid geometry gets its accelerator in idle time, the first
  // time a ray reaches its bounds. A deformed one is tested the plain way, where it is drawn.
  scheduleRuntimeRaycastBvh({ displayRecords: meshes.filter(record => !deformed(record.mesh)) }, { deferUntilRaycast: true });
  const raycaster = new THREE.Raycaster();
  let lastLook = null;
  let clipPlanes = [];
  let highlight = { hovered: [], selected: [] };
  const applyHighlight = () => ink.apply(lastLook, {
    hovered: highlight.hovered.flatMap(drawnUnder), selected: highlight.selected.flatMap(drawnUnder)
  }, clipPlanes);
  // A node as a pick and a reference name it: `n12`, the file's `nodes[12]`.
  const nodeOf = id => { const match = /^n(\d+)$/.exec(String(id || "")); return match && nodes.has(Number(match[1])) ? Number(match[1]) : null; };
  const triangles = mesh => {
    const count = mesh.geometry?.index ? mesh.geometry.index.count : mesh.geometry?.getAttribute?.("position")?.count || 0;
    return Math.floor(count / 3);
  };

  // Explode moves the nodes that draw, rigid ones only, by the file's tree (`sceneExplode.js`).
  const explode = sibling ? null : createSceneExplode(THREE, root, [...nodes.values()]
    .filter(node => node.meshes.some(mesh => !deformed(mesh)) && node.object.userData.gltfNodePath)
    .sort((left, right) => left.object.userData.gltfNodePath.localeCompare(right.object.userData.gltfNodePath, "en", { numeric: true }))
    .map(node => ({ object: node.object, path: `o${node.object.userData.gltfNodePath}`, meshes: node.meshes })), bounds);
  let explodedBounds = null;
  let explodeAmount = 0;
  let disposed = false;
  return {
    document,
    meshCount: look.meshCount,
    keepsAuthoredFinish: [...authored.values()].some(list => list.some(material => material?.userData?.cadAuthoredFinish === true)),
    object3D: root,
    get bounds() { return explodedBounds || bounds; },
    restBounds: bounds,
    // glTF is metres; the scene draws them as millimetres.
    units: GLB_SCENE_UNITS,
    /** How many parts Explode moves apart: none for a GLB of one part (or of one skinned body). */
    explodeParts: explode?.parts || 0,
    /** Explode's amount (0..1); true when it moved anything. */
    setExplode(amount) {
      if (disposed || !explode?.parts) return false;
      const value = Math.min(Math.max(Number(amount) || 0, 0), 1);
      if (value === explodeAmount) return false;
      explodeAmount = value;
      explodedBounds = value > 0 ? explode.set(value) : (explode.set(0), null);
      return true;
    },
    /** Put the parts back where Explode has them, after something else moved them (a routine let go). */
    syncExplode() { if (!disposed && explodeAmount > 0) explode.set(explodeAmount); },
    setSurfaceLook(next) { if (disposed) return; lastLook = next; applyHighlight(); },
    setClipPlanes(planes) {
      if (disposed) return;
      clipPlanes = Array.isArray(planes) ? planes : [];
      look.setClipPlanes(clipPlanes);
    },
    /** Whether `id` (`n12`) is a node of this file that draws. */
    hasPart: id => nodeOf(id) !== null,
    /** A node, as Quick Edit's chip says it: its name, and what the file says of it. */
    describePart(id) {
      const index = nodeOf(id);
      if (index === null) return null;
      const node = nodes.get(index);
      const occurrence = String(node.object.userData?.cadOccurrenceId || "").trim();
      return { name: nodeName(node), facts: [
        { label: "Node", key: "part.node", value: `nodes[${index}]` },
        { label: "Triangles", key: "part.triangles", value: node.meshes.reduce((sum, mesh) => sum + triangles(mesh), 0).toLocaleString("en-US") },
        ...(occurrence ? [{ label: "STEP occurrence", key: "part.stepOccurrence", value: occurrence }] : [])
      ] };
    },
    /** Light what nodes draw: `hovered` and `selected` are nodes as a pick names them (`n12`). */
    setHighlight({ hovered = [], selected = [] } = {}) {
      if (disposed) return;
      const indices = ids => ids.map(nodeOf).filter(index => index !== null);
      highlight = { hovered: indices(hovered), selected: indices(selected) };
      applyHighlight();
    },
    // The first surface under the ray, as the node that draws it, and the point it hit there.
    pick(ray) {
      if (disposed) return null;
      root.updateMatrixWorld();
      raycaster.ray.copy(ray);
      // The first surface Clip has not cut away.
      const hit = raycaster.intersectObjects(pickable, false)
        .find(candidate => candidate.object.visible && clipPlanes.every(plane => plane.distanceToPoint(candidate.point) >= 0));
      const node = hit ? owningNode(hit.object) : null;
      if (!node) return null;
      const index = node.userData.gltfNode;
      return { id: `n${index}`, node: index, name: nodeName(nodes.get(index)), point: hit.point.toArray() };
    },
    /**
     * A second scene of the same document (the viewer's Preview beside its editor): its own copy of
     * the hierarchy (skins rebound to its own bones), its own materials as the file authored them,
     * and its own look, over this scene's geometry and textures (`sharedGeometry.js`). Its
     * `document` is the same document around its own copy, so a routine plays on it alone. This
     * scene stays the owner of the geometry and textures, so the sibling is disposed first.
     */
    createSibling() {
      const copy = cloneSkinned(document.scene);
      // Pair the current source and clone hierarchies first. Runtime overlays can have
      // appeared since the baseline; remove their copies without shifting authored nodes.
      const sources = [], copies = [];
      document.scene.traverse(object => sources.push(object));
      copy.traverse(object => copies.push(object));
      sources.forEach((source, index) => {
        const object = copies[index], pose = authoredPose.get(source);
        if (!pose) { object.removeFromParent(); return; }
        object.position.fromArray(pose.position);
        object.quaternion.fromArray(pose.quaternion);
        object.scale.fromArray(pose.scale);
        object.matrix.fromArray(pose.matrix);
        object.matrixAutoUpdate = pose.matrixAutoUpdate;
        object.matrixWorldNeedsUpdate = true;
        object.visible = pose.visible;
        object.renderOrder = pose.renderOrder;
        if (pose.morphs) object.morphTargetInfluences = pose.morphs.slice();
        if (!object.isMesh) return;
        object.geometry = shareGeometry(THREE, source.geometry);
        const materials = (authored.get(source) || materialList(source)).map(material => material && copyMaterial(material));
        object.material = Array.isArray(source.material) ? materials : materials[0];
      });
      copy.updateMatrixWorld(true);
      return createGlbScene(THREE, { ...document, scene: copy }, { sibling: true });
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      ink.dispose();
      look.dispose();
      for (const list of authored.values()) for (const material of list) material?.dispose();
      if (!sibling) { disposeGlbDocument(document); return; }
      // A sibling owns its copy's materials and its share of the geometry; textures and buffers
      // are its source's.
      document.scene.traverse((object) => {
        if (!object.isMesh) return;
        releaseGeometry(object.geometry);
        for (const material of materialList(object)) material?.dispose();
      });
    }
  };
}
