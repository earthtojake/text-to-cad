// The environment a scene's rig lights with (`sceneRig.js`), prefiltered as OCCT bakes its
// image-based light (`cad/engine/render/look.py`): a surface of each roughness reflects the image
// convolved with the GGX lobe of that roughness, and a surface's diffuse term reads the irradiance's
// nine spherical harmonics.
//
// The result is three's PMREM: a cube target whose mip levels every program that reads an
// environment samples by roughness (`textureLod( envMap, direction, roughnessToMip( roughness ) )`,
// level `lod` holding `PMREMGenerator.lodToRoughness( lod, maxLod )`), and the roughest of them as a
// surface's diffuse light (`getIBLIrradiance`). Three fills the levels as OCCT's bake fills its
// specular map: each the image convolved with the GGX lobe of its roughness, 256 Hammersley samples
// each read at the mip level of its solid angle (PBREnvBaking's). Here, the roughest is instead the
// irradiance as OCCT's program reads it (`occDiffIBLMap`): nine spherical harmonics estimated as OCCT
// estimates them (`occtIrradianceHarmonics`). A GGX lobe of roughness 1 IS the cosine lobe, so that
// level is the same light, to the harmonics' fit; a surface of roughness 1 reflects the fit.

const IRRADIANCE_SAMPLES = 1024;

/** The base-2 radical inverse of `index`: the second coordinate of a Hammersley point. */
export function radicalInverse(index) {
  let bits = index >>> 0;
  bits = ((bits << 16) | (bits >>> 16)) >>> 0;
  bits = (((bits & 0x55555555) << 1) | ((bits & 0xAAAAAAAA) >>> 1)) >>> 0;
  bits = (((bits & 0x33333333) << 2) | ((bits & 0xCCCCCCCC) >>> 2)) >>> 0;
  bits = (((bits & 0x0F0F0F0F) << 4) | ((bits & 0xF0F0F0F0) >>> 4)) >>> 0;
  bits = (((bits & 0x00FF00FF) << 8) | ((bits & 0xFF00FF00) >>> 8)) >>> 0;
  return bits / 4294967296;
}

/**
 * The image along a direction of its own frame (three's equirectangular one: `equirectUv`, the
 * bottom row first), bilinear, around its seam and clamped at its poles.
 */
export function sampleEquirectangular(image, x, y, z) {
  const { width, height, data } = image;
  const u = Math.atan2(z, x) / (2 * Math.PI) + 0.5;
  const v = Math.asin(Math.min(Math.max(y, -1), 1)) / Math.PI + 0.5;
  const fx = u * width - 0.5, fy = Math.min(Math.max(v * height - 0.5, 0), height - 1);
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  const y1 = Math.min(y0 + 1, height - 1);
  const left = ((x0 % width) + width) % width, right = (left + 1) % width;
  const out = [0, 0, 0];
  for (let channel = 0; channel < 3; channel += 1) {
    const at = (row, column) => data[(row * width + column) * 4 + channel];
    const bottom = at(y0, left) * (1 - tx) + at(y0, right) * tx;
    const top = at(y1, left) * (1 - tx) + at(y1, right) * tx;
    out[channel] = bottom * (1 - ty) + top * ty;
  }
  return out;
}

// Each band's cosine-lobe convolution times its basis function's normalisation squared (OCCT's
// `aSHCosCoeffs` and `aSHBasisFuncCoeffs`), the basis functions `1, x, y, z, xz, yz, xy, 3z^2 - 1,
// x^2 - y^2`.
const HARMONIC_WEIGHTS = Object.freeze([
  Math.PI * 0.282095 ** 2, ...Array(3).fill(2 * Math.PI / 3 * 0.488603 ** 2), ...Array(3).fill(Math.PI / 4 * 1.092548 ** 2),
  Math.PI / 4 * 0.315392 ** 2, Math.PI / 4 * 0.546274 ** 2
]);

const harmonicBasis = (x, y, z) => [1, x, y, z, x * z, y * z, x * y, 3 * z * z - 1, x * x - y * y];

/**
 * The irradiance of an environment image as OCCT's program reads it (`occDiffIBLMap`: the irradiance
 * over pi at a normal `n` is `sum_k c_k b_k(n)`), its nine RGB coefficients `c` (27 floats) estimated
 * as OCCT's bake estimates them (PBREnvBaking's `bakeDiffuseSH`): over `samples` Hammersley points
 * spread evenly over the sphere in the document's frame (`Graphic3d_RenderingParams`'
 * `PbrEnvBakingDiffNbSamples`), `c_k = 4 w_k / samples * sum L(d) b_k(d)`. `toImage` takes a direction of
 * the document's frame to the image's (a function of x, y, z returning [x, y, z]).
 */
export function occtIrradianceHarmonics(image, toImage, samples = IRRADIANCE_SAMPLES) {
  const sums = new Float64Array(27);
  for (let i = 0; i < samples; i += 1) {
    const phi = 2 * Math.PI * i / samples;
    const z = 2 * radicalInverse(i) - 1;
    const r = Math.sqrt(Math.max(1 - z * z, 0));
    const x = r * Math.cos(phi), y = r * Math.sin(phi);
    const radiance = sampleEquirectangular(image, ...toImage(x, y, z));
    harmonicBasis(x, y, z).forEach((value, band) => {
      for (let channel = 0; channel < 3; channel += 1) sums[band * 3 + channel] += radiance[channel] * value;
    });
  }
  return Float32Array.from(sums, (sum, at) => 4 * HARMONIC_WEIGHTS[Math.floor(at / 3)] * sum / samples);
}


// An image's texture in half floats (what WebGL2 filters linearly without an extension, as three's
// HDRLoader loads).
function imageTexture(THREE, image) {
  const data = Uint16Array.from(image.data, THREE.DataUtils.toHalfFloat);
  const texture = new THREE.DataTexture(data, image.width, image.height, THREE.RGBAFormat, THREE.HalfFloatType);
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.LinearSRGBColorSpace;
  texture.magFilter = texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

// The roughest level: OCCT's irradiance (over pi) at each texel's direction (three's lookup frame,
// its `cube_vert`'s), taken to the document's frame (`occtIrradianceHarmonics`).
const IRRADIANCE = /* glsl */ `
varying vec3 vWorldDirection;
uniform vec3 harmonics[ 9 ];
uniform mat3 toDocument;
void main() {
  vec3 d = normalize( toDocument * vWorldDirection );
  vec3 e = harmonics[ 0 ] + harmonics[ 1 ] * d.x + harmonics[ 2 ] * d.y + harmonics[ 3 ] * d.z
    + harmonics[ 4 ] * d.x * d.z + harmonics[ 5 ] * d.y * d.z + harmonics[ 6 ] * d.x * d.y
    + harmonics[ 7 ] * ( 3.0 * d.z * d.z - 1.0 ) + harmonics[ 8 ] * ( d.x * d.x - d.y * d.y );
  gl_FragColor = vec4( e, 1.0 );
}
`;

const generators = new WeakMap();

// three's PMREM generator, its roughest level drawn here once three has filled them all. It draws
// that level as three draws every level (`_renderCube`: its box, from inside, into each face).
function generatorClass(THREE) {
  let found = generators.get(THREE.PMREMGenerator);
  if (found) return found;
  found = class GgxPMREMGenerator extends THREE.PMREMGenerator {
    constructor(renderer, irradiance) {
      super(renderer);
      this.ggxIrradiance = irradiance;
      this.ggxMaterial = null;
    }

    _applyPMREM(pmremTarget) {
      super._applyPMREM(pmremTarget);
      const material = this.ggxMaterial ||= new THREE.ShaderMaterial({
        name: "GGXEnvironmentIrradiance", vertexShader: THREE.ShaderChunk.cube_vert, fragmentShader: IRRADIANCE,
        side: THREE.BackSide, blending: THREE.NoBlending, depthTest: false, depthWrite: false,
        uniforms: { harmonics: { value: Array.from({ length: 9 }, () => new THREE.Vector3()) }, toDocument: { value: new THREE.Matrix3() } }
      });
      const { harmonics, toDocument } = this.ggxIrradiance;
      material.uniforms.harmonics.value.forEach((band, at) => band.fromArray(harmonics, at * 3));
      material.uniforms.toDocument.value.copy(toDocument);
      this._renderCube(pmremTarget, pmremTarget.texture.mipmaps.length - 1, material);
    }

    dispose() {
      this.ggxMaterial?.dispose();
      this.ggxMaterial = null;
      super.dispose();
    }
  };
  generators.set(THREE.PMREMGenerator, found);
  return found;
}

/**
 * The rig's environment `image` (`{ width, height, data, rotation }`: an equirectangular image, RGBA
 * floats, the bottom row first, turned into the document's frame by `rotation` as three turns a
 * scene's environment) prefiltered for `renderer`: three's PMREM render target, each level the image
 * convolved with the GGX lobe of its roughness, the roughest OCCT's irradiance. The caller owns it.
 */
export function prefilterEnvironment(THREE, renderer, image) {
  const texture = imageTexture(THREE, image);
  // A document's direction in the image's frame: three turns an environment target by the opposite
  // of the scene's angles (`envMapRotation`, its "left-handed frame").
  const [rx, ry, rz] = image.rotation || [0, 0, 0];
  const toImage = new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(-rx, -ry, -rz)));
  const turned = new THREE.Vector3();
  const harmonics = occtIrradianceHarmonics(image, (x, y, z) => turned.set(x, y, z).applyMatrix3(toImage).toArray());
  const Generator = generatorClass(THREE);
  const generator = new Generator(renderer, { harmonics, toDocument: toImage.clone().transpose() });
  try {
    return generator.fromEquirectangular(texture);
  } finally {
    generator.dispose();
    texture.dispose();
  }
}
