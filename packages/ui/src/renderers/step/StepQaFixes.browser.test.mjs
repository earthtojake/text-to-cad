import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { serveStepHarness } from '../harness/stepScenario.mjs';

// Fixes from a QA pass over the STEP renderer, each pinned in a real browser over the committed
// fixture (`__fixtures__/step`, served by `renderers/harness/stepScenario.mjs`): the two-part
// `hinge_block`, and its base staged alone as the single-part STEP cadgen writes.

let harness, lone;
const cleanups = [];
before(async () => {
  const lifetime = { after: cleanup => cleanups.push(cleanup) };
  [harness, lone] = await Promise.all([serveStepHarness(lifetime), serveStepHarness(lifetime, { singlePart: true })]);
});
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
  await pane.getByRole('region', { name: 'Features', exact: true }).waitFor();
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ axes: { enabled: false } }));
  await page.waitForTimeout(400);
  await settle(page);
  const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  return {
    ...view, box,
    at: projector(await page.evaluate(() => window.__cadCamera()), box),
    state: () => page.evaluate(() => window.cadHarness.a.controller.readState()),
    tool: name => pane.locator('[data-cad-toolbar]').getByRole('button', { name, exact: true }),
    // Display is not a tool: its settings are a popover from the button beside Preview.
    displayButton: () => pane.getByRole('button', { name: 'Display settings', exact: true }),
    tools: () => pane.locator('[data-cad-toolbar]').getByRole('button')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    displayPanel: () => page.locator('[data-display-popover]'),
  };
}
const pressed = async view => (await view.tools()).filter(tool => tool.endsWith(':true')).map(tool => tool.split(':')[0]);
const selection = async view => { const { selectedPartIds, selectedReferenceIds } = await view.state(); return { selectedPartIds, selectedReferenceIds }; };
// A press acts at once; a frame lets what it changed reach the screen.
const afterPress = async page => { await settle(page); };

test('opening Display leaves the tool and the selection as they are; a press on the model closes it, and the camera still orbits', async () => {
  const view = await open(harness);
  const { page, at, box, errors } = view;
  const openDisplay = async () => { await view.displayButton().click(); await view.displayPanel().waitFor(); };

  // Under Select, with the base picked: Display opens over it and changes neither.
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => { const state = window.cadHarness.a.controller.readState();
    return state.selectedPartIds.length + state.selectedReferenceIds.length > 0; });
  await afterPress(page);
  const picked = await selection(view);
  await openDisplay();
  assert.deepEqual(await pressed(view), ['Select'], 'Display is not a tool: Select stays the tool');
  assert.deepEqual(await selection(view), picked, 'and the selection stays');
  assert.equal(await view.tool('Display').count(), 0, 'there is no Display on the strip');
  // A press on the model puts it away; Select is still the tool.
  await page.mouse.click(...at([6, 6, 5]));
  await view.displayPanel().waitFor({ state: 'detached' });
  await afterPress(page);
  assert.deepEqual(await pressed(view), ['Select']);
  assert.equal(await view.displayButton().getAttribute('aria-pressed'), 'false');

  // Under Measure: Display opens beside its panel, and Escape puts it away with Measure still up.
  await view.tool('Measure').click();
  const measurePanel = view.pane.locator('[data-tool-panel][aria-label="Measure controls"]');
  await measurePanel.waitFor();
  await openDisplay();
  assert.deepEqual(await pressed(view), ['Measure']);
  assert.equal(await measurePanel.isVisible(), true, 'Measure\'s panel stays');
  await page.keyboard.press('Escape');
  await view.displayPanel().waitFor({ state: 'detached' });
  assert.deepEqual(await pressed(view), ['Measure']);
  assert.equal(await measurePanel.isVisible(), true);

  // Orbiting is the camera's with Display open: a drag over the model puts Display away and turns
  // the view, and neither measures nor changes the tool.
  await openDisplay();
  const before = await page.evaluate(() => window.__cadCamera().position);
  await page.mouse.move(...at([6, 6, 5]));
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 140, box.y + box.height / 2 + 40, { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(previous => window.__cadCamera().position.some((value, index) => Math.abs(value - previous[index]) > 1e-3), before,
    { timeout: 5000 });
  await view.displayPanel().waitFor({ state: 'detached' });
  await afterPress(page);
  assert.deepEqual(await pressed(view), ['Measure']);
  assert.equal(await view.pane.locator('[data-measure-hint]').count(), 1, 'a drag measures nothing');
  assert.deepEqual(errors, []);
});

test('a single-part STEP names a picked face after its part, never after the XCAF label entry its file carries for a name', async () => {
  const view = await open(lone);
  const { page, pane, at, errors } = view;
  const reference = pane.getByRole('region', { name: 'Reference details', exact: true });
  // The staging is what cadgen writes: one part, named `=>[0:1:1:2]` in the view.
  assert.equal(lone.fixture.view.occurrences[0].name, '=>[0:1:1:2]');
  assert.equal(await view.tool('Explode').count(), 0, 'a single part: no Explode, so this is the lone-part view');
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => /\.f\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  const face = (await view.state()).selectedReferenceIds[0].split('|').at(-1);
  const ordinal = face.replace(/^.*\.f/, '');
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), new RegExp(`^hinge_base · face ${ordinal} Type Face`),
    'the heading is the part, named after the file, and the kind');
  // A second face: the picker's name and every one of its entries read the same way.
  await page.keyboard.down('Shift');
  await page.mouse.click(...at([10, 0, 0]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 2);
  const picker = reference.getByRole('combobox', { name: 'Inspect selected reference' });
  assert.match((await picker.innerText()).replace(/\s+/g, ' '), /^hinge_base · face \d+ 2\/2$/);
  await picker.click();
  const options = await page.getByRole('option').allInnerTexts();
  assert.equal(options.length, 2);
  assert.ok(options.every(option => /^hinge_base · face \d+$/.test(option.trim())), `the picker's entries: ${options}`);
  await page.keyboard.press('Escape');
  assert.doesNotMatch(await pane.innerText(), /=>\[|0:1:1:2/, 'the raw label is nowhere on screen');
  assert.deepEqual(errors, []);
});

test('a single-part STEP: a click selects at once, and a double-click on empty space, with no isolation to leave, keeps the selection its first click found', async () => {
  const view = await open(lone);
  const { page, at, errors } = view;
  const empty = [view.box.x + 30, view.box.y + view.box.height - 30];
  await page.evaluate(() => { window.__clipboardWrites = []; window.cadHarness.a.host.clipboard.writeText = async text => { window.__clipboardWrites.push(text); }; });
  // Under All the one part's faces are what a press picks (Parts is an assembly's mode), and the
  // face is picked by the next frame.
  await page.mouse.click(...at([6, 6, 5]));
  await settle(page);
  const picked = await selection(view);
  assert.equal(picked.selectedReferenceIds.length, 1, `a face is picked by the next frame: ${JSON.stringify(picked)}`);
  // A double-click on empty space: its first click cleared the selection, its second is not a
  // click of its own, and the double-click — with no isolation to leave — puts the pick back.
  await page.mouse.dblclick(...empty);
  await settle(page);
  assert.deepEqual(await selection(view), picked, 'the selection is what it was before the double-click');
  await page.keyboard.down('Shift');
  await page.mouse.dblclick(...empty);
  await page.keyboard.up('Shift');
  await settle(page);
  assert.deepEqual(await selection(view), picked, 'with Shift held too');
  assert.equal(await page.evaluate(() => window.__clipboardWrites.length), 0, 'an empty-space double-click copies nothing');
  // A click on empty space clears at once.
  await page.mouse.click(...empty);
  await settle(page);
  assert.deepEqual(await selection(view), { selectedPartIds: [], selectedReferenceIds: [] });
  // A double-click on the face copies it and leaves it selected, whether or not it was.
  await page.mouse.dblclick(...at([6, 6, 5]));
  await page.waitForFunction(() => window.__clipboardWrites.length === 1);
  await settle(page);
  assert.deepEqual(await selection(view), picked, 'the double-clicked face is the selection');
  await page.mouse.dblclick(...at([6, 6, 5]));
  await page.waitForFunction(() => window.__clipboardWrites.length === 2);
  await settle(page);
  assert.deepEqual(await selection(view), picked, 'and stays it');
  assert.deepEqual(errors, []);
});
