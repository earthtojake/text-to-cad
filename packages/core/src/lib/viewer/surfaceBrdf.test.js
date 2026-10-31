// OCCT's PBR program as the viewer draws it (`surfaceBrdf.js`): its split-sum table OCCT's own, and
// its lobe isotropic whatever a material's anisotropy, as OCCT's program is.
import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { occtEnvironmentScaleBias, occtEnvironmentTable, useSurfaceBrdf } from "./surfaceBrdf.js";

// OCCT 7.9's `Graphic3d_PBRMaterial::GenerateEnvLUT` (64 x 64, 4096 samples) at five of its texels:
// N.V, roughness, scale, bias. three's own table has some 10% more scale at the first.
const OCCT_TABLE = Object.freeze([
  [0.492063, 0.402857, 0.7940, 0.0261], [0.301587, 0.198571, 0.7636, 0.1458], [0.904762, 0.497143, 0.8746, 0.0003],
  [0.158730, 0.795714, 0.6070, 0.0239], [0.793651, 0.088571, 0.9976, 0.0004]
]);

test("the split-sum table is OCCT's", () => {
  for (const [nv, roughness, scale, bias] of OCCT_TABLE) {
    const [found, offset] = occtEnvironmentScaleBias(nv, roughness);
    assert.ok(Math.abs(found - scale) < 0.01 && Math.abs(offset - bias) < 0.01, `N.V ${nv}, roughness ${roughness}: ${found}, ${offset}`);
  }
  const table = occtEnvironmentTable(THREE);
  assert.equal(occtEnvironmentTable(THREE), table, "one for the page");
  assert.deepEqual([table.image.width, table.image.height, table.format, table.type], [32, 32, THREE.RGFormat, THREE.HalfFloatType]);
  assert.deepEqual([table.minFilter, table.magFilter], [THREE.LinearFilter, THREE.LinearFilter]);
  // A texel holds its centre's values: across by N.V, down by roughness.
  const [scale, bias] = occtEnvironmentScaleBias(15.5 / 32, 12.5 / 32);
  const at = (12 * 32 + 15) * 2;
  assert.ok(Math.abs(THREE.DataUtils.fromHalfFloat(table.image.data[at]) - scale) < 1e-3);
  assert.ok(Math.abs(THREE.DataUtils.fromHalfFloat(table.image.data[at + 1]) - bias) < 1e-3);
});

test("the program draws OCCT's isotropic lobe and table, whatever a material's anisotropy", () => {
  const material = new THREE.MeshPhysicalMaterial({ anisotropy: 0.3, roughness: 0.35, metalness: 1 });
  assert.equal(useSurfaceBrdf(THREE, material, "occt"), true);
  const shader = { fragmentShader: THREE.ShaderLib.physical.fragmentShader, uniforms: {} };
  material.onBeforeCompile(shader);
  const text = shader.fragmentShader;
  const occt = text.slice(text.indexOf("// OCCT 7.9's PBR program"), text.indexOf("#define RE_IndirectSpecular RE_IndirectSpecular_Occt"));
  assert.ok(occt.includes("RE_Direct_Occt") && occt.includes("RE_IndirectSpecular_Occt"));
  assert.doesNotMatch(occt, /USE_ANISOTROPY|BRDF_GGX\(|material\.dfg/, "no anisotropic lobe, no bent reflection, not three's table");
  assert.match(occt, /texture2D\( occtEnvironmentTable, vec2\( dotNV, material\.roughness \) \)/);
  assert.equal(shader.uniforms.occtEnvironmentTable.value, occtEnvironmentTable(THREE));
});
