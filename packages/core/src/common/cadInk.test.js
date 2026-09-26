import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { resolveCadEdgeSettings, resolveCadGridSettings } from "./cadInk.js";
import { buildCadEdgeSegmentTexture, CadEdgeInstances } from "./cadEdgeInstances.js";
import { screenSpaceLineDeviceResolution, syncScreenSpaceLineMaterialResolution } from "./renderEdges.js";

test("fixed CAD classes retain distinct restrained device-pixel ink at every pixel ratio", () => {
  const classes = resolveCadEdgeSettings().classes;
  assert.deepEqual(Object.values(classes).map((style) => style.thickness), [1, 0.65, 0.8, 0]);
  const segments = buildCadEdgeSegmentTexture(THREE, {
    positions: new Float32Array([0, 0, 0, 1, 0, 0]), indices: new Uint32Array([0, 1])
  }, [{ classId: "feature", segmentStart: 0, segmentCount: 1 }]);
  const set = new CadEdgeInstances(THREE, { segments, classStyles: Object.entries(classes).map(([classId, style]) => ({ ...style, classId, color: new THREE.Color(style.color) })) });
  for (const dpr of [1, 2, 3]) {
    const resolution = screenSpaceLineDeviceResolution({ getPixelRatio: () => dpr }, 800, 600);
    syncScreenSpaceLineMaterialResolution(set.materials, resolution.width, resolution.height);
    for (const [index, classId] of ["feature", "tangent", "seam"].entries()) {
      const width = set.uniforms.cadClassWidth.value.getComponent(index);
      const effectiveDeviceWidth = width * 600 * dpr / set.uniforms.resolution.value.y;
      assert.equal(effectiveDeviceWidth, classes[classId].thickness);
      assert.ok(effectiveDeviceWidth / dpr <= 1 / dpr);
    }
  }
  set.dispose();
  segments.texture.dispose();
});

test("edge color is configurable while widths stay fixed and grid adapts to appearance", () => {
  const edges = resolveCadEdgeSettings({ color: "#ff0000", thickness: 6 });
  assert.equal(edges.thickness, 1);
  assert.equal(edges.color, "#ff0000");
  assert.equal(new Set(["feature", "tangent", "seam"].map((id) => edges.classes[id].color)).size, 1);
  assert.equal(new Set(Object.values(resolveCadEdgeSettings().classes).map(style => style.color)).size, 3);
  for (const colorMode of ["light", "dark"]) {
    const grid = resolveCadGridSettings({ enabled: true, density: 4, centerColor: "#ff0000" }, { colorMode });
    assert.equal(grid.enabled, true);
    assert.equal(grid.density, 1);
    assert.equal(grid.opacity, 0.16);
    assert.notEqual(grid.centerColor, "#ff0000");
  }
});


test("explicit grid appearance maps identically to cell and origin lines", () => {
  for (const colorMode of ["light", "dark"]) {
    assert.deepEqual(resolveCadGridSettings({ enabled: true, color: "#123456", opacity: 0 }, { colorMode }), {
      enabled: true, centerColor: "#123456", cellColor: "#123456", opacity: 0, density: 1
    });
  }
});
