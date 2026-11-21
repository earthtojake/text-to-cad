import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { harnessBundle } from '../../harness/bundle.mjs';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import * as THREE from 'three';
import { fitRoom, interactiveCameraFrameForBounds } from '../../../../dist/renderers/kit/camera/viewportCameraFit.js';
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from '../../../../dist/renderers/kit/camera/viewportCameraKit.js';
import { CAD_DEFAULT_VERTICAL_FOV_DEGREES } from '../../../../dist/renderers/kit/camera/cameraLens.js';

// A software WebGL renderer (SwiftShader, llvmpipe: Linux CI) caps the pixel ratio at 1, idle and
// moving (`useViewerRuntime.js`), so the hardware-only ratio checks read the policy that applies.
const softwareWebGl = page => page.evaluate(() => {
  const gl = document.createElement('canvas').getContext('webgl');
  const info = gl?.getExtension('WEBGL_debug_renderer_info');
  const name = String(info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl?.getParameter(gl.RENDERER) || '');
  return /swiftshader|llvmpipe|softpipe|software rasterizer|lavapipe/i.test(name);
});

// The harness renders its panes at a fixed CSS size; the spec draws them smaller, so a software
// GL (CI's SwiftShader) has fewer pixels to fill and a screenshot fewer to read.
const HARNESS_SIZE = '<style>#root > div { width: 960px !important; height: 500px !important; }</style>';

// One harness bundle and one browser for the file; every test serves its own files and opens its
// own page. (A browser's first WebGL page pays for compiling the viewer's shaders; later pages
// reuse them.)
let bundle, compiledCss, browser;
before(async () => {
  ({ bundle } = await harnessBundle());
  compiledCss = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
});

/**
 * A server for one test: the harness page, and `route(url, root, response)` for the workspace
 * behind it (it answers `true` for what it served). A harness-only renderer's files are its own,
 * so an empty catalog serves it, and the fonts it asks for are not found.
 */
async function serve(t, route = () => false) {
  const server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const root = url.pathname.split('/')[1];
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(compiledCss); }
    else if (route(url, root, response)) return;
    else if (url.pathname.endsWith('/api/v1/documents')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ documents: ([]).map(entry => ({ entry, revision: entry.hash })) })); }
    else if (url.pathname.endsWith('/api/v1/server')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify({ backend: 'cadgen' })); }
    else if (/\.(woff2|ttf)$/.test(url.pathname)) { response.statusCode = 404; response.end(); }
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  t.after(() => new Promise(resolve => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}`;
}

async function newPage(t, { deviceScaleFactor = 1, timeout = 15000 } = {}) {
  const page = await browser.newPage({ viewport: { width: 960, height: 500 }, deviceScaleFactor });
  t.after(() => page.close());
  page.setDefaultTimeout(timeout);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  return { page, errors };
}
// Two frames on: what a change asked for has been drawn.
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));

// The shell end to end, in a real browser, under the smallest renderer that mounts it: a
// one-triangle mesh file. Everything asserted here is the shell's (kit/shell), so it holds
// for every renderer built on it. Inline fixture bytes are served in memory with a private
// temporary harness.
const mesh = 'solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 20 0 0\nvertex 0 20 0\nendloop\nendfacet\nendsolid triangle\n';

// A phone's navbar, its left end (`ViewerNavbar.jsx`): the toggle, the logo, the name and its ⋯, each 36px tall on one
// line, the first on the row's 8px inset, 4px between neighbours; a finger's tap leaves no fill or ring behind.
test('a phone\'s navbar starts regular: 36px controls 4px apart from the row\'s inset, and a tap leaves no fill or ring', async (t) => {
  const origin = await serve(t);
  const context = await browser.newContext({ viewport: { width: 390, height: 700 }, hasTouch: true, isMobile: true });
  t.after(() => context.close());
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  await page.goto(`${origin}/?file=panel.harness&home=1`);
  await page.addStyleTag({ content: '#root > div { width: 390px !important; height: 700px !important; }' });
  const pane = page.getByTestId('one');
  await pane.locator('[data-viewer-navbar] [data-testid="file-actions"]').waitFor();
  const SELECTORS = ['[data-navbar-panel="left"]', '[data-navbar-menu]', '[data-file-name]', '[data-testid="file-actions"]'];
  const row = () => pane.locator('[data-viewer-navbar]').evaluate((bar, selectors) => {
    const top = bar.getBoundingClientRect();
    const boxes = selectors.map(selector => bar.querySelector(selector).getBoundingClientRect());
    return { left: Math.round(boxes[0].left - top.left), heights: boxes.map(box => Math.round(box.height)), widths: [0, 1, 3].map(at => Math.round(boxes[at].width)),
      gaps: boxes.slice(1).map((box, at) => Math.round(box.left - boxes[at].right)), centred: boxes.every(box => Math.abs(box.top + box.height / 2 - (top.top + top.height / 2)) < 1) };
  }, SELECTORS);
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-viewer-navbar]').getBoundingClientRect().height === 48);
  assert.deepEqual(await row(), { left: 8, heights: [36, 36, 36, 36], widths: [36, 36, 36], gaps: [4, 4, 4], centred: true }, 'the left end, regular');
  const marks = selector => pane.locator(`[data-viewer-navbar] ${selector}`).evaluate(element => {
    const style = getComputedStyle(element);
    return { fill: style.backgroundColor, ring: element.matches(':focus-visible') };
  });
  for (const selector of ['[data-navbar-menu]', '[data-file-name]']) {
    await pane.locator(`[data-viewer-navbar] ${selector}`).tap();
    await page.waitForFunction(selector => document.querySelector(`[data-testid="one"] [data-viewer-navbar] ${selector}`).getAttribute('data-state') === 'open', selector);
    await page.touchscreen.tap(200, 500);
    await page.waitForFunction(selector => document.querySelector(`[data-testid="one"] [data-viewer-navbar] ${selector}`).getAttribute('data-state') === 'closed', selector);
    // Its colour transition (`transition-colors`) run out: what is left is what stays.
    await page.waitForFunction(selector => document.querySelector(`[data-testid="one"] [data-viewer-navbar] ${selector}`).getAnimations()
      .every(animation => animation.playState === 'finished'), selector);
    assert.deepEqual(await marks(selector), { fill: 'rgba(0, 0, 0, 0)', ring: false }, `${selector}: no fill or ring after a tap`);
  }
});

test('a phone\'s tools centre on the viewport as space runs out; its View and Preview are the navbar\'s', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.goto(`${origin}/?file=panel.harness`);
  const pane = page.getByTestId('one');
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  for (const width of [599, 390, 320, 240, 600, 599]) {
    await page.locator('#root > div').evaluate((element, width) => element.style.setProperty('width', `${width}px`, 'important'), width);
    await page.waitForFunction(width => {
      const pane = document.querySelector('[data-testid="one"]');
      const viewport = pane.querySelector('[data-cad-canvas]');
      const strip = pane.querySelector('[aria-label="Interaction tools"]');
      const column = pane.querySelector('[data-cad-tool-groups]');
      if (!viewport || !strip || !column) return false;
      const view = viewport.getBoundingClientRect(), tools = strip.getBoundingClientRect();
      const mobile = width < 600;
      if (Math.abs(view.width - width) > 1 || column.hasAttribute('data-mobile') !== mobile) return false;
      const expected = view.left + Math.max(8, (view.width - tools.width) / 2);
      return Math.abs(tools.left - expected) < 1 && tools.right <= view.right - 7;
    }, width);
  }
  // At 599 every tool fits, and the navbar's right end is View and Preview alone: no More, no cube, no zoom.
  assert.equal(await pane.getByRole('button', { name: 'More tools', exact: true }).count(), 0);
  assert.deepEqual(await pane.locator('[data-navbar-view] [data-navbar-view-controls] > *').evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-label'))), ['View', 'Preview']);
  assert.deepEqual([await pane.locator('[data-view-cube]').count(), await pane.locator('[data-zoom-pill]').count()], [0, 0]);
  assert.deepEqual(errors, []);
});

// ONE FRAME (`kit/shell/ViewFrame.jsx`), over a 3D view (the harness) and a flat one (a drawing with
// layers): the strip stands on the centre of the WHOLE view however the left panel is opened and shut; a panel that
// pushes takes its width out of the canvas, the picture drawn in what it leaves, centred on it; and on a phone the
// strip is centred with no panel.
const LAYERED = JSON.parse(await readFile(new URL('../../dxf/__fixtures__/layered.drawing.json', import.meta.url), 'utf8'));
const drawingRoute = (url, root, response) => {
  if (url.pathname.endsWith('/drawing')) { response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(LAYERED)); return true; }
  if (!url.pathname.endsWith('/api/v1/documents')) return false;
  response.setHeader('Content-Type', 'application/json');
  response.end(JSON.stringify({ id: 'layered.dxf', kind: 'dxf', api: '/api/v1/documents/dxf/layered.dxf',
    documents: [{ entry: { kind: 'dxf', file: '/models/layered.dxf', url: '/layered.dxf', hash: `${root}-layered`, bytes: 4096 }, revision: `${root}-layered` }] }));
  return true;
};
for (const [what, file, route, groups] of [['a 3D view', 'panel.harness', undefined, ['projection', 'display', 'background', 'grid']],
  ['a flat view', 'layered.dxf', drawingRoute, ['background']]]) {
  test(`${what}: the strip stays at the view's centre as the panel opens and shuts, the picture is centred in what a pushed panel leaves, and a phone's panel is a sheet, its View the desktop's menu`, async (t) => {
    const origin = await serve(t, route);
    const { page, errors } = await newPage(t);
    await page.addInitScript(() => { window.Worker = undefined; });
    await page.goto(`${origin}/?file=${file}`);
    const pane = page.getByTestId('one');
    const strip = pane.getByRole('group', { name: 'Interaction tools' });
    await strip.waitFor();
    // The strip's centre against the view's, the canvas's box against the stage's, the panel's width.
    const measure = () => page.evaluate(() => {
      const pane = document.querySelector('[data-testid="one"]');
      const box = element => element?.getBoundingClientRect() ?? null;
      const view = box(pane.querySelector('[data-slot="cad-file-view"]')), stage = box(pane.querySelector('[data-cad-canvas]'));
      const tools = box(pane.querySelector('[aria-label="Interaction tools"]'));
      const canvas = [...pane.querySelectorAll('[data-cad-canvas] canvas')].map(box).sort((a, b) => b.width * b.height - a.width * a.height)[0];
      const panel = pane.querySelector('aside[data-flat-panel]');
      // An overlaid panel covers the stage's edge: the model's area is what it leaves.
      const over = [...pane.querySelectorAll('aside[data-flat-panel]')].filter(aside => !aside.hidden && getComputedStyle(aside).position === 'absolute').map(box);
      const left = Math.max(stage.left, ...over.filter(aside => aside.left <= stage.left + 1).map(aside => aside.right));
      const right = Math.min(stage.right, ...over.filter(aside => aside.right >= stage.right - 1).map(aside => aside.left));
      return { view: view.left + view.width / 2, area: (left + right) / 2, strip: tools.left + tools.width / 2, stage: stage.left + stage.width / 2, stageWidth: stage.width,
        canvas: canvas.left + canvas.width / 2, canvasWidth: canvas.width, panel: panel && !panel.hidden ? box(panel).width : 0,
        pushed: Boolean(panel && !panel.hidden && getComputedStyle(panel).position !== 'absolute') };
    });
    // At 960px the left panel starts open (the model keeps 640px beside its 240px), pushing the model aside; shut
    // from the navbar's toggle, and opened again from it.
    await page.waitForFunction(() => !document.querySelector('[data-testid="one"] aside[data-flat-panel]')?.hidden);
    await settle(page);
    const open = await measure();
    // Every tab's name whole, Search beside the tabs, none over another or past the panel, at the panel's narrowest
    // (Home on its grip): that is what the head needs.
    const head = () => page.evaluate(() => {
      const aside = document.querySelector('[data-testid="one"] aside[data-flat-panel]');
      const row = aside.querySelector('[data-flat-panel-head]');
      const shown = [...row.children].filter(child => !child.hidden).map(child => child.getBoundingClientRect());
      return { width: aside.getBoundingClientRect().width,
        whole: [...row.querySelectorAll('[role=tab], [data-flat-panel-tab-name]')].every(element => element.scrollWidth <= element.clientWidth + 0.5),
        apart: shown.every((box, at) => at === 0 || shown[at - 1].right <= box.left + 0.5),
        inside: shown.at(-1).right <= aside.getBoundingClientRect().right - 8 + 0.5 };
    });
    await pane.getByRole('separator', { name: 'Resize panel', exact: true }).focus();
    await page.keyboard.press('Home');
    await settle(page);
    const narrowest = await head();
    assert.deepEqual([narrowest.whole, narrowest.apart, narrowest.inside], [true, true, true], `at its narrowest, the head's row whole: ${JSON.stringify(narrowest)}`);
    await pane.getByRole('button', { name: 'Hide panel', exact: true }).click();
    await settle(page);
    const shut = await measure();
    assert.equal(await pane.locator('[data-flat-panel-pill]').count(), 0, 'a collapsed panel leaves nothing over the model');
    await pane.getByRole('button', { name: 'Show panel', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('[data-testid="one"] aside[data-flat-panel]').hidden);
    await settle(page);
    const pushed = await measure();
    for (const [state, at] of [['open', open], ['shut', shut], ['opened again', pushed]]) {
      assert.ok(Math.abs(at.strip - at.view) <= 1, `${state}, the strip is at the view's centre: ${at.strip} of ${at.view}`);
      assert.ok(Math.abs(at.canvas - at.stage) <= 1 && Math.abs(at.canvasWidth - at.stageWidth) <= 1, `${state}, the picture fills the stage, centred on it: ${JSON.stringify(at)}`);
    }
    assert.ok(open.pushed && pushed.pushed && shut.panel === 0, 'the panel always pushes');
    assert.ok(pushed.stageWidth <= shut.stageWidth - pushed.panel + 1, 'a pushed panel takes its width out of the canvas');
    // A phone: no docked panel, no pill, the strip centred in the view.
    await page.locator('#root > div').evaluate(element => element.style.setProperty('width', '390px', 'important'));
    await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-tool-groups]')?.hasAttribute('data-mobile'));
    await settle(page);
    const phone = await measure();
    assert.ok(Math.abs(phone.strip - phone.view) <= 1, `on a phone the strip is at the view's centre: ${phone.strip} of ${phone.view}`);
    assert.equal(await pane.locator('[data-flat-panel], [data-zoom-pill], [data-view-cube]').count(), 0, 'a phone has no docked panel, pill or cube');
    // Its panel is a sheet from the left under the navbar, over the model with no scrim and no slide, opened by the
    // navbar's toggle; a tap outside shuts it, at once, and focus goes back to the toggle.
    await pane.locator('[data-navbar-panel="left"]').click();
    const sheet = page.locator('[data-panel-sheet]');
    await sheet.waitFor();
    const placed = await page.evaluate(() => {
      const box = document.querySelector('[data-panel-sheet]').getBoundingClientRect();
      const overlay = document.querySelector('[data-slot="sheet-overlay"]');
      const style = getComputedStyle(document.querySelector('[data-panel-sheet]'));
      return { left: Math.round(box.left), top: Math.round(box.top), navbar: Math.round(document.querySelector('[data-testid="one"] [data-viewer-navbar]').getBoundingClientRect().bottom),
        scrim: overlay ? getComputedStyle(overlay).backgroundColor : null, animation: style.animationName, focused: document.activeElement?.closest('[data-panel-sheet]') !== null };
    });
    assert.deepEqual(placed, { left: 0, top: placed.navbar, navbar: placed.navbar, scrim: 'rgba(0, 0, 0, 0)', animation: 'none', focused: true },
      `in at once at the left edge, its top the navbar's bottom, nothing dimmed, focus in it: ${JSON.stringify(placed)}`);
    assert.equal(await sheet.locator('[data-flat-panel]').getAttribute('data-flat-panel'), 'page');
    await page.mouse.click(380, 300);
    assert.equal(await sheet.count(), 0, 'gone at once');
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('data-navbar-panel')), 'left', 'focus back on the toggle');
    // The navbar's toggle, in sight above it, shuts it too.
    await pane.locator('[data-navbar-panel="left"]').click();
    await sheet.waitFor();
    await pane.locator('[data-navbar-panel="left"]').click();
    await settle(page);
    assert.equal(await sheet.count(), 0, 'the toggle shuts it');
    // View opens the desktop's menu (no bottom sheet), its submenus and check rows the file's, Reset view last; a tap
    // outside shuts it. Pressed over the open sheet, it shuts the sheet and opens its menu, the one press.
    await pane.locator('[data-navbar-panel="left"]').click();
    await sheet.waitFor();
    await pane.locator('[data-view-menu]').click();
    const viewMenu = page.locator('[role=menu][aria-label="View"]');
    await viewMenu.waitFor();
    assert.equal(await sheet.count(), 0, 'View, pressed over the sheet, shut it');
    assert.deepEqual(await viewMenu.locator('[data-view-sub], [data-view-toggle]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-view-sub') ?? node.getAttribute('data-view-toggle'))), groups);
    assert.equal(await viewMenu.locator('[data-view-reset]').count(), 1);
    assert.equal(await page.locator('[data-slot=drawer-content]').count(), 0, 'no bottom sheet');
    await settle(page);
    await page.mouse.click(200, 500);
    await viewMenu.waitFor({ state: 'detached' });
    assert.deepEqual(errors, []);
  });
}

// THE type scale (docs/settings-ui.md, "The type scale"), as a page computes it: a panel row and a menu item at
// 12/16, a tooltip at 11/16, the navbar at 13/20. And the strip's proportions: a 40px bar of 28px tiles 5px in, its
// corners 10px, theirs 4px; the panel's head a 32px row of the same tiles, its rule on the strip's bottom line; the
// panels' toggles the navbar's 28px tiles.
test('the type scale and the strip\'s proportions, as drawn: the panel, a menu, a tooltip and the navbar; the strip, the panel\'s head and the navbar\'s toggles', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.setViewportSize({ width: 1100, height: 600 });
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=panel.harness`);
  await page.addStyleTag({ content: '#root > div { width: 1100px !important; height: 600px !important; }' });
  const pane = page.getByTestId('one');
  const strip = pane.getByRole('group', { name: 'Interaction tools' });
  await strip.waitFor();
  const type = locator => locator.evaluate(element => { const style = getComputedStyle(element); return [style.fontSize, style.lineHeight]; });
  const box = locator => locator.evaluate(element => { const { top, bottom, height, width } = element.getBoundingClientRect(); const style = getComputedStyle(element);
    return { top: Math.round(top), bottom: Math.round(bottom), height: Math.round(height), width: Math.round(width), radius: style.borderTopLeftRadius, padding: style.paddingTop }; });
  const bar = await box(strip), tile = await box(strip.getByRole('button', { name: 'Keep', exact: true }));
  assert.deepEqual([bar.height, bar.radius, bar.padding, tile.height, tile.width, tile.radius], [40, '10px', '5px', 28, 28, '4px'], `the strip: ${JSON.stringify([bar, tile])}`);
  // The panels' toggles are the navbar's: 28px tiles on its 40px row, nothing of a collapsed panel over the model.
  const navbar = await box(pane.locator('[data-viewer-navbar]')), toggle = await box(pane.locator('[data-navbar-panel="left"]'));
  assert.deepEqual([navbar.height, toggle.height, toggle.width], [40, 28, 28], `the navbar's toggle: ${JSON.stringify([navbar, toggle])}`);
  if (await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').count()) await pane.locator('[data-navbar-panel="left"]').click();
  const head = pane.locator('[data-flat-panel-head]');
  await head.waitFor();
  const row = await head.evaluate(element => { const style = getComputedStyle(element); return Math.round(element.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)); });
  const pill = await box(head.getByRole('tab').first());
  assert.deepEqual([row, pill.height, (await box(head)).bottom], [32, 28, bar.bottom + 1], 'the head: a 32px row of 28px pills, its rule just under the strip');
  // The type, where it is drawn.
  assert.deepEqual(await type(pane.locator('aside[data-flat-panel] li').first()), ['12px', '16px'], 'a panel row');
  assert.deepEqual(await type(pane.locator('[data-viewer-navbar] [data-file-name]').first()), ['13px', '20px'], 'the navbar');
  await pane.getByRole('button', { name: 'Keep', exact: true }).hover();
  assert.deepEqual(await type(page.locator('[data-slot="tooltip-content"]').first()), ['11px', '16px'], 'a tooltip');
  await page.mouse.move(0, 0);
  await pane.locator('[data-cad-canvas]').click({ button: 'right', position: { x: 500, y: 300 } });
  assert.deepEqual(await type(page.getByRole('menuitem', { name: 'Note the press', exact: true })), ['12px', '16px'], 'a menu item');
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
});

// In the dark (the harness's app), a toolbar button under the pointer is seen: its fill, lighter or darker as its surface
// is (the corner's is the light viewport's), never the base Button's ghost hover, which matched the surface — the strip, the
// panel's head, and the corner's control, over the dark canvas and over a light viewport.
test('a toolbar button under the pointer is seen on its surface in the dark, over a light viewport: the strip, the panel head and the corner', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.setViewportSize({ width: 1100, height: 600 });
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=panel.harness&background=light`);
  const pane = page.getByTestId('one');
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  assert.equal(await pane.evaluate(element => Boolean(element.closest('.dark'))), true, 'the dark app');
  // The pixels of a control's middle, as drawn: their mean, at rest and under the pointer.
  const mean = async locator => {
    const box = await locator.boundingBox();
    const shot = await page.screenshot({ clip: { x: box.x + 2, y: box.y + 2, width: 4, height: 4 } });
    const { PNG } = await import('pngjs');
    const png = PNG.sync.read(shot);
    let sum = 0;
    for (let at = 0; at < png.data.length; at += 4) sum += (png.data[at] + png.data[at + 1] + png.data[at + 2]) / 3;
    return sum / (png.data.length / 4);
  };
  const seen = async (name, locator, target = locator) => {
    await page.mouse.move(0, 0);
    await page.waitForTimeout(250);
    const rest = await mean(target);
    await locator.hover();
    await page.waitForTimeout(250);
    const hovered = await mean(target);
    assert.ok(Math.abs(hovered - rest) >= 6, `${name}: the hover fill is seen (${rest.toFixed(1)} -> ${hovered.toFixed(1)})`);
  };
  await seen('a strip tool', pane.getByRole('button', { name: 'Keep', exact: true }));
  // A tool with a menu (this harness's has none; `FloatingToolBar.test.tsx` holds its classes) is the strip's fill round both.
  if (await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').count()) await pane.locator('[data-navbar-panel="left"]').click();
  await seen('the panel head', pane.locator('[data-flat-panel-head]').getByRole('tab', { selected: false }).first());
  await seen('View', pane.locator('[data-navbar-view-controls] [data-view-menu]'));
  assert.deepEqual(errors, []);
});

// Preview's chrome over the model is drawn in the backdrop's ink, not the app's: in the dark app over a light backdrop
// (the viewport's Background light, so Preview's own backdrop white), its name and its buttons read dark on it.
test('Preview\'s bar takes the backdrop\'s ink: dark text on a light backdrop in the dark app, at 4.5:1 or more', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.goto(`${origin}/?file=panel.harness&background=light`);
  const pane = page.getByTestId('one');
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  assert.equal(await pane.evaluate(element => Boolean(element.closest('.dark'))), true, 'the dark app');
  await pane.getByRole('button', { name: 'Preview', exact: true }).click();
  const bar = pane.locator('[data-preview-bar]');
  await bar.waitFor();
  const read = await bar.evaluate(element => {
    const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
    const lum = ([r, g, b]) => [r, g, b].map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
      .reduce((sum, v, at) => sum + v * [0.2126, 0.7152, 0.0722][at], 0);
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const backdrop = [255, 255, 255];
    const name = element.querySelector('[data-preview-name]'), button = element.querySelector('[data-preview-controls] button');
    return { scheme: element.getAttribute('data-scheme'), name: ratio(rgb(getComputedStyle(name).color), backdrop), button: ratio(rgb(getComputedStyle(button).color), backdrop) };
  });
  assert.equal(read.scheme, 'light');
  assert.ok(read.name >= 4.5 && read.button >= 4.5, `the bar reads on the backdrop: ${JSON.stringify(read)}`);
  assert.deepEqual(errors, []);
});

test('a shell renderer restores isolated view state on a remount', async (t) => {
  const requests = [];
  const catalogFiles = [];
  const origin = await serve(t, (url, root, response) => {
    requests.push(url.pathname);
    if (url.pathname.endsWith('/api/v1/documents')) {
      // The catalog holds the files on screen: asked for one by its absolute path, it lists it.
      response.setHeader('Content-Type', 'application/json');
      catalogFiles.push({ root, file: url.searchParams.get('path') });
      const entries = url.searchParams.get('path') === '/models/part.stl'
        ? [{ kind: 'stl', file: '/models/part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }] : [];
      response.end(JSON.stringify({ documents: entries.map(entry => ({ entry, revision: entry.hash })) }));
      return true;
    }
    if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); return true; }
    return false;
  });
  // A Retina page: the drawing buffer is device pixels, and a quality switch resizes it.
  const { page, errors } = await newPage(t, { deviceScaleFactor: 2, timeout: 10000 });
  await page.addInitScript(() => {
    window.Worker = undefined;
    // A Retina quality switch resizes the drawing buffer. Every such clear
    // must be followed by its replacement draw in the SAME task, even while
    // shader preparation is asynchronous. Canvas identity alone cannot catch it.
    // A view of the GPU device is handed its frame (`transferFromImageBitmap`) at the end of the
    // frame's task: that is its redraw.
    const draws = new WeakMap();
    const drew = canvas => draws.set(canvas, (draws.get(canvas) || 0) + 1);
    window.cadBufferClears = [];
    for (const name of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) {
      const original = WebGL2RenderingContext.prototype[name];
      WebGL2RenderingContext.prototype[name] = function (...args) {
        drew(this.canvas);
        return original.apply(this, args);
      };
    }
    const transfer = ImageBitmapRenderingContext.prototype.transferFromImageBitmap;
    ImageBitmapRenderingContext.prototype.transferFromImageBitmap = function (...args) {
      drew(this.canvas);
      return transfer.apply(this, args);
    };
    for (const name of ['width', 'height']) {
      const property = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, name);
      Object.defineProperty(HTMLCanvasElement.prototype, name, { ...property, set(value) {
        property.set.call(this, value);
        if (this !== window.cadHarnessView?.canvas) return;
        const before = draws.get(this) || 0;
        queueMicrotask(() => queueMicrotask(() => window.cadBufferClears.push({ name, redrawn: (draws.get(this) || 0) > before })));
      } });
    }

    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
    }
  });
  await page.goto(`${origin}/`);
  const first = page.getByTestId('one');
  // A view's settings are View, the navbar's. A pane narrower than a phone's breakpoint (each of two side by side) has a
  // phone's strip and no cube: View is still the navbar's, the same menu (`ViewSettingsMenu.jsx`).
  const displayButton = pane => pane.locator('[data-view-menu]');
  const viewButton = pane => pane.locator('[data-view-menu]');
  const display = page.locator('[role=menu][aria-label="View"]');
  const cameraZoom = id => page.evaluate(pane => window.cadHarness[pane].controller?.readState().camera?.zoom ?? null, id);
  await displayButton(first).waitFor().catch(async (error) => { throw new Error(`${error.message}; page errors: ${errors.join('; ')}; body: ${await page.locator("body").innerText()}; requests: ${requests.join(", ")}`); });
  await page.waitForFunction(() => Object.keys(window.cadHarness.state.renderers || {}).length > 0);
  assert.ok(catalogFiles.some(({ root, file }) => root === 'one' && file === '/models/part.stl'), 'the file was read by its absolute path');

  // The camera is moved through the live controller: there is no zoom control in the viewer to press.
  // A view refuses commands until it has drawn its file (`liveBinding.ts`), which a software GL
  // takes longer to do than the stored record above takes to be written: wait for it, as for pane b.
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    await controller.setCamera({ ...controller.readState().camera, zoom: 1.1 });
  });
  await page.waitForFunction(() => Math.abs((window.cadHarness.a.controller.readState().camera?.zoom ?? 0) - 1.1) < 1e-6);

  // ISOLATED: a sibling renderer over the same file opens at its own framing, and the first
  // pane keeps the camera it was given.
  await page.evaluate(() => window.cadHarness.second(true));
  await viewButton(page.getByTestId('two')).waitFor();
  assert.equal(await page.getByTestId('two').locator('[data-view-cube], [data-zoom-pill]').count(), 0, 'and no corner');
  await page.waitForFunction(() => window.cadHarness.b.controller?.readState().loading === false);
  assert.equal(await cameraZoom('b'), 1, 'a sibling renderer opens at its own framing');
  assert.ok(requests.includes('/two/mesh.stl'));
  assert.ok(Math.abs(await cameraZoom('a') - 1.1) < 1e-6, 'the first pane kept the camera it was given');
  // A second pane changes the first viewport's dimensions. Let its resize
  // observer and camera event publish before taking the saved snapshot.
  await settle(page);

  // The file goes with its View menu open (the first pane is phone-wide now too): its submenus the 3D view's, the STL's
  // one mode in Display's, Grid a check row that toggles and leaves the menu open.
  await page.setViewportSize({ width: 800, height: 812 });
  await viewButton(first).click();
  await display.waitFor();
  assert.deepEqual(await display.locator('[data-view-sub], [data-view-toggle]').evaluateAll(rows => rows.map(row => row.getAttribute('data-view-sub') ?? row.getAttribute('data-view-toggle'))),
    ['projection', 'display', 'background', 'grid'], 'the menu\'s rows: Projection, Display, Background, Grid');
  await display.locator('[data-view-sub="display"]').click();
  assert.deepEqual(await page.locator('[data-view-sub-content="display"] [data-display-mode-option]').allInnerTexts(), ['Solid'], 'an STL of one mesh: Solid alone');
  assert.equal(await first.locator('[data-viewer-navbar] [data-navbar-panel]').count(), 1, 'an STL has its panel (its Model tab, its one body), so its toggle');
  const grid = display.locator('[data-view-toggle="grid"]');
  await grid.click();
  assert.equal(await grid.getAttribute('aria-checked'), 'true');
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().display.grid === true);
  assert.equal(await display.count(), 1, 'ticking Grid leaves the menu open');
  await page.evaluate(() => window.cadHarness.mounted(false));
  await display.waitFor({ state: 'detached' }).catch(async (error) => {
    const left = await page.evaluate(() => ({
      open: [...document.querySelectorAll('[role=menu]')].map(node => ({ settings: node.getAttribute('aria-label'), state: node.getAttribute('data-state'),
        pane: node.closest('[data-testid]')?.getAttribute('data-testid') ?? 'body' })),
      viewerOne: Boolean(document.querySelector('[data-testid="one"] [data-viewer-layout]')),
      layouts: [...document.querySelectorAll('[data-viewer-layout]')].map(node => `${node.closest('[data-testid]')?.getAttribute('data-testid')}:${node.getAttribute('data-viewer-layout')}`),
      triggers: [...document.querySelectorAll('button[aria-label^="Display mode"]')].map(node => `${node.closest('[data-testid]')?.getAttribute('data-testid')}:${node.closest('[data-viewer-navbar]') ? 'navbar' : 'view'}:${node.getAttribute('aria-expanded')}`),
    }));
    throw new Error(`${error.message}; still on the page: ${JSON.stringify(left)}; page errors: ${errors.join('; ')}`);
  });
  await first.locator('[data-slot="cad-file-view"]').waitFor({ state: 'detached' });
  // Unmount persists the display settings and the camera, under the file and the renderer.
  const before = await page.evaluate(() => window.cadHarness.state);
  assert.deepEqual(Object.keys(before.renderers), [JSON.stringify(['/models/part.stl', 'mesh'])], 'one record per file, keyed [absolute path, renderer id]');
  for (const saved of Object.values(before.renderers)) {
    assert.ok(Math.abs(saved.camera.zoom - 1.1) < 1e-6, `the camera is persisted: ${JSON.stringify(saved.camera)}`);
    assert.deepEqual([saved.display.mode, saved.display.grid], ['solid', true], 'and the display: its mode and the Grid switch');
  }
  await page.evaluate(() => window.cadHarness.mounted(true));
  // Whether View is open is transient, not file state.
  await viewButton(first).waitFor();
  assert.equal(await display.count(), 0, 'the remounted file opens with its View menu shut');
  assert.equal(await viewButton(first).getAttribute('aria-expanded'), 'false');
  // The pane remounts before the viewport adopts the mesh and publishes its restored
  // camera. Wait for the actual presented frame, not an arbitrary settling delay.
  await page.waitForFunction(() => {
    const pane = document.querySelector('[data-testid="one"]');
    return pane?.querySelector('[aria-busy="false"] canvas') &&
      !pane.querySelector('[data-viewer-transition], [data-viewer-loading]');
  });
  // The remount opens at the camera it was left at, not a fresh fit, and the record is unchanged.
  await page.waitForFunction(() => Math.abs((window.cadHarness.a.controller.readState().camera?.zoom ?? 0) - 1.1) < 1e-6);
  const after = await page.evaluate(() => window.cadHarness.state);
  assert.deepEqual(structuredClone(after.renderers), structuredClone(before.renderers));
  assert.equal(requests.filter((path) => path === '/one/mesh.stl').length, 1, 'reopening a file reuses its decoded mesh without another asset request');

  // The live canvas at Retina: a drag drops the drawing buffer to the interaction pixel ratio
  // and its end restores it. Every buffer that clears is drawn again in the same task.
  const canvas = first.locator('[aria-busy] > div > canvas').first();
  await canvas.evaluate(node => { window.cadHarnessView = { canvas: node }; });
  const box = await canvas.boundingBox();
  const idleWidth = await canvas.evaluate(node => node.width);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 20, { steps: 4 });
  await page.mouse.up();
  // Back at the idle ratio, whatever the drag did to it.
  await page.waitForFunction(width => document.querySelector('[data-testid="one"] [aria-busy] > div > canvas').width === width, idleWidth);
  await settle(page);
  const clears = await page.evaluate(() => window.cadBufferClears);
  // A software renderer never changes its pixel ratio, so there is no Retina resize to exercise.
  if (!(await softwareWebGl(page))) assert.ok(clears.length > 0, 'exercise actual Retina buffer resizes');
  assert.ok(clears.every(clear => clear.redrawn), 'no cleared framebuffer is left waiting for a later draw');
  assert.deepEqual(errors, []);
});

test('every view draws through the one GPU device: a view that goes leaves it and no listener on the page, and a lost device is recovered for the view on screen', async (t) => {
  const origin = await serve(t, (url, root, response) => {
    if (url.pathname.endsWith('/api/v1/documents')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ documents: ([{ kind: 'stl', file: '/models/part.stl', url: '/mesh.stl', hash: root, bytes: mesh.length }]).map(entry => ({ entry, revision: entry.hash })) }));
      return true;
    }
    if (url.pathname.endsWith('/mesh.stl')) { response.end(mesh); return true; }
    return false;
  });
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => {
    window.Worker = undefined;
    // Every WebGL context the page makes, on a canvas or off one, and the keydown listeners on the
    // window and the document, counted as the DOM keeps them (one per listener and capture flag).
    const contexts = [];
    for (const Canvas of [HTMLCanvasElement, OffscreenCanvas]) {
      const getContext = Canvas.prototype.getContext;
      Canvas.prototype.getContext = function (type, ...rest) {
        const context = getContext.call(this, type, ...rest);
        if (context && /webgl/.test(type) && !contexts.includes(context)) contexts.push(context);
        return context;
      };
    }
    window.cadContexts = contexts;
    window.cadContextsLost = () => contexts.map(context => context.isContextLost());
    const keydown = new Set(), ids = new WeakMap();
    let next = 0;
    const key = (target, listener, options) => {
      if (!ids.has(listener)) ids.set(listener, next += 1);
      return `${target === window ? 'window' : 'document'}:${ids.get(listener)}:${typeof options === 'boolean' ? options : options?.capture === true}`;
    };
    const { addEventListener, removeEventListener } = EventTarget.prototype;
    EventTarget.prototype.addEventListener = function (type, listener, options) {
      if (type === 'keydown' && listener && (this === window || this === document)) keydown.add(key(this, listener, options));
      return addEventListener.call(this, type, listener, options);
    };
    EventTarget.prototype.removeEventListener = function (type, listener, options) {
      if (type === 'keydown' && listener && (this === window || this === document)) keydown.delete(key(this, listener, options));
      return removeEventListener.call(this, type, listener, options);
    };
    window.cadKeydownListeners = () => keydown.size;
  });
  await page.goto(`${origin}/`);
  const shown = () => page.waitForFunction(() => window.cadHarness?.a?.controller?.readState().loading === false
    && !!document.querySelector('[data-testid="one"] [aria-busy="false"] canvas'));
  const gone = () => page.waitForFunction(() => !document.querySelector('[data-testid="one"] canvas'));
  const state = () => page.evaluate(() => ({ contexts: window.cadContextsLost(), views: window.__cadGpuDevice?.().views ?? null,
    keydown: window.cadKeydownListeners() }));
  await shown();
  const keydown = await page.evaluate(() => window.cadKeydownListeners());
  assert.deepEqual(await state(), { contexts: [false], views: 1, keydown }, 'one context, the device\'s, and one view of it');

  // A file switch, or a library card pictured: the view goes and another comes. The next view draws
  // through the same device (its buffers and programs kept), and the page keeps no listener of the
  // controls that went.
  for (let remount = 1; remount <= 3; remount += 1) {
    await page.evaluate(() => window.cadHarness.mounted(false));
    await gone();
    await page.evaluate(() => window.cadHarness.mounted(true));
    await shown();
    assert.deepEqual(await state(), { contexts: [false], views: 1, keydown }, `after remount ${remount}`);
  }

  // The device's context lost and restored: the view on screen draws again, in the same device, and
  // is a viewer: the camera orbits under a drag.
  await page.evaluate(() => new Promise(resolve => {
    const extension = window.cadContexts[0].getExtension('WEBGL_lose_context');
    window.cadContexts[0].canvas.addEventListener('webglcontextlost', () => setTimeout(() => { extension.restoreContext(); resolve(); }), { once: true });
    extension.loseContext();
  }));
  await page.waitForFunction(() => !window.cadContexts[0].isContextLost());
  await shown();
  assert.deepEqual(await state(), { contexts: [false], views: 1, keydown });
  const before = await page.evaluate(() => window.__cadCamera().position);
  const box = await page.getByTestId('one').locator('[aria-busy="false"] > div > canvas').first().boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 20, { steps: 4 });
  await page.mouse.up();
  await page.waitForFunction(start => window.__cadCamera().position.some((value, index) => Math.abs(value - start[index]) > 1e-3), before);

  // The last view goes: the device holds none, and no test seam keeps a runtime on the window.
  await page.evaluate(() => window.cadHarness.mounted(false));
  await gone();
  await page.waitForFunction(() => window.__cadGpuDevice?.().views === 0);
  assert.deepEqual(await page.evaluate(() => [typeof window.__cadCamera, typeof window.__cadStage]), ['undefined', 'undefined']);
  assert.deepEqual(errors, []);
});

// A wide, flat box: the shape whose fit is decided by its WIDTH against the viewport's
// aspect, so a fit taken under the wrong lens or the wrong canvas shows up immediately.
// (A tall or cubic model is fitted by its height and hides the difference entirely.)
const WIDE_CORNERS = [[0, 0, 0], [140, 0, 0], [140, 80, 0], [0, 80, 0], [0, 0, 2], [140, 0, 2], [140, 80, 2], [0, 80, 2]];
const WIDE_TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]];
const widePlate = `solid plate\n${WIDE_TRIANGLES.map(triangle =>
  `facet normal 0 0 0\nouter loop\n${triangle.map(index => `vertex ${WIDE_CORNERS[index].join(' ')}`).join('\n')}\nendloop\nendfacet`
).join('\n')}\nendsolid plate\n`;

test('a file opens framed at 100% of its own ruler: the open fit is the fit, whatever lens it was taken under', async (t) => {
  const origin = await serve(t, (url, root, response) => {
    if (url.pathname.endsWith('/api/v1/documents')) {
      response.setHeader('Content-Type', 'application/json');
      response.end(JSON.stringify({ documents: ([
        { kind: 'stl', file: '/models/plate.stl', url: '/plate.stl', hash: root, bytes: widePlate.length }]).map(entry => ({ entry, revision: entry.hash })) }));
      return true;
    }
    if (url.pathname.endsWith('/plate.stl')) { response.end(widePlate); return true; }
    return false;
  });
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=plate.stl`);
  const pane = page.getByTestId('one');
  await pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
  await page.waitForFunction(() => window.cadHarness.a.controller?.readState().loading === false);
  await settle(page);

  const opened = await page.evaluate(() => {
    const camera = window.__cadCamera();
    const canvas = document.querySelector('[data-testid="one"] [aria-busy] > div > canvas');
    const strip = Number.parseFloat(getComputedStyle(canvas.closest('[data-slot=cad-file-view]')).getPropertyValue('--cad-tools-bottom')) || 0;
    return { projection: camera.projection, halfHeight: camera.halfHeight, zoomPercent: camera.zoomPercent,
      bounds: camera.originalBounds, aspect: canvas.clientWidth / canvas.clientHeight, room: [strip, canvas.clientHeight] };
  });
  assert.equal(opened.projection, 'orthographic');
  // 100% means "framed as the file opens". It is a ruler the viewport computes independently
  // of the fit, so the two agreeing is the whole claim: a fit taken under the opening
  // PERSPECTIVE lens and then converted to orthographic used to land near 89% of it.
  assert.equal(Math.round(opened.zoomPercent), 100, `opened at ${opened.zoomPercent}% of its own ruler`);
  // And it is the half-height the fit mathematics gives for this box at the REAL canvas aspect, in the
  // room the strip leaves under it.
  const expected = interactiveCameraFrameForBounds(THREE, {
    camera: Object.assign(new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 1000), { fov: CAD_DEFAULT_VERTICAL_FOV_DEGREES }),
    controls: { target: new THREE.Vector3() }, bounds: opened.bounds, frameAspect: opened.aspect,
    minRadius: 0, viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP, room: fitRoom(...opened.room),
  }).halfHeight;
  assert.ok(Math.abs(opened.halfHeight - expected) / expected < 0.01,
    `framed at the fit for this aspect: ${opened.halfHeight} vs ${expected}`);

  // Zoom to fit frames the model again; cube faces keep the current zoom and target.
  const canvas = pane.locator('[aria-busy] > div > canvas').first();
  // The share of the drawn frame that is the model: read the middle/upper canvas region,
  // clear of the bottom prompt action and the viewport controls at the right edge, with the strip
  // (the view's controls, over the top centre) hidden: the canvas's own pixels.
  const inkFraction = async () => {
    const png = PNG.sync.read(await canvas.screenshot({ style: '[data-cad-tool-groups] { visibility: hidden !important; }' }));
    const background = [png.data[0], png.data[1], png.data[2]];
    const columns = Math.floor(png.width * 0.8);
    const rows = Math.floor(png.height * 0.8);
    let drawn = 0;
    for (let y = 0; y < rows; y += 1) for (let x = 0; x < columns; x += 1) {
      const offset = (y * png.width + x) * 4;
      const delta = Math.abs(png.data[offset] - background[0]) + Math.abs(png.data[offset + 1] - background[1])
        + Math.abs(png.data[offset + 2] - background[2]);
      if (delta > 32) drawn += 1;
    }
    return drawn / (columns * rows);
  };
  const settleInk = async (reached, what) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const ink = await inkFraction();
      if (reached(ink)) return ink;
      await settle(page);
    }
    throw new Error(`the drawn frame never ${what}`);
  };
  assert.ok(await settleInk(ink => ink > 0.05, 'showed the plate') > 0.05);
  // Zoomed right in and dragged far off it: the model is no longer on screen.
  await page.evaluate(async () => {
    const controller = window.cadHarness.a.controller;
    const camera = controller.readState().camera;
    await controller.setCamera({ ...camera, target: [camera.target[0] + 4000, camera.target[1] + 4000, camera.target[2]],
      position: [camera.position[0] + 4000, camera.position[1] + 4000, camera.position[2]], zoom: 9 });
  });
  const lost = await settleInk(ink => ink < 0.01, 'emptied when the camera was driven off the model');

  const beforeSnap = await page.evaluate(() => window.__cadCamera());
  await pane.getByRole('button', { name: 'Jump to top view', exact: true }).click();
  await page.waitForFunction(() => { const c = window.__cadCamera(); return Math.hypot(c.position[0] - c.target[0], c.position[1] - c.target[1]) / Math.abs(c.position[2] - c.target[2]) < 0.001; });
  const snapped = await page.evaluate(() => window.__cadCamera());
  snapped.target.forEach((value, index) => assert.ok(Math.abs(value - beforeSnap.target[index]) < 1e-8));
  assert.equal(snapped.zoom, beforeSnap.zoom);
  // Reset view, View's last row (the view the file opened with: `ShellChrome.test.tsx` presses it); no Home on the picture.
  assert.equal(await pane.locator('[data-view-home]').count(), 0, 'no Home on the picture');
  await page.evaluate(() => window.cadHarness.a.controller.resetCamera());
  const recovered = await settleInk(ink => ink > 0.05, 'Zoom to Fit frames the plate after panning away');
  assert.ok(recovered > lost * 5);
  const fitted = await page.evaluate(() => window.__cadCamera());
  assert.ok(Math.hypot(fitted.position[0] - fitted.target[0], fitted.position[1] - fitted.target[1]) / Math.abs(fitted.position[2] - fitted.target[2]) < 0.001,
    'Zoom to fit retains the top-view orientation');
  assert.deepEqual(errors, []);
});

// A scene a renderer publishes in pieces, under the harness-only renderer over one triangle
// (`renderers/shell-harness`): the viewport draws what has arrived, and frames it once whole.
test('a scene that arrives in place is framed when whole', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvasElement = pane.locator('[aria-busy="false"] > div > canvas').first();
  await canvasElement.waitFor();
  // The drawn frame: how much of it is the triangle, and whether it runs off the edge.
  const drawn = async () => {
    const png = PNG.sync.read(await canvasElement.screenshot());
    const { width, height, data } = png;
    const background = [data[8 * 4 * width + 32], data[8 * 4 * width + 33], data[8 * 4 * width + 34]];
    let painted = 0, atEdge = 0;
    for (let y = 0; y < height; y += 2) for (let x = 0; x < width; x += 2) {
      const at = (y * width + x) * 4;
      // The triangle is a flat blue-grey; the grid lines and the axes are thin and sampled away by the solid test.
      const solid = Math.abs(data[at] - background[0]) + Math.abs(data[at + 1] - background[1]) + Math.abs(data[at + 2] - background[2]) > 60
        && data[at + 2] > data[at] + 8;
      if (!solid) continue;
      painted += 1;
      if (x < 6 || y < 6 || x > width - 8 || y > height - 8) atEdge += 1;
    }
    return { painted, atEdge };
  };
  const waitForFrame = async (accept, what) => {
    let last;
    for (let attempt = 0; attempt < 80; attempt += 1) {
      last = await drawn();
      if (accept(last)) return last;
      await settle(page);
    }
    assert.fail(`the drawn frame never ${what}: ${JSON.stringify(last)}`);
  };

  // A SCENE THAT ARRIVES IN PLACE. The same scene identity grows fourfold and says it is not
  // whole yet: the viewport adopts what arrived (it is drawn, larger) but does NOT re-frame,
  // so the triangle runs off the canvas. When the scene says it is whole, it is framed again.
  const opened = await waitForFrame(frame => frame.painted > 500 && frame.atEdge === 0, 'showed the framed triangle');
  // The pose: where the camera looks from (its direction), at, and its zoom. How far back an
  // orthographic eye stands is no part of the picture (`kit/camera/orthographicEye.js`).
  const pose = () => page.evaluate(() => { const c = window.__cadCamera(); const d = c.position.map((v, i) => v - c.target[i]); const l = Math.hypot(...d); return [d.map(v => v / l), c.target, c.zoom]; });
  // The opened camera once it is at rest: the same over several frames running.
  await page.waitForFunction(() => new Promise(resolve => {
    let still = 0, last = null;
    const step = () => {
      const c = window.__cadCamera();
      const now = JSON.stringify([c.position, c.target, c.zoom]);
      still = now === last ? still + 1 : 0;
      last = now;
      if (still >= 5) resolve(true); else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));
  const openedPose = await pose();
  await pane.locator('[data-harness-arrive="partial"]').click();
  const partial = await waitForFrame(frame => frame.painted > opened.painted * 3 && frame.atEdge > 0,
    'drew the grown scene, unframed, while it was still arriving');
  // Not reframed: the pose is the opened one, to within the float noise of a settled camera
  // (a reframe moves it by the scene's own size, four orders of magnitude more).
  const partialPose = (await pose()).flat();
  openedPose.flat().forEach((value, index) => assert.ok(Math.abs(value - partialPose[index]) < 1e-4,
    `the camera did not move for a partial arrival (${index}: ${value} → ${partialPose[index]})`));
  await pane.locator('[data-harness-arrive="whole"]').click();
  const whole = await waitForFrame(frame => frame.atEdge === 0 && frame.painted > 500 && frame.painted < partial.painted,
    'framed the scene once it was whole');
  assert.ok(Math.abs(whole.painted - opened.painted) < opened.painted * 0.2,
    `the whole scene fills the frame as the first one did: ${JSON.stringify({ opened, whole })}`);
  assert.deepEqual(errors, []);
});

// That second framing is for a camera NOBODY set. A view the person turned with the arrow keys
// while the scene was still arriving is theirs, as a dragged one is, and the whole scene keeps it.
test('a view turned with the arrow keys while a scene arrives is kept when it is whole', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvas = pane.locator('[aria-busy="false"] > div > canvas').first();
  await canvas.waitFor();
  // Where the camera looks from (its direction), at, and its zoom (`kit/camera/orthographicEye.js`).
  const pose = () => page.evaluate(() => { const c = window.__cadCamera(); const d = c.position.map((v, i) => v - c.target[i]); const l = Math.hypot(...d); return [...d.map(v => v / l), ...c.target, c.zoom]; });
  // The camera at rest: the same over several frames running.
  const atRest = () => page.waitForFunction(() => new Promise(resolve => {
    let still = 0, last = null;
    const step = () => {
      const c = window.__cadCamera();
      const now = JSON.stringify([c.position, c.target, c.zoom]);
      still = now === last ? still + 1 : 0;
      last = now;
      if (still >= 5) resolve(true); else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));
  await atRest();
  const opened = await pose();
  // Over the viewer, with nothing focused: its arrow keys orbit it. No press, which would be a drag.
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.keyboard.press('ArrowLeft');
  await atRest();
  const turned = await pose();
  assert.ok(turned.some((value, index) => Math.abs(value - opened[index]) > 1e-3), 'the arrow key turned the view');
  await pane.locator('[data-harness-arrive="whole"]').click();
  await page.waitForFunction(() => window.__cadCamera().originalBounds?.max?.[0] === 80);
  await atRest();
  (await pose()).forEach((value, index) => assert.ok(Math.abs(value - turned[index]) < 1e-6,
    `the whole scene kept the turned view (${index}: ${turned[index]} → ${value})`));
  assert.deepEqual(errors, []);
});

test('a renderer says more about its load than a download: finding the file, edit states, a failed update the model survives, the revision on screen, its own snapshot and its own frame', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  await page.goto(`${origin}/?file=one.harness`);
  const pane = page.getByTestId('one');
  const canvasElement = pane.locator('[aria-busy="false"] > div > canvas').first();
  const canvas = await canvasElement.boundingBox();
  const middle = { x: canvas.x + canvas.width / 2, y: canvas.y + canvas.height / 2 };
  const stage = name => pane.locator(`[data-harness-stage="${name}"]`).click();
  // What the shell draws over the viewport about a load: the overlay that covers a model
  // still opening, and the card for an alert. Nothing is drawn beside the filename any more.
  const overlay = pane.locator('[data-viewer-loading]');
  const card = pane.getByRole('alert');
  // The DRAWN frame, and how much of it is the triangle: its lit blue-grey, counted below the
  // harness's own controls along the top, and outside `hole` (a box in canvas pixels).
  const shot = async () => PNG.sync.read(await canvasElement.screenshot());
  // The frame once it shows what `accept` asks of it: never the one frame after a change.
  const shotWhere = async (accept, what) => {
    let last;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      last = await shot();
      if (accept(last)) return last;
      await settle(page);
    }
    assert.fail(`the drawn frame never ${what}`);
  };
  // The frame at rest: the same picture twice running.
  const stillShot = async () => {
    let last = await canvasElement.screenshot();
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await settle(page);
      const next = await canvasElement.screenshot();
      if (next.equals(last)) return PNG.sync.read(next);
      last = next;
    }
    assert.fail('the drawn frame never came to rest');
  };
  const triangle = ({ width, height, data }, hole = null) => {
    let count = 0;
    for (let y = 48; y < height; y += 2) for (let x = 0; x < width; x += 2) {
      if (hole && x >= hole.x0 && x <= hole.x1 && y >= hole.y0 && y <= hole.y1) continue;
      const at = (y * width + x) * 4;
      if (data[at] + data[at + 1] + data[at + 2] > 250 && data[at + 2] > data[at] + 8) count += 1;
    }
    return count;
  };

  // THE FRAME IS THE RENDERER'S TO WRAP. Its own context reaches the frame — and
  // it is above the frame, so it is there before anything the renderer draws in it.
  assert.equal(await pane.locator('[data-harness-frame-context]').innerText(), 'frame:idle');

  // A LOAD THAT IS ONLY A DOWNLOAD SAYS NOTHING. Nothing of the load's extras is
  // passed, and nothing covers the model or stands over it.
  assert.equal(await overlay.count(), 0, 'a plain load covers nothing');
  assert.equal(await card.count(), 0, 'and raises nothing');

  // THE CUBE IS THE TOP-RIGHT CORNER'S: its 6rem box (square: one uniform scale; the cube, its axes and their letters)
  // 8px off the top and 2px from the right, and the bottom row is Quick Edit's alone: the tool stack stops clear of it.
  // The cube stands alone in its corner; View and Preview are the navbar's, at its right end, View left of Preview; the
  // strip is the tools alone, no rule. The bottom middle is the host's (a composer, on some).
  const frameBox = await canvasElement.boundingBox();
  const cubeBox = await pane.getByLabel('View cube', { exact: true }).boundingBox();
  const stackBox = await pane.locator('[data-cad-tool-groups]').boundingBox();
  const offTop = cubeBox.y - frameBox.y;
  assert.deepEqual([Math.round(cubeBox.width), Math.round(cubeBox.height)], [96, 96], 'the cube\'s box, 6rem square');
  assert.ok(Math.abs(offTop - 8) < 0.5, `the view cube sits 8px off the top: ${offTop}px`);
  const offRight = frameBox.x + frameBox.width - cubeBox.x - cubeBox.width;
  assert.ok(Math.abs(offRight - 2) < 0.5, `the view cube stands 2px from the right edge: ${offRight}px`);
  assert.ok(stackBox.y + stackBox.height <= frameBox.y + frameBox.height - 84 + 0.5, 'the tool stack stops clear of Quick Edit\'s row');
  assert.equal(await pane.locator('[data-cad-toolbar] [data-view-controls]').count(), 0, 'nothing of the view on the strip');
  assert.deepEqual(await pane.locator('[data-viewer-navbar] [data-navbar-view-controls] button').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label'))),
    ['View', 'Preview'], 'View and Preview, the navbar\'s');
  const [viewBox, previewBox] = [await pane.locator('[data-navbar-view-controls] [data-view-menu]').boundingBox(), await pane.locator('[data-view-preview]').boundingBox()];
  assert.ok(viewBox.x + viewBox.width <= previewBox.x && Math.abs(viewBox.y - previewBox.y) < 0.5, `View left of Preview, on its line: ${JSON.stringify({ viewBox, previewBox })}`);
  assert.equal(await pane.locator('[data-view-corner] *').count(), 0, 'the corner holds the cube alone');
  assert.equal(await pane.locator('[data-cad-toolbar] [data-strip-rule]').count(), 0, 'no rule on the strip');

  // FINDING: the wait before the file is even located covers the viewport, and says
  // so as such rather than as a phase of reading it.
  await stage('finding');
  await overlay.waitFor();
  assert.match(await overlay.innerText(), /Finding file/);
  assert.equal(await pane.locator('[data-harness-frame-context]').innerText(), 'frame:finding');

  // AN EDIT OF THE PERSON'S OWN is a wait with nothing downloading, and the model it
  // edits stays on screen: nothing covers it. The corner says the model is catching up.
  const updating = pane.locator('[data-view-update-status]');
  await stage('editing');
  await overlay.waitFor({ state: 'detached' });
  assert.equal(await card.count(), 0);
  await updating.waitFor();
  assert.match(await updating.innerText(), /Updating model/);
  // The strip is the top centre's, and the status sits under it, centred on it.
  const updateBox = await updating.boundingBox();
  const toolsBox = await pane.getByRole('group', { name: 'Interaction tools' }).boundingBox();
  const middleX = box => box.x + box.width / 2;
  assert.ok(Math.abs(middleX(toolsBox) - middleX(frameBox)) < 1, `the tool strip is at the top centre: ${JSON.stringify({ toolsBox, frameBox })}`);
  assert.ok(updateBox.y >= toolsBox.y + toolsBox.height && Math.abs(middleX(updateBox) - middleX(toolsBox)) < 1,
    `model update status sits under the tool strip, centred on it: ${JSON.stringify({ updateBox, toolsBox })}`);

  // THE BUILD ENDING ENDS IT: the saved file is on screen, so the wait is over.
  await stage('idle');
  await updating.waitFor({ state: 'detached' });
  const settled = await stillShot();
  assert.deepEqual([await overlay.count(), await card.count()], [0, 0]);
  const whole = triangle(settled);
  assert.ok(whole > 500, `the triangle is drawn: ${whole} samples of it`);

  // A FAILED UPDATE THE MODEL SURVIVES is an error, and the viewport is where it is said:
  // a card over the model — which is still drawn around it, neither blanked nor covered.
  await stage('failed');
  await card.waitFor();
  const said = await card.innerText();
  assert.match(said, /Harness update failed/);
  assert.match(said, /The existing model remains visible/);
  assert.equal(await overlay.count(), 0, 'it is not a load: nothing covers the model');
  const [canvasBox, cardBox] = [await canvasElement.boundingBox(), await card.boundingBox()];
  const hole = { x0: cardBox.x - canvasBox.x - 4, y0: cardBox.y - canvasBox.y - 4,
    x1: cardBox.x - canvasBox.x + cardBox.width + 4, y1: cardBox.y - canvasBox.y + cardBox.height + 4 };
  const around = triangle(settled, hole);
  assert.ok(around > 200, `there is triangle to see around the card: ${around}`);
  const survived = triangle(await shot(), hole);
  assert.ok(Math.abs(survived - around) <= around * 0.05, `and it is still drawn there: ${survived} of ${around}`);
  // DISMISS puts the card away, since the previous version is there to use: the card goes
  // and the whole model is on screen again.
  await card.getByRole('button', { name: 'Dismiss', exact: true }).click();
  await card.waitFor({ state: 'detached' });
  await shotWhere(frame => Math.abs(triangle(frame) - whole) <= whole * 0.05, 'showed the whole triangle under where the card was');
  // It stays put away while that alert stands; once the alert clears, the same failure
  // raised again (a retry that failed the same way) is shown again.
  await settle(page);
  assert.equal(await card.count(), 0, 'dismissed while the same alert stands');
  await stage('idle');
  await settle(page);
  assert.equal(await card.count(), 0);
  await stage('failed');
  await card.waitFor();
  assert.match(await card.innerText(), /Harness update failed/);
  await stage('idle');
  await card.waitFor({ state: 'detached' });

  // THE REVISION ON SCREEN. Live state reports what is being SHOWN, which a renderer
  // holding a predecessor over a rebuild knows and the shell does not.
  const shown = () => page.evaluate(() => { const s = window.cadHarness.a.controller.readState(); return [s.revision, s.resource.revision]; });
  assert.deepEqual(await shown(), ['harness', 'harness']);
  await pane.locator('[data-harness-shown-revision]').click();
  await page.waitForFunction(() => window.cadHarness.a.controller.readState().revision === 'shown-revision');
  assert.deepEqual(await shown(), ['shown-revision', 'shown-revision'], 'both halves name the revision on screen');

  // THE SNAPSHOT IS THE RENDERER'S TO ASSEMBLE. Its own reference vocabulary goes
  // through its own builder — and the resource it names is the one on screen.
  const before = await page.evaluate(() => window.cadHarness.captures.length);
  await page.evaluate(() => window.cadHarness.capture());
  await page.waitForFunction(count => window.cadHarness.captures.length > count, before);
  assert.deepEqual(await page.evaluate(() => {
    const context = window.cadHarness.captures.at(-1);
    return [context.type, context.references.map(reference => reference.resource.revision)];
  }), ['image/png', ['shown-revision']]);
  await pane.locator('[data-harness-shown-revision]').click();

  // A PRESS ON THE MODEL is the renderer's to hear: it puts down what it was
  // showing about something else before the viewport sees the press at all.
  assert.equal(await pane.locator('[data-harness-put-down]').innerText(), '');
  await page.mouse.click(middle.x, middle.y);
  await page.waitForFunction(() => document.querySelector('[data-harness-put-down]')?.textContent === 'put down @idle');
  // And the frame still takes focus on that same press, as it always did.
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.slot), 'cad-file-view');

  // Quick Edit is nowhere until something is picked; then it is the bar at the view's bottom, on the strip's centre
  // line, clear of the corner, a chat's input: its context row over its note, one line, which grows upward as it is
  // written, its bottom staying where it stands.
  const quickEdit = pane.getByRole('region', { name: 'Quick Edit', exact: true });
  assert.equal(await pane.locator('[data-quick-edit-box]').count(), 0, 'nothing picked: no Quick Edit, not even a button');
  await canvasElement.click({ button: 'right', position: { x: 300, y: 200 } });
  await page.getByRole('menuitem', { name: 'Note the press', exact: true }).click();
  await quickEdit.waitFor();
  await quickEdit.evaluate(node => Promise.all(node.getAnimations().map(animation => animation.finished)));
  const opened = await quickEdit.boundingBox();
  const stripBox = await pane.getByRole('group', { name: 'Interaction tools' }).boundingBox();
  assert.ok(Math.abs(opened.x + opened.width / 2 - (stripBox.x + stripBox.width / 2)) <= 1 && Math.abs(frameBox.y + frameBox.height - 16 - opened.y - opened.height) <= 1,
    `Quick Edit is the bar on the strip's line, 16px off the bottom: ${JSON.stringify([opened, stripBox, frameBox])}`);
  assert.ok(opened.width <= 480, 'never wider than 480px');
  const note = quickEdit.getByRole('textbox', { name: 'Describe your changes', exact: true });
  await note.click();
  await page.keyboard.type('One line.');
  for (const line of ['Two.', 'Three.']) { await page.keyboard.press('Shift+Enter'); await page.keyboard.type(line); }
  const grown = await quickEdit.boundingBox();
  assert.ok(grown.height >= opened.height + 39 && Math.abs(grown.y + grown.height - opened.y - opened.height) <= 1,
    `three lines, grown upward by two: ${opened.height} -> ${grown.height}`);
  assert.equal(await note.evaluate(element => element.innerText.split('\n').filter(Boolean).length), 3, 'real new lines');
  // Its X puts it away, the pick kept.
  await quickEdit.getByRole('button', { name: 'Close Quick Edit', exact: true }).click();
  await quickEdit.waitFor({ state: 'detached' });
  assert.deepEqual(errors, []);
});

test('an alert the model survives is drawn on the canvas, beside the docked panel and its tree', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.addInitScript(() => { window.Worker = undefined; });
  // A view wide enough for the panel to push the model aside (`sidebars.js`: the model keeps 600px).
  await page.setViewportSize({ width: 1200, height: 600 });
  await page.goto(`${origin}/?file=panel.harness`);
  await page.addStyleTag({ content: '#root > div { width: 1100px !important; }' });
  const pane = page.getByTestId('one');
  // The tree is the view's panel's, docked at the view's left, made as wide as it goes.
  const harnessTab = pane.locator('[data-flat-panel]').getByRole('tab', { name: 'Harness tree', exact: true });
  await pane.locator('[data-flat-panel] [role=tab], [data-flat-panel] [data-flat-panel-heading]').first().waitFor();
  if (await harnessTab.count()) await harnessTab.click();
  const tree = pane.locator('[data-flat-panel]');
  await pane.getByRole('separator', { name: 'Resize panel', exact: true }).press('End');
  // A failed update keeps the model, and with it the tools: the card stands on the canvas, the panel docked beside it untouched.
  await pane.locator('[data-harness-stage="failed"]').click();
  const card = pane.getByRole('alert');
  await card.waitFor();
  const [over, beside] = [await card.boundingBox(), await tree.boundingBox()];
  assert.ok(over.x >= beside.x + beside.width - 1, `the card is the canvas's, right of the panel: ${JSON.stringify({ over, beside })}`);
  const drawn = await page.evaluate(({ x, y }) => Boolean(document.elementFromPoint(x, y)?.closest('[role="alert"]')),
    { x: over.x + over.width / 2, y: over.y + over.height / 2 });
  assert.ok(drawn, 'the card is drawn where it stands');
  assert.deepEqual(errors, []);
});

// The one panel (`sidebars.js`): it always pushes the model aside, never over it; where open it would leave the model
// under 640px (872px of view, with its 232px) it starts collapsed (never written), and opened then it pushes.
test('the panel always pushes, and starts collapsed where the model would keep under 640px without writing it', async (t) => {
  const origin = await serve(t);
  const page = await browser.newPage({ viewport: { width: 1400, height: 640 } });
  t.after(() => page.close());
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/?file=panel.harness&store=session`);
  const pane = page.getByTestId('one');
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  const width = async value => {
    await page.locator('#root > div').first().evaluate((element, value) => element.style.setProperty('width', `${value}px`, 'important'), value);
    await settle(page);
    await settle(page);
  };
  const surface = pane.locator('[data-cad-surface]');
  const mode = () => surface.getAttribute('data-sidebar');
  const waitMode = value => page.waitForFunction(value => document.querySelector('[data-testid="one"] [data-cad-surface]')?.getAttribute('data-sidebar') === value, value);
  const kept = () => page.evaluate(() => sessionStorage.getItem('text-to-cad:tab:harness') || '');
  // The strip is centred on the whole view, whatever the panel does, and stands over the panel where they meet: what is
  // drawn at its centre is the strip, not the panel.
  const centredOnArea = () => page.evaluate(() => {
    const pane = document.querySelector('[data-testid="one"]');
    const view = pane.querySelector('[data-cad-surface]').getBoundingClientRect();
    const strip = pane.querySelector('[aria-label="Interaction tools"]').getBoundingClientRect();
    const on = document.elementFromPoint(strip.left + 6, strip.top + strip.height / 2);
    return Math.abs(strip.left + strip.width / 2 - (view.left + view.width / 2)) <= 1 && Boolean(on?.closest('[aria-label="Interaction tools"]'));
  });
  // The open panel is beside the stage, never over it; there is one.
  const besideStage = () => page.evaluate(() => {
    const pane = document.querySelector('[data-testid="one"]');
    const stage = pane.querySelector('[data-cad-canvas]').getBoundingClientRect();
    const open = [...pane.querySelectorAll('aside[data-panel-surface]:not([hidden])')];
    return open.length === 1 && open.every(aside => aside.getBoundingClientRect().right <= stage.left + 1);
  });
  // The panel's drawn width: one number at every view width, never the view's share.
  const drawnWidth = () => pane.locator('aside[data-flat-panel]').evaluate(aside => Math.round(aside.getBoundingClientRect().width));
  await width(1300);
  await waitMode('push');
  assert.ok(await centredOnArea(), 'pushed: the strip on the view\'s centre line');
  assert.ok(await besideStage());
  assert.equal(await drawnWidth(), 232);
  // Down to 872px it still pushes: the model keeps 640px beside the 232px panel.
  await width(872);
  await waitMode('push');
  assert.ok(await besideStage());
  assert.equal(await drawnWidth(), 232, 'a narrower view never narrows the panel');
  // Below it collapses on its own, unwritten, and wide again it opens on its own: with no choice on the file, it
  // follows the view across the line.
  await width(867);
  await waitMode('closed');
  assert.ok(!/"open":/.test(await kept()), 'what the width does is not kept');
  await width(1300);
  await waitMode('push');
  await width(700);
  await waitMode('closed');
  // Opened by the person in the narrow view: it pushes, and that choice holds (kept), narrower still or wide.
  await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').click();
  await waitMode('push');
  assert.ok(await besideStage(), 'opened in a narrow view, it pushes');
  assert.equal(await drawnWidth(), 232, 'opened in a narrow view, at its one width');
  assert.ok(await centredOnArea(), 'the strip stays on the view\'s centre, over the panel');
  assert.ok(/"open":true/.test(await kept()), 'the choice is kept');
  await page.keyboard.press('Escape');
  assert.equal(await mode(), 'push');
  // Its grip's bounds are fixed whatever the view: 200px and 480px, in a 700px view too; the width is kept.
  const grip = pane.getByRole('separator', { name: 'Resize panel' });
  assert.deepEqual([await grip.getAttribute('aria-valuemin'), await grip.getAttribute('aria-valuemax')], ['200', '480']);
  await grip.press('Home');
  await page.waitForFunction(() => Math.round(document.querySelector('[data-testid="one"] aside[data-flat-panel]').getBoundingClientRect().width) === 200);
  await grip.press('End');
  await page.waitForFunction(() => Math.round(document.querySelector('[data-testid="one"] aside[data-flat-panel]').getBoundingClientRect().width) === 480);
  await width(1300);
  assert.equal(await mode(), 'push');
  // A person's close is kept, and holds as the view widens; reopened, at the width it had.
  await pane.locator('[data-navbar-panel="left"]').click();
  assert.equal(await mode(), 'closed');
  assert.ok(/"open":false/.test(await kept()));
  await width(1400);
  assert.equal(await mode(), 'closed', 'closed by the person, a wide view leaves it closed');
  await pane.locator('[data-navbar-panel="left"]').click();
  await waitMode('push');
  assert.equal(await drawnWidth(), 480, 'reopened at the width it was dragged to');
  await pane.getByRole('separator', { name: 'Resize panel' }).press('Home');
  await grip.press('ArrowRight');
  await grip.press('ArrowRight');
  await page.waitForFunction(() => Math.round(document.querySelector('[data-testid="one"] aside[data-flat-panel]').getBoundingClientRect().width) === 232);
  await pane.locator('[data-navbar-panel="left"]').click();
  assert.equal(await mode(), 'closed');
  // A mouse resting on the toggle peeks it: over the view, the canvas the size it was and the camera where it was;
  // a click then pins it, and the canvas narrows by the panel's width, as it always has.
  const view = () => page.evaluate(() => {
    const pane = document.querySelector('[data-testid="one"]');
    const stage = pane.querySelector('[data-cad-canvas]').getBoundingClientRect(), canvas = pane.querySelector('canvas').getBoundingClientRect();
    const aside = pane.querySelector('aside[data-flat-panel]'), box = aside.hidden ? null : aside.getBoundingClientRect();
    // The camera to a millionth: a float's last digit may come out of a fresh read alone.
    const camera = window.__cadCamera(), round = value => Math.round(value * 1e6) / 1e6;
    return { stage: [stage.left, stage.width], canvas: [canvas.width, canvas.height],
      camera: camera && [...camera.position, ...(camera.target || []), camera.zoom, camera.aspect].map(round),
      over: Boolean(box && box.right > stage.left + 1 && document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)?.closest('aside[data-flat-panel]')) };
  });
  await page.mouse.move(700, 400);
  await settle(page);
  const before = await view();
  await pane.locator('[data-navbar-panel="left"]').hover();
  await pane.locator('aside[data-panel-peek]').waitFor();
  await settle(page);
  await settle(page);
  const peeked = await view();
  assert.deepEqual([peeked.stage, peeked.canvas, peeked.camera, peeked.over, await mode()], [before.stage, before.canvas, before.camera, true, 'closed'],
    `a peek pushes nothing: ${JSON.stringify({ before, peeked })}`);
  assert.ok(!/"open":true/.test(await kept()), 'a peek is kept nowhere');
  await pane.locator('[data-navbar-panel="left"]').click();
  await waitMode('push');
  await settle(page);
  const pinned = await view();
  assert.deepEqual([pinned.stage[0] - before.stage[0], before.canvas[0] - pinned.canvas[0], pinned.over], [232, 232, false], `pinned, it pushes: ${JSON.stringify(pinned)}`);
  assert.ok(/"open":true/.test(await kept()));
  assert.deepEqual(errors, []);
});

// The strip and Quick Edit's bar are centred on the whole view, always: no panel moves or narrows them, and where they
// meet the panel they stand over it, and take the press. The panel's tab scrolls as one.
test('the strip and Quick Edit stay centred on the view at 1440, 867 and 620 with the panel open, over it where they meet; the panel is one scroller', async (t) => {
  const origin = await serve(t);
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  t.after(() => page.close());
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${origin}/?file=panel.harness`);
  const pane = page.getByTestId('one');
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  // Something picked, so Quick Edit's bar is up.
  const canvas = pane.locator('[data-cad-canvas]').first();
  await canvas.click({ button: 'right', position: { x: 300, y: 200 } });
  await page.getByRole('menuitem', { name: 'Note the press', exact: true }).click();
  await pane.locator('[data-quick-edit-box]').waitFor();
  const read = () => page.evaluate(() => {
    const pane = document.querySelector('[data-testid="one"]');
    const view = pane.querySelector('[data-cad-surface]').getBoundingClientRect();
    const strip = pane.querySelector('[aria-label="Interaction tools"]').getBoundingClientRect();
    const bar = pane.querySelector('[data-quick-edit-box]').getBoundingClientRect();
    const panels = [...pane.querySelectorAll('aside[data-flat-panel]')].filter(aside => !aside.hidden).map(aside => aside.getBoundingClientRect());
    // Where the bar or the strip meets a panel, a press there reaches the bar or the strip.
    const meets = (box, selector) => panels.filter(panel => panel.left < box.right && panel.right > box.left).every(panel => {
      const x = Math.max(box.left, panel.left) + 4, y = box.top + box.height / 2;
      return Boolean(document.elementFromPoint(x, y)?.closest(selector));
    });
    return { view: view.left + view.width / 2, width: view.width, strip: strip.left + strip.width / 2, bar: bar.left + bar.width / 2, barWidth: bar.width,
      panels: panels.length, stripOver: meets(strip, '[aria-label="Interaction tools"]'), barOver: meets(bar, '[data-quick-edit-box]'),
      overlap: panels.some(panel => panel.left < bar.right && panel.right > bar.left) };
  });
  for (const width of [1440, 867, 620]) {
    await page.locator('#root > div').first().evaluate((element, width) => element.style.setProperty('width', `${width}px`, 'important'), width);
    await settle(page); await settle(page);
    // The panel open (a view that would leave the model under 640px starts it collapsed).
    const shut = pane.locator('[data-navbar-panel="left"][aria-expanded="false"]');
    if (await shut.count()) await shut.click();
    await settle(page);
    const at = await read();
    assert.ok(Math.abs(at.strip - at.view) <= 1, `${width}: the strip on the view's centre: ${JSON.stringify(at)}`);
    assert.ok(Math.abs(at.bar - at.view) <= 1, `${width}: Quick Edit on the view's centre: ${JSON.stringify(at)}`);
    assert.equal(Math.round(at.barWidth), Math.min(400, width - 32), `${width}: 400px at most, else the view's width less 16px a side`);
    assert.ok(at.panels > 0 && at.stripOver && at.barOver, `${width}: over the panel where they meet: ${JSON.stringify(at)}`);
    if (width === 620) assert.ok(at.overlap, 'at 620 the bar meets the panel, and stands over it');
  }
  // The panel: one scroller for its tabs; nothing in a tab scrolls on its own.
  await page.locator('#root > div').first().evaluate(element => element.style.setProperty('width', '1440px', 'important'));
  await page.setViewportSize({ width: 1500, height: 900 });
  await settle(page);
  const scrollers = await pane.locator('aside[data-flat-panel]').evaluate(aside => [...aside.querySelectorAll('*')]
    .filter(element => /(auto|scroll)/.test(getComputedStyle(element).overflowY) && !element.closest('[data-flat-panel-tabs]')).map(element => element.getAttribute('data-slot') || element.tagName));
  assert.deepEqual(scrollers, ['scroll-area-viewport'], `one scroller, the panel's: ${scrollers}`);
  assert.deepEqual(errors, []);
});

// Copy Prompt, Quick Edit's one action where the host takes no message (the web's), keeps its words at the bar's full
// 400px — its text and its icon side by side inside the button, beside the note — and drops them for its icon only
// where the window makes the bar narrower.
test('Copy Prompt keeps its words at the 400px bar and a phone\'s full-width one, and is its icon alone only where the window is narrower than the bar', async (t) => {
  const origin = await serve(t);
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  t.after(() => page.close());
  page.setDefaultTimeout(15000);
  await page.addInitScript(() => { window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`${origin}/?file=panel.harness`);
  const pane = page.getByTestId('one');
  await pane.getByRole('group', { name: 'Interaction tools' }).waitFor();
  await pane.locator('[data-cad-canvas]').first().click({ button: 'right', position: { x: 300, y: 200 } });
  await page.getByRole('menuitem', { name: 'Note the press', exact: true }).click();
  await pane.locator('[data-quick-edit-box]').waitFor();
  const read = () => pane.locator('[data-quick-edit-box]').evaluate(bar => {
    const actions = [...bar.querySelectorAll('[data-quick-edit-action]')];
    const button = bar.querySelector('[data-quick-edit-action="copy"]'), words = button.querySelector('span');
    const box = button.getBoundingClientRect(), text = words.getBoundingClientRect(), icon = button.querySelector('svg').getBoundingClientRect();
    return { actions: actions.length, bar: Math.round(bar.getBoundingClientRect().width), words: getComputedStyle(words).display !== 'none' && text.width > 0,
      inside: text.right <= box.right + 0.5 && icon.right <= text.left + 0.5, text: words.textContent };
  });
  // 400px on a desktop; a phone's (432px) the window's full width less 8px a side, uncapped.
  for (const [width, bar] of [[1440, 400], [432, 416]]) {
    await page.locator('#root > div').first().evaluate((element, width) => element.style.setProperty('width', `${width}px`, 'important'), width);
    await settle(page);
    assert.deepEqual(await read(), { actions: 1, bar, words: true, inside: true, text: 'Copy Prompt' }, `${width}: Copy Prompt in words`);
  }
  await page.locator('#root > div').first().evaluate(element => element.style.setProperty('width', '380px', 'important'));
  await settle(page);
  const narrow = await read();
  assert.deepEqual([narrow.bar < 400, narrow.words], [true, false], `a window narrower than the bar: the icon alone: ${JSON.stringify(narrow)}`);
});

// The panel is budgeted for three tabs: the widest three a model can have (Model, Params and Motion) and the search's icon
// fit the 232px panel in English, with no ⋯. A fourth (the qdd actuator's Joints) puts the tabs that do not fit in ⋯, in
// order, the open tab always shown, a tab chosen from it taking the last shown tab's place (`FlatPanel.jsx`'s `fitTabs`);
// at the grip's 200px the same. Measured as drawn: nothing in the row overlapping, cut or past the panel.
test('three tabs and the search fit the 232px panel with no ⋯; a fourth is ⋯\'s, the open tab still shown, at 232px and 200px; a phone\'s sheet draws the same tabs and rows', async (t) => {
  const origin = await serve(t);
  const { page, errors } = await newPage(t);
  await page.goto(`${origin}/?file=panel-qdd-three.harness`);
  const pane = page.getByTestId('one');
  await pane.locator('[data-flat-panel-tab="animation"]').waitFor();
  const head = () => pane.locator('aside[data-flat-panel]').evaluate(aside => {
    const box = aside.getBoundingClientRect(), row = aside.querySelector('[data-flat-panel-head]');
    const shown = [...row.querySelectorAll('[role=tab], [data-flat-panel-more], [data-flat-panel-search-open]')].map(node => node.getBoundingClientRect());
    const tabs = [...row.querySelectorAll('[role=tab]')];
    return { width: Math.round(box.width), tabs: tabs.map(tab => tab.getAttribute('data-flat-panel-tab')),
      names: tabs.map(tab => tab.querySelector('[data-flat-panel-tab-name]').textContent),
      more: Boolean(row.querySelector('[data-flat-panel-more]')), search: Boolean(row.querySelector('[data-flat-panel-search-open]')),
      apart: shown.every((rect, at) => at === 0 || shown[at - 1].right <= rect.left + 0.5),
      inside: shown.every(rect => rect.left >= box.left - 0.5 && rect.right <= box.left + aside.clientWidth + 0.5),
      whole: tabs.every(tab => tab.scrollWidth <= tab.clientWidth + 0.5) };
  });
  assert.deepEqual(await head(), { width: 232, tabs: ['tree', 'parameters', 'animation'], names: ['Model', 'Params', 'Motion'],
    more: false, search: true, apart: true, inside: true, whole: true });
  // Four tabs: ⋯ holds what does not fit, in order; the open tab (the first) shown; the last chosen from ⋯ takes the
  // last shown tab's place.
  await page.goto(`${origin}/?file=panel-qdd.harness`);
  await pane.locator('[data-flat-panel-tab="tree"]').waitFor();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-flat-panel-head] [data-flat-panel-more]'));
  const order = ['tree', 'parameters', 'position', 'animation'];
  const overflow = async (width, open) => {
    const now = await head();
    assert.deepEqual([now.width, now.more, now.search, now.apart, now.inside, now.whole, now.tabs.includes(open)], [width, true, true, true, true, true, true],
      `at ${width}px: ${JSON.stringify(now)}`);
    await page.locator('[data-flat-panel-more-menu]').waitFor({ state: 'detached' });
    await pane.locator('[data-flat-panel-more]').click();
    const held = await page.locator('[data-flat-panel-more-menu] [data-flat-panel-more-tab]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-flat-panel-more-tab')));
    assert.ok(held.length > 0 && held.every(id => !now.tabs.includes(id)), `⋯ holds the tabs not shown: ${JSON.stringify({ held, shown: now.tabs })}`);
    assert.deepEqual([...held].sort((a, b) => order.indexOf(a) - order.indexOf(b)), held, 'in the tabs\' order');
    assert.deepEqual([...now.tabs, ...held].sort(), [...order].sort(), 'every tab shown or in ⋯');
    return held;
  };
  await overflow(232, 'tree');
  await page.locator('[data-flat-panel-more-tab="animation"]').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-flat-panel-tab="animation"][aria-selected="true"]'));
  assert.equal((await head()).tabs.at(-1), 'animation', 'the tab chosen from ⋯ takes the last shown tab\'s place');
  await pane.getByRole('separator', { name: 'Resize panel' }).press('Home');
  await page.waitForFunction(() => Math.round(document.querySelector('[data-testid="one"] aside[data-flat-panel]').getBoundingClientRect().width) === 200);
  await overflow(200, 'animation');
  await page.keyboard.press('Escape');
  await page.locator('[data-flat-panel-more-menu]').waitFor({ state: 'detached' });
  await pane.getByRole('separator', { name: 'Resize panel' }).press('End');
  await page.waitForFunction(() => !document.querySelector('[data-testid="one"] [data-flat-panel-head] [data-flat-panel-more]'));
  // On a phone the panel is a sheet of the same components: a tree row's gap, glyph slot, actions (their gap, size and
  // inset) and a tab's size and type are the desktop's, only the row a finger's height (36px, its own); the four tabs
  // fit the sheet's head, with no ⋯.
  const geometry = () => page.evaluate(() => {
    const surface = [...document.querySelectorAll('[data-testid="one"] [data-panel-surface], [data-panel-sheet] [data-panel-surface]')].find(node => !node.hidden && node.getBoundingClientRect().width > 0);
    const row = surface.querySelector('[data-tree-row]'), actions = row.querySelector('[data-row-actions]'), [isolate, hide] = actions.querySelectorAll('button');
    const tab = surface.querySelector('[role=tab]');
    const size = node => { const r = node.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; };
    return { row: { gap: getComputedStyle(row).columnGap, glyph: size(row.querySelector('[data-tree-row-glyph]'))[0], actionsGap: getComputedStyle(actions).columnGap,
      between: Math.round(hide.getBoundingClientRect().left - isolate.getBoundingClientRect().right), button: size(isolate), inset: getComputedStyle(actions).paddingRight },
    height: Math.round(row.getBoundingClientRect().height), tab: [Math.round(tab.getBoundingClientRect().height), getComputedStyle(tab).paddingLeft, getComputedStyle(tab).fontSize],
    tabs: surface.querySelectorAll('[data-flat-panel-head] [role=tab]').length, more: Boolean(surface.querySelector('[data-flat-panel-more]')) };
  });
  await pane.locator('[data-flat-panel-tab="tree"]').click();
  const desktop = await geometry();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.locator('#root > div').first().evaluate(element => element.style.setProperty('width', '375px', 'important'));
  await page.waitForFunction(() => document.querySelector('[data-testid="one"] [data-cad-tool-groups]')?.hasAttribute('data-mobile'));
  await pane.locator('[data-navbar-panel="left"]').click();
  await page.locator('[data-panel-sheet] [data-tree-row]').first().waitFor();
  await settle(page);
  const phone = await geometry();
  assert.deepEqual([phone.row, phone.tab], [desktop.row, desktop.tab], `the phone's rows and tabs are the desktop's: ${JSON.stringify({ desktop, phone })}`);
  assert.deepEqual([desktop.height, phone.height, desktop.row.between, desktop.tabs, desktop.more, phone.tabs, phone.more], [28, 36, 2, 4, false, 4, false]);
  assert.equal(await page.locator('[data-panel-sheet] [data-flat-panel-head] button:not([role=tab]):not([data-flat-panel-search-open])').count(), 0, 'the sheet\'s head is the tabs and the search alone: no Back');
  assert.deepEqual(errors, []);
});
