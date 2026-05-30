// Load a modal GLB (morph target + baked clip per mode, frequencies + material
// damping in mesh extras) into a three.js group with the morph mesh intact.
//
// The main viewer's GLB path flattens geometry to static mesh-data (dropping
// morph targets and animations). Modal GLBs need the live morph mesh, so the
// workbench branches to this loader, which keeps the GLTFLoader scene and pulls
// out the mode metadata the modal runtime needs.

import { extractModalModes } from "./modalAnimation.js";

// True when a parsed glTF JSON describes a modal model (mesh extras carry the
// per-mode metadata written by `cadpy_fea modal --modal-glb`).
export function isModalGltfJson(json) {
  const meshes = json && Array.isArray(json.meshes) ? json.meshes : [];
  return meshes.some(
    (m) => m && m.extras && Array.isArray(m.extras.modes) && m.extras.modes.length > 0,
  );
}

function findMorphMesh(root) {
  let found = null;
  root?.traverse?.((obj) => {
    if (!found && obj.isMesh && Array.isArray(obj.morphTargetInfluences) && obj.morphTargetInfluences.length) {
      found = obj;
    }
  });
  return found;
}

function modalMeshExtras(gltf) {
  const meshes = gltf?.parser?.json?.meshes;
  if (Array.isArray(meshes)) {
    const withModes = meshes.find((m) => m?.extras && Array.isArray(m.extras.modes));
    if (withModes) return withModes.extras;
  }
  // Fallback: three copies mesh extras to userData on the loaded mesh.
  const mesh = findMorphMesh(gltf?.scene);
  return (mesh && mesh.userData) || {};
}

// Turn a parsed three.js GLTF result into the modal scene payload.
export function parseModalGltf(gltf) {
  const mesh = findMorphMesh(gltf?.scene);
  const extras = modalMeshExtras(gltf);
  const modes = extractModalModes({ animations: gltf?.animations || [], meshExtras: extras });
  const damping = Number.isFinite(extras.dampingRatio) ? extras.dampingRatio : 0.01;
  return {
    scene: gltf?.scene || null,
    mesh,
    modes,
    damping,
    material: extras.material || null,
    animations: gltf?.animations || [],
    isModal: Boolean(mesh && modes.length),
  };
}

// Load a modal GLB from a URL using a three.js GLTFLoader instance.
export async function loadModalScene(THREE, GLTFLoader, url) {
  const gltf = await new GLTFLoader().loadAsync(url);
  return { gltf, ...parseModalGltf(gltf) };
}
