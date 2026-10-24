import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runAnnotateScenario } from '../../../harness/annotateScenario.mjs';
import { serveXbfHarness } from '../../../harness/xbfScenario.mjs';

// The drawing tools under the frame that ships them: the engine document's renderer
// (`renderers/xbf`, which draws an .xbf and a STEP), over core's bracket fixture. They are kit
// tools, so the scenario itself (`harness/annotateScenario.mjs`) knows nothing about the frame.

test('the drawing tools put ink into the model that orbits with it, undo, redo, recolour and clear, and stay when they are left — where Select picks, haloes and deletes it — and goes when the model updates', async (t) => {
  const harness = await serveXbfHarness(t);
  await runAnnotateScenario(await harness.open());
});

test('the drawing controls are one row at every width, its buttons in order on one line, the tools of Shapes in place of Pencil\'s; on a phone the same row, in touch tiles', async (t) => {
  const harness = await serveXbfHarness(t);
  const { page, pane, errors } = await harness.open();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  const pencil = pane.getByRole('button', { name: 'Pencil', exact: true });
  const shapes = pane.getByRole('button', { name: 'Shapes', exact: true });
  await pencil.click();
  const controls = pane.getByRole('toolbar', { name: 'Annotation controls', exact: true });
  const layout = () => controls.evaluate(row => [...row.querySelectorAll('button')].map(button => ({ name: button.getAttribute('aria-label'), box: button.getBoundingClientRect() })));
  for (const width of [1280, 960, 768, 600]) {
    await page.setViewportSize({ width, height: 600 });
    for (const [tool, names] of [[pencil, ['Pen', 'Highlighter', 'Eraser']], [shapes, ['Rectangle', 'Line', 'Arrow', 'Ellipse', 'Text']]]) {
      await tool.click();
      const buttons = await layout();
      assert.deepEqual(buttons.map(button => button.name), [...names, 'Color', 'Stroke width', 'Placement', 'Clear annotations']);
      assert.ok(buttons.every(button => button.box.top === buttons[0].box.top), `${width}px: every control on one line`);
      assert.ok(buttons.every((button, index) => index === 0 || button.box.left > buttons[index - 1].box.left), `${width}px: left to right in order`);
    }
  }
  // A phone: the same row under the strip, in 36px tiles; the strip tools have no chevron.
  await page.setViewportSize({ width: 390, height: 700 });
  await pencil.click();
  assert.equal(await controls.getAttribute('data-touch'), '');
  assert.equal(await pane.getByRole('button', { name: /^(Pencil|Shapes) tools$/ }).count(), 0, 'no chevron');
  const touch = await layout();
  assert.ok(touch.every(button => Math.round(button.box.height) === 36), 'touch tiles');
  await controls.getByRole('button', { name: 'Highlighter', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-cad-toolbar] [aria-label="Pencil"] svg')?.getAttribute('class')?.includes('lucide-highlighter'));
  assert.deepEqual(errors, []);
});
