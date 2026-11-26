import assert from 'node:assert/strict';
import { test } from 'node:test';
import { serveXbfHarness } from '../harness/xbfScenario.mjs';

// An engine document reopens as it was left, as a STEP did: the Model tree's open rows, the parts
// hidden and the node isolated come back when the view is mounted again over the same tab's record
// (a reload), over core's bracket (a plate and two pegs, one prototype: the pegs fold into one row).
// And what is picked in it reaches the agent as a STEP's did, and Export is handed the document.

test('an engine document reopens with its tree as it was left, and its selection reaches the agent', async (t) => {
  const harness = await serveXbfHarness(t);
  const { page, pane, errors } = await harness.open();
  const loaded = () => page.waitForFunction(() => {
    try { return window.cadHarness.a.controller?.readState().loading === false; } catch { return false; }
  });
  // Every control of the tree's rows, by name: a row's disclosure says whether it is open, its eye
  // whether it is hidden, its Isolate whether it is isolated.
  const rows = () => pane.locator('[aria-label="Modeling tree"] button[aria-label]').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
  await loaded();
  // The Model is the view's panel's first tab (its only one, with no tab row, where nothing has a Position), the panel
  // opened from its pill (the 800px view starts it collapsed).
  const openTree = async () => {
    await pane.locator('[data-navbar-panel="left"]').first().waitFor();
    if (await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').count()) await pane.getByRole('button', { name: 'Show panel', exact: true }).click();
    const tab = pane.locator('[data-flat-panel]').getByRole('tab', { name: 'Model', exact: true });
    if (await tab.count()) await tab.click();
  };
  await openTree();
  await pane.getByRole('button', { name: 'Expand peg (2)', exact: true }).click();
  await pane.getByRole('button', { name: 'Hide plate', exact: true }).click();
  await pane.getByRole('button', { name: 'Isolate peg', exact: true }).first().click();
  const left = await rows();
  for (const control of ['Collapse peg (2)', 'Reveal plate', 'Exit isolate peg']) assert.ok(left.includes(control), `${control} in ${left}`);

  // The view goes and comes back over the same record: the tree is as it was left. It has gone before
  // it comes back: a busy React can take the two calls in one render, and a view that never went keeps
  // its panel as it was.
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('[data-flat-panel]').waitFor({ state: 'detached' });
  await page.evaluate(() => window.cadHarness.mounted(true));
  await loaded();
  await openTree();
  await pane.getByRole('button', { name: 'Collapse peg (2)', exact: true }).waitFor();
  assert.deepEqual(await rows(), left);

  // What is selected is what an agent reads of the view (`cad_view`), and what a capture sent to the
  // chat names: the part's reference, as Copy Prompt copies it.
  const published = await page.evaluate(() => window.cadHarness.exportViews.length);
  await pane.getByRole('button', { name: 'Select peg', exact: true }).first().click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selection.length === 1);
  const selection = await page.evaluate(() => window.cadHarness.a.controller.readState().selection);
  assert.deepEqual(selection.map(reference => [reference.resource.path, reference.target.selectors]), [['/models/bracket.xbf', ['bracket/peg.1']]]);
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  assert.deepEqual(await page.evaluate(() => window.cadHarness.captures[0].references), selection);

  // The view hands Export the displayed document and revision, the menu's whole source: nothing of
  // the selection or the pose, so picking a part publishes nothing new (`ExportControls`).
  const views = await page.evaluate(() => window.cadHarness.exportViews);
  assert.equal(views.length, published, 'a selection is not an export source');
  const shown = views.at(-1);
  assert.ok(shown, 'the view handed Export no document');
  assert.deepEqual(Object.keys(shown).sort(), ['doc', 'file', 'name', 'planar', 'revision']);
  assert.ok(shown.doc && shown.revision, JSON.stringify(shown));
  // A bracket is a solid: the scene it draws is not flat, so its menu has no DXF.
  assert.deepEqual([shown.file, shown.name, shown.planar], ['/models/bracket.xbf', 'bracket.xbf', false]);
  assert.deepEqual(errors, []);
});

// While the file loads, a structure tab with no row shows the panel's placeholder rows, its tabpanel busy.
const loadingRows = scope => scope.locator('aside[data-flat-panel] [role="tabpanel"][aria-busy="true"] [data-tree-row-placeholder]');

// Every file has its panel from the first frame: a STEP's Model tab is there while its structure is on its way, its
// rows once it is in — an assembly's, a part file's one — and the panel open then as it is once the file is in.
test('an engine document (a STEP\'s renderer) has its Model tab from the first frame, open as it stays once the file is in: an assembly\'s rows, a part\'s one', async (t) => {
  const harness = await serveXbfHarness(t);
  // Wide enough that the panel starts open beside the model (it keeps 640px).
  for (const [part, rows] of [[false, ['plate', 'peg (2)']], [true, ['plate']]]) {
    const { page, pane, errors, release } = await harness.open({ part, hold: true, width: 1000 });
    const panel = pane.locator('aside[data-flat-panel]');
    await panel.locator('[data-flat-panel-heading]').filter({ hasText: 'Model' }).waitFor();
    const toggle = pane.locator('[data-viewer-navbar] [data-navbar-panel]');
    const first = await toggle.getAttribute('aria-expanded');
    const names = () => panel.locator('[aria-label="Modeling tree"] [data-tree-row-name]').allInnerTexts();
    assert.deepEqual([first, await pane.locator('[aria-busy="true"]').count() > 0, await names(), await loadingRows(pane).count()], ['true', true, [], 6],
      'open, the file still loading, its placeholder rows');
    release();
    await page.waitForFunction(() => { try { return window.cadHarness.a.controller?.readState().loading === false; } catch { return false; } });
    assert.deepEqual([await names(), await loadingRows(pane).count()], [rows, 0]);
    assert.equal(await toggle.getAttribute('aria-expanded'), first, 'the panel as it was at the first frame');
    assert.deepEqual(errors, []);
  }
});

// A pick puts the keyboard in Quick Edit's note, for the person to write about it; until they do, `[` and `]` still
// step to the folder's previous and next document, as they do anywhere in the view. Once they have written in the note,
// or pressed in it themselves, a bracket is what they type.
test('after a pick, [ and ] still step through the folder until the person writes in the note or presses in it', async (t) => {
  const harness = await serveXbfHarness(t);
  const { page, pane, errors } = await harness.open({ project: true });
  const controller = 'window.cadHarness.a.controller';
  await page.waitForFunction(`${controller}?.readState().loading === false`);
  // Straight down, the camera set from outside: the plate's top (z = 2) at (5, 6), where a press picks it.
  await page.evaluate(`${controller}.setCamera(${JSON.stringify({ position: [0, 0, 100], target: [0, 0, 0], up: [0, 1, 0], orthographicHalfHeight: 20, projection: 'orthographic' })})`);
  const box = await pane.locator('canvas').first().boundingBox();
  const plate = { x: box.x + box.width / 2 + 5 * box.height / 40, y: box.y + box.height / 2 - 6 * box.height / 40 };
  const note = pane.locator('[data-quick-edit-note]');
  const noteFocused = () => page.waitForFunction(() => document.activeElement?.matches('[data-quick-edit-note]'));
  const opened = () => page.evaluate(() => window.cadHarness.opened.slice());
  // A press on the plate, nothing selected before it.
  const pick = async () => {
    await page.mouse.move(plate.x, plate.y);
    await page.mouse.click(plate.x, plate.y);
    await page.waitForFunction(`${controller}.readState().selection.length === 1`);
    await noteFocused();
  };

  // The pick takes the keyboard into the note; ] and [ are still the folder's, and nothing is written.
  await pick();
  await page.keyboard.press(']');
  await page.keyboard.press('[');
  assert.deepEqual([await opened(), await note.textContent()], [['/models/after.step', '/models/before.step'], '']);
  // Once the person writes, a bracket is theirs.
  await page.keyboard.type('Round [it]');
  assert.deepEqual([await opened(), await note.textContent()], [['/models/after.step', '/models/before.step'], 'Round [it]']);

  // A press in the note is the person's too, empty or not: after a pick, a press in it and a bracket is typed.
  await page.keyboard.press('ControlOrMeta+KeyA');
  await page.keyboard.press('Backspace');
  // Escape in the emptied note is the view's too: the selection goes, and the next press picks afresh.
  await page.keyboard.press('Escape');
  await page.waitForFunction(`${controller}.readState().selection.length === 0`);
  await pick();
  await note.click();
  await page.keyboard.type('[');
  assert.deepEqual([await opened(), await note.textContent()], [['/models/after.step', '/models/before.step'], '[']);
  assert.deepEqual(errors, []);
});
