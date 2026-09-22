import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { PNG } from 'pngjs';
import { serveStepHarness } from '../harness/stepScenario.mjs';

// The STEP renderer end to end in a real browser, over the committed two-part
// fixture (`__fixtures__/step`): a coloured base with a bore, a coloured arm, one
// revolute mate, one named pose and one routine. Everything under `renderers/step`
// serves STEP alone, and none of it had a browser test until this one — written
// against the renderer as it is, so the move onto the shared shell has a net.
//
// The rule these assertions are built on: a claim that something REACHED THE
// SCREEN reads the drawn frame — a screenshot of the live canvas — never
// `controller.capture()`, which renders a fresh frame before reading and so
// cannot see a missing repaint.

let harness;
const cleanups = [];
before(async () => { harness = await serveStepHarness({ after: cleanup => cleanups.push(cleanup) }); });
after(async () => { for (const cleanup of cleanups.reverse()) await cleanup(); });

const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
/** The last thing the viewport actually DREW. */
const frame = async (pane) => { await settle(pane.page()); return PNG.sync.read(await pane.locator('[aria-busy] > div > canvas').first().screenshot()); };
// A canvas screenshot also catches what is drawn OVER the canvas: the tool strip
// along the top and the view cube in the bottom-right corner. Neither is the
// model, and the strip changes whenever a tool does, so every measurement of the
// picture is taken in the band between them.
const MODEL = { y0: 55, y1: 570 };
function differing(left, right, { x0 = 0, y0 = 0, x1 = left.width, y1 = left.height } = MODEL) {
  let count = 0;
  for (let y = y0; y < y1; y += 1) for (let x = x0; x < x1; x += 1) {
    const offset = (y * left.width + x) * 4;
    if ([0, 1, 2].some(channel => Math.abs(left.data[offset + channel] - right.data[offset + channel]) > 2)) count += 1;
  }
  return count;
}
/** How many pixels of a region are not the backdrop: what is drawn there. */
function painted(image, { x0 = 0, y0 = 0, x1 = image.width, y1 = image.height } = MODEL) {
  const backdrop = [image.data[0], image.data[1], image.data[2]];
  let count = 0;
  for (let y = y0; y < y1; y += 1) for (let x = x0; x < x1; x += 1) {
    const offset = (y * image.width + x) * 4;
    if ([0, 1, 2].reduce((sum, channel) => sum + Math.abs(image.data[offset + channel] - backdrop[channel]), 0) > 12) count += 1;
  }
  return count;
}
const coverage = image => painted(image) / (image.width * (MODEL.y1 - MODEL.y0));
/**
 * Where each part is ON SCREEN, by its own colour: the base is authored blue
 * (#3A6EA5) and the arm orange (#D9772B), so a shaded pixel still belongs to
 * exactly one of them. This is what makes "the parts moved apart" a measurement
 * rather than a guess about total ink.
 */
function partBoxes(image) {
  const boxes = { base: null, arm: null };
  for (let y = MODEL.y0; y < MODEL.y1; y += 1) for (let x = 0; x < image.width; x += 1) {
    const offset = (y * image.width + x) * 4;
    const [red, green, blue] = [image.data[offset], image.data[offset + 1], image.data[offset + 2]];
    if (red + green + blue < 40) continue;
    const part = blue > red + 25 && blue > green + 10 ? 'base' : red > blue + 25 && red > green + 10 ? 'arm' : '';
    if (!part) continue;
    const box = boxes[part] || (boxes[part] = { x0: x, x1: x, y0: y, y1: y, count: 0 });
    box.x0 = Math.min(box.x0, x); box.x1 = Math.max(box.x1, x);
    box.y0 = Math.min(box.y0, y); box.y1 = Math.max(box.y1, y);
    box.count += 1;
  }
  return boxes;
}
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
const translations = page => page.evaluate(() => Object.fromEntries(window.__cadDisplayRecords().map(record => [record.partId, record.matrix.slice(12, 15)])));
/**
 * A labelled row, measured where it is drawn: the label on the left and the control on the
 * same line beside it, pushed to the section's right edge — not a label stacked over a
 * full-width control, and not a control whose label is only a tooltip.
 */
async function assertLabelledRow(section, label, control) {
  const [sectionBox, labelBox, controlBox] = await Promise.all([
    section.boundingBox(), section.getByText(label, { exact: true }).boundingBox(), control.boundingBox()]);
  const middle = box => box.y + box.height / 2;
  assert.ok(Math.abs(middle(labelBox) - middle(controlBox)) < 3,
    `the ${label} label and its control share a line: ${JSON.stringify({ labelBox, controlBox })}`);
  assert.ok(labelBox.x + labelBox.width <= controlBox.x, `the ${label} label leads its control`);
  assert.ok(sectionBox.x + sectionBox.width - (controlBox.x + controlBox.width) <= 12,
    `and the control is right-aligned: ${JSON.stringify({ sectionBox, controlBox })}`);
}
/**
 * The drawn frame once it satisfies `reached`, or a failure naming what it never
 * did. A repaint can land a frame or two after the state that asked for it, so a
 * single shot is a race; a poll that runs out is still the missing-repaint bug.
 */
async function frameWhen(view, reached, what) {
  let last;
  for (let attempt = 0; attempt < 16; attempt += 1) {
    last = await view.frame();
    if (reached(last)) return last;
    await view.page.waitForTimeout(200);
  }
  throw new assert.AssertionError({ message: `the drawn frame never ${what}`, actual: false, expected: true, operator: '==' });
}

async function open() {
  const view = await harness.open();
  const { page, pane } = view;
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  // The file's own panel narrows the viewport, so it is open before anything is located on
  // screen or any frame is compared. Nobody opens it: a STEP opened directly opens with it
  // (the harness starts at `panel: null`), and the fixture is an assembly, so it is named so.
  await pane.locator('[data-file-sheet="Assembly"]').waitFor();
  // The world axes are drawn into the same canvas and the X one is the red the
  // arm is authored in, so they would answer to a question about the arm's pixels.
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ axes: { enabled: false } }));
  await page.waitForTimeout(400);
  await settle(page);
  const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  return {
    ...view, box,
    at: projector(await page.evaluate(() => window.__cadCamera()), box),
    state: () => page.evaluate(() => window.cadHarness.a.controller.readState()),
    display: patch => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch),
    tool: name => pane.getByRole('button', { name, exact: true }),
    tools: () => pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    // The nav row's panel toggles, in order, each with whether its panel is the open one:
    // the row IS the tab strip, so this is what the old tab list was.
    panels: () => pane.locator('[data-file-panel]')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    toggle: id => pane.locator(`[data-file-panel="${id}"]`),
    // The file panel's sections, top to bottom, by their headings.
    sections: () => pane.locator('[data-file-sheet="Assembly"] [data-file-panel-section] h2').allInnerTexts(),
    section: name => pane.getByRole('region', { name, exact: true }),
    displayPanel: () => pane.locator('[data-file-sheet="Display"]'),
    rows: () => pane.locator('[aria-label="Modeling tree"]').getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))
      .filter(label => label?.startsWith('Select ') || label?.startsWith('Expand ') || label?.startsWith('Collapse '))),
    frame: () => frame(pane),
    // What the pointer looks like over the model. Read from the INTERACTIVE
    // canvas: a tool sets the cursor on the viewport host and the canvas
    // inherits it, which three's OrbitControls used to break by pinning
    // `cursor: auto` on the canvas inline (`kit/viewport/useViewerRuntime.js`).
    cursor: () => page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')).cursor),
    waitCursor: value => page.waitForFunction(wanted => getComputedStyle(
      document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')).cursor === wanted, value),
  };
}

// Anything inside a file panel's sections that scrolls on its own: the column is the panel's
// one scroller, and the pinned Reference the only other.
const scrollingInside = (pane, sheet) => pane.locator(`[data-file-sheet="${sheet}"] [data-file-panel-section]`).evaluateAll(sections =>
  sections.flatMap(section => [section, ...section.querySelectorAll('*')])
    .filter(element => /(auto|scroll)/.test(getComputedStyle(element).overflowY) && element.scrollHeight > element.clientHeight + 1)
    .map(element => element.getAttribute('aria-label') || element.getAttribute('data-file-panel-section') || element.tagName));

test('a STEP opens in Select with the tools its sidecar earns and Fullscreen last, on its own panel with the sections the sidecar earns, and paints both authored colours', async () => {
  const view = await open();
  const { pane, errors } = view;
  assert.deepEqual(await view.tools(), ['Select:true', 'Measure:false', 'Draw:false', 'Position:false', 'Animate:false', 'Fullscreen:false'],
    'Position and Animate because the sidecar bound; Fullscreen, an act rather than a mode, is the last button');
  // The nav row is the tab strip: the file's own panel (named for what it is, the icon its
  // tree draws for it), then Display, then the tree. The file opened directly, so it opened
  // on its own panel: never on Display, and not on the tree.
  assert.deepEqual(await view.panels(), ['Display:false', 'Assembly:true', 'Show files:false']);
  assert.equal(await pane.locator('[data-file-sheet="Assembly"]').count(), 1, 'the file panel opens by default, named for the file');
  assert.equal(await view.displayPanel().count(), 0, 'Display is never where a file opens');
  // No tabs anywhere inside it: one column of sections, each under its heading.
  assert.equal(await pane.getByRole('tab').count(), 0);
  assert.deepEqual(await view.sections(), ['Features', 'Position'],
    'Position is here because the sidecar bound: schema 9, and a documentHash matching the STEP');
  // Stacked tight: Position starts where Features ends, and what the panel has left over is
  // left empty below them rather than spread between them.
  const [features, position] = await Promise.all(['features', 'position'].map(id => pane.locator(`[data-file-panel-section="${id}"]`).boundingBox()));
  const sheet = await pane.locator('[data-file-sheet="Assembly"]').boundingBox();
  assert.ok(Math.abs(position.y - (features.y + features.height)) <= 1, `Position follows Features directly: ${features.y + features.height} → ${position.y}`);
  assert.ok(position.y + position.height < sheet.y + sheet.height - 40, 'and the panel under them is empty');
  // Each heading folds its section away and back: a view of the panel and nothing more — the
  // tree stays mounted, and Position rises to meet the folded heading.
  await pane.getByRole('button', { name: 'Collapse Features', exact: true }).click();
  await pane.getByRole('button', { name: 'Select base', exact: true }).waitFor({ state: 'hidden' });
  assert.equal(await pane.getByRole('button', { name: 'Select base', exact: true, includeHidden: true }).count(), 1, 'folded, not unmounted');
  const risen = await pane.locator('[data-file-panel-section="position"]').boundingBox();
  assert.ok(risen.y < position.y - 40, `Position rises under the folded Features: ${position.y} → ${risen.y}`);
  await pane.getByRole('button', { name: 'Expand Features', exact: true }).click();
  await pane.getByRole('button', { name: 'Select base', exact: true }).waitFor();
  const opened = await view.frame();
  assert.ok(coverage(opened) > 0.2, `the opening frame is the model: ${coverage(opened)}`);
  const boxes = partBoxes(opened);
  assert.ok(boxes.base?.count > 2000 && boxes.arm?.count > 1000, `both parts are drawn, each in its own colour: ${JSON.stringify(boxes)}`);
  assert.deepEqual(await view.rows(), ['Expand base', 'Select base', 'Expand arm', 'Select arm']);
  assert.deepEqual(errors, []);
});

test('Select picks parts and faces, a selection lives only under Select, and the Reference pane measures what is picked', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  const reference = pane.getByLabel('Reference details');

  // Hover lights the part under the pointer, and lets go when it leaves.
  const still = await view.frame();
  await page.mouse.move(...at([6, 6, 5]));
  // Over a part the pointer says it can be picked; over the backdrop it does not.
  await view.waitCursor('pointer');
  await frameWhen(view, shot => differing(still, shot) > 2000, 'lit the hovered part');
  await page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
  await view.waitCursor('auto');
  assert.equal(differing(still, await view.frame()), 0, 'and is exactly as it was once the pointer leaves');

  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  assert.deepEqual((await view.state()).selectedPartIds, ['o1.1']);
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), /Name base.*Type Component.*ID o1\.1.*Size 20 × 20 × 10 mm.*Color #3A6EA5/);
  // The Reference is pinned at the panel's foot, under every section — never between two.
  const [pinned, sheet, last] = await Promise.all([reference.boundingBox(), pane.locator('[data-file-sheet="Assembly"]').boundingBox(),
    pane.locator('[data-file-panel-section]').last().boundingBox()]);
  assert.ok(Math.abs(pinned.y + pinned.height - (sheet.y + sheet.height)) <= 1, `the Reference ends where the panel does: ${pinned.y + pinned.height} vs ${sheet.y + sheet.height}`);
  assert.ok(pinned.y >= last.y + last.height - 1, `under the last section: ${pinned.y} vs ${last.y + last.height}`);
  assert.deepEqual(await scrollingInside(pane, 'Assembly'), [], 'no section scrolls inside itself: only the column does');
  assert.equal(await pane.getByRole('button', { name: 'Select base', exact: true }).getAttribute('aria-pressed'), 'true', 'the tree row follows the viewport');
  await page.keyboard.down('Shift');
  await page.mouse.click(...at([15, 0, 4]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 2);
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), /Selection · 2 references/);
  assert.equal(await pane.getByRole('button', { name: 'Add to prompt' }).count(), 1, 'the bottom action is the Select tool’s: the prompt destination');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);

  // A selection exists only under Select. Choosing a row under another tool
  // returns to Select first, rather than selecting into a tool that cannot show it.
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  await view.tool('Measure').click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  assert.deepEqual(await view.tools(), ['Select:true', 'Measure:false', 'Draw:false', 'Position:false', 'Animate:false', 'Fullscreen:false']);
  assert.deepEqual((await view.state()).selectedPartIds, ['o1.2']);
  await page.keyboard.press('Escape');

  // What the host can drive: selectors in, selection out, and a clear.
  await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.2'] }));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  const live = await view.state();
  assert.deepEqual([live.selectedReferenceIds, live.hiddenPartIds, live.isolatedPartIds], [[], [], []]);
  // The selection in the prompt grammar the live contract reads (what `viewer-state` hands an
  // agent): a selector of the document on screen, never the renderer's own copy vocabulary.
  assert.deepEqual(live.selection, [{ resource: live.resource, target: { kind: 'cad-selector', selectors: ['o1.2'] }, label: 'arm' }]);
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  // And what it delivers: the snapshot carries the file, the references carry the selection.
  await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.1'] }));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  await pane.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.equal(captured.type, 'image/png');
  assert.ok(captured.size > 100);
  assert.deepEqual(captured.references.map(reference => reference.target),
    [{ kind: 'cad-selector', selectors: ['o1.1'] }], 'the snapshot carries the selection as its references');
  assert.deepEqual(errors, []);
});

test('expanding a part loads its topology, the second press on Select narrows the filter to faces, and the bore is measured as one', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  // Exact topology follows the tree's expansion frontier: it is loaded for the
  // part that was expanded, and only then can its faces be picked.
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  await view.tool('Select').click();
  await page.getByRole('menuitemradio', { name: /^Faces/ }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'true', 'a second press opens the filter; it does not toggle the tool off');
  assert.match(await pane.locator('[data-cad-toolbar]').innerText(), /Faces/, 'the narrowed filter is named in a pill under the strip');
  // The far wall of the bore, the fixture's one cylindrical face.
  await page.mouse.click(...at([-2.34, 1.88, 4]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 1);
  assert.match((await pane.getByLabel('Reference details').innerText()).replace(/\s+/g, ' '),
    /Type Face · Cylindrical.*Diameter Ø 6 mm.*Radius R 3 mm/, 'the pane measures the face, not the part');
  // An explicit filter never falls back: a press on the arm, whose topology was
  // never asked for, adds no reference.
  await page.mouse.click(...at([15, 0, 4]));
  await page.waitForTimeout(600);
  assert.equal((await view.state()).selectedPartIds.length, 0, 'the Faces filter does not fall back to the part');
  assert.deepEqual(errors, []);
});

test('the Features tree searches as a second view: typing ranks matches and expands nothing, and picking a hit reveals it when the search ends', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const search = pane.getByPlaceholder('Filter model…');
  await search.fill('arm');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-file-sheet="Assembly"]').innerText.includes('1 match'));
  assert.deepEqual(await view.rows(), ['Select arm'], 'a flat ranked list, with no disclosure of its own');
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  await search.fill('');
  await page.waitForFunction(() => !document.querySelector('[data-testid="one"] [data-file-sheet="Assembly"]').innerText.includes('match'));
  assert.deepEqual(await view.rows(), ['Expand base', 'Select base', 'Expand arm', 'Select arm'], 'the tree comes back as it was');
  assert.equal(await pane.getByRole('button', { name: 'Select arm', exact: true }).getAttribute('aria-pressed'), 'true', 'and the hit is revealed, selected');
  assert.deepEqual(errors, []);
});

// What the one part menu offers, in order, ending in the framing group. That group is
// the viewer's ONLY zoom control — the old Inspector's percentage readout and its menu are
// gone — so it is here, on every tree row, and on the empty-space menu below. It cannot
// contradict the tool in hand: every item returns to Select before it acts.
const ZOOM_SECTION = ['Zoom to fit', 'Zoom to selection'];
const PART_MENU = ['Add to prompt', 'Copy Reference', 'Select', 'Isolate', 'Hide others', 'Hide',
  'Expand', 'Collapse', 'Expand all', 'Collapse all', ...ZOOM_SECTION];

test('hiding a part takes it off the screen, and the viewport menus offer what they can do', async () => {
  const view = await open();
  const { page, pane, at, box, errors } = view;
  const opened = await view.frame();
  await pane.getByRole('button', { name: 'Hide arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().hiddenPartIds.join() === 'o1.2');
  const hidden = await view.frame();
  assert.equal(partBoxes(hidden).arm, null, 'a hidden part is off the screen, not merely off a list');
  assert.ok(partBoxes(hidden).base.count > partBoxes(opened).base.count * 0.9, 'and the rest of the model is still drawn');
  await pane.getByRole('button', { name: 'Reveal arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().hiddenPartIds.length === 0);
  const away = () => page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
  await away();
  await frameWhen(view, shot => differing(opened, shot) === 0, 'came back to what hiding the arm took away');
  // Hover runs the other way too: resting on a tree row lights its part.
  await pane.getByRole('button', { name: 'Select arm', exact: true }).hover();
  await frameWhen(view, shot => differing(opened, shot) > 2000, 'lit the part under the hovered row');
  await away();
  await frameWhen(view, shot => differing(opened, shot) === 0, 'and let go of it');

  await page.mouse.click(...at([6, 6, 5]), { button: 'right' });
  await page.getByRole('menu').waitFor();
  assert.deepEqual(await page.getByRole('menuitem').allTextContents(), PART_MENU,
    'the node menu: what can be done to the part under the pointer, then the tree');
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });
  // Empty space asks about the model as a whole. Nothing is hidden here, so besides
  // the framing group all it can offer is the tree.
  await page.mouse.click(box.x + 30, box.y + box.height - 30, { button: 'right' });
  await page.getByRole('menu').waitFor();
  assert.deepEqual(await page.getByRole('menuitem').allTextContents(), ['Expand all', 'Collapse all', ...ZOOM_SECTION]);
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });

  // A tree row carries that same menu, item for item, and the tree's is available
  // under any tool while the viewport's belongs to Select alone.
  await pane.getByRole('button', { name: 'Select base', exact: true }).click({ button: 'right' });
  await page.getByRole('menu').waitFor();
  assert.deepEqual(await page.getByRole('menuitem').allTextContents(), PART_MENU);
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await away();
  for (const tool of ['Measure', 'Position', 'Animate', 'Draw']) {
    await view.tool(tool).click();
    await page.mouse.click(...at([6, 6, 5]), { button: 'right' });
    await page.waitForTimeout(150);
    assert.equal(await page.getByRole('menu').count(), 0, `${tool} opens no viewport menu over a part`);
    await page.mouse.click(box.x + 30, box.y + box.height - 30, { button: 'right' });
    await page.waitForTimeout(150);
    assert.equal(await page.getByRole('menu').count(), 0, `${tool} opens no viewport menu over empty space`);
    // The browser's own menu is still kept off the canvas, and a secondary drag still pans.
    // (The viewer stops the event's propagation as it prevents it, so what it left
    // behind is read from the event itself rather than from a later listener.)
    assert.equal(await page.evaluate(() => {
      const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
      document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').dispatchEvent(event);
      return event.defaultPrevented;
    }), true, `${tool} still suppresses the native menu`);
    // And a secondary DRAG is still a pan. (Not under Draw: that tool locks the
    // view on purpose and the editor takes the drag, which its own test asserts.)
    if (tool === 'Draw') continue;
    const before = await page.evaluate(() => window.__cadCamera().target);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down({ button: 'right' });
    await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2 + 60, { steps: 8 });
    await page.mouse.up({ button: 'right' });
    await page.waitForFunction(target => window.__cadCamera().target.some((value, index) => Math.abs(value - target[index]) > 1e-3), before,
      { timeout: 5000 });
  }
  // A tree-row action chosen under another tool lands in Select first, then acts —
  // Isolate, which has no selection of its own to make and so cannot get there by itself.
  assert.deepEqual(await view.tools(), ['Select:false', 'Measure:false', 'Draw:true', 'Position:false', 'Animate:false', 'Fullscreen:false']);
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Isolate', exact: true }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.2');
  assert.deepEqual(await view.tools(), ['Select:true', 'Measure:false', 'Draw:false', 'Position:false', 'Animate:false', 'Fullscreen:false']);
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
});

test('the context menu frames the model and the selection, from the viewport and from a tree row', async () => {
  const view = await open();
  const { page, pane, at, box, errors } = view;
  const menuItem = name => page.getByRole('menuitem', { name, exact: true });
  const openMenu = async (gesture) => { await gesture(); await page.getByRole('menu').waitFor(); };
  const dismiss = async () => { await page.keyboard.press('Escape'); await page.getByRole('menu').waitFor({ state: 'detached' }); };
  const choose = async (gesture, name) => {
    await openMenu(gesture);
    await menuItem(name).click();
    await page.getByRole('menu').waitFor({ state: 'detached' });
  };
  // Every claim below is read off the DRAWN frame: how wide the arm is in the pane.
  // The camera eases, so each one waits for the picture to arrive rather than sleeping.
  const armWidth = image => { const arm = partBoxes(image).arm; return arm ? arm.x1 - arm.x0 : 0; };
  const emptySpace = () => page.mouse.click(box.x + 30, box.y + box.height - 30, { button: 'right' });
  const overPart = () => page.mouse.click(...at([6, 6, 5]), { button: 'right' });
  const treeRow = name => () => pane.getByRole('button', { name, exact: true }).click({ button: 'right' });

  // With nothing selected the item that needs a selection is off — in all three places
  // the menu is rendered, because the three are one definition.
  for (const gesture of [emptySpace, overPart, treeRow('Select base')]) {
    await openMenu(gesture);
    assert.equal(await menuItem('Zoom to fit').getAttribute('aria-disabled'), null, 'Zoom to fit always acts');
    assert.equal(await menuItem('Zoom to selection').getAttribute('aria-disabled'), 'true',
      'Zoom to selection is off with nothing selected');
    await dismiss();
  }

  // Zoom to fit, asked for over empty space, really pulls the camera back to the model.
  await page.evaluate(() => { const c = window.cadHarness.a.controller;
    return c.setCamera({ ...c.readState().camera, zoom: 2.4 }); });
  const zoomedIn = armWidth(await frameWhen(view, shot => armWidth(shot) > 0, 'drew the arm zoomed in'));
  await choose(emptySpace, 'Zoom to fit');
  const fitted = armWidth(await frameWhen(view, shot => armWidth(shot) > 0 && armWidth(shot) < zoomedIn * 0.75,
    'pulled back to the whole model'));
  assert.ok(coverage(await view.frame()) > 0.2, 'and the model is on screen, not off it');

  // With a selection, Zoom to selection frames THAT and fills the pane with it.
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  await openMenu(overPart);
  assert.equal(await menuItem('Zoom to selection').getAttribute('aria-disabled'), null, 'a selection enables it');
  await menuItem('Zoom to selection').click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await frameWhen(view, shot => coverage(shot) > 0.9, 'filled the pane with what was selected');
  // A selected part wears the selection ink, so its own colour only comes back once the
  // selection is dropped — which moves no camera. THEN the arm can be measured, and it
  // is the arm that the camera was put on.
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  const framedSelection = armWidth(await frameWhen(view, shot => armWidth(shot) > fitted * 1.3,
    `framed the selected arm rather than the model (${fitted} wide at the model fit)`));

  // And from a tree row under another tool it lands in Select first, exactly as every
  // other tree-row action does, then frames the model again.
  await view.tool('Measure').click();
  assert.deepEqual(await view.tools(), ['Select:false', 'Measure:true', 'Draw:false', 'Position:false', 'Animate:false', 'Fullscreen:false']);
  await choose(treeRow('Select base'), 'Zoom to fit');
  assert.deepEqual(await view.tools(), ['Select:true', 'Measure:false', 'Draw:false', 'Position:false', 'Animate:false', 'Fullscreen:false'],
    'a tree-row framing action comes back to Select, like the rest of that menu');
  await frameWhen(view, shot => armWidth(shot) > 0 && armWidth(shot) < framedSelection * 0.9,
    `framed the whole model again from ${framedSelection}`);
  assert.deepEqual(errors, []);
});

test('every Display control reaches the drawn frame: the five modes, edges, the clip plane and its flip, explode, and the surface styles that take the model away', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // Display is a panel of its own, not a tab of the file's: its toggle turns the one column
  // over to it. The file's panel is not torn down for it — it stays mounted, hidden, so its
  // tree keeps its place for the way back.
  await view.toggle('cad-display').click();
  const panel = view.displayPanel();
  await panel.waitFor();
  assert.deepEqual(await view.panels(), ['Display:true', 'Assembly:false', 'Show files:false']);
  assert.equal(await pane.locator('[data-file-sheet="Assembly"]').count(), 1, 'the file panel is still mounted');
  assert.equal(await pane.locator('[data-file-sheet="Assembly"]').isHidden(), true, 'and hidden while Display is up');
  const solid = await view.frame();
  await page.evaluate(() => { window.openingCanvas = document.querySelector('[data-testid="one"] [aria-busy] > div > canvas'); });

  // Each preset draws a different picture, and none of them replaces the canvas.
  const frames = { solid };
  for (const [mode, label] of [['render', 'Render'], ['xray', 'X-ray'], ['hidden-line', 'Hidden line'], ['wireframe', 'Wireframe']]) {
    await panel.getByRole('combobox', { name: 'Mode', exact: true }).click();
    await page.getByRole('option', { name: label, exact: true }).click();
    await page.waitForFunction(wanted => {
      const state = window.cadHarness.a.controller.readState();
      return state.display.mode === wanted && !state.loading;
    }, mode);
    frames[mode] = await frameWhen(view, shot => differing(solid, shot) > 60_000, `redrew the model for ${label}`);
  }
  // Each is its own picture, not merely "not Solid".
  for (const [left, right] of [['render', 'xray'], ['xray', 'hidden-line'], ['hidden-line', 'wireframe']]) {
    assert.ok(differing(frames[left], frames[right]) > 20_000, `${left} and ${right} are different pictures`);
  }
  assert.ok(coverage(frames['hidden-line']) < 0.1 && coverage(solid) > 0.3,
    `hidden line is linework over the backdrop and Solid is filled: ${coverage(frames['hidden-line'])} vs ${coverage(solid)}`);
  assert.equal(await page.evaluate(() => window.openingCanvas === document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')), true,
    'a preset edits the live canvas; it never replaces it');

  await panel.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Solid', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'solid');
  await page.waitForTimeout(500);

  // Edges off takes the linework away and leaves the surfaces.
  const withEdges = await view.frame();
  await panel.getByRole('button', { name: 'Disable Edges', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.edges?.enabled === false);
  const noEdges = await frameWhen(view, shot => differing(withEdges, shot) > 6_000, 'dropped the linework');
  assert.ok(painted(noEdges) > painted(withEdges) * 0.9, 'and the surfaces stayed');
  await panel.getByRole('button', { name: 'Enable Edges', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.edges?.enabled !== false);
  await page.waitForTimeout(400);

  // Clip: the half of the model past the plane stops being drawn, and Flip
  // swaps which half that is.
  const whole = partBoxes(await view.frame());
  await panel.getByRole('button', { name: 'Enable Clip', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.clip?.enabled === true);
  const cut = await frameWhen(view, shot => partBoxes(shot).base.count < whole.base.count * 0.75, 'cut the model down');
  await panel.getByLabel('Flip', { exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.clip?.invert === true);
  const flipped = await frameWhen(view, shot => differing(cut, shot) > 30_000, 'drew the other half after Flip');
  assert.ok(partBoxes(flipped).base.count < whole.base.count * 0.95, 'and it is still a cut');
  await view.display({ clip: { enabled: false } });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.clip?.enabled === false);
  await page.waitForTimeout(500);

  // Explode moves the two parts apart ON SCREEN, and does not re-frame the camera.
  const framed = await page.evaluate(() => window.__cadCamera().zoomPercent);
  const together = partBoxes(await view.frame());
  const gap = boxes => boxes.arm.x0 - boxes.base.x1;
  await panel.getByRole('button', { name: 'Enable Explode', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.exploded?.enabled === true);
  assert.equal(await pane.getByLabel('Explode value', { exact: true }).inputValue(), '50%', 'enabling Explode lands on half');
  // The separation eases over a second (EXPLODED_VIEW_ANIMATION_DURATION_MS).
  await frameWhen(view, shot => gap(partBoxes(shot)) - gap(together) > 80, 'separated the parts on screen');
  assert.equal(await page.evaluate(() => window.__cadCamera().zoomPercent), framed, 'explode never re-frames');
  await view.display({ exploded: { enabled: false } });
  await page.waitForFunction(() => window.__cadDisplayRecords().every(record => Math.abs(record.matrix[12] - (record.partId === 'o1.2' ? 15 : 0)) < 0.01));
  await page.waitForTimeout(400);

  // Surface style: STEP's two extra styles both take the shaded surfaces away.
  // Hidden keeps them as occluders — the grid behind the model stops showing
  // through — where Off removes them from the scene and lets it through.
  const shaded = partBoxes(await view.frame());
  const styled = {};
  for (const [style, label] of [['hidden', 'Hidden'], ['off', 'Off']]) {
    await panel.getByRole('combobox', { name: 'Surface style', exact: true }).click();
    await page.getByRole('option', { name: label, exact: true }).click();
    await page.waitForFunction(wanted => window.cadHarness.a.controller.readState().display.surfaces?.style === wanted, style);
    const shot = await frameWhen(view, frame => partBoxes(frame).arm === null, `took the shaded surfaces away for ${label}`);
    styled[style] = { boxes: partBoxes(shot), painted: painted(shot) };
    assert.ok(styled[style].boxes.base === null || styled[style].boxes.base.count < shaded.base.count * 0.15,
      `${label} draws no shaded surface: ${JSON.stringify(styled[style].boxes.base)}`);
  }
  assert.ok(styled.hidden.painted < styled.off.painted * 0.5,
    `Hidden still occludes what is behind it: ${styled.hidden.painted} vs ${styled.off.painted}`);
  assert.deepEqual(errors, []);
});

test('Position drives the mate and repaints, a named pose jumps, the Position knob is never the camera, and the grid keeps the size the rest pose gave it', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // Position is a section of the file's own panel, on screen as the file opens: no tab to turn to.
  const panel = view.section('Position');
  const slider = pane.getByLabel('hinge slider value', { exact: true });
  const preset = panel.getByRole('combobox', { name: 'Pose', exact: true });
  // ONE section, whose first row is the named pose — labelled, with its dropdown beside the
  // label — then the joint, then Reset. The pose and the joints are no sections of their own.
  await assertLabelledRow(panel, 'Pose', preset);
  for (const heading of ['Pose', 'Joints', 'Kinematics']) {
    assert.equal(await panel.getByRole('heading', { name: heading, exact: true }).count(), 0, `no ${heading} heading inside Position`);
  }
  assert.equal((await preset.innerText()).trim(), 'None');
  assert.equal(await slider.inputValue(), '0.00 deg');

  const rest = await view.frame();
  const restArm = (await translations(page))['o1.2'];
  await slider.fill('60');
  await slider.press('Enter');
  await page.waitForFunction(() => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13]) > 1);
  // The DRAWN frame moved, not just the matrix: a pose that never asks for a
  // repaint leaves the viewport sitting on the picture before it.
  const posed = await frameWhen(view, shot => differing(rest, shot) > 20_000, 'repainted for the mate the slider drove');

  // The grid runs out past the model and is sized from the REST pose, so
  // swinging the arm cannot rescale it. (The Render studio's floor is held to
  // the same rule at the end of this test, where a mode change cannot disturb
  // the frames compared here.)
  const guides = { x0: 0, x1: Math.floor(rest.width * 0.14) };
  assert.ok(painted(rest, guides) > 500, `the compared strip holds grid lines: ${painted(rest, guides)}`);
  assert.equal(differing(rest, posed, guides), 0, 'the guides beside the model are untouched by a pose');

  // A named pose is a full configuration, applied as a jump.
  await preset.click();
  await page.getByRole('option', { name: 'open', exact: true }).click();
  await page.waitForFunction(() => /^90(\.0+)? deg$/.test(document.querySelector('[data-testid="one"] input[aria-label="hinge slider value"]').value));
  assert.equal((await preset.innerText()).trim(), 'open');
  await panel.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => /^0(\.0+)? deg$/.test(document.querySelector('[data-testid="one"] input[aria-label="hinge slider value"]').value));
  await page.waitForTimeout(400);
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'Reset puts the mate back where it started');
  await frameWhen(view, shot => differing(rest, shot) === 0, 'came back to the rest pose after Reset');

  // The Position tool: one knob, on the mate's axis, and dragging it is never the camera.
  await view.tool('Position').click();
  await page.waitForFunction(() => window.__cadJointHandles().length === 1);
  const [knob] = await page.evaluate(() => window.__cadJointHandles());
  assert.equal(knob.id, 'hinge');
  const pivot = view.at([10, 0, 0]);
  assert.ok(Math.hypot(view.box.x + knob.pivotX - pivot[0], view.box.y + knob.pivotY - pivot[1]) < 4,
    `the knob's pivot is the mate's axis on screen: ${JSON.stringify([knob.pivotX, knob.pivotY])} vs ${JSON.stringify(pivot)}`);
  const camera = await page.evaluate(() => window.__cadCamera());
  // `travel` is the arc the knob may be dragged along, from limit to limit, so
  // following it is a drag toward a value rather than a guess at which way the
  // mate's axis turns on screen.
  assert.ok(knob.travel.length > 8, 'a revolute knob carries its arc');
  await page.mouse.move(view.box.x + knob.x, view.box.y + knob.y);
  await page.mouse.down();
  for (const [x, y] of knob.travel.slice(1, 9)) {
    await page.mouse.move(view.box.x + x, view.box.y + y);
    await settle(page);
  }
  await page.waitForFunction(() => window.__cadJointHandles()[0].value > 15);
  const held = (await page.evaluate(() => window.__cadJointHandles()))[0].value;
  await page.mouse.up();
  await page.waitForTimeout(300);
  assert.equal((await page.evaluate(() => window.__cadJointHandles()))[0].value, held, 'nothing eases behind the drag');
  const after = await page.evaluate(() => window.__cadCamera());
  for (const key of ['position', 'target']) {
    after[key].forEach((value, index) => assert.ok(Math.abs(value - camera[key][index]) < 1e-9, `a knob drag never moves the camera: ${key}[${index}]`));
  }
  await frameWhen(view, shot => differing(rest, shot) > 20_000, 'showed the pose the knob dragged to');
  assert.equal(Number.parseFloat(await slider.inputValue()), Math.round(held * 10) / 10, 'the Position slider follows the knob');

  // The Render studio's floor is the same ground as the grid: sized and centred
  // from the REST placement. Entering Render builds the studio against the scene
  // as it stands, so entering it POSED is the case that used to size the floor
  // from the swung arm's box. It must be the floor a model at rest gets.
  const studioFloor = async () => {
    await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true));
    await page.waitForFunction(() => window.__cadStage()?.studioGround && window.cadHarness.a.controller.readState().renderMode === 'render');
    const stage = await page.evaluate(() => window.__cadStage());
    await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(false));
    await page.waitForFunction(() => !window.__cadStage()?.studioGround);
    return stage;
  };
  await slider.fill('60');
  await slider.press('Enter');
  await page.waitForFunction(() => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13]) > 1);
  const posedStage = await studioFloor();
  await panel.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => /^0(\.0+)? deg$/.test(document.querySelector('[data-testid="one"] input[aria-label="hinge slider value"]').value));
  const restStage = await studioFloor();
  const boxShift = Math.max(...[0, 1, 2].flatMap(axis => [
    Math.abs(posedStage.bounds.min[axis] - restStage.bounds.min[axis]), Math.abs(posedStage.bounds.max[axis] - restStage.bounds.max[axis])]));
  assert.ok(boxShift > 1, `the studio was built against a posed box that differs from rest: ${JSON.stringify({ posed: posedStage.bounds, rest: restStage.bounds })}`);
  assert.deepEqual(posedStage.studioGround, restStage.studioGround, 'a pose never resizes or slides the studio floor');
  assert.deepEqual(errors, []);
});

// The test above drives the mate with NOTHING selected, and a selection is not nothing: it
// re-runs the highlight layers, the part visual state and the pick groups around the pose, and
// each of those owns frames of its own. So the pose is driven again here with a selection
// standing — once on a part that does not move, and once on the part the mate swings — and
// what is asserted is the DRAWN frame, because a repaint that never comes leaves a scene that
// is correct in every other way.
test('a pose reaches the screen while a part is selected, whether the selection moves with it or stays put', async () => {
  const view = await open();
  const { page, pane, at, box, errors } = view;
  const slider = pane.getByLabel('hinge slider value', { exact: true });
  const away = () => page.mouse.move(box.x + 20, box.y + box.height - 20);
  const armY = () => page.evaluate(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13]);
  const pose = async (value) => {
    const before = await armY();
    // The slider is in the file panel's Position section, beside the Features tree: both are
    // on screen together, so nothing is turned to between a pick and a pose.
    await slider.fill(String(value));
    await slider.press('Enter');
    await page.waitForFunction(was => Math.abs(window.__cadDisplayRecords()
      .find(record => record.partId === 'o1.2').matrix[13] - was) > 1, before);
  };

  // THE BASE SELECTED: the selection stands still and the arm swings out of it.
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  await away();
  await page.waitForTimeout(400);
  const selected = await view.frame();
  const armAt = image => { const arm = partBoxes(image).arm; return arm ? Math.round((arm.y0 + arm.y1) / 2) : null; };
  assert.ok(armAt(selected) !== null, 'the arm is drawn in its own colour beside the selected base');
  await pose(60);
  const posed = await frameWhen(view, shot => differing(selected, shot) > 20_000,
    'repainted for a mate driven while a part was selected');
  assert.ok(Math.abs(armAt(posed) - armAt(selected)) > 40,
    `and the arm is drawn somewhere else for it (${armAt(selected)} -> ${armAt(posed)})`);
  assert.deepEqual((await view.state()).selectedPartIds, ['o1.1'], 'the selection was standing the whole time');

  // THE ARM SELECTED: now the selection itself is what moves, so its ink has to move with it.
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  await away();
  await page.waitForTimeout(400);
  const armSelected = await frameWhen(view, shot => differing(posed, shot) > 5_000, 'lit the arm it was asked to select');
  await pose(0);
  await frameWhen(view, shot => differing(armSelected, shot) > 20_000, 'repainted for a mate that moved the selected part');
  // Back at rest with the arm still selected, the ink is where the arm is: the picture is the
  // one the same selection gave at rest, not the one it gave posed.
  await pane.getByRole('button', { name: 'Select base', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  await away();
  await frameWhen(view, shot => differing(selected, shot) === 0, 'came back to the rest pose under the same selection');
  assert.deepEqual(errors, []);
});

test('Animate is the last mode on the strip, its playbar plays the routine, leaving it puts the model back exactly, and the Fullscreen button after it presents the same playbar', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const rest = await view.frame();
  const restArm = (await translations(page))['o1.2'];
  await view.tool('Animate').click();
  const playbar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await playbar.waitFor();
  assert.deepEqual(await view.tools(), ['Select:false', 'Measure:false', 'Draw:false', 'Position:false', 'Animate:true', 'Fullscreen:false']);
  // One routine: no routine-list button, just transport and the settings cog.
  assert.deepEqual(await playbar.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Play animation', 'Playback settings']);

  await pane.getByRole('button', { name: 'Play animation', exact: true }).click();
  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  await frameWhen(view, shot => differing(rest, shot) > 20_000, 'showed the playing routine');
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).click();

  // Leaving Animate releases the routine: the model goes back to the pose it
  // was in, to the pixel.
  await view.tool('Select').click();
  await playbar.waitFor({ state: 'detached' });
  await page.waitForTimeout(600);
  assert.deepEqual((await translations(page))['o1.2'], restArm);
  await frameWhen(view, shot => differing(rest, shot) === 0, 'came back to the rest pose exactly');

  // Fullscreen is the strip's last button, and pressing it asks the HOST for its fullscreen
  // (the harness hands this renderer `onFullscreenChange`): the same mode and the same
  // playbar, with no strip, no nav row and no panel.
  await view.tool('Animate').click();
  await playbar.waitFor();
  await view.tool('Fullscreen').click();
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).waitFor();
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).count(), 0, 'fullscreen has no tool strip');
  assert.equal(await pane.locator('[data-file-panel]').count(), 0, 'nor the nav row and its panel toggles');
  assert.equal(await pane.locator('[data-file-sheet]').count(), 0, 'nor a panel');
  await pane.getByRole('toolbar', { name: 'Animation playback' }).waitFor();
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).click();
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  assert.deepEqual(await view.tools(), ['Select:false', 'Measure:false', 'Draw:false', 'Position:false', 'Animate:true', 'Fullscreen:false'],
    'back in the mode it left, and Fullscreen is an act, never a mode left pressed');
  assert.deepEqual(await view.panels(), ['Display:false', 'Assembly:true', 'Show files:false'], 'and the panel it had');
  assert.deepEqual(errors, []);
});

test('Measure reads a distance between two picks; Draw lays ink over a STEP; and the camera, the mode and the open panel survive a remount', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;

  // Measure snaps onto exact topology, which arrives with the tree's frontier.
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  await pane.getByRole('button', { name: 'Expand arm', exact: true }).click();
  await view.tool('Measure').click();
  await view.tool('Measure').click();
  await page.getByRole('menuitemradio', { name: /^Any geometry/ }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  assert.equal(await view.tool('Measure').getAttribute('aria-pressed'), 'true', 'a second press opens the snap filter, it does not toggle the tool off');
  // Measure says what the pointer does over the model: a crosshair, not Select's hand.
  await page.mouse.move(...at([0, 0, 5]));
  await view.waitCursor('crosshair');
  const measurements = pane.getByRole('region', { name: 'Measurements' });
  assert.equal(await measurements.count(), 0, 'no panel until something is measured');
  const measure = async (from, to) => {
    for (const point of [from, to]) {
      await page.mouse.move(...at(point));
      await page.waitForTimeout(220);
      await page.mouse.click(...at(point));
      await page.waitForTimeout(220);
    }
  };
  await measure([0, 0, 5], [15, 0, 4]);
  await measurements.waitFor();
  assert.match(await measurements.innerText(), /\d+\.\d+ mm/, 'the row reads a length');
  assert.equal(await pane.getByRole('button', { name: 'Clear all' }).count(), 0, 'Clear all arrives with the second measurement');
  await measure([0, 10, 0], [15, -4, 4]);
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Measurements"] [role="listitem"]').length === 2);
  await pane.getByRole('button', { name: 'Clear all' }).click();
  await measurements.waitFor({ state: 'detached' });

  // Draw is a kit tool, and it works over a STEP like any other frame.
  await view.tool('Draw').click();
  await pane.locator('[data-cad-drawing-overlay] canvas.excalidraw__canvas.interactive').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  await page.mouse.move(...at([-5, 0, 5]));
  await page.mouse.down();
  await page.mouse.move(...at([15, 0, 5]), { steps: 8 });
  await page.mouse.up();
  const ink = await page.evaluate(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
    let opaque = 0, red = 0;
    for (let index = 0; index < data.length; index += 4) {
      if (data[index + 3] <= 200) continue;
      opaque += 1;
      if (data[index] > 200 && data[index + 1] < 100) red += 1;
    }
    return { opaque, red };
  });
  assert.ok(ink.red > 50, `a neon stroke over a STEP: ${JSON.stringify(ink)}`);
  await view.tool('Draw').click();
  await pane.locator('[data-cad-drawing-overlay]').waitFor({ state: 'detached' });

  // What the file remembers: the camera and the display settings, in its record — and the
  // panel that was open, which is the host's to keep (its `panel`), not the renderer's.
  await view.toggle('cad-display').click();
  await view.displayPanel().waitFor();
  await view.display({ mode: 'wireframe' });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'wireframe');
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ ...window.cadHarness.a.controller.readState().camera, position: [60, -20, 25], target: [4, 1, 0], zoom: 1.3 }));
  await page.waitForTimeout(600);
  const before = await view.state();
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.locator('[data-slot="cad-file-view"]').waitFor({ state: 'detached' });
  assert.deepEqual(Object.keys(await page.evaluate(() => window.cadHarness.state.renderers)),
    [JSON.stringify(['hinge_block.step', 'step'])], 'one record per file, keyed [path, renderer id]');
  await page.evaluate(() => window.cadHarness.mounted(true));
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await page.waitForTimeout(600);
  const restored = await view.state();
  assert.equal(restored.display.mode, 'wireframe');
  for (const key of ['position', 'target']) {
    before.camera[key].forEach((value, index) => assert.ok(Math.abs(value - restored.camera[key][index]) < 1e-6, `${key}[${index}] came back`));
  }
  assert.equal(restored.camera.zoom, before.camera.zoom);
  assert.deepEqual(await view.panels(), ['Display:true', 'Assembly:false', 'Show files:false'], 'and the open panel with them');
  assert.equal(await page.evaluate(() => window.cadHarness.state.panel), 'cad-display');
  assert.deepEqual(errors, []);
});

// A STEP is published in PIECES, and each piece lands in a scene the viewport already
// holds: same object, same identity, more in it. The only thing that tells the viewport
// so is `viewport.commitScene()` from the scene sync, and everything the viewport sizes
// from the model — the ground, the depth range and the framing — is re-read THEN.
//
// The committed two-component fixture cannot show this, and neither can any package
// whose second publish is its LAST: the end of a load changes what the viewport is
// mounted with, so it re-adopts the scene for reasons of its own and a deleted commit
// costs nothing. `stageProgressiveFixture` serves the same two shapes as twenty-five
// components, held one batch at a time, so the MIDDLE publish is an in-place change
// with nothing else moving — and it is the one that brings the base.
test('a package that arrives in pieces re-sizes its ground, its depth range and its framing on a publish in the middle of the load', async (t) => {
  const staged = [];
  const staggered = await serveStepHarness({ after: cleanup => staged.push(cleanup) }, { progressive: true });
  t.after(async () => { for (const cleanup of staged.reverse()) await cleanup(); });
  const { page, errors, pane } = await staggered.open({ timeout: 60000 });
  await pane.locator('[aria-busy] > div > canvas').first().waitFor();
  const read = async () => ({ stage: await page.evaluate(() => window.__cadStage()), camera: await page.evaluate(() => window.__cadCamera()) });
  const span = bounds => [0, 1, 2].map(axis => Math.round(bounds.max[axis] - bounds.min[axis]));
  const publishes = () => page.evaluate(() => [window.__cadMeshCost.publishCount, window.__cadMeshCost.loadedComponents, window.__cadMeshCost.final]);

  // BATCH ONE: eight arms, all at the origin, so this box is one arm's whichever eight
  // of them got there first. The rest of the package is still downloading.
  await page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 8, null, { timeout: 60000 });
  await page.waitForFunction(() => window.__cadStage?.()?.bounds);
  const first = await read();
  const firstFrame = await frame(pane);
  assert.deepEqual(await publishes(), [1, 8, false], 'one publish, and the load is not over');
  assert.deepEqual(span(first.stage.bounds), [10, 8, 8], 'the arm, and nothing else');

  // BATCH TWO, in the MIDDLE of the load: sixteen more components, one of them the base.
  // Nothing else about the viewport changed — same scene, same loading state, same camera
  // request — so every one of these follows from the commit and from nothing else.
  staggered.release('a');
  await page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 24, null, { timeout: 60000 });
  await page.waitForFunction(width => Math.round(window.__cadStage().bounds.max[0] - window.__cadStage().bounds.min[0]) > width, 10);
  const middle = await read();
  const middleFrame = await frame(pane);
  assert.deepEqual(await publishes(), [2, 24, false], 'a second publish, and STILL not the end of the load');
  assert.deepEqual(span(middle.stage.bounds), [20, 20, 10], 'the base is in the box the stage is fitted to');
  assert.ok(middle.stage.gridRadius > first.stage.gridRadius * 1.3,
    `the grid grew with the model (${first.stage.gridRadius} -> ${middle.stage.gridRadius})`);
  assert.ok(middle.stage.floorZ < first.stage.floorZ,
    `and the floor dropped to the model's new underside (${first.stage.floorZ} -> ${middle.stage.floorZ})`);
  assert.ok(middle.camera.far > first.camera.far,
    `the depth range was fitted again (far ${first.camera.far} -> ${middle.camera.far})`);
  // The FRAMING does not follow it, and must not: a model that jumped in the frame every
  // time a batch landed would be unusable while a large assembly loads. It is framed on
  // what arrived first, and once more when the scene is whole.
  assert.equal(middle.camera.halfHeight, first.camera.halfHeight, 'the camera held its frame while the model grew');
  // On the DRAWN frame: the base's own authored blue fills a frame it was barely in, and
  // the arm is drawn SMALLER than it was, because the camera pulled back.
  const before = partBoxes(firstFrame), after = partBoxes(middleFrame);
  const width = box => (box ? box.x1 - box.x0 : 0);
  assert.ok(after.base.count > (before.base?.count || 0) * 5,
    `the base is drawn (${before.base?.count || 0} -> ${after.base.count} pixels of its colour)`);
  assert.ok(width(after.arm) < width(before.arm) * 0.8,
    `and the arm shrank as the camera pulled back (${width(before.arm)}px -> ${width(after.arm)}px)`);
  assert.ok(differing(firstFrame, middleFrame) > 20000, 'the picture changed');

  // THE LAST COMPONENT is one more arm on top of the others, so it places nothing new —
  // but it makes the scene WHOLE, and that is when the camera frames it again, on the box
  // the middle publish had already given the stage.
  staggered.release('b');
  await page.waitForFunction(() => window.__cadMeshCost?.final === true, null, { timeout: 60000 });
  await page.waitForFunction(height => window.__cadCamera().halfHeight > height, first.camera.halfHeight);
  const whole = await read();
  assert.deepEqual(span(whole.stage.bounds), span(middle.stage.bounds), 'the box it was already fitted to');
  assert.ok(whole.camera.halfHeight > middle.camera.halfHeight * 1.3,
    `framed once more, now on the whole model (${middle.camera.halfHeight} -> ${whole.camera.halfHeight})`);
  const framed = partBoxes(await frame(pane));
  assert.ok(framed.base && framed.base.count < after.base.count * 0.8,
    `and it is drawn smaller for it: the base ran off the frame it now sits inside (${after.base.count} -> ${framed.base.count} pixels)`);

  // AND WHOSE CAMERA IT IS. Framing on completion exists for a camera NOBODY set: the fit
  // taken against whichever handful of components arrived first. A camera this file kept from
  // the last time someone looked at it is not that, and it is restored when the model is first
  // framed — on the FIRST publish, which for a package in pieces is not the last word. The
  // completion that follows must leave it alone, or a file that publishes more than once loses
  // the camera every single time it is opened.
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({
    ...window.cadHarness.a.controller.readState().camera, position: [90, -30, 38], target: [4, 1, 0], zoom: 1.6 }));
  await page.waitForTimeout(600);
  const chosen = await page.evaluate(() => window.__cadCamera());
  const chosenFrame = await frame(pane);
  assert.ok(chosen.position.some((value, index) => Math.abs(value - whole.camera.position[index]) > 1),
    'the camera the person set is somewhere the fit never puts it');
  const stored = await page.evaluate(() => JSON.parse(JSON.stringify(window.cadHarness.state)));

  // Reopened: a fresh page over the same package, held in pieces again, carrying what the last
  // session left for this file. (A remount would not do: the client still holds every component
  // it downloaded, so the package would arrive whole in ONE publish and never reach completion
  // as a second framing at all.)
  staggered.hold('a'); staggered.hold('b');
  const reopened = await staggered.open({ timeout: 60000, state: stored });
  await reopened.pane.locator('[aria-busy] > div > canvas').first().waitFor();
  await reopened.page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 8, null, { timeout: 60000 });
  staggered.release('a');
  await reopened.page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 24, null, { timeout: 60000 });
  staggered.release('b');
  await reopened.page.waitForFunction(() => window.__cadMeshCost?.final === true, null, { timeout: 60000 });
  await reopened.page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false, null, { timeout: 60000 });
  await reopened.page.waitForTimeout(800);
  assert.deepEqual(await reopened.page.evaluate(() => [window.__cadMeshCost.publishCount, window.__cadMeshCost.final]),
    [3, true], 'it arrived in three publishes again, so completion really did reframe');
  const kept = await reopened.page.evaluate(() => window.__cadCamera());
  for (const key of ['position', 'target']) {
    chosen[key].forEach((value, index) => assert.ok(Math.abs(value - kept[key][index]) < 1e-6,
      `${key}[${index}] is the camera the file kept, not the fit completion would have taken` +
      ` (${JSON.stringify(chosen[key])} vs ${JSON.stringify(kept[key])}, fit ${JSON.stringify(whole.camera[key])})`));
  }
  // On the DRAWN frame: what the reopened file shows is the picture the person left.
  const reopenedFrame = await frame(reopened.pane);
  assert.ok(differing(chosenFrame, reopenedFrame) < 3000,
    `the reopened picture is the one the person left: ${differing(chosenFrame, reopenedFrame)} pixels differ`);
  assert.deepEqual(reopened.errors, []);
  assert.deepEqual(errors, []);
});
