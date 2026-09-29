import { resolveCadEdgeSettings } from "../../common/cadInk.js";
import {
  PART_HOVER_EMISSIVE_INTENSITY, PART_HOVER_HIGHLIGHT_BLEND, PART_SELECTED_EMISSIVE_INTENSITY,
  PART_SELECTED_HIGHLIGHT_BLEND, partHighlightSurfaceColor
} from "../viewer/partHighlight.js";
import { scheduleRuntimeRaycastBvh } from "../viewer/raycastBvh.js";
import { REFERENCE_HOVER_COLOR } from "../viewer/referenceGeometry.js";
import { createSurfaceLook } from "../viewer/surfaceLook.js";
import { disposeGlbDocument } from "./glbMeshData.js";

const HIGHLIGHT_RENDER_ORDER = 23;

function boundsOf(THREE, root) {
  root.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(root, true);
  if (box.isEmpty()) return { min: [0, 0, 0], max: [0, 0, 0] };
  return { min: box.min.toArray(), max: box.max.toArray() };
}

/** The nearest node at or above `object` that an implicit part wrote as a leaf, else null. */
function implicitLeafNodeOf(object) {
  let node = object;
  while (node) {
    if (node.userData && node.userData.implicitLeaf !== undefined && node.userData.implicitLeaf !== null) return node;
    node = node.parent;
  }
  return null;
}

/**
 * The leaves an implicit part's GLB names: one per glTF node carrying `implicitLeaf`
 * extras (`cadgen implicit` writes one node per primitive in the author's code), in
 * file order, each with the meshes that draw it. Empty for every other GLB.
 */
function collectImplicitLeaves(scene) {
  const byNode = new Map();
  scene.traverse((object) => {
    if (!object.isMesh) return;
    const node = implicitLeafNodeOf(object);
    if (!node) return;
    if (!byNode.has(node)) {
      const extras = node.userData;
      const leaf = Number(extras.implicitLeaf);
      byNode.set(node, {
        id: String(extras.cadOccurrenceId || `implicit:${leaf}`),
        leaf,
        label: String(extras.implicitLabel || node.name || `${extras.implicitKind || "leaf"} ${leaf + 1}`),
        kind: String(extras.implicitKind || ""),
        site: String(extras.implicitSite || ""),
        triangles: Number(extras.implicitTriangles) || 0,
        meshes: []
      });
    }
    byNode.get(node).meshes.push(object);
  });
  return [...byNode.values()].sort((a, b) => a.leaf - b.leaf);
}

/**
 * A GLB's scene (`../viewer/sceneContract.js`): the file's NATIVE glTF hierarchy,
 * always. Nodes, skins, morph targets and authored materials are the file's own;
 * the scene places them in CAD space, wears the look its host resolves, and owns
 * the document from here on (`dispose()` releases its geometry, materials and
 * textures). The ONE builder of a GLB's scene: the viewer's GLB renderer and the
 * snapshot CLI's headless stage both call it, so neither can draw a GLB the other
 * does not.
 *
 * A GLB an implicit part wrote names its LEAVES (one node per primitive in the
 * author's code, with the source line that made it), and only such a GLB selects:
 * `leaves` lists them, `pick(ray)` answers with the leaf under a ray, and
 * `setHighlight` paints hover and selection the way the robot scene does. A GLB with
 * no leaves has no `pick`, so it is shown as before: nothing to select.
 *
 * @param {typeof import("three")} THREE
 * @param {{ scene: import("three").Object3D, clips: object[], cadRootMatrix: number[],
 *   animatedBounds: object | null, restBounds: object | null }} document  `buildGlbDocumentFromBuffer`.
 * @returns {import("../viewer/sceneContract.js").KitScene & { document: object, meshCount: number,
 *   leaves: { id: string, leaf: number, label: string, kind: string, site: string, triangles: number }[] }}
 */
export function createGlbScene(THREE, document) {
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
  const look = createSurfaceLook(THREE, document.scene);
  // One box for framing, lighting and the floor: a routine poses the model inside
  // the box sampled over every clip at load, so playing one never re-frames it.
  const bounds = document.animatedBounds || document.restBounds || boundsOf(THREE, root);
  let disposed = false;

  // ---- leaves: what an implicit part's GLB can select ---------------------------------
  const leafRecords = collectImplicitLeaves(document.scene);
  const leaves = leafRecords.map(({ meshes, ...leaf }) => Object.freeze(leaf));
  const leafById = new Map(leafRecords.map(record => [record.id, record]));
  const leafOfMesh = new Map(leafRecords.flatMap(record => record.meshes.map(mesh => [mesh, record])));
  let lastLook = null;
  let highlight = { hovered: "", selected: [] };
  const highlighted = new Set();
  const hoverColor = new THREE.Color(REFERENCE_HOVER_COLOR);
  const selectedColor = new THREE.Color(resolveCadEdgeSettings().highlightColor);

  function paint(mesh, selected) {
    const material = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
    if (!material?.color) return;
    const color = selected ? selectedColor : hoverColor;
    material.color.copy(partHighlightSurfaceColor(THREE, material.color, color, selected ? PART_SELECTED_HIGHLIGHT_BLEND : PART_HOVER_HIGHLIGHT_BLEND));
    if (material.emissive) {
      material.emissive.copy(color);
      material.emissiveIntensity = selected ? PART_SELECTED_EMISSIVE_INTENSITY : PART_HOVER_EMISSIVE_INTENSITY;
    }
    if (!material.transparent) { material.transparent = true; material.needsUpdate = true; }
    material.opacity = 1;
    mesh.renderOrder = HIGHLIGHT_RENDER_ORDER;
    highlighted.add(mesh);
  }
  function applyHighlight() {
    if (!leafRecords.length) return;
    for (const mesh of highlighted) mesh.renderOrder = 0;
    highlighted.clear();
    // The look restores every base it owns; the render order is undone above.
    look.apply(lastLook);
    const selected = new Set(highlight.selected.flatMap(id => leafById.get(id)?.meshes || []));
    // Selection outranks hover: hovering what is already picked must not weaken it.
    for (const mesh of leafById.get(highlight.hovered)?.meshes || []) if (!selected.has(mesh)) paint(mesh, false);
    for (const mesh of selected) paint(mesh, true);
  }

  const raycaster = new THREE.Raycaster();
  const pickable = leafRecords.flatMap(record => record.meshes);
  if (pickable.length) {
    // A hover is a pick per frame over a mesh of many thousand triangles: each geometry
    // gets its accelerator in idle time, the first time a ray reaches its bounds.
    scheduleRuntimeRaycastBvh({ displayRecords: pickable.map(mesh => ({ mesh })) }, { deferUntilRaycast: true });
  }

  const scene = {
    document,
    meshCount: look.meshCount,
    leaves,
    object3D: root,
    bounds,
    restBounds: bounds,
    setSurfaceLook(next) {
      if (disposed) return;
      lastLook = next;
      look.apply(next);
      applyHighlight();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      root.removeFromParent();
      look.dispose();
      disposeGlbDocument(document);
    }
  };
  if (pickable.length) {
    /** Hover and selection by leaf id; `{}` clears both. */
    scene.setHighlight = (next) => {
      if (disposed) return;
      highlight = { hovered: "", selected: [], ...next };
      applyHighlight();
    };
    /** The leaf under the ray: its id, label, kind and source site, and the hit point. */
    scene.pick = (ray) => {
      if (disposed) return null;
      root.updateMatrixWorld();
      raycaster.ray.copy(ray);
      const hit = raycaster.intersectObjects(pickable, false).find(candidate => candidate.object.visible);
      if (!hit) return null;
      const record = leafOfMesh.get(hit.object);
      if (!record) return null;
      return { id: record.id, leaf: record.leaf, label: record.label, kind: record.kind, site: record.site, point: hit.point };
    };
  }
  return scene;
}
