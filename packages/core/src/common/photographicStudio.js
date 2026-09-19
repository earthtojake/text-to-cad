import { clamp, finiteOr } from "./numbers.js";
import {
  DEFAULT_RENDER_BACKDROP,
  DEFAULT_RENDER_LIGHTING
} from "./sceneSettings.js";
import {
  PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT,
  PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY,
  PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX,
  PHOTOGRAPHIC_STUDIO_KEY_DIRECTION,
  PHOTOGRAPHIC_STUDIO_KEY_ILLUMINANCE,
  PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER
} from "./photographicStudioRig.js";

function component(value, axis, fallback) {
  if (Array.isArray(value)) return finiteOr(value[axis], fallback);
  const key = ["x", "y", "z"][axis];
  return finiteOr(value?.[key], fallback);
}

function resolveBounds(bounds, fallbackRadius = 1) {
  const safeRadius = Math.max(finiteOr(fallbackRadius, 1), 1e-6);
  const min = [0, 1, 2].map((axis) => component(bounds?.min, axis, -safeRadius));
  const max = [0, 1, 2].map((axis) => component(bounds?.max, axis, safeRadius));
  const valid = min.every(Number.isFinite) && max.every(Number.isFinite)
    && max.every((value, axis) => value >= min[axis]);
  if (!valid) {
    return {
      min: [-safeRadius, -safeRadius, -safeRadius],
      max: [safeRadius, safeRadius, safeRadius],
      center: [0, 0, 0],
      radius: safeRadius
    };
  }
  const center = min.map((value, axis) => (value + max[axis]) / 2);
  const radius = Math.max(
    Math.hypot(...max.map((value, axis) => (value - min[axis]) / 2)),
    1e-6
  );
  return { min, max, center, radius };
}

function resolvedConfiguration(configuration = {}) {
  const lighting = configuration.lighting || {};
  const backdrop = configuration.backdrop || {};
  return {
    exposure: clamp(finiteOr(configuration.exposure, 0), -5, 5),
    lighting: {
      rotation: clamp(finiteOr(lighting.rotation, DEFAULT_RENDER_LIGHTING.rotation), -180, 180),
      size: clamp(finiteOr(lighting.size, DEFAULT_RENDER_LIGHTING.size), 0.25, 3),
      fill: clamp(finiteOr(lighting.fill, DEFAULT_RENDER_LIGHTING.fill), 0, 1)
    },
    backdrop: {
      color: typeof backdrop.color === "string" ? backdrop.color : "#e7e7e5",
      transparent: typeof backdrop.transparent === "boolean"
        ? backdrop.transparent
        : DEFAULT_RENDER_BACKDROP.transparent,
      ground: typeof backdrop.ground === "boolean"
        ? backdrop.ground
        : DEFAULT_RENDER_BACKDROP.ground,
      groundPlacement: backdrop.groundPlacement ?? DEFAULT_RENDER_BACKDROP.groundPlacement
    }
  };
}

function disposeMaterial(material) {
  if (Array.isArray(material)) {
    material.forEach((entry) => entry?.dispose?.());
  } else {
    material?.dispose?.();
  }
}

function disposeGround(state) {
  if (!state.ground) return;
  state.group.remove(state.ground);
  state.ground.geometry?.dispose?.();
  disposeMaterial(state.ground.material);
  state.ground = null;
  state.groundKind = null;
}

function updatePhysicalGroundColor(material, color) {
  material.color.set(color).multiplyScalar(PHOTOGRAPHIC_STUDIO_GROUND_DIFFUSE_WEIGHT);
  material.emissive.set(color);
  // A tiny neutral component gives near-black backdrop colors enough linear
  // energy to remain visible without perceptibly cooling ordinary colors.
  material.emissive.r += (1 - material.emissive.r)
    * PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX;
  material.emissive.g += (1 - material.emissive.g)
    * PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX;
  material.emissive.b += (1 - material.emissive.b)
    * PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_NEUTRAL_MIX;
}

function createState(THREE, runtime) {
  const group = new THREE.Group();
  group.name = "cadgen-photographic-studio";

  const keyLight = new THREE.SpotLight(0xffffff, 1);
  keyLight.name = "studio-key-softbox";
  keyLight.decay = 2;
  keyLight.castShadow = true;

  const target = new THREE.Object3D();
  target.name = "studio-key-target";
  keyLight.target = target;
  group.add(keyLight, target);
  runtime.scene.add(group);

  const initialClearColor = new THREE.Color();
  runtime.renderer.getClearColor?.(initialClearColor);
  return {
    group,
    keyLight,
    target,
    shadowMapSize: null,
    ground: null,
    groundKind: null,
    original: {
      toneMapping: runtime.renderer.toneMapping,
      toneMappingExposure: runtime.renderer.toneMappingExposure,
      outputColorSpace: runtime.renderer.outputColorSpace,
      shadowEnabled: runtime.renderer.shadowMap?.enabled,
      shadowType: runtime.renderer.shadowMap?.type,
      background: runtime.scene.background,
      environmentIntensity: runtime.scene.environmentIntensity,
      environmentRotation: runtime.scene.environmentRotation?.clone?.(),
      clearColor: initialClearColor,
      clearAlpha: runtime.renderer.getClearAlpha?.()
    }
  };
}

function updateGround(THREE, state, configuration, bounds, sceneScale) {
  if (!configuration.backdrop.ground) {
    disposeGround(state);
    return;
  }
  const kind = configuration.backdrop.transparent ? "shadow" : "physical";
  if (!state.ground || state.groundKind !== kind) {
    disposeGround(state);
    const material = kind === "shadow"
      ? new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.3, transparent: true })
      : new THREE.MeshStandardMaterial({
        color: configuration.backdrop.color,
        emissive: configuration.backdrop.color,
        emissiveIntensity: PHOTOGRAPHIC_STUDIO_GROUND_EMISSIVE_INTENSITY,
        roughness: 0.88,
        metalness: 0,
        envMapIntensity: 0.22,
        transparent: true,
        opacity: 0.3
      });
    // Keep both the physical floor and transparent-background shadow catcher
    // from hiding geometry or fighting coplanar faces at the exact ground Z.
    material.depthWrite = false;
    material.polygonOffset = true;
    material.polygonOffsetFactor = 1;
    material.polygonOffsetUnits = 1;
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
    ground.name = "studio-ground";
    ground.receiveShadow = true;
    ground.renderOrder = -3;
    state.group.add(ground);
    state.ground = ground;
    state.groundKind = kind;
  }

  if (state.groundKind === "physical") {
    updatePhysicalGroundColor(state.ground.material, configuration.backdrop.color);
  }
  const minimumSize = sceneScale === "urdf" ? 0.5 : 100;
  const spanX = bounds.max[0] - bounds.min[0];
  const spanY = bounds.max[1] - bounds.min[1];
  const stageSize = Math.max(
    spanX,
    spanY,
    bounds.radius * PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER,
    minimumSize
  );
  // Geometry keeps its authored coordinates: the PLANE moves, never the model.
  // It sits at the model's lowest point by default, so nothing is ever hidden
  // under the floor; "origin" pins it to the document's own Z=0 instead.
  const groundZ = configuration.backdrop.groundPlacement === "origin" ? 0 : bounds.min[2];
  state.ground.scale.set(stageSize, stageSize, 1);
  state.ground.position.set(bounds.center[0], bounds.center[1], groundZ);
  state.ground.updateMatrixWorld(true);
}

function updateKeyLight(THREE, state, configuration, bounds, shadowMapSize, softwareRendering) {
  const rotation = THREE.MathUtils.degToRad(configuration.lighting.rotation);
  const direction = new THREE.Vector3(...PHOTOGRAPHIC_STUDIO_KEY_DIRECTION).normalize();
  direction.applyAxisAngle(new THREE.Vector3(0, 0, 1), rotation);

  const distance = Math.max(bounds.radius * 5, 1e-4);
  const center = new THREE.Vector3(...bounds.center);
  state.keyLight.position.copy(center).addScaledVector(direction, distance);
  state.target.position.copy(center);
  state.keyLight.angle = clamp(Math.atan2(bounds.radius * 1.35, distance), 0.18, 0.65);
  state.keyLight.penumbra = clamp(0.48 + configuration.lighting.size * 0.1, 0.5, 0.78);
  // SpotLight intensity is candela. Scaling it by distance squared keeps the
  // incident key illumination stable for millimetre CAD and metre-scale URDF.
  state.keyLight.intensity = PHOTOGRAPHIC_STUDIO_KEY_ILLUMINANCE * distance * distance;
  state.keyLight.castShadow = !softwareRendering;

  const size = Math.round(clamp(finiteOr(shadowMapSize, 2048), 256, 4096));
  if (state.shadowMapSize !== size) {
    state.keyLight.shadow.map?.dispose?.();
    state.keyLight.shadow.map = null;
    state.keyLight.shadow.mapPass?.dispose?.();
    state.keyLight.shadow.mapPass = null;
    state.shadowMapSize = size;
  }
  state.keyLight.shadow.mapSize.set(size, size);
  state.keyLight.shadow.camera.near = Math.max(distance - bounds.radius * 2, distance * 0.05, 1e-5);
  state.keyLight.shadow.camera.far = Math.max(distance + bounds.radius * 3, state.keyLight.shadow.camera.near * 2);
  state.keyLight.shadow.camera.fov = THREE.MathUtils.radToDeg(state.keyLight.angle * 2);
  // Offset receivers by roughly one shadow texel in world space. A fixed
  // model-relative offset was too small for the fitted spotlight frustum and
  // produced diagonal self-shadowing bands on otherwise smooth CAD walls.
  // Deriving this from the cone width also lets Final's larger map retain
  // tighter contact than Preview without using a scene-unit-specific value.
  const shadowWorldSpan = 2 * distance * Math.tan(state.keyLight.angle);
  state.keyLight.shadow.bias = -0.00012;
  state.keyLight.shadow.normalBias = Math.max(shadowWorldSpan / size, 1e-6);
  state.keyLight.shadow.radius = clamp(0.65 + configuration.lighting.size * 0.45, 0.75, 2);
  state.keyLight.shadow.camera.updateProjectionMatrix?.();
  state.keyLight.shadow.needsUpdate = true;
  state.keyLight.updateMatrixWorld(true);
  state.target.updateMatrixWorld(true);
}

function updateRendererAndScene(THREE, runtime, state, configuration) {
  const { renderer, scene } = runtime;
  // Product rendering needs authored paint colors and bright whites to remain
  // distinct. Filmic compression made ordinary CAD albedos look pastel/gray.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 2 ** configuration.exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  if (renderer.shadowMap) {
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
  }

  scene.environmentIntensity = 1;
  scene.environmentRotation?.set?.(0, 0, THREE.MathUtils.degToRad(configuration.lighting.rotation));
  if (configuration.backdrop.transparent) {
    scene.background = null;
    renderer.setClearColor?.(new THREE.Color(configuration.backdrop.color), 0);
  } else {
    const color = new THREE.Color(configuration.backdrop.color);
    scene.background = color;
    renderer.setClearColor?.(color, 1);
  }
  state.keyLight.visible = true;
}

/**
 * Apply the synchronous, model-scaled half of the photographic Render rig.
 * The caller separately owns the PMREM returned by createEnvironmentResource.
 * Repeated calls update the existing objects, so exposure, rotation, framing,
 * and backdrop edits do not rebuild model geometry or scene state.
 */
export function applyPhotographicStudio(THREE, runtime, configuration = {}, {
  bounds = runtime?.modelBounds,
  sceneScale = "cad",
  shadowMapSize = 2048
} = {}) {
  if (!THREE || !runtime?.scene || !runtime?.renderer) {
    throw new Error("applyPhotographicStudio requires THREE and a runtime with scene and renderer");
  }
  if (runtime.renderer.capabilities?.logarithmicDepthBuffer === true) {
    throw new Error("Photographic Render requires a renderer created without logarithmicDepthBuffer so contact shadows remain visible");
  }
  const resolved = resolvedConfiguration(configuration);
  const state = runtime.photographicStudio || createState(THREE, runtime);
  runtime.photographicStudio = state;
  const resolvedBounds = resolveBounds(bounds, runtime.modelRadius);

  updateRendererAndScene(THREE, runtime, state, resolved);
  updateKeyLight(
    THREE,
    state,
    resolved,
    resolvedBounds,
    shadowMapSize,
    runtime.softwareRendering === true
  );
  updateGround(THREE, state, resolved, resolvedBounds, sceneScale);

  runtime.invalidateShadows?.();
  runtime.requestRender?.();
  return state;
}

export function disposePhotographicStudio(runtime) {
  const state = runtime?.photographicStudio;
  if (!state) return;
  disposeGround(state);
  state.keyLight.shadow?.map?.dispose?.();
  state.keyLight.shadow.map = null;
  runtime.scene?.remove?.(state.group);

  const original = state.original;
  if (runtime.renderer) {
    runtime.renderer.toneMapping = original.toneMapping;
    runtime.renderer.toneMappingExposure = original.toneMappingExposure;
    runtime.renderer.outputColorSpace = original.outputColorSpace;
    if (runtime.renderer.shadowMap) {
      runtime.renderer.shadowMap.enabled = original.shadowEnabled;
      runtime.renderer.shadowMap.type = original.shadowType;
    }
    if (original.clearColor && typeof original.clearAlpha === "number") {
      runtime.renderer.setClearColor?.(original.clearColor, original.clearAlpha);
    }
  }
  if (runtime.scene) {
    runtime.scene.background = original.background;
    runtime.scene.environmentIntensity = original.environmentIntensity;
    if (original.environmentRotation && runtime.scene.environmentRotation?.copy) {
      runtime.scene.environmentRotation.copy(original.environmentRotation);
    }
  }
  runtime.photographicStudio = null;
}
