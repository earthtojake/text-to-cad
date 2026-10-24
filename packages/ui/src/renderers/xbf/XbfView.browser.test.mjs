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
  await pane.getByRole('button', { name: 'Model tree', exact: true }).click();
  await pane.getByRole('button', { name: 'Expand peg (2)', exact: true }).click();
  await pane.getByRole('button', { name: 'Hide plate', exact: true }).click();
  await pane.getByRole('button', { name: 'Isolate peg', exact: true }).first().click();
  const left = await rows();
  for (const control of ['Collapse peg (2)', 'Reveal plate', 'Exit isolate peg']) assert.ok(left.includes(control), `${control} in ${left}`);

  // The view goes and comes back over the same record: the tree is as it was left.
  await page.evaluate(() => window.cadHarness.mounted(false));
  await page.evaluate(() => window.cadHarness.mounted(true));
  await pane.getByRole('button', { name: 'Model tree', exact: true }).waitFor();
  await loaded();
  await pane.getByRole('button', { name: 'Model tree', exact: true }).click();
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
  assert.deepEqual(Object.keys(shown).sort(), ['doc', 'file', 'name', 'preview', 'revision']);
  assert.ok(shown.doc && shown.revision, JSON.stringify(shown));
  assert.deepEqual([shown.file, shown.name, shown.preview], ['/models/bracket.xbf', 'bracket.xbf', false]);
  assert.deepEqual(errors, []);
});
