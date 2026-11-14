import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { chromium } from 'playwright';
import { PNG } from 'pngjs';
import { harnessBundle } from '../harness/bundle.mjs';

// A field as the engine answers one (`GET /api/v1/documents/gsl/<id>/field`), written by hand so the
// test needs no gsl: a ball about the origin whose radius is a slider, its march the ray's own
// intersection with it. The shape is omega's (`gsl eval`'s shader): a library with no entry point,
// one std140 block for time and the sliders, each with the byte it sits at.
const LIBRARY = `
struct gsl_Host { float time; float r; };
layout(std140) uniform gsl_Host_block_0Fragment { gsl_Host gsl_host; };
struct gsl_shape { float distance_; uint shapeIndex; };
struct gsl_hit { bool hit; float t; uint shapeIndex; vec3 gradient; };
gsl_shape gsl_field(vec3 p) { return gsl_shape(length(p) - gsl_host.r, 1u); }
gsl_hit gsl_march(vec3 origin, vec3 direction, float tEntry, float tExit, float pixelScale, float ortho, float stepScale, vec4 detail) {
  float b = dot(origin, direction);
  float d = b * b - (dot(origin, origin) - gsl_host.r * gsl_host.r);
  if (d < 0.0) { return gsl_hit(false, tExit, 0u, vec3(0.0)); }
  float t = -b - sqrt(d);
  if (t < max(tEntry, 0.0) || t > tExit) { return gsl_hit(false, tExit, 0u, vec3(0.0)); }
  return gsl_hit(true, t, 1u, normalize(origin + direction * t));
}
`;
const field = (overrides = {}) => ({
  schema: 1, key: 'k1', target: 'glsl-es300', code: LIBRARY, entry: { field: 'gsl_field', march: 'gsl_march' },
  uniformBlock: 'gsl_Host_block_0Fragment', blockBytes: 16,
  uniforms: [{ name: 'time', type: 'f32', offset: 0, value: [0] }],
  sliders: [{ name: 'r', uniform: 'r', type: 'f32', offset: 4, value: 6, min: 2, max: 18 }],
  textures: [], bodies: [{ name: 'ball', index: 1 }], region: [-20, -20, -20, 20, 20, 20], ...overrides
});

// What the routes answer now, and what was asked of them.
let served = { status: 200, body: field() };
const HARNESS_SIZE = '<style>#root > div { width: 800px !important; height: 500px !important; }</style>';
let server, browser;
const requests = [];
before(async () => {
  const { bundle } = await harnessBundle();
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  server = createServer((request, response) => {
    const url = new URL(request.url, 'http://test');
    requests.push(`${request.method} ${url.pathname.replace(/^\/(?:one|two)\b/, '')}`);
    const json = (status, body) => { response.statusCode = status; response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(body)); };
    if (url.pathname === '/harness.js') { response.setHeader('Content-Type', 'text/javascript'); response.end(bundle); }
    else if (url.pathname === '/styles.css') { response.setHeader('Content-Type', 'text/css'); response.end(css); }
    else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'POST') json(201, { id: 'ball', kind: 'gsl', api: '/api/v1/documents/gsl/ball' });
    else if (url.pathname.endsWith('/api/v1/documents/gsl/ball/field')) json(served.status, served.body);
    else if (url.pathname.endsWith('/api/v1/documents') && request.method === 'GET') {
      const entry = { kind: 'gsl', file: '/models/ball.gsl', url: '/ball.gsl', hash: `ball-${served.body.key || 'none'}`, bytes: 80 };
      json(200, { documents: [{ entry, revision: entry.hash }] });
    } else if (url.pathname.endsWith('/api/v1/server')) json(200, { backend: 'cadgen' });
    else { response.setHeader('Content-Type', 'text/html'); response.end(`<!doctype html><html><head><title>Host title</title><link rel="stylesheet" href="/styles.css">${HARNESS_SIZE}</head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>`); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true, args: (process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1')
    ? ['--use-angle=metal'] : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
});

async function open(t) {
  const page = await browser.newPage({ viewport: { width: 800, height: 500 }, deviceScaleFactor: 1 });
  t.after(() => page.close());
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error' && /shader|WebGL|GLSL/i.test(message.text())) errors.push(message.text()); });
  await page.addInitScript(() => {
    window.Worker = undefined;
    for (const name of ['localStorage', 'sessionStorage']) {
      Object.defineProperty(window, name, { get() { throw new Error(`Renderer accessed ${name}`); } });
    }
  });
  requests.length = 0;
  await page.goto(`http://127.0.0.1:${server.address().port}/?file=ball.gsl`);
  return { page, errors, pane: page.getByTestId('one') };
}
const ready = pane => pane.locator('[aria-busy="false"] > div > canvas').first().waitFor();
// The viewport's own pixels, without any chrome over them: what a host capture returns.
async function capture(page) {
  const encoded = await page.evaluate(async () => {
    const blob = await window.cadHarness.a.controller.capture();
    const data = new Uint8Array(await blob.arrayBuffer());
    let binary = ''; for (const byte of data) binary += String.fromCharCode(byte);
    return btoa(binary);
  });
  return PNG.sync.read(Buffer.from(encoded, 'base64'));
}
// How much of the picture the field covers: the pixels that are not the stage's own colour, which a
// corner of the view shows (the stage draws no grid or ground under a field's first look).
function covered(image) {
  const stage = image.data.subarray(0, 3);
  let drawn = 0;
  for (let index = 0; index < image.data.length; index += 4) {
    if (Math.abs(image.data[index] - stage[0]) + Math.abs(image.data[index + 1] - stage[1]) + Math.abs(image.data[index + 2] - stage[2]) > 24) drawn += 1;
  }
  return drawn / (image.width * image.height);
}
const pixel = (image, x, y) => { const at = (Math.round(y) * image.width + Math.round(x)) * 4; return [...image.data.subarray(at, at + 3)]; };

test('a GSL model is drawn as its field, marched in the view, at the middle of the stage', async (t) => {
  served = { status: 200, body: field() };
  const { page, errors, pane } = await open(t);
  await ready(pane);
  const image = await capture(page);
  const share = covered(image);
  assert.ok(share > 0.004 && share < 0.5, `the ball covers a part of the view: ${share}`);
  // The ball is about the origin, which the view frames at its middle; a corner is the stage alone.
  const middle = pixel(image, image.width / 2, image.height / 2);
  const corner = pixel(image, 12, 12);
  assert.ok(middle.some((value, channel) => Math.abs(value - corner[channel]) > 12), `the middle of the view is the ball, not the stage: ${middle} against ${corner}`);
  // It is shaded by the field's gradient: lit from above, so its top is brighter than its underside.
  const top = pixel(image, image.width / 2, image.height / 2 - 18), under = pixel(image, image.width / 2, image.height / 2 + 26);
  assert.ok(top[0] > under[0] + 8, `the top is lit and the underside is not: ${top} against ${under}`);
  assert.deepEqual(errors, []);
  // One tool, Select, in hand; nothing a mesh's settings act on.
  assert.deepEqual(await pane.getByRole('group', { name: 'Interaction tools' }).getByRole('button')
    .evaluateAll(buttons => buttons.filter(button => button.hasAttribute('aria-pressed') && !button.closest('[data-view-controls]')).map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`)),
  ['Select:true']);
  assert.equal(requests.filter(request => request.endsWith('/field')).length, 1, 'the field is read once');
});

test('a slider moves the field at once, by a number in its block, and asks the server for nothing', async (t) => {
  served = { status: 200, body: field() };
  const { page, errors, pane } = await open(t);
  await ready(pane);
  const before = covered(await capture(page));
  // The model's sliders are the view's panel's Parameters tab.
  await pane.getByRole('button', { name: 'Show panel' }).click();
  const slider = pane.getByRole('slider', { name: 'r' });
  await slider.waitFor();
  assert.deepEqual([await slider.getAttribute('aria-valuemin'), await slider.getAttribute('aria-valuemax'), await slider.getAttribute('aria-valuenow')], ['2', '18', '6']);
  requests.length = 0;
  await slider.focus();
  await page.keyboard.press('End');
  await page.waitForFunction(() => document.querySelector('[data-field-parameter="r"] [data-slider-field-value]')?.value === '18');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const after = covered(await capture(page));
  assert.ok(after > before * 4, `a radius three times as large covers far more of the view: ${before} -> ${after}`);
  assert.deepEqual(requests.filter(request => /field|documents/.test(request) && !request.startsWith('GET /api/v1/documents')), [], 'no request for the move');
  assert.deepEqual(errors, []);
});

test('a model gsl does not compile says why, in gsl\'s words', async (t) => {
  served = { status: 400, body: { error: '3:8: undefined identifier: nothing_named_this', hint: 'fix the model as gsl says' } };
  const { pane } = await open(t);
  await pane.getByText(/nothing_named_this/).first().waitFor();
});
