import assert from 'node:assert/strict';
import { PNG } from 'pngjs';

// The drawing tools (Pencil and Shapes) end to end in a real browser: the viewer's own ink, drawn over the real viewport
// and projected into the real model. Unit tests cover the session, the ink geometry and the
// projection; this is the flow a person actually uses.
//
// They are KIT tools, so this body takes an already-open page and knows nothing about the frame
// that mounted it: one scenario, run under each frame that offers them. Today that is the engine
// document's renderer, an .xbf's and a STEP's (`serveXbfHarness`).
//
// Ink is read off screenshots of the viewport, by colour, with the chrome hidden -- and with the drawing
// surface's own preview canvas hidden, so what is counted is the ink the scene draws in WebGL, in the model.

// The chrome over the viewport (the strip and its panels, the cube and its axes, menus) and the
// stroke preview: none of it is ink in the model.
const HIDDEN = '[data-cad-tool-groups], [data-file-sidebar-room], [aria-label="View cube"], [data-slot=popover-content], '
  + '[data-cad-annotation-overlay] canvas { visibility: hidden !important; }';
// Neon red (#ff2d55, the pen's default) and neon green (#39ff14). The fixture's parts are blue and
// grey-blue, neither of them red or green.
const RED = (r, g, b) => r > 200 && g < 100 && b > 50 && b < 150;
const GREEN = (r, g, b) => g > 200 && r < 140 && b < 100;
const NONE = 10;

/**
 * @param {{ page: import('playwright').Page, pane: import('playwright').Locator, errors: string[],
 *   update?: () => Promise<void> }} view
 *   A page the harness has opened on a file whose renderer offers Pencil and Shapes; `update`, where the frame's
 *   harness has one, saves the file again and settles once the new revision is on screen.
 */
export async function runAnnotateScenario({ page, pane, errors, update }) {
  const viewport = pane.locator('[aria-busy] > div > canvas').first();
  // The annotation has no panel: it is Quick Edit's Annotation chip, whose X clears it.
  const panel = pane.locator('[data-quick-edit-ref="annotation"]');
  const strip = pane.getByRole('group', { name: 'Interaction tools' });
  const tool = name => strip.getByRole('button', { name, exact: true });
  // The drawing controls: ONE row hung under the strip, for Pencil and Shapes alike — the tools of the one that is up,
  // what is drawn next, its history.
  const controls = pane.getByRole('toolbar', { name: 'Annotation controls', exact: true });
  const annotateHistory = name => controls.getByRole('button', { name, exact: true });
  // What a strip tool draws with: a button at the row's start, once the strip tool is up.
  const chooseTool = async (family, name) => {
    if (await tool(family).getAttribute('aria-pressed') !== 'true') await tool(family).click();
    await controls.getByRole('group', { name: `${family} tools` }).getByRole('button', { name, exact: true }).click();
  };
  // A setting of what is drawn next, from its dropdown in the row.
  const choose = async (setting, name) => {
    await controls.getByRole('group', { name: 'Annotation style' }).getByRole('button', { name: setting, exact: true }).click();
    // Color's is a grid of swatches, each a plain item; the rest are radio lists.
    await page.getByRole(setting === 'Colour' ? 'menuitem' : 'menuitemradio', { name, exact: true }).click();
  };
  // A shape: its button in the row, Shapes up.
  const shape = name => chooseTool('Shapes', name);
  const names = group => group.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
  const position = () => page.evaluate(() => window.cadHarness.a.controller.readState().camera.position);
  // How far the camera has moved since `from`, in model units (a readback differs in its last bits).
  const moved = async from => Math.hypot(...(await position()).map((value, index) => value - from[index]));

  // The ink on screen: how many pixels are neon red and neon green, and where the red sits.
  const ink = async () => {
    const { width, height, data } = PNG.sync.read(await viewport.screenshot({ style: HIDDEN }));
    const seen = { red: 0, green: 0, x: 0, y: 0 };
    for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4, [r, g, b] = [data[index], data[index + 1], data[index + 2]];
      if (RED(r, g, b)) { seen.red += 1; seen.x += x; seen.y += y; } else if (GREEN(r, g, b)) seen.green += 1;
    }
    if (seen.red) { seen.x /= seen.red; seen.y /= seen.red; }
    return seen;
  };
  // The view reaches what `wanted` asks of its ink: screenshots until it does, failing with the last.
  const until = async (what, wanted, timeout = 10000) => {
    const deadline = Date.now() + timeout;
    for (;;) {
      const seen = await ink();
      if (wanted(seen)) return seen;
      if (Date.now() > deadline) assert.fail(`${what}: ${JSON.stringify(seen)}`);
    }
  };
  const drag = async (from, to) => {
    await page.mouse.move(...from); await page.mouse.down(); await page.mouse.move(...to, { steps: 10 }); await page.mouse.up();
  };

  const draw = tool('Pencil');
  await viewport.waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await until('no ink before drawing', seen => seen.red < NONE && seen.green < NONE);

  // Pencil opens on the pen, Shapes on the rectangle; their controls are one row under the strip, no panel of the tool
  // stack: the colours, then what is drawn next, then the history, all on one line.
  const drawing = ['Pencil', 'Shapes'];
  assert.deepEqual((await names(strip)).filter(name => /^(Pencil|Shapes)/.test(name)), drawing, 'the strip has Pencil and Shapes, plain buttons with no chevron');
  await draw.click();
  const surface = pane.locator('[data-cad-annotation-overlay]');
  await surface.waitFor();
  assert.equal(await draw.getAttribute('aria-pressed'), 'true', 'Pencil is the tool');
  assert.equal(await tool('Shapes').getAttribute('aria-pressed'), 'false');
  assert.equal(await draw.locator('svg').evaluate(icon => icon.getAttribute('class').includes('lucide-pencil')), true, 'Pencil opens on the pen');
  assert.equal(await tool('Shapes').locator('svg').evaluate(icon => icon.getAttribute('class').includes('lucide-square')), true, 'Shapes opens on the rectangle');
  // One row, in order, all on one line: the tools of Pencil, then Color, Stroke width, Placement and Clear.
  const row = await controls.getByRole('button').evaluateAll(buttons => buttons.map(button => [button.getAttribute('aria-label'), button.getBoundingClientRect().top]));
  assert.deepEqual(row.map(([name]) => name), ['Pen', 'Highlighter', 'Eraser', 'Colour', 'Stroke width', 'Placement', 'Clear annotations']);
  assert.equal(await controls.getByRole('button', { name: 'Pen', exact: true }).getAttribute('aria-pressed'), 'true', 'the pen is in hand');
  assert.ok(row.every(([, top]) => top === row[0][1]), 'every control on one line');
  assert.equal(await controls.evaluate(row => Boolean(row.closest('[data-cad-tool-stack], [data-tool-panel]'))), false, 'not a panel of the stack');
  const [stripBox, rowBox] = await Promise.all([strip.boundingBox(), controls.boundingBox()]);
  assert.ok(rowBox.y >= stripBox.y + stripBox.height, 'the row hangs under the strip');
  assert.equal(await panel.count(), 0, 'no Annotation chip before there is ink');
  const copy = panel;
  // Across the middle of the view, clear of the tool stack at its left and Quick Edit at its right.
  const box = await surface.boundingBox();
  const at = (x, y) => [box.x + box.width / 2 + x, box.y + box.height / 2 + y];

  // A pen stroke across the model: red ink on the view's sheet, there once the pen lifts.
  const before = await position();
  await drag(at(-80, 10), at(60, 40));
  const stroke = await until('the stroke is in the model', seen => seen.red > 100);
  await copy.waitFor();
  assert.ok(await moved(before) < 1e-6, 'annotation never moves the camera');

  // Orbited — a right drag over the annotation is the view's — the view keeps the ink where it was
  // drawn on the model: still red, somewhere else.
  await page.mouse.move(...at(150, 150));
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(...at(250, 190), { steps: 8 });
  await page.mouse.up({ button: 'right' });
  // The orbit eases out: the camera is at rest once two readings 100 ms apart agree.
  await page.waitForFunction(() => {
    const now = window.cadHarness.a.controller.readState().camera.position.join();
    const resting = window.__annotateCamera === now;
    window.__annotateCamera = now;
    return resting;
  }, null, { polling: 100 });
  const orbited = await until('the ink orbits with the model',
    seen => seen.red > 50 && Math.hypot(seen.x - stroke.x, seen.y - stroke.y) > 20);
  assert.ok(await moved(before) > 1e-3, 'a right drag orbited the camera');

  // ⌘Z takes the stroke away, ⇧⌘Z brings it back where the view now has it: Undo and Redo
  // are the keyboard's, not buttons.
  await page.keyboard.press('ControlOrMeta+KeyZ');
  await until('Undo removes the stroke', seen => seen.red < NONE);
  await page.keyboard.press('ControlOrMeta+Shift+KeyZ');
  await until('Redo brings it back', seen => seen.red > 50 && Math.hypot(seen.x - orbited.x, seen.y - orbited.y) < 10);

  // Another colour for what is drawn next: a green rectangle beside the red stroke. Each drawing kind keeps its
  // own colour: the pen's is green now, and Shapes' is still the red it opened with until it is chosen too.
  await choose('Colour', 'Neon green');
  await shape('Rectangle');
  assert.equal(await controls.getByRole('button', { name: 'Colour', exact: true }).locator('span').evaluate(swatch => swatch.style.backgroundColor), 'rgb(255, 45, 85)', "Shapes' colour is its own");
  await choose('Colour', 'Neon green');
  await drag(at(-60, -120), at(60, -40));
  await until('a green rectangle beside the red', seen => seen.green > 100 && seen.red > 50);
  await annotateHistory('Clear annotations').click();
  await until('Clear annotation removes all ink', seen => seen.red < NONE && seen.green < NONE);
  await copy.waitFor({ state: 'detached' });

  // The Highlighter, a button of Pencil's row: the strip's Pencil shows it, and a drag puts a stroke down (Quick Edit's chip);
  // it opens in the highlighter's own yellow, not the pen's green.
  await chooseTool('Pencil', 'Highlighter');
  assert.equal(await controls.getByRole('button', { name: 'Colour', exact: true }).locator('span').evaluate(swatch => swatch.style.backgroundColor), 'rgb(255, 230, 0)', "the highlighter's colour is its own");
  assert.equal(await draw.locator('svg').evaluate(icon => icon.getAttribute('class').includes('lucide-highlighter')), true, 'Pencil shows the highlighter');
  assert.equal(await draw.getAttribute('aria-pressed'), 'true');
  await drag(at(-80, 10), at(60, 40));
  await copy.waitFor();
  await annotateHistory('Clear annotations').click();
  await copy.waitFor({ state: 'detached' });

  // Left with ink drawn, the drawing surface and tools go; the ink stays in the model, and its chip in
  // Quick Edit.
  await chooseTool('Pencil', 'Pen');
  await drag(at(-80, 10), at(60, 40));
  // The eraser draws nothing: its row greys out Color, Stroke width and Placement.
  await chooseTool('Pencil', 'Eraser');
  for (const setting of ['Colour', 'Stroke width', 'Placement']) assert.equal(await controls.getByRole('button', { name: setting, exact: true }).isDisabled(), true, `${setting} is greyed out under the Eraser`);
  await chooseTool('Pencil', 'Pen');
  await shape('Rectangle');
  await drag(at(-60, -120), at(60, -40));
  const drawn = await until('the green stroke and rectangle are in the model', seen => seen.green > 200);
  await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button', { name: 'Select', exact: true }).click();
  await surface.waitFor({ state: 'detached' });
  assert.equal(await panel.isVisible(), true, 'the Annotation chip stays with the ink');
  await until('the ink stays after the drawing tools', seen => seen.green > 100);

  // Select picks a mark of the annotation as it picks a part, and Delete deletes what it picked: the
  // stroke, not the rectangle beside it.
  await page.mouse.click(...at(-10, 25));
  await page.keyboard.press('Delete');
  await until('Delete deletes the stroke and keeps the rectangle', seen => seen.green > 100 && seen.green < drawn.green - 50);

  // The rectangle picked, its bar: Fill fills it in its colour, Delete deletes it, fill and all.
  await page.mouse.click(...at(0, -120));
  const bar = pane.getByRole('toolbar', { name: 'Selected annotation' });
  await bar.waitFor();
  await bar.getByRole('button', { name: 'Fill', exact: true }).click();
  assert.equal(await bar.getByRole('button', { name: 'Fill', exact: true }).getAttribute('aria-pressed'), 'true', 'Fill is lit once filled');
  await until('the rectangle is still drawn, filled', seen => seen.green > 100);
  await bar.getByRole('button', { name: 'Delete', exact: true }).click();
  await until('Delete on the bar deletes the rectangle and its fill', seen => seen.green < NONE);
  await bar.waitFor({ state: 'detached' });
  await page.keyboard.press('ControlOrMeta+KeyZ');
  await until('Undo brings them back', seen => seen.green > 100);

  // Back in Select, an ordinary left drag still presents new 3D frames with ink.
  const selectedCamera = await position();
  const selectedFrame = await viewport.screenshot({ style: HIDDEN });
  await drag(at(150, 150), at(250, 190));
  await page.waitForFunction(before => {
    const now = window.cadHarness.a.controller.readState().camera.position;
    return Math.hypot(...now.map((value, index) => value - before[index])) > 1e-3;
  }, selectedCamera);
  assert.notDeepEqual(await viewport.screenshot({ style: HIDDEN }), selectedFrame, 'Select orbit presents a new frame after drawing');

  // An update of the model discards ink drawn over the revision before it, and the panel with it.
  if (update) {
    await update();
    await until('the update discards the ink', seen => seen.green < NONE && seen.red < NONE);
    await panel.waitFor({ state: 'detached' });
  }
  assert.deepEqual(errors, []);
}
