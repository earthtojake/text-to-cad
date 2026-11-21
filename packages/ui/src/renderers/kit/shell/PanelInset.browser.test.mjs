import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { createServer } from 'node:http';
import { harnessBundle } from '../../harness/bundle.mjs';
import { chromium } from 'playwright';

// The view's panel's one horizontal line (`--panel-inset`, `styles/globals.css`): in a real layout, every tab of a STEP
// assembly with Parameters, Position and its Motion, a board, a DXF and a GLB, every piece of content's left edge (a
// text's first glyph, an icon, a control's box, a slider's track) stands on the inset, or a tree level's step past it,
// and every right-hand value, switch and slider ends the inset from the panel's right; the navbar's panel toggle's
// icon stands on the same column.
const require = createRequire(import.meta.url);
const XBF = join(dirname(require.resolve('@cad/core/lib/xbf/xbfDocument.js')), '__fixtures__');
const GLB = join(dirname(require.resolve('@cad/core/lib/render/glbMeshData.js')), 'fixtures');
const HINGE = JSON.parse(readFileSync(join(XBF, 'hinge', 'structure.json'), 'utf8'));
// The hinge (a base, an arm on a revolute elbow), given two parameters and a motion, as an engine model declares them.
HINGE.parameters = [
  { name: 'arm_length', value: 40, kind: 'float', min: 20, max: 80, step: 1, unit: 'mm', writable: true },
  { name: 'holes', value: 2, kind: 'int', min: 1, max: 6, step: 1, writable: true },
];
HINGE.kinematics.motions = { swing: { ease: 'cubic', keys: [{ t: 0, configuration: 'flat' }, { t: 1, configuration: 'raised' }] } };
const STRUCTURE = JSON.stringify(HINGE);
const LOOK = readFileSync(join(XBF, 'look.json'));
const ENVIRONMENT = Buffer.concat([Buffer.from('#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n'), Buffer.from([255, 255, 255, 128])]);
const BOARD = readFileSync(new URL('../../board/__fixtures__/board.plot.json', import.meta.url));
const DRAWING = readFileSync(new URL('../../dxf/__fixtures__/layered.drawing.json', import.meta.url));
const MESH = readFileSync(join(GLB, 'pair.slide.glb'));
const FILES = { 'hinge.step': 'step', 'blinky.kicad_pcb': 'kicad_pcb', 'layered.dxf': 'dxf', 'pair.glb': 'glb' };
const INSET = 16;

let server, browser;
before(async () => {
  const { bundle, css: harnessCss } = await harnessBundle();
  const css = await readFile(new URL('../../../../dist/styles.css', import.meta.url));
  const send = (response, type, body) => { response.setHeader('Content-Type', type); response.end(body); };
  const json = (response, body) => send(response, 'application/json', typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    const path = url.pathname, name = path.split('/').pop();
    if (path === '/harness.js') return send(response, 'text/javascript', bundle);
    if (path === '/styles.css') return send(response, 'text/css', css);
    if (path === '/harness.css') return send(response, 'text/css', harnessCss);
    const at = path.indexOf('/api/v1/');
    if (at < 0) {
      if (name === 'pair.glb') return send(response, 'model/gltf-binary', MESH);
      if (/\.(woff2|ttf)$/.test(path)) { response.statusCode = 404; return response.end(); }
      return send(response, 'text/html', '<!doctype html><html><head><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/harness.css"><style>body { margin: 0 } #root > div { width: 100vw !important; height: 100vh !important }</style></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>');
    }
    const rest = path.slice(at);
    if (rest === '/api/v1/documents' && request.method === 'GET') {
      return json(response, { documents: Object.entries(FILES).map(([file, kind]) => {
        const entry = { kind, file: `/models/${file}`, url: `/${file}`, hash: `h-${file}`, bytes: 4096 };
        return { entry, revision: entry.hash };
      }) });
    }
    if (rest === '/api/v1/documents' && request.method === 'POST') {
      let body = '';
      request.on('data', chunk => { body += chunk; });
      request.on('end', () => {
        const file = String(JSON.parse(body || '{}').path || '').split('/').pop();
        const kind = FILES[file] || 'step';
        response.statusCode = 201;
        json(response, { id: file, kind, api: `/api/v1/documents/${kind}/${file}` });
      });
      return;
    }
    if (rest === '/api/v1/server') return json(response, { backend: 'cadgen' });
    if (rest === '/api/v1/look') return json(response, LOOK);
    if (rest === '/api/v1/look/environment') return send(response, 'application/octet-stream', ENVIRONMENT);
    if (rest.endsWith('/version')) return json(response, { version: HINGE.version, patch: null });
    if (rest.endsWith('/structure')) return json(response, STRUCTURE);
    if (rest.endsWith('/plot')) return json(response, BOARD);
    if (rest.endsWith('/drawing')) return json(response, DRAWING);
    if (/\/parts\/[0-9a-f]+\/groups$/.test(rest)) return json(response, { faces: {}, edges: {} });
    const part = /\/parts\/([0-9a-f]+)$/.exec(rest);
    if (part) { try { return send(response, 'application/octet-stream', readFileSync(join(XBF, 'hinge', `${part[1]}.xbm`))); } catch { /* not a part */ } }
    response.statusCode = 404;
    json(response, { error: 'not found' });
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

// Every visible piece of the panel's content, measured where it is drawn: a text node's glyphs (a range round its
// trimmed text), an icon, a control (a field, a switch, a slider's track) and a box round a choice (a select's or a
// dropdown's trigger, a checkbox: its glyphs are inside it, so not measured). Each is `{ left, right, kind, text, depth,
// line, where, path }`, x from the panel's left; `depth` a tree row's level, `line` the row it is on (its top, rounded).
// A slider's thumb, which stands where its value puts it, is not measured.
function measurePanel() {
  const panel = document.querySelector('[data-testid="one"] [data-flat-panel]');
  const box = panel.getBoundingClientRect();
  const items = [];
  const shown = element => {
    for (let node = element; node && node !== panel; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.visibility === 'hidden' || style.display === 'none' || node.hidden || node.getAttribute('aria-hidden') === 'true' && style.visibility !== 'visible' && node.closest('[data-tab-ruler], [data-more-ruler]')) return false;
      if (node.classList.contains('invisible') || node.classList.contains('sr-only')) return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && rect.bottom > box.top && rect.top < box.bottom;
  };
  const depthOf = element => {
    const row = element.closest('[data-tree-row]');
    return row ? row.querySelectorAll(':scope > [data-tree-guide]').length : 0;
  };
  const push = (element, rect, kind, text = '') => items.push({ left: rect.left - box.left, right: rect.right - box.left, kind, text: text.slice(0, 40),
    depth: depthOf(element), line: Math.round(rect.top - box.top), where: element.closest('[data-flat-panel-head]') ? 'head' : 'body',
    path: [element.closest('[data-tree-row]') ? 'row' : '', element.closest('[data-flat-panel-tab]') ? 'tab' : ''].filter(Boolean).join(','),
    // Inside a button or a box: what its box holds, the box's edge the one on the line (a tab's name, Save's word, a
    // dropdown's choice).
    held: Boolean(element.closest('button, [role=combobox], [aria-haspopup]')) });
  const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent;
    if (!text.trim() || !shown(node.parentElement)) continue;
    if (node.parentElement.closest('input, textarea, [data-panel-grip]')) continue;
    const start = text.length - text.trimStart().length, end = text.trimEnd().length;
    const range = document.createRange();
    range.setStart(node, start);
    range.setEnd(node, end);
    const rects = [...range.getClientRects()].filter(rect => rect.width > 0);
    if (!rects.length) continue;
    const left = Math.min(...rects.map(rect => rect.left)), right = Math.max(...rects.map(rect => rect.right));
    push(node.parentElement, { left, right, top: rects[0].top }, 'text', text.trim());
  }
  const BOX = '[data-flat-panel-body] :is([role=combobox], [aria-haspopup=menu], [data-slot=checkbox])';
  // The search's field is no box (no border, fill or ring): its magnifier and its X are what stand on the insets.
  for (const element of panel.querySelectorAll(`svg, input:not([type=hidden]):not([type=range]):not([data-flat-panel-search] input), [role=switch], [data-slider-field-track], ${BOX}`)) {
    if (element.closest('svg') !== element && element.tagName.toLowerCase() !== 'svg' && element.closest('svg')) continue;
    if (element.tagName.toLowerCase() === 'svg' && element.parentElement.closest('svg')) continue;
    if (!shown(element)) continue;
    if (element.matches('svg') && element.parentElement.closest(BOX)) continue;
    const kind = element.matches('svg') ? 'icon' : element.matches('[data-slider-field-track]') ? 'track' : element.matches('[role=switch]') ? 'switch'
      : element.matches(BOX) ? 'box' : 'control';
    push(element, element.getBoundingClientRect(), kind, element.getAttribute('aria-label') || '');
  }
  return { width: box.width, clientWidth: panel.clientWidth, items };
}

const open = async (t, file, viewport = { width: 1280, height: 800 }) => {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  t.after(() => page.close().catch(() => {}));
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => { window.Worker = undefined; window.__cadPromptDestination = 'clipboard'; });
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=${file}`);
  const pane = page.getByTestId('one');
  await pane.locator('[data-navbar-panel="left"]').first().waitFor();
  if (await pane.locator('[data-navbar-panel="left"][aria-expanded="false"]').count()) await pane.locator('[data-navbar-panel="left"]').first().click();
  await pane.locator('[data-flat-panel]').waitFor();
  return { page, pane, errors };
};

/** Every tab's id, shown or in the row's ⋯; a single tab's panel answers one with no id. */
async function tabIds(pane) {
  return pane.locator('[data-flat-panel] [data-flat-panel-section], [data-flat-panel] [role=tabpanel]').evaluateAll(nodes =>
    [...new Set(nodes.map(node => node.getAttribute('data-flat-panel-section') || node.id.replace(/^flat-panel-body-/, '')).filter(Boolean))]);
}
async function chooseTab(page, pane, id) {
  const tab = pane.locator(`[data-flat-panel] [data-flat-panel-tab="${id}"]`);
  if (await tab.count()) { await tab.click(); return; }
  const more = pane.locator('[data-flat-panel] [data-flat-panel-more]');
  if (await more.count()) {
    await more.click();
    await page.locator(`[data-flat-panel-more-tab="${id}"]`).click();
  }
}
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));

// What the inset asks of one tab's measures (`--panel-inset`, 16px; a tree level 10px more): nothing left of its level's
// line or past the right inset (the panel's `clientWidth`, inside its 1px rule, less 16px); each line's first piece, in
// the panel's left half, on its level's line — a row's glyph slot, or its name 16px after an empty slot — but a box,
// which stands in its row's control column, and a right-aligned line; and every right-hand piece ends on the right inset: a switch, a slider's
// track, a box, and the last piece of a line in the right half (a row's last action, a value's unit, the head's last
// icon), but a word a button or a box holds, whose box stands on the line.
const LEVEL = 10, NAME = 16;
function offInset({ clientWidth, items }) {
  const right = clientWidth - INSET, near = (value, line) => Math.abs(value - line) <= 0.5;
  const off = [];
  for (const item of items) {
    const level = INSET + LEVEL * item.depth;
    if (item.left < level - 0.5 || item.right > right + 0.5) off.push(['outside the insets', item]);
    if (['switch', 'track', 'box'].includes(item.kind) && !near(item.right, right)) off.push(['not ending on the right inset', item]);
  }
  const lines = Map.groupBy(items.filter(item => item.kind !== 'box'), item => `${item.where}@${item.line}`);
  for (const line of lines.values()) {
    const last = line.filter(item => !item.held).reduce((a, b) => (b.right > a.right ? b : a), { right: -Infinity });
    if (last.left > clientWidth / 2 && !near(last.right, right)) off.push(['a line not ending on the right inset', last]);
    // A line of one text ending on the right inset is right-aligned (Parameters' status over Reset and Save).
    const first = line.reduce((a, b) => (b.left < a.left ? b : a));
    const level = INSET + LEVEL * first.depth, aligned = line.length === 1 && first.kind === 'text' && near(first.right, right);
    if (first.left < clientWidth / 2 && !aligned && !near(first.left, level) && !near(first.left, level + NAME)) off.push(['a line not starting on the inset', first]);
  }
  return off;
}

async function report(page, pane, label) {
  const ids = await tabIds(pane);
  const all = [];
  for (const id of ids.length ? ids : [null]) {
    if (id) await chooseTab(page, pane, id);
    await settle(page);
    const { width, clientWidth, items } = await page.evaluate(measurePanel);
    all.push({ tab: id, width, clientWidth, items });
  }
  // The search open, over the first tab it covers: its magnifier on the inset, its X's glyph ending on the right one.
  if (await pane.locator('[data-flat-panel-search-open]').count()) {
    await pane.locator('[data-flat-panel-search-open]').click();
    await pane.locator('[data-flat-panel-search] input').fill('a');
    await settle(page);
    const { width, clientWidth, items } = await page.evaluate(measurePanel);
    all.push({ tab: 'search', width, clientWidth, items });
    await page.keyboard.press('Escape');
    await pane.locator('[data-flat-panel-search]').waitFor({ state: 'detached' });
  }
  if (process.env.PANEL_INSET_DUMP) console.log(JSON.stringify({ label, all }, null, 1));
  return all;
}

for (const file of Object.keys(FILES)) {
  test(`${file}: the panel's content stands on the inset`, async t => {
    const { page, pane, errors } = await open(t, file);
    for (const { tab, clientWidth, items } of await report(page, pane, file)) {
      assert.ok(items.length > 0, `${file}, ${tab}: something measured`);
      assert.equal(clientWidth, 255, `${file}, ${tab}: the 256px panel, inside its 1px rule`);
      assert.deepEqual(offInset({ clientWidth, items }), [], `${file}, ${tab}: every piece on the inset`);
    }
    // The navbar's panel toggle's icon, over the panel, on the same line.
    const toggle = await page.evaluate(() => {
      const icon = document.querySelector('[data-testid="one"] [data-navbar-panel="left"] svg').getBoundingClientRect();
      return icon.left - document.querySelector('[data-testid="one"] [data-flat-panel]').getBoundingClientRect().left;
    });
    assert.ok(Math.abs(toggle - INSET) <= 0.5, `${file}: the navbar's toggle's icon at ${toggle}px`);
    // The collapsed panel peeking over the view (a mouse resting on its toggle) is the same panel, on the same lines.
    if (file === 'hinge.step') {
      // The surface's gaps to the view's frame (left, top, bottom): pinned it touches the edges; peeked it is a card
      // standing in from them, its content where the pinned panel's is.
      const gaps = () => page.evaluate(() => {
        const pane = document.querySelector('[data-testid="one"]'), frame = pane.querySelector('[data-cad-surface]').getBoundingClientRect();
        const surface = (pane.querySelector('[data-panel-peek-card]') ?? pane.querySelector('aside[data-flat-panel]')).getBoundingClientRect();
        return [surface.left - frame.left, surface.top - frame.top, frame.bottom - surface.bottom].map(value => Math.round(value * 2) / 2);
      });
      const pinned = await page.evaluate(measurePanel);
      assert.deepEqual(await gaps(), [0, 0, 0], 'pinned, the panel touches the frame\'s edges');
      // Closed by a click, the pointer still on the toggle: it peeks only once the pointer comes to rest on it again.
      await pane.locator('[data-navbar-panel="left"]').click();
      await page.mouse.move(900, 600);
      await pane.locator('[data-navbar-panel="left"]').hover();
      await pane.locator('aside[data-panel-peek]').waitFor();
      await settle(page);
      const peeked = await page.evaluate(measurePanel);
      assert.deepEqual([peeked.clientWidth, offInset(peeked)], [255, []], 'the peeked panel on the inset');
      assert.ok((await gaps()).every(gap => gap >= 2), `peeked, a card clear of the frame's edges: ${await gaps()}`);
      // The same tab's content, where the pinned panel drew it.
      const at = ({ items }) => items.filter(item => item.where === 'body' || item.path === 'tab').map(item => [item.text, item.kind, Math.round(item.left * 2) / 2, item.line]);
      assert.deepEqual(at(peeked), at(pinned), 'nothing in the peeked panel moves');
    }
    assert.deepEqual(errors, []);
  });
}
