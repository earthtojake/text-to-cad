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
import { writeGlb } from '@hardcore/core/glb/writeGlb.js';

// The robot renderer end to end in a real browser, over inline fixtures made of
// primitives: a URDF, the SRDF paired with it (a "home" state, a named pose, an end
// effector), an SDF, a robot whose only joint travels far past its rest box, and the
// files that must raise an alert instead of a robot. Scene, pose store and handle
// adapter have unit tests; these are the flows a person actually uses.

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
// A mast whose carriage leaves its rest box by three times the mast's height, or sinks below its foot.
const MAST_URDF = `<?xml version="1.0"?>
<robot name="mast">
  <link name="mast">${box('0.1 0.1 1', '0 0 0.5', '0.4 0.4 0.45 1')}</link>
  <link name="carriage">${box('0.16 0.16 0.1', '0 0 0', '0.1 0.4 0.9 1')}</link>
  <joint name="hoist" type="prismatic"><parent link="mast"/><child link="carriage"/><origin xyz="0 0 0.5"/><axis xyz="0 0 1"/>${limit(-0.8, 3)}</joint>
</robot>
`;
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
  'arm.urdf': ARM_URDF, 'arm.srdf': ARM_SRDF, 'swing.sdf': SWING_SDF, 'mast.urdf': MAST_URDF, 'chain.urdf': CHAIN_URDF,
  'gone.urdf': GONE_URDF, 'lonely.srdf': LONELY_SRDF, 'meshes/head.glb': Buffer.from(headGlb.buffer, headGlb.byteOffset, headGlb.byteLength),
};

let server, browser, temporary;
// Bumped by a test to publish a new revision of every description.
let revision = 1;
before(async () => {
  temporary = await mkdtemp(join(tmpdir(), 'hardcore-robot-browser-'));
  await build({ entryPoints: [fileURLToPath(new URL('../harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const [, root, ...rest] = url.pathname.split('/');
    const name = rest.join('/');
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      const entry = file => ({ kind: file.split('.').pop(), file, rootRelativeFile: file, url: `/${file}`, hash: `${root}-${file}-${revision}`, bytes: FILES[file].length });
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: Object.keys(FILES).filter(file => !file.startsWith('meshes/'))
        .map(file => (file === 'arm.srdf' ? { ...entry(file), relations: { urdf: entry('arm.urdf') } } : entry(file))) }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (FILES[name] ?? FILES[url.pathname.slice(1)]) { response.end(FILES[name] ?? FILES[url.pathname.slice(1)]); }
    else if (/\.(woff2|ttf|stl|glb)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host</title><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin' ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  if (temporary) await rm(temporary, { recursive: true, force: true });
});

async function open(t, file, { panel = true } = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
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
    jointField: (name, unit = 'deg') => page.getByLabel(`${name} value in ${unit}`, { exact: true }),
    async openPosition() {
      await robot.tool('Position').click();
    },
    async type(name, value, unit) { await robot.openPosition(); await robot.jointField(name, unit).fill(String(value)); await robot.jointField(name, unit).press('Enter'); },
    pressedRows: () => pane.locator('[aria-label="Robot tree area"] button[aria-pressed="true"]').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    // A selection is React state: it is on screen a render after whatever changed it.
    waitPressed: count => page.waitForFunction(wanted => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === wanted, count),
    // The nav row's panel toggles, in order, each with whether its panel is the open one.
    panels: () => pane.locator('[data-file-panel]')
      .evaluateAll(buttons => buttons.map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
    toggle: id => id === 'cad-display' ? pane.locator('[data-cad-camera-controls]').getByRole('button', { name: 'Display', exact: true }) : pane.locator(`[data-file-panel="${id}"]`),
    // The robot's own panel, and its sections top to bottom by their headings.
    sheet: () => pane.locator('[data-file-sheet="Settings"]'),
    sections: () => pane.locator('[data-file-sheet="Settings"] [data-file-panel-section] h2').allInnerTexts(),
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
    // The robot's panel narrows the viewport, so it is open before anything is located on
    // screen. Nobody opens it: a robot opened directly opens with its own panel.
    await robot.sheet().waitFor();
    await page.waitForTimeout(400);
  }
  return robot;
}
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
// Orbit controls re-derive the camera from its spherical form on a repaint: rounding, not motion.
const sameCamera = (a, b) => a.every((value, index) => Math.abs(value - b[index]) < 1e-9);
const round6 = value => Math.round(value * 1e6) / 1e6;
const translation = matrix => [matrix[3], matrix[7], matrix[11]];

// Anything inside a file panel's sections that scrolls on its own: the column is the panel's
// one scroller, and the pinned Reference the only other.
const scrollingInside = (pane, sheet) => pane.locator(`[data-file-sheet="${sheet}"] [data-file-panel-section]`).evaluateAll(sections =>
  sections.flatMap(section => [section, ...section.querySelectorAll('*')])
    .filter(element => /(auto|scroll)/.test(getComputedStyle(element).overflowY) && element.scrollHeight > element.clientHeight + 1)
    .map(element => element.getAttribute('aria-label') || element.getAttribute('data-file-panel-section') || element.tagName));

test('robot Select defaults match Links and Position remains an explicit tool', async (t) => {
  const robot = await open(t, 'arm.urdf');
  assert.deepEqual(await robot.toolNames(), ['Select:true', 'Position:false', 'Display:false']);
  assert.equal(await robot.pane.getByRole('tab', { name: 'Links', exact: true }).getAttribute('aria-selected'), 'true');
  assert.equal(await robot.tool('Select').locator('svg.lucide-mouse-pointer-2').count(), 1);
  assert.equal(await robot.pane.locator('[data-cad-joint-handle-label]').count(), 0);
  await robot.openPosition();
  await robot.page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  assert.equal(await robot.tool('Position').getAttribute('aria-pressed'), 'true');
  assert.equal(await robot.pane.getByRole('tab', { name: 'Position', exact: true }).getAttribute('aria-selected'), 'true');
  await robot.tool('Display').click();
  assert.equal(await robot.tool('Position').getAttribute('aria-pressed'), 'false');
  assert.equal(await robot.tool('Display').getAttribute('aria-pressed'), 'true');
  assert.equal(await robot.pane.locator('[data-cad-joint-handle-label]').count(), 0);
  await robot.tool('Select').click();
  assert.equal(await robot.tool('Select').getAttribute('aria-pressed'), 'true');
  assert.equal(await robot.pane.locator('[data-cad-joint-handle-label]').count(), 0);
  assert.deepEqual(robot.errors, []);
});

test('a robot opens in Position with sidebar controls: knobs drag joints, the camera keeps every other press, every pose write is a jump, and a pose step renders no component', async (t) => {
  const robot = await open(t, 'arm.srdf');
  const { page, pane } = robot;
  const home = (-0.5 * 180) / Math.PI, raised = (-1.0 * 180) / Math.PI;

  // The robot opens in Position, Position leads its tools, and the robot's own panel is open
  // with Links as its first section.
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  assert.deepEqual(await robot.toolNames(), ['Position:true', 'Select:false']);
  assert.equal(await robot.tool('Draw').count(), 0, 'Draw is a STEP tool; a robot description has none');
  assert.equal(await robot.tool('Fullscreen').count(), 0, 'so is Fullscreen: a robot presents no fullscreen');
  // The nav row has the robot's own panel followed by the tree. Display lives in the toolbar. Opened
  // directly, the file shows its own panel — never Display, and not the tree.
  assert.deepEqual(await robot.panels(), ['Settings:true', 'Show files:false']);
  assert.equal(await robot.sheet().count(), 1, 'the robot panel is named for what the file is, whatever its format');
  assert.equal(await pane.locator('[data-cad-display-popover]').count(), 0, 'Display is never where a file opens');
  assert.equal(await pane.getByRole('tab').count(), 0, 'a panel has no tabs inside it');
  assert.deepEqual(await robot.sections(), ['Links', 'Position']);
  assert.equal(await pane.locator('[data-file-panel-section=position]').count(), 1);
  await robot.openPosition();
  // One knob per joint a person can drive: no fixed joint, no mimic follower. The follower has no slider either.
  assert.deepEqual(Object.keys(await robot.handles()).sort(), ['grip', 'lift', 'nod', 'shoulder']);
  assert.equal(await robot.jointField('grip_mirror', 'm').count(), 0);
  assert.equal(await robot.jointField('camera_mount').count(), 0);
  // The SRDF's "home" state is the pose the robot opens in, and the Position section's Pose
  // row names it: a labelled row of that one section, with its dropdown beside the label.
  assert.equal(round6((await robot.handles()).shoulder.value), round6(home));
  assert.equal((await robot.handles()).lift.value, 0.1);
  const position = pane.locator('[data-file-panel-section=position]');
  const poseSelect = position.getByRole('combobox', { name: 'Pose', exact: true });
  await assertLabelledRow(position, 'Pose', poseSelect);
  for (const heading of ['Pose', 'Joints', 'Kinematics']) {
    assert.equal(await position.getByRole('heading', { name: heading, exact: true }).count(), 0, `no ${heading} heading inside Position`);
  }
  assert.equal((await poseSelect.innerText()).trim(), 'home');

  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const at = (x, y) => [surface.x + x, surface.y + y];
  // Every value the shoulder shows, frame by frame, while `action` runs and settles.
  const shoulderFrames = async (action) => {
    await page.evaluate(() => {
      window.__shoulderFrames = [];
      const sample = () => { window.__shoulderFrames?.push(window.__cadJointHandles().find(handle => handle.id === 'shoulder').value); if (window.__shoulderFrames) requestAnimationFrame(sample); };
      // The first sample is taken now: the action may land before the next frame does.
      sample();
    });
    await action();
    await page.waitForTimeout(600);
    return page.evaluate(() => { const frames = window.__shoulderFrames; window.__shoulderFrames = null; return [...new Set(frames.map(value => Math.round(value * 1e6) / 1e6))]; });
  };

  // Dragging a knob turns its joint and leaves the camera where it was.
  const framed = await robot.camera();
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
  await page.waitForTimeout(300);
  assert.equal(await robot.cursor(), 'grab', 'released, and still on the knob');
  // Nothing eases behind the drag: the value at release is the value that stays.
  assert.equal((await robot.handles()).shoulder.value, held);
  assert.ok(sameCamera(await robot.camera(), framed), 'a knob drag never moves the camera');
  assert.equal(await robot.jointField('shoulder').inputValue(), `${Math.round(held * 10) / 10}°`, 'the Position slider follows the knob');
  assert.equal((await robot.handles()).lift.value, 0.1);
  // What the drag cost: one matrix per step (the joint that moved), and not one render of the renderer's surface.
  const dragged = await robot.stats();
  assert.equal(dragged.lastPoseWrites, 1, 'a pose step writes the one joint that changed');
  assert.ok(dragged.poseWrites - before.poseWrites >= 5 && dragged.poseWrites - before.poseWrites <= 12, JSON.stringify({ before, dragged }));
  // (The one render a drag may cost is the host storing the debounced record, not a step.)
  assert.ok(dragged.surfaceRenders - before.surfaceRenders <= 1, `no React state sits in the per-pose path: ${JSON.stringify({ before, dragged })}`);
  assert.equal((await poseSelect.innerText()).trim(), 'None', 'a joint moved by hand releases the named pose');

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

  // Anywhere else the press is the camera's, and no joint moves.
  const posed = await robot.handles();
  await page.mouse.move(...at(40, 420));
  await robot.waitCursor('auto');
  await page.mouse.down();
  await page.mouse.move(...at(160, 470), { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(start => window.__cadCamera().position.some((value, index) => Math.abs(value - start[index]) > 1e-3), framed);
  const orbited = await robot.handles();
  assert.deepEqual([orbited.shoulder.value, orbited.lift.value], [posed.shoulder.value, posed.lift.value]);
  assert.notDeepEqual([orbited.shoulder.x, orbited.shoulder.y], [posed.shoulder.x, posed.shoulder.y], 'the knobs ride the model through the orbit');

  // A typed value, a named pose and Reset are each where the robot IS from the next frame on: none shows anything between.
  assert.deepEqual(await shoulderFrames(() => robot.type('shoulder', 35)), [round6(held), 35], 'a typed value jumps');
  const choosePose = async (name) => { await poseSelect.click(); await page.getByRole('option', { name, exact: true }).click(); };
  assert.deepEqual(await shoulderFrames(() => choosePose('raised')), [35, round6(raised)], 'a named pose jumps');
  assert.equal((await robot.handles()).lift.value, 0.2);
  assert.equal((await robot.handles()).grip.value, 0.03, 'a named pose merges over the pose as it is');
  assert.equal((await poseSelect.innerText()).trim(), 'raised');
  assert.deepEqual(await shoulderFrames(() => position.getByRole('button', { name: 'Reset', exact: true }).click()), [round6(raised), round6(home)], 'Reset jumps, back to the SRDF home pose');
  assert.equal((await robot.handles()).grip.value, 0);
  assert.equal((await poseSelect.innerText()).trim(), 'home');

  // Folding and switching tools preserve the pose; the tool unfolds its controls.
  await robot.type('shoulder', -40);
  await position.getByRole('button', { name: 'Collapse Position' }).click();
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
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  // Where things are on screen: a knob sits on the link it drives, and a slider's thumb on its carriage.
  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const spots = await robot.handles();
  const onScreen = handle => [surface.x + handle.x, surface.y + handle.y];
  const nod = spots.nod;
  // The antenna reaches away from the nod pivot; the visor sits on it.
  const antenna = [surface.x + nod.pivotX + (nod.x - nod.pivotX) * 2, surface.y + nod.pivotY + (nod.y - nod.pivotY) * 2];
  const visor = [surface.x + nod.pivotX, surface.y + nod.pivotY];

  // Under Position the model picks nothing: a click on it is the camera's.
  await page.mouse.click(...onScreen(spots.lift).map((value, index) => value + (index ? 14 : 14)));
  await robot.settle();
  assert.deepEqual(await robot.toolNames(), ['Position:true', 'Select:false']);
  // Links is a section of the robot's panel, under Position: on screen already, no tab to turn to.
  await robot.section('Links').waitFor();
  assert.deepEqual(await robot.pressedRows(), []);
  // The tree: a frame-only root is elided, so the base leads it, pinned (no chevron of its own).
  assert.equal(await pane.getByRole('button', { name: 'Select base_footprint', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Collapse base', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).count(), 1);

  // Choosing a row under Position returns to Select first; the row is the selection.
  await pane.getByRole('button', { name: 'Select upper_arm', exact: true }).click();
  assert.deepEqual(await robot.toolNames(), ['Position:false', 'Select:true']);
  assert.deepEqual(await robot.pressedRows(), ['Select upper_arm']);
  const reference = pane.getByLabel('Reference details');
  await reference.getByText('shoulder', { exact: true }).first().waitFor();
  assert.match(await reference.innerText(), /arm/, 'the SRDF planning group of the link');
  // Pinned at the panel's foot, under both sections.
  const [pinned, sheetBox, linksAfter] = await Promise.all([reference.boundingBox(), robot.sheet().boundingBox(),
    pane.locator('[data-file-panel-section="links"] [data-file-panel-body]').boundingBox()]);
  assert.ok(Math.abs(pinned.y + pinned.height - (sheetBox.y + sheetBox.height)) <= 1, `the Reference ends where the panel does: ${pinned.y + pinned.height} vs ${sheetBox.y + sheetBox.height}`);
  assert.ok(pinned.y >= linksAfter.y + linksAfter.height - 1, 'under Links');
  // With the Reference pinned, the sections keep their full heights: nothing inside them
  // scrolls — only the column does, and the Reference on its own.
  assert.deepEqual(await scrollingInside(pane, 'Settings'), [], 'no section scrolls inside itself');
  // Leaving Select drops the selection, in the tree and the viewport alike.
  await robot.tool('Position').click();
  await robot.waitPressed(0);
  // Display floats over the viewer, leaving the robot sidebar visible.
  await robot.toggle('cad-display').click();
  await robot.sheet().waitFor({ state: 'visible' });

  // A viewport pick under Select: the link is selected on the very next frame (no wait for
  // a double-click that robots do not have), the robot's panel is revealed with its Links, and
  // the row is pressed.
  await robot.tool('Select').click();
  // (The viewport's own pixels: a page screenshot would also see the toolbar's hover state.)
  const still = (await robot.capture()).data;
  await page.mouse.move(...onScreen(spots.shoulder).map(value => value - 3));
  await page.mouse.move(...onScreen(spots.shoulder));
  // Over a link the pointer says it can be picked; over the backdrop it does not.
  await robot.waitCursor('pointer');
  assert.ok(!(await robot.capture()).data.equals(still), 'a hovered link is lit');
  await page.mouse.move(surface.x + 30, surface.y + surface.height - 30);
  await robot.waitCursor('auto');
  assert.ok((await robot.capture()).data.equals(still), 'and is exactly as it was once the pointer leaves');

  await page.mouse.move(...onScreen(spots.shoulder));
  await page.mouse.down(); await page.mouse.up();
  await robot.settle();
  assert.deepEqual(await robot.pressedRows(), ['Select upper_arm'], 'selected by the next frame');
  assert.deepEqual(await robot.panels(), ['Settings:true', 'Show files:false'], 'the pick revealed the robot\'s panel');
  assert.equal(await robot.section('Links').isVisible(), true, 'where its Links are');
  assert.deepEqual((await page.evaluate(() => window.cadHarness.a.controller.readState())).selectedLinks, ['upper_arm']);
  // The shared camera bar provides zoom framing for robots too.
  assert.equal(await pane.getByRole('button', { name: 'Zoom controls', exact: true }).count(), 0);
  assert.equal(await pane.getByLabel('Zoom level percent', { exact: true }).count(), 0);

  // Escape clears the selection first, and only then shuts the open panel.
  await page.mouse.click(surface.x + 30, surface.y + surface.height - 30);
  assert.deepEqual(await robot.pressedRows(), [], 'a click on nothing clears');
  await page.mouse.click(...onScreen(spots.lift));
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 1);
  assert.deepEqual(await robot.pressedRows(), ['Select carriage']);
  assert.match(await reference.innerText(), /tool/, 'the end effector mounted on the link');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 0);
  assert.equal(await robot.sheet().isVisible(), true, 'the first Escape spent itself on the selection');
  await page.keyboard.press('Escape');
  await robot.sheet().waitFor({ state: 'hidden' });
  assert.deepEqual(await robot.panels(), ['Settings:false', 'Show files:false'], 'the second shut the panel');
  await robot.toggle('cad-file').click();
  await robot.sheet().waitFor();
  await page.waitForTimeout(400);

  // Named objects of a link's mesh select themselves, and Shift adds.
  await page.mouse.click(...visor);
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 1);
  assert.deepEqual(await robot.pressedRows(), ['Select visor']);
  await page.keyboard.down('Shift'); await page.mouse.click(...antenna); await page.keyboard.up('Shift');
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="one"] [aria-label="Robot tree area"] button[aria-pressed="true"]').length === 2);
  assert.deepEqual((await robot.pressedRows()).sort(), ['Select antenna', 'Select visor']);
  assert.deepEqual((await page.evaluate(() => window.cadHarness.a.controller.readState())).selectedPartIds.sort(), ['head:v1/object/0', 'head:v1/object/1']);

  // What names something else can be followed: a parent link selects it, a mesh path opens it.
  await pane.getByRole('button', { name: 'Select head', exact: true }).click();
  await reference.getByRole('button', { name: 'meshes/head.glb' }).click();
  assert.deepEqual(await page.evaluate(() => window.cadHarness.opened), ['meshes/head.glb']);
  await reference.getByRole('button', { name: 'base', exact: true }).first().click();
  assert.deepEqual(await robot.pressedRows(), ['Select base']);
  // The filter finds a link by the joint that carries it.
  await pane.getByPlaceholder('Filter links…').fill('nod');
  await pane.getByRole('list', { name: 'Link search results' }).getByRole('button', { name: 'Select head', exact: true }).waitFor();
  await pane.getByPlaceholder('Filter links…').fill('');

  // Host commands: a robot has no references to select, and says so; clearSelection clears the link selection.
  const declined = await page.evaluate(() => window.cadHarness.a.controller.select(['#f1']).then(() => '', error => error.message));
  assert.match(declined, /no CAD references to select/);
  await page.evaluate(() => window.cadHarness.a.controller.clearSelection());
  assert.deepEqual(await robot.pressedRows(), []);
  assert.deepEqual(robot.errors, []);
});

test('posing a joint far past the rest box never resizes the grid or the studio floor and never moves the camera, while the floor\'s height follows the robot', async (t) => {
  const robot = await open(t, 'mast.urdf');
  const { page } = robot;
  await page.waitForFunction(() => window.__cadJointHandles?.().length === 1);
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ axes: { enabled: false } }));
  await page.waitForTimeout(400);
  const framed = await robot.camera();
  const rest = await robot.capture();
  const restStage = await page.evaluate(() => window.__cadStage());
  await robot.type('hoist', 3, 'm');
  // (Its knob has left the picture with it, so the link itself is asked where it is.)
  await page.waitForFunction(() => window.__robotLinks().find(({ link }) => link === 'carriage').matrixWorld[11] === 3.5);
  await page.waitForTimeout(400);
  const posed = await robot.capture();
  assert.ok(sameCamera(await robot.camera(), framed), 'a pose never re-frames');
  assert.deepEqual([rest.width, rest.height], [posed.width, posed.height]);
  // The mast stands in the middle of the picture; the grid runs out to both sides of it.
  let compared = 0, inked = 0, differing = 0;
  const backdrop = [rest.data[0], rest.data[1], rest.data[2]];
  for (let y = 0; y < rest.height; y += 1) {
    for (let x = 0; x < rest.width; x += 1) {
      if (x > rest.width * 0.3 && x < rest.width * 0.7) continue;
      const offset = (y * rest.width + x) * 4;
      compared += 1;
      if ([0, 1, 2].some(channel => Math.abs(rest.data[offset + channel] - backdrop[channel]) > 3)) inked += 1;
      if ([0, 1, 2].some(channel => Math.abs(rest.data[offset + channel] - posed.data[offset + channel]) > 2)) differing += 1;
    }
  }
  assert.ok(inked > compared * 0.002, `the compared region holds grid lines: ${inked}/${compared}`);
  assert.equal(differing, 0, `the grid is sized from the REST pose: ${differing} pixels of it changed under a pose`);

  // What DOES follow the posed robot is where the stage stands: lighting is fitted to the posed box, and a
  // floor kept under the model drops with it, on the frame of the pose, with no component rendering for it.
  const stage = () => page.evaluate(() => window.__cadStage());
  const lifted = await stage();
  assert.ok(restStage.gridRadius > 0);
  assert.equal(lifted.gridRadius, restStage.gridRadius, 'the ground keeps the size the rest pose gave it');
  assert.equal(lifted.bounds.max[2], 3.55, 'the box lighting and shadows are fitted to is the posed one');
  await page.evaluate(() => window.cadHarness.a.controller.setDisplaySettings({ floor: { enabled: true, placement: 'lowest' } }));
  await robot.type('hoist', 0, 'm');
  await page.waitForFunction(() => window.__cadStage().studioGroundZ === 0);
  const studioFloor = (await stage()).studioGround;
  assert.ok(studioFloor.size > 1);
  const renders = (await robot.stats()).surfaceRenders;
  await robot.type('hoist', -0.8, 'm');
  await page.waitForFunction(() => Math.abs(window.__cadStage().studioGroundZ + 0.35) < 1e-9);
  assert.equal((await stage()).gridRadius, restStage.gridRadius);
  assert.ok((await robot.stats()).surfaceRenders - renders <= 1, 'the bounds reach the stage without a render of the renderer');
  // The studio's floor is a plane with edges: like the grid it keeps the size and the centre the REST
  // pose gave it, however far a joint travels, in Solid with a floor and in Render alike.
  assert.deepEqual((await stage()).studioGround, studioFloor);
  await robot.type('hoist', 3, 'm');
  await page.waitForFunction(() => window.__cadStage().bounds.max[2] === 3.55);
  assert.deepEqual((await stage()).studioGround, studioFloor, 'a carriage 3 m up does not rescale the floor');
  await page.evaluate(() => window.cadHarness.a.controller.setRenderMode(true));
  await page.waitForFunction(() => window.__cadStage().studioGround);
  const renderFloor = (await stage()).studioGround;
  await robot.type('hoist', 0, 'm');
  await page.waitForFunction(() => window.__cadStage().bounds.max[2] === 1);
  assert.deepEqual((await stage()).studioGround, renderFloor, 'nor does posing in Render');
  assert.deepEqual([renderFloor.size, renderFloor.center], [studioFloor.size, studioFloor.center]);
  assert.deepEqual(robot.errors, []);
});

test('a pose, the tool and the open panel survive closing the file, and a pose is dropped when the description changed', async (t) => {
  const robot = await open(t, 'arm.urdf');
  const { page, pane } = robot;
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  await robot.type('shoulder', 25);
  await robot.type('lift', 0.2, 'm');
  // The last write lands in the record although it was never rendered: the record reads the pose when it is written.
  await robot.type('nod', 12);
  // And the column is left on Display. Which panel is open is the host's to keep, not the record's.
  await robot.toggle('cad-display').click();
  await pane.locator('[data-cad-display-popover]').waitFor();
  await page.evaluate(() => window.cadHarness.mounted(false));
  await page.waitForFunction(() => Object.values(window.cadHarness.state.renderers || {}).some(record => record?.renderer?.jointValues?.nod === 12));
  const record = await page.evaluate(() => window.cadHarness.state.renderers[JSON.stringify(['arm.urdf', 'robot'])]);
  assert.deepEqual([record.tool, record.renderer.jointValues.shoulder, record.renderer.jointValues.lift], ['pose', 25, 0.2]);
  assert.equal('inspectorTab' in record, false, 'the record keeps no open tab: there are none, and the open panel is the host\'s');
  assert.notEqual(await page.evaluate(() => window.cadHarness.state.panel), 'cad-display');
  assert.match(record.renderer.signature, /arm\.urdf-1$/);
  await page.evaluate(() => window.cadHarness.mounted(true));
  await pane.locator('[data-file-sheet="Settings"]').waitFor();
  assert.equal(await pane.locator('[data-cad-display-popover]').count(), 0);
  assert.deepEqual(await robot.panels(), ['Settings:true', 'Show files:false'], 'the file sidebar stays open across Display and remounts');
  await robot.openPosition();
  await robot.jointField('shoulder').waitFor();
  assert.deepEqual([await robot.jointField('shoulder').inputValue(), await robot.jointField('lift', 'm').inputValue(), await robot.jointField('nod').inputValue()], ['25°', '0.2 m', '12°']);
  assert.deepEqual(await robot.toolNames(), ['Position:true', 'Select:false'], 'the active Position session is restored');
  const links = await robot.links();
  assert.equal(round6(translation(links.carriage)[2]), 0.35, 'and the robot on screen is in that pose');

  // A new revision behind the mounted robot keeps the pose it is in; a record from another revision is not restored.
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

test('an SDF is the same robot with a section of its own; a robot declines the host\'s fullscreen; a snapshot depicts the whole file', async (t) => {
  const robot = await open(t, 'swing.sdf');
  const { page, pane } = robot;
  await page.waitForFunction(() => window.__cadJointHandles?.().length === 1);
  assert.deepEqual(await robot.toolNames(), ['Position:true', 'Select:false']);
  // The same panel as any robot, named the same whatever the format on disk: SDF is a section of it.
  assert.deepEqual(await robot.panels(), ['Settings:true', 'Show files:false']);
  assert.deepEqual(await robot.sections(), ['Links', 'Position', 'SDF']);
  const text = (await robot.section('SDF').innerText()).replace(/\s+/g, ' ');
  for (const fact of ['Version 1.9', 'Document world', 'World lab', 'Frame mode native', 'Root link base', 'Model swing', 'Links 2', 'Joints 1', 'Lights 1', 'sun / directional']) assert.ok(text.includes(fact), `${fact} in: ${text}`);
  // Its joint frame and its child link frame differ (the child sits at an offset): the knob still drives it.
  await robot.type('hinge', 40);
  const links = await robot.links();
  assert.equal(round6(translation(links.arm)[2]), round6(0.2 - 0.05 * Math.sin((40 * Math.PI) / 180)));
  // The Display menu offers no Edges, Cross-section or Explode.
  await robot.toggle('cad-display').click();
  const displayMenu = pane.locator('[data-cad-display-popover]');
  for (const absent of ['Edges', 'Cross-section', 'Explode']) assert.equal(await displayMenu.getByRole('heading', { name: absent, exact: true }).count(), 0, absent);
  await displayMenu.getByRole('combobox', { name: 'Mode', exact: true }).click();
  assert.deepEqual(await page.getByRole('option').allInnerTexts(), ['Solid', 'Render']);
  await page.keyboard.press('Escape');
  await displayMenu.getByRole('combobox', { name: 'Projection', exact: true }).click();
  assert.deepEqual(await page.getByRole('option').allInnerTexts(), ['Orthographic', 'Perspective']);
  await page.keyboard.press('Escape');
  await robot.toggle('cad-display').click();

  await pane.getByRole('button', { name: 'Take snapshot', exact: true }).click();
  await page.waitForFunction(() => window.cadHarness.captures.length === 1);
  const captured = await page.evaluate(() => window.cadHarness.captures[0]);
  assert.deepEqual([captured.file, captured.type, captured.references.length], ['swing.sdf', 'image/png', 1], 'one context, of the file');

  // Fullscreen is a STEP's alone. A host that asks a robot for it is declined: the nav row,
  // the tools and the knobs all stay, with nothing of fullscreen's own drawn, and the pose
  // is where it was.
  await page.evaluate(() => window.cadHarness.fullscreen(true));
  await page.waitForTimeout(300);
  assert.equal(await pane.getByRole('button', { name: 'Exit fullscreen', exact: true }).count(), 0);
  assert.equal(await pane.getByRole('group', { name: 'Fullscreen controls' }).count(), 0);
  assert.deepEqual(await robot.panels(), ['Settings:true', 'Show files:false'], 'the nav row stays');
  assert.deepEqual(await robot.toolNames(), ['Position:true', 'Select:false'], 'and the tools');
  assert.equal((await robot.handles()).hinge.value, 40, 'and the knob, where the pose left it');
  assert.equal(await pane.getByRole('toolbar', { name: 'Animation playback' }).count(), 0, 'a robot has no routines to play');
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

test('a pose step costs the same on a long chain: one matrix, no component, a few milliseconds of script', async (t) => {
  const robot = await open(t, 'chain.urdf');
  const { page, pane } = robot;
  await page.waitForFunction(count => window.__cadJointHandles?.().length === count, CHAIN_LINKS - 1);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Performance.enable');
  const script = async () => (await cdp.send('Performance.getMetrics')).metrics.find(metric => metric.name === 'ScriptDuration').value;
  const surface = await pane.locator('[data-cad-joint-handles]').boundingBox();
  const knob = (await robot.handles()).j0;
  const radius = Math.hypot(knob.x - knob.pivotX, knob.y - knob.pivotY), bearing = Math.atan2(knob.y - knob.pivotY, knob.x - knob.pivotX);
  await page.mouse.move(surface.x + knob.x, surface.y + knob.y);
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-joint-handle-label]')?.textContent.startsWith('j0'));
  await page.mouse.down();
  const before = await robot.stats();
  const started = await script();
  const STEPS = 60;
  for (let step = 1; step <= STEPS; step += 1) {
    const angle = bearing + Math.sin((step / STEPS) * Math.PI * 2) * 0.6;
    await page.mouse.move(surface.x + knob.pivotX + radius * Math.cos(angle), surface.y + knob.pivotY + radius * Math.sin(angle));
    await robot.settle();
  }
  const perStepMs = ((await script()) - started) * 1000 / STEPS;
  await page.mouse.up();
  const moved = await robot.stats();
  // The root joint carries all 29 links below it, and still one matrix is written per step.
  assert.ok(moved.poseWrites - before.poseWrites >= STEPS * 0.8 && moved.poseWrites - before.poseWrites <= STEPS, JSON.stringify({ before, moved }));
  assert.ok(moved.surfaceRenders - before.surfaceRenders <= 2, `no component of the renderer renders for a pose step: ${JSON.stringify({ before, moved })}`);
  // Posing through React state and a re-placed part list cost ~270 ms a step on a robot this size.
  // The bound is loose on purpose (a development React build, a software GL on CI): it catches that path coming back.
  assert.ok(perStepMs < 30, `a pose step took ${perStepMs.toFixed(2)} ms of script`);
  console.info(`robot pose step on a ${CHAIN_LINKS}-link chain: ${perStepMs.toFixed(2)} ms of script`);
  assert.deepEqual(robot.errors, []);
});

test('robot Links and Position are separate tabs and the Position tool reveals its controls', async t => {
  const robot = await open(t, 'arm.srdf');
  const { pane } = robot;
  assert.equal(await pane.getByRole('tab', { name: 'Links' }).getAttribute('aria-selected'), 'true');
  assert.equal(await pane.getByRole('button', { name: 'Collapse Links' }).count(), 0);
  await robot.openPosition();
  assert.equal(await pane.getByRole('tab', { name: 'Position' }).getAttribute('aria-selected'), 'true');
  await robot.type('shoulder', '30');
  await pane.getByRole('tab', { name: 'Links' }).click();
  assert.equal(await robot.jointField('shoulder').isVisible(), false);
  await pane.getByRole('tab', { name: 'Position' }).click();
  assert.equal(await robot.jointField('shoulder').inputValue(), '30°');
  assert.deepEqual(robot.errors, []);
});
