import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import * as THREE from "three";

import { xbfLookParameters } from "../xbf/xbfScene.js";
import { previewOpacity, transmittedOpacity } from "./previewOpacity.js";

// The engine holds its own copies to the same cases (`test_materials.py`).
const PARITY = JSON.parse(readFileSync(new URL("./previewOpacity.parity.json", import.meta.url), "utf8"));

test("a transmissive look's preview is the engine's, case for case", () => {
  assert.ok(PARITY.previewCases.length);
  for (const { why, alpha, transmission, preview } of PARITY.previewCases) {
    assert.equal(previewOpacity(alpha, transmission), preview, why);
  }
});

test("an xbf's transmissive look is one fade: its GLB's alpha with transmission, its preview without", () => {
  assert.ok(PARITY.lookCases.length);
  for (const { why, opacity, transmission, transmitted, preview } of PARITY.lookCases) {
    assert.equal(transmittedOpacity(opacity), transmitted, why);
    assert.equal(previewOpacity(transmitted, transmission), preview, why);
    // The colour's alpha is build123d's preview already (or one that cannot be told from it): not applied again.
    for (const alpha of [1, preview, 0.3]) {
      const look = xbfLookParameters(THREE, [1, 1, 1, alpha], { pbr: { values: { transmission, opacity } } });
      assert.deepEqual([look.opacity, look.transparent, look.depthWrite, look.transmission, look.userData.cadPreviewOpacity],
        [transmitted, transmitted < 1, transmitted >= 1, transmission, preview], `${why}, colour alpha ${alpha}`);
    }
  }
});
