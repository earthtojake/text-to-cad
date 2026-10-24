// The rig's environment prefiltered as OCCT bakes it (`ggxEnvironment.js`): three's PMREM, each
// level past the image the GGX lobe of the roughness three's `textureCubeUV` reads it at, drawn
// where three reads it, the roughest OCCT's irradiance; and that irradiance itself.
import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { recordingRenderer } from "./__tests__/recordingRenderer.js";
import {
  CUBE_UV_ANCHORS, cubeUVRoughness, equirectangularMipmaps, occtIrradianceHarmonics, prefilterEnvironment
} from "./ggxEnvironment.js";

const LOOK_TURN = (x, y, z) => [x, z, -y]; // a document's direction in the look's image (xbfLook.js's turn)

/** An image whose upper half (in its own frame) is `sky` and lower half `ground`, bottom row first. */
function image(width, height, sky, ground, rotation = undefined) {
  const data = new Float32Array(width * height * 4);
  for (let row = 0; row < height; row += 1) {
    const value = row >= height / 2 ? sky : ground;
    for (let column = 0; column < width; column += 1) data.set([value, value, value, 1], (row * width + column) * 4);
  }
  return { width, height, data, rotation };
}

const irradiance = (harmonics, [x, y, z]) => [1, x, y, z, x * z, y * z, x * y, 3 * z * z - 1, x * x - y * y]
  .reduce((sum, basis, band) => sum + harmonics[band * 3] * basis, 0);

test("each level's roughness is the one three's textureCubeUV reads that level at", () => {
  const chunk = THREE.ShaderChunk.cube_uv_reflection_fragment;
  const define = (name) => Number(new RegExp(`#define ${name} (-? ?[\\d.]+)`).exec(chunk)[1].replace(" ", ""));
  assert.deepEqual(CUBE_UV_ANCHORS, [0, 1, 4, 5, 6].map((k) => [define(`cubeUV_r${k}`), define(`cubeUV_m${k}`)]),
    "three's anchors, as its roughnessToMip has them");
  assert.match(chunk, /mip = - 2\.0 \* log2\( 1\.16 \* roughness \)/, "and its curve past them");
  const [[r0, m0], [r1, m1], [r4, m4], [r5, m5], [r6, m6]] = CUBE_UV_ANCHORS;
  const roughnessToMip = (r) => (r >= r1 ? (r0 - r) * (m1 - m0) / (r0 - r1) + m0
    : r >= r4 ? (r1 - r) * (m4 - m1) / (r1 - r4) + m1
      : r >= r5 ? (r4 - r) * (m5 - m4) / (r4 - r5) + m4
        : r >= r6 ? (r5 - r) * (m6 - m5) / (r5 - r6) + m5
          : -2 * Math.log2(1.16 * r));
  for (let mip = -2; mip <= 8; mip += 1) assert.ok(Math.abs(roughnessToMip(cubeUVRoughness(mip)) - mip) < 1e-9, `level ${mip}`);
  assert.deepEqual([cubeUVRoughness(2), cubeUVRoughness(-2)], [0.4, 1]);
});

test("an image's mipmaps: each texel the mean of the four under it, down to one", () => {
  const data = Float32Array.from({ length: 4 * 2 * 4 }, (_, at) => (at % 4 === 3 ? 1 : Math.floor(at / 4)));
  const levels = equirectangularMipmaps({ width: 4, height: 2, data });
  assert.deepEqual(levels.map(({ width, height }) => [width, height]), [[4, 2], [2, 1], [1, 1]]);
  assert.equal(levels[0].data, data);
  assert.deepEqual(Array.from(levels[1].data), [2.5, 2.5, 2.5, 1, 4.5, 4.5, 4.5, 1], "texels 0 1 4 5 and 2 3 6 7");
  assert.deepEqual(Array.from(levels[2].data), [3.5, 3.5, 3.5, 1]);
});

test("OCCT's irradiance: an even light everywhere, and a sky over a dark ground", () => {
  const even = occtIrradianceHarmonics(image(64, 32, 0.25, 0.25), LOOK_TURN);
  for (const normal of [[0, 0, 1], [0, 0, -1], [1, 0, 0], [0, -0.6, 0.8]]) {
    assert.ok(Math.abs(irradiance(even, normal) - 0.25) < 0.0025, `even at ${normal}`);
  }
  // A sky of radiance 1 over the document's horizon lights a surface (1 + n.z) / 2 (over pi).
  const sky = occtIrradianceHarmonics(image(64, 32, 1, 0), LOOK_TURN);
  for (const normal of [[0, 0, 1], [0, 0, -1], [1, 0, 0], [0, -1, 0], [0.6, 0, 0.8]]) {
    assert.ok(Math.abs(irradiance(sky, normal) - (1 + normal[2]) / 2) < 0.03, `sky at ${normal}: ${irradiance(sky, normal)}`);
  }
});

/** THREE whose PMREM generator lays its levels out as three's does for a `2 ** lodMax` cube and draws them by `_applyPMREM`. */
function headless(lodMax = 7) {
  const made = [];
  class PMREMGenerator {
    constructor(renderer) {
      this._renderer = renderer;
    }

    fromEquirectangular(texture) {
      this._lodMax = lodMax;
      this._cubeSize = 2 ** lodMax;
      this._sizeLods = [];
      this._lodMeshes = [];
      for (let lod = lodMax, at = 0; at < lodMax - 4 + 1 + 6; at += 1) {
        this._sizeLods.push(2 ** lod);
        this._lodMeshes.push(new THREE.Mesh(new THREE.BufferGeometry()));
        if (lod > 4) lod -= 1;
      }
      const target = new THREE.WebGLRenderTarget(3 * Math.max(this._cubeSize, 112), 4 * this._cubeSize);
      this._applyPMREM(target);
      made.push({ texture, target, generator: this });
      return target;
    }

    dispose() {
      this.disposed = true;
    }
  }
  return { three: { ...THREE, PMREMGenerator }, made };
}

test("every level past the image is drawn where three reads it: the GGX lobe of its roughness, the roughest OCCT's irradiance", () => {
  const { three, made } = headless(7);
  const { renderer, draws } = recordingRenderer();
  const drawn = [];
  const render = renderer.render;
  renderer.render = (mesh, camera) => {
    drawn.push({ name: mesh.material.name, roughness: mesh.material.uniforms.roughness?.value,
      source: mesh.material.uniforms.source?.value ?? null });
    render(mesh, camera);
  };
  const lit = image(16, 8, 1, 0, [Math.PI / 2, 0, 0]);
  const target = prefilterEnvironment(three, renderer, lit);
  assert.equal(made.length, 1);
  const [{ texture, generator }] = made;
  assert.equal(target, made[0].target);
  assert.deepEqual([texture.mapping, texture.type, texture.image.width], [THREE.EquirectangularReflectionMapping, THREE.HalfFloatType, 16],
    "three's first level is the image itself, in half floats");
  assert.equal(generator.disposed, true);
  // Levels 1-8 (mips 6 down to -1) and the roughest, at three's places in its CubeUV.
  assert.deepEqual(draws.map(({ viewport }) => viewport.toArray()), [
    [0, 256, 192, 128], [0, 384, 96, 64], [0, 448, 48, 32], [48, 448, 48, 32], [96, 448, 48, 32], [144, 448, 48, 32],
    [192, 448, 48, 32], [240, 448, 48, 32], [288, 448, 48, 32]
  ]);
  assert.ok(draws.every((draw) => draw.target === target && draw.autoClear === false));
  assert.deepEqual(drawn.map(({ name }) => name), [...Array(8).fill("GGXEnvironment"), "GGXEnvironmentIrradiance"]);
  assert.deepEqual(drawn.slice(0, 8).map(({ roughness }) => roughness), [6, 5, 4, 3, 2, 1, 0, -1].map(cubeUVRoughness));
  const source = drawn[0].source;
  assert.deepEqual(source.mipmaps.map(({ width, height }) => [width, height]), [[16, 8], [8, 4], [4, 2], [2, 1], [1, 1]],
    "filtered from the image's own mipmaps");
  assert.equal(source.minFilter, THREE.LinearMipmapLinearFilter);
  assert.equal(renderer.autoClear, true, "the renderer given back as it was");
});
