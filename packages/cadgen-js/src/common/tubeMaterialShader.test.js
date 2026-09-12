import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { applyTubeBraidMaterial } from "./tubeBraidMaterial.js";
import { TUBE_GPU_STAGE, TUBE_MATERIAL_VARYING, ensureTubeMaterialStage } from "./tubeMaterialShader.js";

function compile(material) {
  const shader = {
    uniforms: {},
    vertexShader: THREE.ShaderLib.standard.vertexShader,
    fragmentShader: THREE.ShaderLib.standard.fragmentShader
  };
  material.onBeforeCompile(shader, {});
  return shader;
}

// GLSL has no forward declarations: the first mention of the varying anywhere in
// a stage must be its own declaration, or the driver rejects the program.
function assertDeclaredBeforeUse(source, label) {
  const declaration = source.indexOf(`varying vec3 ${TUBE_MATERIAL_VARYING};`);
  assert.notEqual(declaration, -1, `${label} declares ${TUBE_MATERIAL_VARYING}`);
  assert.equal(
    source.indexOf(TUBE_MATERIAL_VARYING),
    declaration + "varying vec3 ".length,
    `${label} declares ${TUBE_MATERIAL_VARYING} above every use of it`
  );
}

test("the shared varying is declared above the stage code that reads it", () => {
  const material = new THREE.MeshStandardMaterial();
  applyTubeBraidMaterial(THREE, material, { pitch: 0.8, depth: 0.02, strands: 8 });
  const shader = compile(material);
  assert.ok(shader.fragmentShader.includes("cadBraidHeight()"), "the braid finish is in the fragment stage");
  assertDeclaredBeforeUse(shader.vertexShader, "vertex");
  assertDeclaredBeforeUse(shader.fragmentShader, "fragment");
});

test("a producer stage anchored on the same include still leaves the varying declared first", () => {
  const material = new THREE.MeshStandardMaterial();
  // Stands in for the GPU transport: a producer that anchors its own block on
  // `#include <common>` in both stages, as the real one does.
  ensureTubeMaterialStage(material, TUBE_GPU_STAGE, () => ({
    uniforms: { cadFakeStage: { value: 1 } },
    apply(shader) {
      const block = `#include <common>\nfloat cadFakeRead() { return ${TUBE_MATERIAL_VARYING}.x; }`;
      shader.vertexShader = shader.vertexShader.replace("#include <common>", block);
      shader.fragmentShader = shader.fragmentShader.replace("#include <common>", block);
    }
  }));
  applyTubeBraidMaterial(THREE, material, { pitch: 0.8, depth: 0.02, strands: 8 });
  const shader = compile(material);
  assert.equal(shader.uniforms.cadFakeStage.value, 1, "the producer's uniforms reach the shader");
  assertDeclaredBeforeUse(shader.vertexShader, "vertex");
  assertDeclaredBeforeUse(shader.fragmentShader, "fragment");
});
