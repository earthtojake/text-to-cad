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
const frame = async (pane) => { await settle(pane.page()); return PNG.sync.read(await pane.locator('[aria-busy] > div > canvas').first().screenshot({ style: '[data-slot=popover-content], [data-slot=dropdown-menu-content], [data-slot=dropdown-menu-sub-content] { visibility: hidden !important; }' })); };
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
    section.locator('[data-file-panel-body]').boundingBox(), section.getByText(label, { exact: true }).boundingBox(), control.boundingBox()]);
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

async function open(options) {
  const view = await harness.open(options);
  const { page, pane } = view;
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  // The file's own panel narrows the viewport, so it is open before anything is located on
  // screen or any frame is compared. Nobody opens it: a STEP opened directly opens with it
  // (the harness starts at `panel: null`), and the fixture is an assembly, so it is named so.
  await pane.locator('[data-file-sheet="Settings"]').waitFor();
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
    tool: name => pane.locator(name === 'Reset' ? '[data-cad-camera-controls]' : '[data-cad-toolbar]').getByRole('button', { name, exact: true }),
    tools: () => pane.locator('[data-cad-toolbar]').getByRole('button')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    // The nav row's panel toggles, in order, each with whether its panel is the open one:
    // the row IS the tab strip, so this is what the old tab list was.
    panels: () => pane.locator('[data-file-panel]')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    toggle: id => id === 'cad-display' ? pane.locator('[data-cad-toolbar]').getByRole('button', { name: 'Display', exact: true }) : pane.locator(`[data-file-panel="${id}"]`),
    // The file panel's sections, top to bottom, by their headings.
    sections: () => pane.locator('[data-file-sheet="Settings"] [data-file-panel-section] h2').allInnerTexts(),
    section: name => pane.getByRole('region', { name, exact: true }),
    displayPanel: () => page.locator('[data-cad-display-popover]'),
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

test('a STEP opens in Select with the tools its sidecar earns and Display last, on its own panel with the sections the sidecar earns, and paints both authored colours', async () => {
  const view = await open();
  const { pane, errors } = view;
  assert.deepEqual(await view.tools(), ['Select:true', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:false'],
    'Position and Animate because the sidecar bound; Display, an independent settings popover, is the last button');
  // The nav row is the tab strip: the file's own panel (named for what it is, the icon its
  // tree draws for it), then Display, then the tree. The file opened directly, so it opened
  // on its own panel: never on Display, and not on the tree.
  assert.deepEqual(await view.panels(), ['Settings:true', 'Show files:false']);
  assert.equal(await pane.locator('[data-file-sheet="Settings"]').count(), 1, 'the file panel opens by default, named for the file');
  assert.equal(await view.displayPanel().count(), 0, 'Display is never where a file opens');
  // No tabs anywhere inside it: one column of sections, each under its heading.
  assert.equal(await pane.getByRole('tab').count(), 0);
  assert.deepEqual(await view.sections(), ['Features', 'Position'],
    'scene tools no longer occupy sidebar sections');
  // Position follows the tree in the shared scroll flow.
  const position = await pane.locator('[data-file-panel-section=position] [data-file-panel-body]').boundingBox();
  // Each heading folds its section away and back: a view of the panel and nothing more — the
  // tree stays mounted, and Position rises to meet the folded heading.
  await pane.getByRole('button', { name: 'Collapse Features', exact: true }).click();
  await pane.getByRole('button', { name: 'Select base', exact: true }).waitFor({ state: 'hidden' });
  assert.equal(await pane.getByRole('button', { name: 'Select base', exact: true, includeHidden: true }).count(), 1, 'folded, not unmounted');
  const risen = await pane.locator('[data-file-panel-section="position"] [data-file-panel-body]').boundingBox();
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
  const [pinned, sheet, last] = await Promise.all([reference.boundingBox(), pane.locator('[data-file-sheet="Settings"]').boundingBox(),
    pane.locator('[data-file-panel-heading]').last().boundingBox()]);
  assert.ok(Math.abs(pinned.y + pinned.height - (sheet.y + sheet.height)) <= 1, `the Reference ends where the panel does: ${pinned.y + pinned.height} vs ${sheet.y + sheet.height}`);
  assert.ok(pinned.y >= last.y + last.height - 1, `under the last section: ${pinned.y} vs ${last.y + last.height}`);
  assert.deepEqual(await scrollingInside(pane, 'Settings'), [], 'no section scrolls inside itself: only the column does');
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
  assert.deepEqual(await view.tools(), ['Select:true', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:false']);
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
  await page.getByRole('option', { name: /^Faces/ }).click();
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

test('viewport picks individual faces and edges while feature rows retain grouped selection', async () => {
  const view = await open();
  const {page, pane, at, errors} = view;
  // Recognition is unavailable in this harness. Supply a multi-face feature so
  // this tests the distinction between tree grouping and exact viewport hits.
  await page.evaluate(() => {
    window.Worker = class {
      constructor(url) { if (!String(url).includes('modelingTree.worker')) throw new Error('No worker'); }
      postMessage() { queueMicrotask(() => this.onmessage?.({data:{tree:[{
        id:'feature:box',kind:'extrude',label:'Grouped faces',faces:[1,2,3,4,5,6,7],edges:[1,2,3],children:[],complete:true
      }]}})); }
      terminate() {}
    };
  });
  await pane.getByRole('button', {name:'Expand base',exact:true}).click();
  const feature = pane.getByRole('button', {name:'Select Grouped faces',exact:true});
  await feature.click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length > 1);
  await page.mouse.click(...at([6,6,5]));
  await page.waitForFunction(() => {
    const ids = window.cadHarness.a.controller.readState().selectedReferenceIds;
    return ids.length === 1 && /\.f\d+$/.test(ids[0]);
  });
  const face = (await view.state()).selectedReferenceIds[0];
  await page.mouse.click(...at([10,6,5]));
  await page.waitForFunction(() => {
    const ids = window.cadHarness.a.controller.readState().selectedReferenceIds;
    return ids.length === 1 && /\.e\d+$/.test(ids[0]);
  });
  await page.keyboard.down('Shift');
  await page.mouse.click(...at([6,6,5]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 2);
  assert.ok((await view.state()).selectedReferenceIds.includes(face), 'Shift adds only the clicked face');
  await feature.click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length > 2);
  assert.deepEqual(errors, []);
});

test('collapsing selected topology and leaving isolation clear the reference action', async () => {
  const view = await open();
  const {page, pane, at, errors} = view;
  const action = pane.getByRole('button', {name:/^Copy Reference/});
  // Recognition is unavailable in this harness. Supply a multi-face feature so
  // this tests the distinction between tree grouping and exact viewport hits.
  await page.evaluate(() => {
    window.Worker = class {
      constructor(url) { if (!String(url).includes('modelingTree.worker')) throw new Error('No worker'); }
      postMessage() { queueMicrotask(() => this.onmessage?.({data:{tree:[{
        id:'feature:box',kind:'extrude',label:'Grouped faces',faces:[1,2,3,4,5,6,7],edges:[1,2,3],children:[],complete:true
      }]}})); }
      terminate() {}
    };
  });
  await pane.getByRole('button', {name:'Expand base',exact:true}).click();
  await view.tool('Select').click();
  await page.getByRole('menuitemradio', {name:/^Faces/}).click();
  await page.mouse.click(...at([6,6,5]));
  await action.waitFor();
  await pane.getByRole('button', {name:'Collapse base',exact:true}).click();
  await action.waitFor({state:'detached'});
  assert.deepEqual((await view.state()).selectedReferenceIds, [], 'collapsed topology is not a hidden selection');
  await pane.getByRole('button', {name:'Expand base',exact:true}).click();
  await page.mouse.click(...at([6,6,5]));
  await action.waitFor();
  await pane.getByRole('button', {name:'Select base',exact:true}).dblclick();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.length === 1);
  await action.waitFor({state:'detached'});
  await page.mouse.click(...at([6,6,5]));
  await action.waitFor();
  await pane.getByRole('button', {name:'Exit isolate',exact:true}).click();
  await action.waitFor({state:'detached'});
  assert.deepEqual((await view.state()).selectedReferenceIds, [], 'isolation exit clears its topology selection');
  await pane.getByRole('button', {name:'Expand base',exact:true}).click();
  await page.waitForTimeout(300);
  assert.equal(await action.count(), 0, 'reopening the part does not resurrect old selection');
  assert.deepEqual(errors, []);
});

test('the Features tree searches as a second view: typing ranks matches and expands nothing, and picking a hit reveals it when the search ends', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const search = pane.getByPlaceholder('Filter model…');
  await search.fill('arm');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-file-sheet="Settings"]').innerText.includes('1 match'));
  assert.deepEqual(await view.rows(), ['Select arm'], 'a flat ranked list, with no disclosure of its own');
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  await search.fill('');
  await page.waitForFunction(() => !document.querySelector('[data-testid="one"] [data-file-sheet="Settings"]').innerText.includes('match'));
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
  assert.deepEqual(await view.tools(), ['Select:false', 'Draw:true', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:false']);
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Isolate', exact: true }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.2');
  assert.deepEqual(await view.tools(), ['Select:true', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:false']);
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
  assert.deepEqual(await view.tools(), ['Select:false', 'Draw:false', 'Measure:true', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:false']);
  await choose(treeRow('Select base'), 'Zoom to fit');
  assert.deepEqual(await view.tools(), ['Select:true', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:false'],
    'a tree-row framing action comes back to Select, like the rest of that menu');
  await frameWhen(view, shot => armWidth(shot) > 0 && armWidth(shot) < framedSelection * 0.9,
    `framed the whole model again from ${framedSelection}`);
  assert.deepEqual(errors, []);
});

test('every Display control reaches the drawn frame: the five modes, edges, the clip plane and its flip, explode, and the surface styles that take the model away', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // Display is a transient toolbar popover. The file sidebar stays visible and mounted.
  await view.toggle('cad-display').click();
  const panel = view.displayPanel();
  await panel.waitFor();
  assert.deepEqual(await view.panels(), ['Settings:true', 'Show files:false']);
  assert.equal(await pane.locator('[data-file-sheet="Settings"]').count(), 1, 'the file panel is still mounted');
  assert.equal(await pane.locator('[data-file-sheet="Settings"]').isHidden(), false, 'Display keeps the file sidebar visible');
  const solid = await view.frame();
  await page.evaluate(() => { window.openingCanvas = document.querySelector('[data-testid="one"] [aria-busy] > div > canvas'); });

  // Each preset draws a different picture, and none of them replaces the canvas.
  const frames = { solid };
  for (const [mode, label] of [['render', 'Render'], ['xray', 'X-ray'], ['hidden-line', 'Hidden line'], ['wireframe', 'Wireframe']]) {
    if (!await panel.isVisible()) await view.tool('Display').click();
    await panel.getByRole('combobox', { name: 'Mode', exact: true }).click();
    await page.getByRole('option', { name: label, exact: true }).click();
    assert.equal(await panel.isVisible(), true);
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

  if (!await panel.isVisible()) await view.tool('Display').click();
  await panel.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Solid', exact: true }).click();
  assert.equal(await panel.isVisible(), true);
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'solid');
  await page.waitForTimeout(500);

  // Edges off takes the linework away and leaves the surfaces.
  const withEdges = await view.frame();
  if (!await panel.isVisible()) await view.tool('Display').click();
  await page.getByRole('button', { name: 'Disable Edges', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.edges?.enabled === false);
  const noEdges = await frameWhen(view, shot => differing(withEdges, shot) > 6_000, 'dropped the linework');
  assert.ok(painted(noEdges) > painted(withEdges) * 0.9, 'and the surfaces stayed');
  await page.getByRole('button', { name: 'Enable Edges', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.edges?.enabled !== false);
  await page.waitForTimeout(400);

  // Cross-section: the half of the model past the plane stops being drawn, and Flip
  // swaps which half that is.
  const whole = partBoxes(await view.frame());
  await view.toggle('cad-display').click();
  await view.tool('Clip').click();
  assert.equal((await view.state()).display.clip.enabled, false, 'opening Clip does not cut');
  await page.getByLabel('Clip amount value', { exact: true }).fill('50%');
  await page.getByLabel('Clip amount value', { exact: true }).press('Enter');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.clip?.enabled === true);
  const cut = await frameWhen(view, shot => partBoxes(shot).base.count < whole.base.count * 0.75, 'cut the model down');
  await page.getByLabel('Flip', { exact: true }).click();
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
  await view.tool('Explode').click();
  await page.getByRole('slider', { name: 'Explode amount' }).press('End');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.exploded?.enabled === true);
  // The separation eases over a second (EXPLODED_VIEW_ANIMATION_DURATION_MS).
  await frameWhen(view, shot => gap(partBoxes(shot)) - gap(together) > 80, 'separated the parts on screen');
  assert.equal(await page.evaluate(() => window.__cadCamera().zoomPercent), framed, 'explode never re-frames');
  await view.display({ exploded: { enabled: false } });
  await page.waitForFunction(() => window.__cadDisplayRecords().every(record => Math.abs(record.matrix[12] - (record.partId === 'o1.2' ? 15 : 0)) < 0.01));
  await page.waitForTimeout(400);

  await page.getByRole('button', { name: 'Close explode controls' }).click();
  await view.toggle('cad-display').click();

  // Surface style: STEP's two extra styles both take the shaded surfaces away.
  // Hidden keeps them as occluders — the grid behind the model stops showing
  // through — where Off removes them from the scene and lets it through. They are
  // also what Hidden line and Wireframe are made of; both remain directly editable.
  const shaded = partBoxes(await view.frame());
  const styled = {};
  assert.deepEqual(await (async () => {
    await panel.getByRole('combobox', { name: 'Surface style', exact: true }).click();
    await page.getByRole('listbox').waitFor();
    const names = await page.getByRole('option').allTextContents();
    await page.keyboard.press('Escape');
    return names;
  })(), ['Shaded', 'Flat', 'Hidden', 'Off'], 'the Style menu exposes the CLI surface styles');
  for (const [style, label] of [['hidden', 'Hidden'], ['off', 'Off']]) {
    await view.display({ surfaces: { enabled: true, style } });
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


test('persistent tools open neutral, stack at the right, and toggle off without resetting other tools', async () => {
  const view = await open();
  const { pane, page, errors } = view;
  const explode = view.tool('Explode'), clip = view.tool('Clip');
  const stack = pane.locator('[data-model-tool-panels]');
  const explodePanel = stack.getByRole('region', { name: 'Explode controls' });
  const clipPanel = stack.getByRole('region', { name: 'Clip controls' });
  const selected = async (...names) => assert.deepEqual(await pane.getByRole('group', { name: 'Interaction tools' })
    .locator('button[aria-pressed=true]').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))), names);
  await explode.click();
  await selected('Select', 'Explode');
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('separator').count(), 0);
  const amount = explodePanel.getByRole('slider', { name: 'Explode amount' });
  assert.equal(await amount.getAttribute('aria-valuenow'), '0');
  assert.equal((await view.state()).display.exploded.enabled, false);
  await amount.press('End');
  await clip.click();
  await selected('Select', 'Explode', 'Clip');
  assert.equal((await view.state()).display.clip.enabled, false);
  const slider = clipPanel.getByRole('slider', { name: 'Clip amount' });
  for (const axis of ['X', 'Y', 'Z']) {
    await clipPanel.getByRole('radio', { name: `Clip ${axis} axis` }).click();
    assert.equal(Number(await slider.getAttribute('aria-valuemin')), 0);
    assert.equal(Number(await slider.getAttribute('aria-valuemax')), 100);
    assert.equal(Number(await slider.getAttribute('aria-valuenow')), 0);
    assert.equal((await view.state()).display.clip.enabled, false, 'axis selection stays neutral');
  }
  await slider.press('ArrowRight');
  assert.equal((await view.state()).display.clip.enabled, true, 'moving the slider enables clipping');
  await slider.press('Home');
  assert.equal((await view.state()).display.clip.enabled, false, 'the neutral boundary removes clipping');
  await clipPanel.getByRole('radio', { name: 'Clip X axis' }).click();
  const input = clipPanel.getByLabel('Clip amount value');
  await input.fill('50%'); await input.press('Enter');
  assert.equal(Number(await slider.getAttribute('aria-valuenow')), 50);
  assert.equal((await view.state()).display.clip.enabled, true);
  await clipPanel.getByLabel('Flip', { exact: true }).click();
  assert.equal(Number(await slider.getAttribute('aria-valuenow')), 50, 'Flip keeps the plane coordinate');
  const [first, second, canvas] = await Promise.all([explodePanel.boundingBox(), clipPanel.boundingBox(),
    pane.locator('[aria-busy] > div > canvas').first().boundingBox()]);
  assert.equal(first.width, 160);
  assert.ok(Math.abs(canvas.x + canvas.width - first.x - first.width - 14) < 2 && Math.abs(first.y - (await pane.getByRole('group', { name: 'Interaction tools' }).boundingBox()).y - (await pane.getByRole('group', { name: 'Interaction tools' }).boundingBox()).height - 8) < 2);
  assert.ok(second.y >= first.y + first.height && second.x === first.x);
  assert.ok(second.height < 100, 'Clip uses a compact axis row and one slider row');
  assert.equal(await clipPanel.evaluate(element => element.scrollWidth <= element.clientWidth), true);
  await view.tool('Select').click();
  await selected('Select', 'Explode', 'Clip');
  assert.equal(await clipPanel.isVisible(), true);
  assert.equal(await amount.getAttribute('aria-valuenow'), '100');
  await clip.click();
  await clipPanel.waitFor({ state: 'detached' });
  await selected('Select', 'Explode');
  assert.equal((await view.state()).display.clip.enabled, false, 'repeat press removes applied Clip');
  assert.equal(await amount.getAttribute('aria-valuenow'), '100');
  await explodePanel.getByRole('button', { name: 'Close explode controls' }).click();
  await explodePanel.waitFor({ state: 'detached' });
  assert.equal((await view.state()).display.exploded.enabled, false);
  await clip.click(); await selected('Select', 'Clip');
  assert.equal((await view.state()).display.clip.enabled, false, 'reopening starts neutral');
  assert.equal((await view.state()).display.clip.invert, false);
  await clip.click(); await clipPanel.waitFor({ state: 'detached' });
  await selected('Select');
  await explode.click(); await explode.click();
  await explodePanel.waitFor({ state: 'detached' });
  await selected('Select');
  assert.deepEqual(errors, []);
});

test('Position drives the mate and repaints, a named pose jumps, the Position knob is never the camera, and the grid keeps the size the rest pose gave it', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // Position reveals its sidebar controls and enables the joint handles.
  await view.tool('Position').click();
  const panel = pane.locator('[data-file-panel-section=position]');
  const slider = page.getByLabel('hinge slider value', { exact: true });
  const preset = panel.getByRole('combobox', { name: 'Pose', exact: true });
  // ONE section, whose first row is the named pose — labelled, with its dropdown beside the
  // label — then the joint, then Reset. The pose and the joints are no sections of their own.
  await assertLabelledRow(panel, 'Pose', preset);
  for (const heading of ['Pose', 'Joints', 'Kinematics']) {
    assert.equal(await panel.getByRole('heading', { name: heading, exact: true }).count(), 0, `no ${heading} heading inside Position`);
  }
  assert.equal((await preset.innerText()).trim(), 'Default');
  assert.equal(await slider.inputValue(), '0.00 deg');

  await page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
  await page.waitForTimeout(300);
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
  await page.waitForFunction(() => /^90(\.0+)? deg$/.test(document.querySelector('input[aria-label="hinge slider value"]').value));
  assert.equal((await preset.innerText()).trim(), 'open');
  await panel.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => /^0(\.0+)? deg$/.test(document.querySelector('input[aria-label="hinge slider value"]').value));
  await page.waitForTimeout(400);
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'Reset puts the mate back where it started');
  await page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
  await frameWhen(view, shot => differing(rest, shot) === 0, 'came back to the rest pose after Reset');

  // The Position tool: one knob, on the mate's axis, and dragging it is never the camera.
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
  await page.waitForFunction(() => /^0(\.0+)? deg$/.test(document.querySelector('input[aria-label="hinge slider value"]').value));
  const restStage = await studioFloor();
  const boxShift = Math.max(...[0, 1, 2].flatMap(axis => [
    Math.abs(posedStage.bounds.min[axis] - restStage.bounds.min[axis]), Math.abs(posedStage.bounds.max[axis] - restStage.bounds.max[axis])]));
  assert.ok(boxShift > 1, `the studio was built against a posed box that differs from rest: ${JSON.stringify({ posed: posedStage.bounds, rest: restStage.bounds })}`);
  assert.deepEqual(posedStage.studioGround, restStage.studioGround, 'a pose never resizes or slides the studio floor');
  assert.deepEqual(errors, []);
});

test('Position persists across tools and tabs, its tool reveals controls, and Animate can take over', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const rest = await translations(page);
  const position = pane.locator('[data-file-panel-section=position]');
  const setPose = async () => {
    await view.tool('Position').click();
    const input = position.getByLabel('hinge slider value', { exact: true });
    await input.fill('60'); await input.press('Enter');
    await page.waitForFunction(y => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13] - y) > 1, rest['o1.2'][1]);
  };
  await setPose();
  const posed = await translations(page);
  await pane.getByRole('tab', { name: 'Features', exact: true }).click();
  assert.equal(await view.tool('Position').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(await translations(page), posed, 'closing controls keeps the pose');
  await view.tool('Select').click();
  await settle(page);
  assert.deepEqual(await translations(page), posed, 'switching tools preserves the pose');
  await view.tool('Measure').click();
  assert.deepEqual(await translations(page), posed, 'Measure inspects the posed model');
  await setPose();
  await pane.getByRole('tab', { name: 'Features', exact: true }).click();
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await settle(page);
  assert.deepEqual(await translations(page), posed, 'tree selection keeps the pose');
  await setPose();
  await view.tool('Animate').click();
  assert.equal(await view.tool('Animate').getAttribute('aria-pressed'), 'true');
  await page.waitForFunction(y => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13] - y) > 1, rest['o1.2'][1]);
  assert.deepEqual(errors, []);
});

test('Animate is the last mode on the strip, its playbar plays the routine, leaving it puts the model back exactly, and Display’s Preview presents the same playbar', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  await page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
  await page.waitForTimeout(300);
  const rest = await view.frame();
  const restArm = (await translations(page))['o1.2'];
  await view.tool('Animate').click();
  const playbar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await playbar.waitFor();
  assert.deepEqual(await view.tools(), ['Select:false', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:true']);
  // One routine: no routine-list button, just transport and the settings cog.
  assert.deepEqual(await playbar.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Pause animation', 'Playback settings']);

  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  await frameWhen(view, shot => differing(rest, shot) > 20_000, 'showed the playing routine');
  await view.tool('Animate').click();
  assert.equal(await playbar.getByRole('button', { name: 'Play animation', exact: true }).isVisible(), true);
  await view.tool('Animate').click();
  assert.equal(await playbar.getByRole('button', { name: 'Pause animation', exact: true }).isVisible(), true);
  await view.tool('Animate').click();

  // Leaving Animate releases the routine: the model goes back to the pose it
  // was in, to the pixel.
  await view.tool('Select').click();
  await playbar.waitFor({ state: 'detached' });
  await page.waitForTimeout(600);
  assert.deepEqual((await translations(page))['o1.2'], restArm);
  await frameWhen(view, shot => differing(rest, shot) === 0, 'came back to the rest pose exactly');

  // Preview keeps the existing animation transport and the normal layout.
  await view.tool('Animate').click();
  await playbar.waitFor();
  await view.tool('Display').click();
  await page.getByRole('button', { name: 'Enable Orbit', exact: true }).click();
  await view.tool('Display').click();
  assert.equal(await pane.locator('[data-file-panel]').count(), 2, 'Preview retains the nav row');
  assert.equal(await pane.locator('[data-file-sheet="Settings"]').isVisible(), true);
  await playbar.waitFor();
  await view.tool('Display').click();
  await page.getByRole('button', { name: 'Disable Orbit', exact: true }).click();
  await view.tool('Display').click();
  assert.deepEqual(await view.tools(), ['Select:false', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false', 'Position:false', 'Animate:true']);
  assert.deepEqual(await view.panels(), ['Settings:true', 'Show files:false']);
  assert.deepEqual(errors, []);
});

test('Measure reads a distance between two picks; Draw lays ink over a STEP; and the camera, the mode and the open panel survive a remount', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;

  // Measure snaps onto exact topology, which arrives with the tree's frontier.
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  await pane.getByRole('button', { name: 'Expand arm', exact: true }).click();
  await view.tool('Measure').click();
  assert.equal(await page.getByRole('region', { name: 'Measure controls' }).count(), 0, 'activating Measure adds no empty panel');
  assert.equal(await view.tool('Measure').getAttribute('aria-pressed'), 'true');
  await view.tool('Measure').click();
  await page.getByRole('option', { name: /^Any geometry/ }).click();
  assert.equal(await view.tool('Measure').getAttribute('aria-pressed'), 'true', 'repeated activation and options keep Measure armed');
  // Measure says what the pointer does over the model: a crosshair, not Select's hand.
  await page.mouse.move(...at([0, 0, 5]));
  await view.waitCursor('crosshair');
  const measurements = page.getByRole('region', { name: 'Measurements' });
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
  assert.equal(await page.getByRole('button', { name: 'Clear all' }).count(), 0, 'Clear all arrives with the second measurement');
  await measure([0, 10, 0], [15, -4, 4]);
  await page.waitForFunction(() => document.querySelectorAll('[aria-label="Measurements"] [role="listitem"]').length === 2);
  await page.getByRole('button', { name: 'Clear all' }).click();
  await measurements.waitFor({ state: 'detached' });
  await measure([0, 0, 5], [15, 0, 4]);
  await measurements.waitFor();
  await view.tool('Select').click();
  assert.equal(await measurements.isVisible(), true, 'completed rulers persist under another pointer tool');
  assert.equal(await view.tool('Measure').getAttribute('aria-pressed'), 'true');
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'true');
  await view.tool('Measure').locator('[data-tool-menu-corner]').click();
  await page.getByRole('option', { name: /^Any geometry/ }).click();
  assert.equal(await measurements.getByRole('listitem').count(), 1, 'corner activation preserves measurements');
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'false');
  await measure([0, 10, 0], [15, -4, 4]);
  assert.equal(await measurements.getByRole('listitem').count(), 2);
  await view.tool('Measure').click();
  await measurements.waitFor({ state: 'detached' });
  assert.equal(await view.tool('Measure').getAttribute('aria-pressed'), 'false', 'main press clears the retained tool');
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.getByRole('menu').count(), 0, 'clearing results does not open options');
  await view.tool('Measure').locator('[data-tool-menu-corner]').click();
  await page.getByRole('option', { name: /^Any geometry/ }).click();
  await measure([0, 0, 5], [15, 0, 4]);
  await measurements.waitFor();
  await view.tool('Select').click();
  await view.tool('Measure').click();
  await measurements.waitFor({ state: 'detached' });
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'true', 'clearing retained results keeps the current pointer tool');
  await view.tool('Measure').click();
  await measure([0, 0, 5], [15, 0, 4]);
  await measurements.waitFor();
  await page.getByRole('button', { name: 'Close measure controls' }).click();
  await measurements.waitFor({ state: 'detached' });
  assert.equal(await view.tool('Measure').getAttribute('aria-pressed'), 'false');

  // Draw is a kit tool, and it works over a STEP like any other frame.
  await view.tool('Draw').click();
  await pane.locator('[data-cad-drawing-overlay] canvas.excalidraw__canvas.interactive').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  await view.tool('Draw').click();
  const drawingMenu = page.getByRole('menu', { name: 'Draw', exact: true });
  await drawingMenu.getByRole('button', { name: 'Line', exact: true }).click();
  await drawingMenu.waitFor({ state: 'hidden' });
  await page.waitForFunction(() => document.querySelector('[aria-label="Draw"] [data-drawing-tool]')?.getAttribute('data-drawing-tool') === 'line');

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
  await drawingMenu.getByRole('button', { name: 'Undo', exact: true }).click();
  await page.waitForFunction(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    return !pixels.some((value, index) => index % 4 === 3 && value > 200);
  });
  assert.equal(await drawingMenu.isVisible(), true);
  await drawingMenu.getByRole('button', { name: 'Redo', exact: true }).click();
  await page.waitForFunction(() => {
    const canvas = document.querySelector('[data-testid="one"] [data-cad-drawing-overlay] canvas.excalidraw__canvas.static');
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    return pixels.some((value, index) => index % 4 === 3 && value > 200);
  });
  assert.equal(await drawingMenu.isVisible(), true);
  await drawingMenu.getByRole('button', { name: 'Color', exact: true }).click();
  await drawingMenu.getByRole('radio', { name: 'Neon red', exact: true }).click();
  assert.equal(await drawingMenu.isVisible(), true);
  await drawingMenu.getByRole('button', { name: 'Clear drawing', exact: true }).click();
  await drawingMenu.waitFor({ state: 'hidden' });

  await view.tool('Select').click();
  await pane.locator('[data-cad-drawing-overlay]').waitFor({ state: 'detached' });
  await view.tool('Draw').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal(await pane.getByRole('button', { name: /Copy drawing|Add drawing to prompt/ }).count(), 0, 'leaving Draw clears its drawing');
  await view.tool('Select').click();

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
  assert.deepEqual(await view.panels(), ['Settings:true', 'Show files:false'], 'and the open panel with them');
  assert.equal(await view.displayPanel().count(), 0, 'Display popover is transient across remounts');
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

  // Reopening starts fresh even if the previous mounted camera was moved.
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
    whole.camera[key].forEach((value, index) => assert.ok(Math.abs(value - kept[key][index]) < 1e-6,
      `${key}[${index}] returns to the fit for the completed model`));
  }
  const reopenedFrame = await frame(reopened.pane);
  assert.ok(differing(chosenFrame, reopenedFrame) > 3000, 'reopening discards the previous camera');
  assert.deepEqual(reopened.errors, []);
  assert.deepEqual(errors, []);
});


test('sidebar headers stick in one scroller and Position reveals a folded section from another panel', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // The harness has an explicitly sized host; resize that host, not just the browser.
  await pane.evaluate(element => { element.parentElement.style.height = '260px'; });
  await settle(page);
  const scroll = pane.locator('[data-file-panel-scroll]');
  const features = pane.locator('[data-file-panel-section=features]');
  await scroll.evaluate(element => { element.scrollTop = 40; });
  const top = (await scroll.boundingBox()).y;
  assert.ok(await scroll.evaluate(element => element.scrollTop > 0), 'fixture actually scrolls');
  const header = await features.locator('[data-file-panel-heading]').boundingBox();
  assert.ok(Math.abs(header.y - top) < 1, 'Features header stays at the scroller top');
  const viewportBounds = await scroll.boundingBox();
  const headings = await pane.locator('[data-file-panel-heading]').evaluateAll(elements => elements.map(element => {
    const rect = element.getBoundingClientRect(); return { top: rect.top, bottom: rect.bottom };
  }));
  headings.forEach((rect, index) => {
    assert.ok(rect.top >= viewportBounds.y - 1 && rect.bottom <= viewportBounds.y + viewportBounds.height + 1, 'every section header remains reachable');
    if (index) assert.ok(rect.top >= headings[index - 1].bottom - 1, 'sticky headers never overlap');
  });
  assert.deepEqual(await scrollingInside(pane, 'Settings'), [], 'no nested section scrollers');
  const strip = await pane.locator('[data-cad-tool-groups]').boundingBox();
  const canvas = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  assert.ok(Math.abs(strip.x + strip.width - canvas.x - canvas.width + 14) < 2, 'tools align to the viewport right');
  const toolbar = pane.getByRole('group', { name: 'Interaction tools' });
  assert.equal(await toolbar.getByRole('button').last().getAttribute('aria-label'), 'Display');
  await pane.getByRole('button', { name: 'Collapse Position', exact: true }).click();
  await view.toggle('cad-display').click();
  await view.tool('Position').click();
  const position = pane.locator('[data-file-panel-section=position]');
  await position.getByLabel('hinge slider value').waitFor();
  assert.equal(await view.tool('Position').locator('[data-tool-menu-corner]').count(), 0);
  assert.equal(await view.toggle('cad-file').getAttribute('aria-pressed'), 'true');
  const rect = await position.locator('[data-file-panel-body]').boundingBox(), viewport = await scroll.boundingBox();
  assert.ok(rect.y >= viewport.y - 1 && rect.y < viewport.y + viewport.height, 'Position is revealed');
  await pane.getByRole('tab', { name: 'Features', exact: true }).click();
  await view.tool('Position').click();
  await position.getByLabel('hinge slider value').waitFor();
  // A tall host with short content must not acquire artificial scrolling.
  await pane.evaluate(element => { element.parentElement.style.height = '900px'; });
  await settle(page);
  // Titles reveal content without disabling the feature or requiring the tool.
  await scroll.evaluate(element => { element.scrollTop = 0; });
  await position.getByRole('button', { name: 'Position', exact: true }).click();
  const positionHeader = await position.locator('[data-file-panel-heading]').boundingBox();
  const positionBody = await position.locator('[data-file-panel-body]').boundingBox();
  assert.equal(await scroll.evaluate(element => element.scrollTop), 0, 'no scroll is invented when all content fits');
  assert.ok(positionHeader.y > (await scroll.boundingBox()).y + positionHeader.height, 'Position stays at its natural location when there is no content below to scroll');
  assert.ok(Math.abs(positionBody.y - positionHeader.y - positionHeader.height) < 1, 'title aligns content immediately below its header');
  // A long expanded tree pins later headers flush to the bottom.
  await features.locator('[data-file-panel-body]').evaluate(element => { element.style.minHeight = '1400px'; });
  await scroll.evaluate(element => { element.scrollTop = 0; });
  const longViewport = await scroll.boundingBox();
  const lastHeader = await position.locator('[data-file-panel-heading]').boundingBox();
  assert.ok(Math.abs(lastHeader.y + lastHeader.height - longViewport.y - longViewport.height) < 1,
    'last sticky header meets the viewport bottom after reveal and tree expansion');
  const borders = await pane.locator('[data-file-panel-heading]').evaluateAll(elements => elements.map(element => getComputedStyle(element).borderTopWidth));
  assert.deepEqual(borders, ['0px', '1px'], 'only the first section omits its separator');
  assert.equal(await features.locator('[data-file-panel-body]').evaluate(element => getComputedStyle(element).paddingBottom), '4px');
  assert.equal(await features.getByLabel('Model tree area').evaluate(element => getComputedStyle(element).paddingTop), '4px', 'the first and last tree rows have matching gutters');
  // An already-expanded Position below a long tree is revealed only up to the
  // natural maximum: no blank space is added to force a short section to the top.
  const naturalHeight = await scroll.evaluate(element => element.scrollHeight);
  await position.getByRole('button', { name: 'Position', exact: true }).click();
  assert.equal(await scroll.evaluate(element => element.scrollHeight), naturalHeight);
  assert.ok(await scroll.evaluate(element => Math.abs(element.scrollTop - (element.scrollHeight - element.clientHeight)) < 1));
  const revealedBody = await position.locator('[data-file-panel-body]').boundingBox();
  assert.ok(revealedBody.y > longViewport.y + 56 && revealedBody.y + revealedBody.height <= longViewport.y + longViewport.height + 1,
    'Position controls are fully visible without being forced to the top');
  // With enough natural content, preceding headers stick at the TOP in order,
  // just as upcoming headers stick at the bottom.
  await position.locator('[data-file-panel-body]').evaluate(element => { element.style.minHeight = '1400px'; });
  await scroll.evaluate(element => { element.scrollTop = 1550; });
  const pinned = await pane.locator('[data-file-panel-heading]').evaluateAll(elements => elements.slice(0, 2).map(element => element.getBoundingClientRect().top));
  const currentTop = (await scroll.boundingBox()).y;
  assert.deepEqual(pinned, [currentTop, currentTop + 28]);
  await position.locator('[data-file-panel-body]').evaluate(element => { element.style.minHeight = ''; });
  // Display shares section primitives but owns one separate scroll container.
  await view.toggle('cad-display').click();
  const display = view.displayPanel();
  assert.equal(await display.locator('[data-file-panel-scroll]').count(), 1);
  await display.getByRole('button', { name: 'Disable Grid', exact: true }).click();
  await display.getByRole('button', { name: 'Enable Grid', exact: true }).click();
  assert.equal(await display.getByRole('button', { name: 'Disable Grid' }).getAttribute('aria-expanded'), 'true');
  assert.deepEqual(errors, []);
});

test('Display sections edit the live viewer and Preview orbits inline with idle chrome and no cube', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const menu = pane.locator('[data-cad-display-popover]');
  const openMenu = async () => { if (!await menu.isVisible()) await view.tool('Display').click(); };
  assert.equal(await pane.getByRole('button', { name: 'Reset to default isometric view' }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: /^Projection:/ }).count(), 0);
  await openMenu();
  await menu.getByRole('combobox', { name: 'Projection', exact: true }).click();
  await page.getByRole('option', { name: 'Perspective', exact: true }).click();
  assert.equal(await menu.isVisible(), true);
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().camera.projection === 'perspective');
  await openMenu();
  await page.getByRole('button', { name: 'Disable Grid', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.grid.enabled === false);
  await page.getByRole('button', { name: 'Enable Grid', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.grid.enabled === true);
  await page.getByLabel('Surface opacity value', { exact: true }).fill('80%');
  await page.getByLabel('Surface opacity value', { exact: true }).press('Enter');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.surfaces.opacity === 0.8);
  const before = await page.evaluate(() => window.__cadCamera().position);
  const sidebar = await pane.locator('[data-file-sheet="Settings"]').boundingBox();
  await menu.getByRole('button', { name: 'Enable Orbit', exact: true }).click();
  await view.tool('Display').click();
  await page.waitForFunction(previous => window.__cadCamera().position.some((value, index) => Math.abs(value - previous[index]) > 0.1), before);
  assert.equal(await pane.locator('[data-file-panel="cad-file"]').isVisible(), true, 'normal navigation remains');
  assert.deepEqual(await pane.locator('[data-file-sheet="Settings"]').boundingBox(), sidebar, 'Preview never changes the sidebar or viewport size');
  assert.equal(await pane.getByRole('img', { name: 'View cube' }).count(), 0);
  const canvas = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.mouse.click(canvas.x + 8, canvas.y + 80);
  const chrome = pane.locator('[data-preview-chrome]');
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-preview-chrome]')?.getAttribute('data-visible') === 'false');
  await page.mouse.move(canvas.x + 12, canvas.y + 90);
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-preview-chrome]')?.getAttribute('data-visible') === 'true');
  assert.equal(await pane.getByRole('img', { name: 'View cube' }).count(), 0, 'waking tools never reveals the cube');
  await view.tool('Draw').click();
  await page.waitForFunction(() => Boolean(document.querySelector('[data-testid="one"] [data-drawing-ready]')));
  const locked = await page.evaluate(() => window.__cadCamera().position);
  await page.waitForTimeout(180);
  const held = await page.evaluate(() => window.__cadCamera().position);
  assert.ok(held.every((value, index) => Math.abs(value - locked[index]) < 1e-8), 'drawing locks orbit');
  await view.tool('Select').click();
  await openMenu();
  await menu.getByRole('button', { name: 'Disable Orbit', exact: true }).click();
  await view.tool('Display').click();
  await pane.getByRole('img', { name: 'View cube' }).waitFor();
  assert.deepEqual(errors, []);
});


test('Display sheet keeps controls together, resets optional sections and stays within the viewer', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const sheet = view.displayPanel();
  await view.tool('Display').click();
  await sheet.waitFor();
  assert.equal(await sheet.locator('[data-file-panel-scroll]').count(), 1);
  assert.equal(await sheet.getByRole('combobox', { name: 'Mode', exact: true }).isVisible(), true);
  assert.equal(await sheet.getByRole('combobox', { name: 'Projection', exact: true }).isVisible(), true);
  for (const dismiss of ['Escape', 'trigger', 'section', 'outside']) {
    const mode = sheet.getByRole('combobox', { name: 'Mode', exact: true });
    const triggerBox = await mode.boundingBox();
    const headingBox = await sheet.getByRole('heading', { name: 'Display', exact: true }).boundingBox();
    await mode.click(); await page.getByRole('listbox').waitFor();
    if (dismiss === 'Escape') await page.keyboard.press('Escape');
    else {
      const target = dismiss === 'trigger' ? triggerBox
        : dismiss === 'section' ? headingBox
        : { x: 8, y: 80, width: 2, height: 2 };
      await page.mouse.click(target.x + target.width / 2, target.y + target.height / 2);
    }
    await page.locator('[data-slot=select-content]').waitFor({ state: 'detached' });
    assert.equal(await sheet.isVisible(), true, `dismissing a dropdown with ${dismiss} preserves its parent`);
  }
  assert.equal(await sheet.getByRole('region', { name: 'Surfaces', exact: true }).isVisible(), true);
  const headingSize = await sheet.getByRole('heading', { name: 'Display', exact: true }).locator('button').evaluate(el => getComputedStyle(el).fontSize);
  const controlSize = await sheet.getByRole('combobox', { name: 'Mode', exact: true }).evaluate(el => getComputedStyle(el).fontSize);
  assert.equal(headingSize, controlSize, 'Display headings match control text');
  assert.equal((await view.tools()).at(-1).split(':')[0], 'Animate', 'Animate is rightmost');
  const initial = await sheet.boundingBox();
  const surface = await pane.locator('[data-cad-surface]').boundingBox();
  assert.ok(initial.width <= 280 && initial.height <= 520);
  assert.ok(initial.x >= surface.x && initial.y >= surface.y);
  assert.ok(initial.x + initial.width <= surface.x + surface.width + 1);
  assert.ok(initial.y + initial.height <= surface.y + surface.height + 1);
  await sheet.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Render', exact: true }).click();
  assert.equal(await sheet.isVisible(), true, 'choosing a preset keeps the sheet open');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'render');
  await sheet.getByRole('combobox', { name: 'Mode', exact: true }).click();
  await page.getByRole('option', { name: 'Solid', exact: true }).click();
  await sheet.getByRole('button', { name: 'Enable Lighting', exact: true }).click();
  const exposure = sheet.getByLabel('Exposure value', { exact: true });
  await exposure.fill('0.8'); await exposure.press('Enter');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.lighting.exposure === 0.8);
  await sheet.getByRole('button', { name: 'Disable Lighting', exact: true }).click();
  assert.equal(await exposure.count(), 0);
  await sheet.getByRole('button', { name: 'Enable Lighting', exact: true }).click();
  assert.equal(await exposure.inputValue(), '0.0 EV', 'reopening resets to defaults');
  await sheet.getByRole('button', { name: 'Grid color', exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Color opacity' }).fill('40');
  await page.getByRole('spinbutton', { name: 'Color opacity' }).press('Tab');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.grid.opacity === 0.4);
  await page.keyboard.press('Escape');
  assert.equal(await sheet.isVisible(), true, 'Escape closes the color editor first');
  await sheet.getByRole('button', { name: 'Enable Orbit', exact: true }).click();
  assert.equal(await sheet.getByRole('slider', { name: 'Orbit speed' }).isVisible(), true);
  await page.waitForTimeout(2200);
  assert.equal(await pane.locator('[data-preview-chrome]').getAttribute('data-visible'), 'true', 'open settings hold chrome visible');
  await sheet.getByRole('button', { name: 'Disable Orbit', exact: true }).click();
  assert.equal(await sheet.getByRole('slider', { name: 'Orbit speed' }).count(), 0);
  await sheet.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.lighting?.enabled !== true);
  await page.keyboard.press('Escape'); await sheet.waitFor({ state: 'hidden' });
  await view.tool('Display').click(); await view.tool('Display').click(); await view.tool('Display').click();
  await sheet.waitFor(); await page.keyboard.press('Escape'); await sheet.waitFor({ state: 'hidden' });
  await view.tool('Display').click();
  const canvas = await pane.locator('[aria-busy] > div > canvas').first().boundingBox();
  await page.mouse.click(canvas.x + 8, canvas.y + 80);
  await sheet.waitFor({ state: 'hidden' });
  assert.deepEqual(errors, []);
});

test('neutral model tools leave with another tool; applied effects persist until cleared', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const clip = pane.getByRole('region', { name: 'Clip controls', exact: true });
  const explode = pane.getByRole('region', { name: 'Explode controls', exact: true });
  await view.tool('Clip').click(); await clip.waitFor();
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'false');
  assert.equal(await view.tool('Clip').getAttribute('aria-pressed'), 'true');
  await view.tool('Select').click(); await clip.waitFor({ state: 'hidden' });
  await view.tool('Explode').click(); await explode.waitFor();
  assert.equal(await view.tool('Select').getAttribute('aria-pressed'), 'false');
  assert.equal(await view.tool('Explode').getAttribute('aria-pressed'), 'true');
  assert.equal((await view.state()).display.exploded.amount, 0);
  await view.tool('Measure').click(); await explode.waitFor({ state: 'hidden' });
  await view.tool('Clip').click();
  await view.tool('Explode').click(); await clip.waitFor({ state: 'hidden' });
  await page.getByRole('slider', { name: 'Explode amount' }).press('End');
  await view.tool('Select').click();
  assert.equal(await explode.isVisible(), true);
  await view.tool('Clip').click();
  await page.getByLabel('Clip amount value', { exact: true }).fill('35');
  await page.getByLabel('Clip amount value', { exact: true }).press('Enter');
  await view.tool('Measure').click();
  assert.equal(await clip.isVisible(), true);
  assert.equal(await explode.isVisible(), true);
  await page.getByLabel('Clip amount value', { exact: true }).fill('0');
  await page.getByLabel('Clip amount value', { exact: true }).press('Enter');
  await page.getByRole('slider', { name: 'Explode amount' }).press('Home');
  await view.tool('Select').click();
  await clip.waitFor({ state: 'hidden' }); await explode.waitFor({ state: 'hidden' });
  await view.tool('Clip').click(); await view.tool('Clip').click(); await clip.waitFor({ state: 'hidden' });
  assert.deepEqual(errors, []);
});


test('Preview starts animation, its corner chooses routines and Orbit, and only the playbar pauses', async () => {
  const animation = harness.entry.sourceSidecar.animation;
  const original = animation.source;
  let view;
  try {
    animation.source += '\nclips.short = { ...clips.swing, label: "Short swing", duration: 2 };';
    view = await open();
  } finally { animation.source = original; }
  const { page, pane, errors } = view;
  const tool = view.tool('Preview');
  const firstCorner = await tool.locator('[data-tool-menu-corner]').boundingBox();
  await page.mouse.click(firstCorner.x + firstCorner.width - 2, firstCorner.y + firstCorner.height - 2);
  assert.equal(await page.getByRole('menu').count(), 0, 'first corner click selects without opening options');
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await bar.getByRole('button', { name: 'Pause animation' }).waitFor();
  const corner = await tool.locator('[data-tool-menu-corner]').boundingBox();
  await page.mouse.click(corner.x + corner.width - 2, corner.y + corner.height - 2);
  assert.equal(await bar.getByRole('button', {name:'Playback settings'}).count(), 0);
  await page.getByRole('menuitemcheckbox', {name:'Loop',exact:true}).click();
  assert.equal(await page.getByRole('menuitemcheckbox', {name:'Loop',exact:true}).getAttribute('aria-checked'), 'false');
  await page.getByRole('menuitem', {name:/^Speed/}).hover();
  await page.getByRole('menuitemradio', {name:'2×',exact:true}).click();
  await page.getByRole('menu', {name:'Preview',exact:true}).waitFor({state:'detached'});
  await tool.click();
  assert.equal(await page.getByRole('menuitemcheckbox', { name: 'Orbit', exact: true }).getAttribute('aria-checked'), 'false', 'animation files default to no orbit');
  await page.getByRole('menuitemcheckbox', { name: 'Orbit', exact: true }).click();
  assert.equal(await page.getByRole('slider', { name: 'Orbit speed' }).count(), 0);
  await page.getByRole('menuitem', { name: 'Routine', exact: true }).hover();
  await page.getByRole('menuitemradio', { name: 'Short swing', exact: true }).click();
  await page.getByRole('menu', {name:'Preview', exact:true}).waitFor({state:'detached'});
  assert.equal(await bar.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuemax'), '2');
  await bar.getByRole('button', { name: 'Play animation' }).click();
  await tool.click();
  await page.getByRole('menu').waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('menu', {name:'Preview', exact:true}).waitFor({state:'detached'});
  await bar.getByRole('button', { name: 'Pause animation' }).click();
  assert.equal(await tool.getAttribute('aria-pressed'), 'true');
  const canvasBox = await pane.locator('canvas').first().boundingBox();
  await page.mouse.move(canvasBox.x + 20, canvasBox.y + 100);
  await page.waitForFunction(() => document.querySelector('[data-preview-chrome]')?.dataset.visible === 'false');
  assert.equal(await pane.locator('[data-preview-cube]').getAttribute('data-visible'), 'false');
  await page.mouse.move(canvasBox.x + 30, canvasBox.y + 100);
  await page.waitForFunction(() => document.querySelector('[data-preview-chrome]')?.dataset.visible === 'true');
  assert.equal(await pane.locator('[data-preview-cube]').getAttribute('data-visible'), 'true');
  await view.tool('Select').click();
  await bar.waitFor({ state:'detached' });
  assert.deepEqual(errors, []);
});


test('Preview is available without animations and pauses Orbit from its playbar', async t => {
  const original = harness.entry.sourceSidecar.animation;
  t.after(() => { harness.entry.sourceSidecar.animation = original; });
  let view;
  try { harness.entry.sourceSidecar.animation = { language: "javascript", source: "export const clips = {};" }; view = await open(); }
  catch (error) { harness.entry.sourceSidecar.animation = original; throw error; }
  const { page, pane, errors } = view;
  await view.tool('Preview').click();
  const bar = pane.getByRole('toolbar', { name: 'Orbit playback' });
  await bar.getByRole('button', { name: 'Pause orbit' }).click();
  assert.equal(await bar.getByRole('button', { name: 'Play orbit' }).isVisible(), true);
  await view.tool('Preview').click();
  await page.getByRole('menuitemcheckbox', { name: 'Orbit' }).waitFor();
  assert.equal(await page.getByRole('menuitemcheckbox', {name:'Orbit',exact:true}).getAttribute('aria-checked'), 'true');
  assert.equal(await page.getByRole('menuitemradio').count(), 0);
  await page.keyboard.press('Escape');
  await view.tool('Select').click();
  await bar.waitFor({ state: 'detached' });
  assert.deepEqual(errors, []);
});


test('Preview suspends persistent effects without losing values and restores them on exit', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const whole = partBoxes(await view.frame());
  await view.tool('Clip').click();
  await page.getByLabel('Clip amount value', { exact: true }).fill('50%');
  await page.getByLabel('Clip amount value', { exact: true }).press('Enter');
  await frameWhen(view, shot => partBoxes(shot).base.count < whole.base.count * 0.8, 'clip removes geometry before preview');
  await view.tool('Explode').click();
  await page.getByRole('slider', { name: 'Explode amount' }).press('End');
  const saved = (await view.state()).display;
  await view.tool('Preview').click();
  await pane.getByRole('toolbar', { name: 'Animation playback' }).getByRole('button', { name: 'Pause animation' }).click();
  await frameWhen(view, shot => partBoxes(shot).base.count > whole.base.count * 0.9, 'preview restores unclipped geometry');
  assert.equal(await page.getByRole('region', {name:'Clip controls', exact:true}).count(), 0);
  assert.equal(await view.tool('Clip').getAttribute('aria-pressed'), 'false');
  assert.equal((await view.state()).display.clip.enabled, saved.clip.enabled);
  // Restoring via a previously live tool must exit Preview, not remove the effect.
  await view.tool('Clip').click();
  await page.getByLabel('Clip amount value', { exact: true }).waitFor();
  assert.equal(await view.tool('Preview').getAttribute('aria-pressed'), 'false');
  assert.deepEqual((await view.state()).display.clip, saved.clip);
  assert.deepEqual((await view.state()).display.exploded, saved.exploded);
  assert.deepEqual(errors, []);
});


test('sidebar follows explicit Position requests and picks without reopening a closed panel', async () => {
  const view = await open();
  const {page, pane, errors} = view;
  await view.tool('Position').click();
  assert.equal(await pane.getByRole('tab', {name:'Position', exact:true}).getAttribute('aria-selected'), 'true');
  await view.tool('Select').click();
  assert.equal(await pane.getByRole('tab', {name:'Position', exact:true}).getAttribute('aria-selected'), 'true');
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors:['o1.2']}));
  await page.waitForFunction(() => Array.from(document.querySelectorAll('[role=tab]')).some(tab => tab.textContent === 'Features' && tab.getAttribute('aria-selected') === 'true'));
  assert.equal(await pane.getByRole('tab', {name:'Features', exact:true}).getAttribute('aria-selected'), 'true');
  await view.toggle('cad-file').click();
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors:['o1.1']}));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.includes('o1.1'));
  assert.equal(await pane.locator('[data-file-sheet="Settings"]').count(), 0);
  await view.tool('Position').click();
  await pane.getByRole('tab', {name:'Position', exact:true}).waitFor();
  assert.equal(await pane.getByRole('tab', {name:'Position', exact:true}).getAttribute('aria-selected'), 'true');
  assert.deepEqual(errors, []);
});

test('cube and reference action share their vertical center', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors:['o1.2']}));
  const action = pane.getByRole('button', {name:/^(Copy |Add to prompt)/}).first();
  await action.waitFor();
  for (const face of [null, 'Jump to top view']) {
    if (face) await pane.getByRole('button', {name:face, exact:true}).click();
    await settle(page);
    const {center, actionCenter} = await pane.evaluate(element => {
      const boxes = [...element.querySelectorAll('polygon[data-cube-artwork]')].map(face => face.getBoundingClientRect());
      const button = [...element.querySelectorAll('button')].find(button => /^(Copy |Add to prompt)/.test(button.textContent)).getBoundingClientRect();
      return {center:(Math.max(...boxes.map(box => box.bottom)) + Math.min(...boxes.map(box => box.top))) / 2, actionCenter:button.y + button.height / 2};
    });
    assert.ok(Math.abs(center - actionCenter) < 1, `cube center ${center} matches action center ${actionCenter}`);
  }
  assert.deepEqual(errors, []);
});

test('reference CTA, double clicks and copy shortcut deliver references with useful feedback', async () => {
  const view = await open();
  const {page, pane, at, errors} = view;
  await page.evaluate(() => {
    window.__clipboardWrites = [];
    window.__imageCopies = [];
    window.cadHarness.a.host.clipboard.writeImage = async pending => { const blob = await pending; window.__imageCopies.push({size:blob.size,type:blob.type}); };
    window.cadHarness.a.host.clipboard.writeText = async text => { window.__clipboardWrites.push(text); };
  });
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors:['o1.2']}));
  const action = pane.getByRole('button', {name:/^Copy Reference\b/});
  await action.click();
  await page.waitForFunction(() => window.__clipboardWrites.length === 1);
  assert.match(await page.evaluate(() => window.__clipboardWrites[0]), /#o1\.2/);
  assert.ok((await action.boundingBox()).height >= 44);
  assert.equal(await page.getByText('Reference copied', {exact:true}).isVisible(), true);
  const toast = await page.locator('[data-slot="toast"]').boundingBox();
  const viewport = await pane.locator('[data-cad-surface]').boundingBox();
  assert.ok(toast.y >= viewport.y + 11, `toast begins below the navbar with padding: ${JSON.stringify({toast,viewport})}`);
  const fullBody = await pane.locator('[data-file-viewer-body]').boundingBox();
  assert.ok(Math.abs(toast.x + toast.width - (fullBody.x + fullBody.width - 12)) < 1, 'notification is anchored to the full viewer, including sidebar');
  assert.ok(toast.width < 250, 'short notification fits its content');
  await action.press('Control+c');
  await page.waitForFunction(() => window.__clipboardWrites.length === 2);
  await page.mouse.dblclick(...at([6,6,5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.1');
  assert.equal(await page.evaluate(() => window.__clipboardWrites.length), 2, 'component double-click isolates rather than copying');
  await pane.getByRole('button', {name:'Select base',exact:true}).dblclick();
  assert.deepEqual((await view.state()).isolatedPartIds, ['o1.1']);
  assert.equal(await page.evaluate(() => window.__clipboardWrites.length), 2, 'tree component double-click never copies');
  await view.tool('Select').click();
  await page.getByRole('menuitemradio', { name: /^Faces/ }).click();
  await page.mouse.dblclick(...at([6,6,5]));
  await page.waitForFunction(() => window.__clipboardWrites.length === 3);
  assert.match(await page.evaluate(() => window.__clipboardWrites[2]), /#o1\.1\.f\d+/);
  await page.waitForTimeout(350);
  await view.tool('Select').click();
  await page.getByRole('menuitemradio', { name: /^Edges/ }).click();
  await page.mouse.dblclick(...at([10,6,5]));
  await page.waitForFunction(() => window.__clipboardWrites.length === 4);
  assert.match(await page.evaluate(() => window.__clipboardWrites[3]), /#o1\.1\.e\d+/);
  assert.deepEqual((await view.state()).isolatedPartIds, ['o1.1'], 'topology double-click keeps isolation');
  await page.mouse.dblclick(view.box.x + 30, view.box.y + view.box.height - 30);
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.length === 0);
  assert.ok(partBoxes(await view.frame()).arm, 'double-clicking empty space restores the other component');
  assert.equal(await page.evaluate(() => window.__clipboardWrites.length), 4, 'empty-space double-click does not copy');
  await view.tool('Draw').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  await page.mouse.move(view.box.x + 150, view.box.y + 150);
  await page.mouse.down();
  await page.mouse.move(view.box.x + 250, view.box.y + 200, {steps:8});
  await page.mouse.up();
  const drawingAction = pane.getByRole('button', {name:/^Copy Drawing/});
  await drawingAction.waitFor();
  await drawingAction.press('Control+c');
  await page.waitForFunction(() => window.__imageCopies.length === 1);
  assert.equal(await page.evaluate(() => window.__imageCopies[0].type), 'image/png');
  assert.ok(await page.evaluate(() => window.__imageCopies[0].size > 100));
  await page.getByText('Drawing copied', {exact:true}).waitFor();
  assert.deepEqual(errors, []);
});


test('toolbar tooltips wait for deliberate hover and never stick after selection or menu dismissal', async () => {
  const view = await open();
  const { page } = view;
  const tips = page.getByRole('tooltip');
  const draw = view.tool('Draw'), measure = view.tool('Measure');
  await draw.hover();
  await page.waitForTimeout(150);
  assert.equal(await tips.count(), 0, 'passing over a tool does not flash a tooltip');
  await page.getByRole('tooltip', { name: 'Draw', exact: true }).waitFor();
  // Leaving toward the tip must dismiss it, rather than creating a hover bridge.
  const tipBox = await tips.boundingBox();
  await page.mouse.move(tipBox.x + tipBox.width / 2, tipBox.y + tipBox.height / 2);
  await tips.waitFor({ state: 'detached' });
  await measure.hover();
  await page.waitForTimeout(150);
  assert.equal(await tips.count(), 0, 'switching tools keeps the same hover delay');
  await page.getByRole('tooltip', { name: 'Measure', exact: true }).waitFor();
  await measure.click();
  await tips.waitFor({ state: 'detached' });
  await measure.click();
  await page.getByRole('menu').waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await page.mouse.move(view.box.x + 20, view.box.y + 150);
  await view.tool('Select').click();
  await page.mouse.move(view.box.x + 20, view.box.y + 150);
  await page.waitForTimeout(500);
  assert.equal(await tips.count(), 0, 'deselection never resurrects a previously open tooltip');
  const home = view.tool('Home');
  await home.hover();
  await page.getByRole('tooltip', { name: 'Home', exact: true }).waitFor();
  await home.click();
  await page.waitForTimeout(500);
  assert.equal(await tips.count(), 0, 'click focus does not pin a tooltip');
  await draw.click();
  const disabledHome = await home.boundingBox();
  await page.mouse.move(disabledHome.x + disabledHome.width / 2, disabledHome.y + disabledHome.height / 2);
  await page.waitForTimeout(500);
  assert.equal(await tips.count(), 0, 'disabled camera controls have no tooltip');
  await view.tool('Preview').click();
  await measure.hover();
  await page.getByRole('tooltip', { name: 'Measure', exact: true }).waitFor();
  await page.waitForFunction(() => document.querySelector('[data-preview-chrome]')?.dataset.visible === 'false');
  assert.equal(await tips.count(), 0, 'portalled tooltips disappear with preview chrome');
  assert.deepEqual(view.errors, []);
});

test('animated Render bounds follow moving geometry without moving the camera or resizing the floor', async () => {
  const animation = harness.entry.sourceSidecar.animation;
  const original = animation.source;
  let view;
  try {
    animation.source = `export const clips = { swing: { label: "Approach", duration: 4, loop: true,
      update(t, m) { m.get("arm").translate([t * 8, -t * 8, t * 4]); } } };`;
    view = await open();
  } finally { animation.source = original; }
  const { page, pane } = view;
  await page.evaluate(() => { void window.cadHarness.a.controller.setRenderMode(true); });
  await page.waitForFunction(() => window.__cadStage()?.studioGround, null, { timeout: 10000 });
  const before = await page.evaluate(() => ({ camera: window.__cadCamera(), stage: window.__cadStage() }));
  await view.tool('Preview').click();
  await page.waitForFunction(() => window.__cadStage().bounds.max[0] > 35, null, { timeout: 10000 });
  await page.mouse.move(view.box.x + 20, view.box.y + 100);
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).click();
  await settle(page);
  const after = await page.evaluate(() => ({ camera: window.__cadCamera(), stage: window.__cadStage(), records: window.__cadDisplayRecords() }));
  assert.ok(after.stage.bounds.max[0] > before.stage.bounds.max[0] + 10, 'live bounds include the translated arm');
  assert.deepEqual(after.stage.studioGround, before.stage.studioGround, 'ground footprint stays anchored at rest');
  for (const key of ['position', 'target', 'zoom']) {
    const actual = [].concat(after.camera[key]), expected = [].concat(before.camera[key]);
    assert.ok(actual.every((value, index) => Math.abs(value - expected[index]) < 1e-8), `animation preserves ${key}`);
  }
  assert.ok(after.camera.near < before.camera.near, 'near plane follows the approaching part');
  const forward = after.camera.target.map((value, axis) => value - after.camera.position[axis]);
  const length = Math.hypot(...forward);
  const depths = [0, 1, 2, 3, 4, 5, 6, 7].map(mask => [0, 1, 2].reduce((sum, axis) => {
    const value = after.stage.bounds[(mask & (1 << axis)) ? 'max' : 'min'][axis];
    return sum + (value - after.camera.position[axis]) * forward[axis] / length;
  }, 0));
  assert.ok(Math.min(...depths) > after.camera.near && Math.max(...depths) < after.camera.far,
    'all corners of the moving model remain within the depth range');
  // The actual presented frame must still contain the moving arm.
  const shot = await view.frame();
  assert.ok(partBoxes(shot).arm?.count > 100, 'moving arm remains drawn in Render');
  assert.deepEqual(view.errors, []);
});

test('Fullscreen fills the viewer below the navbar and restores the sidebar from its exit control', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const sheet = pane.locator('[data-file-sheet="Settings"]');
  const before = await sheet.boundingBox();
  await pane.getByRole('tab', { name: 'Position', exact: true }).click();
  const viewportBefore = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  const toolbar = await pane.locator('[data-cad-tool-groups]').boundingBox();
  assert.ok(Math.abs(toolbar.x - viewportBefore.x - 14) < 2, 'toolbar is inset from the viewport left');
  await pane.getByRole('button', { name: 'Fullscreen', exact: true }).click();
  await sheet.waitFor({ state: 'hidden' });
  assert.equal(await sheet.count(), 1, 'sidebar content remains mounted');
  assert.equal(await pane.locator('[data-file-panel]').evaluateAll(nodes => nodes.every(node => node.disabled)), true);
  const viewportDuring = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  assert.ok(viewportDuring.width > viewportBefore.width, 'preview reclaims the sidebar width');
  assert.equal(await pane.locator('header [data-file-navigation-status]').count(), 1);
  assert.equal(await pane.locator('header').isVisible(), true);
  assert.equal(await pane.locator('[data-cad-toolbar]').isVisible(), false);
  assert.equal(await pane.getByLabel('View cube', { exact: true }).isVisible(), false);
  await page.mouse.move(viewportDuring.x + viewportDuring.width - 20, viewportDuring.y + 20);
  await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).click();
  await sheet.waitFor({ state: 'visible' });
  assert.equal((await sheet.boundingBox()).width, before.width);
  assert.equal(await pane.getByRole('tab', { name: 'Position', exact: true }).getAttribute('aria-selected'), 'true');
  assert.equal(await pane.locator('[data-file-panel]').evaluateAll(nodes => nodes.every(node => !node.disabled)), true);
  assert.deepEqual(errors, []);
});

test('Fullscreen settings and playback share visibility while editor controls stay hidden; Escape preserves panel state', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const sheet = pane.locator('[data-file-sheet="Settings"]');
  await pane.getByRole('tab', { name: 'Position', exact: true }).click();
  assert.equal(await pane.getByRole('button', { name: 'Fullscreen', exact: true }).locator('[data-tool-menu-corner]').count(), 0, 'Preview is a direct action without a corner menu');
  await pane.getByRole('button', { name: 'Fullscreen', exact: true }).click();
  await sheet.waitFor({ state: 'hidden' });
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await bar.getByRole('button', { name: 'Play animation', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector('[data-preview-controls] [role="slider"][aria-label="Animation time"]')?.getAttribute('aria-valuenow')) > 0.1);
  await bar.hover();
  await page.waitForTimeout(1200);
  assert.equal(await pane.locator('[data-preview-controls]').getAttribute('data-visible'), 'true');
  await pane.getByRole('button', { name: 'Animation settings', exact: true }).click();
  await page.getByRole('menu').waitFor();
  await page.waitForTimeout(1200);
  assert.equal(await pane.locator('[data-preview-controls]').getAttribute('data-visible'), 'true', 'open settings stay available');
  await page.keyboard.press('Escape');
  assert.equal(await sheet.isVisible(), false, 'menu dismissal does not exit Preview');
  const canvas = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  await page.mouse.move(canvas.x + 30, canvas.y + 100);
  await page.waitForFunction(() => document.querySelector('[data-preview-controls]')?.dataset.visible === 'false');
  assert.equal(await pane.locator('[data-preview-controls]').getAttribute('inert'), '');
  assert.equal(await pane.locator('[data-cad-toolbar]').isVisible(), false);
  await page.mouse.move(canvas.x + 40, canvas.y + 100);
  assert.equal(await pane.locator('[data-preview-controls]').getAttribute('data-visible'), 'true');
  assert.equal(await pane.locator('[data-cad-toolbar]').isVisible(), false);
  await page.keyboard.press('Escape');
  await sheet.waitFor({ state: 'visible' });
  assert.equal(await pane.getByRole('tab', { name: 'Position', exact: true }).getAttribute('aria-selected'), 'true');
  await pane.getByRole('button', { name: 'Settings', exact: true }).click();
  await sheet.waitFor({ state: 'detached' });
  await pane.getByRole('button', { name: 'Fullscreen', exact: true }).click();
  await page.keyboard.press('Escape');
  assert.equal(await sheet.count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Fullscreen', exact: true }).isVisible(), true);
  assert.deepEqual(errors, []);
});

test('Position header offers Default and Reset together above the joint values', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  await view.tool('Position').click();
  const panel = pane.locator('[data-file-panel-section=position]');
  const preset = panel.getByRole('combobox', { name: 'Pose', exact: true });
  const reset = panel.getByRole('button', { name: 'Reset', exact: true });
  const value = panel.getByLabel('hinge slider value', { exact: true });
  assert.equal((await preset.innerText()).trim(), 'Default');
  const headerBox = await panel.locator('[data-position-header]').boundingBox();
  assert.ok((await reset.boundingBox()).y >= headerBox.y);
  assert.ok((await value.boundingBox()).y >= headerBox.y + headerBox.height);
  const joint = panel.locator('[data-position-control]').first();
  const labelBox = await joint.getByText('hinge', { exact: true }).boundingBox();
  const valueBox = await value.boundingBox();
  const sliderBox = await joint.getByRole('slider').boundingBox();
  assert.ok(sliderBox.x + sliderBox.width < valueBox.x, 'numeric value sits beside the label/slider pair');
  assert.ok(sliderBox.y >= labelBox.y + labelBox.height - 4, 'slider is directly beneath its label');
  assert.ok((await preset.boundingBox()).width > headerBox.width * 0.9, 'pose dropdown fills the control width');
  assert.ok((await reset.boundingBox()).y < (await preset.boundingBox()).y, 'small Reset sits beside the label above the dropdown');
  assert.equal((await reset.boundingBox()).width, 20);
  await preset.click();
  await page.getByRole('option', { name: 'open', exact: true }).click();
  assert.equal(await value.inputValue(), '90.0 deg');
  await preset.click();
  await page.getByRole('option', { name: 'Default', exact: true }).click();
  assert.equal(await value.inputValue(), '0.00 deg');
  assert.equal((await preset.innerText()).trim(), 'Default');
  await value.fill('25'); await value.press('Enter');
  assert.equal((await preset.innerText()).trim(), 'Custom');
  await reset.click();
  assert.equal(await value.inputValue(), '0.00 deg');
  assert.equal((await preset.innerText()).trim(), 'Default');
  assert.deepEqual(errors, []);
});

test('Display takes ownership from Draw and keeps selection after its sheet closes', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  await view.tool('Draw').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  const canvas = await pane.locator('canvas.excalidraw__canvas.interactive').boundingBox();
  await page.mouse.move(canvas.x + 90, canvas.y + 120);
  await page.mouse.down();
  await page.mouse.move(canvas.x + 190, canvas.y + 170, { steps: 8 });
  await page.mouse.up();
  await pane.getByRole('button', { name: /Copy Drawing/i }).waitFor();
  const display = view.tool('Display');
  assert.equal(await display.isEnabled(), true, 'Display is available while drawing');
  await display.click();
  await pane.getByRole('dialog', { name: 'Display settings' }).waitFor();
  await pane.locator('[data-cad-drawing-overlay]').waitFor({ state: 'detached' });
  assert.deepEqual(await pane.getByRole('group', { name: 'Interaction tools' }).locator('button[aria-pressed="true"]').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))), ['Display']);
  await page.keyboard.press('Escape');
  await pane.getByRole('dialog', { name: 'Display settings' }).waitFor({ state: 'hidden' });
  assert.equal(await display.getAttribute('aria-pressed'), 'true');
  await display.click();
  await pane.getByRole('dialog', { name: 'Display settings' }).waitFor();
  await view.tool('Draw').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  assert.equal(await display.getAttribute('aria-pressed'), 'false');
  await pane.getByRole('dialog', { name: 'Display settings' }).waitFor({ state: 'hidden' });
  assert.equal(await pane.getByRole('button', { name: /Copy Drawing/i }).count(), 0, 'leaving Draw cleared the drawing');
  assert.deepEqual(errors, []);
});

test('Draw history buttons track the SDK stacks, including empty canvas and discarded redo', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  await view.tool('Draw').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  await view.tool('Draw').click();
  const menu = page.getByRole('menu', { name: 'Draw', exact: true });
  const undo = menu.getByRole('button', { name: 'Undo', exact: true });
  const redo = menu.getByRole('button', { name: 'Redo', exact: true });
  assert.equal(await undo.isEnabled(), false);
  assert.equal(await redo.isEnabled(), false);
  assert.equal(await menu.getByRole('button', { name: 'Select and move drawings', exact: true }).locator('svg.lucide-square-mouse-pointer').count(), 1);
  await menu.getByRole('button', { name: 'Line', exact: true }).click();
  await menu.waitFor({ state: 'hidden' });
  const canvas = await pane.locator('canvas.excalidraw__canvas.interactive').boundingBox();
  const stroke = async offset => {
    await page.mouse.move(canvas.x + 70, canvas.y + 100 + offset);
    await page.mouse.down();
    await page.mouse.move(canvas.x + 180, canvas.y + 150 + offset, { steps: 8 });
    await page.mouse.up();
  };
  const history = async (canUndo, canRedo) => page.waitForFunction(({ canUndo, canRedo }) => {
    const menu = document.querySelector('[role="menu"]');
    return menu?.querySelector('[aria-label="Undo"]')?.disabled === !canUndo
      && menu?.querySelector('[aria-label="Redo"]')?.disabled === !canRedo;
  }, { canUndo, canRedo });
  await stroke(0);
  await view.tool('Draw').click();
  await history(true, false);
  await undo.click();
  await history(false, true);
  await redo.click();
  await history(true, false);
  await menu.getByRole('button', { name: 'Clear drawing', exact: true }).click();
  await menu.waitFor({ state: 'hidden' });
  await view.tool('Draw').click();
  await menu.waitFor();
  await history(true, false);
  await undo.click();
  await history(true, true);
  await page.keyboard.press('Escape');
  await menu.waitFor({ state: 'hidden' });
  await stroke(40);
  await view.tool('Draw').click();
  await history(true, false);
  await page.keyboard.press('Escape');
  await view.tool('Select').click();
  await view.tool('Draw').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-drawing-ready]'));
  await view.tool('Draw').click();
  await history(false, false);
  assert.deepEqual(errors, []);
});

test('mobile sheets overlay the scene and the full toolbar fits down to 320px', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const resize = async width => {
    await page.setViewportSize({ width, height: 800 });
    await pane.evaluate((element, width) => { element.parentElement.style.width = `${width}px`; }, width);
    await page.waitForFunction(mobile => document.querySelector('[data-viewer-layout]')?.dataset.viewerLayout === (mobile ? 'mobile' : 'desktop'), width < 720);
    await settle(page);
  };
  for (const width of [719, 390, 320]) {
    await resize(width);
    await pane.locator('[data-file-panel-container]').waitFor({ state: 'hidden' });
    const scene = pane.locator('[data-cad-scene-backdrop]');
    const before = await scene.boundingBox();
    const toolbar = await pane.getByRole('group', { name: 'Interaction tools' }).boundingBox();
    const fullscreen = await pane.getByRole('button', { name: 'Fullscreen', exact: true }).boundingBox();
    assert.ok(toolbar.x + toolbar.width <= fullscreen.x, 'toolbar leaves room for fullscreen');
    assert.ok(Math.abs(toolbar.y + toolbar.height / 2 - fullscreen.y - fullscreen.height / 2) < 1, 'fullscreen aligns with the toolbar');
    const buttons = await pane.getByRole('group', { name: 'Interaction tools' }).locator('button').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().y));
    assert.equal(new Set(buttons).size, 1, `all eight tools fit one row at ${width}px`);
    assert.equal(await pane.getByRole('img', { name: 'View cube' }).count(), 0, 'no cube on mobile');
    await page.evaluate(() => {
      window.__panelLayoutFrames = [];
      const sample = () => {
        const root = document.querySelector('[data-viewer-layout]');
        const panel = root.querySelector('[data-mobile-panel]')?.getBoundingClientRect();
        const bounds = root.getBoundingClientRect();
        window.__panelLayoutFrames.push({ x: bounds.x, scroll: window.scrollX, width: document.documentElement.scrollWidth,
          panelWithin: !panel || (panel.left >= bounds.left && panel.right <= bounds.right) });
        if (window.__panelLayoutFrames.length < 45) requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    });
    await view.toggle('cad-file').click();
    const sheet = pane.locator('[data-mobile-panel]');
    await sheet.waitFor();
    await sheet.evaluate(async node => { await Promise.all(node.getAnimations().map(animation => animation.finished.catch(() => {}))); });
    assert.equal((await scene.boundingBox()).width, before.width, 'opening the sheet never resizes the scene');
    const close = await sheet.getByRole('button', { name: 'Close panel' }).boundingBox();
    assert.equal(close.width, 20, 'compact sidebar close button');
    const box = await sheet.boundingBox();
    assert.ok(box.x >= before.x && box.x + box.width <= before.x + before.width);
    assert.equal(await sheet.locator('[data-slot=sheet-title]').evaluate(node => getComputedStyle(node).position), 'absolute', 'accessible name has no visible title row');
    await sheet.getByRole('tab', { name: 'Position', exact: true }).click();
    await sheet.getByRole('combobox', { name: 'Pose', exact: true }).waitFor();
    await view.toggle('tree').click();
    await pane.getByPlaceholder('Filter files…').waitFor();
    await pane.getByRole('button', { name: 'Close panel' }).click();
    await sheet.waitFor({ state: 'hidden' });
    await page.waitForFunction(() => window.__panelLayoutFrames.length === 45);
    const frames = await page.evaluate(() => window.__panelLayoutFrames);
    assert.ok(frames.every(frame => frame.x === 0 && frame.scroll === 0 && frame.width === width && frame.panelWithin), `no sideways movement during opening/switching/closing: ${JSON.stringify(frames)}`);
  }
  await resize(720);
  await pane.locator('[data-file-panel-container="cad-file"]').waitFor();
  assert.equal(await pane.locator('[data-mobile-panel]').count(), 0);
  assert.equal(await pane.getByRole('separator', { name: /Resize/ }).count(), 1);
  assert.equal(await pane.getByRole('button', { name: /^Orbit (left|right|up|down)$/ }).count(), 0);
  assert.equal(await pane.locator('[data-cad-camera-controls]').count(), 0);
  assert.deepEqual(errors, []);
});

test('reopening ignores a saved camera and fits the model at the default perspective', async () => {
  const view = await open();
  const initial = (await view.state()).camera;
  await view.page.evaluate(() => {
    const controller = window.cadHarness.a.controller;
    const camera = controller.readState().camera;
    controller.setCamera({ ...camera, position: camera.position.map(value => value * 2), target: [15, 20, 5], zoom: 3 });
  });
  assert.notDeepEqual((await view.state()).camera.position, initial.position);
  const stored = await view.page.evaluate(() => window.cadHarness.state);
  for (const record of Object.values(stored.renderers)) record.camera = { ...initial, target: [15, 20, 5], zoom: 3, position: initial.position.map(value => value * 2) };
  const reopened = await open({ state: stored });
  const actual = (await reopened.state()).camera;
  for (const property of ['position', 'target', 'zoom']) {
    const a = [actual[property]].flat(), b = [initial[property]].flat();
    assert.ok(a.every((value, index) => Math.abs(value - b[index]) < 1e-8), `${property} is fitted fresh`);
  }
  assert.deepEqual(reopened.errors, []);
});

test('navigation and tools share short tooltips without native titles or fullscreen hints', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  await view.toggle('tree').hover();
  await page.getByRole('tooltip', { name: 'Files', exact: true }).waitFor();
  const navigationStyle = await page.locator('[data-slot="tooltip-content"]').first().getAttribute('class');
  await view.tool('Draw').hover();
  await page.getByRole('tooltip', { name: 'Draw', exact: true }).waitFor();
  const toolbarStyle = await page.locator('[data-slot="tooltip-content"]').first().getAttribute('class');
  assert.equal(toolbarStyle, navigationStyle);
  await pane.getByRole('button', { name: 'Fullscreen', exact: true }).hover();
  await page.waitForTimeout(500);
  assert.equal(await page.getByRole('tooltip').count(), 0);
  await view.tool('Display').hover();
  await page.getByRole('tooltip', { name: 'Display', exact: true }).waitFor();
  await view.tool('Display').click();
  await pane.getByRole('dialog', { name: 'Display settings' }).waitFor();
  assert.equal(await page.getByRole('tooltip').count(), 0, 'pressing a trigger dismisses its hint');
  const titles = await pane.locator('[title]').evaluateAll(nodes => nodes.map(node => node.getAttribute('title')).filter(Boolean));
  assert.deepEqual(titles, [], 'the viewer no longer mixes native hints with styled tooltips');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);
  assert.equal(await page.getByRole('tooltip').count(), 0, 'menu focus restoration does not resurrect a hint');
  await pane.getByRole('button', { name: 'File actions', exact: true }).click();
  await page.getByRole('menu', { name: 'File actions', exact: true }).waitFor();
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
});

test('mobile touch operates every STEP tool without hover or accidental pinch selections', async () => {
  const view = await open({ hasTouch: true, timeout: 10000 });
  const { page, pane, errors } = view;
  await page.setViewportSize({ width: 390, height: 844 });
  await pane.evaluate(element => { element.parentElement.style.width = '390px'; });
  await page.waitForFunction(() => document.querySelector('[data-viewer-layout]')?.dataset.viewerLayout === 'mobile');
  await page.waitForTimeout(700);
  const touch = await page.context().newCDPSession(page);
  const points = coords => coords.map(([x, y], id) => ({ x, y, id, radiusX: 3, radiusY: 3, force: 1 }));
  const gesture = async frames => {
    await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: points(frames[0]) });
    for (const coords of frames.slice(1)) {
      await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: points(coords) });
      await settle(page);
    }
    await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await settle(page);
  };
  const slide = async slider => {
    const root = slider.locator('xpath=ancestor::*[@data-slot="slider"]');
    const box = await root.boundingBox();
    const thumb = await slider.boundingBox();
    await gesture([[[thumb.x + thumb.width / 2, thumb.y + thumb.height / 2]], [[box.x + box.width * .6, box.y + box.height / 2]]]);
  };
  const sceneBox = await pane.locator('[data-cad-scene-backdrop]').boundingBox();
  const project = projector(await page.evaluate(() => window.__cadCamera()), sceneBox);
  await view.tool('Select').tap();
  await page.getByRole('menuitemradio', { name: /^Parts/ }).tap();
  await page.touchscreen.tap(...project([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  assert.equal(await pane.locator('[data-mobile-panel]').count(), 0, 'a touch pick does not cover the model with a sidebar');
  const copyAction = pane.getByRole('button', { name: /Copy Reference/ });
  await copyAction.waitFor();
  assert.ok((await copyAction.boundingBox()).width < 260, 'the mobile action hugs its content');
  assert.equal(await copyAction.locator('kbd').count(), 0, 'no desktop shortcut on mobile');
  await view.tool('Measure').tap();
  await view.tool('Measure').tap();
  await page.getByRole('menuitemradio', { name: /^Any geometry/ }).tap();
  for (const point of [[0, 0, 5], [15, 0, 4]]) await page.touchscreen.tap(...project(point));
  await page.getByRole('region', { name: 'Measurements', exact: true }).waitFor();
  assert.match(await page.getByRole('region', { name: 'Measurements', exact: true }).innerText(), /\d+\.\d+ mm/);
  await page.getByRole('button', { name: 'Close measure controls' }).tap();

  // Starting a second finger cancels a pending pick, even before either finger moves.
  await view.tool('Select').tap();
  const onModel = project([6, 6, 5]);
  await gesture([[onModel, [onModel[0] + 35, onModel[1]]], [onModel, [onModel[0] + 36, onModel[1]]]]);
  await page.waitForTimeout(250);
  assert.equal((await view.state()).selectedPartIds.length, 0);
  const cameraBefore = (await view.state()).camera;
  await gesture([[[150, 420]], [[180, 440]], [[205, 460]]]);
  await page.waitForTimeout(400);
  assert.notDeepEqual((await view.state()).camera.position, cameraBefore.position, 'one finger orbits');
  assert.equal((await view.state()).selectedPartIds.length, 0, 'orbiting never picks');

  await view.tool('Explode').tap();
  await slide(page.getByRole('slider', { name: 'Explode amount' }));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.exploded.amount > 0);
  await page.getByRole('button', { name: 'Close explode controls' }).tap();
  await view.tool('Clip').tap();
  await slide(page.getByRole('slider', { name: 'Clip amount' }));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.clip.enabled);
  await page.getByLabel('Clip Y axis', { exact: true }).tap();
  await page.getByRole('checkbox', { name: 'Flip', exact: true }).tap();
  assert.equal((await view.state()).display.clip.invert, true);
  await page.getByRole('button', { name: 'Close clip controls' }).tap();

  await view.tool('Position').tap();
  assert.equal(await pane.locator('[data-mobile-panel]').count(), 0);
  await page.waitForFunction(() => window.__cadJointHandles().length === 1);
  const [knob] = await page.evaluate(() => window.__cadJointHandles());
  const camera = (await view.state()).camera;
  await gesture([[[sceneBox.x + knob.x, sceneBox.y + knob.y]], ...knob.travel.slice(1, 9).map(([x, y]) => [[sceneBox.x + x, sceneBox.y + y]])]);
  await page.waitForFunction(() => Math.abs(window.__cadJointHandles()[0].value) > 1);
  assert.ok((await view.state()).camera.position.every((value, index) => Math.abs(value - camera.position[index]) < .01), 'joint touch dragging does not orbit (apart from residual camera damping)');
  await view.toggle('cad-file').tap();
  const sheet = pane.locator('[data-mobile-panel]');
  assert.equal(await sheet.getByRole('tab', { name: 'Features', exact: true }).getAttribute('data-state'), 'active', 'Position tool never changes the sidebar tab on mobile');
  assert.equal(await view.toggle('cad-file').getAttribute('aria-label'), 'Settings');
  assert.equal(await view.toggle('cad-file').locator('svg.lucide-sliders-horizontal').count(), 1);
  await sheet.getByRole('tab', { name: 'Position', exact: true }).tap();
  await sheet.getByRole('combobox', { name: 'Pose', exact: true }).tap();
  await page.getByRole('option', { name: 'open', exact: true }).tap();
  await page.waitForFunction(() => Number.parseFloat(document.querySelector('input[aria-label="hinge slider value"]').value) === 90);
  await sheet.getByRole('button', { name: 'Reset', exact: true }).tap();
  await slide(sheet.getByRole('slider'));
  assert.notEqual(await sheet.getByLabel('hinge slider value', { exact: true }).inputValue(), '0.00 deg');
  await sheet.getByRole('button', { name: 'Close panel' }).tap();

  await view.tool('Select').tap();
  const pinchBefore = (await view.state()).camera;
  await gesture([[[130, 450], [230, 450]], [[100, 450], [260, 450]], [[90, 450], [280, 450]]]);
  await page.waitForTimeout(300);
  assert.notEqual((await view.state()).camera.zoom, pinchBefore.zoom, 'two fingers pinch to zoom');
  const panBefore = (await view.state()).camera;
  await gesture([[[130, 450], [230, 450]], [[145, 470], [245, 470]], [[160, 480], [260, 480]]]);
  await page.waitForTimeout(300);
  assert.notDeepEqual((await view.state()).camera.target, panBefore.target, 'two fingers pan');
  assert.equal((await view.state()).selectedPartIds.length, 0, 'pinching and panning never select geometry');

  await view.tool('Draw').tap();
  await page.waitForFunction(() => document.querySelector('[data-drawing-ready]'));
  await gesture([[[110, 350]], [[125, 370]], [[150, 375]], [[175, 400]]]);
  await pane.getByRole('button', { name: /Copy Drawing|Add drawing/ }).waitFor();
  await view.tool('Draw').tap();
  const draw = page.getByRole('menu', { name: 'Draw' });
  await draw.getByRole('button', { name: 'Undo', exact: true }).tap();
  assert.equal(await draw.getByRole('button', { name: 'Redo', exact: true }).isEnabled(), true);
  await draw.getByRole('button', { name: 'Redo', exact: true }).tap();
  await draw.getByRole('button', { name: 'Line', exact: true }).tap();
  await draw.waitFor({ state: 'hidden' });
  await gesture([[[90, 330]], [[190, 440]]]);

  await view.tool('Display').tap();
  const settings = page.locator('[data-cad-display-popover]');
  await settings.waitFor();
  const mode = settings.getByRole('combobox', { name: 'Mode', exact: true });
  await mode.tap();
  await page.getByRole('option', { name: 'Wireframe', exact: true }).tap();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.mode === 'wireframe');
  await settings.getByRole('button', { name: 'Reset', exact: true }).tap();
  await page.touchscreen.tap(30, 700);
  await settings.waitFor({ state: 'hidden' });

  await view.tool('Animate').tap();
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).waitFor();
  await view.tool('Animate').tap();
  await page.getByRole('menuitem', { name: /Speed/ }).tap();
  await page.getByRole('menuitemradio', { name: '2×', exact: true }).tap();
  await pane.getByRole('button', { name: 'Pause animation', exact: true }).tap();
  await pane.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await pane.getByRole('button', { name: 'Fullscreen', exact: true }).tap();
  await page.getByRole('button', { name: 'Orbit settings', exact: true }).tap();
  await page.getByRole('menuitemcheckbox', { name: 'Orbit', exact: true }).tap();
  await page.touchscreen.tap(30, 700);
  await page.getByRole('button', { name: 'Exit fullscreen' }).tap();
  assert.deepEqual(errors, []);
});

test('freehand ink has the same visual weight as line ink', async () => {
  const view = await open();
  const { page, pane, box } = view;
  await view.tool('Draw').click();
  const ink = pane.locator('canvas.excalidraw__canvas.static');
  await page.waitForFunction(() => document.querySelector('[data-drawing-ready]'));
  const stroke = async y => {
    await page.mouse.move(box.x + 100, box.y + y);
    await page.mouse.down();
    await page.mouse.move(box.x + 240, box.y + y, { steps: 25 });
    await page.mouse.up();
  };
  await stroke(240);
  await view.tool('Draw').click();
  await page.getByRole('menu', { name: 'Draw', exact: true }).getByRole('button', { name: 'Line', exact: true }).click();
  await stroke(300);
  const shot = PNG.sync.read(await ink.screenshot());
  const thickness = y => {
    const samples = [];
    for (let x = 150; x < 200; x++) {
      let count = 0;
      for (let row = y - 10; row <= y + 10; row++) {
        const offset = (row * shot.width + x) * 4;
        if (shot.data[offset] > 180 && shot.data[offset + 1] < 110 && shot.data[offset + 2] < 150 && shot.data[offset + 3] > 100) count++;
      }
      samples.push(count);
    }
    return samples.sort((a, b) => a - b)[25];
  };
  const pen = thickness(240), line = thickness(300);
  assert.ok(pen > 0 && line > 0, `both strokes are visible: ${pen}, ${line}`);
  assert.ok(pen <= line * 1.5, `freehand is no longer an oversized brush: ${pen}px vs ${line}px`);
  assert.deepEqual(view.errors, []);
});
