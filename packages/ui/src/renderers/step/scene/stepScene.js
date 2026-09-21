import { buildModel } from "@hardcore/core/common/cadScene.js";

// The STEP renderer's kit scene (`kit/scene.js`): ONE identity for as long as a file
// is mounted, around whatever core's `buildModel` has built for it right now.
//
// A STEP does not arrive once. A large assembly is published in pieces, each
// component's detail is swapped as the camera moves, and a display mode that changes
// how records are BUILT replaces the whole build. None of that is a new scene to the
// viewport: the roots below never change, so the viewport adopts this object once
// and is told (`viewport.commitScene()`) when what is inside it changed. Re-adopting
// a fresh identity per publish would re-dress every material and re-walk every mesh
// six times while a big model opens.
//
// Ownership. The build (`cadScene`) owns its records, materials and the geometries it
// created. Component geometry is SHARED between builds and between scenes through
// core's owner counts (`syncRecordGeometryOwnership`), so releasing a build drops this
// scene's count and frees a buffer only when no other build holds it; `releaseGpu:
// false` keeps the GPU buffers and BVHs for a rebuild of the same model. Nothing here
// disposes a geometry directly.

const EMPTY_BOUNDS = Object.freeze({ min: Object.freeze([0, 0, 0]), max: Object.freeze([0, 0, 0]) });
const EMPTY_RECORDS = Object.freeze([]);

// Why a live build was replaced rather than reused: the build-key fields that changed.
function buildDifference(previous, next) {
  const reasons = [];
  if (previous.modelKey !== next.modelKey) reasons.push("model key");
  if (previous.viewerTheme !== next.viewerTheme) reasons.push("viewer theme");
  if (previous.key !== next.key) {
    try {
      const before = JSON.parse(previous.key || "{}");
      const after = JSON.parse(next.key || "{}");
      for (const field of new Set([...Object.keys(before), ...Object.keys(after)])) {
        if (JSON.stringify(before[field]) !== JSON.stringify(after[field])) reasons.push(field);
      }
    } catch {
      reasons.push("build key");
    }
  }
  return reasons.join(",");
}

// What the viewport resolved and what STEP resolved are the same look, derived twice from
// the same settings; this is how the scene tells that one of them has already been worn.
function lookKey(materialSettings, surfaceSettings) {
  try {
    return JSON.stringify([materialSettings, surfaceSettings?.style ?? null, surfaceSettings?.opacity ?? null]);
  } catch {
    return "";
  }
}

/**
 * @param {typeof import("three")} THREE
 * @returns {import("../../kit/scene.js").KitScene & object}
 */
export function createStepScene(THREE) {
  const object3D = new THREE.Group();
  object3D.name = "StepScene";
  // Linework is drawn in the viewport's own edge layer, above the surfaces, so it has a
  // root of its own; the renderer's layers parent it there.
  const edgesObject3D = new THREE.Group();
  edgesObject3D.name = "StepSceneEdges";
  // Overlays that belong WITH the surfaces rather than with the linework -- the reference
  // highlight's face fill -- hang here, inside this scene's own root. The viewport's
  // `modelGroup` is the viewport's: nothing here may add to it, because nothing here clears
  // it (`render/lodSceneCleanup.js` clears the edge and pick groups and deliberately leaves
  // the model group alone), and an overlay parked there outlives the build it was drawn
  // against -- a picked face whose outline goes with the rebuild while its fill stays lit.
  const overlayObject3D = new THREE.Group();
  overlayObject3D.name = "StepSceneOverlay";
  object3D.add(overlayObject3D);

  let cadScene = null;
  let built = { key: "", viewerTheme: null, modelKey: "" };
  // What STEP resolves beyond the kit's surface look: the theme, the app appearance (edge
  // ink), authored-material overrides, the whole Surfaces section and shadow reception.
  let lookContext = null;
  let wornLookKey = "";

  const dress = (materialSettings) => {
    if (!cadScene || !lookContext) return false;
    cadScene.update({
      theme: lookContext.theme,
      appearance: lookContext.appearance,
      materialSettings,
      materialOverrides: lookContext.materialOverrides,
      receiveShadows: lookContext.receiveShadows,
      surfaceSettings: lookContext.surfaceSettings
    });
    cadScene.syncSurfaceInstances();
    wornLookKey = lookKey(materialSettings, lookContext.surfaceSettings);
    return true;
  };

  const scene = {
    object3D,
    edgesObject3D,
    overlayObject3D,
    get cadScene() { return cadScene; },
    get source() { return cadScene?.source || null; },
    get displayRecords() { return cadScene?.displayRecords || EMPTY_RECORDS; },
    /** As posed now: what lighting, shadows and the floor's height follow. */
    get bounds() { return cadScene?.bounds || cadScene?.source?.bounds || EMPTY_BOUNDS; },
    /** The authored placement: what the camera frames and the ground is sized from. */
    get restBounds() { return cadScene?.restBounds || cadScene?.source?.bounds || EMPTY_BOUNDS; },
    /** `false` while components of a progressive package are still to come. */
    get complete() {
      const missing = cadScene?.source?.missingComponentIds;
      return !(Array.isArray(missing) && missing.length > 0);
    },
    placedObjects() { return cadScene?.displayRecords || EMPTY_RECORDS; },

    /** Whether the live build can take this publish in place, and if not, why. */
    plan({ modelKey = "", buildKey = "", viewerTheme = null } = {}) {
      const next = { key: buildKey, viewerTheme, modelKey: modelKey || "" };
      const reuse = Boolean(cadScene) && built.modelKey === next.modelKey && built.key === next.key
        && built.viewerTheme === next.viewerTheme;
      return { reuse, sameModel: Boolean(cadScene) && built.modelKey === next.modelKey,
        reason: !reuse && cadScene ? buildDifference(built, next) : "" };
    },
    /** Hand the live build a new publish: records on screen are reconciled, never rebuilt. */
    update(source, settings) {
      cadScene.update({ source, ...settings });
      wornLookKey = lookKey(settings.materialSettings, settings.surfaceSettings);
      return cadScene;
    },
    /** Replace the build. The previous one must already have been released (`release`). */
    build(source, { modelKey = "", buildKey = "", viewerTheme = null }, settings) {
      if (cadScene) throw new Error("The STEP scene still holds a build; release it first.");
      cadScene = buildModel(THREE, source, settings);
      object3D.add(cadScene.modelGroup);
      edgesObject3D.add(cadScene.edgesGroup);
      built = { key: buildKey, viewerTheme, modelKey: modelKey || "" };
      wornLookKey = lookKey(settings.materialSettings, settings.surfaceSettings);
      return cadScene;
    },
    /** A build whose construction failed and could not clean up after itself: held for teardown. */
    holdFailedBuild(failedCadScene) {
      cadScene = failedCadScene;
      object3D.add(failedCadScene.modelGroup);
      edgesObject3D.add(failedCadScene.edgesGroup);
    },
    /**
     * Release the live build and name the source it showed. `releaseGpu: false` keeps the
     * components' GPU buffers and BVHs for a rebuild of the SAME model (a display mode, a
     * theme); `preserveModelIdentity` keeps knowing which model that was.
     */
    release({ releaseGpu = true, preserveModelIdentity = false } = {}) {
      const source = cadScene?.source || null;
      cadScene?.dispose?.({ releaseGpu });
      cadScene = null;
      wornLookKey = "";
      built = preserveModelIdentity ? { key: "", viewerTheme: null, modelKey: built.modelKey } : { key: "", viewerTheme: null, modelKey: "" };
      return source;
    },

    /** STEP's half of the look. Dresses the build at once when any of it changed. */
    setLookContext(next) {
      const previous = lookContext;
      lookContext = next;
      const changed = !previous || previous.theme !== next.theme || previous.appearance !== next.appearance
        || previous.materialSettings !== next.materialSettings || previous.materialOverrides !== next.materialOverrides
        || previous.receiveShadows !== next.receiveShadows || previous.surfaceSettings !== next.surfaceSettings;
      return changed ? dress(next.materialSettings) : false;
    },
    /** The kit's half: a look the build is not already wearing is put on with STEP's context. */
    setSurfaceLook(look) {
      if (!look || !cadScene || !lookContext) return;
      if (lookKey(look.materialSettings, look.surface) === wornLookKey) return;
      dress(look.materialSettings);
    },

    /**
     * Shadow reception is per RECORD here (`syncRecordShadowPolicy` in core): an unlit or a
     * see-through surface -- a watch crystal -- never takes one, so the viewport must not set
     * every mesh. The setting itself arrives with the look context, in the same commit.
     */
    setShadowReception(receives) {
      if (!lookContext || lookContext.receiveShadows === (receives === true)) return;
      scene.setLookContext({ ...lookContext, receiveShadows: receives === true });
    },

    // Release everything the scene created and leave the viewport. NOT terminal: React's
    // development remount runs an owner's cleanup and then its effects again over the same
    // scene, which must then simply build again.
    dispose() {
      scene.release();
      object3D.removeFromParent();
      edgesObject3D.removeFromParent();
    }
  };
  return scene;
}

/** The same scene, saying whether Inspect should give it a neutral environment to reflect. */
export function stepSceneView(scene, keepsAuthoredFinish) {
  return Object.create(scene, { keepsAuthoredFinish: { value: keepsAuthoredFinish === true, enumerable: true } });
}
