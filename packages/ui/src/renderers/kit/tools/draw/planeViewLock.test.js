import assert from "node:assert/strict";
import test from "node:test";
import { planeViewForViewport } from "./planeViewLock.js";

// A point of the picture and a point of the ink that were on the same pixel stay on the same pixel.
const plotToScreen = (t, [x, y]) => [x * t.scale + t.offsetX, -y * t.scale + t.offsetY];
const inkToScreen = (v, [x, y]) => [(x + v.scrollX) * v.zoom, (y + v.scrollY) * v.zoom];
const screenToInk = (v, [x, y]) => [x / v.zoom - v.scrollX, y / v.zoom - v.scrollY];

test("the picture follows the editor's scroll and zoom, so ink stays on it", () => {
  const lock = { transform: { scale: 8, offsetX: 100, offsetY: 400 }, viewport: { scrollX: 3, scrollY: -2, zoom: 1.5 } };
  const point = [12.5, 30];
  const ink = screenToInk(lock.viewport, plotToScreen(lock.transform, point));
  for (const viewport of [{ scrollX: 3, scrollY: -2, zoom: 1.5 }, { scrollX: 40, scrollY: 10, zoom: 1.5 }, { scrollX: -7, scrollY: 25, zoom: 3.25 }]) {
    const followed = planeViewForViewport(lock, viewport);
    const [bx, by] = plotToScreen(followed, point);
    const [ix, iy] = inkToScreen(viewport, ink);
    assert.ok(Math.abs(bx - ix) < 1e-9 && Math.abs(by - iy) < 1e-9, JSON.stringify(viewport));
  }
});
