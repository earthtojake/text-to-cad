import {
  TUBE_BRAID_STAGE,
  TUBE_GPU_STAGE,
  TUBE_MATERIAL_ATTRIBUTE,
  TUBE_MATERIAL_VARYING,
  ensureTubeMaterialStage
} from "./tubeMaterialShader.js";

// A braid is a procedural surface finish on the real STEP tube, not additional
// collision geometry. Rest material coordinates (arc length, transverse offsets)
// survive mesh deformation: the CPU path stores them in an attribute, the GPU
// path derives them from its mapping texture; both write the shared varying.
const PARS = `
uniform vec3 cadBraidParameters;
uniform float cadBraidEnabled;
float cadBraidHeight() {
  float angle = atan(${TUBE_MATERIAL_VARYING}.z, ${TUBE_MATERIAL_VARYING}.y);
  float turns = ${TUBE_MATERIAL_VARYING}.x / cadBraidParameters.x;
  float carrierA = cadBraidParameters.z * (angle / 6.28318530718 + turns);
  float carrierB = cadBraidParameters.z * (angle / 6.28318530718 - turns);
  float a = fract(carrierA), b = fract(carrierB);
  float bandA = sqrt(max(0.0, 1.0 - pow((a - 0.5) / 0.44, 2.0)));
  float bandB = sqrt(max(0.0, 1.0 - pow((b - 0.5) / 0.44, 2.0)));
  float over = mod(floor(carrierA) + floor(carrierB), 2.0);
  float crown = mix(max(bandA, bandB * 0.60), max(bandB, bandA * 0.60), over);
  float fineFibers = 0.035 * cos(6.28318530718 * 5.0 * mix(carrierA, carrierB, over));
  return cadBraidEnabled * cadBraidParameters.y * (crown + fineFibers - 1.035);
}
vec3 cadBraidNormal(vec3 surfacePosition, vec3 surfaceNormal, float height) {
  vec3 dx = dFdx(surfacePosition), dy = dFdy(surfacePosition);
  vec3 r1 = cross(dy, surfaceNormal), r2 = cross(surfaceNormal, dx);
  float determinant = dot(dx, r1);
  vec3 gradient = sign(determinant) * (dFdx(height) * r1 + dFdy(height) * r2);
  return normalize(abs(determinant) * surfaceNormal - gradient);
}
`;

function applyBraidStage(shader, stages) {
  if (!stages[TUBE_GPU_STAGE]) {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", `#include <common>\nattribute vec3 ${TUBE_MATERIAL_ATTRIBUTE};`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>\n${TUBE_MATERIAL_VARYING} = ${TUBE_MATERIAL_ATTRIBUTE};`);
  }
  shader.fragmentShader = shader.fragmentShader
    .replace("#include <common>", `#include <common>\n${PARS}`)
    .replace(
      "#include <color_fragment>",
      "#include <color_fragment>\nfloat cadBraidRelief = cadBraidHeight();\n"
        + "diffuseColor.rgb *= 1.0 + 0.22 * cadBraidRelief / max(cadBraidParameters.y, 0.000001);"
    )
    .replace(
      "#include <normal_fragment_maps>",
      "#include <normal_fragment_maps>\nif (cadBraidEnabled > 0.5) normal = cadBraidNormal(-vViewPosition, normal, cadBraidRelief);"
    );
}

export function applyTubeBraidMaterial(THREE, material, braid) {
  if (!material) {
    return;
  }
  if (!braid && !material.userData.cadTubeShader?.stages[TUBE_BRAID_STAGE]) {
    return;
  }
  const stage = ensureTubeMaterialStage(material, TUBE_BRAID_STAGE, () => ({
    uniforms: {
      cadBraidParameters: { value: new THREE.Vector3(1, 0, 8) },
      cadBraidEnabled: { value: 0 }
    },
    apply: applyBraidStage
  }));
  stage.uniforms.cadBraidEnabled.value = braid ? 1 : 0;
  if (braid) {
    stage.uniforms.cadBraidParameters.value.set(braid.pitch, braid.depth, braid.strands);
  }
}
