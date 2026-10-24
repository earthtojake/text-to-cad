import assert from 'node:assert/strict';
import { test } from 'node:test';
import { serveXbfHarness } from '../harness/xbfScenario.mjs';

// An engine document's Measure and Look at under real pointers, over core's bracket (a 40 x 20 x 4
// plate on z = -2..2, a Ø6 peg 12 tall standing at x = 12): two presses take two faces whole and
// read what they make, a step Undo takes back; a double-click on a face turns the view square to it
// and picks nothing.

const unit = v => { const length = Math.hypot(...v); return v.map(c => c / length); };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

test('Measure takes two faces whole and reads them square across; a double-click looks square at a face and picks nothing', async (t) => {
  const harness = await serveXbfHarness(t);
  const { page, pane, errors } = await harness.open();
  const controller = 'window.cadHarness.a.controller';
  await page.waitForFunction(`${controller}?.readState().loading === false`);
  const canvas = pane.locator('canvas').first();
  // A camera set from outside, orthographic; where a model point falls on screen under it.
  const view = async (camera) => {
    await page.evaluate(`${controller}.setCamera(${JSON.stringify({ ...camera, projection: 'orthographic' })})`);
    const box = await canvas.boundingBox();
    const live = await page.evaluate(() => window.__cadCamera());
    const forward = unit(live.target.map((value, axis) => value - live.position[axis]));
    const right = unit(cross(forward, live.up)), up = cross(right, forward);
    const scale = box.height / (2 * live.halfHeight / live.zoom);
    return point => {
      const offset = point.map((value, axis) => value - live.target[axis]);
      return { x: box.x + box.width / 2 + dot(offset, right) * scale, y: box.y + box.height / 2 - dot(offset, up) * scale };
    };
  };

  // Straight down: the plate's top (z = 2), then the peg's top (z = 14).
  const down = await view({ position: [0, 0, 100], target: [0, 0, 0], up: [0, 1, 0], orthographicHalfHeight: 20 });
  await pane.getByRole('button', { name: 'Measure', exact: true }).click();
  for (const point of [[5, 6, 2], [12, 0, 14]]) {
    const at = down(point);
    await page.mouse.move(at.x, at.y);
    await page.mouse.click(at.x, at.y);
  }
  const row = pane.locator('[data-measurements]');
  await row.getByText('⟂ 12.00 mm').waitFor();
  // Taking it was a step of the view's history, as ink is: ⌘Z takes it away, ⇧⌘Z brings it back.
  await page.keyboard.press('ControlOrMeta+KeyZ');
  await row.waitFor({ state: 'detached' });
  await page.keyboard.press('ControlOrMeta+Shift+KeyZ');
  await row.getByText('⟂ 12.00 mm').waitFor();

  // Select picking Faces (in an assembly, All takes a part whose row is shut whole); from up and off
  // to the front-right, a double-click on the plate's front face.
  await pane.locator('[data-select-filter-trigger]').click();
  await page.locator('[data-select-filter="faces"]').click();
  const oblique = await view({ position: [60, -80, 70], target: [0, 0, 0], up: [0, 0, 1], orthographicHalfHeight: 30 });
  const front = oblique([5, -10, 0]);
  await page.mouse.dblclick(front.x, front.y);
  // The view turns to look along the face's normal, from the side the camera was on.
  await page.waitForFunction(() => {
    const live = window.__cadCamera();
    const toEye = live.position.map((value, axis) => value - live.target[axis]);
    return toEye[1] < 0 && Math.abs(toEye[0]) < 1e-3 * Math.hypot(...toEye) && Math.abs(toEye[2]) < 1e-3 * Math.hypot(...toEye);
  });
  // And its first click's pick was put back: nothing is selected.
  assert.deepEqual(await page.evaluate(`${controller}.readState().selected`), []);
  assert.deepEqual(errors, []);
});
