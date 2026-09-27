// Fixed reflection fill for authored finishes in the workbench. A tiny neutral
// hemisphere keeps metals legible without loading the photographic studio or
// an external HDR image. Three derives and caches its roughness mipmaps per
// renderer, and releases them when the source texture is disposed.
export const INSPECT_ENVIRONMENT_ID = "inspect-neutral-hemisphere";

export function hasAuthoredMaterials(meshData) {
  return Boolean(meshData?.parts?.some((part) => part?.material));
}

export function createInspectEnvironmentResource(THREE) {
  const width = 64, height = 32;
  const pixels = new Float32Array(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    const radiance = 0.2 + 0.6 * (y + 0.5) / height;
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4;
      pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = radiance;
      pixels[offset + 3] = 1;
    }
  }
  const texture = new THREE.DataTexture(pixels, width, height, THREE.RGBAFormat, THREE.FloatType);
  texture.name = INSPECT_ENVIRONMENT_ID;
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.LinearSRGBColorSpace;
  texture.needsUpdate = true;
  let disposed = false;
  return {
    identity: INSPECT_ENVIRONMENT_ID,
    texture,
    dispose() {
      if (disposed) return;
      disposed = true;
      texture.dispose();
    }
  };
}
