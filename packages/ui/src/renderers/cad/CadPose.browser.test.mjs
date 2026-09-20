import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// The Pose tool end to end in a real browser, over a robot made of primitives:
// the tool a robot opens in, a knob dragging its joint and nothing else, the
// camera left to every other press, and the rule that every pose write lands at
// once: a knob, a typed value, a named pose, Reset. The drag mathematics and the
// adapters have unit tests; this is the flow a person actually uses.
const box = (size, xyz, rgba) => `<visual><origin xyz="${xyz}"/><geometry><box size="${size}"/></geometry><material name="m${rgba.replaceAll(' ', '')}"><color rgba="${rgba}"/></material></visual>`;
const urdf = `<?xml version="1.0"?>
<robot name="arm">
  <link name="base">${box('0.4 0.4 0.1', '0 0 0.05', '0.3 0.3 0.35 1')}</link>
  <link name="upper_arm">${box('0.5 0.08 0.08', '0.25 0 0', '0.9 0.5 0.1 1')}</link>
  <link name="carriage">${box('0.1 0.1 0.1', '0 0 0', '0.1 0.4 0.9 1')}</link>
  <link name="camera">${box('0.06 0.06 0.06', '0 0 0', '0.1 0.7 0.3 1')}</link>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="upper_arm"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/><limit lower="-1.5708" upper="1.5708" effort="1" velocity="1"/></joint>
  <joint name="lift" type="prismatic"><parent link="base"/><child link="carriage"/><origin xyz="-0.15 0.15 0.15"/><axis xyz="0 0 1"/><limit lower="0" upper="0.3" effort="1" velocity="1"/></joint>
  <joint name="camera_mount" type="fixed"><parent link="base"/><child link="camera"/><origin xyz="0.15 -0.15 0.13"/></joint>
</robot>
`;
const srdf = `<?xml version="1.0"?>
<robot name="arm">
  <group name="arm"><joint name="shoulder"/><joint name="lift"/></group>
  <group_state name="stowed" group="arm"><joint name="shoulder" value="0"/><joint name="lift" value="0"/></group_state>
  <group_state name="raised" group="arm"><joint name="shoulder" value="-1.0"/><joint name="lift" value="0.2"/></group_state>
</robot>
`;

test('a robot opens in Pose: knobs drag joints, the camera keeps every other press, and every pose write is a jump', async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), 'hardcore-cad-pose-'));
  let server, browser;
  t.after(async () => { await browser?.close(); if (server) await new Promise((resolve) => server.close(resolve)); await rm(temporary, { recursive: true, force: true }); });
  await build({ entryPoints: [fileURLToPath(new URL('./harness/index.tsx', import.meta.url))], outfile: join(temporary, 'harness.js'), bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic', loader: { '.webp': 'dataurl', '.woff2': 'dataurl' } });
  const bundle = await readFile(join(temporary, 'harness.js'));
  const bundledCss = await readFile(join(temporary, 'harness.css')).catch(() => '');
  const compiledCss = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (url.pathname === '/harness.css') { response.setHeader('Content-Type', 'text/css'); response.end(bundledCss); }
    else if (url.pathname.endsWith('/__cad/catalog')) {
      const paired = { kind: 'urdf', file: 'arm.urdf', rootRelativeFile: 'arm.urdf', url: '/arm.urdf', hash: `${root}-urdf`, bytes: urdf.length };
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ rootId: root, entries: [paired, { kind: 'srdf', file: 'arm.srdf', rootRelativeFile: 'arm.srdf', url: '/arm.srdf', hash: `${root}-srdf`, bytes: srdf.length, relations: { urdf: paired } }] }));
    } else if (url.pathname.endsWith('/__cad/server')) {
      response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ rootId: root, rootPath: '/models', backend: 'cadgen' }));
    } else if (url.pathname.endsWith('/arm.urdf')) { response.end(urdf); }
    else if (url.pathname.endsWith('/arm.srdf')) { response.end(srdf); }
    else if (/\.(woff2|ttf)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><html><head><title>Host</title><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>'); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: process.platform === 'darwin' ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=arm.srdf`);
  const pane = page.getByTestId('one');
  const tools = pane.getByRole('group', { name: 'Interaction tools' });
  const toolNames = () => tools.getByRole('button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
  const handles = async () => Object.fromEntries((await page.evaluate(() => window.__cadJointHandles())).map(handle => [handle.id, handle]));
  const camera = () => page.evaluate(() => { const { position, target, zoom } = window.__cadCamera(); return [...position, ...target, zoom]; });
  // Orbit controls re-derive the camera from its spherical form on a repaint: rounding, not motion.
  const sameCamera = (a, b) => a.every((value, index) => Math.abs(value - b[index]) < 1e-9);
  const jointField = name => pane.getByLabel(`${name} value in ${name === 'lift' ? 'm' : 'deg'}`, { exact: true });

  // The robot opens in Pose, and Pose leads its tools.
  await page.waitForFunction(() => window.__cadJointHandles?.().length > 0);
  assert.deepEqual(await toolNames(), ['Pose', 'Select', 'Draw']);
  assert.equal(await tools.getByRole('button', { name: 'Pose', exact: true }).getAttribute('aria-pressed'), 'true');
  assert.equal(await tools.getByRole('button', { name: 'Select', exact: true }).getAttribute('aria-pressed'), 'false');
  // One knob per joint a person can drive: the fixed camera mount has none.
  assert.deepEqual(Object.keys(await handles()).sort(), ['lift', 'shoulder']);
  // The Inspector narrows the viewport, so it opens before any knob is located.
  await pane.getByRole('button', { name: 'Inspector', exact: true }).click();
  await pane.getByRole('tab', { name: 'Kinematics', exact: true }).click();
  await jointField('shoulder').waitFor();
  await page.waitForTimeout(500);

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
    return page.evaluate(() => { const frames = window.__shoulderFrames; window.__shoulderFrames = null; return frames; });
  };

  // Dragging a knob turns its joint and leaves the camera where it was.
  const framed = await camera();
  const { shoulder } = await handles();
  await page.mouse.move(...at(shoulder.x, shoulder.y));
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-joint-handle-label]')?.textContent.startsWith('shoulder'));
  await page.mouse.down();
  // Swing the knob a quarter turn round its pivot, on screen.
  const radius = Math.hypot(shoulder.x - shoulder.pivotX, shoulder.y - shoulder.pivotY);
  const bearing = Math.atan2(shoulder.y - shoulder.pivotY, shoulder.x - shoulder.pivotX);
  for (let step = 1; step <= 9; step += 1) {
    const angle = bearing - (step * Math.PI) / 18;
    await page.mouse.move(...at(shoulder.pivotX + radius * Math.cos(angle), shoulder.pivotY + radius * Math.sin(angle)));
  }
  await page.waitForFunction(() => Math.abs(window.__cadJointHandles().find(handle => handle.id === 'shoulder').value) > 20);
  const held = (await handles()).shoulder.value;
  assert.match(await pane.locator('[data-cad-joint-handle-label]').textContent(), /^shoulder\s+-?\d+\.\d°$/);
  await page.mouse.up();
  await page.waitForTimeout(300);
  // Nothing eases behind the drag: the value at release is the value that stays.
  assert.equal((await handles()).shoulder.value, held);
  assert.ok(sameCamera(await camera(), framed), 'a knob drag never moves the camera');
  assert.equal(await jointField('shoulder').inputValue(), `${Math.round(held * 10) / 10}°`, 'the Kinematics slider follows the knob');
  assert.equal((await handles()).lift.value, 0);

  // A slider drags along its axis, to its limit and no further.
  const { lift } = await handles();
  await page.mouse.move(...at(lift.x, lift.y));
  await page.mouse.down();
  await page.mouse.move(...at(lift.x + (lift.x - lift.pivotX) * 12, lift.y + (lift.y - lift.pivotY) * 12), { steps: 10 });
  await page.mouse.up();
  await page.waitForFunction(() => window.__cadJointHandles().find(handle => handle.id === 'lift').value === 0.3);

  // Anywhere else the press is the camera's, and no joint moves.
  const posed = await handles();
  await page.mouse.move(...at(40, 420));
  await page.mouse.down();
  await page.mouse.move(...at(160, 470), { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(before => window.__cadCamera().position.some((value, index) => Math.abs(value - before[index]) > 1e-3), framed);
  const orbited = await handles();
  assert.deepEqual([orbited.shoulder.value, orbited.lift.value], [posed.shoulder.value, posed.lift.value]);
  assert.notDeepEqual([orbited.shoulder.x, orbited.shoulder.y], [posed.shoulder.x, posed.shoulder.y], 'the knobs ride the model through the orbit');

  // A typed value is where the joint is: the next frame shows it, and none shows anything between.
  const typed = await shoulderFrames(async () => { await jointField('shoulder').fill('35'); await jointField('shoulder').press('Enter'); });
  assert.equal(typed.at(-1), 35);
  assert.deepEqual([...new Set(typed)], [held, 35], 'a typed value jumps');

  // So is a named pose, and so is Reset: every pose write is a jump. Motion over time is the Animate tool's.
  const choosePose = async (name) => {
    await pane.getByRole('tabpanel', { name: 'Kinematics', exact: true }).getByRole('combobox').first().click();
    await page.getByRole('option', { name, exact: true }).click();
  };
  const raised = (-1.0 * 180) / Math.PI;
  const posedFrames = await shoulderFrames(() => choosePose('raised'));
  assert.deepEqual([...new Set(posedFrames.map(value => Math.round(value * 1e6) / 1e6))], [35, Math.round(raised * 1e6) / 1e6], 'a named pose jumps');
  assert.equal((await handles()).lift.value, 0.2);
  const resetFrames = await shoulderFrames(() => pane.getByRole('button', { name: 'Reset', exact: true }).click());
  assert.deepEqual([...new Set(resetFrames.map(value => Math.round(value * 1e6) / 1e6))], [Math.round(raised * 1e6) / 1e6, 0], 'Reset jumps');

  // Leaving for Select keeps the pose and takes the knobs away; coming back finds the pose where it was.
  await jointField('shoulder').fill('-40');
  await jointField('shoulder').press('Enter');
  await tools.getByRole('button', { name: 'Select', exact: true }).click();
  await page.waitForFunction(() => window.__cadJointHandles().length === 0);
  assert.equal(await jointField('shoulder').inputValue(), '-40°');
  await tools.getByRole('button', { name: 'Pose', exact: true }).click();
  await page.waitForFunction(() => window.__cadJointHandles().length === 2);
  assert.equal((await handles()).shoulder.value, -40);
  assert.deepEqual(errors, []);
  console.info('PASS: Pose leads and opens; knob drags joint, not camera; limits; orbit elsewhere; fixed joint has no knob; typed value, named pose and Reset all jump; Select keeps the pose');
});
