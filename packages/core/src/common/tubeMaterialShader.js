// One onBeforeCompile per material for every tube shader stage. Stages run in
// a fixed order -- the skin (which moves the vertex) before the braid finish
// (which shades by the tube's rest material coordinates, an attribute cadgen
// binds with the skin) -- so the result is the same whichever frame first enables
// each stage.
export const TUBE_MATERIAL_VARYING = "vCadTubeMaterial";
export const TUBE_MATERIAL_ATTRIBUTE = "cadTubeMaterial";
export const TUBE_SKIN_STAGE = "skin";
export const TUBE_BRAID_STAGE = "braid";
const STAGE_ORDER = [TUBE_SKIN_STAGE, TUBE_BRAID_STAGE];

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
      for (const stageName of STAGE_ORDER) {
        const stage = shared.stages[stageName];
        if (!stage) {
          continue;
        }
        Object.assign(shader.uniforms, stage.uniforms);
        stage.apply(shader, shared.stages);
      }
      // Declared last, so it lands directly under `#include <common>` and above
      // every stage's code. A stage anchors its own text on that same include,
      // so declaring first would leave the varying BELOW a stage that reads it
      // — GLSL rejects the identifier and the whole program fails to compile.
      const declaration = `#include <common>\nvarying vec3 ${TUBE_MATERIAL_VARYING};`;
      shader.vertexShader = shader.vertexShader.replace("#include <common>", declaration);
      shader.fragmentShader = shader.fragmentShader.replace("#include <common>", declaration);
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
