// The environment a scene's rig lights with (`sceneRig.js`), prefiltered as OCCT bakes its
// image-based light (`cadgen/engine/render/look.py`): a surface of each roughness reflects the image
// convolved with the GGX lobe of that roughness, and a surface's diffuse term reads the irradiance's
// nine spherical harmonics.
//
// The result is three's PMREM: its CubeUV layout, which every program that reads an environment
// samples through three's `textureCubeUV( envMap, direction, roughness )` -- the level a roughness
// maps to (`roughnessToMip`, three's `cube_uv_reflection_fragment`) and the next, blended -- and
// level 0, the image itself. What the other levels hold is this module's: three blurs each from the
// one before by a lobe of an "incremental" roughness, which leaves a level far sharper than the
// roughness that reads it (a metal of roughness 0.4 reflected a softbox of the studio 40% brighter
// than its GGX lobe does). Here:
//   - each level is the image convolved with the GGX lobe of the roughness three reads it at
//     (`cubeUVRoughness`), importance-sampled from the image's own mipmaps as OCCT's bake samples its
//     cube map's (PBREnvBaking's specular map: 256 samples, each read at the level of its solid angle);
//   - but the roughest, which three reads as a surface's diffuse light (`getIBLIrradiance`), is the
//     irradiance as OCCT's program reads it (`occDiffIBLMap`): nine spherical harmonics estimated as
//     OCCT estimates them (`occtIrradianceHarmonics`). A GGX lobe of roughness 1 IS the cosine lobe, so
//     that level is the same light, to the harmonics' fit; a surface of roughness 1 reflects the fit.

const SAMPLES = 256;
const IRRADIANCE_SAMPLES = 1024;

// three's `roughnessToMip` (r186): the levels it reads by roughness, linear between these
// (roughness, mip) and `-2 log2(1.16 r)` past the last.
export const CUBE_UV_ANCHORS = Object.freeze([[1.0, -2], [0.8, -1], [0.4, 2], [0.305, 3], [0.21, 4]]);

/** The roughness three reads a CubeUV level (`mip`, as its `roughnessToMip` counts them) at. */
export function cubeUVRoughness(mip) {
  const anchor = CUBE_UV_ANCHORS.find(([, level]) => level === mip);
  if (anchor) return anchor[0];
  const last = CUBE_UV_ANCHORS[CUBE_UV_ANCHORS.length - 1];
  if (mip > last[1]) return 2 ** (-mip / 2) / 1.16;
  if (mip < CUBE_UV_ANCHORS[0][1]) return CUBE_UV_ANCHORS[0][0];
  const at = CUBE_UV_ANCHORS.findIndex(([, level]) => mip < level);
  const [[from, fromLevel], [to, toLevel]] = [CUBE_UV_ANCHORS[at - 1], CUBE_UV_ANCHORS[at]];
  return from + (to - from) * (mip - fromLevel) / (toLevel - fromLevel);
}

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
 * An equirectangular image's mipmaps (RGBA floats, as the rig holds it), each level half the one
 * before (at least a texel) and each texel the mean of those under it, down to one texel.
 * @returns {{ width: number, height: number, data: Float32Array }[]}
 */
export function equirectangularMipmaps(image) {
  const levels = [{ width: image.width, height: image.height, data: image.data }];
  // The first texel of a side of `from` under each texel of a side of `to`, and the end.
  const starts = (from, to) => Int32Array.from({ length: to + 1 }, (_, at) => (at === to ? from : Math.floor(at * from / to)));
  for (let level = levels[0]; level.width > 1 || level.height > 1;) {
    const width = Math.max(1, level.width >> 1), height = Math.max(1, level.height >> 1);
    const data = new Float32Array(width * height * 4);
    const rows = starts(level.height, height), columns = starts(level.width, width);
    const source = level.data;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let r = 0, g = 0, b = 0, a = 0;
        for (let row = rows[y]; row < rows[y + 1]; row += 1) {
          for (let column = columns[x], at = (row * level.width + column) * 4; column < columns[x + 1]; column += 1, at += 4) {
            r += source[at]; g += source[at + 1]; b += source[at + 2]; a += source[at + 3];
          }
        }
        const count = (rows[y + 1] - rows[y]) * (columns[x + 1] - columns[x]);
        const to = (y * width + x) * 4;
        data[to] = r / count;
        data[to + 1] = g / count;
        data[to + 2] = b / count;
        data[to + 3] = a / count;
      }
    }
    levels.push(level = { width, height, data });
  }
  return levels;
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
// HDRLoader loads), with its mipmaps where given: then repeating around the image's seam.
function imageTexture(THREE, image, mipmaps = null) {
  const texture = new THREE.DataTexture(image.data, image.width, image.height, THREE.RGBAFormat, THREE.HalfFloatType);
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.LinearSRGBColorSpace;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = mipmaps ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter;
  texture.generateMipmaps = false;
  if (mipmaps) {
    texture.mipmaps = mipmaps;
    texture.wrapS = THREE.RepeatWrapping;
  }
  texture.needsUpdate = true;
  return texture;
}

const VERTEX = /* glsl */ `
attribute vec3 outputDirection;
varying vec3 vOutputDirection;
void main() {
  vOutputDirection = outputDirection;
  gl_Position = vec4( position, 1.0 );
}
`;

// One level: the image convolved with the GGX lobe of `roughness` around each texel's direction
// (the view along it, as a prefiltered environment assumes), weighted by N.L; each sample read at
// the mipmap whose texel spans its share of the lobe's solid angle. Directions are three's lookup
// frame, the image three's equirectangular one (`equirectUv`).
const PREFILTER = /* glsl */ `
precision highp float;
precision highp int;
varying vec3 vOutputDirection;
uniform sampler2D source;
uniform vec2 sourceSize;
uniform float roughness;
uniform int samples;
#define PI 3.141592653589793

float radicalInverse( uint bits ) {
  bits = ( bits << 16u ) | ( bits >> 16u );
  bits = ( ( bits & 0x55555555u ) << 1u ) | ( ( bits & 0xAAAAAAAAu ) >> 1u );
  bits = ( ( bits & 0x33333333u ) << 2u ) | ( ( bits & 0xCCCCCCCCu ) >> 2u );
  bits = ( ( bits & 0x0F0F0F0Fu ) << 4u ) | ( ( bits & 0xF0F0F0F0u ) >> 4u );
  bits = ( ( bits & 0x00FF00FFu ) << 8u ) | ( ( bits & 0xFF00FF00u ) >> 8u );
  return float( bits ) * 2.3283064365386963e-10;
}

vec2 imageUv( vec3 direction ) {
  return vec2( atan( direction.z, direction.x ) * ( 0.5 / PI ) + 0.5, asin( clamp( direction.y, -1.0, 1.0 ) ) / PI + 0.5 );
}

void main() {
  vec3 n = normalize( vOutputDirection );
  vec3 up = abs( n.z ) < 0.999 ? vec3( 0.0, 0.0, 1.0 ) : vec3( 1.0, 0.0, 0.0 );
  vec3 tangent = normalize( cross( up, n ) );
  vec3 bitangent = cross( n, tangent );
  float a2 = pow( roughness, 4.0 );
  // A texel's solid angle on the image's equator; nearer a pole its texels are narrower.
  float texel = ( 2.0 * PI / sourceSize.x ) * ( PI / sourceSize.y );
  vec3 sum = vec3( 0.0 );
  float weight = 0.0;
  for ( int i = 0; i < samples; i ++ ) {
    float phi = 2.0 * PI * float( i ) / float( samples );
    float xi = radicalInverse( uint( i ) );
    float cosTheta = sqrt( ( 1.0 - xi ) / ( 1.0 + ( a2 - 1.0 ) * xi ) );
    float sinTheta = sqrt( max( 1.0 - cosTheta * cosTheta, 0.0 ) );
    vec3 h = tangent * ( sinTheta * cos( phi ) ) + bitangent * ( sinTheta * sin( phi ) ) + n * cosTheta;
    vec3 l = 2.0 * cosTheta * h - n;
    float nl = dot( n, l );
    if ( nl > 0.0 ) {
      float d = cosTheta * cosTheta * ( a2 - 1.0 ) + 1.0;
      // the pdf is D / 4 where the view is the normal, and a sample's share 1 / (samples pdf)
      float share = 4.0 * PI * d * d / ( float( samples ) * a2 );
      float level = 0.5 * log2( share / ( texel * max( sqrt( 1.0 - l.y * l.y ), 1e-3 ) ) );
      sum += textureLod( source, imageUv( l ), max( level, 0.0 ) ).rgb * nl;
      weight += nl;
    }
  }
  gl_FragColor = vec4( sum / weight, 1.0 );
}
`;

// The roughest level: OCCT's irradiance (over pi) at each texel's direction, taken to the document's
// frame (`occtIrradianceHarmonics`).
const IRRADIANCE = /* glsl */ `
precision highp float;
varying vec3 vOutputDirection;
uniform vec3 harmonics[ 9 ];
uniform mat3 toDocument;
void main() {
  vec3 d = normalize( toDocument * vOutputDirection );
  vec3 e = harmonics[ 0 ] + harmonics[ 1 ] * d.x + harmonics[ 2 ] * d.y + harmonics[ 3 ] * d.z
    + harmonics[ 4 ] * d.x * d.z + harmonics[ 5 ] * d.y * d.z + harmonics[ 6 ] * d.x * d.y
    + harmonics[ 7 ] * ( 3.0 * d.z * d.z - 1.0 ) + harmonics[ 8 ] * ( d.x * d.x - d.y * d.y );
  gl_FragColor = vec4( e, 1.0 );
}
`;

const generators = new WeakMap();

// three's PMREM generator, its levels past the first made here. It reads three's own layout off
// itself (its level meshes, their sizes, the largest level), as its own filter does.
function generatorClass(THREE) {
  let found = generators.get(THREE.PMREMGenerator);
  if (found) return found;
  const LOD_MIN = 4; // three's smallest face, 16 texels: the levels past it are all that size
  found = class GgxPMREMGenerator extends THREE.PMREMGenerator {
    constructor(renderer, source, irradiance) {
      super(renderer);
      this.ggxSource = source;
      this.ggxIrradiance = irradiance;
      this.ggxMaterials = null;
    }

    _applyPMREM(cubeUV) {
      const renderer = this._renderer;
      const autoClear = renderer.autoClear;
      renderer.autoClear = false;
      const common = { vertexShader: VERTEX, blending: THREE.NoBlending, depthTest: false, depthWrite: false };
      const materials = this.ggxMaterials ||= {
        prefilter: new THREE.ShaderMaterial({ ...common, name: "GGXEnvironment", fragmentShader: PREFILTER,
          uniforms: { source: { value: null }, sourceSize: { value: new THREE.Vector2() }, roughness: { value: 0 },
            samples: { value: SAMPLES } } }),
        irradiance: new THREE.ShaderMaterial({ ...common, name: "GGXEnvironmentIrradiance", fragmentShader: IRRADIANCE,
          uniforms: { harmonics: { value: Array.from({ length: 9 }, () => new THREE.Vector3()) },
            toDocument: { value: new THREE.Matrix3() } } })
      };
      const { source, harmonics, toDocument } = { source: this.ggxSource, ...this.ggxIrradiance };
      materials.prefilter.uniforms.source.value = source;
      materials.prefilter.uniforms.sourceSize.value.set(source.image.width, source.image.height);
      materials.irradiance.uniforms.harmonics.value.forEach((band, at) => band.fromArray(harmonics, at * 3));
      materials.irradiance.uniforms.toDocument.value.copy(toDocument);
      const camera = new THREE.OrthographicCamera();
      const last = this._lodMeshes.length - 1;
      try {
        for (let lod = 1; lod <= last; lod += 1) {
          const size = this._sizeLods[lod];
          const x = 3 * size * (lod > this._lodMax - LOD_MIN ? lod - this._lodMax + LOD_MIN : 0);
          const y = 4 * (this._cubeSize - size);
          const mesh = this._lodMeshes[lod];
          if (lod === last) {
            mesh.material = materials.irradiance;
          } else {
            materials.prefilter.uniforms.roughness.value = cubeUVRoughness(this._lodMax - lod);
            mesh.material = materials.prefilter;
          }
          cubeUV.viewport.set(x, y, 3 * size, 2 * size);
          cubeUV.scissor.set(x, y, 3 * size, 2 * size);
          renderer.setRenderTarget(cubeUV);
          renderer.render(mesh, camera);
        }
      } finally {
        materials.prefilter.uniforms.source.value = null;
        renderer.autoClear = autoClear;
      }
    }

    dispose() {
      if (this.ggxMaterials) for (const material of Object.values(this.ggxMaterials)) material.dispose();
      this.ggxMaterials = null;
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
 * convolved with the GGX lobe of the roughness three reads it at, the roughest OCCT's irradiance.
 * The caller owns it.
 */
export function prefilterEnvironment(THREE, renderer, image) {
  const levels = equirectangularMipmaps(image).map((level) => ({ ...level,
    data: Uint16Array.from(level.data, THREE.DataUtils.toHalfFloat) }));
  // three's first level is the image itself; the others are filtered from its mipmaps.
  const texture = imageTexture(THREE, levels[0]);
  const source = imageTexture(THREE, levels[0], levels);
  // A document's direction in the image's frame: three turns an environment target by the opposite
  // of the scene's angles (`envMapRotation`, its "left-handed frame").
  const [rx, ry, rz] = image.rotation || [0, 0, 0];
  const toImage = new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(-rx, -ry, -rz)));
  const turned = new THREE.Vector3();
  const harmonics = occtIrradianceHarmonics(image, (x, y, z) => turned.set(x, y, z).applyMatrix3(toImage).toArray());
  const Generator = generatorClass(THREE);
  const generator = new Generator(renderer, source, { harmonics, toDocument: toImage.clone().transpose() });
  try {
    return generator.fromEquirectangular(texture);
  } finally {
    generator.dispose();
    texture.dispose();
    source.dispose();
  }
}
