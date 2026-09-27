// A GLB, an STL, a 3MF or a robot description (URDF, SRDF, SDF) on the snapshot CLI's
// headless stage, as the SCENE ITS VIEWER RENDERER DRAWS. There is one builder per file
// family and it lives in this package so that both hosts call it: the viewer's renderers
// (`@hardcore/ui` renderers/glb, mesh, robot) and this stage. A snapshot of those files
// therefore cannot show something the viewer does not — the same loader reads the file,
// the same builder makes the scene, the same look (`resolveSceneSurfaceLook`) dresses it
// and the same pose poses it. What is this stage's own is only what a still has and a
// viewport does not: the camera fit, the studio set up once per output, and PNG encoding
// (`renderMeshScene.js`).
//
// A STEP model is not here: its scene is `buildModel` (`cadScene.js`), which the viewer's
// STEP renderer and the headless stage already share.

import { createHttpCadResourceProvider } from "../client/resources.js";
import { loadRenderGlbDocument } from "../lib/renderAssetClient.js";
import {
  renderAssetSourceScope,
  renderAssetSourceScopeForJob,
  setRenderAssetSourceScope
} from "../lib/renderAssetSourceScope.js";
import { disposeGlbDocument } from "../lib/render/glbMeshData.js";
import { createGlbScene } from "../lib/render/glbScene.js";
import { loadRenderMeshByUrl } from "../lib/render/meshLoaders.js";
import { buildMeshScene } from "../lib/render/meshScene.js";
import { loadRobot } from "../lib/urdf/loadRobot.js";
import { robotOpeningPose } from "../lib/urdf/motion.js";
import { createRobotScene } from "../lib/urdf/robotScene.js";
import { isKitScene, sceneFramingBounds } from "../lib/viewer/sceneContract.js";
import { resolveSceneSurfaceLook } from "./sceneSettings.js";

function jobKind(job) {
  return String(job?.resolved?.kind || job?.kind || "").trim().toLowerCase();
}

function jobUrl(job) {
  const url = String(job?.url || job?.resolved?.url || "").trim();
  if (!url) throw new Error(`a ${jobKind(job).toUpperCase()} render job needs resolved.url`);
  return url;
}

function jobFile(job) {
  return String(job?.resolved?.inputPath || job?.url || job?.resolved?.url || "the file");
}

// A mesh file's decode lives in page-lifetime caches shared by every job in a packet, so a
// resolved job declares whose it is while it loads (`renderAssetSourceScope.js`), exactly as a
// STEP source does; the declaration never outlives the load.
async function inSourceScope(job, load) {
  const previous = renderAssetSourceScope();
  setRenderAssetSourceScope(renderAssetSourceScopeForJob(job));
  try { return await load(); }
  finally { setRenderAssetSourceScope(previous); }
}

const GLB_FAMILY = Object.freeze({
  name: "glb",
  // The native document the GLB renderer loads (`useGlbScene`): uncached, one owner.
  load: (job, { resources }) => inSourceScope(job, () => loadRenderGlbDocument(jobUrl(job), { resources })),
  build: (THREE, document) => createGlbScene(THREE, document),
  release: document => disposeGlbDocument(document)
});

const MESH_FAMILY = Object.freeze({
  name: "mesh",
  // The decode the mesh renderer loads (`useMeshScene`), cached per file for the page.
  load: (job, { resources }) => inSourceScope(job, () => loadRenderMeshByUrl(jobUrl(job), { resources, fallback: jobKind(job) })),
  build(THREE, meshData, job) {
    const scene = buildMeshScene(THREE, meshData);
    // The viewer's "No geometry to display": a file that parses to no triangles is not a picture.
    if (!scene) throw new Error(`${jobFile(job)} holds no triangles to draw`);
    return scene;
  },
  release: () => {}
});

const ROBOT_FAMILY = Object.freeze({
  name: "robot",
  // The robot the robot renderer loads (`useRobotDocument`): the description and every link mesh.
  load: (job, { resources }) => loadRobot(jobKind(job), {
    url: jobUrl(job), urdfUrl: String(job?.resolved?.urdfUrl || job?.urdfUrl || "").trim(), resources
  }),
  build(THREE, robot, job) {
    const scene = createRobotScene(THREE, robot);
    // Where the viewer OPENS this robot, with the joints the request names on top: one
    // write through the one path a pose takes (the scene's joint matrices).
    scene.setJointValues({ ...robotOpeningPose(robot.description), ...jointValuesOf(job) });
    return scene;
  },
  release: () => {}
});

function jointValuesOf(job) {
  const values = job?.jointValues ?? job?.resolved?.jointValues ?? null;
  return values && typeof values === "object" && !Array.isArray(values) ? values : {};
}

const FAMILY_BY_KIND = Object.freeze({
  glb: GLB_FAMILY,
  stl: MESH_FAMILY,
  "3mf": MESH_FAMILY,
  urdf: ROBOT_FAMILY,
  srdf: ROBOT_FAMILY,
  sdf: ROBOT_FAMILY
});

/**
 * The family whose shared builder draws this job's file, or null for a STEP model (and for
 * anything that is not a file family: the caller refuses it).
 *
 * @returns {{ name: string, load: Function, build: Function, release: Function } | null}
 */
export function headlessSceneFamily(job) {
  return FAMILY_BY_KIND[jobKind(job)] || null;
}

/** The HTTP resource provider every family loads through, addressed at the snapshot host. */
export function headlessResources() {
  const origin = String(globalThis.window?.__cadgenSnapshotAssetOrigin || "").replace(/\/+$/, "");
  return createHttpCadResourceProvider({ origin, cache: "no-store" });
}

/**
 * What a scene wears on this stage, from the job's resolved scene settings: the viewer's look
 * (`resolveSceneSurfaceLook`, the one the viewport resolves) and its shadow rule (the scene takes
 * shadows while the lighting is on).
 */
export function headlessSceneDress(sceneSettings) {
  return {
    look: resolveSceneSurfaceLook({
      themeSettings: sceneSettings.theme,
      displaySettings: sceneSettings.display,
      renderMode: sceneSettings.render.enabled,
      renderConfiguration: sceneSettings.render.configuration
    }),
    receiveShadows: sceneSettings.view.lighting.enabled === true
  };
}

function worldBox(THREE, object) {
  const box = new THREE.Box3().setFromObject(object, false);
  return box.isEmpty() ? null : { min: box.min.toArray(), max: box.max.toArray() };
}

// The name a builder gives what it drew: a GLB node's authored name (GLTFLoader keeps it in
// `userData.name`, up the node's parents), else the mesh's own name.
function displayName(object) {
  for (let current = object; current; current = current.parent) {
    const name = String(current.userData?.name || "").trim();
    if (name) return name;
  }
  return String(object.name || "");
}

// Its identity: a robot part's id, a node's CAD occurrence (up its parents), else its name.
function partIdentity(object) {
  if (object.userData?.partId) return String(object.userData.partId);
  for (let current = object; current; current = current.parent) {
    const occurrence = String(current.userData?.cadOccurrenceId || "").trim();
    if (occurrence) return occurrence;
  }
  return String(object.name || "");
}

/**
 * A family's scene as the headless stage holds it: dressed exactly as the viewer's viewport
 * dresses a scene it adopts (the look first, then shadow reception, `ShellViewport`), and
 * exposing what `renderModel`/`captureModel` read of any model. The scene is its builder's; this
 * adds nothing to it and owns it from here (`dispose()`).
 *
 * @param {typeof import("three")} THREE
 * @param {import("../lib/viewer/sceneContract.js").KitScene} scene  A family builder's scene.
 * @param {{ look: object | null, receiveShadows: boolean }} dress  `headlessSceneDress`.
 */
export function headlessSceneModel(THREE, scene, { look = null, receiveShadows = false } = {}) {
  if (!isKitScene(scene)) {
    throw new Error("the headless stage holds a family's scene: { object3D, bounds, dispose() } (lib/viewer/sceneContract.js)");
  }
  scene.setSurfaceLook?.(look);
  if (scene.setShadowReception) scene.setShadowReception(receiveShadows);
  else scene.object3D.traverse((object) => { if (object.isMesh) object.receiveShadow = receiveShadows; });
  const meshes = [];
  scene.object3D.traverse((object) => { if (object.isMesh) meshes.push(object); });
  const model = {
    scene,
    root: scene.object3D,
    get bounds() { return scene.bounds; },
    get restBounds() { return sceneFramingBounds(scene); },
    keepsAuthoredFinish: scene.keepsAuthoredFinish === true,
    // What the still's tight frame fits on and what its mesh count counts: every mesh drawn.
    displayRecords: meshes.map(mesh => ({ mesh })),
    // What the near/far fit may place objects by; a family scene that names none is fitted on its box.
    placedObjects: () => scene.placedObjects?.() || [],
    // A family scene is posed once, as it is built; an output has nothing more to pose.
    update: () => model,
    // `--mode list`: what the scene drew, one row per mesh, placed as posed.
    listParts() {
      scene.object3D.updateMatrixWorld(true);
      return meshes.map((mesh) => {
        const position = mesh.geometry?.getAttribute?.("position");
        const index = mesh.geometry?.getIndex?.();
        const vertexCount = position?.count || 0;
        return {
          id: partIdentity(mesh),
          name: displayName(mesh),
          vertexCount,
          triangleCount: Math.floor((index ? index.count : vertexCount) / 3),
          bounds: worldBox(THREE, mesh)
        };
      });
    },
    dispose: () => scene.dispose()
  };
  return model;
}
