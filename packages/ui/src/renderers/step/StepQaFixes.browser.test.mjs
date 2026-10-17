import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { serveStepHarness } from '../harness/stepScenario.mjs';

// Fixes from a QA pass over the STEP renderer, pinned in a real browser over the committed
// fixture (`__fixtures__/step`, served by `renderers/harness/stepScenario.mjs`): its base staged
// alone as the single-part STEP cadgen writes.

let lone;
const cleanups = [];
before(async () => { lone = await serveStepHarness({ after: cleanup => cleanups.push(cleanup) }, { singlePart: true }); });
after(async () => { for (const cleanup of cleanups.reverse()) await cleanup(); });

const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
/** World point -> page coordinates, from the camera the viewport publishes. */
function projector(camera, box) {
  const sub = (a, b) => a.map((value, index) => value - b[index]);
  const norm = vector => { const length = Math.hypot(...vector); return vector.map(value => value / length); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a.reduce((sum, value, index) => sum + value * b[index], 0);
  const forward = norm(sub(camera.target, camera.position));
  const right = norm(cross(forward, camera.up));
  const up = cross(right, forward);
  const halfWidth = camera.halfHeight * (box.width / box.height);
  return point => {
    const offset = sub(point, camera.target);
    return [box.x + (dot(offset, right) / halfWidth * 0.5 + 0.5) * box.width,
      box.y + (0.5 - dot(offset, up) / camera.halfHeight * 0.5) * box.height];
  };
}

async function open(server) {
  const view = await server.open();
  const { page, pane } = view;
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await pane.locator('[data-cad-toolbar]').getByRole('button', { name: 'Select', exact: true }).waitFor();
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ axes: { enabled: false } }));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.axes?.enabled === false);
  // The opening fit at rest, the same camera two frames running: `at` projects from it.
  await page.waitForFunction(() => {
    const camera = JSON.stringify(window.__cadCamera());
    const still = window.__lastCamera === camera;
    window.__lastCamera = camera;
    return still;
  }, null, { polling: 'raf' });
  await settle(page);
  const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  return {
    ...view, box,
    at: projector(await page.evaluate(() => window.__cadCamera()), box),
    state: () => page.evaluate(() => window.cadHarness.a.controller.readState()),
    tool: name => pane.locator('[data-cad-toolbar]').getByRole('button', { name, exact: true }),
  };
}

test('a single-part STEP names a picked face after its part, by the name the view gives it', async () => {
  const view = await open(lone);
  const { page, pane, at, errors } = view;
  const reference = pane.getByRole('region', { name: 'Reference details', exact: true });
  // The staging is what cadgen writes: one part, named `base` in the view, in `hinge_base.step`.
  assert.equal(lone.fixture.view.occurrences[0].name, 'base');
  assert.equal(await view.tool('Explode').count(), 0, 'a single part: no Explode, so this is the lone-part view');
  // A single part has no tree under Select (its one row would be all of it), and nothing marks
  // Select; its modes are in the navbar, All, Faces and Edges, with no Parts.
  assert.equal(await pane.locator('[data-cad-tool-stack] [data-tool-panel][aria-label="Features"]').count(), 0, 'no tree for a part file');
  assert.equal(await view.tool('Select').locator('[data-tool-panel-closed]').count(), 0);
  await pane.locator('[data-view-controls]').getByRole('button', { name: 'Select mode: All', exact: true }).click();
  assert.deepEqual(await page.locator('[role=menu][aria-label="Select mode"]').getByRole('menuitemradio').allInnerTexts(), ['All', 'Faces', 'Edges']);
  await page.keyboard.press('Escape');
  await page.locator('[role=menu]').waitFor({ state: 'detached' });
  // Its faces load once Select is up: under All a press picks one.
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => /\/f:[\w.]+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  const face = (await view.state()).selectedReferenceIds[0].split('|').at(-1);
  const name = face.replace(/^.*\//, '');
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), new RegExp(`^base · face ${name.replaceAll('.', '\\.')} Area `),
    'the heading is the part, by its own name rather than the file\'s, and the kind, over the face\'s area');
  // A second face: the picker's name and every one of its entries read the same way.
  await page.keyboard.down('Shift');
  await page.mouse.click(...at([10, 0, 0]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 2);
  const picker = reference.getByRole('combobox', { name: 'Inspect selected reference' });
  assert.match((await picker.innerText()).replace(/\s+/g, ' '), /^base · face f:[\w.]+ 2\/2$/);
  await picker.click();
  const options = await page.getByRole('option').allInnerTexts();
  assert.equal(options.length, 2);
  assert.ok(options.every(option => /^base · face f:[\w.]+$/.test(option.trim())), `the picker's entries: ${options}`);
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
});
