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
      enabled: lighting.enabled !== false,
      rotation: clamp(finiteOr(lighting.rotation, DEFAULT_RENDER_LIGHTING.rotation), -180, 180),
      size: clamp(finiteOr(lighting.size, DEFAULT_RENDER_LIGHTING.size), 0.25, 3),
      fill: clamp(finiteOr(lighting.fill, DEFAULT_RENDER_LIGHTING.fill), 0, 1)
    },
    backdrop: {
      ...(Object.hasOwn(backdrop, "opacity") ? { opacity: clamp(finiteOr(backdrop.opacity, 1), 0, 1) } : {}),
      color: typeof backdrop.color === "string" ? backdrop.color : "#ffffff",
      transparent: typeof backdrop.transparent === "boolean"
        ? backdrop.transparent
        : DEFAULT_RENDER_BACKDROP.transparent,
      ground: typeof backdrop.ground === "boolean"
        ? backdrop.ground
        : DEFAULT_RENDER_BACKDROP.ground,
      groundPlacement: backdrop.groundPlacement ?? DEFAULT_RENDER_BACKDROP.groundPlacement,
      groundColor: backdrop.groundColor ?? backdrop.color ?? "#e7e7e5",
      groundOpacity: clamp(finiteOr(backdrop.groundOpacity, DEFAULT_RENDER_BACKDROP.groundOpacity), 0, 1)
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

function updateGround(THREE, state, configuration, bounds, sceneScale, extentBounds = bounds) {
  if (!configuration.backdrop.ground) {
    disposeGround(state);
    return;
  }
  // Grouped floor is independent of background alpha. Preserve the historical
  // shadow-catcher behavior only for callers of the legacy studio recipe.
  const kind = configuration.backdrop.transparent && !Object.hasOwn(configuration.backdrop, "opacity") ? "shadow" : "physical";
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
        opacity: configuration.backdrop.groundOpacity
      });
    // Keep both the physical floor and transparent-background shadow catcher
    // from hiding geometry or fighting coplanar faces at the exact ground Z.
    material.depthWrite = false;
    // One translucent surface from either side. A closed blended box would
    // stack entry/exit opacity and expose extra boundaries during orbiting.
    material.side = THREE.DoubleSide;
    material.forceSinglePass = true;
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
    updatePhysicalGroundColor(state.ground.material, configuration.backdrop.groundColor);
  }
  state.ground.material.opacity = configuration.backdrop.groundOpacity;
  const minimumSize = sceneScale === "urdf" ? 0.5 : 100;
  // The plane's SIZE and where it is centred come from `extentBounds`: a caller whose
  // model moves hands over its rest placement, so posing or playing never rescales
  // or slides the floor under it. Only the plane's height follows the model.
  const spanX = extentBounds.max[0] - extentBounds.min[0];
  const spanY = extentBounds.max[1] - extentBounds.min[1];
  const stageSize = Math.max(
    spanX,
    spanY,
    extentBounds.radius * PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER,
    minimumSize
  );
  // Geometry keeps its authored coordinates: the PLANE moves, never the model.
  // The default pins the floor to the document's Z=0; "lowest" follows the
  // current bounds. Neither placement clips the model.
  const groundZ = configuration.backdrop.groundPlacement === "origin" ? 0 : bounds.min[2];
  state.ground.scale.set(stageSize, stageSize, 1);
  state.ground.position.set(extentBounds.center[0], extentBounds.center[1], groundZ);
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
  renderer.toneMapping = configuration.lighting.enabled ? THREE.NeutralToneMapping : state.original.toneMapping;
  renderer.toneMappingExposure = configuration.lighting.enabled ? 2 ** configuration.exposure : state.original.toneMappingExposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  if (renderer.shadowMap) {
    renderer.shadowMap.enabled = configuration.lighting.enabled;
    renderer.shadowMap.type = THREE.PCFShadowMap;
  }

  if (configuration.lighting.enabled) {
    scene.environmentIntensity = 1;
    scene.environmentRotation?.set?.(0, 0, THREE.MathUtils.degToRad(configuration.lighting.rotation));
  } else {
    // The neutral scene owns its reflection fill. Its intensity can change
    // after the studio was created (for example when authored materials load),
    // so a background/floor update must not restore that stale initial value.
    if (state.original.environmentRotation) scene.environmentRotation?.copy?.(state.original.environmentRotation);
  }
  const alpha = configuration.backdrop.opacity ?? (configuration.backdrop.transparent ? 0 : 1);
  const color = new THREE.Color(configuration.backdrop.color);
  // A Scene.background Color is always opaque; clear alpha owns fractional
  // canvas alpha so the viewer checkerboard and PNG export agree exactly.
  scene.background = alpha < 1 ? null : color;
  renderer.setClearColor?.(color, alpha);
  state.keyLight.visible = configuration.lighting.enabled;
}

/**
 * Apply the synchronous, model-scaled half of the photographic Render rig.
 * The caller separately owns the PMREM returned by createEnvironmentResource.
 * Repeated calls update the existing objects, so exposure, rotation, framing,
 * and backdrop edits do not rebuild model geometry or scene state.
 *
 * `bounds` is the model as it is now: the key light, its shadow and a floor kept at
 * the lowest point follow it. `groundBounds` (default: `bounds`) is what the floor's
 * size and centre are taken from; a viewer passes the model's REST placement.
 */
export function applyPhotographicStudio(THREE, runtime, configuration = {}, {
  bounds = runtime?.modelBounds,
  groundBounds = null,
  sceneScale = "cad",
  shadowMapSize = 2048
} = {}) {
  if (!THREE || !runtime?.scene || !runtime?.renderer) {
    throw new Error("applyPhotographicStudio requires THREE and a runtime with scene and renderer");
  }
  if (configuration.lighting?.enabled !== false && runtime.renderer.capabilities?.logarithmicDepthBuffer === true) {
    throw new Error("Photographic Render requires a renderer created without logarithmicDepthBuffer so contact shadows remain visible");
  }
  const resolved = resolvedConfiguration(configuration);
  const state = runtime.photographicStudio || createState(THREE, runtime);
  runtime.photographicStudio = state;
  const resolvedBounds = resolveBounds(bounds, runtime.modelRadius);

  updateRendererAndScene(THREE, runtime, state, resolved);
  if (resolved.lighting.enabled) updateKeyLight(
    THREE,
    state,
    resolved,
    resolvedBounds,
    shadowMapSize,
    runtime.softwareRendering === true
  );
  updateGround(THREE, state, resolved, resolvedBounds, sceneScale,
    groundBounds ? resolveBounds(groundBounds, runtime.modelRadius) : resolvedBounds);

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
