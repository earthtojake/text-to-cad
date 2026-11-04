// The rig's environment prefiltered as OCCT bakes it (`ggxEnvironment.js`): three's PMREM, each
// level the GGX lobe of its roughness, the roughest OCCT's irradiance; and that irradiance itself.
import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { occtIrradianceHarmonics, prefilterEnvironment } from "./ggxEnvironment.js";

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

/** THREE whose PMREM generator fills a cube's `levels` as three's does (`_applyPMREM`, each by `_renderCube`). */
function headless(levels = 6) {
  const made = [];
  class PMREMGenerator {
    constructor(renderer) {
      this._renderer = renderer;
      this.drawn = [];
    }

    fromEquirectangular(texture) {
      const target = { texture: { mipmaps: Array.from({ length: levels }, () => ({})) } };
      this._applyPMREM(target);
      made.push({ texture, target, generator: this });
      return target;
    }

    _applyPMREM(target) {
      for (let lod = 0; lod < target.texture.mipmaps.length; lod += 1) this._renderCube(target, lod, { name: "three's GGX" });
    }

    _renderCube(target, lod, material) {
      this.drawn.push({ target, lod, name: material.name, harmonics: material.uniforms?.harmonics.value.map((band) => band.toArray()) });
    }

    dispose() {
      this.disposed = true;
    }
  }
  return { three: { ...THREE, PMREMGenerator }, made };
}

test("three fills every level with the GGX lobe of its roughness; the roughest is then OCCT's irradiance", () => {
  const { three, made } = headless(6);
  const lit = image(16, 8, 1, 0, [Math.PI / 2, 0, 0]);
  const target = prefilterEnvironment(three, {}, lit);
  assert.equal(made.length, 1);
  const [{ texture, generator }] = made;
  assert.equal(target, made[0].target);
  assert.deepEqual([texture.mapping, texture.type, texture.image.width], [THREE.EquirectangularReflectionMapping, THREE.HalfFloatType, 16],
    "three prefilters the image itself, in half floats");
  assert.equal(generator.disposed, true);
  assert.deepEqual(generator.drawn.map(({ lod, name }) => [lod, name]),
    [...[0, 1, 2, 3, 4, 5].map((lod) => [lod, "three's GGX"]), [5, "GGXEnvironmentIrradiance"]]);
  assert.ok(generator.drawn.every((draw) => draw.target === target));
  const harmonics = occtIrradianceHarmonics(lit, (x, y, z) => new THREE.Vector3(x, y, z)
    .applyMatrix3(new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0)))).toArray());
  const drawnHarmonics = generator.drawn.at(-1).harmonics.flat();
  assert.ok(drawnHarmonics.every((value, at) => Math.abs(value - harmonics[at]) < 1e-6), "the image's own harmonics");
});
