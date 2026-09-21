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
  const tool = name => pane.getByRole('group', { name: 'Drawing tools' }).getByRole('button', { name, exact: true });
  const camera = () => page.evaluate(() => window.cadHarness.a.controller.readState().camera);
  // What the static ink canvas holds: pixel counts by kind, and the ink's left edge in CSS pixels.
  const ink = () => page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    if (!canvas) return null;
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    const counts = { opaque: 0, translucent: 0, green: 0, red: 0 }; let left = Infinity;
    for (let index = 0; index < data.length; index += 4) {
      const [r, g, b, a] = [data[index], data[index + 1], data[index + 2], data[index + 3]];
      if (a > 200) { counts.opaque += 1; left = Math.min(left, (index / 4) % canvas.width); if (g > 200 && r < 120) counts.green += 1; if (r > 200 && g < 100) counts.red += 1; }
      else if (a > 30) counts.translucent += 1;
    }
    return { ...counts, left: left * canvas.getBoundingClientRect().width / canvas.width };
  });
  const drag = async (from, to) => { await page.mouse.move(...from); await page.mouse.down(); await page.mouse.move(...to, { steps: 8 }); await page.mouse.up(); };

  const draw = pane.getByRole('button', { name: 'Draw', exact: true });
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);

  await draw.click();
  await pane.locator('[data-cad-drawing-overlay] canvas.excalidraw__canvas.interactive').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal(await tool('Pen').getAttribute('aria-pressed'), 'true', 'Draw opens on the pen');
  // The sub-toolbar reads left to right in the order a sketch is made: the marks,
  // the colour they are made in, the two ways of moving around what was drawn,
  // then undo/redo and Clear.
  assert.deepEqual(await pane.getByRole('group', { name: 'Drawing tools' }).getByRole('button')
    .evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
  ['Pen', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text', 'Fill area', 'Eraser',
    'Color', 'Select and move drawings', 'Pan view', 'Undo', 'Redo', 'Clear drawing']);
  assert.equal(await pane.locator('.layer-ui__wrapper').isVisible(), false, 'the SDK has no controls of its own here');
  const box = await pane.locator('[data-cad-drawing-overlay]').boundingBox();
  const at = (x, y) => [box.x + x, box.y + y];

  // Locked: a drag that would have orbited the model draws instead.
  const locked = await camera();
  await drag(at(120, 120), at(260, 150));
  // Exactly, to the last bit a frame's camera readback carries: the pose is re-derived from the controls each time.
  const afterStroke = await camera();
  for (const key of ['position', 'target', 'up']) afterStroke[key].forEach((value, index) => assert.ok(Math.abs(value - locked[key][index]) < 1e-9, `drawing never moves the camera: ${key}[${index}]`));
  assert.deepEqual([afterStroke.zoom, afterStroke.projection], [locked.zoom, locked.projection]);
  const stroke = await ink();
  assert.ok(stroke.red > 50, `neon red ink: ${JSON.stringify(stroke)}`);

  // Pan belongs to the editor; the camera follows along its own plane.
  await page.mouse.move(...at(200, 300));
  await page.mouse.wheel(-90, 0);
  await page.waitForFunction(left => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    for (let x = 0; x < canvas.width; x += 1) for (let y = 0; y < canvas.height; y += 1) if (data[(y * canvas.width + x) * 4 + 3] > 200) return x * canvas.getBoundingClientRect().width / canvas.width > left + 60;
    return false;
  }, stroke.left);
  const panned = await camera();
  const direction = state => state.position.map((value, index) => value - state.target[index]);
  assert.ok(Math.hypot(...panned.target.map((value, index) => value - locked.target[index])) > 1e-3, 'the model moved with the ink');
  direction(panned).forEach((value, index) => assert.ok(Math.abs(value - direction(locked)[index]) < 1e-6, 'the view direction did not change'));
  // The lock re-derives the camera from the editor's scroll and zoom: the zoom comes back to within rounding, as the direction does.
  assert.ok(Math.abs(panned.zoom - locked.zoom) < 1e-9, `a pan is not a zoom: ${locked.zoom} -> ${panned.zoom}`);

  // The Pan view tool drags the same picture.
  await tool('Pan view').click();
  await drag(at(300, 300), at(340, 330));
  const dragged = await camera();
  assert.ok(Math.hypot(...dragged.target.map((value, index) => value - panned.target[index])) > 1e-3);
  assert.equal((await ink()).opaque > 0, true, 'panning draws nothing');

  // Sticky tools: a rectangle is followed by a rectangle.
  await tool('Rectangle').click();
  await drag(at(120, 220), at(300, 360));
  assert.equal(await tool('Rectangle').getAttribute('aria-pressed'), 'true');
  // Color is for what comes next; the red ink stays red.
  await tool('Color').click();
  await pane.getByRole('radio', { name: 'Neon green', exact: true }).click();
  await drag(at(330, 220), at(400, 300));
  const colored = await ink();
  assert.ok(colored.green > 50 && colored.red >= stroke.red, JSON.stringify(colored));

  // Fill: a translucent area inside the first rectangle, and nothing opaque added.
  await tool('Fill area').click();
  await page.mouse.click(...at(210, 290));
  await page.waitForFunction(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
    return translucent > 5000;
  });
  assert.equal(await tool('Fill area').getAttribute('aria-pressed'), 'true');
  // One Undo, one fill.
  await tool('Undo').click();
  await page.waitForFunction(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    let translucent = 0; for (let index = 3; index < data.length; index += 4) if (data[index] > 30 && data[index] <= 200) translucent += 1;
    return translucent < 5000;
  });

  // The capture carries the ink, registered to the viewport.
  // "Copy Drawing" for a clipboard host, "Add to Prompt" where the host has a composer.
  await pane.getByRole('button', { name: /^(Copy Drawing|Add to Prompt)$/ }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length > 0);

  // Pressing Draw again ends the session and the sketch with it.
  await draw.click();
  await pane.locator('[data-cad-drawing-overlay]').waitFor({ state: 'detached' });
  assert.equal(await pane.getByRole('group', { name: 'Drawing tools' }).count(), 0);
  const left = await camera();
  for (const key of ['position', 'target']) left[key].forEach((value, index) => assert.ok(Math.abs(value - dragged[key][index]) < 1e-6, `the camera keeps the pose the sketch left it in: ${key}`));
  await draw.click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal((await ink()).opaque, 0, 'a new session starts empty');
  assert.deepEqual(errors, []);
}
