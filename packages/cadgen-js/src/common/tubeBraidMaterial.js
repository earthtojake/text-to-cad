// A braid is a procedural surface finish on the real STEP tube, not additional
// collision geometry. Rest material coordinates survive mesh deformation.
const PARS = `
uniform vec3 cadBraidParameters;
uniform float cadBraidEnabled;
varying vec3 vCadTubeMaterial;
float cadBraidHeight() {
  float angle = atan(vCadTubeMaterial.z, vCadTubeMaterial.y);
  float turns = vCadTubeMaterial.x / cadBraidParameters.x;
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

export function applyTubeBraidMaterial(THREE, material, braid) {
  if (!material) return;
  let state=material.userData.cadTubeBraid;
  if(!state && !braid)return;
  if(!state) {
    const originalCompile=material.onBeforeCompile,originalKey=material.customProgramCacheKey;
    state=material.userData.cadTubeBraid={parameters:{value:new THREE.Vector3(1,0,8)},enabled:{value:0}};
    material.onBeforeCompile=function(shader,renderer) {
      originalCompile.call(this,shader,renderer);
      shader.uniforms.cadBraidParameters=state.parameters;
      shader.uniforms.cadBraidEnabled=state.enabled;
      shader.vertexShader=shader.vertexShader.replace('#include <common>', '#include <common>\nattribute vec3 cadTubeMaterial;\nvarying vec3 vCadTubeMaterial;');
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvCadTubeMaterial = cadTubeMaterial;');
      shader.fragmentShader=shader.fragmentShader.replace('#include <common>',`#include <common>\n${PARS}`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>',`#include <color_fragment>\nfloat cadBraidRelief = cadBraidHeight();\ndiffuseColor.rgb *= 1.0 + 0.22 * cadBraidRelief / max(cadBraidParameters.y, 0.000001);`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\nif (cadBraidEnabled > 0.5) normal = cadBraidNormal(-vViewPosition, normal, cadBraidRelief);');
    };
    material.customProgramCacheKey=function(){return `${originalKey.call(this)}:cad-tube-braid-v1`;};
    material.needsUpdate=true;
  }
  state.enabled.value=braid?1:0;
  if(braid)state.parameters.value.set(braid.pitch,braid.depth,braid.strands);
}
