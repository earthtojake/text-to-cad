import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { existsSync, readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { harnessBundle } from '../harness/bundle.mjs';
import { pressInPreview } from '../harness/preview.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';

// The robot renderer end to end in a real browser, over the fixture descriptions in `__fixtures__`
// as cadgen resolved them (`make_fixtures.py`; the Python suite holds the files current): a URDF of
// primitives, the SRDF paired with it (a "home" state, a named pose, an end effector), a
// long chain, a four-bar linkage cadgen closes, and the two cadgen refuses (their alerts are
// `useRobotDocument.test.tsx`'s and `ViewportError.test.tsx`'s, an SDF's own section `SdfSection.test.tsx`'s: no GPU needed). This server answers `GET /__cad/robot` as the viewer's does, from
// those files, so the page here is the page a CAD Viewer serves. Scene, pose store and handle adapter
// have unit tests; these are the flows a person actually uses.

const FIXTURES = new URL('./__fixtures__/', import.meta.url);
const DESCRIPTIONS = ['arm.urdf', 'arm.srdf', 'chain.urdf', 'linkage.urdf', 'gone.urdf', 'lonely.srdf'];
const payloadFile = name => new URL(`${name.slice(0, name.lastIndexOf('.'))}.${name.split('.').pop()}.robot.json`, FIXTURES);
// cadgen's answer for each description: its payload, or the sentence it refuses it with.
const PAYLOADS = Object.fromEntries(DESCRIPTIONS.filter(name => existsSync(payloadFile(name))).map(name => [name, readFileSync(payloadFile(name), 'utf8')]));
const REFUSALS = JSON.parse(readFileSync(new URL('refusals.json', FIXTURES), 'utf8'));
// A chain long enough that a per-pose cost proportional to the robot would show.
// The strip with Select in hand: a robot's four tools (`robot/tools.js`).
// The tools that can be in hand; Clip, a popover from its tile, is never one.
const SELECT_IN_HAND = ['Select:true', 'Pencil:false', 'Shapes:false', 'Measure:false'];
const CHAIN_LINKS = 30;
// The harness renders its panes at a fixed CSS size; the spec draws them smaller, so a software
// GL (CI's SwiftShader) has fewer pixels to fill and a capture fewer to read.
const HARNESS_SIZE = '<style>#root > div { width: 800px !important; height: 500px !important; }</style>';

let server, browser;
// Bumped by a test to publish a new revision of every description.
let revision = 1;
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const [, root, ...rest] = url.pathname.split('/');
    const name = rest.join('/');
    const json = (status, body) => { response.statusCode = status; response.setHeader('Content-Type', 'application/json'); response.end(body); };
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      const entry = file => ({ kind: file.split('.').pop(), file: `/models/${file}`, url: `/${file}`, hash: `${root}-${file}-${revision}`, bytes: 1 });
      json(200, JSON.stringify({ entries: DESCRIPTIONS.map(file => (file === 'arm.srdf' ? { ...entry(file), relations: { urdf: entry('arm.urdf') } } : entry(file))) }));
    } else if (url.pathname.endsWith('/__cad/server')) json(200, JSON.stringify({ backend: 'cadgen' }));
    else if (url.pathname.endsWith('/__cad/robot')) {
      // As the viewer's route answers: the payload, or cadgen's refusal as a 400.
      const file = String(url.searchParams.get('file') || '').replace(/^\/models\//, '');
      if (PAYLOADS[file]) json(200, PAYLOADS[file]);
      else json(REFUSALS[file] ? 400 : 404, JSON.stringify({ error: REFUSALS[file] || `${file}: no such description` }));
    } else {
      // A link mesh file beside the descriptions, or a primitive cadgen meshed, by the URL the payload names.
      const asset = [url.pathname.slice(1), name].find(candidate => /^(meshes|primitives)\/[^/]+\.glb$/.test(candidate) && existsSync(new URL(candidate, FIXTURES)));
      if (asset) { response.setHeader('Content-Type', 'model/gltf-binary'); response.end(readFileSync(new URL(asset, FIXTURES))); }
      else if (/\.(woff2|ttf|stl|glb)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
      else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><title>Host</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1') ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

async function open(t, file, { panel = true } = {}) {
  const context = await browser.newContext({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => context.close());
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.Worker = undefined;
    for (const name of ['localStorage', 'sessionStorage']) Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
  });
  // Committed, not loaded: what follows waits for the view itself (its canvas, its tiles, its text),
  // never for the page's every resource under one fixed bound.
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`, { waitUntil: 'commit' });
  const pane = page.getByTestId('one');
  const tools = pane.getByRole('group', { name: 'Interaction tools' });
  const robot = {
    page, pane, tools, errors,
    tool: name => tools.getByRole('button', { name, exact: true }),
    // The strip's tools (its buttons pressed or not, before the view's controls), and what Select's chevron says it picks.
    toolNames: () => tools.getByRole('button').evaluateAll(buttons => buttons.filter(button => button.hasAttribute('aria-pressed') && !button.closest('[data-view-controls]'))
      .map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    filter: () => tools.locator('[data-select-filter-trigger]').getAttribute('aria-label'),
    // Select's mode chosen from its chevron's menu ("all", "links" or "position"), which puts the menu away.
    async filterTo(mode) {
      await tools.locator('[data-select-filter-trigger]').click();
      const menu = page.locator('[role=menu][aria-label="Selection filter"]');
      await menu.locator(`[data-select-filter="${mode}"]`).click();
      await menu.waitFor({ state: 'detached' });
    },
    handles: async () => Object.fromEntries((await page.evaluate(() => window.__cadJointHandles())).map(handle => [handle.id, handle])),
    links: async () => Object.fromEntries((await page.evaluate(() => window.__robotLinks())).map(({ link, matrixWorld }) => [link, matrixWorld])),
    camera: () => page.evaluate(() => { const { position, target, zoom } = window.__cadCamera(); return [...position, ...target, zoom]; }),
    stats: () => page.evaluate(() => window.__robotPoseStats()),
    jointField: (name, unit = 'deg') => page.getByLabel(`${name} value in ${unit}`, { exact: true }),
    // Select picking the joints' knobs alone (a press on the model picks nothing), or its links alone (no knobs).
    openPosition: () => robot.filterTo('position'),
    pickLinks: () => robot.filterTo('links'),
    // The view is written a moment after a change (the host stores its record on a debounce):
    // a test that counts renders or reads the framing waits until nothing has rendered and the
    // camera has not moved for longer than that debounce.
    settled: () => page.waitForFunction(() => new Promise(resolve => {
      const read = () => JSON.stringify([window.__robotPoseStats?.().surfaceRenders, window.__cadCamera?.()?.position]);
      let last = read(), since = performance.now();
      const step = () => {
        const now = read();
        if (now !== last) { last = now; since = performance.now(); }
        if (performance.now() - since >= 300) resolve(true); else requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    })),
    // The file sidebar's tiles, and a section opened by its tile (one at a time), left open if it is.
    tiles: () => pane.locator('[data-file-sidebar-tools] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    async openSection(name) {
      const tile = pane.getByRole('group', { name: 'File sidebar' }).getByRole('button', { name, exact: true });
      if (await tile.getAttribute('aria-pressed') !== 'true') await tile.click();
      await pane.locator(`[data-file-sidebar-tools] button[aria-pressed="true"][aria-label="${name}"]`).waitFor();
    },
    // In and out of Preview, by Preview at the strip's end and Exit preview in Preview's bar, once its cover has lifted.
    // Exit preview is pressed as a person presses it, the bar it is on brought back (`harness/preview.mjs`).
    async preview(enter) {
      const press = pane.getByRole('button', { name: enter ? 'Preview' : 'Exit preview', exact: true });
      if (enter) await press.click(); else await pressInPreview(page, pane, press);
      await pane.getByRole('button', { name: enter ? 'Exit preview' : 'Preview', exact: true }).waitFor();
      await page.waitForFunction(() => !document.querySelector('[data-testid="one"] [data-preview-cover]'));
    },
    // A joint set from the sidebar's Position section, whatever Select picks.
    async type(name, value, unit) {
      await robot.openSection('Position');
      await robot.jointField(name, unit).fill(String(value)); await robot.jointField(name, unit).press('Enter');
    },
    pressedRows: () => pane.locator('[aria-label="Robot tree area"] button[aria-pressed="true"]').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    // The pressed rows once they read `wanted` (in any order), or the assertion naming what they did read.
    async pressed(wanted, message) {
      const expected = [...wanted].sort();
      const read = await page.waitForFunction(want => {
        const rows = [...document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]')]
          .map(button => button.getAttribute('aria-label')).sort();
        return JSON.stringify(rows) === JSON.stringify(want);
      }, expected, { timeout: 5000 }).then(() => true, () => false);
      if (!read) assert.deepEqual((await robot.pressedRows()).sort(), expected, message);
    },
    // A selection is React state: it is on screen a render after whatever changed it.
    waitPressed: count => page.waitForFunction(wanted => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === wanted, count),
    // The view's controls at the strip's end, after its rule: Projection, Display (the mode in hand), then Preview.
    viewControls: () => tools.locator('[data-view-controls] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    // Display: its tile between Projection and Preview, the mode in hand; its menu, the modes and the Grid switch.
    displayButton: () => tools.locator('[data-view-controls]').getByRole('button', { name: /^Display mode: / }),
    async openDisplay() {
      await robot.displayButton().click();
      await robot.displayPanel().waitFor();
    },
    // Display's menu: a dropdown from the strip, portaled out of the viewer.
    displayPanel: () => page.locator('[role=menu][aria-label="Display"]'),
    // The tool stack's panels on screen, top to bottom, by their accessible names.
    stack: () => pane.locator('[data-cad-tool-stack] [data-tool-panel]').evaluateAll(panels => panels
      .filter(panel => panel.getClientRects().length > 0).map(panel => panel.getAttribute('aria-label'))),
    // The file sidebar's sections, top to bottom, the same way. A section draws no box of its own
    // (`display: contents`): one not hidden is on screen.
    sidebar: () => pane.locator('[data-cad-file-sidebar] [data-tool-panel]').evaluateAll(panels => panels
      .filter(panel => !panel.closest('[hidden]')).map(panel => panel.getAttribute('aria-label'))),
    linksPanel: () => pane.locator('[data-tool-panel][aria-label="Links"]'),
    // What is selected is Quick Edit's to show: a chip each, by its name (`robotReferences.jsx`).
    chips: () => pane.locator('[data-quick-edit-refs] [data-quick-edit-ref] > button:first-child')
      .evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    // A chip's card, what the description says of it: the pointer rests on the chip, and it opens beside it.
    async chipCard(label) {
      await pane.locator('[data-quick-edit-refs]').getByRole('button', { name: label, exact: true }).hover();
      const card = page.locator('[data-quick-edit-ref-card]').filter({ has: page.getByText(label, { exact: true }) });
      await card.waitFor();
      return card;
    },
    position: () => pane.locator('[data-tool-panel][aria-label="Position controls"]'),
    section: name => pane.getByRole('region', { name, exact: true }),
    settle: () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))),
    // The viewport's own pixels, without any chrome over them: what a host capture returns.
    async capture() {
      const base64 = await page.evaluate(async () => {
        const data = new Uint8Array(await (await window.cadHarness.a.controller.capture()).arrayBuffer());
        let binary = ''; for (const byte of data) binary += String.fromCharCode(byte);
        return btoa(binary);
      });
      return PNG.sync.read(Buffer.from(base64, 'base64'));
    },
    async surface() { return pane.locator('[data-cad-surface] canvas').first().boundingBox(); },
    // What the pointer looks like over the model. Read from the INTERACTIVE
    // canvas: a tool sets the cursor on the viewport host and the canvas
    // inherits it, which three's OrbitControls used to break by pinning
    // `cursor: auto` on the canvas inline (`kit/viewport/useViewerRuntime.js`).
    cursor: () => page.evaluate(() => getComputedStyle(document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')).cursor),
    waitCursor: value => page.waitForFunction(wanted => getComputedStyle(
      document.querySelector('[data-testid="one"] [aria-busy] > div > canvas')).cursor === wanted, value),
  };
  if (panel) {
    await pane.locator('[aria-busy="false"] canvas').first().waitFor();
    // Its Links are the file sidebar's, opened by their tile.
    await robot.openSection('Links');
    await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
    await robot.settled();
  }
  return robot;
}
// Orbit controls re-derive the camera from its spherical form on a repaint: rounding, not motion.
const sameCamera = (a, b) => a.every((value, index) => Math.abs(value - b[index]) < 1e-9);
const round6 = value => Math.round(value * 1e6) / 1e6;
const translation = matrix => [matrix[3], matrix[7], matrix[11]];
// A point of a link, in the robot's space: through the link's row-major frame.
const through = (matrix, [x, y, z]) => [0, 4, 8].map(row => matrix[row] * x + matrix[row + 1] * y + matrix[row + 2] * z + matrix[row + 3]);

test('a robot\'s knobs are Select\'s while it picks Position, beside the sidebar controls: knobs drag joints, the camera keeps every other press, every pose write is a jump, and a pose step renders no component', async (t) => {
  const robot = await open(t, 'arm.srdf');
  const { page, pane, tools } = robot;
  const home = (-0.5 * 180) / Math.PI, raised = (-1.0 * 180) / Math.PI;

  // The robot opens in Select, its one tool, picking its links and showing its joints' knobs; its
  // filter can pick Position's knobs alone. Its controls are the file sidebar's, under the Links,
  // whatever Select picks; the tool stack holds nothing of a robot's.
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  assert.deepEqual(await robot.toolNames(), SELECT_IN_HAND);
  assert.equal(await robot.tool('Position').count(), 0, 'Position is no tool of its own');
  await robot.openPosition();
  assert.deepEqual([await robot.toolNames(), await robot.filter()], [SELECT_IN_HAND, 'Selection filter: Position']);
  assert.equal(await robot.tool('Explode').count(), 0, 'a robot is posed, never exploded');
  // Projection, Display and Preview are the view's controls, at the strip's end after its rule, for a robot as for any 3D file.
  assert.deepEqual(await robot.viewControls(), ['Projection: Orthographic', 'Display mode: Solid', 'Preview']);
  assert.equal(await tools.locator('[data-strip-rule]').count(), 1, 'one rule, after the tools that pick');
  assert.equal(await tools.locator('[data-view-controls]').evaluate(element => element.previousElementSibling?.getAttribute('aria-label')), 'Clip', 'the view\'s controls follow Clip, no rule between');
  assert.equal(await pane.locator('[data-viewer-navbar] [data-view-controls] button').count(), 0, 'and nothing of the view in the navbar');
  // Display is the tile beside Preview, shut as the file opens.
  assert.equal(await robot.displayPanel().count(), 0, 'Display is never where a file opens');
  assert.equal(await pane.getByRole('tab').count(), 0, 'no tabs');
  assert.deepEqual([await robot.sidebar(), await robot.stack(), await robot.tiles()], [['Links', 'Position controls'], [], ['Links', 'Position']]);
  // Its tile opens it in Links' place. Headed "Position", its Reset (idle at the default pose) and its X.
  await robot.openSection('Position');
  assert.equal(await robot.linksPanel().isVisible(), false, 'one section at a time');
  const positionHeading = robot.position().locator('[data-sidebar-head]');
  assert.equal((await positionHeading.getByRole('heading').innerText()).trim(), 'Position');
  assert.deepEqual(await positionHeading.getByRole('button').evaluateAll(buttons => buttons.map(button => [button.getAttribute('aria-label'), button.disabled])),
    [['Reset position', true], ['Close position', false]], 'the heading is its Reset and its X');
  await robot.openPosition();
  // One knob per moving joint row of the articulation: no fixed joint; a mimic follower's knob
  // writes its leader. A slider exists per CONTROL, so the follower has none, nor the fixed joint.
  assert.deepEqual(Object.keys(await robot.handles()).sort(), ['grip', 'grip_mirror', 'lift', 'nod', 'shoulder']);
  assert.equal(await robot.jointField('grip_mirror', 'm').count(), 0);
  assert.equal(await robot.jointField('camera_mount').count(), 0);
  // The SRDF's "home" state is the pose the robot opens in, and the Position section's Pose menu,
  // its first row, names it.
  assert.equal(round6((await robot.handles()).shoulder.value), round6(home));
  assert.equal((await robot.handles()).lift.value, 0.1);
  const position = robot.position();
  const poseSelect = position.locator('[data-tool-panel-body] [data-pose-row] [data-pose-menu]');
  assert.equal(await poseSelect.getAttribute('aria-label'), 'Pose: Default');
  // Compact joint rows: a small value field beside each slider, as wide as its text needs (a
  // length "0 m" as a turn "0°"), never clipping it; rows 6px apart.
  const fields = await position.locator('[data-position-control] input').evaluateAll(inputs => inputs.map(input => {
    const box = input.getBoundingClientRect();
    return { value: input.value, width: box.width, height: box.height, fits: input.scrollWidth <= input.clientWidth };
  }));
  assert.ok(fields.length >= 3 && fields.every(field => field.height <= 24 && field.width <= 80), `small value fields: ${JSON.stringify(fields)}`);
  assert.ok(fields.every(field => field.fits), `every value fits its field: ${JSON.stringify(fields)}`);
  const rowTops = await position.locator('[data-position-control]').evaluateAll(rows => rows.map(row => row.getBoundingClientRect()));
  assert.ok(rowTops.slice(1).every((row, index) => Math.abs(row.top - rowTops[index].bottom - 6) <= 0.5),
    `rows 6px apart: ${JSON.stringify(rowTops.slice(1).map((row, index) => row.top - rowTops[index].bottom))}`);
  // A longer value widens its field rather than being cut.
  await robot.type('lift', 0.25, 'm');
  assert.equal(await robot.jointField('lift', 'm').evaluate(input => [input.value, input.scrollWidth <= input.clientWidth].join()), '0.25 m,true');
  // Back to the value it opened at (the SRDF's home), so the pose is still the default.
  await robot.type('lift', 0.1, 'm');
  for (const heading of ['Pose', 'Joints', 'Kinematics']) {
    assert.equal(await position.getByRole('heading', { name: heading, exact: true }).count(), 0, `no ${heading} heading inside Position`);
  }
  assert.equal((await poseSelect.innerText()).trim(), 'Default');

  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const at = (x, y) => [surface.x + x, surface.y + y];
  // Every value the shoulder shows, frame by frame, while `action` runs and until it reaches `final`.
  const shoulderFrames = async (action, final) => {
    await page.evaluate(() => {
      window.__shoulderFrames = [];
      const sample = () => { window.__shoulderFrames?.push(window.__cadJointHandles().find(handle => handle.id === 'shoulder').value); if (window.__shoulderFrames) requestAnimationFrame(sample); };
      // The first sample is taken now: the action may land before the next frame does.
      sample();
    });
    await action();
    // Whatever the robot passes through on its way is sampled before it gets there; two frames
    // more say it stays.
    await page.waitForFunction(target => window.__shoulderFrames.length > 2
      && window.__shoulderFrames.slice(-3).every(value => Math.round(value * 1e6) / 1e6 === target), final);
    return page.evaluate(() => { const frames = window.__shoulderFrames; window.__shoulderFrames = null; return [...new Set(frames.map(value => Math.round(value * 1e6) / 1e6))]; });
  };

  // Dragging a knob turns its joint and leaves the camera where it was.
  await robot.settled();
  const framed = await robot.camera();
  const restStage = await page.evaluate(() => window.__cadStage());
  const before = await robot.stats();
  const { shoulder } = await robot.handles();
  await page.mouse.move(...at(shoulder.x, shoulder.y));
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-joint-handle-label]')?.textContent.startsWith('shoulder'));
  // Over a knob the pointer says it can be taken hold of, and says so while it is held.
  await robot.waitCursor('grab');
  await page.mouse.down();
  await robot.waitCursor('grabbing');
  const radius = Math.hypot(shoulder.x - shoulder.pivotX, shoulder.y - shoulder.pivotY);
  const bearing = Math.atan2(shoulder.y - shoulder.pivotY, shoulder.x - shoulder.pivotX);
  for (let step = 1; step <= 9; step += 1) {
    const angle = bearing + (step * Math.PI) / 18;
    await page.mouse.move(...at(shoulder.pivotX + radius * Math.cos(angle), shoulder.pivotY + radius * Math.sin(angle)));
    await robot.settle();
  }
  await page.waitForFunction(start => Math.abs(window.__cadJointHandles().find(handle => handle.id === 'shoulder').value - start) > 20, home);
  const held = (await robot.handles()).shoulder.value;
  assert.match(await pane.locator('[data-cad-joint-handle-label]').textContent(), /^shoulder\s+-?\d+\.\d°$/);
  await page.mouse.up();
  await robot.waitCursor('grab');
  assert.equal(await robot.cursor(), 'grab', 'released, and still on the knob');
  // Nothing eases behind the drag: the value at release is the value that stays, frame after frame.
  const released = await page.evaluate(() => new Promise(resolve => {
    const values = [];
    const sample = () => {
      values.push(window.__cadJointHandles().find(handle => handle.id === 'shoulder').value);
      if (values.length === 10) resolve(values); else requestAnimationFrame(sample);
    };
    sample();
  }));
  assert.deepEqual([...new Set(released)], [held]);
  assert.ok(sameCamera(await robot.camera(), framed), 'a knob drag never moves the camera');
  assert.equal(await robot.jointField('shoulder').inputValue(), `${Math.round(held * 10) / 10}°`, 'the Position slider follows the knob');
  assert.equal((await robot.handles()).lift.value, 0.1);
  // What the drag cost: one matrix per step (the joint that moved), and not one render of the renderer's surface.
  const dragged = await robot.stats();
  assert.equal(dragged.lastPoseWrites, 1, 'a pose step writes the one joint that changed');
  assert.ok(dragged.poseWrites - before.poseWrites >= 5 && dragged.poseWrites - before.poseWrites <= 12, JSON.stringify({ before, dragged }));
  // (The one render a drag may cost is the host storing the debounced record, not a step.)
  assert.ok(dragged.surfaceRenders - before.surfaceRenders <= 1, `no React state sits in the per-pose path: ${JSON.stringify({ before, dragged })}`);
  assert.equal((await poseSelect.innerText()).trim(), 'Custom', 'a joint moved by hand releases the named pose');

  // A sliding joint's knob sits ON its pivot, its track runs through it, and it drags to its limit and no further.
  const { lift } = await robot.handles();
  assert.deepEqual([lift.x, lift.y], [lift.pivotX, lift.pivotY], 'a thumb on its track: no arm');
  assert.equal(lift.travel.length, 2);
  const [low, high] = lift.travel;
  const along = ((lift.x - low[0]) * (high[0] - low[0]) + (lift.y - low[1]) * (high[1] - low[1])) / ((high[0] - low[0]) ** 2 + (high[1] - low[1]) ** 2);
  assert.ok(Math.abs(along - 0.1 / 0.3) < 0.01, `the thumb is a third of the way up its 0..0.3 m track: ${along}`);
  assert.ok(Math.hypot(low[0] + (high[0] - low[0]) * along - lift.x, low[1] + (high[1] - low[1]) * along - lift.y) < 0.5, 'and on it');
  await page.mouse.move(...at(lift.x, lift.y));
  await page.mouse.down();
  await page.mouse.move(...at(lift.x + (high[0] - lift.x) * 3, lift.y + (high[1] - lift.y) * 3), { steps: 10 });
  await page.mouse.up();
  await page.waitForFunction(() => window.__cadJointHandles().find(handle => handle.id === 'lift').value === 0.3);

  // A mimic follower moves with its leader: the fingers part symmetrically.
  await robot.type('grip', 0.03, 'm');
  await page.waitForFunction(() => window.__cadJointHandles().find(handle => handle.id === 'grip').value === 0.03);
  const links = await robot.links();
  const [left, right, carriage] = [translation(links.finger_left), translation(links.finger_right), translation(links.carriage)];
  assert.deepEqual([round6(left[1] - carriage[1]), round6(right[1] - carriage[1])], [0.04, -0.04]);
  assert.equal((await robot.stats()).lastPoseWrites, 2, 'the leader and its follower, nothing else');
  assert.equal((await robot.handles()).grip_mirror.value, -0.03, 'the follower’s knob reads its own row');

  // Posing a joint far past the rest box never resizes the ground, and never moves the camera: the
  // arm swung straight up stands well above anything the rest pose reached. (Preview has no file
  // sidebar, so nothing poses there: it draws the robot as it opens.)
  const toolsCamera = await robot.camera();
  await robot.type('shoulder', -90);
  await page.waitForFunction(top => window.__cadStage().bounds.max[2] > top + 0.2, restStage.bounds.max[2]);
  const swung = await page.evaluate(() => window.__cadStage());
  assert.ok(restStage.gridRadius > 0);
  assert.equal(swung.gridRadius, restStage.gridRadius, 'the ground keeps the size the rest pose gave it');
  assert.ok(sameCamera(await robot.camera(), toolsCamera), 'a pose never re-frames');

  // Anywhere else the press is the camera's, and no joint moves.
  const posed = await robot.handles();
  await page.mouse.move(...at(40, surface.height - 70));
  await robot.waitCursor('auto');
  await page.mouse.down();
  await page.mouse.move(...at(160, surface.height - 25), { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(start => window.__cadCamera().position.some((value, index) => Math.abs(value - start[index]) > 1e-3), framed);
  const orbited = await robot.handles();
  assert.deepEqual([orbited.shoulder.value, orbited.lift.value], [posed.shoulder.value, posed.lift.value]);
  assert.notDeepEqual([orbited.shoulder.x, orbited.shoulder.y], [posed.shoulder.x, posed.shoulder.y], 'the knobs ride the model through the orbit');

  // A typed value, a named pose and Default are each where the robot IS from the next frame on: none shows anything between.
  assert.deepEqual(await shoulderFrames(() => robot.type('shoulder', 35), 35), [-90, 35], 'a typed value jumps');
  const choosePose = async (name) => { await poseSelect.click(); await page.locator('[role=menu][aria-label="Pose"]').getByRole('menuitemradio', { name, exact: true }).click(); };
  assert.deepEqual(await shoulderFrames(() => choosePose('raised'), round6(raised)), [35, round6(raised)], 'a named pose jumps');
  assert.equal((await robot.handles()).lift.value, 0.2);
  assert.equal((await robot.handles()).grip.value, 0.03, 'a named pose merges over the pose as it is');
  assert.equal((await poseSelect.innerText()).trim(), 'raised');
  assert.deepEqual(await shoulderFrames(() => choosePose('Default'), round6(home)), [round6(raised), round6(home)], 'Default jumps, back to the SRDF home pose');
  assert.equal((await robot.handles()).grip.value, 0);
  assert.equal((await poseSelect.innerText()).trim(), 'Default');

  // Picking the links alone puts the knobs away and keeps the pose, its controls still in the
  // sidebar; reaching for a control changes neither the tool nor what it picks.
  await robot.type('shoulder', -40);
  assert.equal((await robot.handles()).shoulder.value, -40);
  await robot.pickLinks();
  await page.waitForFunction(() => window.__cadJointHandles().length === 0);
  assert.equal(await robot.jointField('shoulder').isVisible(), true);
  await robot.jointField('shoulder').click();
  await robot.settle();
  assert.deepEqual([await robot.toolNames(), await robot.filter(), await page.evaluate(() => window.__cadJointHandles().length)],
    [SELECT_IN_HAND, 'Selection filter: Links', 0]);
  assert.equal(await robot.jointField('shoulder').inputValue(), '-40°');
  await robot.openPosition();
  const declaredHandles = JSON.parse(PAYLOADS['arm.srdf']).articulation.handles.map(handle => handle.id).sort();
  await page.waitForFunction(expected => JSON.stringify(window.__cadJointHandles().map(handle => handle.id).sort()) === JSON.stringify(expected), declaredHandles);
  assert.equal(round6((await robot.handles()).shoulder.value), -40);

  assert.deepEqual(robot.errors, []);
});

test('Select picks a visual at once; a selection outlives Select; Links shows what the description says and follows what it names', async (t) => {
  const robot = await open(t, 'arm.srdf');
  const { page, pane } = robot;
  await robot.openPosition();
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  // Where things are on screen: a knob sits on the link it drives, and a slider's thumb on its carriage.
  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const spots = await robot.handles();
  const onScreen = handle => [surface.x + handle.x, surface.y + handle.y];
  const nod = spots.nod;
  // The antenna reaches away from the nod pivot; the visor sits on it.
  const antenna = [surface.x + nod.pivotX + (nod.x - nod.pivotX) * 2, surface.y + nod.pivotY + (nod.y - nod.pivotY) * 2];
  const visor = [surface.x + nod.pivotX, surface.y + nod.pivotY];
  // Nothing: the backdrop right of the robot, clear of the file sidebar down the left and the view cube in the corner.
  const backdrop = [surface.x + surface.width - 90, surface.y + surface.height / 2];

  // Picking Position alone, a press on the model picks nothing: a click on it is the camera's.
  await page.mouse.click(...onScreen(spots.lift).map((value, index) => value + (index ? 14 : 14)));
  await robot.settle();
  await robot.pressed([]);
  assert.deepEqual([await robot.toolNames(), await robot.filter()], [SELECT_IN_HAND, 'Selection filter: Position']);
  // Links is the sidebar's, whatever Select picks: on screen picking Position, and picking links.
  assert.equal(await robot.linksPanel().isVisible(), true);
  await robot.pickLinks();
  await robot.linksPanel().waitFor();
  await robot.pressed([]);
  // The tree: a frame-only root is elided, so the base leads it, pinned (no chevron of its own).
  assert.equal(await pane.getByRole('button', { name: 'Select base_footprint', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Collapse base', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).count(), 1);

  // A row is the selection.
  await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).click();
  assert.deepEqual(await robot.toolNames(), SELECT_IN_HAND);
  await robot.pressed(['Select upper_arm']);
  // What is selected is Quick Edit's: a chip for the link, by its name, and no panel comes with it.
  // The chip's card, on a rest of the pointer, is what the description says of the link.
  assert.deepEqual(await robot.chips(), ['upper_arm']);
  assert.deepEqual([await robot.sidebar(), await robot.stack()], [['Links', 'Position controls'], []], 'no Reference panel under Links');
  const card = await robot.chipCard('upper_arm');
  await card.getByText('shoulder', { exact: true }).first().waitFor();
  assert.match(await card.innerText(), /arm/, 'the SRDF planning group of the link');
  assert.match(await card.innerText(), /^upper_arm\s+ID\s+upper_arm\s/, 'headed by the link\'s name, its id the name too');
  // A link's facts are in the card's one face and size, never monospace, in compact rows; its ID, one
  // monospace line, is the reference, not a fact.
  assert.match(await card.locator('[data-chip-id]').evaluate(node => getComputedStyle(node).fontFamily), /mono/i, 'the ID in monospace');
  const faces = await card.locator('[data-info-row]:not(:has([data-chip-id])) *').evaluateAll(nodes => [...new Set(nodes
    .filter(node => !node.childElementCount && node.textContent.trim())
    .map(node => `${getComputedStyle(node).fontFamily} | ${getComputedStyle(node).fontSize}`))]);
  assert.equal(faces.length, 1, `one face and size: ${faces.join(' / ')}`);
  assert.doesNotMatch(faces[0], /mono/i);
  assert.ok((await card.locator('[data-info-row]').first().boundingBox()).height <= 19, 'a compact row');
  // Picking Position alone keeps the selection: Quick Edit still carries it, and the Links stay.
  await robot.openPosition();
  assert.equal(await robot.linksPanel().isVisible(), true, 'Links stay while Select picks Position');
  assert.deepEqual(await robot.chips(), ['upper_arm'], 'the selection stays while Select picks Position');
  // Display is a dropdown over the viewer, never a panel: the sidebar stays as it is, and so does
  // what Select picks; a second press puts it away.
  await robot.openDisplay();
  assert.deepEqual([await robot.sidebar(), await robot.stack()], [['Links', 'Position controls'], []]);
  assert.deepEqual([await robot.toolNames(), await robot.filter()], [SELECT_IN_HAND, 'Selection filter: Position']);
  await robot.displayButton().click();
  await robot.displayPanel().waitFor({ state: 'detached' });

  // A viewport pick, Select picking links: the link is selected on the very next frame (no wait for
  // a double-click that robots do not have), and its row is pressed in the Links panel.
  await robot.pickLinks();
  // The kept selection goes by its chip's X, so nothing is lit before the hover.
  await pane.getByRole('button', { name: 'Remove upper_arm', exact: true }).click();
  await pane.locator('[data-quick-edit-box]').waitFor({ state: 'detached' });
  // (The viewport's own pixels: a page screenshot would also see the toolbar's hover state.)
  const still = (await robot.capture()).data;
  await page.mouse.move(...onScreen(spots.shoulder).map(value => value - 3));
  await page.mouse.move(...onScreen(spots.shoulder));
  // Over a link the pointer says it can be picked; over the backdrop it does not.
  await robot.waitCursor('pointer');
  assert.ok(!(await robot.capture()).data.equals(still), 'a hovered link is lit');
  await page.mouse.move(...backdrop);
  await robot.waitCursor('auto');
  assert.ok((await robot.capture()).data.equals(still), 'and is exactly as it was once the pointer leaves');

  await page.mouse.move(...onScreen(spots.shoulder));
  await page.mouse.down(); await page.mouse.up();
  await robot.settle();
  // A pick selects the visual under the pointer, named by its URDF `name` (cadgen's label for it),
  // and opens its link so the visual's row is on screen under it; its chip is that name.
  assert.deepEqual(await robot.pressedRows(), ['Select upper_arm_shell'], 'selected by the next frame');
  assert.deepEqual(await page.evaluate(() => (({ selectedLinks, selectedPartIds }) => [selectedLinks, selectedPartIds])(window.cadHarness.a.controller.readState())),
    [[], ['upper_arm:v1']]);
  assert.equal(await pane.getByRole('button', { name: 'Collapse upper_arm', exact: true }).getAttribute('aria-expanded'), 'true', 'its link opens');
  assert.deepEqual(await robot.chips(), ['upper_arm_shell']);
  // The shared camera bar provides zoom framing for robots too.
  assert.equal(await pane.getByRole('button', { name: 'Zoom controls', exact: true }).count(), 0);
  assert.equal(await pane.getByLabel('Zoom level percent', { exact: true }).count(), 0);

  // Escape clears the selection; the stack's panels are never its to close.
  await page.mouse.click(...backdrop);
  await robot.pressed([], 'a click on nothing clears');
  await page.mouse.click(...onScreen(spots.lift));
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 1);
  // A visual with no name of its own is named for its geometry.
  await robot.pressed(['Select box']);
  // Shift adds a visual to the selection, from another link too.
  await page.keyboard.down('Shift'); await page.mouse.click(...onScreen(spots.shoulder)); await page.keyboard.up('Shift');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 2);
  await robot.pressed(['Select box', 'Select upper_arm_shell']);
  assert.deepEqual((await page.evaluate(() => window.cadHarness.a.controller.readState())).selectedPartIds.sort(), ['carriage:v1', 'upper_arm:v1']);
  assert.deepEqual((await robot.chips()).sort(), ['box', 'upper_arm_shell'], 'a chip each');
  // A link is still selected by its row, with what the description says about it.
  await pane.getByRole('button', { name: 'Select carriage', exact: true }).click();
  await robot.pressed(['Select carriage']);
  assert.match(await (await robot.chipCard('carriage')).innerText(), /tool/, 'the end effector mounted on the link');
  await page.keyboard.down('Shift'); await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).click(); await page.keyboard.up('Shift');
  await robot.pressed(['Select carriage', 'Select upper_arm']);
  assert.deepEqual((await page.evaluate(() => window.cadHarness.a.controller.readState())).selectedLinks.sort(), ['carriage', 'upper_arm']);
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 0);
  await page.keyboard.press('Escape');
  await robot.settle();
  assert.equal(await robot.linksPanel().isVisible(), true, 'a second Escape leaves Links where it is');

  // Named objects of a link's mesh select themselves, and Shift adds.
  await page.mouse.click(...visor);
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 1);
  await robot.pressed(['Select visor']);
  await page.keyboard.down('Shift'); await page.mouse.click(...antenna); await page.keyboard.up('Shift');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 2);
  await robot.pressed(['Select antenna', 'Select visor']);
  assert.deepEqual((await page.evaluate(() => window.cadHarness.a.controller.readState())).selectedPartIds.sort(), ['head:v1/object/0', 'head:v1/object/1']);
  // Links and knobs together, as the robot opens: a press on a knob is the knob's and picks
  // nothing, so the selection stays; a press on a link anywhere else picks it.
  await robot.filterTo('all');
  await page.waitForFunction(() => window.__cadJointHandles().length > 0);
  const knob = (await robot.handles()).shoulder;
  await page.mouse.click(surface.x + knob.x, surface.y + knob.y);
  await robot.settle();
  await robot.pressed(['Select antenna', 'Select visor'], 'a press on a knob picks nothing');
  await page.mouse.click(...visor);
  await robot.pressed(['Select visor'], 'a press off the knobs picks');

  // What names something else can be followed: a parent link selects it, a mesh path opens it,
  // by the absolute path cadgen resolved for it beside the description.
  await pane.getByRole('button', { name: 'Select head', exact: true }).click();
  const headCard = await robot.chipCard('head');
  await headCard.getByRole('button', { name: 'meshes/head.glb' }).click();
  assert.deepEqual(await page.evaluate(() => window.cadHarness.opened), ['/models/meshes/head.glb']);
  await headCard.getByRole('button', { name: 'base', exact: true }).first().click();
  await robot.pressed(['Select base']);
  // The search box heading Links finds a link by the joint that carries it.
  await pane.getByRole('textbox', { name: 'Filter links', exact: true }).fill('nod');
  await pane.getByRole('list', { name: 'Link search results' }).getByRole('button', { name: 'Select head', exact: true }).waitFor();
  await pane.getByRole('button', { name: 'Clear filter', exact: true }).click();
  await pane.getByRole('list', { name: 'Robot links', exact: true }).waitFor();

  // Host commands: a robot has no faces or edges for a command to select, and says so; clearSelection clears the link selection.
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select(['#f1']).then(() => '', error => error.message));
  assert.match(declined, /no faces or edges for a command to select/);
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  await robot.pressed([]);
  assert.deepEqual(robot.errors, []);
});

test('a reload of the tab brings the pose and the hidden visuals back, and nothing of the tool or the Display dropdown, and both are dropped when the description changed', async (t) => {
  const robot = await open(t, 'arm.urdf');
  const { page, pane } = robot;
  // A link's eye hides its own visuals and leaves its child links; the eye stays crossed out
  // while they are hidden, and Reveal draws exactly what was there.
  const shown = (await robot.capture()).data;
  await pane.getByRole('button', { name: 'Hide upper_arm', exact: true }).click();
  await pane.getByRole('button', { name: 'Reveal upper_arm', exact: true }).waitFor();
  await robot.settled();
  assert.ok(!(await robot.capture()).data.equals(shown), 'the hidden visual is not drawn');
  await pane.getByRole('button', { name: 'Reveal upper_arm', exact: true }).click();
  // Off the row, which lights its link while the pointer is on it.
  const surface = await robot.surface();
  await page.mouse.move(surface.x + surface.width - 90, surface.y + surface.height / 2);
  await robot.settled();
  assert.ok((await robot.capture()).data.equals(shown), 'and Reveal draws it again');
  await pane.getByRole('button', { name: 'Hide upper_arm', exact: true }).click();
  await pane.getByRole('button', { name: 'Reveal upper_arm', exact: true }).waitFor();
  await robot.openPosition();
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  await robot.type('shoulder', 25);
  await robot.type('lift', 0.2, 'm');
  // The last write lands in the record although it was never rendered: the record reads the pose when it is written.
  await robot.type('nod', 12);
  // The page goes with its Display settings open: they are not a tool, and the tool is not saved either.
  // The harness's unmount and remount keep the tab's record, as a reload does (the web's pagehide
  // unmounts the viewer, and its sessionStorage outlives the page). Leaving the file for another, or
  // for the home, drops its view instead: `cad-viewer/CadViewerFileViews.test.tsx`.
  await robot.openDisplay();
  await page.evaluate(() => window.cadHarness.mounted(false));
  // It has gone before it comes back: a busy React can take the two calls in one render, and a view
  // that never went keeps its sidebar open, for the press on its tile to close.
  await pane.getByRole('group', { name: 'File sidebar' }).waitFor({ state: 'detached' });
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(record => record?.renderer?.pose?.value?.jointValues?.nod === 12));
  const record = await page.evaluate(() => window.cadHarness.state.renderers[JSON.stringify(['/models/arm.urdf', 'robot'])]);
  assert.deepEqual([record.renderer.pose.value.jointValues.shoulder, record.renderer.pose.value.jointValues.lift], [25, 0.2]);
  assert.deepEqual(Object.keys(record.renderer).sort(), ['pose', 'visibility'], 'two slices: the pose and the hidden visuals, and no selection or tree');
  assert.deepEqual(record.renderer.visibility.value, { hiddenPartIds: ['upper_arm:v1'] });
  assert.equal('tool' in record, false, 'the view keeps no tool');
  assert.match(record.renderer.pose.signature, /arm\.urdf-1$/);
  assert.equal(record.renderer.visibility.signature, record.renderer.pose.signature, 'both against the description');
  await page.evaluate(() => window.cadHarness.mounted(true));
  // The tool is never saved, nor what it picks: the reloaded file opens in Select picking links and
  // knobs, Display shut, no section open.
  await robot.openSection('Links');
  assert.deepEqual([await robot.toolNames(), await robot.filter()], [SELECT_IN_HAND, 'Selection filter: everything']);
  await pane.getByRole('button', { name: 'Reveal upper_arm', exact: true }).waitFor();
  assert.equal(await robot.displayPanel().count(), 0, 'it comes back with Display shut');
  await robot.openSection('Position');
  await robot.jointField('shoulder').waitFor();
  assert.deepEqual([await robot.jointField('shoulder').inputValue(), await robot.jointField('lift', 'm').inputValue(), await robot.jointField('nod').inputValue()], ['25°', '0.2 m', '12°']);
  await page.waitForFunction(() => window.__cadJointHandles?.().find(handle => handle.id === 'shoulder')?.value === 25);
  const links = await robot.links();
  assert.equal(round6(translation(links.carriage)[2]), 0.35, 'and the robot on screen is in that pose');

  // A record written against another revision is not restored. (A new revision behind the mounted robot
  // keeps its pose only while its controls and named poses are unchanged: `RobotTools.test.tsx`.)
  await page.evaluate(() => window.cadHarness.mounted(false));
  await pane.getByRole('group', { name: 'File sidebar' }).waitFor({ state: 'detached' });
  revision += 1;
  t.after(() => { revision = 1; });
  await page.evaluate(() => window.cadHarness.a.client.refresh());
  await page.evaluate(() => window.cadHarness.mounted(true));
  await robot.openSection('Position');
  await robot.jointField('shoulder').waitFor();
  assert.deepEqual([await robot.jointField('shoulder').inputValue(), await robot.jointField('lift', 'm').inputValue()], ['0°', '0 m'], 'a pose belongs to the description it was made on');
  await robot.openSection('Links');
  await pane.getByRole('button', { name: 'Hide upper_arm', exact: true }).waitFor();
  assert.equal(await pane.getByRole('button', { name: 'Reveal upper_arm', exact: true }).count(), 0, 'and so do its hidden visuals');
  assert.deepEqual(robot.errors, []);
});

test('Preview draws the robot as it opens, and leaving it finds the tools view as it was: the pose, the hidden visual and the selection', async (t) => {
  const robot = await open(t, 'arm.urdf');
  const { page, pane } = robot;
  const opening = await robot.links();
  const away = async () => { const surface = await robot.surface(); await page.mouse.move(surface.x + surface.width - 90, surface.y + surface.height / 2); };
  const enterPreview = async () => { await robot.preview(true); await robot.settled(); };
  const exitPreview = () => robot.preview(false);
  // Preview opens still (Orbit off): the robot as Preview draws a file opened afresh.
  await away();
  await enterPreview();
  const authored = (await robot.capture()).data;
  await exitPreview();

  // Work in the tools view: the shoulder turned, the base's visual hidden, the upper arm picked.
  await robot.type('shoulder', 25);
  await page.waitForFunction(() => window.__robotLinks().some(({ link }) => link === 'upper_arm'));
  const posed = await robot.links();
  assert.notDeepEqual(posed.upper_arm, opening.upper_arm, 'the shoulder turned the upper arm');
  await robot.openSection('Links');
  await pane.getByRole('button', { name: 'Hide base', exact: true }).click();
  await pane.getByRole('button', { name: 'Reveal base', exact: true }).waitFor();
  await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).click();
  await robot.pressed(['Select upper_arm']);

  // Preview draws none of it: the opening pose, every visual, nothing lit.
  await away();
  await enterPreview();
  assert.deepEqual(await robot.links(), opening, 'Preview poses the robot as it opens');
  assert.ok((await robot.capture()).data.equals(authored), 'Preview draws the robot as it opens');
  // Preview has no file sidebar (a robot has no routine, so no playbar either), and no navbar: its own
  // bar holds only the file's name, its settings and the way out.
  assert.equal(await pane.locator('[data-file-sidebar-room]').isHidden(), true, 'no file sidebar in Preview');
  assert.equal(await pane.locator('[data-preview-playbar]').count(), 0, 'no playbar for a file with no routine');
  assert.equal(await pane.locator('[data-viewer-navbar]').count(), 0, 'no navbar in Preview');
  assert.deepEqual(await pane.locator('[data-preview-bar] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['Preview settings', 'Exit preview']);

  // Leaving finds the tools view's work as it was left.
  await exitPreview();
  assert.deepEqual(await robot.links(), posed, 'the pose comes back');
  await robot.pressed(['Select upper_arm'], 'the selection comes back');
  assert.equal(await pane.getByRole('button', { name: 'Reveal base', exact: true }).count(), 1, 'the base is still hidden');
  assert.deepEqual(robot.errors, []);
});

test('a pose step costs the same on a long chain: one matrix, no component', async (t) => {
  const robot = await open(t, 'chain.urdf');
  const { page, pane } = robot;
  await robot.openPosition();
  await robot.openSection('Position');
  await page.waitForFunction(count => window.__cadJointHandles?.().length === count, CHAIN_LINKS - 1);
  await robot.settled();
  // What a step costs is counted, never timed: the matrices it writes and the renders it causes.
  // (Posing through React state and a re-placed part list rendered the renderer every step.)
  // The file sidebar, its 29-joint Position section with it, floats over the chain's root on this
  // viewport. This measures what a pose step costs, not the layout, so the sidebar is kept out of
  // the pointer's way (still rendered: its slider rows are what a step must not re-render).
  await page.addStyleTag({ content: '[data-testid="one"] [data-file-sidebar-room] { visibility: hidden !important; }' });
  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const knob = (await robot.handles()).j0;
  const radius = Math.hypot(knob.x - knob.pivotX, knob.y - knob.pivotY), bearing = Math.atan2(knob.y - knob.pivotY, knob.x - knob.pivotX);
  await page.mouse.move(surface.x + knob.x, surface.y + knob.y);
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-joint-handle-label]')?.textContent.startsWith('j0'));
  await page.mouse.down();
  const before = await robot.stats();
  const STEPS = 30;
  for (let step = 1; step <= STEPS; step += 1) {
    const angle = bearing + Math.sin((step / STEPS) * Math.PI * 2) * 0.6;
    await page.mouse.move(surface.x + knob.pivotX + radius * Math.cos(angle), surface.y + knob.pivotY + radius * Math.sin(angle));
    await robot.settle();
  }
  await page.mouse.up();
  const moved = await robot.stats();
  // The root joint carries all 29 links below it, and still one matrix is written per step.
  assert.equal(moved.lastPoseWrites, 1, 'a step writes the one joint that moved');
  assert.ok(moved.poseWrites - before.poseWrites >= STEPS * 0.8 && moved.poseWrites - before.poseWrites <= STEPS, JSON.stringify({ before, moved }));
  assert.ok(moved.surfaceRenders - before.surfaceRenders <= 2, `no component of the renderer renders for a pose step: ${JSON.stringify({ before, moved })}`);
  assert.deepEqual(robot.errors, []);
});
