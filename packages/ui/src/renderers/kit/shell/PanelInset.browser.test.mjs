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
// trimmed text), an icon, a control (a field, a switch, a select's trigger, a slider's track). Each is `{ left, right,
// kind, text, depth, line }`, x from the panel's left; `depth` a tree row's level, `line` the row it is on (its top,
// rounded), `end` whether it is a right-hand value (a switch, a value's field, a row's last action, a select's chevron).
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
    path: [element.closest('[data-tree-row]') ? 'row' : '', element.closest('[data-flat-panel-tab]') ? 'tab' : ''].filter(Boolean).join(',') });
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
  for (const element of panel.querySelectorAll('svg, input:not([type=hidden]):not([type=range]), [role=switch], [role=combobox], [data-slider-field-track], [role=slider]')) {
    if (element.closest('svg') !== element && element.tagName.toLowerCase() !== 'svg' && element.closest('svg')) continue;
    if (element.tagName.toLowerCase() === 'svg' && element.parentElement.closest('svg')) continue;
    if (!shown(element)) continue;
    if (element.matches('[role=slider]') && element.closest('[data-slider-field-track]')) continue;
    const kind = element.matches('svg') ? 'icon' : element.matches('[data-slider-field-track]') ? 'track' : element.matches('[role=switch]') ? 'switch' : 'control';
    push(element, element.getBoundingClientRect(), kind, element.getAttribute('aria-label') || '');
  }
  return { width: box.width, items };
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

async function report(page, pane, label) {
  const ids = await tabIds(pane);
  const all = [];
  for (const id of ids.length ? ids : [null]) {
    if (id) await chooseTab(page, pane, id);
    await settle(page);
    const { width, items } = await page.evaluate(measurePanel);
    all.push({ tab: id, width, items });
    if (process.env.PANEL_INSET_SHOTS) await pane.locator('[data-flat-panel]').screenshot({ path: `${process.env.PANEL_INSET_SHOTS}/${label}-${id || 'one'}.png` });
  }
  if (process.env.PANEL_INSET_DUMP) console.log(JSON.stringify({ label, all }, null, 1));
  return all;
}

for (const file of Object.keys(FILES)) {
  test(`${file}: the panel's content stands on the inset`, async t => {
    const { page, pane } = await open(t, file);
    await report(page, pane, file);
  });
}
