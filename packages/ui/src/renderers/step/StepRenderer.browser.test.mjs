import assert from 'node:assert/strict';
import { after, afterEach, before, test } from 'node:test';
import { PNG } from 'pngjs';
import { serveStepHarness } from '../harness/stepScenario.mjs';
import { TOOL_PANEL_WIDTH } from '../../../dist/renderers/kit/tools/toolStackLayout.js';

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
const frame = async (pane) => { await settle(pane.page()); return PNG.sync.read(await pane.locator('[aria-busy] > div > canvas').first().screenshot({ style: '[data-slot=popover-content], [data-slot=dropdown-menu-content], [data-slot=dropdown-menu-sub-content], [data-cad-tool-groups] { visibility: hidden !important; }' })); };
// A canvas screenshot also catches what is drawn OVER the canvas: the tool strip
// along the top, the tool stack's panels under it (hidden for the shot: they change with
// every tool and selection) and the view cube in the bottom-right corner. None is the
// model, so every measurement of the picture is taken in the band between them (the
// harness page is `VIEWPORT`, 800 × 600: an 800 × 564 canvas, the cube's top at ~445). Pixel
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
// sessionStorage, the file's view is seeded with Orbit off in its Playback settings — a still
// preview camera, so what moves in a frame is the model — as a previous session would have left it.
async function open(options = {}) {
  const seeded = options.record === undefined && options.store !== 'session'
    ? { record: { version: 1, settings: {}, files: { [JSON.stringify(['one', harness.fixture.file, 'step'])]: { version: 2, playback: { orbit: false } } } } } : {};
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
    // Preview: its button, the play icon beside Display settings; its X back. The file's view was
    // seeded with Orbit off: a still camera, so what moves in a frame is the model.
    enterPreview: async () => {
      await pane.getByRole('button', { name: 'Preview', exact: true }).click();
      await pane.getByRole('button', { name: 'Exit preview', exact: true }).waitFor();
    },
    exitPreview: async () => {
      await pane.getByRole('button', { name: 'Exit preview', exact: true }).click();
      await pane.getByRole('button', { name: 'Preview', exact: true }).waitFor();
    },
    // Display is not a tool: its settings button sits beside Preview at the viewport's top right.
    tool: name => name === 'Display' ? pane.getByRole('button', { name: 'Display settings', exact: true })
      : pane.locator(name === 'Reset' ? '[data-cad-camera-controls]' : '[data-cad-toolbar]').getByRole('button', { name, exact: true }),
    tools: () => pane.locator('[data-cad-toolbar]').getByRole('button')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    // The nav row's panel toggles, in order, each with whether its panel is the open one. A STEP
    // declares none of its own: the file tree's is the only one.
    panels: () => pane.locator('[data-file-panel]')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    toggle: id => id === 'cad-display' ? pane.getByRole('button', { name: 'Display settings', exact: true }) : pane.locator(`[data-file-panel="${id}"]`),
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
    // Display's settings: a popover, portaled out of the viewer.
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


test('a STEP opens in Select with the tools its sidecar earns and Display last, its Features in the tool stack, and paints both authored colours', async () => {
  const view = await open();
  const { page, pane, errors } = view;
  assert.deepEqual(await view.tools(), ['Select:true', 'Position:false', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false'],
    'Position because the sidecar bound; no Animate: its routine plays in preview. Display is a settings popover, not a tool');
  // The nav row has no panel of the file's: its controls are the tool stack's. The file tree's
  // toggle is the only one, and a file opened directly opens with nothing beside it.
  assert.deepEqual(await view.panels(), ['Show files:false']);
  assert.equal(await pane.locator('[data-file-panel-container]').count(), 0, 'no panel column beside the file');
  assert.equal(await view.displayPanel().count(), 0, 'Display is never where a file opens');
  // Select is the tool, so the stack shows its Features: no tabs, and nothing of Position's.
  assert.deepEqual(await view.stack(), ['Features']);
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
  // It folds to its filter row by the chevron at that row's end, and unfolds as it was.
  // (Recognition is unavailable in this harness: a part opens onto one supplied feature.)
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
  const fold = featuresPanel.locator('[data-slot=tree-filter]').getByRole('button', { name: 'Collapse features', exact: true });
  assert.equal(await fold.locator('[data-chevron]').getAttribute('data-chevron'), 'up', 'open: the chevron points up, to fold');
  await fold.click();
  assert.equal(await pane.locator('[aria-label="Modeling tree"]').isVisible(), false);
  const foldedBox = await featuresPanel.boundingBox();
  assert.ok(Math.abs(foldedBox.height - fit.filter - 2) <= 1, 'folded to its filter row');
  assert.equal(await pane.getByRole('textbox', { name: 'Filter model', exact: true }).isVisible(), true);
  const unfold = featuresPanel.getByRole('button', { name: 'Expand features', exact: true });
  assert.deepEqual([await unfold.getAttribute('aria-expanded'), await unfold.locator('[data-chevron]').getAttribute('data-chevron')], ['false', 'down'],
    'folded: the chevron points down, to open');
  // Folded, Features keeps its width handle — there is a width to set — and loses its height's
  // and the corner: there is no height to set. Its chevron opens it again, its expansion kept.
  assert.deepEqual(await featuresPanel.getByRole('separator').evaluateAll(handles => handles.map(handle => handle.getAttribute('aria-label'))), ['Resize features width']);
  const widthHandle = await pane.getByRole('separator', { name: 'Resize features width', exact: true }).boundingBox();
  assert.ok(Math.abs(widthHandle.x + widthHandle.width / 2 - (foldedBox.x + foldedBox.width)) <= 1, 'the width handle is centred on the folded panel\'s right edge');
  await unfold.click();
  await featuresPanel.getByRole('button', { name: 'Collapse features', exact: true }).waitFor();
  assert.deepEqual(await view.rows(), openedRows, 'the tree kept its expansion while folded');
  assert.deepEqual(await featuresPanel.getByRole('separator').evaluateAll(handles => handles.map(handle => handle.getAttribute('aria-label'))),
    ['Resize features width', 'Resize features height', 'Resize features'], 'open: all three handles');
  assert.deepEqual(await page.evaluate(() => window.cadHarness.preferences.getSnapshot().toolStack), { panels: {}, collapsed: {} }, 'nothing sized, nothing folded: nothing stored');
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
  await page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
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
  await pane.getByRole('button', { name: 'Select Grouped faces', exact: true }).waitFor();
  await page.mouse.click(...at([6, 6, 5]));
  await page.waitForFunction(() => { const ids = window.cadHarness.a.controller.readState().selectedReferenceIds;
    return ids.length === 1 && /\.f\d+$/.test(ids[0]); });
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
  // Headed by the part's name; the id is a row, what a copy carries.
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), /^base .*Type Component.*ID o1\.1.*Size 20 × 20 × 10 mm.*Color #3A6EA5/);
  assert.equal(await reference.locator('[data-reference-count]').count(), 0, 'one reference has no i/N');
  // Compact rows in the panel's one face: every value is the UI font at the panel's size, never
  // monospace; and a component's facts fit the panel's default height without scrolling. The
  // Reference is a fixed panel: every panel's width, and no handle of its own — so a long value
  // (a size) wraps to a second line rather than widening it.
  assert.equal(Math.round((await reference.boundingBox()).width), TOOL_PANEL_WIDTH);
  assert.equal(await reference.getByRole('separator').count(), 0);
  const faces = await reference.locator('[data-tool-panel-body] *').evaluateAll(nodes => [...new Set(nodes
    .filter(node => !node.childElementCount && node.textContent.trim())
    .map(node => `${getComputedStyle(node).fontFamily} | ${getComputedStyle(node).fontSize}`))]);
  assert.equal(faces.length, 1, `one face and size: ${faces.join(' / ')}`);
  assert.doesNotMatch(faces[0], /mono/i);
  assert.match(faces[0], /\| 11px$/);
  const rowHeights = await reference.locator('[data-info-row]').evaluateAll(rows => rows.map(row => row.getBoundingClientRect().height));
  assert.ok(rowHeights.length >= 4 && rowHeights.every(height => height <= 19 * 2), `compact rows, a line or two each: ${rowHeights}`);
  assert.equal(await reference.locator('[data-tool-panel-body]').evaluate(body => body.scrollHeight <= body.clientHeight), true, 'a component fits without scrolling');
  // The Reference is the next panel of the stack, under Features, the stack's width.
  assert.deepEqual(await view.stack(), ['Features', 'Reference details']);
  const [features, pinned] = await Promise.all([pane.getByRole('region', { name: 'Features', exact: true }).boundingBox(), reference.boundingBox()]);
  assert.ok(pinned.y >= features.y + features.height && pinned.y - (features.y + features.height) <= 10, `directly under Features: ${pinned.y} vs ${features.y + features.height}`);
  assert.equal(pinned.width, features.width, 'the width of every stack item');
  // The Features filter row is a heading's height, dense: its buttons sit exactly where a heading's
  // do, 5px down from their panel's top.
  const featuresPanel = pane.getByRole('region', { name: 'Features', exact: true });
  const [chevron, clear] = await Promise.all([featuresPanel.getByRole('button', { name: 'Collapse features', exact: true }).boundingBox(),
    reference.getByRole('button', { name: 'Clear selection', exact: true }).boundingBox()]);
  assert.equal(Math.round(chevron.y - features.y), 5, 'the filter row\'s chevron');
  assert.equal(Math.round(clear.y - pinned.y), 5, 'the Reference heading\'s X');
  assert.equal(chevron.height, clear.height);
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
    reference.getByText('Type', { exact: true }).boundingBox()]);
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
  // The bottom action is the Select tool’s: Annotate, a note on what is picked. No Copy button:
  // the copy is its shortcut, and the prompt is reached through a pick's own menu.
  await pane.getByRole('button', { name: 'Annotate', exact: true }).waitFor();
  assert.equal(await pane.getByRole('button', { name: /^Copy Reference/ }).count(), 0, 'no copy button');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.length === 0);

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

test('under Faces or Edges, one press on a part whose faces are not loaded loads that part alone and picks what is under the pointer', async () => {
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
  // Named by its part as the tree names it and its kind, never by its raw id; the id is a row.
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), new RegExp(`^base · face ${face.replace(/^.*\.f/, '')} Type Face · Planar ID ${face.replace(/\./g, '\\.')}`),
    'the Reference names the face under the pointer');
  assert.deepEqual((await view.state()).selectedPartIds, [], 'the mode never falls back to the part');
  // Edges likewise, on the arm, whose topology is still not loaded (the panel says so again):
  // its top edge over the +x face.
  const sawBefore = await page.evaluate(() => window.__sawLoading.length);
  await mode('Edges');
  await page.mouse.click(...at([20, 0, 4]));
  await page.waitForFunction(() => /^topology\|o1\.2\|edge\|o1\.2\.e\d+$/.test(window.cadHarness.a.controller.readState().selectedReferenceIds.join()));
  assert.ok(await page.evaluate(() => window.__sawLoading.length) > sawBefore, 'only the pressed part had loaded');
  const edge = (await selected())[0].split('|').at(-1);
  assert.match((await reference.innerText()).replace(/\s+/g, ' '), new RegExp(`^arm · edge ${edge.replace(/^.*\.e/, '')} Type Edge.*ID ${edge.replace(/\./g, '\\.')}`));
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
  const opened = await restingFrame(view);
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
  await page.mouse.click(box.x + 30, box.y + box.height - 30, { button: 'right' });
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
  for (const tool of ['Measure', 'Position', 'Draw']) {
    await view.tool(tool).click();
    // A menu opens in the render the press causes: two frames on, it would be there.
    await page.mouse.click(...at([6, 6, 5]), { button: 'right' });
    await settle(page);
    assert.equal(await page.getByRole('menu').count(), 0, `${tool} opens no viewport menu over a part`);
    await page.mouse.click(box.x + 30, box.y + box.height - 30, { button: 'right' });
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
  assert.deepEqual(await view.tools(), ['Select:false', 'Position:false', 'Draw:true', 'Measure:false', 'Explode:false', 'Clip:false']);
  assert.equal(await pane.getByRole('button', { name: 'Select arm', exact: true }).isVisible(), false);
  await view.tool('Select').click();
  // A menu goes when the camera moves, and the last pan is still coasting: it opens at rest.
  await pane.getByRole('button', { name: 'Select arm', exact: true }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Isolate', exact: true }).click();
  await page.getByRole('menu').waitFor({ state: 'detached' });
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().isolatedPartIds.join() === 'o1.2');
  assert.deepEqual(await view.tools(), ['Select:true', 'Position:false', 'Draw:false', 'Measure:false', 'Explode:false', 'Clip:false']);
  await page.keyboard.press('Escape');
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
  // Display is a popover from its button in the viewport's top-right bar.
  await view.toggle('cad-display').click();
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
    assert.equal(await panel.isVisible(), true, 'choosing a preset keeps the popover');
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
  // A file with movable joints has Position straight after Select on the strip.
  assert.deepEqual((await pane.getByRole('group', { name: 'Interaction tools' }).locator('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')))).slice(0, 3),
    ['Select', 'Position', 'Draw']);
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
  // Sized like the tree: its content's height, capped at half the stack, with a height handle.
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

  await page.mouse.move(view.box.x + 20, view.box.y + view.box.height - 20);
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
  // The tools view carries nothing of the routine's: no Animate tool, no transport.
  assert.equal(await view.tool('Animate').count(), 0);
  assert.equal(await pane.locator('[data-animation-transport]').count(), 0);
  await view.enterPreview();
  // The tools are put away, and the playbar is under the model.
  assert.equal(await pane.getByRole('group', { name: 'Interaction tools' }).isVisible(), false);
  const bar = pane.getByRole('toolbar', { name: 'Animation playback' });
  await bar.waitFor();
  // Autoplay is off by default: entered, the routine waits, at rest.
  await bar.getByRole('button', { name: 'Play animation', exact: true }).waitFor();
  await page.waitForTimeout(300);
  assert.deepEqual((await translations(page))['o1.2'], restArm, 'nothing plays until its play button is pressed');
  const rest = await view.frame();
  // The transport, then Playback settings: the cog at the playbar's right end.
  assert.deepEqual(await bar.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))), ['Play animation', 'Playback settings']);
  assert.equal(await bar.getByRole('slider', { name: 'Animation time', exact: true }).count(), 1);

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
    await new Promise(resolve => setTimeout(resolve, 150));
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
  assert.ok(differing(firstFrame, middleFrame) > 10_000, 'the picture changed');

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
  // (The middle frame's base already fills nearly all of the band this is counted in, so the
  // shrink it can show here is less than the camera's 1.3× pull-back would suggest.)
  assert.ok(framed.base && framed.base.count < after.base.count * 0.9,
    `and it is drawn smaller for it: the base ran off the frame it now sits inside (${after.base.count} -> ${framed.base.count} pixels)`);

  // Reopening restores the camera the person set: the completion fit exists for a camera
  // nobody set, and a stored one is the person's.
  await page.evaluate(() => window.cadHarness.a.controller.setCamera({
    ...window.cadHarness.a.controller.readState().camera, position: [90, -30, 38], target: [4, 1, 0], zoom: 1.6 }));
  await restingCamera(page);
  const chosen = await page.evaluate(() => window.__cadCamera());
  const chosenFrame = await restingFrame({ page, frame: () => frame(pane) });
  assert.ok(chosen.position.some((value, index) => Math.abs(value - whole.camera.position[index]) > 1),
    'the camera the person set is somewhere the fit never puts it');
  const stored = await page.evaluate(() => JSON.parse(JSON.stringify(window.cadHarness.tabStore.getSnapshot())));

  // Reopened: a fresh page over the same package, held in pieces again, carrying what the last
  // session left for this file. (A remount would not do: the client still holds every component
  // it downloaded, so the package would arrive whole in ONE publish and never reach completion
  // as a second framing at all.)
  staggered.hold('a'); staggered.hold('b');
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
  const view = await open();
  const { page, box, at, errors } = view;
  const selection = () => page.evaluate(() => { const state = window.cadHarness.a.controller.readState();
    return { parts: state.selectedPartIds, refs: state.selectedReferenceIds, isolated: state.isolatedPartIds }; });
  const cleared = () => page.waitForFunction(() => { const state = window.cadHarness.a.controller.readState();
    return state.selectedPartIds.length + state.selectedReferenceIds.length === 0; });
  const copies = () => page.evaluate(() => window.__clipboardWrites.length);
  const empty = [box.x + 30, box.y + box.height - 30];
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
  assert.match(await page.evaluate(() => window.__clipboardWrites[0]), /^hinge_block\.step#o1\.2\.f\d+$/);
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
  // Where the explosion put every part, to be found in the same place after the reload.
  const explodedLeft = await translations(page);
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
  // the rest placement, so the restored camera still frames the same picture.
  const sameLayout = async () => {
    const now = await translations(page);
    return Object.keys(explodedLeft).every(id => now[id] && explodedLeft[id].every((value, axis) => Math.abs(value - now[id][axis]) < 1e-6));
  };
  for (let tries = 0; tries < 20 && !(await sameLayout()); tries += 1) await page.waitForTimeout(100);
  assert.ok(await sameLayout(), `every exploded part comes back where it was: ${JSON.stringify({ before: explodedLeft, after: await translations(page) })}`);
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

test('annotations live in the chat box: making one puts it there, and its dot is on the model only while the chat box holds it', async () => {
  const view = await open();
  const {page, pane} = view;
  // A chat box that keeps annotations apart from its text, as the desktop's does: it says which it holds.
  await page.evaluate(() => {
    window.__delivered = [];
    window.__held = [];
    const harness = window.cadHarness.a;
    const hold = ids => { window.__held = ids; harness.setPromptDestination({held: [...ids]}); };
    window.__hold = hold;
    hold([]);
    harness.host.promptContext.deliver = async context => {
      window.__delivered.push(context.parts.map(part => ({kind: part.kind, id: part.id,
        selectors: part.references?.flatMap(reference => reference.target.selectors), text: part.text})));
      hold([...new Set([...window.__held, ...context.parts.map(part => part.id)])]);
      return {status: 'added', partIds: context.parts.map(part => part.id)};
    };
    harness.host.promptContext.retract = ids => hold(window.__held.filter(id => !ids.includes(id)));
  });
  const delivered = () => page.evaluate(() => window.__delivered);
  const annotate = async (selector, note) => {
    await page.evaluate(value => window.cadHarness.a.controller.select({selectors: [value]}), selector);
    await pane.getByRole('button', {name: 'Annotate', exact: true}).click();
    const box = page.getByRole('textbox', {name: 'Annotation', exact: true});
    await box.fill(note);
    await box.press('Enter');
  };

  // Making an annotation puts it in the chat box at once; nothing is sent to the agent by it.
  await annotate('o1.2', 'make a hole in it');
  await page.waitForFunction(() => window.__delivered.length === 1);
  const [first] = (await delivered())[0];
  assert.deepEqual([first.kind, first.selectors, first.text], ['annotation', ['o1.2'], 'make a hole in it']);
  assert.equal(await pane.getByRole('toolbar', {name: 'Annotations'}).count(), 0, 'there is no bar over the model');
  assert.equal(await pane.getByRole('list', {name: 'Annotations'}).count(), 0, 'annotations are not listed in the panel');

  // It is a numbered dot on the model, over the part it was made on; pressing the dot opens its card there.
  const dot = pane.getByRole('button', {name: 'Annotation 1', exact: true});
  await dot.waitFor();
  const dotBox = await dot.boundingBox();
  const canvasBox = await pane.locator('[data-cad-surface] canvas').first().boundingBox();
  assert.ok(dotBox.x > canvasBox.x && dotBox.x < canvasBox.x + canvasBox.width && dotBox.y > canvasBox.y && dotBox.y < canvasBox.y + canvasBox.height,
    'the dot is on the model, inside the viewport');
  const card = pane.getByRole('dialog', {name: 'Annotation 1 details'});
  await dot.click();
  await card.waitFor();
  assert.match((await card.innerText()).replace(/\s+/g, ' '), /^Annotation 1: .+ make a hole in it/);
  const chip = card.locator('[data-annotation-chip="o1.2"]');

  // Pressing the chip selects that geometry again, whatever is selected now.
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors:['o1.1']}));
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.1');
  await chip.click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');

  // An edit replaces the chat box's copy: the same annotation, delivered again. The box opens
  // focused with the caret at the end, so typing goes straight into the note.
  await card.getByRole('button', {name: 'Edit annotation 1'}).click();
  const edit = card.getByRole('textbox', {name: 'Edit annotation 1'});
  assert.equal(await edit.evaluate(element => document.activeElement === element), true, 'the edit box has focus');
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type('make a 6 mm hole in it');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => window.__delivered.length === 2);
  const [edited] = (await delivered())[1];
  assert.deepEqual([edited.id, edited.text], [first.id, 'make a 6 mm hole in it']);

  // Escape leaves the note as it was; clicking away from the box saves what was typed.
  await card.getByRole('button', {name: 'Edit annotation 1'}).click();
  await page.keyboard.type(' now');
  await page.keyboard.press('Escape');
  assert.match(await card.innerText(), /make a 6 mm hole in it$/m);
  await card.getByRole('button', {name: 'Edit annotation 1'}).click();
  await page.keyboard.type(', deburred');
  await card.getByText(/^Annotation 1:/).click();
  await page.waitForFunction(() => window.__delivered.length === 3);
  assert.equal((await delivered())[2][0].text, 'make a 6 mm hole in it, deburred');

  // A note rewritten in the chat box's own list reaches the card through what the box says it
  // holds, with nothing delivered back.
  await page.evaluate(id => window.cadHarness.a.setPromptDestination({heldText: {[id]: 'make it 8 mm, from the chat box'}}), first.id);
  await card.getByText('make it 8 mm, from the chat box').waitFor();
  assert.equal((await delivered()).length, 3, 'the chat box edit is not delivered back');
  await card.getByRole('button', {name: 'Close', exact: true}).click();
  await card.waitFor({state: 'detached'});

  // The chat box names an annotation (its chip was pressed there): its geometry is selected and its card opens.
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors:['o1.1']}));
  await page.evaluate(id => window.cadHarness.a.openAnnotation(id), first.id);
  await card.waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().selectedPartIds.join() === 'o1.2');

  // Deleting it on the model takes it out of the chat box.
  await card.getByRole('button', {name: 'Delete annotation 1'}).click();
  await dot.waitFor({state: 'detached'});
  assert.deepEqual(await page.evaluate(() => window.__held), []);

  // Sending the prompt (or removing the annotations from the chat box) takes their dots off the model.
  await annotate('o1.1', 'add a fillet');
  await annotate('o1.2', 'and chamfer it');
  const second = pane.getByRole('button', {name: 'Annotation 2', exact: true});
  await second.waitFor();
  await page.evaluate(() => window.__hold([]));
  await dot.waitFor({state: 'detached'});
  await second.waitFor({state: 'detached'});

  // With no chat to put them in, there is nothing to annotate into.
  await page.evaluate(() => window.cadHarness.a.setPromptDestination({available: false, reason: 'No chat'}));
  await page.evaluate(() => window.cadHarness.a.controller.select({selectors: ['o1.2']}));
  assert.equal(await pane.getByRole('button', {name: 'Annotate', exact: true}).isDisabled(), true);
  assert.deepEqual(view.errors, []);
});
