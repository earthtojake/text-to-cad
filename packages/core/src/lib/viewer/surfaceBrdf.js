// The surface models a look may light its surfaces by (`surfaceLook.js`'s `brdf`), each a
// program change three's physical material takes in `onBeforeCompile`: GLSL put after three's own
// lighting functions, which the lighting loop is then pointed at (`RE_Direct`,
// `RE_IndirectSpecular`), and a line after three's material setup. Nothing of three's chunks is
// edited, so a program that names no model is three's own.
//
// `occt` is OCCT 7.9's PBR raster program (`occt_phong-pbr`), which the engine's look of the
// regular modes is defined by (`cadgen/engine/render/look.py`). Where three's physical model
// differs from it, the model draws OCCT's:
//   - the roughness as given (at least 0.01), with no floor of 0.0525 and no roughness added for a
//     curved surface's screen-space normal change;
//   - per light, `((1 - F) (1 - metallic) base / pi + D G F / 4) * radiance * max(0, N.L)`: GGX `D`,
//     Schlick-GGX `G = 1 / ((N.V (1 - k) + k) (N.L (1 - k) + k))` with `k = (r + 1)^2 / 8`, exact
//     Schlick `F` at V.H from `F0 = mix(F0(ior), base, metallic)` -- three's height-correlated
//     Smith term and its multiple-scattering compensation are not drawn;
//   - from the environment `(F0 A + B) * prefiltered(R, r)` and
//     `(1 - F_r) (1 - metallic) base * irradiance / pi`, `F_r` Schlick at N.V from the same F0 toward
//     `max(1 - r, F0)`: single scattering, three's multiple-scattering term not drawn. `A` and `B` are
//     OCCT's own split-sum table (`occtEnvironmentTable`: its `GenerateEnvLUT`, Schlick-GGX at
//     `k = r^2 / 2`), not three's (whose Smith term reflects some 10% more of a metal's environment);
//     the environment is prefiltered by GGX, as OCCT bakes it (`ggxEnvironment.js`, the rig's);
//   - the surface is isotropic, as OCCT's program is: an anisotropic material is drawn with its
//     roughness alone (three bends an anisotropic surface's reflection toward its brushing, which
//     turned a brushed plate's top seen from above from the studio's softbox to its dark wall).
// What else OCCT's raster has no term for stays three's, as the look has the viewer draw it: a clear
// coat's layer and transmission.

import { radicalInverse } from "./ggxEnvironment.js";

const OCCT_LIGHTING = /* glsl */ `
// OCCT 7.9's PBR program (surfaceBrdf.js).
uniform sampler2D occtEnvironmentTable;

float occtFresnel( const in float cosine ) {
	float x = 1.0 - cosine;
	float x2 = x * x;
	return x2 * x2 * x;
}

void RE_Direct_Occt( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		clearcoatSpecularDirect += dotNLcc * directLight.color * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	vec3 halfDir = normalize( directLight.direction + geometryViewDir );
	float dotVH = saturate( dot( geometryViewDir, halfDir ) );
	vec3 f0 = material.specularColorBlended;
	vec3 F = f0 + ( 1.0 - f0 ) * occtFresnel( dotVH );
	float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
	float dotNH = saturate( dot( geometryNormal, halfDir ) );
	float k = pow2( material.roughness + 1.0 ) * 0.125;
	float G = 1.0 / ( ( dotNV * ( 1.0 - k ) + k ) * ( dotNL * ( 1.0 - k ) + k ) );
	vec3 specular = D_GGX( pow2( material.roughness ), dotNH ) * G * F * 0.25;
	reflectedLight.directSpecular += irradiance * specular;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );
}

void RE_IndirectSpecular_Occt( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	vec3 reflected = radiance;
	#ifdef ENVMAP_TYPE_CUBE_UV
		// The environment along the mirror direction itself (three bends it toward the normal, and an
		// anisotropic surface's toward its brushing).
		vec3 mirror = transformDirectionByInverseViewMatrix( reflect( - geometryViewDir, geometryNormal ), viewMatrix );
		reflected = textureCubeUV( envMap, envMapRotation * mirror, material.roughness ).rgb * envMapIntensity;
	#endif
	float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
	vec2 scaleBias = texture2D( occtEnvironmentTable, vec2( dotNV, material.roughness ) ).rg;
	vec3 f0 = material.specularColorBlended;
	reflectedLight.indirectSpecular += reflected * ( f0 * scaleBias.x + scaleBias.y );
	vec3 fresnel = f0 + ( max( vec3( 1.0 - material.roughness ), f0 ) - f0 ) * occtFresnel( dotNV );
	reflectedLight.indirectDiffuse += ( 1.0 - fresnel ) * material.diffuseContribution * irradiance * RECIPROCAL_PI;
}

#undef RE_Direct
#define RE_Direct RE_Direct_Occt
#undef RE_IndirectSpecular
#define RE_IndirectSpecular RE_IndirectSpecular_Occt
`;

const OCCT_ROUGHNESS = /* glsl */ `
material.roughness = clamp( roughnessFactor, 0.01, 1.0 );
`;

// OCCT's split-sum table, as its `Graphic3d_PBRMaterial::GenerateEnvLUT` makes it: by N.V (across)
// and roughness (down), the scale and bias of F0 a reflected environment is weighted by, each the
// mean over Hammersley samples of the GGX lobe (alpha = r^2) of `G V.H / (N.V N.H)` times `1 - Fc`
// and `Fc`, `Fc = (1 - V.H)^5`, `G` Schlick-GGX at `k = r^2 / 2`. Values at texel centres.
const TABLE_SIZE = 32;
const TABLE_SAMPLES = 512;

/** OCCT's split-sum scale and bias for a view at `nv` (N.V) on a surface of `roughness`. */
export function occtEnvironmentScaleBias(nv, roughness, samples = TABLE_SAMPLES) {
  const alpha = roughness * roughness;
  const a2 = alpha * alpha;
  const k = alpha / 2;
  const vx = Math.sqrt(Math.max(1 - nv * nv, 0));
  let scale = 0;
  let bias = 0;
  for (let i = 0; i < samples; i += 1) {
    const phi = 2 * Math.PI * i / samples;
    const xi = radicalInverse(i);
    const cosTheta = Math.sqrt((1 - xi) / (1 + (a2 - 1) * xi));
    const sinTheta = Math.sqrt(Math.max(1 - cosTheta * cosTheta, 0));
    const vh = vx * sinTheta * Math.cos(phi) + nv * cosTheta;
    const nl = 2 * vh * cosTheta - nv;
    if (nl <= 0 || vh <= 0) continue;
    const g = nl / ((nl * (1 - k) + k) * (nv * (1 - k) + k));
    const weighted = g * vh / cosTheta;
    const fc = (1 - vh) ** 5;
    scale += weighted * (1 - fc);
    bias += weighted * fc;
  }
  return [scale / samples, bias / samples];
}

let environmentTable = null;

/** OCCT's split-sum table as a texture (half floats, filtered): one for the page, made on first use. */
export function occtEnvironmentTable(THREE) {
  if (environmentTable) return environmentTable;
  const data = new Uint16Array(TABLE_SIZE * TABLE_SIZE * 2);
  for (let row = 0; row < TABLE_SIZE; row += 1) {
    for (let column = 0; column < TABLE_SIZE; column += 1) {
      const [scale, bias] = occtEnvironmentScaleBias((column + 0.5) / TABLE_SIZE, (row + 0.5) / TABLE_SIZE);
      data[(row * TABLE_SIZE + column) * 2] = THREE.DataUtils.toHalfFloat(scale);
      data[(row * TABLE_SIZE + column) * 2 + 1] = THREE.DataUtils.toHalfFloat(bias);
    }
  }
  const table = new THREE.DataTexture(data, TABLE_SIZE, TABLE_SIZE, THREE.RGFormat, THREE.HalfFloatType);
  table.name = "OCCT environment table";
  table.minFilter = table.magFilter = THREE.LinearFilter;
  table.wrapS = table.wrapT = THREE.ClampToEdgeWrapping;
  table.generateMipmaps = false;
  table.needsUpdate = true;
  environmentTable = table;
  return table;
}

function occtCompile(shader) {
  const after = (include, text) => {
    const found = `#include <${include}>`;
    if (!shader.fragmentShader.includes(found)) throw new Error(`the occt surface model needs three's ${found}`);
    shader.fragmentShader = shader.fragmentShader.replace(found, `${found}\n${text}`);
  };
  if (!environmentTable) throw new Error("the occt surface model's table is made when a material takes the model (useSurfaceBrdf)");
  after("lights_physical_pars_fragment", OCCT_LIGHTING);
  after("lights_physical_fragment", OCCT_ROUGHNESS);
  shader.uniforms.occtEnvironmentTable = { value: environmentTable };
}

const occtKey = () => "surface-brdf:occt";

/** The models by name: what a material takes to be lit by one (`useSurfaceBrdf`). */
export const SURFACE_BRDFS = Object.freeze({
  occt: Object.freeze({ onBeforeCompile: occtCompile, customProgramCacheKey: occtKey, prepare: occtEnvironmentTable })
});

/**
 * Light a physical material by the model `name` (`SURFACE_BRDFS`), or by three's own for none;
 * returns whether its program changes (the caller then sets `needsUpdate`).
 */
export function useSurfaceBrdf(THREE, material, name = null) {
  if (name != null && !Object.hasOwn(SURFACE_BRDFS, name)) {
    throw new Error(`a surface model is one of ${Object.keys(SURFACE_BRDFS).join(", ")}, not ${JSON.stringify(name)}`);
  }
  const model = name == null ? null : SURFACE_BRDFS[name];
  model?.prepare(THREE);
  const onBeforeCompile = model ? model.onBeforeCompile : THREE.Material.prototype.onBeforeCompile;
  const customProgramCacheKey = model ? model.customProgramCacheKey : THREE.Material.prototype.customProgramCacheKey;
  if (material.onBeforeCompile === onBeforeCompile && material.customProgramCacheKey === customProgramCacheKey) return false;
  material.onBeforeCompile = onBeforeCompile;
  material.customProgramCacheKey = customProgramCacheKey;
  return true;
}
