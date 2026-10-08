import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { writeGlb } from '@text-to-cad/core/glb/writeGlb.js';

// The robot renderer end to end in a real browser, over inline fixtures made of
// primitives: a URDF, the SRDF paired with it (a "home" state, a named pose, an end
// effector), an SDF, a long chain, and the files that must raise an alert instead of a
// robot. Scene, pose store and handle adapter have unit tests; these are the flows a
// person actually uses.

const box = (size, xyz, rgba) => `<visual><origin xyz="${xyz}"/><geometry><box size="${size}"/></geometry><material name="m${rgba.replaceAll(' ', '')}"><color rgba="${rgba}"/></material></visual>`;
const limit = (lower, upper) => `<limit lower="${lower}" upper="${upper}" effort="1" velocity="1"/>`;
const ARM_URDF = `<?xml version="1.0"?>
<robot name="arm">
  <link name="base_footprint"/>
  <link name="base">${box('0.4 0.4 0.1', '0 0 0.05', '0.3 0.3 0.35 1')}</link>
  <link name="upper_arm">${box('0.5 0.08 0.08', '0.25 0 0', '0.9 0.5 0.1 1')}</link>
  <link name="carriage">${box('0.1 0.1 0.1', '0 0 0', '0.1 0.4 0.9 1')}</link>
  <link name="camera">${box('0.06 0.06 0.06', '0 0 0', '0.1 0.7 0.3 1')}</link>
  <link name="finger_left">${box('0.02 0.02 0.08', '0 0 0.09', '0.8 0.8 0.2 1')}</link>
  <link name="finger_right">${box('0.02 0.02 0.08', '0 0 0.09', '0.8 0.8 0.2 1')}</link>
  <link name="head"><visual><geometry><mesh filename="meshes/head.glb" scale="0.001 0.001 0.001"/></geometry></visual></link>
  <joint name="footprint" type="fixed"><parent link="base_footprint"/><child link="base"/></joint>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="upper_arm"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/>${limit(-1.5708, 1.5708)}</joint>
  <joint name="lift" type="prismatic"><parent link="base"/><child link="carriage"/><origin xyz="-0.15 0.15 0.15"/><axis xyz="0 0 1"/>${limit(0, 0.3)}</joint>
  <joint name="camera_mount" type="fixed"><parent link="base"/><child link="camera"/><origin xyz="0.15 -0.15 0.13"/></joint>
  <joint name="grip" type="prismatic"><parent link="carriage"/><child link="finger_left"/><origin xyz="0 0.01 0"/><axis xyz="0 1 0"/>${limit(0, 0.04)}</joint>
  <joint name="grip_mirror" type="prismatic"><parent link="carriage"/><child link="finger_right"/><origin xyz="0 -0.01 0"/><axis xyz="0 1 0"/>${limit(-0.04, 0)}<mimic joint="grip" multiplier="-1"/></joint>
  <joint name="nod" type="revolute"><parent link="base"/><child link="head"/><origin xyz="-0.15 -0.15 0.14"/><axis xyz="0 1 0"/>${limit(-1, 1)}</joint>
</robot>
`;
const ARM_SRDF = `<?xml version="1.0"?>
<robot name="arm">
  <group name="arm"><joint name="shoulder"/><joint name="lift"/></group>
  <group name="gripper"><joint name="grip"/></group>
  <end_effector name="tool" parent_link="carriage" group="gripper" parent_group="arm"/>
  <group_state name="home" group="arm"><joint name="shoulder" value="-0.5"/><joint name="lift" value="0.1"/></group_state>
  <group_state name="raised" group="arm"><joint name="shoulder" value="-1.0"/><joint name="lift" value="0.2"/></group_state>
</robot>
`;
const SWING_SDF = `<?xml version="1.0"?>
<sdf version="1.9"><world name="lab"><light name="sun" type="directional"/><model name="swing">
  <link name="base"><visual name="v"><pose>0 0 0.05 0 0 0</pose><geometry><box><size>0.4 0.4 0.1</size></box></geometry></visual></link>
  <link name="arm"><pose relative_to="hinge">0.05 0 0 0 0 0</pose><visual name="v"><pose>0.25 0 0 0 0 0</pose><geometry><box><size>0.5 0.08 0.06</size></box></geometry></visual></link>
  <joint name="hinge" type="revolute"><pose relative_to="base">0 0 0.2 0 0 0</pose><parent>base</parent><child>arm</child><axis><xyz>0 1 0</xyz><limit><lower>-1.2</lower><upper>1.2</upper></limit></axis></joint>
</model></world></sdf>`;
// A chain long enough that a per-pose cost proportional to the robot would show.
const CHAIN_LINKS = 30;
const CHAIN_URDF = `<?xml version="1.0"?>\n<robot name="chain">\n${Array.from({ length: CHAIN_LINKS }, (_, index) => `  <link name="l${index}">${box('0.1 0.04 0.04', '0.05 0 0', '0.5 0.5 0.55 1')}</link>`).join('\n')}
${Array.from({ length: CHAIN_LINKS - 1 }, (_, index) => `  <joint name="j${index}" type="revolute"><parent link="l${index}"/><child link="l${index + 1}"/><origin xyz="0.1 0 0"/><axis xyz="0 ${index % 2} ${1 - (index % 2)}"/>${limit(-1, 1)}</joint>`).join('\n')}\n</robot>\n`;
const GONE_URDF = `<?xml version="1.0"?><robot name="gone"><link name="base"><visual><geometry><mesh filename="meshes/absent.stl"/></geometry></visual></link></robot>`;
const LONELY_SRDF = `<?xml version="1.0"?><robot name="nobody"><group name="arm"><joint name="shoulder"/></group></robot>`;

function glbBox([x, y, z], [sx, sy, sz]) {
  const [a, b, c] = [x + sx, y + sy, z + sz];
  const corners = [[x, y, z], [a, y, z], [a, b, z], [x, b, z], [x, y, c], [a, y, c], [a, b, c], [x, b, c]];
  const faces = [[0, 2, 1, 0, 3, 2], [4, 5, 6, 4, 6, 7], [0, 1, 5, 0, 5, 4], [2, 3, 7, 2, 7, 6], [1, 2, 6, 1, 6, 5], [3, 0, 4, 3, 4, 7]];
  return new Float32Array(faces.flat().flatMap(index => corners[index]));
}
// A link mesh with two NAMED objects: the visor sits on the nod joint's pivot, the antenna stands up from it
// (a GLB is Y-up, so that is the robot's Z).
const headGlb = writeGlb({ primitives: [
  { name: 'visor', node: 'visor', positions: glbBox([-0.03, -0.03, -0.03], [0.06, 0.06, 0.06]), color: '#d02020' },
  { name: 'antenna', node: 'antenna', positions: glbBox([-0.01, 0.04, -0.01], [0.02, 0.3, 0.02]), color: '#e8e8e8' },
] }, { preset: 'export' });
const FILES = {
  'arm.urdf': ARM_URDF, 'arm.srdf': ARM_SRDF, 'swing.sdf': SWING_SDF, 'chain.urdf': CHAIN_URDF,
  'gone.urdf': GONE_URDF, 'lonely.srdf': LONELY_SRDF, 'meshes/head.glb': Buffer.from(headGlb.buffer, headGlb.byteOffset, headGlb.byteLength),
};

// The harness renders its panes at a fixed CSS size; the spec draws them smaller, so a software
// GL (CI's SwiftShader) has fewer pixels to fill and a capture fewer to read.
const HARNESS_SIZE = '<style>#root > div { width: 800px !important; height: 500px !important; }</style>';

let server, browser, temporary;
// Bumped by a test to publish a new revision of every description.
let revision = 1;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-robot-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const [, root, ...rest] = url.pathname.split('/');
    const name = rest.join('/');
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      const entry = file => ({ kind: file.split('.').pop(), file: `/models/${file}`, url: `/${file}`, hash: `${root}-${file}-${revision}`, bytes: FILES[file].length });
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ entries: Object.keys(FILES).filter(file => !file.startsWith('meshes/'))
        .map(file => (file === 'arm.srdf' ? { ...entry(file), relations: { urdf: entry('arm.urdf') } } : entry(file))) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' }));
    } else if (FILES[name] ?? FILES[url.pathname.slice(1)]) { response.end(FILES[name] ?? FILES[url.pathname.slice(1)]); }
    else if (/\.(woff2|ttf|stl|glb)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><title>Host</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1') ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  if (temporary) await rm(temporary, { recursive: true, force: true });
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
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`);
  const pane = page.getByTestId('one');
  const tools = pane.getByRole('group', { name: 'Interaction tools' });
  const robot = {
    page, pane, tools, errors,
    tool: name => tools.getByRole('button', { name, exact: true }),
    toolNames: () => tools.getByRole('button').evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    handles: async () => Object.fromEntries((await page.evaluate(() => window.__cadJointHandles())).map(handle => [handle.id, handle])),
    links: async () => Object.fromEntries((await page.evaluate(() => window.__robotLinks())).map(({ link, matrixWorld }) => [link, matrixWorld])),
    camera: () => page.evaluate(() => { const { position, target, zoom } = window.__cadCamera(); return [...position, ...target, zoom]; }),
    stats: () => page.evaluate(() => window.__robotPoseStats()),
    // Whether the Position tool's icon carries its dot: the pose is off its default.
    posedMark: () => tools.getByRole('button', { name: 'Position', exact: true }).locator('[data-position-custom]').count(),
    jointField: (name, unit = 'deg') => page.getByLabel(`${name} value in ${unit}`, { exact: true }),
    async openPosition() {
      await robot.tool('Position').click();
    },
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
    async type(name, value, unit) { await robot.openPosition(); await robot.jointField(name, unit).fill(String(value)); await robot.jointField(name, unit).press('Enter'); },
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
    // Display: its button at the navbar's right end, before Preview.
    displayButton: () => pane.locator('[data-view-controls]').getByRole('button', { name: 'Display', exact: true }),
    // Display's settings: a dropdown from the navbar, portaled out of the viewer.
    displayPanel: () => page.locator('[data-display-popover]'),
    // The tool stack's panels on screen, top to bottom, by their accessible names.
    stack: () => pane.locator('[data-cad-tool-stack] [data-tool-panel]').evaluateAll(panels => panels
      .filter(panel => panel.getClientRects().length > 0).map(panel => panel.getAttribute('aria-label'))),
    linksPanel: () => pane.locator('[data-tool-panel][aria-label="Links"]'),
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
    // A robot opens in Select, so its Links panel is in the tool stack before anything is located.
    await robot.linksPanel().waitFor();
    await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
    await robot.settled();
  }
  return robot;
}
// Orbit controls re-derive the camera from its spherical form on a repaint: rounding, not motion.
const sameCamera = (a, b) => a.every((value, index) => Math.abs(value - b[index]) < 1e-9);
const round6 = value => Math.round(value * 1e6) / 1e6;
const translation = matrix => [matrix[3], matrix[7], matrix[11]];

test('a robot can enter Position with sidebar controls: knobs drag joints, the camera keeps every other press, every pose write is a jump, and a pose step renders no component', async (t) => {
  const robot = await open(t, 'arm.srdf');
  const { page, pane } = robot;
  const home = (-0.5 * 180) / Math.PI, raised = (-1.0 * 180) / Math.PI;

  // The robot opens in Select; Position is its explicit tool, and shows its panel in the stack.
  await robot.openPosition();
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  assert.deepEqual(await robot.toolNames(), ['Select:false', 'Position:true']);
  assert.equal(await robot.tool('Draw').count(), 0, 'Draw is a STEP tool; a robot description has none');
  assert.equal(await robot.tool('Preview').count(), 0, 'Preview is no toolbar tool');
  assert.equal(await pane.getByRole('button', { name: 'Preview', exact: true }).count(), 1, 'it is the viewer’s corner button, for a robot as for any 3D file');
  // Display is the button beside Preview, shut as the file opens.
  assert.equal(await robot.displayPanel().count(), 0, 'Display is never where a file opens');
  assert.equal(await pane.getByRole('tab').count(), 0, 'no tabs');
  assert.deepEqual(await robot.stack(), ['Position controls']);
  // Headed "Position", with its Reset and the fold chevron in the heading.
  const positionHeading = robot.position().locator('[data-tool-panel-heading]');
  assert.equal((await positionHeading.getByRole('heading').innerText()).trim(), 'Position');
  assert.equal(await positionHeading.getByRole('button', { name: 'Reset', exact: true }).count(), 1);
  // It does not fold: its heading is Reset, then the X that puts Position down.
  assert.deepEqual(await positionHeading.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))), ['Reset', 'Close position']);
  await robot.openPosition();
  // One knob per joint a person can drive: no fixed joint, no mimic follower. The follower has no slider either.
  assert.deepEqual(Object.keys(await robot.handles()).sort(), ['grip', 'lift', 'nod', 'shoulder']);
  assert.equal(await robot.jointField('grip_mirror', 'm').count(), 0);
  assert.equal(await robot.jointField('camera_mount').count(), 0);
  // The SRDF's "home" state is the pose the robot opens in, and the Position panel's Pose row
  // names it: a label and its dropdown side by side.
  assert.equal(round6((await robot.handles()).shoulder.value), round6(home));
  assert.equal((await robot.handles()).lift.value, 0.1);
  const position = robot.position();
  const poseSelect = position.getByRole('combobox', { name: 'Pose', exact: true });
  const [poseLabel, poseBox, panelBody] = await Promise.all([position.getByText('Pose', { exact: true }).boundingBox(), poseSelect.boundingBox(),
    position.locator('[data-tool-panel-body]').boundingBox()]);
  assert.ok(poseLabel.x + poseLabel.width <= poseBox.x, 'the label is beside its dropdown');
  assert.ok(Math.abs((poseLabel.y + poseLabel.height / 2) - (poseBox.y + poseBox.height / 2)) <= 2, 'on one line');
  assert.ok(panelBody.x + panelBody.width - (poseBox.x + poseBox.width) <= 12, 'and the dropdown runs to the row\'s end');
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
  // The Position icon's dot (the pose is off its default) is the one thing a step may render, and
  // only as the pose leaves or reaches its default: counted, never per step.
  let flips = 0, marked = await robot.posedMark();
  for (let step = 1; step <= 9; step += 1) {
    const angle = bearing + (step * Math.PI) / 18;
    await page.mouse.move(...at(shoulder.pivotX + radius * Math.cos(angle), shoulder.pivotY + radius * Math.sin(angle)));
    await robot.settle();
    const now = await robot.posedMark();
    if (now !== marked) { flips += 1; marked = now; }
  }
  assert.ok(flips <= 1, 'a drag one way leaves the default once at most');
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
  assert.ok(dragged.surfaceRenders - before.surfaceRenders <= 1 + flips, `no React state sits in the per-pose path: ${JSON.stringify({ before, dragged, flips })}`);
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

  // A mimic follower moves with its master: the fingers part symmetrically.
  await robot.type('grip', 0.03, 'm');
  await page.waitForFunction(() => window.__cadJointHandles().find(handle => handle.id === 'grip').value === 0.03);
  const links = await robot.links();
  const [left, right, carriage] = [translation(links.finger_left), translation(links.finger_right), translation(links.carriage)];
  assert.deepEqual([round6(left[1] - carriage[1]), round6(right[1] - carriage[1])], [0.04, -0.04]);
  assert.equal((await robot.stats()).lastPoseWrites, 2, 'the master and its follower, nothing else');

  // Posing a joint far past the rest box never resizes the grid or the studio floor, and never
  // moves the camera: the arm swung straight up stands well above anything the rest pose reached.
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ floor: { enabled: true } }));
  await page.waitForFunction(() => window.__cadStage()?.studioGround);
  const floored = await page.evaluate(() => window.__cadStage());
  await robot.type('shoulder', -90);
  await page.waitForFunction(top => window.__cadStage().bounds.max[2] > top + 0.1, floored.bounds.max[2]);
  const swung = await page.evaluate(() => window.__cadStage());
  assert.ok(swung.bounds.max[2] > restStage.bounds.max[2] + 0.2, `past the rest box: ${JSON.stringify([restStage.bounds, swung.bounds])}`);
  assert.ok(restStage.gridRadius > 0);
  assert.equal(swung.gridRadius, restStage.gridRadius, 'the ground keeps the size the rest pose gave it');
  assert.deepEqual(swung.studioGround, floored.studioGround, 'so does the studio floor');
  assert.ok(sameCamera(await robot.camera(), framed), 'a pose never re-frames');

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

  // A typed value, a named pose and Reset are each where the robot IS from the next frame on: none shows anything between.
  assert.deepEqual(await shoulderFrames(() => robot.type('shoulder', 35), 35), [-90, 35], 'a typed value jumps');
  const choosePose = async (name) => { await poseSelect.click(); await page.getByRole('option', { name, exact: true }).click(); };
  assert.deepEqual(await shoulderFrames(() => choosePose('raised'), round6(raised)), [35, round6(raised)], 'a named pose jumps');
  assert.equal((await robot.handles()).lift.value, 0.2);
  assert.equal((await robot.handles()).grip.value, 0.03, 'a named pose merges over the pose as it is');
  assert.equal((await poseSelect.innerText()).trim(), 'raised');
  assert.deepEqual(await shoulderFrames(() => position.getByRole('button', { name: 'Reset', exact: true }).click(), round6(home)), [round6(raised), round6(home)], 'Reset jumps, back to the SRDF home pose');
  assert.equal((await robot.handles()).grip.value, 0);
  assert.equal((await poseSelect.innerText()).trim(), 'Default');

  // Switching tools preserves the pose; the tool brings its panel back.
  await robot.type('shoulder', -40);
  assert.equal((await robot.handles()).shoulder.value, -40);
  await robot.tool('Select').click();
  await page.waitForFunction(() => window.__cadJointHandles().length === 0);
  assert.equal(await robot.jointField('shoulder').isVisible(), false);
  await robot.tool('Position').click();
  await page.waitForFunction(() => window.__cadJointHandles().length === 4);
  assert.equal(round6((await robot.handles()).shoulder.value), -40);
  assert.equal(await robot.jointField('shoulder').isVisible(), true);

  assert.deepEqual(robot.errors, []);
});

test('Select picks links at once; a selection lives only under Select; Links shows what the description says and follows what it names', async (t) => {
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
  // Nothing: the backdrop right of the robot, clear of the tool stack down the left and the view cube in the corner.
  const backdrop = [surface.x + surface.width - 90, surface.y + surface.height / 2];

  // Under Position the model picks nothing: a click on it is the camera's.
  await page.mouse.click(...onScreen(spots.lift).map((value, index) => value + (index ? 14 : 14)));
  await robot.settle();
  assert.deepEqual(await robot.toolNames(), ['Select:false', 'Position:true']);
  // Links is Select's: under Position it is off screen, and Select brings it.
  assert.equal(await robot.linksPanel().isVisible(), false);
  await robot.tool('Select').click();
  await robot.linksPanel().waitFor();
  await robot.pressed([]);
  // The tree: a frame-only root is elided, so the base leads it, pinned (no chevron of its own).
  assert.equal(await pane.getByRole('button', { name: 'Select base_footprint', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Collapse base', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).count(), 1);

  // A row is the selection.
  await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).click();
  assert.deepEqual(await robot.toolNames(), ['Select:true', 'Position:false']);
  await robot.pressed(['Select upper_arm']);
  const reference = pane.getByRole('region', { name: 'Reference details', exact: true });
  await reference.getByText('shoulder', { exact: true }).first().waitFor();
  assert.match(await reference.innerText(), /arm/, 'the SRDF planning group of the link');
  // The Reference is the next panel of the stack, under Links, headed by the link's name.
  assert.deepEqual(await robot.stack(), ['Links', 'Reference details']);
  assert.equal(await reference.getByRole('heading').innerText(), 'upper_arm');
  const [links, pinned] = await Promise.all([robot.linksPanel().boundingBox(), reference.boundingBox()]);
  assert.ok(pinned.y >= links.y + links.height, 'under Links');
  assert.equal(pinned.width, links.width, 'the one width, until a person sizes either');
  // A link's facts are in the panel's one face and size, never monospace, in compact rows.
  const faces = await reference.locator('[data-tool-panel-body] *').evaluateAll(nodes => [...new Set(nodes
    .filter(node => !node.childElementCount && node.textContent.trim())
    .map(node => `${getComputedStyle(node).fontFamily} | ${getComputedStyle(node).fontSize}`))]);
  assert.equal(faces.length, 1, `one face and size: ${faces.join(' / ')}`);
  assert.doesNotMatch(faces[0], /mono/i);
  assert.ok((await reference.locator('[data-info-row]').first().boundingBox()).height <= 19, 'a compact row');
  // Links closes by the X at its filter row's end, and the Reference moves up into its place;
  // Select, pressed while it is the tool, opens Links again with its selection.
  const linksPanel = robot.linksPanel();
  await linksPanel.locator('[data-slot=tree-filter]').getByRole('button', { name: 'Close links', exact: true }).click();
  await linksPanel.waitFor({ state: 'hidden' });
  assert.deepEqual(await robot.stack(), ['Reference details']);
  assert.ok((await reference.boundingBox()).y < pinned.y, 'the Reference moves up into its place');
  await robot.tool('Select').click();
  await linksPanel.waitFor();
  await robot.pressed(['Select upper_arm'], 'the tree kept its selection while closed');
  // Leaving Select drops the selection, in the tree and the viewport alike.
  await robot.tool('Position').click();
  await robot.waitPressed(0);
  assert.equal(await robot.linksPanel().isVisible(), false, 'and Position shows its own panel instead');
  // Display is a dropdown over the viewer, never a panel in the stack: Position's panel stays, and
  // Position stays the tool; a second press puts it away.
  await robot.displayButton().click();
  await robot.displayPanel().waitFor();
  assert.deepEqual(await robot.stack(), ['Position controls']);
  assert.deepEqual(await robot.toolNames(), ['Select:false', 'Position:true']);
  await robot.displayButton().click();
  await robot.displayPanel().waitFor({ state: 'detached' });

  // A viewport pick under Select: the link is selected on the very next frame (no wait for
  // a double-click that robots do not have), and its row is pressed in the Links panel.
  await robot.tool('Select').click();
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
  assert.deepEqual(await robot.pressedRows(), ['Select upper_arm'], 'selected by the next frame');
  assert.deepEqual((await page.evaluate(() => window.cadHarness.a.controller.readState())).selectedLinks, ['upper_arm']);
  // The shared camera bar provides zoom framing for robots too.
  assert.equal(await pane.getByRole('button', { name: 'Zoom controls', exact: true }).count(), 0);
  assert.equal(await pane.getByLabel('Zoom level percent', { exact: true }).count(), 0);

  // Escape clears the selection; the stack's panels are never its to close.
  await page.mouse.click(...backdrop);
  await robot.pressed([], 'a click on nothing clears');
  await page.mouse.click(...onScreen(spots.lift));
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 1);
  await robot.pressed(['Select carriage']);
  assert.match(await reference.innerText(), /tool/, 'the end effector mounted on the link');
  // Shift adds a link to the selection, as it adds a named object.
  await page.keyboard.down('Shift'); await page.mouse.click(...onScreen(spots.shoulder)); await page.keyboard.up('Shift');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 2);
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

  // What names something else can be followed: a parent link selects it, a mesh path opens it,
  // by its absolute path beside the description.
  await pane.getByRole('button', { name: 'Select head', exact: true }).click();
  await reference.getByRole('button', { name: 'meshes/head.glb' }).click();
  assert.deepEqual(await page.evaluate(() => window.cadHarness.opened), ['/models/meshes/head.glb']);
  await reference.getByRole('button', { name: 'base', exact: true }).first().click();
  await robot.pressed(['Select base']);
  // The filter finds a link by the joint that carries it.
  await pane.getByRole('textbox', { name: 'Filter links', exact: true }).fill('nod');
  await pane.getByRole('list', { name: 'Link search results' }).getByRole('button', { name: 'Select head', exact: true }).waitFor();
  await pane.getByRole('textbox', { name: 'Filter links', exact: true }).fill('');

  // Host commands: a robot has no references to select, and says so; clearSelection clears the link selection.
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select(['#f1']).then(() => '', error => error.message));
  assert.match(declined, /no CAD references to select/);
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  await robot.pressed([]);
  assert.deepEqual(robot.errors, []);
});

test('a reload of the tab brings the pose back, and nothing of the tool or the Display dropdown, and a pose is dropped when the description changed', async (t) => {
  const robot = await open(t, 'arm.urdf');
  const { page, pane } = robot;
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
  await robot.displayButton().click();
  await robot.displayPanel().waitFor();
  await page.evaluate(() => window.cadHarness.mounted(false));
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(record => record?.renderer?.pose?.value?.jointValues?.nod === 12));
  const record = await page.evaluate(() => window.cadHarness.state.renderers[JSON.stringify(['/models/arm.urdf', 'robot'])]);
  assert.deepEqual([record.renderer.pose.value.jointValues.shoulder, record.renderer.pose.value.jointValues.lift], [25, 0.2]);
  assert.deepEqual(Object.keys(record.renderer), ['pose'], 'one slice: the pose, and no selection or tree');
  assert.equal('tool' in record, false, 'the view keeps no tool');
  assert.match(record.renderer.pose.signature, /arm\.urdf-1$/);
  await page.evaluate(() => window.cadHarness.mounted(true));
  // The tool is never saved: the reloaded file opens in Select, Display shut.
  await robot.linksPanel().waitFor();
  assert.deepEqual(await robot.toolNames(), ['Select:true', 'Position:false']);
  assert.equal(await robot.displayPanel().count(), 0, 'it comes back with Display shut');
  await robot.openPosition();
  await robot.jointField('shoulder').waitFor();
  assert.deepEqual([await robot.jointField('shoulder').inputValue(), await robot.jointField('lift', 'm').inputValue(), await robot.jointField('nod').inputValue()], ['25°', '0.2 m', '12°']);
  assert.deepEqual(await robot.toolNames(), ['Select:false', 'Position:true'], 'Position takes up the restored pose');
  const links = await robot.links();
  assert.equal(round6(translation(links.carriage)[2]), 0.35, 'and the robot on screen is in that pose');

  // A record written against another revision is not restored. (A new revision behind the mounted robot
  // keeps its pose only while its joints and named poses are unchanged: `RobotTools.test.tsx`.)
  await page.evaluate(() => window.cadHarness.mounted(false));
  revision += 1;
  t.after(() => { revision = 1; });
  await page.evaluate(() => window.cadHarness.a.client.refresh());
  await page.evaluate(() => window.cadHarness.mounted(true));
  await robot.openPosition();
  await robot.jointField('shoulder').waitFor();
  assert.deepEqual([await robot.jointField('shoulder').inputValue(), await robot.jointField('lift', 'm').inputValue()], ['0°', '0 m'], 'a pose belongs to the description it was made on');
  assert.deepEqual(robot.errors, []);
});

test('an SDF is the same robot with a section of its own; a snapshot depicts the whole file', async (t) => {
  const robot = await open(t, 'swing.sdf');
  const { page, pane } = robot;
  await robot.openPosition();
  await page.waitForFunction(() => window.__cadJointHandles?.().length === 1);
  assert.deepEqual(await robot.toolNames(), ['Select:false', 'Position:true']);
  // The same panels as any robot, whatever the format on disk: SDF is a panel of Select's, under
  // Links (what the description says about itself sits with its links), folded until opened.
  assert.deepEqual(await robot.stack(), ['Position controls']);
  await robot.tool('Select').click();
  assert.deepEqual(await robot.stack(), ['Links', 'SDF']);
  await robot.section('SDF').getByRole('button', { name: 'Expand sdf', exact: true }).click();
  const [linksTree, sdfBox] = await Promise.all([robot.linksPanel().boundingBox(), robot.section('SDF').boundingBox()]);
  assert.ok(sdfBox.y >= linksTree.y + linksTree.height - 1, 'SDF follows the link tree');
  const text = (await robot.section('SDF').innerText()).replace(/\s+/g, ' ');
  for (const fact of ['Version 1.9', 'Document world', 'World lab', 'Frame mode native', 'Root link base', 'Model swing', 'Links 2', 'Joints 1', 'Lights 1', 'sun / directional']) assert.ok(text.includes(fact), `${fact} in: ${text}`);
  // Its joint frame and its child link frame differ (the child sits at an offset): the knob still drives it.
  await robot.type('hinge', 40);
  const links = await robot.links();
  assert.equal(round6(translation(links.arm)[2]), round6(0.2 - 0.05 * Math.sin((40 * Math.PI) / 180)));
  // Display offers no Edges, Cross-section or Explode.
  await robot.displayButton().click();
  const displayMenu = robot.displayPanel();
  for (const absent of ['Edges', 'Cross-section', 'Explode']) assert.equal(await displayMenu.getByRole('heading', { name: absent, exact: true }).count(), 0, absent);
  await displayMenu.getByRole('combobox', { name: 'Mode', exact: true }).click();
  assert.deepEqual(await page.getByRole('option').allInnerTexts(), ['Solid', 'Render', 'Grid']);
  await page.keyboard.press('Escape');
  await displayMenu.getByRole('combobox', { name: 'Projection', exact: true }).click();
  assert.deepEqual(await page.getByRole('option').allInnerTexts(), ['Orthographic', 'Perspective']);
  await page.keyboard.press('Escape');
  await robot.displayButton().click();
  await displayMenu.waitFor({ state: 'detached' });
  // Display was never the tool: Position was in hand throughout, and still is.
  assert.deepEqual(await robot.toolNames(), ['Select:false', 'Position:true']);
  await robot.openPosition();

  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.deepEqual([captured.file, captured.type, captured.references.length], ['/models/swing.sdf', 'image/png', 1], 'one context, of the file');

  assert.deepEqual(robot.errors, []);
});

test('files that cannot be shown say why: an SRDF with no URDF beside it, and a robot whose link mesh is missing', async (t) => {
  const lonely = await open(t, 'lonely.srdf', { panel: false });
  const alert = lonely.pane.getByText('No URDF beside this SRDF', { exact: true });
  await alert.waitFor();
  const said = (await lonely.pane.innerText()).replace(/\s+/g, ' ');
  assert.match(said, /exactly one \.urdf file whose <robot name> is “nobody”/, 'it names what was looked for');
  assert.match(said, /Put the robot's URDF next to this SRDF/);
  assert.equal(await lonely.pane.getByText('Reading model').count(), 0, 'it does not load forever');
  assert.deepEqual(lonely.errors, []);

  const gone = await open(t, 'gone.urdf', { panel: false });
  await gone.pane.getByText('Couldn’t load the model', { exact: true }).waitFor();
  assert.match((await gone.pane.innerText()).replace(/\s+/g, ' '), /meshes\/absent\.stl: 404/);
  assert.deepEqual(gone.errors, []);
});

test('a pose step costs the same on a long chain: one matrix, no component', async (t) => {
  const robot = await open(t, 'chain.urdf');
  const { page, pane } = robot;
  await robot.openPosition();
  await page.waitForFunction(count => window.__cadJointHandles?.().length === count, CHAIN_LINKS - 1);
  await robot.settled();
  // What a step costs is counted, never timed: the matrices it writes and the renders it causes.
  // (Posing through React state and a re-placed part list rendered the renderer every step.)
  // A 29-joint Position panel floats over the chain's root on this viewport. This measures
  // what a pose step costs, not the layout, so the stack is kept out of the pointer's way
  // (still rendered: its slider rows are what a step must not re-render).
  await page.addStyleTag({ content: '[data-testid="one"] [data-cad-tool-stack] { visibility: hidden !important; }' });
  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const knob = (await robot.handles()).j0;
  const radius = Math.hypot(knob.x - knob.pivotX, knob.y - knob.pivotY), bearing = Math.atan2(knob.y - knob.pivotY, knob.x - knob.pivotX);
  await page.mouse.move(surface.x + knob.x, surface.y + knob.y);
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-joint-handle-label]')?.textContent.startsWith('j0'));
  await page.mouse.down();
  const before = await robot.stats();
  // The Position icon's dot turning on or off as the swing leaves or passes the default is the
  // one render allowed beyond the host's record; read it between steps.
  let flips = 0, marked = await robot.posedMark();
  const STEPS = 30;
  for (let step = 1; step <= STEPS; step += 1) {
    const angle = bearing + Math.sin((step / STEPS) * Math.PI * 2) * 0.6;
    await page.mouse.move(surface.x + knob.pivotX + radius * Math.cos(angle), surface.y + knob.pivotY + radius * Math.sin(angle));
    await robot.settle();
    const now = await robot.posedMark();
    if (now !== marked) { flips += 1; marked = now; }
  }
  await page.mouse.up();
  const moved = await robot.stats();
  // The root joint carries all 29 links below it, and still one matrix is written per step.
  assert.equal(moved.lastPoseWrites, 1, 'a step writes the one joint that moved');
  assert.ok(moved.poseWrites - before.poseWrites >= STEPS * 0.8 && moved.poseWrites - before.poseWrites <= STEPS, JSON.stringify({ before, moved }));
  assert.ok(moved.surfaceRenders - before.surfaceRenders <= 2 + flips, `no component of the renderer renders for a pose step: ${JSON.stringify({ before, moved, flips })}`);
  assert.ok(flips <= 4, `the dot turns only as the swing leaves and reaches the default: ${flips}`);
  assert.deepEqual(robot.errors, []);
});
