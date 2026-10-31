// Clip over any family's scene (`sceneContract.js`): a GLB, an STL or 3MF, a robot. One plane
// along an axis, from the view's `clip`, cuts every surface the scene drew and caps the cut where
// it passes through a closed surface (`sectionCaps.js`, the stencil fill a STEP's cut wears). The
// viewer's viewport (`@text-to-cad/ui` renderers/kit) and the parity page's headless stage
// (`common/renderMeshScene.js`) both clip through this, so a cut cannot differ between them.
//
// The plane is placed in the box the camera frames (the scene's rest placement), so a pose or an
// exploded view never moves it, and `clip.at` is in the FILE's unit (`sceneUnits.js`).

import { buildStepClipPlane, clipAxisBounds, syncMaterialClipPlanes } from "./clipPlane.js";
import { sceneFramingBounds } from "./sceneContract.js";
import { clipInWorld } from "./sceneUnits.js";
import { disposeSectionCaps, syncSectionCaps } from "./sectionCaps.js";

const STENCIL = "Section stencil";

/** What `object` draws that a cut reaches: every mesh but the caps' own stencils. */
function clippedMeshes(object) {
  const meshes = [];
  object?.traverse?.((child) => { if (child.isMesh && child.name !== STENCIL) meshes.push(child); });
  return meshes;
}

// What a cut is capped over: a mesh of the scene's own, drawn as it stands. A mesh hung under
// another is that mesh's decoration (a highlight's ghost); a skinned or morphed one is not drawn
// where its geometry says, so a stencil over that geometry would fill the wrong place.
function cappable(mesh) {
  return mesh.visible && !mesh.parent?.isMesh && !mesh.isSkinnedMesh && !(mesh.morphTargetInfluences?.length > 0);
}

/**
 * Cut `scene`'s surfaces by `planes`: through its own `setClipPlanes` where it has one (a scene
 * that makes materials later — a look's stand-ins, a highlight's ghosts — keeps them cut), else on
 * every material it drew now.
 */
export function applySceneClipPlanes(scene, planes) {
  if (!scene) return;
  if (typeof scene.setClipPlanes === "function") { scene.setClipPlanes(planes); return; }
  for (const mesh of clippedMeshes(scene.object3D)) syncMaterialClipPlanes(mesh.material, planes);
}

/**
 * The cut of one host's scene. `sync` places the plane `clip` says on the scene the host holds now
 * and returns the planes in force (none when the clip is off or cuts nothing): what the host's own
 * overlays (an annotation's ink) are cut by too. `dispose` takes the cut and its caps away.
 *
 * @param {typeof import("three")} THREE
 * @param {{ stage: import("three").Object3D }} host  Where the caps' fill plane is drawn: the host's
 *   three scene, beside the model.
 */
export function createSceneClip(THREE, { stage }) {
  const runtime = { THREE, scene: stage, displayRecords: [], modelBounds: null, modelRadius: 1, sectionCaps: null };
  let clipped = null;
  let planes = [];
  const clear = () => {
    if (clipped && planes.length) applySceneClipPlanes(clipped, []);
    disposeSectionCaps(runtime);
    clipped = null;
    planes = [];
  };
  return {
    get planes() { return planes; },
    /**
     * @param {import("./sceneContract.js").KitScene | null} scene
     * @param {object | null} clip  The view's `clip` (`normalizeStepClipSettings`), `at` in the file's unit.
     */
    sync(scene, clip) {
      if (scene !== clipped) clear();
      const bounds = scene ? sceneFramingBounds(scene) : null;
      const plane = scene && bounds ? buildStepClipPlane(THREE, clipInWorld(clip, scene.units), bounds) : null;
      if (!plane) { clear(); return planes; }
      clipped = scene;
      planes = [plane];
      applySceneClipPlanes(scene, planes);
      scene.object3D.updateMatrixWorld(true);
      runtime.displayRecords = clippedMeshes(scene.object3D).filter(cappable).map(mesh => ({ mesh }));
      runtime.modelBounds = bounds;
      const extents = [0, 1, 2].map(index => { const { min, max } = clipAxisBounds(bounds, ["x", "y", "z"][index]); return max - min; });
      runtime.modelRadius = Math.max(Math.hypot(...extents) / 2, 1e-6);
      syncSectionCaps(runtime, plane, clip);
      return planes;
    },
    dispose: clear
  };
}
