import * as THREE from "three";

import { DEFAULT_RENDER_LIGHTING } from "./sceneSettings.js";
import {
  PHOTOGRAPHIC_STUDIO_CARD_RADIANCE,
  PHOTOGRAPHIC_STUDIO_FILL_DIRECTION,
  PHOTOGRAPHIC_STUDIO_KEY_DIRECTION,
  PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE
} from "./photographicStudioRig.js";

export const PROCEDURAL_STUDIO_ENVIRONMENT_ID = "photographic-softbox";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function finite(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function proceduralEnvironmentSize(value) {
  const numeric = finite(value, 256);
  return Math.min(Math.max(2 ** Math.round(Math.log2(Math.max(numeric, 1))), 64), 1024);
}

function lightingConfiguration(configuration = {}) {
  const lighting = configuration?.lighting || {};
  return {
    size: clamp(finite(lighting.size, DEFAULT_RENDER_LIGHTING.size), 0.25, 3),
    fill: clamp(finite(lighting.fill, DEFAULT_RENDER_LIGHTING.fill), 0, 1)
  };
}

export function environmentResourceIdentity(configuration = {}, { size = 256 } = {}) {
  const lighting = lightingConfiguration(configuration);
  return `${PROCEDURAL_STUDIO_ENVIRONMENT_ID}:${JSON.stringify([
    lighting.size,
    lighting.fill,
    proceduralEnvironmentSize(size)
  ])}`;
}

function card(scene, {
  name,
  direction,
  width,
  height,
  intensity
}) {
  if (!(intensity > 0)) return null;
  const material = new THREE.MeshBasicMaterial({
    color: new THREE.Color(intensity, intensity, intensity),
    side: THREE.DoubleSide,
    toneMapped: false
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material);
  mesh.name = name;
  mesh.position.copy(direction).normalize().multiplyScalar(6);
  mesh.lookAt(0, 0, 0);
  mesh.updateMatrixWorld(true);
  scene.add(mesh);
  return mesh;
}

/**
 * Build the normalized HDR source scene used by PMREM. It contains a bright
 * neutral key card and an opposing fill card. Their directions match the
 * photographic direct-light rig; scene.environmentRotation rotates both at
 * runtime without rebuilding this resource.
 */
export function createStudioEnvironmentScene(configuration = {}) {
  const lighting = lightingConfiguration(configuration);
  // Emissive radiance is inversely proportional to card area, so changing the
  // apparent softbox size changes highlight width without changing total flux.
  const cardRadiance = PHOTOGRAPHIC_STUDIO_CARD_RADIANCE / (lighting.size * lighting.size);
  const scene = new THREE.Scene();
  scene.name = "cadgen-photographic-environment";
  const roomColor = new THREE.Color().setScalar(PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE);
  scene.background = roomColor;

  const room = new THREE.Mesh(
    new THREE.BoxGeometry(30, 30, 30),
    new THREE.MeshBasicMaterial({
      color: roomColor,
      side: THREE.BackSide,
      toneMapped: false
    })
  );
  room.name = "studio-room";
  scene.add(room);

  card(scene, {
    name: "studio-key-card",
    direction: new THREE.Vector3(...PHOTOGRAPHIC_STUDIO_KEY_DIRECTION),
    width: 2.5 * lighting.size,
    height: 3.6 * lighting.size,
    intensity: cardRadiance
  });
  card(scene, {
    name: "studio-fill-card",
    direction: new THREE.Vector3(...PHOTOGRAPHIC_STUDIO_FILL_DIRECTION),
    width: 3.2 * lighting.size,
    height: 4.2 * lighting.size,
    intensity: cardRadiance * lighting.fill
  });
  return scene;
}

function disposeScene(scene) {
  scene?.traverse?.((object) => {
    object.geometry?.dispose?.();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) material?.dispose?.();
  });
}

function ownedEnvironmentResource(identity, target) {
  let disposed = false;
  return {
    identity,
    texture: target.texture,
    dispose() {
      if (disposed) return;
      disposed = true;
      target.dispose?.();
    }
  };
}

/**
 * Create a caller-owned PMREM resource. Rotation is intentionally absent from
 * its identity: callers apply it through scene.environmentRotation so rotating
 * the studio remains a cheap live update.
 */
export async function createEnvironmentResource(renderer, configuration = {}, {
  size = 256
} = {}) {
  if (!renderer) {
    throw new Error("A WebGL renderer is required for the photographic studio environment");
  }
  const identity = environmentResourceIdentity(configuration, { size });
  const environmentScene = createStudioEnvironmentScene(configuration);
  const generator = new THREE.PMREMGenerator(renderer);
  try {
    const target = generator.fromScene(environmentScene, 0, 0.1, 100, {
      size: proceduralEnvironmentSize(size)
    });
    target.texture.name = PROCEDURAL_STUDIO_ENVIRONMENT_ID;
    return ownedEnvironmentResource(identity, target);
  } finally {
    disposeScene(environmentScene);
    generator.dispose();
  }
}

export function disposeEnvironmentResource(resource) {
  resource?.dispose?.();
}
