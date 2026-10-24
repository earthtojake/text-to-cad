import { createInspectEnvironmentResource, hasAuthoredMaterials } from "./inspectEnvironment.js";
import { resolveCadEdgeSettings } from "./cadInk.js";
import * as THREE from "three";
import { createAnnotationLayer, normalizeAnnotation, ANNOTATION_REFERENCE_HEIGHT_PX } from "./annotation.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import {
  displayModeIsWireframe,
  CAMERA_PROJECTION,
  resolveDisplayEdgeSettings
} from "./displaySettings.js";
import { normalizedSelectorValues } from "./cadScene.js";
import {
  applyDisplayRecordTransform
} from "./displayRecordTransform.js";
import {
  resolveTopologyDisplayEdgeRuntimes,
  shouldRenderTopologyDisplayEdges
} from "./topologyDisplayEdgeRuntime.js";
import {
  screenSpaceLineDeviceResolution,
  syncScreenSpaceLineMaterialResolution
} from "./renderEdges.js";
import {
  syncTopologyDisplayEdgeLine
} from "../lib/viewer/topologyDisplayEdgeLine.js";
import { syncRuntimeStepClipPlane } from "../lib/viewer/modelRuntime.js";
import { createSceneClip } from "../lib/viewer/sceneClip.js";
import { disposeSectionCaps } from "../lib/viewer/sectionCaps.js";
import { applySceneRig, renderWithSceneRig, sceneRigFor } from "../lib/viewer/sceneRig.js";
import {
  applyExplodedViewProgress,
  clearExplodedViewRecords,
  computeExplodedViewLayout,
  explodedViewBounds,
  occurrencePathsFromAssemblyRoot
} from "../lib/viewer/explodedView.js";
import {
  addFloor as addSharedFloor,
  applyLighting as applySharedLighting,
  boundsFromVertices as sharedBoundsFromVertices,
  colorTextureFromBackground as sharedColorTextureFromBackground,
  configurePngRenderer,
  createSharedRenderOptions,
  fitPerspectiveCamera as fitSharedPerspectiveCamera,
  fitCameraDepthToBounds,
  fitOrthographicCamera,
  framePadding as sharedFramePadding,
  inferRenderSceneScale,
  outputSize as sharedOutputSize,
  RENDER_SCENE_SCALE,
  RENDER_VIEW_PRESETS,
  rendererDataUrlWithOptionalLabel as sharedRendererDataUrlWithOptionalLabel,
  resolveRenderView
} from "./renderOptions.js";
import {
  normalizeCameraSpec
} from "./camera.js";
import {
  resolveDisplayMaterialSettings,
  resolveViewSceneSettings
} from "./sceneSettings.js";
import { viewFeaturesForKind } from "./viewSettings.js";
import {
  createEnvironmentResource,
  disposeEnvironmentResource
} from "./environmentMap.js";
import {
  applyPhotographicStudio,
  disposePhotographicStudio
} from "./photographicStudio.js";
import { PHOTOGRAPHIC_STUDIO_FRAME, PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "./photographicStudioRig.js";
import { validateSnapshotRenderJob } from "./snapshotJobValidation.js";
import { isSoftwareWebGlRenderer } from "../lib/viewer/webglSupport.js";

// A snapshot draws its studio frame (`studioFrame.js`) supersampled at its render scale, so the
// frame needs no MSAA of its own.
const SNAPSHOT_STUDIO_FRAME = Object.freeze({ multisample: 0 });

/**
 * How many samples a snapshot's studio frame converges over: a still's, all of them; a video's
 * frame (a `frameBounds` capture) and a software renderer's, one, which is a whole picture of
 * its own (its occlusion smoothed, its shadows the key's own) at the cost of one draw.
 */
export function snapshotStudioSamples({ video = false, softwareRendering = false } = {}) {
  return video || softwareRendering ? 1 : PHOTOGRAPHIC_STUDIO_FRAME.stillSamples;
}

const DEFAULT_RENDER_SCALE = 1;
const RENDER_SCENE_SCALE_SETTINGS = Object.freeze({
  [RENDER_SCENE_SCALE.CAD]: Object.freeze({
    minBoundsSpan: 1,
    minModelRadius: 1,
    minFloorSize: 100,
    minCameraDistance: 10,
    minCameraFar: 1000
  }),
  [RENDER_SCENE_SCALE.URDF]: Object.freeze({
    minBoundsSpan: 0.05,
    minModelRadius: 0.05,
    minFloorSize: 0.5,
    minCameraDistance: 0.5,
    minCameraFar: 10
  })
});

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function resolveRenderSceneScale(job = {}) {
  const explicit = String(job.scale || "").trim().toLowerCase();
  return inferRenderSceneScale({
    explicit,
    kind: job.resolved?.kind || job.kind
  });
}

function resolveView(camera = "iso") {
  return resolveRenderView(camera, RENDER_VIEW_PRESETS, { strict: true });
}

function boundsFromVertices(vertices) {
  return sharedBoundsFromVertices(vertices);
}

function colorTextureFromBackground(background, width, height) {
  return sharedColorTextureFromBackground(background, width, height);
}

function applyLighting(scene, themeSettings, bounds, sceneScale, shadowMapSize) {
  return applySharedLighting(scene, themeSettings, { bounds, sceneScale, shadowMapSize });
}

function addFloor(scene, bounds, themeSettings, sceneScale = RENDER_SCENE_SCALE.CAD, guideSettings = null, sizeBounds = null) {
  return addSharedFloor(scene, bounds, themeSettings, sceneScale, RENDER_SCENE_SCALE_SETTINGS, guideSettings, sizeBounds);
}

function framePadding(job = {}) {
  return sharedFramePadding(job);
}

function fitCamera(camera, view, bounds, width, height, lockedHalfHeight = null, padding = 0.12, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return fitOrthographicCamera(camera, view, bounds, width, height, {
    lockedHalfHeight,
    padding,
    sceneScale,
    settingsByScale: RENDER_SCENE_SCALE_SETTINGS
  });
}

function fitPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
  framePoints = null,
  padding = 0.12,
  sceneScale = RENDER_SCENE_SCALE.CAD
} = {}) {
  return fitSharedPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
    framePoints,
    padding,
    sceneScale,
    settingsByScale: RENDER_SCENE_SCALE_SETTINGS,
    strict: true
  });
}

function outputSize(output, job) {
  return sharedOutputSize(output, job);
}

function configureRenderer(width, height, job, context) {
  return configurePngRenderer(width, height, job, {
    defaultRenderScale: context.quality?.renderScale ?? DEFAULT_RENDER_SCALE,
    // Render replaces this wholesale in applyPhotographicStudio; only the CAD
    // inspection scene takes its exposure from the theme.
    toneMappingExposure: context.theme?.lighting?.toneMappingExposure ?? 1
  });
}

function shouldBurnInViewLabels(job = {}) {
  return sharedShouldBurnInViewLabels(job);
}

function rendererDataUrlWithOptionalLabel(renderer, label, job, size) {
  return sharedRendererDataUrlWithOptionalLabel(renderer, label, job, size);
}

export function disposeSnapshotSceneResources(scene, modelRoot = null, extraTextures = []) {
  const disposedGeometries = new Set();
  const disposedMaterials = new Set();
  const disposedTextures = new Set();
  const disposeTexture = (texture) => {
    if (!texture?.isTexture || disposedTextures.has(texture)) return;
    disposedTextures.add(texture);
    texture.dispose?.();
  };
  const disposeMaterial = (material) => {
    if (!material || disposedMaterials.has(material)) return;
    disposedMaterials.add(material);
    for (const value of Object.values(material)) {
      disposeTexture(value);
    }
    material.dispose?.();
  };
  for (const child of [...(scene?.children || [])]) {
    if (child === modelRoot) continue;
    child.traverse?.((object) => {
      if (object.geometry && !disposedGeometries.has(object.geometry)) {
        disposedGeometries.add(object.geometry);
        object.geometry.dispose?.();
      }
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach(disposeMaterial);
    });
    scene.remove?.(child);
  }
  for (const texture of extraTextures) disposeTexture(texture);
  disposeTexture(scene?.background);
  disposeTexture(scene?.environment);
  if (scene?.background?.isTexture) scene.background = null;
  if (scene?.environment?.isTexture) scene.environment = null;
  return {
    geometryCount: disposedGeometries.size,
    materialCount: disposedMaterials.size,
    textureCount: disposedTextures.size
  };
}

function tightFrameEnabled(job = {}) {
  return normalizeBoolean(job.output?.tightFrame, true);
}

// A vertex where it is drawn. A skinned or morphed mesh (a GLB's native scene) is deformed
// on the GPU, so its position attribute is the rest shape: three's `getVertexPosition` applies
// the morph targets and the skin the way the shader does. Every other mesh reads its attribute.
function vertexWorldPosition(mesh, position, index, target) {
  if (mesh.isSkinnedMesh || mesh.morphTargetInfluences?.length) mesh.getVertexPosition(index, target);
  else target.fromBufferAttribute(position, index);
  return target.applyMatrix4(mesh.matrixWorld);
}

export function projectedVisibleGeometryFrame(records, camera) {
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
  const screenUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
  const point = new THREE.Vector3();
  const min = { x: Infinity, y: Infinity };
  const max = { x: -Infinity, y: -Infinity };
  let count = 0;

  for (const record of Array.isArray(records) ? records : []) {
    const mesh = record?.mesh;
    const position = mesh?.geometry?.getAttribute?.("position");
    if (!mesh?.visible || !position || position.count <= 0) {
      continue;
    }
    mesh.updateWorldMatrix?.(true, false);
    for (let index = 0; index < position.count; index += 1) {
      vertexWorldPosition(mesh, position, index, point);
      const x = point.dot(right);
      const y = point.dot(screenUp);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        continue;
      }
      min.x = Math.min(min.x, x);
      min.y = Math.min(min.y, y);
      max.x = Math.max(max.x, x);
      max.y = Math.max(max.y, y);
      count += 1;
    }
  }

  if (!count || ![min.x, min.y, max.x, max.y].every(Number.isFinite)) {
    return null;
  }

  return {
    centerX: (min.x + max.x) / 2,
    centerY: (min.y + max.y) / 2,
    spanX: Math.max(max.x - min.x, 1e-6),
    spanY: Math.max(max.y - min.y, 1e-6),
    count
  };
}

function *visibleGeometryWorldPoints(records) {
  const point = new THREE.Vector3();
  for (const record of Array.isArray(records) ? records : []) {
    const mesh = record?.mesh;
    const position = mesh?.geometry?.getAttribute?.("position");
    if (!mesh?.visible || !position || position.count <= 0) {
      continue;
    }
    mesh.updateWorldMatrix?.(true, false);
    for (let index = 0; index < position.count; index += 1) {
      yield vertexWorldPosition(mesh, position, index, point);
    }
  }
}

function applyTightOrthographicFrame(camera, records, width, height, padding, zoom = 1) {
  camera.updateMatrixWorld(true);
  const frame = projectedVisibleGeometryFrame(records, camera);
  if (!frame) {
    return null;
  }

  const aspect = Math.max(width / Math.max(height, 1), 0.01);
  const safeContentScale = Math.max(1 - (padding * 2), 0.1);
  const halfHeight = Math.max(
    frame.spanY / (2 * safeContentScale),
    frame.spanX / (2 * aspect * safeContentScale),
    1e-6
  ) / Math.max(toFiniteNumber(zoom, 1), 1e-6);
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
  const screenUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
  const currentCenterX = camera.position.dot(right);
  const currentCenterY = camera.position.dot(screenUp);
  camera.position
    .addScaledVector(right, frame.centerX - currentCenterX)
    .addScaledVector(screenUp, frame.centerY - currentCenterY);
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return {
    ...frame,
    halfHeight
  };
}

// Coordinates are millimetres. The mesh pipeline emits full float64 precision
// (-2449.9999046325684 for what is 2450 mm), which is 16 significant figures of noise per
// number, six numbers per part. Three decimals is a nanometre -- far below any tolerance
// this repo models to -- and costs about a fifth of the payload.
const LIST_BOUNDS_DECIMALS = 3;

function roundedBounds(bounds) {
  if (!bounds || typeof bounds !== "object") {
    return null;
  }
  const axis = (values) => (Array.isArray(values)
    ? values.map((value) => {
      const numeric = toFiniteNumber(value, 0);
      return Number(numeric.toFixed(LIST_BOUNDS_DECIMALS));
    })
    : null);
  const min = axis(bounds.min);
  const max = axis(bounds.max);
  return min && max ? { min, max } : null;
}

// The parts inventory of a family scene (a GLB, an STL, a 3MF, a robot, an engine document):
// what it drew.
//
// This is the ONLY output whose size grows with the model -- everything else in the CLI
// surface is constant (a 600-part assembly logs the same ~100 bytes a single part does).
// So it is the one payload where redundancy is measured in tens of thousands of tokens:
// on a 600-part rover the previous shape was 294 KB, of which `id`, `occurrenceId` and
// `ref` were the same string three times over (identical in 600/600 parts), `label`
// duplicated `name` (600/600), and the coordinates carried 16 significant figures.
//
// `ref` survives rather than `id`/`occurrenceId` because it is the form a reader hands
// back to address the part; the bare id is one string slice away for anyone who needs it.
// A label ref (`#eye_shank`) addresses a part by the `name` already in every row, so this
// payload deliberately does NOT carry a second `labelRef` identifier -- that would undo the
// size work above for a string the row already contains. A duplicated label's numbered
// aliases (`#wheel_1`, `#wheel_2`) are spelled out where the bare label is refused.
export function listRenderableParts(parts) {
  return toArray(parts).map((part, index) => {
    const occurrenceId = String(part?.occurrenceId || part?.id || "");
    return {
      ref: occurrenceId ? `#${occurrenceId}` : "",
      name: String(part?.name || part?.label || part?.id || `Part ${index + 1}`),
      triangleCount: Math.max(0, Math.floor(toFiniteNumber(part?.triangleCount, 0))),
      vertexCount: Math.max(0, Math.floor(toFiniteNumber(part?.vertexCount, 0))),
      bounds: roundedBounds(part?.bounds)
    };
  });
}

export function resolveOutputCameraSpec(context, cameraSpec) {
  const contextCamera = context?.camera || {
    preset: "iso",
    projection: context?.projection || CAMERA_PROJECTION.ORTHOGRAPHIC
  };
  if (cameraSpec == null) {
    return contextCamera;
  }
  if (typeof cameraSpec === "string") {
    return {
      preset: cameraSpec,
      projection: contextCamera.projection,
      ...(contextCamera.focalLength != null ? { focalLength: contextCamera.focalLength } : {})
    };
  }
  return {
    ...(contextCamera.focalLength != null ? { focalLength: contextCamera.focalLength } : {}),
    ...cameraSpec,
    projection: cameraSpec.projection ?? contextCamera.projection
  };
}

// Projection is one field of the canonical per-output camera spec. A named
// output view inherits the job camera's projection unless it explicitly says
// otherwise.
export function resolveOutputCameraProjection(context, cameraSpec) {
  return normalizeCameraSpec(resolveOutputCameraSpec(context, cameraSpec), {
    presets: RENDER_VIEW_PRESETS,
    strict: true,
    defaultProjection: context?.camera?.projection || CAMERA_PROJECTION.ORTHOGRAPHIC
  }).projection;
}

export function renderJobContext(meshData, job = {}) {
  validateSnapshotRenderJob(job);
  const mode = String(job.mode || "view").trim().toLowerCase();
  const sceneScale = resolveRenderSceneScale(job);
  const sourceKind = String(job.resolved?.kind || job.kind || "").trim().toLowerCase();
  const stepDisplayEnabled = sourceKind === "step" || sourceKind === "stp";
  const sceneSettings = resolveViewSceneSettings({
    // Appearance is `display.appearance`; the CLI default is Light.
    appearance: "light",
    camera: job.camera || null,
    display: job.display ?? {},
    // Preview's look is the job's own request (`preview: true`), over the same display, at
    // Preview's defaults: a snapshot has no Preview settings of its own.
    preview: job.preview === true,
    // The viewer's rule for this file: only a CAD model has edges to draw; Parts colours a file of
    // several parts; a GLB of several parts explodes; every 3D file is cut by Clip (`viewFeaturesForKind`).
    features: viewFeaturesForKind(sourceKind, { parts: meshData.partCount || 0, explodeParts: meshData.explodeParts || 0 })
  });
  // Neutral CAD lights remain available when only the background/floor is on.
  const theme = sceneSettings.theme;
  const displaySettings = sceneSettings.display;
  const projection = sceneSettings.camera.projection;
  const displayMode = displaySettings.mode;
  const bounds = meshData.bounds || boundsFromVertices(meshData.vertices || []);
  const outputs = toArray(job.outputs);
  const warnings = [];
  const sharedRenderOptions = createSharedRenderOptions({
    themeSettings: theme,
    display: displaySettings,
    camera: sceneSettings.camera,
    sceneScale,
    clip: displaySettings.clip,
    selection: job.selection || null,
    floor: theme?.floor || null,
    background: theme?.background || null,
    lighting: theme?.lighting || null,
    renderScale: job.output?.renderScale ?? sceneSettings.quality.renderScale
  });
  const displayEdgeSettings = resolveCadEdgeSettings(
    resolveDisplayEdgeSettings(displaySettings)
  );
  const edgeSettings = {
    ...displayEdgeSettings,
    enabled: sceneSettings.view.edges.enabled,
    depthTest: sceneSettings.view.edges.visibility !== "all"
  };
  const wireframeMode = displayModeIsWireframe(displayMode);
  const edgesVisible = sceneSettings.view.edges.enabled;
  const selectorRuntime = job.selectorRuntime || null;
  const topologyDisplayEdgesVisible = shouldRenderTopologyDisplayEdges({
    edgesVisible,
    wireframeMode,
    cadEdgeSource: stepDisplayEnabled,
    selectorRuntime,
    edgeSettings
  });
  return {
    mode,
    theme,
    sceneSettings,
    camera: sceneSettings.camera,
    quality: sceneSettings.quality,
    sceneScale,
    sourceKind,
    stepDisplayEnabled,
    displaySettings,
    projection,
    displayMode,
    wireframeMode,
    edgesVisible,
    bounds,
    outputs,
    warnings,
    sharedRenderOptions,
    edgeSettings,
    selectorRuntime,
    topologyDisplayEdgesVisible
  };
}

export function modelOptionsForRenderJob(context, job = {}) {
  const selection = job.selection || {};
  const keepsAllParts = context.mode === "view";
  const filterSelection = keepsAllParts
    ? {
        hide: selection.hide
      }
    : selection;
  // View/orbit focus keeps every part in the scene so the frame retains
  // assembly context (hide is the removal filter); the focused refs instead
  // ghost the rest of the model through the same focusedPartId path the
  // interactive viewer uses. List mode isolates via filterSelection.
  const focusedPartId = keepsAllParts ? normalizedSelectorValues(selection.focus) : [];
  const renderEnabled = context.sceneSettings.view.lighting.enabled;
  return {
    theme: context.theme ?? undefined,
    // Render's finish is the studio's, not a theme's. CAD takes its material
    // settings from the resolved theme.
    materialSettings: renderEnabled
      ? resolveDisplayMaterialSettings(
          PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS,
          context.displaySettings.partColor
        )
      : undefined,
    appearance: context.sceneSettings.appearance,
    edgeSettings: context.topologyDisplayEdgesVisible
      ? { ...context.edgeSettings, enabled: false }
      : context.edgesVisible
        ? context.edgeSettings
        : { ...context.edgeSettings, enabled: false },
    materialOverrides: context.sceneSettings.materialOverrides,
    receiveShadows: renderEnabled,
    displayMode: context.displayMode,
    surfaceSettings: context.sceneSettings.view.surfaces,
    applyDisplayModeEdgePolicy: false,
    scale: context.sceneScale,
    clip: context.sharedRenderOptions.clip,
    silhouette: context.topologyDisplayEdgesVisible && context.edgeSettings.silhouette === true,
    renderPartsIndividually: true,
    selection: {
      ...selection,
      ...(focusedPartId.length ? { focusedPartId } : {}),
      showEdges: context.edgesVisible
    },
    edgeRendering: {
      mode: "screen-space",
      Line2,
      LineGeometry,
      LineSegments2,
      LineSegmentsGeometry,
      LineMaterial
    },
    callbacks: {
      onWarning: (warning) => {
        const message = String(warning?.message || warning?.title || "").trim();
        if (message) {
          context.warnings.push(message);
        }
      },
      // The choreography half of a still: `{clip, elapsedSec}` rides the channel
      // cadScene's effects pass already reads (the docs hero drives playback
      // through the same key), so the clip's frame merges over the pose exactly
      // as it does in the viewer — one applySceneState, no snapshot-side twin.
      animation: job.stepAnimation || null
    },
    filterSelection
  };
}

// Kinematics is model state in both Inspect and Render. Per-output values take
// precedence so a multi-output capture can pose each frame independently.
export function stepParametersForSnapshotOutput(output = {}, job = {}) {
  return output.stepParameters || job.stepParameters || null;
}

// Inspect gives authored finishes a small neutral environment to reflect. A family's scene
// says so itself (`keepsAuthoredFinish`, the viewer's viewport reads the same flag); a CAD
// model built by `buildModel` answers from its composed parts.
function keepsAuthoredFinish(model) {
  return typeof model.keepsAuthoredFinish === "boolean" ? model.keepsAuthoredFinish : hasAuthoredMaterials(model.meshData);
}

export function renderModel(_THREE, model, viewportOptions = {}) {
  if (!model?.root) {
    throw new Error("renderModel requires a model returned by buildModel");
  }
  const job = viewportOptions.job || {};
  const context = viewportOptions.context || renderJobContext(model.meshData, job);
  const sceneBuildStarted = performance.now();
  const firstSize = outputSize(context.outputs[0] || {}, job);
  const renderer = configureRenderer(firstSize.width, firstSize.height, job, context);
  const scene = new THREE.Scene();
  let disposed = false;
  let environmentResource = null;
  let backgroundTexture = null;
  const photographicConfiguration = context.sceneSettings.render.configuration || null;
  const studioConfiguration = photographicConfiguration && normalizeBoolean(job.output?.transparent, false)
    ? { ...photographicConfiguration, backdrop: { ...photographicConfiguration.backdrop, transparent: true, opacity: 0 } }
    : photographicConfiguration;
  // What the GROUND is sized from. The viewer sizes the grid, the stage and the studio floor from
  // the model's rest placement, so posing or playing never rescales the ground under it; the CLI
  // follows the same rule so a posed snapshot shows the ground the viewer shows. A video passes
  // `floorBounds` (the union across its frames) and keeps it for everything.
  const restGroundBounds = model.restBounds || null;
  const studioRuntime = studioConfiguration ? { scene, renderer, modelBounds: model.bounds || context.bounds } : null;
  if (studioRuntime) {
    applyPhotographicStudio(THREE, studioRuntime, studioConfiguration, {
      bounds: viewportOptions.floorBounds || studioRuntime.modelBounds,
      // The viewer sizes the studio floor from the REST placement (`groundBounds`), so a posed
      // still must too, or the CLI and the viewer disagree about how big the ground is.
      groundBounds: viewportOptions.floorBounds ? null : restGroundBounds,
      shadowMapSize: context.quality.shadowMapSize,
      // Each kept pixel averages renderScale² drawn ones: the floor's dither is drawn that much wider.
      ditherScale: renderer.getPixelRatio(),
      frame: SNAPSHOT_STUDIO_FRAME
    });
  } else if (normalizeBoolean(job.output?.transparent, false) || context.theme.background?.type === "transparent") {
    scene.background = null;
    renderer.setClearColor(new THREE.Color("#000000"), 0);
  } else {
    backgroundTexture = colorTextureFromBackground(context.theme.background || {}, firstSize.width, firstSize.height);
    scene.background = backgroundTexture;
  }
  // A family's scene that brings its own lighting (`sceneContract.js`'s `rig`, or `rigFor` the look
  // it wears) is lit by it outside Render, in place of the theme's rig, as the viewer's viewport
  // lights it (`sceneRig.js`): its environment is the scene's, and it is drawn as the rig blends
  // (`renderWithSceneRig`, in `captureModel`).
  const ownRig = photographicConfiguration ? null : sceneRigFor(model.scene, model.look);
  const sceneRig = ownRig ? applySceneRig(THREE, { scene, renderer }, ownRig) : null;
  // PMREM generation is synchronous, but `ready` stays a promise so a failure
  // reaches the caller after it holds a viewport it can dispose.
  const ready = Promise.resolve().then(() => {
    if (sceneRig) return null;
    const resource = context.sceneSettings.view.lighting.enabled
      ? createEnvironmentResource(renderer, studioConfiguration, { size: context.quality.environmentMapSize })
      : keepsAuthoredFinish(model) ? createInspectEnvironmentResource(THREE) : null;
    if (disposed) {
      disposeEnvironmentResource(resource);
      return null;
    }
    environmentResource = resource;
    scene.environment = resource?.texture || null;
    return resource;
  });
  if (!sceneRig && !context.sceneSettings.view.lighting.enabled) applyLighting(
    scene,
    context.theme,
    model.bounds || context.bounds,
    context.sceneScale,
    context.quality.shadowMapSize
  );
  // CAD edges are drawn with screen-space lines; only a CAD model has them (a family's scene
  // from `headlessScene.js` has no edges, which is the viewer's rule for it too).
  if (model.runtime) {
    Object.assign(model.runtime, {
      Line2,
      LineGeometry,
      LineSegments2,
      LineSegmentsGeometry,
      LineMaterial
    });
  }
  scene.add(model.root);
  // `floorBounds` is what a locked camera will frame, for a caller that knows
  // more than this pose does. The stage plane and grid are sized and centred on
  // whatever they are handed, and `model.bounds` is the pose the model happens
  // to be in right now — right for a still, which is posed before it gets here,
  // and wrong for a video, whose camera frames the union across its frames and
  // would otherwise show the grid's edge with the moving part walking off it.
  const floor = addFloor(
    scene,
    viewportOptions.floorBounds || model.bounds || context.bounds,
    { ...context.theme, floor: { enabled: false }, colorMode: context.sceneSettings.appearance },
    context.sceneScale,
    context.displaySettings.guides,
    // A still is sized from rest, as the viewer is; a video keeps its union box for both.
    viewportOptions.floorBounds ? null : restGroundBounds
  );
  const orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 10000);
  const perspectiveCamera = new THREE.PerspectiveCamera(48, firstSize.width / Math.max(firstSize.height, 1), 0.1, 50000);
  const viewport = {
    THREE: _THREE || THREE,
    model,
    scene,
    renderer,
    orthographicCamera,
    perspectiveCamera,
    studioRuntime,
    studioConfiguration,
    // The scene's own rig, up on this stage (`applySceneRig`), or null.
    sceneRig,
    // The grid as drawn, for the depth fit: the viewer fits its near and far planes to it too.
    gridBounds: floor?.gridBounds ?? null,
    context,
    sceneBuildStarted,
    ready,
    dispose() {
      if (disposed) return;
      disposed = true;
      viewport.annotationLayer?.layer.dispose();
      viewport.annotationLayer = null;
      if (viewport.clipRuntime) disposeSectionCaps(viewport.clipRuntime);
      viewport.sceneClip?.dispose();
      model.dispose?.();
      scene.remove?.(model.root);
      sceneRig?.dispose();
      if (studioRuntime) disposePhotographicStudio(studioRuntime);
      if (scene.environment === environmentResource?.texture) scene.environment = null;
      if (scene.background === environmentResource?.texture) scene.background = null;
      disposeEnvironmentResource(environmentResource);
      environmentResource = null;
      disposeSnapshotSceneResources(scene, model.root, [backgroundTexture]);
      backgroundTexture = null;
      renderer.dispose?.();
    }
  };
  const cleanDisposedResources = () => {
    if (disposed) {
      disposeSnapshotSceneResources(scene, model.root, [backgroundTexture]);
    }
  };
  // Observe both outcomes without creating a second unhandled rejection. The
  // original ready promise remains the caller's authoritative render failure.
  Promise.resolve(ready).then(cleanDisposedResources, cleanDisposedResources);
  return viewport;
}

// What the viewer's Clip sync (`syncRuntimeStepClipPlane`) reads of its runtime, over this
// snapshot's model: the plane is measured against the model at rest, as the viewer measures it,
// and the cut is capped as it is there. One per viewport, so its caps are kept and released.
function viewportClipRuntime(viewport) {
  const { model } = viewport;
  viewport.clipRuntime ??= {
    THREE,
    renderer: viewport.renderer,
    scene: viewport.scene,
    cadScene: model,
    modelGroup: model.runtime.modelGroup,
    get displayRecords() { return model.displayRecords; },
    get topologyDisplayEdgeLine() { return model.runtime.topologyDisplayEdgeLine; },
    get zeroPoseBounds() { return model.restBounds; },
    get modelRadius() { return model.runtime.modelRadius; },
    modelBounds: null
  };
  return viewport.clipRuntime;
}

function displayRecordPartIds(displayRecords = []) {
  return Array.from(new Set(
    toArray(displayRecords)
      .map((record) => String(record?.partId || "").trim())
      .filter((partId) => partId && partId !== "__model__")
  ));
}

// `layoutBounds` is what the layout radiates from: the model's REST placement, as the viewer's
// (`useStepExplode`) is, never the bounds as posed. `bounds` is what the returned box falls back to.
function applyViewportExplodedView(viewport, bounds, layoutBounds = bounds) {
  const { context, model, THREE: RuntimeTHREE } = viewport;
  const settings = context.displaySettings?.exploded;
  const THREEImpl = RuntimeTHREE || THREE;
  const resetExplodedView = () => {
    clearExplodedViewRecords(model.displayRecords);
    for (const record of model.displayRecords) {
      applyDisplayRecordTransform(THREEImpl, record);
    }
    model.root?.updateMatrixWorld?.(true);
  };
  if (settings?.enabled !== true) {
    resetExplodedView();
    return bounds;
  }
  // The tree is the only hierarchy a part has: a token names no ancestors.
  const hierarchy = occurrencePathsFromAssemblyRoot(model.meshData?.assemblyRoot);
  const layout = computeExplodedViewLayout(model.displayRecords, layoutBounds, { hierarchy });
  if (!layout.entries.length) {
    resetExplodedView();
    return bounds;
  }
  const amount = clamp(Number(settings.amount ?? 1), 0, 1);
  applyExplodedViewProgress(THREEImpl, layout, amount);
  for (const record of model.displayRecords) {
    applyDisplayRecordTransform(THREEImpl, record);
  }
  model.root?.updateMatrixWorld?.(true);
  return explodedViewBounds(layout, bounds, amount);
}

function syncViewportTopologyDisplayEdges(viewport) {
  const { context, model } = viewport;
  const renderedPartIds = displayRecordPartIds(model.displayRecords);
  const edgeRuntimes = resolveTopologyDisplayEdgeRuntimes({
    selectorRuntime: context.selectorRuntime,
    displayRecords: model.displayRecords
  });
  syncTopologyDisplayEdgeLine(
    model.runtime,
    edgeRuntimes.selectorRuntime,
    {
      visible: context.topologyDisplayEdgesVisible,
      edgeSettings: renderedPartIds.length
        ? {
            ...context.edgeSettings,
            includePartIds: renderedPartIds
          }
        : context.edgeSettings,
      viewerTheme: model.runtime?.baseTheme,
      displayRecords: model.displayRecords
    }
  );
}


// The job's annotation (`job.annotation`, the ink a person drew with the viewer's Annotate tool), drawn over this
// output with the viewer's own code (`annotation.js`): each mark where it was drawn, in model
// coordinates, cut by the same clip planes. Its ink is as heavy against this output's height as it was against a
// viewer `ANNOTATION_REFERENCE_HEIGHT_PX` tall, so one layer serves every output of that height and is
// rebuilt only for an output of another.
function syncViewportAnnotation(viewport, job, { height }) {
  if (job.annotation == null) return;
  const lineScale = (height / ANNOTATION_REFERENCE_HEIGHT_PX) * (viewport.renderer.getPixelRatio?.() || 1);
  if (viewport.annotationLayer?.lineScale !== lineScale) {
    viewport.annotationLayer?.layer.dispose();
    const layer = createAnnotationLayer({ THREE, Line2, LineGeometry, LineMaterial }, normalizeAnnotation(job.annotation), { lineScale });
    viewport.scene.add(layer.group);
    viewport.annotationLayer = { layer, lineScale };
  }
  if (viewport.renderer) viewport.renderer.localClippingEnabled = true;
  viewport.annotationLayer.layer.place(viewport.clipRuntime?.activeClipPlanes || viewport.sceneClip?.planes || []);
}

export async function captureModel(viewport, captureOptions = {}) {
  const job = captureOptions.job || {};
  const context = viewport.context || renderJobContext(viewport.model.meshData, job);
  const meshData = viewport.model.meshData;
  const {
    mode,
    sceneScale,
    bounds,
    outputs,
    warnings
  } = context;
  const modelBounds = viewport.model?.bounds || meshData?.bounds || bounds;

  if (mode === "list") {
    if (typeof viewport.model.listParts !== "function") {
      throw new Error("--mode list lists a GLB, mesh or robot scene here; cadgen lists a STEP model's parts itself");
    }
    return {
      ok: true,
      mode,
      parts: listRenderableParts(viewport.model.listParts()),
      bounds: roundedBounds(modelBounds) || modelBounds,
      warnings
    };
  }

  const stageTimings = captureOptions.stageTimings;
  const readyStarted = performance.now();
  await viewport.ready;
  if (stageTimings) {
    stageTimings.waitViewportMs = Math.round(performance.now() - readyStarted);
    stageTimings.outputs = [];
  }
  const sceneBuildMs = performance.now() - viewport.sceneBuildStarted;
  const padding = framePadding(job);
  const renderedOutputs = [];
  const renderStarted = performance.now();
  for (const output of outputs) {
    const outputTimings = stageTimings ? { path: String(output.path || "") } : null;
    let stageStarted = performance.now();
    const parameters = stepParametersForSnapshotOutput(output, job);
    const { width, height } = outputSize(output, job);
    viewport.renderer.setSize(width, height, false);
    // ONE update per output. `modelState` is a patch a caller needs applied in
    // the same pass -- a video's `callbacks.animation` for this frame -- because
    // applying it separately first means the clip evaluator and the effects pass
    // over every display record run twice for one image.
    const posedBounds = viewport.model.update({
      stepParameters: parameters,
      ...(captureOptions.modelState || null)
    }).bounds;
    // `frameBounds` locks what the camera frames on. A still frames the model
    // it just posed, which is right for one image and wrong for a sequence:
    // every frame of a video would re-fit to that frame's pose and the camera
    // would breathe as the model moves. A video passes the union across its
    // frames, computed once (headlessRenderEntry sequenceFrameBounds).
    const baseOutputBounds = captureOptions.frameBounds || posedBounds;
    // The model at rest (a package's declared box when it has one): what the viewer sizes the
    // ground from and radiates an exploded view from, whatever the pose.
    const restBounds = viewport.model.restBounds || null;
    let outputBounds = baseOutputBounds;
    // The exploded view, topology edges and their screen-space line widths are a CAD
    // model's (`buildModel`'s runtime). A family's scene has no edges; it explodes and is cut
    // through the scene contract, as the viewer's viewport explodes and cuts it
    // (`sceneExplode.js`, `sceneClip.js`), under the features the job was resolved with.
    if (!viewport.model.runtime) {
      const familyScene = viewport.model.scene;
      const exploded = context.displaySettings.exploded;
      if (familyScene.setExplode) {
        familyScene.setExplode(exploded?.enabled === true ? Number(exploded.amount) || 0 : 0);
        outputBounds = captureOptions.frameBounds || familyScene.bounds;
      }
      viewport.sceneClip ??= createSceneClip(THREE, { stage: viewport.scene });
      viewport.sceneClip.sync(familyScene, context.displaySettings.clip);
    } else {
      outputBounds = applyViewportExplodedView(viewport, baseOutputBounds, restBounds || baseOutputBounds);
      syncViewportTopologyDisplayEdges(viewport);
      // The Clip tool cuts and caps the model as the viewer's does, on every material, edge set and
      // the topology edges drawn just above.
      const clipRuntime = viewportClipRuntime(viewport);
      clipRuntime.modelBounds = outputBounds;
      syncRuntimeStepClipPlane(clipRuntime, context.displaySettings.clip);
      // Device pixels: renderScale is the renderer's pixel ratio, so a
      // supersampled drawing buffer keeps `thickness` in drawing-buffer units
      // before the final PNG is resampled to this output's requested dimensions.
      const lineResolution = screenSpaceLineDeviceResolution(viewport.renderer, width, height);
      syncScreenSpaceLineMaterialResolution(
        viewport.model.runtime.screenSpaceLineMaterials,
        lineResolution.width,
        lineResolution.height
      );
    }
    if (outputTimings) outputTimings.updateModelMs = Math.round(performance.now() - stageStarted);
    stageStarted = performance.now();
    const cameraSpec = resolveOutputCameraSpec(context, output.camera || null);
    const outputProjection = resolveOutputCameraProjection(context, cameraSpec);
    const usePerspectiveCamera = outputProjection === CAMERA_PROJECTION.PERSPECTIVE;
    const cameraView = usePerspectiveCamera ? null : resolveView(cameraSpec);
    const useTightFrame = !captureOptions.frameBounds && tightFrameEnabled(job);
    if (usePerspectiveCamera && useTightFrame) {
      viewport.scene.updateMatrixWorld(true);
    }
    const resolvedCamera = usePerspectiveCamera
      ? fitPerspectiveCamera(viewport.perspectiveCamera, cameraSpec, outputBounds, width, height, {
          framePoints: useTightFrame ? visibleGeometryWorldPoints(viewport.model.displayRecords) : null,
          padding,
          sceneScale
        })
      : fitCamera(viewport.orthographicCamera, cameraView, outputBounds, width, height, null, padding, sceneScale);
    const renderCamera = usePerspectiveCamera ? viewport.perspectiveCamera : viewport.orthographicCamera;
    // The tight frame is a per-POSE refinement: it re-fits to the vertices the
    // records project right now. Running it on every frame of a sequence is the
    // breathing `frameBounds` exists to stop, and there is no one pose to run it
    // against, so a locked frame keeps the bounds fit and skips it.
    if (!usePerspectiveCamera && useTightFrame) {
      viewport.scene.updateMatrixWorld(true);
      applyTightOrthographicFrame(renderCamera, viewport.model.displayRecords, width, height, padding, cameraView?.zoom);
    }
    // Every preset draws with ordinary depth, fitted to what this output frames, as the viewer
    // fits its own every frame (`fitCameraDepthToBounds` in useViewerRuntime.js).
    const fitDepth = () => fitCameraDepthToBounds(renderCamera, outputBounds, {
      placedObjects: viewport.model.runtime ? viewport.model.displayRecords : viewport.model.placedObjects(),
      modelGroup: viewport.model.runtime?.modelGroup ?? null,
      groundZ: viewport.studioRuntime?.photographicStudio?.ground?.position.z ?? null,
      gridBounds: viewport.gridBounds ?? null,
      pivot: resolvedCamera?.target ?? null
    });
    if (!viewport.studioRuntime) fitDepth();
    if (outputTimings) outputTimings.frameCameraMs = Math.round(performance.now() - stageStarted);
    if (viewport.studioRuntime) {
      stageStarted = performance.now();
      applyPhotographicStudio(THREE, viewport.studioRuntime, viewport.studioConfiguration, {
        bounds: outputBounds,
        // The floor and its contact shadow are sized and centred from the REST placement, as the
        // viewer's are (and as `renderModel` placed them), so an exploded view or a pose never
        // rescales or slides them; a video's locked frame keeps its union box for both.
        groundBounds: captureOptions.frameBounds ? null : restBounds,
        shadowMapSize: context.quality.shadowMapSize,
        ditherScale: viewport.renderer.getPixelRatio?.() ?? 1,
        frame: SNAPSHOT_STUDIO_FRAME
      });
      fitDepth();
      if (outputTimings) outputTimings.prepareStudioMs = Math.round(performance.now() - stageStarted);
    }
    stageStarted = performance.now();
    syncViewportAnnotation(viewport, job, { height });
    // Render is drawn through its studio's frame, every sample of it; anything else is one draw, as
    // the scene's own rig blends it.
    const studioFrame = viewport.studioRuntime?.photographicStudio?.frame || null;
    if (studioFrame) {
      studioFrame.renderStill(viewport.renderer, viewport.scene, renderCamera, {
        samples: snapshotStudioSamples({
          video: Boolean(captureOptions.frameBounds),
          softwareRendering: isSoftwareWebGlRenderer(viewport.renderer)
        })
      });
    } else {
      renderWithSceneRig(viewport.sceneRig, viewport.renderer, viewport.scene, renderCamera);
    }
    if (outputTimings) outputTimings.drawSubmitMs = Math.round(performance.now() - stageStarted);
    // WebGL submission can return before GPU completion. PNG readback may
    // wait for that work, so this is image readback/encoding, not pure CPU PNG.
    stageStarted = performance.now();
    const viewLabel = String(output.viewLabel || output.label || resolvedCamera.name || "").toUpperCase();
    const dataUrl = rendererDataUrlWithOptionalLabel(viewport.renderer, viewLabel, job, { width, height });
    if (outputTimings) {
      outputTimings.encodeImageMs = Math.round(performance.now() - stageStarted);
      stageTimings.outputs.push(outputTimings);
    }
    renderedOutputs.push({
      path: String(output.path || ""),
      camera: resolvedCamera.name,
      // Authoritative per-output echo from the canonical camera specification.
      projection: outputProjection,
      width,
      height,
      mimeType: "image/png",
      dataUrl
    });
  }
  const renderMs = performance.now() - renderStarted;
  return {
    ok: true,
    mode,
    // Echo the display and canonical camera state actually applied.
    displayMode: context.displayMode,
    projection: context.projection,
    quality: context.quality.id,
    outputs: renderedOutputs,
    timings: {
      sceneBuildMs,
      renderMs,
      meshCount: viewport.model.displayRecords.length || toArray(meshData?.parts).length || 1
    },
    warnings
  };
}

export async function renderMeshJob(meshData, job = {}) {
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, meshData, modelOptionsForRenderJob(context, job));
  if (context.mode === "list") {
    try {
      return await captureModel({ model, context }, { job });
    } finally {
      model.dispose();
    }
  }
  const viewport = renderModel(THREE, model, { job, context });
  try {
    return await captureModel(viewport, { job });
  } finally {
    viewport.dispose();
  }
}
