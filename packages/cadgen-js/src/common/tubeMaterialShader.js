// One onBeforeCompile per material for every tube shader stage. Stages run in
// a fixed order — the GPU transport (which produces the vertex and the tube
// material coordinates) before the braid finish (which consumes them) — so the
// result is the same whichever frame first enables each stage. The braid never
// has to know how the GPU stage stores its data; it reads the shared varying.
export const TUBE_MATERIAL_VARYING = "vCadTubeMaterial";
export const TUBE_MATERIAL_ATTRIBUTE = "cadTubeMaterial";
export const TUBE_GPU_STAGE = "gpu";
export const TUBE_BRAID_STAGE = "braid";
const STAGE_ORDER = [TUBE_GPU_STAGE, TUBE_BRAID_STAGE];

export function tubeMaterialStage(material, name) {
  return material?.userData?.cadTubeShader?.stages[name] || null;
}

// Returns the named stage, creating it with `create()` -> {uniforms, apply}
// on first use. `apply(shader, stages)` edits the shader text; `stages` lets a
// consumer see which producers are present.
export function ensureTubeMaterialStage(material, name, create) {
  if (!material) {
    return null;
  }
  let shared = material.userData.cadTubeShader;
  if (!shared) {
    const originalCompile = material.onBeforeCompile;
    const originalKey = material.customProgramCacheKey;
    shared = material.userData.cadTubeShader = { stages: {} };
    material.onBeforeCompile = function (shader, renderer) {
      originalCompile.call(this, shader, renderer);
      const declaration = `#include <common>\nvarying vec3 ${TUBE_MATERIAL_VARYING};`;
      shader.vertexShader = shader.vertexShader.replace("#include <common>", declaration);
      shader.fragmentShader = shader.fragmentShader.replace("#include <common>", declaration);
      for (const stageName of STAGE_ORDER) {
        const stage = shared.stages[stageName];
        if (!stage) {
          continue;
        }
        Object.assign(shader.uniforms, stage.uniforms);
        stage.apply(shader, shared.stages);
      }
    };
    material.customProgramCacheKey = function () {
      const active = STAGE_ORDER.filter((stageName) => shared.stages[stageName]).join("+");
      return `${originalKey.call(this)}:cad-tube:${active}`;
    };
    material.needsUpdate = true;
  }
  let stage = shared.stages[name];
  if (!stage) {
    stage = shared.stages[name] = create();
    material.needsUpdate = true;
  }
  return stage;
}
