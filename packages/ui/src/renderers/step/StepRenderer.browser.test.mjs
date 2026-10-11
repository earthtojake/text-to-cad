import assert from 'node:assert/strict';
import { after, afterEach, before, test } from 'node:test';
import { PNG } from 'pngjs';
import { parseCadRefToken } from '@text-to-cad/core/lib/cadRefs.js';
import { loadStepFixture, serveStepHarness } from '../harness/stepScenario.mjs';
import { TOOL_PANEL_REFERENCE_HEIGHT, TOOL_PANEL_WIDTH } from '../../../dist/renderers/kit/tools/toolStackLayout.js';

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
afterEach(async () => { await harness?.closePages(); });
after(async () => { for (const cleanup of cleanups.reverse()) await cleanup(); });

const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
// The camera at rest from one frame to the next: the opening fit, or a camera a test set.
const restingCamera = async page => {
  await page.evaluate(() => { window.__lastCamera = null; });
  await page.waitForFunction(() => {
    const camera = JSON.stringify(window.__cadCamera());
    const still = window.__lastCamera === camera;
    window.__lastCamera = camera;
    return still;
  }, null, { polling: 'raf' });
};
/** The last thing the viewport actually DREW. */
const frame = async (pane) => { await settle(pane.page()); return PNG.sync.read(await pane.locator('[aria-busy] > div > canvas').first().screenshot({ style: '[data-slot=popover-content], [data-slot=dropdown-menu-content], [data-slot=dropdown-menu-sub-content], [data-cad-tool-groups], [aria-label="View cube"] { visibility: hidden !important; }' })); };
// A canvas screenshot also catches what is drawn OVER the canvas: the tool strip
// along the top, the tool stack's panels under it (hidden for the shot: they change with
// every tool and selection) and the top-right view cube (also hidden for the shot). None is the
// model. Measurements keep the original model band of the 800 × 600 harness
// (an 800 × 564 canvas), so control placement cannot affect part-color counts. Pixel
// counts below are for this band, 385 × 800: half what the tests once measured at 1200 × 720.
const MODEL = { y0: 55, y1: 440 };
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
// Where the parts come to rest, no longer where they were (`from`): an explosion turned on has eased
// all the way out. Read on the page's own frames, not on a timer: the ease moves the parts on every
// frame it runs, so a layout unchanged for `still` frames in a row is one the ease has finished
// with. (A timer's two reads can both land between two frames of an ease a slow software renderer
// is still drawing.) It answers that layout.
const restingLayout = (page, from, still = 5) => page.evaluate(({ from, still }) => new Promise((resolve, reject) => {
  const layout = () => Object.fromEntries(window.__cadDisplayRecords().map(record => [record.partId, record.matrix.slice(12, 15)]));
  const same = (a, b) => Object.keys(a).length === Object.keys(b).length
    && Object.keys(a).every(id => b[id] && a[id].every((value, axis) => value === b[id][axis]));
  const deadline = performance.now() + 30_000;
  let last = null, unchanged = 0;
  const frame = () => {
    const now = layout();
    unchanged = last && same(now, last) && !same(now, from) ? unchanged + 1 : 0;
    last = now;
    if (unchanged >= still) resolve(now);
    else if (performance.now() > deadline) reject(new Error(`the parts never came to rest: ${JSON.stringify(now)}`));
    else requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}), { from, still });
/**
 * A label and its control on one line, measured where they are drawn: the label to the left of
 * its control, their centres level, and the control running to the panel's right edge.
 */
async function assertPairedRow(section, label, control) {
  const [sectionBox, labelBox, controlBox] = await Promise.all([
    section.locator('[data-tool-panel-body]').boundingBox(), section.getByText(label, { exact: true }).boundingBox(), control.boundingBox()]);
  assert.ok(labelBox.x + labelBox.width <= controlBox.x, 'the label sits beside its control');
  assert.ok(Math.abs((labelBox.y + labelBox.height / 2) - (controlBox.y + controlBox.height / 2)) <= 2, 'on one line');
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
  // Up to ~8 s: a software renderer's idle-quality repaint can land seconds after the pointer stops.
  for (let attempt = 0; attempt < 40; attempt += 1) {
    last = await view.frame();
    if (reached(last)) return last;
    await view.page.waitForTimeout(200);
  }
  throw new assert.AssertionError({ message: `the drawn frame never ${what}`, actual: false, expected: true, operator: '==' });
}

/**
 * The view at rest: a frame once two in a row are the same. One taken a fixed moment after a
 * change can still be the interactive pass that an idle-quality repaint replaces later, and a
 * baseline like that is one no later frame ever matches.
 */
async function restingFrame(view) {
  let last = await view.frame();
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await view.page.waitForTimeout(200);
    const next = await view.frame();
    if (differing(last, next) === 0) return next;
    last = next;
  }
  throw new assert.AssertionError({ message: 'the drawn frame never came to rest', actual: false, expected: true, operator: '==' });
}

/**
 * Measure picks: each point hovered, then pressed, a frame apart. What they measured is the
 * caller's to await (a ruler in the Measurements list).
 */
async function measurePoints(page, at, ...points) {
  for (const point of points) {
    await page.mouse.move(...at(point));
    await settle(page);
    await page.mouse.click(...at(point));
    await settle(page);
  }
}

// A page over the fixture. Unless a test seeds a record of its own, or keeps the tab in
// sessionStorage, the file's view is seeded with preview's Orbit off — a still
// preview camera, so what moves in a frame is the model — as a previous session would have left it.
async function open(options = {}) {
  const seeded = options.record === undefined && options.store !== 'session'
    ? { record: { version: 2, settings: {}, files: { [JSON.stringify([`/models/${harness.fixture.file}`, 'step'])]: { version: 2, playback: { orbit: false } } } } } : {};
  const view = await harness.open({ ...options, ...seeded });
  const { page, pane } = view;
  const ready = async () => {
    await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
    await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
    // A STEP opens in Select, so its Features panel is in the tool stack before anything is
    // located on screen. The stack floats over the viewport: it never narrows it.
    await pane.getByRole('region', { name: 'Features', exact: true }).waitFor();
    // The world axes are drawn into the same canvas and the X one is the red the
    // arm is authored in, so they would answer to a question about the arm's pixels.
    await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ axes: { enabled: false } }));
    await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.axes?.enabled === false);
    await restingCamera(page);
    await settle(page);
    const box = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
    return { box, at: projector(await page.evaluate(() => window.__cadCamera()), box) };
  };
  const { box, at } = await ready();
  const opened = {
    ...view, box, at,
    // The page again — the same tab, for a page whose tab record is in sessionStorage.
    reload: async () => { await page.reload(); Object.assign(opened, await ready()); },
    state: () => page.evaluate(() => window.cadHarness.a.controller.readState()),
    display: patch => page.evaluate(next => window.cadHarness.a.controller.setDisplaySettings(next), patch),
    // Preview: its button, last in the navbar; its X back. The file's view was seeded with Orbit
    // off: a still camera, so what moves in a frame is the model.
    enterPreview: async () => {
      await pane.getByRole('button', { name: 'Preview', exact: true }).click();
      await pane.getByRole('button', { name: 'Exit preview', exact: true }).waitFor();
    },
    exitPreview: async () => {
      await pane.getByRole('button', { name: 'Exit preview', exact: true }).click();
      await pane.getByRole('button', { name: 'Preview', exact: true }).waitFor();
    },
    // Display is not a tool: its button sits before Preview at the navbar's right end.
    tool: name => name === 'Display' ? pane.locator('[data-view-controls]').getByRole('button', { name, exact: true })
      : pane.locator(name === 'Reset' ? '[data-cad-camera-controls]' : '[data-cad-toolbar]').getByRole('button', { name, exact: true }),
    tools: () => pane.locator('[data-cad-toolbar]').getByRole('button')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    // The tool stack's panels on screen, top to bottom, by their accessible names.
    stack: () => pane.locator('[data-cad-tool-stack] [data-tool-panel]').evaluateAll(panels => panels
      .filter(panel => panel.getClientRects().length > 0).map(panel => panel.getAttribute('aria-label'))),
    // Select's modes are a menu in the Features filter row (`SelectionModes.jsx`); the strip opens no menu.
    chooseSelectMode: async name => {
      // The mode menu steps aside while the filter box has focus.
      await page.evaluate(() => document.activeElement instanceof HTMLInputElement && document.activeElement.blur());
      await pane.getByRole('button', { name: /^Select mode: / }).click();
      await page.locator('[role=menu][aria-label="Select mode"]').getByRole('menuitemradio', { name, exact: true }).click();
      await page.locator('[role=menu]').waitFor({ state: 'detached' });
    },
    // Display's settings: a dropdown, portaled out of the viewer.
    displayPanel: () => page.locator('[data-display-popover]'),
    rows: () => pane.locator('[aria-label="Modeling tree"]').getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))
      .filter(label => label?.startsWith('Select ') || label?.startsWith('Expand ') || label?.startsWith('Collapse '))),
    frame: () => frame(pane),
    // What the pointer looks like over the model. Read from the INTERACTIVE
    // canvas: a tool sets the cursor on the viewport host and the canvas
    // inherits it, which three's OrbitControls used to break by pinning
    // `cursor: auto` on the canvas inline (`kit/viewport/useViewerRuntime.js`).
    waitCursor: value => page.waitForFunction(wanted => getComputedStyle(
      document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')).cursor === wanted, value),
  };
  return opened;
}


test('a STEP opens in Select with the tools its sidecar earns, its Features in the tool stack and Display and Preview in the navbar, and paints both authored colours', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  assert.deepEqual(await view.tools(), ['Select:true', 'Position:false', 'Animation:false', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false'],
    'Position because the sidecar bound, Animation because it has a routine. Display is a dropdown from the navbar, not a tool');
  assert.deepEqual(await pane.locator('[data-view-controls] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Display', 'Preview'], 'the view\'s controls at the navbar\'s right end: Display, then Preview');
  assert.equal(await view.displayPanel().count(), 0, 'Display is never where a file opens');
  assert.equal(await pane.locator('[data-view-controls]').getByRole('button', { name: 'Preview', exact: true }).count(), 1,
    'a STEP is 3D: Preview sits in its navbar');
  // Select is the tool, so the stack shows its Features — an assembly's tree starts open — with no
  // tabs, and nothing of Position's.
  assert.deepEqual(await view.stack(), ['Features']);
  assert.equal(await view.tool('Select').locator('[data-tool-panel-closed]').count(), 0, 'Select unmarked: its tree is open');
  assert.equal(await pane.getByRole('tab').count(), 0, 'no tabs anywhere');
  assert.equal(await pane.getByRole('combobox', { name: 'Pose', exact: true }).isVisible(), false);
  const [stack, toolbar] = await Promise.all([pane.getByRole('region', { name: 'Features', exact: true }).boundingBox(),
    pane.locator('[data-cad-toolbar]').boundingBox()]);
  assert.ok(Math.abs(stack.x - toolbar.x) <= 1 && stack.y >= toolbar.y + toolbar.height, 'Features hangs under the toolbar, at its left edge');
  // The stack floats over the viewport: the canvas is the viewer's whole width.
  assert.equal(view.box.width, (await pane.locator('[data-cad-scene-backdrop]').boundingBox()).width);
  const opened = await view.frame();
  assert.ok(coverage(opened) > 0.2, `the opening frame is the model: ${coverage(opened)}`);
  const boxes = partBoxes(opened);
  assert.ok(boxes.base?.count > 2000 && boxes.arm?.count > 1000, `both parts are drawn, each in its own colour: ${JSON.stringify(boxes)}`);
  assert.deepEqual(await view.rows(), ['Expand base', 'Select base', 'Expand arm', 'Select arm']);
  // Its cap is half the stack's own height (the area under the strip), and a cap is never a
  // floor: two rows are two rows tall.
  const featuresPanel = pane.getByRole('region', { name: 'Features', exact: true });
  const stackHeight = await pane.locator('[data-cad-tool-stack]').evaluate(node => node.clientHeight);
  const fit = await featuresPanel.evaluate(node => ({ cap: node.style.maxHeight, height: node.getBoundingClientRect().height,
    rows: node.querySelector('[data-tool-panel-body]').scrollHeight, filter: node.querySelector('[data-slot=tree-filter]').getBoundingClientRect().height }));
  assert.equal(fit.cap, `${Math.round(stackHeight / 2)}px`, 'the tree opens capped at half the stack');
  assert.ok(Math.abs(fit.height - (fit.filter + fit.rows + 2)) <= 1, `and is its filter row and its rows: ${JSON.stringify(fit)}`);
  // Its X, at the filter row's end, closes it; Select, pressed while it is the tool, opens it again
  // as it was. (Recognition is unavailable in this harness: a part opens onto one supplied feature.)
  await page.evaluate(() => {
    window.Worker = class {
      constructor(url) { if (!String(url).includes('modelingTree.worker')) throw new Error('No worker'); }
      postMessage() { queueMicrotask(() => this.onmessage?.({ data: { tree: [{
        id: 'feature:box', kind: 'extrude', label: 'Box', faces: [1, 2, 3], edges: [1], children: [], complete: true
      }] } })); }
      terminate() {}
    };
  });
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  await pane.getByRole('button', { name: 'Select Box', exact: true }).waitFor();
  await pane.getByRole('button', { name: 'Collapse base', exact: true }).waitFor();
  const openedRows = await view.rows();
  assert.equal(await featuresPanel.getByRole('button', { name: /^(?:Collapse|Expand) features$/ }).count(), 0, 'the tree does not fold');
  const selectMark = view.tool('Select').locator('[data-tool-panel-closed]');
  assert.equal(await selectMark.count(), 0);
  await featuresPanel.locator('[data-slot=tree-filter]').getByRole('button', { name: 'Close features', exact: true }).click();
  await featuresPanel.waitFor({ state: 'hidden' });
  assert.deepEqual(await view.stack(), [], 'closed: the tree is off the stack');
  // Select carries the flyout corner while its tree is closed, in its button's bottom-right corner.
  const [mark, selectBox] = await Promise.all([selectMark.boundingBox(), view.tool('Select').boundingBox()]);
  assert.ok(mark && Math.abs(mark.x + mark.width - selectBox.x - selectBox.width) <= 1 && Math.abs(mark.y + mark.height - selectBox.y - selectBox.height) <= 1,
    `the mark sits in Select's bottom-right corner: ${JSON.stringify([mark, selectBox])}`);
  assert.deepEqual((await page.evaluate(() => window.cadHarness.preferences.getSnapshot().toolStack)).closed, { tree: true });
  await view.tool('Select').click();
  await featuresPanel.waitFor();
  assert.equal(await selectMark.count(), 0, 'open again: the mark goes');
  assert.deepEqual(await view.rows(), openedRows, 'the tree kept its expansion while closed');
  assert.deepEqual(await page.evaluate(() => window.cadHarness.preferences.getSnapshot().toolStack), { panels: {}, collapsed: {}, closed: { tree: false } },
    'nothing sized; the tree opened again, the person\'s choice for every file of the tab');
  // One grip, Quick Edit's, in the bottom-right corner and inside the panel's border: it alone sizes the panel.
  assert.deepEqual(await featuresPanel.getByRole('separator').evaluateAll(handles => handles.map(handle => handle.getAttribute('aria-label'))), ['Resize features']);
  const [grip, panelBox] = await Promise.all([featuresPanel.getByRole('separator', { name: 'Resize features', exact: true }).boundingBox(), featuresPanel.boundingBox()]);
  assert.ok(Math.abs(grip.x + grip.width - (panelBox.x + panelBox.width - 1)) <= 1 && Math.abs(grip.y + grip.height - (panelBox.y + panelBox.height - 1)) <= 1,
    `the grip fills the corner inside the border: ${JSON.stringify([grip, panelBox])}`);
  // The stack itself never scrolls while its panels fit — nothing reaches past its column — so a
  // wheel over it moves no border. Held shorter than its rows, the tree scrolls inside its own
  // border instead.
  const stackOverflow = () => pane.locator('[data-tool-stack-scroller]').evaluate(node => [node.scrollWidth - node.clientWidth, node.scrollHeight - node.clientHeight]);
  assert.deepEqual(await stackOverflow(), [0, 0], 'the stack has nothing to scroll');
  await pane.getByRole('separator', { name: 'Resize features', exact: true }).press('Home');
  await pane.locator('section[aria-label="Features"][style*="max-height: 64px"]').waitFor();
  assert.equal(await featuresPanel.locator('[data-tool-panel-body]').evaluate(node => node.scrollHeight > node.clientHeight), true, 'the tree scrolls its rows');
  assert.deepEqual(await stackOverflow(), [0, 0], 'and the stack still has nothing to scroll');
  assert.deepEqual(errors, []);
});

test('a pick names its face or edge by the id cadgen minted in the selector table, and Group edges grows it to the table\'s chain', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  // The table the surface request served for the base, as cadgen stored it beside the surface:
  // the ids a pick must answer with are its rows', joined to the mesh by ordinal, never the page's.
  const fixture = await loadStepFixture();
  const base = fixture.view.occurrences.find(occurrence => occurrence.name === 'base');
  const table = JSON.parse(fixture.surfaces.get(fixture.view.components[base.component].surfaceInput).selectors.bytes.toString());
  const rows = (name, columns) => table[name].map(row => Object.fromEntries(table.tables[columns].map((column, index) => [column, row[index]])));
  const top = rows('faces', 'faceColumns').find(face => face.normal && face.normal[2] > 0.5);
  const edges = rows('edges', 'edgeColumns');
  const rim = edges.find(edge => edge.curveType === 'line' && edge.bbox.min[0] === 10 && edge.bbox.max[0] === 10
    && edge.bbox.min[2] === 5 && edge.bbox.max[2] === 5);
  assert.ok(top && rim, 'the base has a top face and a top rim edge along +X');
  // A selected reference id ends in the selector the pick resolved to (`topology|<part>|<type>|<selector>`).
  const selected = () => page.evaluate(() => window.cadHarness.a.controller.readState().selectedReferenceIds.map(id => id.split('|').pop()));
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  // The part's topology lands after the row opens, and a press before it lands picks the part:
  // press until a face answers, then hold it to cadgen's id.
  for (let attempt = 0; attempt < 50 && !(await selected()).some(id => /\.f\d+$/.test(id)); attempt += 1) {
    await page.mouse.click(...at([6, 6, 5]));
    await page.waitForTimeout(100);
  }
  assert.deepEqual(await selected(), [`${base.id}.${top.localId}`], 'the top face is the table\'s row, under its occurrence');
  await page.mouse.click(...at([10, 6, 5]));
  await page.waitForFunction(() => /\.e\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds[0] || ''));
  assert.deepEqual(await selected(), [`${base.id}.${rim.localId}`], 'the rim edge is the table\'s row');
  // Group edges: the pick grows to the edges of the table's chain, which for a box edge is itself
  // alone (its ends each meet two edges at a right angle), however close the neighbours lie.
  await page.evaluate(() => document.activeElement instanceof HTMLInputElement && document.activeElement.blur());
  await pane.getByRole('button', { name: /^Select mode: / }).click();
  await page.locator('[role=menu][aria-label="Select mode"]').getByRole('menuitemcheckbox', { name: 'Group edges', exact: true }).click();
  // A checkbox item keeps its menu open for the next one; Escape puts it away.
  await page.keyboard.press('Escape');
  await page.locator('[role=menu]').waitFor({ state: 'detached' });
  await page.mouse.click(...at([10, 6, 5]));
  await page.waitForFunction(() => /\.e\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds[0] || ''));
  const chain = edges.filter(edge => edge.chain === rim.chain).map(edge => `${base.id}.${edge.localId}`);
  assert.deepEqual((await selected()).sort(), chain.sort(), 'the grown selection is the table\'s chain');
  assert.deepEqual(errors, []);
});

test('Select picks parts and faces, a selection lives only under Select, and the Reference panel measures what is picked', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  const reference = pane.getByRole('region', { name: 'Reference details', exact: true });

  // Hover lights the part under the pointer, and lets go when it leaves.
  const still = await restingFrame(view);
  await page.mouse.move(...at([6, 6, 5]));
  // Over a part the pointer says it can be picked; over the backdrop it does not.
  await view.waitCursor('pointer');
  await frameWhen(view, shot => differing(still, shot) > 2000, 'lit the hovered part');
  await page.mouse.move(view.box.x + view.box.width - 20, view.box.y + view.box.height - 20);
  await view.waitCursor('auto');
  await frameWhen(view, shot => differing(still, shot) === 0, 'came back exactly as it was once the pointer left');

  // In the viewport a press picks ONE face or ONE edge, even where the tree groups them: under
  // All an open part's faces are what a press picks, and this part opens onto a feature of seven
  // faces (recognition is unavailable in this harness, so the feature is supplied).
  await page.evaluate(() => {
    window.Worker = class {
      constructor(url) { if (!String(url).includes('modelingTree.worker')) throw new Error('No worker'); }
      postMessage() { queueMicrotask(() => this.onmessage?.({ data: { tree: [{
        id: 'feature:box', kind: 'extrude', label: 'Grouped faces', faces: [1, 2, 3, 4, 5, 6, 7], edges: [1, 2, 3], children: [], complete: true
      }] } })); }
      terminate() {}
    };
  });
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  // The feature row can arrive before the faces it names, and under All a press before they land
  // picks the part. The row's own press waits for them and selects what it groups, its seven faces
  // and three edges; the viewport press then narrows that to one face.
  await pane.getByRole('button', { name: 'Select Grouped faces', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds
    .filter(id => /\.f\d+$/.test(id)).length === 7);
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => { const ids = window.cadHarness.a.controller.readState().selectedReferenceIds;
    return ids.length === 1 && /\.f\d+$/.test(ids[0]); });
  // The pick opened Quick Edit with the pick attached, and the keyboard is in its box.
  const quickEdit = pane.getByRole('region', { name: 'Quick Edit', exact: true });
  await quickEdit.locator('[data-quick-edit-chip="references"]').waitFor();
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'Describe your changes');
  await page.mouse.click(...at([10, 6, 5]));
  await page.waitForFunction(() => { const ids = window.cadHarness.a.controller.readState().selectedReferenceIds;
    return ids.length === 1 && /\.e\d+$/.test(ids[0]); });
  // Folding the part away unloads its faces, and the pick with them: the tree is as it opened.
  await pane.getByRole('button', { name: 'Collapse base', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 0);

  // No Reference until something is picked: it comes with the selection.
  assert.deepEqual(await view.stack(), ['Features']);
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  assert.deepEqual((await view.state()).selectedPartIds, ['o1.1']);
  // Headed by the part's name, over its key measurements and its Copy: no id, type, position or
  // material rows (what a copy carries is the Copy's).
  const partText = (await reference.innerText()).replace(/\s+/g, ' ');
  assert.match(partText, /^base Size 20 × 20 × 10 mm (?:Volume [\d,.]+ mm³ )?Copy/);
  assert.doesNotMatch(partText, /\bType\b|\bID\b|o1\.1|Center|Material|Color/);
  assert.equal(await reference.locator('[data-reference-count]').count(), 0, 'one reference has no i/N');
  // Compact rows in the panel's one face: every value is the UI font at the panel's size, never
  // monospace. The Reference opens at every panel's width and its own default cap, shorter than the
  // tree's, and is sized on its own by its corner grip — so a long value (a size) wraps to a second
  // line rather than widening it, and what runs past the cap scrolls inside it.
  assert.equal(Math.round((await reference.boundingBox()).width), TOOL_PANEL_WIDTH);
  assert.equal(await reference.evaluate(node => node.style.maxHeight), `${TOOL_PANEL_REFERENCE_HEIGHT}px`);
  assert.ok((await reference.boundingBox()).height <= TOOL_PANEL_REFERENCE_HEIGHT, 'never past its cap');
  assert.deepEqual(await reference.getByRole('separator').evaluateAll(handles => handles.map(handle => handle.getAttribute('aria-label'))), ['Resize reference details']);
  const faces = await reference.locator('[data-tool-panel-body] *').evaluateAll(nodes => [...new Set(nodes
    .filter(node => !node.childElementCount && node.textContent.trim())
    .map(node => `${getComputedStyle(node).fontFamily} | ${getComputedStyle(node).fontSize}`))]);
  assert.equal(faces.length, 1, `one face and size: ${faces.join(' / ')}`);
  assert.doesNotMatch(faces[0], /mono/i);
  assert.match(faces[0], /\| 11px$/);
  const rowHeights = await reference.locator('[data-info-row]').evaluateAll(rows => rows.map(row => row.getBoundingClientRect().height));
  assert.ok(rowHeights.length >= 1 && rowHeights.every(height => height <= 19 * 2), `compact rows, a line or two each: ${rowHeights}`);
  assert.equal(await reference.locator('[data-tool-panel-body]').evaluate(node => node.scrollHeight <= node.clientHeight), true,
    'the name, the key measurements and the Copy fit the cap it opens with: nothing to scroll to');
  // The Reference is the next panel of the stack, under Features, both at the one width until a person sizes either.
  assert.deepEqual(await view.stack(), ['Features', 'Reference details']);
  const [features, pinned] = await Promise.all([pane.getByRole('region', { name: 'Features', exact: true }).boundingBox(), reference.boundingBox()]);
  assert.ok(pinned.y >= features.y + features.height && pinned.y - (features.y + features.height) <= 10, `directly under Features: ${pinned.y} vs ${features.y + features.height}`);
  assert.equal(pinned.width, features.width, 'the one width');
  // The Features filter row is a heading's height, dense: its buttons sit exactly where a heading's
  // do, 5px down from their panel's top.
  const featuresPanel = pane.getByRole('region', { name: 'Features', exact: true });
  const [close, clear] = await Promise.all([featuresPanel.getByRole('button', { name: 'Close features', exact: true }).boundingBox(),
    reference.getByRole('button', { name: 'Clear selection', exact: true }).boundingBox()]);
  assert.equal(Math.round(close.y - features.y), 5, 'the filter row\'s X');
  assert.equal(Math.round(clear.y - pinned.y), 5, 'the Reference heading\'s X');
  assert.equal(close.height, clear.height);
  assert.equal(await pane.getByRole('textbox', { name: 'Filter model', exact: true }).evaluate(node => getComputedStyle(node).fontSize), '11px');
  assert.equal(await pane.getByRole('button', { name: 'Select base', exact: true }).getAttribute('aria-pressed'), 'true', 'the tree row follows the viewport');
  await page.keyboard.down('Shift');
  await page.mouse.click(...at([15, 0, 4]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 2);
  // Two references: the heading is a picker, the browsed one's name and its place, and no count line.
  const picker = reference.getByRole('combobox', { name: 'Inspect selected reference' });
  assert.match((await picker.innerText()).replace(/\s+/g, ' '), /^arm 2\/2$/);
  // Its text is flush with the rows' labels.
  const [nameBox, labelBox] = await Promise.all([picker.locator('[data-reference-label] > span').first().boundingBox(),
    reference.getByText('Size', { exact: true }).boundingBox()]);
  assert.ok(Math.abs(nameBox.x - labelBox.x) <= 1, `the picker's text aligns with the row labels: ${nameBox.x} vs ${labelBox.x}`);
  // Hovering it is quiet in either theme — no fill — and moves nothing in the heading.
  for (const dark of [false, true]) {
    await page.evaluate(on => document.documentElement.classList.toggle('dark', on), dark);
    await page.mouse.move(view.box.x + view.box.width - 40, view.box.y + 40);
    const [still, stillName] = await Promise.all([picker.boundingBox(), picker.locator('[data-reference-label]').boundingBox()]);
    await picker.hover();
    await page.waitForTimeout(150);
    assert.equal(await picker.evaluate(node => getComputedStyle(node).backgroundColor), 'rgba(0, 0, 0, 0)', `no hover fill (${dark ? 'dark' : 'light'})`);
    assert.deepEqual([await picker.boundingBox(), await picker.locator('[data-reference-label]').boundingBox()], [still, stillName], 'hovering moves nothing');
  }
  await page.evaluate(() => document.documentElement.classList.remove('dark'));
  assert.doesNotMatch(await reference.innerText(), /Selection ·|references|Total/);
  // Quick Edit counts both references, and the person's pick put the keyboard in its note; Escape in
  // its empty box clears the selection, as it would from the model, and the box goes with it.
  await quickEdit.waitFor();
  assert.equal(await quickEdit.locator('[data-quick-edit-chip="references"]').innerText(), '2 refs');
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'Describe your changes');
  assert.equal(await pane.locator('[data-viewport-bottom-actions]').count(), 0, 'nothing sits at the bottom of the view');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  await quickEdit.waitFor({ state: 'detached' });

  // A selection exists only under Select, and so do its panels: another tool takes both away,
  // and Select brings the tree back as it was.
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  await view.tool('Measure').click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  assert.deepEqual(await view.stack(), ['Measure controls'], 'Measure shows its own panel: no Features and no Reference');
  await view.tool('Select').click();
  assert.deepEqual(await view.stack(), ['Features']);
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  assert.deepEqual((await view.state()).selectedPartIds, ['o1.2']);
  // The Reference's X clears the selection, and the panel goes with it.
  await reference.getByRole('button', { name: 'Clear selection', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  assert.deepEqual(await view.stack(), ['Features']);

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
  // And what a host's capture delivers: the snapshot carries the file, the references the selection.
  await page.evaluate(() => window.cadHarness.a.controller.select({ selectors: ['o1.1'] }));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.equal(captured.type, 'image/png');
  assert.ok(captured.size > 100);
  assert.deepEqual(captured.references.map(reference => reference.target),
    [{ kind: 'cad-selector', selectors: ['o1.1'] }], 'the snapshot carries the selection as its references');

  assert.deepEqual(errors, []);
});

test('under Faces or Edges, one press on a part whose faces are not loaded loads that part alone and picks what is under the pointer, and an update keeps the mode', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  const reference = pane.getByRole('region', { name: 'Reference details', exact: true });
  const mode = name => view.chooseSelectMode(name);
  const selected = () => page.evaluate(() => window.cadHarness.a.controller.readState().selectedReferenceIds);
  // The tree loads a part's faces as its row comes on screen. With a filter that matches
  // nothing, no row is on screen, so under Faces no part has its faces loaded.
  await pane.getByRole('textbox', { name: 'Filter model', exact: true }).fill('zzz');
  await mode('Faces');
  assert.deepEqual([(await view.state()).selectedPartIds, await view.rows()], [[], []]);
  // One press on the base's top face: the base's topology loads — the Features panel says so
  // while it does — and that face is picked, with no second press. The load is quick here, so
  // what the panel showed is recorded as it is drawn.
  await page.evaluate(() => {
    window.__sawLoading = [];
    new MutationObserver(() => {
      for (const status of document.querySelectorAll('[data-testid="one"] [aria-label="Features"] [role=status]')) {
        if (status.textContent === 'Loading…') window.__sawLoading.push(window.cadHarness.a.controller.readState().selectedReferenceIds.length);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => /^topology\|o1\.1\|face\|o1\.1\.f\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  const face = (await selected())[0].split('|').at(-1);
  assert.deepEqual(await page.evaluate(() => window.__sawLoading.slice(0, 1)), [0], 'the Features panel said it was loading, before anything was picked');
  assert.equal(await pane.getByRole('region', { name: 'Features', exact: true }).getByText('Loading…').count(), 0, 'and stops once the face is picked');
  assert.equal(await pane.locator('[data-cad-toolbar] [role=status]').count(), 0, 'nothing under the strip says so');
  // Named by its part as the tree names it and its kind, never by its raw id, which is no row either.
  const faceText = (await reference.innerText()).replace(/\s+/g, ' ');
  assert.match(faceText, new RegExp(`^base · face ${face.replace(/^.*\.f/, '')} Area [\\d,.]+ mm² Copy`), 'the Reference names the face under the pointer, over its area');
  assert.doesNotMatch(faceText, new RegExp(`\\bType\\b|\\bID\\b|${face.replace(/\./g, '\\.')}|Center|Normal|Material`));
  assert.deepEqual((await view.state()).selectedPartIds, [], 'the mode never falls back to the part');
  // Edges likewise, on the arm, whose topology is still not loaded (the panel says so again):
  // its top edge over the +x face.
  const sawBefore = await page.evaluate(() => window.__sawLoading.length);
  await mode('Edges');
  await page.mouse.click(...at([20, 0, 4]));
  await page.waitForFunction(() => /^topology\|o1\.2\|edge\|o1\.2\.e\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  assert.ok(await page.evaluate(() => window.__sawLoading.length) > sawBefore, 'only the pressed part had loaded');
  const edge = (await selected())[0].split('|').at(-1);
  const edgeText = (await reference.innerText()).replace(/\s+/g, ' ');
  assert.match(edgeText, new RegExp(`^arm · edge ${edge.replace(/^.*\.e/, '')} Length [\\d,.]+ mm Copy`), 'its length, the one measurement a straight edge has');
  assert.doesNotMatch(edgeText, new RegExp(`\\bType\\b|\\bID\\b|${edge.replace(/\./g, '\\.')}`));
  // An update of the model keeps the mode, and drops what was picked in the revision before it.
  await view.update();
  assert.equal(await view.tool('Select').locator('[data-select-mode]').getAttribute('data-select-mode'), 'edges');
  assert.deepEqual(await selected(), []);
  assert.deepEqual(errors, []);
});

test('a revision that fails to build leaves the model before it on screen, and its tree, to work with', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const parts = async () => (await view.rows()).filter(label => label.startsWith('Select '));
  assert.deepEqual(await parts(), ['Select base', 'Select arm']);
  await pane.getByRole('button', { name: 'Hide arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().hiddenPartIds.join() === 'o1.2');
  // The file saved again, broken: the card says so over the model the view still shows, and the
  // tree lists that model's parts -- not the bare part a file with no build is listed as. (Their
  // features and faces are its build's, which the broken file has none of.)
  await view.fail();
  await pane.getByRole('alert').waitFor();
  assert.deepEqual(await parts(), ['Select base', 'Select arm']);
  assert.deepEqual((await view.state()).hiddenPartIds, ['o1.2'], 'what was hidden stays hidden');
  // Nothing is coming to replace it, so it is not held as a rebuild is: it is picked from, and the
  // view does not read as loading.
  await pane.getByRole('button', { name: 'Select base', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  assert.equal((await view.state()).loading, false);
  assert.deepEqual(errors, []);
});

// What the one part menu offers, in order, ending in the framing group. That group is
// the viewer's ONLY zoom control — the old Inspector's percentage readout and its menu are
// gone — so it is here, on every tree row, and on the empty-space menu below. It cannot
// contradict the tool in hand: every item returns to Select before it acts.
const ZOOM_SECTION = ['Zoom to fit', 'Zoom to selection'];
const PART_MENU = ['Copy Reference', 'Select', 'Isolate', 'Hide others', 'Hide',
  'Expand', 'Collapse', 'Expand all', 'Collapse all', ...ZOOM_SECTION];

test('hiding a part takes it off the screen, and the viewport menus offer what they can do', async () => {
  const view = await open();
  const { page, pane, at, box, errors } = view;
  const opened = await restingFrame(view);
  await pane.getByRole('button', { name: 'Hide arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().hiddenPartIds.join() === 'o1.2');
  const hidden = await view.frame();
  assert.equal(partBoxes(hidden).arm, null, 'a hidden part is off the screen, not merely off a list');
  assert.ok(partBoxes(hidden).base.count > partBoxes(opened).base.count * 0.9, 'and the rest of the model is still drawn');
  await pane.getByRole('button', { name: 'Reveal arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().hiddenPartIds.length === 0);
  const away = () => page.mouse.move(view.box.x + view.box.width - 20, view.box.y + view.box.height - 20);
  await away();
  await frameWhen(view, shot => differing(opened, shot) === 0, 'came back to what hiding the arm took away');
  // Hover runs the other way too: resting on a tree row lights its part. These frames keep the
  // tool stack on screen and are read to its right: hiding it for a screenshot is the pointer
  // leaving the row, which on a slow (software) renderer lands before the hover is drawn.
  const canvas = pane.locator('[aria-busy] > div > canvas').first();
  const withStack = async () => { await settle(page); return PNG.sync.read(await canvas.screenshot()); };
  const [canvasBox, stackBox] = [await canvas.boundingBox(), await pane.locator('[data-cad-tool-stack]').boundingBox()];
  const rest = await withStack();
  const rightOfStack = { x0: Math.ceil(stackBox.x + stackBox.width - canvasBox.x) + 4, y0: 0, x1: rest.width, y1: rest.height };
  await pane.getByRole('button', { name: 'Select arm', exact: true }).hover();
  let lit = 0;
  for (let attempt = 0; attempt < 16 && lit <= 2000; attempt += 1) {
    lit = differing(rest, await withStack(), rightOfStack);
    if (lit <= 2000) await page.waitForTimeout(200);
  }
  assert.ok(lit > 2000, `the drawn frame lit the part under the hovered row: ${lit} pixels changed`);
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
  await page.mouse.click(box.x + box.width - 30, box.y + box.height - 30, { button: 'right' });
  await page.getByRole('menu').waitFor();
  assert.deepEqual(await page.getByRole('menuitem').allTextContents(), ['Expand all', 'Collapse all', ...ZOOM_SECTION]);
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });

  // A tree row carries that same menu, item for item; the viewport's belongs to Select alone.
  await pane.getByRole('button', { name: 'Select base', exact: true }).click({ button: 'right' });
  await page.getByRole('menu').waitFor();
  assert.deepEqual(await page.getByRole('menuitem').allTextContents(), PART_MENU);
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await away();
  for (const tool of ['Measure', 'Position', 'Animation', 'Draw']) {
    await view.tool(tool).click();
    // A menu opens in the render the press causes: two frames on, it would be there.
    await page.mouse.click(...at([6, 6, 5]), { button: 'right' });
    await settle(page);
    assert.equal(await page.getByRole('menu').count(), 0, `${tool} opens no viewport menu over a part`);
    await page.mouse.click(box.x + box.width - 30, box.y + box.height - 30, { button: 'right' });
    await settle(page);
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
  // The tree is Select's: under another tool it is off screen, and Select brings it back to act
  // from — Isolate, which has no selection of its own to make.
  assert.deepEqual(await view.tools(), ['Select:false', 'Position:false', 'Animation:false', 'Draw:true', 'Measure:false', 'Explode:false', 'Clip:false']);
  assert.equal(await pane.getByRole('button', { name: 'Select arm', exact: true }).isVisible(), false);
  await view.tool('Select').click();
  // A menu goes when the camera moves, and the last pan is still coasting: it opens at rest.
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Isolate', exact: true }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.2');
  assert.deepEqual(await view.tools(), ['Select:true', 'Position:false', 'Animation:false', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false']);
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
});

test('a library picture is the model on its own, on transparency: the grid and axes a person turned on are not in it', async () => {
  const view = await open();
  const { page, errors } = view;
  const picture = () => page.evaluate(async () => {
    const png = await window.cadHarness.a.controller.thumbnail({ width: 240, height: 180 });
    return Array.from(new Uint8Array(await png.arrayBuffer()));
  });
  const bare = await picture();
  assert.equal(PNG.sync.read(Buffer.from(bare)).data[3], 0, 'its corner is transparent');
  await view.display({ grid: { enabled: true }, axes: { enabled: true } });
  await page.waitForFunction(() => { const { display } = window.cadHarness.a.controller.readState(); return display.grid?.enabled === true && display.axes?.enabled === true; });
  assert.deepEqual(await picture(), bare, 'the same picture with the grid and the axes up');
  assert.deepEqual(errors, []);
});

test('the context menu\'s Zoom to selection frames the selection', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  const menuItem = name => page.getByRole('menuitem', { name, exact: true });
  // Read off the DRAWN frame: how wide the arm is in the pane. The camera eases, so each claim
  // waits for the picture to arrive rather than sleeping.
  const armWidth = image => { const arm = partBoxes(image).arm; return arm ? arm.x1 - arm.x0 : 0; };
  const fitted = armWidth(await frameWhen(view, shot => armWidth(shot) > 0, 'drew the arm'));
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  await page.mouse.click(...at([6, 6, 5]), { button: 'right' });
  await page.getByRole('menu').waitFor();
  assert.equal(await menuItem('Zoom to selection').getAttribute('aria-disabled'), null, 'a selection enables it');
  await menuItem('Zoom to selection').click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await frameWhen(view, shot => coverage(shot) > 0.9, 'filled the pane with what was selected');
  // A selected part wears the selection ink, so its own colour only comes back once the
  // selection is dropped — which moves no camera. THEN the arm can be measured, and it
  // is the arm that the camera was put on.
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);
  await frameWhen(view, shot => armWidth(shot) > fitted * 1.3,
    `framed the selected arm rather than the model (${fitted} wide at the model fit)`);
  assert.deepEqual(errors, []);
});

// How much of the model band each preset repaints against Solid, at the least: a tenth of it,
// but Grid, which only rules lines over Solid's own surfaces.
const MIN_REDRAWN = { render: 30_000, xray: 30_000, 'hidden-line': 30_000, wireframe: 30_000, grid: 6_000 };
test('every Display preset reaches the drawn frame, on the live canvas', async () => {
  const view = await open();
  const { page, errors } = view;
  // Display is a dropdown from its button in the navbar, over the viewport.
  await view.tool('Display').click();
  const panel = view.displayPanel();
  await panel.waitFor();
  const solid = await restingFrame(view);
  await page.evaluate(() => { window.openingCanvas = document.querySelector('[data-testid="one"] [aria-busy] > div > canvas'); });

  // Each preset draws a different picture, and none of them replaces the canvas.
  const frames = { solid };
  for (const [mode, label] of [['render', 'Render'], ['xray', 'X-ray'], ['hidden-line', 'Hidden line'], ['wireframe', 'Wireframe'], ['grid', 'Grid']]) {
    if (!await panel.isVisible()) await view.tool('Display').click();
    await panel.getByRole('combobox', { name: 'Mode', exact: true }).click();
    await page.getByRole('option', { name: label, exact: true }).click();
    assert.equal(await panel.isVisible(), true, 'choosing a preset keeps the dropdown');
    await page.waitForFunction(wanted => {
      const state = window.cadHarness.a.controller.readState();
      return state.display.mode === wanted && !state.loading;
    }, mode);
    frames[mode] = await frameWhen(view, shot => differing(solid, shot) > MIN_REDRAWN[mode], `redrew the model for ${label}`);
  }
  // Each is its own picture, not merely "not Solid".
  for (const [left, right] of [['render', 'xray'], ['xray', 'hidden-line'], ['hidden-line', 'wireframe'], ['wireframe', 'grid']]) {
    assert.ok(differing(frames[left], frames[right]) > 10_000, `${left} and ${right} are different pictures`);
  }
  assert.ok(coverage(frames['hidden-line']) < 0.1 && coverage(solid) > 0.3,
    `hidden line is linework over the backdrop and Solid is filled: ${coverage(frames['hidden-line'])} vs ${coverage(solid)}`);
  assert.equal(await page.evaluate(() => window.openingCanvas === document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')), true,
    'a preset edits the live canvas; it never replaces it');
  assert.deepEqual(errors, []);
});

test('Position drives the mate and repaints, a named pose jumps, the Position knob is never the camera, and the grid keeps the size the rest pose gave it', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // The grid is only the Grid preset's by default; this compares its lines, so it is turned on.
  await view.display({ grid: { enabled: true } });
  // A file with movable joints has Position straight after Select on the strip, and one with
  // routines Animation after it.
  assert.deepEqual((await pane.getByRole('group', { name: 'Interaction tools' }).locator('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')))).slice(0, 4),
    ['Select', 'Position', 'Animation', 'Draw']);
  // Position shows its panel in the tool stack, in place of Select's, and enables the joint handles.
  await view.tool('Position').click();
  const panel = pane.getByRole('region', { name: 'Position controls', exact: true });
  assert.deepEqual(await view.stack(), ['Position controls']);
  assert.deepEqual(await panel.getByRole('heading').allInnerTexts(), ['Position'], 'headed Position');
  const slider = page.getByLabel('hinge slider value', { exact: true });
  const preset = panel.getByRole('combobox', { name: 'Pose', exact: true });
  // ONE panel, whose first row is the named pose — a label beside its dropdown — then the joint.
  // The pose and the joints are no sections of their own.
  await assertPairedRow(panel, 'Pose', preset);
  for (const heading of ['Pose', 'Joints', 'Kinematics']) {
    assert.equal(await panel.getByRole('heading', { name: heading, exact: true }).count(), 0, `no ${heading} heading inside Position`);
  }
  // Sized like the tree: its content's height, capped at half the stack, with its corner grip.
  const positionFit = await panel.evaluate(node => ({ cap: node.style.maxHeight, stack: node.closest('[data-cad-tool-stack]').clientHeight,
    scrolls: node.querySelector('[data-tool-panel-body]').scrollHeight > node.querySelector('[data-tool-panel-body]').clientHeight }));
  assert.equal(positionFit.cap, `${Math.round(positionFit.stack / 2)}px`);
  assert.equal(positionFit.scrolls, false);
  assert.equal(await pane.getByRole('separator', { name: 'Resize position controls', exact: true }).count(), 1);
  // A compact value field: 24px tall and about five characters wide.
  const field = await slider.boundingBox();
  assert.ok(field.height <= 24 && field.width <= 60, `a compact value field: ${JSON.stringify(field)}`);
  assert.equal((await preset.innerText()).trim(), 'Default');
  assert.equal(await slider.inputValue(), '0.00°');

  await page.mouse.move(view.box.x + view.box.width - 20, view.box.y + view.box.height - 20);
  const rest = await restingFrame(view);
  const restArm = (await translations(page))['o1.2'];
  await slider.fill('60');
  await slider.press('Enter');
  await page.waitForFunction(() => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13]) > 1);
  // The DRAWN frame moved, not just the matrix: a pose that never asks for a
  // repaint leaves the viewport sitting on the picture before it.
  const posed = await frameWhen(view, shot => differing(rest, shot) > 10_000, 'repainted for the mate the slider drove');

  // The grid runs out past the model and is sized from the REST pose, so
  // swinging the arm cannot rescale it. (The Render studio's floor is held to
  // the same rule at the end of this test, where a mode change cannot disturb
  // the frames compared here.)
  const guides = { x0: 0, x1: Math.floor(rest.width * 0.08) };
  assert.ok(painted(rest, guides) > 500, `the compared strip holds grid lines: ${painted(rest, guides)}`);
  assert.equal(differing(rest, posed, guides), 0, 'the guides beside the model are untouched by a pose');

  // A named pose is a full configuration, applied as a jump.
  await preset.click();
  await page.getByRole('option', { name: 'open', exact: true }).click();
  await page.waitForFunction(() => /^90(\.0+)?°$/.test(document.querySelector('input[aria-label="hinge slider value"]').value));
  assert.equal((await preset.innerText()).trim(), 'open');
  await panel.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.waitForFunction(() => /^0(\.0+)?°$/.test(document.querySelector('input[aria-label="hinge slider value"]').value));
  await page.waitForFunction(rest => JSON.stringify(Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix.slice(12, 15))) === JSON.stringify(rest), restArm)
    .catch(() => {});
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'Reset puts the mate back where it started');
  await page.mouse.move(view.box.x + view.box.width - 20, view.box.y + view.box.height - 20);
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
  await frameWhen(view, shot => differing(rest, shot) > 10_000, 'showed the pose the knob dragged to');
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
  await page.waitForFunction(() => /^0(\.0+)?°$/.test(document.querySelector('input[aria-label="hinge slider value"]').value));
  const restStage = await studioFloor();
  const boxShift = Math.max(...[0, 1, 2].flatMap(axis => [
    Math.abs(posedStage.bounds.min[axis] - restStage.bounds.min[axis]), Math.abs(posedStage.bounds.max[axis] - restStage.bounds.max[axis])]));
  assert.ok(boxShift > 1, `the studio was built against a posed box that differs from rest: ${JSON.stringify({ posed: posedStage.bounds, rest: restStage.bounds })}`);
  assert.deepEqual(posedStage.studioGround, restStage.studioGround, 'a pose never resizes or slides the studio floor');
  assert.deepEqual(errors, []);
});

test('preview opens paused, its playbar plays and pauses the routine without moving the camera or the floor, and leaving restores the pose and the camera', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  // A camera of the person's own, which preview's must never overwrite.
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ ...window.cadHarness.a.controller.readState().camera, zoom: 1.6, target: [4, 5, 2] }));
  await restingCamera(page);
  const saved = (await view.state()).camera;
  // The pointer rests on the backdrop: zoomed in, the model runs under the bottom-left corner.
  const away = () => page.mouse.move(view.box.x + view.box.width - 20, view.box.y + 100);
  await away();
  const toolsRest = await restingFrame(view);
  const restArm = (await translations(page))['o1.2'];
  // Under Select the tools view carries nothing of the routine's: no transport.
  assert.equal(await pane.locator('[data-animation-transport]').count(), 0);
  const boxes = names => Promise.all(names.map(name => pane.getByRole('button', { name, exact: true }).boundingBox()));
  const viewControls = await boxes(['Display', 'Preview']);
  await view.enterPreview();
  // Preview has the page to itself: the navbar goes, and its corner holds Orbit, then Display and the
  // way out exactly where Display and Preview sat in the navbar.
  await pane.locator('[data-viewer-navbar]').waitFor({ state: 'detached' });
  const [orbitBox, ...cornerBoxes] = await boxes(['Orbit', 'Display', 'Exit preview']);
  assert.deepEqual(cornerBoxes, viewControls);
  assert.ok(orbitBox.y === viewControls[0].y && orbitBox.x + orbitBox.width < viewControls[0].x, 'Orbit sits just before Display');
  // The tools are put away, and the playbar is under the model.
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).isVisible(), false);
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await bar.waitFor();
  // Autoplay is off by default: entered, the routine waits, at rest.
  await bar.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await page.waitForTimeout(300);
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'nothing plays until its play button is pressed');
  // Display is preview's too: its dropdown opens from the corner over the file's own settings, an
  // edit there draws in the preview, and Escape puts it away, preview kept.
  const edged = await restingFrame(view);
  await pane.locator('[data-preview-corner]').getByRole('button', { name: 'Display', exact: true }).click();
  await view.displayPanel().getByRole('button', { name: 'Disable Edges', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.edges?.enabled === false);
  await frameWhen(view, shot => differing(edged, shot) > 100, 'drew the preview without its edges');
  await page.keyboard.press('Escape');
  await view.displayPanel().waitFor({ state: 'detached' });
  assert.equal(await pane.getByRole('button', { name: 'Exit preview', exact: true }).isVisible(), true, 'Escape closes Display before preview');
  await view.display({ edges: { enabled: true } });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.edges?.enabled === true);
  const rest = await restingFrame(view);
  // Preview puts away prompt actions, leaving only playback controls: one routine has no list of
  // routines, and the routine's settings end the playbar. The view's own are the corner's.
  assert.deepEqual(await bar.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))), ['Play animation', 'Playback settings']);
  assert.deepEqual(await pane.locator('[data-preview-corner]').getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Orbit', 'Display', 'Exit preview']);
  assert.equal(await bar.getByRole('slider', { name: 'Animation time', exact: true }).count(), 1);
  assert.equal(await pane.getByRole('button', { name: 'Quick Edit' }).count(), 0);

  await bar.getByRole('button', { name: 'Play animation' }).click();
  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  await frameWhen(view, shot => differing(rest, shot) > 10_000, 'showed the playing routine');
  await bar.getByRole('button', { name: 'Pause animation' }).click();
  assert.equal(await bar.getByRole('button', { name: 'Play animation', exact: true }).isVisible(), true);
  await bar.getByRole('button', { name: 'Play animation' }).click();
  assert.equal(await bar.getByRole('button', { name: 'Pause animation', exact: true }).isVisible(), true);
  // A drag in preview turns preview's camera alone.
  const orbit = await page.evaluate(() => window.__cadCamera().position);
  await page.mouse.move(view.box.x + view.box.width / 2, view.box.y + view.box.height / 2);
  await page.mouse.down();
  await page.mouse.move(view.box.x + view.box.width / 2 + 90, view.box.y + view.box.height / 2 + 20, { steps: 5 });
  await page.mouse.up();
  await page.waitForFunction(previous => window.__cadCamera().position.some((value, index) => Math.abs(value - previous[index]) > 1e-3), orbit);

  // Leaving preview releases the routine, playing or not: the model goes back to the pose it
  // was in, in the tools view's own camera, to the pixel.
  await view.exitPreview();
  await bar.waitFor({ state: 'detached' });
  await page.waitForFunction(rest => JSON.stringify(Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix.slice(12, 15))) === JSON.stringify(rest), restArm)
    .catch(() => {});
  assert.deepEqual((await translations(page))['o1.2'], restArm);
  const restored = (await view.state()).camera;
  for (const key of ['position', 'target', 'up']) saved[key].forEach((value, index) => assert.ok(Math.abs(value - restored[key][index]) < 1e-6, `the tools view's camera comes back: ${key}`));
  assert.equal(restored.zoom, saved.zoom);
  await away();
  await frameWhen(view, shot => differing(toolsRest, shot) === 0, 'came back to the rest pose exactly');

  // Under Render, which stands the model on a studio floor: the routine moves the model, never
  // the camera or the floor under it.
  await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true));
  await view.enterPreview();
  await page.waitForFunction(() => window.__cadStage()?.studioGround, null, { timeout: 10000 });
  await restingCamera(page);
  const still = await page.evaluate(() => ({ camera: window.__cadCamera(), stage: window.__cadStage() }));
  await bar.getByRole('button', { name: 'Play animation' }).click();
  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  const playing = await page.evaluate(() => ({ camera: window.__cadCamera(), stage: window.__cadStage() }));
  for (const key of ['position', 'target', 'zoom']) {
    const actual = [].concat(playing.camera[key]), expected = [].concat(still.camera[key]);
    assert.ok(actual.every((value, index) => Math.abs(value - expected[index]) < 1e-8), `the routine never moves the camera: ${key}`);
  }
  assert.deepEqual(playing.stage.studioGround, still.stage.studioGround, 'nor the studio floor');
  await view.exitPreview();
  assert.deepEqual(errors, []);
});

test('preview and the tools view are two states: preview draws the model as authored, and leaving it drops what was done there and gives the tools view back as it was', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const away = () => page.mouse.move(view.box.x + view.box.width - 20, view.box.y + 100);
  const arm = async () => (await translations(page))['o1.2'];
  const armAt = expected => page.waitForFunction(at => JSON.stringify(Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix.slice(12, 15))) === JSON.stringify(at), expected)
    .catch(() => {});
  const restArm = await arm();
  // The model as preview draws a file opened afresh: the picture every later preview draws too,
  // whatever the tools view holds.
  await away();
  await view.enterPreview();
  const authored = await restingFrame(view);
  await view.exitPreview();

  // Work in the tools view: the arm swung on Position, the base hidden, the arm picked, the model
  // clipped, and a camera of the person's own.
  await view.tool('Position').click();
  const slider = page.getByLabel('hinge slider value', { exact: true });
  await slider.fill('60');
  await slider.press('Enter');
  await page.waitForFunction(() => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13]) > 1);
  const posedArm = await arm();
  await view.tool('Select').click();
  await pane.getByRole('button', { name: 'Hide base', exact: true }).click();
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click();
  await view.display({ clip: { enabled: true, axis: 'z', offsets: { x: 1, y: 1, z: 0.5 }, invert: false } });
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ ...window.cadHarness.a.controller.readState().camera, zoom: 1.4, target: [3, 4, 2] }));
  await page.waitForFunction(() => {
    const state = window.cadHarness.a.controller.readState();
    return state.hiddenPartIds.join() === 'o1.1' && state.selectedPartIds.join() === 'o1.2' && state.display.clip?.enabled === true;
  });
  await restingCamera(page);
  const work = await view.state();

  // Preview draws none of it: the arm at rest, the base there, nothing picked or cut away.
  await away();
  await view.enterPreview();
  await armAt(restArm);
  assert.deepEqual(await arm(), restArm, 'preview poses the model at rest');
  const shown = await frameWhen(view, shot => differing(authored, shot) === 0, 'drew the model as authored');
  assert.ok(partBoxes(shown).base && partBoxes(shown).arm, 'both parts are drawn');

  // What is done in preview is preview's: its routine played, its camera turned.
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await bar.getByRole('button', { name: 'Play animation' }).click();
  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  const orbit = await page.evaluate(() => window.__cadCamera().position);
  await page.mouse.move(view.box.x + view.box.width / 2, view.box.y + view.box.height / 2);
  await page.mouse.down();
  await page.mouse.move(view.box.x + view.box.width / 2 + 90, view.box.y + view.box.height / 2 + 20, { steps: 5 });
  await page.mouse.up();
  await page.waitForFunction(previous => window.__cadCamera().position.some((value, index) => Math.abs(value - previous[index]) > 1e-3), orbit);

  // Leaving drops it, and gives the tools view back as it was left: the pose, the hidden base, the
  // pick, the clip and its camera.
  await view.exitPreview();
  await armAt(posedArm);
  assert.deepEqual(await arm(), posedArm, 'the pose comes back');
  const back = await view.state();
  assert.deepEqual([back.hiddenPartIds, back.selectedPartIds, back.display.clip], [work.hiddenPartIds, work.selectedPartIds, work.display.clip]);
  for (const key of ['position', 'target', 'up']) work.camera[key].forEach((value, index) => assert.ok(Math.abs(value - back.camera[key][index]) < 1e-6, `the tools view's camera comes back: ${key}`));
  assert.equal(back.camera.zoom, work.camera.zoom);
  await view.tool('Position').click();
  assert.match(await slider.inputValue(), /^60(\.0+)?°$/);

  // An isolated part is the tools view's too: preview draws the whole model, and leaving finds the part isolated.
  await view.tool('Select').click();
  await pane.getByRole('button', { name: 'Reveal base', exact: true }).click();
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Isolate', exact: true }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.2');
  await away();
  await view.enterPreview();
  await frameWhen(view, shot => differing(authored, shot) === 0, 'drew the whole model, as authored');
  await view.exitPreview();
  assert.deepEqual((await view.state()).isolatedPartIds, ['o1.2']);
  assert.deepEqual(errors, []);
});

test('the Animation tool plays the routine in the tools view, preview leaves its routine as it was, and putting the tool down puts the model back at rest', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const arm = () => page.evaluate(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix);
  const restArm = (await translations(page))['o1.2'];
  // Its panel leads the stack, headed as Measure's is: Animation, its settings and its X, over the
  // transport, with no Routine row for the one routine.
  await view.tool('Animation').click();
  const panel = pane.getByRole('region', { name: 'Animation controls', exact: true });
  assert.deepEqual(await view.stack(), ['Animation controls']);
  assert.deepEqual(await panel.getByRole('heading').allInnerTexts(), ['Animation']);
  assert.deepEqual(await panel.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Animation settings', 'Close animation controls', 'Play animation']);
  assert.equal(await panel.getByRole('combobox', { name: 'Routine' }).count(), 0);
  assert.equal(Math.round((await panel.boundingBox()).width), 164, 'one width, as every fixed panel');
  // Its 24px row flush under the heading, the play glyph's ink on the title's line, the scrubber 8px
  // in from the right and the row 4px off the foot (the panel's 1px border on top of each).
  const play = panel.getByRole('button', { name: 'Play animation' });
  const [panelBox, titleBox, glyphBox, playBox, trackBox] = await Promise.all([panel.boundingBox(), panel.getByRole('heading').boundingBox(),
    play.locator('svg > *').first().boundingBox(), play.boundingBox(), panel.locator('[data-slot=slider-track]').boundingBox()]);
  assert.ok(Math.abs(glyphBox.x - titleBox.x) <= 1, `the play glyph sits under the title: ${glyphBox.x - panelBox.x} vs ${titleBox.x - panelBox.x}`);
  assert.deepEqual([playBox.y - panelBox.y, playBox.height, panelBox.x + panelBox.width - trackBox.x - trackBox.width,
    panelBox.y + panelBox.height - playBox.y - playBox.height].map(Math.round), [29, 24, 9, 5]);
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'taken up, the model waits at rest: Autoplay is off');

  await panel.getByRole('button', { name: 'Play animation' }).click();
  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  await panel.getByRole('button', { name: 'Pause animation' }).click();
  await panel.getByRole('button', { name: 'Play animation' }).waitFor();
  const paused = await translations(page);
  // Preview's routine is its own: it opens at rest and waits (Autoplay is off), whatever the tool's is doing.
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  const atRest = () => page.waitForFunction(rest => JSON.stringify(Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix.slice(12, 15))) === JSON.stringify(rest), restArm)
    .catch(() => {});
  await view.enterPreview();
  await bar.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await atRest();
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'preview opens on the model at rest');
  // Leaving hands the tool's routine back where it was: paused mid-way...
  await view.exitPreview();
  await panel.getByRole('button', { name: 'Play animation' }).waitFor();
  await page.waitForFunction(at => JSON.stringify(Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix.slice(12, 15))) === JSON.stringify(at), paused['o1.2'])
    .catch(() => {});
  assert.deepEqual(await translations(page), paused);
  // ...or playing, once it plays.
  await panel.getByRole('button', { name: 'Play animation' }).click();
  await view.enterPreview();
  await bar.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await atRest();
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'preview opens at rest while the tool plays');
  await view.exitPreview();
  await panel.getByRole('button', { name: 'Pause animation' }).waitFor();
  const playing = (await arm())[1];
  await page.waitForFunction(previous => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] !== previous, playing);

  // A second press puts it down: the routine stops and the model is at rest, back in Select.
  await view.tool('Animation').click();
  assert.deepEqual(await view.stack(), ['Features']);
  await page.waitForFunction(rest => JSON.stringify(Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix.slice(12, 15))) === JSON.stringify(rest), restArm)
    .catch(() => {});
  assert.deepEqual((await translations(page))['o1.2'], restArm);

  // Autoplay, ticked in its settings, starts the routine whenever the tool is taken up.
  await view.tool('Animation').click();
  await panel.getByRole('button', { name: 'Animation settings' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'Autoplay', exact: true }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('menu', { name: 'Animation settings' }).waitFor({ state: 'detached' });
  // Its X puts it down as the second press does.
  await panel.getByRole('button', { name: 'Close animation controls' }).click();
  assert.deepEqual(await view.stack(), ['Features']);
  await view.tool('Animation').click();
  await panel.getByRole('button', { name: 'Pause animation' }).waitFor();
  assert.deepEqual(errors, []);
});

test('preview\'s Speed and Loop are its own, forgotten on the way out, while Orbit is the file\'s in both', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  const toolSettings = pane.getByRole('region', { name: 'Animation controls', exact: true }).getByRole('button', { name: 'Animation settings' });
  const previewSettings = pane.getByRole('toolbar', { name: 'Animation playback' }).getByRole('button', { name: 'Playback settings' });
  // A menu's Speed and Loop, as it shows them.
  const settings = async (button, name) => {
    await button.click();
    const menu = page.getByRole('menu', { name, exact: true });
    const read = [await menu.getByRole('menuitem', { name: /^Animation speed: / }).getAttribute('aria-label'),
      await menu.getByRole('menuitemcheckbox', { name: 'Loop', exact: true }).getAttribute('aria-checked')];
    await page.keyboard.press('Escape');
    await menu.waitFor({ state: 'detached' });
    return read;
  };
  // Chooses a Speed, and turns Loop over. By keyboard: a menu item still easing in under a loaded
  // software renderer never reads as stable under the pointer.
  const choose = async (button, name, speed) => {
    await button.click();
    await page.getByRole('menu', { name, exact: true }).getByRole('menuitem', { name: /^Animation speed: / }).click();
    await page.getByRole('menuitemradio', { name: `${speed}×`, exact: true }).press('Enter');
    await page.getByRole('menu', { name, exact: true }).waitFor({ state: 'detached' });
    await button.click();
    await page.getByRole('menu', { name, exact: true }).getByRole('menuitemcheckbox', { name: 'Loop', exact: true }).press('Enter');
    await page.keyboard.press('Escape');
    await page.getByRole('menu', { name, exact: true }).waitFor({ state: 'detached' });
  };
  // The tools view's own: the Animation tool at 2×, its routine not looping.
  await view.tool('Animation').click();
  assert.deepEqual(await settings(toolSettings, 'Animation settings'), ['Animation speed: 1×', 'true'], 'the routine\'s own Speed and Loop');
  await choose(toolSettings, 'Animation settings', 2);
  assert.deepEqual(await settings(toolSettings, 'Animation settings'), ['Animation speed: 2×', 'false']);

  // Preview opens on the routine's own, never the tools view's; what is chosen there is preview's.
  await view.enterPreview();
  assert.deepEqual(await settings(previewSettings, 'Playback settings'), ['Animation speed: 1×', 'true'], 'preview opens at the routine\'s own Speed and Loop');
  await choose(previewSettings, 'Playback settings', 0.5);
  assert.deepEqual(await settings(previewSettings, 'Playback settings'), ['Animation speed: 0.5×', 'false']);
  // Orbit is the file's: off (as this file's view was left) it stays off; on, it stays on.
  const corner = pane.locator('[data-preview-corner]');
  const orbit = () => page.getByRole('menu', { name: 'Orbit', exact: true }).getByRole('menuitemcheckbox', { name: 'Orbit', exact: true });
  const orbitChecked = async () => {
    await corner.getByRole('button', { name: 'Orbit', exact: true }).click();
    const checked = await orbit().getAttribute('aria-checked');
    await page.keyboard.press('Escape');
    await page.getByRole('menu', { name: 'Orbit', exact: true }).waitFor({ state: 'detached' });
    return checked;
  };
  assert.equal(await orbitChecked(), 'false');
  await view.exitPreview();

  // The tools view's settings are as it left them, and preview's are gone.
  assert.deepEqual(await settings(toolSettings, 'Animation settings'), ['Animation speed: 2×', 'false'], 'preview never writes the tools view\'s');
  await view.enterPreview();
  assert.deepEqual(await settings(previewSettings, 'Playback settings'), ['Animation speed: 1×', 'true'], 'preview forgot its own');
  assert.equal(await orbitChecked(), 'false', 'Orbit off stays off');
  const still = await page.evaluate(() => window.__cadCamera().position);
  await corner.getByRole('button', { name: 'Orbit', exact: true }).click();
  await orbit().press('Enter');
  await page.keyboard.press('Escape');
  await page.waitForFunction(start => window.__cadCamera().position.some((value, axis) => Math.abs(value - start[axis]) > 1e-6), still);
  await view.exitPreview();
  await view.enterPreview();
  assert.equal(await orbitChecked(), 'true', 'and on stays on');
  await view.exitPreview();
  assert.deepEqual(errors, []);
});

test('a pose pass React re-runs while a routine plays draws the clock, never the time playback started from', async () => {
  // The pose pass has two callers: the clock per playing tick, and React whenever something the
  // pass reads changes (a detail swap, a progressive publish, a display change). React's copy of
  // the time is where playback STARTED, so a re-run mid-play used to put the model back there for
  // a frame: on a routine that starts at rest, a flash of the rest pose on every re-run.
  const view = await open();
  const { page, pane, errors } = view;
  await view.enterPreview();
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await bar.getByRole('button', { name: 'Play animation' }).click();
  await page.waitForFunction(() => window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[1] > 0.2);
  // Hold the clock where it is: animation frames are queued, not run, so no tick can repaint the
  // pose over whatever React's pass draws. The pass itself is not a frame: a display change
  // reaches it through a task (`afterViewPaint`'s fallback), with frames held.
  const [ticked, rerun] = await page.evaluate(async () => {
    const arm = () => Array.from(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix);
    window.__heldFrames = [];
    window.__releaseFrames = window.requestAnimationFrame;
    window.requestAnimationFrame = callback => { window.__heldFrames.push(callback); return 0; };
    // The tick already queued through the real rAF still runs, in the next frame, and it poses
    // the model synchronously. Wait for that frame, not for a time: on a software-WebGL runner it
    // can land after any fixed wait, and then its tick moves the arm mid-test. A callback asked
    // of the real rAF now runs in that same frame, after the tick; the tick's own next request is
    // held.
    await new Promise(resolve => window.__releaseFrames.call(window, resolve));
    const beforeRerun = arm();
    const edges = window.cadHarness.a.controller.readState().display.edges?.enabled !== false;
    window.cadHarness.a.controller.setDisplaySettings({ edges: { enabled: !edges } });
    await new Promise(resolve => setTimeout(resolve, 600));
    return [beforeRerun, arm()];
  });
  await page.evaluate(() => {
    window.requestAnimationFrame = window.__releaseFrames;
    for (const callback of window.__heldFrames.splice(0)) window.requestAnimationFrame(callback);
  });
  assert.ok(ticked[1] > 0.2, 'the routine had turned the arm away from its start');
  ticked.forEach((value, index) => assert.ok(Math.abs(value - rerun[index]) < 1e-9,
    `React's pass drew the routine where the clock is, not where it started: ${ticked} != ${rerun}`));
  await view.exitPreview();
  assert.deepEqual(errors, []);
});

test('Measure reads a distance between two picks', async () => {
  const view = await open();
  const { page, pane, at, errors } = view;
  // Measure snaps onto exact topology, which arrives with the tree's frontier.
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  await pane.getByRole('button', { name: 'Expand arm', exact: true }).click();
  await view.tool('Measure').click();
  // Its panel is up as soon as it is the tool, empty but for a hint.
  const measurePanel = pane.getByRole('region', { name: 'Measure controls', exact: true });
  await measurePanel.waitFor();
  assert.equal((await measurePanel.locator('[data-measure-hint]').innerText()).trim(), 'Pick two points to measure');
  // Measure says what the pointer does over the model: a crosshair, not Select's hand.
  await page.mouse.move(...at([0, 0, 5]));
  await view.waitCursor('crosshair');
  const measurements = page.getByRole('region', { name: 'Measurements' });
  assert.equal(await measurements.count(), 0, 'no results until something is measured');
  await measurePoints(page, at, [0, 0, 5], [15, 0, 4]);
  await measurements.waitFor();
  assert.match(await measurements.innerText(), /\d+\.\d+ mm/, 'the row reads a length');
  assert.equal(await measurements.getByRole('listitem').count(), 1, 'one ruler');
  assert.equal(await measurePanel.locator('[data-measure-hint]').count(), 0, 'the hint gives way to the results');
  assert.deepEqual(errors, []);
});

// A STEP is published in PIECES, and each piece lands in a scene the viewport already
// holds: same object, same identity, more in it. The only thing that tells the viewport
// so is `viewport.commitScene()` from the scene sync, and what the viewport sizes from what
// is PLACED — the depth range and the floor's height — is re-read THEN. What it sizes from
// the model's REST box — the framing, the zoom ruler and the grid — was final at the first
// publish: the descriptor declares the whole model's box (`bbox`), so the camera does not
// move while the rest of the model arrives (the owner's report: "the model position jumps
// around a bit as it is rendering").
//
// The committed two-component fixture cannot show this, and neither can any package
// whose second publish is its LAST: the end of a load changes what the viewport is
// mounted with, so it re-adopts the scene for reasons of its own and a deleted commit
// costs nothing. `stageProgressiveFixture` serves the same two shapes as twenty-five
// components, held one batch at a time, so the MIDDLE publish is an in-place change
// with nothing else moving — and it is the one that brings the base.
test('a package that arrives in pieces is framed once, on the box it declares; a publish in the middle of the load re-fits only its depth range and floor', async (t) => {
  const staged = [];
  const staggered = await serveStepHarness({ after: cleanup => staged.push(cleanup) }, { progressive: true });
  t.after(async () => { for (const cleanup of staged.reverse()) await cleanup(); });
  const { page, errors, pane } = await staggered.open({ timeout: 60000 });
  await pane.locator('[aria-busy] > div > canvas').first().waitFor();
  const read = async () => ({ stage: await page.evaluate(() => window.__cadStage()), camera: await page.evaluate(() => window.__cadCamera()) });
  const span = bounds => [0, 1, 2].map(axis => Math.round(bounds.max[axis] - bounds.min[axis]));
  const publishes = () => page.evaluate(() => [window.__cadMeshCost.publishCount, window.__cadMeshCost.loadedComponents, window.__cadMeshCost.final]);
  // The view a publish must not move: where the camera stands and looks, its zoom and frustum, and the grid.
  const sameView = (from, to, what) => {
    for (const key of ['position', 'target', 'up']) from.camera[key].forEach((value, index) => assert.ok(Math.abs(value - to.camera[key][index]) < 1e-6,
      `${what}: camera ${key}[${index}] held (${value} -> ${to.camera[key][index]})`));
    assert.deepEqual([to.camera.zoom, to.camera.halfHeight, to.stage.gridRadius], [from.camera.zoom, from.camera.halfHeight, from.stage.gridRadius],
      `${what}: the zoom, the frustum and the grid held`);
  };

  // BATCH ONE: eight arms, all at the origin, so what is placed is one arm's box whichever
  // eight of them got there first. The rest of the package is still downloading.
  await page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 8, null, { timeout: 60000 });
  // ...as cadgen holds a part it is still meshing: pending, which holds no request open. A held
  // response would take one of the browser's six connections to the host, the loader's lanes
  // (up to eight) could fill them all, and an unheld component queued behind them would never land.
  await staggered.idle();
  await page.waitForFunction(() => window.__cadStage?.()?.bounds);
  await restingCamera(page);
  const first = await read();
  const firstFrame = await frame(pane);
  assert.deepEqual(await publishes(), [1, 8, false], 'one publish, and the load is not over');
  assert.deepEqual(span(first.stage.bounds), [10, 8, 8], 'the arm, and nothing else, is placed');
  assert.deepEqual(span(first.camera.originalBounds), [20, 20, 10], "but the camera is framed on the whole model's declared box");

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
  assert.ok(middle.stage.floorZ < first.stage.floorZ,
    `the floor dropped to the model's new underside (${first.stage.floorZ} -> ${middle.stage.floorZ})`);
  assert.ok(middle.camera.far > first.camera.far,
    `the depth range was fitted again (far ${first.camera.far} -> ${middle.camera.far})`);
  sameView(first, middle, 'the second publish');
  // On the DRAWN frame: the base's own authored blue fills a frame it was not in.
  const before = partBoxes(firstFrame), after = partBoxes(middleFrame);
  assert.ok(after.base.count > (before.base?.count || 0) * 5,
    `the base is drawn (${before.base?.count || 0} -> ${after.base.count} pixels of its colour)`);
  assert.ok(differing(firstFrame, middleFrame) > 10_000, 'the picture changed');

  // THE LAST COMPONENT is one more arm on top of the others: the scene is whole, and the
  // camera that framed it whole from the start has nothing to do.
  staggered.release('b');
  await page.waitForFunction(() => window.__cadMeshCost?.final === true, null, { timeout: 60000 });
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false, null, { timeout: 60000 });
  await restingCamera(page);
  const whole = await read();
  assert.deepEqual(span(whole.stage.bounds), span(middle.stage.bounds), 'the box it was already fitted to');
  sameView(first, whole, 'the last publish');

  // A descriptor that declares no box is framed on its first batch and once more when it is
  // whole, but that second framing is for a camera NOBODY set: the camera the person set, kept
  // with the tab, is restored through every publish and the completion.
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({
    ...window.cadHarness.a.controller.readState().camera, position: [90, -30, 38], target: [4, 1, 0], zoom: 1.6 }));
  await restingCamera(page);
  const chosen = await page.evaluate(() => window.__cadCamera());
  const chosenFrame = await restingFrame({ page, frame: () => frame(pane) });
  assert.ok(chosen.position.some((value, index) => Math.abs(value - whole.camera.position[index]) > 1),
    'the camera the person set is somewhere the fit never puts it');
  const stored = await page.evaluate(() => JSON.parse(JSON.stringify(window.cadHarness.tabStore.getSnapshot())));

  // Reopened: a fresh page over the same package with no declared box, held in pieces again,
  // carrying what the last session left for this file. (A remount would not do: the client still
  // holds every component it downloaded, so the package would arrive whole in ONE publish and
  // never reach completion as a second framing at all.)
  staggered.hold('a'); staggered.hold('b'); staggered.declare(false);
  const reopened = await staggered.open({ timeout: 60000, record: stored });
  await reopened.pane.locator('[aria-busy] > div > canvas').first().waitFor();
  await reopened.page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 8, null, { timeout: 60000 });
  staggered.release('a');
  await reopened.page.waitForFunction(() => window.__cadMeshCost?.loadedComponents === 24, null, { timeout: 60000 });
  staggered.release('b');
  await reopened.page.waitForFunction(() => window.__cadMeshCost?.final === true, null, { timeout: 60000 });
  await reopened.page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false, null, { timeout: 60000 });
  await restingCamera(reopened.page);
  assert.deepEqual(await reopened.page.evaluate(() => [window.__cadMeshCost.publishCount, window.__cadMeshCost.final]),
    [3, true], 'it arrived in three publishes again, so completion really did reframe');
  const kept = await reopened.page.evaluate(() => window.__cadCamera());
  for (const key of ['position', 'target']) {
    chosen[key].forEach((value, index) => assert.ok(Math.abs(value - kept[key][index]) < 1e-6,
      `${key}[${index}] is the camera the person set, through every publish and the completion`));
  }
  // The picture settles a frame or two after the camera does (level of detail refines on a slow
  // renderer), so it is read until it matches, and a picture that never does still fails.
  let left = Infinity;
  for (let attempt = 0; attempt < 16 && left >= 250; attempt += 1) {
    left = differing(chosenFrame, await frame(reopened.pane));
    if (left >= 250) await reopened.page.waitForTimeout(250);
  }
  assert.ok(left < 250, `reopening shows what the person left on screen: ${left} pixels differ`);
  assert.deepEqual(reopened.errors, []);
  assert.deepEqual(errors, []);
});

// A warm package's open, request by request: where each component probed the shared cache and
// read its body alone (twenty-five of each here), a chunk of components shares a probe and a
// batch of them one read, growing from the loader's first publish of eight.
test('a warm package opens with a probe per chunk and its bodies in batches, and nothing read one component at a time', async (t) => {
  const staged = [];
  const warm = await serveStepHarness({ after: cleanup => staged.push(cleanup) }, { progressive: true, warmCache: true });
  t.after(async () => { for (const cleanup of staged.reverse()) await cleanup(); });
  warm.release('a'); warm.release('b');
  const { page, errors } = await warm.open();
  await page.waitForFunction(() => window.__cadMeshCost?.final === true && window.__cadMeshCost.loadedComponents === 25);
  const sent = pattern => warm.requests.filter(request => pattern.test(request)).length;
  assert.equal(sent(/^POST \/one\/__tess_cache\/probe$/), 3, 'a probe for each chunk: eight, sixteen and the last one');
  assert.equal(sent(/^POST \/one\/__tess_cache\/batch$/), 3, 'a read for each batch: eight, sixteen and the last one');
  assert.equal(sent(/^GET \/one\/__tess_cache\//), 0, 'no body read alone');
  assert.equal(sent(/\/__cad\/surfaces/), 0, 'no surface resolved');
  assert.equal(sent(/^GET \/one\/__cad\/store\?tree=/), 0, 'no surface read');
  assert.deepEqual(errors, []);
});

test('mobile touch: a tap selects, and a two-finger pinch zooms without selecting', async () => {
  const view = await open({ hasTouch: true, timeout: 10000 });
  const { page, pane, errors } = view;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.querySelector('[data-viewer-layout]')?.dataset.viewerLayout === 'mobile');
  // The camera takes the phone canvas's shape: points are projected from where it comes to rest.
  await page.waitForFunction(() => {
    const box = document.querySelector('[data-testid="one"] [data-cad-scene-backdrop]').getBoundingClientRect();
    return Math.abs(window.__cadCamera().aspect - box.width / box.height) < 0.01;
  });
  await restingCamera(page);
  await settle(page);
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
  const sceneBox = await pane.locator('[data-cad-scene-backdrop]').boundingBox();
  const project = projector(await page.evaluate(() => window.__cadCamera()), sceneBox);
  // A tap on a part picks it, with no hover before it.
  await page.touchscreen.tap(...project([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);

  // Two fingers that land on the model pinch: the camera zooms, and neither finger is a pick.
  const pinchBefore = (await view.state()).camera;
  const [x, y] = project([6, 6, 5]);
  await gesture([[[x - 50, y], [x + 50, y]], [[x - 80, y], [x + 80, y]], [[x - 90, y], [x + 90, y]]]);
  await page.waitForFunction(zoom => window.cadHarness.a.controller.readState().camera.zoom !== zoom, pinchBefore.zoom);
  // A tap's pick lands in the render its touch causes; two frames on, a pick would be there.
  await settle(page);
  assert.deepEqual([(await view.state()).selectedPartIds, (await view.state()).selectedReferenceIds], [[], []], 'pinching never selects geometry');
  assert.deepEqual(errors, []);
});

test('a click selects at once, and a double-click ends where it did when a click waited: the part isolated, isolation left, or the face copied and kept, on the selection its first click found', async () => {
  // Files are named by their absolute paths, and every copy says so.
  const view = await open({ init: () => { window.__cadPromptDestination = 'clipboard'; } });
  const { page, box, at, errors } = view;
  const selection = () => page.evaluate(() => { const state = window.cadHarness.a.controller.readState();
    return { parts: state.selectedPartIds, refs: state.selectedReferenceIds, isolated: state.isolatedPartIds }; });
  const cleared = () => page.waitForFunction(() => { const state = window.cadHarness.a.controller.readState();
    return state.selectedPartIds.length + state.selectedReferenceIds.length === 0; });
  const copies = () => page.evaluate(() => window.__clipboardWrites.length);
  // Empty space: the bottom-right, the one corner with nothing of the viewer's own in it.
  const empty = [box.x + box.width - 30, box.y + box.height - 30];
  const opening = (await view.state()).camera;
  await page.evaluate(() => {
    window.__clipboardWrites = [];
    window.cadHarness.a.host.clipboard.writeText = async text => { window.__clipboardWrites.push(text); };
    // A probe timer set at the press, ahead of the viewer's own handlers: it fires before any wait
    // the viewer could start there (the double-click window was 220 ms), however slow the frames.
    window.__selectedByProbe = null;
    document.addEventListener('pointerup', () => {
      window.__selectedByProbe = null;
      setTimeout(() => { window.__selectedByProbe = window.cadHarness.a.controller.readState().selectedPartIds.length > 0; }, 200);
    }, true);
  });
  // A click's selection does not wait to tell it from a double-click.
  await page.mouse.click(...at([15, 0, 4]));
  await page.waitForFunction(() => window.__selectedByProbe !== null);
  assert.equal(await page.evaluate(() => window.__selectedByProbe), true, 'the arm is selected before any double-click window could close');
  assert.deepEqual(await selection(), { parts: ['o1.2'], refs: [], isolated: [] });
  // The Reference panel's Copy, at its foot: the selection's reference.
  await view.pane.getByRole('region', { name: 'Reference details', exact: true }).getByRole('button', { name: 'Copy', exact: true }).click();
  await page.waitForFunction(() => window.__clipboardWrites.length === 1);
  assert.equal(await page.evaluate(() => window.__clipboardWrites[0]), '/models/hinge_block.step#o1.2');
  await page.evaluate(() => { window.__clipboardWrites = []; });

  // A double-click on the base isolates it. Its first click picked the base; the double-click
  // put the arm back before isolating — and isolating clears the selection, as it always has.
  await page.mouse.dblclick(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.1');
  await settle(page);
  assert.deepEqual(await selection(), { parts: [], refs: [], isolated: ['o1.1'] });
  assert.equal(await copies(), 0, 'a part double-click copies nothing');
  // Inside the isolation, the base picked (under Parts: the isolated part is open, so under All a
  // press there picks a face, which leaving isolation folds away): a double-click on empty space
  // leaves isolation with the base still selected. Its first click cleared the selection; the
  // double-click brought it back.
  await view.chooseSelectMode('Parts');
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  await page.mouse.dblclick(...empty);
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.length === 0);
  await settle(page);
  assert.deepEqual(await selection(), { parts: ['o1.1'], refs: [], isolated: [] }, 'leaving isolation keeps the part picked inside it');
  // Shift held through the double-click: a shift-click on empty space never clears, and the
  // double-click still leaves isolation with the selection as it was.
  await page.mouse.dblclick(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.1');
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  await page.keyboard.down('Shift');
  await page.mouse.dblclick(...empty);
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.length === 0);
  await settle(page);
  assert.deepEqual(await selection(), { parts: ['o1.1'], refs: [], isolated: [] });

  // Under Faces, with both parts' faces loaded (a press on each loads its part's faces and picks
  // one), a double-click copies the face and leaves it selected...
  await view.chooseSelectMode('Faces');
  for (const [point, part] of [[[15, 0, 4], 'o1.2'], [[6, 6, 5], 'o1.1']]) {
    await page.mouse.click(...at(point));
    await page.waitForFunction(id => new RegExp(`\\|${id.replace('.', '\\.')}\\.f\\d+$`).test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()), part);
  }
  await page.keyboard.press('Escape');
  await cleared();
  await page.mouse.dblclick(...at([15, 0, 4]));
  await page.waitForFunction(() => window.__clipboardWrites.length === 1);
  await settle(page);
  const armFace = (await selection()).refs;
  assert.equal(armFace.length, 1, `the double-clicked face is the selection: ${JSON.stringify(armFace)}`);
  assert.match(armFace[0], /\|o1\.2\.f\d+$/);
  assert.match(await page.evaluate(() => window.__clipboardWrites[0]), /^\/models\/hinge_block\.step#o1\.2\.f\d+$/);
  // ...also when it was selected already: the two clicks it is made of do not toggle it off.
  await page.mouse.dblclick(...at([15, 0, 4]));
  await page.waitForFunction(() => window.__clipboardWrites.length === 2);
  await settle(page);
  assert.deepEqual((await selection()).refs, armFace, 'a second double-click keeps the face selected');
  // With Shift, the double-clicked face joins the selection; a second shift double-click keeps it.
  await page.keyboard.down('Shift');
  await page.mouse.dblclick(...at([6, 6, 5]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.__clipboardWrites.length === 3);
  await settle(page);
  const both = (await selection()).refs;
  assert.equal(both.length, 2, `shift adds the double-clicked face: ${JSON.stringify(both)}`);
  assert.equal(both[0], armFace[0]);
  assert.match(both[1], /\|o1\.1\.f\d+$/);
  await page.keyboard.down('Shift');
  await page.mouse.dblclick(...at([6, 6, 5]));
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => window.__clipboardWrites.length === 4);
  await settle(page);
  assert.deepEqual((await selection()).refs, both, 'a shift double-click on a selected face keeps it');
  assert.deepEqual((await selection()).isolated, [], 'a topology double-click never isolates');
  // A double-click on empty space with no isolation to leave (as on a single-part STEP, whose
  // faces are what a press picks): its first click cleared the selection, and the double-click
  // puts the faces back, copying nothing.
  await page.mouse.dblclick(...empty);
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedReferenceIds.length === 2);
  await settle(page);
  assert.deepEqual((await selection()).refs, both, 'an empty-space double-click keeps the selection its first click found');
  assert.equal(await copies(), 4, 'and copies nothing');
  await view.pane.getByRole('region', { name: 'Reference details', exact: true }).getByRole('button', { name: 'Copy All', exact: true }).click();
  await page.waitForFunction(() => window.__clipboardWrites.length === 5);
  const copiedSelection = parseCadRefToken(await page.evaluate(() => window.__clipboardWrites[4]));
  assert.equal(copiedSelection.cadPath, '/models/hinge_block.step');
  assert.deepEqual([...copiedSelection.selectors].sort(), both.map(reference => reference.split('|').at(-1)).sort());

  // Hover is untouched: under Faces the face under the pointer lights, under Edges the edge does.
  await page.keyboard.press('Escape');
  await cleared();
  await page.mouse.move(...empty);
  const faces = await restingFrame(view);
  await page.mouse.move(...at([6, 6, 5]));
  await frameWhen(view, shot => differing(faces, shot) > 200, 'lit the hovered face');
  await page.mouse.move(...empty);
  // Let go: back to the unlit frame, give or take a software renderer's few pixels of noise
  // (the lit face changes hundreds).
  await frameWhen(view, shot => differing(faces, shot) <= 20, 'let go of the hovered face');
  await view.chooseSelectMode('Edges');
  await page.mouse.move(...empty);
  const edges = await restingFrame(view);
  await page.mouse.move(...at([10, 6, 5]));
  await frameWhen(view, shot => differing(edges, shot) > 10, 'lit the hovered edge');
  await page.mouse.move(...empty);
  await frameWhen(view, shot => differing(edges, shot) <= 2, 'let go of the hovered edge');

  // A drag orbits and selects nothing; a right-click opens the menu and selects nothing.
  await view.chooseSelectMode('All');
  await page.mouse.click(...at([15, 0, 4]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');
  const before = await selection();
  const camera = await page.evaluate(() => window.__cadCamera().position);
  const [x, y] = at([6, 6, 5]);
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 120, y + 40, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(previous => window.__cadCamera().position.some((value, index) => Math.abs(value - previous[index]) > 1e-3), camera);
  await settle(page);
  assert.deepEqual(await selection(), before, 'a drag is not a click');
  await page.mouse.click(x + 120, y + 40, { button: 'right' });
  await page.getByRole('menu').waitFor();
  await settle(page);
  assert.deepEqual(await selection(), before, 'a right-click is not a click');
  await page.keyboard.press('Escape');
  await page.getByRole('menu').waitFor({ state: 'detached' });

  // Under Explode, where a pick takes up Select, a double-click on a part isolates it and Explode
  // stays the tool: its first click waits out the double-click window, which the second cancels.
  // (On the opening camera, where `at` projects, and with nothing selected.)
  await page.evaluate(camera => { const controller = window.cadHarness.a.controller; controller.clearSelection(); return controller.setCamera(camera); }, opening);
  await restingCamera(page);
  await view.tool('Explode').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-toolbar] [aria-label="Explode"]')?.getAttribute('aria-pressed') === 'true');
  // The arm: the base's faces, loaded above, are what a press on the base picks now.
  await page.mouse.dblclick(...at([15, 0, 4]));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.2');
  // Past the window (220 ms) a first click that was not cancelled would have taken up Select.
  await page.waitForTimeout(400);
  await settle(page);
  assert.deepEqual((await view.tools()).filter(tool => tool.endsWith(':true')).map(tool => tool.split(':')[0]), ['Explode'], 'the tool stays Explode');
  assert.deepEqual(await selection(), { parts: [], refs: [], isolated: ['o1.2'] });
  assert.deepEqual(errors, []);
});

// ---- the tab ---------------------------------------------------------------------------------
// A page whose tab record is in its own sessionStorage (`?store=session`): a reload of the page is
// a reload of the tab, and a new page is a new tab.
test('a reload of the tab brings back the view — camera, Display, Clip, Explode, hidden and isolated parts, the tree and the pose — and starts afresh: Select, no selection, no measurement', async () => {
  const view = await open({ store: 'session' });
  const { page, pane, at, errors } = view;
  const rest = await translations(page);
  // The tree: expanded; the pose: posed, then Select again.
  await pane.getByRole('button', { name: 'Expand base', exact: true }).click();
  await view.tool('Position').click();
  const position = pane.locator('[data-tool-panel][aria-label="Position controls"]');
  const input = position.getByLabel('hinge slider value', { exact: true });
  await input.fill('60'); await input.press('Enter');
  await page.waitForFunction(y => Math.abs(window.__cadDisplayRecords().find(record => record.partId === 'o1.2').matrix[13] - y) > 1, rest['o1.2'][1]);
  const posed = await translations(page);
  await view.tool('Select').click();
  // A measurement, kept under Select; a part selected in the tree.
  await view.tool('Measure').click();
  const measurements = page.getByRole('region', { name: 'Measurements' });
  await measurePoints(page, at, [0, 0, 5], [15, 0, 4]);
  await measurements.waitFor();
  await view.tool('Select').click();
  assert.equal(await measurements.isVisible(), true);
  await pane.getByRole('button', { name: 'Select base', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 1);
  // A part hidden, another isolated.
  await pane.getByRole('button', { name: 'Hide arm', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().hiddenPartIds.join() === 'o1.2');
  await pane.getByRole('button', { name: 'Select base', exact: true }).dblclick();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.length === 1);
  // The Display settings, with Clip and Explode; then the camera.
  await view.display({ mode: 'wireframe', clip: { enabled: true, axis: 'x', offsets: { x: 0.6 } }, exploded: { enabled: true, amount: 0.3 } });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.exploded.enabled === true);
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({ ...window.cadHarness.a.controller.readState().camera, position: [60, -20, 25], target: [4, 1, 0], zoom: 1.3 }));
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {})[0]?.camera?.zoom === 1.3);
  const left = await view.state();
  // Where the explosion put every part once it has eased out, to be found in the same place after the reload.
  const explodedLeft = await restingLayout(page, posed);
  // The tree as isolation shows it: the base's rows, opened.
  const rowsLeft = await view.rows();
  assert.ok(rowsLeft.length > 1, `the tree has the base's rows before the reload: ${rowsLeft.join(', ')}`);
  assert.deepEqual(await page.evaluate(() => Object.keys(sessionStorage)), ['text-to-cad:tab:harness'], 'one record, and nothing else in the tab');

  await view.reload();
  const back = await view.state();
  for (const property of ['position', 'target', 'zoom']) {
    const a = [back.camera[property]].flat(), b = [left.camera[property]].flat();
    assert.ok(a.every((value, index) => Math.abs(value - b[index]) < 1e-6), `the saved camera comes back in place of the fit: ${property} ${JSON.stringify([a, b])}`);
  }
  assert.deepEqual([back.display.mode, back.display.clip.enabled, back.display.clip.axis, back.display.exploded.enabled, back.display.exploded.amount],
    ['wireframe', true, 'x', true, 0.3], 'the Display settings, Clip and Explode come back');
  // An explosion restored on load lays the parts out exactly as the live one did: it is centred on
  // the rest placement, so the restored camera still frames the same picture. It is laid out once
  // the model is drawn again, so it is awaited, on the page's frames.
  const laidOut = await page.waitForFunction(left => {
    const now = Object.fromEntries(window.__cadDisplayRecords().map(record => [record.partId, record.matrix.slice(12, 15)]));
    return Object.keys(left).every(id => now[id] && left[id].every((value, axis) => Math.abs(value - now[id][axis]) < 1e-6));
  }, explodedLeft, { polling: 'raf', timeout: 30_000 }).then(() => true, () => false);
  assert.ok(laidOut, `every exploded part comes back where it was: ${JSON.stringify({ before: explodedLeft, after: await translations(page) })}`);
  assert.deepEqual([back.hiddenPartIds, back.isolatedPartIds.length], [['o1.2'], 1], 'the hidden and the isolated parts come back');
  assert.deepEqual(await view.rows(), rowsLeft, 'the tree comes back as it was, expanded');
  assert.deepEqual([back.selectedPartIds, back.selectedReferenceIds], [[], []], 'the selection does not');
  assert.equal(await measurements.count(), 0, 'nor the measurement');
  // The tool in hand is Select, the default; Explode and Clip are pressed only because their
  // restored effects are applied (an applied effect marks its tool), not because either is in hand.
  assert.deepEqual((await view.tools()).filter(tool => tool.endsWith(':true')), ['Select:true', 'Explode:true', 'Clip:true'], 'and the tool is the default');
  await view.tool('Measure').click();
  assert.equal((await pane.getByRole('region', { name: 'Measure controls', exact: true }).locator('[data-measure-hint]').innerText()).trim(), 'Pick two points to measure');
  await view.tool('Position').click();
  await input.waitFor({ state: 'attached' });
  assert.equal(await input.inputValue(), '60.0°', 'the pose comes back');
  assert.deepEqual(errors, []);
});
