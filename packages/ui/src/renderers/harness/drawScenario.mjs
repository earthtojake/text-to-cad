import assert from 'node:assert/strict';

// The Draw tool end to end in a real browser: the real drawing editor over the
// real viewport. Unit tests cover the camera mathematics, the editor controller
// and the fill algorithm; this is the flow a person actually uses.
//
// Draw is a KIT tool, so this body takes an already-open page and knows nothing
// about the frame that mounted it: one scenario, run under each frame that
// offers Draw. Today that is STEP (`serveStepHarness`, whose server must keep
// serving `/harness.css` — without the editor's own stylesheet it has no layout
// and sizes its canvas from an unconstrained container).

/**
 * @param {{ page: import('playwright').Page, pane: import('playwright').Locator, errors: string[] }} view
 *   A page the harness has opened on a file whose renderer offers Draw.
 */
export async function runDrawScenario({ page, pane, errors }) {
  // Draw's tools, color and history: a panel in the tool stack for as long as Draw is the tool.
  const menu = pane.locator('[data-tool-panel][aria-label="Drawing controls"]');
  const tool = name => menu.getByRole('button', { name, exact: true });
  // Choosing anything keeps the panel: it is the tool's, not a menu.
  const choose = async name => {
    await tool(name).click();
    assert.equal(await menu.isVisible(), true, `${name} keeps the panel`);
  };
  const camera = () => page.evaluate(() => window.cadHarness.a.controller.readState().camera);
  // What the static ink canvas holds: pixel counts by kind, and the ink's left edge in CSS pixels.
  // Pen ink is as thin as a line's, so a diagonal stroke is mostly antialiased edge: a pixel is
  // ink by its alpha (> 30), its colour is read wherever it is ink, and `opaque`/`translucent`
  // split the ink by coverage (a fill is translucent throughout).
  const ink = () => page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    if (!canvas) return null;
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    const counts = { ink: 0, opaque: 0, translucent: 0, green: 0, red: 0 }; let left = Infinity;
    for (let index = 0; index < data.length; index += 4) {
      const [r, g, b, a] = [data[index], data[index + 1], data[index + 2], data[index + 3]];
      if (a <= 30) continue;
      counts.ink += 1; counts[a > 200 ? 'opaque' : 'translucent'] += 1;
      left = Math.min(left, (index / 4) % canvas.width);
      if (g > 200 && r < 120) counts.green += 1; if (r > 200 && g < 100) counts.red += 1;
    }
    return { ...counts, left: left * canvas.getBoundingClientRect().width / canvas.width };
  });
  // History is mirrored from the SDK asynchronously: wait for a control to settle rather than read it once.
  const settles = (name, enabled) => page.waitForFunction(([name, enabled]) => {
    const button = document.querySelector(`[data-testid="one"] [data-tool-panel][aria-label="Drawing controls"] button[aria-label="${name}"]`);
    return Boolean(button) && button.disabled === !enabled;
  }, [name, enabled], { timeout: 5000 });
  const translucentInk = () => page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
    return translucent;
  });
  const drag = async (from, to) => { await page.mouse.move(...from); await page.mouse.down(); await page.mouse.move(...to, { steps: 8 }); await page.mouse.up(); };

  const draw = pane.getByRole('button', { name: 'Draw', exact: true });
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);

  await draw.click();
  await pane.locator('[data-cad-drawing-overlay] canvas.excalidraw__canvas.interactive').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  await menu.waitFor();
  assert.equal(await tool('Pen').getAttribute('aria-pressed'), 'true', 'Draw opens on the pen');
  // The panel's tools read left to right: the two ways of moving around what was drawn,
  // then the marks; then, with no rule between, the colour and weight they are made in, undo/redo and Clear.
  assert.deepEqual(await menu.getByRole('group', { name: 'Drawing tools' }).getByRole('button')
    .evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
  ['Select and move drawings', 'Pan view', 'Pen', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text', 'Fill area', 'Eraser']);
  assert.deepEqual(await menu.getByRole('group', { name: 'Drawing settings' }).getByRole('button')
    .evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
  ['Color', 'Stroke width', 'Undo', 'Redo', 'Clear drawing']);
  assert.equal(await pane.locator('.layer-ui__wrapper').isVisible(), false, 'the SDK has no controls of its own here');
  // Clear of the tool stack at the overlay's left, where the Drawing panel sits.
  const box = await pane.locator('[data-cad-drawing-overlay]').boundingBox();
  const at = (x, y) => [box.x + 300 + x, box.y + y];

  // Locked: a drag that would have orbited the model draws instead.
  const locked = await camera();
  await drag(at(120, 120), at(260, 150));
  // Exactly, to the last bit a frame's camera readback carries: the pose is re-derived from the controls each time.
  const afterStroke = await camera();
  for (const key of ['position', 'target', 'up']) afterStroke[key].forEach((value, index) => assert.ok(Math.abs(value - locked[key][index]) < 1e-9, `drawing never moves the camera: ${key}[${index}]`));
  // The zoom likewise: the lock re-derives it from the editor's, which rounds in the last bits.
  assert.ok(Math.abs(afterStroke.zoom - locked.zoom) < 1e-9, `drawing never zooms: ${locked.zoom} -> ${afterStroke.zoom}`);
  assert.equal(afterStroke.projection, locked.projection);
  const stroke = await ink();
  assert.ok(stroke.red > 50, `neon red ink: ${JSON.stringify(stroke)}`);
  // A sketch begun opens Quick Edit once the pen lifts, with the view attached, and it takes the keyboard.
  const quickEdit = pane.getByRole('region', { name: 'Quick Edit', exact: true });
  await quickEdit.locator('[data-quick-edit-chip="sketch"]').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'Describe your changes');
  await quickEdit.getByRole('textbox', { name: 'Describe your changes', exact: true }).fill('Add a boss where the ink is.');
  // Put away, the note kept, it leaves the view to the pen: going on drawing does not bring it back.
  await pane.getByRole('button', { name: 'Quick Edit', exact: true }).click();
  await quickEdit.waitFor({ state: 'detached' });
  await settles('Undo', true);
  await settles('Redo', false);
  // Undo and Redo trade places in the history buttons, the one stroke going and coming back.
  await choose('Undo');
  await settles('Undo', false);
  await settles('Redo', true);
  await choose('Redo');
  await settles('Undo', true);
  await settles('Redo', false);

  // Pan belongs to the editor; the camera follows along its own plane.
  await page.mouse.move(...at(200, 300));
  await page.mouse.wheel(-90, 0);
  await page.waitForFunction(left => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    for (let x = 0; x < canvas.width; x += 1) for (let y = 0; y < canvas.height; y += 1) if (data[(y * canvas.width + x) * 4 + 3] > 30) return x * canvas.getBoundingClientRect().width / canvas.width > left + 60;
    return false;
  }, stroke.left);
  const panned = await camera();
  const direction = state => state.position.map((value, index) => value - state.target[index]);
  assert.ok(Math.hypot(...panned.target.map((value, index) => value - locked.target[index])) > 1e-3, 'the model moved with the ink');
  direction(panned).forEach((value, index) => assert.ok(Math.abs(value - direction(locked)[index]) < 1e-6, 'the view direction did not change'));
  // The lock re-derives the camera from the editor's scroll and zoom: the zoom comes back to within rounding, as the direction does.
  assert.ok(Math.abs(panned.zoom - locked.zoom) < 1e-9, `a pan is not a zoom: ${locked.zoom} -> ${panned.zoom}`);

  // The Pan view tool drags the same picture.
  const panInk = (await ink()).ink;
  await choose('Pan view');
  await drag(at(300, 300), at(340, 330));
  const dragged = await camera();
  assert.ok(Math.hypot(...dragged.target.map((value, index) => value - panned.target[index])) > 1e-3);
  assert.equal((await ink()).ink, panInk, 'panning draws nothing');

  // Sticky tools: a rectangle is followed by a rectangle.
  await choose('Rectangle');
  await drag(at(120, 220), at(300, 360));
  assert.equal(await draw.locator('[data-drawing-tool]').getAttribute('data-drawing-tool'), 'rectangle');
  // Color and weight are for what comes next; the red ink stays red. Choosing them never
  // costs the sketch its history (each choice used to hand the panel a fresh, empty one).
  await choose('Color');
  await menu.getByRole('radio', { name: 'Neon green', exact: true }).click();
  await choose('Stroke width');
  await menu.getByRole('radio', { name: 'Bold', exact: true }).click();
  await settles('Undo', true);
  await drag(at(330, 220), at(400, 300));
  const colored = await ink();
  assert.ok(colored.green > 50 && colored.red >= stroke.red, JSON.stringify(colored));
  await settles('Undo', true);

  // Fill: a translucent area inside the first rectangle, and nothing opaque added.
  const fillsInside = async () => {
    await page.mouse.click(...at(210, 290));
    await page.waitForFunction(() => {
      const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
      const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
      let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
      return translucent > 5000;
    });
    // A fill is an undo step like any ink (Undo stayed disabled after one while choosing Fill reset the panel's history).
    await settles('Undo', true);
    // One Undo, one fill; and Redo brings it back.
    await choose('Undo');
    await page.waitForFunction(() => {
      const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
      const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
      let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
      return translucent < 5000;
    });
    await settles('Redo', true);
    await choose('Redo');
    await page.waitForFunction(() => {
      const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
      const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
      let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
      return translucent > 5000;
    });
    await settles('Redo', false);
  };
  await choose('Fill area');
  await fillsInside();
  assert.equal(await draw.locator('[data-drawing-tool]').getAttribute('data-drawing-tool'), 'fill');

  assert.equal(await quickEdit.count(), 0, 'the sketch went on without Quick Edit coming back');

  // Quick Edit queues the note with the view and its ink for the host, as a PNG.
  await page.evaluate(() => {
    window.__drawingPrompts = [];
    const port = window.cadHarness.a.host.promptContext;
    const originalDeliver = port.deliver;
    port.deliver = async context => {
      const image = context.parts.find(part => part.kind === 'attachment');
      const blob = await image.content;
      window.__drawingPrompts.push({ size: blob.size, type: blob.type });
      return originalDeliver(context);
    };
  });
  await pane.getByRole('button', { name: 'Quick Edit', exact: true }).click();
  assert.equal(await quickEdit.getByRole('textbox').inputValue(), 'Add a boss where the ink is.');
  await quickEdit.getByRole('button', { name: 'Queue', exact: true }).click();
  await page.waitForFunction(() => window.__drawingPrompts.length === 1);
  const [added] = await page.evaluate(() => window.__drawingPrompts);
  assert.ok(added.type === 'image/png' && added.size > 100, JSON.stringify(added));
  await quickEdit.waitFor({ state: 'detached' });

  // Leaving Draw ends the session and the sketch with it; the tool and colour in hand wait for the next.
  await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button', { name: 'Select', exact: true }).click();
  await pane.locator('[data-cad-drawing-overlay]').waitFor({ state: 'detached' });
  assert.equal(await page.getByRole('group', { name: 'Drawing tools' }).count(), 0, 'its panel went with it');
  const left = await camera();
  for (const key of ['position', 'target']) left[key].forEach((value, index) => assert.ok(Math.abs(value - dragged[key][index]) < 1e-6, `the camera keeps the pose the sketch left it in: ${key}`));
  await draw.click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal((await ink()).ink, 0, 'a new session starts empty');
  await menu.waitFor();
  // Its history too: nothing to undo, redo or clear.
  for (const name of ['Undo', 'Redo', 'Clear drawing']) assert.equal(await tool(name).isDisabled(), true, `${name} starts disabled`);
  assert.equal(await tool('Fill area').getAttribute('aria-pressed'), 'true', 'with the tool it was left on');
  assert.equal(await draw.locator('[data-drawing-tool]').getAttribute('data-drawing-tool'), 'fill');
  await choose('Color');
  assert.equal(await menu.getByRole('radio', { name: 'Neon green', exact: true }).getAttribute('aria-checked'), 'true', 'and its colour');
  await choose('Color');
  await choose('Stroke width');
  assert.equal(await menu.getByRole('radio', { name: 'Bold', exact: true }).getAttribute('aria-checked'), 'true', 'and its stroke width');
  await choose('Stroke width');
  // The tool it reopened on works, and the new sketch keeps a history of its own.
  await page.mouse.click(...at(210, 290));
  assert.equal((await ink()).ink, 0, 'a fill with no ink around it adds nothing');
  await choose('Rectangle');
  await drag(at(120, 220), at(300, 360));
  const reopened = await ink();
  assert.ok(reopened.green > 50 && reopened.red === 0, `drawn in the colour kept: ${JSON.stringify(reopened)}`);
  await settles('Undo', true);
  await choose('Fill area');
  await fillsInside();
  assert.ok(await translucentInk() > 5000);
  assert.deepEqual(errors, []);
}
