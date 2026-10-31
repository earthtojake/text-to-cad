import assert from "node:assert/strict";
import test from "node:test";
import { resolveCadEdgeSettings, resolveCadGridSettings } from "./cadInk.js";
import { GRID_LINE_DEFAULTS } from "../lib/viewer/stageGrid.js";

test("fixed CAD classes keep distinct restrained widths", () => {
  const classes = resolveCadEdgeSettings().classes;
  assert.deepEqual(Object.values(classes).map((style) => style.thickness), [1, 0.65, 0.8, 0]);
});

test("edge color is configurable while widths stay fixed and grid adapts to appearance", () => {
  const edges = resolveCadEdgeSettings({ color: "#ff0000", thickness: 6 });
  assert.equal(edges.thickness, 1);
  assert.equal(edges.color, "#ff0000");
  assert.equal(new Set(["feature", "tangent", "seam"].map((id) => edges.classes[id].color)).size, 1);
  assert.equal(new Set(Object.values(resolveCadEdgeSettings().classes).map(style => style.color)).size, 3);
  for (const colorMode of ["light", "dark"]) {
    const grid = resolveCadGridSettings({ enabled: true, density: 4 }, { colorMode });
    assert.equal(grid.enabled, true);
    assert.equal(grid.density, 4, "a view's grid density reaches the grid");
    assert.equal(resolveCadGridSettings({ enabled: true }, { colorMode }).density, 1, "and is 1 unless a view sets it");
    assert.equal(grid.opacity, GRID_LINE_DEFAULTS[colorMode].opacity);
  }
  // The lines adapt to the backdrop, and so do the red X and green Y axes.
  const [light, dark] = ["light", "dark"].map(colorMode => resolveCadGridSettings({ enabled: true }, { colorMode }));
  for (const name of ["color", "xAxisColor", "yAxisColor"]) assert.notEqual(light[name], dark[name], name);
});


test("an explicit grid colour is every line's but the axes', which stay red and green", () => {
  for (const colorMode of ["light", "dark"]) {
    const grid = resolveCadGridSettings({ enabled: true, color: "#123456", opacity: 0 }, { colorMode });
    assert.deepEqual({ ...grid, xAxisColor: undefined, yAxisColor: undefined },
      { enabled: true, color: "#123456", opacity: 0, density: 1, xAxisColor: undefined, yAxisColor: undefined });
    assert.notEqual(grid.xAxisColor, "#123456");
    assert.notEqual(grid.yAxisColor, "#123456");
  }
});
