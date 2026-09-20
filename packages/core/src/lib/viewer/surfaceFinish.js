import { BASE_VIEWER_THEME } from "./stageTheme.js";

// The viewer's surface FINISH, as data. A finish is what makes two scenes read as
// one product under the same lights: how rough, how metallic, how coated. It is
// not a colour, a map or an opacity; those identify the part and stay its own.
// Whoever builds a scene applies these values to its own materials.

/** The finish every surface wears when no theme overrides it. */
export const SURFACE_FINISH_DEFAULTS = Object.freeze({
  roughness: BASE_VIEWER_THEME.surfaceRoughness,
  metalness: BASE_VIEWER_THEME.surfaceMetalness,
  clearcoat: BASE_VIEWER_THEME.surfaceClearcoat
});

/**
 * The finish a resolved viewer theme asks for.
 * @returns {{ roughness: number, metalness: number, clearcoat: number }}
 */
export function resolveSurfaceFinish(viewerTheme = null) {
  return {
    roughness: Number(viewerTheme?.surfaceRoughness ?? SURFACE_FINISH_DEFAULTS.roughness),
    metalness: Number(viewerTheme?.surfaceMetalness ?? SURFACE_FINISH_DEFAULTS.metalness),
    clearcoat: Number(viewerTheme?.surfaceClearcoat ?? SURFACE_FINISH_DEFAULTS.clearcoat)
  };
}

// What a material authored about its own finish. Remembered on the material the
// first time a finish is applied, so the authored look can always be restored.
export const AUTHORED_FINISH_KEYS = ["roughness", "metalness", "clearcoat", "clearcoatRoughness", "envMapIntensity"];

/**
 * Give every standard material under `root` a finish, or (`finish` null) the
 * finish it was authored with. Colour, maps and opacity are never touched. The
 * authored values are kept on the material, so this is safe to call repeatedly
 * and in either order.
 */
export function applySurfaceFinish(root, finish = null) {
  const materials = new Set();
  root?.traverse?.((object) => {
    for (const material of Array.isArray(object?.material) ? object.material : [object?.material]) {
      if (material?.isMeshStandardMaterial) materials.add(material);
    }
  });
  for (const material of materials) {
    const authored = material.userData.authoredFinish ||= Object.fromEntries(
      AUTHORED_FINISH_KEYS.filter((key) => key in material).map((key) => [key, material[key]])
    );
    const values = finish ? { ...authored, ...finish } : authored;
    for (const key of Object.keys(authored)) material[key] = values[key];
    material.needsUpdate = true;
  }
}
